from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from elmos_autonomous_qa.api import QaApi, TrustedIdentity
from elmos_autonomous_qa.control_plane import QaControlPlane, ResourceQuotaExceeded
from elmos_autonomous_qa.delivery_service import TrustedDeliveryService


class QaApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.api = QaApi(QaControlPlane(Path(self.temporary.name) / "qa.sqlite3"))
        self.writer = TrustedIdentity(
            tenant_id="tenant-a",
            actor_id="actor-a",
            roles=frozenset({"qa:read", "qa:write", "qa:audit"}),
            project_ids=frozenset({"project-a"}),
        )

    def test_identity_scope_is_not_taken_from_request_json(self) -> None:
        created = self.api.handle(
            "POST",
            "/api/v1/qa/runs",
            {
                "tenant_id": "tenant-b",
                "run_id": "run-1",
                "project_id": "project-a",
                "mode": "generate",
                "payload": {"snapshot": "snapshot-1"},
                "idempotency_key": "create-1",
            },
            self.writer,
        )
        self.assertEqual(created.status, 201)
        self.assertEqual(created.body["tenant_id"], "tenant-a")
        other_tenant = TrustedIdentity(
            tenant_id="tenant-b",
            actor_id="actor-b",
            roles=frozenset({"qa:read"}),
            project_ids=frozenset({"project-a"}),
        )
        missing = self.api.handle("GET", "/api/v1/qa/runs/run-1", {}, other_tenant)
        self.assertEqual(missing.status, 404)

    def test_unauthenticated_and_unprivileged_requests_are_denied(self) -> None:
        unauthenticated = self.api.handle("GET", "/api/v1/qa/capabilities", {}, None)
        self.assertEqual(unauthenticated.status, 403)
        reader = TrustedIdentity(
            "tenant-a",
            "reader-a",
            frozenset({"qa:read"}),
            frozenset({"project-a"}),
        )
        denied = self.api.handle(
            "POST",
            "/api/v1/qa/runs",
            {"project_id": "project-a", "mode": "generate", "idempotency_key": "key"},
            reader,
        )
        self.assertEqual(denied.status, 403)

    def test_trusted_identity_requires_exact_types(self) -> None:
        with self.assertRaises(TypeError):
            TrustedIdentity(  # type: ignore[arg-type]
                "tenant-a", "actor-a", "qa:read", frozenset({"project-a"})
            )
        with self.assertRaises(TypeError):
            TrustedIdentity(
                "tenant-a",
                "actor-a",
                frozenset({"qa:read"}),
                frozenset({"project-a"}),
                authenticated=1,  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            TrustedIdentity(
                "tenant-a", "", frozenset({"qa:read"}), frozenset({"project-a"})
            )
        for invalid_tenant in (
            " tenant-a",
            "tenant-a ",
            "tenant-\u202e",
            "tenant-\u0085",
        ):
            with self.subTest(invalid_tenant=invalid_tenant):
                with self.assertRaises(ValueError):
                    TrustedIdentity(
                        invalid_tenant,
                        "actor-a",
                        frozenset({"qa:read"}),
                        frozenset({"project-a"}),
                    )
        with self.assertRaises(ValueError):
            TrustedIdentity(
                "tenant-a",
                "actor-a",
                frozenset({"qa:read "}),
                frozenset({"project-a"}),
            )
        with self.assertRaises(ValueError):
            TrustedIdentity(
                "tenant-a",
                "actor-a",
                frozenset(f"role-{index}" for index in range(65)),
                frozenset({"project-a"}),
            )
        with self.assertRaises(ValueError):
            TrustedIdentity(
                "tenant-a",
                "actor-a",
                frozenset({"qa:read"}),
                frozenset(f"project-{index}" for index in range(1025)),
            )
        unauthenticated = TrustedIdentity(
            "tenant-a",
            "actor-a",
            frozenset({"qa:read"}),
            frozenset({"project-a"}),
            authenticated=False,
        )
        response = self.api.handle(
            "GET", "/api/v1/qa/capabilities", {}, unauthenticated
        )
        self.assertEqual(response.status, 403)

    def test_same_tenant_cross_project_access_is_denied(self) -> None:
        project_b_writer = TrustedIdentity(
            "tenant-a",
            "actor-b",
            frozenset({"qa:read", "qa:write", "qa:audit"}),
            frozenset({"project-b"}),
        )
        project_a_intruder = TrustedIdentity(
            "tenant-a",
            "intruder-a",
            frozenset(
                {
                    "qa:read",
                    "qa:write",
                    "qa:audit",
                    "qa:approve",
                    "qa:evidence:verify",
                    "qa:evidence:revoke",
                }
            ),
            frozenset({"project-a"}),
        )
        created = self.api.handle(
            "POST",
            "/api/v1/qa/runs",
            {
                "run_id": "run-project-b",
                "project_id": "project-b",
                "mode": "verify",
                "idempotency_key": "create-project-b",
            },
            project_b_writer,
        )
        self.assertEqual(created.status, 201)
        denied_read = self.api.handle(
            "GET", "/api/v1/qa/runs/run-project-b", {}, project_a_intruder
        )
        self.assertEqual(denied_read.status, 403)
        denied_events = self.api.handle(
            "GET",
            "/api/v1/qa/runs/run-project-b/events",
            {},
            project_a_intruder,
        )
        self.assertEqual(denied_events.status, 403)
        denied_audit = self.api.handle(
            "GET",
            "/api/v1/qa/runs/run-project-b/audit",
            {},
            project_a_intruder,
        )
        self.assertEqual(denied_audit.status, 403)
        denied_transition = self.api.handle(
            "POST",
            "/api/v1/qa/runs/run-project-b:start",
            {"idempotency_key": "start-project-b"},
            project_a_intruder,
        )
        self.assertEqual(denied_transition.status, 403)
        denied_approval = self.api.handle(
            "POST",
            "/api/v1/qa/runs/run-project-b:approve",
            {"idempotency_key": "approve-project-b", "details": {}},
            project_a_intruder,
        )
        self.assertEqual(denied_approval.status, 403)
        denied_retry = self.api.handle(
            "POST",
            "/api/v1/qa/runs/run-project-b:retry",
            {
                "new_run_id": "run-project-b-retry",
                "idempotency_key": "retry-project-b",
            },
            project_a_intruder,
        )
        self.assertEqual(denied_retry.status, 403)
        denied_create = self.api.handle(
            "POST",
            "/api/v1/qa/runs",
            {
                "run_id": "run-project-b-other",
                "project_id": "project-b",
                "mode": "verify",
                "idempotency_key": "create-project-b-other",
            },
            project_a_intruder,
        )
        self.assertEqual(denied_create.status, 403)
        denied_skill = self.api.handle(
            "POST",
            "/api/v1/qa/skills/02-spec-normalization:execute",
            {"project_id": "project-b", "inputs": {}},
            project_a_intruder,
        )
        self.assertEqual(denied_skill.status, 403)
        denied_evidence = self.api.handle(
            "POST",
            "/api/v1/qa/evidence",
            {
                "receipt_id": "receipt-project-b",
                "run_id": "run-project-b",
                "scope": "scope-b",
                "subject_digest": "a" * 64,
                "evidence_digest": "b" * 64,
                "artifact_digest": "c" * 64,
                "authorization_ref": "authorization-b",
                "executor_id": "executor-b",
                "verifier_id": "intruder-a",
                "valid_until": "2099-01-01T00:00:00Z",
            },
            project_a_intruder,
        )
        self.assertEqual(denied_evidence.status, 403)

        self.assertEqual(
            self.api.handle(
                "POST",
                "/api/v1/qa/runs/run-project-b:start",
                {"idempotency_key": "start-project-b-owner"},
                project_b_writer,
            ).status,
            200,
        )
        self.assertEqual(
            self.api.handle(
                "POST",
                "/api/v1/qa/runs/run-project-b:request_approval",
                {
                    "idempotency_key": "request-project-b-owner",
                    "details": {
                        "scope": "scope-b",
                        "subject_digest": "a" * 64,
                        "authorization_ref": "authorization-b",
                    },
                },
                project_b_writer,
            ).status,
            200,
        )
        project_b_verifier = TrustedIdentity(
            "tenant-a",
            "verifier-b",
            frozenset({"qa:evidence:verify"}),
            frozenset({"project-b"}),
        )
        self.assertEqual(
            self.api.handle(
                "POST",
                "/api/v1/qa/evidence",
                {
                    "receipt_id": "receipt-project-b",
                    "run_id": "run-project-b",
                    "scope": "scope-b",
                    "subject_digest": "a" * 64,
                    "evidence_digest": "b" * 64,
                    "artifact_digest": "c" * 64,
                    "authorization_ref": "authorization-b",
                    "executor_id": "executor-b",
                    "verifier_id": "verifier-b",
                    "valid_until": "2099-01-01T00:00:00Z",
                },
                project_b_verifier,
            ).status,
            201,
        )
        denied_revoke = self.api.handle(
            "POST",
            "/api/v1/qa/evidence/receipt-project-b:revoke",
            {},
            project_a_intruder,
        )
        self.assertEqual(denied_revoke.status, 403)

    def test_skill_dispatch_uses_trusted_scope_and_keeps_external_boundary(self) -> None:
        response = self.api.handle(
            "POST",
            "/api/v1/qa/skills/02-spec-normalization:execute",
            {
                "request_id": "request-1",
                "project_id": "project-a",
                "idempotency_key": "skill-1",
                "inputs": {
                    "requirements": [
                        {
                            "requirement_id": "REQ-1",
                            "title": "Behavior",
                            "statement": "Behavior is deterministic.",
                            "priority": "P0",
                            "required": True,
                            "source_refs": ["requirements.md:1"],
                            "acceptance_criteria": ["Same input yields the same output."],
                            "ambiguities": [],
                            "status": "ready",
                        }
                    ]
                },
            },
            self.writer,
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["external_evidence"], "NOT_RUN")
        self.assertEqual(response.body["certification"], "NOT_CERTIFIED")

    def test_delivery_skills_require_exact_roles_and_use_trusted_service(self) -> None:
        denied = self.api.handle(
            "POST",
            "/api/v1/qa/skills/38-project-output-bundle-publishing:execute",
            {
                "project_id": "project-a",
                "idempotency_key": "publish-denied",
                "inputs": {"session_id": "delivery-session-denied"},
            },
            self.writer,
        )
        self.assertEqual(denied.status, 403)

        root = Path(self.temporary.name)
        embedded = root / "delivery-project-a"
        embedded.mkdir(mode=0o700)
        service = TrustedDeliveryService(
            staging_root=root / "delivery-staging",
            publication_root=root / "delivery-publication",
            lifecycle_root=root / "delivery-lifecycle",
            state_root=root / "delivery-state",
            database_path=root / "delivery-state" / "delivery.sqlite3",
            embedded_roots={("tenant-a", "project-a"): embedded},
        )
        api = QaApi(
            QaControlPlane(root / "delivery-control-plane.sqlite3"),
            delivery_service=service,
        )
        delivery_identity = TrustedIdentity(
            tenant_id="tenant-a",
            actor_id="actor-delivery",
            roles=frozenset({"qa:write", "qa:publish", "qa:lifecycle"}),
            project_ids=frozenset({"project-a"}),
        )
        test_case = {
            "test_case_id": "TC-api-delivery",
            "title": "API delivery remains tenant and project bound",
            "test_type": "functional",
            "priority": "P0",
            "required": True,
            "requirement_refs": ["REQ-api-delivery"],
            "preconditions": ["the trusted delivery service is configured"],
            "steps": [
                {
                    "step_id": "observe-output",
                    "action": "observe-output",
                    "input": {"expected": "project-bound"},
                    "timeout_ms": 30_000,
                    "side_effect": False,
                }
            ],
            "oracles": [
                {
                    "oracle_id": "oracle-api-delivery",
                    "kind": "invariant",
                    "assertion": "output remains in the authorized project",
                    "source": "REQ-api-delivery",
                }
            ],
            "evidence_requirements": ["raw-runner-output"],
            "cleanup": [],
            "executor": {
                "adapter_key": "python",
                "capability": "unit",
                "parameters": {},
                "environment_profile": "isolated-local",
            },
        }
        materialized = api.handle(
            "POST",
            "/api/v1/qa/skills/37-test-source-materialization:execute",
            {
                "request_id": "request-api-materialize",
                "project_id": "project-a",
                "idempotency_key": "api-materialize",
                "inputs": {
                    "suite_id": "suite-api-delivery",
                    "adapter_key": "python",
                    "test_cases": [test_case],
                    "fixture_records": [],
                    "mock_records": [],
                    "synthetic_data_records": [],
                    "config": {"runtime_profile": "isolated-local"},
                    "revision_id": "revision-api-delivery",
                    "run_id": "run-api-delivery",
                    "run_mode": "generate",
                    "output_mode": "sidecar",
                    "source_snapshot_digest": "d" * 64,
                },
            },
            delivery_identity,
        )
        self.assertEqual(materialized.status, 200)
        self.assertEqual(materialized.body["state"], "PARTIAL")
        self.assertEqual(materialized.body["outputs"]["native_build"], "NOT_RUN")
        session_id = materialized.body["outputs"]["session_id"]

        published = api.handle(
            "POST",
            "/api/v1/qa/skills/38-project-output-bundle-publishing:execute",
            {
                "request_id": "request-api-publish",
                "project_id": "project-a",
                "idempotency_key": "api-publish",
                "inputs": {"session_id": session_id},
            },
            delivery_identity,
        )
        self.assertEqual(published.status, 200)
        self.assertEqual(published.body["state"], "SUCCEEDED")
        self.assertEqual(published.body["outputs"]["signing"], "NOT_RUN")

        registered = api.handle(
            "POST",
            "/api/v1/qa/skills/39-output-versioning-retention:execute",
            {
                "request_id": "request-api-register",
                "project_id": "project-a",
                "idempotency_key": "api-register",
                "inputs": {"action": "register", "session_id": session_id},
            },
            delivery_identity,
        )
        self.assertEqual(registered.status, 200)
        self.assertEqual(registered.body["state"], "SUCCEEDED")
        self.assertTrue(registered.body["outputs"]["lifecycle_registered"])

    def test_approval_requires_separate_privilege_and_exact_evidence(self) -> None:
        self.api.handle(
            "POST",
            "/api/v1/qa/runs",
            {
                "run_id": "run-approval",
                "project_id": "project-a",
                "mode": "repair",
                "idempotency_key": "create-approval",
            },
            self.writer,
        )
        self.api.handle(
            "POST",
            "/api/v1/qa/runs/run-approval:start",
            {"idempotency_key": "start-approval"},
            self.writer,
        )
        self.api.handle(
            "POST",
            "/api/v1/qa/runs/run-approval:request_approval",
            {
                "idempotency_key": "request-approval",
                "details": {
                    "scope": "run-approval:repair-plan-1",
                    "subject_digest": "a" * 64,
                    "authorization_ref": "authorization-1",
                },
            },
            self.writer,
        )
        denied = self.api.handle(
            "POST",
            "/api/v1/qa/runs/run-approval:approve",
            {"idempotency_key": "approve-1", "details": {}},
            self.writer,
        )
        self.assertEqual(denied.status, 403)
        verifier = TrustedIdentity(
            "tenant-a",
            "verifier-b",
            frozenset({"qa:evidence:verify"}),
            frozenset({"project-a"}),
        )
        registered = self.api.handle(
            "POST",
            "/api/v1/qa/evidence",
            {
                "receipt_id": "receipt-approval",
                "run_id": "run-approval",
                "scope": "run-approval:repair-plan-1",
                "subject_digest": "a" * 64,
                "evidence_digest": "b" * 64,
                "artifact_digest": "c" * 64,
                "authorization_ref": "authorization-1",
                "executor_id": "executor-a",
                "verifier_id": "verifier-b",
                "valid_until": "2099-01-01T00:00:00Z",
            },
            verifier,
        )
        self.assertEqual(registered.status, 201)
        approver = TrustedIdentity(
            "tenant-a",
            "reviewer-a",
            frozenset({"qa:approve"}),
            frozenset({"project-a"}),
        )
        approval_details = {
            "decision": "approved",
            "approver_id": "reviewer-a",
            "scope": "run-approval:repair-plan-1",
            "subject_digest": "a" * 64,
            "authorization_ref": "authorization-1",
            "evidence_receipt_id": "receipt-approval",
            "executor_id": "executor-a",
            "verifier_id": "verifier-b",
        }
        forged_actor = self.api.handle(
            "POST",
            "/api/v1/qa/runs/run-approval:approve",
            {
                "idempotency_key": "approve-forged-actor",
                "details": {**approval_details, "approver_id": "body-selected-actor"},
            },
            approver,
        )
        self.assertEqual(forged_actor.status, 409)
        approved = self.api.handle(
            "POST",
            "/api/v1/qa/runs/run-approval:approve",
            {"idempotency_key": "approve-good", "details": approval_details},
            approver,
        )
        self.assertEqual(approved.status, 200)
        self.assertEqual(approved.body["status"], "running")
        receipt = self.api.control_plane.get_verified_evidence(
            tenant_id="tenant-a", receipt_id="receipt-approval"
        )
        self.assertEqual(receipt.consumed_by, "reviewer-a")

    def test_json_field_types_reject_null_without_stringifying_it(self) -> None:
        rejected = self.api.handle(
            "POST",
            "/api/v1/qa/runs",
            {
                "run_id": None,
                "project_id": None,
                "mode": "verify",
                "payload": {},
                "idempotency_key": "create-null",
            },
            self.writer,
        )
        self.assertEqual(rejected.status, 422)
        self.assertEqual(rejected.body["error_code"], "QA_REQUEST_INVALID")
        missing = self.api.handle("GET", "/api/v1/qa/runs/None", {}, self.writer)
        self.assertEqual(missing.status, 404)

    def test_evidence_registration_and_revocation_endpoints_are_tenant_scoped(self) -> None:
        created = self.api.handle(
            "POST",
            "/api/v1/qa/runs",
            {
                "run_id": "run-evidence",
                "project_id": "project-a",
                "mode": "verify",
                "payload": {},
                "idempotency_key": "create-evidence",
            },
            self.writer,
        )
        self.assertEqual(created.status, 201)
        started = self.api.handle(
            "POST",
            "/api/v1/qa/runs/run-evidence:start",
            {"idempotency_key": "start-evidence"},
            self.writer,
        )
        self.assertEqual(started.status, 200)
        requested = self.api.handle(
            "POST",
            "/api/v1/qa/runs/run-evidence:request_approval",
            {
                "idempotency_key": "request-evidence",
                "details": {
                    "scope": "run-evidence:scope-1",
                    "subject_digest": "a" * 64,
                    "authorization_ref": "authorization-1",
                },
            },
            self.writer,
        )
        self.assertEqual(requested.status, 200)
        verifier = TrustedIdentity(
            "tenant-a",
            "verifier-b",
            frozenset({"qa:evidence:verify", "qa:evidence:revoke"}),
            frozenset({"project-a"}),
        )
        evidence = {
            "receipt_id": "receipt-1",
            "run_id": "run-evidence",
            "scope": "run-evidence:scope-1",
            "subject_digest": "a" * 64,
            "evidence_digest": "b" * 64,
            "artifact_digest": "c" * 64,
            "authorization_ref": "authorization-1",
            "executor_id": "executor-a",
            "verifier_id": "verifier-b",
            "valid_until": "2099-01-01T00:00:00Z",
        }
        mismatched_verifier = self.api.handle(
            "POST",
            "/api/v1/qa/evidence",
            {
                **evidence,
                "receipt_id": "receipt-verifier-mismatch",
                "verifier_id": "untrusted-body-verifier",
            },
            verifier,
        )
        self.assertEqual(mismatched_verifier.status, 422)
        registered = self.api.handle(
            "POST", "/api/v1/qa/evidence", evidence, verifier
        )
        self.assertEqual(registered.status, 201)
        self.assertEqual(registered.body["tenant_id"], "tenant-a")
        revoked = self.api.handle(
            "POST", "/api/v1/qa/evidence/receipt-1:revoke", {}, verifier
        )
        replay = self.api.handle(
            "POST", "/api/v1/qa/evidence/receipt-1:revoke", {}, verifier
        )
        self.assertEqual(revoked.status, 200)
        self.assertTrue(revoked.body["revoked"])
        self.assertEqual(revoked.body, replay.body)

        other_verifier = TrustedIdentity(
            "tenant-b",
            "verifier-b",
            frozenset({"qa:evidence:revoke"}),
            frozenset({"project-a"}),
        )
        missing = self.api.handle(
            "POST", "/api/v1/qa/evidence/receipt-1:revoke", {}, other_verifier
        )
        self.assertEqual(missing.status, 404)
        self.assertEqual(
            missing.body["error_code"], "QA_EVIDENCE_RECEIPT_NOT_FOUND"
        )

    def test_conflict_transition_and_evidence_errors_are_distinct(self) -> None:
        request = {
            "run_id": "run-errors",
            "project_id": "project-a",
            "mode": "verify",
            "payload": {},
            "idempotency_key": "create-errors",
        }
        self.assertEqual(
            self.api.handle("POST", "/api/v1/qa/runs", request, self.writer).status,
            201,
        )
        duplicate = self.api.handle(
            "POST",
            "/api/v1/qa/runs",
            {**request, "idempotency_key": "create-errors-2"},
            self.writer,
        )
        self.assertEqual(duplicate.status, 409)
        self.assertEqual(duplicate.body["error_code"], "QA_RUN_ALREADY_EXISTS")
        idempotency_conflict = self.api.handle(
            "POST",
            "/api/v1/qa/runs",
            {**request, "run_id": "run-other"},
            self.writer,
        )
        self.assertEqual(idempotency_conflict.status, 409)
        self.assertEqual(
            idempotency_conflict.body["error_code"], "QA_IDEMPOTENCY_CONFLICT"
        )

        illegal = self.api.handle(
            "POST",
            "/api/v1/qa/runs/run-errors:pause",
            {"idempotency_key": "pause-created", "details": {}},
            self.writer,
        )
        self.assertEqual(illegal.status, 409)
        self.assertEqual(illegal.body["error_code"], "QA_ILLEGAL_TRANSITION")

        verifier = TrustedIdentity(
            "tenant-a",
            "verifier-b",
            frozenset({"qa:evidence:verify"}),
            frozenset({"project-a"}),
        )
        invalid_evidence = self.api.handle(
            "POST",
            "/api/v1/qa/evidence",
            {
                "receipt_id": "receipt-bad",
                "run_id": "run-errors",
                "scope": "scope-1",
                "subject_digest": "a" * 64,
                "evidence_digest": "b" * 64,
                "artifact_digest": "c" * 64,
                "authorization_ref": "authorization-1",
                "executor_id": "verifier-b",
                "verifier_id": "verifier-b",
                "valid_until": "2099-01-01T00:00:00Z",
            },
            verifier,
        )
        self.assertEqual(invalid_evidence.status, 422)
        self.assertEqual(
            invalid_evidence.body["error_code"], "QA_EVIDENCE_REJECTED"
        )

    def test_sqlite_operational_error_is_retryable_service_unavailable(self) -> None:
        with patch.object(
            self.api.control_plane,
            "create_run",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            response = self.api.handle(
                "POST",
                "/api/v1/qa/runs",
                {
                    "run_id": "run-locked",
                    "project_id": "project-a",
                    "mode": "verify",
                    "payload": {},
                    "idempotency_key": "create-locked",
                },
                self.writer,
            )
        self.assertEqual(response.status, 503)
        self.assertEqual(response.body["error_code"], "QA_STORAGE_UNAVAILABLE")
        self.assertTrue(response.body["retryable"])

    def test_sqlite_integrity_error_fails_closed(self) -> None:
        with patch.object(
            self.api.control_plane,
            "create_run",
            side_effect=sqlite3.IntegrityError("foreign key constraint failed"),
        ):
            response = self.api.handle(
                "POST",
                "/api/v1/qa/runs",
                {
                    "run_id": "run-integrity-error",
                    "project_id": "project-a",
                    "mode": "verify",
                    "payload": {},
                    "idempotency_key": "create-integrity-error",
                },
                self.writer,
            )
        self.assertEqual(response.status, 500)
        self.assertEqual(
            response.body["error_code"], "QA_CONTROL_PLANE_INTEGRITY_ERROR"
        )
        self.assertFalse(response.body["retryable"])

    def test_resource_quota_is_reported_without_retrying_the_mutation(self) -> None:
        with patch.object(
            self.api.control_plane,
            "create_run",
            side_effect=ResourceQuotaExceeded("tenant quota reached"),
        ):
            response = self.api.handle(
                "POST",
                "/api/v1/qa/runs",
                {
                    "run_id": "run-quota",
                    "project_id": "project-a",
                    "mode": "verify",
                    "idempotency_key": "create-quota",
                },
                self.writer,
            )
        self.assertEqual(429, response.status)
        self.assertEqual("QA_RESOURCE_QUOTA_EXCEEDED", response.body["error_code"])
        self.assertFalse(response.body["retryable"])

    def test_deep_request_body_is_rejected_before_route_processing(self) -> None:
        nested: object = "leaf"
        for _ in range(40):
            nested = {"child": nested}
        response = self.api.handle(
            "GET",
            "/api/v1/qa/capabilities",
            {"nested": nested},
            self.writer,
        )
        self.assertEqual(response.status, 422)
        self.assertEqual(response.body["error_code"], "QA_REQUEST_INVALID")

    def test_method_and_path_inputs_are_bounded_before_routing(self) -> None:
        oversized_method = self.api.handle(
            "G" * 17, "/api/v1/qa/capabilities", {}, self.writer
        )
        self.assertEqual(422, oversized_method.status)
        self.assertEqual(
            "QA_REQUEST_INVALID", oversized_method.body["error_code"]
        )
        oversized_path = self.api.handle("GET", "/" + "a" * 1024, {}, self.writer)
        self.assertEqual(422, oversized_path.status)
        self.assertEqual("QA_REQUEST_INVALID", oversized_path.body["error_code"])

    def test_event_and_audit_api_reads_are_cursor_paginated(self) -> None:
        created = self.api.handle(
            "POST",
            "/api/v1/qa/runs",
            {
                "run_id": "run-pages",
                "project_id": "project-a",
                "mode": "verify",
                "idempotency_key": "create-pages",
            },
            self.writer,
        )
        self.assertEqual(201, created.status)
        for action in ("start", "pause", "resume"):
            transitioned = self.api.handle(
                "POST",
                f"/api/v1/qa/runs/run-pages:{action}",
                {"idempotency_key": f"{action}-pages"},
                self.writer,
            )
            self.assertEqual(200, transitioned.status)
        first = self.api.handle(
            "GET",
            "/api/v1/qa/runs/run-pages/events",
            {"limit": 2},
            self.writer,
        )
        self.assertEqual(200, first.status)
        self.assertEqual(2, len(first.body["events"]))
        self.assertEqual(2, first.body["next_after_sequence"])
        second = self.api.handle(
            "GET",
            "/api/v1/qa/runs/run-pages/events",
            {"limit": 2, "after_sequence": first.body["next_after_sequence"]},
            self.writer,
        )
        self.assertEqual([3, 4], [event["sequence"] for event in second.body["events"]])
        audit = self.api.handle(
            "GET",
            "/api/v1/qa/runs/run-pages/audit",
            {"limit": 1},
            self.writer,
        )
        self.assertEqual(200, audit.status)
        self.assertEqual(1, len(audit.body["audit"]))
        self.assertIsNotNone(audit.body["next_after_audit_id"])
        boundary = self.api.handle(
            "GET",
            "/api/v1/qa/runs/run-pages/events",
            {"limit": 500},
            self.writer,
        )
        self.assertEqual(200, boundary.status)
        self.assertEqual(500, boundary.body["page_limit"])
        rejected = self.api.handle(
            "GET",
            "/api/v1/qa/runs/run-pages/events",
            {"limit": 501},
            self.writer,
        )
        self.assertEqual(422, rejected.status)
        self.assertEqual("QA_REQUEST_INVALID", rejected.body["error_code"])


if __name__ == "__main__":
    unittest.main()
