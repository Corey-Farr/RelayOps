import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from relayops.core.config import settings
from relayops.core.db import Session
from relayops.models import Delivery, Worker, now
from relayops.services.ingestion import ingest
from relayops.services.queue import claim, complete

pytestmark = pytest.mark.integration


async def test_graceful_stop_finishes_inflight_without_claiming_more(database, monkeypatch):
    from relayops.workers import runner

    monkeypatch.setattr(settings(), "worker_concurrency", 1)
    monkeypatch.setattr(settings(), "worker_id", "shutdown-test")
    started, release, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async with Session.begin() as db:
        for key in ("one", "two"):
            await ingest(db, database["project_id"], "shutdown.event", {}, key)

    async def dispatch(job, client):
        started.set()
        await release.wait()
        await complete(job, 200, None, 1, now(), None, database["policy"], "")

    monkeypatch.setattr(runner, "dispatch", dispatch)
    worker = asyncio.create_task(runner.run(stop))
    try:
        await asyncio.wait_for(started.wait(), 5)
        stop.set()
        release.set()
        await asyncio.wait_for(worker, 5)
    finally:
        stop.set()
        release.set()
        if not worker.done():
            await asyncio.wait_for(worker, 5)
    async with Session() as db:
        states = (await db.scalars(select(Delivery.status))).all()
        assert sorted(states) == ["delivered", "pending"]
        assert (await db.get(Worker, "shutdown-test")).state == "stopped"


async def test_shutdown_deadline_cancels_work_and_lease_is_recoverable(database, monkeypatch):
    from relayops.workers import runner

    monkeypatch.setattr(settings(), "worker_concurrency", 1)
    monkeypatch.setattr(settings(), "worker_id", "cancel-test")
    monkeypatch.setattr(settings(), "shutdown_grace_seconds", 0.05)
    started, cancelled, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async with Session.begin() as db:
        await ingest(db, database["project_id"], "shutdown.event", {}, "cancel")

    async def dispatch(job, client):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(runner, "dispatch", dispatch)
    worker = asyncio.create_task(runner.run(stop))
    await asyncio.wait_for(started.wait(), 5)
    stop.set()
    await asyncio.wait_for(worker, 5)
    assert cancelled.is_set()
    async with Session.begin() as db:
        job = await db.scalar(select(Delivery))
        assert job.status == "leased"
        job.lease_until = now() - timedelta(seconds=1)
    reclaimed = await claim("replacement", "us-east", 1)
    assert len(reclaimed) == 1 and reclaimed[0].lease_owner == "replacement"
