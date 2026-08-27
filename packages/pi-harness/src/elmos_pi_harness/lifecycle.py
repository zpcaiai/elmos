"""Fail-closed task state transitions."""

from __future__ import annotations

from .models import TASK_TRANSITIONS, InvalidTransitionError, TaskState


def assert_transition(current: str | TaskState, target: str | TaskState) -> tuple[TaskState, TaskState]:
    try:
        source = TaskState(current)
        destination = TaskState(target)
    except ValueError as exc:
        raise InvalidTransitionError("unknown task lifecycle state") from exc
    if destination not in TASK_TRANSITIONS[source]:
        raise InvalidTransitionError(f"transition {source.value} -> {destination.value} is not allowed")
    return source, destination


def can_transition(current: str | TaskState, target: str | TaskState) -> bool:
    try:
        assert_transition(current, target)
    except InvalidTransitionError:
        return False
    return True


def is_terminal(state: str | TaskState) -> bool:
    return TaskState(state) in {TaskState.CANCELLED, TaskState.SUCCEEDED, TaskState.FAILED}
