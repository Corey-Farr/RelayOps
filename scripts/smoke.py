"""Verify real delivery, failure and recovery with bounded condition polling."""

import argparse
import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.request
import uuid

from demo import read_env


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        self.csrf = ""

    def request(self, path, data=None, headers=None, method=None):
        request_headers = {
            "Content-Type": "application/json",
            "X-CSRF-Token": self.csrf,
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(
            self.base + path,
            data=None if data is None else json.dumps(data).encode(),
            headers=request_headers,
            method=method,
        )
        with self.opener.open(request, timeout=10) as response:
            return json.loads(response.read())

    def login(self):
        env = {**read_env(), **os.environ}
        auth = self.request(
            "/api/auth/login",
            {"email": env["ADMIN_EMAIL"], "password": env["ADMIN_PASSWORD"]},
        )
        self.csrf = auth["csrf_token"]


def poll(description, callback, timeout=90):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            result = callback()
            if result:
                return result
        except (urllib.error.URLError, TimeoutError) as exc:
            last = str(exc)
        time.sleep(0.5)
    raise AssertionError(f"Timed out waiting for {description}. Last network error: {last}")


def run(base, monitoring=False):
    client = Client(base)
    poll("database-backed API readiness", lambda: client.request("/ready"))
    client.login()

    def healthy_pools():
        value = client.request("/api/workers")
        return value if len([p for p in value["pools"] if p["healthy"]]) == 3 else None

    pools = poll("three healthy logical worker pools", healthy_pools)
    assert len(pools["pools"]) == 3
    projects = client.request("/api/projects")
    assert projects, "Bootstrap did not create the demo project"
    project = next((item for item in projects if item["name"] == "Demo project"), None)
    assert project, "Bootstrap did not create the named Demo project"
    destinations = client.request(f"/api/destinations?project_id={project['id']}")
    sink_url = os.getenv("DEMO_SINK_URL", read_env().get("DEMO_SINK_URL", "http://demo-sink:8081"))
    assert any(d["enabled"] and d["url"] == sink_url.rstrip("/") + "/webhook" for d in destinations)

    def submit():
        return client.request(
            "/api/events",
            {
                "project_id": project["id"],
                "type": "smoke.delivery",
                "payload": {"source": "integration-smoke"},
            },
            {"Idempotency-Key": str(uuid.uuid4())},
        )

    def delivered(event_id):
        event = client.request(f"/api/events/{event_id}")
        return (
            event
            if event["deliveries"] and all(d["status"] == "delivered" for d in event["deliveries"])
            else None
        )

    client.request("/api/lab/scenario", {"mode": "normal"})
    event = submit()
    result = poll("successful signed webhook delivery", lambda: delivered(event["id"]))
    assert all(d["attempts"] and d["attempts"][-1]["http_status"] == 200 for d in result["deliveries"])
    try:
        client.request("/api/lab/scenario", {"mode": "unavailable"})
        event = submit()

        def failed_attempt():
            details = client.request(f"/api/events/{event['id']}")
            return (
                details
                if any(a["http_status"] == 503 for d in details["deliveries"] for a in d["attempts"])
                else None
            )

        failure = poll("actual HTTP 503 attempt", failed_attempt)
        assert failure
    finally:
        client.request("/api/lab/scenario", {"mode": "normal"})
    result = poll("automatic retry recovery", lambda: delivered(event["id"]))
    assert any(len(d["attempts"]) >= 2 for d in result["deliveries"])
    with urllib.request.urlopen(base.rstrip("/") + "/metrics", timeout=5) as response:
        assert b"relayops_" in response.read()
    if monitoring:
        for url in [
            "http://localhost:9090/-/ready",
            "http://localhost:3000/api/health",
            "http://localhost:16686/",
        ]:
            with urllib.request.urlopen(url, timeout=10) as response:
                assert response.status == 200
    print(
        "PASS: readiness, three worker pools, signed delivery, persisted 503 attempt, retry recovery and metrics"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--monitoring", action="store_true")
    options = parser.parse_args()
    run(options.base_url, options.monitoring)
