"""Run the native demo against an existing PostgreSQL instance; stop with Ctrl+C."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

from demo import ROOT, initialize, read_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frontend",
        action="store_true",
        help="also run Vite on localhost:8080 (npm ci first)",
    )
    parser.add_argument("--api-port", type=int, default=8000)
    args = parser.parse_args()
    initialize()
    env = {**read_env(), **os.environ}
    if not env.get("DATABASE_URL"):
        raise SystemExit(
            "Set DATABASE_URL to an existing local PostgreSQL database; this launcher does not install PostgreSQL."
        )
    env.update(
        {
            "APP_ENV": "demo",
            "DEMO_SINK_URL": "http://127.0.0.1:8081",
            "SINK_HOST": "127.0.0.1",
            "SINK_STATE_PATH": str(ROOT / ".local" / "sink" / "fault.json"),
            "OTEL_EXPORTER_OTLP_ENDPOINT": env.get("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
        }
    )
    executable = (
        ROOT
        / "backend"
        / ".venv"
        / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    python = str(executable) if executable.exists() else sys.executable
    subprocess.run(
        [python, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env=env,
        check=True,
    )
    subprocess.run(
        [python, "-m", "relayops.bootstrap"], cwd=ROOT / "backend", env=env, check=True
    )
    local = ROOT / ".local" / "native"
    local.mkdir(parents=True, exist_ok=True)
    children = []
    logs = []

    def start(name, command, cwd, overrides=None):
        log = (local / f"{name}.log").open("a", encoding="utf-8")
        logs.append(log)
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env={**env, **(overrides or {})},
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        children.append((name, process))

    try:
        start("sink", [python, "-u", "server.py"], ROOT / "demo-sink")
        start(
            "api",
            [
                python,
                "-m",
                "uvicorn",
                "relayops.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.api_port),
            ],
            ROOT / "backend",
        )
        for index, region in enumerate(["us-east", "eu-west", "ap-southeast"]):
            start(
                region,
                [python, "-m", "relayops.workers.runner"],
                ROOT / "backend",
                {
                    "WORKER_REGION": region,
                    "WORKER_ID": f"native-{region}",
                    "WORKER_METRICS_PORT": str(9001 + index),
                },
            )
        if args.frontend:
            npm = shutil.which("npm")
            if not npm:
                raise SystemExit("npm is required for --frontend")
            start(
                "frontend",
                [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", "8080"],
                ROOT / "frontend",
            )
        (local / "pids.json").write_text(
            json.dumps({name: process.pid for name, process in children})
        )
        print(
            f"Native demo API http://localhost:{args.api_port}; logs in {local}. Ctrl+C stops child processes."
        )
        print(
            "Monitoring containers are not started. Use DEMO_SINK_URL=http://127.0.0.1:8081 with scripts/smoke.py."
        )
        while True:
            for name, process in children:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"{name} exited with {process.returncode}; inspect {local / (name + '.log')}"
                    )
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping native processes...")
    finally:
        for _, process in reversed(children):
            if process.poll() is None:
                process.terminate()
        for _, process in reversed(children):
            try:
                process.wait(timeout=40)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for log in logs:
            log.close()
        (local / "pids.json").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
