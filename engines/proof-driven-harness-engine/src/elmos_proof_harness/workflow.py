"""Durable workflow state machine with cancellation, deadlines and recovery.

``WorkflowEngine`` validates lifecycle semantics and delegates atomic state,
outbox and checkpoint commits to :class:`storage.ControlPlaneStore`. Recovery always
increments both execution epoch and fencing generation, making every old worker
unable to commit even if it later wakes up.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .contracts import CheckpointRecord, LeaseGrant, SecurityContext, utc_now
from .errors import ConflictError, WorkflowError
from .storage import ControlPlaneStore
from .store import RunSnapshot


class RunState(StrEnum):
    CREATED = "CREATED"
    ADMITTED = "ADMITTED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    CHECKPOINTED = "CHECKPOINTED"
    PAUSED = "PAUSED"
    RESUMING = "RESUMING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    VERIFYING = "VERIFYING"
    CERTIFYING = "CERTIFYING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    PARTIAL = "PARTIAL"


TERMINAL_STATES = frozenset(
    {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED, RunState.TIMED_OUT, RunState.PARTIAL}
)


_ALLOWED: dict[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset({RunState.ADMITTED, RunState.CANCELLED, RunState.TIMED_OUT}),
    RunState.ADMITTED: frozenset({RunState.PLANNING, RunState.BLOCKED, RunState.CANCELLED, RunState.TIMED_OUT}),
    RunState.PLANNING: frozenset({RunState.EXECUTING, RunState.BLOCKED, RunState.CANCELLED, RunState.TIMED_OUT}),
    RunState.EXECUTING: frozenset(
        {
            RunState.CHECKPOINTED,
            RunState.PAUSED,
            RunState.AWAITING_REVIEW,
            RunState.VERIFYING,
            RunState.BLOCKED,
            RunState.FAILED,
            RunState.CANCELLED,
            RunState.TIMED_OUT,
        }
    ),
    RunState.CHECKPOINTED: frozenset(
        {RunState.EXECUTING, RunState.PAUSED, RunState.RESUMING, RunState.CANCELLED, RunState.TIMED_OUT}
    ),
    RunState.PAUSED: frozenset({RunState.RESUMING, RunState.CANCELLED, RunState.TIMED_OUT}),
    RunState.RESUMING: frozenset(
        {RunState.EXECUTING, RunState.VERIFYING, RunState.BLOCKED, RunState.CANCELLED, RunState.TIMED_OUT}
    ),
    RunState.AWAITING_REVIEW: frozenset(
        {RunState.EXECUTING, RunState.VERIFYING, RunState.BLOCKED, RunState.CANCELLED, RunState.TIMED_OUT}
    ),
    RunState.VERIFYING: frozenset(
        {RunState.EXECUTING, RunState.CERTIFYING, RunState.BLOCKED, RunState.FAILED, RunState.PARTIAL, RunState.CANCELLED, RunState.TIMED_OUT}
    ),
    RunState.CERTIFYING: frozenset(
        {RunState.COMPLETED, RunState.BLOCKED, RunState.FAILED, RunState.PARTIAL, RunState.CANCELLED, RunState.TIMED_OUT}
    ),
    RunState.BLOCKED: frozenset({RunState.RESUMING, RunState.CANCELLED, RunState.TIMED_OUT}),
    RunState.COMPLETED: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
    RunState.TIMED_OUT: frozenset(),
    RunState.PARTIAL: frozenset(),
}


@dataclass(frozen=True, slots=True)
class RunAggregate:
    run_id: str
    revision_set_id: str
    state: RunState
    sequence: int
    execution_epoch: int
    fencing_generation: int
    deadline_at: datetime | None = None

    @classmethod
    def from_snapshot(cls, snapshot: RunSnapshot) -> "RunAggregate":
        return cls(
            run_id=snapshot.run_id,
            revision_set_id=snapshot.revision_set_id,
            state=RunState(snapshot.state),
            sequence=snapshot.sequence,
            execution_epoch=snapshot.execution_epoch,
            fencing_generation=snapshot.fencing_generation,
            deadline_at=snapshot.deadline_at,
        )

    def validate_transition(
        self,
        target: RunState,
        *,
        expected_sequence: int,
        execution_epoch: int,
        fencing_generation: int,
        now: datetime,
    ) -> None:
        if expected_sequence != self.sequence:
            raise ConflictError("optimistic sequence conflict")
        if execution_epoch != self.execution_epoch:
            raise ConflictError("execution epoch is stale", code="STALE_EPOCH")
        if fencing_generation != self.fencing_generation:
            raise ConflictError("fencing generation is stale", code="STALE_FENCE")
        if self.deadline_at is not None and now >= self.deadline_at and target not in {RunState.TIMED_OUT, RunState.CANCELLED}:
            raise WorkflowError("run deadline elapsed", code="RUN_DEADLINE_EXCEEDED")
        if target not in _ALLOWED[self.state]:
            raise WorkflowError(
                "invalid workflow transition",
                details={"source": self.state.value, "target": target.value},
            )


@dataclass(frozen=True, slots=True)
class RecoverySession:
    context: SecurityContext
    run: RunAggregate
    lease: LeaseGrant
    checkpoint: CheckpointRecord
    checkpoint_payload: bytes


class WorkflowEngine:
    """Lifecycle façade over the durable store."""

    def __init__(self, store: ControlPlaneStore) -> None:
        self._store = store

    def create(
        self,
        context: SecurityContext,
        *,
        run_id: str,
        revision_set_id: str,
        deadline_at: datetime | None = None,
        idempotency_key: str | None = None,
        now: datetime | None = None,
    ) -> RunAggregate:
        snapshot = self._store.create_run(
            context,
            run_id=run_id,
            revision_set_id=revision_set_id,
            deadline_at=deadline_at,
            idempotency_key=idempotency_key,
            now=now,
        )
        return RunAggregate.from_snapshot(snapshot)

    def acquire(
        self,
        context: SecurityContext,
        *,
        owner_id: str,
        expected_sequence: int,
        ttl_seconds: int = 300,
        now: datetime | None = None,
    ) -> LeaseGrant:
        return self._store.acquire_lease(
            context,
            owner_id=owner_id,
            expected_sequence=expected_sequence,
            ttl_seconds=ttl_seconds,
            now=now,
        )

    def transition(
        self,
        context: SecurityContext,
        target: RunState,
        *,
        expected_sequence: int,
        lease_token: str,
        now: datetime | None = None,
    ) -> RunAggregate:
        current_time = now or utc_now()
        current = RunAggregate.from_snapshot(self._store.get_run(context))
        if target is RunState.COMPLETED and self._store.unsettled_side_effect_count(
            context, run_id=current.run_id
        ):
            raise WorkflowError(
                "run cannot complete while external effects are unsettled",
                code="SIDE_EFFECTS_UNSETTLED",
            )
        current.validate_transition(
            target,
            expected_sequence=expected_sequence,
            execution_epoch=context.execution_epoch,
            fencing_generation=context.fencing_generation,
            now=current_time,
        )
        snapshot = self._store.transition_run(
            context,
            target_state=target.value,
            expected_sequence=expected_sequence,
            lease_token=lease_token,
            now=current_time,
        )
        return RunAggregate.from_snapshot(snapshot)

    def cancel(
        self,
        context: SecurityContext,
        *,
        expected_sequence: int,
        lease_token: str,
        now: datetime | None = None,
    ) -> RunAggregate:
        current = RunAggregate.from_snapshot(self._store.get_run(context))
        if current.state is RunState.CANCELLED:
            return current
        if current.state in TERMINAL_STATES:
            raise WorkflowError("terminal run cannot be cancelled", code="RUN_TERMINAL")
        return self.transition(
            context,
            RunState.CANCELLED,
            expected_sequence=expected_sequence,
            lease_token=lease_token,
            now=now,
        )

    def enforce_timeout(
        self,
        context: SecurityContext,
        *,
        expected_sequence: int,
        lease_token: str,
        now: datetime | None = None,
    ) -> RunAggregate:
        current_time = now or utc_now()
        current = RunAggregate.from_snapshot(self._store.get_run(context))
        if current.deadline_at is None or current_time < current.deadline_at:
            raise WorkflowError("run deadline has not elapsed", code="RUN_NOT_TIMED_OUT")
        return self.transition(
            context,
            RunState.TIMED_OUT,
            expected_sequence=expected_sequence,
            lease_token=lease_token,
            now=current_time,
        )

    def checkpoint(
        self,
        context: SecurityContext,
        payload: bytes,
        *,
        expected_sequence: int,
        lease_token: str,
        checkpoint_id: str | None = None,
        now: datetime | None = None,
    ) -> CheckpointRecord:
        current = RunAggregate.from_snapshot(self._store.get_run(context))
        if current.state not in {RunState.EXECUTING, RunState.CHECKPOINTED}:
            raise WorkflowError("run cannot checkpoint from its current state", details={"state": current.state.value})
        return self._store.append_checkpoint(
            context,
            payload,
            expected_sequence=expected_sequence,
            lease_token=lease_token,
            checkpoint_id=checkpoint_id,
            now=now,
        )

    def recover(
        self,
        context: SecurityContext,
        *,
        owner_id: str,
        expected_sequence: int,
        ttl_seconds: int = 300,
        now: datetime | None = None,
    ) -> RecoverySession:
        snapshot, lease, checkpoint, payload = self._store.recover_run(
            context,
            owner_id=owner_id,
            expected_sequence=expected_sequence,
            ttl_seconds=ttl_seconds,
            now=now,
        )
        recovered_context = context.for_run(
            snapshot.run_id,
            execution_epoch=snapshot.execution_epoch,
            fencing_generation=snapshot.fencing_generation,
        )
        return RecoverySession(
            context=recovered_context,
            run=RunAggregate.from_snapshot(snapshot),
            lease=lease,
            checkpoint=checkpoint,
            checkpoint_payload=payload,
        )
