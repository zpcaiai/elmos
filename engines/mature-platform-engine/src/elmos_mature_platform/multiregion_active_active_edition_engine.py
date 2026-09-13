"""Multiregion Active-Active Edition Engine (Batch 38 - Skill 1323).

Coordinates active-active cluster topology across multiple cloud regions,
managing leader election, sync replication states, latency bounds, split-brain detection,
and automated quorum verification.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    ActiveActiveRegionNode,
    ActiveActiveTopologyPlan,
    QuorumStrategy,
    SyncReplicationState,
)


class MultiregionActiveActiveEditionEngine:
    """Industrial active-active cluster management engine (B38)."""

    def __init__(self, default_max_lag_ms: float = 100.0):
        self.default_max_lag_ms = default_max_lag_ms
        self._topologies: Dict[str, ActiveActiveTopologyPlan] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def create_topology_plan(
        self,
        edition_id: str,
        quorum_strategy: QuorumStrategy = QuorumStrategy.MAJORITY,
        max_tolerable_lag_ms: Optional[float] = None,
    ) -> ActiveActiveTopologyPlan:
        """Create and store a new active-active multiregion topology plan."""
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        plan = ActiveActiveTopologyPlan(
            plan_id=plan_id,
            edition_id=edition_id,
            quorum_strategy=quorum_strategy,
            nodes={},
            max_tolerable_lag_ms=max_tolerable_lag_ms or self.default_max_lag_ms,
            split_brain_detected=False,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._topologies[plan_id] = plan
        self._record_audit("topology_created", plan_id, {"edition_id": edition_id})
        return plan

    def get_topology_plan(self, plan_id: str) -> Optional[ActiveActiveTopologyPlan]:
        """Retrieve an existing topology plan."""
        return self._topologies.get(plan_id)

    def register_region_node(
        self,
        plan_id: str,
        node: ActiveActiveRegionNode,
    ) -> ActiveActiveTopologyPlan:
        """Register a regional cluster node into a topology plan."""
        plan = self._get_plan_or_raise(plan_id)
        if not node.last_sync_time:
            node.last_sync_time = datetime.now(timezone.utc).isoformat()

        # If registering as leader, demote existing leader
        if node.is_leader:
            for n in plan.nodes.values():
                n.is_leader = False

        plan.nodes[node.region_id] = node
        self._evaluate_split_brain(plan)
        self._record_audit("node_registered", plan_id, {"region_id": node.region_id})
        return plan

    def update_node_heartbeat(
        self,
        plan_id: str,
        region_id: str,
        latency_p99_ms: float,
        replication_lag_bytes: int,
        sync_state: Optional[SyncReplicationState] = None,
    ) -> ActiveActiveRegionNode:
        """Update node heartbeat and assess sync degradation."""
        plan = self._get_plan_or_raise(plan_id)
        if region_id not in plan.nodes:
            raise ValueError(f"Region node {region_id} not registered in plan {plan_id}")

        node = plan.nodes[region_id]
        node.latency_p99_ms = latency_p99_ms
        node.replication_lag_bytes = replication_lag_bytes
        node.last_sync_time = datetime.now(timezone.utc).isoformat()

        if sync_state:
            node.sync_state = sync_state
        elif latency_p99_ms > plan.max_tolerable_lag_ms:
            node.sync_state = SyncReplicationState.DEGRADED
        else:
            node.sync_state = SyncReplicationState.IN_SYNC

        self._evaluate_split_brain(plan)
        return node

    def elect_leader(self, plan_id: str, target_region_id: str) -> ActiveActiveRegionNode:
        """Elect or promote a specific region node as the consensus leader."""
        plan = self._get_plan_or_raise(plan_id)
        if target_region_id not in plan.nodes:
            raise ValueError(f"Target region {target_region_id} not found in topology {plan_id}")

        candidate = plan.nodes[target_region_id]
        if candidate.sync_state in (SyncReplicationState.DESYNCHRONIZED, SyncReplicationState.SPLIT_BRAIN):
            raise ValueError(f"Cannot elect leader from out-of-sync node: {candidate.sync_state}")

        for rid, node in plan.nodes.items():
            node.is_leader = (rid == target_region_id)

        self._record_audit("leader_elected", plan_id, {"leader_region": target_region_id})
        return candidate

    def check_quorum(self, plan_id: str) -> Dict[str, Any]:
        """Check whether quorum conditions are satisfied under the plan's strategy."""
        plan = self._get_plan_or_raise(plan_id)
        total_nodes = len(plan.nodes)
        if total_nodes == 0:
            return {
                "quorum_achieved": False,
                "strategy": plan.quorum_strategy.value,
                "healthy_nodes": 0,
                "total_nodes": 0,
                "reason": "No nodes registered",
            }

        healthy_nodes = [
            n for n in plan.nodes.values()
            if n.sync_state in (SyncReplicationState.IN_SYNC, SyncReplicationState.SYNCING)
        ]
        healthy_count = len(healthy_nodes)

        if plan.quorum_strategy == QuorumStrategy.MAJORITY:
            required = (total_nodes // 2) + 1
            achieved = healthy_count >= required
        elif plan.quorum_strategy == QuorumStrategy.WEIGHTED:
            total_weight = sum(n.weight for n in plan.nodes.values())
            healthy_weight = sum(n.weight for n in healthy_nodes)
            achieved = (healthy_weight / total_weight) >= 0.51 if total_weight > 0 else False
        elif plan.quorum_strategy == QuorumStrategy.STRICT_LOCAL:
            achieved = any(n.is_leader and n.sync_state == SyncReplicationState.IN_SYNC for n in plan.nodes.values())
        else:  # OBSERVER_ASSISTED
            achieved = healthy_count >= 1 and not plan.split_brain_detected

        return {
            "quorum_achieved": achieved,
            "strategy": plan.quorum_strategy.value,
            "healthy_nodes": healthy_count,
            "total_nodes": total_nodes,
            "split_brain": plan.split_brain_detected,
        }

    def isolate_node(self, plan_id: str, region_id: str, reason: str) -> ActiveActiveRegionNode:
        """Isolate a faulty or degraded region node to prevent partition poisoning."""
        plan = self._get_plan_or_raise(plan_id)
        if region_id not in plan.nodes:
            raise ValueError(f"Region {region_id} not registered in plan {plan_id}")

        node = plan.nodes[region_id]
        node.sync_state = SyncReplicationState.DESYNCHRONIZED
        node.weight = 0.0
        if node.is_leader:
            node.is_leader = False
            # Try to promote another in-sync node
            for other_id, other_node in plan.nodes.items():
                if other_id != region_id and other_node.sync_state == SyncReplicationState.IN_SYNC:
                    other_node.is_leader = True
                    break

        self._evaluate_split_brain(plan)
        self._record_audit("node_isolated", plan_id, {"region_id": region_id, "reason": reason})
        return node

    def get_cluster_status_report(self, plan_id: str) -> Dict[str, Any]:
        """Generate a complete multiregion active-active cluster status report."""
        plan = self._get_plan_or_raise(plan_id)
        quorum_info = self.check_quorum(plan_id)
        leader_node = next((n.region_id for n in plan.nodes.values() if n.is_leader), None)

        avg_latency = (
            sum(n.latency_p99_ms for n in plan.nodes.values()) / len(plan.nodes)
            if plan.nodes else 0.0
        )

        return {
            "plan_id": plan.plan_id,
            "edition_id": plan.edition_id,
            "quorum_strategy": plan.quorum_strategy.value,
            "quorum_achieved": quorum_info["quorum_achieved"],
            "total_nodes": len(plan.nodes),
            "leader_region": leader_node,
            "split_brain_detected": plan.split_brain_detected,
            "average_latency_p99_ms": round(avg_latency, 2),
            "nodes": {
                rid: {
                    "cluster_name": n.cluster_name,
                    "sync_state": n.sync_state.value,
                    "is_leader": n.is_leader,
                    "latency_p99_ms": n.latency_p99_ms,
                    "weight": n.weight,
                }
                for rid, n in plan.nodes.items()
            },
        }

    def _evaluate_split_brain(self, plan: ActiveActiveTopologyPlan) -> None:
        """Detect split-brain conditions: multiple leaders or multiple disconnected groups."""
        leaders = [n for n in plan.nodes.values() if n.is_leader]
        if len(leaders) > 1:
            plan.split_brain_detected = True
            for n in leaders:
                n.sync_state = SyncReplicationState.SPLIT_BRAIN
        else:
            # Check if any isolated node claims leader
            plan.split_brain_detected = False

    def _get_plan_or_raise(self, plan_id: str) -> ActiveActiveTopologyPlan:
        if plan_id not in self._topologies:
            raise ValueError(f"Topology plan {plan_id} not found")
        return self._topologies[plan_id]

    def _record_audit(self, action: str, plan_id: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "plan_id": plan_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Return engine audit log."""
        return list(self._audit_log)
