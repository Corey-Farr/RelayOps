from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from relayops.core.db import Session
from relayops.models import Delivery, now
from relayops.services.ingestion import ingest

pytestmark = pytest.mark.integration


async def test_filters_precede_pagination_and_support_time_sort_destination(database):
    from relayops.main import app

    baseline = now() - timedelta(hours=1)
    ids = []
    async with Session.begin() as db:
        for index in range(15):
            event, _ = await ingest(db, database["project_id"], "search.test", {}, str(index))
            event.created_at = baseline + timedelta(minutes=index)
            ids.append(event.id)
        jobs = (await db.scalars(select(Delivery))).all()
        for job in jobs:
            if job.event_id in ids[:3]:
                job.status = "delivered"
                job.delivered_at = now()
        destination = jobs[0].destination_id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (
            await client.post(
                "/api/auth/login", json={"email": "admin@example.test", "password": "test-password-long"}
            )
        ).status_code == 200
        result = await client.get(
            "/api/events",
            params={"status": "delivered", "limit": 2, "sort": "created_at", "direction": "asc"},
        )
        assert [row["id"] for row in result.json()] == ids[:2]
        result = await client.get(
            "/api/events", params={"status": "delivered", "limit": 2, "offset": 2, "direction": "asc"}
        )
        assert [row["id"] for row in result.json()] == ids[2:3]
        result = await client.get(
            "/api/events",
            params={
                "destination_id": destination,
                "event_type": "search.test",
                "project_id": database["project_id"],
                "created_from": (baseline + timedelta(minutes=10)).isoformat(),
                "created_to": (baseline + timedelta(minutes=12)).isoformat(),
                "direction": "asc",
            },
        )
        assert [row["id"] for row in result.json()] == ids[10:13]
        assert (
            await client.get("/api/events", params={"created_from": "2026-01-01T00:00:00"})
        ).status_code == 422
        assert (await client.get("/api/events", params={"status": "made_up"})).status_code == 422
