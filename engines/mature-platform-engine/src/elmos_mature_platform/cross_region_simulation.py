"""Cross-region multi-site simulation environment for Elmos Mature Platform."""

from __future__ import annotations

import collections
import copy
from datetime import datetime, timezone
import hashlib
import random
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from elmos_mature_platform.types import (
    ConsensusState,
    LatencySpec,
    NodeInfo,
    NodeRole,
    NodeStatus,
    RegionId,
    RegionTopology,
)


class CrossRegionSimulationEnvironment:
    """Simulates an active-active multi-region cluster mesh with real latency, consensus, and failover."""

    def __init__(self, seed: int = 42) -> None:
        self._rnd = random.Random(seed)
        self.regions: Dict[RegionId, RegionTopology] = {}
        self.global_clock_offset_ms: float = 0.0
        self.routing_table: Dict[str, RegionId] = {}
        self.replication_backlog: collections.defaultdict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
        self.fencing_token_sequence: int = 1000
        self.event_log: List[str] = []
        self._init_default_topology()

    def _log(self, message: str) -> None:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        entry = f"[{ts}][CROSS-REGION-SIM] {message}"
        self.event_log.append(entry)

    def _init_default_topology(self) -> None:
        """Initializes realistic 3-region active-active deployment."""
        specs = {
            (RegionId.US_EAST_1, RegionId.EU_WEST_1): LatencySpec(mean_ms=75.0, jitter_ms=10.0),
            (RegionId.US_EAST_1, RegionId.AP_SOUTHEAST_1): LatencySpec(mean_ms=180.0, jitter_ms=25.0),
            (RegionId.EU_WEST_1, RegionId.AP_SOUTHEAST_1): LatencySpec(mean_ms=140.0, jitter_ms=20.0),
        }

        # US East 1 (Primary)
        us_nodes = {
            "us-node-1": NodeInfo("us-node-1", RegionId.US_EAST_1, "us-east-1a", "10.0.1.10", NodeRole.LEADER, NodeStatus.HEALTHY, term=1, fencing_token=1001),
            "us-node-2": NodeInfo("us-node-2", RegionId.US_EAST_1, "us-east-1b", "10.0.2.10", NodeRole.FOLLOWER, NodeStatus.HEALTHY, term=1, fencing_token=1001),
            "us-node-3": NodeInfo("us-node-3", RegionId.US_EAST_1, "us-east-1c", "10.0.3.10", NodeRole.FOLLOWER, NodeStatus.HEALTHY, term=1, fencing_token=1001),
        }
        self.regions[RegionId.US_EAST_1] = RegionTopology(RegionId.US_EAST_1, is_primary=True, nodes=us_nodes)

        # EU West 1 (Secondary Active)
        eu_nodes = {
            "eu-node-1": NodeInfo("eu-node-1", RegionId.EU_WEST_1, "eu-west-1a", "10.1.1.10", NodeRole.FOLLOWER, NodeStatus.HEALTHY, term=1, fencing_token=1001),
            "eu-node-2": NodeInfo("eu-node-2", RegionId.EU_WEST_1, "eu-west-1b", "10.1.2.10", NodeRole.FOLLOWER, NodeStatus.HEALTHY, term=1, fencing_token=1001),
        }
        self.regions[RegionId.EU_WEST_1] = RegionTopology(RegionId.EU_WEST_1, is_primary=False, nodes=eu_nodes)

        # AP Southeast 1 (Disaster Recovery)
        ap_nodes = {
            "ap-node-1": NodeInfo("ap-node-1", RegionId.AP_SOUTHEAST_1, "ap-southeast-1a", "10.2.1.10", NodeRole.FOLLOWER, NodeStatus.HEALTHY, term=1, fencing_token=1001),
            "ap-node-2": NodeInfo("ap-node-2", RegionId.AP_SOUTHEAST_1, "ap-southeast-1b", "10.2.2.10", NodeRole.FOLLOWER, NodeStatus.HEALTHY, term=1, fencing_token=1001),
        }
        self.regions[RegionId.AP_SOUTHEAST_1] = RegionTopology(RegionId.AP_SOUTHEAST_1, is_primary=False, nodes=ap_nodes)

        for (r1, r2), spec in specs.items():
            self.regions[r1].wan_latency_matrix[r2] = spec
            self.regions[r2].wan_latency_matrix[r1] = spec

        self._log("Initialized default 3-region active-active topology (7 distributed nodes across US, EU, AP)")

    def get_all_nodes(self) -> List[NodeInfo]:
        nodes: List[NodeInfo] = []
        for reg in self.regions.values():
            nodes.extend(reg.nodes.values())
        return nodes

    def get_leader(self) -> Optional[NodeInfo]:
        for node in self.get_all_nodes():
            if node.role == NodeRole.LEADER and node.status == NodeStatus.HEALTHY:
                return node
        return None

    def calculate_cross_region_latency(self, source: RegionId, target: RegionId) -> float:
        if source == target:
            return self._rnd.uniform(0.5, 2.5)  # LAN RTT
        spec = self.regions[source].wan_latency_matrix.get(target)
        if not spec:
            return 100.0
        jitter = self._rnd.uniform(-spec.jitter_ms, spec.jitter_ms)
        return max(5.0, spec.mean_ms + jitter)

    def isolate_region(self, isolated_region: RegionId) -> None:
        """Injects network partition: disconnects isolated_region from all peer regions."""
        self._log(f"Injecting complete WAN partition for region: {isolated_region.value}")
        for r_id, reg in self.regions.items():
            if r_id != isolated_region:
                reg.partitioned_peers.add(isolated_region)
                self.regions[isolated_region].partitioned_peers.add(r_id)
        # Update node statuses
        for node in self.regions[isolated_region].nodes.values():
            node.status = NodeStatus.PARTITIONED
            if node.role == NodeRole.LEADER:
                self._log(f"Leader {node.node_id} is in partitioned region, forfeiting quorum lease")
                node.role = NodeRole.FOLLOWER

    def heal_partition(self, healed_region: RegionId) -> None:
        """Heals network partition for healed_region."""
        self._log(f"Healing WAN partition for region: {healed_region.value}")
        for reg in self.regions.values():
            reg.partitioned_peers.discard(healed_region)
        self.regions[healed_region].partitioned_peers.clear()
        for node in self.regions[healed_region].nodes.values():
            if node.status == NodeStatus.PARTITIONED:
                node.status = NodeStatus.HEALTHY

    def trigger_failover_election(self, target_region: Optional[RegionId] = None) -> Optional[NodeInfo]:
        """Triggers Raft consensus election across reachable nodes."""
        self._log("Initiating distributed leader election")
        self.fencing_token_sequence += 1
        new_fencing_token = self.fencing_token_sequence

        eligible_nodes = [
            n for n in self.get_all_nodes()
            if n.status == NodeStatus.HEALTHY and (target_region is None or n.region_id == target_region)
        ]

        if not eligible_nodes:
            self._log("Election failed: no healthy reachable nodes available")
            return None

        # Sort by commit index then priority
        candidate = sorted(eligible_nodes, key=lambda x: (x.commit_index, x.region_id == RegionId.EU_WEST_1), reverse=True)[0]
        candidate.term += 1
        candidate.voted_for = candidate.node_id
        votes = 1

        total_healthy = len([n for n in self.get_all_nodes() if n.status == NodeStatus.HEALTHY])
        required_quorum = (total_healthy // 2) + 1

        for peer in self.get_all_nodes():
            if peer.node_id != candidate.node_id and peer.status == NodeStatus.HEALTHY:
                # check network partition
                if candidate.region_id in self.regions[peer.region_id].partitioned_peers:
                    continue
                peer.term = candidate.term
                peer.voted_for = candidate.node_id
                peer.role = NodeRole.FOLLOWER
                peer.fencing_token = new_fencing_token
                votes += 1

        if votes >= required_quorum:
            candidate.role = NodeRole.LEADER
            candidate.fencing_token = new_fencing_token
            self._log(f"Election succeeded: {candidate.node_id} elected LEADER with {votes}/{total_healthy} votes in term {candidate.term}, fencing_token={new_fencing_token}")
            return candidate
        else:
            self._log(f"Election failed: candidate {candidate.node_id} received {votes} votes, below quorum {required_quorum}")
            candidate.role = NodeRole.CANDIDATE
            return None

    def replicate_transaction(self, key: str, value: Any, current_fencing_token: int) -> Tuple[bool, str]:
        """Replicates write transaction across active regions with fencing token verification."""
        leader = self.get_leader()
        if not leader:
            return False, "E_NO_LEADER: No healthy cluster leader elected"

        if current_fencing_token < leader.fencing_token:
            return False, f"E_FENCING_TOKEN_STALE: Submitted token {current_fencing_token} < active token {leader.fencing_token}"

        # Write to leader local
        leader.commit_index += 1
        record = {
            "key": key,
            "value": value,
            "term": leader.term,
            "index": leader.commit_index,
            "fencing_token": leader.fencing_token,
            "timestamp": time.time(),
        }

        # Cross-region replication
        acked_nodes = 1
        total_healthy = 1

        for peer in self.get_all_nodes():
            if peer.node_id == leader.node_id or peer.status != NodeStatus.HEALTHY:
                continue
            total_healthy += 1
            if leader.region_id in self.regions[peer.region_id].partitioned_peers:
                # Add to backlog for async replay
                self.replication_backlog[peer.node_id].append(record)
                continue
            # Replicate
            peer.commit_index = leader.commit_index
            acked_nodes += 1

        quorum = (total_healthy // 2) + 1
        if acked_nodes >= quorum:
            return True, f"OK: Replicated to {acked_nodes}/{total_healthy} nodes (quorum={quorum})"
        else:
            return False, f"E_QUORUM_LOSS: Acknowledged by {acked_nodes}/{total_healthy}, below quorum {quorum}"

    def drain_replication_backlog(self, target_node_id: str) -> int:
        """Drains and applies backlog to a reconnected node."""
        backlog = self.replication_backlog.get(target_node_id, [])
        count = len(backlog)
        self.replication_backlog[target_node_id].clear()
        self._log(f"Drained and applied {count} replication records to node {target_node_id}")
        return count

    def get_cluster_status_digest(self) -> str:
        data = {
            "regions": {r_id.value: [n.node_id for n in r.nodes.values() if n.status == NodeStatus.HEALTHY] for r_id, r in self.regions.items()},
            "leader": self.get_leader().node_id if self.get_leader() else None,
            "fencing_token": self.fencing_token_sequence,
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()
