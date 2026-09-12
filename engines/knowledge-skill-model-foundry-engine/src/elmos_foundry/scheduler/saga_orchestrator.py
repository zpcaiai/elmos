from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class SagaStatus(str, Enum):
    PENDING = "PENDING"
    FORWARD_EXECUTING = "FORWARD_EXECUTING"
    COMPLETED = "COMPLETED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"


@dataclass
class SagaStep:
    name: str
    forward_fn: Callable[[Dict[str, Any]], Dict[str, Any]]
    compensate_fn: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None
    executed: bool = False
    forward_result: Optional[Dict[str, Any]] = None
    compensated: bool = False
    error: Optional[str] = None


@dataclass
class SagaExecutionReceipt:
    saga_id: str
    status: SagaStatus
    steps_total: int
    steps_executed: int
    steps_compensated: int
    duration_ms: float
    merkle_root: str
    error: Optional[str] = None


class DistributedSagaOrchestrator:
    """Enterprise-grade Distributed Saga Orchestrator with LIFO Compensation."""

    def __init__(self, saga_id: str):
        self.saga_id = saga_id
        self.steps: List[SagaStep] = []
        self.context: Dict[str, Any] = {}
        self.status = SagaStatus.PENDING
        self.step_hashes: List[str] = []

    def add_step(
        self,
        name: str,
        forward_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        compensate_fn: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None,
    ) -> DistributedSagaOrchestrator:
        self.steps.append(SagaStep(name=name, forward_fn=forward_fn, compensate_fn=compensate_fn))
        return self

    def execute(self, initial_context: Optional[Dict[str, Any]] = None) -> SagaExecutionReceipt:
        start_time = time.time()
        if initial_context:
            self.context.update(initial_context)

        self.status = SagaStatus.FORWARD_EXECUTING
        executed_steps: List[SagaStep] = []
        execution_error: Optional[str] = None

        for step in self.steps:
            try:
                res = step.forward_fn(self.context)
                step.executed = True
                step.forward_result = res
                if res and isinstance(res, dict):
                    self.context.update(res)
                executed_steps.append(step)

                # Record step cryptographic hash
                step_data = f"{step.name}:{json.dumps(res, sort_keys=True, default=str)}"
                h = hashlib.sha256(step_data.encode("utf-8")).hexdigest()
                self.step_hashes.append(h)
            except Exception as e:
                execution_error = str(e)
                step.error = execution_error
                break

        if execution_error is None:
            self.status = SagaStatus.COMPLETED
            merkle = self._compute_merkle_root()
            return SagaExecutionReceipt(
                saga_id=self.saga_id,
                status=self.status,
                steps_total=len(self.steps),
                steps_executed=len(executed_steps),
                steps_compensated=0,
                duration_ms=(time.time() - start_time) * 1000,
                merkle_root=merkle,
            )

        # Failure occurred -> initiate LIFO backward compensation
        self.status = SagaStatus.COMPENSATING
        compensated_count = 0

        for step in reversed(executed_steps):
            if step.compensate_fn:
                try:
                    step.compensate_fn(self.context, step.forward_result or {})
                    step.compensated = True
                    compensated_count += 1
                    comp_data = f"COMPENSATE:{step.name}"
                    h = hashlib.sha256(comp_data.encode("utf-8")).hexdigest()
                    self.step_hashes.append(h)
                except Exception as comp_err:
                    step.error = f"Compensation failed: {comp_err}"

        self.status = SagaStatus.COMPENSATED
        merkle = self._compute_merkle_root()
        return SagaExecutionReceipt(
            saga_id=self.saga_id,
            status=self.status,
            steps_total=len(self.steps),
            steps_executed=len(executed_steps),
            steps_compensated=compensated_count,
            duration_ms=(time.time() - start_time) * 1000,
            merkle_root=merkle,
            error=execution_error,
        )

    def _compute_merkle_root(self) -> str:
        if not self.step_hashes:
            return hashlib.sha256(b"empty_saga").hexdigest()
        current = self.step_hashes
        while len(current) > 1:
            next_level = []
            for i in range(0, len(current), 2):
                if i + 1 < len(current):
                    combined = current[i] + current[i + 1]
                else:
                    combined = current[i] + current[i]
                next_level.append(hashlib.sha256(combined.encode("utf-8")).hexdigest())
            current = next_level
        return current[0]
