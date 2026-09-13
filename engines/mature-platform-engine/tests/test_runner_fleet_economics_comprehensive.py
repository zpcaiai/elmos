"""Comprehensive test suite for RunnerFleetEconomicsEngine (Batch 44 - Skill 1460)."""

import unittest

from elmos_mature_platform.runner_fleet_economics_engine import RunnerFleetEconomicsEngine
from elmos_mature_platform.types import (
    RunnerFleetEconomicsSummary,
    RunnerFleetNode,
    RunnerInstanceTier,
)


class TestRunnerFleetEconomicsComprehensive(unittest.TestCase):
    """Rigorous unit testing for RunnerFleetEconomicsEngine."""

    def setUp(self) -> None:
        self.engine = RunnerFleetEconomicsEngine()

    def test_register_node_success(self) -> None:
        node = RunnerFleetNode(
            node_id="node-1",
            tier=RunnerInstanceTier.ON_DEMAND,
            hourly_rate_usd=0.085,
        )
        nid = self.engine.register_node(node)
        self.assertEqual(nid, "node-1")
        retrieved = self.engine.get_node("node-1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.tier, RunnerInstanceTier.ON_DEMAND)
        self.assertTrue(retrieved.is_active)
        self.assertTrue(len(retrieved.provisioned_at) > 0)

    def test_register_node_auto_generates_id(self) -> None:
        node = RunnerFleetNode(
            node_id="",
            tier=RunnerInstanceTier.SPOT_PREEMPTIBLE,
            hourly_rate_usd=0.025,
        )
        nid = self.engine.register_node(node)
        self.assertTrue(nid.startswith("node-"))
        self.assertEqual(node.node_id, nid)

    def test_register_node_negative_rate_raises(self) -> None:
        node = RunnerFleetNode(
            node_id="n-neg",
            tier=RunnerInstanceTier.ON_DEMAND,
            hourly_rate_usd=-1.0,
        )
        with self.assertRaises(ValueError):
            self.engine.register_node(node)

    def test_record_node_activity_success(self) -> None:
        node = RunnerFleetNode(
            node_id="n-act",
            tier=RunnerInstanceTier.ON_DEMAND,
            hourly_rate_usd=1.0,
        )
        self.engine.register_node(node)
        updated = self.engine.record_node_activity("n-act", busy_hours=8.0, idle_hours=2.0)
        self.assertEqual(updated.active_busy_hours, 8.0)
        self.assertEqual(updated.idle_hours, 2.0)
        self.assertEqual(updated.total_running_hours, 10.0)

    def test_record_node_activity_negative_hours_raises(self) -> None:
        node = RunnerFleetNode(
            node_id="n-err",
            tier=RunnerInstanceTier.ON_DEMAND,
            hourly_rate_usd=1.0,
        )
        self.engine.register_node(node)
        with self.assertRaises(ValueError):
            self.engine.record_node_activity("n-err", busy_hours=-1.0, idle_hours=2.0)
        with self.assertRaises(ValueError):
            self.engine.record_node_activity("n-err", busy_hours=1.0, idle_hours=-2.0)

    def test_record_node_activity_unknown_node_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.record_node_activity("nonexistent", busy_hours=5.0, idle_hours=1.0)

    def test_record_activity_on_decommissioned_node_raises(self) -> None:
        node = RunnerFleetNode(
            node_id="n-decom",
            tier=RunnerInstanceTier.ON_DEMAND,
            hourly_rate_usd=0.5,
        )
        self.engine.register_node(node)
        self.engine.decommission_node("n-decom")
        self.assertFalse(node.is_active)
        with self.assertRaises(ValueError):
            self.engine.record_node_activity("n-decom", busy_hours=1.0, idle_hours=1.0)

    def test_decommission_unknown_node_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.decommission_node("ghost-node")

    def test_compute_node_economics(self) -> None:
        node = RunnerFleetNode(
            node_id="n-econ",
            tier=RunnerInstanceTier.ON_DEMAND,
            hourly_rate_usd=2.0,
        )
        self.engine.register_node(node)
        self.engine.record_node_activity("n-econ", busy_hours=75.0, idle_hours=25.0)

        econ = self.engine.compute_node_economics("n-econ")
        self.assertEqual(econ["total_running_hours"], 100.0)
        self.assertEqual(econ["active_busy_hours"], 75.0)
        self.assertEqual(econ["idle_hours"], 25.0)
        self.assertEqual(econ["total_spend_usd"], 200.0)
        self.assertEqual(econ["idle_spend_usd"], 50.0)
        self.assertEqual(econ["utilization_pct"], 75.0)

    def test_compute_node_economics_zero_hours(self) -> None:
        node = RunnerFleetNode(
            node_id="n-zero",
            tier=RunnerInstanceTier.ON_DEMAND,
            hourly_rate_usd=1.0,
        )
        self.engine.register_node(node)
        econ = self.engine.compute_node_economics("n-zero")
        self.assertEqual(econ["total_spend_usd"], 0.0)
        self.assertEqual(econ["utilization_pct"], 0.0)

    def test_compute_fleet_economics_multi_tier(self) -> None:
        # On-Demand: 10h @ $1.0 = $10 (8h busy, 2h idle)
        self.engine.register_node(
            RunnerFleetNode(
                node_id="n-od",
                tier=RunnerInstanceTier.ON_DEMAND,
                hourly_rate_usd=1.0,
            )
        )
        self.engine.record_node_activity("n-od", busy_hours=8.0, idle_hours=2.0)

        # Spot: 20h @ $0.5 = $10 (12h busy, 8h idle)
        self.engine.register_node(
            RunnerFleetNode(
                node_id="n-spot",
                tier=RunnerInstanceTier.SPOT_PREEMPTIBLE,
                hourly_rate_usd=0.5,
            )
        )
        self.engine.record_node_activity("n-spot", busy_hours=12.0, idle_hours=8.0)

        # Reserved: 50h @ $0.2 = $10 (40h busy, 10h idle)
        self.engine.register_node(
            RunnerFleetNode(
                node_id="n-res",
                tier=RunnerInstanceTier.RESERVED_COMMITTED,
                hourly_rate_usd=0.2,
            )
        )
        self.engine.record_node_activity("n-res", busy_hours=40.0, idle_hours=10.0)

        summary = self.engine.compute_fleet_economics()
        self.assertEqual(summary.total_nodes_count, 3)
        self.assertEqual(summary.active_nodes_count, 3)
        self.assertEqual(summary.total_fleet_spend_usd, 30.0)
        # Idle spend: 2*1.0 + 8*0.5 + 10*0.2 = 2.0 + 4.0 + 2.0 = 8.0
        self.assertEqual(summary.waste_idle_spend_usd, 8.0)
        # Busy hours: 8 + 12 + 40 = 60; Total: 10 + 20 + 50 = 80; Util: 60/80 = 75.0%
        self.assertEqual(summary.fleet_utilization_pct, 75.0)
        self.assertEqual(summary.by_tier[RunnerInstanceTier.ON_DEMAND.value], 10.0)
        self.assertEqual(summary.by_tier[RunnerInstanceTier.SPOT_PREEMPTIBLE.value], 10.0)
        self.assertEqual(summary.by_tier[RunnerInstanceTier.RESERVED_COMMITTED.value], 10.0)

    def test_get_fleet_report(self) -> None:
        self.engine.register_node(
            RunnerFleetNode(node_id="n-1", tier=RunnerInstanceTier.ON_DEMAND, hourly_rate_usd=1.0)
        )
        self.engine.register_node(
            RunnerFleetNode(node_id="n-2", tier=RunnerInstanceTier.SPOT_PREEMPTIBLE, hourly_rate_usd=0.5)
        )
        self.engine.decommission_node("n-2")

        rep = self.engine.get_fleet_report()
        self.assertEqual(rep["total_nodes"], 2)
        self.assertEqual(rep["active_nodes"], 1)
        self.assertEqual(rep["decommissioned_nodes"], 1)
        self.assertIn("total_fleet_spend_usd", rep)


if __name__ == "__main__":
    unittest.main()
