"""Offline account administration using deployment database credentials."""

import argparse
import asyncio
import getpass

from sqlalchemy import select
from relayops.core.db import Session, engine
from relayops.models import Audit, User
from relayops.security.crypto import passwords


async def create_user(email: str, password: str, role: str):
    if role not in {"admin", "operator", "viewer"} or "@" not in email or len(email) > 254:
        raise ValueError("Use a valid email and admin/operator/viewer role")
    if len(password) < 12:
        raise ValueError("Passwords must have at least 12 characters")
    async with Session.begin() as db:
        if await db.scalar(select(User.id).where(User.email == email)):
            raise ValueError("Account already exists")
        user = User(email=email, password_hash=await asyncio.to_thread(passwords.hash, password), role=role)
        db.add(user)
        await db.flush()
        db.add(
            Audit(
                actor="offline-administrator",
                action="user.create",
                resource=user.id,
                details={"email": email, "role": role},
            )
        )
    return user.id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    parser.add_argument("--role", choices=["admin", "operator", "viewer"], default="viewer")
    args = parser.parse_args()
    password = getpass.getpass("New account password (12+ characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords did not match")

    async def run():
        try:
            await create_user(args.email, password, args.role)
        finally:
            await engine.dispose()

    asyncio.run(run())
    print("Account created. Password was not written to command history or logs.")


if __name__ == "__main__":
    main()
