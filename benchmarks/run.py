"""Run a bounded local k6 workload and save measured results, never synthetic statistics."""

import argparse
import datetime
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from smoke import Client  # noqa: E402 - shared local CLI client after adding scripts to the import path


def percentile(values, quantile):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def run(args):
    host = urlsplit(args.base_url).hostname
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("Benchmarks are restricted to a localhost demo API.")
    client = Client(args.base_url)
    client.login()
    if not client.request("/api/lab")["enabled"]:
        raise SystemExit("Benchmarks require explicitly enabled demo mode.")
    projects = client.request("/api/projects")
    project = (
        next((p for p in projects if p["id"] == args.project_id), None)
        if args.project_id
        else next((p for p in projects if p["name"] == "Demo project"), None)
    )
    if not project:
        raise SystemExit("No matching project; initialize the demo first.")
    run_id = uuid.uuid4().hex
    output = ROOT / "benchmarks" / "results" / run_id
    output.mkdir(parents=True)
    key = client.request(f"/api/projects/{project['id']}/keys", {"name": f"benchmark-{run_id}"})
    env = {
        **os.environ,
        "BASE_URL": args.base_url,
        "PROJECT_ID": project["id"],
        "API_KEY": key["key"],
        "RUN_ID": run_id,
        "SCENARIO": args.scenario,
        "RATE": str(args.rate),
        "VUS": str(args.vus),
        "DURATION": f"{args.seconds}s",
        "SUMMARY_PATH": str(output / "k6-summary.json"),
    }
    snapshots = []
    errors = []
    stop = threading.Event()

    def sample():
        while not stop.is_set():
            try:
                overview = client.request("/api/overview")
                snapshots.append(
                    {
                        "at": datetime.datetime.now(datetime.UTC).isoformat(),
                        "queue_depth": overview["queue_depth"],
                        "in_flight": overview["in_flight"],
                        "estimated_drain_seconds": overview["estimated_drain_seconds"],
                    }
                )
            except (URLError, TimeoutError, ValueError, KeyError) as exc:
                errors.append(type(exc).__name__)
            stop.wait(2)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    start = time.monotonic()
    code = None
    details = []
    try:
        if shutil.which("k6"):
            command = ["k6", "run", str(ROOT / "benchmarks" / "ingestion.js")]
        elif shutil.which("docker"):
            env["BASE_URL"] = "http://api:8000"
            env["SUMMARY_PATH"] = "/results/k6-summary.json"
            command = [
                "docker",
                "run",
                "--rm",
                "--network",
                "relayops_default",
                "--user",
                "0:0",
            ]
            for name in [
                "BASE_URL",
                "PROJECT_ID",
                "API_KEY",
                "RUN_ID",
                "SCENARIO",
                "RATE",
                "VUS",
                "DURATION",
                "SUMMARY_PATH",
            ]:
                command += ["-e", name]
            command += [
                "-v",
                f"{ROOT / 'benchmarks'}:/scripts:ro",
                "-v",
                f"{output}:/results",
                "grafana/k6:1.3.0",
                "run",
                "/scripts/ingestion.js",
            ]
        else:
            raise SystemExit("Install k6 or run the Compose demo with Docker to benchmark.")
        code = subprocess.run(command, env=env, check=False).returncode
        deadline = time.monotonic() + args.drain_seconds
        while True:
            events = client.request(f"/api/events?search=benchmark.{run_id}&limit=100")
            details = [client.request(f"/api/events/{event['id']}") for event in events]
            unsettled = any(
                d["status"] not in {"delivered", "dead_letter"} for e in details for d in e["deliveries"]
            )
            if not unsettled or time.monotonic() >= deadline:
                break
            time.sleep(2)
    finally:
        stop.set()
        thread.join(timeout=12)
        client.request(f"/api/keys/{key['id']}", method="DELETE")
    latencies = [
        (
            datetime.datetime.fromisoformat(d["delivered_at"])
            - datetime.datetime.fromisoformat(e["created_at"])
        ).total_seconds()
        * 1000
        for e in details
        for d in e["deliveries"]
        if d.get("delivered_at")
    ]
    report = {
        "run_id": run_id,
        "recorded_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
        "configuration": vars(args),
        "elapsed_seconds_including_drain": time.monotonic() - start,
        "k6_exit_code": code,
        "backlog_samples": snapshots,
        "sample_errors": errors,
        "end_to_end": {
            "sample_event_count": len(details),
            "delivered_sample_count": len(latencies),
            "p50_ms": percentile(latencies, 0.50),
            "p95_ms": percentile(latencies, 0.95),
            "p99_ms": percentile(latencies, 0.99),
        },
        "limitations": "End-to-end latencies sample at most 100 newest matching events; backlog includes all project activity. Null means no measured deliveries.",
    }
    summary_path = output / "k6-summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())["metrics"]
        reqs = summary.get("http_reqs", {}).get("values", {})
        durations = summary.get("http_req_duration", {}).get("values", {})
        accepted = summary.get("events_accepted", {}).get("values", {}).get("count", 0)
        report["ingestion"] = {
            "total_requests": reqs.get("count"),
            "successful_requests": accepted,
            "failed_or_rejected_requests": reqs.get("count", 0) - accepted,
            "requests_per_second": reqs.get("rate"),
            "p50_ms": durations.get("med"),
            "p95_ms": durations.get("p(95)"),
            "p99_ms": durations.get("p(99)"),
            "backpressure_responses": summary.get("backpressure_responses", {})
            .get("values", {})
            .get("count", 0),
        }
    (output / "report.json").write_text(json.dumps(report, indent=2))
    print(f"Measured report: {output / 'report.json'}")
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--project-id")
    parser.add_argument(
        "--scenario",
        choices=["ingestion", "concurrent", "burst", "sustained", "backpressure"],
        default="sustained",
    )
    parser.add_argument("--rate", type=int, choices=range(1, 201), default=20, metavar="1..200")
    parser.add_argument("--vus", type=int, choices=range(1, 101), default=10, metavar="1..100")
    parser.add_argument("--seconds", type=int, choices=range(1, 301), default=30, metavar="1..300")
    parser.add_argument("--drain-seconds", type=int, default=60)
    run(parser.parse_args())
