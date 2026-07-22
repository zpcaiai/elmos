import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "test-suites/batch1-65-slightly-strict"
VALIDATOR = ROOT / "scripts/test-suite/validate_batch1_65_slightly_strict.py"
GATE = ROOT / "scripts/test-suite/run_batch1_65_slightly_strict_gate.py"


class BatchOneToSixtyFiveSupplementalTest(unittest.TestCase):
    def command(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)

    def copy_suite(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        destination = Path(temporary.name) / "suite"
        shutil.copytree(SUITE, destination)
        return temporary, destination

    def test_suite_is_structurally_valid(self):
        result = self.command("python3", str(VALIDATOR), str(SUITE))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("750 cases", result.stdout)
        self.assertIn("1296 source Skills", result.stdout)

    def test_release_gate_fails_closed_for_not_run_cases(self):
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        result = self.command("python3", str(GATE), str(suite))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        gate = json.loads((suite / "release-gate.json").read_text(encoding="utf-8"))
        self.assertEqual(gate["decision"], "BLOCKED")
        self.assertEqual(gate["field_evidence_status"], "NOT_RUN")
        self.assertEqual(gate["metrics"]["status_counts"]["NOT_RUN"], 750)
        self.assertFalse(gate["certification_authority"])

    def test_missing_result_cannot_gain_an_aggregate_pass(self):
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "results/catalog.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["results"].pop()
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        result = self.command("python3", str(VALIDATOR), str(suite))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly 750 results", result.stdout)
        self.assertIn("result and case ID sets differ", result.stdout)

    def test_not_run_result_cannot_claim_evidence(self):
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "results/catalog.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["results"][0]["artifact_digest"] = "sha256:" + "1" * 64
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        result = self.command("python3", str(VALIDATOR), str(suite))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NOT_RUN result cannot contain execution claims", result.stdout)

    def test_synthetic_pass_without_bindings_is_rejected(self):
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "results/catalog.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["results"][0]["status"] = "PASSED"
        payload["results"][0]["evidence_complete"] = True
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        result = self.command("python3", str(VALIDATOR), str(suite))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("passed result requires real or approved-equivalent execution", result.stdout)
        self.assertIn("passed result requires an independent verifier", result.stdout)
        self.assertIn("target_manifest_digest is missing or stale", result.stdout)

    def test_controlled_case_tampering_is_detected(self):
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "cases/by-skill/T065.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["cases"][0]["expected"] = "weakened"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        result = self.command("python3", str(VALIDATOR), str(suite))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("controlled file digest mismatch", result.stdout)
        self.assertIn("split catalog differs from master", result.stdout)

    def test_source_package_tampering_is_detected(self):
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "source-package/ANTI_FRAUD_POLICY.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nweakened\n", encoding="utf-8")
        result = self.command("python3", str(VALIDATOR), str(suite))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("imported source package tree digest mismatch", result.stdout)
        self.assertIn("source package digest mismatch", result.stdout)


if __name__ == "__main__":
    unittest.main()
