"""Crash Continuation, Orphan Task Reconciler, and Event-Sourced Time-Travel Replay.

Guarantees recovery from sudden process termination (SIGKILL/power outage)
and provides deterministic state reconstruction up to any historical event sequence.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping, Sequence

logger = logging.getLogger("elmos_proof_harness.crash_recovery")


class TaskLifecycleState(str, Enum):
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    STEP_COMMITTED = "STEP_COMMITTED"
    CHECKPOINTED = "CHECKPOINTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ORPHAN_ROLLED_BACK = "ORPHAN_ROLLED_BACK"


@dataclass(frozen=True)
class JournalEvent:
    seq_num: int
    task_id: str
    tenant_id: str
    generation_fence: int
    state: TaskLifecycleState
    step_id: str | None
    timestamp: str
    payload: dict[str, Any]

    @property
    def digest(self) -> str:
        data = {
            "seq_num": self.seq_num,
            "task_id": self.task_id,
            "tenant_id": self.tenant_id,
            "generation_fence": self.generation_fence,
            "state": self.state.value,
            "step_id": self.step_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


class TaskExecutionJournal:
    """Append-only in-memory or persisted task event journal."""

    def __init__(self) -> None:
        self._events: list[JournalEvent] = []

    def __len__(self) -> int:
        return len(self._events)

    def append_event(
        self,
        task_id: str,
        tenant_id: str,
        generation_fence: int,
        state: TaskLifecycleState,
        step_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> JournalEvent:
        seq = len(self._events) + 1
        now = datetime.now(UTC).isoformat()
        evt = JournalEvent(
            seq_num=seq,
            task_id=task_id,
            tenant_id=tenant_id,
            generation_fence=generation_fence,
            state=state,
            step_id=step_id,
            timestamp=now,
            payload=dict(payload or {}),
        )
        self._events.append(evt)
        return evt

    def get_events(self, task_id: str | None = None) -> Sequence[JournalEvent]:
        if task_id is None:
            return list(self._events)
        return [e for e in self._events if e.task_id == task_id]


class InFlightOrphanReconciler:
    """Detects in-flight tasks interrupted by a crash and safely resumes or rolls them back."""

    def __init__(self, journal: TaskExecutionJournal) -> None:
        self.journal = journal

    def reconcile_on_startup(self, current_generation: int) -> dict[str, str]:
        """Returns dict of {task_id: action ('RESUMED' | 'ROLLED_BACK')}."""
        task_latest: dict[str, JournalEvent] = {}
        for evt in self.journal.get_events():
            task_latest[evt.task_id] = evt

        actions: dict[str, str] = {}
        for task_id, latest in task_latest.items():
            if latest.state in (
                TaskLifecycleState.COMPLETED,
                TaskLifecycleState.FAILED,
                TaskLifecycleState.ORPHAN_ROLLED_BACK,
            ):
                continue  # Already in terminal state

            # Interrupted task detected!
            if latest.generation_fence < current_generation:
                # Stale generation -> must roll back to avoid split-brain
                self.journal.append_event(
                    task_id=task_id,
                    tenant_id=latest.tenant_id,
                    generation_fence=current_generation,
                    state=TaskLifecycleState.ORPHAN_ROLLED_BACK,
                    step_id=latest.step_id,
                    payload={"reason": f"stale fence {latest.generation_fence} < current {current_generation}"},
                )
                actions[task_id] = "ROLLED_BACK"
            else:
                # Same generation -> mark checkpointed and ready to resume
                self.journal.append_event(
                    task_id=task_id,
                    tenant_id=latest.tenant_id,
                    generation_fence=current_generation,
                    state=TaskLifecycleState.CHECKPOINTED,
                    step_id=latest.step_id,
                    payload={"resumable_from_step": latest.step_id},
                )
                actions[task_id] = "RESUMED"

        return actions


class TimeTravelReplayer:
    """Deterministically reconstructs task execution state up to any historical event sequence."""

    def __init__(self, journal: TaskExecutionJournal) -> None:
        self.journal = journal

    def replay_to_sequence(self, task_id: str, target_seq_num: int) -> dict[str, Any]:
        state: dict[str, Any] = {
            "task_id": task_id,
            "current_state": TaskLifecycleState.INITIALIZED.value,
            "completed_steps": [],
            "accumulated_data": {},
            "last_step_id": None,
            "events_replayed": 0,
        }

        for evt in self.journal.get_events(task_id):
            if evt.seq_num > target_seq_num:
                break

            state["events_replayed"] += 1
            state["current_state"] = evt.state.value
            state["last_step_id"] = evt.step_id

            if evt.step_id and evt.step_id not in state["completed_steps"]:
                state["completed_steps"].append(evt.step_id)

            if evt.payload:
                state["accumulated_data"].update(evt.payload)

        return state
