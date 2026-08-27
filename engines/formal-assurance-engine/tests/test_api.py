from __future__ import annotations

import json
import unittest

from elmos_formal_assurance.api import FormalAssuranceApi, make_environ
from elmos_formal_assurance.contracts import TrustedIdentity
from elmos_formal_assurance.runtime import FormalAssuranceRuntime
from elmos_formal_assurance.store import StateStore


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = StateStore()
        self.api = FormalAssuranceApi(FormalAssuranceRuntime(store=self.store))
        self.identity = TrustedIdentity("tenant-a", "operator-a", "project-a")

    def tearDown(self) -> None:
        self.store.close()

    def call(
        self,
        path: str,
        method: str = "GET",
        payload: dict[str, object] | None = None,
        identity: TrustedIdentity | None = None,
        trusted: bool = True,
    ) -> tuple[str, dict[str, object] | list[object]]:
        environ = make_environ(path, method, payload, identity)
        environ["elmos.trusted_transport"] = trusted
        captured: list[str] = []
        body = b"".join(
            self.api(environ, lambda status, headers: captured.append(status))
        )
        return captured[0], json.loads(body)

    def test_health_and_listing(self) -> None:
        status, payload = self.call("/livez")
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["status"], "live")
        status, payload = self.call("/v1/skills")
        self.assertEqual(status, "200 OK")
        self.assertEqual(len(payload["skills"]), 60)

    def test_execute_requires_transport_identity(self) -> None:
        status, payload = self.call(
            "/v1/skills/elmos-requirement-to-formal-spec/execute",
            "POST",
            {"requirements": "The route must preserve tenant isolation"},
            trusted=False,
        )
        self.assertEqual(status, "403 Forbidden")
        self.assertIn("identity", payload["error"])

    def test_execute_uses_authenticated_scope(self) -> None:
        payload = {
            "scope": {
                "tenantId": "tenant-a",
                "accountId": "account-a",
                "projectId": "project-a",
                "sourceArtifactDigest": "a" * 64,
                "targetArtifactDigest": "b" * 64,
                "environmentDigest": "c" * 64,
                "workloadKey": "api-test",
            },
            "subjectId": "subject-a",
            "idempotencyKey": "api-1",
            "requirements": "The route must preserve tenant isolation",
        }
        status, result = self.call(
            "/v1/skills/elmos-requirement-to-formal-spec/execute",
            "POST",
            payload,
            self.identity,
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(result["scope"]["tenantId"], "tenant-a")
        self.assertEqual(result["proofStatus"], "BOUNDED_NO_COUNTEREXAMPLE")


if __name__ == "__main__":
    unittest.main()
