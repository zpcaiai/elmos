from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts/test-suite"
SUITE = ROOT / "test-suites/batch81-95-language-packs-slightly-strict"
SOURCE = ROOT / "elmos-batch81-95-slightly-strict-test-skills"
sys.path.insert(0, str(SCRIPTS))

from validate_batch81_95_language_packs import validate_suite  # noqa: E402


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class Batch81To95LanguagePackTest(unittest.TestCase):
    def copy_suite(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        target = Path(temporary.name) / SUITE.name
        shutil.copytree(SUITE, target)
        return temporary, target

    def refresh_control(self, suite: Path, relative: str) -> None:
        path = suite / "control-manifest.json"
        controls = json.loads(path.read_text(encoding="utf-8"))
        controls["controlled_files"][relative] = digest(suite / relative)
        write_json(path, controls)

    def run_gate(self, suite: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "run_batch81_95_language_pack_gate.py"),
                str(suite),
                "--source",
                str(SOURCE),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_pristine_suite_is_structurally_valid(self) -> None:
        errors, metrics = validate_suite(SUITE, SOURCE)
        self.assertEqual([], errors)
        self.assertEqual(
            {
                "batches": 15,
                "test_skills": 40,
                "source_skills": 180,
                "cases": 640,
                "direct_edges": 180,
                "total_edges": 47700,
                "results": 640,
                "critical_cases": 170,
                "high_cases": 400,
                "medium_cases": 70,
            },
            metrics,
        )

    def test_gate_fails_closed_while_all_cases_are_not_run(self) -> None:
        completed = self.run_gate(SUITE)
        self.assertEqual(2, completed.returncode, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual("NOT_RUN", report["source_status"])
        self.assertEqual("BLOCKED", report["decision"])
        self.assertFalse(report["certified"])
        self.assertFalse(report["approves_vendor_or_physical_operation"])
        self.assertFalse(report["updates_batch1_37_certification"])
        self.assertEqual(640, report["metrics"]["status_counts"]["NOT_RUN"])

    def test_missing_result_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "results/catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        catalog["results"].pop()
        write_json(path, catalog)
        errors, _ = validate_suite(suite, SOURCE)
        self.assertTrue(any("exactly 640 results" in error for error in errors), errors)

    def test_reordered_result_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "results/catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        catalog["results"][0], catalog["results"][1] = (
            catalog["results"][1],
            catalog["results"][0],
        )
        write_json(path, catalog)
        errors, _ = validate_suite(suite, SOURCE)
        self.assertTrue(any("ordered case catalog" in error for error in errors), errors)

    def test_fabricated_native_pass_without_evidence_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "results/catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        catalog["results"][0]["status"] = "PASSED"
        catalog["results"][0]["reason"] = "claimed native pass"
        write_json(path, catalog)
        errors, _ = validate_suite(suite, SOURCE)
        self.assertTrue(
            any("PASSED requires real or approved-equivalent" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("PASSED requires immutable raw evidence" in error for error in errors),
            errors,
        )

    def test_self_verification_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "results/catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        result = catalog["results"][0]
        result["status"] = "PASSED"
        result["executor"] = {"id": "same-agent"}
        result["verifier"] = {"id": "same-agent", "independent": True}
        write_json(path, catalog)
        errors, _ = validate_suite(suite, SOURCE)
        self.assertTrue(
            any("executor and verifier must be different" in error for error in errors), errors
        )

    def test_not_run_execution_claim_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "results/catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        catalog["results"][0]["artifact_digest"] = "sha256:" + "1" * 64
        write_json(path, catalog)
        errors, _ = validate_suite(suite, SOURCE)
        self.assertTrue(
            any("NOT_RUN result cannot contain execution claims" in error for error in errors),
            errors,
        )

    def test_package_local_namespace_cannot_be_relabelled(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "suite.json"
        descriptor = json.loads(path.read_text(encoding="utf-8"))
        descriptor["source_namespace"] = "global-project-synthesis"
        write_json(path, descriptor)
        self.refresh_control(suite, "suite.json")
        errors, _ = validate_suite(suite, SOURCE)
        self.assertTrue(any("source_namespace" in error for error in errors), errors)

    def test_case_source_id_relabel_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "cases/catalog.json"
        cases = json.loads(path.read_text(encoding="utf-8"))
        cases[0]["target_skills"] = ["PG001"]
        write_json(path, cases)
        self.refresh_control(suite, "cases/catalog.json")
        errors, _ = validate_suite(suite, SOURCE)
        self.assertTrue(any("immutable 640-case source catalog" in error for error in errors), errors)

    def test_coverage_removal_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "coverage-matrix.json"
        coverage = json.loads(path.read_text(encoding="utf-8"))
        coverage["rows"].pop()
        write_json(path, coverage)
        self.refresh_control(suite, "coverage-matrix.json")
        errors, _ = validate_suite(suite, SOURCE)
        self.assertTrue(any("exactly 180 ordered" in error for error in errors), errors)
        self.assertTrue(any("180 direct" in error for error in errors), errors)

    def test_install_manifest_result_binding_tamper_is_rejected(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "results/catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        catalog["results"][0]["language_install_manifest_digest"] = "sha256:" + "0" * 64
        write_json(path, catalog)
        errors, _ = validate_suite(suite, SOURCE)
        self.assertTrue(
            any("language_install_manifest_digest" in error for error in errors), errors
        )

    def test_zero_tolerance_finding_blocks_the_gate(self) -> None:
        temporary, suite = self.copy_suite()
        self.addCleanup(temporary.cleanup)
        path = suite / "results/catalog.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        result = catalog["results"][0]
        result["status"] = "FAILED"
        result["reason"] = "security boundary failed"
        result["findings"] = ["cross-project or cross-tenant leak"]
        write_json(path, catalog)
        completed = self.run_gate(suite)
        self.assertEqual(2, completed.returncode, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(1, report["metrics"]["zero_tolerance_findings"])
        self.assertTrue(
            any("zero-tolerance findings" in blocker for blocker in report["blockers"])
        )


if __name__ == "__main__":
    unittest.main()
