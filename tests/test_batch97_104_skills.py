from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "elmos-codex-skills-batch97-104-complete"
INSTALLED_MANIFEST = ROOT / "docs" / "batch97-104" / "installed-manifest.json"


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class Batch97104RepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
        cls.installed = json.loads(INSTALLED_MANIFEST.read_text(encoding="utf-8"))

    def test_importer_check_is_idempotent(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tooling" / "import_batch97_104_assets.py"), "--check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"skills": 128', result.stdout)

    def test_exact_identity_and_namespace_are_preserved(self) -> None:
        expected = [f"B{batch}-S{sequence:02d}" for batch in range(97, 105) for sequence in range(1, 17)]
        self.assertEqual(expected, [entry["id"] for entry in self.package["skills"]])
        self.assertEqual(128, self.package["skill_count"])
        self.assertTrue(all(entry["global_id"] is None for entry in self.package["skills"]))
        self.assertEqual("batch-local-product-closure", self.installed["source_id_namespace"])
        self.assertEqual("UNASSIGNED", self.installed["global_id_assignment"])
        self.assertEqual("NOT_RUN", self.installed["external_evidence_status"])

    def test_all_128_installed_skills_and_interfaces_match_source_digests(self) -> None:
        self.assertEqual(128, len(self.installed["skills"]))
        expected_names = {entry["installed_name"] for entry in self.installed["skills"]}
        actual_names = {
            path.parent.name
            for batch in range(97, 105)
            for path in (ROOT / "agent-skills" / "runtime").glob(f"b{batch}-*/SKILL.md")
        }
        self.assertEqual(expected_names, actual_names)
        for entry in self.installed["skills"]:
            source = ROOT / entry["source_path"]
            installed = ROOT / entry["installed_path"]
            interface = ROOT / entry["interface_path"]
            self.assertEqual(entry["source_sha256"], sha256(source))
            self.assertEqual(entry["installed_sha256"], sha256(installed))
            self.assertEqual(entry["interface_sha256"], sha256(interface))
            self.assertEqual(source.read_bytes(), installed.read_bytes())
            self.assertIn(f"${entry['installed_name']}", interface.read_text(encoding="utf-8"))

    def test_normalization_records_repairs_without_external_claims(self) -> None:
        record = json.loads((PACKAGE / "NORMALIZATION.json").read_text(encoding="utf-8"))
        self.assertEqual("NOT_RUN", record["external_evidence_status"])
        repairs = {entry["code"]: entry for entry in record["repairs"]}
        self.assertEqual(32, repairs["DUPLICATE_OUTPUTS"]["affected_skills"])
        self.assertEqual(["B101-S16", "B102-S15"], repairs["BLOCKING_DEPENDENCY_CYCLES"]["affected_skills"])

    def test_no_evidence_gate_fails_closed(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(PACKAGE / "scripts" / "run_certification_gate.py"),
                "--package",
                str(PACKAGE),
                "--scope",
                "B104-S16",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("not_run", payload["status"])
        self.assertNotIn("certified", payload)


if __name__ == "__main__":
    unittest.main()
