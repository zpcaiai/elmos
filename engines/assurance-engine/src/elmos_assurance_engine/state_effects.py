"""Implementation of B02: State machine, temporal ordering, and side effect models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AssuranceRunState(str, Enum):
    NEW = "NEW"
    SCOPED = "SCOPED"
    CONTRACT_APPROVED = "CONTRACT_APPROVED"
    PLANNED = "PLANNED"
    BUILDING = "BUILDING"
    SMOKE = "SMOKE"
    REGRESSION = "REGRESSION"
    ADVANCED = "ADVANCED"
    SEALED = "SEALED"
    AUDITING = "AUDITING"
    DECIDED = "DECIDED"


ALLOWED_TRANSITIONS = {
    AssuranceRunState.NEW: {AssuranceRunState.SCOPED},
    AssuranceRunState.SCOPED: {AssuranceRunState.CONTRACT_APPROVED},
    AssuranceRunState.CONTRACT_APPROVED: {AssuranceRunState.PLANNED},
    AssuranceRunState.PLANNED: {AssuranceRunState.BUILDING},
    AssuranceRunState.BUILDING: {AssuranceRunState.SMOKE},
    AssuranceRunState.SMOKE: {AssuranceRunState.REGRESSION},
    AssuranceRunState.REGRESSION: {AssuranceRunState.ADVANCED},
    AssuranceRunState.ADVANCED: {AssuranceRunState.SEALED},
    AssuranceRunState.SEALED: {AssuranceRunState.AUDITING},
    AssuranceRunState.AUDITING: {AssuranceRunState.DECIDED},
}


@dataclass
class RunLifecycleStateMachine:
    current_state: AssuranceRunState = AssuranceRunState.NEW
    history: list[AssuranceRunState] = field(default_factory=lambda: [AssuranceRunState.NEW])

    def transition_to(self, new_state: AssuranceRunState) -> None:
        allowed = ALLOWED_TRANSITIONS.get(self.current_state, set())
        if new_state not in allowed:
            raise ValueError(
                f"INVALID_STATE_TRANSITION: Cannot transition from {self.current_state} to {new_state}"
            )
        self.current_state = new_state
        self.history.append(new_state)


@dataclass(frozen=True)
class SideEffectRecord:
    effect_id: str
    target_system: str
    action: str
    payload_digest: str
    status: str = "COMMITTED"
