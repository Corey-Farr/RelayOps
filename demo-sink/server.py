"""Local-only receiver: real HMAC verification and persistent, bounded fault injection."""

import hashlib
import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODES = {"normal", "intermittent", "rate_limit", "latency", "timeout", "unavailable"}
LOCK = threading.Lock()
STATE_PATH = Path(os.getenv("SINK_STATE_PATH", "/data/fault.json"))
SECRET = os.getenv("DEMO_SIGNING_SECRET", "")
CONTROL_TOKEN = os.getenv("DEMO_CONTROL_TOKEN", "")


def verify(body: bytes, timestamp: str, signature: str, secret: str, now=None) -> bool:
    try:
        if abs((time.time() if now is None else now) - int(timestamp)) > 300:
            return False
    except (TypeError, ValueError):
        return False
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature.removeprefix("sha256="), expected)


def read_state():
    if not STATE_PATH.exists():
        return {"mode": "normal", "requests": 0}
    return json.loads(STATE_PATH.read_text())


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state))
    temporary.replace(STATE_PATH)


class Handler(BaseHTTPRequestHandler):
    server_version = "RelayOpsDemoSink/1"

    def log_message(self, fmt, *args):
        # Do not log bodies, headers, tokens or query strings.
        print(
            json.dumps(
                {
                    "service": "demo-sink",
                    "method": self.command,
                    "path": self.path.split("?")[0],
                    "status": str(args[1]) if len(args) > 1 else "unknown",
                }
            ),
            flush=True,
        )

    def respond(self, status, body, headers=None):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Expected when timeout mode outlives the dispatcher's deadline.

    def authenticated(self):
        return hmac.compare_digest(self.headers.get("X-Control-Token", ""), CONTROL_TOKEN)

    def body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid content length") from None
        if not 0 <= length <= 262144:
            raise ValueError("body exceeds 256 KiB")
        return self.rfile.read(length)

    def do_GET(self):
        if self.path == "/health":
            return self.respond(200, {"status": "ok"})
        if self.path == "/control" and self.authenticated():
            with LOCK:
                state = read_state()
            return self.respond(200, state)
        self.respond(404, {"detail": "not found"})

    def control(self):
        if self.path != "/control":
            return self.respond(404, {"detail": "not found"})
        if not self.authenticated():
            return self.respond(401, {"detail": "invalid control token"})
        try:
            data = json.loads(self.body())
            mode = data["mode"]
            if mode not in MODES:
                raise ValueError("unsupported mode")
            with LOCK:
                state = {"mode": mode, "requests": 0}
                save_state(state)
        except (ValueError, TypeError, KeyError):
            return self.respond(422, {"detail": "a supported mode is required"})
        self.respond(200, state)

    def do_POST(self):
        if self.path == "/control":
            return self.control()
        if self.path != "/webhook":
            return self.respond(404, {"detail": "not found"})
        try:
            body = self.body()
        except ValueError as exc:
            return self.respond(413, {"detail": str(exc)})
        if not verify(
            body,
            self.headers.get("X-RelayOps-Timestamp", ""),
            self.headers.get("X-RelayOps-Signature", ""),
            SECRET,
        ):
            return self.respond(401, {"detail": "signature verification failed"})
        with LOCK:
            state = read_state()
            state["requests"] += 1
            save_state(state)
        mode = state["mode"]
        if mode == "unavailable":
            return self.respond(503, {"detail": "simulated destination outage"})
        if mode == "intermittent" and state["requests"] % 2 == 1:
            return self.respond(500, {"detail": "simulated intermittent failure"})
        if mode == "rate_limit":
            return self.respond(429, {"detail": "simulated rate limit"}, {"Retry-After": "2"})
        if mode == "latency":
            time.sleep(2)
        elif mode == "timeout":
            time.sleep(35)
        self.respond(200, {"accepted": True, "event_id": self.headers.get("X-RelayOps-Event-ID")})


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64
    slots = threading.BoundedSemaphore(64)

    def process_request(self, request, client_address):
        request.settimeout(10)
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


if __name__ == "__main__":
    if len(SECRET) < 32 or len(CONTROL_TOKEN) < 32:
        raise SystemExit(
            "DEMO_SIGNING_SECRET and DEMO_CONTROL_TOKEN must each contain at least 32 characters"
        )
    Server((os.getenv("SINK_HOST", "127.0.0.1"), 8081), Handler).serve_forever()
