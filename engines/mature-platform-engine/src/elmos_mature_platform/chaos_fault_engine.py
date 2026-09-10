"""Chaos Fault Injection Engine and Blast-Radius Governor for Elmos Mature Platform."""

from __future__ import annotations

from datetime import datetime, timezone
import random
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from elmos_mature_platform.cross_region_simulation import CrossRegionSimulationEnvironment
from elmos_mature_platform.types import (
    ChaosExecutionResult,
    ChaosExperimentConfig,
    FaultDescriptor,
    FaultState,
    FaultType,
    NodeRole,
    NodeStatus,
    RegionId,
)


class EnterpriseChaosEngine:
    """Industrial Chaos Fault Injection Engine supporting 12 fault types with blast-radius safety governor."""

    def __init__(self, cluster_sim: CrossRegionSimulationEnvironment, seed: int = 1337) -> None:
        self.sim = cluster_sim
        self._rnd = random.Random(seed)
        self.active_faults: Dict[str, FaultDescriptor] = {}
        self.history: List[FaultDescriptor] = []
        self.governor_interventions: int = 0
        self.event_log: List[str] = []

    def _log(self, message: str) -> None:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        entry = f"[{ts}][CHAOS-ENGINE] {message}"
        self.event_log.append(entry)

    def inject_fault(self, fault: FaultDescriptor) -> bool:
        """Injects a specified fault into the simulated environment."""
        self._log(f"Injecting fault: ID={fault.fault_id}, Type={fault.fault_type.value}, TargetRegion={fault.target_region.value}")
        fault.state = FaultState.ACTIVE
        fault.started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        try:
            if fault.fault_type == FaultType.NETWORK_PARTITION:
                self.sim.isolate_region(fault.target_region)
                fault.impact_summary = f"Isolated region {fault.target_region.value} from peer mesh"

            elif fault.fault_type == FaultType.LATENCY_INJECTION:
                added_latency = fault.parameters.get("latency_ms", 250.0)
                for peer in self.sim.regions[fault.target_region].wan_latency_matrix.values():
                    peer.mean_ms += added_latency
                fault.impact_summary = f"Injected {added_latency}ms latency to region {fault.target_region.value}"

            elif fault.fault_type == FaultType.PACKET_DROP_CORRUPT:
                drop_rate = fault.parameters.get("packet_loss_rate", 0.15)
                for peer in self.sim.regions[fault.target_region].wan_latency_matrix.values():
                    peer.packet_loss_rate = drop_rate
                fault.impact_summary = f"Configured {drop_rate*100:.1f}% packet drop on region {fault.target_region.value}"

            elif fault.fault_type == FaultType.CPU_EXHAUSTION:
                for node_id in fault.target_node_ids:
                    node = self.sim.regions[fault.target_region].nodes.get(node_id)
                    if node:
                        node.status = NodeStatus.DEGRADED
                fault.impact_summary = f"Saturated CPU threads on nodes: {fault.target_node_ids}"

            elif fault.fault_type == FaultType.MEMORY_LEAK_PRESSURE:
                for node_id in fault.target_node_ids:
                    node = self.sim.regions[fault.target_region].nodes.get(node_id)
                    if node:
                        node.status = NodeStatus.DEGRADED
                fault.impact_summary = f"Simulated memory pressure / OOM risk on nodes: {fault.target_node_ids}"

            elif fault.fault_type == FaultType.DISK_IO_FAILURE:
                for node_id in fault.target_node_ids:
                    node = self.sim.regions[fault.target_region].nodes.get(node_id)
                    if node:
                        node.status = NodeStatus.DEGRADED
                fault.impact_summary = f"Simulated read-only disk I/O errors on nodes: {fault.target_node_ids}"

            elif fault.fault_type == FaultType.DISK_SPACE_EXHAUSTION:
                for node_id in fault.target_node_ids:
                    node = self.sim.regions[fault.target_region].nodes.get(node_id)
                    if node:
                        node.storage_used_bytes = node.storage_total_bytes  # ENOSPC
                        node.status = NodeStatus.DEGRADED
                fault.impact_summary = f"Simulated ENOSPC (Disk Full) on nodes: {fault.target_node_ids}"

            elif fault.fault_type == FaultType.PROCESS_CRASH_ZOMBIE:
                for node_id in fault.target_node_ids:
                    node = self.sim.regions[fault.target_region].nodes.get(node_id)
                    if node:
                        node.status = NodeStatus.TERMINATED
                        if node.role == NodeRole.LEADER:
                            node.role = NodeRole.FOLLOWER
                fault.impact_summary = f"Terminated process (SIGKILL) on nodes: {fault.target_node_ids}"

            elif fault.fault_type == FaultType.CLOCK_SKEW_DRIFT:
                skew_ms = fault.parameters.get("skew_ms", 5000.0)
                self.sim.global_clock_offset_ms += skew_ms
                fault.impact_summary = f"Skewed cluster clock by {skew_ms}ms"

            elif fault.fault_type == FaultType.POISON_MESSAGE_QUEUE:
                poison_count = fault.parameters.get("count", 10)
                for node_id in fault.target_node_ids:
                    for i in range(poison_count):
                        self.sim.replication_backlog[node_id].append({
                            "key": f"poison_payload_{i}",
                            "value": "\x00CORRUPT_SERIALIZATION_BOMB",
                            "term": 99999,
                            "index": -1,
                            "fencing_token": 0,
                            "timestamp": time.time(),
                        })
                fault.impact_summary = f"Injected {poison_count} poison messages into node backlogs"

            elif fault.fault_type == FaultType.CASCADING_DEPENDENCY:
                for reg in self.sim.regions.values():
                    for node in reg.nodes.values():
                        node.status = NodeStatus.DEGRADED
                fault.impact_summary = "Triggered cascading circuit trips across all nodes"

            elif fault.fault_type == FaultType.SPLIT_BRAIN_PARTITION:
                # Disconnect primary from both secondaries
                self.sim.isolate_region(RegionId.US_EAST_1)
                # Force candidate in EU
                eu_leader = self.sim.trigger_failover_election(RegionId.EU_WEST_1)
                fault.impact_summary = f"Simulated split-brain condition (EU leader elected={eu_leader is not None})"

            self.active_faults[fault.fault_id] = fault
            return True

        except Exception as exc:
            fault.state = FaultState.FAILED
            fault.impact_summary = f"Fault injection error: {exc}"
            self._log(f"Failed to inject fault {fault.fault_id}: {exc}")
            return False

    def revert_fault(self, fault_id: str) -> bool:
        """Reverts an active fault to healthy baseline state."""
        fault = self.active_faults.get(fault_id)
        if not fault:
            return False

        self._log(f"Reverting fault: ID={fault.fault_id}, Type={fault.fault_type.value}")
        try:
            if fault.fault_type in (FaultType.NETWORK_PARTITION, FaultType.SPLIT_BRAIN_PARTITION):
                self.sim.heal_partition(fault.target_region)
                if fault.fault_type == FaultType.SPLIT_BRAIN_PARTITION:
                    self.sim.heal_partition(RegionId.US_EAST_1)

            elif fault.fault_type == FaultType.LATENCY_INJECTION:
                added_latency = fault.parameters.get("latency_ms", 250.0)
                for peer in self.sim.regions[fault.target_region].wan_latency_matrix.values():
                    peer.mean_ms = max(5.0, peer.mean_ms - added_latency)

            elif fault.fault_type == FaultType.PACKET_DROP_CORRUPT:
                for peer in self.sim.regions[fault.target_region].wan_latency_matrix.values():
                    peer.packet_loss_rate = 0.0

            elif fault.fault_type in (FaultType.CPU_EXHAUSTION, FaultType.MEMORY_LEAK_PRESSURE, FaultType.DISK_IO_FAILURE):
                for node_id in fault.target_node_ids:
                    node = self.sim.regions[fault.target_region].nodes.get(node_id)
                    if node:
                        node.status = NodeStatus.HEALTHY

            elif fault.fault_type == FaultType.DISK_SPACE_EXHAUSTION:
                for node_id in fault.target_node_ids:
                    node = self.sim.regions[fault.target_region].nodes.get(node_id)
                    if node:
                        node.storage_used_bytes = 10 * 1024 * 1024 * 1024  # 10GB
                        node.status = NodeStatus.HEALTHY

            elif fault.fault_type == FaultType.PROCESS_CRASH_ZOMBIE:
                for node_id in fault.target_node_ids:
                    node = self.sim.regions[fault.target_region].nodes.get(node_id)
                    if node:
                        node.status = NodeStatus.HEALTHY

            elif fault.fault_type == FaultType.CLOCK_SKEW_DRIFT:
                self.sim.global_clock_offset_ms = 0.0

            elif fault.fault_type == FaultType.POISON_MESSAGE_QUEUE:
                for node_id in fault.target_node_ids:
                    self.sim.drain_replication_backlog(node_id)

            elif fault.fault_type == FaultType.CASCADING_DEPENDENCY:
                for reg in self.sim.regions.values():
                    for node in reg.nodes.values():
                        node.status = NodeStatus.HEALTHY

            fault.state = FaultState.REVERTED
            fault.reverted_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            del self.active_faults[fault_id]
            self.history.append(fault)
            return True

        except Exception as exc:
            self._log(f"Error reverting fault {fault_id}: {exc}")
            return False

    clear_fault = revert_fault

    def abort_all_chaos(self, reason: str = "Safety Governor Intervention") -> int:
        """Emergency blast-radius killswitch: reverts all currently active faults."""
        self._log(f"BLAST RADIUS GOVERNOR ABORT TRIGGERED: {reason}")
        self.governor_interventions += 1
        reverted_count = 0
        active_ids = list(self.active_faults.keys())
        for f_id in active_ids:
            if self.revert_fault(f_id):
                reverted_count += 1
        return reverted_count

    def run_chaos_experiment(
        self,
        config: ChaosExperimentConfig,
        workload_fn: Optional[Callable[[], Tuple[int, int, float]]] = None,
    ) -> ChaosExecutionResult:
        """Executes a structured chaos experiment with automated safety governance."""
        self._log(f"Starting chaos experiment '{config.title}' (ID: {config.experiment_id})")
        start_time = time.time()
        injected = 0
        reverted = 0
        zero_tolerance_violations = 0

        # 1. Inject planned faults
        for fault in config.target_faults:
            if self.inject_fault(fault):
                injected += 1

        # 2. Run workload and monitor metrics
        total_requests = 100
        errors = 0
        p99_latency = 45.0

        if workload_fn:
            total_requests, errors, p99_latency = workload_fn()
        else:
            # Simulated workload run
            for _ in range(100):
                leader = self.sim.get_leader()
                if not leader:
                    errors += 1
                else:
                    success, _ = self.sim.replicate_transaction("chaos_key", "test_val", leader.fencing_token)
                    if not success:
                        errors += 1

        error_rate = errors / max(1, total_requests)

        # 3. Check Safety Governor conditions
        if error_rate > config.allowed_error_rate_threshold:
            self._log(f"Governor Alert: Error rate {error_rate:.4f} exceeded threshold {config.allowed_error_rate_threshold}")
            self.abort_all_chaos("Error rate threshold exceeded")
            reverted = injected
        elif time.time() - start_time > config.max_duration_seconds:
            self._log("Governor Alert: Maximum experiment duration reached")
            self.abort_all_chaos("Duration timeout")
            reverted = injected
        else:
            # Graceful revert
            for fault in config.target_faults:
                if self.revert_fault(fault.fault_id):
                    reverted += 1

        success = (reverted == injected) and (zero_tolerance_violations == 0)

        result = ChaosExecutionResult(
            experiment_id=config.experiment_id,
            success=success,
            faults_executed=injected,
            faults_reverted=reverted,
            governor_interventions=self.governor_interventions,
            zero_tolerance_violations=zero_tolerance_violations,
            telemetry_summary={
                "total_requests": total_requests,
                "error_count": errors,
                "error_rate": error_rate,
                "p99_latency_ms": p99_latency,
            },
            log_traces=self.event_log.copy(),
        )
        self._log(f"Finished chaos experiment {config.experiment_id}: success={success}")
        return result
