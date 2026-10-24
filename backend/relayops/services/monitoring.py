from datetime import timedelta
from math import ceil
from sqlalchemy import func, select, text
from relayops.core.config import settings
from relayops.core.db import Session
from relayops.models import Delivery, Event, Incident, Pool, Worker, now
from relayops.services.policy import ACTIVE


def fraction(numerator, denominator):
    return numerator / denominator if denominator else None


async def slo(db, hours=24, observed_at=None):
    """Count only matured deliveries, from event acceptance, inside PostgreSQL."""
    cfg = settings()
    timestamp = observed_at or now()
    end = timestamp - timedelta(seconds=cfg.slo_deadline_seconds)
    start = timestamp - timedelta(hours=hours)
    timely = (
        (Delivery.status == "delivered")
        & (Delivery.delivered_at.is_not(None))
        & (Delivery.delivered_at >= Event.created_at)
        & (Delivery.delivered_at <= Event.created_at + timedelta(seconds=cfg.slo_deadline_seconds))
    )
    eligible, good = (
        await db.execute(
            select(func.count(Delivery.id), func.count(Delivery.id).filter(timely))
            .join(Event, Event.id == Delivery.event_id)
            .where(Event.created_at >= start, Event.created_at <= end)
        )
    ).one()
    compliance = fraction(good, eligible)
    bad_rate = fraction(eligible - good, eligible)
    return {
        "target": cfg.slo_target,
        "window_hours": hours,
        "deadline_seconds": cfg.slo_deadline_seconds,
        "eligible": eligible,
        "good": good,
        "compliance": compliance,
        "error_budget_remaining": (1 - bad_rate / (1 - cfg.slo_target)) if bad_rate is not None else None,
        "burn_rate": bad_rate / (1 - cfg.slo_target) if bad_rate is not None else None,
        "sufficient_data": eligible >= cfg.slo_min_samples,
    }


async def objective_windows(db):
    timestamp = now()
    long = await slo(db, observed_at=timestamp)
    short = await slo(db, 1, observed_at=timestamp)
    long["short_burn_rate"] = short["burn_rate"]
    long["short_sufficient_data"] = short["sufficient_data"]
    long["short_eligible"] = short["eligible"]
    return long


async def overview(db):
    counts = dict((await db.execute(select(Delivery.status, func.count()).group_by(Delivery.status))).all())
    total = sum(counts.values())
    depth = sum(counts.get(s, 0) for s in ACTIVE)
    completed = counts.get("delivered", 0)
    dead = counts.get("dead_letter", 0)
    elapsed_ms = func.extract("epoch", Delivery.delivered_at - Event.created_at) * 1000
    latency = await db.scalar(
        select(func.percentile_cont(0.95).within_group(elapsed_ms))
        .join(Event, Event.id == Delivery.event_id)
        .where(Delivery.status == "delivered")
    )
    p99 = await db.scalar(
        select(func.percentile_cont(0.99).within_group(elapsed_ms))
        .join(Event, Event.id == Delivery.event_id)
        .where(Delivery.status == "delivered")
    )
    recent = await db.scalar(
        select(func.count())
        .select_from(Delivery)
        .where(Delivery.delivered_at >= now() - timedelta(minutes=5))
    )
    rate = recent / 5
    long = await objective_windows(db)
    rows = (
        (
            await db.execute(
                text("""
        WITH hours AS (SELECT generate_series(date_trunc('hour', now()) - interval '23 hours', date_trunc('hour', now()), interval '1 hour') AS timestamp),
        e AS (SELECT date_trunc('hour', created_at) AS timestamp, count(*) AS accepted FROM events WHERE created_at >= now() - interval '24 hours' GROUP BY 1),
        d AS (SELECT date_trunc('hour', delivered_at) AS timestamp, count(*) AS delivered FROM deliveries WHERE delivered_at >= now() - interval '24 hours' GROUP BY 1),
        a AS (SELECT date_trunc('hour', ended_at) AS timestamp, count(*) AS failed FROM attempts WHERE failure_category IS NOT NULL AND ended_at >= now() - interval '24 hours' GROUP BY 1)
        SELECT h.timestamp, coalesce(e.accepted,0) AS accepted, coalesce(d.delivered,0) AS delivered, coalesce(a.failed,0) AS failed FROM hours h LEFT JOIN e USING(timestamp) LEFT JOIN d USING(timestamp) LEFT JOIN a USING(timestamp) ORDER BY h.timestamp
    """)
            )
        )
        .mappings()
        .all()
    )
    return {
        "events_total": await db.scalar(select(func.count()).select_from(Event)),
        "deliveries_total": total,
        "queue_depth": depth,
        "in_flight": counts.get("leased", 0),
        "delivered": completed,
        "dead_letter": dead,
        "success_rate": fraction(completed, completed + dead),
        "p95_latency_ms": latency,
        "p99_latency_ms": p99,
        "throughput_per_minute": rate,
        "estimated_drain_seconds": depth / (rate / 60) if rate else None,
        "slo": long,
        "series": [dict(row) for row in rows],
    }


async def detect_incidents():
    cfg = settings()
    async with Session.begin() as db:
        # A shared monitor lock avoids duplicate evaluation across worker pools.
        if not await db.scalar(text("SELECT pg_try_advisory_xact_lock(7319202)")):
            return
        # Monitor evaluation does not need percentile sorts or dashboard chart queries.
        counts = dict(
            (await db.execute(select(Delivery.status, func.count()).group_by(Delivery.status))).all()
        )
        evidence = {
            "dead_letter": counts.get("dead_letter", 0),
            "queue_depth": sum(counts.get(status, 0) for status in ACTIVE),
            "slo": await objective_windows(db),
        }
        conditions = []
        if evidence["dead_letter"] >= cfg.incident_dead_letter_threshold:
            conditions.append(
                (
                    "dead_letters",
                    "Dead-letter accumulation",
                    "warning",
                    "delivery",
                    {"count": evidence["dead_letter"], "threshold": cfg.incident_dead_letter_threshold},
                )
            )
        objective = evidence["slo"]
        if (
            objective["sufficient_data"]
            and objective["short_sufficient_data"]
            and objective["burn_rate"] >= 2
            and objective["short_burn_rate"] >= 2
        ):
            conditions.append(("slo_burn", "Delivery error budget burning", "critical", "slo", objective))
        if evidence["queue_depth"] >= ceil(cfg.max_queue_depth * 0.8):
            conditions.append(
                (
                    "queue_capacity",
                    "Delivery queue nearing capacity",
                    "warning",
                    "queue",
                    {"depth": evidence["queue_depth"], "capacity": cfg.max_queue_depth},
                )
            )
        pools = (await db.scalars(select(Pool))).all()
        for pool in pools:
            healthy = await db.scalar(
                select(Worker.id)
                .where(
                    Worker.region == pool.region,
                    Worker.state == "running",
                    Worker.last_heartbeat > now() - timedelta(seconds=cfg.failover_seconds),
                )
                .limit(1)
            )
            affected = await db.scalar(
                select(func.count())
                .select_from(Delivery)
                .where(Delivery.region == pool.region, Delivery.status.in_(ACTIVE))
            )
            if affected and (not healthy or pool.paused):
                conditions.append(
                    (
                        "pool_" + pool.region,
                        "Worker pool unavailable",
                        "warning",
                        pool.region,
                        {"queued": affected, "paused": pool.paused},
                    )
                )
        for fingerprint, title, severity, component, details in conditions:
            incident = await db.scalar(select(Incident).where(Incident.fingerprint == fingerprint))
            stamp = now()
            if not incident:
                db.add(
                    Incident(
                        fingerprint=fingerprint,
                        title=title,
                        description="Observed threshold exceeded. Inspect evidence and delivery history before remediation.",
                        severity=severity,
                        source=fingerprint,
                        component=component,
                        evidence=details,
                        timeline=[{"at": stamp.isoformat(), "action": "detected", "actor": "monitor"}],
                    )
                )
            elif incident.status == "resolved":
                incident.status = "open"
                incident.updated_at = stamp
                incident.evidence = details
                incident.timeline = incident.timeline + [
                    {"at": stamp.isoformat(), "action": "condition_recurred", "actor": "monitor"}
                ]
            elif incident.evidence != details:
                # Acknowledgement is an operator action, not proof of recovery.
                # Keep the latest evidence current without flooding the timeline.
                incident.evidence = details
                incident.updated_at = stamp
