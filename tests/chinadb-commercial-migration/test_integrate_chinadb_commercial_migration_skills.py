from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLING_ROOT = REPOSITORY_ROOT / "tooling"
if str(TOOLING_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLING_ROOT))

import integrate_chinadb_commercial_migration_skills as integration


class ChinaDbCommercialMigrationIntegrationTest(unittest.TestCase):
    def temporary_repository(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory(prefix="chinadb-integration-")
        root = Path(temporary.name)
        source = root / integration.PACKAGE_RELATIVE
        source.parent.mkdir(parents=True)
        shutil.copytree(REPOSITORY_ROOT / integration.PACKAGE_RELATIVE, source)
        return temporary, root, source

    def test_source_contract_has_exact_inventory_and_spec_only_state(self) -> None:
        source = REPOSITORY_ROOT / integration.PACKAGE_RELATIVE
        summary = integration.validate_source(source)

        self.assertEqual(len(summary["inventory"]), 85)
        self.assertEqual(len(summary["checksums"]), 84)
        self.assertEqual(len(summary["skills"]), 47)
        self.assertEqual(len(summary["baselines"]), 13)
        self.assertEqual(len(summary["routes"]), 78)
        self.assertEqual(
            summary["aliases"],
            [f"chinadb-{source_directory}" for source_directory in integration.EXPECTED_SKILLS],
        )
        self.assertLessEqual(max(map(len, summary["aliases"])), 64)

    def test_source_checksum_tamper_fails_closed(self) -> None:
        temporary, _root, source = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        tampered = source / "skills" / "06-sql-auto-conversion" / "SKILL.md"
        tampered.write_bytes(tampered.read_bytes() + b"\nTAMPERED\n")

        with self.assertRaisesRegex(integration.IntegrationError, "checksum mismatch"):
            integration.validate_source(source)

    def test_source_and_self_describing_checksum_tamper_still_fails_trusted_root(self) -> None:
        temporary, _root, source = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        relative = "skills/06-sql-auto-conversion/SKILL.md"
        tampered = source / relative
        tampered.write_bytes(tampered.read_bytes() + b"\nTAMPERED AND REHASHED\n")
        replacement = hashlib.sha256(tampered.read_bytes()).hexdigest()
        checksum_path = source / "CHECKSUMS.sha256"
        lines = checksum_path.read_text(encoding="utf-8").splitlines()
        checksum_path.write_text(
            "\n".join(
                f"{replacement}  {relative}" if line.endswith(f"  {relative}") else line
                for line in lines
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(integration.IntegrationError, "trusted root digest mismatch"):
            integration.validate_source(source)

    def test_source_extra_file_breaks_exact_checksum_coverage(self) -> None:
        temporary, _root, source = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        (source / "unexpected.txt").write_text("not manifest owned\n", encoding="utf-8")

        with self.assertRaisesRegex(integration.IntegrationError, "exactly 85 files"):
            integration.validate_source(source)

    def test_source_symlink_is_rejected_before_path_traversal(self) -> None:
        temporary, _root, source = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        (source / "escape-link").symlink_to(Path(tempfile.gettempdir()))

        with self.assertRaisesRegex(integration.IntegrationError, "symbolic links"):
            integration.validate_source(source)

    def test_write_and_check_install_exact_dual_roots_and_baselines(self) -> None:
        temporary, root, source = self.temporary_repository()
        self.addCleanup(temporary.cleanup)

        expected = integration.write_install(root, source)
        checked = integration.check_install(root, source)
        self.assertEqual(expected["manifest_bytes"], checked["manifest_bytes"])

        manifest_path = root / integration.DOC_RELATIVE / integration.INSTALL_MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["implementation_state"], "SPEC_ONLY")
        self.assertEqual(manifest["external_evidence_status"], "NOT_RUN")
        self.assertEqual(manifest["production_certification"], "NOT_CERTIFIED")
        self.assertTrue(manifest["dual_root_byte_identical"])
        self.assertEqual(len(manifest["source_files"]), 85)
        self.assertEqual(len(manifest["skills"]), 47)
        self.assertEqual(
            sum(record["target_baseline"] is not None for record in manifest["skills"]),
            13,
        )
        for record in manifest["skills"]:
            self.assertFalse(record["implemented"])
            self.assertEqual(record["evidence_ids"], [])
            self.assertEqual(record["implementation_state"], "SPEC_ONLY")
            self.assertEqual(record["external_evidence_status"], "NOT_RUN")
            self.assertEqual(record["production_certification"], "NOT_CERTIFIED")
            alias = record["installed_alias"]
            runtime = root / integration.RUNTIME_RELATIVE / alias
            workspace = root / integration.WORKSPACE_RELATIVE / alias
            self.assertEqual(integration._read_tree(runtime), integration._read_tree(workspace))
            installed_text = (runtime / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(installed_text.startswith(f"---\nname: {alias}\n"))
            self.assertIn("\ndescription: \"", installed_text)
            self.assertIn("\nmetadata:\n", installed_text)
            self.assertIn("source_sha256: \"sha256:", installed_text)
            self.assertIn("## Repository Integration Boundary", installed_text)
            self.assertTrue((runtime / "agents" / "openai.yaml").is_file())

    def test_check_detects_installed_skill_drift(self) -> None:
        temporary, root, source = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        expected = integration.write_install(root, source)
        alias = sorted(expected["trees"])[0]
        drifted = root / integration.RUNTIME_RELATIVE / alias / "SKILL.md"
        drifted.write_bytes(drifted.read_bytes() + b"\nDRIFT\n")

        with self.assertRaisesRegex(integration.IntegrationError, "installation drifted"):
            integration.check_install(root, source)

        with self.assertRaisesRegex(integration.IntegrationError, "has drifted"):
            integration.write_install(root, source)

    def test_write_refuses_unowned_alias_collision(self) -> None:
        temporary, root, source = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        alias = integration.alias_for(integration.EXPECTED_SKILLS[0])
        collision = root / integration.RUNTIME_RELATIVE / alias
        collision.mkdir(parents=True)
        (collision / "SKILL.md").write_text("unowned\n", encoding="utf-8")

        with self.assertRaisesRegex(integration.IntegrationError, "unowned Runtime Skill"):
            integration.write_install(root, source)

    def test_forged_manifest_cannot_claim_or_replace_user_skill(self) -> None:
        temporary, root, source = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        expected = integration.build_expected(source)
        forged = json.loads(expected["manifest_bytes"])
        forged["forged_owner_claim"] = True
        doc_root = root / integration.DOC_RELATIVE
        doc_root.mkdir(parents=True)
        (doc_root / integration.INSTALL_MANIFEST_NAME).write_text(
            json.dumps(forged), encoding="utf-8"
        )
        (doc_root / integration.README_NAME).write_bytes(expected["readme_bytes"])
        alias = integration.alias_for(integration.EXPECTED_SKILLS[0])
        user_skill = root / integration.RUNTIME_RELATIVE / alias
        user_skill.mkdir(parents=True)
        marker = user_skill / "user-owned.txt"
        marker.write_text("preserve me\n", encoding="utf-8")

        with self.assertRaisesRegex(integration.IntegrationError, "trusted generated manifest"):
            integration.write_install(root, source)
        self.assertEqual("preserve me\n", marker.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
