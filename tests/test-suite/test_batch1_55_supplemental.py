import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "test-suites/batch1-55-slightly-strict"
VALIDATOR = ROOT / "scripts/test-suite/validate_batch1_55_slightly_strict.py"
GATE = ROOT / "scripts/test-suite/run_batch1_55_slightly_strict_gate.py"


class BatchOneToFiftyFiveSupplementalTest(unittest.TestCase):
    def command(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, cwd=ROOT, text=True, capture_output=True)

    def copy_suite(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        destination = Path(temporary.name) / "suite"
        shutil.copytree(SUITE, destination)
        return temporary, destination

    def test_suite_is_structurally_valid(self):
        result = self.command("python3", str(VALIDATOR), str(SUITE))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("660 cases", result.stdout)
        self.assertIn("42 repaired source ids", result.stdout)

    def test_all_source_ids_have_consistent_priority_after_normalization(self):
        catalog = json.loads((SUITE / "cases/catalog.json").read_text())
        for batch in catalog["batches"].values():
            for case in batch["cases"]:
                self.assertIn(f"-{case['priority']}-", case["id"])

    def test_gate_fails_closed_for_every_not_run_case(self):
        temporary, destination = self.copy_suite()
        try:
            result = self.command("python3", str(GATE), str(destination))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            gate = json.loads((destination / "release-gate.json").read_text())
            self.assertEqual(gate["decision"], "BLOCKED")
            self.assertFalse(gate["certification_authority"])
            self.assertEqual(gate["field_evidence_status"], "NOT_RUN")
            self.assertEqual(gate["metrics"]["status_counts"]["not-run"], 660)
            self.assertIn("migration-pack:M34-M45", gate["uncovered_repository_namespaces"])
        finally:
            temporary.cleanup()

    def test_validator_rejects_a_forged_pass_without_raw_evidence(self):
        temporary, destination = self.copy_suite()
        try:
            results_path = destination / "results/catalog.json"
            results = json.loads(results_path.read_text())
            result = results["cases"][0]
            result["status"] = "passed"
            result["artifact_digest"] = "sha256:" + "1" * 64
            result["environment_digest"] = "sha256:" + "2" * 64
            result["started_at"] = "2026-07-22T00:00:00Z"
            result["finished_at"] = "2026-07-22T00:00:01Z"
            results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
            outcome = self.command("python3", str(VALIDATOR), str(destination))
            self.assertNotEqual(outcome.returncode, 0)
            self.assertIn("requires immutable evidence", outcome.stdout)
        finally:
            temporary.cleanup()

    def test_validator_rejects_control_catalog_tampering(self):
        temporary, destination = self.copy_suite()
        try:
            catalog_path = destination / "cases/catalog.json"
            catalog = json.loads(catalog_path.read_text())
            catalog["batches"]["1"]["cases"][0]["then"] = "tampered assertion"
            catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
            outcome = self.command("python3", str(VALIDATOR), str(destination))
            self.assertNotEqual(outcome.returncode, 0)
            self.assertIn("controlled file digest mismatch", outcome.stdout)
        finally:
            temporary.cleanup()

    def test_source_skill_pack_does_not_replace_repository_test_authority(self):
        suite = json.loads((SUITE / "suite.json").read_text())
        self.assertFalse(suite["source_skills_installed"])
        self.assertFalse(suite["replaces_batch1_37_strict_suite"])
        self.assertEqual(suite["maximum_success_decision"], "READY_FOR_EXTERNAL_GATE")


if __name__ == "__main__":
    unittest.main()
