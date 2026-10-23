import asyncio
from collections import defaultdict, deque
from datetime import timedelta
import time
import httpx
from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from relayops.core.config import settings
from relayops.core.db import session
from relayops.models import (
    APIKey,
    Attempt,
    Audit,
    Control,
    Delivery,
    Destination,
    Event,
    Incident,
    LoginSession,
    Policy,
    Pool,
    Project,
    User,
    Worker,
    now,
    uid,
)
from relayops.observability import telemetry as metrics
from relayops.schemas import (
    DestinationIn,
    DestinationPatch,
    EventIn,
    GenerateIn,
    LoginIn,
    NameIn,
    PolicyIn,
    ScenarioIn,
)
from relayops.security.auth import admin, identity, ingest_identity, operator
from relayops.security.crypto import digest, encrypt, passwords, token, validate_destination
from relayops.services.ingestion import ingest
from relayops.services.monitoring import overview
from relayops.services.queue import redrive
from relayops.services.serialization import delivery_json, event_json, serialize

metrics.setup("relayops-api")
app = FastAPI(title="RelayOps", version="0.1.0")
FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready,metrics")
login_attempts: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def request_bounds(request, call_next):
    # Stream-count before parsing; Content-Length alone can be omitted or dishonest.
    if request.method in {"POST", "PUT", "PATCH"}:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > settings().max_payload_bytes + 4096:
                return JSONResponse({"detail": "Request exceeds payload limit"}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse({"detail": "Resource conflicts with existing data"}, status_code=409)


def audit(db, user, action, resource, details=None):
    db.add(Audit(actor=user.email, action=action, resource=str(resource), details=details or {}))


async def required(db, model, identifier):
    value = await db.get(model, identifier)
    if not value:
        raise HTTPException(404, "Resource not found")
    return value


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready(db=Depends(session)):
    await db.execute(text("SELECT 1"))
    if not await db.get(Control, 1):
        raise HTTPException(503, "Bootstrap required")
    return {"status": "ready"}


@app.get("/metrics")
async def prometheus(db=Depends(session)):
    from relayops.services.policy import ACTIVE

    metrics.queue.set(
        await db.scalar(select(func.count()).select_from(Delivery).where(Delivery.status.in_(ACTIVE)))
    )
    metrics.inflight.set(
        await db.scalar(select(func.count()).select_from(Delivery).where(Delivery.status == "leased"))
    )
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/auth/login")
async def login(body: LoginIn, request: Request, response: Response, db=Depends(session)):
    host = request.client.host if request.client else "unknown"
    clock = time.monotonic()
    attempts = login_attempts[host]
    while attempts and attempts[0] < clock - 60:
        attempts.popleft()
    if len(attempts) >= 10:
        raise HTTPException(429, "Too many login attempts", headers={"Retry-After": "60"})
    attempts.append(clock)
    user = await db.scalar(select(User).where(User.email == body.email))
    valid = False
    if user:
        try:
            valid = await asyncio.to_thread(passwords.verify, user.password_hash, body.password)
        except VerificationError:
            pass
    if not valid:
        raise HTTPException(401, "Invalid email or password")
    raw = token()
    csrf = token()
    db.add(
        LoginSession(
            id=digest(raw),
            user_id=user.id,
            csrf=csrf,
            expires_at=now() + timedelta(hours=settings().session_hours),
        )
    )
    audit(db, user, "login", user.id)
    await db.commit()
    response.set_cookie(
        "relayops_session",
        raw,
        httponly=True,
        secure=settings().app_env == "production",
        samesite="strict",
        max_age=settings().session_hours * 3600,
        path="/",
    )
    return {"user": serialize(user, ("password_hash",)), "csrf_token": csrf}


@app.get("/api/auth/me")
async def me(request: Request, user=Depends(identity)):
    return {"user": serialize(user, ("password_hash",)), "csrf_token": request.state.csrf}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response, user=Depends(identity), db=Depends(session)):
    saved = await db.get(LoginSession, digest(request.cookies["relayops_session"]))
    await db.delete(saved)
    audit(db, user, "logout", user.id)
    await db.commit()
    response.delete_cookie("relayops_session", path="/")
    return {"ok": True}


@app.get("/api/projects")
async def projects(user=Depends(identity), db=Depends(session)):
    return [serialize(p) for p in (await db.scalars(select(Project).order_by(Project.created_at))).all()]


@app.post("/api/projects", status_code=201)
async def create_project(body: NameIn, user=Depends(admin), db=Depends(session)):
    project = Project(name=body.name)
    db.add(project)
    await db.flush()
    audit(db, user, "project.create", project.id)
    await db.commit()
    return serialize(project)


@app.get("/api/projects/{project_id}/keys")
async def keys(project_id: str, user=Depends(admin), db=Depends(session)):
    return [
        serialize(k, ("digest",))
        for k in (await db.scalars(select(APIKey).where(APIKey.project_id == project_id))).all()
    ]


@app.post("/api/projects/{project_id}/keys", status_code=201)
async def create_key(project_id: str, body: NameIn, user=Depends(admin), db=Depends(session)):
    await required(db, Project, project_id)
    raw = "ro_" + token()
    key = APIKey(project_id=project_id, name=body.name, prefix=raw[:10], digest=digest(raw))
    db.add(key)
    await db.flush()
    audit(db, user, "key.create", key.id)
    await db.commit()
    return {"id": key.id, "key": raw}


@app.delete("/api/keys/{identifier}")
async def revoke_key(identifier: str, user=Depends(admin), db=Depends(session)):
    key = await required(db, APIKey, identifier)
    key.revoked_at = now()
    audit(db, user, "key.revoke", identifier)
    await db.commit()
    return {"ok": True}


@app.get("/api/destinations")
async def destinations(project_id: str | None = None, user=Depends(identity), db=Depends(session)):
    query = select(Destination)
    if project_id:
        query = query.where(Destination.project_id == project_id)
    return [serialize(d, ("secret_encrypted",)) for d in (await db.scalars(query)).all()]


@app.post("/api/destinations", status_code=201)
async def create_destination(body: DestinationIn, user=Depends(operator), db=Depends(session)):
    await required(db, Project, body.project_id)
    try:
        validate_destination(body.url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    secret = body.signing_secret or token()
    destination = Destination(**body.model_dump(exclude={"signing_secret"}), secret_encrypted=encrypt(secret))
    db.add(destination)
    await db.flush()
    audit(db, user, "destination.create", destination.id)
    await db.commit()
    return {**serialize(destination, ("secret_encrypted",)), "signing_secret": secret}


@app.patch("/api/destinations/{identifier}")
async def patch_destination(
    identifier: str, body: DestinationPatch, user=Depends(operator), db=Depends(session)
):
    destination = await required(db, Destination, identifier)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(destination, key, value)
    audit(db, user, "destination.update", identifier, body.model_dump(exclude_none=True))
    await db.commit()
    return serialize(destination, ("secret_encrypted",))


@app.post("/api/events")
async def create_event(
    body: EventIn, request: Request, response: Response, actor=Depends(ingest_identity), db=Depends(session)
):
    if isinstance(actor, APIKey) and actor.project_id != body.project_id:
        raise HTTPException(403, "API key belongs to another project")
    with metrics.tracer.start_as_current_span("event.ingest"):
        event, created = await ingest(
            db, body.project_id, body.type, body.payload, request.headers.get("Idempotency-Key", "")
        )
        await db.commit()
    if created:
        metrics.accepted.inc()
    response.status_code = 201 if created else 200
    return await event_json(db, event, True)


@app.get("/api/events")
async def events(
    project_id: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 100,
    user=Depends(identity),
    db=Depends(session),
):
    query = select(Event).order_by(Event.created_at.desc())
    if project_id:
        query = query.where(Event.project_id == project_id)
    if search:
        query = query.where(
            Event.type.ilike("%" + search[:120] + "%") | Event.id.ilike("%" + search[:120] + "%")
        )
    results = [
        await event_json(db, e) for e in (await db.scalars(query.limit(min(max(limit, 1), 500)))).all()
    ]
    return [r for r in results if not status or r["status"] == status]


@app.get("/api/events/{identifier}")
async def event_detail(identifier: str, user=Depends(identity), db=Depends(session)):
    return await event_json(db, await required(db, Event, identifier), True)


@app.get("/api/deliveries")
async def deliveries(status: str = "dead_letter", user=Depends(identity), db=Depends(session)):
    rows = (
        await db.execute(
            select(Delivery, Event.type)
            .join(Event)
            .where(Delivery.status == status)
            .order_by(Delivery.created_at.desc())
            .limit(500)
        )
    ).all()
    return [{**await delivery_json(db, delivery), "type": kind} for delivery, kind in rows]


@app.post("/api/deliveries/{identifier}/redrive")
async def redrive_delivery(identifier: str, user=Depends(operator), db=Depends(session)):
    job = await redrive(db, identifier)
    audit(db, user, "delivery.redrive", identifier)
    await db.commit()
    return await delivery_json(db, job)


@app.get("/api/overview")
async def get_overview(user=Depends(identity), db=Depends(session)):
    return await overview(db)


@app.get("/api/workers")
async def workers(user=Depends(identity), db=Depends(session)):
    pools = (await db.scalars(select(Pool))).all()
    result = []
    for pool in pools:
        rows = (await db.scalars(select(Worker).where(Worker.region == pool.region))).all()
        healthy = (
            any(
                w.last_heartbeat > now() - timedelta(seconds=settings().failover_seconds)
                and w.state == "running"
                for w in rows
            )
            and not pool.paused
        )
        result.append(
            {
                "region": pool.region,
                "paused": pool.paused,
                "healthy": healthy,
                "workers": [serialize(w) for w in rows],
            }
        )
    return {"pools": result}


@app.post("/api/workers/{region}/{action}")
async def control_pool(region: str, action: str, user=Depends(operator), db=Depends(session)):
    if action not in {"pause", "resume"}:
        raise HTTPException(404, "Unknown action")
    pool = await required(db, Pool, region)
    pool.paused = action == "pause"
    audit(db, user, "pool." + action, region)
    await db.commit()
    return serialize(pool)


@app.get("/api/incidents")
async def incidents(user=Depends(identity), db=Depends(session)):
    return [
        serialize(i)
        for i in (await db.scalars(select(Incident).order_by(Incident.created_at.desc()).limit(200))).all()
    ]


@app.get("/api/incidents/{identifier}")
async def incident_detail(identifier: str, user=Depends(identity), db=Depends(session)):
    return serialize(await required(db, Incident, identifier))


@app.post("/api/incidents/{identifier}/{action}")
async def incident_action(identifier: str, action: str, user=Depends(operator), db=Depends(session)):
    if action not in {"acknowledge", "resolve"}:
        raise HTTPException(404, "Unknown action")
    incident = await db.scalar(select(Incident).where(Incident.id == identifier).with_for_update())
    if not incident:
        raise HTTPException(404, "Incident not found")
    incident.status = "acknowledged" if action == "acknowledge" else "resolved"
    incident.updated_at = now()
    incident.timeline = incident.timeline + [{"at": now().isoformat(), "action": action, "actor": user.email}]
    audit(db, user, "incident." + action, identifier)
    await db.commit()
    return serialize(incident)


@app.get("/api/lab")
async def lab(user=Depends(identity), db=Depends(session)):
    control = await required(db, Control, 1)
    history = (
        await db.scalars(
            select(Audit)
            .where(Audit.action.in_(["lab.scenario", "lab.generate"]))
            .order_by(Audit.created_at.desc())
            .limit(50)
        )
    ).all()
    return {
        "enabled": settings().app_env == "demo",
        "mode": control.lab_mode,
        "history": [{"id": a.id, "actor": a.actor, "created_at": a.created_at, **a.details} for a in history],
    }


@app.post("/api/lab/scenario")
async def scenario(body: ScenarioIn, user=Depends(operator), db=Depends(session)):
    cfg = settings()
    if cfg.app_env != "demo":
        raise HTTPException(403, "Fault lab is available only in demo mode")
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            result = await client.post(
                cfg.demo_sink_url + "/control",
                json={"mode": body.mode, "seed": 42},
                headers={"X-Control-Token": cfg.demo_control_token},
                timeout=5,
            )
            result.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Demo receiver control unavailable") from exc
    control = await required(db, Control, 1)
    control.lab_mode = body.mode
    audit(db, user, "lab.scenario", "demo-sink", {"mode": body.mode, "event_count": 0})
    await db.commit()
    return {"mode": body.mode}


@app.post("/api/lab/generate")
async def generate(body: GenerateIn, user=Depends(operator), db=Depends(session)):
    if settings().app_env != "demo":
        raise HTTPException(403, "Fault lab is available only in demo mode")
    destinations = (
        await db.scalars(
            select(Destination).where(
                Destination.project_id == body.project_id, Destination.enabled.is_(True)
            )
        )
    ).all()
    if not destinations or any(d.url != settings().demo_sink_url + "/webhook" for d in destinations):
        raise HTTPException(409, "Lab generation requires only demo receiver destinations")
    run = uid()
    ids = []
    for i in range(body.count):
        event, _ = await ingest(
            db,
            body.project_id,
            "demo.event",
            {"sequence": i, "seed": body.seed, "value": (i * 17 + body.seed) % 1000},
            f"lab-{run}-{i}",
        )
        ids.append(event.id)
    control = await required(db, Control, 1)
    audit(db, user, "lab.generate", run, {"mode": control.lab_mode, "event_count": len(ids)})
    await db.commit()
    metrics.accepted.inc(len(ids))
    return {"accepted": len(ids), "event_ids": ids}


@app.get("/api/policies")
async def policies(user=Depends(identity), db=Depends(session)):
    control = await required(db, Control, 1)
    rows = (await db.scalars(select(Policy).order_by(Policy.version.desc()))).all()
    comparison = []
    for policy in rows:
        counts = dict(
            (
                await db.execute(
                    select(Delivery.status, func.count())
                    .where(Delivery.policy_id == policy.id)
                    .group_by(Delivery.status)
                )
            ).all()
        )
        total = sum(counts.values())
        delivered = counts.get("delivered", 0)
        terminal = delivered + counts.get("dead_letter", 0)
        p95 = await db.scalar(
            select(func.percentile_cont(0.95).within_group(Attempt.duration_ms))
            .join(Delivery, Delivery.id == Attempt.delivery_id)
            .where(Delivery.policy_id == policy.id, Attempt.http_status.between(200, 299))
        )
        comparison.append(
            {
                "policy_id": policy.id,
                "total": total,
                "delivered": delivered,
                "dead_letter": counts.get("dead_letter", 0),
                "success_rate": delivered / terminal if terminal else None,
                "p95_latency_ms": p95,
            }
        )
    history = (
        await db.scalars(
            select(Audit).where(Audit.action.like("policy.%")).order_by(Audit.created_at.desc()).limit(50)
        )
    ).all()
    return {
        "stable": serialize(await required(db, Policy, control.stable_id)),
        "candidate": serialize(await required(db, Policy, control.candidate_id))
        if control.candidate_id
        else None,
        "canary_percent": control.canary_percent,
        "history": [serialize(a) for a in history],
        "comparison": comparison,
    }


@app.post("/api/policies/candidate")
async def candidate(body: PolicyIn, user=Depends(operator), db=Depends(session)):
    if body.backoff_cap < body.backoff_base:
        raise HTTPException(422, "Backoff cap must be at least the base")
    control = await db.scalar(select(Control).where(Control.id == 1).with_for_update())
    version = (await db.scalar(select(func.max(Policy.version)))) + 1
    policy = Policy(version=version, **body.model_dump(exclude={"canary_percent"}))
    db.add(policy)
    await db.flush()
    control.candidate_id = policy.id
    control.canary_percent = body.canary_percent
    audit(db, user, "policy.candidate", policy.id, body.model_dump())
    await db.commit()
    return serialize(policy)


@app.post("/api/policies/{action}")
async def policy_action(action: str, user=Depends(operator), db=Depends(session)):
    control = await db.scalar(select(Control).where(Control.id == 1).with_for_update())
    if action == "promote":
        if not control.candidate_id:
            raise HTTPException(409, "No candidate policy")
        control.previous_id = control.stable_id
        control.stable_id = control.candidate_id
        control.candidate_id = None
    elif action == "rollback":
        if control.candidate_id:
            control.candidate_id = None
        elif control.previous_id:
            control.stable_id, control.previous_id = control.previous_id, control.stable_id
        else:
            raise HTTPException(409, "No policy to roll back")
    else:
        raise HTTPException(404, "Unknown policy action")
    control.canary_percent = 0
    audit(db, user, "policy." + action, control.stable_id)
    await db.commit()
    return {"ok": True, "stable_id": control.stable_id}


@app.get("/api/audit")
async def audits(limit: int = 100, user=Depends(admin), db=Depends(session)):
    return [
        serialize(a)
        for a in (
            await db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(min(max(limit, 1), 500)))
        ).all()
    ]
