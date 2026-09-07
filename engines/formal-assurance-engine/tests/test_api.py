from __future__ import annotations

import json
import unittest

from elmos_formal_assurance.api import FormalAssuranceApi, make_environ
from elmos_formal_assurance.contracts import ProofRunState, Scope, TrustedIdentity
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
        query: str = "",
    ) -> tuple[str, dict[str, object] | list[object]]:
        environ = make_environ(path, method, payload, identity)
        environ["elmos.trusted_transport"] = trusted
        environ["QUERY_STRING"] = query
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

    def test_api_closes_only_the_runtime_it_owns(self) -> None:
        owned = FormalAssuranceApi()
        owned_store = owned.runtime.store
        owned.close()
        owned.close()
        self.assertTrue(owned_store.closed)

        injected_runtime = FormalAssuranceRuntime(store=self.store)
        injected = FormalAssuranceApi(injected_runtime)
        injected.close()
        self.assertFalse(self.store.closed)

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
        }
        headers = self.resource_headers("run-api-request")
        status, result = self.call(
            "/v1/proof-runs", "POST", run, self.identity, headers=headers
        )
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(result["id"], "run-api")
        self.assertEqual(result["state"], "QUEUED")
        self.assertIn("startedAt", result)

        status, result = self.call(
            "/v1/proof-runs/run-api", "GET", identity=self.identity, headers=headers
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(result["tenant"]["accountId"], "account-a")

        invalid = {
            **run,
            "id": "run-api-forged-time",
            "startedAt": "2026-08-28T00:00:00Z",
        }
        status, rejected = self.call(
            "/v1/proof-runs",
            "POST",
            invalid,
            self.identity,
            headers=self.resource_headers("run-api-forged-time"),
        )
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("unknown fields", rejected["error"])

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
        gate_document = gate["output"]["gateDocument"]
        self.assertEqual(
            set(gate_document),
            {
                "id",
                "tenant",
                "subjectId",
                "gate",
                "decision",
                "policyRevision",
                "evaluatedAt",
                "blockingReasons",
                "evidenceHash",
                "gateEvidence",
            },
        )
        self.assertEqual(
            gate_document["gateEvidence"]["verificationStatus"], "NOT_RUN"
        )
        self.assertEqual(len(gate_document["evidenceHash"]), 64)
        status, latest = self.call(
            "/v1/gates/release-api/latest",
            "GET",
            identity=self.identity,
            headers=self.resource_headers(),
            query="gate=E2_MODEL",
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(latest, gate_document)

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
        self.store.put_execution_receipt(current_scope, "exec-api", "d" * 64, receipt)
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
        leased = self.store.lease_run(trusted_scope, "run-control", "worker-a", 1)
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

        status, impersonation = self.call(
            "/v1/proof-runs/run-control/actions",
            "POST",
            {
                "action": "PAUSE",
                "workerId": "worker-a",
                "token": leased["fencing_token"],
            },
            self.identity,
            headers=headers,
        )
        self.assertEqual(status, "403 Forbidden")
        self.assertIn("authenticated actor", impersonation["error"])

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

    def test_checkpoint_and_retry_routes_preserve_fencing_and_terminal_history(self) -> None:
        headers = self.resource_headers("checkpoint-api-request")
        scope_payload = {
            "tenantId": "tenant-a",
            "accountId": "account-a",
            "projectId": "project-a",
            "sourceArtifactDigest": "a" * 64,
            "targetArtifactDigest": "b" * 64,
            "environmentDigest": "c" * 64,
            "workloadKey": "api-contract",
        }
        worker = TrustedIdentity("tenant-a", "worker-a", "project-a")
        self.api.runtime.submit_run(
            {
                "scope": scope_payload,
                "runId": "run-checkpoint",
                "obligationId": "obl-checkpoint",
            },
            worker,
        )
        trusted_scope = self.api.runtime._scope(scope_payload, worker)
        leased = self.store.lease_run(
            trusted_scope, "run-checkpoint", "worker-a", 1
        )
        self.store.start_run(
            trusted_scope,
            "run-checkpoint",
            "worker-a",
            leased["fencing_token"],
        )
        status, checkpointed = self.call(
            "/v1/proof-runs/run-checkpoint/checkpoints",
            "POST",
            {
                "workerId": "worker-a",
                "token": leased["fencing_token"],
                "checkpoint": {"cursor": 7},
                "progress": {
                    "completed": 1,
                    "total": 2,
                    "phase": "solver",
                    "etaWallClockSeconds": 3,
                },
            },
            worker,
            headers=headers,
        )
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(checkpointed["checkpoint"]["sequence"], 1)
        self.assertEqual(
            checkpointed["checkpoint"]["progress"]["etaUnit"],
            "wall-clock-seconds",
        )
        status, replay = self.call(
            "/v1/proof-runs/run-checkpoint/checkpoints",
            "POST",
            {
                "workerId": "worker-a",
                "token": leased["fencing_token"],
                "checkpoint": {"cursor": 7},
                "progress": {
                    "completed": 1,
                    "total": 2,
                    "phase": "solver",
                    "etaWallClockSeconds": 3,
                },
            },
            worker,
            headers=headers,
        )
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(checkpointed, replay)

        self.store.authorized_transition(
            trusted_scope,
            "run-checkpoint",
            "worker-a",
            leased["fencing_token"],
            ProofRunState.TIMED_OUT,
        )
        controller = TrustedIdentity(
            "tenant-a",
            "controller-a",
            "project-a",
            roles=("formal-assurance-control",),
        )
        retry_headers = self.resource_headers("retry-api-request")
        status, retried = self.call(
            "/v1/proof-runs/run-checkpoint/retries",
            "POST",
            {"retryRunId": "run-checkpoint-retry", "maximumAttempts": 2},
            controller,
            headers=retry_headers,
        )
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(retried["state"], "QUEUED")
        self.assertEqual(retried["options"]["retryOf"], "run-checkpoint")
        self.assertEqual(retried["retryRootRunId"], "run-checkpoint")
        self.assertEqual(retried["retryAttempt"], 1)
        self.assertEqual(retried["retryMaximumAttempts"], 2)
        self.assertEqual(
            self.store.get_run(trusted_scope, "run-checkpoint")["state"],
            "TIMED_OUT",
        )
        status, replayed_retry = self.call(
            "/v1/proof-runs/run-checkpoint/retries",
            "POST",
            {"retryRunId": "run-checkpoint-retry", "maximumAttempts": 2},
            controller,
            headers=retry_headers,
        )
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(retried, replayed_retry)

        status, duplicate_parent = self.call(
            "/v1/proof-runs/run-checkpoint/retries",
            "POST",
            {"retryRunId": "run-checkpoint-retry-branch"},
            controller,
            headers=self.resource_headers("retry-api-branch"),
        )
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("immutable retry child", duplicate_parent["error"])

        retry_lease = self.store.lease_run(
            trusted_scope, "run-checkpoint-retry", "worker-a", 1
        )
        self.store.start_run(
            trusted_scope,
            "run-checkpoint-retry",
            "worker-a",
            retry_lease["fencing_token"],
        )
        self.store.authorized_transition(
            trusted_scope,
            "run-checkpoint-retry",
            "worker-a",
            retry_lease["fencing_token"],
            ProofRunState.TIMED_OUT,
        )
        status, changed_limit = self.call(
            "/v1/proof-runs/run-checkpoint-retry/retries",
            "POST",
            {"retryRunId": "run-checkpoint-retry-two", "maximumAttempts": 3},
            controller,
            headers=self.resource_headers("retry-api-changed-limit"),
        )
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("immutable", changed_limit["error"])

        status, retry_two = self.call(
            "/v1/proof-runs/run-checkpoint-retry/retries",
            "POST",
            {"retryRunId": "run-checkpoint-retry-two"},
            controller,
            headers=self.resource_headers("retry-api-two"),
        )
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(retry_two["retryAttempt"], 2)
        self.assertEqual(retry_two["retryRootRunId"], "run-checkpoint")
        retry_two_lease = self.store.lease_run(
            trusted_scope, "run-checkpoint-retry-two", "worker-a", 1
        )
        self.store.start_run(
            trusted_scope,
            "run-checkpoint-retry-two",
            "worker-a",
            retry_two_lease["fencing_token"],
        )
        self.store.authorized_transition(
            trusted_scope,
            "run-checkpoint-retry-two",
            "worker-a",
            retry_two_lease["fencing_token"],
            ProofRunState.TIMED_OUT,
        )
        status, exceeded = self.call(
            "/v1/proof-runs/run-checkpoint-retry-two/retries",
            "POST",
            {"retryRunId": "run-checkpoint-retry-three"},
            controller,
            headers=self.resource_headers("retry-api-three"),
        )
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("retry limit exceeded", exceeded["error"])


if __name__ == "__main__":
    unittest.main()
