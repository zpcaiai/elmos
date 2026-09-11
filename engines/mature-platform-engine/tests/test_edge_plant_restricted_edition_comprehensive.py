import unittest
from elmos_mature_platform.edge_plant_restricted_edition_engine import (
    EdgePlantRestrictedEditionEngine,
)
from elmos_mature_platform.types import (
    EdgeConnectivityState,
    EdgeNodeConfig,
    EdgeSyncEvent,
    PlantProtocolSupport,
)


class TestEdgePlantRestrictedEditionComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = EdgePlantRestrictedEditionEngine()

    def test_register_and_heartbeat(self):
        node = EdgeNodeConfig(
            node_id="",
            plant_id="plant-shanghai-01",
            site_name="Assembly Plant Line 4",
            supported_protocols=[PlantProtocolSupport.OPC_UA, PlantProtocolSupport.MODBUS_TCP],
            local_storage_limit_gb=100.0,
            used_storage_gb=12.5,
        )
        node_id = self.engine.register_edge_node(node)
        self.assertTrue(bool(node_id))
        self.assertTrue(node_id.startswith("edge-"))

        updated = self.engine.record_heartbeat(node_id, 15.0)
        self.assertEqual(updated.used_storage_gb, 15.0)

    def test_connectivity_and_quarantine(self):
        node = EdgeNodeConfig(
            node_id="edge-airgap-1",
            plant_id="plant-munich-02",
            site_name="Chemical Reactor Cell",
            connectivity_state=EdgeConnectivityState.ONLINE,
        )
        self.engine.register_edge_node(node)

        self.engine.update_connectivity("edge-airgap-1", EdgeConnectivityState.ISOLATED_AIRGAP)
        self.assertEqual(node.connectivity_state, EdgeConnectivityState.ISOLATED_AIRGAP)

        self.engine.quarantine_node("edge-airgap-1", reason="Unrecognized Modbus payload sequence")
        self.assertTrue(node.is_quarantined)

        # Quarantined node cannot sync
        sync = EdgeSyncEvent(
            node_id="edge-airgap-1",
            sync_id="",
            records_buffered=500,
            records_synced=500,
            conflict_count=0,
        )
        with self.assertRaises(PermissionError):
            self.engine.sync_offline_buffer(sync)

    def test_sync_buffer_and_storage_pressure(self):
        node = EdgeNodeConfig(
            node_id="edge-sync-1",
            plant_id="plant-detroit-03",
            site_name="Stamping Facility",
            local_storage_limit_gb=50.0,
            used_storage_gb=46.0,  # 92% pressure
        )
        self.engine.register_edge_node(node)

        pressured = self.engine.detect_storage_pressure_nodes(threshold_pct=85.0)
        self.assertEqual(len(pressured), 1)
        self.assertEqual(pressured[0].node_id, "edge-sync-1")

        sync = EdgeSyncEvent(
            node_id="edge-sync-1",
            sync_id="",
            records_buffered=1000,
            records_synced=1000,
            conflict_count=0,
        )
        res = self.engine.sync_offline_buffer(sync)
        self.assertEqual(res.status, "success")

        report = self.engine.get_plant_edge_fleet_report()
        self.assertEqual(report["total_edge_nodes"], 1)
        self.assertEqual(report["total_synced_records"], 1000)

    def test_register_missing_plant_id_error(self):
        node = EdgeNodeConfig(node_id="node-bad", plant_id="", site_name="")
        with self.assertRaises(ValueError):
            self.engine.register_edge_node(node)

    def test_sync_partial_with_conflicts(self):
        node = EdgeNodeConfig(
            node_id="edge-conflict",
            plant_id="plant-nagoya-04",
            site_name="Robotics Bay",
        )
        self.engine.register_edge_node(node)

        sync = EdgeSyncEvent(
            node_id="edge-conflict",
            sync_id="s-conf",
            records_buffered=200,
            records_synced=180,
            conflict_count=20,
        )
        res = self.engine.sync_offline_buffer(sync)
        self.assertEqual(res.status, "partial")
        self.assertEqual(res.conflict_count, 20)

    def test_get_sync_history(self):
        node = EdgeNodeConfig(node_id="edge-hist", plant_id="plant-seoul", site_name="Semiconductor Plant")
        self.engine.register_edge_node(node)

        s1 = EdgeSyncEvent(node_id="edge-hist", records_buffered=50, records_synced=50)
        s2 = EdgeSyncEvent(node_id="edge-hist", records_buffered=80, records_synced=80)
        self.engine.sync_offline_buffer(s1)
        self.engine.sync_offline_buffer(s2)

        history = self.engine.get_sync_history("edge-hist")
        self.assertEqual(len(history), 2)

    def test_fleet_report_multiple_states(self):
        n1 = EdgeNodeConfig("n1", "p1", "Site 1", EdgeConnectivityState.ONLINE)
        n2 = EdgeNodeConfig("n2", "p2", "Site 2", EdgeConnectivityState.ISOLATED_AIRGAP)
        self.engine.register_edge_node(n1)
        self.engine.register_edge_node(n2)
        self.engine.quarantine_node("n2")

        rep = self.engine.get_plant_edge_fleet_report()
        self.assertEqual(rep["total_edge_nodes"], 2)
        self.assertEqual(rep["online_nodes"], 1)
        self.assertEqual(rep["quarantined_nodes"], 1)


if __name__ == "__main__":
    unittest.main()
