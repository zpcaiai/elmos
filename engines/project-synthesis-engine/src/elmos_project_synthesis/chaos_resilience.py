"""Industrial Chaos Engineering, Distributed Saga Recovery, and Resource Soak Leak Auditor.

Pillar 1: Bridges the gap between single-machine green tests and real-world distributed fault resilience.
"""

from __future__ import annotations

import collections
import dataclasses
import enum
import logging
import random
import time
from typing import Any, Callable

logger = logging.getLogger("elmos_project_synthesis.chaos_resilience")


class ChaosFaultType(str, enum.Enum):
    LATENCY_SPIKE = "latency_spike"
    PACKET_LOSS = "packet_loss"
    CONNECTION_REFUSED = "connection_refused"
    PARTIAL_PAYLOAD_DROP = "partial_payload_drop"
    TIMEOUT = "timeout"


@dataclasses.dataclass(frozen=True)
class ChaosRule:
    fault_type: ChaosFaultType
    probability: float  # 0.0 to 1.0
    latency_ms: float = 0.0
    target_endpoint_pattern: str = "*"


class ChaosFaultInjector:
    """Injects probabilistic network, latency, and connection failures into service execution paths."""

    def __init__(self, seed: int | None = 42) -> None:
        self.rules: list[ChaosRule] = []
        self._rng = random.Random(seed)
        self.faults_injected_count: int = 0

    def add_rule(self, rule: ChaosRule) -> None:
        self.rules.append(rule)

    def execute_with_chaos(
        self,
        endpoint: str,
        action: Callable[[], Any],
    ) -> Any:
        for rule in self.rules:
            if rule.target_endpoint_pattern != "*" and rule.target_endpoint_pattern not in endpoint:
                continue

            if self._rng.random() < rule.probability:
                self.faults_injected_count += 1
                if rule.fault_type == ChaosFaultType.LATENCY_SPIKE:
                    if rule.latency_ms > 0:
                        time.sleep(rule.latency_ms / 1000.0)
                elif rule.fault_type == ChaosFaultType.CONNECTION_REFUSED:
                    raise ConnectionRefusedError(f"Chaos injected: Connection refused for {endpoint}")
                elif rule.fault_type == ChaosFaultType.TIMEOUT:
                    raise TimeoutError(f"Chaos injected: Upstream timeout for {endpoint}")
                elif rule.fault_type == ChaosFaultType.PACKET_LOSS:
                    raise OSError(f"Chaos injected: Network packet dropped for {endpoint}")
                elif rule.fault_type == ChaosFaultType.PARTIAL_PAYLOAD_DROP:
                    raise ValueError(f"Chaos injected: Corrupted or truncated payload for {endpoint}")

        return action()


class SagaStepState(str, enum.Enum):
    PENDING = "PENDING"
    COMMITTED = "COMMITTED"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"


@dataclasses.dataclass
class SagaStep:
    name: str
    forward_action: Callable[[], Any]
    compensate_action: Callable[[], Any]
    state: SagaStepState = SagaStepState.PENDING
    result: Any = None
    error: str | None = None


class DistributedSagaRecoverySimulator:
    """Orchestrates multi-step distributed business workflows under simulated network/node crashes."""

    def __init__(self) -> None:
        self.steps: list[SagaStep] = []
        self.execution_journal: list[str] = []

    def register_step(
        self,
        name: str,
        forward_action: Callable[[], Any],
        compensate_action: Callable[[], Any],
    ) -> None:
        self.steps.append(SagaStep(name=name, forward_action=forward_action, compensate_action=compensate_action))

    def execute(self) -> dict[str, Any]:
        """Executes the forward transaction. On any failure, triggers reverse compensation."""
        committed_steps: list[SagaStep] = []
        overall_success = True
        failure_reason = None

        for step in self.steps:
            self.execution_journal.append(f"START:{step.name}")
            try:
                step.result = step.forward_action()
                step.state = SagaStepState.COMMITTED
                committed_steps.append(step)
                self.execution_journal.append(f"COMMIT:{step.name}")
            except Exception as exc:
                step.state = SagaStepState.FAILED
                step.error = str(exc)
                overall_success = False
                failure_reason = str(exc)
                self.execution_journal.append(f"FAIL:{step.name}:{exc}")
                break

        if not overall_success:
            # Trigger compensating transactions in reverse order
            self.execution_journal.append("COMPENSATION_TRIGGERED")
            for step in reversed(committed_steps):
                try:
                    step.compensate_action()
                    step.state = SagaStepState.COMPENSATED
                    self.execution_journal.append(f"COMPENSATE:{step.name}")
                except Exception as comp_exc:
                    self.execution_journal.append(f"COMPENSATE_ERROR:{step.name}:{comp_exc}")

        return {
            "success": overall_success,
            "failure_reason": failure_reason,
            "steps": [
                {
                    "name": s.name,
                    "state": s.state.value,
                    "error": s.error,
                }
                for s in self.steps
            ],
            "journal": self.execution_journal,
        }


@dataclasses.dataclass(frozen=True)
class ResourceSnapshot:
    timestamp: float
    open_handles_count: int
    active_connections_count: int
    allocated_memory_bytes: int


class SoakResourceLeakAuditor:
    """Tracks resource allocation across repetitive workloads to detect connection or descriptor leaks."""

    def __init__(self) -> None:
        self.snapshots: list[ResourceSnapshot] = []

    def record_snapshot(
        self,
        open_handles: int,
        active_connections: int,
        memory_bytes: int,
    ) -> ResourceSnapshot:
        snapshot = ResourceSnapshot(
            timestamp=time.time(),
            open_handles_count=open_handles,
            active_connections_count=active_connections,
            allocated_memory_bytes=memory_bytes,
        )
        self.snapshots.append(snapshot)
        return snapshot

    def analyze_leak_trend(self) -> dict[str, Any]:
        """Analyzes whether open handles or connections exhibit monotonic non-reclaimed growth."""
        if len(self.snapshots) < 2:
            return {"verdict": "INSUFFICIENT_SAMPLES", "leak_detected": False}

        initial = self.snapshots[0]
        final = self.snapshots[-1]

        handle_delta = final.open_handles_count - initial.open_handles_count
        connection_delta = final.active_connections_count - initial.active_connections_count
        memory_delta = final.allocated_memory_bytes - initial.allocated_memory_bytes

        leak_detected = handle_delta > 0 or connection_delta > 0

        return {
            "verdict": "LEAK_DETECTED" if leak_detected else "NO_LEAK_DETECTED",
            "leak_detected": leak_detected,
            "samples_count": len(self.snapshots),
            "open_handles_delta": handle_delta,
            "active_connections_delta": connection_delta,
            "memory_delta_bytes": memory_delta,
        }
