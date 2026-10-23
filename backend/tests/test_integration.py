import asyncio
from datetime import timedelta
import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from relayops.core.config import settings
from relayops.core.db import Session
from relayops.models import Attempt, Delivery, Event, Incident, Pool, Worker, now
from relayops.services.ingestion import ingest
from relayops.services.queue import claim, complete, redrive
from relayops.services.monitoring import detect_incidents

pytestmark = pytest.mark.integration


async def accepted(project_id, key="one", payload=None):
    async with Session.begin() as db:
        event, created = await ingest(db, project_id, "order.created", payload or {"value": 1}, key)
    return event, created


async def test_atomic_idempotency_conflict(database):
    event, _ = await accepted(database["project_id"])
    duplicate, created = await accepted(database["project_id"])
    assert duplicate.id == event.id and not created
    with pytest.raises(HTTPException) as exc:
        await accepted(database["project_id"], payload={"value": 2})
    assert exc.value.status_code == 409
    async with Session() as db:
        assert await db.scalar(select(func.count()).select_from(Event)) == 1
        assert await db.scalar(select(func.count()).select_from(Delivery)) == 1


async def test_concurrent_ingest_and_claim(database):
    results = await asyncio.gather(*(accepted(database["project_id"], "same") for _ in range(8)))
    assert len({e.id for e, _ in results}) == 1
    await asyncio.gather(*(accepted(database["project_id"], str(i)) for i in range(8)))
    claims = await asyncio.gather(*(claim(f"worker-{i}", "us-east", 3) for i in range(4)))
    ids = [j.id for jobs in claims for j in jobs]
    assert len(ids) == 9 and len(set(ids)) == 9


async def test_backpressure_atomic(database, monkeypatch):
    monkeypatch.setattr(settings(), "max_queue_depth", 1)
    results = await asyncio.gather(
        accepted(database["project_id"], "a"), accepted(database["project_id"], "b"), return_exceptions=True
    )
    assert sum(isinstance(r, HTTPException) and r.status_code == 429 for r in results) == 1
    async with Session() as db:
        assert await db.scalar(select(func.count()).select_from(Event)) == 1


async def test_rollback_atomicity(database):
    async with Session() as db:
        await ingest(db, database["project_id"], "order.created", {}, "rolled-back")
        await db.rollback()
    async with Session() as db:
        assert await db.scalar(select(func.count()).select_from(Event)) == 0
        assert await db.scalar(select(func.count()).select_from(Delivery)) == 0


async def test_lease_recovery_fencing(database):
    await accepted(database["project_id"])
    old = (await claim("old", "us-east", 1))[0]
    async with Session.begin() as db:
        job = await db.get(Delivery, old.id)
        job.lease_until = now() - timedelta(seconds=1)
    new = (await claim("new", "us-east", 1))[0]
    assert new.lease_version > old.lease_version
    assert not await complete(old, 200, None, 2, now(), None, database["policy"], "")
    async with Session() as db:
        assert (await db.get(Delivery, old.id)).lease_owner == "new"
    assert await complete(new, 200, None, 2, now(), None, database["policy"], "")
    async with Session() as db:
        assert (await db.get(Delivery, old.id)).status == "delivered"
        assert await db.scalar(select(func.count()).select_from(Attempt)) == 2


async def test_retry_dead_letter_redrive(database):
    await accepted(database["project_id"])
    job = (await claim("worker", "us-east", 1))[0]
    await complete(job, 503, "http_error", 1, now(), "2", database["policy"], "")
    async with Session.begin() as db:
        delivery = await db.get(Delivery, job.id)
        assert delivery.status == "retry_wait" and delivery.next_attempt_at > now()
        delivery.next_attempt_at = now() - timedelta(seconds=1)
    job = (await claim("worker", "us-east", 1))[0]
    await complete(job, 404, "http_error", 1, now(), None, database["policy"], "")
    async with Session.begin() as db:
        assert (await db.get(Delivery, job.id)).status == "dead_letter"
        await redrive(db, job.id)
    job = (await claim("worker", "us-east", 1))[0]
    await complete(job, 200, None, 1, now(), None, database["policy"], "")
    async with Session() as db:
        assert (await db.get(Delivery, job.id)).status == "delivered"


async def test_pause_failover(database):
    await accepted(database["project_id"])
    async with Session.begin() as db:
        job = await db.scalar(select(Delivery))
        job.region = "eu-west"
        db.add(Worker(id="eu", region="eu-west", last_heartbeat=now(), capacity=1, state="running"))
    assert await claim("us", "us-east", 1) == []
    async with Session.begin() as db:
        (await db.get(Pool, "eu-west")).paused = True
    assert await claim("eu", "eu-west", 1) == []
    assert len(await claim("us", "us-east", 1)) == 1


async def test_real_dispatch_signature(database):
    from relayops.workers.runner import dispatch
    from relayops.security.crypto import signature

    await accepted(database["project_id"])
    job = (await claim("worker", "us-east", 1))[0]

    def receiver(request):
        assert request.headers["X-RelayOps-Signature"] == signature(
            "test-signing-secret", request.headers["X-RelayOps-Timestamp"], request.content
        )
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver)) as client:
        await dispatch(job, client)
    async with Session() as db:
        assert (await db.get(Delivery, job.id)).status == "delivered"


async def test_incident_deduplication(database, monkeypatch):
    monkeypatch.setattr(settings(), "incident_dead_letter_threshold", 1)
    await accepted(database["project_id"])
    async with Session.begin() as db:
        (await db.scalar(select(Delivery))).status = "dead_letter"
    await asyncio.gather(detect_incidents(), detect_incidents(), detect_incidents())
    async with Session() as db:
        assert await db.scalar(select(func.count()).select_from(Incident)) == 1


async def test_api_auth_csrf_keys_and_policies(database):
    from relayops.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/projects")).status_code == 401
        result = await client.post(
            "/api/auth/login", json={"email": "admin@example.test", "password": "test-password-long"}
        )
        assert result.status_code == 200
        assert "HttpOnly" in result.headers["set-cookie"]
        assert (await client.post("/api/projects", json={"name": "denied"})).status_code == 403
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        key = (
            await client.post(f"/api/projects/{database['project_id']}/keys", json={"name": "ingest"})
        ).json()
        body = {"project_id": database["project_id"], "type": "order.created", "payload": {}}
        result = await client.post(
            "/api/events",
            json=body,
            headers={"Authorization": "Bearer " + key["key"], "Idempotency-Key": "api"},
        )
        assert result.status_code == 201
        await client.delete("/api/keys/" + key["id"])
        assert (
            await client.post(
                "/api/events",
                json=body,
                headers={"Authorization": "Bearer " + key["key"], "Idempotency-Key": "api2"},
            )
        ).status_code == 401
        before = (await client.get("/api/policies")).json()["stable"]["id"]
        result = await client.post(
            "/api/policies/candidate",
            json={
                "timeout_seconds": 2,
                "max_attempts": 2,
                "backoff_base": 1,
                "backoff_cap": 5,
                "canary_percent": 100,
            },
        )
        assert result.status_code == 200
        assert (await client.post("/api/policies/promote")).status_code == 200
        assert (await client.post("/api/policies/rollback")).status_code == 200
        assert (await client.get("/api/policies")).json()["stable"]["id"] == before
        assert (
            await client.post(
                "/api/events", json={"project_id": database["project_id"], "type": "bad type", "payload": []}
            )
        ).status_code == 422
        await client.post("/api/auth/logout")
        assert (await client.get("/api/auth/me")).status_code == 401
        result = await client.post(
            "/api/auth/login", json={"email": "viewer@example.test", "password": "test-password-long"}
        )
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        assert (await client.post("/api/projects", json={"name": "viewer denied"})).status_code == 403
