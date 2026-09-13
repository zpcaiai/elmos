"""Comprehensive test suite for PlatformCostAnomalyMonitoringEngine (B39 - Skill 1362)."""

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.platform_cost_anomaly_monitoring_engine import (
    PlatformCostAnomalyMonitoringEngine,
)
from elmos_mature_platform.types import (
    CostAnomalyAlert,
    CostAnomalySeverity,
    CostDataPoint,
    CostMetricType,
    CostMitigationAction,
    CostThrottlePolicy,
)


class TestPlatformCostAnomalyMonitoringComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = PlatformCostAnomalyMonitoringEngine(
            baseline_min_samples=5,
            default_z_threshold=3.0,
        )

    def test_initialization(self):
        self.assertEqual(self.engine.baseline_min_samples, 5)
        self.assertEqual(self.engine.default_z_threshold, 3.0)
        self.assertEqual(len(self.engine.list_alerts()), 0)
        self.assertEqual(len(self.engine.get_audit_log()), 0)

    def test_set_and_get_throttle_policy(self):
        policy = CostThrottlePolicy(
            policy_id="pol-001",
            tenant_id="tenant-alpha",
            metric_type=CostMetricType.LLM_TOKENS,
            hourly_spend_cap_usd=100.0,
            daily_spend_cap_usd=1000.0,
        )
        self.engine.set_throttle_policy(policy)
        retrieved = self.engine.get_throttle_policy("tenant-alpha", CostMetricType.LLM_TOKENS)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.hourly_spend_cap_usd, 100.0)
        self.assertEqual(retrieved.daily_spend_cap_usd, 1000.0)
        self.assertFalse(retrieved.circuit_breaker_tripped)

    def test_get_nonexistent_policy(self):
        policy = self.engine.get_throttle_policy("nonexistent", CostMetricType.LLM_TOKENS)
        self.assertIsNone(policy)

    def test_policy_overwrite(self):
        p1 = CostThrottlePolicy("p1", "t1", CostMetricType.COMPUTE_CPU_HOURS, 50.0, 500.0)
        p2 = CostThrottlePolicy("p2", "t1", CostMetricType.COMPUTE_CPU_HOURS, 75.0, 750.0)
        self.engine.set_throttle_policy(p1)
        self.engine.set_throttle_policy(p2)
        retrieved = self.engine.get_throttle_policy("t1", CostMetricType.COMPUTE_CPU_HOURS)
        self.assertEqual(retrieved.hourly_spend_cap_usd, 75.0)

    def test_record_cost_data_point_insufficient_samples(self):
        # Samples < 5 -> no alert produced
        for i in range(4):
            pt = CostDataPoint(
                point_id=f"pt-{i}",
                tenant_id="tenant-1",
                metric_type=CostMetricType.STORAGE_GB_MONTHS,
                timestamp="2026-09-11T00:00:00Z",
                amount_usd=10.0,
                quantity=100.0,
                unit="GB-month",
            )
            alert = self.engine.record_cost_data_point(pt)
            self.assertIsNone(alert)

    def test_circuit_breaker_tripping_on_hourly_cap(self):
        policy = CostThrottlePolicy(
            policy_id="pol-cb",
            tenant_id="tenant-cb",
            metric_type=CostMetricType.NETWORK_EGRESS_GB,
            hourly_spend_cap_usd=50.0,
            daily_spend_cap_usd=500.0,
        )
        self.engine.set_throttle_policy(policy)

        # Spend 30
        pt1 = CostDataPoint(
            point_id="pt1",
            tenant_id="tenant-cb",
            metric_type=CostMetricType.NETWORK_EGRESS_GB,
            timestamp="2026-09-11T00:00:00Z",
            amount_usd=30.0,
            quantity=300.0,
            unit="GB",
        )
        self.engine.record_cost_data_point(pt1)
        self.assertFalse(policy.circuit_breaker_tripped)

        # Spend 25 -> total 55 > 50 -> tripped
        pt2 = CostDataPoint(
            point_id="pt2",
            tenant_id="tenant-cb",
            metric_type=CostMetricType.NETWORK_EGRESS_GB,
            timestamp="2026-09-11T00:01:00Z",
            amount_usd=25.0,
            quantity=250.0,
            unit="GB",
        )
        self.engine.record_cost_data_point(pt2)
        self.assertTrue(policy.circuit_breaker_tripped)

    def test_circuit_breaker_tripping_on_daily_cap(self):
        policy = CostThrottlePolicy(
            policy_id="pol-daily",
            tenant_id="tenant-daily",
            metric_type=CostMetricType.COMPUTE_CPU_HOURS,
            hourly_spend_cap_usd=200.0,
            daily_spend_cap_usd=150.0,
        )
        self.engine.set_throttle_policy(policy)
        pt = CostDataPoint(
            point_id="pt-d",
            tenant_id="tenant-daily",
            metric_type=CostMetricType.COMPUTE_CPU_HOURS,
            timestamp="2026-09-11T00:00:00Z",
            amount_usd=160.0,
            quantity=80.0,
            unit="vCPU-hours",
        )
        self.engine.record_cost_data_point(pt)
        self.assertTrue(policy.circuit_breaker_tripped)

    def test_reset_circuit_breaker_success(self):
        policy = CostThrottlePolicy(
            policy_id="pol-reset",
            tenant_id="tenant-rst",
            metric_type=CostMetricType.CACHE_OPERATIONS,
            hourly_spend_cap_usd=10.0,
            daily_spend_cap_usd=100.0,
            circuit_breaker_tripped=True,
            current_hourly_spend_usd=25.0,
        )
        self.engine.set_throttle_policy(policy)
        res = self.engine.reset_circuit_breaker("tenant-rst", CostMetricType.CACHE_OPERATIONS)
        self.assertTrue(res)
        self.assertFalse(policy.circuit_breaker_tripped)
        self.assertEqual(policy.current_hourly_spend_usd, 0.0)

    def test_reset_circuit_breaker_missing_policy(self):
        res = self.engine.reset_circuit_breaker("unknown-tenant", CostMetricType.CACHE_OPERATIONS)
        self.assertFalse(res)

    def test_statistical_anomaly_detection_critical(self):
        # Establish baseline: 5 points of ~$10 each
        for i in range(5):
            self.engine.record_cost_data_point(
                CostDataPoint(
                    point_id=f"b-{i}",
                    tenant_id="tenant-stat",
                    metric_type=CostMetricType.LLM_TOKENS,
                    timestamp="2026-09-11T00:00:00Z",
                    amount_usd=10.0 + (i * 0.1),
                    quantity=1000.0,
                    unit="tokens",
                )
            )
        # Spike with $100 -> z-score will be very high (>= 5.0)
        spike = CostDataPoint(
            point_id="spike-1",
            tenant_id="tenant-stat",
            metric_type=CostMetricType.LLM_TOKENS,
            timestamp="2026-09-11T01:00:00Z",
            amount_usd=100.0,
            quantity=10000.0,
            unit="tokens",
        )
        alert = self.engine.record_cost_data_point(spike)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, CostAnomalySeverity.CRITICAL)
        self.assertEqual(alert.recommended_action, CostMitigationAction.TRIP_CIRCUIT_BREAKER)
        self.assertIn("runaway recursive prompt loop", alert.anomaly_reason)
        self.assertEqual(alert.current_amount_usd, 100.0)

    def test_statistical_anomaly_detection_high(self):
        # Create baseline with larger variance so we can hit 3.5 <= z < 5.0
        # amounts = [8, 9, 10, 11, 12] -> mean=10, variance=2, std=sqrt(2)=1.414
        # target z = 4.0 -> amount = 10 + 4.0 * 1.414 = 15.656
        for i, val in enumerate([8.0, 9.0, 10.0, 11.0, 12.0]):
            self.engine.record_cost_data_point(
                CostDataPoint(
                    point_id=f"b-{i}",
                    tenant_id="t-high",
                    metric_type=CostMetricType.COMPUTE_CPU_HOURS,
                    timestamp="2026-09-11T00:00:00Z",
                    amount_usd=val,
                    quantity=10.0,
                    unit="vCPU-hours",
                )
            )
        spike = CostDataPoint(
            point_id="sp-high",
            tenant_id="t-high",
            metric_type=CostMetricType.COMPUTE_CPU_HOURS,
            timestamp="2026-09-11T01:00:00Z",
            amount_usd=16.0,
            quantity=16.0,
            unit="vCPU-hours",
        )
        alert = self.engine.record_cost_data_point(spike)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, CostAnomalySeverity.HIGH)
        self.assertEqual(alert.recommended_action, CostMitigationAction.THROTTLE_RATE_LIMIT)
        self.assertIn("infinite retry or CPU spinning", alert.anomaly_reason)

    def test_statistical_anomaly_detection_medium(self):
        # baseline: [8, 9, 10, 11, 12], std ~ 1.414
        # target z ~ 2.8 -> amount = 10 + 2.8 * 1.414 = 13.96
        for i, val in enumerate([8.0, 9.0, 10.0, 11.0, 12.0]):
            self.engine.record_cost_data_point(
                CostDataPoint(
                    point_id=f"b-{i}",
                    tenant_id="t-med",
                    metric_type=CostMetricType.STORAGE_GB_MONTHS,
                    timestamp="2026-09-11T00:00:00Z",
                    amount_usd=val,
                    quantity=10.0,
                    unit="GB-month",
                )
            )
        spike = CostDataPoint(
            point_id="sp-med",
            tenant_id="t-med",
            metric_type=CostMetricType.STORAGE_GB_MONTHS,
            timestamp="2026-09-11T01:00:00Z",
            amount_usd=14.0,
            quantity=14.0,
            unit="GB-month",
        )
        alert = self.engine.record_cost_data_point(spike)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, CostAnomalySeverity.MEDIUM)
        self.assertEqual(alert.recommended_action, CostMitigationAction.ALERT_ONCALL)
        self.assertIn("checkpoint accumulation", alert.anomaly_reason)

    def test_statistical_anomaly_detection_low(self):
        # target z ~ 2.2 -> amount = 10 + 2.2 * 1.414 = 13.11
        for i, val in enumerate([8.0, 9.0, 10.0, 11.0, 12.0]):
            self.engine.record_cost_data_point(
                CostDataPoint(
                    point_id=f"b-{i}",
                    tenant_id="t-low",
                    metric_type=CostMetricType.NETWORK_EGRESS_GB,
                    timestamp="2026-09-11T00:00:00Z",
                    amount_usd=val,
                    quantity=10.0,
                    unit="GB",
                )
            )
        spike = CostDataPoint(
            point_id="sp-low",
            tenant_id="t-low",
            metric_type=CostMetricType.NETWORK_EGRESS_GB,
            timestamp="2026-09-11T01:00:00Z",
            amount_usd=13.2,
            quantity=13.2,
            unit="GB",
        )
        alert = self.engine.record_cost_data_point(spike)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, CostAnomalySeverity.LOW)
        self.assertEqual(alert.recommended_action, CostMitigationAction.NOTIFY_ONLY)
        self.assertIn("Anomalous network egress burst", alert.anomaly_reason)

    def test_anomaly_reason_other_metric(self):
        for i, val in enumerate([8.0, 9.0, 10.0, 11.0, 12.0]):
            self.engine.record_cost_data_point(
                CostDataPoint(
                    point_id=f"b-{i}",
                    tenant_id="t-other",
                    metric_type=CostMetricType.CACHE_OPERATIONS,
                    timestamp="2026-09-11T00:00:00Z",
                    amount_usd=val,
                    quantity=10.0,
                    unit="ops",
                )
            )
        spike = CostDataPoint(
            point_id="sp-other",
            tenant_id="t-other",
            metric_type=CostMetricType.CACHE_OPERATIONS,
            timestamp="2026-09-11T01:00:00Z",
            amount_usd=25.0,
            quantity=25.0,
            unit="ops",
        )
        alert = self.engine.record_cost_data_point(spike)
        self.assertIsNotNone(alert)
        self.assertIn("Unusual consumption spike in cache_operations", alert.anomaly_reason)

    def test_normal_datapoint_above_min_samples_no_alert(self):
        for i in range(5):
            self.engine.record_cost_data_point(
                CostDataPoint(
                    point_id=f"b-{i}",
                    tenant_id="t-norm",
                    metric_type=CostMetricType.LLM_TOKENS,
                    timestamp="2026-09-11T00:00:00Z",
                    amount_usd=10.0,
                    quantity=100.0,
                    unit="tokens",
                )
            )
        normal_pt = CostDataPoint(
            point_id="norm-1",
            tenant_id="t-norm",
            metric_type=CostMetricType.LLM_TOKENS,
            timestamp="2026-09-11T01:00:00Z",
            amount_usd=10.01,
            quantity=100.0,
            unit="tokens",
        )
        alert = self.engine.record_cost_data_point(normal_pt)
        self.assertIsNone(alert)

    def test_resolve_alert(self):
        for i in range(5):
            self.engine.record_cost_data_point(
                CostDataPoint(
                    point_id=f"b-{i}",
                    tenant_id="t-res",
                    metric_type=CostMetricType.LLM_TOKENS,
                    timestamp="2026-09-11T00:00:00Z",
                    amount_usd=10.0,
                    quantity=100.0,
                    unit="tokens",
                )
            )
        spike = CostDataPoint(
            point_id="sp-res",
            tenant_id="t-res",
            metric_type=CostMetricType.LLM_TOKENS,
            timestamp="2026-09-11T01:00:00Z",
            amount_usd=50.0,
            quantity=500.0,
            unit="tokens",
        )
        alert = self.engine.record_cost_data_point(spike)
        self.assertIsNotNone(alert)
        self.assertFalse(alert.is_resolved)

        res = self.engine.resolve_alert(alert.alert_id)
        self.assertTrue(res)
        self.assertTrue(alert.is_resolved)
        self.assertIsNotNone(alert.resolved_at)

        self.assertFalse(self.engine.resolve_alert("unknown-alert-id"))

    def test_list_alerts_filtering(self):
        for i in range(5):
            self.engine.record_cost_data_point(
                CostDataPoint(
                    point_id=f"b-{i}",
                    tenant_id="tenant-a",
                    metric_type=CostMetricType.LLM_TOKENS,
                    timestamp="2026-09-11T00:00:00Z",
                    amount_usd=10.0,
                    quantity=100.0,
                    unit="tokens",
                )
            )
            self.engine.record_cost_data_point(
                CostDataPoint(
                    point_id=f"b2-{i}",
                    tenant_id="tenant-b",
                    metric_type=CostMetricType.LLM_TOKENS,
                    timestamp="2026-09-11T00:00:00Z",
                    amount_usd=10.0,
                    quantity=100.0,
                    unit="tokens",
                )
            )
        al_a = self.engine.record_cost_data_point(
            CostDataPoint(
                point_id="sp-a",
                tenant_id="tenant-a",
                metric_type=CostMetricType.LLM_TOKENS,
                timestamp="2026-09-11T01:00:00Z",
                amount_usd=50.0,
                quantity=500.0,
                unit="tokens",
            )
        )
        al_b = self.engine.record_cost_data_point(
            CostDataPoint(
                point_id="sp-b",
                tenant_id="tenant-b",
                metric_type=CostMetricType.LLM_TOKENS,
                timestamp="2026-09-11T01:00:00Z",
                amount_usd=50.0,
                quantity=500.0,
                unit="tokens",
            )
        )
        self.assertEqual(len(self.engine.list_alerts()), 2)
        self.assertEqual(len(self.engine.list_alerts(tenant_id="tenant-a")), 1)

        self.engine.resolve_alert(al_a.alert_id)
        self.assertEqual(len(self.engine.list_alerts(unresolved_only=True)), 1)
        self.assertEqual(len(self.engine.list_alerts(tenant_id="tenant-a", unresolved_only=True)), 0)

    def test_tenant_cost_summary(self):
        self.engine.record_cost_data_point(
            CostDataPoint(
                point_id="p1",
                tenant_id="t-sum",
                metric_type=CostMetricType.LLM_TOKENS,
                timestamp="2026-09-11T00:00:00Z",
                amount_usd=15.5,
                quantity=100.0,
                unit="tokens",
            )
        )
        self.engine.record_cost_data_point(
            CostDataPoint(
                point_id="p2",
                tenant_id="t-sum",
                metric_type=CostMetricType.LLM_TOKENS,
                timestamp="2026-09-11T01:00:00Z",
                amount_usd=24.5,
                quantity=200.0,
                unit="tokens",
            )
        )
        self.engine.record_cost_data_point(
            CostDataPoint(
                point_id="p3",
                tenant_id="t-sum",
                metric_type=CostMetricType.STORAGE_GB_MONTHS,
                timestamp="2026-09-11T01:00:00Z",
                amount_usd=10.0,
                quantity=50.0,
                unit="GB-month",
            )
        )

        summary = self.engine.get_tenant_cost_summary("t-sum")
        self.assertEqual(summary["tenant_id"], "t-sum")
        self.assertAlmostEqual(summary["total_spend_usd"], 50.0, places=2)
        self.assertEqual(summary["metric_breakdown"]["llm_tokens"]["data_points_count"], 2)
        self.assertAlmostEqual(summary["metric_breakdown"]["llm_tokens"]["total_usd"], 40.0, places=2)
        self.assertAlmostEqual(summary["metric_breakdown"]["llm_tokens"]["mean_amount_usd"], 20.0, places=2)
        self.assertAlmostEqual(summary["metric_breakdown"]["llm_tokens"]["max_amount_usd"], 24.5, places=2)
        self.assertEqual(summary["active_anomalies_count"], 0)
        self.assertEqual(summary["highest_active_severity"], "none")

    def test_tenant_cost_summary_empty(self):
        summary = self.engine.get_tenant_cost_summary("empty-tenant")
        self.assertEqual(summary["total_spend_usd"], 0.0)
        self.assertEqual(len(summary["metric_breakdown"]), 0)
        self.assertEqual(summary["active_anomalies_count"], 0)

    def test_audit_log_records_events(self):
        policy = CostThrottlePolicy("p-aud", "t-aud", CostMetricType.LLM_TOKENS, 10.0, 50.0)
        self.engine.set_throttle_policy(policy)
        self.engine.reset_circuit_breaker("t-aud", CostMetricType.LLM_TOKENS)

        audit = self.engine.get_audit_log()
        actions = [a["action"] for a in audit]
        self.assertIn("policy_updated", actions)
        self.assertIn("circuit_breaker_reset", actions)


if __name__ == "__main__":
    unittest.main()
