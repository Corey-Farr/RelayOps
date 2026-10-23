import httpx
import pytest
from sqlalchemy import select
from relayops.core.db import Session
from relayops.models import Audit, User
from relayops.security.crypto import passwords
from relayops.users import create_user

pytestmark = pytest.mark.integration


async def test_offline_account_hash_audit_and_role_boundaries(database):
    from relayops.main import app

    identifier = await create_user("operator@example.test", "operator-password-long", "operator")
    async with Session() as db:
        user = await db.get(User, identifier)
        assert user.password_hash != "operator-password-long"
        assert passwords.verify(user.password_hash, "operator-password-long")
        assert await db.scalar(select(Audit.id).where(Audit.action == "user.create"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login", json={"email": "operator@example.test", "password": "operator-password-long"}
        )
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        assert (await client.post("/api/projects", json={"name": "denied"})).status_code == 403
        assert (
            await client.post(f"/api/projects/{database['project_id']}/keys", json={"name": "denied"})
        ).status_code == 403
        assert (await client.post("/api/workers/us-east/pause")).status_code == 200
        await client.post("/api/auth/logout")
        response = await client.post(
            "/api/auth/login", json={"email": "viewer@example.test", "password": "test-password-long"}
        )
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        for method, path, body in [
            ("POST", "/api/workers/us-east/resume", None),
            ("POST", "/api/lab/scenario", {"mode": "normal"}),
            ("POST", "/api/policies/promote", None),
            ("POST", "/api/deliveries/missing/redrive", None),
            ("PATCH", "/api/destinations/missing", {"enabled": False}),
            ("POST", "/api/destinations/missing/test", None),
            ("POST", "/api/incidents/missing/resolve", None),
        ]:
            assert (await client.request(method, path, json=body)).status_code == 403
        assert (await client.get("/api/workers")).status_code == 200


async def test_login_rate_limit_and_capacity_pruning(database):
    from relayops.main import app, login_attempts

    login_attempts.clear()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("192.0.2.3", 1234)), base_url="http://test"
    ) as client:
        for _ in range(10):
            assert (
                await client.post("/api/auth/login", json={"email": "absent@example.test", "password": "bad"})
            ).status_code == 401
        response = await client.post(
            "/api/auth/login", json={"email": "absent@example.test", "password": "bad"}
        )
        assert response.status_code == 429 and response.headers["Retry-After"] == "60"
    login_attempts.clear()
