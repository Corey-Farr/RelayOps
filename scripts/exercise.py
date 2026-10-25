"""Run a bounded local outage -> incident -> redrive recovery exercise."""

import argparse
from datetime import datetime, UTC
import json
from pathlib import Path
from urllib.parse import urlsplit

from smoke import Client, poll


def run(base, output):
    if urlsplit(base).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Exercise is restricted to the local demo")
    client = Client(base)
    client.login()
    if not client.request("/api/lab")["enabled"]:
        raise ValueError("Demo mode is required")
    policies = client.request("/api/policies")
    if policies["candidate"]:
        raise ValueError("Finish the existing candidate rollout before this exercise")
    if client.request("/api/overview")["queue_depth"]:
        raise ValueError("Drain existing work before this exercise")
    project = next(p for p in client.request("/api/projects") if p["name"] == "Demo project")
    timeline = []

    def record(action, **evidence):
        timeline.append({"at": datetime.now(UTC).isoformat(), "action": action, **evidence})

    event_ids = []
    candidate = None
    try:
        candidate = client.request(
            "/api/policies/candidate",
            {
                "timeout_seconds": 3,
                "max_attempts": 1,
                "backoff_base": 1,
                "backoff_cap": 5,
                "canary_percent": 100,
            },
        )
        client.request("/api/lab/scenario", {"mode": "unavailable"})
        record("outage_enabled", policy_id=candidate["id"])
        generated = client.request(
            "/api/lab/generate", {"project_id": project["id"], "count": 20, "seed": 42}
        )
        event_ids = generated["event_ids"]
        record("events_accepted", count=len(event_ids))

        def all_in_state(state):
            events = [client.request(f"/api/events/{identifier}") for identifier in event_ids]
            return events if all(e["status"] == state for e in events) else None

        failed = poll("20 dead-letter events", lambda: all_in_state("dead_letter"))
        assert all(
            any(a["http_status"] == 503 for a in d["attempts"]) for e in failed for d in e["deliveries"]
        )
        record("dead_letters_observed", count=len(failed))

        def detected():
            return next(
                (
                    i
                    for i in client.request("/api/incidents")
                    if i["source"] == "dead_letters" and i["status"] == "open"
                ),
                None,
            )

        incident = poll("automatic dead-letter incident", detected)
        record(
            "incident_detected",
            incident_id=incident["id"],
            evidence=incident["evidence"],
        )
        acknowledged = client.request(f"/api/incidents/{incident['id']}/acknowledge", {}, method="POST")
        assert acknowledged["status"] == "acknowledged"
        record("incident_acknowledged")
        client.request("/api/lab/scenario", {"mode": "normal"})
        record("receiver_restored")
        for event in failed:
            for delivery in event["deliveries"]:
                client.request(f"/api/deliveries/{delivery['id']}/redrive", {}, method="POST")
        recovered = poll("redriven deliveries recovered", lambda: all_in_state("delivered"))
        assert all(len(d["attempts"]) >= 2 for e in recovered for d in e["deliveries"])
        record("deliveries_recovered", count=len(recovered))
        resolved = client.request(f"/api/incidents/{incident['id']}/resolve", {}, method="POST")
        assert resolved["status"] == "resolved"
        record("incident_resolved")
        report = {
            "scenario": "destination outage and dead-letter recovery",
            "timeline": timeline,
            "event_ids": event_ids,
            "incident": resolved,
            "attempts": [
                {
                    "event_id": e["id"],
                    "deliveries": [
                        {
                            "id": d["id"],
                            "status": d["status"],
                            "attempts": d["attempts"],
                        }
                        for d in e["deliveries"]
                    ],
                }
                for e in recovered
            ],
        }
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(
            f"PASS: 20 real HTTP failures, automatic incident, acknowledgement, redrive and resolution. Evidence: {path}"
        )
    finally:
        try:
            client.request("/api/lab/scenario", {"mode": "normal"})
        finally:
            if candidate:
                current = client.request("/api/policies")
                if current["candidate"] and current["candidate"]["id"] == candidate["id"]:
                    client.request("/api/policies/rollback", {}, method="POST")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output", default=".local/incident-exercise.json")
    args = parser.parse_args()
    run(args.base_url, args.output)
