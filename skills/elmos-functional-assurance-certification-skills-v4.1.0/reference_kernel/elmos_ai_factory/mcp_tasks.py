from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class TaskState(str, Enum):
    ACCEPTED="ACCEPTED"; RUNNING="RUNNING"; WAITING_INPUT="WAITING_INPUT"; PAUSED="PAUSED"; CANCELLING="CANCELLING"; CANCELLED="CANCELLED"; BLOCKED="BLOCKED"; FAILED="FAILED"; COMPLETED="COMPLETED"

_TERMINAL={TaskState.CANCELLED,TaskState.BLOCKED,TaskState.FAILED,TaskState.COMPLETED}
_ALLOWED={
 TaskState.ACCEPTED:{TaskState.RUNNING,TaskState.CANCELLED,TaskState.BLOCKED},
 TaskState.RUNNING:{TaskState.WAITING_INPUT,TaskState.PAUSED,TaskState.CANCELLING,TaskState.BLOCKED,TaskState.FAILED,TaskState.COMPLETED},
 TaskState.WAITING_INPUT:{TaskState.RUNNING,TaskState.CANCELLING,TaskState.BLOCKED},
 TaskState.PAUSED:{TaskState.RUNNING,TaskState.CANCELLING,TaskState.BLOCKED},
 TaskState.CANCELLING:{TaskState.CANCELLED,TaskState.BLOCKED},
}

@dataclass
class McpTaskBridge:
    task_id: str
    run_id: str
    execution_epoch: int
    fencing_token: int
    state: TaskState = TaskState.ACCEPTED
    unresolved_side_effects: int = 0
    applied_idempotency_keys: set[str] = field(default_factory=set)
    journal: list[dict[str, Any]] = field(default_factory=list)

    def update(self, *, epoch: int, fencing_token: int, idempotency_key: str, next_state: TaskState, payload: dict[str, Any] | None=None) -> str:
        if epoch != self.execution_epoch or fencing_token != self.fencing_token:
            return "STALE_REJECTED"
        if idempotency_key in self.applied_idempotency_keys:
            return "DUPLICATE_IGNORED"
        if self.state in _TERMINAL:
            return "TERMINAL_REJECTED"
        if next_state not in _ALLOWED.get(self.state,set()):
            return "ILLEGAL_TRANSITION"
        if next_state in {TaskState.COMPLETED,TaskState.CANCELLED} and self.unresolved_side_effects:
            return "SIDE_EFFECTS_UNRESOLVED"
        previous=self.state; self.state=next_state; self.applied_idempotency_keys.add(idempotency_key)
        self.journal.append({'from':previous.value,'to':next_state.value,'key':idempotency_key,'payload':payload or {}})
        return "APPLIED"

    def rebind(self, *, new_epoch: int, new_fencing_token: int) -> None:
        if new_epoch <= self.execution_epoch or new_fencing_token <= self.fencing_token:
            raise ValueError("epoch and fencing token must increase")
        self.execution_epoch=new_epoch; self.fencing_token=new_fencing_token
