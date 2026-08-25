from __future__ import annotations

import sqlite3
import stat
import sys
import tempfile
import unittest
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
        self.temporary = tempfile.TemporaryDirectory()
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

        published = self.service.execute_publishing(
            self.runtime_request(
                {"session_id": session_id},
                request_id="request-publish",
                idempotency_key="runtime-publish-key",
            )
        )
        self.assertEqual(published["state"], "SUCCEEDED")
        self.assertEqual(published["outputs"]["signing"], "NOT_RUN")
        registered = self.service.execute_lifecycle(
            self.runtime_request(
                {"action": "register", "session_id": session_id},
                request_id="request-register",
                idempotency_key="runtime-register-key",
            )
        )
        self.assertEqual(registered["state"], "SUCCEEDED")
        self.assertTrue(registered["outputs"]["lifecycle_registered"])

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
        self.assertTrue((plan.final_root / "bundles" / "tests-only.zip").is_file())
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
        result = self.register(session_id, "published-tamper")
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["code"], "LIFECYCLE_OPERATION_BLOCKED")
        self.assertEqual(result["outputs"]["mutation_outcome"], "UNKNOWN")
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
        self.assertEqual(
            (self.embedded_b / "tests" / "test_value.py").read_bytes(), source
        )
        self.assertFalse((self.embedded_a / "tests" / "test_value.py").exists())

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
            result = self.service.publish(
                self.publish_request(
                    session_id, idempotency_key="publish-post-commit"
                )
            )
        self.assertTrue(final_root.exists())
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["code"], "PUBLICATION_OUTCOME_UNKNOWN")
        self.assertEqual(result["outputs"]["durability_status"], "UNKNOWN")
        persisted = self.service._session_row(
            tenant_id="tenant-a", project_id="project-a", session_id=session_id
        )
        self.assertEqual(persisted["status"], "DURABILITY_UNKNOWN")
        self.assertIsNone(persisted["published_output_json"])
        blocked = self.register(session_id, "post-commit")
        self.assertEqual(blocked["code"], "PUBLISHED_OUTPUT_REQUIRED")

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
        self.assertFalse(old_root.exists())
        self.assertTrue(new_root.exists())

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
            replay_publish["code"], "IMMUTABLE_OUTPUT_ALREADY_EXISTS"
        )
        self.assertTrue(replay_publish["outputs"]["output_identity_reserved"])
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

    def test_database_schema_drift_is_rejected_before_operation(self) -> None:
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE caller_owned (value TEXT)")
        with self.assertRaises(DeliveryStateError):
            self.service.stage(
                self.stage_request(idempotency_key="after-schema-drift")
            )


if __name__ == "__main__":
    unittest.main()
