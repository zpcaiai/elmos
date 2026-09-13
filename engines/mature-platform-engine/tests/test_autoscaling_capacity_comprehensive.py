import unittest
import time
from typing import Dict
from elmos_mature_platform.types import (
    ScalingDirection, ScalingTrigger, ScalingPolicy, ScalingDecision,
    AutoscalingCapacityPlan, FairSchedulingQuota
)
from elmos_mature_platform.autoscaling_capacity_engine import AutoscalingCapacityEngine

class TestAutoscalingCapacityEngine(unittest.TestCase):
    def setUp(self):
        self.engine = AutoscalingCapacityEngine()

    def test_register_policy(self):
        policy = ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0)
        self.engine.register_policy(policy)
        self.assertIn("web", self.engine.policies)

    def test_evaluate_scaling_up(self):
        policy = ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0)
        self.engine.register_policy(policy)
        decision = self.engine.evaluate_scaling("web", 5, {"cpu_threshold": 90.0})
        self.assertEqual(decision.direction, ScalingDirection.SCALE_UP)
        self.assertEqual(decision.target_instances, 6)

    def test_evaluate_scaling_down(self):
        policy = ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0, min_instances=2)
        self.engine.register_policy(policy)
        decision = self.engine.evaluate_scaling("web", 5, {"cpu_threshold": 20.0})
        self.assertEqual(decision.direction, ScalingDirection.SCALE_DOWN)
        self.assertEqual(decision.target_instances, 4)

    def test_evaluate_scaling_no_change(self):
        policy = ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0)
        self.engine.register_policy(policy)
        decision = self.engine.evaluate_scaling("web", 5, {"cpu_threshold": 60.0})
        self.assertEqual(decision.direction, ScalingDirection.NO_CHANGE)
        self.assertEqual(decision.target_instances, 5)

    def test_evaluate_scaling_missing_policy(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate_scaling("web", 5, {"cpu_threshold": 60.0})

    def test_evaluate_scaling_missing_metric(self):
        policy = ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0)
        self.engine.register_policy(policy)
        with self.assertRaises(ValueError):
            self.engine.evaluate_scaling("web", 5, {"memory_threshold": 60.0})

    def test_apply_scaling_decision_no_change(self):
        policy = ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0)
        self.engine.register_policy(policy)
        decision = self.engine.evaluate_scaling("web", 5, {"cpu_threshold": 60.0})
        result = self.engine.apply_scaling_decision(decision)
        self.assertEqual(result["status"], "no_change")

    def test_apply_scaling_decision_cooldown(self):
        policy = ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0, cooldown_seconds=10)
        self.engine.register_policy(policy)
        decision1 = self.engine.evaluate_scaling("web", 5, {"cpu_threshold": 90.0})
        self.engine.apply_scaling_decision(decision1)
        
        decision2 = self.engine.evaluate_scaling("web", 6, {"cpu_threshold": 90.0})
        result = self.engine.apply_scaling_decision(decision2)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["decision"].blocked)

    def test_apply_scaling_decision_bounds_max(self):
        policy = ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0, max_instances=5)
        self.engine.register_policy(policy)
        decision = ScalingDecision("d1", "web", ScalingDirection.SCALE_UP, 5, 6, ScalingTrigger.CPU_THRESHOLD, 90.0, "p1")
        result = self.engine.apply_scaling_decision(decision)
        self.assertEqual(result["status"], "blocked")

    def test_apply_scaling_decision_bounds_min(self):
        policy = ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0, min_instances=2)
        self.engine.register_policy(policy)
        decision = ScalingDecision("d1", "web", ScalingDirection.SCALE_DOWN, 2, 1, ScalingTrigger.CPU_THRESHOLD, 20.0, "p1")
        result = self.engine.apply_scaling_decision(decision)
        self.assertEqual(result["status"], "blocked")

    def test_check_cooldown_false(self):
        self.assertFalse(self.engine.check_cooldown("web"))

    def test_check_cooldown_true(self):
        policy = ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0, cooldown_seconds=10)
        self.engine.register_policy(policy)
        self.engine.last_scaling_time["web"] = time.time()
        self.assertTrue(self.engine.check_cooldown("web"))

    def test_create_capacity_plan(self):
        plan = self.engine.create_capacity_plan("web", 10, 100.0, 5.0)
        self.assertEqual(plan.recommended_capacity, 120)
        self.assertEqual(plan.estimated_monthly_cost, 600.0)

    def test_create_capacity_plan_with_policy(self):
        policy = ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0, max_instances=50)
        self.engine.register_policy(policy)
        plan = self.engine.create_capacity_plan("web", 10, 100.0, 5.0)
        self.assertEqual(plan.recommended_capacity, 50)

    def test_set_fair_quota(self):
        quota = FairSchedulingQuota("t1", "web", 10, 20)
        self.engine.set_fair_quota(quota)
        self.assertIn("t1", self.engine.quotas)

    def test_check_fair_scheduling_guaranteed(self):
        quota = FairSchedulingQuota("t1", "web", 10, 20)
        self.engine.set_fair_quota(quota)
        result = self.engine.check_fair_scheduling("t1", "web", 5)
        self.assertEqual(result["status"], "allowed")
        self.assertEqual(result["granted"], 5)

    def test_check_fair_scheduling_burst(self):
        quota = FairSchedulingQuota("t1", "web", 10, 20, current_usage=8)
        self.engine.set_fair_quota(quota)
        result = self.engine.check_fair_scheduling("t1", "web", 5)
        self.assertEqual(result["status"], "allowed")
        self.assertEqual(result["granted"], 5)

    def test_check_fair_scheduling_blocked(self):
        quota = FairSchedulingQuota("t1", "web", 10, 20, current_usage=18)
        self.engine.set_fair_quota(quota)
        result = self.engine.check_fair_scheduling("t1", "web", 5)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["granted"], 2)

    def test_check_fair_scheduling_missing_tenant(self):
        with self.assertRaises(PermissionError):
            self.engine.check_fair_scheduling("t1", "web", 5)

    def test_protect_downstream_saturation_scale_down(self):
        decision = self.engine.protect_downstream_saturation("web", 5, 10)
        self.assertEqual(decision.direction, ScalingDirection.SCALE_DOWN)
        self.assertEqual(decision.target_instances, 5)

    def test_protect_downstream_saturation_no_change(self):
        decision = self.engine.protect_downstream_saturation("web", 10, 5)
        self.assertEqual(decision.direction, ScalingDirection.NO_CHANGE)

    def test_get_scaling_history(self):
        policy = ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0)
        self.engine.register_policy(policy)
        decision = self.engine.evaluate_scaling("web", 5, {"cpu_threshold": 90.0})
        self.engine.apply_scaling_decision(decision)
        history = self.engine.get_scaling_history("web")
        self.assertEqual(len(history), 1)

    def test_get_capacity_report(self):
        policy = ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0)
        self.engine.register_policy(policy)
        decision = self.engine.evaluate_scaling("web", 5, {"cpu_threshold": 90.0})
        self.engine.apply_scaling_decision(decision)
        report = self.engine.get_capacity_report()
        self.assertEqual(report["policies_count"], 1)
        self.assertEqual(report["total_scaling_events"], 1)

    def test_evaluate_scaling_memory(self):
        policy = ScalingPolicy("p2", "api", ScalingTrigger.MEMORY_THRESHOLD, 75.0)
        self.engine.register_policy(policy)
        decision = self.engine.evaluate_scaling("api", 10, {"memory_threshold": 80.0})
        self.assertEqual(decision.direction, ScalingDirection.SCALE_UP)

    def test_evaluate_scaling_queue(self):
        policy = ScalingPolicy("p3", "worker", ScalingTrigger.QUEUE_DEPTH, 100.0, scale_up_increment=5)
        self.engine.register_policy(policy)
        decision = self.engine.evaluate_scaling("worker", 2, {"queue_depth": 150.0})
        self.assertEqual(decision.target_instances, 7)

    def test_cooldown_expiration(self):
        policy = ScalingPolicy("p1", "web", ScalingTrigger.CPU_THRESHOLD, 80.0, cooldown_seconds=0.1)
        self.engine.register_policy(policy)
        decision1 = self.engine.evaluate_scaling("web", 5, {"cpu_threshold": 90.0})
        self.engine.apply_scaling_decision(decision1)
        time.sleep(0.15)
        decision2 = self.engine.evaluate_scaling("web", 6, {"cpu_threshold": 90.0})
        result = self.engine.apply_scaling_decision(decision2)
        self.assertEqual(result["status"], "applied")

    def test_fair_scheduling_exact_burst(self):
        quota = FairSchedulingQuota("t1", "web", 10, 20, current_usage=15)
        self.engine.set_fair_quota(quota)
        result = self.engine.check_fair_scheduling("t1", "web", 5)
        self.assertEqual(result["status"], "allowed")

    def test_fair_scheduling_multi_tenant(self):
        self.engine.set_fair_quota(FairSchedulingQuota("t1", "web", 10, 20))
        self.engine.set_fair_quota(FairSchedulingQuota("t2", "web", 5, 10))
        res1 = self.engine.check_fair_scheduling("t1", "web", 15)
        res2 = self.engine.check_fair_scheduling("t2", "web", 15)
        self.assertEqual(res1["status"], "allowed")
        self.assertEqual(res2["status"], "blocked")
        self.assertEqual(res2["granted"], 10)

if __name__ == "__main__":
    unittest.main()
