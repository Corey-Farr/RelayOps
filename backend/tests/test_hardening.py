import httpx
import pytest
from pydantic import ValidationError

from relayops.core.config import Settings


@pytest.mark.parametrize(
    "overrides",
    [
        {"slo_target": 1},
        {"slo_target": 0},
        {"max_queue_depth": 0},
        {"lease_seconds": 10},
        {"worker_region": "unknown"},
        {"heartbeat_seconds": 20, "failover_seconds": 20},
    ],
)
def test_invalid_operational_limits_are_rejected(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


@pytest.mark.integration
async def test_dispatch_does_not_download_response_body(database):
    from relayops.core.db import Session
    from relayops.services.ingestion import ingest
    from relayops.services.queue import claim
    from relayops.workers.runner import dispatch

    class BodyMustNotBeRead(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise AssertionError("Webhook response body was downloaded")
            yield b""  # makes this an async generator

    async with Session.begin() as db:
        await ingest(db, database["project_id"], "response.test", {}, "bounded-response")
    job = (await claim("bounded-worker", "us-east", 1))[0]
    transport = httpx.MockTransport(lambda _: httpx.Response(200, stream=BodyMustNotBeRead()))
    async with httpx.AsyncClient(transport=transport) as client:
        await dispatch(job, client)
