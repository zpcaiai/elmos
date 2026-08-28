from __future__ import annotations

import json
import unittest

from elmos_formal_assurance.api import FormalAssuranceApi, make_environ
from elmos_formal_assurance.contracts import Scope, TrustedIdentity
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
        headers: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, object] | list[object]]:
        environ = make_environ(path, method, payload, identity)
        environ["elmos.trusted_transport"] = trusted
        environ.update(headers or {})
        captured: list[str] = []
        body = b"".join(
            self.api(environ, lambda status, headers: captured.append(status))
        )
        return captured[0], json.loads(body)

    def resource_headers(self, key: str = "api-document-1") -> dict[str, str]:
        return {
            "HTTP_X_ELMOS_ACCOUNT_ID": "account-a",
            "HTTP_X_ELMOS_PROJECT_ID": "project-a",
            "HTTP_X_ELMOS_SOURCE_ARTIFACT_DIGEST": "a" * 64,
            "HTTP_X_ELMOS_TARGET_ARTIFACT_DIGEST": "b" * 64,
            "HTTP_X_ELMOS_ENVIRONMENT_DIGEST": "c" * 64,
            "HTTP_X_ELMOS_WORKLOAD_KEY": "api-contract",
            "HTTP_X_ELMOS_IDEMPOTENCY_KEY": key,
        }

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

    def test_formal_spec_and_proof_plan_contract_routes_persist_documents(self) -> None:
        formal_spec = {
            "id": "spec-api",
            "tenant": {"tenantId": "tenant-a", "accountId": "account-a"},
            "businessLine": "core",
            "specKind": "FUNCTION",
            "version": "1.0.0",
            "sourceHash": "d" * 64,
            "semanticProfile": "python-3.12",
            "status": "FROZEN",
            "body": {"declaredVariables": ["x"], "freeVariables": ["x"]},
            "provenance": {
                "sourceType": "api-test",
                "sourceRevision": "r1",
                "capturedAt": "2026-08-28T00:00:00Z",
            },
        }
        status, result = self.call(
            "/v1/formal/specs",
            "POST",
            formal_spec,
            self.identity,
            headers=self.resource_headers("spec-api-request"),
        )
        self.assertEqual(status, "201 Created")
        self.assertTrue(result["output"]["registration"]["immutable"])

        plan = {
            "id": "plan-api",
            "tenant": {"tenantId": "tenant-a", "accountId": "account-a"},
            "businessLine": "core",
            "obligationIds": ["obl-a", "obl-b"],
            "dag": [{"from": "obl-a", "to": "obl-b"}],
            "budget": {
                "wallClockSeconds": 30,
                "cpuSeconds": 10,
                "memoryMb": 256,
                "creditMicros": 0,
            },
            "createdAt": "2026-08-28T00:00:00Z",
        }
        status, result = self.call(
            "/v1/proof-plans",
            "POST",
            plan,
            self.identity,
            headers=self.resource_headers("plan-api-request"),
        )
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(result["output"]["order"], ["obl-a", "obl-b"])

    def test_proof_run_contract_route_is_scope_bound_and_fail_closed_gate(self) -> None:
        run = {
            "id": "run-api",
            "tenant": {
                "tenantId": "tenant-a",
                "accountId": "account-a",
                "projectId": "project-a",
            },
            "obligationId": "obl-api",
            "engine": "elmos-local-bounded",
            "engineVersion": "1.0.0",
            "mode": "BOUNDED",
            "bound": {"scope": 1},
            "state": "QUEUED",
            "fencingToken": 1,
            "startedAt": "2026-08-28T00:00:00Z",
        }
        headers = self.resource_headers("run-api-request")
        status, result = self.call(
            "/v1/proof-runs", "POST", run, self.identity, headers=headers
        )
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(result["id"], "run-api")
        self.assertEqual(result["state"], "QUEUED")

        status, result = self.call(
            "/v1/proof-runs/run-api", "GET", identity=self.identity, headers=headers
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(result["tenant"]["accountId"], "account-a")

        status, gate = self.call(
            "/v1/gates/evaluate",
            "POST",
            {
                "subjectId": "release-api",
                "gate": "E2_MODEL",
                "policyRevision": "policy-v1",
            },
            self.identity,
            headers=self.resource_headers("gate-api-request"),
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(gate["output"]["gateDecision"]["decision"], "DENY")
        self.assertEqual(gate["output"]["certification"], "NOT_CERTIFIED")

    def test_native_execution_receipt_route_is_full_scope_bound(self) -> None:
        current_scope = Scope(
            "tenant-a",
            "account-a",
            "project-a",
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "api-contract",
        )
        receipt = {
            "format": "elmos-formal-native-execution-receipt/v1",
            "executionId": "exec-api",
            "bindingDigest": "d" * 64,
            "externalEvidenceStatus": "NOT_RUN",
            "certificationStatus": "NOT_CERTIFIED",
        }
        self.store.put_execution_receipt(
            current_scope, "exec-api", "d" * 64, receipt
        )
        status, result = self.call(
            "/v1/executions/exec-api",
            "GET",
            identity=self.identity,
            headers=self.resource_headers(),
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(result, receipt)
        wrong_project = self.resource_headers()
        wrong_project["HTTP_X_ELMOS_PROJECT_ID"] = "project-b"
        status, result = self.call(
            "/v1/executions/exec-api",
            "GET",
            identity=TrustedIdentity("tenant-a", "operator-a", "project-b"),
            headers=wrong_project,
        )
        self.assertEqual(status, "400 Bad Request")

    def test_control_action_requires_role_and_is_idempotent(self) -> None:
        headers = self.resource_headers("control-request")
        scope = {
            "tenantId": "tenant-a",
            "accountId": "account-a",
            "projectId": "project-a",
            "sourceArtifactDigest": "a" * 64,
            "targetArtifactDigest": "b" * 64,
            "environmentDigest": "c" * 64,
            "workloadKey": "api-contract",
        }
        self.api.runtime.submit_run(
            {"scope": scope, "runId": "run-control", "obligationId": "obl-control"},
            self.identity,
        )
        trusted_scope = self.api.runtime._scope(scope, self.identity)
        leased = self.store.lease_run(
            trusted_scope, "run-control", "worker-a", 1
        )
        self.store.start_run(
            trusted_scope,
            "run-control",
            "worker-a",
            leased["fencing_token"],
        )
        status, denied = self.call(
            "/v1/proof-runs/run-control/actions",
            "POST",
            {"action": "PAUSE", "idempotencyKey": "pause-control"},
            self.identity,
            headers=headers,
        )
        self.assertEqual(status, "403 Forbidden")
        self.assertIn("control role", denied["error"])

        controller = TrustedIdentity(
            "tenant-a",
            "controller-a",
            "project-a",
            roles=("formal-assurance-control",),
        )
        status, paused = self.call(
            "/v1/proof-runs/run-control/actions",
            "POST",
            {"action": "PAUSE", "idempotencyKey": "pause-control"},
            controller,
            headers=headers,
        )
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(paused["state"], "PAUSED")
        status, replay = self.call(
            "/v1/proof-runs/run-control/actions",
            "POST",
            {"action": "PAUSE", "idempotencyKey": "pause-control"},
            controller,
            headers=headers,
        )
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(paused, replay)


if __name__ == "__main__":
    unittest.main()
