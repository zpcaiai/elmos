import unittest
import uuid
from typing import List

from elmos_mature_platform.types import (
    AgentDeployment,
    AgentDeploymentMode,
    ShadowComparison,
    AgentComparisonVerdict,
    CanaryMetrics,
    CanaryPromotionDecision
)
from elmos_mature_platform.agent_shadow_canary_engine import AgentShadowCanaryEngine


class TestAgentShadowCanaryEngine(unittest.TestCase):
    def setUp(self):
        self.engine = AgentShadowCanaryEngine()
        self.prod_dep = AgentDeployment(
            deployment_id="prod-1",
            agent_id="agent-1",
            agent_version="v1.0",
            mode=AgentDeploymentMode.PRODUCTION,
            traffic_pct=100.0,
            is_active=True
        )
        self.engine.create_deployment(self.prod_dep)

    def _create_shadow(self, dep_id="shadow-1"):
        shadow_dep = AgentDeployment(
            deployment_id=dep_id,
            agent_id="agent-1",
            agent_version="v1.1",
            mode=AgentDeploymentMode.SHADOW,
            traffic_pct=0.0,
            is_active=True
        )
        return self.engine.create_deployment(shadow_dep)
        
    def _create_canary(self, dep_id="canary-1"):
        canary_dep = AgentDeployment(
            deployment_id=dep_id,
            agent_id="agent-1",
            agent_version="v1.2",
            mode=AgentDeploymentMode.CANARY,
            traffic_pct=0.0,
            is_active=True
        )
        return self.engine.create_deployment(canary_dep)

    def test_create_deployment_success(self):
        dep = AgentDeployment(
            deployment_id="dep-2",
            agent_id="agent-2",
            agent_version="v2.0",
            mode=AgentDeploymentMode.PRODUCTION,
            traffic_pct=0.0
        )
        created = self.engine.create_deployment(dep)
        self.assertEqual(created.deployment_id, "dep-2")
        self.assertEqual(len(self.engine.get_deployment_history()), 2)

    def test_create_deployment_duplicate_fails(self):
        with self.assertRaises(ValueError):
            self.engine.create_deployment(self.prod_dep)

    def test_start_shadow_success(self):
        self._create_shadow()
        comp = self.engine.start_shadow("prod-1", "shadow-1")
        self.assertEqual(comp.production_deployment_id, "prod-1")
        self.assertEqual(comp.shadow_deployment_id, "shadow-1")

    def test_start_shadow_invalid_prod(self):
        self._create_shadow()
        with self.assertRaises(ValueError):
            self.engine.start_shadow("non-existent", "shadow-1")

    def test_start_shadow_invalid_shadow(self):
        with self.assertRaises(ValueError):
            self.engine.start_shadow("prod-1", "non-existent")

    def test_start_shadow_prod_not_production_mode(self):
        shadow1 = self._create_shadow("shadow-1")
        shadow2 = self._create_shadow("shadow-2")
        with self.assertRaises(ValueError):
            self.engine.start_shadow("shadow-1", "shadow-2")

    def test_start_shadow_shadow_not_shadow_mode(self):
        canary = self._create_canary()
        with self.assertRaises(ValueError):
            self.engine.start_shadow("prod-1", "canary-1")

    def test_start_shadow_with_traffic_fails(self):
        shadow = self._create_shadow()
        shadow.traffic_pct = 10.0
        with self.assertRaises(ValueError):
            self.engine.start_shadow("prod-1", "shadow-1")

    def test_record_shadow_result_match(self):
        self._create_shadow()
        comp = self.engine.start_shadow("prod-1", "shadow-1")
        self.engine.record_shadow_result(comp.comparison_id, "output", "output", 100, 105)
        
        updated = self.engine.get_shadow_comparison(comp.comparison_id)
        self.assertEqual(updated.request_count, 1)
        self.assertEqual(updated.match_count, 1)
        self.assertEqual(updated.divergence_count, 0)

    def test_record_shadow_result_divergence(self):
        self._create_shadow()
        comp = self.engine.start_shadow("prod-1", "shadow-1")
        self.engine.record_shadow_result(comp.comparison_id, "output1", "output2", 100, 105)
        
        updated = self.engine.get_shadow_comparison(comp.comparison_id)
        self.assertEqual(updated.request_count, 1)
        self.assertEqual(updated.match_count, 0)
        self.assertEqual(updated.divergence_count, 1)
        self.assertEqual(len(updated.divergence_examples), 1)

    def test_record_shadow_result_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.record_shadow_result("non-existent", "o1", "o2", 10, 10)

    def test_get_shadow_comparison_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.get_shadow_comparison("invalid")

    def test_evaluate_shadow_verdict_unknown(self):
        self._create_shadow()
        comp = self.engine.start_shadow("prod-1", "shadow-1")
        verdict = self.engine.evaluate_shadow_verdict(comp.comparison_id)
        self.assertEqual(verdict, AgentComparisonVerdict.UNKNOWN)

    def test_evaluate_shadow_verdict_equivalent(self):
        self._create_shadow()
        comp = self.engine.start_shadow("prod-1", "shadow-1")
        for _ in range(100):
            self.engine.record_shadow_result(comp.comparison_id, "out", "out", 10, 10)
        
        verdict = self.engine.evaluate_shadow_verdict(comp.comparison_id)
        self.assertEqual(verdict, AgentComparisonVerdict.EQUIVALENT)

    def test_evaluate_shadow_verdict_degraded(self):
        self._create_shadow()
        comp = self.engine.start_shadow("prod-1", "shadow-1")
        for _ in range(100):
            self.engine.record_shadow_result(comp.comparison_id, "out", "bad", 10, 10)
            
        verdict = self.engine.evaluate_shadow_verdict(comp.comparison_id)
        self.assertEqual(verdict, AgentComparisonVerdict.DEGRADED)

    def test_evaluate_shadow_verdict_divergent(self):
        self._create_shadow()
        comp = self.engine.start_shadow("prod-1", "shadow-1")
        # 90 matches, 10 diverges -> 90%
        for _ in range(90):
            self.engine.record_shadow_result(comp.comparison_id, "out", "out", 10, 10)
        for _ in range(10):
            self.engine.record_shadow_result(comp.comparison_id, "out", "diff", 10, 10)
            
        verdict = self.engine.evaluate_shadow_verdict(comp.comparison_id)
        self.assertEqual(verdict, AgentComparisonVerdict.DIVERGENT)

    def test_start_canary_success(self):
        self._create_canary()
        self.engine.start_canary("canary-1", 10.0)
        
        self.assertEqual(self.engine.deployments["prod-1"].traffic_pct, 90.0)
        self.assertEqual(self.engine.deployments["canary-1"].traffic_pct, 10.0)

    def test_start_canary_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.start_canary("invalid", 10.0)

    def test_start_canary_not_canary_mode(self):
        with self.assertRaises(ValueError):
            self.engine.start_canary("prod-1", 10.0)

    def test_start_canary_invalid_traffic(self):
        self._create_canary()
        with self.assertRaises(ValueError):
            self.engine.start_canary("canary-1", 60.0)
            
        with self.assertRaises(ValueError):
            self.engine.start_canary("canary-1", 0.0)

    def test_start_canary_no_active_prod(self):
        self._create_canary()
        self.engine.deployments["prod-1"].is_active = False
        with self.assertRaises(ValueError):
            self.engine.start_canary("canary-1", 10.0)

    def test_start_canary_insufficient_prod_traffic(self):
        self._create_canary()
        self.engine.deployments["prod-1"].traffic_pct = 5.0
        with self.assertRaises(ValueError):
            self.engine.start_canary("canary-1", 10.0)

    def test_record_canary_request_success(self):
        self._create_canary()
        self.engine.start_canary("canary-1", 10.0)
        self.engine.record_canary_request("canary-1", True, 50.0, 0.01)
        
        metrics = self.engine.get_canary_metrics("canary-1")
        self.assertEqual(metrics.total_requests, 1)
        self.assertEqual(metrics.success_rate, 1.0)
        self.assertEqual(metrics.error_count, 0)
        self.assertEqual(metrics.p50_latency_ms, 50.0)
        self.assertEqual(metrics.p99_latency_ms, 50.0)
        self.assertEqual(metrics.cost_per_request, 0.01)

    def test_record_canary_request_failure(self):
        self._create_canary()
        self.engine.start_canary("canary-1", 10.0)
        self.engine.record_canary_request("canary-1", False, 100.0, 0.01)
        
        metrics = self.engine.get_canary_metrics("canary-1")
        self.assertEqual(metrics.total_requests, 1)
        self.assertEqual(metrics.success_rate, 0.0)
        self.assertEqual(metrics.error_count, 1)

    def test_record_canary_request_unstarted(self):
        self._create_canary()
        with self.assertRaises(ValueError):
            self.engine.record_canary_request("canary-1", True, 50.0, 0.01)

    def test_get_canary_metrics_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_canary_metrics("invalid")

    def test_evaluate_canary_promotion_insufficient_requests(self):
        self._create_canary()
        self.engine.start_canary("canary-1", 10.0)
        self.engine.record_canary_request("canary-1", True, 50.0, 0.01)
        
        decision = self.engine.evaluate_canary_promotion("canary-1", min_requests=10, min_success_rate=0.99)
        self.assertFalse(decision.promote)
        self.assertFalse(decision.rollback_recommended)
        self.assertEqual(decision.reason, "Insufficient requests for evaluation")

    def test_evaluate_canary_promotion_low_success(self):
        self._create_canary()
        self.engine.start_canary("canary-1", 10.0)
        for _ in range(10):
            self.engine.record_canary_request("canary-1", False, 50.0, 0.01)
            
        decision = self.engine.evaluate_canary_promotion("canary-1", min_requests=10, min_success_rate=0.99)
        self.assertFalse(decision.promote)
        self.assertTrue(decision.rollback_recommended)
        self.assertEqual(decision.reason, "Success rate below minimum threshold")

    def test_evaluate_canary_promotion_success(self):
        self._create_canary()
        self.engine.start_canary("canary-1", 10.0)
        for _ in range(10):
            self.engine.record_canary_request("canary-1", True, 50.0, 0.01)
            
        decision = self.engine.evaluate_canary_promotion("canary-1", min_requests=10, min_success_rate=0.99)
        self.assertTrue(decision.promote)
        self.assertFalse(decision.rollback_recommended)

    def test_evaluate_canary_promotion_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate_canary_promotion("invalid", 10, 0.9)

    def test_promote_canary_success(self):
        self._create_canary()
        self.engine.start_canary("canary-1", 10.0)
        self.engine.promote_canary("canary-1")
        
        self.assertEqual(self.engine.deployments["canary-1"].mode, AgentDeploymentMode.PRODUCTION)
        self.assertEqual(self.engine.deployments["canary-1"].traffic_pct, 100.0)
        
        self.assertEqual(self.engine.deployments["prod-1"].traffic_pct, 0.0)
        self.assertFalse(self.engine.deployments["prod-1"].is_active)

    def test_promote_canary_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.promote_canary("invalid")

    def test_promote_canary_not_canary(self):
        with self.assertRaises(ValueError):
            self.engine.promote_canary("prod-1")

    def test_promote_canary_unmapped(self):
        self._create_canary()
        with self.assertRaises(ValueError):
            self.engine.promote_canary("canary-1")

    def test_rollback_canary_success(self):
        self._create_canary()
        self.engine.start_canary("canary-1", 20.0)
        self.engine.rollback_canary("canary-1")
        
        self.assertEqual(self.engine.deployments["canary-1"].traffic_pct, 0.0)
        self.assertFalse(self.engine.deployments["canary-1"].is_active)
        self.assertEqual(self.engine.deployments["prod-1"].traffic_pct, 100.0)

    def test_rollback_canary_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.rollback_canary("invalid")

    def test_rollback_canary_not_canary(self):
        with self.assertRaises(ValueError):
            self.engine.rollback_canary("prod-1")

    def test_rollback_canary_unmapped(self):
        self._create_canary()
        with self.assertRaises(ValueError):
            self.engine.rollback_canary("canary-1")

    def test_kill_switch_canary(self):
        self._create_canary()
        self.engine.start_canary("canary-1", 15.0)
        self.engine.kill_switch("canary-1")
        
        self.assertEqual(self.engine.deployments["canary-1"].traffic_pct, 0.0)
        self.assertFalse(self.engine.deployments["canary-1"].is_active)
        self.assertEqual(self.engine.deployments["prod-1"].traffic_pct, 100.0)

    def test_kill_switch_production(self):
        self.engine.kill_switch("prod-1")
        self.assertEqual(self.engine.deployments["prod-1"].traffic_pct, 0.0)
        self.assertFalse(self.engine.deployments["prod-1"].is_active)

    def test_kill_switch_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.kill_switch("invalid")

    def test_get_deployment_history(self):
        self._create_canary()
        self._create_shadow()
        history = self.engine.get_deployment_history()
        self.assertEqual(len(history), 3)

    def test_get_active_deployments(self):
        self._create_canary()
        self._create_shadow()
        
        self.engine.kill_switch("shadow-1")
        active = self.engine.get_active_deployments()
        self.assertEqual(len(active), 2)
        active_ids = {d.deployment_id for d in active}
        self.assertIn("prod-1", active_ids)
        self.assertIn("canary-1", active_ids)

if __name__ == "__main__":
    unittest.main()
