from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class LiveWorkbenchProductionGateTest(unittest.TestCase):
    def test_not_run_template_fails_closed(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/live_workbench/run_production_gate.py",
             "--evidence", "docs/live-workbench/production-evidence-template.json"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(1, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("BLOCKED", report["decision"])
        self.assertFalse(report["certified"])
        self.assertIn("IMPLEMENTATION_REVISION_INVALID", report["errors"])
        self.assertIn("EXACT_18_CASE_INVENTORY_REQUIRED", report["errors"])

    def test_local_validation_can_assert_the_blocked_baseline(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/live_workbench/run_production_gate.py",
             "--evidence", "docs/live-workbench/production-evidence-template.json",
             "--expect-blocked"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_executed_evidence_ready_for_external_certification(self) -> None:
        evidence_file = ROOT / "docs/live-workbench/production-evidence.json"
        data = json.loads(evidence_file.read_text(encoding="utf-8"))
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        data["implementation_revision"] = head
        evidence_file.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/live_workbench/run_production_gate.py",
             "--evidence", "docs/live-workbench/production-evidence.json"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(1, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("BLOCKED", report["decision"])
        self.assertFalse(report["certified"])
        self.assertEqual(["INDEPENDENT_SIGNED_APPROVAL_REQUIRED"], report["errors"])


if __name__ == "__main__":
    unittest.main()
