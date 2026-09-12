import unittest
from datetime import datetime, timezone
import uuid

from elmos_mature_platform.types import (
    FinalGateMaturityDimension as MaturityDimension,
    DimensionVerdict,
    FinalGateDimensionAssessment as DimensionAssessment,
    FinalGateDecision
)
from elmos_mature_platform.mature_product_final_gate_engine import MatureProductFinalGateEngine

class TestMatureProductFinalGateEngine(unittest.TestCase):
    def setUp(self):
        self.engine = MatureProductFinalGateEngine()

    def test_create_gate_success(self):
        gate = FinalGateDecision(gate_id="g1", product_name="Elmos", version="v1.0")
        gate_id = self.engine.create_gate(gate)
        self.assertEqual(gate_id, "g1")
        self.assertEqual(self.engine._gates["g1"].product_name, "Elmos")

    def test_create_gate_auto_id(self):
        gate = FinalGateDecision(gate_id="", product_name="Elmos", version="v1.0")
        gate_id = self.engine.create_gate(gate)
        self.assertTrue(len(gate_id) > 0)
        self.assertIn(gate_id, self.engine._gates)

    def test_set_mandatory_dimensions(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.set_mandatory_dimensions("g1", [MaturityDimension.SECURITY, MaturityDimension.FUNCTIONAL])
        gate = self.engine._gates["g1"]
        self.assertIn(MaturityDimension.SECURITY.value, gate.mandatory_dimensions)
        self.assertIn(MaturityDimension.FUNCTIONAL.value, gate.mandatory_dimensions)

    def test_set_mandatory_dimensions_invalid_gate(self):
        with self.assertRaises(ValueError):
            self.engine.set_mandatory_dimensions("non_existent", [MaturityDimension.SECURITY])

    def test_submit_assessment(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        assessment = DimensionAssessment(dimension=MaturityDimension.SECURITY, verdict=DimensionVerdict.PASS, score=95.0)
        self.engine.submit_assessment("g1", assessment)
        self.assertIn(MaturityDimension.SECURITY.value, self.engine._gates["g1"].assessments)
        self.assertEqual(self.engine._gates["g1"].assessments[MaturityDimension.SECURITY.value].score, 95.0)

    def test_submit_assessment_invalid_gate(self):
        with self.assertRaises(ValueError):
            assessment = DimensionAssessment(dimension=MaturityDimension.SECURITY)
            self.engine.submit_assessment("non_existent", assessment)

    def test_evaluate_gate_all_pass(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.set_mandatory_dimensions("g1", [MaturityDimension.SECURITY])
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, verdict=DimensionVerdict.PASS))
        gate = self.engine.evaluate_gate("g1")
        self.assertEqual(gate.overall_verdict, DimensionVerdict.PASS)

    def test_evaluate_gate_missing_mandatory(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.set_mandatory_dimensions("g1", [MaturityDimension.SECURITY, MaturityDimension.FUNCTIONAL])
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, verdict=DimensionVerdict.PASS))
        gate = self.engine.evaluate_gate("g1")
        self.assertEqual(gate.overall_verdict, DimensionVerdict.FAIL)

    def test_evaluate_gate_mandatory_fail(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.set_mandatory_dimensions("g1", [MaturityDimension.SECURITY])
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, verdict=DimensionVerdict.FAIL))
        gate = self.engine.evaluate_gate("g1")
        self.assertEqual(gate.overall_verdict, DimensionVerdict.FAIL)

    def test_evaluate_gate_mandatory_conditional(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.set_mandatory_dimensions("g1", [MaturityDimension.SECURITY, MaturityDimension.FUNCTIONAL])
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, verdict=DimensionVerdict.PASS))
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.FUNCTIONAL, verdict=DimensionVerdict.CONDITIONAL_PASS))
        gate = self.engine.evaluate_gate("g1")
        self.assertEqual(gate.overall_verdict, DimensionVerdict.CONDITIONAL_PASS)

    def test_evaluate_gate_invalid_gate(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate_gate("non_existent")

    def test_authorize_release_pass(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.set_mandatory_dimensions("g1", [MaturityDimension.SECURITY])
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, verdict=DimensionVerdict.PASS))
        self.engine.evaluate_gate("g1")
        gate = self.engine.authorize_release("g1", "alice")
        self.assertTrue(gate.release_authorized)
        self.assertEqual(gate.decision_maker, "alice")
        self.assertTrue(bool(gate.decision_made_at))

    def test_authorize_release_conditional(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.set_mandatory_dimensions("g1", [MaturityDimension.SECURITY])
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, verdict=DimensionVerdict.CONDITIONAL_PASS))
        self.engine.evaluate_gate("g1")
        gate = self.engine.authorize_release("g1", "bob")
        self.assertTrue(gate.release_authorized)

    def test_authorize_release_fail(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.set_mandatory_dimensions("g1", [MaturityDimension.SECURITY])
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, verdict=DimensionVerdict.FAIL))
        self.engine.evaluate_gate("g1")
        with self.assertRaises(ValueError):
            self.engine.authorize_release("g1", "charlie")

    def test_authorize_release_invalid_gate(self):
        with self.assertRaises(ValueError):
            self.engine.authorize_release("non_existent", "alice")

    def test_get_blocking_dimensions(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.set_mandatory_dimensions("g1", [MaturityDimension.SECURITY, MaturityDimension.PERFORMANCE])
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, verdict=DimensionVerdict.FAIL))
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.PERFORMANCE, verdict=DimensionVerdict.PASS))
        blockers = self.engine.get_blocking_dimensions("g1")
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0].dimension, MaturityDimension.SECURITY)

    def test_get_blocking_dimensions_none(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.set_mandatory_dimensions("g1", [MaturityDimension.SECURITY])
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, verdict=DimensionVerdict.PASS))
        blockers = self.engine.get_blocking_dimensions("g1")
        self.assertEqual(len(blockers), 0)

    def test_get_blocking_dimensions_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_blocking_dimensions("non_existent")

    def test_get_conditions(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, conditions=["Must rotate keys"]))
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.PERFORMANCE, conditions=["Must improve p99 latency"]))
        conditions = self.engine.get_conditions("g1")
        self.assertEqual(len(conditions), 2)
        self.assertIn("Must rotate keys", conditions)

    def test_get_conditions_empty(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, conditions=[]))
        conditions = self.engine.get_conditions("g1")
        self.assertEqual(len(conditions), 0)

    def test_get_conditions_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_conditions("non_existent")

    def test_get_readiness_score(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, score=90.0))
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.PERFORMANCE, score=80.0))
        score = self.engine.get_readiness_score("g1")
        self.assertEqual(score, 85.0)

    def test_get_readiness_score_empty(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        score = self.engine.get_readiness_score("g1")
        self.assertEqual(score, 0.0)

    def test_get_readiness_score_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_readiness_score("non_existent")

    def test_compare_gates(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.create_gate(FinalGateDecision(gate_id="g2", product_name="p", version="v2"))
        
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, score=80.0))
        self.engine.submit_assessment("g2", DimensionAssessment(dimension=MaturityDimension.SECURITY, score=90.0))
        
        comp = self.engine.compare_gates("g1", "g2")
        self.assertIn(MaturityDimension.SECURITY.value, comp)
        self.assertEqual(comp[MaturityDimension.SECURITY.value]["diff"], 10.0)

    def test_compare_gates_missing_dim(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.create_gate(FinalGateDecision(gate_id="g2", product_name="p", version="v2"))
        
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, score=80.0))
        self.engine.submit_assessment("g2", DimensionAssessment(dimension=MaturityDimension.PERFORMANCE, score=90.0))
        
        comp = self.engine.compare_gates("g1", "g2")
        self.assertEqual(comp[MaturityDimension.SECURITY.value]["diff"], -80.0)
        self.assertEqual(comp[MaturityDimension.PERFORMANCE.value]["diff"], 90.0)

    def test_compare_gates_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.compare_gates("g1", "non_existent")

    def test_get_gate_report(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.set_mandatory_dimensions("g1", [MaturityDimension.SECURITY])
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, verdict=DimensionVerdict.PASS, score=95.0))
        self.engine.evaluate_gate("g1")
        report = self.engine.get_gate_report("g1")
        self.assertEqual(report["gate_id"], "g1")
        self.assertEqual(report["overall_verdict"], DimensionVerdict.PASS.value)
        self.assertEqual(report["readiness_score"], 95.0)

    def test_get_gate_report_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_gate_report("non_existent")

    def test_evaluate_gate_not_evaluated(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.set_mandatory_dimensions("g1", [MaturityDimension.SECURITY])
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, verdict=DimensionVerdict.NOT_EVALUATED))
        gate = self.engine.evaluate_gate("g1")
        self.assertEqual(gate.overall_verdict, DimensionVerdict.FAIL)
        
    def test_authorize_release_not_evaluated(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        with self.assertRaises(ValueError):
            self.engine.authorize_release("g1", "alice")

    def test_submit_assessment_replaces_old(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, score=80.0))
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.SECURITY, score=95.0))
        self.assertEqual(self.engine._gates["g1"].assessments[MaturityDimension.SECURITY.value].score, 95.0)
        
    def test_get_blocking_dimensions_non_mandatory_fail(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        self.engine.set_mandatory_dimensions("g1", [MaturityDimension.SECURITY])
        self.engine.submit_assessment("g1", DimensionAssessment(dimension=MaturityDimension.PERFORMANCE, verdict=DimensionVerdict.FAIL))
        blockers = self.engine.get_blocking_dimensions("g1")
        self.assertEqual(len(blockers), 0)

    def test_evaluate_gate_no_mandatory_dimensions(self):
        self.engine.create_gate(FinalGateDecision(gate_id="g1", product_name="p", version="v1"))
        gate = self.engine.evaluate_gate("g1")
        # According to logic, all mandatory (none) evaluated, no fail, no cond = PASS
        self.assertEqual(gate.overall_verdict, DimensionVerdict.PASS)

if __name__ == '__main__':
    unittest.main()
