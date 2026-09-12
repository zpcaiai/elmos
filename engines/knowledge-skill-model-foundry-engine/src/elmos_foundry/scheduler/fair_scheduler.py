from __future__ import annotations

import collections
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ScheduledItem:
    task_id: str
    tenant_id: str
    cost: int
    payload: Dict[str, Any]


class TenantQueue:
    def __init__(self, tenant_id: str, weight: int = 10):
        self.tenant_id = tenant_id
        self.weight = weight
        self.quantum = weight * 10
        self.deficit = 0
        self.items: collections.deque[ScheduledItem] = collections.deque()
        self.active_count = 0


class DeficitWeightedRoundRobinScheduler:
    """Multi-tenant Deficit Weighted Round-Robin (DWRR) task scheduler."""

    def __init__(self, default_weight: int = 10, max_active_per_tenant: int = 5):
        self.default_weight = default_weight
        self.max_active_per_tenant = max_active_per_tenant
        self._lock = threading.Lock()
        self._tenants: Dict[str, TenantQueue] = {}
        self._active_tenant_order: List[str] = []
        self._current_idx = 0

    def register_tenant(self, tenant_id: str, weight: Optional[int] = None) -> None:
        with self._lock:
            if tenant_id not in self._tenants:
                w = weight if weight is not None else self.default_weight
                tq = TenantQueue(tenant_id, w)
                self._tenants[tenant_id] = tq
                self._active_tenant_order.append(tenant_id)

    def enqueue(self, tenant_id: str, task_id: str, payload: Dict[str, Any], cost: int = 1) -> None:
        with self._lock:
            if tenant_id not in self._tenants:
                self.register_tenant(tenant_id)
            item = ScheduledItem(task_id=task_id, tenant_id=tenant_id, cost=max(1, cost), payload=payload)
            self._tenants[tenant_id].items.append(item)

    def schedule_next(self) -> Optional[ScheduledItem]:
        """Select next task according to DWRR algorithm and tenant concurrency caps."""
        with self._lock:
            if not self._active_tenant_order:
                return None

            rounds = len(self._active_tenant_order)
            for _ in range(rounds):
                if self._current_idx >= len(self._active_tenant_order):
                    self._current_idx = 0

                tenant_id = self._active_tenant_order[self._current_idx]
                tq = self._tenants[tenant_id]

                if not tq.items:
                    tq.deficit = 0
                    self._current_idx += 1
                    continue

                if tq.active_count >= self.max_active_per_tenant:
                    # Concurrency cap reached, skip this turn
                    self._current_idx += 1
                    continue

                tq.deficit += tq.quantum
                head = tq.items[0]

                if head.cost <= tq.deficit:
                    item = tq.items.popleft()
                    tq.deficit -= item.cost
                    tq.active_count += 1
                    # Keep pointer on this tenant if it still has deficit and items
                    if not tq.items or (tq.items and tq.items[0].cost > tq.deficit):
                        self._current_idx += 1
                    return item
                else:
                    self._current_idx += 1

            return None

    def release_task(self, tenant_id: str) -> None:
        with self._lock:
            if tenant_id in self._tenants:
                if self._tenants[tenant_id].active_count > 0:
                    self._tenants[tenant_id].active_count -= 1

    def pending_count(self) -> int:
        with self._lock:
            return sum(len(t.items) for t in self._tenants.values())
