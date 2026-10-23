import httpx
import pytest
from sqlalchemy import select
from relayops.core.db import Session
from relayops.models import Destination
from relayops.security.crypto import encrypt

pytestmark = pytest.mark.integration


async def test_destination_edit_test_event_scope_and_health(database):
    from relayops.main import app

    async with Session.begin() as db:
        first = await db.scalar(select(Destination))
        db.add(
            Destination(
                project_id=database["project_id"],
                name="Second",
                url=first.url,
                secret_encrypted=encrypt("second-test-secret"),
            )
        )
        identifier = first.id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        auth = await client.post(
            "/api/auth/login", json={"email": "admin@example.test", "password": "test-password-long"}
        )
        client.headers["X-CSRF-Token"] = auth.json()["csrf_token"]
        assert (
            await client.patch(f"/api/destinations/{identifier}", json={"url": "file:///etc/passwd"})
        ).status_code == 422
        result = await client.patch(
            f"/api/destinations/{identifier}", json={"name": "Updated", "event_types": ["specific.event"]}
        )
        assert result.status_code == 200
        assert result.json()["name"] == "Updated"
        assert "secret_encrypted" not in result.json()
        result = await client.post(f"/api/destinations/{identifier}/test")
        assert result.status_code == 201
        event = result.json()
        assert event["type"] == "specific.event"
        assert len(event["deliveries"]) == 1
        assert event["deliveries"][0]["destination_id"] == identifier
        health = (await client.get(f"/api/destinations/{identifier}/health")).json()
        assert health["counts"] == {"pending": 1}
        assert health["success_rate"] is None
        await client.patch(f"/api/destinations/{identifier}", json={"enabled": False})
        assert (await client.post(f"/api/destinations/{identifier}/test")).status_code == 409
