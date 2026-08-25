from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import os
import shutil
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
IMPORTER_PATH = REPOSITORY_ROOT / "tooling/integrate_autonomous_qa_self_healing_skills.py"
ARCHIVE_PATH = (
    REPOSITORY_ROOT
    / "skills/subskills/elmos-autonomous-qa-self-healing-skills-v1.1.0.zip"
)

SPEC = importlib.util.spec_from_file_location(
    "integrate_autonomous_qa_self_healing_skills", IMPORTER_PATH
)
assert SPEC is not None and SPEC.loader is not None
integration = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = integration
SPEC.loader.exec_module(integration)


def _synthetic_zip(path: Path, names: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for index, name in enumerate(names):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, f"payload-{index}".encode())


class AutonomousQaIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = integration.validate_archive(ARCHIVE_PATH)
        cls.runtime = integration.validate_runtime_registry(
            REPOSITORY_ROOT, cls.snapshot.skills
        )

    def temporary_repository(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory(prefix="autonomous-qa-integration-")
        root = Path(temporary.name)
        archive = root / integration.ARCHIVE_RELATIVE
        archive.parent.mkdir(parents=True)
        shutil.copy2(ARCHIVE_PATH, archive)
        for relative in integration.RUNTIME_AUTHORITY_MODULES:
            runtime = root / relative
            runtime.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPOSITORY_ROOT / relative, runtime)
        return temporary, root, archive

    def test_pinned_archive_inventory_contract_and_known_source_defects_are_exact(self) -> None:
        snapshot = self.snapshot
        self.assertEqual(integration.EXPECTED_ARCHIVE_SHA256, snapshot.archive_sha256)
        self.assertEqual(125, snapshot.entry_count)
        self.assertEqual(298_308, snapshot.uncompressed_bytes)
        self.assertEqual(40, len(snapshot.skills))
        self.assertEqual(
            67, sum(len(skill.dependencies) for skill in snapshot.skills)
        )
        self.assertEqual(
            tuple(skill.source_id for skill in snapshot.skills),
            snapshot.topological_order,
        )
        self.assertEqual(
            [
                ("policies/auto-fix-policy.yaml", "/artifact_update_rules"),
                ("policies/execution-policy.yaml", "/test_artifact_execution"),
            ],
            [
                (finding["path"], finding["json_pointer"])
                for finding in snapshot.policy_findings
            ],
        )
        self.assertTrue(
            all(finding["immutable_source_rewritten"] is False for finding in snapshot.policy_findings)
        )

    def test_yaml_loader_is_dependency_injected_and_cannot_hide_null_policy_defects(self) -> None:
        calls: list[str] = []

        def recording_loader(value: str) -> Any:
            calls.append(value)
            return integration._default_yaml_loader(value)

        snapshot = integration.validate_archive(ARCHIVE_PATH, yaml_loader=recording_loader)
        self.assertGreater(len(calls), 40)
        self.assertEqual(2, len(snapshot.policy_findings))

        def silently_repairing_loader(value: str) -> Any:
            document = integration._default_yaml_loader(value)
            if isinstance(document, dict):
                for section in ("artifact_update_rules", "test_artifact_execution"):
                    if section in document and document[section] is None:
                        document[section] = {}
            return document

        with self.assertRaisesRegex(
            integration.IntegrationError, "malformed null policy section"
        ):
            integration.validate_archive(
                ARCHIVE_PATH, yaml_loader=silently_repairing_loader
            )

    def test_yaml_loader_rejects_direct_and_merge_key_duplicates(self) -> None:
        ambiguous_documents = (
            "root:\n  value: one\n  value: two\n",
            (
                "base: &base\n"
                "  value: inherited\n"
                "root:\n"
                "  <<: *base\n"
                "  value: explicit\n"
            ),
        )
        for document in ambiguous_documents:
            with self.subTest(document=document), self.assertRaisesRegex(
                integration.IntegrationError, "duplicate YAML mapping key"
            ):
                integration._default_yaml_loader(document)

    def test_archive_digest_tamper_fails_before_package_parsing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="autonomous-qa-tamper-") as temporary:
            tampered = Path(temporary) / "tampered.zip"
            tampered.write_bytes(ARCHIVE_PATH.read_bytes() + b"tamper")
            with self.assertRaisesRegex(integration.IntegrationError, "SHA-256 mismatch"):
                integration.validate_archive(tampered)

    def test_archive_paths_reject_traversal_absolute_backslash_unicode_and_reserved_names(self) -> None:
        unsafe_names = (
            f"{integration.ARCHIVE_ROOT}/../escape.txt",
            "/absolute.txt",
            f"{integration.ARCHIVE_ROOT}\\escape.txt",
            f"{integration.ARCHIVE_ROOT}/cafe\u0301.txt",
            f"{integration.ARCHIVE_ROOT}/CON.txt",
            f"{integration.ARCHIVE_ROOT}/trailing-dot.",
        )
        for index, unsafe in enumerate(unsafe_names):
            with self.subTest(name=unsafe), tempfile.TemporaryDirectory(
                prefix=f"autonomous-qa-unsafe-{index}-"
            ) as temporary:
                archive = Path(temporary) / "unsafe.zip"
                _synthetic_zip(archive, [unsafe])
                with self.assertRaises(integration.IntegrationError):
                    integration.inspect_archive(
                        archive,
                        trusted_sha256=None,
                        expected_entry_count=None,
                        expected_total_bytes=None,
                        expected_mode_counts=None,
                    )

    def test_archive_rejects_casefold_collisions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="autonomous-qa-casefold-") as temporary:
            archive = Path(temporary) / "casefold.zip"
            _synthetic_zip(
                archive,
                [
                    f"{integration.ARCHIVE_ROOT}/One.txt",
                    f"{integration.ARCHIVE_ROOT}/one.txt",
                ],
            )
            with self.assertRaisesRegex(integration.IntegrationError, "collision"):
                integration.inspect_archive(
                    archive,
                    trusted_sha256=None,
                    expected_entry_count=None,
                    expected_total_bytes=None,
                    expected_mode_counts=None,
                )

    def test_member_metadata_rejects_symlinks_encryption_and_other_compression(self) -> None:
        base = zipfile.ZipInfo(f"{integration.ARCHIVE_ROOT}/payload.txt")
        base.create_system = 3
        base.compress_type = zipfile.ZIP_DEFLATED
        base.external_attr = (stat.S_IFREG | 0o644) << 16
        self.assertEqual(0o644, integration._validate_member_metadata(base))

        symlink = zipfile.ZipInfo(f"{integration.ARCHIVE_ROOT}/link")
        symlink.create_system = 3
        symlink.compress_type = zipfile.ZIP_DEFLATED
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(integration.IntegrationError, "link or special"):
            integration._validate_member_metadata(symlink)

        encrypted = zipfile.ZipInfo(f"{integration.ARCHIVE_ROOT}/encrypted")
        encrypted.create_system = 3
        encrypted.compress_type = zipfile.ZIP_DEFLATED
        encrypted.external_attr = (stat.S_IFREG | 0o644) << 16
        encrypted.flag_bits |= 0x1
        with self.assertRaisesRegex(integration.IntegrationError, "encrypted"):
            integration._validate_member_metadata(encrypted)

        stored = zipfile.ZipInfo(f"{integration.ARCHIVE_ROOT}/stored")
        stored.create_system = 3
        stored.compress_type = zipfile.ZIP_STORED
        stored.external_attr = (stat.S_IFREG | 0o644) << 16
        with self.assertRaisesRegex(integration.IntegrationError, "compression"):
            integration._validate_member_metadata(stored)

        non_unix = zipfile.ZipInfo(f"{integration.ARCHIVE_ROOT}/dos-origin")
        non_unix.create_system = 0
        non_unix.compress_type = zipfile.ZIP_DEFLATED
        non_unix.external_attr = (stat.S_IFREG | 0o644) << 16
        with self.assertRaisesRegex(integration.IntegrationError, "Unix metadata"):
            integration._validate_member_metadata(non_unix)

    def test_dependency_cycle_is_rejected_before_edge_or_order_claims(self) -> None:
        skills = list(self.snapshot.skills)
        skills[0] = dataclasses.replace(
            skills[0], dependencies=(skills[1].source_id,)
        )
        with self.assertRaisesRegex(integration.IntegrationError, "cycle"):
            integration.validate_skill_graph(
                skills,
                expected_order=self.snapshot.topological_order,
                expected_edges=None,
            )

    def test_normalized_frontmatter_is_codex_safe_and_provenance_bound(self) -> None:
        expected = integration.build_expected(self.snapshot, self.runtime)
        skill = self.snapshot.skills[0]
        payload = expected["skill_trees"][skill.alias]["SKILL.md"].content
        frontmatter, body = integration._split_frontmatter(
            payload, skill.alias, integration._default_yaml_loader
        )
        self.assertEqual({"name", "description", "metadata"}, set(frontmatter))
        self.assertEqual(skill.alias, frontmatter["name"])
        self.assertRegex(frontmatter["name"], r"^[a-z0-9-]+$")
        self.assertLessEqual(len(frontmatter["name"]), 64)
        self.assertEqual(
            f"Run {skill.source_id} through its exact repository-owned "
            "Autonomous QA handler.",
            frontmatter["description"],
        )
        self.assertEqual(skill.source_id, frontmatter["metadata"]["source_id"])
        self.assertEqual(
            "sha256:" + skill.source_sha256,
            frontmatter["metadata"]["source_sha256"],
        )
        self.assertEqual(integration.RUNTIME_MODULE, frontmatter["metadata"]["runtime_module"])
        self.assertEqual(self.runtime.phases[0], frontmatter["metadata"]["runtime_phase"])
        self.assertEqual(
            self.runtime.operation_ids[0],
            frontmatter["metadata"]["runtime_operation"],
        )
        self.assertNotIn(skill.body.strip(), body)
        self.assertIn("Trusted Repository Runtime Wrapper", body)
        self.assertIn("Repository Integration Boundary", body)
        source_record = self.snapshot.files[skill.source_path]
        self.assertEqual(skill.source_sha256, hashlib.sha256(source_record.content).hexdigest())

        adversarial_marker = "UNTRUSTED-SOURCE-INSTRUCTION-MUST-NOT-BE-ACTIVATED"
        adversarial = dataclasses.replace(
            skill,
            source_name=adversarial_marker,
            category=adversarial_marker,
            description=adversarial_marker,
            body=adversarial_marker,
        )
        rendered_skill = integration._render_skill(adversarial, self.runtime)
        rendered_interface = integration._render_interface(adversarial)
        self.assertNotIn(adversarial_marker.encode(), rendered_skill)
        self.assertNotIn(adversarial_marker.encode(), rendered_interface)
        contract = expected["compiled_manifest"]["skills"][0]
        self.assertTrue(contract["repository_owned_wrapper"])
        self.assertFalse(contract["source_body_embedded_in_wrapper"])
        self.assertFalse(contract["source_instructions_activated"])

    def test_write_is_dual_root_byte_identical_idempotent_and_checkable(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        first = integration.write_integration(root, archive)
        expected = integration.build_expected(
            first, integration.validate_runtime_registry(root, first.skills)
        )
        before = {
            action.destination.relative_to(root).as_posix(): integration._tree_digest(
                integration._read_tree(action.destination)
            )
            for action in integration._managed_actions(root, expected)
        }
        second = integration.write_integration(root, archive)
        integration.check_integration(root, archive)
        after = {
            action.destination.relative_to(root).as_posix(): integration._tree_digest(
                integration._read_tree(action.destination)
            )
            for action in integration._managed_actions(root, expected)
        }
        self.assertEqual(first.archive_sha256, second.archive_sha256)
        self.assertEqual(before, after)
        for skill in first.skills:
            left = integration._read_tree(
                root / integration.INSTALL_ROOTS[0] / skill.alias
            )
            right = integration._read_tree(
                root / integration.INSTALL_ROOTS[1] / skill.alias
            )
            self.assertEqual(left, right)

    def test_generated_manifests_coexist_with_reviewer_owned_documentation(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        docs = root / integration.DOC_RELATIVE
        docs.mkdir(parents=True)
        reviewer_document = docs / "README.md"
        reviewer_document.write_bytes(b"reviewer-owned\n")

        integration.write_integration(root, archive)
        integration.check_integration(root, archive)

        self.assertEqual(b"reviewer-owned\n", reviewer_document.read_bytes())
        generated = root / integration.GENERATED_DOC_RELATIVE
        self.assertEqual(
            {
                "compiled-manifest.json",
                "implementation-matrix.json",
                "installed-manifest.json",
            },
            {path.name for path in generated.iterdir()},
        )

    def test_unowned_collision_fails_preflight_without_partial_install(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        alias = self.snapshot.skills[0].alias
        collision = root / integration.INSTALL_ROOTS[0] / alias
        collision.mkdir(parents=True)
        user_bytes = b"user-owned\n"
        (collision / "SKILL.md").write_bytes(user_bytes)
        with self.assertRaisesRegex(integration.IntegrationError, "refusing unowned"):
            integration.write_integration(root, archive)
        self.assertEqual(user_bytes, (collision / "SKILL.md").read_bytes())
        self.assertFalse((root / integration.SOURCE_RELATIVE).exists())
        self.assertFalse((root / integration.INSTALL_ROOTS[1] / alias).exists())
        self.assertFalse((root / integration.DOC_RELATIVE).exists())

    def test_check_detects_installed_content_drift(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        snapshot = integration.write_integration(root, archive)
        target = (
            root
            / integration.INSTALL_ROOTS[1]
            / snapshot.skills[0].alias
            / "SKILL.md"
        )
        target.write_bytes(target.read_bytes() + b"\ndrift\n")
        with self.assertRaisesRegex(integration.IntegrationError, "drifted"):
            integration.check_integration(root, archive)

    def test_check_detects_managed_directory_mode_drift(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        snapshot = integration.write_integration(root, archive)
        target = root / integration.INSTALL_ROOTS[0] / snapshot.skills[0].alias
        target.chmod(0o700)
        with self.assertRaisesRegex(integration.IntegrationError, "root mode changed"):
            integration.check_integration(root, archive)

    def test_managed_tree_reader_bounds_entries_and_rejects_hardlinks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="autonomous-qa-tree-") as temporary:
            root = Path(temporary)
            (root / "one.txt").write_bytes(b"one")
            (root / "two.txt").write_bytes(b"two")
            with mock.patch.object(integration, "MAX_MANAGED_TREE_ENTRIES", 1):
                with self.assertRaisesRegex(integration.IntegrationError, "entry budget"):
                    integration._read_tree(root)

        if hasattr(os, "link"):
            with tempfile.TemporaryDirectory(prefix="autonomous-qa-hardlink-") as temporary:
                root = Path(temporary)
                original = root / "one.txt"
                original.write_bytes(b"one")
                os.link(original, root / "two.txt")
                with self.assertRaisesRegex(
                    integration.IntegrationError, "changed before read"
                ):
                    integration._read_tree(root)

    def test_managed_tree_reader_rejects_same_name_child_and_root_swaps(self) -> None:
        with tempfile.TemporaryDirectory(prefix="autonomous-qa-tree-swap-") as temporary:
            root = Path(temporary) / "managed"
            child = root / "child"
            child.mkdir(parents=True)
            (child / "owned.txt").write_bytes(b"owned\n")
            displaced_child = root / "verified-child"
            real_stat = integration.os.stat
            child_stats = 0

            def swap_child_on_recheck(
                path: object, *args: object, **kwargs: object
            ) -> os.stat_result:
                nonlocal child_stats
                if path == "child" and kwargs.get("dir_fd") is not None:
                    child_stats += 1
                    if child_stats == 2:
                        child.rename(displaced_child)
                        child.mkdir()
                        (child / "owner.txt").write_bytes(b"do not delete\n")
                return real_stat(path, *args, **kwargs)

            with mock.patch.object(
                integration.os, "stat", side_effect=swap_child_on_recheck
            ), self.assertRaisesRegex(integration.IntegrationError, "replaced"):
                integration._read_tree(root)
            self.assertEqual(b"do not delete\n", (child / "owner.txt").read_bytes())
            self.assertEqual(b"owned\n", (displaced_child / "owned.txt").read_bytes())

        with tempfile.TemporaryDirectory(prefix="autonomous-qa-root-swap-") as temporary:
            parent = Path(temporary)
            root = parent / "managed"
            root.mkdir()
            (root / "owned.txt").write_bytes(b"owned\n")
            displaced_root = parent / "verified-root"
            real_read = integration._read_tree_descriptor

            def swap_root_after_descriptor_read(
                descriptor: int, *, label: str
            ) -> integration.ManagedTreeSnapshot:
                snapshot = real_read(descriptor, label=label)
                root.rename(displaced_root)
                root.mkdir()
                (root / "owner.txt").write_bytes(b"do not delete\n")
                return snapshot

            with mock.patch.object(
                integration,
                "_read_tree_descriptor",
                side_effect=swap_root_after_descriptor_read,
            ), self.assertRaisesRegex(integration.IntegrationError, "root was replaced"):
                integration._read_tree(root)
            self.assertEqual(b"do not delete\n", (root / "owner.txt").read_bytes())
            self.assertEqual(b"owned\n", (displaced_root / "owned.txt").read_bytes())

    def test_managed_tree_reader_rejects_post_enumeration_extra_entries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="autonomous-qa-tree-extra-") as temporary:
            root = Path(temporary)
            (root / "owned.txt").write_bytes(b"owned\n")
            real_stat = integration.os.stat
            file_stats = 0

            def inject_after_file_recheck(
                path: object, *args: object, **kwargs: object
            ) -> os.stat_result:
                nonlocal file_stats
                result = real_stat(path, *args, **kwargs)
                if path == "owned.txt" and kwargs.get("dir_fd") is not None:
                    file_stats += 1
                    if file_stats == 2:
                        (root / "concurrent-owner.txt").write_bytes(
                            b"do not delete\n"
                        )
                return result

            with mock.patch.object(
                integration.os, "stat", side_effect=inject_after_file_recheck
            ), self.assertRaisesRegex(integration.IntegrationError, "changed during read"):
                integration._read_tree(root)
            self.assertEqual(
                b"do not delete\n", (root / "concurrent-owner.txt").read_bytes()
            )

    def test_descriptor_close_cleanup_is_non_interrupting(self) -> None:
        with mock.patch.object(
            integration.os, "close", side_effect=OSError("injected close failure")
        ) as close:
            integration._close_descriptors((101, 102, 103))
        self.assertEqual(3, close.call_count)

    def test_exact_file_cleanup_rejects_a_post_verify_tombstone_swap(self) -> None:
        with tempfile.TemporaryDirectory(prefix="autonomous-qa-file-cleanup-") as value:
            parent = Path(value)
            managed = parent / "managed"
            managed.mkdir(mode=0o755)
            managed.chmod(0o755)
            (managed / "owned.txt").write_bytes(b"owned\n")
            snapshot = integration._read_tree_snapshot(managed)
            parent_descriptor = os.open(parent, integration._directory_open_flags())
            real_verify = integration._read_expected_file_at
            displaced = managed / "verified-file"
            swapped = False

            def swap_after_verify(
                descriptor: int,
                name: str,
                *,
                expected_identity: tuple[int, int],
                expected_payload: integration.FilePayload,
                label: str,
                keep_open: bool = False,
            ) -> int:
                nonlocal swapped
                pinned = real_verify(
                    descriptor,
                    name,
                    expected_identity=expected_identity,
                    expected_payload=expected_payload,
                    label=label,
                    keep_open=keep_open,
                )
                if keep_open and not swapped:
                    tombstone = managed / name
                    tombstone.rename(displaced)
                    tombstone.write_bytes(b"do not delete\n")
                    swapped = True
                return pinned

            try:
                with mock.patch.object(
                    integration,
                    "_read_expected_file_at",
                    side_effect=swap_after_verify,
                ), self.assertRaisesRegex(
                    integration.IntegrationError, "file tombstone was replaced"
                ):
                    integration._remove_exact_tree_at(
                        parent_descriptor,
                        managed.name,
                        snapshot,
                        label="file cleanup race",
                        allow_missing=False,
                    )
            finally:
                integration._close_descriptor(parent_descriptor)
            self.assertTrue(swapped)
            replacement = next(
                managed.glob(integration.DELETE_TOMBSTONE_PREFIX + "*")
            )
            self.assertEqual(b"do not delete\n", replacement.read_bytes())
            self.assertEqual(b"owned\n", displaced.read_bytes())

    def test_empty_directory_cleanup_rejects_a_post_verify_name_swap(self) -> None:
        with tempfile.TemporaryDirectory(prefix="autonomous-qa-empty-cleanup-") as value:
            parent = Path(value)
            owned = parent / "owned"
            owned.mkdir(mode=0o755)
            owned.chmod(0o755)
            expected_identity = (owned.stat().st_dev, owned.stat().st_ino)
            parent_descriptor = os.open(parent, integration._directory_open_flags())
            real_inventory = integration._bounded_directory_names
            displaced = parent / "verified-empty-directory"
            swapped = False

            def swap_after_verify(descriptor: int, *, label: str) -> tuple[str, ...]:
                nonlocal swapped
                names = real_inventory(descriptor, label=label)
                if label == "empty cleanup race" and not swapped:
                    tombstone = next(
                        parent.glob(integration.EMPTY_TOMBSTONE_PREFIX + "*")
                    )
                    tombstone.rename(displaced)
                    tombstone.mkdir(mode=0o755)
                    (tombstone / "owner.txt").write_bytes(b"do not delete\n")
                    swapped = True
                return names

            try:
                with mock.patch.object(
                    integration,
                    "_bounded_directory_names",
                    side_effect=swap_after_verify,
                ), self.assertRaisesRegex(
                    integration.IntegrationError, "tombstone was replaced"
                ):
                    integration._remove_empty_directory_at(
                        parent_descriptor,
                        owned.name,
                        expected_identity,
                        expected_mode=0o755,
                        label="empty cleanup race",
                    )
            finally:
                integration._close_descriptor(parent_descriptor)
            self.assertTrue(swapped)
            replacement = next(
                parent.glob(integration.EMPTY_TOMBSTONE_PREFIX + "*")
            )
            self.assertEqual(
                b"do not delete\n", (replacement / "owner.txt").read_bytes()
            )
            self.assertTrue(displaced.is_dir())

    def test_exact_directory_cleanup_rejects_a_post_verify_tombstone_swap(self) -> None:
        with tempfile.TemporaryDirectory(prefix="autonomous-qa-dir-cleanup-") as value:
            parent = Path(value)
            managed = parent / "managed"
            child = managed / "child"
            child.mkdir(parents=True, mode=0o755)
            managed.chmod(0o755)
            child.chmod(0o755)
            (child / "owned.txt").write_bytes(b"owned\n")
            snapshot = integration._read_tree_snapshot(managed)
            parent_descriptor = os.open(parent, integration._directory_open_flags())
            real_inventory = integration._bounded_directory_names
            displaced = managed / "verified-directory"
            swapped = False

            def swap_after_verify(descriptor: int, *, label: str) -> tuple[str, ...]:
                nonlocal swapped
                names = real_inventory(descriptor, label=label)
                if label == "directory cleanup race directory tombstone" and not swapped:
                    tombstone = next(
                        managed.glob(integration.DELETE_TOMBSTONE_PREFIX + "*")
                    )
                    tombstone.rename(displaced)
                    tombstone.mkdir(mode=0o755)
                    (tombstone / "owner.txt").write_bytes(b"do not delete\n")
                    swapped = True
                return names

            try:
                with mock.patch.object(
                    integration,
                    "_bounded_directory_names",
                    side_effect=swap_after_verify,
                ), self.assertRaisesRegex(
                    integration.IntegrationError,
                    "directory tombstone was replaced",
                ):
                    integration._remove_exact_tree_at(
                        parent_descriptor,
                        managed.name,
                        snapshot,
                        label="directory cleanup race",
                        allow_missing=False,
                    )
            finally:
                integration._close_descriptor(parent_descriptor)
            self.assertTrue(swapped)
            replacement = next(
                managed.glob(integration.DELETE_TOMBSTONE_PREFIX + "*")
            )
            self.assertEqual(
                b"do not delete\n", (replacement / "owner.txt").read_bytes()
            )
            self.assertTrue(displaced.is_dir())

    def test_transaction_root_and_children_are_pinned_mode_0700(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        real_create = integration._create_transaction
        observed_modes: list[int] = []

        def inspect_transaction(
            path: Path,
            *,
            expected_repository_identity: tuple[int, int] | None = None,
        ) -> integration.PinnedTransaction:
            transaction = real_create(
                path,
                expected_repository_identity=expected_repository_identity,
            )
            observed_modes.extend(
                stat.S_IMODE(os.fstat(descriptor).st_mode)
                for descriptor in (
                    transaction.root_descriptor,
                    transaction.staged_descriptor,
                    transaction.rollback_descriptor,
                )
            )
            return transaction

        with mock.patch.object(
            integration, "_create_transaction", side_effect=inspect_transaction
        ):
            integration.write_integration(root, archive)
        self.assertEqual([0o700, 0o700, 0o700], observed_modes)

    def test_runtime_registry_drift_invalidates_installed_provenance(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        integration.write_integration(root, archive)
        runtime = root / integration.RUNTIME_MODULE
        runtime.write_bytes(runtime.read_bytes() + b"\n# reviewed drift\n")
        with self.assertRaisesRegex(integration.IntegrationError, "drifted"):
            integration.check_integration(root, archive)

    def test_runtime_operation_module_drift_invalidates_installed_provenance(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        integration.write_integration(root, archive)
        operation_module = root / (
            "engines/autonomous-qa-engine/src/elmos_autonomous_qa/generators.py"
        )
        operation_module.write_bytes(
            operation_module.read_bytes() + b"\n# reviewed operation drift\n"
        )
        with self.assertRaisesRegex(integration.IntegrationError, "drifted"):
            integration.check_integration(root, archive)

    def test_runtime_snapshot_digest_and_handler_identity_are_exact(self) -> None:
        expected = integration.build_expected(self.snapshot, self.runtime)
        observed_bindings = tuple(
            zip(
                self.runtime.source_ids,
                self.runtime.phases,
                self.runtime.mutating_flags,
                self.runtime.operation_ids,
                self.runtime.handler_ids,
            )
        )
        self.assertEqual(integration.EXPECTED_RUNTIME_BINDINGS, observed_bindings)
        self.assertEqual(
            self.runtime.module_sha256,
            expected["compiled_manifest"]["runtime_authority"]["module_sha256"],
        )
        self.assertEqual(
            self.runtime.module_sha256,
            expected["installed_manifest"]["runtime_authority"]["module_sha256"],
        )
        self.assertEqual(
            self.runtime.authority_sha256,
            expected["compiled_manifest"]["runtime_authority"]["authority_sha256"],
        )
        self.assertEqual(
            self.runtime.authority_sha256,
            expected["installed_manifest"]["runtime_authority"]["authority_sha256"],
        )
        self.assertEqual(
            [
                {"path": path, "sha256": digest, "bytes": size}
                for path, digest, size in self.runtime.authority_modules
            ],
            expected["compiled_manifest"]["runtime_authority"]["authority_modules"],
        )
        self.assertTrue(
            all(
                record["runtime_binding"]["module_sha256"]
                == self.runtime.module_sha256
                for record in expected["installed_manifest"]["skills"]
            )
        )
        self.assertTrue(
            all(
                record["runtime_binding"]["authority_sha256"]
                == self.runtime.authority_sha256
                for record in expected["installed_manifest"]["skills"]
            )
        )
        first_binding = expected["installed_manifest"]["skills"][0][
            "runtime_binding"
        ]
        self.assertEqual(self.runtime.phases[0], first_binding["phase"])
        self.assertEqual(self.runtime.mutating_flags[0], first_binding["mutating"])
        self.assertEqual(self.runtime.operation_ids[0], first_binding["operation_id"])
        self.assertEqual(
            [
                {
                    "source_id": source_id,
                    "phase": phase,
                    "mutating": mutating,
                    "operation_id": operation_id,
                    "handler_id": handler_id,
                }
                for source_id, phase, mutating, operation_id, handler_id in observed_bindings
            ],
            expected["compiled_manifest"]["runtime_authority"]["bindings"],
        )
        mismatched = dataclasses.replace(
            self.runtime,
            handler_ids=("execute_wrong_handler", *self.runtime.handler_ids[1:]),
        )
        with self.assertRaisesRegex(
            integration.IntegrationError, "exactly provenance-bound"
        ):
            integration.build_expected(self.snapshot, mismatched)

    def test_runtime_source_phase_mutation_operation_and_handler_drift_fail_closed(self) -> None:
        exact_spec = (
            '("00-qa-control-plane", "control", True, '
            "domain.create_run_contract)"
        )
        mutations = (
            (
                exact_spec,
                '("99-unowned-skill", "control", True, domain.create_run_contract)',
                "importer-owned exact binding contract",
            ),
            (
                exact_spec,
                '("00-qa-control-plane", "planning", True, '
                "domain.create_run_contract)",
                "importer-owned exact binding contract",
            ),
            (
                exact_spec,
                '("00-qa-control-plane", "control", False, '
                "domain.create_run_contract)",
                "importer-owned exact binding contract",
            ),
            (
                exact_spec,
                '("00-qa-control-plane", "control", True, domain.ingest_snapshot)',
                "importer-owned exact binding contract",
            ),
            (
                'handler.__name__ = "execute_" + source_id.replace("-", "_")',
                'handler.__name__ = "run_" + source_id.replace("-", "_")',
                "handler name construction is not exact",
            ),
            (
                '("00-qa-control-plane", "control", True, '
                '"elmos_autonomous_qa.domain.create_run_contract")',
                '("00-qa-control-plane", "control", True, '
                '"elmos_autonomous_qa.domain.ingest_snapshot")',
                "runtime-owned canonical binding contract",
            ),
        )
        for before, after, message in mutations:
            with self.subTest(after=after):
                temporary, root, _archive = self.temporary_repository()
                self.addCleanup(temporary.cleanup)
                runtime_path = root / integration.RUNTIME_MODULE
                source = runtime_path.read_text(encoding="utf-8")
                self.assertEqual(1, source.count(before))
                runtime_path.write_text(
                    source.replace(before, after, 1), encoding="utf-8"
                )
                with self.assertRaisesRegex(integration.IntegrationError, message):
                    integration.validate_runtime_registry(root, self.snapshot.skills)

    def test_json_duplicates_and_unconfined_or_missing_schema_refs_fail_closed(self) -> None:
        with self.assertRaisesRegex(integration.IntegrationError, "duplicate JSON key"):
            integration._parse_json('{"value": 1, "value": 2}', "duplicate.json")

        schema_path = "schemas/example.schema.json"
        schema_id = "https://elmos.dev/schemas/example.schema.json"
        base_schema = {
            "$schema": integration.DRAFT202012_META_SCHEMA,
            "$id": schema_id,
            "$defs": {"known": {"type": "string"}},
            "$ref": "#/$defs/known",
        }
        integration._validate_json_schemas(
            [schema_path], {schema_path: base_schema}
        )

        missing_pointer = {**base_schema, "$ref": "#/$defs/missing"}
        with self.assertRaisesRegex(integration.IntegrationError, "missing JSON Pointer"):
            integration._validate_json_schemas(
                [schema_path], {schema_path: missing_pointer}
            )

        unconfined = {
            **base_schema,
            "$ref": "https://attacker.invalid/schema.json",
        }
        with self.assertRaisesRegex(integration.IntegrationError, "unconfined"):
            integration._validate_json_schemas(
                [schema_path], {schema_path: unconfined}
            )

    def test_partial_commit_failure_rolls_back_every_managed_destination(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)

        def fail_after_first(index: int, _action: integration.ManagedAction) -> None:
            if index == 2:
                raise RuntimeError("injected commit failure")

        with self.assertRaisesRegex(RuntimeError, "injected commit failure"):
            integration.write_integration(root, archive, before_commit=fail_after_first)
        runtime = integration.validate_runtime_registry(root, self.snapshot.skills)
        expected = integration.build_expected(self.snapshot, runtime)
        self.assertTrue(
            all(
                not action.destination.exists() and not action.destination.is_symlink()
                for action in integration._managed_actions(root, expected)
            )
        )
        self.assertFalse((root / ".agents/skills").exists())
        self.assertFalse((root / ".agents").exists())
        self.assertEqual([], list(root.glob(".autonomous-qa-install-*")))

    def test_stage_tree_is_reverified_immediately_before_commit(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        real_publish = integration._rename_directory_no_replace
        mutated_stage: Path | None = None

        def inject_extra_before_publish(
            source: Path,
            destination: Path,
            parent_descriptor: int,
            *,
            expected_snapshot: integration.ManagedTreeSnapshot,
            source_parent_descriptor: int | None = None,
        ) -> integration.DirectoryCommit:
            nonlocal mutated_stage
            if mutated_stage is None:
                mutated_stage = source
                (source / "concurrent-owner.txt").write_bytes(b"do not delete\n")
            return real_publish(
                source,
                destination,
                parent_descriptor,
                expected_snapshot=expected_snapshot,
                source_parent_descriptor=source_parent_descriptor,
            )

        with mock.patch.object(
            integration,
            "_rename_directory_no_replace",
            side_effect=inject_extra_before_publish,
        ), self.assertRaises(integration.IntegrationError):
            integration.write_integration(root, archive)
        assert mutated_stage is not None
        self.assertEqual(
            b"do not delete\n", (mutated_stage / "concurrent-owner.txt").read_bytes()
        )
        with self.assertRaisesRegex(
            integration.IntegrationError, "reserved Autonomous QA transaction roots"
        ):
            integration.write_integration(root, archive)
        with self.assertRaisesRegex(
            integration.IntegrationError, "reserved Autonomous QA transaction roots"
        ):
            integration.check_integration(root, archive)
        self.assertEqual(
            b"do not delete\n", (mutated_stage / "concurrent-owner.txt").read_bytes()
        )

    def test_transaction_cleanup_never_adopts_a_replacement_root(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        replacement: Path | None = None

        def replace_transaction(
            index: int, _action: integration.ManagedAction
        ) -> None:
            nonlocal replacement
            if index != 0:
                return
            transaction = next(root.glob(".autonomous-qa-install-*"))
            displaced = root / "displaced-autonomous-qa-transaction"
            transaction.rename(displaced)
            transaction.mkdir(mode=0o700)
            (transaction / "owner.txt").write_bytes(b"do not delete\n")
            replacement = transaction
            raise RuntimeError("injected transaction replacement")

        with self.assertRaises(integration.IntegrationError):
            integration.write_integration(
                root, archive, before_commit=replace_transaction
            )
        assert replacement is not None
        self.assertEqual(b"do not delete\n", (replacement / "owner.txt").read_bytes())

    def test_all_reserved_cleanup_prefixes_block_rerun_without_adoption(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        managed_parent = root / ".agents"
        managed_parent.mkdir()
        residues = tuple(
            managed_parent / f"{prefix}owner-residue"
            for prefix in integration.RESERVED_IMPORTER_PREFIXES
        )
        for residue in residues:
            residue.mkdir()
            (residue / "owner.txt").write_bytes(b"do not delete\n")

        with self.assertRaisesRegex(
            integration.IntegrationError, "cleanup entries require manual review"
        ) as raised:
            integration.write_integration(root, archive)
        for residue in residues:
            self.assertIn(residue.name, str(raised.exception))
            self.assertEqual(b"do not delete\n", (residue / "owner.txt").read_bytes())
        with self.assertRaisesRegex(
            integration.IntegrationError, "cleanup entries require manual review"
        ):
            integration.check_integration(root, archive)
        for residue in residues:
            self.assertEqual(b"do not delete\n", (residue / "owner.txt").read_bytes())

    def test_commit_rejects_a_same_name_repository_root_replacement(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        real_publish = integration._rename_directory_no_replace
        displaced_root = root.parent / f"{root.name}-verified-root"
        replacement_created = False

        def replace_repository_after_publish(
            source: Path,
            destination: Path,
            parent_descriptor: int,
            *,
            expected_snapshot: integration.ManagedTreeSnapshot,
            source_parent_descriptor: int | None = None,
        ) -> integration.DirectoryCommit:
            nonlocal replacement_created
            result = real_publish(
                source,
                destination,
                parent_descriptor,
                expected_snapshot=expected_snapshot,
                source_parent_descriptor=source_parent_descriptor,
            )
            if not replacement_created:
                root.rename(displaced_root)
                root.mkdir(mode=0o700)
                (root / "owner.txt").write_bytes(b"do not delete\n")
                replacement_created = True
            return result

        with mock.patch.object(
            integration,
            "_rename_directory_no_replace",
            side_effect=replace_repository_after_publish,
        ), self.assertRaises(integration.IntegrationError) as raised:
            integration.write_integration(root, archive)
        causes: list[str] = []
        current: BaseException | None = raised.exception
        while current is not None:
            causes.append(str(current))
            current = current.__cause__
        self.assertIn("repository root identity changed", " ".join(causes))
        self.assertTrue(replacement_created)
        self.assertEqual(b"do not delete\n", (root / "owner.txt").read_bytes())
        self.assertTrue(displaced_root.is_dir())

    def test_rollback_is_no_replace_and_preserves_a_concurrent_collision(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        collision: Path | None = None

        def collide_with_rollback(
            index: int, _action: integration.ManagedAction
        ) -> None:
            nonlocal collision
            if index != 1:
                return
            transaction = next(root.glob(".autonomous-qa-install-*"))
            collision = transaction / "rollback/000"
            collision.mkdir()
            (collision / "owner.txt").write_bytes(b"do not replace\n")
            raise RuntimeError("injected rollback collision")

        with self.assertRaises(integration.IntegrationError):
            integration.write_integration(
                root, archive, before_commit=collide_with_rollback
            )
        assert collision is not None
        self.assertEqual(b"do not replace\n", (collision / "owner.txt").read_bytes())

    def test_committed_but_unsynced_publication_fails_closed_and_rolls_back(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        real_publish = integration._rename_directory_no_replace
        injected = False

        def report_first_commit_as_unsynced(
            source: Path,
            destination: Path,
            parent_descriptor: int,
            *,
            expected_snapshot: integration.ManagedTreeSnapshot,
            source_parent_descriptor: int | None = None,
        ) -> integration.DirectoryCommit:
            nonlocal injected
            result = real_publish(
                source,
                destination,
                parent_descriptor,
                expected_snapshot=expected_snapshot,
                source_parent_descriptor=source_parent_descriptor,
            )
            if not injected:
                injected = True
                return dataclasses.replace(result, durable=False)
            return result

        with mock.patch.object(
            integration,
            "_rename_directory_no_replace",
            side_effect=report_first_commit_as_unsynced,
        ), self.assertRaisesRegex(integration.IntegrationError, "durability is unknown"):
            integration.write_integration(root, archive)
        self.assertTrue(injected)
        expected = integration.build_expected(
            self.snapshot,
            integration.validate_runtime_registry(root, self.snapshot.skills),
        )
        self.assertTrue(
            all(
                not action.destination.exists() and not action.destination.is_symlink()
                for action in integration._managed_actions(root, expected)
            )
        )
        self.assertEqual([], list(root.glob(".autonomous-qa-install-*")))

    def test_atomic_publication_does_not_replace_a_concurrent_destination(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        real_publish = integration._rename_directory_no_replace
        collision: Path | None = None
        collision_inode: int | None = None
        owner_bytes = b"concurrent-owner\n"

        def publish_after_collision(
            source: Path,
            destination: Path,
            parent_descriptor: int,
            *,
            expected_snapshot: integration.ManagedTreeSnapshot,
            source_parent_descriptor: int | None = None,
        ) -> integration.DirectoryCommit:
            nonlocal collision, collision_inode
            if collision is None:
                destination.mkdir()
                (destination / "owner.txt").write_bytes(owner_bytes)
                collision = destination
                collision_inode = destination.stat(follow_symlinks=False).st_ino
            return real_publish(
                source,
                destination,
                parent_descriptor,
                expected_snapshot=expected_snapshot,
                source_parent_descriptor=source_parent_descriptor,
            )

        with mock.patch.object(
            integration,
            "_rename_directory_no_replace",
            side_effect=publish_after_collision,
        ), self.assertRaisesRegex(
            integration.IntegrationError, "appeared concurrently"
        ):
            integration.write_integration(root, archive)

        self.assertIsNotNone(collision)
        assert collision is not None
        self.assertEqual(collision_inode, collision.stat(follow_symlinks=False).st_ino)
        self.assertEqual(owner_bytes, (collision / "owner.txt").read_bytes())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_parent_swap_immediately_before_commit_is_rejected_without_escape(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        outside = root / "outside"
        outside.mkdir()

        def swap_first_install_parent(
            index: int, _action: integration.ManagedAction
        ) -> None:
            if index == 1:
                (root / ".agents").symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(integration.IntegrationError, "symlink"):
            integration.write_integration(
                root,
                archive,
                before_commit=swap_first_install_parent,
            )
        self.assertFalse((outside / "skills").exists())
        self.assertFalse((root / integration.SOURCE_RELATIVE).exists())
        self.assertFalse((root / integration.GENERATED_DOC_RELATIVE).exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_symlink_repository_archive_and_final_destination_are_rejected(self) -> None:
        temporary, root, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        link = root.parent / f"{root.name}-link"
        link.symlink_to(root, target_is_directory=True)
        self.addCleanup(lambda: link.unlink(missing_ok=True))
        with self.assertRaisesRegex(integration.IntegrationError, "must not be a symlink"):
            integration.write_integration(link, link / integration.ARCHIVE_RELATIVE)

        alternate = root / "alternate.zip"
        shutil.copy2(archive, alternate)
        with self.assertRaisesRegex(integration.IntegrationError, "canonical pinned archive"):
            integration.write_integration(root, alternate)

        archive.unlink()
        archive.symlink_to(alternate)
        with self.assertRaisesRegex(integration.IntegrationError, "archive"):
            integration.write_integration(root, archive)
        archive.unlink()
        shutil.copy2(alternate, archive)

        target = root / "user-owned-source"
        target.mkdir()
        destination = root / integration.SOURCE_RELATIVE
        destination.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(integration.IntegrationError, "symlink"):
            integration.write_integration(root, archive)

    def test_malformed_frontmatter_envelope_is_rejected(self) -> None:
        with self.assertRaisesRegex(integration.IntegrationError, "frontmatter envelope"):
            integration._split_frontmatter(
                b"---\nid: broken\n", "broken/SKILL.md", integration._default_yaml_loader
            )


if __name__ == "__main__":
    unittest.main()
