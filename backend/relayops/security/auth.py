import hmac
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from relayops.core.db import session
from relayops.models import APIKey, LoginSession, User, now
from relayops.security.crypto import digest


async def identity(request: Request, db=Depends(session)):
    cookie = request.cookies.get("relayops_session")
    saved = await db.get(LoginSession, digest(cookie)) if cookie else None
    if not saved or saved.expires_at <= now():
        raise HTTPException(401, "Authentication required")
    user = await db.get(User, saved.user_id)
    if user is None or user.role not in {"admin", "operator", "viewer"}:
        raise HTTPException(401, "Account is unavailable")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(saved.csrf, supplied):
            raise HTTPException(403, "Invalid CSRF token")
    request.state.csrf = saved.csrf
    return user


async def operator(user=Depends(identity)):
    if user.role not in {"admin", "operator"}:
        raise HTTPException(403, "Operator role required")
    return user


async def admin(user=Depends(identity)):
    if user.role != "admin":
        raise HTTPException(403, "Admin role required")
    return user


async def ingest_identity(request: Request, db=Depends(session)):
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        key = await db.scalar(
            select(APIKey).where(APIKey.digest == digest(authorization[7:]), APIKey.revoked_at.is_(None))
        )
        if not key:
            raise HTTPException(401, "Invalid API key")
        return key
    return await operator(await identity(request, db))
