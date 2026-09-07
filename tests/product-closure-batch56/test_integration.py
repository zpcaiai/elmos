from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "elmos-codex-skills-batch56-product-closure"
MANIFEST = ROOT / "docs" / "product-closure-batch56" / "installed-manifest.json"
OVERLAP_MAP = ROOT / "docs" / "product-closure-batch56" / "overlap-map.json"
IMPORTER = ROOT / "tooling" / "import_product_batch56_closure.py"
EXPECTED_IDS = [f"C56-{number:02d}" for number in range(1, 17)]

# The canonical import bundle is intentionally absent from a normal source
# checkout (see tooling/validate_batch97_104_installed.py for the same rule).
# The assertions that read the bundle are skipped with an explicit reason in
# that case; the installed-distribution assertions below always run, so an
# absent bundle can never be mistaken for a validated one.
SOURCE_PACKAGE_PRESENT = (PACKAGE / "manifest.json").is_file()
SOURCE_PACKAGE_ABSENT_REASON = (
    f"SOURCE_PACKAGE_ABSENT={PACKAGE.name} "
    "reason=missing:manifest.json — source-bundle assertions skipped; "
    "installed distribution is still validated"
)
requires_source_package = unittest.skipUnless(
    SOURCE_PACKAGE_PRESENT, SOURCE_PACKAGE_ABSENT_REASON
)


class ProductBatch56IntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (
            json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
            if SOURCE_PACKAGE_PRESENT
            else {}
        )
        cls.installed = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.overlaps = json.loads(OVERLAP_MAP.read_text(encoding="utf-8"))

    @requires_source_package
    def test_importer_verifies_exact_install(self) -> None:
        result = subprocess.run(
            [sys.executable, str(IMPORTER)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(16, report["source_skills"])
        self.assertEqual(5, report["source_name_length_invalid"])
        self.assertEqual(11, report["source_skill_creator_compatible_valid"])
        self.assertEqual(16, report["installed_skills_valid"])
        self.assertEqual("inactive", report["activation_default"])
        self.assertEqual("NOT_RUN", report["external_evidence"])

    @requires_source_package
    def test_source_identity_and_inventory_are_exact(self) -> None:
        self.assertEqual("56", self.source["batch"])
        self.assertEqual(EXPECTED_IDS, [item["id"] for item in self.source["skills"]])
        inventory = json.loads(
            (ROOT / "docs" / "product-closure-batch56" / "source-inventory.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(25, inventory["file_count"])
        self.assertEqual(25, len(inventory["files"]))
        for item in inventory["files"]:
            self.assertRegex(item["sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertGreater(item["bytes"], 0)
        self.assertTrue(os.access(PACKAGE / "validate.sh", os.X_OK))
        self.assertTrue(os.access(PACKAGE / "install.sh", os.X_OK))

    def test_aliases_are_unique_bounded_and_provenance_bound(self) -> None:
        skills = self.installed["skills"]
        aliases = [item["installed_alias"] for item in skills]
        self.assertEqual(16, len(aliases))
        self.assertEqual(16, len(set(aliases)))
        self.assertTrue(all(alias.startswith("b56-") and len(alias) <= 64 for alias in aliases))
        for item in skills:
            path = ROOT / item["installed_path"]
            content = path.read_text(encoding="utf-8")
            frontmatter = yaml.safe_load(content.split("---", 2)[1])
            self.assertEqual(item["installed_alias"], frontmatter["name"])
            self.assertEqual(item["source_id"], frontmatter["metadata"]["source_id"])
            self.assertEqual("inactive", frontmatter["metadata"]["activation_default"])
            self.assertEqual("product-batch56a", frontmatter["metadata"]["readiness_authority"])
            self.assertIn("reviewed implementation guidance", content)
            self.assertIn("cannot approve GA", content)

    def test_all_semantic_overlaps_are_explicit_and_inactive(self) -> None:
        relationships = self.overlaps["relationships"]
        self.assertEqual(EXPECTED_IDS, [item["source_id"] for item in relationships])
        self.assertTrue(
            all(item["relationship"] == "supplementary-overlap" for item in relationships)
        )
        self.assertTrue(all(item["product_56a_source_ids"] for item in relationships))
        self.assertEqual("inactive", self.overlaps["activation_default"])
        self.assertEqual(
            "scripts/product-closure-batch56a/run_product_closure_gate.py",
            self.overlaps["readiness_authority"],
        )

    def test_exact_source_name_collision_does_not_overwrite_product56a(self) -> None:
        self.assertEqual(
            ["canonical-domain-kernel-consolidation"],
            self.installed["exact_runtime_name_collisions_before_aliasing"],
        )
        original = ROOT / "agent-skills" / "runtime" / "canonical-domain-kernel-consolidation"
        normalized = ROOT / "agent-skills" / "runtime" / "b56-canonical-domain-kernel-consolidation"
        self.assertTrue((original / "SKILL.md").is_file())
        self.assertTrue((normalized / "SKILL.md").is_file())
        self.assertNotEqual(
            (original / "SKILL.md").read_bytes(),
            (normalized / "SKILL.md").read_bytes(),
        )

    def test_source_static_validation_is_not_promoted_to_completion(self) -> None:
        template = json.loads(
            (
                ROOT
                / "templates"
                / "product-closure-batch56"
                / "closure-program-status.source.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual("PLANNED", template["status"])
        self.assertEqual([], template["evidenceRefs"])
        self.assertEqual("NOT_RUN", self.installed["external_evidence"])
        self.assertFalse(self.installed["ga_approved"])
        self.assertFalse(self.installed["production_certified"])
        self.assertEqual("READY_FOR_EXTERNAL_GATE", self.installed["maximum_local_decision"])
        self.assertEqual(
            "repository-pinned-skill-creator-compatible",
            self.installed["source_skill_validation"]["contract"],
        )


if __name__ == "__main__":
    unittest.main()
