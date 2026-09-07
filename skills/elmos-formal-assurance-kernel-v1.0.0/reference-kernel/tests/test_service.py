from __future__ import annotations
import json
import unittest
from elmos_formal_assurance.service import application, make_environ

def call(path, method="GET", payload=None):
    captured = {}
    def start(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)
    body = b"".join(application(make_environ(path,method,payload), start))
    return captured["status"], captured["headers"], body

class ServiceTests(unittest.TestCase):
    def test_livez(self):
        status, _, body = call("/livez")
        self.assertEqual("200 OK", status)
        self.assertEqual("live", json.loads(body)["status"])

    def test_readyz(self):
        status, _, _ = call("/readyz")
        self.assertEqual("200 OK", status)

    def test_metrics(self):
        status, headers, body = call("/metrics")
        self.assertEqual("200 OK", status)
        self.assertIn(b"kernel_ready 1", body)

    def test_version(self):
        status, _, body = call("/version")
        self.assertEqual("1.0.0", json.loads(body)["version"])

    def test_gate_endpoint_denies_unknown(self):
        payload = {
          "obligations":[{"id":"o1","criticality":"P0","propertyKind":"STATE_INVARIANT","requiredAssurance":"A2_SOLVER_PROVED"}],
          "results":[{"obligationId":"o1","status":"UNKNOWN_TIMEOUT","assuranceLevel":"NONE","mode":"SMT"}]
        }
        status, _, body = call("/v1/gates/evaluate","POST",payload)
        self.assertEqual("200 OK", status)
        self.assertEqual("DENY", json.loads(body)["decision"])

    def test_bad_gate_payload_returns_400(self):
        status, _, _ = call("/v1/gates/evaluate","POST",{"obligations":[{"id":"x"}]})
        self.assertEqual("400 Bad Request", status)

    def test_not_found(self):
        status, _, _ = call("/missing")
        self.assertEqual("404 Not Found", status)

if __name__ == "__main__":
    unittest.main()
