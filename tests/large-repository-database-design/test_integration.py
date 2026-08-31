from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[2]
TOOLING = ROOT / "tooling"
if str(TOOLING) not in sys.path:
    sys.path.insert(0, str(TOOLING))


def load_integration_module():
    path = TOOLING / "integrate_large_repository_database_design.py"
    spec = importlib.util.spec_from_file_location(
        "large_repository_database_design_integration", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load integration module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


integration = load_integration_module()


def load_runtime_renderer_module():
    path = (
        ROOT
        / "scripts"
        / "large_repository_database_design"
        / "render_runtime_migrations.py"
    )
    spec = importlib.util.spec_from_file_location(
        "large_repository_database_design_runtime_renderer", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load runtime renderer from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runtime_renderer = load_runtime_renderer_module()


class LargeRepositoryDatabaseDesignIntegrationTests(unittest.TestCase):
    def copy_archive(self, repository: Path) -> Path:
        source = ROOT / integration.ARCHIVE_RELATIVE
        destination = repository / integration.ARCHIVE_RELATIVE
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination

    def rewrite_archive(self, destination: Path, mutate) -> None:
        source = ROOT / integration.ARCHIVE_RELATIVE
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, "w") as changed:
            for index, source_info in enumerate(original.infolist()):
                info = copy.copy(source_info)
                data = original.read(source_info)
                info, data = mutate(index, info, data)
                changed.writestr(info, data)

    def test_01_pinned_archive_inventory_checksums_and_modes_are_exact(self) -> None:
        archive = ROOT / integration.ARCHIVE_RELATIVE
        self.assertEqual(integration.EXPECTED_ARCHIVE_BYTES, archive.stat().st_size)
        self.assertEqual(
            integration.EXPECTED_ARCHIVE_SHA256,
            integration.sha256_file(archive),
        )
        snapshot = integration.read_archive(archive)
        self.assertEqual(integration.EXPECTED_SOURCE_FILES, len(snapshot.files))
        self.assertEqual(
            integration.EXPECTED_SOURCE_DIRECTORIES, len(snapshot.directories)
        )
        self.assertEqual(integration.EXPECTED_SOURCE_BYTES, snapshot.uncompressed_bytes)
        self.assertEqual(
            integration.EXPECTED_CHECKSUM_ENTRIES, len(snapshot.checksums)
        )
        self.assertEqual(
            {integration.EXPECTED_ARCHIVE_DIRECTORY_MODE},
            set(snapshot.directories.values()),
        )
        self.assertEqual(
            {"scripts/validate_database_design.py"},
            {path for path, mode in snapshot.file_modes.items() if mode == 0o755},
        )

    def test_02_clean_write_check_and_repeated_write_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-large-db-install-") as temporary:
            repository = Path(temporary)
            self.copy_archive(repository)
            with mock.patch.object(
                subprocess,
                "run",
                side_effect=AssertionError("importer executed source package code"),
            ):
                first = integration.write_install(repository)
                checked = integration.check_install(repository)
                second = integration.write_install(repository)

            self.assertEqual(first["manifest_bytes"], checked["manifest_bytes"])
            self.assertEqual(first["manifest_bytes"], second["manifest_bytes"])
            source = repository / integration.SOURCE_RELATIVE
            snapshot = integration.read_archive(repository / integration.ARCHIVE_RELATIVE)
            validated = integration.validate_source_tree(source, snapshot)
            self.assertEqual(integration.EXPECTED_SOURCE_FILES, len(validated["files"]))
            self.assertEqual(
                {integration.CANONICAL_DIRECTORY_MODE},
                set(validated["directories"].values()),
            )

    def test_03_normalized_skill_is_valid_and_preserves_canonical_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-large-db-normalized-") as temporary:
            repository = Path(temporary)
            self.copy_archive(repository)
            result = integration.write_install(repository)
            snapshot = result["summary"]["snapshot"]
            canonical = (
                repository / integration.SOURCE_RELATIVE / integration.SOURCE_SKILL_RELATIVE
            )
            self.assertEqual(
                snapshot.files[integration.SOURCE_SKILL_RELATIVE.as_posix()],
                canonical.read_bytes(),
            )
            for relative_root in (
                integration.RUNTIME_RELATIVE,
                integration.WORKSPACE_RELATIVE,
            ):
                skill_root = repository / relative_root / integration.SKILL_NAME
                valid, message = integration.skill_creator_tools.validate_skill(skill_root)
                self.assertTrue(valid, message)
                text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
                match = integration.re.match(r"^---\n(.*?)\n---", text, integration.re.DOTALL)
                self.assertIsNotNone(match)
                assert match is not None
                frontmatter = yaml.safe_load(match.group(1))
                self.assertNotIn("compatibility", frontmatter)
                self.assertIn("source_compatibility", frontmatter["metadata"])
                self.assertEqual(
                    "STATIC_VALIDATED", frontmatter["metadata"]["implementation_state"]
                )
                self.assertEqual(
                    "NOT_CERTIFIED", frontmatter["metadata"]["certification"]
                )

    def test_04_manifest_records_source_defects_and_fail_closed_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-large-db-manifest-") as temporary:
            repository = Path(temporary)
            self.copy_archive(repository)
            result = integration.write_install(repository)
            manifest_path = (
                repository / integration.DOC_RELATIVE / integration.INSTALL_MANIFEST_NAME
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(result["manifest"], manifest)
            self.assertEqual(
                "PRESERVED_SOURCE_DRIFT", manifest["source_version_drift"]["state"]
            )
            self.assertEqual(
                "1.0.0",
                manifest["source_version_drift"]["package_manifest_version"],
            )
            self.assertEqual(
                "1.1.0",
                manifest["source_version_drift"]["validation_report_heading_version"],
            )
            self.assertEqual(
                "PRESENT_BROKEN_REFERENCE",
                manifest["broken_source_workflow_reference"]["state"],
            )
            self.assertFalse(
                manifest["broken_source_workflow_reference"]
                ["referenced_path_present_in_archive"]
            )
            partition_defect = manifest["postgresql_partition_constraint_defect"]
            self.assertEqual(
                "PRESERVED_CANONICAL_SOURCE_REQUIRES_COMPATIBILITY_OVERLAY",
                partition_defect["state"],
            )
            self.assertFalse(partition_defect["canonical_source_mutated"])
            self.assertEqual("NOT_APPROVED", partition_defect["production_resolution"])
            slot_defect = manifest["postgresql_account_slot_uniqueness_defect"]
            self.assertEqual(
                "PRESERVED_CANONICAL_SOURCE_REQUIRES_COMPATIBILITY_OVERLAY",
                slot_defect["state"],
            )
            self.assertEqual("core.account_task_slot", slot_defect["affected_table"])
            self.assertFalse(slot_defect["canonical_source_mutated"])
            self.assertEqual("NOT_APPROVED", slot_defect["production_resolution"])
            evidence = manifest["evidence"]
            self.assertEqual("STATIC_VALIDATED", evidence["maximum_local_status"])
            self.assertFalse(evidence["source_scripts_executed_by_importer"])
            for field in (
                "postgresql_16_runtime_evidence",
                "postgresql_17_runtime_evidence",
                "migration_execution_evidence",
                "concurrency_evidence",
                "rls_evidence",
                "failover_evidence",
                "upgrade_evidence",
                "restore_evidence",
                "external_evidence",
            ):
                self.assertEqual("NOT_RUN", evidence[field], field)
            self.assertEqual("NOT_CERTIFIED", evidence["certification"])
            self.assertEqual(
                manifest["installation"]["runtime_tree_sha256"],
                manifest["installation"]["workspace_tree_sha256"],
            )
            self.assertTrue(manifest["installation"]["dual_root_byte_identical"])
            self.assertTrue(manifest["installation"]["interface_sha256"].startswith("sha256:"))

    def test_05_unsafe_and_non_normal_archive_paths_fail_closed(self) -> None:
        root = integration.PACKAGE_DIRECTORY
        variants = (
            f"/{root}/database/examples/",
            f"../{root}/database/examples/",
            f"{root}\\database\\examples/",
            f"{root}/database//examples/",
            f"C:/{root}/database/examples/",
        )
        original_name = f"{root}/database/examples/"
        for index, variant in enumerate(variants):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory(
                prefix=f"elmos-large-db-path-{index}-"
            ) as temporary:
                archive = Path(temporary) / "fixture.zip"

                def mutate(_index, info, data):
                    if info.filename == original_name:
                        info.filename = variant
                    return info, data

                self.rewrite_archive(archive, mutate)
                with self.assertRaisesRegex(
                    integration.IntegrationError,
                    "unsafe|non-normal|absolute|traversal|outside",
                ):
                    integration.read_archive(archive, enforce_identity=False)

    def test_06_casefold_collision_symlink_and_unsupported_modes_fail_closed(self) -> None:
        root = integration.PACKAGE_DIRECTORY
        cases = {
            "casefold": "casefold-colliding",
            "symlink": "symbolic link",
            "file-mode": "file mode",
            "directory-mode": "directory mode",
        }
        for case, message in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix=f"elmos-large-db-{case}-"
            ) as temporary:
                archive = Path(temporary) / "fixture.zip"

                def mutate(_index, info, data):
                    if case == "casefold" and info.filename == f"{root}/database/examples/":
                        info.filename = f"{root}/database/QUERIES/"
                    elif case == "symlink" and info.filename == f"{root}/README.md":
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    elif case == "file-mode" and info.filename == f"{root}/README.md":
                        info.external_attr = (stat.S_IFREG | 0o600) << 16
                    elif case == "directory-mode" and info.filename == f"{root}/database/":
                        info.external_attr = (stat.S_IFDIR | 0o755) << 16
                    return info, data

                self.rewrite_archive(archive, mutate)
                with self.assertRaisesRegex(integration.IntegrationError, message):
                    integration.read_archive(archive, enforce_identity=False)

    def test_07_checksum_mismatch_and_unchecked_extra_path_fail_closed(self) -> None:
        root = integration.PACKAGE_DIRECTORY
        cases = ("checksum", "unchecked")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix=f"elmos-large-db-{case}-"
            ) as temporary:
                archive = Path(temporary) / "fixture.zip"

                def mutate(_index, info, data):
                    if info.filename == f"{root}/README.md":
                        if case == "checksum":
                            data = b"!" + data[1:]
                        else:
                            info.filename = f"{root}/UNTRACKED.md"
                    return info, data

                self.rewrite_archive(archive, mutate)
                with self.assertRaisesRegex(
                    integration.IntegrationError,
                    "checksum mismatch|checksum coverage|unchecked",
                ):
                    integration.read_archive(archive, enforce_identity=False)

    def test_08_canonical_source_byte_and_mode_drift_fail_closed(self) -> None:
        cases = ("bytes", "mode")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix=f"elmos-large-db-source-{case}-"
            ) as temporary:
                repository = Path(temporary)
                self.copy_archive(repository)
                source = integration.extract_canonical_source(repository)
                target = source / "README.md"
                if case == "bytes":
                    target.write_bytes(target.read_bytes() + b"drift\n")
                    message = "bytes differ"
                else:
                    target.chmod(0o600)
                    message = "file mode differs"
                with self.assertRaisesRegex(integration.IntegrationError, message):
                    integration.validate_source(repository)

    def test_09_installed_content_mode_directory_and_manifest_drift_fail_closed(self) -> None:
        targets = ("source", "interface", "mode", "empty-directory", "manifest")
        for target_name in targets:
            with self.subTest(target=target_name), tempfile.TemporaryDirectory(
                prefix=f"elmos-large-db-installed-{target_name}-"
            ) as temporary:
                repository = Path(temporary)
                self.copy_archive(repository)
                integration.write_install(repository)
                if target_name == "source":
                    target = (
                        repository
                        / integration.RUNTIME_RELATIVE
                        / integration.SKILL_NAME
                        / "SKILL.md"
                    )
                elif target_name == "interface":
                    target = (
                        repository
                        / integration.WORKSPACE_RELATIVE
                        / integration.SKILL_NAME
                        / "agents/openai.yaml"
                    )
                elif target_name == "manifest":
                    target = (
                        repository
                        / integration.DOC_RELATIVE
                        / integration.INSTALL_MANIFEST_NAME
                    )
                elif target_name == "mode":
                    target = (
                        repository
                        / integration.RUNTIME_RELATIVE
                        / integration.SKILL_NAME
                        / "SKILL.md"
                    )
                else:
                    target = (
                        repository
                        / integration.WORKSPACE_RELATIVE
                        / integration.SKILL_NAME
                        / "unexpected-empty"
                    )
                if target_name == "mode":
                    target.chmod(0o600)
                elif target_name == "empty-directory":
                    target.mkdir()
                else:
                    target.write_bytes(target.read_bytes() + b"drift\n")
                with self.assertRaisesRegex(
                    integration.IntegrationError, "installed drift|manifest drift|drifted"
                ):
                    integration.check_install(repository)

    def test_10_first_write_refuses_unowned_install_collisions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-large-db-collision-") as temporary:
            repository = Path(temporary)
            self.copy_archive(repository)
            collision = (
                repository / integration.RUNTIME_RELATIVE / integration.SKILL_NAME
            )
            collision.mkdir(parents=True)
            (collision / "SKILL.md").write_text("user-owned\n", encoding="utf-8")
            with self.assertRaisesRegex(
                integration.IntegrationError, "unowned installed Skill"
            ):
                integration.write_install(repository)
            self.assertEqual(
                "user-owned\n", (collision / "SKILL.md").read_text(encoding="utf-8")
            )

    def test_11_staged_validation_failure_rolls_back_and_symlinked_ancestor_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-large-db-rollback-") as temporary:
            repository = Path(temporary)
            self.copy_archive(repository)
            with mock.patch.object(
                integration.skill_creator_tools,
                "validate_skill",
                return_value=(False, "injected invalid Skill"),
            ):
                with self.assertRaisesRegex(
                    integration.IntegrationError, "injected invalid Skill"
                ):
                    integration.write_install(repository)
            self.assertFalse(
                (repository / integration.RUNTIME_RELATIVE / integration.SKILL_NAME).exists()
            )
            self.assertFalse(
                (repository / integration.WORKSPACE_RELATIVE / integration.SKILL_NAME).exists()
            )
            self.assertFalse(
                (
                    repository
                    / integration.DOC_RELATIVE
                    / integration.INSTALL_MANIFEST_NAME
                ).exists()
            )

        with tempfile.TemporaryDirectory(prefix="elmos-large-db-ancestor-") as temporary:
            repository = Path(temporary)
            self.copy_archive(repository)
            outside = repository / "outside"
            outside.mkdir()
            (repository / "agent-skills").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(
                integration.IntegrationError, "symbolic-link ancestor"
            ):
                integration.write_install(repository)
            self.assertEqual([], list(outside.iterdir()))

    def test_12_runtime_migration_overlay_is_exact_and_fails_closed(self) -> None:
        source_root = ROOT / integration.SOURCE_RELATIVE
        with tempfile.TemporaryDirectory(prefix="elmos-large-db-overlay-") as temporary:
            temporary_root = Path(temporary)
            output_root = temporary_root / "rendered"
            result = runtime_renderer.render_runtime_migrations(source_root, output_root)
            self.assertEqual(
                len(runtime_renderer.EXPECTED_MIGRATIONS), result["migration_count"]
            )
            patched = (output_root / runtime_renderer.PATCHED_MIGRATION).read_bytes()
            self.assertEqual(
                runtime_renderer.EXPECTED_PATCH_OUTPUT_SHA256,
                runtime_renderer.sha256_bytes(patched),
            )
            self.assertIn(b") PARTITION BY HASH (tenant_id);", patched)
            self.assertNotIn(b") PARTITION BY HASH (run_id);", patched)
            self.assertNotIn(b") PARTITION BY HASH (session_id);", patched)
            self.assertIn(b"UNIQUE (tenant_id, event_id)", patched)
            self.assertIn(
                b"UNIQUE (tenant_id, temporal_namespace, temporal_workflow_id, temporal_run_id)",
                patched,
            )
            self.assertNotIn(
                b"UNIQUE NULLS NOT DISTINCT (tenant_id, temporal_namespace, temporal_workflow_id, temporal_run_id)",
                patched,
            )

            account_slot = (
                output_root / runtime_renderer.ACCOUNT_SLOT_MIGRATION
            ).read_bytes()
            self.assertEqual(
                runtime_renderer.EXPECTED_ACCOUNT_SLOT_OUTPUT_SHA256,
                runtime_renderer.sha256_bytes(account_slot),
            )
            self.assertIn(
                b"UNIQUE (tenant_id, claimed_by_run_id)", account_slot
            )
            self.assertNotIn(
                b"UNIQUE NULLS NOT DISTINCT (tenant_id, claimed_by_run_id)",
                account_slot,
            )

            unchanged = runtime_renderer.EXPECTED_MIGRATIONS[0]
            self.assertEqual(
                (source_root / "database" / "migrations" / unchanged).read_bytes(),
                (output_root / unchanged).read_bytes(),
            )

            drifted_source = temporary_root / "drifted-source"
            shutil.copytree(source_root, drifted_source)
            drifted_v020 = (
                drifted_source
                / "database"
                / "migrations"
                / runtime_renderer.PATCHED_MIGRATION
            )
            drifted_v020.write_bytes(drifted_v020.read_bytes() + b"-- drift\n")
            with self.assertRaisesRegex(
                runtime_renderer.RuntimeMigrationError, "checksum mismatch"
            ):
                runtime_renderer.render_runtime_migrations(
                    drifted_source, temporary_root / "rejected"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
