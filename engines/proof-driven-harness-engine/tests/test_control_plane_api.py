from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest

from elmos_proof_harness.control_plane import DurableControlPlane
from elmos_proof_harness.service import AuthPrincipal, HarnessService
from elmos_proof_harness.skills import SkillRuntime
from elmos_proof_harness.store import SQLiteStore


TOKEN = "control-plane-token-0123456789"
OTHER_TOKEN = "other-tenant-token-0123456789"
LIMITED_TOKEN = "limited-scope-token-0123456789"
EXPIRED_TOKEN = "expired-principal-0123456789"
SOURCE = "sha256:" + "1" * 64
REQUIREMENTS = "sha256:" + "2" * 64
POLICY = "sha256:" + "3" * 64
TOOLCHAIN = "sha256:" + "4" * 64
ENVIRONMENT = "sha256:" + "5" * 64
DOMAIN = "sha256:" + "6" * 64
AUTH_CONTEXT = "sha256:" + "7" * 64
AUTHORITY_REVISION = "sha256:" + "8" * 64
BASELINE = "sha256:" + "9" * 64
WORKFLOW = "sha256:" + "a" * 64
MODEL_ROUTE = "sha256:" + "b" * 64
ALL_SCOPES = (
    "proof-harness.invoke",
    "proof-harness.read",
    "proof-harness.cancel",
    "proof-harness.observe",
    "proof-harness.evidence.read",
    "proof-harness.review.read",
)


def _json(response):
    return json.loads(response.body)


class DurableControlPlaneApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.expiry = datetime.now(UTC) + timedelta(hours=2)
        self.principal = self._principal(
            "tenant-1", "project-1", "actor-1", ALL_SCOPES
        )
        self.other_principal = self._principal(
            "tenant-2", "project-1", "actor-1", ALL_SCOPES
        )
        self.limited_principal = self._principal(
            "tenant-1", "project-1", "actor-limited", ("proof-harness.read",)
        )
        self.expired_principal = AuthPrincipal(
            tenant_id="tenant-1",
            project_id="project-1",
            actor_id="actor-expired",
            authority=ALL_SCOPES,
            authentication_context_digest=AUTH_CONTEXT,
            authority_id="authority-1",
            authority_revision=AUTHORITY_REVISION,
            environment_id="environment-1",
            environment_revision=ENVIRONMENT,
            execution_epoch=1,
            fencing_generation=1,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        self.runtime = SkillRuntime(workspace_roots=(self.root,))
        self.store = SQLiteStore(self.root / "state.db")
        self.control_plane = DurableControlPlane(self.store, self.runtime)
        self.service = HarnessService(
            self.runtime,
            auth_tokens={
                TOKEN: self.principal,
                OTHER_TOKEN: self.other_principal,
                LIMITED_TOKEN: self.limited_principal,
                EXPIRED_TOKEN: self.expired_principal,
            },
            control_plane=self.control_plane,
            max_request_bytes=32 * 1024,
            runtime_mode="local-engineering",
        )

    def tearDown(self) -> None:
        self.control_plane.shutdown()
        self.store.close()
        self.temporary.cleanup()

    def _principal(
        self,
        tenant_id: str,
        project_id: str,
        actor_id: str,
        scopes: tuple[str, ...],
    ) -> AuthPrincipal:
        return AuthPrincipal(
            tenant_id=tenant_id,
            project_id=project_id,
            actor_id=actor_id,
            authority=scopes,
            authentication_context_digest=AUTH_CONTEXT,
            authority_id="authority-1",
            authority_revision=AUTHORITY_REVISION,
            environment_id="environment-1",
            environment_revision=ENVIRONMENT,
            execution_epoch=1,
            fencing_generation=1,
            expires_at=self.expiry,
        )

    def _request(
        self,
        *,
        principal: AuthPrincipal | None = None,
        skill: str = "elmos-goal-specification-kernel",
        input_value: dict | None = None,
        idempotency_key: str = "invoke-idempotency-0001",
        request_id: str = "request-0001",
    ) -> dict:
        bound = principal or self.principal
        return {
            "apiVersion": "elmos.ai/proof-harness/v3",
            "requestId": request_id,
            "skill": skill,
            "identity": {
                "tenantId": bound.tenant_id,
                "projectId": bound.project_id,
                "actorId": bound.actor_id,
                "authenticationContextDigest": (
                    bound.authentication_context_digest
                ),
            },
            "revisionSet": {
                "revisionSetId": "revision-set-1",
                "source": SOURCE,
                "baseline": BASELINE,
                "requirements": REQUIREMENTS,
                "policy": POLICY,
                "toolchain": TOOLCHAIN,
                "environment": bound.environment_revision,
                "domainPack": DOMAIN,
                "workflow": WORKFLOW,
                "modelRoute": MODEL_ROUTE,
            },
            "authority": {
                "authorityId": bound.authority_id,
                "revision": bound.authority_revision,
                "environmentId": bound.environment_id,
                "executionEpoch": bound.execution_epoch,
                "fencingGeneration": bound.fencing_generation,
                "expiresAt": bound.expires_at.astimezone(UTC)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z"),
            },
            "idempotencyKey": idempotency_key,
            "input": input_value
            or {
                "objective": "ship the exact release",
                "requirements": ["R1"],
                "revisions": {"repository": SOURCE},
            },
        }

    @staticmethod
    def _headers(token: str, idempotency_key: str | None = None) -> dict[str, str]:
        result = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if idempotency_key is not None:
            result["Idempotency-Key"] = idempotency_key
        return result

    def _invoke(self, request: dict, token: str = TOKEN):
        return self.service.handle_request(
            "POST",
            "/v3/invocations",
            self._headers(token, request["idempotencyKey"]),
            json.dumps(request, sort_keys=True).encode(),
        )

    def _complete(self, request: dict, token: str = TOKEN):
        admitted = self._invoke(request, token)
        self.assertEqual(admitted.status, 202, admitted.body)
        self.assertEqual(_json(admitted)["status"], "ADMITTED")
        run_id = admitted.headers["X-Run-ID"]
        self.assertTrue(self.control_plane.wait_for_run(run_id, 10))
        completed = self._invoke(request, token)
        self.assertEqual(completed.status, 200, completed.body)
        return admitted, completed

    def test_admit_replay_run_and_content_verified_evidence(self) -> None:
        request = self._request()
        first = self._invoke(request)
        self.assertEqual(first.status, 202, first.body)
        admission = _json(first)
        self.assertEqual(
            set(admission),
            {
                "apiVersion",
                "requestId",
                "skill",
                "status",
                "runId",
                "resultAvailable",
                "requestDigest",
                "acceptedAt",
            },
        )
        self.assertEqual(admission["status"], "ADMITTED")
        self.assertFalse(admission["resultAvailable"])
        run_id = first.headers["X-Run-ID"]
        self.assertTrue(self.control_plane.wait_for_run(run_id, 10))
        replay = self._invoke(request)
        self.assertEqual(replay.status, 200, replay.body)
        result = _json(replay)
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(result["subjectRevision"], SOURCE)
        self.assertTrue(result["metrics"]["cacheHit"])
        run = self.service.handle_request(
            "GET",
            f"/v3/runs/{run_id}",
            self._headers(TOKEN),
        )
        self.assertEqual(run.status, 200, run.body)
        self.assertEqual(
            set(_json(run)),
            {
                "runId",
                "state",
                "version",
                "executionEpoch",
                "fencingGeneration",
                "updatedAt",
            },
        )
        evidence = self.service.handle_request(
            "GET",
            f"/v3/evidence/{result['evidenceIds'][0]}",
            self._headers(TOKEN),
        )
        self.assertEqual(evidence.status, 200, evidence.body)
        metadata = _json(evidence)
        self.assertEqual(metadata["subjectRevision"], SOURCE)
        self.assertRegex(metadata["contentDigest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(replay.headers["Idempotent-Replay"], "true")
        self.assertTrue(_json(replay)["metrics"]["cacheHit"])
        self.assertEqual(_json(replay)["evidenceIds"], result["evidenceIds"])

    def test_identity_authority_idempotency_and_fence_mismatches_fail(self) -> None:
        missing_scope = self._invoke(
            self._request(principal=self.limited_principal),
            token=LIMITED_TOKEN,
        )
        self.assertEqual(missing_scope.status, 403)

        identity = self._request(idempotency_key="invoke-idempotency-0002")
        identity["identity"]["tenantId"] = "other"
        response = self._invoke(identity)
        self.assertEqual(response.status, 422)
        self.assertEqual(_json(response)["code"], "IDENTITY_MISMATCH")

        authority = self._request(idempotency_key="invoke-idempotency-0003")
        authority["authority"]["authorityId"] = "other-authority"
        response = self._invoke(authority)
        self.assertEqual(response.status, 422)
        self.assertEqual(_json(response)["code"], "AUTHORITY_MISMATCH")

        stale = self._request(idempotency_key="invoke-idempotency-0004")
        stale["authority"]["fencingGeneration"] = 2
        response = self._invoke(stale)
        self.assertEqual(response.status, 422)
        self.assertEqual(_json(response)["code"], "STALE_FENCE")

        mismatch = self._request(idempotency_key="invoke-idempotency-0005")
        response = self.service.handle_request(
            "POST",
            "/v3/invocations",
            self._headers(TOKEN, "different-header-key-0005"),
            json.dumps(mismatch).encode(),
        )
        self.assertEqual(response.status, 422)
        self.assertEqual(_json(response)["code"], "IDEMPOTENCY_MISMATCH")

        expired = self._request(principal=self.expired_principal)
        response = self._invoke(expired, EXPIRED_TOKEN)
        self.assertEqual(response.status, 401)

        body_grant = self._request(idempotency_key="invoke-idempotency-0006")
        body_grant["grant"] = {"scopes": ["proof-harness.cancel"]}
        response = self._invoke(body_grant)
        self.assertEqual(response.status, 422)

    def test_same_idempotency_key_with_different_request_conflicts(self) -> None:
        request = self._request(idempotency_key="same-idempotency-key-01")
        self.assertEqual(self._invoke(request).status, 202)
        changed = json.loads(json.dumps(request))
        changed["input"]["objective"] = "different objective"
        response = self._invoke(changed)
        self.assertEqual(response.status, 409)
        self.assertEqual(_json(response)["code"], "IDEMPOTENCY_CONFLICT")

    def test_cross_tenant_run_and_evidence_lookups_do_not_resolve(self) -> None:
        first, completed = self._complete(self._request())
        result = _json(completed)
        run_id = first.headers["X-Run-ID"]
        run = self.service.handle_request(
            "GET",
            f"/v3/runs/{run_id}",
            self._headers(OTHER_TOKEN),
        )
        self.assertEqual(run.status, 404)
        evidence = self.service.handle_request(
            "GET",
            f"/v3/evidence/{result['evidenceIds'][0]}",
            self._headers(OTHER_TOKEN),
        )
        self.assertEqual(evidence.status, 404)

    def test_forged_independence_never_becomes_verified_or_certified(self) -> None:
        forged_digest = "9" * 64
        request = self._request(
            skill="elmos-proof-verification-kernel",
            idempotency_key="forged-independence-0001",
            input_value={
                "obligations": [
                    {"id": "O1", "required_evidence": ["compiler"]}
                ],
                "evidence": [
                    {
                        "obligation_id": "O1",
                        "kind": "compiler",
                        "status": "PASS",
                        "digest": forged_digest,
                        "independent": True,
                    }
                ],
            },
        )
        _, response = self._complete(request)
        result = _json(response)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["externalEvidence"], "NOT_RUN")
        self.assertNotEqual(result["certification"], "CERTIFIED")
        self.assertFalse(
            result["output"]["results"][0]["independent_claim_trusted"]
        )

    def test_effectful_invocation_is_blocked_without_durable_effect_binding(self) -> None:
        target = self.root / "value.txt"
        target.write_text("before", encoding="utf-8")
        request = self._request(
            skill="elmos-transformation-kernel",
            idempotency_key="effectful-invocation-0001",
            input_value={
                "repository": str(self.root),
                "changes": [
                    {
                        "path": "value.txt",
                        "expected_digest": hashlib.sha256(b"before").hexdigest(),
                        "content": "after",
                    }
                ],
                "reason": "test",
                "request_id": "effect-request",
                "apply": True,
            },
        )
        _, response = self._complete(request)
        self.assertEqual(_json(response)["status"], "BLOCKED")
        self.assertEqual(target.read_text(encoding="utf-8"), "before")

    def test_cancel_is_durable_replayable_and_stale_version_does_not_poison(self) -> None:
        context = self.control_plane.register_scope(self.principal)
        run = self.control_plane.workflow.create(
            context,
            run_id="run-cancel-test",
            revision_set_id="revision-set-1",
            idempotency_key="core-create-cancel-0001",
        )
        self.control_plane.workflow.acquire(
            context.for_run(run.run_id),
            owner_id=self.control_plane.owner_id,
            expected_sequence=run.sequence,
        )
        stale_body = {"expectedVersion": 2, "reason": "operator request"}
        stale = self.service.handle_request(
            "POST",
            "/v3/runs/run-cancel-test/cancel",
            self._headers(TOKEN, "cancel-idempotency-0001"),
            json.dumps(stale_body).encode(),
        )
        self.assertEqual(stale.status, 409)
        body = {"expectedVersion": 1, "reason": "operator request"}
        cancelled = self.service.handle_request(
            "POST",
            "/v3/runs/run-cancel-test/cancel",
            self._headers(TOKEN, "cancel-idempotency-0001"),
            json.dumps(body).encode(),
        )
        self.assertEqual(cancelled.status, 202, cancelled.body)
        self.assertEqual(_json(cancelled)["state"], "CANCELLED")
        replay = self.service.handle_request(
            "POST",
            "/v3/runs/run-cancel-test/cancel",
            self._headers(TOKEN, "cancel-idempotency-0001"),
            json.dumps(body).encode(),
        )
        self.assertEqual(replay.status, 200, replay.body)
        self.assertEqual(replay.headers["Idempotent-Replay"], "true")

    def test_readiness_review_and_metric_catalog_are_fail_closed(self) -> None:
        readiness = self.service.handle_request("GET", "/readyz", {})
        self.assertEqual(readiness.status, 200)
        self.assertEqual(
            _json(readiness),
            {
                "status": "ready",
                "checks": {
                    "authentication": "ready",
                    "runtimeRegistry": "ready",
                    "durableStore": "ready",
                    "runtimeAssurance": "ready",
                    "transportSecurity": "ready",
                    "requiredConfig": "ready",
                },
            },
        )
        registry = self.service.handle_request(
            "GET", "/v3/skills", self._headers(TOKEN)
        )
        self.assertEqual(registry.status, 200)
        adapters = _json(registry)["adapters"]
        self.assertEqual(len(adapters), 27)
        self.assertTrue(
            all(
                item["implementationState"] == "ADAPTER_REQUIRED"
                and item["runtimeStatus"] == "NOT_RUN"
                for item in adapters
            )
        )
        review = self.service.handle_request(
            "GET",
            "/v3/completion-reviews/review-1",
            self._headers(TOKEN),
        )
        self.assertEqual(review.status, 501)
        self.assertEqual(_json(review)["code"], "NOT_CONFIGURED")
        self._invoke(self._request(idempotency_key="metrics-invocation-0001"))
        metrics = self.service.handle_request(
            "GET", "/metrics", self._headers(TOKEN)
        )
        self.assertEqual(metrics.status, 200)
        text = metrics.body.decode()
        self.assertIn("elmos_proof_harness_invocations_total", text)
        self.assertIn("elmos_proof_harness_invocation_duration_seconds", text)
        self.assertNotIn("elmos_http_requests_total", text)
        for forbidden in (
            "tenant_id",
            "project_id",
            "actor_id",
            "repository_url",
            "source_path",
            "evidence_id",
        ):
            self.assertNotIn(forbidden + "=", text)

    def test_restart_reclaims_checkpointed_admission_and_pending_replay_is_stable(
        self,
    ) -> None:
        database = self.root / "restart.db"
        store = SQLiteStore(database)
        first_plane = DurableControlPlane(
            store,
            self.runtime,
            lease_ttl_seconds=1,
            auto_start_workers=False,
        )
        first_service = HarnessService(
            self.runtime,
            auth_tokens={TOKEN: self.principal},
            control_plane=first_plane,
            runtime_mode="local-engineering",
        )
        request = self._request(idempotency_key="restart-recovery-0001")
        try:
            first = first_service.handle_request(
                "POST",
                "/v3/invocations",
                self._headers(TOKEN, request["idempotencyKey"]),
                json.dumps(request).encode(),
            )
            pending = first_service.handle_request(
                "POST",
                "/v3/invocations",
                self._headers(TOKEN, request["idempotencyKey"]),
                json.dumps(request).encode(),
            )
            self.assertEqual(first.status, 202)
            self.assertEqual(pending.status, 202)
            self.assertEqual(first.body, pending.body)
            run_id = first.headers["X-Run-ID"]
        finally:
            first_plane.shutdown()
            store.close()
        time.sleep(1.1)
        restarted_store = SQLiteStore(database)
        restarted = DurableControlPlane(
            restarted_store,
            self.runtime,
            lease_ttl_seconds=1,
        )
        restarted_service = HarnessService(
            self.runtime,
            auth_tokens={TOKEN: self.principal},
            control_plane=restarted,
            runtime_mode="local-engineering",
        )
        try:
            self.assertEqual(restarted.reconcile_scope(self.principal), 1)
            self.assertTrue(restarted.wait_for_run(run_id, 10))
            replay = restarted_service.handle_request(
                "POST",
                "/v3/invocations",
                self._headers(TOKEN, request["idempotencyKey"]),
                json.dumps(request).encode(),
            )
            self.assertEqual(replay.status, 200, replay.body)
            self.assertEqual(_json(replay)["status"], "SUCCEEDED")
            self.assertGreater(_json(replay)["metrics"]["costMicrounits"], 0)
        finally:
            restarted.shutdown()
            restarted_store.close()

    def test_wall_output_and_cost_limits_fail_closed_with_durable_results(self) -> None:
        wall = self._request(idempotency_key="wall-limit-00001")
        wall["limits"] = {"wallClockSeconds": 0.001, "maxOutputBytes": 4096}
        _, wall_result = self._complete(wall)
        self.assertEqual(_json(wall_result)["status"], "FAILED")
        wall_run = self.service.handle_request(
            "GET",
            f"/v3/runs/{wall_result.headers['X-Run-ID']}",
            self._headers(TOKEN),
        )
        self.assertEqual(_json(wall_run)["state"], "TIMED_OUT")

        output = self._request(idempotency_key="output-limit-00001")
        output["limits"] = {"maxOutputBytes": 1}
        _, output_result = self._complete(output)
        self.assertEqual(_json(output_result)["status"], "FAILED")
        self.assertEqual(_json(output_result)["output"], {})

        unavailable = self._request(idempotency_key="cost-unavailable-0001")
        unavailable["limits"] = {"maxCostMicrounits": 1000000}
        _, unavailable_result = self._complete(unavailable)
        self.assertEqual(_json(unavailable_result)["status"], "FAILED")
        self.assertIn("BUDGET_UNAVAILABLE", _json(unavailable_result)["errors"][0]["message"])

        exceeded = self._request(idempotency_key="cost-exceeded-0001")
        exceeded["limits"] = {
            "wallClockSeconds": 1,
            "maxOutputBytes": 1024,
            "maxCostMicrounits": 0,
        }
        _, exceeded_result = self._complete(exceeded)
        self.assertEqual(_json(exceeded_result)["status"], "FAILED")
        self.assertIn("BUDGET_EXCEEDED", _json(exceeded_result)["errors"][0]["message"])

    def test_strict_json_and_removed_invoke_alias_fail_closed(self) -> None:
        request = self._request(idempotency_key="strict-json-0001")
        raw = json.dumps(request)[:-1] + ',"skill":"elmos-goal-specification-kernel"}'
        duplicate = self.service.handle_request(
            "POST",
            "/v3/invocations",
            self._headers(TOKEN, request["idempotencyKey"]),
            raw.encode(),
        )
        self.assertEqual(duplicate.status, 400)
        decomposed = self._request(idempotency_key="strict-json-0002")
        decomposed["input"] = {"e\u0301": 1, "é": 2}
        collision = self.service.handle_request(
            "POST",
            "/v3/invocations",
            self._headers(TOKEN, decomposed["idempotencyKey"]),
            json.dumps(decomposed, ensure_ascii=False).encode(),
        )
        self.assertEqual(collision.status, 400)
        nonfinite = self._request(idempotency_key="strict-json-0003")
        nonfinite["input"] = {"value": float("nan")}
        response = self.service.handle_request(
            "POST",
            "/v3/invocations",
            self._headers(TOKEN, nonfinite["idempotencyKey"]),
            json.dumps(nonfinite).encode(),
        )
        self.assertEqual(response.status, 400)
        alias = self.service.handle_request(
            "POST",
            "/v3/invoke",
            self._headers(TOKEN, request["idempotencyKey"]),
            json.dumps(request).encode(),
        )
        self.assertEqual(alias.status, 404)


if __name__ == "__main__":
    unittest.main()
