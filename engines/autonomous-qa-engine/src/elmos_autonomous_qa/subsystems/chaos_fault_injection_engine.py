"""Chaos Engineering & Fault Injection Simulation Engine.

Injects controlled network latency, packet loss, and service degradation
to evaluate circuit breaker triggers and fallback resiliency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import random
import time
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class CircuitBreakerState:
    status: str  # CLOSED, OPEN, HALF_OPEN
    failure_count: int = 0
    failure_threshold: int = 5
    recovery_timeout_sec: float = 10.0
    last_state_change: float = field(default_factory=time.time)

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.status = "OPEN"
            self.last_state_change = time.time()

    def record_success(self) -> None:
        if self.status == "HALF_OPEN":
            self.status = "CLOSED"
            self.failure_count = 0
            self.last_state_change = time.time()


@dataclass
class ChaosExperimentResult:
    total_calls: int
    successful_calls: int
    fallback_calls: int
    dropped_calls: int
    circuit_breaker_opened: bool
    resilience_score: float


class ChaosFaultInjectionEngine:
    """Simulates chaos faults and asserts client resilience."""

    @classmethod
    def execute_with_fault_injection(
        cls,
        total_requests: int,
        fault_rate: float,
        target_function: Callable[[], Any],
        fallback_function: Callable[[], Any],
        circuit_breaker: Optional[CircuitBreakerState] = None,
    ) -> ChaosExperimentResult:
        if circuit_breaker is None:
            circuit_breaker = CircuitBreakerState(status="CLOSED", failure_threshold=3)

        success = 0
        fallbacks = 0
        dropped = 0
        cb_opened = False

        for i in range(total_requests):
            if circuit_breaker.status == "OPEN":
                cb_opened = True
                # Direct fallback when circuit is open
                fallbacks += 1
                fallback_function()
                continue

            # Simulate fault injection
            is_fault = (i / max(1, total_requests)) < fault_rate

            if is_fault:
                circuit_breaker.record_failure()
                try:
                    fallback_function()
                    fallbacks += 1
                except Exception:
                    dropped += 1
            else:
                try:
                    target_function()
                    success += 1
                    circuit_breaker.record_success()
                except Exception:
                    circuit_breaker.record_failure()
                    fallbacks += 1

        resilience = round(((success + fallbacks) / max(1, total_requests)) * 100.0, 2)

        return ChaosExperimentResult(
            total_calls=total_requests,
            successful_calls=success,
            fallback_calls=fallbacks,
            dropped_calls=dropped,
            circuit_breaker_opened=cb_opened,
            resilience_score=resilience,
        )
