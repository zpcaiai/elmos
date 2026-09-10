import unittest
import sys
from pathlib import Path
import time

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from elmos_mature_platform.chaos_fault_engine import EnterpriseChaosEngine
from elmos_mature_platform.cross_region_simulation import CrossRegionSimulationEnvironment
from elmos_mature_platform.types import (
    FaultDescriptor,
    FaultType,
    RegionId,
    NodeStatus,
    NodeRole,
    FaultState,
    ChaosExperimentConfig
)

class TestEnterpriseChaosEngine(unittest.TestCase):
    def setUp(self):
        """Set up a fresh simulation environment and chaos engine before each test."""
        self.sim = CrossRegionSimulationEnvironment(seed=42)
        self.engine = EnterpriseChaosEngine(self.sim, seed=1337)
        self.sim.trigger_failover_election()

    def test_network_partition(self):
        """Test NETWORK_PARTITION injects correctly and heals on revert."""
        fault = FaultDescriptor(
            fault_id="f1",
            fault_type=FaultType.NETWORK_PARTITION,
            target_region=RegionId.US_EAST_1,
            target_node_ids=[]
        )
        self.assertTrue(self.engine.inject_fault(fault))
        self.assertIn(RegionId.US_EAST_1, self.sim.regions[RegionId.EU_WEST_1].partitioned_peers)
        self.assertEqual(self.sim.regions[RegionId.US_EAST_1].nodes["us-node-1"].status, NodeStatus.PARTITIONED)

        self.assertTrue(self.engine.revert_fault("f1"))
        self.assertNotIn(RegionId.US_EAST_1, self.sim.regions[RegionId.EU_WEST_1].partitioned_peers)
        self.assertEqual(self.sim.regions[RegionId.US_EAST_1].nodes["us-node-1"].status, NodeStatus.HEALTHY)

    def test_latency_injection(self):
        """Test LATENCY_INJECTION modifies wan_latency_matrix and resets on revert."""
        fault = FaultDescriptor(
            fault_id="f2",
            fault_type=FaultType.LATENCY_INJECTION,
            target_region=RegionId.US_EAST_1,
            target_node_ids=[],
            parameters={"latency_ms": 100.0}
        )
        old_latency = self.sim.regions[RegionId.US_EAST_1].wan_latency_matrix[RegionId.EU_WEST_1].mean_ms
        self.assertTrue(self.engine.inject_fault(fault))
        new_latency = self.sim.regions[RegionId.US_EAST_1].wan_latency_matrix[RegionId.EU_WEST_1].mean_ms
        self.assertEqual(new_latency, old_latency + 100.0)

        self.assertTrue(self.engine.revert_fault("f2"))
        reverted_latency = self.sim.regions[RegionId.US_EAST_1].wan_latency_matrix[RegionId.EU_WEST_1].mean_ms
        self.assertEqual(reverted_latency, old_latency)

    def test_packet_drop_corrupt(self):
        """Test PACKET_DROP_CORRUPT sets packet loss rate and resets it on revert."""
        fault = FaultDescriptor(
            fault_id="f3",
            fault_type=FaultType.PACKET_DROP_CORRUPT,
            target_region=RegionId.US_EAST_1,
            target_node_ids=[],
            parameters={"packet_loss_rate": 0.25}
        )
        self.assertTrue(self.engine.inject_fault(fault))
        loss = self.sim.regions[RegionId.US_EAST_1].wan_latency_matrix[RegionId.EU_WEST_1].packet_loss_rate
        self.assertEqual(loss, 0.25)

        self.assertTrue(self.engine.revert_fault("f3"))
        reverted_loss = self.sim.regions[RegionId.US_EAST_1].wan_latency_matrix[RegionId.EU_WEST_1].packet_loss_rate
        self.assertEqual(reverted_loss, 0.0)

    def test_cpu_exhaustion(self):
        """Test CPU_EXHAUSTION sets DEGRADED status and resets to HEALTHY."""
        fault = FaultDescriptor(
            fault_id="f4",
            fault_type=FaultType.CPU_EXHAUSTION,
            target_region=RegionId.US_EAST_1,
            target_node_ids=["us-node-2"]
        )
        self.assertTrue(self.engine.inject_fault(fault))
        self.assertEqual(self.sim.regions[RegionId.US_EAST_1].nodes["us-node-2"].status, NodeStatus.DEGRADED)

        self.assertTrue(self.engine.revert_fault("f4"))
        self.assertEqual(self.sim.regions[RegionId.US_EAST_1].nodes["us-node-2"].status, NodeStatus.HEALTHY)

    def test_memory_leak_pressure(self):
        """Test MEMORY_LEAK_PRESSURE sets DEGRADED status and resets to HEALTHY."""
        fault = FaultDescriptor(
            fault_id="f5",
            fault_type=FaultType.MEMORY_LEAK_PRESSURE,
            target_region=RegionId.EU_WEST_1,
            target_node_ids=["eu-node-1"]
        )
        self.assertTrue(self.engine.inject_fault(fault))
        self.assertEqual(self.sim.regions[RegionId.EU_WEST_1].nodes["eu-node-1"].status, NodeStatus.DEGRADED)

        self.assertTrue(self.engine.revert_fault("f5"))
        self.assertEqual(self.sim.regions[RegionId.EU_WEST_1].nodes["eu-node-1"].status, NodeStatus.HEALTHY)

    def test_disk_io_failure(self):
        """Test DISK_IO_FAILURE sets DEGRADED status and resets to HEALTHY."""
        fault = FaultDescriptor(
            fault_id="f6",
            fault_type=FaultType.DISK_IO_FAILURE,
            target_region=RegionId.AP_SOUTHEAST_1,
            target_node_ids=["ap-node-1"]
        )
        self.assertTrue(self.engine.inject_fault(fault))
        self.assertEqual(self.sim.regions[RegionId.AP_SOUTHEAST_1].nodes["ap-node-1"].status, NodeStatus.DEGRADED)

        self.assertTrue(self.engine.revert_fault("f6"))
        self.assertEqual(self.sim.regions[RegionId.AP_SOUTHEAST_1].nodes["ap-node-1"].status, NodeStatus.HEALTHY)

    def test_disk_space_exhaustion(self):
        """Test DISK_SPACE_EXHAUSTION fills disk and degrades node, resets on revert."""
        fault = FaultDescriptor(
            fault_id="f7",
            fault_type=FaultType.DISK_SPACE_EXHAUSTION,
            target_region=RegionId.US_EAST_1,
            target_node_ids=["us-node-3"]
        )
        node = self.sim.regions[RegionId.US_EAST_1].nodes["us-node-3"]
        self.assertTrue(self.engine.inject_fault(fault))
        self.assertEqual(node.status, NodeStatus.DEGRADED)
        self.assertEqual(node.storage_used_bytes, node.storage_total_bytes)

        self.assertTrue(self.engine.revert_fault("f7"))
        self.assertEqual(node.status, NodeStatus.HEALTHY)
        self.assertEqual(node.storage_used_bytes, 10 * 1024 * 1024 * 1024)

    def test_process_crash_zombie(self):
        """Test PROCESS_CRASH_ZOMBIE terminates node and demotes leader, heals on revert."""
        fault = FaultDescriptor(
            fault_id="f8",
            fault_type=FaultType.PROCESS_CRASH_ZOMBIE,
            target_region=RegionId.US_EAST_1,
            target_node_ids=["us-node-1"]
        )
        node = self.sim.regions[RegionId.US_EAST_1].nodes["us-node-1"]
        self.assertTrue(self.engine.inject_fault(fault))
        self.assertEqual(node.status, NodeStatus.TERMINATED)
        self.assertEqual(node.role, NodeRole.FOLLOWER)

        self.assertTrue(self.engine.revert_fault("f8"))
        self.assertEqual(node.status, NodeStatus.HEALTHY)

    def test_clock_skew_drift(self):
        """Test CLOCK_SKEW_DRIFT changes global offset and resets on revert."""
        fault = FaultDescriptor(
            fault_id="f9",
            fault_type=FaultType.CLOCK_SKEW_DRIFT,
            target_region=RegionId.US_EAST_1,
            target_node_ids=[],
            parameters={"skew_ms": 3000.0}
        )
        self.assertTrue(self.engine.inject_fault(fault))
        self.assertEqual(self.sim.global_clock_offset_ms, 3000.0)

        self.assertTrue(self.engine.revert_fault("f9"))
        self.assertEqual(self.sim.global_clock_offset_ms, 0.0)

    def test_poison_message_queue(self):
        """Test POISON_MESSAGE_QUEUE adds poison to backlog, drains on revert."""
        fault = FaultDescriptor(
            fault_id="f10",
            fault_type=FaultType.POISON_MESSAGE_QUEUE,
            target_region=RegionId.EU_WEST_1,
            target_node_ids=["eu-node-2"],
            parameters={"count": 5}
        )
        self.assertTrue(self.engine.inject_fault(fault))
        backlog = self.sim.replication_backlog["eu-node-2"]
        self.assertEqual(len(backlog), 5)
        self.assertEqual(backlog[0]["key"], "poison_payload_0")

        self.assertTrue(self.engine.revert_fault("f10"))
        self.assertEqual(len(self.sim.replication_backlog["eu-node-2"]), 0)

    def test_cascading_dependency(self):
        """Test CASCADING_DEPENDENCY degrades all nodes globally, restores on revert."""
        fault = FaultDescriptor(
            fault_id="f11",
            fault_type=FaultType.CASCADING_DEPENDENCY,
            target_region=RegionId.US_EAST_1,
            target_node_ids=[]
        )
        self.assertTrue(self.engine.inject_fault(fault))
        for reg in self.sim.regions.values():
            for node in reg.nodes.values():
                self.assertEqual(node.status, NodeStatus.DEGRADED)

        self.assertTrue(self.engine.revert_fault("f11"))
        for reg in self.sim.regions.values():
            for node in reg.nodes.values():
                self.assertEqual(node.status, NodeStatus.HEALTHY)

    def test_split_brain_partition(self):
        """Test SPLIT_BRAIN_PARTITION isolates US_EAST_1 and elects in EU."""
        fault = FaultDescriptor(
            fault_id="f12",
            fault_type=FaultType.SPLIT_BRAIN_PARTITION,
            target_region=RegionId.US_EAST_1,
            target_node_ids=[]
        )
        self.assertTrue(self.engine.inject_fault(fault))
        self.assertIn(RegionId.US_EAST_1, self.sim.regions[RegionId.EU_WEST_1].partitioned_peers)
        
        # Verify an EU node became leader during the failover call inside inject_fault
        eu_nodes = self.sim.regions[RegionId.EU_WEST_1].nodes.values()
        has_eu_leader = any(n.role == NodeRole.LEADER for n in eu_nodes)
        self.assertTrue(has_eu_leader)

        self.assertTrue(self.engine.revert_fault("f12"))
        self.assertNotIn(RegionId.US_EAST_1, self.sim.regions[RegionId.EU_WEST_1].partitioned_peers)
        self.assertEqual(self.sim.regions[RegionId.US_EAST_1].nodes["us-node-1"].status, NodeStatus.HEALTHY)

    def test_abort_all_chaos(self):
        """Test abort_all_chaos reverts multiple injected faults."""
        f1 = FaultDescriptor("fa1", FaultType.NETWORK_PARTITION, RegionId.US_EAST_1, [])
        f2 = FaultDescriptor("fa2", FaultType.CLOCK_SKEW_DRIFT, RegionId.US_EAST_1, [])
        self.engine.inject_fault(f1)
        self.engine.inject_fault(f2)
        
        self.assertEqual(len(self.engine.active_faults), 2)
        count = self.engine.abort_all_chaos("Test reason")
        
        self.assertEqual(count, 2)
        self.assertEqual(len(self.engine.active_faults), 0)
        self.assertEqual(self.engine.governor_interventions, 1)

    def test_run_chaos_experiment_no_workload(self):
        """Test run_chaos_experiment using the simulated workload."""
        faults = [FaultDescriptor("exp1", FaultType.LATENCY_INJECTION, RegionId.US_EAST_1, [])]
        config = ChaosExperimentConfig(
            experiment_id="e1",
            title="Test",
            target_faults=faults
        )
        res = self.engine.run_chaos_experiment(config)
        self.assertTrue(res.success)
        self.assertEqual(res.faults_executed, 1)
        self.assertEqual(res.faults_reverted, 1)
        self.assertEqual(len(self.engine.active_faults), 0)

    def test_run_chaos_experiment_with_workload(self):
        """Test run_chaos_experiment using a custom workload fn."""
        faults = [FaultDescriptor("exp2", FaultType.LATENCY_INJECTION, RegionId.US_EAST_1, [])]
        config = ChaosExperimentConfig(
            experiment_id="e2",
            title="Test 2",
            target_faults=faults
        )
        def my_workload():
            return 200, 5, 120.0
        
        res = self.engine.run_chaos_experiment(config, workload_fn=my_workload)
        self.assertTrue(res.success)
        self.assertEqual(res.telemetry_summary["total_requests"], 200)
        self.assertEqual(res.telemetry_summary["error_count"], 5)
        self.assertEqual(res.telemetry_summary["p99_latency_ms"], 120.0)

    def test_run_chaos_experiment_governor_intervention(self):
        """Test governor aborts if error rate exceeds threshold."""
        faults = [FaultDescriptor("exp3", FaultType.NETWORK_PARTITION, RegionId.US_EAST_1, [])]
        config = ChaosExperimentConfig(
            experiment_id="e3",
            title="Test 3",
            target_faults=faults,
            allowed_error_rate_threshold=0.01
        )
        def high_error_workload():
            return 100, 50, 50.0  # 50% error rate
            
        res = self.engine.run_chaos_experiment(config, workload_fn=high_error_workload)
        # It's an abort, so reverted == injected, but governor intervention triggered.
        self.assertEqual(res.governor_interventions, 1)
        # We also check that active faults is 0
        self.assertEqual(len(self.engine.active_faults), 0)

    def test_fault_state_transitions(self):
        """Test FaultDescriptor state changes PENDING -> ACTIVE -> REVERTED."""
        fault = FaultDescriptor("st1", FaultType.LATENCY_INJECTION, RegionId.US_EAST_1, [])
        self.assertEqual(fault.state, FaultState.PENDING)
        
        self.engine.inject_fault(fault)
        self.assertEqual(fault.state, FaultState.ACTIVE)
        self.assertIsNotNone(fault.started_at)
        
        self.engine.revert_fault("st1")
        self.assertEqual(fault.state, FaultState.REVERTED)
        self.assertIsNotNone(fault.reverted_at)

    def test_history_tracking(self):
        """Test reverted faults appear in the history list."""
        fault = FaultDescriptor("ht1", FaultType.LATENCY_INJECTION, RegionId.US_EAST_1, [])
        self.engine.inject_fault(fault)
        self.engine.revert_fault("ht1")
        
        self.assertEqual(len(self.engine.history), 1)
        self.assertEqual(self.engine.history[0].fault_id, "ht1")

    def test_event_log_entries(self):
        """Test the engine logs events."""
        initial_log_len = len(self.engine.event_log)
        fault = FaultDescriptor("lg1", FaultType.LATENCY_INJECTION, RegionId.US_EAST_1, [])
        self.engine.inject_fault(fault)
        self.assertTrue(len(self.engine.event_log) > initial_log_len)
        self.assertIn("Injecting fault", self.engine.event_log[-1])

    def test_revert_non_existent_fault(self):
        """Test reverting a fault that does not exist returns False."""
        self.assertFalse(self.engine.revert_fault("non_existent"))

    def test_inject_fault_non_existent_target_nodes(self):
        """Test injecting CPU exhaustion on non-existent node fails gracefully."""
        fault = FaultDescriptor(
            fault_id="nf1",
            fault_type=FaultType.CPU_EXHAUSTION,
            target_region=RegionId.US_EAST_1,
            target_node_ids=["invalid-node-id"]
        )
        self.assertTrue(self.engine.inject_fault(fault)) # Still returns true, just doesn't find the node
        # Ensure no crash happened.

    def test_run_chaos_experiment_timeout_governor(self):
        """Test that governor aborts when experiment duration is too long."""
        faults = [FaultDescriptor("exp4", FaultType.LATENCY_INJECTION, RegionId.US_EAST_1, [])]
        config = ChaosExperimentConfig(
            experiment_id="e4",
            title="Test Timeout",
            target_faults=faults,
            max_duration_seconds=-1.0 # Force timeout
        )
        res = self.engine.run_chaos_experiment(config)
        self.assertEqual(res.governor_interventions, 1)

    def test_inject_exception_fails(self):
        """Test fault injection gracefully handles exceptions."""
        fault = FaultDescriptor("err1", FaultType.NETWORK_PARTITION, RegionId.US_EAST_1, [])
        # We can simulate an exception by passing an invalid fault_type that fails inside inject_fault
        # Or mock sim.isolate_region. A simpler way is to just delete the region from sim
        del self.sim.regions[RegionId.US_EAST_1]
        self.assertFalse(self.engine.inject_fault(fault))
        self.assertEqual(fault.state, FaultState.FAILED)

    def test_revert_exception_fails(self):
        """Test fault revert gracefully handles exceptions."""
        fault = FaultDescriptor("err2", FaultType.NETWORK_PARTITION, RegionId.US_EAST_1, [])
        self.engine.active_faults["err2"] = fault # Bypass injection
        del self.sim.regions[RegionId.US_EAST_1]
        self.assertFalse(self.engine.revert_fault("err2"))

    def test_clear_fault_alias(self):
        """Test clear_fault is an alias for revert_fault."""
        fault = FaultDescriptor("clr1", FaultType.LATENCY_INJECTION, RegionId.US_EAST_1, [])
        self.engine.inject_fault(fault)
        self.assertTrue(self.engine.clear_fault("clr1"))
        self.assertEqual(fault.state, FaultState.REVERTED)

if __name__ == "__main__":
    unittest.main()
