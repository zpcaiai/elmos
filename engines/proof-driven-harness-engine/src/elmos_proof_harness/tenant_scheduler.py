"""Multi-Tenant Fair Scheduler, Concurrency Slot Leasing, and Noisy-Neighbor Defense.

Enforces per-tenant concurrency quotas, burst buffers, priority preemption,
anti-starvation priority aging, and cluster backpressure.
"""

from __future__ import annotations

import heapq
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Mapping

logger = logging.getLogger("elmos_proof_harness.tenant_scheduler")


class PriorityTier(IntEnum):
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    BATCH = 4


class TenantQuotaExceededError(Exception):
    def __init__(self, tenant_id: str, active: int, max_slots: int, retry_after_seconds: float) -> None:
        super().__init__(
            f"tenant '{tenant_id}' exceeded concurrency quota: {active}/{max_slots} active slots. "
            f"Retry after {retry_after_seconds:.2f}s."
        )
        self.tenant_id = tenant_id
        self.active = active
        self.max_slots = max_slots
        self.retry_after_seconds = retry_after_seconds


@dataclass(order=True)
class QueuedTask:
    priority: int
    enqueued_at: float
    task_id: str = field(compare=False)
    tenant_id: str = field(compare=False)
    payload: Mapping[str, Any] = field(compare=False, default_factory=dict)


class TenantConcurrencyPool:
    """Tracks active concurrent slots per tenant and overall cluster capacity."""

    def __init__(
        self,
        total_cluster_slots: int = 100,
        default_tenant_slots: int = 10,
        tenant_burst_allowance: int = 5,
    ) -> None:
        self.total_cluster_slots = total_cluster_slots
        self.default_tenant_slots = default_tenant_slots
        self.tenant_burst_allowance = tenant_burst_allowance

        self._active_per_tenant: dict[str, int] = {}
        self._total_active: int = 0
        self._custom_tenant_limits: dict[str, int] = {}

    def set_tenant_limit(self, tenant_id: str, limit: int) -> None:
        self._custom_tenant_limits[tenant_id] = limit

    def get_tenant_limit(self, tenant_id: str) -> int:
        return self._custom_tenant_limits.get(tenant_id, self.default_tenant_slots)

    @property
    def total_active(self) -> int:
        return self._total_active

    @property
    def saturation_ratio(self) -> float:
        if self.total_cluster_slots == 0:
            return 1.0
        return self._total_active / self.total_cluster_slots

    def try_acquire_slot(self, tenant_id: str, allow_burst: bool = True) -> bool:
        limit = self.get_tenant_limit(tenant_id)
        max_allowed = limit + (self.tenant_burst_allowance if allow_burst else 0)

        current = self._active_per_tenant.get(tenant_id, 0)
        if current >= max_allowed:
            return False

        if self._total_active >= self.total_cluster_slots:
            return False

        self._active_per_tenant[tenant_id] = current + 1
        self._total_active += 1
        return True

    def release_slot(self, tenant_id: str) -> None:
        current = self._active_per_tenant.get(tenant_id, 0)
        if current > 0:
            self._active_per_tenant[tenant_id] = current - 1
            self._total_active = max(0, self._total_active - 1)


class PriorityPreemptionQueue:
    """Priority heap queue with anti-starvation aging and backpressure load shedding."""

    def __init__(
        self,
        aging_threshold_seconds: float = 30.0,
        backpressure_threshold: float = 0.85,
    ) -> None:
        self.aging_threshold = aging_threshold_seconds
        self.backpressure_threshold = backpressure_threshold
        self._heap: list[QueuedTask] = []

    def __len__(self) -> int:
        return len(self._heap)

    def enqueue(
        self,
        task_id: str,
        tenant_id: str,
        priority: PriorityTier = PriorityTier.NORMAL,
        payload: Mapping[str, Any] | None = None,
        cluster_saturation: float = 0.0,
    ) -> bool:
        # Load-shed BATCH tasks under heavy saturation
        if cluster_saturation >= self.backpressure_threshold and priority >= PriorityTier.BATCH:
            logger.warning(
                f"shedding batch task {task_id} for tenant {tenant_id} due to backpressure ({cluster_saturation:.2%})"
            )
            return False

        task = QueuedTask(
            priority=int(priority),
            enqueued_at=time.time(),
            task_id=task_id,
            tenant_id=tenant_id,
            payload=payload or {},
        )
        heapq.heappush(self._heap, task)
        return True

    def dequeue(self) -> QueuedTask | None:
        if not self._heap:
            return None

        # Age tasks to prevent lower priority starvation
        now = time.time()
        for task in self._heap:
            if now - task.enqueued_at > self.aging_threshold and task.priority > PriorityTier.CRITICAL:
                task.priority -= 1  # Boost priority tier
        heapq.heapify(self._heap)

        return heapq.heappop(self._heap)


class TenantFairScheduler:
    """Coordinates multi-tenant slot admission, fair queuing, and backpressure."""

    def __init__(
        self,
        concurrency_pool: TenantConcurrencyPool | None = None,
        queue: PriorityPreemptionQueue | None = None,
    ) -> None:
        self.pool = concurrency_pool or TenantConcurrencyPool()
        self.queue = queue or PriorityPreemptionQueue()

    def submit_or_queue(
        self,
        task_id: str,
        tenant_id: str,
        priority: PriorityTier = PriorityTier.NORMAL,
        payload: Mapping[str, Any] | None = None,
    ) -> str:
        # Check immediate execution slot
        if self.pool.try_acquire_slot(tenant_id):
            return "EXECUTING"

        # If slot full, enqueue
        enqueued = self.queue.enqueue(
            task_id=task_id,
            tenant_id=tenant_id,
            priority=priority,
            payload=payload,
            cluster_saturation=self.pool.saturation_ratio,
        )
        if not enqueued:
            retry_after = 2.0 * (1.0 + self.pool.saturation_ratio)
            raise TenantQuotaExceededError(
                tenant_id,
                active=self.pool._active_per_tenant.get(tenant_id, 0),
                max_slots=self.pool.get_tenant_limit(tenant_id),
                retry_after_seconds=retry_after,
            )

        return "QUEUED"

    def complete_task(self, tenant_id: str) -> QueuedTask | None:
        self.pool.release_slot(tenant_id)
        next_task = self.queue.dequeue()
        if next_task:
            if self.pool.try_acquire_slot(next_task.tenant_id):
                return next_task
            else:
                # Re-queue if tenant still has no slot
                self.queue.enqueue(
                    next_task.task_id,
                    next_task.tenant_id,
                    priority=PriorityTier(next_task.priority),
                    payload=next_task.payload,
                    cluster_saturation=self.pool.saturation_ratio,
                )
        return None
