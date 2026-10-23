import asyncio
from sqlalchemy import select
from relayops.core.config import settings
from relayops.core.db import Session, engine
from relayops.models import Control, Destination, Policy, Pool, Project, User
from relayops.security.crypto import encrypt, passwords
from relayops.services.policy import REGIONS


async def bootstrap():
    cfg = settings()
    if len(cfg.admin_password) < 12 or not cfg.encryption_key:
        raise ValueError("Set ADMIN_PASSWORD (12+ characters) and ENCRYPTION_KEY before bootstrap")
    async with Session.begin() as db:
        if not await db.scalar(select(User).where(User.email == cfg.admin_email)):
            db.add(
                User(email=cfg.admin_email, password_hash=passwords.hash(cfg.admin_password), role="admin")
            )
        if not await db.get(Control, 1):
            policy = Policy(version=1)
            db.add(policy)
            await db.flush()
            db.add(Control(id=1, stable_id=policy.id))
        for region in REGIONS:
            if not await db.get(Pool, region):
                db.add(Pool(region=region))
        if cfg.app_env == "demo":
            project = await db.scalar(select(Project).where(Project.name == "Demo project"))
            if not project:
                project = Project(name="Demo project")
                db.add(project)
                await db.flush()
            if not await db.scalar(select(Destination).where(Destination.project_id == project.id)):
                if not cfg.demo_signing_secret:
                    raise ValueError("DEMO_SIGNING_SECRET is required for demo bootstrap")
                db.add(
                    Destination(
                        project_id=project.id,
                        name="Demo receiver",
                        url=cfg.demo_sink_url + "/webhook",
                        secret_encrypted=encrypt(cfg.demo_signing_secret),
                    )
                )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(bootstrap())
