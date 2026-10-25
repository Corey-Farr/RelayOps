"""Verify real local receiver fault modes through the durable worker path."""

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
from urllib.parse import urlsplit

from smoke import Client, poll


def run(base, output):
    if urlsplit(base).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Only the localhost demo is permitted")
    client = Client(base)
    client.login()
    if not client.request("/api/lab")["enabled"]:
        raise ValueError("Demo mode required")
    if client.request("/api/policies")["candidate"]:
        raise ValueError("Finish the active candidate before running fault checks")
    project = next(p for p in client.request("/api/projects") if p["name"] == "Demo project")
    results = []
    for mode in ["normal", "intermittent", "rate_limit", "latency", "timeout"]:
        candidate = None
        try:
            candidate = client.request(
                "/api/policies/candidate",
                {
                    "timeout_seconds": 0.5 if mode == "timeout" else 3,
                    "max_attempts": 5,
                    "backoff_base": 1,
                    "backoff_cap": 5,
                    "canary_percent": 100,
                },
            )
            client.request("/api/lab/scenario", {"mode": mode})
            identifier = client.request(
                "/api/lab/generate",
                {"project_id": project["id"], "count": 1, "seed": 42},
            )["event_ids"][0]

            def attempted():
                event = client.request(f"/api/events/{identifier}")
                return event if event["deliveries"] and event["deliveries"][0]["attempts"] else None

            first = poll(f"{mode} first real attempt", attempted)
            attempt = first["deliveries"][0]["attempts"][0]
            assert first["deliveries"][0]["policy_id"] == candidate["id"]
            expected = {
                "normal": 200,
                "intermittent": 500,
                "rate_limit": 429,
                "latency": 200,
                "timeout": None,
            }[mode]
            assert attempt["http_status"] == expected, (mode, attempt)
            if mode == "timeout":
                assert attempt["failure_category"] == "timeout" and attempt["duration_ms"] >= 400
            if mode == "latency":
                assert attempt["duration_ms"] >= 1900
            client.request("/api/lab/scenario", {"mode": "normal"})

            def recovered():
                event = client.request(f"/api/events/{identifier}")
                return event if event["status"] == "delivered" else None

            event = poll(f"{mode} recovery", recovered)
            attempts = event["deliveries"][0]["attempts"]
            if mode == "rate_limit":
                delay = (
                    datetime.fromisoformat(attempts[1]["started_at"])
                    - datetime.fromisoformat(attempts[0]["ended_at"])
                ).total_seconds()
                assert delay >= 1.9, "Retry-After was not respected"
            results.append(
                {
                    "mode": mode,
                    "event_id": identifier,
                    "policy_id": candidate["id"],
                    "status": event["status"],
                    "attempts": attempts,
                }
            )
            print(
                f"PASS: {mode}: initial {expected or 'timeout'}, recovered delivery with {len(attempts)} attempt(s)"
            )
        finally:
            try:
                client.request("/api/lab/scenario", {"mode": "normal"})
            finally:
                if candidate:
                    current = client.request("/api/policies")
                    if current["candidate"] and current["candidate"]["id"] == candidate["id"]:
                        client.request("/api/policies/rollback", {}, method="POST")
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"recorded_at": datetime.now(UTC).isoformat(), "results": results}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output", default=".local/fault-modes.json")
    args = parser.parse_args()
    run(args.base_url, args.output)
