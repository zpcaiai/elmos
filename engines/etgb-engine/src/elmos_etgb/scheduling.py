"""Tenant-isolated fair scheduling with an explicit three-task account cap."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskRequest:
    task_id: str
    tenant_id: str
    account_id: str
    priority: int = 0


class FairScheduler:
    def __init__(self, *, max_active_per_account: int = 3) -> None:
        if max_active_per_account < 1:
            raise ValueError("max_active_per_account must be positive")
        self.max_active_per_account = max_active_per_account
        self._queues: dict[str, deque[TaskRequest]] = defaultdict(deque)
        self._active: dict[str, set[str]] = defaultdict(set)
        self._tasks: dict[str, TaskRequest] = {}

    def enqueue(self, request: TaskRequest) -> dict[str, Any]:
        if request.task_id in self._tasks:
            raise ValueError(f"duplicate task_id: {request.task_id}")
        if not request.tenant_id or not request.account_id:
            raise ValueError("tenant_id and account_id are required")
        self._tasks[request.task_id] = request
        self._queues[request.account_id].append(request)
        return {"status": "QUEUED", "task_id": request.task_id, "tenant_id": request.tenant_id, "account_id": request.account_id}

    def dispatch(self, *, account_id: str | None = None, tenant_id: str | None = None) -> dict[str, Any] | None:
        accounts = [account_id] if account_id else sorted(self._queues)
        candidates: list[TaskRequest] = []
        for account in accounts:
            if account is None or len(self._active[account]) >= self.max_active_per_account:
                continue
            queue = self._queues.get(account)
            if not queue:
                continue
            candidates.extend(task for task in list(queue) if tenant_id is None or task.tenant_id == tenant_id)
        if not candidates:
            return None
        request = min(candidates, key=lambda value: (-value.priority, value.task_id))
        self._queues[request.account_id].remove(request)
        self._active[request.account_id].add(request.task_id)
        return {"status": "DISPATCHED", "task_id": request.task_id, "tenant_id": request.tenant_id, "account_id": request.account_id, "active_count": len(self._active[request.account_id]), "max_active_per_account": self.max_active_per_account}

    def complete(self, *, task_id: str, tenant_id: str) -> dict[str, Any]:
        request = self._tasks.get(task_id)
        if request is None:
            raise KeyError(task_id)
        if request.tenant_id != tenant_id:
            raise PermissionError("tenant mismatch")
        self._active[request.account_id].discard(task_id)
        return {"status": "COMPLETED", "task_id": task_id, "tenant_id": tenant_id, "account_id": request.account_id}

    def snapshot(self) -> dict[str, Any]:
        return {"max_active_per_account": self.max_active_per_account, "queued": {key: [item.task_id for item in value] for key, value in self._queues.items()}, "active": {key: sorted(value) for key, value in self._active.items()}}
