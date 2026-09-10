import unittest
import uuid
from elmos_mature_platform.types import MixedVersionCluster, ClusterNode, MixedVersionState
from elmos_mature_platform.rolling_mixed_version_engine import RollingMixedVersionEngine

class TestRollingMixedVersionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = RollingMixedVersionEngine()

    def test_create_cluster(self):
        cluster = MixedVersionCluster(cluster_id="c1", name="cluster-1")
        c_id = self.engine.create_cluster(cluster)
        self.assertEqual(c_id, "c1")
        self.assertEqual(self.engine.clusters["c1"].state, MixedVersionState.HOMOGENEOUS)

    def test_create_cluster_auto_id(self):
        cluster = MixedVersionCluster(cluster_id="", name="cluster-2")
        c_id = self.engine.create_cluster(cluster)
        self.assertTrue(c_id != "")
        self.assertEqual(self.engine.clusters[c_id].name, "cluster-2")

    def test_add_node(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        node = ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0")
        self.engine.add_node(node)
        self.assertEqual(self.engine.clusters["c1"].total_nodes, 1)
        self.assertEqual(self.engine.clusters["c1"].source_version, "1.0.0")

    def test_add_node_invalid_cluster(self):
        node = ClusterNode(node_id="n1", cluster_id="invalid", current_version="1.0.0")
        with self.assertRaises(ValueError):
            self.engine.add_node(node)

    def test_add_node_mixed_state(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        self.engine.add_node(ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0"))
        self.engine.add_node(ClusterNode(node_id="n2", cluster_id="c1", current_version="1.1.0"))
        self.assertEqual(self.engine.clusters["c1"].state, MixedVersionState.MIXED)

    def test_check_compatibility_valid(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        self.engine.add_node(ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0"))
        check = self.engine.check_compatibility("c1", "1.1.0")
        self.assertTrue(check.overall_compatible)

    def test_check_compatibility_invalid(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        self.engine.add_node(ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0"))
        check = self.engine.check_compatibility("c1", "2.0.0")
        self.assertFalse(check.overall_compatible)
        self.assertTrue(len(check.issues) > 0)

    def test_check_compatibility_missing_cluster(self):
        with self.assertRaises(ValueError):
            self.engine.check_compatibility("c1", "1.1.0")

    def test_start_rolling_upgrade_without_compat(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        with self.assertRaises(ValueError):
            self.engine.start_rolling_upgrade("c1", "1.1.0")

    def test_start_rolling_upgrade_valid(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        self.engine.add_node(ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0"))
        self.engine.check_compatibility("c1", "1.1.0")
        cluster = self.engine.start_rolling_upgrade("c1", "1.1.0")
        self.assertEqual(cluster.state, MixedVersionState.ROLLING)

    def test_start_rolling_upgrade_missing_cluster(self):
        with self.assertRaises(ValueError):
            self.engine.start_rolling_upgrade("c1", "1.1.0")

    def test_upgrade_next_batch_missing_cluster(self):
        with self.assertRaises(ValueError):
            self.engine.upgrade_next_batch("c1")

    def test_upgrade_next_batch_wrong_state(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        with self.assertRaises(ValueError):
            self.engine.upgrade_next_batch("c1")

    def test_upgrade_next_batch_basic(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1", max_unavailable=2))
        self.engine.add_node(ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0"))
        self.engine.add_node(ClusterNode(node_id="n2", cluster_id="c1", current_version="1.0.0"))
        self.engine.add_node(ClusterNode(node_id="n3", cluster_id="c1", current_version="1.0.0"))
        self.engine.check_compatibility("c1", "1.1.0")
        self.engine.start_rolling_upgrade("c1", "1.1.0")
        
        batch = self.engine.upgrade_next_batch("c1")
        self.assertEqual(len(batch), 2)
        self.assertEqual(batch[0].drain_status, "draining")

    def test_complete_node_upgrade_missing_node(self):
        with self.assertRaises(ValueError):
            self.engine.complete_node_upgrade("n1")

    def test_complete_node_upgrade_not_scheduled(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        self.engine.add_node(ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0"))
        with self.assertRaises(ValueError):
            self.engine.complete_node_upgrade("n1")

    def test_complete_node_upgrade(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        self.engine.add_node(ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0"))
        self.engine.check_compatibility("c1", "1.1.0")
        self.engine.start_rolling_upgrade("c1", "1.1.0")
        self.engine.upgrade_next_batch("c1")
        node = self.engine.complete_node_upgrade("n1")
        self.assertTrue(node.upgraded)
        self.assertEqual(node.current_version, "1.1.0")

    def test_complete_node_upgrade_completes_cluster(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        self.engine.add_node(ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0"))
        self.engine.check_compatibility("c1", "1.1.0")
        self.engine.start_rolling_upgrade("c1", "1.1.0")
        self.engine.upgrade_next_batch("c1")
        self.engine.complete_node_upgrade("n1")
        self.assertEqual(self.engine.clusters["c1"].state, MixedVersionState.COMPLETED)

    def test_verify_node_health(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        self.engine.add_node(ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0"))
        self.assertTrue(self.engine.verify_node_health("n1"))
        self.engine.nodes["n1"].healthy = False
        self.assertFalse(self.engine.verify_node_health("n1"))

    def test_verify_node_health_missing(self):
        with self.assertRaises(ValueError):
            self.engine.verify_node_health("n1")

    def test_pause_upgrade_missing(self):
        with self.assertRaises(ValueError):
            self.engine.pause_upgrade("c1")

    def test_pause_upgrade_wrong_state(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        with self.assertRaises(ValueError):
            self.engine.pause_upgrade("c1")

    def test_pause_upgrade(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        self.engine.add_node(ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0"))
        self.engine.check_compatibility("c1", "1.1.0")
        self.engine.start_rolling_upgrade("c1", "1.1.0")
        cluster = self.engine.pause_upgrade("c1")
        self.assertEqual(cluster.state, MixedVersionState.PAUSED)

    def test_resume_upgrade_missing(self):
        with self.assertRaises(ValueError):
            self.engine.resume_upgrade("c1")

    def test_resume_upgrade_wrong_state(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        with self.assertRaises(ValueError):
            self.engine.resume_upgrade("c1")

    def test_resume_upgrade(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        self.engine.add_node(ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0"))
        self.engine.check_compatibility("c1", "1.1.0")
        self.engine.start_rolling_upgrade("c1", "1.1.0")
        self.engine.pause_upgrade("c1")
        cluster = self.engine.resume_upgrade("c1")
        self.assertEqual(cluster.state, MixedVersionState.ROLLING)

    def test_rollback_upgrade_missing(self):
        with self.assertRaises(ValueError):
            self.engine.rollback_upgrade("c1")

    def test_rollback_upgrade(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        self.engine.add_node(ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0"))
        self.engine.check_compatibility("c1", "1.1.0")
        self.engine.start_rolling_upgrade("c1", "1.1.0")
        self.engine.upgrade_next_batch("c1")
        self.engine.complete_node_upgrade("n1")
        
        cluster = self.engine.rollback_upgrade("c1")
        self.assertEqual(cluster.state, MixedVersionState.MIXED)
        self.assertEqual(cluster.upgraded_nodes, 0)
        self.assertEqual(self.engine.nodes["n1"].current_version, "1.0.0")
        self.assertFalse(self.engine.nodes["n1"].upgraded)

    def test_get_cluster_state_missing(self):
        with self.assertRaises(ValueError):
            self.engine.get_cluster_state("c1")

    def test_get_cluster_state(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        self.engine.add_node(ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0"))
        state = self.engine.get_cluster_state("c1")
        self.assertEqual(state["total_nodes"], 1)
        self.assertEqual(state["healthy_nodes"], 1)
        self.assertEqual(state["unhealthy_nodes"], 0)

    def test_get_upgrade_progress_missing(self):
        with self.assertRaises(ValueError):
            self.engine.get_upgrade_progress("c1")

    def test_get_upgrade_progress(self):
        self.engine.create_cluster(MixedVersionCluster(cluster_id="c1", name="c1"))
        self.engine.add_node(ClusterNode(node_id="n1", cluster_id="c1", current_version="1.0.0"))
        self.engine.check_compatibility("c1", "1.1.0")
        self.engine.start_rolling_upgrade("c1", "1.1.0")
        prog = self.engine.get_upgrade_progress("c1")
        self.assertEqual(prog["percentage"], 0)
        
        self.engine.upgrade_next_batch("c1")
        self.engine.complete_node_upgrade("n1")
        prog2 = self.engine.get_upgrade_progress("c1")
        self.assertEqual(prog2["percentage"], 100)
        self.assertTrue(prog2["completed"])

if __name__ == "__main__":
    unittest.main()
