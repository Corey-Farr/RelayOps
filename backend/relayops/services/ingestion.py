import hashlib
import json
from fastapi import HTTPException
from opentelemetry.propagate import inject
from sqlalchemy import func, select, text
from relayops.core.config import settings
from relayops.models import Control, Delivery, Destination, Event, Project, uid
from relayops.observability.telemetry import tracer
from relayops.services.policy import ACTIVE, choose_policy, region_for


async def ingest(db, project_id: str, event_type: str, payload: dict, key: str):
    if not key or len(key) > 200:
        raise HTTPException(422, "Idempotency-Key must contain 1..200 characters")
    canonical = json.dumps(
        {"type": event_type, "payload": payload}, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    if len(canonical.encode()) > settings().max_payload_bytes:
        raise HTTPException(413, "Payload exceeds configured limit")
    fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
    # One short transaction-level advisory lock serializes capacity checks and acceptance.
    # Duplicate checks precede capacity rejection; uniqueness also exists in PostgreSQL.
    await db.execute(text("SELECT pg_advisory_xact_lock(7319201)"))
    existing = await db.scalar(
        select(Event).where(Event.project_id == project_id, Event.idempotency_key == key)
    )
    if existing:
        if existing.payload_hash != fingerprint:
            raise HTTPException(409, "Idempotency key conflicts with a different event")
        return existing, False
    if not await db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    destinations = (
        await db.scalars(
            select(Destination).where(Destination.project_id == project_id, Destination.enabled.is_(True))
        )
    ).all()
    destinations = [d for d in destinations if "*" in d.event_types or event_type in d.event_types]
    depth = await db.scalar(select(func.count()).select_from(Delivery).where(Delivery.status.in_(ACTIVE)))
    if depth + len(destinations) > settings().max_queue_depth:
        from relayops.observability.telemetry import backpressure

        backpressure.inc()
        raise HTTPException(429, "Delivery queue capacity exhausted", headers={"Retry-After": "5"})
    control = await db.get(Control, 1)
    if not control:
        raise HTTPException(503, "Run bootstrap before ingesting events")
    carrier: dict[str, str] = {}
    inject(carrier)
    event = Event(
        project_id=project_id,
        type=event_type,
        payload=payload,
        idempotency_key=key,
        payload_hash=fingerprint,
        trace_context=carrier,
    )
    with tracer.start_as_current_span("event.persist"):
        db.add(event)
        await db.flush()
        for destination in destinations:
            identifier = uid()
            db.add(
                Delivery(
                    id=identifier,
                    event_id=event.id,
                    destination_id=destination.id,
                    region=region_for(identifier),
                    policy_id=choose_policy(
                        identifier, control.stable_id, control.candidate_id, control.canary_percent
                    ),
                )
            )
        await db.flush()
    return event, True
