from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "test-suite"
SUITE = ROOT / "test-suites" / "batch66-80-slightly-strict"
sys.path.insert(0, str(SCRIPTS))

from validate_batch66_80_slightly_strict import validate_suite  # noqa: E402


class Batch66To80SupplementalTest(unittest.TestCase):
    def copy_suite(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        target = Path(temporary.name) / SUITE.name
        shutil.copytree(SUITE, target)
        return temporary, target

    def first_result(self, suite: Path) -> Path:
        return sorted((suite / "results").glob("*.json"))[0]

    def test_pristine_suite_is_structurally_valid(self) -> None:
        errors, metrics = validate_suite(SUITE)
        self.assertEqual([], errors)
        self.assertEqual(15, metrics["batches"])
        self.assertEqual(35, metrics["test_skills"])
        self.assertEqual(195, metrics["source_skills"])
        self.assertEqual(450, metrics["cases"])
        self.assertEqual(390, metrics["source_specific_cases"])
        self.assertEqual(60, metrics["cross_cutting_cases"])
        self.assertEqual(450, metrics["coverage_edges"])
        self.assertEqual(450, metrics["results"])
        self.assertEqual(103, metrics["zero_tolerance_cases"])
        self.assertEqual({"P0": 312, "P1": 120, "P2": 18}, metrics["priority_counts"])
        self.assertEqual({"not-run": 450}, metrics["status_counts"])

    def test_gate_fails_closed_while_all_cases_are_not_run(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "run_batch66_80_slightly_strict_gate.py"),
                str(SUITE),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, completed.returncode, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual("NOT_RUN", report["source_gate_status"])
        self.assertEqual("BLOCKED", report["decision"])
        self.assertFalse(report["certified"])
        self.assertFalse(report["approves_production_or_provider_operation"])
        self.assertEqual(450, report["metrics"]["status_counts"]["not-run"])

    def test_missing_result_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        self.first_result(suite).unlink()
        errors, _ = validate_suite(suite)
        self.assertTrue(any("exactly and uniquely cover all 450" in error for error in errors), errors)

    def test_fabricated_pass_without_evidence_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = self.first_result(suite)
        result = json.loads(path.read_text(encoding="utf-8"))
        result.update(
            {
                "status": "passed",
                "attempts": 1,
                "source_sha256": "1" * 64,
                "environment_sha256": "2" * 64,
                "fixture_sha256": "3" * 64,
                "started_at": "2026-07-22T00:00:00+00:00",
                "finished_at": "2026-07-22T00:00:01+00:00",
            }
        )
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        errors, _ = validate_suite(suite)
        self.assertTrue(any("does not match the exact source Skill" in error for error in errors), errors)
        self.assertTrue(any("at least two immutable evidence" in error for error in errors), errors)
        self.assertTrue(any("independent-verification" in error for error in errors), errors)
        self.assertTrue(any("authorization" in error for error in errors), errors)

    def test_not_run_execution_claim_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = self.first_result(suite)
        result = json.loads(path.read_text(encoding="utf-8"))
        result["source_sha256"] = "1" * 64
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        errors, _ = validate_suite(suite)
        self.assertTrue(any("not-run cannot claim source_sha256" in error for error in errors), errors)

    def test_case_catalog_tamper_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "cases" / "catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        catalog["cases"][0]["then"] = "accept anything"
        path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
        errors, _ = validate_suite(suite)
        self.assertTrue(any("differs from canonical package: cases/catalog.json" in error for error in errors), errors)

    def test_coverage_removal_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "coverage-matrix.json"
        coverage = json.loads(path.read_text(encoding="utf-8"))
        coverage["source_skills"].pop()
        path.write_text(json.dumps(coverage, indent=2) + "\n", encoding="utf-8")
        errors, _ = validate_suite(suite)
        self.assertTrue(any("differs from canonical package: coverage-matrix.json" in error for error in errors), errors)
        self.assertTrue(any("contiguous PG223-PG417" in error for error in errors), errors)

    def test_result_filename_identity_tamper_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = self.first_result(suite)
        result = json.loads(path.read_text(encoding="utf-8"))
        result["case_id"] = "forged-case"
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        errors, _ = validate_suite(suite)
        self.assertTrue(any("filename/catalog case" in error for error in errors), errors)

    def test_unknown_result_file_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        shutil.copy2(self.first_result(suite), suite / "results" / "forged-extra.json")
        errors, _ = validate_suite(suite)
        self.assertTrue(any("exactly and uniquely cover all 450" in error for error in errors), errors)

    def test_zero_tolerance_waiver_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        catalog = json.loads((suite / "cases" / "catalog.json").read_text(encoding="utf-8"))
        case = next(item for item in catalog["cases"] if item["zero_tolerance"])
        path = suite / "results" / f"{case['case_id']}.json"
        result = json.loads(path.read_text(encoding="utf-8"))
        result["status"] = "waived"
        result["waiver_id"] = "W-forged"
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        errors, _ = validate_suite(suite)
        self.assertTrue(any("zero-tolerance cases cannot be waived" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
