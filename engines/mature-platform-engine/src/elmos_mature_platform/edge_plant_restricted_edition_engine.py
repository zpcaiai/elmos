"""Edge, Plant, and Restricted Network Edition Engine (Batch 38 - Skill 1334).

Coordinates edge node runtimes in industrial plant sites, offline-first data buffering,
industrial protocol gateways (OPC UA, Modbus, Profinet), and network synchronization.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    EdgeConnectivityState,
    EdgeNodeConfig,
    EdgeSyncEvent,
    PlantProtocolSupport,
)


class EdgePlantRestrictedEditionEngine:
    """Manages edge runtime configurations, buffering, and sync for plant networks."""

    def __init__(self) -> None:
        self._nodes: Dict[str, EdgeNodeConfig] = {}
        self._sync_history: Dict[str, List[EdgeSyncEvent]] = {}

    def register_edge_node(self, node: EdgeNodeConfig) -> str:
        """Register a plant edge node runtime."""
        if not node.node_id:
            node.node_id = f"edge-{uuid.uuid4().hex[:8]}"
        if not node.plant_id or not node.site_name:
            raise ValueError("plant_id and site_name are required")

        if not node.last_heartbeat:
            node.last_heartbeat = datetime.now(timezone.utc).isoformat()

        self._nodes[node.node_id] = node
        self._sync_history[node.node_id] = []
        return node.node_id

    def record_heartbeat(self, node_id: str, used_storage_gb: float) -> EdgeNodeConfig:
        """Record operational telemetry heartbeat from an edge node."""
        node = self._nodes.get(node_id)
        if not node:
            raise ValueError(f"Node not found: {node_id}")

        node.last_heartbeat = datetime.now(timezone.utc).isoformat()
        node.used_storage_gb = used_storage_gb
        return node

    def update_connectivity(
        self, node_id: str, state: EdgeConnectivityState
    ) -> EdgeNodeConfig:
        """Update network connectivity posture for an edge node."""
        node = self._nodes.get(node_id)
        if not node:
            raise ValueError(f"Node not found: {node_id}")

        node.connectivity_state = state
        return node

    def quarantine_node(self, node_id: str, reason: str = "") -> EdgeNodeConfig:
        """Quarantine an edge node upon security anomaly or safety breach."""
        node = self._nodes.get(node_id)
        if not node:
            raise ValueError(f"Node not found: {node_id}")

        node.is_quarantined = True
        return node

    def sync_offline_buffer(self, sync_event: EdgeSyncEvent) -> EdgeSyncEvent:
        """Execute buffer synchronization between plant edge node and central control."""
        node = self._nodes.get(sync_event.node_id)
        if not node:
            raise ValueError(f"Node not found: {sync_event.node_id}")
        if node.is_quarantined:
            raise PermissionError(f"Cannot sync quarantined node: {sync_event.node_id}")

        if not sync_event.sync_id:
            sync_event.sync_id = f"sync-{uuid.uuid4().hex[:8]}"
        if not sync_event.synced_at:
            sync_event.synced_at = datetime.now(timezone.utc).isoformat()

        if sync_event.conflict_count == 0 and sync_event.records_synced == sync_event.records_buffered:
            sync_event.status = "success"
        elif sync_event.records_synced > 0:
            sync_event.status = "partial"
        else:
            sync_event.status = "failed"

        self._sync_history[sync_event.node_id].append(sync_event)
        return sync_event

    def get_sync_history(self, node_id: str) -> List[EdgeSyncEvent]:
        """Return synchronization event history for an edge node."""
        if node_id not in self._nodes:
            raise ValueError(f"Node not found: {node_id}")
        return self._sync_history.get(node_id, [])

    def detect_storage_pressure_nodes(self, threshold_pct: float = 85.0) -> List[EdgeNodeConfig]:
        """Return nodes exceeding local disk buffer safety thresholds."""
        alert_nodes = []
        for node in self._nodes.values():
            if node.local_storage_limit_gb > 0:
                utilization = (node.used_storage_gb / node.local_storage_limit_gb) * 100.0
                if utilization >= threshold_pct:
                    alert_nodes.append(node)
        return alert_nodes

    def get_plant_edge_fleet_report(self) -> Dict[str, Any]:
        """Generate comprehensive fleet status across all plant sites."""
        total_nodes = len(self._nodes)
        quarantined = sum(1 for n in self._nodes.values() if n.is_quarantined)
        online = sum(
            1
            for n in self._nodes.values()
            if n.connectivity_state == EdgeConnectivityState.ONLINE and not n.is_quarantined
        )
        airgapped = sum(
            1
            for n in self._nodes.values()
            if n.connectivity_state == EdgeConnectivityState.ISOLATED_AIRGAP
        )

        all_syncs = [s for hist in self._sync_history.values() for s in hist]
        total_synced_records = sum(s.records_synced for s in all_syncs)
        total_conflicts = sum(s.conflict_count for s in all_syncs)

        return {
            "total_edge_nodes": total_nodes,
            "online_nodes": online,
            "quarantined_nodes": quarantined,
            "airgapped_nodes": airgapped,
            "total_synced_records": total_synced_records,
            "total_sync_conflicts": total_conflicts,
        }
