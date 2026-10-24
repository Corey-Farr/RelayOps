"""Policy selection is persisted even if the rollout changes during retry."""

import httpx
import pytest
from sqlalchemy import select

from relayops.core.db import Session
from relayops.models import Delivery
from relayops.services.ingestion import ingest
from relayops.services.queue import claim, complete

pytestmark = pytest.mark.integration


async def test_candidate_pin_survives_rollback_and_retry(database):
    from relayops.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post(
            "/api/auth/login", json={"email": "admin@example.test", "password": "test-password-long"}
        )
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        candidate = await client.post(
            "/api/policies/candidate",
            json={
                "timeout_seconds": 2,
                "max_attempts": 2,
                "backoff_base": 1,
                "backoff_cap": 5,
                "canary_percent": 100,
            },
        )
        assert candidate.status_code == 200
        candidate_id = candidate.json()["id"]
        async with Session.begin() as db:
            first, _ = await ingest(db, database["project_id"], "policy.test", {}, "before-rollback")
        assert (await client.post("/api/policies/rollback")).status_code == 200
        async with Session.begin() as db:
            second, _ = await ingest(db, database["project_id"], "policy.test", {}, "after-rollback")
        jobs = await claim("policy-test", "us-east", 2)
        original = next(job for job in jobs if job.event_id == first.id)
        new = next(job for job in jobs if job.event_id == second.id)
        assert original.policy_id == candidate_id
        assert new.policy_id == database["policy"].id
        from relayops.models import Policy, now

        async with Session() as db:
            policy = await db.get(Policy, candidate_id)
        await complete(original, 503, "http_error", 1, now(), None, policy, "")
        async with Session() as db:
            saved = await db.get(Delivery, original.id)
            assert saved.status == "retry_wait"
            assert saved.policy_id == candidate_id
        policies = (await client.get("/api/policies")).json()
        assert policies["candidate"] is None
        assert any(row["policy_id"] == candidate_id and row["total"] == 1 for row in policies["comparison"])
        assert [row["action"] for row in policies["history"]] == ["policy.rollback", "policy.candidate"]


async def test_policy_comparison_uses_delivery_latency_and_reports_sample_counts(database):
    from datetime import timedelta
    from relayops.models import Attempt, now
    from relayops.services.monitoring import policy_comparison

    async with Session.begin() as db:
        event, _ = await ingest(db, database["project_id"], "comparison.test", {}, "comparison")
        event.created_at = now() - timedelta(seconds=100)
        delivery = await db.scalar(select(Delivery).where(Delivery.event_id == event.id))
        delivery.status = "delivered"
        delivery.delivered_at = event.created_at + timedelta(seconds=20)
        db.add(
            Attempt(
                delivery_id=delivery.id,
                number=1,
                worker_id="old",
                region="us-east",
                started_at=now(),
                ended_at=now(),
                duration_ms=1,
                http_status=200,
            )
        )
    async with Session() as db:
        result = (await policy_comparison(db))[0]
    assert result["p95_latency_ms"] == pytest.approx(20000)
    assert result["terminal_samples"] == 1
    assert result["latency_samples"] == 1
    assert result["success_rate"] == 1
    assert result["sufficient_data"] is False


async def test_redrive_backoff_restarts_at_first_cycle_attempt(database, monkeypatch):
    from relayops.models import now
    from relayops.services.queue import redrive
    from relayops.services import queue

    async with Session.begin() as db:
        await ingest(db, database["project_id"], "redrive.test", {}, "redrive")
        delivery = await db.scalar(select(Delivery))
        delivery.status = "dead_letter"
        delivery.attempt_count = 12
        delivery.cycle_attempt_count = 3
        await redrive(db, delivery.id)
    captured = []

    def delay(attempt, *_):
        captured.append(attempt)
        return 1

    monkeypatch.setattr(queue, "retry_delay", delay)
    job = (await claim("redrive-test", "us-east", 1))[0]
    assert job.attempt_count == 13
    await complete(job, 503, "http_error", 1, now(), None, database["policy"], "")
    assert captured == [1]
