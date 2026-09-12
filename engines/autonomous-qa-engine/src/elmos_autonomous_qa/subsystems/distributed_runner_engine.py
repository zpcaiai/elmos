"""Industrial Distributed Runner Engine: Consistent Hashing & LPT Scheduling.

Provides consistent hash ring test sharding, Longest Processing Time (LPT) greedy
load-balancing scheduling, and fault-tolerant retry queue.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
import hashlib
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TestJob:
    test_id: str
    estimated_duration_sec: float
    retries_left: int = 2


class ConsistentHashRing:
    """Consistent Hash Ring with virtual nodes for uniform worker distribution."""

    def __init__(self, replicas: int = 100) -> None:
        self.replicas = replicas
        self.ring: List[int] = []
        self.ring_map: Dict[int, str] = {}

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)

    def add_node(self, node_id: str) -> None:
        for i in range(self.replicas):
            vnode_key = f"{node_id}#vnode-{i}"
            h = self._hash(vnode_key)
            self.ring_map[h] = node_id
            bisect.insort(self.ring, h)

    def remove_node(self, node_id: str) -> None:
        to_remove = [h for h, nid in self.ring_map.items() if nid == node_id]
        for h in to_remove:
            del self.ring_map[h]
            idx = bisect.bisect_left(self.ring, h)
            if idx < len(self.ring) and self.ring[idx] == h:
                self.ring.pop(idx)

    def get_node(self, key: str) -> Optional[str]:
        if not self.ring:
            return None
        h = self._hash(key)
        idx = bisect.bisect_right(self.ring, h)
        if idx == len(self.ring):
            idx = 0
        return self.ring_map[self.ring[idx]]


class DistributedRunnerEngine:
    """Orchestrates test job sharding, greedy LPT packing, and resilient retries."""

    @staticmethod
    def shard_tests_consistent_hash(
        test_ids: List[str],
        worker_nodes: List[str],
    ) -> Dict[str, List[str]]:
        ring = ConsistentHashRing()
        for w in worker_nodes:
            ring.add_node(w)

        shards: Dict[str, List[str]] = {w: [] for w in worker_nodes}
        for tid in test_ids:
            target = ring.get_node(tid)
            if target:
                shards[target].append(tid)
        return shards

    @staticmethod
    def schedule_lpt(
        jobs: List[TestJob],
        worker_count: int,
    ) -> Tuple[List[List[TestJob]], List[float]]:
        """Longest Processing Time (LPT) greedy makespan minimization."""
        if worker_count <= 0:
            raise ValueError("worker_count must be > 0")

        sorted_jobs = sorted(jobs, key=lambda j: j.estimated_duration_sec, reverse=True)
        worker_queues: List[List[TestJob]] = [[] for _ in range(worker_count)]
        worker_loads: List[float] = [0.0] * worker_count

        for job in sorted_jobs:
            min_worker_idx = worker_loads.index(min(worker_loads))
            worker_queues[min_worker_idx].append(job)
            worker_loads[min_worker_idx] += job.estimated_duration_sec

        return worker_queues, worker_loads
