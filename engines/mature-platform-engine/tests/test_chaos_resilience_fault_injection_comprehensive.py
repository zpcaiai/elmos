import unittest
from datetime import datetime
from elmos_mature_platform.chaos_resilience_fault_injection_engine import ChaosResilienceFaultInjectionEngine
from elmos_mature_platform.types import FaultInjectionRule, ChaosExperiment, ExperimentStatus, ChaosFaultType as FaultType

class TestChaosResilienceFaultInjectionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ChaosResilienceFaultInjectionEngine()
        
    def test_create_rule_valid(self):
        rule = FaultInjectionRule("r1", FaultType.LATENCY, "service-a", probability=0.5)
        r_id = self.engine.create_rule(rule)
        self.assertEqual(r_id, "r1")
        self.assertEqual(self.engine._rules["r1"].probability, 0.5)

    def test_create_rule_invalid_probability(self):
        rule = FaultInjectionRule("r2", FaultType.ERROR, "service-b", probability=1.5)
        with self.assertRaises(ValueError):
            self.engine.create_rule(rule)
            
    def test_create_rule_negative_probability(self):
        rule = FaultInjectionRule("r3", FaultType.ERROR, "service-b", probability=-0.1)
        with self.assertRaises(ValueError):
            self.engine.create_rule(rule)
            
    def test_create_experiment(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        e_id = self.engine.create_experiment(exp)
        self.assertEqual(e_id, "e1")
        self.assertEqual(self.engine._experiments["e1"].status, ExperimentStatus.DRAFT)
        
    def test_add_rule_to_experiment(self):
        rule = FaultInjectionRule("r1", FaultType.LATENCY, "service-a")
        self.engine.create_rule(rule)
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        self.engine.add_rule_to_experiment("e1", "r1")
        self.assertIn("r1", self.engine._experiments["e1"].rules)

    def test_add_rule_to_missing_experiment(self):
        rule = FaultInjectionRule("r1", FaultType.LATENCY, "service-a")
        self.engine.create_rule(rule)
        with self.assertRaises(KeyError):
            self.engine.add_rule_to_experiment("e_missing", "r1")

    def test_add_missing_rule_to_experiment(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        with self.assertRaises(KeyError):
            self.engine.add_rule_to_experiment("e1", "r_missing")

    def test_add_rule_to_non_draft_experiment(self):
        rule = FaultInjectionRule("r1", FaultType.LATENCY, "service-a")
        self.engine.create_rule(rule)
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        self.engine.approve_experiment("e1", "admin")
        with self.assertRaises(ValueError):
            self.engine.add_rule_to_experiment("e1", "r1")

    def test_approve_experiment(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        result = self.engine.approve_experiment("e1", "admin")
        self.assertEqual(result.status, ExperimentStatus.APPROVED)
        self.assertEqual(result.approved_by, "admin")

    def test_approve_missing_experiment(self):
        with self.assertRaises(KeyError):
            self.engine.approve_experiment("e_missing", "admin")

    def test_approve_non_draft_experiment(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        self.engine.approve_experiment("e1", "admin")
        with self.assertRaises(ValueError):
            self.engine.approve_experiment("e1", "admin2")

    def test_approve_experiment_empty_approver(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        with self.assertRaises(ValueError):
            self.engine.approve_experiment("e1", "")

    def test_approve_experiment_region_blast_radius(self):
        exp = ChaosExperiment("e1", "test", "hypothesis", blast_radius="region")
        self.engine.create_experiment(exp)
        with self.assertRaises(PermissionError):
            self.engine.approve_experiment("e1", "")

    def test_start_experiment(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        self.engine.approve_experiment("e1", "admin")
        result = self.engine.start_experiment("e1")
        self.assertEqual(result.status, ExperimentStatus.RUNNING)
        self.assertTrue(bool(result.started_at))

    def test_start_missing_experiment(self):
        with self.assertRaises(KeyError):
            self.engine.start_experiment("e_missing")

    def test_start_unapproved_experiment(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        with self.assertRaises(ValueError):
            self.engine.start_experiment("e1")

    def test_complete_experiment(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        self.engine.approve_experiment("e1", "admin")
        self.engine.start_experiment("e1")
        result = self.engine.complete_experiment("e1", "All good", True)
        self.assertEqual(result.status, ExperimentStatus.COMPLETED)
        self.assertTrue(bool(result.completed_at))
        self.assertEqual(result.result_summary, "All good")
        self.assertTrue(result.hypothesis_confirmed)

    def test_complete_missing_experiment(self):
        with self.assertRaises(KeyError):
            self.engine.complete_experiment("e_missing", "summary", True)

    def test_complete_non_running_experiment(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        with self.assertRaises(ValueError):
            self.engine.complete_experiment("e1", "summary", True)

    def test_abort_experiment(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        self.engine.approve_experiment("e1", "admin")
        self.engine.start_experiment("e1")
        result = self.engine.abort_experiment("e1", "Things broke")
        self.assertEqual(result.status, ExperimentStatus.ABORTED)
        self.assertEqual(result.result_summary, "ABORTED: Things broke")

    def test_abort_missing_experiment(self):
        with self.assertRaises(KeyError):
            self.engine.abort_experiment("e_missing", "reason")

    def test_abort_non_running_experiment(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        with self.assertRaises(ValueError):
            self.engine.abort_experiment("e1", "reason")

    def test_rollback_experiment_running(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        self.engine.approve_experiment("e1", "admin")
        self.engine.start_experiment("e1")
        result = self.engine.rollback_experiment("e1")
        self.assertEqual(result.status, ExperimentStatus.ROLLED_BACK)

    def test_rollback_experiment_completed(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        self.engine.approve_experiment("e1", "admin")
        self.engine.start_experiment("e1")
        self.engine.complete_experiment("e1", "sum", True)
        result = self.engine.rollback_experiment("e1")
        self.assertEqual(result.status, ExperimentStatus.ROLLED_BACK)

    def test_rollback_experiment_aborted(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        self.engine.approve_experiment("e1", "admin")
        self.engine.start_experiment("e1")
        self.engine.abort_experiment("e1", "bad")
        result = self.engine.rollback_experiment("e1")
        self.assertEqual(result.status, ExperimentStatus.ROLLED_BACK)

    def test_rollback_missing_experiment(self):
        with self.assertRaises(KeyError):
            self.engine.rollback_experiment("e_missing")

    def test_rollback_invalid_status_experiment(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        with self.assertRaises(ValueError):
            self.engine.rollback_experiment("e1")

    def test_get_active_experiments(self):
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        self.engine.approve_experiment("e1", "admin")
        self.engine.start_experiment("e1")
        
        exp2 = ChaosExperiment("e2", "test2", "hypothesis2")
        self.engine.create_experiment(exp2)
        self.engine.approve_experiment("e2", "admin")
        
        active = self.engine.get_active_experiments()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].experiment_id, "e1")

    def test_get_blast_radius_assessment(self):
        rule1 = FaultInjectionRule("r1", FaultType.LATENCY, "service-a", duration_seconds=100)
        rule2 = FaultInjectionRule("r2", FaultType.ERROR, "service-b", duration_seconds=50)
        self.engine.create_rule(rule1)
        self.engine.create_rule(rule2)
        
        exp = ChaosExperiment("e1", "test", "hypothesis", blast_radius="zone")
        self.engine.create_experiment(exp)
        self.engine.add_rule_to_experiment("e1", "r1")
        self.engine.add_rule_to_experiment("e1", "r2")
        
        assessment = self.engine.get_blast_radius_assessment("e1")
        self.assertEqual(assessment["blast_radius"], "zone")
        self.assertCountEqual(assessment["services_affected"], ["service-a", "service-b"])
        self.assertEqual(assessment["total_duration_seconds"], 100)
        self.assertEqual(len(assessment["rules"]), 2)

    def test_get_blast_radius_missing_experiment(self):
        with self.assertRaises(KeyError):
            self.engine.get_blast_radius_assessment("e_missing")

    def test_get_experiment_history(self):
        rule = FaultInjectionRule("r1", FaultType.LATENCY, "service-a")
        self.engine.create_rule(rule)
        exp = ChaosExperiment("e1", "test", "hypothesis")
        self.engine.create_experiment(exp)
        self.engine.add_rule_to_experiment("e1", "r1")
        
        history = self.engine.get_experiment_history("service-a")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].experiment_id, "e1")
        
        history_b = self.engine.get_experiment_history("service-b")
        self.assertEqual(len(history_b), 0)

    def test_get_chaos_report(self):
        rule = FaultInjectionRule("r1", FaultType.LATENCY, "service-a")
        self.engine.create_rule(rule)
        
        exp1 = ChaosExperiment("e1", "t1", "h1")
        self.engine.create_experiment(exp1)
        self.engine.add_rule_to_experiment("e1", "r1")
        self.engine.approve_experiment("e1", "admin")
        self.engine.start_experiment("e1")
        self.engine.complete_experiment("e1", "s1", True)
        
        exp2 = ChaosExperiment("e2", "t2", "h2")
        self.engine.create_experiment(exp2)
        self.engine.add_rule_to_experiment("e2", "r1")
        self.engine.approve_experiment("e2", "admin")
        self.engine.start_experiment("e2")
        self.engine.complete_experiment("e2", "s2", False)
        
        exp3 = ChaosExperiment("e3", "t3", "h3")
        self.engine.create_experiment(exp3)
        
        report = self.engine.get_chaos_report()
        self.assertEqual(report["total_experiments"], 3)
        self.assertEqual(report["by_status"][ExperimentStatus.COMPLETED.value], 2)
        self.assertEqual(report["by_status"][ExperimentStatus.DRAFT.value], 1)
        self.assertEqual(report["hypothesis_confirmation_rate"], 0.5)
        self.assertEqual(report["common_faults"]["latency"], 2)

if __name__ == "__main__":
    unittest.main()
