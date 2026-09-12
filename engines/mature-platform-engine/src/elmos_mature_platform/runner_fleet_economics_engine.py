"""Runner Fleet Economics Engine (Batch 44 - Skill 1460).

Analyzes runner compute capacity, node instance tiers (On-Demand, Spot, Reserved),
active busy execution vs idle standby waste, autoscaling efficiency, and total fleet economics.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    RunnerFleetEconomicsSummary,
    RunnerFleetNode,
    RunnerInstanceTier,
)


class RunnerFleetEconomicsEngine:
    """FinOps compute fleet analyzer and runner capacity economics engine."""

    def __init__(self) -> None:
        self._nodes: Dict[str, RunnerFleetNode] = {}

    def register_node(self, node: RunnerFleetNode) -> str:
        """Register a compute runner node in the fleet."""
        if node.hourly_rate_usd < 0:
            raise ValueError("hourly_rate_usd cannot be negative")

        if not node.node_id:
            node.node_id = f"node-{uuid.uuid4().hex[:8]}"

        if not node.provisioned_at:
            node.provisioned_at = datetime.now(timezone.utc).isoformat()

        self._nodes[node.node_id] = node
        return node.node_id

    def record_node_activity(
        self, node_id: str, busy_hours: float, idle_hours: float
    ) -> RunnerFleetNode:
        """Record busy execution hours and idle standby hours for a runner node."""
        if busy_hours < 0 or idle_hours < 0:
            raise ValueError("hours cannot be negative")

        node = self._nodes.get(node_id)
        if not node:
            raise ValueError(f"Runner node not found: {node_id}")

        if not node.is_active:
            raise ValueError(f"Runner node {node_id} is decommissioned; cannot record activity")

        node.active_busy_hours += busy_hours
        node.idle_hours += idle_hours
        node.total_running_hours = node.active_busy_hours + node.idle_hours
        return node

    def decommission_node(self, node_id: str) -> RunnerFleetNode:
        """Decommission a runner node from active fleet duty."""
        node = self._nodes.get(node_id)
        if not node:
            raise ValueError(f"Runner node not found: {node_id}")

        node.is_active = False
        return node

    def get_node(self, node_id: str) -> Optional[RunnerFleetNode]:
        """Retrieve node details."""
        return self._nodes.get(node_id)

    def compute_node_economics(self, node_id: str) -> Dict[str, float]:
        """Calculate spend, idle waste spend, and utilization for a specific runner node."""
        node = self._nodes.get(node_id)
        if not node:
            raise ValueError(f"Runner node not found: {node_id}")

        total_spend = node.total_running_hours * node.hourly_rate_usd
        idle_spend = node.idle_hours * node.hourly_rate_usd
        utilization_pct = (
            (node.active_busy_hours / node.total_running_hours * 100.0)
            if node.total_running_hours > 0
            else 0.0
        )

        return {
            "total_running_hours": round(node.total_running_hours, 2),
            "active_busy_hours": round(node.active_busy_hours, 2),
            "idle_hours": round(node.idle_hours, 2),
            "total_spend_usd": round(total_spend, 2),
            "idle_spend_usd": round(idle_spend, 2),
            "utilization_pct": round(utilization_pct, 2),
        }

    def compute_fleet_economics(self) -> RunnerFleetEconomicsSummary:
        """Calculate macro fleet-wide economics, idle waste, and tier distributions."""
        total_spend = sum(n.total_running_hours * n.hourly_rate_usd for n in self._nodes.values())
        idle_spend = sum(n.idle_hours * n.hourly_rate_usd for n in self._nodes.values())
        total_busy = sum(n.active_busy_hours for n in self._nodes.values())
        total_hours = sum(n.total_running_hours for n in self._nodes.values())

        fleet_util = (total_busy / total_hours * 100.0) if total_hours > 0 else 0.0

        by_tier: Dict[str, float] = {tier.value: 0.0 for tier in RunnerInstanceTier}
        for n in self._nodes.values():
            spend = n.total_running_hours * n.hourly_rate_usd
            t_key = n.tier.value
            by_tier[t_key] = round(by_tier.get(t_key, 0.0) + spend, 2)

        return RunnerFleetEconomicsSummary(
            total_nodes_count=len(self._nodes),
            active_nodes_count=sum(1 for n in self._nodes.values() if n.is_active),
            total_fleet_spend_usd=round(total_spend, 2),
            waste_idle_spend_usd=round(idle_spend, 2),
            fleet_utilization_pct=round(fleet_util, 2),
            by_tier=by_tier,
        )

    def get_fleet_report(self) -> Dict[str, Any]:
        """Generate comprehensive runner fleet economics governance report."""
        summary = self.compute_fleet_economics()
        return {
            "total_nodes": summary.total_nodes_count,
            "active_nodes": summary.active_nodes_count,
            "decommissioned_nodes": summary.total_nodes_count - summary.active_nodes_count,
            "total_fleet_spend_usd": summary.total_fleet_spend_usd,
            "waste_idle_spend_usd": summary.waste_idle_spend_usd,
            "fleet_utilization_pct": summary.fleet_utilization_pct,
            "spend_by_tier": summary.by_tier,
        }
