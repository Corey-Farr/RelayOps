import os
import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("DEMO_SINK_URL", "http://127.0.0.1:8081")


@pytest.fixture
async def database():
    if not os.getenv("DATABASE_URL"):
        pytest.skip("Set DATABASE_URL to a dedicated PostgreSQL test database")
    from sqlalchemy.engine import make_url

    database_name = make_url(os.environ["DATABASE_URL"]).database or ""
    if not database_name.endswith("_test"):
        pytest.fail("Refusing destructive fixtures: DATABASE_URL database name must end with _test")
    from relayops.core.db import engine, Session
    from relayops.models import Base, Control, Policy, Pool, Project, Destination, User
    from relayops.security.crypto import encrypt, passwords
    from relayops.services.policy import REGIONS

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with Session.begin() as db:
        policy = Policy(version=1, max_attempts=3, timeout_seconds=1, backoff_base=0.1, backoff_cap=1)
        project = Project(name="Test")
        db.add_all([policy, project])
        await db.flush()
        db.add(Control(id=1, stable_id=policy.id))
        db.add_all([Pool(region=r) for r in REGIONS])
        db.add(
            Destination(
                project_id=project.id,
                name="Test receiver",
                url="http://127.0.0.1:8081/webhook",
                secret_encrypted=encrypt("test-signing-secret"),
            )
        )
        db.add(
            User(email="admin@example.test", password_hash=passwords.hash("test-password-long"), role="admin")
        )
        db.add(
            User(
                email="viewer@example.test", password_hash=passwords.hash("test-password-long"), role="viewer"
            )
        )
    yield {"project_id": project.id, "policy": policy}
    await engine.dispose()
