from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from relayops.core.db import Session
from relayops.models import Audit, Incident, now


@pytest.mark.integration
async def test_historical_incident_pagination_actions_and_audit(database):
    from relayops.main import app

    async with Session.begin() as db:
        for index in range(205):
            db.add(
                Incident(
                    fingerprint=f"history-{index}",
                    title="Historical incident",
                    description="Test",
                    severity="warning" if index < 3 else "critical",
                    component="queue",
                    source="test",
                    status="resolved" if index < 3 else "open",
                    evidence={},
                    timeline=[],
                    created_at=now() + timedelta(seconds=index),
                )
            )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.test",
                "password": "test-password-long",
            },
        )
        client.headers["X-CSRF-Token"] = auth.json()["csrf_token"]
        older = (await client.get("/api/incidents?offset=200&limit=10")).json()
        assert len(older) == 5
        filtered = (
            await client.get("/api/incidents?status=resolved&severity=warning&limit=2&offset=1")
        ).json()
        assert len(filtered) == 2 and all(row["status"] == "resolved" for row in filtered)
        identifier = older[0]["id"]
        for action, expected in [("acknowledge", "acknowledged"), ("resolve", "resolved")]:
            result = await client.post(f"/api/incidents/{identifier}/{action}")
            assert result.status_code == 200 and result.json()["status"] == expected
            assert result.json()["timeline"][-1]["action"] == action
        assert (await client.get("/api/incidents?offset=-1")).status_code == 422
    async with Session() as db:
        actions = (await db.scalars(select(Audit.action).where(Audit.resource == identifier))).all()
        assert set(actions) == {"incident.acknowledge", "incident.resolve"}
