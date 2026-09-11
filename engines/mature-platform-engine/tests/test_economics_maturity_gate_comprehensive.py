"""Comprehensive test suite for EconomicsMaturityGateEngine (Batch 44 - Skill 1474)."""

import unittest
from datetime import datetime, timezone

from elmos_mature_platform.economics_maturity_gate_engine import EconomicsMaturityGateEngine
from elmos_mature_platform.types import (
    EconomicsGateCheckType,
    EconomicsGateCriterion,
    EconomicsGateVerdict,
    EconomicsMaturityGateEvaluation,
)


class TestEconomicsMaturityGateComprehensive(unittest.TestCase):
    """Rigorous unit testing for EconomicsMaturityGateEngine."""

    def setUp(self) -> None:
        self.engine = EconomicsMaturityGateEngine()

    def test_create_gate_evaluation_success(self) -> None:
        eval_id = self.engine.create_gate_evaluation(
            pack_key="batch44-commercial-prod",
            scope="enterprise-migration-pipeline",
        )
        self.assertTrue(eval_id.startswith("econ-gate-"))
        evaluation = self.engine.get_gate_evaluation(eval_id)
        self.assertIsNotNone(evaluation)
        self.assertEqual(evaluation.pack_key, "batch44-commercial-prod")
        self.assertEqual(evaluation.overall_verdict, EconomicsGateVerdict.PENDING)

    def test_create_gate_evaluation_missing_fields_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.create_gate_evaluation("", "scope")
        with self.assertRaises(ValueError):
            self.engine.create_gate_evaluation("pack", "")

    def test_add_criterion_success(self) -> None:
        eval_id = self.engine.create_gate_evaluation("p1", "s1")
        crit = EconomicsGateCriterion(
            criterion_id="crit-margin",
            check_type=EconomicsGateCheckType.MINIMUM_GROSS_MARGIN,
            target_threshold=60.0,
        )
        updated = self.engine.add_criterion(eval_id, crit)
        self.assertIn("crit-margin", updated.criteria)

    def test_add_criterion_auto_generates_id(self) -> None:
        eval_id = self.engine.create_gate_evaluation("p1", "s1")
        crit = EconomicsGateCriterion(
            criterion_id="",
            check_type=EconomicsGateCheckType.UNIT_ECONOMICS_BOUND,
            target_threshold=0.05,
        )
        updated = self.engine.add_criterion(eval_id, crit)
        self.assertEqual(len(updated.criteria), 1)
        generated_id = list(updated.criteria.keys())[0]
        self.assertTrue(generated_id.startswith("crit-"))

    def test_add_criterion_missing_eval_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.add_criterion("missing-eval", EconomicsGateCriterion("c", EconomicsGateCheckType.MINIMUM_GROSS_MARGIN, 50.0))

    def test_evaluate_criterion_higher_is_better(self) -> None:
        eval_id = self.engine.create_gate_evaluation("p1", "s1")
        self.engine.add_criterion(
            eval_id,
            EconomicsGateCriterion(
                criterion_id="c-margin",
                check_type=EconomicsGateCheckType.MINIMUM_GROSS_MARGIN,
                target_threshold=65.0,
            ),
        )

        # Pass: 70.0 >= 65.0
        c1 = self.engine.evaluate_criterion(eval_id, "c-margin", 70.0, evidence_ref="ev-1")
        self.assertEqual(c1.verdict, EconomicsGateVerdict.PASS)

        # Conditional: 60.0 >= 65.0 * 0.9 (58.5) but < 65.0
        c2 = self.engine.evaluate_criterion(eval_id, "c-margin", 60.0)
        self.assertEqual(c2.verdict, EconomicsGateVerdict.CONDITIONAL)

        # Fail: 50.0 < 58.5
        c3 = self.engine.evaluate_criterion(eval_id, "c-margin", 50.0)
        self.assertEqual(c3.verdict, EconomicsGateVerdict.FAIL)

    def test_evaluate_criterion_lower_is_better(self) -> None:
        eval_id = self.engine.create_gate_evaluation("p1", "s1")
        self.engine.add_criterion(
            eval_id,
            EconomicsGateCriterion(
                criterion_id="c-tol",
                check_type=EconomicsGateCheckType.BILLING_RECONCILIATION_TOLERANCE,
                target_threshold=1.0,  # 1.0% tolerance
            ),
        )

        # Pass: 0.5 <= 1.0
        c1 = self.engine.evaluate_criterion(eval_id, "c-tol", 0.5)
        self.assertEqual(c1.verdict, EconomicsGateVerdict.PASS)

        # Conditional: 1.05 <= 1.0 * 1.1 (1.10) but > 1.0
        c2 = self.engine.evaluate_criterion(eval_id, "c-tol", 1.05)
        self.assertEqual(c2.verdict, EconomicsGateVerdict.CONDITIONAL)

        # Fail: 1.50 > 1.10
        c3 = self.engine.evaluate_criterion(eval_id, "c-tol", 1.50)
        self.assertEqual(c3.verdict, EconomicsGateVerdict.FAIL)

    def test_finalize_gate_pass(self) -> None:
        eval_id = self.engine.create_gate_evaluation("p1", "s1")
        self.engine.add_criterion(
            eval_id,
            EconomicsGateCriterion("c1", EconomicsGateCheckType.MINIMUM_GROSS_MARGIN, 60.0),
        )
        self.engine.add_criterion(
            eval_id,
            EconomicsGateCriterion("c2", EconomicsGateCheckType.BUDGET_OVERRUN_GUARDRAIL, 5.0),
        )

        self.engine.evaluate_criterion(eval_id, "c1", 65.0)
        self.engine.evaluate_criterion(eval_id, "c2", 3.0)

        finalized = self.engine.finalize_gate(eval_id, evaluated_by="Auditor Alice", sign_off_notes="All clear")
        self.assertEqual(finalized.overall_verdict, EconomicsGateVerdict.PASS)
        self.assertEqual(finalized.evaluated_by, "Auditor Alice")

    def test_finalize_gate_fail_if_any_fail(self) -> None:
        eval_id = self.engine.create_gate_evaluation("p1", "s1")
        self.engine.add_criterion(
            eval_id,
            EconomicsGateCriterion("c1", EconomicsGateCheckType.MINIMUM_GROSS_MARGIN, 60.0),
        )
        self.engine.add_criterion(
            eval_id,
            EconomicsGateCriterion("c2", EconomicsGateCheckType.BUDGET_OVERRUN_GUARDRAIL, 5.0),
        )

        self.engine.evaluate_criterion(eval_id, "c1", 65.0)  # PASS
        self.engine.evaluate_criterion(eval_id, "c2", 15.0)  # FAIL (15 > 5.5)

        finalized = self.engine.finalize_gate(eval_id)
        self.assertEqual(finalized.overall_verdict, EconomicsGateVerdict.FAIL)

    def test_finalize_gate_conditional_if_conditional_and_no_fail(self) -> None:
        eval_id = self.engine.create_gate_evaluation("p1", "s1")
        self.engine.add_criterion(
            eval_id,
            EconomicsGateCriterion("c1", EconomicsGateCheckType.MINIMUM_GROSS_MARGIN, 60.0),
        )
        self.engine.add_criterion(
            eval_id,
            EconomicsGateCriterion("c2", EconomicsGateCheckType.BUDGET_OVERRUN_GUARDRAIL, 5.0),
        )

        self.engine.evaluate_criterion(eval_id, "c1", 65.0)  # PASS
        self.engine.evaluate_criterion(eval_id, "c2", 5.2)   # CONDITIONAL (5.2 <= 5.5)

        finalized = self.engine.finalize_gate(eval_id)
        self.assertEqual(finalized.overall_verdict, EconomicsGateVerdict.CONDITIONAL)

    def test_finalize_gate_zero_criteria_raises(self) -> None:
        eval_id = self.engine.create_gate_evaluation("p1", "s1")
        with self.assertRaises(ValueError):
            self.engine.finalize_gate(eval_id)

    def test_get_economics_gate_report(self) -> None:
        rep_empty = self.engine.get_economics_gate_report()
        self.assertEqual(rep_empty["total_gate_reviews"], 0)
        self.assertEqual(rep_empty["passed_gates"], 0)

        e1 = self.engine.create_gate_evaluation("p1", "s1")
        self.engine.add_criterion(e1, EconomicsGateCriterion("c1", EconomicsGateCheckType.MINIMUM_GROSS_MARGIN, 60.0))
        self.engine.evaluate_criterion(e1, "c1", 70.0)
        self.engine.finalize_gate(e1)

        rep = self.engine.get_economics_gate_report()
        self.assertEqual(rep["total_gate_reviews"], 1)
        self.assertEqual(rep["passed_gates"], 1)
        self.assertEqual(rep["failed_gates"], 0)


if __name__ == "__main__":
    unittest.main()
