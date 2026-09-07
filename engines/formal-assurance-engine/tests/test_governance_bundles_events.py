from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from elmos_formal_assurance.api import FormalAssuranceApi, make_environ
from elmos_formal_assurance.artifact_store import AesGcmEnvelopeCipher
from elmos_formal_assurance.bundles import (
    EvidenceBundleService,
    HmacEvidenceBundleSigner,
)
from elmos_formal_assurance.contracts import (
    AssuranceLevel,
    ProofResult,
    ProofStatus,
    Scope,
    TrustedIdentity,
)
from elmos_formal_assurance.events import (
    DigestReceiptPublisher,
    OutboxDispatcher,
)
from elmos_formal_assurance.governance import (
    GovernanceAuthorizationError,
    GovernanceError,
)
from elmos_formal_assurance.runtime import (
    FormalAssuranceRuntime,
    RuntimeAuthorizationError,
    RuntimeConfig,
)
from elmos_formal_assurance.store import StateStore, StoreError


def current_scope(tenant: str = "tenant-a") -> Scope:
    return Scope(
        tenant,
        "account-a",
        "project-a",
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "governance-test",
    )


def iso(offset: timedelta = timedelta()) -> str:
    return (
        (datetime.now(timezone.utc) + offset)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def assumption_document(identifier: str = "assumption-a") -> dict[str, object]:
    return {
        "id": identifier,
        "tenant": {
            "tenantId": "tenant-a",
            "accountId": "account-a",
            "projectId": "project-a",
            "dataClassification": "confidential",
        },
        "statement": "The pinned database enforces all declared constraints",
        "formalExpression": "DB |= DeclaredConstraints",
        "riskLevel": "HIGH",
        "owner": "actor-a",
        "status": "ACTIVE",
        "hash": "d" * 64,
        "createdAt": iso(timedelta(minutes=-1)),
        "expiresAt": iso(timedelta(days=30)),
        "monitorId": "schema-drift-monitor",
        "evidence": [],
    }


class GovernanceLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = StateStore()
        self.runtime = FormalAssuranceRuntime(store=self.store)
        self.scope = current_scope()
        self.actor = TrustedIdentity("tenant-a", "actor-a", "project-a")

    def tearDown(self) -> None:
        self.store.close()

    def test_assumption_and_tcb_mutations_are_scope_role_and_digest_bound(self) -> None:
        request = {
            "scope": self.scope.to_dict(),
            "idempotencyKey": "assumption-register-a",
            **assumption_document(),
        }
        created = self.runtime.register_assumption(request, self.actor)
        replay = self.runtime.register_assumption(request, self.actor)
        self.assertEqual(created, replay)
        self.assertEqual(created["status"], "ACTIVE")
        self.assertEqual(created["hash"], "sha256:" + "d" * 64)

        invalid = assumption_document("assumption-no-expiry")
        invalid.pop("expiresAt")
        with self.assertRaises(GovernanceError):
            self.runtime.register_assumption(
                {
                    "scope": self.scope.to_dict(),
                    "idempotencyKey": "assumption-no-expiry",
                    **invalid,
                },
                self.actor,
            )

        component = {
            "id": "tcb-z3",
            "name": "Z3 adapter",
            "componentType": "SOLVER",
            "version": "4.15.3",
            "digest": "e" * 64,
            "trustReason": "Exact executable and adapter image are digest pinned",
            "status": "PINNED",
            "affectedProofCount": 1,
        }
        tcb_request = {
            "scope": self.scope.to_dict(),
            "idempotencyKey": "tcb-register-a",
            **component,
        }
        with self.assertRaises(GovernanceAuthorizationError):
            self.runtime.register_trusted_component(tcb_request, self.actor)
        tcb_admin = TrustedIdentity(
            "tenant-a",
            "tcb-admin",
            "project-a",
            roles=("formal-assurance-tcb-admin",),
            authorization_ref="authz:tcb-change-1",
        )
        registered = self.runtime.register_trusted_component(tcb_request, tcb_admin)
        self.assertEqual(registered["digest"], "sha256:" + "e" * 64)
        audit = self.store.security_audit(tcb_admin)
        self.assertTrue(any(item["decision"] == "DENY" for item in audit))
        self.assertTrue(any(item["decision"] == "ALLOW" for item in audit))

    def test_waiver_requires_independent_authenticated_four_eyes(self) -> None:
        waiver = {
            "id": "waiver-a",
            "tenant": {
                "tenantId": "tenant-a",
                "accountId": "account-a",
                "projectId": "project-a",
                "dataClassification": "confidential",
            },
            "obligationId": "obligation-a",
            "reason": "A proprietary dependency needs a bounded migration exception",
            "risk": "HIGH",
            "owner": "actor-a",
            "compensatingControls": [
                "shadow traffic comparison",
                "runtime invariant monitor",
            ],
            "approvals": [
                {
                    "approver": "security-a",
                    "role": "security",
                    "approvedAt": iso(timedelta(minutes=-1)),
                },
                {
                    "approver": "business-a",
                    "role": "business",
                    "approvedAt": iso(timedelta(minutes=-1)),
                },
            ],
            "createdAt": iso(timedelta(minutes=-1)),
            "expiresAt": iso(timedelta(days=7)),
            "status": "PROPOSED",
        }
        proposed = self.runtime.propose_waiver(
            {
                "scope": self.scope.to_dict(),
                "idempotencyKey": "waiver-propose-a",
                **waiver,
            },
            self.actor,
        )
        self.assertEqual(proposed["state"], "PROPOSED")
        self.assertEqual(proposed["trustedApprovalCount"], 0)

        security = TrustedIdentity(
            "tenant-a",
            "security-a",
            "project-a",
            roles=("formal-assurance-waiver-security",),
            authorization_ref="authz:security-approval-a",
        )
        first = self.runtime.approve_waiver(
            {
                "scope": self.scope.to_dict(),
                "idempotencyKey": "waiver-approve-security-a",
                "waiverId": "waiver-a",
                "approvalRole": "formal-assurance-waiver-security",
            },
            security,
        )
        self.assertEqual(first["state"], "PROPOSED")

        business = TrustedIdentity(
            "tenant-a",
            "business-a",
            "project-a",
            roles=("formal-assurance-waiver-business",),
            authorization_ref="authz:business-approval-a",
        )
        second = self.runtime.approve_waiver(
            {
                "scope": self.scope.to_dict(),
                "idempotencyKey": "waiver-approve-business-a",
                "waiverId": "waiver-a",
                "approvalRole": "formal-assurance-waiver-business",
            },
            business,
        )
        self.assertEqual(second["state"], "APPROVED")
        self.assertTrue(second["fourEyes"])
        lifecycle = self.store.get_document(self.scope, "proof_waiver", "waiver-a")[
            "document"
        ]
        self.assertEqual(lifecycle["state"], "APPROVED")
        self.assertEqual(len(lifecycle["trustedApprovals"]), 2)

        direct = {**waiver, "id": "waiver-direct", "status": "APPROVED"}
        with self.assertRaises(GovernanceAuthorizationError):
            self.runtime.propose_waiver(
                {
                    "scope": self.scope.to_dict(),
                    "idempotencyKey": "waiver-direct",
                    **direct,
                },
                self.actor,
            )

    def test_drift_invalidates_cache_results_and_enqueues_minimal_reproof(self) -> None:
        self.store.submit_run(self.scope, "run-drift", "obligation-drift")
        leased = self.store.lease_run(self.scope, "run-drift", "worker-a", 1)
        self.store.start_run(
            self.scope, "run-drift", "worker-a", leased["fencing_token"]
        )
        self.store.commit_run(
            self.scope,
            "run-drift",
            "worker-a",
            leased["fencing_token"],
            ProofResult(
                "run-drift",
                "obligation-drift",
                ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
                AssuranceLevel.A1_BOUNDED,
                "local",
                "BOUNDED",
                "d" * 64,
                "e" * 64,
                bound={"steps": 1},
            ),
        )
        self.store.register_dependency(
            self.scope,
            subject_type="proof_run",
            subject_id="run-drift",
            dependency_kind="TCB",
            dependency_id="tcb-z3",
            dependency_hash="d" * 64,
        )
        self.store.put_cache(
            self.scope,
            "cache-drift",
            {
                "dependencies": ["tcb-z3"],
                "dependencyBindings": {"tcb-z3": "sha256:" + "d" * 64},
                "value": "prior-evidence",
            },
        )
        drift_actor = TrustedIdentity(
            "tenant-a",
            "drift-monitor",
            "project-a",
            roles=("formal-assurance-drift",),
            authorization_ref="authz:drift-event-a",
        )
        result = self.runtime.report_drift(
            {
                "scope": self.scope.to_dict(),
                "idempotencyKey": "drift-tcb-z3-a",
                "dependencyKind": "TCB",
                "dependencyId": "tcb-z3",
                "newHash": "f" * 64,
            },
            drift_actor,
        )
        self.assertEqual(result["cacheEntriesInvalidated"], 1)
        self.assertEqual(result["proofResultsMarkedStale"], 1)
        self.assertIsNone(self.store.get_cache(self.scope, "cache-drift"))
        persisted = json.loads(
            self.store.get_run(self.scope, "run-drift")["result_json"]
        )
        self.assertTrue(persisted["stale"])
        self.assertEqual(
            self.store.pending_reproofs(self.scope)[0]["subjectId"], "run-drift"
        )
        drift_events = self.store.events(self.scope, "proof_drift", "tcb-z3")
        self.assertEqual(drift_events[-1]["eventType"], "dependency_changed")
        self.assertEqual(
            [
                item["topic"]
                for item in self.store.pending_outbox(self.scope, limit=1000)
                if item["event"]["aggregateType"] == "proof_drift"
            ],
            ["driftEvents"],
        )


class EvidenceBundleAndEventTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = StateStore()
        self.scope = current_scope()
        self.identity = TrustedIdentity("tenant-a", "actor-a", "project-a")
        self.runtime = FormalAssuranceRuntime(
            store=self.store,
            config=RuntimeConfig(
                artifact_root=self.root / "artifacts",
                artifact_envelope_cipher=AesGcmEnvelopeCipher(
                    b"g" * 32, key_id="bundle-test-key"
                ),
                bundle_signer=HmacEvidenceBundleSigner(b"b" * 32),
            ),
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def test_bundle_is_redacted_content_addressed_signed_and_offline_verified(
        self,
    ) -> None:
        self.store.put_document(
            self.scope,
            "counterexample",
            "counterexample-bundle",
            {
                "runId": "run-bundle",
                "witness": {"token": "secret-token", "value": 7},
                "proofStatus": "REFUTED_WITH_COUNTEREXAMPLE",
            },
        )
        built = self.runtime.build_evidence_bundle(
            {
                "scope": self.scope.to_dict(),
                "idempotencyKey": "bundle-build-a",
                "subjectId": "run-bundle",
                "redactionPolicy": "STRICT",
                "sign": True,
            },
            self.identity,
        )
        verified = self.runtime.verify_evidence_bundle(
            {
                "scope": self.scope.to_dict(),
                "idempotencyKey": "bundle-verify-a",
                "bundleId": built["bundleId"],
            },
            self.identity,
        )
        self.assertEqual(verified["integrityStatus"], "VERIFIED")
        self.assertEqual(verified["signatureStatus"], "LOCAL_SELF_ATTESTED_VERIFIED")
        descriptor = self.store.get_document(
            self.scope, "evidence_bundle", built["bundleId"]
        )["document"]
        manifest_bytes = self.runtime.artifact_store.get(
            "tenant-a", descriptor["manifestRef"]["sha256"]
        )
        manifest = json.loads(manifest_bytes)
        evidence_bytes = self.runtime.artifact_store.get(
            "tenant-a", manifest["files"][0]["sha256"]
        )
        self.assertNotIn(b"secret-token", evidence_bytes)
        with self.assertRaises(StoreError):
            EvidenceBundleService(
                self.store,
                self.runtime.artifact_store,
                HmacEvidenceBundleSigner(b"b" * 32),
            ).verify(current_scope("tenant-b"), bundle_id=built["bundleId"])

    def test_requested_signature_fails_closed_and_path_components_are_encoded(
        self,
    ) -> None:
        unsigned_runtime = FormalAssuranceRuntime(
            store=self.store,
            config=RuntimeConfig(
                artifact_root=self.root / "unsigned-artifacts",
                artifact_envelope_cipher=AesGcmEnvelopeCipher(
                    b"h" * 32, key_id="unsigned-bundle-test-key"
                ),
            ),
        )
        self.store.put_document(
            self.scope,
            "proof_artifact",
            "artifact/nested",
            {"runId": "run-unsigned", "status": "LOCAL_ENGINEERING"},
        )
        built = unsigned_runtime.build_evidence_bundle(
            {
                "scope": self.scope.to_dict(),
                "idempotencyKey": "unsigned-build",
                "subjectId": "run-unsigned",
                "redactionPolicy": "STRICT",
                "sign": True,
            },
            self.identity,
        )
        verified = unsigned_runtime.verify_evidence_bundle(
            {
                "scope": self.scope.to_dict(),
                "idempotencyKey": "unsigned-verify",
                "bundleId": built["bundleId"],
            },
            self.identity,
        )
        self.assertEqual(verified["integrityStatus"], "FAILED")
        self.assertEqual(verified["signatureStatus"], "NOT_RUN")
        self.assertIn("requested bundle signature is missing", verified["errors"])
        descriptor = self.store.get_document(
            self.scope, "evidence_bundle", built["bundleId"]
        )["document"]
        manifest = json.loads(
            unsigned_runtime.artifact_store.get(
                "tenant-a", descriptor["manifestRef"]["sha256"]
            )
        )
        self.assertIn("artifact%2Fnested", manifest["files"][0]["path"])

    def test_transactional_outbox_dispatches_and_dead_letters_failures(self) -> None:
        self.store.append_event(
            self.scope,
            "proof_run",
            "run-outbox",
            "submitted",
            {"obligationId": "obligation-outbox"},
        )
        pending = self.store.pending_outbox(self.scope, limit=100)
        self.assertEqual(
            set(pending[-1]["event"]["message"]),
            {
                "eventId",
                "eventType",
                "tenantId",
                "aggregateId",
                "occurredAt",
                "payload",
            },
        )
        publisher = DigestReceiptPublisher()
        result = OutboxDispatcher(self.store, publisher).dispatch(self.scope, limit=100)
        self.assertEqual(result.failed, 0)
        self.assertGreaterEqual(result.published, 1)
        self.assertEqual(self.store.pending_outbox(self.scope), [])
        self.assertEqual(publisher.events[-1]["topic"], "proofEvents")

        self.store.put_document(
            self.scope,
            "gate_decision",
            "gate-outbox",
            {
                "id": "gate-outbox",
                "tenant": {
                    "tenantId": "tenant-a",
                    "accountId": "account-a",
                    "projectId": "project-a",
                    "dataClassification": "confidential",
                },
                "subjectId": "release-outbox",
                "gate": "E2_MODEL",
                "decision": "DENY",
                "policyRevision": "policy-v1",
                "evaluatedAt": iso(),
                "blockingReasons": ["external evidence is not available"],
                "evidenceHash": "d" * 64,
            },
        )
        gate_result = OutboxDispatcher(self.store, publisher).dispatch(self.scope)
        self.assertEqual(gate_result.published, 1)
        self.assertEqual(publisher.events[-1]["topic"], "gateEvents")

        self.store.append_event(
            self.scope,
            "proof_drift",
            "dependency-outbox",
            "dependency_changed",
            {
                "dependencyKind": "TCB",
                "dependencyId": "dependency-outbox",
                "oldHash": "e" * 64,
                "newHash": "f" * 64,
            },
        )

        class FailingPublisher:
            def publish(self, **_: object) -> str:
                raise RuntimeError("broker unavailable")

        failed = OutboxDispatcher(
            self.store, FailingPublisher(), max_attempts=1
        ).dispatch(self.scope)
        self.assertEqual(failed.failed, 1)
        self.assertEqual(failed.dead, 1)

    def test_runtime_wires_authorized_bounded_outbox_delivery(self) -> None:
        publisher = DigestReceiptPublisher()
        runtime = FormalAssuranceRuntime(
            store=self.store,
            config=RuntimeConfig(event_publisher=publisher),
        )
        self.store.append_event(
            self.scope,
            "proof_run",
            "run-runtime-outbox",
            "submitted",
            {"obligationId": "obligation-runtime-outbox"},
        )
        with self.assertRaises(RuntimeAuthorizationError):
            runtime.dispatch_outbox({"scope": self.scope.to_dict()}, self.identity)
        publisher_identity = TrustedIdentity(
            "tenant-a",
            "event-publisher",
            "project-a",
            roles=("formal-assurance-event-publisher",),
            authorization_ref="authz:event-publisher:a",
        )
        result = runtime.dispatch_outbox(
            {"scope": self.scope.to_dict(), "limit": 100}, publisher_identity
        )
        self.assertGreaterEqual(result["published"], 1)
        self.assertEqual(
            result["deliverySemantics"],
            "AT_LEAST_ONCE_WITH_IDEMPOTENCY_AND_RECONCILIATION",
        )
        self.assertEqual(result["externalEvidenceStatus"], "NOT_RUN")
        audit = self.store.security_audit(publisher_identity)
        self.assertTrue(any(item["decision"] == "ALLOW" for item in audit))


class GovernanceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = StateStore()
        runtime = FormalAssuranceRuntime(
            store=self.store,
            config=RuntimeConfig(
                artifact_root=Path(self.temporary.name) / "artifacts",
                artifact_envelope_cipher=AesGcmEnvelopeCipher(
                    b"i" * 32, key_id="api-test-key"
                ),
                bundle_signer=HmacEvidenceBundleSigner(b"a" * 32),
            ),
        )
        self.api = FormalAssuranceApi(runtime)
        self.identity = TrustedIdentity("tenant-a", "actor-a", "project-a")

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def headers(self, idempotency_key: str) -> dict[str, str]:
        return {
            "HTTP_X_ELMOS_ACCOUNT_ID": "account-a",
            "HTTP_X_ELMOS_PROJECT_ID": "project-a",
            "HTTP_X_ELMOS_SOURCE_ARTIFACT_DIGEST": "a" * 64,
            "HTTP_X_ELMOS_TARGET_ARTIFACT_DIGEST": "b" * 64,
            "HTTP_X_ELMOS_ENVIRONMENT_DIGEST": "c" * 64,
            "HTTP_X_ELMOS_WORKLOAD_KEY": "governance-test",
            "HTTP_X_ELMOS_IDEMPOTENCY_KEY": idempotency_key,
        }

    def call(
        self,
        path: str,
        payload: dict[str, object],
        identity: TrustedIdentity,
        idempotency_key: str,
    ) -> tuple[str, dict[str, object]]:
        environ = make_environ(path, "POST", payload, identity)
        environ.update(self.headers(idempotency_key))
        captured: list[str] = []
        body = b"".join(self.api(environ, lambda status, _: captured.append(status)))
        return captured[0], json.loads(body)

    def test_governance_and_bundle_openapi_paths_are_wired(self) -> None:
        status, assumption = self.call(
            "/v1/assumptions",
            assumption_document("assumption-api"),
            self.identity,
            "assumption-api",
        )
        self.assertEqual(status, "201 Created")
        self.assertEqual(assumption["status"], "ACTIVE")

        self.store.put_document(
            current_scope(),
            "proof_artifact",
            "artifact-api",
            {"runId": "run-api-bundle", "proofStatus": "BOUNDED_NO_COUNTEREXAMPLE"},
        )
        status, bundle = self.call(
            "/v1/evidence-bundles",
            {
                "subjectId": "run-api-bundle",
                "redactionPolicy": "STRICT",
                "sign": True,
            },
            self.identity,
            "bundle-api-build",
        )
        self.assertEqual(status, "202 Accepted")
        status, verified = self.call(
            f"/v1/evidence-bundles/{bundle['bundleId']}/verify",
            {},
            self.identity,
            "bundle-api-verify",
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(verified["integrityStatus"], "VERIFIED")

        status, denied = self.call(
            "/v1/trusted-components",
            {
                "id": "tcb-api",
                "name": "Z3",
                "componentType": "SOLVER",
                "version": "4.15.3",
                "digest": "e" * 64,
                "trustReason": "Pinned executable",
                "status": "PINNED",
            },
            self.identity,
            "tcb-api-denied",
        )
        self.assertEqual(status, "403 Forbidden")
        self.assertIn("TCB admin", denied["error"])


if __name__ == "__main__":
    unittest.main()
