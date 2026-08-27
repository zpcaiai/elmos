"""Runtime-plane worker registry, admission control and cursor streams."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Iterable

from .errors import ContractViolation, LeaseLost
from .ledger import EventLedger
from .models import Event, Identity, new_id


@dataclass(frozen=True, slots=True)
class WorkerLease:
    worker_id: str
    region: str
    capabilities: frozenset[str]
    fencing_token: str
    expires_at: float
    draining: bool = False


class WorkerRegistry:
    def __init__(self, *, lease_seconds: float = 30.0) -> None:
        self.lease_seconds = lease_seconds
        self._workers: dict[str, WorkerLease] = {}
        self._lock = threading.RLock()

    def register(self, worker_id: str, region: str, capabilities: Iterable[str], *, now: float | None = None) -> WorkerLease:
        if not worker_id or not region:
            raise ContractViolation("worker identity and region are required")
        now = time.time() if now is None else now
        lease = WorkerLease(worker_id, region, frozenset(capabilities), new_id(), now + self.lease_seconds)
        with self._lock:
            self._workers[worker_id] = lease
        return lease

    def heartbeat(self, lease: WorkerLease, *, now: float | None = None) -> WorkerLease:
        now = time.time() if now is None else now
        with self._lock:
            current = self._workers.get(lease.worker_id)
            if current is None or current.fencing_token != lease.fencing_token or current.expires_at <= now:
                raise LeaseLost("worker lease is stale")
            updated = WorkerLease(lease.worker_id, lease.region, lease.capabilities, lease.fencing_token, now + self.lease_seconds, lease.draining)
            self._workers[lease.worker_id] = updated
            return updated

    def drain(self, lease: WorkerLease) -> WorkerLease:
        with self._lock:
            current = self._workers.get(lease.worker_id)
            if current is None or current.fencing_token != lease.fencing_token:
                raise LeaseLost("worker lease is stale")
            updated = WorkerLease(current.worker_id, current.region, current.capabilities, current.fencing_token, current.expires_at, True)
            self._workers[lease.worker_id] = updated
            return updated

    def choose(self, *, region: str, required_capabilities: Iterable[str], now: float | None = None) -> WorkerLease:
        now = time.time() if now is None else now
        required = set(required_capabilities)
        with self._lock:
            candidates = [worker for worker in self._workers.values() if not worker.draining and worker.region == region and worker.expires_at > now and required.issubset(worker.capabilities)]
        if not candidates:
            raise LeaseLost("no healthy worker satisfies placement constraints")
        return sorted(candidates, key=lambda worker: worker.worker_id)[0]


class AdmissionController:
    def __init__(self, quotas: dict[str, int] | None = None) -> None:
        self.quotas = quotas or {}
        self._active: dict[str, int] = {}
        self._lock = threading.RLock()

    def admit(self, tenant_id: str) -> None:
        with self._lock:
            limit = self.quotas.get(tenant_id, 1)
            active = self._active.get(tenant_id, 0)
            if active >= limit:
                raise ContractViolation("tenant concurrency quota exceeded")
            self._active[tenant_id] = active + 1

    def release(self, tenant_id: str) -> None:
        with self._lock:
            self._active[tenant_id] = max(0, self._active.get(tenant_id, 0) - 1)

    def active(self, tenant_id: str) -> int:
        return self._active.get(tenant_id, 0)


class EventStream:
    def __init__(self, ledger: EventLedger) -> None:
        self.ledger = ledger

    def read(self, identity: Identity, *, after_seq: int = -1, limit: int = 100) -> tuple[Event, ...]:
        return tuple(self.ledger.events(identity.tenant_id, identity.run_id, after_seq=after_seq, limit=limit))
