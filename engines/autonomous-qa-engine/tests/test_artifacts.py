from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import elmos_autonomous_qa.artifacts as artifact_module  # noqa: E402
from elmos_autonomous_qa.artifacts import (  # noqa: E402
    ArtifactLifecycleStore,
    ArtifactPublisher,
    ArtifactValidationError,
    CertificationDenied,
    LifecycleError,
    OutputMode,
    OutputPlan,
    PublicationError,
)
from elmos_autonomous_qa.canonical import UnsafePathError  # noqa: E402


class ArtifactPublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        # macOS exposes its default temporary directory through the /var
        # symlink.  Production artifact roots deliberately reject every
        # symlinked ancestor, so create the fixture below the physical temp
        # directory instead of weakening that boundary for tests.
        temporary_base = Path(tempfile.gettempdir()).resolve(strict=True)
        self.temporary = tempfile.TemporaryDirectory(dir=temporary_base)
        root = Path(self.temporary.name)
        self.staging = root / "staging"
        self.publication = root / "published"
        self.embedded = root / "worktree"
        self.staging.mkdir()
        self.publication.mkdir()
        self.embedded.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def plan(
        self,
        *,
        revision: str = "revision-1",
        mode: OutputMode = OutputMode.SIDECAR,
        run_mode: str = "generate",
    ) -> OutputPlan:
        return OutputPlan(
            tenant_id="tenant-a",
            project_id="project-a",
            revision_id=revision,
            run_id=f"run-{revision}",
            run_mode=run_mode,
            output_mode=mode,
            source_snapshot_digest="b" * 64,
            staging_root=self.staging,
            publication_root=self.publication,
            embedded_root=self.embedded if mode in {OutputMode.EMBEDDED, OutputMode.BOTH} else None,
            created_at="2026-08-22T00:00:00Z",
        )

    def write(self, path: str, content: str) -> None:
        target = self.staging / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def publisher_with_test(self, *, revision: str = "revision-1") -> ArtifactPublisher:
        self.write("tests/test_math.py", "def test_add():\n    assert 1 + 2 == 3\n")
        publisher = ArtifactPublisher(self.plan(revision=revision))
        publisher.register_file(
            "tests/test_math.py",
            artifact_id="artifact-test-math",
            category="test_source",
            role="unit_test",
            producer="test-generator-v1",
            requirement_refs=("REQ-MATH-1",),
            test_case_refs=("TC-MATH-1",),
        )
        return publisher

    def publisher_with_test_for_mode(self, mode: OutputMode) -> ArtifactPublisher:
        self.write("tests/test_embedded.py", "def test_value():\n    assert 2 + 2 == 4\n")
        publisher = ArtifactPublisher(self.plan(mode=mode))
        publisher.register_file(
            "tests/test_embedded.py",
            artifact_id="artifact-test-embedded",
            category="test_source",
            role="unit_test",
            producer="test-generator-v1",
            requirement_refs=("REQ-EMBEDDED-1",),
            test_case_refs=("TC-EMBEDDED-1",),
        )
        return publisher

    def test_path_traversal_and_symlink_are_rejected(self) -> None:
        publisher = ArtifactPublisher(self.plan())
        with self.assertRaises(UnsafePathError):
            publisher.register_file(
                "../escape.py",
                artifact_id="escape",
                category="test_source",
                role="unit",
                producer="generator",
                requirement_refs=("REQ-1",),
                test_case_refs=("TC-1",),
            )

    def test_casefold_path_collision_is_rejected(self) -> None:
        self.write("Tests/test_math.py", "def test_add():\n    assert 1 + 2 == 3\n")
        publisher = ArtifactPublisher(self.plan())
        publisher.register_file(
            "Tests/test_math.py",
            artifact_id="first",
            category="test_source",
            role="unit",
            producer="generator",
            requirement_refs=("REQ-1",),
            test_case_refs=("TC-1",),
        )
        with self.assertRaises(ArtifactValidationError):
            publisher.register_file(
                "tests/test_math.py",
                artifact_id="second",
                category="test_source",
                role="unit",
                producer="generator",
                requirement_refs=("REQ-1",),
                test_case_refs=("TC-1",),
            )
        outside = Path(self.temporary.name) / "outside.py"
        outside.write_text("safe = True\n", encoding="utf-8")
        (self.staging / "link.py").symlink_to(outside)
        with self.assertRaises((UnsafePathError, ArtifactValidationError)):
            publisher.register_file(
                "link.py",
                artifact_id="link",
                category="test_source",
                role="unit",
                producer="generator",
                requirement_refs=("REQ-1",),
                test_case_refs=("TC-1",),
            )

    def test_descriptor_reads_reject_hardlinks_and_symlinked_directories(self) -> None:
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        (outside / "test_external.py").write_text(
            "def test_external():\n    assert 4 == 4\n", encoding="utf-8"
        )
        os.link(outside / "test_external.py", self.staging / "hardlink.py")
        publisher = ArtifactPublisher(self.plan())
        with self.assertRaises(ArtifactValidationError):
            publisher.register_file(
                "hardlink.py",
                artifact_id="hardlink",
                category="test_source",
                role="unit",
                producer="generator",
                requirement_refs=("REQ-1",),
                test_case_refs=("TC-1",),
            )

        (self.staging / "linked-directory").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ArtifactValidationError):
            publisher.register_file(
                "linked-directory/test_external.py",
                artifact_id="linked-directory",
                category="test_source",
                role="unit",
                producer="generator",
                requirement_refs=("REQ-1",),
                test_case_refs=("TC-1",),
            )

    def test_artifact_metadata_is_closed_and_required_outputs_are_traced(self) -> None:
        samples = {
            "status.py": "def test_status():\n    assert 1 == 1\n",
            "role.py": "def test_role():\n    assert 1 == 1\n",
            "producer.py": "def test_producer():\n    assert 1 == 1\n",
            "certificate.json": "{}\n",
            "report.json": "{}\n",
        }
        for path, content in samples.items():
            self.write(path, content)
        publisher = ArtifactPublisher(self.plan())
        common = {
            "category": "test_source",
            "role": "unit",
            "producer": "generator",
            "requirement_refs": ("REQ-1",),
            "test_case_refs": ("TC-1",),
        }
        with self.assertRaises(CertificationDenied):
            publisher.register_file(
                "status.py", artifact_id="status", validation_status="certified", **common
            )
        with self.assertRaises(ArtifactValidationError):
            publisher.register_file(
                "role.py", artifact_id="role", **{**common, "role": "arbitrary-role"}
            )
        with self.assertRaises(ArtifactValidationError):
            publisher.register_file(
                "producer.py",
                artifact_id="producer",
                **{**common, "producer": "unregistered-producer"},
            )
        with self.assertRaises(CertificationDenied):
            publisher.register_file(
                "certificate.json",
                artifact_id="certificate",
                category="certificate",
                role="evidence",
                producer="evidence-collector",
                requirement_refs=("REQ-1",),
            )
        with self.assertRaises(ArtifactValidationError):
            publisher.register_file(
                "report.json",
                artifact_id="untraced-report",
                category="report",
                role="report",
                producer="generator",
            )

    def test_storage_paths_use_stable_opaque_identity_segments(self) -> None:
        plan = self.plan()
        relative = plan.final_root.relative_to(self.publication.resolve())
        self.assertEqual(len(relative.parts), 4)
        self.assertNotIn(plan.tenant_id, relative.parts)
        self.assertNotIn(plan.project_id, relative.parts)
        self.assertNotIn(plan.revision_id, relative.parts)
        self.assertNotIn(plan.output_id, relative.parts)
        self.assertEqual(plan.final_root, self.plan().final_root)
        case_variant = replace(plan, tenant_id=plan.tenant_id.upper())
        self.assertNotEqual(plan.final_root, case_variant.final_root)
        run_variant = replace(plan, run_id="a-different-run")
        self.assertNotEqual(plan.final_root, run_variant.final_root)

    def test_created_at_must_be_canonical_utc(self) -> None:
        for invalid in ("", "2026-08-22T00:00:00+00:00", "not-a-timestamp"):
            with self.subTest(created_at=invalid), self.assertRaises(ValueError):
                replace(self.plan(), created_at=invalid)

    def test_atomic_file_install_never_replaces_an_existing_target(self) -> None:
        target = self.publication / "owned.txt"
        target.write_text("owner-data\n", encoding="utf-8")
        with self.assertRaises(PublicationError):
            artifact_module._write_bytes_atomic(target.resolve(), b"replacement\n")
        self.assertEqual(target.read_text(encoding="utf-8"), "owner-data\n")
        self.assertTrue(target.is_file())

    def test_secrets_placeholders_assert_true_and_disabled_tests_are_rejected(self) -> None:
        samples = {
            "secret.py": 'api_key = "abcdefghijklmnop"\n',
            "placeholder.py": "def test_x():\n    # TODO implement\n    pass\n",
            "assert_true.py": "def test_x():\n    assert True\n",
            "disabled.py": "import pytest\n@pytest.mark.skip\ndef test_x(): pass\n",
        }
        for index, (name, source) in enumerate(samples.items()):
            with self.subTest(name=name):
                self.write(name, source)
                publisher = ArtifactPublisher(self.plan(revision=f"revision-{index}"))
                with self.assertRaises(ArtifactValidationError):
                    publisher.register_file(
                        name,
                        artifact_id=f"artifact-{index}",
                        category="test_source",
                        role="unit",
                        producer="generator",
                        requirement_refs=("REQ-1",),
                        test_case_refs=("TC-1",),
                    )
                (self.staging / name).unlink()

    def test_tamper_and_unmanifested_files_fail_validation(self) -> None:
        publisher = self.publisher_with_test()
        (self.staging / "tests/test_math.py").write_text(
            "def test_add():\n    assert 0 == 1\n", encoding="utf-8"
        )
        with self.assertRaises(ArtifactValidationError):
            publisher.validate()

        (self.staging / "tests/test_math.py").write_text(
            "def test_add():\n    assert 1 + 2 == 3\n", encoding="utf-8"
        )
        self.write("untracked.txt", "not registered\n")
        with self.assertRaises(ArtifactValidationError):
            publisher.validate()

    def test_staging_inventory_rejects_same_name_directory_swap(self) -> None:
        publisher = self.publisher_with_test()
        original = self.staging / "tests"
        displaced = self.staging / "tests-displaced"
        real_stat = artifact_module.os.stat
        observed_parent_stats = 0

        def swap_before_parent_recheck(
            path: object, *args: object, **kwargs: object
        ) -> os.stat_result:
            nonlocal observed_parent_stats
            if path == "tests" and kwargs.get("dir_fd") is not None:
                observed_parent_stats += 1
                if observed_parent_stats == 2:
                    original.rename(displaced)
                    original.mkdir()
                    (original / "test_math.py").write_text(
                        "def test_add():\n    assert 1 + 2 == 3\n",
                        encoding="utf-8",
                    )
                    (original / "owner-data.txt").write_text(
                        "do not adopt\n", encoding="utf-8"
                    )
            return real_stat(path, *args, **kwargs)

        with mock.patch.object(
            artifact_module.os, "stat", side_effect=swap_before_parent_recheck
        ):
            with self.assertRaises(ArtifactValidationError):
                publisher.validate()
        self.assertGreaterEqual(observed_parent_stats, 2)
        self.assertEqual(
            "do not adopt\n",
            (original / "owner-data.txt").read_text(encoding="utf-8"),
        )

    def test_bundle_is_deterministic_and_verified(self) -> None:
        publisher = self.publisher_with_test()
        first_bytes, first_digest = publisher.build_bundle("tests-only")
        second_bytes, second_digest = publisher.build_bundle("tests-only")
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(first_digest, second_digest)

    def test_partial_output_is_published_on_validation_failure(self) -> None:
        publisher = self.publisher_with_test()
        self.write("untracked.txt", "untracked\n")
        output = publisher.publish(partial_on_failure=True)
        self.assertEqual(output.status, "partial")
        self.assertTrue((output.root / "manifests/project-output-manifest.json").is_file())
        manifest = json.loads(
            (output.root / "manifests/project-output-manifest.json").read_text(encoding="utf-8")
        )
        self.assertFalse(manifest["certified"])
        self.assertEqual(manifest["external_evidence_status"], "NOT_RUN")
        self.assertEqual(manifest["bundles"], [])

    def test_certification_and_signing_are_external_only(self) -> None:
        publisher = self.publisher_with_test()
        with self.assertRaises(CertificationDenied):
            publisher.publish(requested_status="certified")

    def test_output_modes_return_explicit_materialization_targets(self) -> None:
        embedded = self.plan(mode=OutputMode.EMBEDDED)
        both = self.plan(mode=OutputMode.BOTH)
        self.assertEqual(embedded.materialization_targets(), (self.embedded.resolve(),))
        self.assertEqual(len(both.materialization_targets()), 2)
        self.assertEqual(
            self.plan(mode=OutputMode.BOTH, run_mode="plan-only").materialization_targets(),
            (),
        )

    def test_plan_only_never_materializes(self) -> None:
        path = "tests/revision-plan-only.py"
        self.write(path, "def test_value():\n    assert 2 + 2 == 4\n")
        publisher = ArtifactPublisher(
            self.plan(
                revision="revision-plan-only",
                mode=OutputMode.BOTH,
                run_mode="plan-only",
            )
        )
        publisher.register_file(
            path,
            artifact_id="artifact-revision-plan-only",
            category="test_source",
            role="unit_test",
            producer="test-generator-v1",
            requirement_refs=("REQ-NON-MATERIALIZED",),
            test_case_refs=("TC-NON-MATERIALIZED",),
        )
        output = publisher.publish()
        self.assertEqual(output.status, "verified")
        self.assertFalse((self.embedded / path).exists())
        self.assertFalse((output.root / "project").exists())
        self.assertFalse((output.root / "bundles").exists())
        manifest = json.loads(
            (output.root / "manifests/project-output-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["bundles"], [])
        self.assertEqual(manifest["materialization"]["embedded_test_artifacts"], 0)
        self.assertEqual(manifest["materialization"]["sidecar_artifacts"], 0)

    def test_caller_cannot_request_partial_or_failed_status(self) -> None:
        for requested_status in ("partial", "failed"):
            revision = f"revision-caller-{requested_status}"
            path = f"tests/{revision}.py"
            with self.subTest(requested_status=requested_status):
                self.write(path, "def test_value():\n    assert 2 + 2 == 4\n")
                publisher = ArtifactPublisher(
                    self.plan(revision=revision, mode=OutputMode.BOTH)
                )
                publisher.register_file(
                    path,
                    artifact_id=f"artifact-{revision}",
                    category="test_source",
                    role="unit_test",
                    producer="test-generator-v1",
                    requirement_refs=("REQ-NON-MATERIALIZED",),
                    test_case_refs=("TC-NON-MATERIALIZED",),
                )
                with self.assertRaises(PublicationError):
                    publisher.publish(requested_status=requested_status)
                self.assertFalse(publisher.plan.final_root.exists())
                self.assertFalse((self.embedded / path).exists())
                (self.staging / path).unlink()

    def test_every_registered_artifact_has_a_delivery_channel(self) -> None:
        self.write("reports/summary.json", '{"status":"local"}\n')
        publisher = ArtifactPublisher(self.plan(revision="revision-report"))
        publisher.register_file(
            "reports/summary.json",
            artifact_id="artifact-report",
            category="report",
            role="report",
            producer="generator",
            requirement_refs=("REQ-REPORT",),
        )
        output = publisher.publish()
        bundle = output.root / "bundles" / f"{output.output_id}-qa-evidence.zip"
        self.assertTrue(bundle.is_file())
        with zipfile.ZipFile(bundle) as archive:
            self.assertIn("reports/summary.json", archive.namelist())
        self.assertFalse((output.root / "project/reports/summary.json").exists())

    def test_repair_publication_without_patch_artifact_fails_closed(self) -> None:
        self.write("tests/test_repair.py", "def test_value():\n    assert 2 + 2 == 4\n")
        publisher = ArtifactPublisher(
            self.plan(revision="revision-repair", run_mode="repair")
        )
        publisher.register_file(
            "tests/test_repair.py",
            artifact_id="artifact-repair-test",
            category="test_source",
            role="unit_test",
            producer="test-generator-v1",
            requirement_refs=("REQ-REPAIR",),
            test_case_refs=("TC-REPAIR",),
        )
        output = publisher.publish()
        self.assertEqual("partial", output.status)
        self.assertFalse((output.root / "project").exists())
        self.assertFalse((output.root / "bundles").exists())

        self.write("unsupported.bin", "bounded\n")
        rejected = ArtifactPublisher(self.plan(revision="revision-other"))
        with self.assertRaises(ArtifactValidationError):
            rejected.register_file(
                "unsupported.bin",
                artifact_id="artifact-other",
                category="other",
                role="evidence",
                producer="generator",
                requirement_refs=("REQ-OTHER",),
            )

    def test_registration_enforces_record_and_aggregate_limits(self) -> None:
        self.write("tests/one.py", "def test_one():\n    assert 1 == 1\n")
        self.write("tests/two.py", "def test_two():\n    assert 2 == 2\n")
        publisher = ArtifactPublisher(self.plan(revision="revision-count-limit"))
        with mock.patch.object(artifact_module, "MAX_REGISTERED_ARTIFACTS", 1):
            publisher.register_file(
                "tests/one.py",
                artifact_id="artifact-one",
                category="test_source",
                role="unit_test",
                producer="generator",
                requirement_refs=("REQ-ONE",),
                test_case_refs=("TC-ONE",),
            )
            with self.assertRaises(ArtifactValidationError):
                publisher.register_file(
                    "tests/two.py",
                    artifact_id="artifact-two",
                    category="test_source",
                    role="unit_test",
                    producer="generator",
                    requirement_refs=("REQ-TWO",),
                    test_case_refs=("TC-TWO",),
                )

        aggregate = ArtifactPublisher(self.plan(revision="revision-byte-limit"))
        with mock.patch.object(artifact_module, "MAX_REGISTERED_ARTIFACT_BYTES", 8):
            with self.assertRaises(ArtifactValidationError):
                aggregate.register_file(
                    "tests/one.py",
                    artifact_id="artifact-too-large",
                    category="test_source",
                    role="unit_test",
                    producer="generator",
                    requirement_refs=("REQ-LIMIT",),
                    test_case_refs=("TC-LIMIT",),
                )

    def test_staging_inventory_is_descriptor_rooted_and_bounded(self) -> None:
        publisher = self.publisher_with_test(revision="revision-inventory-limit")
        (self.staging / "empty-extra").mkdir()
        with mock.patch.object(artifact_module, "MAX_STAGING_TREE_ENTRIES", 1):
            with self.assertRaises(ArtifactValidationError):
                publisher.validate()

    def test_bundle_limit_includes_content_manifest_bytes(self) -> None:
        publisher = self.publisher_with_test(revision="revision-bundle-overhead")
        payload_bytes = sum(record.size_bytes for record in publisher.records)
        with mock.patch.object(
            artifact_module, "MAX_BUNDLE_UNCOMPRESSED_BYTES", payload_bytes
        ):
            with self.assertRaises(ArtifactValidationError):
                publisher.build_bundle("tests-only")

    def test_both_mode_materializes_embedded_and_versioned_sidecar_files(self) -> None:
        output = self.publisher_with_test_for_mode(OutputMode.BOTH).publish()
        self.assertTrue((self.embedded / "tests/test_embedded.py").is_file())
        self.assertTrue((output.root / "project/tests/test_embedded.py").is_file())

    def test_embedded_mode_never_overwrites_an_existing_file(self) -> None:
        existing = self.embedded / "tests/test_embedded.py"
        existing.parent.mkdir(parents=True)
        existing.write_text("user-owned\n", encoding="utf-8")
        output = self.publisher_with_test_for_mode(OutputMode.EMBEDDED).publish()
        self.assertEqual("partial", output.status)
        self.assertEqual("user-owned\n", existing.read_text(encoding="utf-8"))

    def test_embedded_creation_race_never_overwrites_the_new_file(self) -> None:
        publisher = self.publisher_with_test_for_mode(OutputMode.EMBEDDED)
        destination = (self.embedded / "tests/test_embedded.py").resolve()
        real_install = artifact_module._install_embedded_file_atomic

        def create_destination_before_write(
            path: Path, data: bytes, **kwargs: object
        ) -> artifact_module._EmbeddedCreation:
            if path == destination and not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("racing-owner\n", encoding="utf-8")
            return real_install(path, data, **kwargs)

        with mock.patch.object(
            artifact_module,
            "_install_embedded_file_atomic",
            side_effect=create_destination_before_write,
        ):
            output = publisher.publish()
        self.assertEqual("partial", output.status)
        self.assertEqual("racing-owner\n", destination.read_text(encoding="utf-8"))

    def test_embedded_post_install_pin_failure_rolls_back_exact_file(self) -> None:
        publisher = self.publisher_with_test_for_mode(OutputMode.EMBEDDED)
        destination = self.embedded / "tests/test_embedded.py"
        real_digest = artifact_module._stable_file_digest
        calls = 0

        def fail_first_digest(*args: object, **kwargs: object):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ArtifactValidationError("injected post-install pin failure")
            return real_digest(*args, **kwargs)

        with mock.patch.object(
            artifact_module, "_stable_file_digest", side_effect=fail_first_digest
        ):
            output = publisher.publish()
        self.assertEqual("partial", output.status)
        self.assertFalse(destination.exists())

    def test_rollback_never_deletes_a_modified_embedded_file(self) -> None:
        publisher = self.publisher_with_test_for_mode(OutputMode.BOTH)
        destination = (self.embedded / "tests/test_embedded.py").resolve()

        def mutate_then_fail(_kind: str) -> tuple[bytes, str]:
            destination.write_text("modified-after-materialization\n", encoding="utf-8")
            raise ArtifactValidationError("injected bundle failure")

        with mock.patch.object(publisher, "build_bundle", side_effect=mutate_then_fail):
            output = publisher.publish()
        self.assertEqual("partial", output.status)
        self.assertEqual(
            "modified-after-materialization\n",
            destination.read_text(encoding="utf-8"),
        )

    def test_rollback_uses_the_pinned_parent_not_a_replacement_path(self) -> None:
        publisher = self.publisher_with_test_for_mode(OutputMode.BOTH)
        original_parent = self.embedded / "tests"
        displaced_parent = self.embedded / "tests-pinned-original"
        replacement = original_parent / "test_embedded.py"

        def replace_parent_then_fail(_kind: str) -> tuple[bytes, str]:
            original_parent.rename(displaced_parent)
            original_parent.mkdir()
            replacement.write_text("replacement-owner\n", encoding="utf-8")
            raise ArtifactValidationError("injected bundle failure")

        with mock.patch.object(
            publisher, "build_bundle", side_effect=replace_parent_then_fail
        ):
            output = publisher.publish()
        self.assertEqual(output.status, "partial")
        self.assertEqual(replacement.read_text(encoding="utf-8"), "replacement-owner\n")
        self.assertFalse((displaced_parent / "test_embedded.py").exists())

    def test_legal_hold_and_references_block_garbage_collection(self) -> None:
        publisher = self.publisher_with_test()
        output = publisher.publish()
        lifecycle = ArtifactLifecycleStore(
            Path(self.temporary.name) / "lifecycle.sqlite3", self.publication
        )
        lifecycle.register_output(output)
        lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        lifecycle.set_legal_hold(
            tenant_id="tenant-a", output_id=output.output_id, enabled=True
        )
        self.assertEqual(lifecycle.gc_candidates(tenant_id="tenant-a"), ())
        lifecycle.set_legal_hold(
            tenant_id="tenant-a", output_id=output.output_id, enabled=False
        )
        lifecycle.add_reference(
            tenant_id="tenant-a", output_id=output.output_id, reference_id="audit-1"
        )
        self.assertEqual(lifecycle.gc_candidates(tenant_id="tenant-a"), ())
        lifecycle.remove_reference(
            tenant_id="tenant-a", output_id=output.output_id, reference_id="audit-1"
        )
        self.assertEqual(
            lifecycle.collect_garbage(tenant_id="tenant-a", dry_run=True),
            (output.output_id,),
        )
        self.assertTrue(output.root.exists())

    def test_existing_final_output_is_never_replaced(self) -> None:
        first = self.publisher_with_test().publish()
        original_manifest = (
            first.root / "manifests/project-output-manifest.json"
        ).read_bytes()
        second = self.publisher_with_test()
        with self.assertRaises(PublicationError):
            second.publish(partial_on_failure=False)
        self.assertEqual(
            (first.root / "manifests/project-output-manifest.json").read_bytes(),
            original_manifest,
        )

    def test_final_output_creation_race_is_no_replace(self) -> None:
        publisher = self.publisher_with_test()
        real_rename = artifact_module._rename_no_replace

        def create_destination_before_rename(
            source: Path,
            destination: Path,
            *,
            expected_source_identity: tuple[int, int] | None = None,
            expected_source_snapshot: artifact_module._TreeSnapshot | None = None,
        ) -> None:
            destination.mkdir()
            real_rename(
                source,
                destination,
                expected_source_identity=expected_source_identity,
                expected_source_snapshot=expected_source_snapshot,
            )

        with mock.patch.object(
            artifact_module,
            "_rename_no_replace",
            side_effect=create_destination_before_rename,
        ):
            with self.assertRaises(PublicationError):
                publisher.publish(partial_on_failure=False)
        self.assertTrue(publisher.plan.final_root.is_dir())
        self.assertEqual(tuple(publisher.plan.final_root.iterdir()), ())

    def test_candidate_tree_is_exactly_verified_before_commit(self) -> None:
        publisher = self.publisher_with_test(revision="revision-candidate-extra")
        real_write = artifact_module._write_bytes_atomic

        def inject_extra(path: Path, data: bytes, mode: int = 0o644) -> None:
            real_write(path, data, mode)
            if path.name == "checksums.sha256":
                real_write(path.parents[1] / "unmanifested.txt", b"unexpected\n")

        with mock.patch.object(
            artifact_module, "_write_bytes_atomic", side_effect=inject_extra
        ), mock.patch.object(artifact_module, "_rename_no_replace") as rename:
            with self.assertRaises(PublicationError):
                publisher.publish(partial_on_failure=False)
        rename.assert_not_called()
        self.assertFalse(publisher.plan.final_root.exists())
        pending = tuple(
            publisher.plan.final_root.parent.glob(
                f".pending-{publisher.plan.output_id}-*"
            )
        )
        self.assertEqual(1, len(pending))
        self.assertEqual(
            b"unexpected\n", (pending[0] / "unmanifested.txt").read_bytes()
        )

    def test_atomic_write_unlink_failure_rolls_back_only_its_exact_inode(self) -> None:
        destination = self.publication / "atomic-unlink" / "output.bin"
        real_unlink = artifact_module.os.unlink
        injected = False
        temporary_unlinks: list[str] = []
        link_count_at_failure: int | None = None

        def fail_first_temporary_unlink(
            path: object, *args: object, **kwargs: object
        ) -> None:
            nonlocal injected, link_count_at_failure
            if isinstance(path, str) and ".tmp-" in path:
                temporary_unlinks.append(path)
                if not injected:
                    parent_descriptor = kwargs.get("dir_fd")
                    assert isinstance(parent_descriptor, int)
                    link_count_at_failure = os.stat(
                        path,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    ).st_nlink
                    injected = True
                    raise OSError("injected temporary unlink failure")
            real_unlink(path, *args, **kwargs)

        with mock.patch.object(
            artifact_module.os, "unlink", side_effect=fail_first_temporary_unlink
        ):
            with self.assertRaises(OSError):
                artifact_module._write_bytes_atomic(destination, b"owned\n")
        self.assertTrue(injected)
        self.assertEqual(link_count_at_failure, 2)
        self.assertGreaterEqual(len(temporary_unlinks), 2)
        self.assertEqual(temporary_unlinks[0], temporary_unlinks[1])
        self.assertFalse(destination.exists())
        self.assertEqual((), tuple(destination.parent.iterdir()))

    def test_atomic_write_directory_sync_failure_rolls_back_exact_output(self) -> None:
        destination = self.publication / "atomic-sync" / "output.bin"
        real_sync = artifact_module._fsync_directory_descriptor
        calls = 0

        def fail_first_directory_sync(descriptor: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("injected directory sync failure")
            real_sync(descriptor)

        with mock.patch.object(
            artifact_module,
            "_fsync_directory_descriptor",
            side_effect=fail_first_directory_sync,
        ):
            with self.assertRaises(OSError):
                artifact_module._write_bytes_atomic(destination, b"owned\n")
        self.assertGreaterEqual(calls, 2)
        self.assertFalse(destination.exists())
        self.assertEqual((), tuple(destination.parent.iterdir()))

    def test_unsupported_directory_sync_is_not_treated_as_durable(self) -> None:
        with mock.patch.object(
            artifact_module.os,
            "fsync",
            side_effect=OSError(
                artifact_module.errno.EINVAL,
                "directory fsync unsupported",
            ),
        ):
            with self.assertRaises(OSError):
                artifact_module._fsync_directory_descriptor(1)

    def test_descriptor_cleanup_rejects_file_replacement_at_final_identity_check(
        self,
    ) -> None:
        cleanup_parent = Path(self.temporary.name) / "cleanup-file-parent"
        cleanup_parent.mkdir(mode=0o700)
        cleanup_parent.chmod(0o700)
        cleanup_root = cleanup_parent / "candidate"
        cleanup_root.mkdir()
        owned_path = cleanup_root / "owned.txt"
        displaced_path = cleanup_root / "owned-verified-original.txt"
        owned_path.write_bytes(b"verified original\n")
        descriptors, snapshot = artifact_module._open_tree_snapshot(cleanup_root)
        artifact_module._close_descriptors(descriptors)
        real_assert_identity = artifact_module._assert_named_descriptor_identity
        file_identity_checks = 0
        replacement_path: Path | None = None

        def replace_before_identity_check(
            parent_descriptor: int,
            name: str,
            pinned_descriptor: int,
            *,
            device: int,
            inode: int,
            directory: bool,
            link_count: int | None = None,
        ) -> os.stat_result:
            nonlocal file_identity_checks, replacement_path
            if not directory:
                file_identity_checks += 1
            if file_identity_checks == 3 and replacement_path is None:
                replacement_path = cleanup_root / name
                replacement_path.rename(displaced_path)
                replacement_path.write_bytes(b"replacement owner data\n")
            return real_assert_identity(
                parent_descriptor,
                name,
                pinned_descriptor,
                device=device,
                inode=inode,
                directory=directory,
                link_count=link_count,
            )

        with mock.patch.object(
            artifact_module,
            "_assert_named_descriptor_identity",
            side_effect=replace_before_identity_check,
        ):
            with self.assertRaises(LifecycleError):
                artifact_module._delete_directory_tree_nofollow(
                    cleanup_parent,
                    cleanup_root.name,
                    expected=snapshot,
                )
        self.assertEqual(file_identity_checks, 3)
        assert replacement_path is not None
        self.assertTrue(replacement_path.name.startswith(".elmos-delete-"))
        self.assertEqual(replacement_path.read_bytes(), b"replacement owner data\n")
        self.assertEqual(displaced_path.read_bytes(), b"verified original\n")
        self.assertFalse(owned_path.exists())

    def test_descriptor_cleanup_rejects_final_window_hardlink_alias(self) -> None:
        cleanup_parent = Path(self.temporary.name) / "cleanup-hardlink-parent"
        cleanup_parent.mkdir(mode=0o700)
        cleanup_parent.chmod(0o700)
        cleanup_root = cleanup_parent / "candidate"
        cleanup_root.mkdir()
        owned_path = cleanup_root / "owned.txt"
        displaced_path = cleanup_root / "owned-verified-original.txt"
        owned_path.write_bytes(b"verified original\n")
        descriptors, snapshot = artifact_module._open_tree_snapshot(cleanup_root)
        artifact_module._close_descriptors(descriptors)
        real_assert_identity = artifact_module._assert_named_descriptor_identity
        file_identity_checks = 0
        alias_path: Path | None = None

        def alias_before_identity_check(
            parent_descriptor: int,
            name: str,
            pinned_descriptor: int,
            *,
            device: int,
            inode: int,
            directory: bool,
            link_count: int | None = None,
        ) -> os.stat_result:
            nonlocal file_identity_checks, alias_path
            if not directory:
                file_identity_checks += 1
            if file_identity_checks == 3 and alias_path is None:
                alias_path = cleanup_root / name
                alias_path.rename(displaced_path)
                os.link(displaced_path, alias_path)
            return real_assert_identity(
                parent_descriptor,
                name,
                pinned_descriptor,
                device=device,
                inode=inode,
                directory=directory,
                link_count=link_count,
            )

        with mock.patch.object(
            artifact_module,
            "_assert_named_descriptor_identity",
            side_effect=alias_before_identity_check,
        ):
            with self.assertRaises(LifecycleError):
                artifact_module._delete_directory_tree_nofollow(
                    cleanup_parent,
                    cleanup_root.name,
                    expected=snapshot,
                )
        self.assertEqual(file_identity_checks, 3)
        assert alias_path is not None
        self.assertEqual(alias_path.stat().st_ino, displaced_path.stat().st_ino)
        self.assertEqual(alias_path.stat().st_nlink, 2)
        self.assertEqual(alias_path.read_bytes(), b"verified original\n")

    def test_descriptor_cleanup_rejects_root_replacement_at_final_identity_check(
        self,
    ) -> None:
        cleanup_parent = Path(self.temporary.name) / "cleanup-root-parent"
        cleanup_parent.mkdir(mode=0o700)
        cleanup_parent.chmod(0o700)
        cleanup_root = cleanup_parent / "candidate"
        displaced_root = cleanup_parent / "candidate-verified-original"
        cleanup_root.mkdir()
        descriptors, snapshot = artifact_module._open_tree_snapshot(cleanup_root)
        artifact_module._close_descriptors(descriptors)
        real_assert_identity = artifact_module._assert_named_descriptor_identity
        injected = False

        def replace_before_identity_check(
            parent_descriptor: int,
            name: str,
            pinned_descriptor: int,
            *,
            device: int,
            inode: int,
            directory: bool,
            link_count: int | None = None,
        ) -> os.stat_result:
            nonlocal injected
            if name == cleanup_root.name and directory and not injected:
                injected = True
                cleanup_root.rename(displaced_root)
                cleanup_root.mkdir()
                (cleanup_root / "owner-data.txt").write_bytes(b"do not delete\n")
            return real_assert_identity(
                parent_descriptor,
                name,
                pinned_descriptor,
                device=device,
                inode=inode,
                directory=directory,
                link_count=link_count,
            )

        with mock.patch.object(
            artifact_module,
            "_assert_named_descriptor_identity",
            side_effect=replace_before_identity_check,
        ):
            with self.assertRaises(LifecycleError):
                artifact_module._delete_directory_tree_nofollow(
                    cleanup_parent,
                    cleanup_root.name,
                    expected=snapshot,
                )
        self.assertTrue(injected)
        self.assertEqual(
            (cleanup_root / "owner-data.txt").read_bytes(), b"do not delete\n"
        )
        self.assertTrue(displaced_root.is_dir())

    def test_candidate_cleanup_never_adopts_a_replacement_path(self) -> None:
        publisher = self.publisher_with_test(revision="revision-candidate-replaced")
        real_write = artifact_module._write_bytes_atomic
        replacement_root: Path | None = None
        displaced_root: Path | None = None

        def replace_candidate_then_fail(
            path: Path, data: bytes, mode: int = 0o644
        ) -> None:
            nonlocal replacement_root, displaced_root
            candidate = path
            while candidate != candidate.parent and not candidate.name.startswith(".pending-"):
                candidate = candidate.parent
            if candidate.name.startswith(".pending-") and replacement_root is None:
                replacement_root = candidate
                displaced_root = candidate.with_name(candidate.name + "-pinned-original")
                candidate.rename(displaced_root)
                candidate.mkdir(mode=0o700)
                (candidate / "owner-data.txt").write_text(
                    "do not delete\n", encoding="utf-8"
                )
                raise ArtifactValidationError("injected candidate path replacement")
            real_write(path, data, mode)

        with mock.patch.object(
            artifact_module, "_write_bytes_atomic", side_effect=replace_candidate_then_fail
        ):
            with self.assertRaises(PublicationError):
                publisher.publish(partial_on_failure=False)
        assert replacement_root is not None
        assert displaced_root is not None
        self.assertEqual(
            "do not delete\n",
            (replacement_root / "owner-data.txt").read_text(encoding="utf-8"),
        )
        self.assertTrue(displaced_root.is_dir())

    def test_success_path_performs_no_fallible_final_tree_read_after_rename(self) -> None:
        publisher = self.publisher_with_test(revision="revision-no-post-read")
        real_read = artifact_module._read_regular_file_nofollow
        real_rename = artifact_module._rename_no_replace
        renamed = False

        def guarded_read(*args: object, **kwargs: object) -> bytes:
            if renamed:
                raise AssertionError("final output was read after commit")
            return real_read(*args, **kwargs)

        def mark_rename(
            source: Path,
            destination: Path,
            *,
            expected_source_identity: tuple[int, int] | None = None,
            expected_source_snapshot: artifact_module._TreeSnapshot | None = None,
        ) -> bool:
            nonlocal renamed
            durable = real_rename(
                source,
                destination,
                expected_source_identity=expected_source_identity,
                expected_source_snapshot=expected_source_snapshot,
            )
            renamed = True
            return durable

        with mock.patch.object(
            artifact_module, "_read_regular_file_nofollow", side_effect=guarded_read
        ), mock.patch.object(
            artifact_module, "_rename_no_replace", side_effect=mark_rename
        ):
            output = publisher.publish(partial_on_failure=False)
        self.assertTrue(renamed)
        self.assertEqual(output.status, "verified")
        self.assertEqual(output.durability_status, "DURABLE")

    def test_post_rename_directory_sync_failure_does_not_reverse_commit(self) -> None:
        publisher = self.publisher_with_test(revision="revision-post-rename-sync")
        real_renameat = artifact_module._renameat_no_replace
        real_fsync = artifact_module._fsync_directory_descriptor
        renamed = False

        def mark_commit(
            source_parent: int,
            source_name: str,
            destination_parent: int,
            destination_name: str,
        ) -> None:
            nonlocal renamed
            real_renameat(
                source_parent,
                source_name,
                destination_parent,
                destination_name,
            )
            # Descriptor-rooted candidate cleanup also uses no-replace renames
            # for deletion tombstones.  Arm the fsync failure only for the
            # actual publication namespace commit.
            if (
                source_name.startswith(f".pending-{publisher.plan.output_id}-")
                and destination_name == publisher.plan.final_root.name
            ):
                renamed = True

        def fail_only_after_commit(descriptor: int) -> None:
            if renamed:
                raise OSError("injected post-commit sync failure")
            real_fsync(descriptor)

        with mock.patch.object(
            artifact_module, "_renameat_no_replace", side_effect=mark_commit
        ), mock.patch.object(
            artifact_module,
            "_fsync_directory_descriptor",
            side_effect=fail_only_after_commit,
        ):
            output = publisher.publish(partial_on_failure=False)
        self.assertTrue(renamed)
        self.assertEqual("verified", output.status)
        self.assertEqual(
            "COMMITTED_DURABILITY_UNKNOWN", output.durability_status
        )
        self.assertTrue(output.root.is_dir())

    def test_commit_rechecks_the_complete_candidate_tree(self) -> None:
        publisher = self.publisher_with_test(revision="revision-precommit-recheck")
        real_rename = artifact_module._rename_no_replace

        def mutate_then_rename(
            source: Path,
            destination: Path,
            **kwargs: object,
        ) -> None:
            manifest = source / "manifests/project-output-manifest.json"
            manifest.write_bytes(manifest.read_bytes() + b" ")
            real_rename(source, destination, **kwargs)

        with mock.patch.object(
            artifact_module, "_rename_no_replace", side_effect=mutate_then_rename
        ):
            with self.assertRaises(PublicationError):
                publisher.publish(partial_on_failure=False)
        self.assertFalse(publisher.plan.final_root.exists())

    def test_lifecycle_registration_verifies_manifest_digest(self) -> None:
        output = self.publisher_with_test().publish()
        lifecycle = ArtifactLifecycleStore(
            Path(self.temporary.name) / "manifest-lifecycle.sqlite3", self.publication
        )
        with self.assertRaises(LifecycleError):
            lifecycle.register_output(replace(output, manifest_digest="f" * 64))
        manifest_path = output.root / "manifests/project-output-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["certified"] = True
        forged_bytes = json.dumps(manifest, sort_keys=True).encode("utf-8")
        manifest_path.write_bytes(forged_bytes)
        with self.assertRaises(LifecycleError):
            lifecycle.register_output(
                replace(output, manifest_digest=artifact_module.sha256_bytes(forged_bytes))
            )

    def lifecycle_row(
        self, lifecycle: ArtifactLifecycleStore, output_id: str
    ) -> sqlite3.Row:
        with lifecycle._connect() as connection:
            row = connection.execute(
                "SELECT * FROM lifecycle_outputs WHERE tenant_id = ? AND output_id = ?",
                ("tenant-a", output_id),
            ).fetchone()
        assert row is not None
        return row

    def expire_collection_lease(
        self, lifecycle: ArtifactLifecycleStore, output_id: str
    ) -> None:
        with lifecycle._connect() as connection:
            rowcount = connection.execute(
                "UPDATE lifecycle_outputs SET collection_lease_until = ? "
                "WHERE tenant_id = ? AND output_id = ? AND state = 'collecting'",
                ("1970-01-01T00:00:00Z", "tenant-a", output_id),
            ).rowcount
        self.assertEqual(rowcount, 1)

    def assert_collected(
        self, lifecycle: ArtifactLifecycleStore, output_id: str
    ) -> None:
        row = self.lifecycle_row(lifecycle, output_id)
        self.assertEqual(row["state"], "collected")
        for field in (
            "collecting_from",
            "quarantine_path",
            "quarantine_snapshot",
            "quarantine_snapshot_digest",
            "collection_owner",
            "collection_lease_until",
            "collection_phase",
        ):
            self.assertIsNone(row[field])
        self.assertEqual(row["quarantine_verified"], 0)

    def test_lifecycle_registration_verifies_the_published_envelope(self) -> None:
        output = self.publisher_with_test(revision="revision-envelope").publish()
        lifecycle = ArtifactLifecycleStore(
            Path(self.temporary.name) / "envelope-lifecycle.sqlite3", self.publication
        )
        with self.assertRaises(LifecycleError):
            lifecycle.register_output(replace(output, bundle_digests={}))
        with self.assertRaises(LifecycleError):
            lifecycle.register_output(replace(output, failure="invented failure"))
        with self.assertRaises(LifecycleError):
            lifecycle.register_output(
                replace(output, durability_status="COMMITTED_DURABILITY_UNKNOWN")
            )

        failure_publisher = self.publisher_with_test(revision="revision-failure-envelope")
        self.write("untracked-failure-envelope.txt", "force partial output\n")
        failed = failure_publisher.publish()
        self.assertEqual(failed.status, "partial")
        assert failed.failure is not None
        self.assertEqual(failed.failure["type"], "ArtifactValidationError")
        lifecycle.register_output(failed)
        with self.assertRaises(LifecycleError):
            lifecycle.register_output(
                replace(
                    failed,
                    failure={
                        "type": "DifferentFailureType",
                        "message": failed.failure["message"],
                    },
                )
            )

    def test_lifecycle_rejects_extras_checksums_and_sidecar_byte_drift(self) -> None:
        scenarios = ("extra", "checksums", "sidecar")
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                output = self.publisher_with_test(
                    revision=f"revision-lifecycle-{scenario}"
                ).publish()
                lifecycle = ArtifactLifecycleStore(
                    Path(self.temporary.name) / f"lifecycle-{scenario}.sqlite3",
                    self.publication,
                )
                checksum_path = output.root / "manifests/checksums.sha256"
                if scenario == "extra":
                    (output.root / "unmanifested.txt").write_text(
                        "unexpected\n", encoding="utf-8"
                    )
                elif scenario == "checksums":
                    checksum_path.write_text("0" * 64 + "  forged.txt\n", encoding="utf-8")
                else:
                    sidecar = output.root / "project/tests/test_math.py"
                    sidecar.write_text(
                        "def test_add():\n    assert 5 == 6\n", encoding="utf-8"
                    )
                    lines = []
                    for path in sorted(output.root.rglob("*")):
                        if path.is_file() and path != checksum_path:
                            lines.append(
                                f"{artifact_module.sha256_file(path)}  "
                                f"{path.relative_to(output.root).as_posix()}"
                            )
                    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                with self.assertRaises(LifecycleError):
                    lifecycle.register_output(output)

    def test_gc_refuses_a_replaced_output_directory(self) -> None:
        output = self.publisher_with_test().publish()
        lifecycle = ArtifactLifecycleStore(
            Path(self.temporary.name) / "replacement-lifecycle.sqlite3", self.publication
        )
        lifecycle.register_output(output)
        lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        shutil.rmtree(output.root)
        output.root.mkdir(parents=True)
        replacement = output.root / "owner-data.txt"
        replacement.write_text("do not delete\n", encoding="utf-8")
        with self.assertRaises(LifecycleError):
            lifecycle.collect_garbage(tenant_id="tenant-a", dry_run=False)
        self.assertEqual(replacement.read_text(encoding="utf-8"), "do not delete\n")

    def test_collecting_quarantine_recovers_after_restart(self) -> None:
        output = self.publisher_with_test().publish()
        database = Path(self.temporary.name) / "recovery-lifecycle.sqlite3"
        lifecycle = ArtifactLifecycleStore(database, self.publication)
        lifecycle.register_output(output)
        lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        with mock.patch.object(
            artifact_module,
            "_delete_directory_tree_nofollow",
            side_effect=LifecycleError("injected failure"),
        ):
            with self.assertRaises(LifecycleError):
                lifecycle.collect_garbage(tenant_id="tenant-a", dry_run=False)
        self.assertFalse(output.root.exists())
        self.expire_collection_lease(lifecycle, output.output_id)
        reopened = ArtifactLifecycleStore(database, self.publication)
        self.assert_collected(reopened, output.output_id)
        self.assertEqual(reopened.gc_candidates(tenant_id="tenant-a"), ())
        self.assertFalse(output.root.exists())

    def test_gc_descriptor_delete_refuses_a_quarantine_path_replacement(self) -> None:
        output = self.publisher_with_test(revision="revision-gc-race").publish()
        lifecycle = ArtifactLifecycleStore(
            Path(self.temporary.name) / "gc-race-lifecycle.sqlite3", self.publication
        )
        lifecycle.register_output(output)
        lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        real_delete = artifact_module._delete_directory_tree_nofollow
        replacement_path: Path | None = None
        displaced_path: Path | None = None

        def replace_before_delete(
            parent: Path,
            name: str,
            *,
            expected: artifact_module._TreeSnapshot,
            allow_missing: bool = False,
        ) -> None:
            nonlocal replacement_path, displaced_path
            replacement_path = parent / name
            displaced_path = parent / f"{name}-verified-original"
            replacement_path.rename(displaced_path)
            replacement_path.mkdir()
            (replacement_path / "owner-data.txt").write_text(
                "do not delete\n", encoding="utf-8"
            )
            real_delete(parent, name, expected=expected, allow_missing=allow_missing)

        with mock.patch.object(
            artifact_module,
            "_delete_directory_tree_nofollow",
            side_effect=replace_before_delete,
        ):
            with self.assertRaises(LifecycleError):
                lifecycle.collect_garbage(tenant_id="tenant-a", dry_run=False)
        assert replacement_path is not None
        assert displaced_path is not None
        self.assertEqual(
            (replacement_path / "owner-data.txt").read_text(encoding="utf-8"),
            "do not delete\n",
        )
        self.assertTrue(displaced_path.is_dir())

    def test_gc_resumes_after_a_file_was_deleted(self) -> None:
        output = self.publisher_with_test(revision="revision-gc-partial").publish()
        database = Path(self.temporary.name) / "partial-gc-lifecycle.sqlite3"
        lifecycle = ArtifactLifecycleStore(database, self.publication)
        lifecycle.register_output(output)
        lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        real_unlink = artifact_module.os.unlink
        injected = False

        def delete_then_fail(path: object, *args: object, **kwargs: object) -> None:
            nonlocal injected
            real_unlink(path, *args, **kwargs)
            if isinstance(path, str) and path.startswith(".elmos-delete-") and not injected:
                injected = True
                raise OSError("injected crash after deletion")

        with mock.patch.object(artifact_module.os, "unlink", side_effect=delete_then_fail):
            with self.assertRaises(LifecycleError):
                lifecycle.collect_garbage(tenant_id="tenant-a", dry_run=False)
        self.assertTrue(injected)
        self.expire_collection_lease(lifecycle, output.output_id)
        reopened = ArtifactLifecycleStore(database, self.publication)
        self.assert_collected(reopened, output.output_id)
        self.assertEqual(reopened.gc_candidates(tenant_id="tenant-a"), ())
        self.assertFalse(output.root.exists())

    def test_legacy_lifecycle_layout_fails_closed(self) -> None:
        database = Path(self.temporary.name) / "legacy-layout.sqlite3"
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE lifecycle_outputs (
                    output_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    output_path TEXT NOT NULL,
                    manifest_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    legal_hold INTEGER NOT NULL DEFAULT 0,
                    superseded_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE lifecycle_references (
                    output_id TEXT NOT NULL,
                    reference_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (output_id, reference_id),
                    FOREIGN KEY (output_id) REFERENCES lifecycle_outputs (output_id)
                );
                """
            )
            before = connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_schema "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            ).fetchall()
        with self.assertRaises(LifecycleError):
            ArtifactLifecycleStore(database, self.publication)
        with closing(sqlite3.connect(database)) as connection, connection:
            after = connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_schema "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            ).fetchall()
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(lifecycle_outputs)")
            }
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(after, before)
        self.assertNotIn("layout_version", columns)
        self.assertEqual(version, 0)

    def test_fresh_lifecycle_schema_has_exact_version_fingerprint_and_composite_fk(
        self,
    ) -> None:
        lifecycle = ArtifactLifecycleStore(
            Path(self.temporary.name) / "fresh-layout.sqlite3", self.publication
        )
        with lifecycle._connect() as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                artifact_module.LIFECYCLE_SCHEMA_VERSION,
            )
            self.assertEqual(
                lifecycle._physical_schema_fingerprint(connection),
                lifecycle._expected_schema_fingerprint(),
            )
            foreign_keys = connection.execute(
                "PRAGMA foreign_key_list(lifecycle_references)"
            ).fetchall()
        self.assertEqual(
            {(row["from"], row["to"]) for row in foreign_keys},
            {("tenant_id", "tenant_id"), ("output_id", "output_id")},
        )
        self.assertIn(
            "length(quarantine_snapshot) <= "
            f"{artifact_module.MAX_GC_SNAPSHOT_BYTES}",
            ArtifactLifecycleStore._SCHEMA_OUTPUTS_SQL,
        )

    def test_lifecycle_candidate_and_recovery_queries_are_bounded(self) -> None:
        database = Path(self.temporary.name) / "bounded-lifecycle.sqlite3"
        lifecycle = ArtifactLifecycleStore(database, self.publication)
        outputs = (
            self.publisher_with_test(revision="revision-bounded-a").publish(),
            self.publisher_with_test(revision="revision-bounded-b").publish(),
        )
        for output in outputs:
            lifecycle.register_output(output)
            lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        with mock.patch.object(artifact_module, "LIFECYCLE_PAGE_SIZE", 1):
            self.assertEqual(
                lifecycle.gc_candidates(tenant_id="tenant-a"),
                tuple(sorted(output.output_id for output in outputs)),
            )
        with mock.patch.object(artifact_module, "LIFECYCLE_PAGE_SIZE", 1), mock.patch.object(
            artifact_module, "MAX_LIFECYCLE_RESULTS", 1
        ):
            with self.assertRaises(LifecycleError):
                lifecycle.gc_candidates(tenant_id="tenant-a")

        with lifecycle._connect() as connection:
            for index, output in enumerate(outputs):
                quarantine_path = lifecycle._quarantine_path(
                    tenant_id=output.tenant_id,
                    output_id=output.output_id,
                    manifest_digest=output.manifest_digest,
                )
                connection.execute(
                    "UPDATE lifecycle_outputs SET state = 'collecting', "
                    "collecting_from = 'stale', quarantine_path = ?, "
                    "collection_owner = ?, collection_lease_until = ?, "
                    "collection_phase = 'prepared' "
                    "WHERE tenant_id = ? AND output_id = ?",
                    (
                        str(quarantine_path),
                        f"gc-operation-{index:032x}",
                        artifact_module._utc_after(60),
                        output.tenant_id,
                        output.output_id,
                    ),
                )
        with mock.patch.object(artifact_module, "MAX_LIFECYCLE_RESULTS", 1):
            with self.assertRaises(LifecycleError):
                ArtifactLifecycleStore(database, self.publication)

    def test_runtime_rejects_an_oversized_database_snapshot_without_loading_it(
        self,
    ) -> None:
        output = self.publisher_with_test(revision="revision-db-snapshot-bound").publish()
        database = Path(self.temporary.name) / "db-snapshot-bound.sqlite3"
        lifecycle = ArtifactLifecycleStore(database, self.publication)
        lifecycle.register_output(output)
        lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        payload = b"123456789"
        quarantine_path = lifecycle._quarantine_path(
            tenant_id=output.tenant_id,
            output_id=output.output_id,
            manifest_digest=output.manifest_digest,
        )
        with lifecycle._connect() as connection:
            connection.execute(
                "UPDATE lifecycle_outputs SET state = 'collecting', "
                "collecting_from = 'stale', quarantine_path = ?, "
                "quarantine_verified = 1, quarantine_snapshot = ?, "
                "quarantine_snapshot_digest = ?, collection_owner = ?, "
                "collection_lease_until = ?, collection_phase = 'verified' "
                "WHERE tenant_id = ? AND output_id = ?",
                (
                    str(quarantine_path),
                    payload,
                    artifact_module.sha256_bytes(payload),
                    "gc-operation-" + "a" * 32,
                    artifact_module._utc_after(60),
                    output.tenant_id,
                    output.output_id,
                ),
            )
        with mock.patch.object(artifact_module, "MAX_GC_SNAPSHOT_BYTES", 8):
            with self.assertRaises(LifecycleError):
                ArtifactLifecycleStore(database, self.publication)

    def test_fresh_schema_initialization_rolls_back_atomically(self) -> None:
        database = Path(self.temporary.name) / "atomic-layout.sqlite3"

        def fail_after_first_table(connection: sqlite3.Connection) -> None:
            connection.execute(ArtifactLifecycleStore._SCHEMA_METADATA_SQL)
            raise sqlite3.OperationalError("injected schema migration failure")

        with mock.patch.object(
            ArtifactLifecycleStore,
            "_create_current_schema",
            side_effect=fail_after_first_table,
        ):
            with self.assertRaises(LifecycleError):
                ArtifactLifecycleStore(database, self.publication)
        with closing(sqlite3.connect(database)) as connection, connection:
            objects = connection.execute(
                "SELECT name FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
            ).fetchall()
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(objects, [])
        self.assertEqual(version, 0)

    def test_unverified_double_path_loss_remains_unknown(self) -> None:
        output = self.publisher_with_test(revision="revision-gc-unknown-loss").publish()
        database = Path(self.temporary.name) / "unknown-loss.sqlite3"
        lifecycle = ArtifactLifecycleStore(database, self.publication)
        lifecycle.register_output(output)
        lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        real_verify = lifecycle._verify_row_path
        removed = False

        def remove_before_verification(
            row: sqlite3.Row, path: Path, *, normal_path: bool
        ) -> artifact_module._TreeSnapshot:
            nonlocal removed
            if normal_path and not removed:
                removed = True
                shutil.rmtree(path)
                raise LifecycleError("injected loss before quarantine verification")
            return real_verify(row, path, normal_path=normal_path)

        with mock.patch.object(
            lifecycle, "_verify_row_path", side_effect=remove_before_verification
        ):
            with self.assertRaises(LifecycleError):
                lifecycle.collect_garbage(tenant_id="tenant-a", dry_run=False)
        self.assertTrue(removed)
        row = self.lifecycle_row(lifecycle, output.output_id)
        self.assertEqual(row["state"], "collecting")
        self.assertEqual(row["collection_phase"], "prepared")
        self.assertEqual(row["quarantine_verified"], 0)
        self.expire_collection_lease(lifecycle, output.output_id)
        with self.assertRaises(LifecycleError):
            ArtifactLifecycleStore(database, self.publication)
        row = self.lifecycle_row(lifecycle, output.output_id)
        self.assertEqual(row["state"], "collecting")
        self.assertEqual(row["quarantine_verified"], 0)

    def test_gc_envelope_is_bound_to_the_exact_row_and_manifest(self) -> None:
        output = self.publisher_with_test(revision="revision-gc-envelope").publish()
        database = Path(self.temporary.name) / "gc-envelope.sqlite3"
        lifecycle = ArtifactLifecycleStore(database, self.publication)
        lifecycle.register_output(output)
        lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        with mock.patch.object(
            artifact_module,
            "_delete_directory_tree_nofollow",
            side_effect=LifecycleError("retain verified quarantine"),
        ):
            with self.assertRaises(LifecycleError):
                lifecycle.collect_garbage(tenant_id="tenant-a", dry_run=False)
        row = self.lifecycle_row(lifecycle, output.output_id)
        original_quarantine_path = str(row["quarantine_path"])
        with lifecycle._connect() as connection:
            connection.execute(
                "UPDATE lifecycle_outputs SET quarantine_path = ? "
                "WHERE tenant_id = ? AND output_id = ?",
                (
                    str(lifecycle.quarantine_root / "gc-wrong-row-binding"),
                    "tenant-a",
                    output.output_id,
                ),
            )
        with self.assertRaises(LifecycleError):
            lifecycle._row_quarantine_path(self.lifecycle_row(lifecycle, output.output_id))
        with lifecycle._connect() as connection:
            connection.execute(
                "UPDATE lifecycle_outputs SET quarantine_path = ? "
                "WHERE tenant_id = ? AND output_id = ?",
                (original_quarantine_path, "tenant-a", output.output_id),
            )
        row = self.lifecycle_row(lifecycle, output.output_id)
        envelope = json.loads(bytes(row["quarantine_snapshot"]).decode("utf-8"))
        with self.assertRaises(LifecycleError):
            artifact_module._gc_snapshot_envelope_from_bytes(
                bytes(row["quarantine_snapshot"]) + b" ",
                tenant_id=output.tenant_id,
                output_id=output.output_id,
                project_id=output.project_id,
                revision_id=output.revision_id,
                run_id=output.run_id,
                manifest_digest=output.manifest_digest,
                quarantine_name=Path(original_quarantine_path).name,
            )
        manifest_forgery = json.loads(bytes(row["quarantine_snapshot"]).decode("utf-8"))
        for file_row in manifest_forgery["tree"]["files"]:
            if file_row["path"] == "manifests/project-output-manifest.json":
                file_row["sha256"] = "f" * 64
        forged_tree = artifact_module.canonical_json_bytes(manifest_forgery["tree"])
        manifest_forgery["tree_sha256"] = artifact_module.sha256_bytes(forged_tree)
        forged_manifest_envelope = artifact_module.canonical_json_bytes(manifest_forgery)
        with self.assertRaises(LifecycleError):
            artifact_module._gc_snapshot_envelope_from_bytes(
                forged_manifest_envelope,
                tenant_id=output.tenant_id,
                output_id=output.output_id,
                project_id=output.project_id,
                revision_id=output.revision_id,
                run_id=output.run_id,
                manifest_digest=output.manifest_digest,
                quarantine_name=Path(original_quarantine_path).name,
            )
        envelope["project_id"] = "other-project"
        forged = artifact_module.canonical_json_bytes(envelope)
        with lifecycle._connect() as connection:
            connection.execute(
                "UPDATE lifecycle_outputs SET quarantine_snapshot = ?, "
                "quarantine_snapshot_digest = ?, collection_lease_until = ? "
                "WHERE tenant_id = ? AND output_id = ?",
                (
                    forged,
                    artifact_module.sha256_bytes(forged),
                    "1970-01-01T00:00:00Z",
                    "tenant-a",
                    output.output_id,
                ),
            )
        with self.assertRaises(LifecycleError):
            ArtifactLifecycleStore(database, self.publication)
        self.assertTrue(Path(row["quarantine_path"]).is_dir())

    def test_gc_snapshot_rejects_an_oversized_blob_before_parsing(self) -> None:
        with mock.patch.object(artifact_module, "MAX_GC_SNAPSHOT_BYTES", 8):
            with self.assertRaises(LifecycleError):
                artifact_module._tree_snapshot_from_bytes(b"{" + b" " * 8)

    def test_gc_fence_prevents_recovery_even_if_the_lease_expires(self) -> None:
        output = self.publisher_with_test(revision="revision-gc-two-stores").publish()
        database = Path(self.temporary.name) / "two-stores.sqlite3"
        lifecycle = ArtifactLifecycleStore(database, self.publication)
        lifecycle.register_output(output)
        lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        real_verify = lifecycle._verify_row_path
        interleaved = False

        def open_second_store(
            row: sqlite3.Row, path: Path, *, normal_path: bool
        ) -> artifact_module._TreeSnapshot:
            nonlocal interleaved
            if normal_path and not interleaved:
                interleaved = True
                active_owner = str(row["collection_owner"])
                self.assertRegex(active_owner, r"^gc-operation-[0-9a-f]{32}$")
                self.expire_collection_lease(lifecycle, output.output_id)
                self.assertEqual(lifecycle.recover_collecting(), ())
                second = ArtifactLifecycleStore(database, self.publication)
                active = self.lifecycle_row(second, output.output_id)
                self.assertEqual(active["state"], "collecting")
                self.assertEqual(active["collection_phase"], "prepared")
                self.assertEqual(active["collection_owner"], active_owner)
                self.assertTrue(output.root.is_dir())
            return real_verify(row, path, normal_path=normal_path)

        with mock.patch.object(
            lifecycle, "_verify_row_path", side_effect=open_second_store
        ):
            self.assertEqual(
                lifecycle.collect_garbage(tenant_id="tenant-a", dry_run=False),
                (output.output_id,),
            )
        self.assertTrue(interleaved)
        self.assert_collected(lifecycle, output.output_id)
        self.assertFalse(output.root.exists())
        self.assertEqual(
            tuple(
                path
                for path in lifecycle.quarantine_root.iterdir()
                if path.name.startswith("gc-")
            ),
            (),
        )

    def test_gc_fence_rejects_a_hardlinked_lock_entry(self) -> None:
        lifecycle = ArtifactLifecycleStore(
            Path(self.temporary.name) / "hardlinked-fence.sqlite3", self.publication
        )
        lock_path = lifecycle.quarantine_root / lifecycle._FENCE_FILE
        os.link(lock_path, lifecycle.quarantine_root / "hardlinked-fence-copy")
        with self.assertRaises(LifecycleError):
            lifecycle.recover_collecting()

    def test_replaced_gc_fence_blocks_the_next_namespace_mutation(self) -> None:
        output = self.publisher_with_test(revision="revision-gc-replaced-fence").publish()
        lifecycle = ArtifactLifecycleStore(
            Path(self.temporary.name) / "replaced-fence.sqlite3", self.publication
        )
        lifecycle.register_output(output)
        lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        quarantine_path = lifecycle._quarantine_path(
            tenant_id=output.tenant_id,
            output_id=output.output_id,
            manifest_digest=output.manifest_digest,
        )
        real_verify = lifecycle._verify_row_path
        replaced = False

        def replace_after_verification(
            row: sqlite3.Row, path: Path, *, normal_path: bool
        ) -> artifact_module._TreeSnapshot:
            nonlocal replaced
            snapshot = real_verify(row, path, normal_path=normal_path)
            if normal_path and not replaced:
                replaced = True
                lock_path = lifecycle.quarantine_root / lifecycle._FENCE_FILE
                lock_path.unlink()
                lock_path.write_bytes(b"replacement lock inode")
            return snapshot

        with mock.patch.object(
            lifecycle, "_verify_row_path", side_effect=replace_after_verification
        ):
            with self.assertRaises(LifecycleError):
                lifecycle.collect_garbage(tenant_id="tenant-a", dry_run=False)
        self.assertTrue(replaced)
        self.assertTrue(output.root.is_dir())
        self.assertFalse(quarantine_path.exists())
        row = self.lifecycle_row(lifecycle, output.output_id)
        self.assertEqual(row["state"], "stale")

    def test_expired_verification_owner_is_fenced_before_quarantine(self) -> None:
        output = self.publisher_with_test(revision="revision-gc-expired-verify").publish()
        database = Path(self.temporary.name) / "expired-verify.sqlite3"
        lifecycle = ArtifactLifecycleStore(database, self.publication)
        second = ArtifactLifecycleStore(database, self.publication)
        lifecycle.register_output(output)
        lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        real_verify = lifecycle._verify_row_path
        first_owner: str | None = None
        claimed_owner: str | None = None

        def claim_after_verification(
            row: sqlite3.Row, path: Path, *, normal_path: bool
        ) -> artifact_module._TreeSnapshot:
            nonlocal first_owner, claimed_owner
            snapshot = real_verify(row, path, normal_path=normal_path)
            if normal_path and claimed_owner is None:
                first_owner = str(row["collection_owner"])
                self.expire_collection_lease(lifecycle, output.output_id)
                claimed = second._claim_collecting(
                    tenant_id="tenant-a", output_id=output.output_id
                )
                assert claimed is not None
                claimed_owner = str(claimed["collection_owner"])
            return snapshot

        with mock.patch.object(
            lifecycle, "_verify_row_path", side_effect=claim_after_verification
        ):
            with self.assertRaises(LifecycleError):
                lifecycle.collect_garbage(tenant_id="tenant-a", dry_run=False)
        assert first_owner is not None
        assert claimed_owner is not None
        self.assertNotEqual(first_owner, claimed_owner)
        row = self.lifecycle_row(lifecycle, output.output_id)
        self.assertEqual(row["collection_owner"], claimed_owner)
        self.assertEqual(row["collection_phase"], "prepared")
        self.assertTrue(output.root.is_dir())
        self.assertFalse(Path(row["quarantine_path"]).exists())

        self.expire_collection_lease(lifecycle, output.output_id)
        reopened = ArtifactLifecycleStore(database, self.publication)
        recovered = self.lifecycle_row(reopened, output.output_id)
        self.assertEqual(recovered["state"], "stale")
        self.assertTrue(output.root.is_dir())

    def test_expired_deletion_owner_cannot_finalize_another_claim(self) -> None:
        output = self.publisher_with_test(revision="revision-gc-expired-delete").publish()
        database = Path(self.temporary.name) / "expired-delete.sqlite3"
        lifecycle = ArtifactLifecycleStore(database, self.publication)
        second = ArtifactLifecycleStore(database, self.publication)
        lifecycle.register_output(output)
        lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        real_delete = artifact_module._delete_directory_tree_nofollow
        claimed_owner: str | None = None

        def delete_then_claim(*args: object, **kwargs: object) -> None:
            nonlocal claimed_owner
            real_delete(*args, **kwargs)
            self.expire_collection_lease(lifecycle, output.output_id)
            claimed = second._claim_collecting(
                tenant_id="tenant-a", output_id=output.output_id
            )
            assert claimed is not None
            claimed_owner = str(claimed["collection_owner"])

        with mock.patch.object(
            artifact_module,
            "_delete_directory_tree_nofollow",
            side_effect=delete_then_claim,
        ):
            with self.assertRaises(LifecycleError):
                lifecycle.collect_garbage(tenant_id="tenant-a", dry_run=False)
        assert claimed_owner is not None
        row = self.lifecycle_row(lifecycle, output.output_id)
        self.assertEqual(row["state"], "collecting")
        self.assertEqual(row["collection_phase"], "verified")
        self.assertEqual(row["collection_owner"], claimed_owner)
        self.assertFalse(output.root.exists())
        self.assertFalse(Path(row["quarantine_path"]).exists())

        self.expire_collection_lease(lifecycle, output.output_id)
        reopened = ArtifactLifecycleStore(database, self.publication)
        self.assert_collected(reopened, output.output_id)

    def test_unknown_quarantine_rename_durability_never_collects(self) -> None:
        output = self.publisher_with_test(revision="revision-gc-unknown-sync").publish()
        lifecycle = ArtifactLifecycleStore(
            Path(self.temporary.name) / "unknown-sync.sqlite3", self.publication
        )
        lifecycle.register_output(output)
        lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        real_rename = artifact_module._rename_no_replace

        def commit_without_durability(*args: object, **kwargs: object) -> bool:
            real_rename(*args, **kwargs)
            return False

        with mock.patch.object(
            artifact_module,
            "_rename_no_replace",
            side_effect=commit_without_durability,
        ):
            with self.assertRaises(LifecycleError):
                lifecycle.collect_garbage(tenant_id="tenant-a", dry_run=False)
        row = self.lifecycle_row(lifecycle, output.output_id)
        self.assertEqual(row["state"], "collecting")
        self.assertEqual(row["collection_phase"], "prepared")
        self.assertEqual(row["quarantine_verified"], 0)
        self.assertFalse(output.root.exists())
        self.assertTrue(Path(row["quarantine_path"]).is_dir())

    def test_unknown_restore_durability_recovers_to_the_prior_state(self) -> None:
        output = self.publisher_with_test(
            revision="revision-gc-unknown-restore-sync"
        ).publish()
        database = Path(self.temporary.name) / "unknown-restore-sync.sqlite3"
        lifecycle = ArtifactLifecycleStore(database, self.publication)
        lifecycle.register_output(output)
        lifecycle.mark_stale(tenant_id="tenant-a", output_id=output.output_id)
        real_verify = lifecycle._verify_row_path
        real_rename = artifact_module._rename_no_replace
        rename_count = 0

        def reject_quarantine(
            row: sqlite3.Row, path: Path, *, normal_path: bool
        ) -> artifact_module._TreeSnapshot:
            if not normal_path:
                raise LifecycleError("injected quarantine verification failure")
            return real_verify(row, path, normal_path=normal_path)

        def lose_restore_durability(*args: object, **kwargs: object) -> bool:
            nonlocal rename_count
            durable = real_rename(*args, **kwargs)
            rename_count += 1
            return False if rename_count == 2 else durable

        with mock.patch.object(
            lifecycle, "_verify_row_path", side_effect=reject_quarantine
        ), mock.patch.object(
            artifact_module,
            "_rename_no_replace",
            side_effect=lose_restore_durability,
        ):
            with self.assertRaises(LifecycleError):
                lifecycle.collect_garbage(tenant_id="tenant-a", dry_run=False)
        self.assertEqual(rename_count, 2)
        row = self.lifecycle_row(lifecycle, output.output_id)
        self.assertEqual(row["state"], "collecting")
        self.assertEqual(row["collection_phase"], "quarantined")
        self.assertEqual(row["quarantine_verified"], 0)
        self.assertTrue(output.root.is_dir())
        self.assertFalse(Path(row["quarantine_path"]).exists())

        self.expire_collection_lease(lifecycle, output.output_id)
        reopened = ArtifactLifecycleStore(database, self.publication)
        recovered = self.lifecycle_row(reopened, output.output_id)
        self.assertEqual(recovered["state"], "stale")
        self.assertTrue(output.root.is_dir())
        self.assertIn(output.output_id, reopened.gc_candidates(tenant_id="tenant-a"))
        for field in (
            "collecting_from",
            "quarantine_path",
            "quarantine_snapshot",
            "quarantine_snapshot_digest",
            "collection_owner",
            "collection_lease_until",
            "collection_phase",
        ):
            self.assertIsNone(recovered[field])
        self.assertEqual(recovered["quarantine_verified"], 0)


if __name__ == "__main__":
    unittest.main()
