from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid

from elmos_pi_harness.api import HarnessHTTPServer
from elmos_pi_harness.persistence import DurableStore


def uid() -> str:
    return str(uuid.uuid4())


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="pi-harness-api-")
        self.store = DurableStore(":memory:", artifact_root=self.temp.name)
        self.server = HarnessHTTPServer(("127.0.0.1", 0), self.store, api_token="test-token")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.tenant = uid()
        self.other_tenant = uid()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.store.close()
        self.temp.cleanup()

    def request(self, path: str, *, method: str = "GET", body: dict | None = None, tenant: str | None = None, key: str | None = None):
        headers = {"Authorization": "Bearer test-token", "X-Tenant-Id": tenant or self.tenant, "X-Actor-Id": "operator-1"}
        if key:
            headers["Idempotency-Key"] = key
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, method=method, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status, json.loads(response.read())

    def test_authenticated_idempotent_task_api_and_tenant_isolation(self) -> None:
        payload = {"project_id": uid(), "objective": "API task"}
        status, created = self.request("/v1/tasks", method="POST", body=payload, key="api-create-1")
        self.assertEqual(status, 201)
        task_id = created["task_id"]
        status, replay = self.request("/v1/tasks", method="POST", body=payload, key="api-create-1")
        self.assertEqual(status, 200)
        self.assertEqual(replay["task_id"], task_id)
        status, detail = self.request(f"/v1/tasks/{task_id}")
        self.assertEqual((status, detail["status"]), (200, "CREATED"))
        status, events = self.request(f"/v1/tasks/{task_id}/events")
        self.assertEqual((status, events["items"][0]["event_type"]), (200, "task.created"))
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request(f"/v1/tasks/{task_id}", tenant=self.other_tenant)
        self.assertEqual(error.exception.code, 404)
        error.exception.close()

    def test_missing_bearer_is_rejected(self) -> None:
        req = urllib.request.Request(self.base + "/v1/tasks", method="GET")
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(error.exception.code, 401)
        error.exception.close()


if __name__ == "__main__":
    unittest.main()
