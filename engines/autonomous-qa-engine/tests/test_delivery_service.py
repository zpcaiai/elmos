from __future__ import annotations

import copy
import sqlite3
import stat
import sys
import tempfile
import threading
import unittest
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import elmos_autonomous_qa.artifacts as artifact_module  # noqa: E402
import elmos_autonomous_qa.delivery_service as delivery_service_module  # noqa: E402
from elmos_autonomous_qa.contracts import RuntimeRequest  # noqa: E402
from elmos_autonomous_qa.delivery_service import (  # noqa: E402
    DeliveryAuthorizationError,
    DeliveryContractError,
    DeliveryStateError,
    TrustedDeliveryService,
    lifecycle_operation_contract,
    publishing_operation_contract,
)


class TrustedDeliveryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        # macOS exposes its default temporary directory through the /var
        # symlink.  Delivery roots must reject symlinked ancestors, so keep the
        # fixture on the physical path and preserve the production boundary.
        temporary_base = Path(tempfile.gettempdir()).resolve(strict=True)
        self.temporary = tempfile.TemporaryDirectory(dir=temporary_base)
        self.root = Path(self.temporary.name)
        self.staging = self.root / "private-staging"
        self.publication = self.root / "publication"
        self.lifecycle = self.root / "lifecycle"
        self.state = self.root / "state"
        self.embedded_a = self.root / "project-a-worktree"
        self.embedded_b = self.root / "project-b-worktree"
        self.embedded_a.mkdir(mode=0o700)
        self.embedded_b.mkdir(mode=0o700)
        self.database = self.state / "delivery.sqlite3"
        self.configuration = {
            "staging_root": self.staging,
            "publication_root": self.publication,
            "lifecycle_root": self.lifecycle,
            "state_root": self.state,
            "database_path": self.database,
            "embedded_roots": {
                ("tenant-a", "project-a"): self.embedded_a,
                ("tenant-a", "project-b"): self.embedded_b,
            },
        }
        self.service = TrustedDeliveryService(**self.configuration)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def stage_request(
        self,
        *,
        idempotency_key: str = "stage-1",
        revision_id: str = "revision-1",
        run_id: str = "run-1",
        project_id: str = "project-a",
        source_snapshot_digest: str = "b" * 64,
        source: bytes = b"def test_value():\n    assert 2 + 2 == 4\n",
        output_mode: str = "sidecar",
    ) -> dict[str, object]:
        return {
            "tenant_id": "tenant-a",
            "project_id": project_id,
            "revision_id": revision_id,
            "run_id": run_id,
            "run_mode": "generate",
            "output_mode": output_mode,
            "source_snapshot_digest": source_snapshot_digest,
            "idempotency_key": idempotency_key,
            "artifacts": [
                {
                    "artifact_id": "artifact-test-value",
                    "path": "tests/test_value.py",
                    "category": "test_source",
                    "role": "unit_test",
                    "producer": "test-generator-v1",
                    "required": True,
                    "validation_status": "generated",
                    "requirement_refs": ["REQ-VALUE-1"],
                    "test_case_refs": ["TC-VALUE-1"],
                    "source_bytes": source,
                }
            ],
        }

    @staticmethod
    def publish_request(
        session_id: str,
        *,
        idempotency_key: str = "publish-1",
        project_id: str = "project-a",
    ) -> dict[str, str]:
        return {
            "tenant_id": "tenant-a",
            "project_id": project_id,
            "session_id": session_id,
            "idempotency_key": idempotency_key,
        }

    def lifecycle_request(
        self,
        action: str,
        idempotency_key: str,
        *,
        project_id: str = "project-a",
        **fields: object,
    ) -> dict[str, object]:
        return {
            "tenant_id": "tenant-a",
            "project_id": project_id,
            "action": action,
            "idempotency_key": idempotency_key,
            **fields,
        }

    @staticmethod
    def dsl_case() -> dict[str, object]:
        return {
            "test_case_id": "TC-trusted-delivery",
            "title": "trusted delivery preserves the emitted test contract",
            "test_type": "functional",
            "priority": "P0",
            "required": True,
            "requirement_refs": ["REQ-trusted-delivery"],
            "preconditions": ["the tenant project grant is active"],
            "steps": [
                {
                    "step_id": "observe-output",
                    "action": "observe-output",
                    "input": {"expected": "tenant-scoped"},
                    "timeout_ms": 30_000,
                    "side_effect": False,
                }
            ],
            "oracles": [
                {
                    "oracle_id": "oracle-output",
                    "kind": "invariant",
                    "assertion": "the output remains bound to the authorized project",
                    "source": "REQ-trusted-delivery",
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

    @staticmethod
    def runtime_request(
        inputs: dict[str, object],
        *,
        request_id: str,
        idempotency_key: str,
        project_id: str = "project-a",
    ) -> RuntimeRequest:
        return RuntimeRequest.parse(
            {
                "schema_version": "1.0",
                "request_id": request_id,
                "tenant_id": "tenant-a",
                "project_id": project_id,
                "actor_id": "actor-qa-publisher",
                "idempotency_key": idempotency_key,
                "inputs": inputs,
            }
        )

    def stage_and_publish(
        self,
        *,
        suffix: str,
        revision_id: str,
        source_snapshot_digest: str,
    ) -> tuple[str, str, Path]:
        staged = self.service.stage(
            self.stage_request(
                idempotency_key=f"stage-{suffix}",
                revision_id=revision_id,
                run_id=f"run-{suffix}",
                source_snapshot_digest=source_snapshot_digest,
            )
        )
        session_id = str(staged["outputs"]["session_id"])
        published = self.service.publish(
            self.publish_request(
                session_id, idempotency_key=f"publish-{suffix}"
            )
        )
        self.assertEqual(published["state"], "SUCCEEDED")
        row = self.service._session_row(
            tenant_id="tenant-a",
            project_id="project-a",
            session_id=session_id,
        )
        final_root = self.service._plan_from_row(row).final_root
        return session_id, str(staged["outputs"]["output_id"]), final_root

    def register(self, session_id: str, suffix: str) -> dict[str, object]:
        return dict(
            self.service.lifecycle(
                self.lifecycle_request(
                    "register",
                    f"lifecycle-register-{suffix}",
                    session_id=session_id,
                )
            )
        )

    def stale_registered_output(
        self, *, suffix: str, source_snapshot_digest: str
    ) -> tuple[str, Path]:
        session_id, output_id, output_root = self.stage_and_publish(
            suffix=suffix,
            revision_id=f"revision-{suffix}",
            source_snapshot_digest=source_snapshot_digest,
        )
        self.assertEqual(self.register(session_id, suffix)["state"], "SUCCEEDED")
        self.service.lifecycle_store.mark_stale(
            tenant_id="tenant-a", output_id=output_id
        )
        return output_id, output_root

    def expire_collection_lease(self, output_id: str) -> None:
        with self.service.lifecycle_store._connect() as connection:
            updated = connection.execute(
                "UPDATE lifecycle_outputs SET collection_lease_until = ? "
                "WHERE tenant_id = ? AND project_id = ? AND output_id = ? "
                "AND state = 'collecting'",
                ("1970-01-01T00:00:00Z", "tenant-a", "project-a", output_id),
            )
        self.assertEqual(updated.rowcount, 1)

    def test_pure_38_39_contracts_require_the_trusted_binder(self) -> None:
        runtime_context = {
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "actor_id": "actor-qa-publisher",
            "request_id": "request-pure-contract",
            "idempotency_key": "pure-contract-key",
        }
        publishing = publishing_operation_contract(
            {
                "session_id": "delivery-session-1",
                "_runtime_context": runtime_context,
            }
        )
        self.assertEqual(publishing["state"], "BLOCKED")
        self.assertEqual(publishing["code"], "TRUSTED_DELIVERY_BINDER_REQUIRED")
        self.assertEqual(
            publishing["outputs"]["external_adapter"],
            "EXTERNAL_ADAPTER_REQUIRED",
        )
        lifecycle = lifecycle_operation_contract(
            {
                "action": "collect",
                "dry_run": True,
                "_runtime_context": runtime_context,
            }
        )
        self.assertEqual(lifecycle["state"], "BLOCKED")
        self.assertEqual(lifecycle["outputs"]["action"], "collect")
        with self.assertRaises(DeliveryContractError):
            publishing_operation_contract(
                {
                    "session_id": "delivery-session-1",
                    "publication_root": str(self.root / "caller-root"),
                    "_runtime_context": runtime_context,
                }
            )
        with self.assertRaises(DeliveryContractError):
            lifecycle_operation_contract(
                {
                    "action": "collect",
                    "dry_run": True,
                    "tenant_id": "caller-tenant",
                    "_runtime_context": runtime_context,
                }
            )

    def test_runtime_binders_stage_publish_and_register_skill37_output(self) -> None:
        materialization_inputs = {
            "suite_id": "suite-trusted-delivery",
            "adapter_key": "python",
            "test_cases": [self.dsl_case()],
            "fixture_records": [],
            "mock_records": [],
            "synthetic_data_records": [],
            "config": {"runtime_profile": "isolated-local"},
            "revision_id": "revision-runtime-binder",
            "run_id": "run-runtime-binder",
            "run_mode": "generate",
            "output_mode": "sidecar",
            "source_snapshot_digest": "7" * 64,
        }
        materialized = self.service.execute_materialization(
            self.runtime_request(
                materialization_inputs,
                request_id="request-materialize",
                idempotency_key="runtime-materialize-key",
            )
        )
        self.assertEqual(materialized["state"], "PARTIAL")
        self.assertEqual(
            materialized["code"],
            "TEST_SOURCES_STAGED_NATIVE_VALIDATION_REQUIRED",
        )
        self.assertEqual(materialized["outputs"]["native_parser"], "NOT_RUN")
        self.assertEqual(materialized["outputs"]["native_build"], "NOT_RUN")
        self.assertEqual(materialized["outputs"]["native_smoke"], "NOT_RUN")
        self.assertGreaterEqual(materialized["outputs"]["skill37_artifact_count"], 2)
        session_id = str(materialized["outputs"]["session_id"])
        emission_digest = str(materialized["outputs"]["skill37_emission_digest"])
        staged_row = self.service._session_row(
            tenant_id="tenant-a",
            project_id="project-a",
            session_id=session_id,
        )
        plan_document = self.service._plan_document_from_row(staged_row)
        manifest = self.service._document(
            staged_row["artifact_manifest_json"],
            staged_row["artifact_manifest_digest"],
            "test artifact manifest",
        )
        self.assertEqual(plan_document["skill37_emission_digest"], emission_digest)
        self.assertEqual(manifest["skill37_emission_digest"], emission_digest)
        materialization_authorization_digest = plan_document[
            "authorization_context"
        ]["authorization_digest"]
        self.assertIn(
            f"elmos-qa/provenance/skill37-{emission_digest[:24]}.json",
            {artifact["path"] for artifact in manifest["artifacts"]},
        )

        published = self.service.execute_publishing(
            self.runtime_request(
                {"session_id": session_id},
                request_id="request-publish",
                idempotency_key="runtime-publish-key",
            )
        )
        self.assertEqual(published["state"], "SUCCEEDED")
        self.assertEqual(published["outputs"]["signing"], "NOT_RUN")
        published_row = self.service._session_row(
            tenant_id="tenant-a",
            project_id="project-a",
            session_id=session_id,
        )
        published_document = self.service._document(
            published_row["published_output_json"],
            published_row["published_output_digest"],
            "test published output",
        )
        self.assertEqual(
            published_document["skill37_emission_digest"], emission_digest
        )
        publication_authorization_digest = published_document[
            "publication_authorization_context"
        ]["authorization_digest"]
        published_materialization_context = published_document[
            "materialization_authorization_context"
        ]
        self.assertEqual(
            published_materialization_context["authorization_digest"],
            materialization_authorization_digest,
        )
        self.assertNotEqual(
            publication_authorization_digest,
            materialization_authorization_digest,
        )
        self.assertEqual(
            published["outputs"]["publication_authorization_digest"],
            publication_authorization_digest,
        )
        self.assertEqual(
            published["outputs"]["materialization_authorization_digest"],
            materialization_authorization_digest,
        )
        registered = self.service.execute_lifecycle(
            self.runtime_request(
                {"action": "register", "session_id": session_id},
                request_id="request-register",
                idempotency_key="runtime-register-key",
            )
        )
        self.assertEqual(registered["state"], "SUCCEEDED")
        self.assertTrue(registered["outputs"]["lifecycle_registered"])
        self.assertEqual(
            registered["outputs"]["skill37_emission_digest"], emission_digest
        )

    def test_runtime_binders_reject_caller_identity_and_path_controls(self) -> None:
        base = {
            "suite_id": "suite-no-caller-path",
            "adapter_key": "python",
            "test_cases": [self.dsl_case()],
            "revision_id": "revision-no-caller-path",
            "run_id": "run-no-caller-path",
            "run_mode": "generate",
            "output_mode": "sidecar",
            "source_snapshot_digest": "8" * 64,
        }
        for field, value in (
            ("native_root", "caller/tests"),
            ("existing_paths", []),
            ("staging_root", str(self.root / "caller-staging")),
            ("tenant_id", "tenant-caller"),
            ("idempotency_key", "caller-key"),
            ("_runtime_context", {}),
        ):
            with self.subTest(field=field):
                with self.assertRaises(DeliveryContractError):
                    self.service.execute_materialization(
                        self.runtime_request(
                            {**base, field: value},
                            request_id=f"request-reject-{field.replace('_', '-')}",
                            idempotency_key=f"reject-{field}",
                        )
                    )
        with self.assertRaises(DeliveryContractError):
            self.service.execute_materialization(
                self.runtime_request(
                    {**base, "output_mode": "embedded"},
                    request_id="request-reject-embedded-binder",
                    idempotency_key="reject-embedded-binder",
                )
            )
        with self.assertRaises(DeliveryContractError):
            self.service.execute_publishing(
                self.runtime_request(
                    {
                        "session_id": "delivery-session-1",
                        "publication_root": str(self.root / "caller-publication"),
                    },
                    request_id="request-reject-publish-root",
                    idempotency_key="reject-publish-root",
                )
            )
        with self.assertRaises(DeliveryContractError):
            self.service.execute_lifecycle(
                self.runtime_request(
                    {
                        "action": "collect",
                        "dry_run": True,
                        "project_id": "project-caller",
                    },
                    request_id="request-reject-lifecycle-project",
                    idempotency_key="reject-lifecycle-project",
                )
            )

    def test_materialization_rejects_tampered_skill37_content_envelope(self) -> None:
        inputs = {
            "suite_id": "suite-tampered-emission",
            "adapter_key": "python",
            "test_cases": [self.dsl_case()],
            "revision_id": "revision-tampered-emission",
            "run_id": "run-tampered-emission",
            "run_mode": "generate",
            "output_mode": "sidecar",
            "source_snapshot_digest": "9" * 64,
        }
        original = delivery_service_module.delivery_skills.emit_test_sources

        def tampered_emitter(
            emitter_inputs: dict[str, object],
        ) -> dict[str, object]:
            emitted = dict(original(emitter_inputs))
            outputs = dict(emitted["outputs"])
            artifacts = [dict(artifact) for artifact in outputs["artifacts"]]
            artifacts[0]["sha256"] = "sha256:" + "0" * 64
            outputs["artifacts"] = artifacts
            emitted["outputs"] = outputs
            return emitted

        with mock.patch.object(
            delivery_service_module.delivery_skills,
            "emit_test_sources",
            side_effect=tampered_emitter,
        ):
            with self.assertRaises(DeliveryStateError):
                self.service.execute_materialization(
                    self.runtime_request(
                        inputs,
                        request_id="request-tampered-emission",
                        idempotency_key="tampered-emission-key",
                    )
                )
        self.assertEqual(list(self.staging.glob("stage-*")), [])

    def test_skill37_full_contract_is_exact_and_order_independent(self) -> None:
        emitter_inputs = {
            "suite_id": "suite-contract-audit",
            "adapter_key": "python",
            "test_cases": [self.dsl_case()],
            "fixture_records": [],
            "mock_records": [],
            "synthetic_data_records": [],
            "config": {"runtime_profile": "isolated-local"},
            "_runtime_context": {
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "actor_id": "actor-qa-publisher",
                "request_id": "request-contract-audit",
                "idempotency_key": "contract-audit-key",
            },
        }
        emission = delivery_service_module.delivery_skills.emit_test_sources(
            emitter_inputs
        )
        _artifacts, expected_digest = self.service._emitted_artifacts(
            emission,
            suite_id="suite-contract-audit",
            adapter_key="python",
            tenant_id="tenant-a",
            project_id="project-a",
            request_id="request-contract-audit",
        )
        for label, mutate in (
            (
                "schema",
                lambda value: value["outputs"].__setitem__(
                    "contract_schema_version", "tampered"
                ),
            ),
            (
                "diff",
                lambda value: value["outputs"]["artifacts"][0].__setitem__(
                    "diff", "tampered"
                ),
            ),
            (
                "manifest",
                lambda value: value["outputs"]["manifest_draft"].__setitem__(
                    "draft_digest", "sha256:" + "0" * 64
                ),
            ),
        ):
            with self.subTest(label=label):
                tampered = copy.deepcopy(emission)
                mutate(tampered)
                with self.assertRaises(DeliveryStateError):
                    self.service._emitted_artifacts(
                        tampered,
                        suite_id="suite-contract-audit",
                        adapter_key="python",
                        tenant_id="tenant-a",
                        project_id="project-a",
                        request_id="request-contract-audit",
                    )
        reordered = copy.deepcopy(emission)
        reordered["outputs"]["artifacts"].reverse()
        reordered["outputs"]["manifest_draft"]["files"].reverse()
        reordered_manifest = reordered["outputs"]["manifest_draft"]
        reordered_manifest_body = {
            key: value
            for key, value in reordered_manifest.items()
            if key != "draft_digest"
        }
        reordered_manifest["draft_digest"] = (
            "sha256:" + artifact_module.canonical_digest(reordered_manifest_body)
        )
        _reordered_artifacts, reordered_digest = self.service._emitted_artifacts(
            reordered,
            suite_id="suite-contract-audit",
            adapter_key="python",
            tenant_id="tenant-a",
            project_id="project-a",
            request_id="request-contract-audit",
        )
        self.assertEqual(reordered_digest, expected_digest)

    def test_stage_publish_restart_and_idempotency_are_durable(self) -> None:
        request = self.stage_request()
        first = self.service.stage(request)
        self.assertEqual(first["state"], "SUCCEEDED")
        self.assertEqual(first["outputs"]["stage_durability_status"], "DURABLE")
        self.assertEqual(first["outputs"]["object_upload"], "NOT_RUN")
        self.assertEqual(first["outputs"]["signing"], "NOT_RUN")
        self.assertEqual(first["outputs"]["external_evidence"], "NOT_RUN")
        self.assertEqual(first["outputs"]["certification"], "NOT_CERTIFIED")
        self.assertFalse(first["outputs"]["caller_paths_accepted"])

        session_id = str(first["outputs"]["session_id"])
        row = self.service._session_row(
            tenant_id="tenant-a", project_id="project-a", session_id=session_id
        )
        plan = self.service._plan_from_row(row)
        staged_file = plan.staging_root / "tests" / "test_value.py"
        self.assertEqual(stat.S_IMODE(plan.staging_root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(staged_file.stat().st_mode), 0o600)
        self.assertEqual(self.service.stage(request), first)

        restarted = TrustedDeliveryService(**self.configuration)
        self.assertEqual(restarted.stage(request), first)
        publish_request = self.publish_request(session_id)
        published = restarted.publish(publish_request)
        self.assertEqual(published["state"], "SUCCEEDED")
        self.assertEqual(published["code"], "OUTPUT_PUBLISHED")
        self.assertEqual(published["outputs"]["durability_status"], "DURABLE")
        self.assertTrue(plan.final_root.is_dir())
        self.assertTrue(
            (plan.final_root / "manifests" / "project-output-manifest.json").is_file()
        )
        self.assertTrue(
            (
                plan.final_root
                / "bundles"
                / f"{plan.output_id}-tests-only.zip"
            ).is_file()
        )
        self.assertEqual(restarted.publish(publish_request), published)

        with restarted._connect() as connection:
            version = connection.execute(
                "SELECT version FROM delivery_sessions WHERE tenant_id = ? "
                "AND project_id = ? AND session_id = ?",
                ("tenant-a", "project-a", session_id),
            ).fetchone()[0]
        self.assertEqual(version, 3)

    def test_idempotency_rejects_changed_input(self) -> None:
        self.service.stage(self.stage_request(idempotency_key="stable-key"))
        with self.assertRaises(DeliveryStateError):
            self.service.stage(
                self.stage_request(
                    idempotency_key="stable-key",
                    source=b"def test_value():\n    assert False\n",
                )
            )

    def test_caller_paths_unsafe_paths_and_non_utf8_are_rejected(self) -> None:
        caller_path = self.stage_request(idempotency_key="caller-path")
        caller_path["publication_root"] = self.root / "caller-selected"
        with self.assertRaises(DeliveryContractError):
            self.service.stage(caller_path)

        traversal = self.stage_request(idempotency_key="traversal")
        traversal_artifact = dict(traversal["artifacts"][0])
        traversal_artifact["path"] = "../escape.py"
        traversal["artifacts"] = [traversal_artifact]
        with self.assertRaises(DeliveryContractError):
            self.service.stage(traversal)

        invalid_utf8 = self.stage_request(idempotency_key="invalid-utf8")
        invalid_artifact = dict(invalid_utf8["artifacts"][0])
        invalid_artifact["source_bytes"] = b"\xff\xfe"
        invalid_utf8["artifacts"] = [invalid_artifact]
        with self.assertRaises(DeliveryContractError):
            self.service.stage(invalid_utf8)

        with self.assertRaises(DeliveryContractError):
            TrustedDeliveryService(
                **{
                    **self.configuration,
                    "database_path": self.root / "caller-selected.sqlite3",
                }
            )

    def test_tenant_project_session_isolation_fails_closed(self) -> None:
        staged = self.service.stage(self.stage_request())
        session_id = str(staged["outputs"]["session_id"])
        with self.assertRaises(DeliveryAuthorizationError):
            self.service.publish(
                self.publish_request(
                    session_id,
                    project_id="project-b",
                    idempotency_key="cross-project-publish",
                )
            )
        with self.assertRaises(DeliveryAuthorizationError):
            self.service.publish(
                {
                    **self.publish_request(
                        session_id, idempotency_key="unknown-tenant"
                    ),
                    "tenant_id": "tenant-unknown",
                }
            )

    def test_staged_tamper_blocks_publication(self) -> None:
        staged = self.service.stage(self.stage_request())
        session_id = str(staged["outputs"]["session_id"])
        row = self.service._session_row(
            tenant_id="tenant-a", project_id="project-a", session_id=session_id
        )
        plan = self.service._plan_from_row(row)
        (plan.staging_root / "tests" / "test_value.py").write_bytes(
            b"def test_value():\n    assert False\n"
        )
        result = self.service.publish(self.publish_request(session_id))
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["code"], "STAGED_ARTIFACT_VERIFICATION_FAILED")
        self.assertFalse(plan.final_root.exists())

    def test_published_tamper_blocks_lifecycle_registration(self) -> None:
        session_id, _output_id, final_root = self.stage_and_publish(
            suffix="published-tamper",
            revision_id="revision-published-tamper",
            source_snapshot_digest="5" * 64,
        )
        manifest = final_root / "manifests" / "project-output-manifest.json"
        manifest.write_bytes(b"{}\n")
        with self.assertRaises(DeliveryStateError):
            self.service.publish(
                self.publish_request(
                    session_id,
                    idempotency_key="publish-after-published-tamper",
                )
            )
        result = self.register(session_id, "published-tamper")
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["code"], "LIFECYCLE_STATE_INVALID")
        self.assertEqual(result["outputs"]["mutation_outcome"], "UNKNOWN")
        self.assertFalse(result["outputs"]["receipt_persisted"])
        with self.service._connect() as connection:
            receipt_count = connection.execute(
                "SELECT COUNT(*) FROM delivery_receipts WHERE tenant_id = ? "
                "AND project_id = ? AND operation = ? AND idempotency_key = ?",
                (
                    "tenant-a",
                    "project-a",
                    "lifecycle:register",
                    "lifecycle-register-published-tamper",
                ),
            ).fetchone()[0]
        self.assertEqual(receipt_count, 0)
        with self.service.lifecycle_store._connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM lifecycle_outputs"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_existing_output_is_never_overwritten(self) -> None:
        first = self.service.stage(self.stage_request(idempotency_key="stage-first"))
        first_session = str(first["outputs"]["session_id"])
        first_published = self.service.publish(
            self.publish_request(first_session, idempotency_key="publish-first")
        )
        self.assertEqual(first_published["state"], "SUCCEEDED")
        first_row = self.service._session_row(
            tenant_id="tenant-a",
            project_id="project-a",
            session_id=first_session,
        )
        final_root = self.service._plan_from_row(first_row).final_root
        manifest_path = final_root / "manifests" / "project-output-manifest.json"
        original_manifest = manifest_path.read_bytes()

        second = self.service.stage(
            self.stage_request(
                idempotency_key="stage-second",
                source=b"def test_value():\n    assert 5 == 5\n",
            )
        )
        self.assertEqual(first["outputs"]["output_id"], second["outputs"]["output_id"])
        second_result = self.service.publish(
            self.publish_request(
                str(second["outputs"]["session_id"]),
                idempotency_key="publish-second",
            )
        )
        self.assertEqual(second_result["state"], "BLOCKED")
        self.assertEqual(second_result["code"], "IMMUTABLE_OUTPUT_ALREADY_EXISTS")
        self.assertFalse(second_result["outputs"]["overwrite_performed"])
        self.assertEqual(manifest_path.read_bytes(), original_manifest)

    def test_embedded_delivery_uses_only_admin_scope_mapping(self) -> None:
        source = b"def test_value():\n    assert 7 == 7\n"
        staged = self.service.stage(
            self.stage_request(
                idempotency_key="stage-embedded-b",
                revision_id="revision-embedded-b",
                run_id="run-embedded-b",
                project_id="project-b",
                source_snapshot_digest="6" * 64,
                source=source,
                output_mode="embedded",
            )
        )
        published = self.service.publish(
            self.publish_request(
                str(staged["outputs"]["session_id"]),
                idempotency_key="publish-embedded-b",
                project_id="project-b",
            )
        )
        self.assertEqual(published["state"], "SUCCEEDED")
        self.assertFalse(published["outputs"]["atomic_publish"])
        self.assertFalse(published["outputs"]["embedded_materialization_atomic"])
        self.assertEqual(
            (self.embedded_b / "tests" / "test_value.py").read_bytes(), source
        )
        self.assertFalse((self.embedded_a / "tests" / "test_value.py").exists())
        (self.embedded_b / "tests" / "test_value.py").write_bytes(
            b"def test_value():\n    assert 8 == 8\n"
        )
        with self.assertRaises(DeliveryStateError):
            self.service.publish(
                self.publish_request(
                    str(staged["outputs"]["session_id"]),
                    idempotency_key="publish-embedded-b-replay",
                    project_id="project-b",
                )
            )

    def test_embedded_collection_does_not_assert_unverified_worktree_retention(
        self,
    ) -> None:
        source = b"def test_retained_value():\n    assert 9 == 9\n"
        staged = self.service.stage(
            self.stage_request(
                idempotency_key="stage-embedded-retention",
                revision_id="revision-embedded-retention",
                run_id="run-embedded-retention",
                project_id="project-b",
                source_snapshot_digest="a" * 64,
                source=source,
                output_mode="embedded",
            )
        )
        session_id = str(staged["outputs"]["session_id"])
        output_id = str(staged["outputs"]["output_id"])
        self.service.publish(
            self.publish_request(
                session_id,
                idempotency_key="publish-embedded-retention",
                project_id="project-b",
            )
        )
        self.service.lifecycle(
            self.lifecycle_request(
                "register",
                "register-embedded-retention",
                project_id="project-b",
                session_id=session_id,
            )
        )
        self.service.lifecycle(
            self.lifecycle_request(
                "mark_stale",
                "stale-embedded-retention",
                project_id="project-b",
                output_id=output_id,
            )
        )
        collected = self.service.lifecycle(
            self.lifecycle_request(
                "collect",
                "collect-embedded-retention",
                project_id="project-b",
                dry_run=False,
            )
        )
        self.assertEqual(
            collected["outputs"]["retention_dispositions"],
            [
                {
                    "output_id": output_id,
                    "publication_copy": "COLLECTED",
                    "private_staging_copy": "RETAINED_PRIVATE",
                    "embedded_worktree_copy": "UNMANAGED_NOT_VERIFIED",
                }
            ],
        )
        self.assertEqual(
            (self.embedded_b / "tests" / "test_value.py").read_bytes(), source
        )

    def test_unknown_publication_durability_cannot_enter_lifecycle_or_gc(self) -> None:
        staged = self.service.stage(self.stage_request())
        session_id = str(staged["outputs"]["session_id"])
        original_rename = artifact_module._rename_no_replace

        def committed_but_unknown(*args: object, **kwargs: object) -> bool:
            original_rename(*args, **kwargs)
            return False

        with mock.patch.object(
            artifact_module,
            "_rename_no_replace",
            side_effect=committed_but_unknown,
        ):
            published = self.service.publish(self.publish_request(session_id))

        self.assertEqual(published["state"], "PARTIAL")
        self.assertEqual(published["code"], "PUBLICATION_DURABILITY_UNKNOWN")
        self.assertEqual(
            published["outputs"]["durability_status"],
            "COMMITTED_DURABILITY_UNKNOWN",
        )
        registration = self.register(session_id, "unknown")
        self.assertEqual(registration["state"], "BLOCKED")
        self.assertEqual(
            registration["code"], "PUBLISHED_OUTPUT_DURABILITY_UNKNOWN"
        )
        candidates = self.service.lifecycle(
            self.lifecycle_request("candidates", "unknown-candidates")
        )
        self.assertEqual(candidates["outputs"]["gc_candidates"], [])
        collected = self.service.lifecycle(
            self.lifecycle_request("collect", "unknown-collect", dry_run=False)
        )
        self.assertEqual(collected["outputs"]["collected_output_ids"], [])
        with self.service.lifecycle_store._connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM lifecycle_outputs"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_post_commit_state_failure_is_recorded_as_unknown_not_failed(self) -> None:
        staged = self.service.stage(
            self.stage_request(idempotency_key="stage-post-commit")
        )
        session_id = str(staged["outputs"]["session_id"])
        row = self.service._session_row(
            tenant_id="tenant-a", project_id="project-a", session_id=session_id
        )
        final_root = self.service._plan_from_row(row).final_root
        with mock.patch.object(
            self.service,
            "_published_document",
            side_effect=DeliveryStateError("simulated state-write boundary"),
        ):
            with self.assertRaises(DeliveryStateError):
                self.service.publish(
                    self.publish_request(
                        session_id, idempotency_key="publish-post-commit"
                    )
                )
        self.assertTrue(final_root.exists())
        interrupted = self.service._session_row(
            tenant_id="tenant-a", project_id="project-a", session_id=session_id
        )
        self.assertEqual(interrupted["status"], "PUBLISHING")
        result = self.service.publish(
            self.publish_request(
                session_id, idempotency_key="publish-post-commit-reconcile"
            )
        )
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["code"], "PUBLICATION_OUTCOME_UNKNOWN")
        self.assertEqual(result["outputs"]["durability_status"], "UNKNOWN")
        persisted = self.service._session_row(
            tenant_id="tenant-a", project_id="project-a", session_id=session_id
        )
        self.assertEqual(persisted["status"], "DURABILITY_UNKNOWN")
        self.assertIsNone(persisted["published_output_json"])
        blocked = self.register(session_id, "post-commit")
        self.assertEqual(blocked["code"], "PUBLICATION_OUTCOME_UNKNOWN")

    def test_lifecycle_actions_are_project_scoped_restart_safe_and_collect(self) -> None:
        old_session, old_output, old_root = self.stage_and_publish(
            suffix="old",
            revision_id="revision-old",
            source_snapshot_digest="1" * 64,
        )
        new_session, new_output, new_root = self.stage_and_publish(
            suffix="new",
            revision_id="revision-new",
            source_snapshot_digest="2" * 64,
        )
        self.assertEqual(self.register(old_session, "old")["state"], "SUCCEEDED")
        self.assertEqual(self.register(new_session, "new")["state"], "SUCCEEDED")

        restarted = TrustedDeliveryService(**self.configuration)
        superseded = restarted.lifecycle(
            self.lifecycle_request(
                "supersede",
                "supersede-old",
                old_output_id=old_output,
                new_output_id=new_output,
            )
        )
        self.assertEqual(superseded["state"], "SUCCEEDED")
        candidates = restarted.lifecycle(
            self.lifecycle_request("candidates", "candidate-old")
        )
        self.assertEqual(candidates["outputs"]["gc_candidates"], [old_output])

        restarted.lifecycle(
            self.lifecycle_request(
                "reference",
                "reference-add",
                output_id=old_output,
                reference_id="release-reference-1",
                present=True,
            )
        )
        referenced = restarted.lifecycle(
            self.lifecycle_request("candidates", "candidate-referenced")
        )
        self.assertEqual(referenced["outputs"]["gc_candidates"], [])
        restarted.lifecycle(
            self.lifecycle_request(
                "reference",
                "reference-remove",
                output_id=old_output,
                reference_id="release-reference-1",
                present=False,
            )
        )
        restarted.lifecycle(
            self.lifecycle_request(
                "legal_hold",
                "hold-enable",
                output_id=old_output,
                enabled=True,
            )
        )
        held = restarted.lifecycle(
            self.lifecycle_request("candidates", "candidate-held")
        )
        self.assertEqual(held["outputs"]["gc_candidates"], [])
        restarted.lifecycle(
            self.lifecycle_request(
                "legal_hold",
                "hold-disable",
                output_id=old_output,
                enabled=False,
            )
        )
        dry_run = restarted.lifecycle(
            self.lifecycle_request("collect", "collect-dry", dry_run=True)
        )
        self.assertEqual(dry_run["outputs"]["collected_output_ids"], [])
        self.assertEqual(dry_run["outputs"]["gc_candidates"], [old_output])
        self.assertTrue(old_root.exists())
        collected = restarted.lifecycle(
            self.lifecycle_request("collect", "collect-old", dry_run=False)
        )
        self.assertEqual(collected["outputs"]["collected_output_ids"], [old_output])
        self.assertEqual(
            collected["outputs"]["deletion_scope"],
            "MANAGED_PUBLICATION_COPY_ONLY",
        )
        self.assertEqual(
            collected["outputs"]["retention_dispositions"],
            [
                {
                    "output_id": old_output,
                    "publication_copy": "COLLECTED",
                    "private_staging_copy": "RETAINED_PRIVATE",
                    "embedded_worktree_copy": "NOT_APPLICABLE",
                }
            ],
        )
        self.assertFalse(old_root.exists())
        self.assertTrue(new_root.exists())
        reregister = restarted.lifecycle(
            self.lifecycle_request(
                "register",
                "register-old-after-gc",
                session_id=old_session,
            )
        )
        self.assertEqual(reregister["state"], "BLOCKED")
        self.assertEqual(reregister["code"], "OUTPUT_COLLECTED")

        replay_stage = restarted.stage(
            self.stage_request(
                idempotency_key="stage-old-after-gc",
                revision_id="revision-old",
                run_id="run-old",
                source_snapshot_digest="1" * 64,
            )
        )
        replay_publish = restarted.publish(
            self.publish_request(
                str(replay_stage["outputs"]["session_id"]),
                idempotency_key="publish-old-after-gc",
            )
        )
        self.assertEqual(replay_publish["state"], "BLOCKED")
        self.assertEqual(
            replay_publish["code"], "OUTPUT_COLLECTED"
        )
        self.assertFalse(replay_publish["outputs"]["lifecycle_registered"])
        self.assertFalse(old_root.exists())

        stale = restarted.lifecycle(
            self.lifecycle_request(
                "mark_stale", "stale-new", output_id=new_output
            )
        )
        self.assertEqual(stale["outputs"]["lifecycle_state"], "stale")
        recovered = restarted.lifecycle(
            self.lifecycle_request("recover", "recover-none")
        )
        self.assertEqual(recovered["outputs"]["recovered_output_ids"], [])
        replay = restarted.lifecycle(
            self.lifecycle_request(
                "mark_stale", "stale-new", output_id=new_output
            )
        )
        self.assertEqual(replay, stale)
        self.assertEqual(replay["outputs"]["external_evidence"], "NOT_RUN")

    def test_collect_replays_exact_intent_after_effect_before_receipt(self) -> None:
        session_id, output_id, output_root = self.stage_and_publish(
            suffix="intent-effect",
            revision_id="revision-intent-effect",
            source_snapshot_digest="c" * 64,
        )
        self.assertEqual(self.register(session_id, "intent-effect")["state"], "SUCCEEDED")
        self.service.lifecycle(
            self.lifecycle_request(
                "mark_stale", "stale-intent-effect", output_id=output_id
            )
        )
        request = self.lifecycle_request(
            "collect", "collect-intent-effect", dry_run=False
        )
        with mock.patch.object(
            self.service,
            "_store_receipt",
            side_effect=sqlite3.OperationalError("simulated receipt write crash"),
        ):
            interrupted = self.service.lifecycle(request)

        self.assertEqual(interrupted["state"], "BLOCKED")
        self.assertEqual(interrupted["outputs"]["mutation_outcome"], "UNKNOWN")
        self.assertFalse(output_root.exists())
        pending = self.service._lifecycle_intent(
            tenant_id="tenant-a",
            project_id="project-a",
            action="collect",
            idempotency_key="collect-intent-effect",
        )
        self.assertIsNotNone(pending)
        assert pending is not None
        self.assertEqual(pending.status, "PENDING")
        self.assertEqual(pending.candidate_output_ids, (output_id,))
        with self.service._connect() as connection:
            receipt_count = connection.execute(
                "SELECT COUNT(*) FROM delivery_receipts WHERE tenant_id = ? "
                "AND project_id = ? AND operation = ? AND idempotency_key = ?",
                (
                    "tenant-a",
                    "project-a",
                    "lifecycle:collect",
                    "collect-intent-effect",
                ),
            ).fetchone()[0]
        self.assertEqual(receipt_count, 0)
        changed_authorization = dict(request)
        changed_authorization["authorization_context"] = (
            self.service._runtime_authorization(
                self.runtime_request(
                    {"action": "collect", "dry_run": False},
                    request_id="request-intent-auth-conflict",
                    idempotency_key="unused-runtime-key",
                ),
                action="lifecycle:collect",
            )
        )
        conflict = self.service.lifecycle(changed_authorization)
        self.assertEqual(conflict["state"], "BLOCKED")
        self.assertEqual(conflict["code"], "LIFECYCLE_STATE_INVALID")

        restarted = TrustedDeliveryService(**self.configuration)
        resumed = restarted.lifecycle(request)
        self.assertEqual(resumed["state"], "SUCCEEDED")
        self.assertEqual(resumed["outputs"]["gc_candidates"], [output_id])
        self.assertEqual(resumed["outputs"]["collected_output_ids"], [output_id])
        finalized = restarted._lifecycle_intent(
            tenant_id="tenant-a",
            project_id="project-a",
            action="collect",
            idempotency_key="collect-intent-effect",
        )
        self.assertIsNotNone(finalized)
        assert finalized is not None
        self.assertEqual(finalized.status, "FINALIZED")
        self.assertEqual(restarted.lifecycle(request), resumed)

    def test_empty_collect_intent_never_reselects_later_candidates(self) -> None:
        request = self.lifecycle_request(
            "collect", "collect-empty-intent", dry_run=False
        )
        empty = self.service.lifecycle(request)
        self.assertEqual(empty["state"], "SUCCEEDED")
        self.assertEqual(empty["outputs"]["gc_candidates"], [])
        self.assertEqual(empty["outputs"]["collected_output_ids"], [])

        session_id, output_id, output_root = self.stage_and_publish(
            suffix="after-empty-intent",
            revision_id="revision-after-empty-intent",
            source_snapshot_digest="0" * 64,
        )
        self.assertEqual(
            self.register(session_id, "after-empty-intent")["state"], "SUCCEEDED"
        )
        self.service.lifecycle(
            self.lifecycle_request(
                "mark_stale", "stale-after-empty-intent", output_id=output_id
            )
        )

        self.assertEqual(self.service.lifecycle(request), empty)
        self.assertTrue(output_root.exists())
        candidates = self.service.lifecycle(
            self.lifecycle_request("candidates", "candidates-after-empty-intent")
        )
        self.assertEqual(candidates["outputs"]["gc_candidates"], [output_id])

    def test_collect_reconciles_lifecycle_tombstone_before_delivery_sync(self) -> None:
        session_id, output_id, output_root = self.stage_and_publish(
            suffix="intent-sync",
            revision_id="revision-intent-sync",
            source_snapshot_digest="d" * 64,
        )
        self.assertEqual(self.register(session_id, "intent-sync")["state"], "SUCCEEDED")
        self.service.lifecycle(
            self.lifecycle_request(
                "mark_stale", "stale-intent-sync", output_id=output_id
            )
        )
        request = self.lifecycle_request(
            "collect", "collect-intent-sync", dry_run=False
        )
        with mock.patch.object(
            self.service,
            "_sync_collected_sessions",
            side_effect=DeliveryStateError("simulated crash before delivery sync"),
        ):
            interrupted = self.service.lifecycle(request)

        self.assertEqual(interrupted["state"], "BLOCKED")
        self.assertFalse(output_root.exists())
        with self.service.lifecycle_store._connect() as connection:
            lifecycle_state = connection.execute(
                "SELECT state FROM lifecycle_outputs WHERE tenant_id = ? "
                "AND project_id = ? AND output_id = ?",
                ("tenant-a", "project-a", output_id),
            ).fetchone()[0]
        self.assertEqual(lifecycle_state, "collected")
        delivery_row = self.service._session_row(
            tenant_id="tenant-a",
            project_id="project-a",
            session_id=session_id,
        )
        self.assertEqual(delivery_row["status"], "PUBLISHED")

        restarted = TrustedDeliveryService(**self.configuration)
        resumed = restarted.lifecycle(request)
        self.assertEqual(resumed["state"], "SUCCEEDED")
        self.assertEqual(resumed["outputs"]["collected_output_ids"], [output_id])
        reconciled = restarted._session_row(
            tenant_id="tenant-a",
            project_id="project-a",
            session_id=session_id,
        )
        self.assertEqual(reconciled["status"], "COLLECTED")

    def test_pending_collect_is_not_reselected_or_adopted_across_projects(self) -> None:
        session_a, output_a, root_a = self.stage_and_publish(
            suffix="pending-project-a",
            revision_id="revision-pending-project-a",
            source_snapshot_digest="e" * 64,
        )
        self.assertEqual(
            self.register(session_a, "pending-project-a")["state"], "SUCCEEDED"
        )
        staged_b = self.service.stage(
            self.stage_request(
                idempotency_key="stage-pending-project-b",
                revision_id="revision-pending-project-b",
                run_id="run-pending-project-b",
                project_id="project-b",
                source_snapshot_digest="f" * 64,
            )
        )
        session_b = str(staged_b["outputs"]["session_id"])
        output_b = str(staged_b["outputs"]["output_id"])
        self.assertEqual(
            self.service.publish(
                self.publish_request(
                    session_b,
                    idempotency_key="publish-pending-project-b",
                    project_id="project-b",
                )
            )["state"],
            "SUCCEEDED",
        )
        self.assertEqual(
            self.service.lifecycle(
                self.lifecycle_request(
                    "register",
                    "register-pending-project-b",
                    project_id="project-b",
                    session_id=session_b,
                )
            )["state"],
            "SUCCEEDED",
        )
        row_b = self.service._session_row(
            tenant_id="tenant-a", project_id="project-b", session_id=session_b
        )
        root_b = self.service._plan_from_row(row_b).final_root
        for project_id, output_id in (
            ("project-a", output_a),
            ("project-b", output_b),
        ):
            self.service.lifecycle(
                self.lifecycle_request(
                    "mark_stale",
                    f"stale-pending-{project_id}",
                    project_id=project_id,
                    output_id=output_id,
                )
            )

        request_a = self.lifecycle_request(
            "collect", "collect-pending-project-a", dry_run=False
        )
        with mock.patch.object(
            self.service,
            "_run_destructive_lifecycle_intent",
            side_effect=DeliveryStateError("simulated crash after intent commit"),
        ):
            interrupted = self.service.lifecycle(request_a)
        self.assertEqual(interrupted["state"], "BLOCKED")
        pending = self.service._lifecycle_intent(
            tenant_id="tenant-a",
            project_id="project-a",
            action="collect",
            idempotency_key="collect-pending-project-a",
        )
        self.assertIsNotNone(pending)
        assert pending is not None
        self.assertEqual(pending.candidate_output_ids, (output_a,))

        blocked = self.service.lifecycle(
            self.lifecycle_request("recover", "recover-cannot-adopt-pending")
        )
        self.assertEqual(blocked["code"], "LIFECYCLE_INTENT_PENDING")
        collected_b = self.service.lifecycle(
            self.lifecycle_request(
                "collect",
                "collect-pending-project-b",
                project_id="project-b",
                dry_run=False,
            )
        )
        self.assertEqual(collected_b["outputs"]["collected_output_ids"], [output_b])
        self.assertNotIn(output_a, collected_b["outputs"]["collected_output_ids"])
        self.assertTrue(root_a.exists())
        self.assertFalse(root_b.exists())

        resumed_a = self.service.lifecycle(request_a)
        self.assertEqual(resumed_a["outputs"]["gc_candidates"], [output_a])
        self.assertEqual(resumed_a["outputs"]["collected_output_ids"], [output_a])
        self.assertFalse(root_a.exists())

    def test_pending_collect_never_reselects_late_candidate_in_same_project(self) -> None:
        session_a, output_a, root_a = self.stage_and_publish(
            suffix="pending-exact-a",
            revision_id="revision-pending-exact-a",
            source_snapshot_digest="7" * 64,
        )
        session_b, output_b, root_b = self.stage_and_publish(
            suffix="pending-exact-b",
            revision_id="revision-pending-exact-b",
            source_snapshot_digest="8" * 64,
        )
        self.assertEqual(
            self.register(session_a, "pending-exact-a")["state"], "SUCCEEDED"
        )
        self.assertEqual(
            self.register(session_b, "pending-exact-b")["state"], "SUCCEEDED"
        )
        self.service.lifecycle(
            self.lifecycle_request(
                "mark_stale", "stale-pending-exact-a", output_id=output_a
            )
        )
        request = self.lifecycle_request(
            "collect", "collect-pending-exact", dry_run=False
        )
        with mock.patch.object(
            self.service,
            "_run_destructive_lifecycle_intent",
            side_effect=DeliveryStateError("simulated crash after exact intent commit"),
        ):
            interrupted = self.service.lifecycle(request)
        self.assertEqual(interrupted["state"], "BLOCKED")
        intent = self.service._lifecycle_intent(
            tenant_id="tenant-a",
            project_id="project-a",
            action="collect",
            idempotency_key="collect-pending-exact",
        )
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.status, "PENDING")
        self.assertEqual(intent.candidate_output_ids, (output_a,))

        # Make another output eligible only after the exact candidate set is durable.
        self.service.lifecycle_store.mark_stale(
            tenant_id="tenant-a", output_id=output_b
        )
        restarted = TrustedDeliveryService(**self.configuration)
        resumed = restarted.lifecycle(request)
        self.assertEqual(resumed["state"], "SUCCEEDED")
        self.assertEqual(resumed["outputs"]["gc_candidates"], [output_a])
        self.assertEqual(resumed["outputs"]["collected_output_ids"], [output_a])
        self.assertFalse(root_a.exists())
        self.assertTrue(root_b.exists())
        self.assertEqual(
            restarted.lifecycle_store.gc_candidates(
                tenant_id="tenant-a", project_id="project-a"
            ),
            (output_b,),
        )

    def test_lifecycle_registration_reconciles_store_first_crash_window(self) -> None:
        session_id, _output_id, _root = self.stage_and_publish(
            suffix="reconcile",
            revision_id="revision-reconcile",
            source_snapshot_digest="3" * 64,
        )
        row = self.service._session_row(
            tenant_id="tenant-a",
            project_id="project-a",
            session_id=session_id,
        )
        output = self.service._published_from_row(row)
        self.service.lifecycle_store.register_output(output)

        restarted = TrustedDeliveryService(**self.configuration)
        reconciled = restarted.lifecycle(
            self.lifecycle_request(
                "register", "register-reconcile", session_id=session_id
            )
        )
        self.assertEqual(reconciled["state"], "SUCCEEDED")
        with restarted._connect() as connection:
            registered, version = connection.execute(
                "SELECT lifecycle_registered, version FROM delivery_sessions "
                "WHERE tenant_id = ? AND project_id = ? AND session_id = ?",
                ("tenant-a", "project-a", session_id),
            ).fetchone()
        self.assertEqual(registered, 1)
        self.assertEqual(version, 4)

    def test_lifecycle_cross_project_output_is_not_disclosed(self) -> None:
        session_id, output_id, _root = self.stage_and_publish(
            suffix="scope",
            revision_id="revision-scope",
            source_snapshot_digest="4" * 64,
        )
        self.register(session_id, "scope")
        with self.assertRaises(DeliveryAuthorizationError):
            self.service.lifecycle(
                self.lifecycle_request(
                    "mark_stale",
                    "cross-project-stale",
                    project_id="project-b",
                    output_id=output_id,
                )
            )

    def test_recover_active_lease_stays_pending_until_exact_candidate_is_claimable(self) -> None:
        session_id, output_id, output_root = self.stage_and_publish(
            suffix="recover-active-lease",
            revision_id="revision-recover-active-lease",
            source_snapshot_digest="6" * 64,
        )
        self.assertEqual(
            self.register(session_id, "recover-active-lease")["state"],
            "SUCCEEDED",
        )
        self.service.lifecycle(
            self.lifecycle_request(
                "mark_stale", "stale-recover-active-lease", output_id=output_id
            )
        )
        with self.service.lifecycle_store._connect() as connection:
            row = connection.execute(
                "SELECT manifest_digest FROM lifecycle_outputs WHERE tenant_id = ? "
                "AND project_id = ? AND output_id = ?",
                ("tenant-a", "project-a", output_id),
            ).fetchone()
            quarantine_path = self.service.lifecycle_store._quarantine_path(
                tenant_id="tenant-a",
                output_id=output_id,
                manifest_digest=str(row["manifest_digest"]),
            )
            updated = connection.execute(
                "UPDATE lifecycle_outputs SET state = 'collecting', "
                "collecting_from = 'stale', quarantine_path = ?, "
                "quarantine_verified = 0, quarantine_snapshot = NULL, "
                "quarantine_snapshot_digest = NULL, collection_owner = ?, "
                "collection_lease_until = ?, collection_phase = 'prepared' "
                "WHERE tenant_id = ? AND project_id = ? AND output_id = ? "
                "AND state = 'stale'",
                (
                    str(quarantine_path),
                    "gc-operation-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "2999-01-01T00:00:00Z",
                    "tenant-a",
                    "project-a",
                    output_id,
                ),
            )
        self.assertEqual(updated.rowcount, 1)
        request = self.lifecycle_request("recover", "recover-active-lease")
        blocked = self.service.lifecycle(request)
        self.assertEqual(blocked["state"], "BLOCKED")
        self.assertEqual(blocked["outputs"]["mutation_outcome"], "UNKNOWN")
        pending = self.service._lifecycle_intent(
            tenant_id="tenant-a",
            project_id="project-a",
            action="recover",
            idempotency_key="recover-active-lease",
        )
        self.assertIsNotNone(pending)
        assert pending is not None
        self.assertEqual(pending.status, "PENDING")
        self.assertEqual(pending.candidate_output_ids, (output_id,))
        self.assertTrue(output_root.exists())

        with self.service.lifecycle_store._connect() as connection:
            connection.execute(
                "UPDATE lifecycle_outputs SET collection_lease_until = ? "
                "WHERE tenant_id = ? AND project_id = ? AND output_id = ? "
                "AND state = 'collecting'",
                ("1970-01-01T00:00:00Z", "tenant-a", "project-a", output_id),
            )
        resumed = self.service.lifecycle(request)
        self.assertEqual(resumed["state"], "SUCCEEDED")
        self.assertEqual(resumed["outputs"]["recovered_output_ids"], [output_id])
        self.assertTrue(output_root.exists())

    def test_recover_commits_receipt_before_releasing_gc_fence(self) -> None:
        session_id, output_id, output_root = self.stage_and_publish(
            suffix="recover-fence-sync",
            revision_id="revision-recover-fence-sync",
            source_snapshot_digest="7" * 64,
        )
        self.assertEqual(
            self.register(session_id, "recover-fence-sync")["state"],
            "SUCCEEDED",
        )
        self.service.lifecycle(
            self.lifecycle_request(
                "mark_stale", "stale-recover-fence-sync", output_id=output_id
            )
        )
        with self.service.lifecycle_store._connect() as connection:
            row = connection.execute(
                "SELECT manifest_digest FROM lifecycle_outputs WHERE tenant_id = ? "
                "AND project_id = ? AND output_id = ?",
                ("tenant-a", "project-a", output_id),
            ).fetchone()
        quarantine_path = self.service.lifecycle_store._quarantine_path(
            tenant_id="tenant-a",
            output_id=output_id,
            manifest_digest=str(row["manifest_digest"]),
        )
        with self.service.lifecycle_store._connect() as connection:
            updated = connection.execute(
                "UPDATE lifecycle_outputs SET state = 'collecting', "
                "collecting_from = 'stale', quarantine_path = ?, "
                "quarantine_verified = 0, quarantine_snapshot = NULL, "
                "quarantine_snapshot_digest = NULL, collection_owner = ?, "
                "collection_lease_until = ?, collection_phase = 'prepared' "
                "WHERE tenant_id = ? AND project_id = ? AND output_id = ? "
                "AND state = 'stale'",
                (
                    str(quarantine_path),
                    "gc-operation-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    "1970-01-01T00:00:00Z",
                    "tenant-a",
                    "project-a",
                    output_id,
                ),
            )
        self.assertEqual(updated.rowcount, 1)

        external = artifact_module.ArtifactLifecycleStore(
            self.service.lifecycle_database_path,
            self.publication,
            auto_recover=False,
        )
        result_built = threading.Event()
        first_attempt_finished = threading.Event()
        receipt_committed = threading.Event()
        collector_entered = threading.Event()
        retry_pause = threading.Event()
        failures: list[BaseException] = []

        def contend_for_gc_fence() -> None:
            try:
                if not result_built.wait(timeout=5):
                    raise AssertionError("lifecycle result barrier was not reached")
                first = external._acquire_gc_fence()
                if first is not None:
                    external._release_gc_fence(first)
                    raise AssertionError("external collector entered before finalization")
                first_attempt_finished.set()
                for _attempt in range(500):
                    fence = external._acquire_gc_fence()
                    if fence is not None:
                        try:
                            if not receipt_committed.is_set():
                                raise AssertionError(
                                    "external collector entered before receipt commit"
                                )
                            collector_entered.set()
                        finally:
                            external._release_gc_fence(fence)
                        return
                    retry_pause.wait(timeout=0.01)
                raise AssertionError("external collector never acquired the released fence")
            except BaseException as exc:
                failures.append(exc)
                first_attempt_finished.set()

        real_result = self.service._destructive_lifecycle_result_under_gc_fence

        def synchronized_result(
            *,
            intent: delivery_service_module._LifecycleIntent,
            request: Mapping[str, object],
            fence: artifact_module._LifecycleFence,
        ) -> Mapping[str, object]:
            result = real_result(intent=intent, request=request, fence=fence)
            result_built.set()
            if not first_attempt_finished.wait(timeout=5):
                raise AssertionError("external collector did not contend for the fence")
            self.assertFalse(collector_entered.is_set())
            return result

        real_finalize = self.service._finalize_lifecycle_intent

        def observed_finalize(
            *,
            intent: delivery_service_module._LifecycleIntent,
            result: Mapping[str, object],
        ) -> None:
            real_finalize(intent=intent, result=result)
            receipt_committed.set()

        contender = threading.Thread(target=contend_for_gc_fence)
        contender.start()
        request = self.lifecycle_request("recover", "recover-fence-sync")
        with mock.patch.object(
            self.service,
            "_destructive_lifecycle_result_under_gc_fence",
            side_effect=synchronized_result,
        ), mock.patch.object(
            self.service,
            "_finalize_lifecycle_intent",
            side_effect=observed_finalize,
        ):
            recovered = self.service.lifecycle(request)
        contender.join(timeout=5)

        self.assertFalse(contender.is_alive())
        self.assertEqual(failures, [])
        self.assertTrue(receipt_committed.is_set())
        self.assertTrue(collector_entered.is_set())
        self.assertEqual(recovered["state"], "SUCCEEDED")
        self.assertEqual(recovered["outputs"]["recovered_output_ids"], [output_id])
        self.assertEqual(
            recovered["outputs"]["reconciled_collected_output_ids"], []
        )
        with self.service.lifecycle_store._connect() as connection:
            lifecycle_state = connection.execute(
                "SELECT state FROM lifecycle_outputs WHERE tenant_id = ? "
                "AND project_id = ? AND output_id = ?",
                ("tenant-a", "project-a", output_id),
            ).fetchone()[0]
        self.assertEqual(lifecycle_state, "stale")
        delivery_row = self.service._session_row(
            tenant_id="tenant-a",
            project_id="project-a",
            session_id=session_id,
        )
        self.assertEqual(delivery_row["status"], "PUBLISHED")
        self.assertTrue(output_root.exists())
        self.assertEqual(self.service.lifecycle(request), recovered)

    def test_replaced_fence_after_receipt_commit_never_replays_success(self) -> None:
        session_id, output_id, _output_root = self.stage_and_publish(
            suffix="fence-pending-receipt",
            revision_id="revision-fence-pending-receipt",
            source_snapshot_digest="8" * 64,
        )
        self.assertEqual(
            self.register(session_id, "fence-pending-receipt")["state"],
            "SUCCEEDED",
        )
        self.service.lifecycle(
            self.lifecycle_request(
                "mark_stale", "stale-fence-pending-receipt", output_id=output_id
            )
        )
        real_commit = self.service._commit_lifecycle_intent_result

        def commit_then_replace_fence(
            *,
            intent: delivery_service_module._LifecycleIntent,
            result: Mapping[str, object],
        ) -> None:
            real_commit(intent=intent, result=result)
            lock_path = (
                self.service.lifecycle_store.quarantine_root
                / self.service.lifecycle_store._FENCE_FILE
            )
            lock_path.unlink()
            lock_path.write_bytes(b"replacement fence inode")

        request = self.lifecycle_request(
            "collect", "collect-fence-pending-receipt", dry_run=False
        )
        with mock.patch.object(
            self.service,
            "_commit_lifecycle_intent_result",
            side_effect=commit_then_replace_fence,
        ):
            first = self.service.lifecycle(request)

        self.assertEqual(first["state"], "BLOCKED")
        self.assertEqual(first["outputs"]["mutation_outcome"], "UNKNOWN")
        self.assertTrue(first["outputs"]["receipt_persisted"])
        intent = self.service._lifecycle_intent(
            tenant_id="tenant-a",
            project_id="project-a",
            action="collect",
            idempotency_key="collect-fence-pending-receipt",
        )
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.status, "COMMITTED_FENCE_PENDING")
        self.assertIsNotNone(intent.result_digest)
        with self.service._connect() as connection:
            persisted = connection.execute(
                "SELECT finalized_at, result_json FROM delivery_lifecycle_intents "
                "JOIN delivery_receipts USING "
                "(tenant_id, project_id, idempotency_key) "
                "WHERE tenant_id = ? AND project_id = ? AND action = ? "
                "AND idempotency_key = ? AND operation = ?",
                (
                    "tenant-a",
                    "project-a",
                    "collect",
                    "collect-fence-pending-receipt",
                    "lifecycle:collect",
                ),
            ).fetchone()
        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertIsNone(persisted["finalized_at"])
        self.assertIsInstance(persisted["result_json"], bytes)

        replay = self.service.lifecycle(request)
        self.assertEqual(replay["state"], "BLOCKED")
        self.assertEqual(replay["code"], "LIFECYCLE_INTENT_PENDING")
        self.assertEqual(
            replay["outputs"]["pending_status"], "COMMITTED_FENCE_PENDING"
        )
        self.assertTrue(replay["outputs"]["receipt_persisted"])
        other = self.service.lifecycle(
            self.lifecycle_request(
                "collect", "collect-blocked-by-fence-pending", dry_run=False
            )
        )
        self.assertEqual(other["code"], "LIFECYCLE_INTENT_PENDING")

    def test_finalized_receipt_replays_after_fence_cleanup_error(self) -> None:
        request = self.lifecycle_request(
            "collect", "collect-fence-cleanup-error", dry_run=False
        )
        real_release = self.service.lifecycle_store._release_gc_fence

        def release_then_report_cleanup_error(
            fence: artifact_module._LifecycleFence,
        ) -> None:
            real_release(fence)
            raise OSError("simulated post-finalization cleanup error")

        with mock.patch.object(
            self.service.lifecycle_store,
            "_release_gc_fence",
            side_effect=release_then_report_cleanup_error,
        ):
            first = self.service.lifecycle(request)

        self.assertEqual(first["state"], "BLOCKED")
        self.assertEqual(first["code"], "LIFECYCLE_FENCE_CLEANUP_UNKNOWN")
        self.assertEqual(first["outputs"]["mutation_outcome"], "COMPLETED")
        self.assertTrue(first["outputs"]["operation_completed"])
        self.assertTrue(first["outputs"]["receipt_persisted"])
        intent = self.service._lifecycle_intent(
            tenant_id="tenant-a",
            project_id="project-a",
            action="collect",
            idempotency_key="collect-fence-cleanup-error",
        )
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.status, "FINALIZED")
        replay = self.service.lifecycle(request)
        self.assertEqual(replay["state"], "SUCCEEDED")
        self.assertEqual(
            replay["outputs"]["lifecycle_intent_digest"], intent.intent_digest
        )

    def test_finalized_receipt_replay_blocks_after_pre_cas_fence_replacement(
        self,
    ) -> None:
        request = self.lifecycle_request(
            "collect", "collect-pre-cas-fence-replaced", dry_run=False
        )
        real_finalize = self.service._finalize_lifecycle_intent

        def replace_fence_then_finalize(
            *,
            intent: delivery_service_module._LifecycleIntent,
            result: Mapping[str, object],
        ) -> None:
            lock_path = (
                self.service.lifecycle_store.quarantine_root
                / self.service.lifecycle_store._FENCE_FILE
            )
            lock_path.unlink()
            lock_path.write_bytes(b"post-assert replacement fence inode")
            lock_path.chmod(0o600)
            real_finalize(intent=intent, result=result)

        with mock.patch.object(
            self.service,
            "_finalize_lifecycle_intent",
            side_effect=replace_fence_then_finalize,
        ):
            first = self.service.lifecycle(request)

        self.assertEqual(first["state"], "BLOCKED")
        self.assertEqual(first["code"], "LIFECYCLE_FENCE_CLEANUP_UNKNOWN")
        self.assertEqual(first["outputs"]["mutation_outcome"], "COMPLETED")
        self.assertTrue(first["outputs"]["receipt_persisted"])
        intent = self.service._lifecycle_intent(
            tenant_id="tenant-a",
            project_id="project-a",
            action="collect",
            idempotency_key="collect-pre-cas-fence-replaced",
        )
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.status, "FINALIZED")

        replay = self.service.lifecycle(request)
        self.assertEqual(replay["state"], "BLOCKED")
        self.assertEqual(
            replay["code"], "LIFECYCLE_REPLAY_FENCE_IDENTITY_MISMATCH"
        )
        self.assertEqual(replay["outputs"]["mutation_outcome"], "UNKNOWN")
        self.assertTrue(replay["outputs"]["receipt_persisted"])

    def test_recover_collecting_is_project_scoped_within_one_tenant(self) -> None:
        session_a, output_a, _root_a = self.stage_and_publish(
            suffix="recover-project-a",
            revision_id="revision-recover-project-a",
            source_snapshot_digest="a" * 64,
        )
        self.assertEqual(
            self.register(session_a, "recover-project-a")["state"],
            "SUCCEEDED",
        )
        staged_b = self.service.stage(
            self.stage_request(
                idempotency_key="stage-recover-project-b",
                revision_id="revision-recover-project-b",
                run_id="run-recover-project-b",
                project_id="project-b",
                source_snapshot_digest="b" * 64,
            )
        )
        session_b = str(staged_b["outputs"]["session_id"])
        output_b = str(staged_b["outputs"]["output_id"])
        published_b = self.service.publish(
            self.publish_request(
                session_b,
                idempotency_key="publish-recover-project-b",
                project_id="project-b",
            )
        )
        self.assertEqual(published_b["state"], "SUCCEEDED")
        registered_b = self.service.lifecycle(
            self.lifecycle_request(
                "register",
                "register-recover-project-b",
                project_id="project-b",
                session_id=session_b,
            )
        )
        self.assertEqual(registered_b["state"], "SUCCEEDED")

        for project_id, output_id in (
            ("project-a", output_a),
            ("project-b", output_b),
        ):
            stale = self.service.lifecycle(
                self.lifecycle_request(
                    "mark_stale",
                    f"mark-stale-{project_id}",
                    project_id=project_id,
                    output_id=output_id,
                )
            )
            self.assertEqual(stale["outputs"]["lifecycle_state"], "stale")

        with self.service.lifecycle_store._connect() as connection:
            rows = connection.execute(
                "SELECT output_id, manifest_digest FROM lifecycle_outputs "
                "WHERE tenant_id = ? AND project_id IN (?, ?) "
                "ORDER BY project_id",
                ("tenant-a", "project-a", "project-b"),
            ).fetchall()
            self.assertEqual(
                {row["output_id"] for row in rows},
                {output_a, output_b},
            )
            for index, row in enumerate(rows):
                quarantine_path = self.service.lifecycle_store._quarantine_path(
                    tenant_id="tenant-a",
                    output_id=str(row["output_id"]),
                    manifest_digest=str(row["manifest_digest"]),
                )
                updated = connection.execute(
                    "UPDATE lifecycle_outputs SET state = 'collecting', "
                    "collecting_from = 'stale', quarantine_path = ?, "
                    "quarantine_verified = 0, quarantine_snapshot = NULL, "
                    "quarantine_snapshot_digest = NULL, collection_owner = ?, "
                    "collection_lease_until = ?, collection_phase = 'prepared' "
                    "WHERE tenant_id = ? AND output_id = ? AND state = 'stale'",
                    (
                        str(quarantine_path),
                        f"gc-operation-{index:032x}",
                        "1970-01-01T00:00:00Z",
                        "tenant-a",
                        row["output_id"],
                    ),
                )
                self.assertEqual(updated.rowcount, 1)

        recovered = self.service.lifecycle(
            self.lifecycle_request("recover", "recover-project-a")
        )
        self.assertEqual(recovered["state"], "SUCCEEDED")
        self.assertEqual(recovered["outputs"]["recovered_output_ids"], [output_a])
        intent = self.service._lifecycle_intent(
            tenant_id="tenant-a",
            project_id="project-a",
            action="recover",
            idempotency_key="recover-project-a",
        )
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.candidate_output_ids, (output_a,))
        with self.service.lifecycle_store._connect() as connection:
            states = {
                row["project_id"]: row["state"]
                for row in connection.execute(
                    "SELECT project_id, state FROM lifecycle_outputs "
                    "WHERE tenant_id = ? AND output_id IN (?, ?)",
                    ("tenant-a", output_a, output_b),
                )
            }
        self.assertEqual(
            states,
            {"project-a": "stale", "project-b": "collecting"},
        )

    def test_recover_prepared_after_durable_quarantine_rename(self) -> None:
        output_id, output_root = self.stale_registered_output(
            suffix="recover-prepared-rename",
            source_snapshot_digest="9" * 64,
        )
        store = self.service.lifecycle_store
        with mock.patch.object(
            store,
            "_advance_collection_phase",
            side_effect=artifact_module.LifecycleError(
                "simulated crash after quarantine rename"
            ),
        ):
            with self.assertRaises(artifact_module.LifecycleError):
                store.collect_garbage(
                    tenant_id="tenant-a", project_id="project-a", dry_run=False
                )
        with store._connect() as connection:
            row = store._select_lifecycle_row(
                connection, tenant_id="tenant-a", output_id=output_id
            )
        self.assertIsNotNone(row)
        assert row is not None
        quarantine_path = Path(str(row["quarantine_path"]))
        self.assertEqual(row["collection_phase"], "prepared")
        self.assertFalse(output_root.exists())
        self.assertTrue(quarantine_path.exists())

        self.expire_collection_lease(output_id)
        recovered = store.recover_collecting(
            tenant_id="tenant-a",
            project_id="project-a",
            candidates=(output_id,),
        )
        self.assertEqual(recovered, (output_id,))
        self.assertFalse(quarantine_path.exists())
        with store._connect() as connection:
            terminal = store._select_lifecycle_row(
                connection, tenant_id="tenant-a", output_id=output_id
            )
        self.assertIsNotNone(terminal)
        assert terminal is not None
        self.assertEqual(terminal["state"], "collected")

    def test_recover_quarantined_before_snapshot_persistence(self) -> None:
        output_id, output_root = self.stale_registered_output(
            suffix="recover-quarantined-snapshot",
            source_snapshot_digest="a" * 64,
        )
        store = self.service.lifecycle_store
        with mock.patch.object(
            store,
            "_persist_verified_snapshot",
            side_effect=artifact_module.LifecycleError(
                "simulated crash before snapshot persistence"
            ),
        ):
            with self.assertRaises(artifact_module.LifecycleError):
                store.collect_garbage(
                    tenant_id="tenant-a", project_id="project-a", dry_run=False
                )
        with store._connect() as connection:
            row = store._select_lifecycle_row(
                connection, tenant_id="tenant-a", output_id=output_id
            )
        self.assertIsNotNone(row)
        assert row is not None
        quarantine_path = Path(str(row["quarantine_path"]))
        self.assertEqual(row["collection_phase"], "quarantined")
        self.assertEqual(row["quarantine_verified"], 0)
        self.assertFalse(output_root.exists())
        self.assertTrue(quarantine_path.exists())

        self.expire_collection_lease(output_id)
        self.assertEqual(
            store.recover_collecting(
                tenant_id="tenant-a",
                project_id="project-a",
                candidates=(output_id,),
            ),
            (output_id,),
        )
        self.assertFalse(quarantine_path.exists())
        with store._connect() as connection:
            terminal = store._select_lifecycle_row(
                connection, tenant_id="tenant-a", output_id=output_id
            )
        self.assertIsNotNone(terminal)
        assert terminal is not None
        self.assertEqual(terminal["state"], "collected")

    def test_recover_verified_missing_finalizes_collected(self) -> None:
        output_id, output_root = self.stale_registered_output(
            suffix="recover-verified-missing",
            source_snapshot_digest="b" * 64,
        )
        store = self.service.lifecycle_store
        with mock.patch.object(
            store,
            "_finish_collection",
            side_effect=artifact_module.LifecycleError(
                "simulated crash after verified deletion"
            ),
        ):
            with self.assertRaises(artifact_module.LifecycleError):
                store.collect_garbage(
                    tenant_id="tenant-a", project_id="project-a", dry_run=False
                )
        with store._connect() as connection:
            row = store._select_lifecycle_row(
                connection, tenant_id="tenant-a", output_id=output_id
            )
        self.assertIsNotNone(row)
        assert row is not None
        quarantine_path = Path(str(row["quarantine_path"]))
        self.assertEqual(row["collection_phase"], "verified")
        self.assertEqual(row["quarantine_verified"], 1)
        self.assertFalse(output_root.exists())
        self.assertFalse(quarantine_path.exists())

        self.expire_collection_lease(output_id)
        self.assertEqual(
            store.recover_collecting(
                tenant_id="tenant-a",
                project_id="project-a",
                candidates=(output_id,),
            ),
            (output_id,),
        )
        with store._connect() as connection:
            terminal = store._select_lifecycle_row(
                connection, tenant_id="tenant-a", output_id=output_id
            )
        self.assertIsNotNone(terminal)
        assert terminal is not None
        self.assertEqual(terminal["state"], "collected")

    def test_recover_unverified_missing_remains_unknown(self) -> None:
        output_id, output_root = self.stale_registered_output(
            suffix="recover-unverified-missing",
            source_snapshot_digest="c" * 64,
        )
        store = self.service.lifecycle_store
        with store._connect() as connection:
            row = store._select_lifecycle_row(
                connection, tenant_id="tenant-a", output_id=output_id
            )
            self.assertIsNotNone(row)
            assert row is not None
            quarantine_path = store._quarantine_path(
                tenant_id="tenant-a",
                output_id=output_id,
                manifest_digest=str(row["manifest_digest"]),
            )
            updated = connection.execute(
                "UPDATE lifecycle_outputs SET state = 'collecting', "
                "collecting_from = 'stale', quarantine_path = ?, "
                "quarantine_verified = 0, quarantine_snapshot = NULL, "
                "quarantine_snapshot_digest = NULL, collection_owner = ?, "
                "collection_lease_until = ?, collection_phase = 'prepared' "
                "WHERE tenant_id = ? AND project_id = ? AND output_id = ? "
                "AND state = 'stale'",
                (
                    str(quarantine_path),
                    "gc-operation-dddddddddddddddddddddddddddddddd",
                    "1970-01-01T00:00:00Z",
                    "tenant-a",
                    "project-a",
                    output_id,
                ),
            )
        self.assertEqual(updated.rowcount, 1)
        held_path = self.root / "held-unverified-lifecycle-output"
        output_root.rename(held_path)
        self.assertFalse(output_root.exists())
        self.assertFalse(quarantine_path.exists())

        blocked = self.service.lifecycle(
            self.lifecycle_request("recover", "recover-unverified-missing")
        )
        self.assertEqual(blocked["state"], "BLOCKED")
        self.assertEqual(blocked["code"], "LIFECYCLE_OPERATION_BLOCKED")
        self.assertEqual(blocked["outputs"]["mutation_outcome"], "UNKNOWN")
        self.assertTrue(held_path.exists())
        with store._connect() as connection:
            terminal = store._select_lifecycle_row(
                connection, tenant_id="tenant-a", output_id=output_id
            )
        self.assertIsNotNone(terminal)
        assert terminal is not None
        self.assertEqual(terminal["state"], "collecting")
        self.assertEqual(terminal["collection_phase"], "prepared")
        self.assertEqual(terminal["quarantine_verified"], 0)

    def test_publish_scope_fence_prevents_active_claim_theft(self) -> None:
        staged = self.service.stage(
            self.stage_request(idempotency_key="stage-concurrent-publish")
        )
        session_id = str(staged["outputs"]["session_id"])
        contender = TrustedDeliveryService(**self.configuration)
        entered = threading.Event()
        release = threading.Event()
        outcomes: list[dict[str, object]] = []
        failures: list[BaseException] = []
        original = artifact_module.ArtifactPublisher.publish

        def blocked_publish(
            publisher: artifact_module.ArtifactPublisher,
            *args: object,
            **kwargs: object,
        ) -> object:
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("publication concurrency barrier timed out")
            return original(publisher, *args, **kwargs)

        def first_publisher() -> None:
            try:
                outcomes.append(
                    dict(
                        self.service.publish(
                            self.publish_request(
                                session_id,
                                idempotency_key="publish-concurrent-first",
                            )
                        )
                    )
                )
            except BaseException as exc:  # capture the deterministic thread outcome
                failures.append(exc)

        with mock.patch.object(
            artifact_module.ArtifactPublisher,
            "publish",
            new=blocked_publish,
        ):
            thread = threading.Thread(target=first_publisher, daemon=True)
            thread.start()
            self.assertTrue(entered.wait(timeout=5))
            contended = contender.publish(
                self.publish_request(
                    session_id,
                    idempotency_key="publish-concurrent-second",
                )
            )
            self.assertEqual(contended["state"], "BLOCKED")
            self.assertEqual(contended["code"], "DELIVERY_OPERATION_IN_PROGRESS")
            self.assertTrue(contended["retryable"])
            row = contender._session_row(
                tenant_id="tenant-a",
                project_id="project-a",
                session_id=session_id,
            )
            self.assertEqual(row["status"], "PUBLISHING")
            release.set()
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(outcomes[0]["state"], "SUCCEEDED")

    def test_delivery_scope_fence_hardlink_is_rejected_before_chmod(self) -> None:
        external = self.root / "external-fence-sentinel"
        external.write_bytes(b"external-fence-sentinel")
        external.chmod(0o640)
        identity = delivery_service_module.canonical_digest(
            {
                "schema_version": "elmos.autonomous-qa.delivery-fence.v1",
                "tenant_id": "tenant-a",
                "project_id": "project-a",
            }
        )
        (self.state / f".delivery-scope-{identity}.lock").hardlink_to(external)

        with self.assertRaises(DeliveryStateError):
            self.service.stage(
                self.stage_request(idempotency_key="stage-hardlinked-fence")
            )

        self.assertEqual(external.read_bytes(), b"external-fence-sentinel")
        self.assertEqual(stat.S_IMODE(external.stat().st_mode), 0o640)

    def test_delivery_scope_fence_detects_state_root_replacement(self) -> None:
        fence = self.service._acquire_scope_fence(
            tenant_id="tenant-a", project_id="project-a"
        )
        self.assertIsNotNone(fence)
        assert fence is not None
        held_state = self.root / "held-state"
        self.state.rename(held_state)
        self.state.mkdir(mode=0o700)

        with self.assertRaisesRegex(DeliveryStateError, "root was replaced"):
            self.service._release_scope_fence(fence)

    def test_concurrent_first_startup_converges_on_one_exact_schema(self) -> None:
        case_root = self.root / "concurrent-startup"
        embedded = case_root / "project"
        embedded.mkdir(parents=True, mode=0o700)
        configuration = {
            "staging_root": case_root / "staging",
            "publication_root": case_root / "publication",
            "lifecycle_root": case_root / "lifecycle",
            "state_root": case_root / "state",
            "database_path": case_root / "state" / "delivery.sqlite3",
            "embedded_roots": {("tenant-a", "project-a"): embedded},
        }
        barrier = threading.Barrier(2)
        services: list[TrustedDeliveryService] = []
        failures: list[BaseException] = []

        def construct() -> None:
            try:
                barrier.wait(timeout=5)
                services.append(TrustedDeliveryService(**configuration))
            except BaseException as exc:  # capture the exact startup outcome
                failures.append(exc)

        threads = [threading.Thread(target=construct, daemon=True) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertEqual(len(services), 2)
        services[0]._assert_database()
        services[1]._assert_database()

    def test_orphaned_stage_is_quarantined_and_retry_completes(self) -> None:
        request = self.stage_request(idempotency_key="stage-orphan-recovery")
        session_id = "delivery-" + artifact_module.canonical_digest(
            {
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "idempotency_key": "stage-orphan-recovery",
            }
        )[:32]
        orphan, _durable = self.service._create_session_root(session_id)
        (orphan / "partial.txt").write_text("partial\n", encoding="utf-8")
        recovered = self.service.stage(request)
        self.assertEqual(recovered["state"], "SUCCEEDED")
        self.assertEqual(recovered["outputs"]["session_id"], session_id)
        self.assertEqual(len(list(self.staging.glob(".orphaned-stage-*"))), 1)

    def test_dangling_database_symlink_is_rejected_without_external_write(self) -> None:
        case_root = self.root / "dangling-database-case"
        state = case_root / "state"
        embedded = case_root / "project"
        state.mkdir(parents=True, mode=0o700)
        embedded.mkdir(mode=0o700)
        external = case_root / "external" / "escaped.sqlite3"
        (state / "delivery.sqlite3").symlink_to(external)
        with self.assertRaises(DeliveryStateError):
            TrustedDeliveryService(
                staging_root=case_root / "staging",
                publication_root=case_root / "publication",
                lifecycle_root=case_root / "lifecycle",
                state_root=state,
                database_path=state / "delivery.sqlite3",
                embedded_roots={("tenant-a", "project-a"): embedded},
            )
        self.assertFalse(external.exists())

    def test_delivery_connect_closes_connection_after_post_open_validation(self) -> None:
        connection = mock.Mock()
        with mock.patch.object(
            self.service,
            "_assert_database_sidecars",
            side_effect=[None, DeliveryStateError("unsafe sidecar after open")],
        ), mock.patch.object(
            delivery_service_module.sqlite3,
            "connect",
            return_value=connection,
        ):
            with self.assertRaises(DeliveryStateError):
                self.service._connect()
        connection.close.assert_called_once_with()

    def test_lifecycle_connect_closes_connection_after_schema_validation_failure(
        self,
    ) -> None:
        connection = mock.Mock()
        with mock.patch.object(
            self.service.lifecycle_store,
            "_assert_current_schema",
            side_effect=artifact_module.LifecycleError("simulated lifecycle schema drift"),
        ), mock.patch.object(
            artifact_module.sqlite3,
            "connect",
            return_value=connection,
        ):
            with self.assertRaises(artifact_module.LifecycleError):
                self.service.lifecycle_store._connect()
        connection.close.assert_called_once_with()

    def test_lifecycle_integrity_check_rejects_non_ok_result(self) -> None:
        store = self.service.lifecycle_store
        with store._connect() as connection:
            integrity_cursor = mock.Mock()
            integrity_cursor.fetchmany.return_value = [("database disk image is malformed",)]
            proxy = mock.Mock()

            def execute(statement: str, *parameters: object) -> object:
                if statement == "PRAGMA integrity_check(1)":
                    return integrity_cursor
                return connection.execute(statement, *parameters)

            proxy.execute.side_effect = execute
            with self.assertRaisesRegex(
                artifact_module.LifecycleError,
                "lifecycle database integrity check failed",
            ):
                store._assert_current_schema(proxy)

    def test_lifecycle_integrity_check_wraps_sqlite_error(self) -> None:
        store = self.service.lifecycle_store
        with store._connect() as connection:
            proxy = mock.Mock()

            def execute(statement: str, *parameters: object) -> object:
                if statement == "PRAGMA integrity_check(1)":
                    raise sqlite3.DatabaseError("simulated integrity read failure")
                return connection.execute(statement, *parameters)

            proxy.execute.side_effect = execute
            with self.assertRaisesRegex(
                artifact_module.LifecycleError,
                "lifecycle database integrity validation failed",
            ):
                store._assert_current_schema(proxy)

    def test_delivery_database_sidecars_must_remain_private(self) -> None:
        sidecar = Path(str(self.database) + "-journal")
        sidecar.write_bytes(b"unsafe-sidecar")
        sidecar.chmod(0o644)
        with self.assertRaises(DeliveryStateError):
            self.service._assert_database_sidecars()

    def test_lifecycle_database_symlink_is_rejected_without_external_write(self) -> None:
        case_root = self.root / "lifecycle-symlink-case"
        lifecycle = case_root / "lifecycle"
        embedded = case_root / "project"
        lifecycle.mkdir(parents=True, mode=0o700)
        embedded.mkdir(mode=0o700)
        external = case_root / "external" / "escaped.sqlite3"
        (lifecycle / "lifecycle.sqlite3").symlink_to(external)
        with self.assertRaises(artifact_module.LifecycleError):
            TrustedDeliveryService(
                staging_root=case_root / "staging",
                publication_root=case_root / "publication",
                lifecycle_root=lifecycle,
                state_root=case_root / "state",
                database_path=case_root / "state" / "delivery.sqlite3",
                embedded_roots={("tenant-a", "project-a"): embedded},
            )
        self.assertFalse(external.exists())

    def test_lifecycle_database_hardlink_is_rejected_before_chmod_or_write(self) -> None:
        case_root = self.root / "lifecycle-hardlink-case"
        lifecycle = case_root / "lifecycle"
        embedded = case_root / "project"
        external = case_root / "external" / "existing.sqlite3"
        lifecycle.mkdir(parents=True, mode=0o700)
        embedded.mkdir(mode=0o700)
        external.parent.mkdir(mode=0o700)
        external.write_bytes(b"external-sentinel")
        external.chmod(0o640)
        (lifecycle / "lifecycle.sqlite3").hardlink_to(external)
        with self.assertRaises(artifact_module.LifecycleError):
            TrustedDeliveryService(
                staging_root=case_root / "staging",
                publication_root=case_root / "publication",
                lifecycle_root=lifecycle,
                state_root=case_root / "state",
                database_path=case_root / "state" / "delivery.sqlite3",
                embedded_roots={("tenant-a", "project-a"): embedded},
            )
        self.assertEqual(external.read_bytes(), b"external-sentinel")
        self.assertEqual(stat.S_IMODE(external.stat().st_mode), 0o640)

    def test_database_schema_drift_is_rejected_before_operation(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("CREATE TABLE caller_owned (value TEXT)")
        with self.assertRaises(DeliveryStateError):
            self.service.stage(
                self.stage_request(idempotency_key="after-schema-drift")
            )

    def test_live_lifecycle_schema_drift_is_rejected_before_operation(self) -> None:
        with closing(
            sqlite3.connect(self.service.lifecycle_database_path)
        ) as connection, connection:
            connection.execute("CREATE TABLE caller_owned (value TEXT)")
        blocked = self.service.lifecycle(
            self.lifecycle_request("candidates", "after-live-lifecycle-schema-drift")
        )
        self.assertEqual(blocked["state"], "BLOCKED")
        self.assertEqual(blocked["code"], "LIFECYCLE_OPERATION_BLOCKED")
        with self.assertRaisesRegex(
            artifact_module.LifecycleError,
            "legacy or altered lifecycle schema",
        ):
            self.service.lifecycle_store.gc_candidates(
                tenant_id="tenant-a", project_id="project-a"
            )


if __name__ == "__main__":
    unittest.main()
