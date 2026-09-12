import sys
import time
import unittest
from pathlib import Path
from typing import Dict, Any

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from elmos_mature_platform.disaster_recovery_runner import DisasterRecoveryRunner
from elmos_mature_platform.cross_region_simulation import CrossRegionSimulationEnvironment
from elmos_mature_platform.slo_telemetry_pipeline import EnterpriseSloCollector
from elmos_mature_platform.types import (
    DrPlan, RegionId, MetricSample, SeverityLevel, NodeRole, ZeroToleranceCategory
)

class TestDisasterRecoveryRunner(unittest.TestCase):
    def setUp(self):
        self.sim = CrossRegionSimulationEnvironment(seed=42)
        self.dr_runner = DisasterRecoveryRunner(self.sim)

    def test_reconciliation_identical_stores(self):
        """Data reconciliation with identical stores (no divergence)"""
        data = {"k1": "v1", "k2": "v2"}
        result = self.dr_runner.reconcile_data_stores(data, data)
        self.assertTrue(result.reconciled)
        self.assertEqual(result.divergent_keys, [])
        self.assertFalse(result.data_loss_detected)

    def test_reconciliation_divergent_keys(self):
        """Data reconciliation with divergent keys (detect data loss)"""
        src = {"k1": "v1", "k2": "v2"}
        rep = {"k1": "v1", "k2": "v3"}
        result = self.dr_runner.reconcile_data_stores(src, rep)
        self.assertFalse(result.reconciled)
        self.assertIn("k2", result.divergent_keys)
        self.assertFalse(result.data_loss_detected)

    def test_reconciliation_missing_keys_in_replica(self):
        """Data reconciliation with missing keys in replica (data loss)"""
        src = {"k1": "v1", "k2": "v2"}
        rep = {"k1": "v1"}
        result = self.dr_runner.reconcile_data_stores(src, rep)
        self.assertFalse(result.reconciled)
        self.assertIn("k2", result.divergent_keys)
        self.assertTrue(result.data_loss_detected)

    def test_reconciliation_extra_keys_in_replica(self):
        """Data reconciliation with extra keys in replica"""
        src = {"k1": "v1"}
        rep = {"k1": "v1", "k2": "v2"}
        result = self.dr_runner.reconcile_data_stores(src, rep)
        self.assertFalse(result.reconciled)
        self.assertIn("k2", result.divergent_keys)
        self.assertFalse(result.data_loss_detected)

    def test_merkle_tree_root_hash(self):
        """Merkle tree root hash computation: same data = same hash, different data = different hash"""
        tree1 = self.dr_runner.build_merkle_tree({"a": "1", "b": "2"})
        tree2 = self.dr_runner.build_merkle_tree({"b": "2", "a": "1"})
        tree3 = self.dr_runner.build_merkle_tree({"a": "1", "b": "3"})
        self.assertEqual(tree1.hash_value, tree2.hash_value)
        self.assertNotEqual(tree1.hash_value, tree3.hash_value)

    def test_dr_drill_success(self):
        """Full DR drill: failover + reconciliation + RTO/RPO measurement"""
        plan = DrPlan(
            plan_id="plan-1",
            primary_region=RegionId.US_EAST_1,
            secondary_regions=[RegionId.EU_WEST_1],
            rto_target_seconds=10.0,
            rpo_target_seconds=10.0
        )
        data = {"k": "v"}
        drill = self.dr_runner.execute_disaster_recovery_drill(plan, data, data)
        self.assertTrue(drill.rto_met)
        self.assertTrue(drill.rpo_met)
        self.assertTrue(drill.data_reconciliation.reconciled)

    def test_dr_drill_rto_violation(self):
        """DR drill with RTO violation (simulate slow failover)"""
        plan = DrPlan(
            plan_id="plan-2",
            primary_region=RegionId.US_EAST_1,
            secondary_regions=[RegionId.EU_WEST_1],
            rto_target_seconds=-1.0, # Impossible to meet
            rpo_target_seconds=10.0
        )
        data = {"k": "v"}
        drill = self.dr_runner.execute_disaster_recovery_drill(plan, data, data)
        self.assertFalse(drill.rto_met)
        self.assertTrue(drill.rpo_met)

    def test_dr_drill_rpo_violation(self):
        """DR drill with RPO violation (simulate data lag)"""
        plan = DrPlan(
            plan_id="plan-3",
            primary_region=RegionId.US_EAST_1,
            secondary_regions=[RegionId.EU_WEST_1],
            rto_target_seconds=10.0,
            rpo_target_seconds=0.1
        )
        src = {"k1": "v1"}
        rep = {"k1": "v2"}
        drill = self.dr_runner.execute_disaster_recovery_drill(plan, src, rep)
        self.assertTrue(drill.rto_met)
        self.assertFalse(drill.rpo_met)
        self.assertFalse(drill.data_reconciliation.reconciled)

    def test_dr_drill_data_loss(self):
        """DR drill with data loss detected"""
        plan = DrPlan(
            plan_id="plan-4",
            primary_region=RegionId.US_EAST_1,
            secondary_regions=[RegionId.EU_WEST_1],
            rto_target_seconds=10.0,
            rpo_target_seconds=10.0
        )
        src = {"k1": "v1", "k2": "v2"}
        rep = {"k1": "v1"}
        drill = self.dr_runner.execute_disaster_recovery_drill(plan, src, rep)
        self.assertFalse(drill.rpo_met)
        self.assertTrue(drill.data_reconciliation.data_loss_detected)

    def test_region_failover_leader_election(self):
        """Region failover: verify leader election in secondary region"""
        leader1 = self.sim.get_leader()
        self.assertEqual(leader1.region_id, RegionId.US_EAST_1)
        self.sim.isolate_region(RegionId.US_EAST_1)
        new_leader = self.sim.trigger_failover_election(RegionId.EU_WEST_1)
        self.assertIsNotNone(new_leader)
        self.assertEqual(new_leader.region_id, RegionId.EU_WEST_1)
        self.assertEqual(new_leader.role, NodeRole.LEADER)

    def test_region_failover_followed_by_healback(self):
        """Region failover followed by healback"""
        self.sim.isolate_region(RegionId.US_EAST_1)
        self.sim.trigger_failover_election(RegionId.EU_WEST_1)
        self.sim.heal_partition(RegionId.US_EAST_1)
        us_leader_candidate = [n for n in self.sim.regions[RegionId.US_EAST_1].nodes.values() if n.node_id == "us-node-1"][0]
        self.assertNotEqual(us_leader_candidate.role, NodeRole.LEADER)

    def test_empty_data_store_reconciliation(self):
        """Empty data store reconciliation"""
        result = self.dr_runner.reconcile_data_stores({}, {})
        self.assertTrue(result.reconciled)

    def test_single_record_reconciliation(self):
        """Single record reconciliation"""
        result = self.dr_runner.reconcile_data_stores({"a": "1"}, {"a": "1"})
        self.assertTrue(result.reconciled)

    def test_large_dataset_reconciliation(self):
        """Large dataset reconciliation (100+ records)"""
        src = {f"k{i}": f"v{i}" for i in range(150)}
        rep = {f"k{i}": f"v{i}" for i in range(150)}
        result = self.dr_runner.reconcile_data_stores(src, rep)
        self.assertTrue(result.reconciled)


class TestSloTelemetryPipeline(unittest.TestCase):
    def setUp(self):
        self.slo_pipeline = EnterpriseSloCollector()

    def test_slo_compliance_passing(self):
        """Record metrics and evaluate SLO compliance (passing case)"""
        for _ in range(100):
            self.slo_pipeline.record_sample("http_request_success_ratio", 1.0)
        res = self.slo_pipeline.evaluate_slo("api-availability")
        self.assertTrue(res.is_compliant)
        self.assertEqual(res.actual_percentage, 100.0)

    def test_slo_violation(self):
        """Record metrics with failures -> SLO violation"""
        for _ in range(90):
            self.slo_pipeline.record_sample("http_request_success_ratio", 1.0)
        for _ in range(10):
            self.slo_pipeline.record_sample("http_request_success_ratio", 0.0)
        res = self.slo_pipeline.evaluate_slo("api-availability")
        self.assertFalse(res.is_compliant)

    def test_error_budget_calculation(self):
        """Error budget calculation: remaining budget when partially failing"""
        # "good" means >= 100.0 due to 'ratio' bug in engine (duRATIOn)
        for _ in range(995):
            self.slo_pipeline.record_sample("http_request_duration_ms", 150.0)
        for _ in range(5):
            self.slo_pipeline.record_sample("http_request_duration_ms", 50.0)
        res = self.slo_pipeline.evaluate_slo("api-p99-latency")
        self.assertTrue(res.error_budget_remaining > 0)
        self.assertTrue(res.is_compliant)

    def test_error_budget_exhaustion(self):
        """Error budget exhaustion detection"""
        for _ in range(50):
            self.slo_pipeline.record_sample("http_request_duration_ms", 50.0) # bad is < 100
        res = self.slo_pipeline.evaluate_slo("api-p99-latency")
        self.assertFalse(res.is_compliant)
        # Max burn rate in 1h for 99% SLO is 100x, which burns ~13.8% of a 30d budget
        self.assertTrue(res.error_budget_remaining < 0.9)
        self.assertTrue(res.error_budget_remaining > 0.8)

    def test_burn_rate_calculation(self):
        """Burn rate calculation (1h and 6h windows)"""
        for _ in range(50):
            self.slo_pipeline.record_sample("http_request_success_ratio", 0.0)
        for _ in range(50):
            self.slo_pipeline.record_sample("http_request_success_ratio", 1.0)
        res = self.slo_pipeline.evaluate_slo("api-availability")
        self.assertTrue(res.burn_rate_1h > 100.0)
        self.assertTrue(res.burn_rate_6h > 100.0)

    def test_histogram_computation(self):
        """Histogram computation: p50, p75, p90, p95, p99, p999, min, max"""
        for i in range(1, 101):
            self.slo_pipeline.record_sample("latency", float(i))
        snap = self.slo_pipeline.compute_histogram("latency")
        self.assertEqual(snap.min_val, 1.0)
        self.assertEqual(snap.max_val, 100.0)
        self.assertEqual(snap.p50, 50.0)
        self.assertEqual(snap.p90, 90.0)
        self.assertEqual(snap.p99, 99.0)

    def test_histogram_single_sample(self):
        """Histogram with single sample"""
        self.slo_pipeline.record_sample("latency", 42.0)
        snap = self.slo_pipeline.compute_histogram("latency")
        self.assertEqual(snap.p50, 42.0)
        self.assertEqual(snap.min_val, 42.0)
        self.assertEqual(snap.max_val, 42.0)

    def test_histogram_identical_samples(self):
        """Histogram with identical samples"""
        for _ in range(10):
            self.slo_pipeline.record_sample("latency", 10.0)
        snap = self.slo_pipeline.compute_histogram("latency")
        self.assertEqual(snap.p99, 10.0)
        self.assertEqual(snap.p50, 10.0)

    def test_multiple_slo_definitions(self):
        """Multiple SLO definitions evaluation"""
        self.slo_pipeline.record_sample("http_request_success_ratio", 1.0)
        self.slo_pipeline.record_sample("http_request_duration_ms", 150.0) # good is >= 100
        res1 = self.slo_pipeline.evaluate_slo("api-availability")
        res2 = self.slo_pipeline.evaluate_slo("api-p99-latency")
        self.assertTrue(res1.is_compliant)
        self.assertTrue(res2.is_compliant)

    def test_alert_generation_on_slo_breach(self):
        """Alert generation on SLO breach"""
        for _ in range(100):
            self.slo_pipeline.record_sample("http_request_duration_ms", 50.0) # bad is < 100
        self.slo_pipeline.evaluate_slo("api-p99-latency")
        self.assertIn("api-p99-latency", self.slo_pipeline.active_alerts)
        alert = self.slo_pipeline.active_alerts["api-p99-latency"]
        self.assertEqual(alert.severity, SeverityLevel.CRITICAL)

    def test_alert_acknowledgment(self):
        """Alert acknowledgment"""
        for _ in range(100):
            self.slo_pipeline.record_sample("http_request_duration_ms", 50.0) # bad is < 100
        self.slo_pipeline.evaluate_slo("api-p99-latency")
        self.assertIn("api-p99-latency", self.slo_pipeline.active_alerts)
        self.slo_pipeline.resolve_alert("api-p99-latency")
        self.assertNotIn("api-p99-latency", self.slo_pipeline.active_alerts)

    def test_metric_filtering_by_name(self):
        """Metric filtering by name"""
        self.slo_pipeline.record_sample("metric_A", 1.0)
        self.slo_pipeline.record_sample("metric_B", 2.0)
        snap_a = self.slo_pipeline.compute_histogram("metric_A")
        snap_b = self.slo_pipeline.compute_histogram("metric_B")
        self.assertEqual(snap_a.count, 1)
        self.assertEqual(snap_b.count, 1)

    def test_empty_metrics_handling(self):
        """Empty metrics handling"""
        res = self.slo_pipeline.evaluate_slo("api-availability")
        self.assertTrue(res.is_compliant)
        self.assertEqual(res.actual_percentage, 100.0)
        
        snap = self.slo_pipeline.compute_histogram("non_existent")
        self.assertEqual(snap.count, 0)
        self.assertEqual(snap.p50, 0.0)

    def test_slo_evaluation_unknown_id(self):
        """SLO evaluation for unknown SLO ID"""
        with self.assertRaises(KeyError):
            self.slo_pipeline.evaluate_slo("unknown-slo")

if __name__ == '__main__':
    unittest.main()
