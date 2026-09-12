"""Comprehensive test suite for MultiregionActiveActiveEditionEngine (B38 - Skill 1323)."""

import unittest
from datetime import datetime, timezone

from elmos_mature_platform.multiregion_active_active_edition_engine import (
    MultiregionActiveActiveEditionEngine,
)
from elmos_mature_platform.types import (
    ActiveActiveRegionNode,
    QuorumStrategy,
    SyncReplicationState,
)


class TestMultiregionActiveActiveEditionComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = MultiregionActiveActiveEditionEngine(default_max_lag_ms=80.0)

    def _create_node(self, rid="us-east-1", weight=1.0, is_leader=False, lag=20.0):
        return ActiveActiveRegionNode(
            region_id=rid,
            cluster_name=f"cluster-{rid}",
            endpoint=f"https://{rid}.cluster.elmos.io",
            weight=weight,
            is_leader=is_leader,
            sync_state=SyncReplicationState.IN_SYNC,
            latency_p99_ms=lag,
            replication_lag_bytes=1024,
        )

    def test_create_topology_plan(self):
        plan = self.engine.create_topology_plan("ed-enterprise", QuorumStrategy.MAJORITY)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.edition_id, "ed-enterprise")
        self.assertEqual(plan.quorum_strategy, QuorumStrategy.MAJORITY)
        self.assertEqual(len(plan.nodes), 0)
        self.assertFalse(plan.split_brain_detected)

    def test_register_single_node(self):
        plan = self.engine.create_topology_plan("ed-01")
        node = self._create_node("us-east-1", is_leader=True)
        self.engine.register_region_node(plan.plan_id, node)
        retrieved = self.engine.get_topology_plan(plan.plan_id)
        self.assertIn("us-east-1", retrieved.nodes)
        self.assertTrue(retrieved.nodes["us-east-1"].is_leader)

    def test_register_multiple_leaders_demotes_prior(self):
        plan = self.engine.create_topology_plan("ed-01")
        node1 = self._create_node("us-east-1", is_leader=True)
        node2 = self._create_node("eu-west-1", is_leader=True)
        self.engine.register_region_node(plan.plan_id, node1)
        self.engine.register_region_node(plan.plan_id, node2)

        retrieved = self.engine.get_topology_plan(plan.plan_id)
        self.assertFalse(retrieved.nodes["us-east-1"].is_leader)
        self.assertTrue(retrieved.nodes["eu-west-1"].is_leader)

    def test_heartbeat_degradation_on_high_latency(self):
        plan = self.engine.create_topology_plan("ed-01", max_tolerable_lag_ms=50.0)
        node = self._create_node("ap-southeast-1", lag=10.0)
        self.engine.register_region_node(plan.plan_id, node)

        # Lag exceeds 50.0 ms -> DEGRADED
        updated = self.engine.update_node_heartbeat(plan.plan_id, "ap-southeast-1", latency_p99_ms=65.0, replication_lag_bytes=2048)
        self.assertEqual(updated.sync_state, SyncReplicationState.DEGRADED)

    def test_heartbeat_recovery_to_in_sync(self):
        plan = self.engine.create_topology_plan("ed-01", max_tolerable_lag_ms=50.0)
        node = self._create_node("ap-southeast-1", lag=60.0)
        self.engine.register_region_node(plan.plan_id, node)

        updated = self.engine.update_node_heartbeat(plan.plan_id, "ap-southeast-1", latency_p99_ms=25.0, replication_lag_bytes=512)
        self.assertEqual(updated.sync_state, SyncReplicationState.IN_SYNC)

    def test_elect_leader_success(self):
        plan = self.engine.create_topology_plan("ed-01")
        self.engine.register_region_node(plan.plan_id, self._create_node("us-east-1"))
        self.engine.register_region_node(plan.plan_id, self._create_node("eu-central-1"))

        leader = self.engine.elect_leader(plan.plan_id, "eu-central-1")
        self.assertTrue(leader.is_leader)
        self.assertFalse(plan.nodes["us-east-1"].is_leader)

    def test_elect_leader_desynchronized_node_fails(self):
        plan = self.engine.create_topology_plan("ed-01")
        node = self._create_node("us-west-2")
        node.sync_state = SyncReplicationState.DESYNCHRONIZED
        self.engine.register_region_node(plan.plan_id, node)

        with self.assertRaises(ValueError):
            self.engine.elect_leader(plan.plan_id, "us-west-2")

    def test_check_quorum_majority(self):
        plan = self.engine.create_topology_plan("ed-01", QuorumStrategy.MAJORITY)
        self.engine.register_region_node(plan.plan_id, self._create_node("r1"))
        self.engine.register_region_node(plan.plan_id, self._create_node("r2"))
        self.engine.register_region_node(plan.plan_id, self._create_node("r3"))

        q = self.engine.check_quorum(plan.plan_id)
        self.assertTrue(q["quorum_achieved"])
        self.assertEqual(q["healthy_nodes"], 3)

        # Degrade 2 nodes
        plan.nodes["r1"].sync_state = SyncReplicationState.DESYNCHRONIZED
        plan.nodes["r2"].sync_state = SyncReplicationState.DESYNCHRONIZED

        q2 = self.engine.check_quorum(plan.plan_id)
        self.assertFalse(q2["quorum_achieved"])
        self.assertEqual(q2["healthy_nodes"], 1)

    def test_check_quorum_weighted(self):
        plan = self.engine.create_topology_plan("ed-01", QuorumStrategy.WEIGHTED)
        self.engine.register_region_node(plan.plan_id, self._create_node("primary", weight=60.0))
        self.engine.register_region_node(plan.plan_id, self._create_node("secondary", weight=40.0))

        q = self.engine.check_quorum(plan.plan_id)
        self.assertTrue(q["quorum_achieved"])

        # Primary down, only 40% weight left -> fails
        plan.nodes["primary"].sync_state = SyncReplicationState.DESYNCHRONIZED
        q2 = self.engine.check_quorum(plan.plan_id)
        self.assertFalse(q2["quorum_achieved"])

    def test_isolate_node_reroutes_leader(self):
        plan = self.engine.create_topology_plan("ed-01")
        self.engine.register_region_node(plan.plan_id, self._create_node("r1", is_leader=True))
        self.engine.register_region_node(plan.plan_id, self._create_node("r2", is_leader=False))

        isolated = self.engine.isolate_node(plan.plan_id, "r1", reason="Network partition detected")
        self.assertEqual(isolated.sync_state, SyncReplicationState.DESYNCHRONIZED)
        self.assertFalse(isolated.is_leader)
        self.assertEqual(isolated.weight, 0.0)

        # Leader should have shifted to r2
        self.assertTrue(plan.nodes["r2"].is_leader)

    def test_cluster_status_report(self):
        plan = self.engine.create_topology_plan("ed-full")
        self.engine.register_region_node(plan.plan_id, self._create_node("us-east", lag=25.0, is_leader=True))
        self.engine.register_region_node(plan.plan_id, self._create_node("eu-west", lag=35.0))

        report = self.engine.get_cluster_status_report(plan.plan_id)
        self.assertEqual(report["total_nodes"], 2)
        self.assertEqual(report["leader_region"], "us-east")
        self.assertEqual(report["average_latency_p99_ms"], 30.0)
        self.assertTrue(report["quorum_achieved"])

    def test_audit_log_tracks_events(self):
        plan = self.engine.create_topology_plan("ed-audit")
        self.engine.register_region_node(plan.plan_id, self._create_node("r1"))
        self.engine.isolate_node(plan.plan_id, "r1", "test")
        logs = self.engine.get_audit_log()
        self.assertGreaterEqual(len(logs), 3)


if __name__ == "__main__":
    unittest.main()
