"""Launcher regression checks; isolated directories and sockets, no running stack mutation."""

import base64
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import demo
import native


class LaunchTests(unittest.TestCase):
    def test_init_preserves_secrets_and_creates_valid_fernet_key(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(demo, "ROOT", Path(directory)):
            demo.initialize()
            initial = (Path(directory) / ".env").read_bytes()
            values = demo.read_env()
            self.assertEqual(len(base64.urlsafe_b64decode(values["ENCRYPTION_KEY"])), 32)
            self.assertGreaterEqual(len(values["ADMIN_PASSWORD"]), 24)
            self.assertNotEqual(values["DEMO_CONTROL_TOKEN"], values["DEMO_SIGNING_SECRET"])
            demo.initialize()
            self.assertEqual(initial, (Path(directory) / ".env").read_bytes())

    def test_incomplete_env_is_rejected_without_replacing_credentials(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(demo, "ROOT", Path(directory)):
            path = Path(directory) / ".env"
            path.write_text("ADMIN_PASSWORD=keep-this-value\n")
            with self.assertRaises(SystemExit):
                demo.initialize()
            self.assertEqual(path.read_text(), "ADMIN_PASSWORD=keep-this-value\n")

    def test_missing_docker_is_explicit(self):
        with patch.object(demo.shutil, "which", return_value=None):
            with self.assertRaisesRegex(SystemExit, "Docker is unavailable"):
                demo.compose("up")

    def test_native_checks_port_before_startup(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            with self.assertRaisesRegex(SystemExit, "is in use"):
                native.check_ports([listener.getsockname()[1]])

    def test_native_frontend_launches_node_directly(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(native, "ROOT", Path(directory)):
            vite = Path(directory) / "frontend/node_modules/vite/bin/vite.js"
            vite.parent.mkdir(parents=True)
            vite.write_text("// fixture")
            with patch.object(native.shutil, "which", return_value="node"):
                command = native.frontend_command()
            self.assertEqual(command[:2], ["node", str(vite)])
            self.assertIn("--strictPort", command)


if __name__ == "__main__":
    unittest.main()
