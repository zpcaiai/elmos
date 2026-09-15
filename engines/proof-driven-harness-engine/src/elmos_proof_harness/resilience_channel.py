"""Industrial-grade resilience channel with chaos fault injection, circuit breaker, and exponential backoff retry."""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, TypeVar

logger = logging.getLogger("elmos_proof_harness.resilience_channel")

T = TypeVar("T")


class ChaosFaultType(str, Enum):
    LATENCY_INJECTION = "LATENCY_INJECTION"
    CONNECTION_DROP = "CONNECTION_DROP"
    DEADLOCK_EXCEPTION = "DEADLOCK_EXCEPTION"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(RuntimeError):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""


class NonRetryableError(RuntimeError):
    """Marks an error that should not be retried (e.g. fatal syntax error, constraint violation)."""


@dataclass
class ChaosConfig:
    enabled: bool = False
    injected_latency_ms: int = 0
    failure_rate: float = 0.0  # 0.0 to 1.0 probability
    fault_type: ChaosFaultType = ChaosFaultType.CONNECTION_DROP
    max_injections: int | None = None


class ChaosFaultInjector:
    """Injects artificial latency and network drops for resilience and chaos qualification."""

    def __init__(self, config: ChaosConfig | None = None) -> None:
        self.config = config or ChaosConfig()
        self._lock = threading.Lock()
        self.injected_count = 0

    def maybe_inject_fault(self) -> None:
        """Applies configured network latency or raises simulated connection failures."""
        if not self.config.enabled:
            return

        with self._lock:
            if self.config.max_injections is not None and self.injected_count >= self.config.max_injections:
                return

            # 1. Latency injection
            if self.config.injected_latency_ms > 0:
                time.sleep(self.config.injected_latency_ms / 1000.0)

            # 2. Failure probability injection
            if self.config.failure_rate > 0.0 and random.random() < self.config.failure_rate:
                self.injected_count += 1
                if self.config.fault_type == ChaosFaultType.CONNECTION_DROP:
                    raise ConnectionResetError("[CHAOS] Connection reset by peer (injected network drop)")
                elif self.config.fault_type == ChaosFaultType.DEADLOCK_EXCEPTION:
                    raise RuntimeError("[CHAOS] 40P01 deadlock detected (injected lock contention)")
                elif self.config.fault_type == ChaosFaultType.TIMEOUT_ERROR:
                    raise TimeoutError("[CHAOS] Network read timeout (injected TCP stall)")
                else:
                    raise OSError("[CHAOS] Network I/O failure (injected fault)")


class CircuitBreaker:
    """Thread-safe circuit breaker preventing cascade failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 5.0,
        half_open_success_threshold: int = 2,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        self.half_open_threshold = half_open_success_threshold

        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.last_failure_time = 0.0
        self._lock = threading.Lock()

    def record_success(self) -> None:
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.consecutive_successes += 1
                if self.consecutive_successes >= self.half_open_threshold:
                    self.state = CircuitState.CLOSED
                    self.consecutive_failures = 0
                    self.consecutive_successes = 0
                    logger.info("Circuit breaker reset to CLOSED")
            elif self.state == CircuitState.CLOSED:
                self.consecutive_failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self.consecutive_failures += 1
            self.last_failure_time = time.monotonic()
            if self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN):
                if self.consecutive_failures >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    logger.warning(
                        "Circuit breaker tripped to OPEN after %d consecutive failures",
                        self.consecutive_failures,
                    )

    def allow_request(self) -> bool:
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.monotonic() - self.last_failure_time > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.consecutive_successes = 0
                    logger.info("Circuit breaker transitioning to HALF_OPEN probe")
                    return True
                return False
            # HALF_OPEN allows probe
            return True


@dataclass(frozen=True)
class RetryMetrics:
    total_calls: int
    retried_calls: int
    successful_calls: int
    circuit_breaker_rejections: int


class ResilientDatabaseChannel:
    """Provides chaos-aware, backoff-retryable, and circuit-breaker guarded execution."""

    def __init__(
        self,
        max_retries: int = 3,
        base_backoff_seconds: float = 0.05,
        max_backoff_seconds: float = 2.0,
        fault_injector: ChaosFaultInjector | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.base_backoff = base_backoff_seconds
        self.max_backoff = max_backoff_seconds
        self.fault_injector = fault_injector or ChaosFaultInjector()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

        self.total_calls = 0
        self.retried_calls = 0
        self.successful_calls = 0
        self.circuit_rejections = 0
        self._stats_lock = threading.Lock()

    def is_retryable_exception(self, exc: Exception) -> bool:
        """Determines whether a raised exception indicates a transient network/lock failure."""
        if isinstance(exc, NonRetryableError):
            return False
        # Retryable patterns: connection reset, deadlocks, timeouts, OS network drops
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return True
        msg = str(exc).lower()
        retryable_keywords = ("deadlock", "timeout", "connection reset", "could not connect", "broken pipe", "40p01")
        return any(kw in msg for kw in retryable_keywords)

    def execute(self, action: Callable[[], T], on_reconnect: Callable[[], None] | None = None) -> T:
        """Executes an action with exponential backoff, jitter, chaos injection, and circuit protection."""
        with self._stats_lock:
            self.total_calls += 1

        if not self.circuit_breaker.allow_request():
            with self._stats_lock:
                self.circuit_rejections += 1
            raise CircuitBreakerOpenError("Circuit breaker is OPEN; operation rejected to prevent cascading failure")

        attempt = 0
        while True:
            try:
                # Potential chaos injection prior to running
                self.fault_injector.maybe_inject_fault()

                res = action()
                self.circuit_breaker.record_success()
                with self._stats_lock:
                    self.successful_calls += 1
                return res

            except Exception as exc:
                if not self.is_retryable_exception(exc) or attempt >= self.max_retries:
                    self.circuit_breaker.record_failure()
                    raise

                attempt += 1
                with self._stats_lock:
                    self.retried_calls += 1

                # Calculate Exponential Backoff with Full Jitter:
                # sleep = uniform(0, min(max_backoff, base * 2^attempt))
                backoff_cap = min(self.max_backoff, self.base_backoff * (2 ** attempt))
                sleep_duration = random.uniform(0.5 * backoff_cap, backoff_cap)
                logger.warning(
                    "Transient database channel error on attempt %d/%d: %s. Backing off for %.3fs",
                    attempt,
                    self.max_retries,
                    exc,
                    sleep_duration,
                )
                time.sleep(sleep_duration)

                # Invoke reconnect callback if provided
                if on_reconnect:
                    try:
                        on_reconnect()
                    except Exception as rec_err:
                        logger.warning("Reconnect callback failed: %s", rec_err)

    def metrics(self) -> RetryMetrics:
        with self._stats_lock:
            return RetryMetrics(
                total_calls=self.total_calls,
                retried_calls=self.retried_calls,
                successful_calls=self.successful_calls,
                circuit_breaker_rejections=self.circuit_rejections,
            )
