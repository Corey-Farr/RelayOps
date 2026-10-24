"""Cross-platform local launcher; Python 3.12+, Docker Engine and Compose v2 required."""

import argparse
import base64
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_env():
    path = ROOT / ".env"
    if not path.exists():
        return {}
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
    )


def initialize():
    path = ROOT / ".env"
    if path.exists():
        required = {
            "POSTGRES_PASSWORD",
            "SESSION_SECRET",
            "ENCRYPTION_KEY",
            "ADMIN_PASSWORD",
            "DEMO_SIGNING_SECRET",
            "DEMO_CONTROL_TOKEN",
            "GRAFANA_PASSWORD",
        }
        values = read_env()
        if any(not values.get(key) for key in required):
            raise SystemExit(
                "Existing .env is incomplete; populate its empty secret values or move it aside and run init."
            )
        print("Using existing .env; credentials and data are preserved.")
        return
    values = {
        "APP_ENV": "demo",
        "POSTGRES_PASSWORD": secrets.token_hex(24),
        "SESSION_SECRET": secrets.token_hex(32),
        "ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "ADMIN_EMAIL": "admin@relayops.local",
        "ADMIN_PASSWORD": secrets.token_urlsafe(24),
        "DEMO_SIGNING_SECRET": secrets.token_hex(32),
        "DEMO_CONTROL_TOKEN": secrets.token_hex(32),
        "DEMO_SINK_URL": "http://demo-sink:8081",
        "GRAFANA_PASSWORD": secrets.token_urlsafe(24),
    }
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write("# Generated local secrets. Do not commit or share.\n")
        handle.writelines(f"{key}={value}\n" for key, value in values.items())
    print("Generated private .env. Administrator email/password: ADMIN_EMAIL / ADMIN_PASSWORD in that file.")
    print("Grafana username: admin; password: GRAFANA_PASSWORD in .env.")


def compose(*args):
    if not shutil.which("docker"):
        raise SystemExit("Docker is unavailable. Install Docker with Compose v2, then rerun this command.")
    subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "demo", "up", "down", "clean"])
    args = parser.parse_args()
    if args.command in {"init", "demo", "up"}:
        initialize()
    if args.command in {"demo", "up"}:
        compose("up", "--build", "--detach", "--wait", "--wait-timeout", "180")
        print("Application http://localhost:8080 | API http://localhost:8000/docs")
        print(
            "Grafana http://localhost:3000 | Prometheus http://localhost:9090 | Jaeger http://localhost:16686"
        )
        print(
            "Login with ADMIN_EMAIL / ADMIN_PASSWORD in .env; initialization runs migrations and seeds the demo."
        )
    elif args.command == "down":
        compose("down")
    elif args.command == "clean":
        compose("down", "--volumes", "--remove-orphans")
        print("Removed demo database and monitoring volumes. .env retained to preserve credentials.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
