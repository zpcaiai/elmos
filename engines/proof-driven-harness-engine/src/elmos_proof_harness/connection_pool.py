"""Industrial-grade thread-safe PostgreSQL connection pool with health probes and failover."""

from __future__ import annotations

import logging
import queue
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, NamedTuple

logger = logging.getLogger("elmos_proof_harness.connection_pool")


class PoolMetrics(NamedTuple):
    total_connections: int
    available_connections: int
    active_connections: int
    created_total: int
    reconnected_total: int
    failed_health_checks: int


class PoolError(Exception):
    """Raised when connection pool operations fail."""


class PoolExhaustedError(PoolError):
    """Raised when no connections are available within the timeout."""


class PooledConnection:
    """Wrapper around a raw DB-API connection tracking creation and idle timestamps."""

    def __init__(self, raw_connection: Any) -> None:
        self.raw = raw_connection
        self.created_at = time.monotonic()
        self.last_used_at = time.monotonic()
        self.is_healthy = True

    def ping(self) -> bool:
        """Probe the connection with SELECT 1."""
        try:
            cur = self.raw.cursor()
            try:
                cur.execute("SELECT 1")
                res = cur.fetchone()
                return bool(res)
            finally:
                cur.close()
        except Exception:
            self.is_healthy = False
            return False

    def close(self) -> None:
        try:
            self.raw.close()
        except Exception:
            pass


class PostgresConnectionPool:
    """Thread-safe, bounded, self-healing connection pool for PostgreSQL."""

    def __init__(
        self,
        connect_fn: Callable[[], Any],
        min_size: int = 2,
        max_size: int = 10,
        timeout_seconds: float = 30.0,
        max_idle_seconds: float = 300.0,
        ping_on_borrow: bool = True,
    ) -> None:
        if min_size < 0 or max_size <= 0 or min_size > max_size:
            raise ValueError(f"Invalid pool sizes: min_size={min_size}, max_size={max_size}")
        self._connect_fn = connect_fn
        self._min_size = min_size
        self._max_size = max_size
        self._timeout_seconds = timeout_seconds
        self._max_idle_seconds = max_idle_seconds
        self._ping_on_borrow = ping_on_borrow

        self._pool: queue.Queue[PooledConnection] = queue.Queue(maxsize=max_size)
        self._lock = threading.Lock()
        self._total_connections = 0
        self._created_total = 0
        self._reconnected_total = 0
        self._failed_health_checks = 0
        self._closed = False

        # Warm up to min_size
        self._warmup()

    def _warmup(self) -> None:
        with self._lock:
            for _ in range(self._min_size):
                try:
                    conn = self._create_new_connection()
                    self._pool.put_nowait(conn)
                except Exception as exc:
                    logger.warning("Failed to warm up connection pool connection: %s", exc)
                    break

    def _create_new_connection(self) -> PooledConnection:
        raw = self._connect_fn()
        conn = PooledConnection(raw)
        self._total_connections += 1
        self._created_total += 1
        return conn

    @contextmanager
    def acquire(self, timeout: float | None = None) -> Iterator[Any]:
        """Borrow a connection from the pool, yielding the raw connection.

        Returns it back to the pool upon context exit or closes it if broken.
        """
        if self._closed:
            raise PoolError("Connection pool is closed")

        deadline = time.monotonic() + (timeout if timeout is not None else self._timeout_seconds)
        pooled_conn: PooledConnection | None = None

        while pooled_conn is None:
            now = time.monotonic()
            remaining = deadline - now
            if remaining <= 0:
                raise PoolExhaustedError(
                    f"Timed out waiting for connection after {self._timeout_seconds}s "
                    f"(active={self._total_connections - self._pool.qsize()}, total={self._total_connections})"
                )

            # 1. Try to get an idle connection from the queue
            try:
                candidate = self._pool.get(block=True, timeout=min(0.2, remaining))
            except queue.Empty:
                candidate = None

            if candidate is not None:
                # Validate idle lifetime and ping
                idle_duration = time.monotonic() - candidate.last_used_at
                healthy = True
                if idle_duration > self._max_idle_seconds or self._ping_on_borrow:
                    if not candidate.ping():
                        healthy = False
                        self._failed_health_checks += 1
                        logger.debug("Discarding unhealthy idle connection from pool")

                if healthy:
                    pooled_conn = candidate
                    break
                else:
                    # Discard dead connection
                    candidate.close()
                    with self._lock:
                        self._total_connections -= 1
                    continue

            # 2. If queue had no connection, check if we can spawn a new one under max_size
            with self._lock:
                if self._closed:
                    raise PoolError("Connection pool is closed")
                if self._total_connections < self._max_size:
                    try:
                        pooled_conn = self._create_new_connection()
                        self._reconnected_total += 1
                        break
                    except Exception as exc:
                        logger.error("Failed to establish new pooled connection: %s", exc)
                        # Backoff slightly before next loop iteration
                        time.sleep(0.05)
                        continue

        pooled_conn.last_used_at = time.monotonic()
        should_discard = False
        try:
            yield pooled_conn.raw
        except Exception as exc:
            # Check if this exception represents a fatal DB connection loss
            err_msg = str(exc).lower()
            if any(term in err_msg for term in ("connection reset", "closed", "broken pipe", "terminating connection")):
                should_discard = True
            raise
        finally:
            if self._closed or should_discard or not pooled_conn.is_healthy:
                pooled_conn.close()
                with self._lock:
                    self._total_connections -= 1
            else:
                pooled_conn.last_used_at = time.monotonic()
                try:
                    self._pool.put_nowait(pooled_conn)
                except queue.Full:
                    # Shouldn't happen, but safeguard against leaks
                    pooled_conn.close()
                    with self._lock:
                        self._total_connections -= 1

    def metrics(self) -> PoolMetrics:
        with self._lock:
            avail = self._pool.qsize()
            active = max(0, self._total_connections - avail)
            return PoolMetrics(
                total_connections=self._total_connections,
                available_connections=avail,
                active_connections=active,
                created_total=self._created_total,
                reconnected_total=self._reconnected_total,
                failed_health_checks=self._failed_health_checks,
            )

    def close(self) -> None:
        """Drain and close all connections in the pool."""
        with self._lock:
            self._closed = True
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                except queue.Empty:
                    break
            self._total_connections = 0
