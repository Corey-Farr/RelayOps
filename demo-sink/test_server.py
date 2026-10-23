import hashlib
import hmac
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import server


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(server, "STATE_PATH", Path(self.temp.name) / "state.json")
        self.path_patch.start()
        server.SECRET = "s" * 32
        server.CONTROL_TOKEN = "c" * 32
        self.httpd = server.Server(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()
        self.path_patch.stop()
        self.temp.cleanup()

    def request(self, path, body=None, method=None, headers=None):
        request = urllib.request.Request(self.base + path, data=body, method=method, headers=headers or {})
        try:
            return urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            return error

    def deliver(self, signature=None):
        body = b'{"type":"test"}'
        ts = str(int(time.time()))
        sig = hmac.new(server.SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        return self.request("/webhook", body, headers={"X-RelayOps-Timestamp": ts,
                            "X-RelayOps-Signature": signature or "sha256=" + sig})

    def fault(self, mode):
        return self.request("/control", json.dumps({"mode": mode}).encode(), "POST",
                            {"X-Control-Token": server.CONTROL_TOKEN})

    def test_signature_body_and_age(self):
        self.assertEqual(self.deliver().status, 200)
        self.assertEqual(self.deliver("bad").status, 401)
        self.assertFalse(server.verify(b"x", "1", "bad", server.SECRET))
        self.assertFalse(server.verify(b"x", "invalid", "bad", server.SECRET))

    def test_control_requires_token_and_valid_mode(self):
        self.assertEqual(self.request("/control", b'{"mode":"unavailable"}', "POST").status, 401)
        self.assertEqual(self.fault("arbitrary-url").status, 422)
        self.assertEqual(self.deliver().status, 200)

    def test_persistent_outage_recovery_and_intermit(self):
        self.assertEqual(self.fault("unavailable").status, 200)
        self.assertEqual(server.read_state()["mode"], "unavailable")
        self.assertEqual(self.deliver().status, 503)
        self.fault("intermittent")
        self.assertEqual(self.deliver().status, 500)
        self.assertEqual(self.deliver().status, 200)
        self.fault("normal")
        self.assertEqual(self.deliver().status, 200)

    def test_rate_limit_and_delay_modes(self):
        self.fault("rate_limit")
        response = self.deliver()
        self.assertEqual(response.status, 429)
        self.assertEqual(response.headers["Retry-After"], "2")
        for mode, delay in [("latency", 2), ("timeout", 35)]:
            self.fault(mode)
            with patch.object(server.time, "sleep") as sleep:
                self.assertEqual(self.deliver().status, 200)
                sleep.assert_called_once_with(delay)


if __name__ == "__main__":
    unittest.main()
