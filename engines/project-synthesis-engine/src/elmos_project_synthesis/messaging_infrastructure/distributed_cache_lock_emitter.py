"""Enterprise Distributed Cache, Redis Lock with Fencing Tokens, and Cache Stampede Defense.

Provides Redis distributed lock management with background heartbeat renewal daemon,
monotonically increasing fencing tokens, and XFetch probabilistic early expiration.
"""

from __future__ import annotations

import math
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class DistributedLockHandle:
    """Represents an actively held distributed mutex with monotonic fencing token."""

    resource_key: str
    owner_token: str
    fencing_token: int
    ttl_seconds: float
    acquired_at: float
    expires_at: float
    is_active: bool = True

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at


class MockRedisState:
    """Thread-safe in-memory simulation of Redis atomic primitives (SET NX PX, GET, EVAL)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, tuple[str, float]] = {}  # key -> (val, expire_time)
        self._fencing_sequence: int = 1000

    def set_nx_px(self, key: str, value: str, ttl_seconds: float) -> tuple[bool, int]:
        with self._lock:
            now = time.time()
            existing = self._data.get(key)
            if existing and existing[1] > now:
                return False, 0  # Key already exists and valid

            self._fencing_sequence += 1
            token = self._fencing_sequence
            self._data[key] = (value, now + ttl_seconds)
            return True, token

    def extend_ttl(self, key: str, expected_value: str, ttl_seconds: float) -> bool:
        with self._lock:
            now = time.time()
            existing = self._data.get(key)
            if not existing or existing[1] <= now or existing[0] != expected_value:
                return False
            self._data[key] = (expected_value, now + ttl_seconds)
            return True

    def delete_if_match(self, key: str, expected_value: str) -> bool:
        with self._lock:
            existing = self._data.get(key)
            if existing and existing[0] == expected_value:
                del self._data[key]
                return True
            return False


class RedisClusterLockManager:
    """Industrial-grade distributed lock manager with fencing token and safety guarantees."""

    def __init__(self, redis_state: MockRedisState | None = None) -> None:
        self._redis = redis_state or MockRedisState()

    def acquire_lock(
        self,
        resource_key: str,
        owner_token: str,
        ttl_seconds: float = 10.0,
        timeout_seconds: float = 2.0,
        retry_interval_seconds: float = 0.05,
    ) -> DistributedLockHandle | None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            success, fencing_token = self._redis.set_nx_px(resource_key, owner_token, ttl_seconds)
            if success:
                now = time.time()
                return DistributedLockHandle(
                    resource_key=resource_key,
                    owner_token=owner_token,
                    fencing_token=fencing_token,
                    ttl_seconds=ttl_seconds,
                    acquired_at=now,
                    expires_at=now + ttl_seconds,
                    is_active=True,
                )
            time.sleep(retry_interval_seconds)
        return None

    def renew_lock(self, handle: DistributedLockHandle, ttl_seconds: float = 10.0) -> bool:
        if not handle.is_active or handle.is_expired:
            return False
        success = self._redis.extend_ttl(handle.resource_key, handle.owner_token, ttl_seconds)
        if success:
            handle.expires_at = time.time() + ttl_seconds
            handle.ttl_seconds = ttl_seconds
        else:
            handle.is_active = False
        return success

    def release_lock(self, handle: DistributedLockHandle) -> bool:
        if not handle.is_active:
            return False
        handle.is_active = False
        return self._redis.delete_if_match(handle.resource_key, handle.owner_token)


class LockHeartbeatDaemon:
    """Background daemon thread that periodically refreshes lock TTL to prevent premature timeout."""

    def __init__(
        self,
        lock_manager: RedisClusterLockManager,
        handle: DistributedLockHandle,
        heartbeat_interval_seconds: float = 0.5,
    ) -> None:
        self.lock_manager = lock_manager
        self.handle = handle
        self.heartbeat_interval = heartbeat_interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(self.heartbeat_interval)
            if self._stop_event.is_set():
                break
            renewed = self.lock_manager.renew_lock(self.handle, ttl_seconds=self.handle.ttl_seconds)
            if not renewed:
                self.handle.is_active = False
                break


@dataclass
class CacheEntry:
    value: Any
    created_at: float
    delta_computation_time: float  # Seconds taken to compute value
    ttl_seconds: float

    @property
    def expiry_timestamp(self) -> float:
        return self.created_at + self.ttl_seconds


class XFetchCacheStampedeGuard:
    """Probabilistic early expiration algorithm (Optimal Probabilistic Cache Stampede Prevention).

    Formula: recompute if (now - delta * beta * ln(rand())) > expiry_timestamp
    where:
    - delta: execution time to compute the value
    - beta: aggressiveness multiplier (> 0, default 1.0)
    - rand(): uniform random number between (0, 1]
    """

    def __init__(self, beta: float = 1.0) -> None:
        self.beta = beta
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    def get_or_compute(self, key: str, compute_func: Callable[[], Any], ttl_seconds: float) -> Any:
        with self._lock:
            entry = self._cache.get(key)

        now = time.time()

        if entry is None:
            return self._recompute_and_store(key, compute_func, ttl_seconds)

        # Evaluate XFetch early expiration condition
        # delta * beta * ln(rand) is negative because ln(u) <= 0 for u in (0, 1]
        # subtracting it increases the left-hand side, triggering early refresh
        random_val = max(1e-6, random.random())
        early_threshold = now - (entry.delta_computation_time * self.beta * math.log(random_val))

        if early_threshold >= entry.expiry_timestamp:
            # Trigger background or inline refresh
            return self._recompute_and_store(key, compute_func, ttl_seconds)

        return entry.value

    def _recompute_and_store(self, key: str, compute_func: Callable[[], Any], ttl_seconds: float) -> Any:
        start_t = time.time()
        new_val = compute_func()
        duration = max(0.001, time.time() - start_t)

        with self._lock:
            self._cache[key] = CacheEntry(
                value=new_val,
                created_at=time.time(),
                delta_computation_time=duration,
                ttl_seconds=ttl_seconds,
            )

        return new_val
