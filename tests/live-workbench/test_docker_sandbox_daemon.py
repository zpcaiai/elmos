#!/usr/bin/env python3
"""Integration tests for Docker Sandbox Daemon."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import subprocess
import time
import unittest
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
DAEMON_SCRIPT = ROOT / "scripts/live_workbench/docker_sandbox_daemon.py"
PORT = 8099
KEY = "0123456789abcdef0123456789abcdef"


def compute_sig(path: str, idempotency: str, ts: str, body: bytes, key: str) -> tuple[str, str]:
    body_sha = hashlib.sha256(body).hexdigest()
    canonical = f"lw.v1\n{path}\n{idempotency}\n{ts}\n{body_sha}".encode("utf-8")
    sig = hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return body_sha, sig


class DockerSandboxDaemonTest(unittest.TestCase):
    daemon_proc: subprocess.Popen | None = None

    @classmethod
    def setUpClass(cls):
        import sys
        cls.daemon_proc = subprocess.Popen(
            [sys.executable, str(DAEMON_SCRIPT), "--port", str(PORT), "--key", KEY, "--repo-root", str(ROOT)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        time.sleep(1.0)

    @classmethod
    def tearDownClass(cls):
        if cls.daemon_proc:
            cls.daemon_proc.terminate()
            cls.daemon_proc.wait(timeout=5)

    def _request(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        url = f"http://127.0.0.1:{PORT}{path}"
        idempotency = f"test-idemp-{int(time.time() * 1000)}"
        ts = str(int(time.time()))
        body_bytes = json.dumps(payload).encode("utf-8") if payload else b""
        body_sha, sig = compute_sig(path, idempotency, ts, body_bytes, KEY)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency,
            "X-Elmos-Timestamp": ts,
            "X-Elmos-Body-SHA256": body_sha,
            "X-Elmos-Signature": sig,
        }
        req = urllib.request.Request(url, data=body_bytes if method == "POST" else None, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return resp.status, data
        except urllib.error.HTTPError as err:
            err_data = json.loads(err.read().decode("utf-8"))
            return err.code, err_data

    def test_01_health(self):
        status, data = self._request("GET", "/v1/workbench/health")
        self.assertEqual(200, status)
        self.assertEqual("lw.v1", data["schemaVersion"])
        self.assertTrue(data["dockerAvailable"])

    def test_02_admission(self):
        status, data = self._request("POST", "/v1/workbench/admission", {
            "snapshotId": "sha256:" + "0" * 64,
            "sessionId": "test-session-1",
        })
        self.assertEqual(200, status)
        self.assertEqual("ROOTLESS_OCI", data["isolationProvider"])
        self.assertTrue(data["capabilityAttested"])

    def test_03_session_lifecycle(self):
        sess_id = f"test-run-{int(time.time())}"
        status, alloc = self._request("POST", "/v1/workbench/sessions", {
            "sessionId": sess_id,
            "requestedHardDeadlineEpochSecond": int(time.time()) + 600,
        })
        self.assertEqual(200, status)
        prov_id = alloc["providerSessionId"]

        status, dbg = self._request("POST", f"/v1/workbench/sessions/{prov_id}/debug-commands", {
            "command": "next",
            "commandId": "cmd-1",
        })
        self.assertEqual(200, status)
        self.assertEqual("COMMITTED", dbg["state"])

        status, prev = self._request("POST", f"/v1/workbench/sessions/{prov_id}/preview-access")
        self.assertEqual(200, status)
        self.assertTrue(prev["url"].startswith("https://preview.example.test/preview/"))

        status, cl = self._request("POST", f"/v1/workbench/sessions/{prov_id}/cleanup")
        self.assertEqual(200, status)
        self.assertEqual("CLEANED", cl["status"])
        self.assertTrue(cl["memberChecks"]["containerKilled"])


if __name__ == "__main__":
    import sys
    unittest.main()
