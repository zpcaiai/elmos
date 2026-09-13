"""Production self-healing: race, deadlock, fencing, async — without weakening tests."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
QA_SRC = ROOT / "engines/autonomous-qa-engine/src"
if str(QA_SRC) not in sys.path:
    sys.path.insert(0, str(QA_SRC))

from elmos_autonomous_qa.industrial.evaluate import evaluate_all_planted, heal_planted_system
from elmos_autonomous_qa.industrial.loop_guard import LoopDecision, RepairLoopGuard
from elmos_autonomous_qa.industrial.planted_systems import PLANTED, STRICT_TESTS
from elmos_autonomous_qa.industrial.test_integrity import TestIntegrityOracle
from elmos_autonomous_qa.pr_self_healing.defect_triage_rca import DefectTriageRCA
from elmos_autonomous_qa.pr_self_healing.scm_models import FailureCategory, FailureTrace, RepairStrategy


class ProductionHealingTests(unittest.TestCase):
    def test_all_planted_systems_heal_without_weakening(self) -> None:
        results = evaluate_all_planted()
        self.assertEqual(len(results), 5)
        for row in results:
            self.assertTrue(row.healed, f"{row.name} not healed: {row.details}")
            self.assertTrue(row.integrity_ok, f"{row.name} integrity: {row.details}")
            self.assertTrue(row.mutation_caught, f"{row.name} mutation not caught: {row.details}")
            self.assertTrue(row.loop_guard_ok, row.name)

    def test_race_healer_adds_lock_not_sleep(self) -> None:
        result = heal_planted_system("ledger_race.py")
        self.assertTrue(result.healed)
        healed = result.details["after"]
        self.assertEqual(healed["balance"], 1600)

    def test_integrity_rejects_skip_and_tautology(self) -> None:
        before = STRICT_TESTS["test_ledger_race.py"]
        weakened = before.replace("assert ledger_balance == expected", "assert True")
        report = TestIntegrityOracle.evaluate(before, weakened, is_test=True)
        self.assertFalse(report.ok)
        self.assertTrue(any("tautolog" in item or "forbidden" in item for item in report.violations))

    def test_loop_guard_aborts_oscillation(self) -> None:
        guard = RepairLoopGuard(max_cycles=3)
        self.assertEqual(guard.begin_cycle("race"), LoopDecision.CONTINUE)
        self.assertEqual(guard.record_patch("aaa"), LoopDecision.CONTINUE)
        self.assertEqual(guard.record_patch("aaa"), LoopDecision.OSCILLATION_ABORT)

    def test_loop_guard_aborts_after_ceiling(self) -> None:
        guard = RepairLoopGuard(max_cycles=2)
        self.assertEqual(guard.record_patch("a"), LoopDecision.CONTINUE)
        self.assertEqual(guard.record_patch("b"), LoopDecision.CONTINUE)
        self.assertEqual(guard.begin_cycle("race"), LoopDecision.MAX_CYCLES_ABORT)

    def test_triage_routes_production_defects(self) -> None:
        cases = (
            ("lost update in shared state", FailureCategory.RACE_CONDITION),
            ("DeadlockDetectedError circular wait", FailureCategory.DEADLOCK),
            ("stale fencing token rejected", FailureCategory.DISTRIBUTED_LOCK_FAILURE),
            ("database deadlock detected", FailureCategory.DATABASE_DEADLOCK),
            ("asyncio timing producer has not published", FailureCategory.ASYNC_TIMING),
        )
        for message, expected in cases:
            trace = FailureTrace(
                test_id="t",
                test_file="src/ledger.py",
                test_function="test_x",
                failure_category=FailureCategory.RUNTIME_EXCEPTION,
                exception_class="RuntimeError",
                error_message=message,
                stack_trace=("src/ledger.py:10 in deposit",),
            )
            classified = DefectTriageRCA.triage_failure(trace)
            self.assertEqual(classified.category, expected, message)
            self.assertEqual(classified.recommended_strategy, RepairStrategy.SAFE_CODE_FIX)

    def test_planted_sources_are_real_python(self) -> None:
        for name, source in PLANTED.items():
            compile(source, name, "exec")


if __name__ == "__main__":
    unittest.main()
