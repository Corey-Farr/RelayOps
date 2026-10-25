from datetime import timedelta
from sqlalchemy import and_, exists, or_, select
from relayops.core.config import settings
from relayops.core.db import Session
from relayops.models import Attempt, Delivery, DispatchStart, Event, Policy, Pool, Worker, now
from relayops.observability import telemetry as metrics
from relayops.services.policy import retry_delay, retryable


async def claim(worker_id: str, region: str, limit: int):
    cfg = settings()
    timestamp = now()
    exhausted = 0
    async with Session.begin() as db:
        pool = await db.get(Pool, region)
        if not pool or pool.paused:
            return []
        healthy_owner = exists(
            select(Worker.id)
            .join(Pool, Pool.region == Worker.region)
            .where(
                Worker.region == Delivery.region,
                Worker.last_heartbeat > timestamp - timedelta(seconds=cfg.failover_seconds),
                Worker.state == "running",
                Pool.paused.is_(False),
            )
        )
        available = or_(
            and_(Delivery.status.in_(["pending", "retry_wait"]), Delivery.next_attempt_at <= timestamp),
            and_(Delivery.status == "leased", Delivery.lease_until < timestamp),
        )
        routing = or_(Delivery.region == region, ~healthy_owner)
        with metrics.tracer.start_as_current_span("delivery.claim"):
            jobs = (
                await db.scalars(
                    select(Delivery)
                    .where(available, routing)
                    .order_by(Delivery.next_attempt_at, Delivery.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            claimed = []
            for job in jobs:
                policy = await db.get(Policy, job.policy_id)
                if policy is None:
                    raise RuntimeError("Delivery policy no longer exists")
                if job.cycle_attempt_count >= policy.max_attempts:
                    job.status = "dead_letter"
                    job.lease_owner = None
                    job.lease_until = None
                    job.lease_version += 1
                    exhausted += 1
                    continue
                job.status = "leased"
                job.lease_owner = worker_id
                job.lease_version += 1
                job.lease_until = timestamp + timedelta(seconds=cfg.lease_seconds)
                job.attempt_count += 1
                job.cycle_attempt_count += 1
                claimed.append(job)
    # Recovery can exhaust a delivery without another HTTP result. Count only
    # committed transitions, just as complete() does for observed outcomes.
    if exhausted:
        metrics.dead.labels(region).inc(exhausted)
    return claimed


async def begin_dispatch(job, started_at, trace_id: str):
    """Fence before I/O and leave evidence if the process dies before completion."""
    async with Session.begin() as db:
        current = await db.scalar(select(Delivery).where(Delivery.id == job.id).with_for_update())
        if (
            current is None
            or current.status != "leased"
            or current.lease_owner != job.lease_owner
            or current.lease_version != job.lease_version
            or current.lease_until is None
            or current.lease_until <= now()
        ):
            return False
        existing = await db.scalar(
            select(DispatchStart.id).where(
                DispatchStart.delivery_id == job.id, DispatchStart.lease_version == job.lease_version
            )
        )
        if existing:
            return False
        db.add(
            DispatchStart(
                delivery_id=job.id,
                lease_version=job.lease_version,
                number=job.attempt_count,
                worker_id=job.lease_owner,
                region=settings().worker_region,
                started_at=started_at,
                trace_id=trace_id,
            )
        )
    return True


async def complete(
    job,
    status: int | None,
    category: str | None,
    duration_ms: float,
    started_at,
    retry_after: str | None,
    policy,
    trace_id: str,
):
    finished = now()
    async with Session.begin() as db:
        # Persist every observed real HTTP outcome, including stale workers, but never
        # let stale workers mutate queue state or count a stale result as delivered.
        db.add(
            Attempt(
                delivery_id=job.id,
                number=job.attempt_count,
                worker_id=job.lease_owner,
                region=settings().worker_region,
                started_at=started_at,
                ended_at=finished,
                duration_ms=duration_ms,
                http_status=status,
                failure_category=category,
                error=category,
                trace_id=trace_id,
            )
        )
        current = await db.scalar(select(Delivery).where(Delivery.id == job.id).with_for_update())
        if current is None:
            raise RuntimeError("Claimed delivery no longer exists")
        if (
            current.lease_version != job.lease_version
            or current.lease_owner != job.lease_owner
            or current.status != "leased"
        ):
            return False
        region = settings().worker_region
        if status is not None and 200 <= status < 300:
            current.status = "delivered"
            current.delivered_at = finished
            event = await db.get(Event, job.event_id)
            if event is None:
                raise RuntimeError("Delivery event no longer exists")
            elapsed = (finished - event.created_at).total_seconds()
        elif retryable(status) and current.cycle_attempt_count < policy.max_attempts:
            with metrics.tracer.start_as_current_span("delivery.retry_schedule"):
                current.status = "retry_wait"
                current.next_attempt_at = finished + timedelta(
                    seconds=retry_delay(
                        current.cycle_attempt_count, policy.backoff_base, policy.backoff_cap, retry_after
                    )
                )
        else:
            current.status = "dead_letter"
        current.lease_owner = None
        current.lease_until = None
        outcome = current.status
    if outcome == "delivered":
        metrics.succeeded.labels(region).inc()
        metrics.e2e_duration.labels(region).observe(elapsed)
    elif outcome == "retry_wait":
        metrics.retries.labels(region).inc()
    else:
        metrics.dead.labels(region).inc()
    return True


async def redrive(db, identifier: str):
    # Serialize with ingestion capacity; maintain monotonic attempt history and fencing.
    from sqlalchemy import func, text
    from fastapi import HTTPException
    from relayops.services.policy import ACTIVE

    await db.execute(text("SELECT pg_advisory_xact_lock(7319201)"))
    job = await db.scalar(select(Delivery).where(Delivery.id == identifier).with_for_update())
    if not job:
        raise HTTPException(404, "Delivery not found")
    if job.status != "dead_letter":
        raise HTTPException(409, "Only dead-letter deliveries may be redriven")
    depth = await db.scalar(select(func.count()).select_from(Delivery).where(Delivery.status.in_(ACTIVE)))
    if depth >= settings().max_queue_depth:
        raise HTTPException(429, "Delivery queue capacity exhausted")
    job.status = "pending"
    job.next_attempt_at = now()
    job.lease_version += 1
    job.cycle_attempt_count = 0
    # Start a bounded retry cycle without resetting historical attempt numbers.
    return job
