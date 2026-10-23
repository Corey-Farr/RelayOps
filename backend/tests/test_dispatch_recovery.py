from datetime import timedelta

import pytest
from sqlalchemy import select

from relayops.core.db import Session
from relayops.models import Delivery, DispatchStart, now
from relayops.services.ingestion import ingest
from relayops.services.queue import begin_dispatch, claim, complete, redrive
from relayops.services.serialization import delivery_json

pytestmark = pytest.mark.integration


async def seed(database):
    async with Session.begin() as db:
        await ingest(db, database["project_id"], "crash.test", {}, "crash")


async def expire(identifier):
    async with Session.begin() as db:
        job = await db.get(Delivery, identifier)
        job.lease_until = now() - timedelta(seconds=1)


async def test_crash_leaves_unknown_dispatch_and_reclaim_is_fenced(database):
    await seed(database)
    old = (await claim("old", "us-east", 1))[0]
    assert await begin_dispatch(old, now(), "trace")
    assert not await begin_dispatch(old, now(), "duplicate")
    await expire(old.id)
    new = (await claim("new", "us-east", 1))[0]
    assert not await begin_dispatch(old, now(), "stale")
    assert await begin_dispatch(new, now(), "recovery")
    await complete(new, 200, None, 1, now(), None, database["policy"], "recovery")
    async with Session() as db:
        details = await delivery_json(db, await db.get(Delivery, old.id), True)
        assert details["status"] == "delivered"
        assert len(details["dispatches"]) == 2
        assert not details["dispatches"][0]["outcome_recorded"]
        assert details["dispatches"][1]["outcome_recorded"]
        assert len(details["attempts"]) == 1


async def test_repeated_crashes_are_bounded_and_redrive_restores_retry_budget(database):
    await seed(database)
    for _ in range(database["policy"].max_attempts):
        job = (await claim("crashing", "us-east", 1))[0]
        assert await begin_dispatch(job, now(), "trace")
        await expire(job.id)
    assert await claim("recovery", "us-east", 1) == []
    async with Session.begin() as db:
        saved = await db.get(Delivery, job.id)
        assert saved.status == "dead_letter"
        assert saved.attempt_count == 3
        await redrive(db, job.id)
    job = (await claim("recovery", "us-east", 1))[0]
    assert job.attempt_count == 4 and job.cycle_attempt_count == 1
    await complete(job, 503, "http_error", 1, now(), None, database["policy"], "trace")
    async with Session() as db:
        assert (await db.get(Delivery, job.id)).status == "retry_wait"
        assert len((await db.scalars(select(DispatchStart))).all()) == 3
