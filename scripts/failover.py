"""Verify actual delivery continuity while one local logical pool is paused."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from smoke import Client, poll


def run(base, output):
    if urlsplit(base).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Exercise is restricted to the local demo")
    client = Client(base)
    client.login()
    lab = client.request("/api/lab")
    if not lab["enabled"] or lab["mode"] != "normal":
        raise ValueError("Demo receiver must be in normal mode")
    pools = client.request("/api/workers")["pools"]
    if not all(pool["healthy"] and not pool["paused"] for pool in pools):
        raise ValueError("All three pools must be healthy before this exercise")
    project = next(p for p in client.request("/api/projects") if p["name"] == "Demo project")
    region = "us-east"
    started = datetime.now(UTC).isoformat()
    try:
        client.request(f"/api/workers/{region}/pause", {})
        generated = client.request(
            "/api/lab/generate", {"project_id": project["id"], "count": 30, "seed": 71}
        )

        def delivered():
            events = [client.request(f"/api/events/{identifier}") for identifier in generated["event_ids"]]
            return events if all(event["status"] == "delivered" for event in events) else None

        events = poll("all deliveries during pool pause", delivered)
        reassigned = [
            delivery for event in events for delivery in event["deliveries"] if delivery["region"] == region
        ]
        assert reassigned, "Sample did not include work assigned to the paused pool"
        assert all(
            attempt["region"] != region and attempt["http_status"] == 200
            for delivery in reassigned
            for attempt in delivery["attempts"]
        )
        evidence = {
            "started_at": started,
            "completed_at": datetime.now(UTC).isoformat(),
            "paused_region": region,
            "accepted": len(events),
            "delivered": len(events),
            "reassigned_deliveries": len(reassigned),
            "event_ids": generated["event_ids"],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps({key: value for key, value in evidence.items() if key != "event_ids"}))
    finally:
        client.request(f"/api/workers/{region}/resume", {})
        poll(
            "resumed pool health", lambda: all(p["healthy"] for p in client.request("/api/workers")["pools"])
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--output", type=Path, default=Path(".local/failover.json"))
    args = parser.parse_args()
    run(args.base, args.output)
