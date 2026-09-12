from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict

logger = logging.getLogger('elmos.foundry.scheduler.worker')

@dataclass
class FencingToken:
    worker_id: str
    generation: int
    lease_id: str
    issued_at: float
    expires_at: float

    def is_valid(self) -> bool:
        return time.time() < self.expires_at

@dataclass
class WorkerLease:
    lease_id: str
    worker_id: str
    task_id: str
    token: FencingToken
    ttl_seconds: float

class WorkerPool:
    """Concurrent worker pool with capability leases, fencing tokens, and heartbeat tracking."""

    def __init__(self, max_workers: int = 8):
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='elmos-worker')
        self._lock = threading.Lock()
        self._leases: Dict[str, WorkerLease] = {}
        self._worker_generations: Dict[str, int] = {}
        self._heartbeats: Dict[str, float] = {}

    def acquire_lease(self, worker_id: str, task_id: str, ttl_seconds: float = 30.0) -> WorkerLease:
        with self._lock:
            gen = self._worker_generations.get(worker_id, 0) + 1
            self._worker_generations[worker_id] = gen
            now = time.time()
            lease_id = str(uuid.uuid4())
            token = FencingToken(
                worker_id=worker_id,
                generation=gen,
                lease_id=lease_id,
                issued_at=now,
                expires_at=now + ttl_seconds,
            )
            lease = WorkerLease(
                lease_id=lease_id,
                worker_id=worker_id,
                task_id=task_id,
                token=token,
                ttl_seconds=ttl_seconds,
            )
            self._leases[lease_id] = lease
            self._heartbeats[worker_id] = now
            return lease

    def renew_lease(self, lease_id: str, extension_seconds: float = 30.0) -> bool:
        with self._lock:
            lease = self._leases.get(lease_id)
            if not lease:
                return False
            now = time.time()
            if now > lease.token.expires_at:
                # Already expired, fail-closed
                return False
            lease.token.expires_at = now + extension_seconds
            self._heartbeats[lease.worker_id] = now
            return True

    def release_lease(self, lease_id: str) -> None:
        with self._lock:
            lease = self._leases.pop(lease_id, None)
            if lease:
                self._heartbeats.pop(lease.worker_id, None)

    def verify_lease(self, lease_id: str, token: FencingToken) -> bool:
        with self._lock:
            lease = self._leases.get(lease_id)
            if not lease:
                return False
            if lease.token.generation != token.generation:
                return False
            if time.time() > lease.token.expires_at:
                return False
            return True

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future[Any]:
        return self._executor.submit(fn, *args, **kwargs)

    def heartbeat(self, worker_id: str) -> None:
        with self._lock:
            self._heartbeats[worker_id] = time.time()

    def reap_expired_leases(self) -> int:
        reaped = 0
        now = time.time()
        with self._lock:
            expired_ids = [lid for lid, lease in self._leases.items() if now > lease.token.expires_at]
            for lid in expired_ids:
                del self._leases[lid]
                reaped += 1
        return reaped

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
