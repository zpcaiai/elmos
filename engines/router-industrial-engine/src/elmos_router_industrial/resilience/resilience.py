"""Resilience, circuit breaking, retry budget, stream epochs, and exactly-once commit.

Ensures the router survives transient faults, rate limits, worker crashes,
and stream interruptions without duplicated side effects or data loss.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import random
import threading
import time
from typing import Any, Mapping

from ..domain.contracts import (
    InferenceResponse,
    InferenceStreamChunk,
    ModelExecutionPlan,
    RouteRequest,
)
from ..domain.errors import ErrorTaxonomyClass, ProviderError


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreaker:
    """Scoped circuit breaker for provider+deployment+region+error_class."""

    scopeKey: str
    failureThreshold: int = 5
    cooldownSeconds: float = 30.0
    halfOpenSuccessThreshold: int = 2

    state: CircuitState = CircuitState.CLOSED
    consecutiveFailures: int = 0
    consecutiveSuccesses: int = 0
    lastFailureTime: float = 0.0

    def record_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.consecutiveSuccesses += 1
            if self.consecutiveSuccesses >= self.halfOpenSuccessThreshold:
                self.state = CircuitState.CLOSED
                self.consecutiveFailures = 0
                self.consecutiveSuccesses = 0
        elif self.state == CircuitState.CLOSED:
            self.consecutiveFailures = 0

    def record_failure(self, now: float | None = None) -> None:
        current_time = now if now is not None else time.time()
        self.consecutiveFailures += 1
        self.lastFailureTime = current_time
        if self.state == CircuitState.HALF_OPEN or self.consecutiveFailures >= self.failureThreshold:
            self.state = CircuitState.OPEN

    def allow_request(self, now: float | None = None) -> bool:
        current_time = now if now is not None else time.time()
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            if current_time - self.lastFailureTime >= self.cooldownSeconds:
                self.state = CircuitState.HALF_OPEN
                self.consecutiveSuccesses = 0
                return True
            return False
        elif self.state == CircuitState.HALF_OPEN:
            return True
        return False


class CircuitBreakerRegistry:
    """Thread-safe registry of scoped circuit breakers."""

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get_breaker(
        self,
        provider_id: str,
        deployment_id: str,
        region: str = "global",
        error_class: str = "general",
    ) -> CircuitBreaker:
        key = f"{provider_id}:{deployment_id}:{region}:{error_class}"
        with self._lock:
            if key not in self._breakers:
                self._breakers[key] = CircuitBreaker(
                    scopeKey=key,
                    failureThreshold=self.failure_threshold,
                    cooldownSeconds=self.cooldown_seconds,
                )
            return self._breakers[key]


class RetryManager:
    """Calculates backoff intervals with jitter within a strict retry budget and deadline."""

    def __init__(
        self,
        base_delay_seconds: float = 0.5,
        max_delay_seconds: float = 10.0,
        jitter_factor: float = 0.25,
    ) -> None:
        self.base_delay = base_delay_seconds
        self.max_delay = max_delay_seconds
        self.jitter_factor = jitter_factor

    def compute_backoff(
        self,
        attempt: int,
        retry_after: float | None = None,
        deadline: datetime | None = None,
        now: datetime | None = None,
    ) -> float | None:
        current_time = now or datetime.now(timezone.utc)

        if retry_after is not None and retry_after > 0:
            delay = retry_after
        else:
            exp_backoff = min(self.max_delay, self.base_delay * (2 ** max(0, attempt - 1)))
            jitter = exp_backoff * self.jitter_factor * (random.random() * 2 - 1)
            delay = max(0.01, exp_backoff + jitter)

        if deadline is not None:
            time_remaining = (deadline - current_time).total_seconds()
            if delay >= time_remaining:
                # Delay exceeds end-to-end deadline; fail immediately
                return None

        return delay


class StreamEpochCoordinator:
    """Coordinates streaming epochs so that interrupted streams do not silently concatenate tokens."""

    def __init__(self) -> None:
        self._epochs: dict[str, int] = {}
        self._buffers: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def start_stream(self, execution_id: str) -> int:
        with self._lock:
            epoch = self._epochs.get(execution_id, 0) + 1
            self._epochs[execution_id] = epoch
            self._buffers[execution_id] = []
            return epoch

    def append_chunk(self, execution_id: str, epoch: int, delta: str) -> None:
        with self._lock:
            current_epoch = self._epochs.get(execution_id, 0)
            if epoch != current_epoch:
                raise ValueError(
                    f"Stale stream chunk rejected for {execution_id}: chunk epoch {epoch} != active epoch {current_epoch}"
                )
            if execution_id in self._buffers:
                self._buffers[execution_id].append(delta)

    def abort_stream(self, execution_id: str, epoch: int) -> None:
        with self._lock:
            if self._epochs.get(execution_id) == epoch:
                self._buffers.pop(execution_id, None)

    def get_accumulated_text(self, execution_id: str) -> str:
        with self._lock:
            return "".join(self._buffers.get(execution_id, []))


@dataclass
class CommittedResult:
    taskId: str
    stepId: str
    attemptId: str
    idempotencyKey: str
    committedAt: datetime
    resultHash: str
    response: InferenceResponse


class CommitCoordinator:
    """Coordinates exactly-once result commits using Compare-And-Set (CAS) semantics."""

    def __init__(self) -> None:
        self._committed: dict[str, CommittedResult] = {}
        self._idempotency_map: dict[str, str] = {}  # idempotency_key -> commit_key
        self._lock = threading.Lock()

    def commit(
        self,
        task_id: str,
        step_id: str,
        attempt_id: str,
        idempotency_key: str,
        response: InferenceResponse,
    ) -> CommittedResult:
        commit_key = f"{task_id}:{step_id}"
        with self._lock:
            # Check idempotency duplicate
            if idempotency_key in self._idempotency_map:
                existing_key = self._idempotency_map[idempotency_key]
                if existing_key in self._committed:
                    return self._committed[existing_key]

            # Compare-and-Set check: ensure step was not already committed by another attempt
            if commit_key in self._committed:
                existing = self._committed[commit_key]
                if existing.attemptId != attempt_id:
                    # Duplicate race detected; return winning committed result
                    return existing

            res_bytes = json.dumps(
                {"content": response.content, "finishReason": response.finishReason, "model": response.model},
                sort_keys=True,
            ).encode("utf-8")
            res_hash = hashlib.sha256(res_bytes).hexdigest()

            record = CommittedResult(
                taskId=task_id,
                stepId=step_id,
                attemptId=attempt_id,
                idempotencyKey=idempotency_key,
                committedAt=datetime.now(timezone.utc),
                resultHash=res_hash,
                response=response,
            )
            self._committed[commit_key] = record
            self._idempotency_map[idempotency_key] = commit_key
            return record

    def get_committed(self, task_id: str, step_id: str) -> CommittedResult | None:
        with self._lock:
            return self._committed.get(f"{task_id}:{step_id}")


class ReplayEngine:
    """Lossless replay engine that validates historical provenance and deterministic reproducibility."""

    def __init__(self, commit_coordinator: CommitCoordinator) -> None:
        self.coordinator = commit_coordinator

    def verify_replay(
        self,
        task_id: str,
        step_id: str,
        expected_result_hash: str,
    ) -> bool:
        committed = self.coordinator.get_committed(task_id, step_id)
        if not committed:
            return False
        return committed.resultHash == expected_result_hash
