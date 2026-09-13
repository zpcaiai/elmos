"""Closed-loop Insight: Foundry kernels + QA production heals = 100% industrial."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
FOUNDRY_SRC = ROOT / "engines/knowledge-skill-model-foundry-engine/src"
QA_SRC = ROOT / "engines/autonomous-qa-engine/src"
for path in (FOUNDRY_SRC, QA_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from elmos_autonomous_qa.industrial.evaluate import evaluate_all_planted
from elmos_foundry.industrial_runtime.closed_loop import run_closed_loop


class ClosedLoopInsightTests(unittest.TestCase):
    def test_foundry_qa_insight_reaches_100_percent(self) -> None:
        qa = evaluate_all_planted()
        report = run_closed_loop(qa)
        self.assertEqual(report.foundry_executed, 1244)
        self.assertEqual(report.foundry_succeeded, 1244)
        self.assertEqual(report.local_semantic_skills, 66)
        self.assertEqual(report.atomic_executable, 1310)
        self.assertEqual(report.input_dependent_passed, report.input_dependent_checks)
        self.assertGreaterEqual(report.input_dependent_checks, 8)
        self.assertEqual(report.qa_healed, 5)
        self.assertEqual(report.qa_integrity_ok, 5)
        self.assertEqual(report.qa_mutation_caught, 5)
        self.assertEqual(report.qa_loop_guard_ok, 5)
        self.assertEqual(report.industrial_quality_percent, 100.0)
        self.assertTrue(report.ok)


if __name__ == "__main__":
    unittest.main()
