"""Industrial Distributed Workflow and Message Stream Verification Engine.

Provides message ordering validation, transactional outbox deduplication testing,
and Saga orchestrator compensation state machine verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


@dataclass
class MessageEvent:
    message_id: str
    topic: str
    sequence_no: int
    payload: Dict[str, Any]
    idempotency_key: str
    timestamp: float


@dataclass
class StreamOrderReport:
    is_strictly_ordered: bool
    total_messages: int
    out_of_order_count: int
    duplicate_count: int
    missing_sequences: List[int]


@dataclass
class SagaStep:
    name: str
    action_fn: Callable[[Dict[str, Any]], bool]
    compensate_fn: Callable[[Dict[str, Any]], bool]


@dataclass
class SagaExecutionResult:
    is_success: bool
    completed_steps: List[str]
    compensated_steps: List[str]
    failed_step: Optional[str] = None
    compensation_consistent: bool = True


class WorkflowMessageTestEngine:
    """Verifies event stream semantics and distributed saga workflow integrity."""

    @staticmethod
    def verify_stream_ordering(events: List[MessageEvent]) -> StreamOrderReport:
        """Verifies sequence numbers are monotonic, without gaps or duplicates."""
        if not events:
            return StreamOrderReport(True, 0, 0, 0, [])

        seen_ids: Set[str] = set()
        seen_keys: Set[str] = set()
        duplicates = 0
        out_of_order = 0
        missing_seqs = []

        last_seq = events[0].sequence_no - 1
        for ev in events:
            if ev.message_id in seen_ids or ev.idempotency_key in seen_keys:
                duplicates += 1
            seen_ids.add(ev.message_id)
            seen_keys.add(ev.idempotency_key)

            if ev.sequence_no <= last_seq:
                out_of_order += 1
            elif ev.sequence_no > last_seq + 1:
                missing_seqs.extend(range(last_seq + 1, ev.sequence_no))
            last_seq = ev.sequence_no

        is_strictly_ordered = (duplicates == 0) and (out_of_order == 0) and (len(missing_seqs) == 0)
        return StreamOrderReport(
            is_strictly_ordered=is_strictly_ordered,
            total_messages=len(events),
            out_of_order_count=out_of_order,
            duplicate_count=duplicates,
            missing_sequences=missing_seqs,
        )

    @staticmethod
    def execute_saga(
        steps: List[SagaStep],
        initial_context: Dict[str, Any],
    ) -> SagaExecutionResult:
        """Executes distributed Saga. On failure, triggers compensations in reverse order."""
        executed: List[SagaStep] = []
        ctx = dict(initial_context)

        for step in steps:
            try:
                ok = step.action_fn(ctx)
                if not ok:
                    return WorkflowMessageTestEngine._compensate_saga(executed, step.name, ctx)
                executed.append(step)
            except Exception:
                return WorkflowMessageTestEngine._compensate_saga(executed, step.name, ctx)

        return SagaExecutionResult(
            is_success=True,
            completed_steps=[s.name for s in executed],
            compensated_steps=[],
            failed_step=None,
            compensation_consistent=True,
        )

    @staticmethod
    def _compensate_saga(
        executed_steps: List[SagaStep],
        failed_step_name: str,
        ctx: Dict[str, Any],
    ) -> SagaExecutionResult:
        compensated = []
        all_comp_ok = True
        for step in reversed(executed_steps):
            try:
                ok = step.compensate_fn(ctx)
                if ok:
                    compensated.append(step.name)
                else:
                    all_comp_ok = False
            except Exception:
                all_comp_ok = False

        return SagaExecutionResult(
            is_success=False,
            completed_steps=[s.name for s in executed_steps],
            compensated_steps=compensated,
            failed_step=failed_step_name,
            compensation_consistent=all_comp_ok and (len(compensated) == len(executed_steps)),
        )
