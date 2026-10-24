import asyncio
import json
import logging
import signal
import socket
import time
import httpx
from opentelemetry.propagate import extract
from prometheus_client import start_http_server
from sqlalchemy import func, select
from relayops.core.config import settings
from relayops.core.db import Session, engine
from relayops.models import Delivery, Destination, Event, Policy, Pool, Worker, now
from relayops.observability import telemetry as metrics
from relayops.security.crypto import decrypt, signature, validate_destination
from relayops.services.policy import ACTIVE
from relayops.services.queue import begin_dispatch, claim, complete

log = logging.getLogger(__name__)


async def dispatch(job, client):
    async with Session() as db:
        destination = await db.get(Destination, job.destination_id)
        event = await db.get(Event, job.event_id)
        policy = await db.get(Policy, job.policy_id)
    if destination is None or event is None or policy is None:
        raise RuntimeError("Claimed delivery references missing data")
    body = json.dumps(
        {
            "id": event.id,
            "project_id": event.project_id,
            "type": event.type,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
        },
        separators=(",", ":"),
    ).encode()
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "X-RelayOps-Event-ID": event.id,
        "X-RelayOps-Delivery-ID": job.id,
        "X-RelayOps-Timestamp": timestamp,
        "X-RelayOps-Signature": signature(decrypt(destination.secret_encrypted), timestamp, body),
    }
    status = None
    category = None
    retry_after = None
    started = now()
    clock = time.monotonic()
    region = settings().worker_region
    with metrics.tracer.start_as_current_span(
        "delivery.dispatch", context=extract(event.trace_context)
    ) as span:
        span.set_attribute("relayops.event_id", event.id)
        span.set_attribute("relayops.delivery_id", job.id)
        span.set_attribute("relayops.region", region)
        trace_id = f"{span.get_span_context().trace_id:032x}"
        if not await begin_dispatch(job, started, trace_id):
            return
        clock = time.monotonic()
        metrics.attempted.labels(region).inc()
        try:
            validate_destination(destination.url)
            async with client.stream(
                "POST", destination.url, content=body, headers=headers, timeout=policy.timeout_seconds
            ) as response:
                status = response.status_code
                retry_after = response.headers.get("retry-after")
            if not 200 <= status < 300:
                category = "http_error"
        except httpx.TimeoutException:
            category = "timeout"
        except httpx.RequestError:
            category = "network_error"
        except ValueError:
            category = "destination_rejected"
            status = 400
        duration = (time.monotonic() - clock) * 1000
        metrics.http_duration.labels(region).observe(duration / 1000)
        if category:
            metrics.failed.labels(region).inc()
        with metrics.tracer.start_as_current_span("delivery.complete"):
            await complete(job, status, category, duration, started, retry_after, policy, trace_id)


async def heartbeat(worker_id, state="running"):
    cfg = settings()
    async with Session.begin() as db:
        worker = await db.get(Worker, worker_id)
        pool = await db.get(Pool, cfg.worker_region)
        values = dict(
            region=cfg.worker_region,
            last_heartbeat=now(),
            version="0.1.0",
            capacity=cfg.worker_concurrency,
            state="paused" if pool and pool.paused else state,
        )
        if not worker:
            db.add(Worker(id=worker_id, **values))
        else:
            for key, value in values.items():
                setattr(worker, key, value)
        depth = await db.scalar(select(func.count()).select_from(Delivery).where(Delivery.status.in_(ACTIVE)))
        active = await db.scalar(
            select(func.count()).select_from(Delivery).where(Delivery.status == "leased")
        )
        metrics.queue.set(depth or 0)
        metrics.inflight.set(active or 0)
        metrics.heartbeat.labels(cfg.worker_region).set(time.time())


async def run(stop=None):
    cfg = settings()
    worker_id = cfg.worker_id or f"{cfg.worker_region}-{socket.gethostname()}"
    own_stop = stop is None
    stop = stop or asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM) if own_stop else ():
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
    tasks: set[asyncio.Task] = set()
    last_heartbeat = 0.0
    async with httpx.AsyncClient(
        follow_redirects=False,
        trust_env=False,
        limits=httpx.Limits(
            max_connections=cfg.worker_concurrency, max_keepalive_connections=cfg.worker_concurrency
        ),
    ) as client:
        while not stop.is_set():
            try:
                if time.monotonic() - last_heartbeat >= cfg.heartbeat_seconds:
                    await heartbeat(worker_id)
                    from relayops.services.monitoring import detect_incidents

                    await detect_incidents()
                    last_heartbeat = time.monotonic()
                done = {task for task in tasks if task.done()}
                for task in done:
                    try:
                        task.result()
                    except Exception:
                        log.exception("Delivery task failed; lease will recover")
                tasks -= done
                jobs = (
                    await claim(worker_id, cfg.worker_region, cfg.worker_concurrency - len(tasks))
                    if len(tasks) < cfg.worker_concurrency
                    else []
                )
                tasks.update(asyncio.create_task(dispatch(job, client)) for job in jobs)
            except Exception:
                log.exception("Worker loop failed; retrying after bounded delay")
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.25)
            except TimeoutError:
                pass
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=cfg.shutdown_grace_seconds)
            for task in pending:
                task.cancel()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    log.error("Delivery failed during shutdown; lease will recover", exc_info=result)
        await heartbeat(worker_id, "stopped")
    await engine.dispose()


if __name__ == "__main__":
    metrics.setup("relayops-worker")
    start_http_server(settings().worker_metrics_port)
    asyncio.run(run())
