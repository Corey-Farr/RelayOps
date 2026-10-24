"""PostgreSQL-backed SLO boundaries and incident lifecycle regression tests."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from relayops.core.config import settings
from relayops.core.db import Session
from relayops.models import Delivery, Incident, now
from relayops.services.ingestion import ingest
from relayops.services.monitoring import detect_incidents, objective_windows, slo

pytestmark = pytest.mark.integration


async def observation(project_id, age, delay=None, status=None, delivery_created_age=None):
    async with Session.begin() as db:
        event, _ = await ingest(db, project_id, "slo.test", {}, str(now().timestamp()))
        delivery = await db.scalar(select(Delivery).where(Delivery.event_id == event.id))
        event.created_at = now() - timedelta(seconds=age)
        delivery.created_at = now() - timedelta(seconds=delivery_created_age or age)
        delivery.status = status or ("delivered" if delay is not None else "dead_letter")
        delivery.delivered_at = event.created_at + timedelta(seconds=delay) if delay is not None else None
        return event.id


async def test_slo_empty_honest_nulls(database):
    async with Session() as db:
        result = await slo(db)
    assert result["eligible"] == 0
    assert result["good"] == 0
    assert result["compliance"] is None
    assert result["burn_rate"] is None
    assert result["error_budget_remaining"] is None
    assert result["sufficient_data"] is False


async def test_slo_maturity_acceptance_and_status(database, monkeypatch):
    monkeypatch.setattr(settings(), "slo_min_samples", 3)
    project = database["project_id"]
    await observation(project, 5, delay=1)  # A success is still too young to count.
    await observation(project, 100, delay=5, delivery_created_age=2)  # Acceptance, not job creation.
    await observation(project, 100, delay=31)  # Success after the deadline spends the budget.
    await observation(project, 100, delay=5, status="leased")  # Nonterminal jobs are not successes.
    await observation(project, 90000, delay=5)  # Outside the rolling window.
    async with Session() as db:
        result = await slo(db)
    assert result["eligible"] == 3
    assert result["good"] == 1
    assert result["compliance"] == pytest.approx(1 / 3)
    assert result["burn_rate"] == pytest.approx((2 / 3) / 0.01)
    assert result["error_budget_remaining"] < 0
    assert result["sufficient_data"] is True


async def test_slo_exact_deadline_inclusive(database):
    await observation(database["project_id"], 100, delay=30)
    async with Session() as db:
        assert (await slo(db))["good"] == 1


async def test_dual_window_requires_short_samples_and_current_burn(database, monkeypatch):
    monkeypatch.setattr(settings(), "slo_min_samples", 2)
    project = database["project_id"]
    await observation(project, 7200)
    await observation(project, 7201)
    await detect_incidents()
    async with Session() as db:
        windows = await objective_windows(db)
        assert windows["sufficient_data"]
        assert not windows["short_sufficient_data"]
        assert not await db.scalar(select(Incident).where(Incident.fingerprint == "slo_burn"))
    # Enough recent samples, but recent health gates the historical failure alert.
    await observation(project, 120, delay=1)
    await observation(project, 121, delay=1)
    await detect_incidents()
    async with Session() as db:
        assert not await db.scalar(select(Incident).where(Incident.fingerprint == "slo_burn"))
    await observation(project, 122)
    await detect_incidents()
    async with Session() as db:
        incident = await db.scalar(select(Incident).where(Incident.fingerprint == "slo_burn"))
        assert incident and incident.component == "slo"
        assert incident.evidence["short_eligible"] == 3


async def test_acknowledgement_retains_current_evidence_and_resolution_reopens(database, monkeypatch):
    monkeypatch.setattr(settings(), "incident_dead_letter_threshold", 1)
    project = database["project_id"]
    await observation(project, 120)
    await detect_incidents()
    async with Session.begin() as db:
        incident = await db.scalar(select(Incident).where(Incident.fingerprint == "dead_letters"))
        identifier = incident.id
        incident.status = "acknowledged"
    await observation(project, 121)
    await detect_incidents()
    async with Session.begin() as db:
        incident = await db.get(Incident, identifier)
        assert incident.status == "acknowledged"
        assert incident.evidence["count"] == 2
        assert len(incident.timeline) == 1  # No duplicate monitoring entries.
        incident.status = "resolved"
    await detect_incidents()
    await detect_incidents()
    async with Session() as db:
        incident = await db.get(Incident, identifier)
        assert incident.status == "open"
        assert len(incident.timeline) == 2
        assert incident.timeline[-1]["action"] == "condition_recurred"


async def test_condition_clearing_does_not_fabricate_manual_resolution(database, monkeypatch):
    monkeypatch.setattr(settings(), "incident_dead_letter_threshold", 1)
    await observation(database["project_id"], 120)
    await detect_incidents()
    async with Session.begin() as db:
        delivery = await db.scalar(select(Delivery))
        delivery.status = "delivered"
        delivery.delivered_at = now()
    await detect_incidents()
    async with Session() as db:
        incident = await db.scalar(select(Incident).where(Incident.fingerprint == "dead_letters"))
        assert incident.status == "open"
