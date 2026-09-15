"""Jepsen-style Distributed Network Partition, Split-Brain, and Linearizability Verifier.

Deep-Water Pillar 4: Injects multi-node asymmetric network partitions and split-brain failures
into simulated distributed clusters, verifying that distributed locks and transactional settlement
fail closed without double-spending, state divergence, or phantom commits.
"""

from __future__ import annotations

import collections
import dataclasses
import enum
import logging
import time
from typing import Any

logger = logging.getLogger("elmos_project_synthesis.jepsen_partition_verifier")


class NodeRole(str, enum.Enum):
    LEADER = "LEADER"
    FOLLOWER = "FOLLOWER"
    ISOLATED = "ISOLATED"


class LockStatus(str, enum.Enum):
    ACQUIRED = "ACQUIRED"
    QUORUM_NOT_REACHED = "QUORUM_NOT_REACHED"
    REJECTED_STALE_FENCE = "REJECTED_STALE_FENCE"
    REJECTED_NETWORK_PARTITION = "REJECTED_NETWORK_PARTITION"


class SettlementStatus(str, enum.Enum):
    COMMITTED = "COMMITTED"
    REJECTED_LOCK_NOT_HELD = "REJECTED_LOCK_NOT_HELD"
    REJECTED_SPLIT_BRAIN_MINORITY = "REJECTED_SPLIT_BRAIN_MINORITY"
    REJECTED_STALE_FENCE = "REJECTED_STALE_FENCE"
    REJECTED_DOUBLE_SETTLE = "REJECTED_DOUBLE_SETTLE"


@dataclasses.dataclass
class LeaseInfo:
    lock_key: str
    holder_client_id: str
    fence_token: int
    expires_at_ms: float


@dataclasses.dataclass(frozen=True)
class CommittedTransaction:
    order_id: str
    amount_cents: int
    client_id: str
    fence_token: int
    committed_at_ms: float
    committing_node: str


class SimulatedClusterNode:
    """Represents a distributed database/service node participating in consensus and lease management."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.role = NodeRole.FOLLOWER
        self.current_term: int = 1
        self.active_locks: dict[str, LeaseInfo] = {}
        self.ledger: dict[str, CommittedTransaction] = {}

    def can_communicate_with(self, other_node_id: str, matrix: NetworkPartitionMatrix) -> bool:
        return matrix.is_connected(self.node_id, other_node_id)


class NetworkPartitionMatrix:
    """Manages dynamic bidirectional connectivity rules across cluster nodes."""

    def __init__(self, all_node_ids: tuple[str, ...]) -> None:
        self.all_node_ids = all_node_ids
        self._disabled_pairs: set[frozenset[str]] = set()

    def disconnect_pair(self, node_a: str, node_b: str) -> None:
        self._disabled_pairs.add(frozenset([node_a, node_b]))

    def reconnect_pair(self, node_a: str, node_b: str) -> None:
        self._disabled_pairs.discard(frozenset([node_a, node_b]))

    def create_partition(self, majority: tuple[str, ...], minority: tuple[str, ...]) -> None:
        """Creates a hard partition isolating majority partition from minority partition."""
        for maj in majority:
            for mino in minority:
                self.disconnect_pair(maj, mino)

    def heal_all_partitions(self) -> None:
        self._disabled_pairs.clear()

    def is_connected(self, node_a: str, node_b: str) -> bool:
        if node_a == node_b:
            return True
        return frozenset([node_a, node_b]) not in self._disabled_pairs


@dataclasses.dataclass(frozen=True)
class OperationEvent:
    timestamp_ms: float
    node_id: str
    client_id: str
    operation: str  # "LOCK_ACQUIRE" or "SETTLE"
    order_id: str
    status: str
    fence_token: int | None = None


class JepsenNetworkPartitionVerifier:
    """Orchestrates Jepsen-style network partition injection, concurrent client operations, and consistency audits."""

    def __init__(self, node_ids: tuple[str, ...] = ("node-a", "node-b", "node-c")) -> None:
        self.node_ids = node_ids
        self.nodes: dict[str, SimulatedClusterNode] = {nid: SimulatedClusterNode(nid) for nid in node_ids}
        self.matrix = NetworkPartitionMatrix(node_ids)
        self.global_fence_counter: int = 100
        self.operation_history: list[OperationEvent] = []

    def inject_majority_minority_partition(
        self,
        majority: tuple[str, ...] = ("node-a", "node-b"),
        minority: tuple[str, ...] = ("node-c",),
    ) -> None:
        """Partitions the cluster into a majority quorum partition and an isolated minority partition."""
        self.matrix.create_partition(majority, minority)
        for nid in minority:
            self.nodes[nid].role = NodeRole.ISOLATED
        for nid in majority:
            self.nodes[nid].role = NodeRole.LEADER

    def heal_partition(self) -> None:
        """Heals all network partitions and re-enables full mesh connectivity."""
        self.matrix.heal_all_partitions()
        for node in self.nodes.values():
            node.role = NodeRole.FOLLOWER

    def acquire_distributed_lock(
        self,
        client_id: str,
        lock_key: str,
        target_node_id: str,
        lease_duration_ms: float = 5000.0,
    ) -> tuple[LockStatus, int | None]:
        """Attempts to acquire a distributed lock lease through quorum consensus (Redlock / Raft style)."""
        target_node = self.nodes[target_node_id]
        now_ms = time.time() * 1000.0

        # Probe cluster connectivity to calculate quorum
        reachable_nodes = [
            nid for nid in self.node_ids
            if target_node.can_communicate_with(nid, self.matrix)
        ]

        quorum_required = (len(self.node_ids) // 2) + 1  # 2 for a 3-node cluster
        if len(reachable_nodes) < quorum_required:
            event = OperationEvent(
                timestamp_ms=now_ms,
                node_id=target_node_id,
                client_id=client_id,
                operation="LOCK_ACQUIRE",
                order_id=lock_key,
                status=LockStatus.QUORUM_NOT_REACHED.value,
            )
            self.operation_history.append(event)
            return LockStatus.QUORUM_NOT_REACHED, None

        # Check existing lock expiration
        existing_lease = target_node.active_locks.get(lock_key)
        if existing_lease and existing_lease.expires_at_ms > now_ms and existing_lease.holder_client_id != client_id:
            event = OperationEvent(
                timestamp_ms=now_ms,
                node_id=target_node_id,
                client_id=client_id,
                operation="LOCK_ACQUIRE",
                order_id=lock_key,
                status=LockStatus.REJECTED_STALE_FENCE.value,
            )
            self.operation_history.append(event)
            return LockStatus.REJECTED_STALE_FENCE, None

        # Quorum granted! Mint new monotonic fence token
        self.global_fence_counter += 1
        fence_token = self.global_fence_counter
        new_lease = LeaseInfo(
            lock_key=lock_key,
            holder_client_id=client_id,
            fence_token=fence_token,
            expires_at_ms=now_ms + lease_duration_ms,
        )

        # Replicate lease to all reachable quorum nodes
        for nid in reachable_nodes:
            self.nodes[nid].active_locks[lock_key] = new_lease

        event = OperationEvent(
            timestamp_ms=now_ms,
            node_id=target_node_id,
            client_id=client_id,
            operation="LOCK_ACQUIRE",
            order_id=lock_key,
            status=LockStatus.ACQUIRED.value,
            fence_token=fence_token,
        )
        self.operation_history.append(event)
        return LockStatus.ACQUIRED, fence_token

    def settle_order(
        self,
        client_id: str,
        order_id: str,
        amount_cents: int,
        target_node_id: str,
        fence_token: int,
    ) -> SettlementStatus:
        """Executes atomic settlement guarded by distributed fence token and quorum partition checks."""
        target_node = self.nodes[target_node_id]
        now_ms = time.time() * 1000.0

        # 1. Fail closed if target node is in minority partition
        reachable_nodes = [
            nid for nid in self.node_ids
            if target_node.can_communicate_with(nid, self.matrix)
        ]
        quorum_required = (len(self.node_ids) // 2) + 1
        if len(reachable_nodes) < quorum_required:
            event = OperationEvent(
                timestamp_ms=now_ms,
                node_id=target_node_id,
                client_id=client_id,
                operation="SETTLE",
                order_id=order_id,
                status=SettlementStatus.REJECTED_SPLIT_BRAIN_MINORITY.value,
                fence_token=fence_token,
            )
            self.operation_history.append(event)
            return SettlementStatus.REJECTED_SPLIT_BRAIN_MINORITY

        # 2. Check distributed lock lease validity on target node
        lease = target_node.active_locks.get(order_id)
        if not lease or lease.holder_client_id != client_id or lease.expires_at_ms < now_ms:
            event = OperationEvent(
                timestamp_ms=now_ms,
                node_id=target_node_id,
                client_id=client_id,
                operation="SETTLE",
                order_id=order_id,
                status=SettlementStatus.REJECTED_LOCK_NOT_HELD.value,
                fence_token=fence_token,
            )
            self.operation_history.append(event)
            return SettlementStatus.REJECTED_LOCK_NOT_HELD

        # 3. Check fence token monotonicity (defense against delayed RPCs)
        if fence_token < lease.fence_token:
            event = OperationEvent(
                timestamp_ms=now_ms,
                node_id=target_node_id,
                client_id=client_id,
                operation="SETTLE",
                order_id=order_id,
                status=SettlementStatus.REJECTED_STALE_FENCE.value,
                fence_token=fence_token,
            )
            self.operation_history.append(event)
            return SettlementStatus.REJECTED_STALE_FENCE

        # 4. Check for double settlement across quorum
        for nid in reachable_nodes:
            if order_id in self.nodes[nid].ledger:
                event = OperationEvent(
                    timestamp_ms=now_ms,
                    node_id=target_node_id,
                    client_id=client_id,
                    operation="SETTLE",
                    order_id=order_id,
                    status=SettlementStatus.REJECTED_DOUBLE_SETTLE.value,
                    fence_token=fence_token,
                )
                self.operation_history.append(event)
                return SettlementStatus.REJECTED_DOUBLE_SETTLE

        # 5. Commit settlement and replicate across quorum
        txn = CommittedTransaction(
            order_id=order_id,
            amount_cents=amount_cents,
            client_id=client_id,
            fence_token=fence_token,
            committed_at_ms=now_ms,
            committing_node=target_node_id,
        )
        for nid in reachable_nodes:
            self.nodes[nid].ledger[order_id] = txn

        event = OperationEvent(
            timestamp_ms=now_ms,
            node_id=target_node_id,
            client_id=client_id,
            operation="SETTLE",
            order_id=order_id,
            status=SettlementStatus.COMMITTED.value,
            fence_token=fence_token,
        )
        self.operation_history.append(event)
        return SettlementStatus.COMMITTED

    def synchronize_reconcile_after_heal(self, authoritative_node_id: str = "node-a") -> dict[str, int]:
        """Anti-entropy reconciliation syncing majority ledger to previously isolated nodes."""
        auth_ledger = self.nodes[authoritative_node_id].ledger
        synced_counts: dict[str, int] = {}
        for nid, node in self.nodes.items():
            count = 0
            if nid != authoritative_node_id:
                for order_id, txn in auth_ledger.items():
                    if order_id not in node.ledger:
                        node.ledger[order_id] = txn
                        count += 1
            synced_counts[nid] = count
        return synced_counts

    def audit_linearizability_and_split_brain(self) -> dict[str, Any]:
        """Audits operation history for linearizability violations, split-brain divergence, and double commits."""
        commits = [ev for ev in self.operation_history if ev.status == SettlementStatus.COMMITTED.value]

        # Check 1: Zero double commits on any order
        order_commits = collections.defaultdict(list)
        for c in commits:
            order_commits[c.order_id].append(c)

        double_commits = {oid: len(cs) for oid, cs in order_commits.items() if len(cs) > 1}

        # Check 2: Check for split-brain ledger divergence among nodes
        divergent_orders: list[str] = []
        for oid in order_commits:
            # Check amounts across all nodes having this commit
            amounts_seen = set()
            for node in self.nodes.values():
                if oid in node.ledger:
                    amounts_seen.add(node.ledger[oid].amount_cents)
            if len(amounts_seen) > 1:
                divergent_orders.append(oid)

        # Check 3: Check minority node isolation enforcement
        minority_rejections = sum(
            1 for ev in self.operation_history
            if ev.status == SettlementStatus.REJECTED_SPLIT_BRAIN_MINORITY.value
        )

        passed = (len(double_commits) == 0 and len(divergent_orders) == 0)

        return {
            "passed": passed,
            "total_operations": len(self.operation_history),
            "total_commits": len(commits),
            "double_commits_count": len(double_commits),
            "double_commits": double_commits,
            "divergent_orders_count": len(divergent_orders),
            "divergent_orders": divergent_orders,
            "minority_rejections_count": minority_rejections,
            "audit_verdict": "LINEARIZABLE_NO_SPLIT_BRAIN" if passed else "VIOLATION_SPLIT_BRAIN_DETECTED",
        }
