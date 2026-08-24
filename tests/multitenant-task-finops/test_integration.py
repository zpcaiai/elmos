from __future__ import annotations

import importlib.util
import io
import json
import shutil
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
IMPORTER_PATH = REPOSITORY_ROOT / "tooling/integrate_multitenant_task_finops_skills.py"
SPEC = importlib.util.spec_from_file_location(
    "integrate_multitenant_task_finops_skills",
    IMPORTER_PATH,
)
assert SPEC is not None and SPEC.loader is not None
integration = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = integration
SPEC.loader.exec_module(integration)


class MultitenantTaskFinopsIntegrationTests(unittest.TestCase):
    def real_archive(self) -> Path:
        return REPOSITORY_ROOT / integration.ARCHIVE_RELATIVE_PATH

    def temporary_repository(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        archive = root / integration.ARCHIVE_RELATIVE_PATH
        archive.parent.mkdir(parents=True)
        shutil.copyfile(self.real_archive(), archive)
        return temporary, root

    def test_pinned_archive_contract_is_exact(self) -> None:
        snapshot = integration.validate_archive(self.real_archive())

        self.assertEqual(integration.EXPECTED_ARCHIVE_SHA256, snapshot.archive_sha256)
        self.assertEqual(122, len(snapshot.files))
        self.assertEqual(12, len(snapshot.skills))
        self.assertEqual(144, len(snapshot.tasks))
        self.assertEqual(12, len(snapshot.dependency_order))
        self.assertEqual(
            (
                "elmos-architecture-contract-governance",
                "elmos-identity-tenant-security",
                "elmos-observability-finops",
                "elmos-temporal-task-reliability",
            ),
            snapshot.external_dependencies,
        )
        self.assertEqual(
            {"P0": 96, "P1": 48},
            dict(integration.Counter(task.priority for task in snapshot.tasks)),
        )

    def test_archive_size_is_rejected_before_reading_sparse_payload(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        archive = Path(temporary.name) / "oversized.zip"
        with archive.open("wb") as handle:
            handle.truncate(1024 * 1024 * 1024)

        with self.assertRaisesRegex(integration.IntegrationError, "byte count mismatch"):
            integration.validate_archive(archive)

    def test_write_check_and_second_write_are_idempotent(self) -> None:
        temporary, root = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        archive = root / integration.ARCHIVE_RELATIVE_PATH

        written = integration.write_integration(root, archive)
        checked = integration.check_integration(root, archive)
        second = integration.write_integration(root, archive)

        self.assertEqual(written.archive_sha256, checked.archive_sha256)
        self.assertEqual(checked.archive_sha256, second.archive_sha256)
        source = root / integration.SOURCE_RELATIVE_PATH
        self.assertTrue((source / "FILE-MANIFEST.sha256").is_file())
        for install_root in integration.INSTALL_ROOTS:
            for skill in written.skills:
                skill_root = root / install_root / skill.name
                self.assertTrue((skill_root / "SKILL.md").is_file())
                self.assertTrue((skill_root / "agents/openai.yaml").is_file())

        installed = json.loads(
            (root / integration.INSTALLED_MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8")
        )
        self.assertFalse(installed["package_scripts_executed"])
        self.assertEqual("NOT_APPLIED", installed["reference_material_application_status"])
        self.assertEqual("DECLARED_UNRESOLVED", installed["external_dependency_status"])
        self.assertEqual("NOT_RUN", installed["external_evidence_status"])
        self.assertEqual("NOT_CERTIFIED", installed["certification_status"])

    def test_exact_legacy_generated_output_refreshes_without_broad_deletion(self) -> None:
        temporary, root = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        archive = root / integration.ARCHIVE_RELATIVE_PATH
        snapshot = integration.validate_archive(archive)

        integration._write_tree_atomic(
            root / integration.SOURCE_RELATIVE_PATH,
            integration._source_files(snapshot),
        )
        for install_root in integration.INSTALL_ROOTS:
            for skill in snapshot.skills:
                integration._write_tree_atomic(
                    root / install_root / skill.name,
                    integration._skill_files(
                        snapshot,
                        skill,
                        include_repository_boundary=False,
                    ),
                )
        for relative, content in integration._integration_artifacts(
            snapshot,
            include_repository_boundary=False,
            include_current_safety_assessment=False,
        ).items():
            integration._write_file_atomic(root / relative, content)

        integration.write_integration(root, archive)
        integration.check_integration(root, archive)

        installed = (
            root
            / integration.INSTALL_ROOTS[0]
            / snapshot.skills[0].name
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("## Repository integration boundary", installed)
        self.assertIn("Do not execute bundled package code", installed)
        self.assertIn("certification remains `NOT_CERTIFIED`", installed)

    def test_exact_prior_risk_register_refreshes_without_overwriting_drift(self) -> None:
        temporary, root = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        archive = root / integration.ARCHIVE_RELATIVE_PATH
        snapshot = integration.validate_archive(archive)

        integration._write_tree_atomic(
            root / integration.SOURCE_RELATIVE_PATH,
            integration._source_files(snapshot),
        )
        for install_root in integration.INSTALL_ROOTS:
            for skill in snapshot.skills:
                integration._write_tree_atomic(
                    root / install_root / skill.name,
                    integration._skill_files(snapshot, skill),
                )
        for relative, content in integration._integration_artifacts(
            snapshot,
            include_current_safety_assessment=False,
        ).items():
            integration._write_file_atomic(root / relative, content)

        integration.write_integration(root, archive)
        integration.check_integration(root, archive)
        register = json.loads(
            (root / integration.SOURCE_RISK_REGISTER_RELATIVE_PATH).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(11, register["open_zero_tolerance_findings"])
        self.assertEqual(
            "BYTE_IDENTITY_ONLY",
            register["supply_chain"]["archive_digest_meaning"],
        )

    def test_normalized_skills_preserve_source_provenance(self) -> None:
        temporary, root = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        snapshot = integration.write_integration(
            root,
            root / integration.ARCHIVE_RELATIVE_PATH,
        )

        skill = snapshot.skills[0]
        installed = (root / integration.INSTALL_ROOTS[0] / skill.name / "SKILL.md").read_text(
            encoding="utf-8"
        )
        frontmatter = installed.split("---", 2)[1]
        self.assertIn(f'name: "{skill.name}"', frontmatter)
        self.assertIn("metadata:", frontmatter)
        self.assertIn(f'source_id: "{skill.skill_id}"', frontmatter)
        self.assertIn(f'source_sha256: "sha256:{skill.skill_md_sha256}"', frontmatter)
        self.assertNotIn("\nid:", frontmatter)
        self.assertNotIn("\ndepends_on:", frontmatter)
        interface = (
            root / integration.INSTALL_ROOTS[0] / skill.name / "agents/openai.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(f"${skill.name}", interface)
        self.assertIn("## Repository integration boundary", installed)

    def test_collision_fails_before_any_installation_is_written(self) -> None:
        temporary, root = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        snapshot = integration.validate_archive(root / integration.ARCHIVE_RELATIVE_PATH)
        conflict = root / integration.INSTALL_ROOTS[-1] / snapshot.skills[-1].name
        conflict.mkdir(parents=True)
        marker = conflict / "SKILL.md"
        marker.write_text("user-owned\n", encoding="utf-8")

        with self.assertRaisesRegex(integration.IntegrationError, "refusing to overwrite"):
            integration.write_integration(root, root / integration.ARCHIVE_RELATIVE_PATH)

        self.assertEqual("user-owned\n", marker.read_text(encoding="utf-8"))
        self.assertFalse((root / integration.SOURCE_RELATIVE_PATH).exists())
        self.assertFalse(
            (root / integration.INSTALL_ROOTS[0] / snapshot.skills[0].name).exists()
        )

    def test_repository_paths_reject_every_symlink_component(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        real_agents = root / "real-agents"
        real_agents.mkdir()
        (root / ".agents").symlink_to(real_agents, target_is_directory=True)

        with self.assertRaisesRegex(integration.IntegrationError, "symlink component"):
            integration._resolve_below(root, Path(".agents/skills/example"))

        real_docs = root / "real-docs"
        real_docs.mkdir()
        docs = root / "docs"
        docs.mkdir()
        (docs / "generated.json").symlink_to(real_docs / "generated.json")
        with self.assertRaisesRegex(integration.IntegrationError, "symlink component"):
            integration._resolve_below(root, Path("docs/generated.json"))

    def test_atomic_file_write_rechecks_preflight_ownership(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        destination = root / "docs/generated.json"
        destination.parent.mkdir()
        destination.write_bytes(b"changed-after-preflight")

        with self.assertRaisesRegex(integration.IntegrationError, "changed after preflight"):
            integration._write_file_atomic(
                destination,
                b"replacement",
                safety_root=root,
                expected_existing=b"owned-before-preflight",
            )
        self.assertEqual(b"changed-after-preflight", destination.read_bytes())

        with self.assertRaisesRegex(integration.IntegrationError, "appeared after preflight"):
            integration._write_file_atomic(
                destination,
                b"replacement",
                safety_root=root,
                must_be_absent=True,
            )
        self.assertEqual(b"changed-after-preflight", destination.read_bytes())

    def test_generated_artifact_mode_drift_is_rejected_consistently(self) -> None:
        temporary, root = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        archive = root / integration.ARCHIVE_RELATIVE_PATH
        integration.write_integration(root, archive)
        artifact = root / integration.INTEGRATION_README_RELATIVE_PATH
        artifact.chmod(0o755)

        with self.assertRaisesRegex(integration.IntegrationError, "refusing to overwrite"):
            integration.write_integration(root, archive)
        with self.assertRaisesRegex(integration.IntegrationError, "mode drifted"):
            integration.check_integration(root, archive)
        self.assertEqual(0o755, stat.S_IMODE(artifact.stat().st_mode))

    def test_check_rejects_source_and_installed_drift(self) -> None:
        temporary, root = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        snapshot = integration.write_integration(root, root / integration.ARCHIVE_RELATIVE_PATH)
        installed = root / integration.INSTALL_ROOTS[0] / snapshot.skills[0].name / "SKILL.md"
        installed.write_text(installed.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")

        with self.assertRaisesRegex(integration.IntegrationError, "drifted"):
            integration.check_integration(root, root / integration.ARCHIVE_RELATIVE_PATH)

    def test_checksum_validation_rejects_member_tampering(self) -> None:
        snapshot = integration.validate_archive(self.real_archive())
        files = dict(snapshot.files)
        target = "README.md"
        original = files[target]
        files[target] = integration.FilePayload(
            content=original.content + b"tampered\n",
            mode=original.mode,
        )

        with self.assertRaisesRegex(integration.IntegrationError, "checksum mismatch"):
            integration._validate_internal_checksums(files)

    def test_archive_structure_rejects_traversal_links_and_case_collisions(self) -> None:
        def archive_with(entries: list[tuple[str, int]]) -> zipfile.ZipFile:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                for name, mode in entries:
                    info = zipfile.ZipInfo(name)
                    info.create_system = 3
                    info.external_attr = mode << 16
                    archive.writestr(info, b"value")
            buffer.seek(0)
            handle = zipfile.ZipFile(buffer, "r")
            handle._test_buffer = buffer  # type: ignore[attr-defined]
            return handle

        regular = stat.S_IFREG | 0o644
        traversal = archive_with([(f"{integration.ARCHIVE_ROOT}/../escape", regular)])
        self.addCleanup(traversal.close)
        with self.assertRaises(integration.IntegrationError):
            integration._validate_central_directory(traversal, exact_inventory=False)

        symlink = archive_with([(f"{integration.ARCHIVE_ROOT}/link", stat.S_IFLNK | 0o777)])
        self.addCleanup(symlink.close)
        with self.assertRaisesRegex(integration.IntegrationError, "link or special"):
            integration._validate_central_directory(symlink, exact_inventory=False)

        collision = archive_with(
            [
                (f"{integration.ARCHIVE_ROOT}/A.txt", regular),
                (f"{integration.ARCHIVE_ROOT}/a.txt", regular),
            ]
        )
        self.addCleanup(collision.close)
        with self.assertRaisesRegex(integration.IntegrationError, "case-folding"):
            integration._validate_central_directory(collision, exact_inventory=False)

    def test_generated_matrix_keeps_every_repository_task_not_run(self) -> None:
        snapshot = integration.validate_archive(self.real_archive())
        matrix = integration._implementation_matrix(snapshot)

        self.assertEqual({"total": 144, "NOT_RUN": 144, "PASS": 0}, matrix["summary"])
        self.assertEqual(144, len(matrix["tasks"]))
        self.assertTrue(all(task["status"] == "NOT_RUN" for task in matrix["tasks"]))
        self.assertTrue(all(task["evidence"] == [] for task in matrix["tasks"]))


if __name__ == "__main__":
    unittest.main()
