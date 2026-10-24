"""Run the native demo against an existing PostgreSQL instance; stop with Ctrl+C."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time

from demo import ROOT, initialize, read_env


def check_ports(ports):
    """Fail before migrations or process creation when another local stack is active."""
    for port in ports:
        with socket.socket() as listener:
            try:
                listener.bind(("127.0.0.1", port))
            except OSError:
                raise SystemExit(
                    f"Local port {port} is in use; stop its owning service before native startup."
                ) from None


def frontend_command():
    node = shutil.which("node")
    vite = ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
    if not node or not vite.exists():
        raise SystemExit("Install Node.js and run npm ci in frontend before --frontend.")
    return [node, str(vite), "--host", "127.0.0.1", "--port", "8080", "--strictPort"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frontend",
        action="store_true",
        help="also run Vite on localhost:8080 (npm ci first)",
    )
    parser.add_argument("--api-port", type=int, default=8000)
    args = parser.parse_args()
    if not 1024 <= args.api_port <= 65535:
        parser.error("--api-port must be between 1024 and 65535")
    ports = [args.api_port, 8081, 9001, 9002, 9003] + ([8080] if args.frontend else [])
    if len(set(ports)) != len(ports):
        parser.error("--api-port conflicts with another native service")
    check_ports(ports)
    frontend = frontend_command() if args.frontend else None
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
            "API_PROXY_TARGET": f"http://127.0.0.1:{args.api_port}",
        }
    )
    executable = ROOT / "backend" / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python = str(executable) if executable.exists() else sys.executable
    subprocess.run(
        [python, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env=env,
        check=True,
    )
    subprocess.run([python, "-m", "relayops.bootstrap"], cwd=ROOT / "backend", env=env, check=True)
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
        if frontend:
            start(
                "frontend",
                frontend,
                ROOT / "frontend",
            )
        (local / "pids.json").write_text(json.dumps({name: process.pid for name, process in children}))
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
