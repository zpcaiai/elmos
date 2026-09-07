"""Repository-owned Temporal activity implementation for PI Harness tasks.

The external task backend is injected, but identity, tenant, lifecycle,
idempotency, evidence, and late-executor fencing stay inside this boundary.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from .canonical import canonical_bytes, require_nonempty
from .models import ConflictError, ExecutorIdentity, TaskState
from .persistence import DurableStore
from .temporal import TaskWorkflowInput

Heartbeat = Callable[[Mapping[str, Any]], None]


class TaskExecutionBackend(Protocol):
    """An idempotent executor for one exact task execution request."""

    def execute(
        self,
        value: TaskWorkflowInput,
        *,
        idempotency_key: str,
        heartbeat: Heartbeat,
    ) -> Mapping[str, Any] | Awaitable[Mapping[str, Any]]: ...


class TemporalTaskActivity:
    """Validate and execute a Temporal task without bypassing kernel state."""

    ACTIVITY_NAME = "pi-harness-execute-task-v1"
    CONTROL_ACTIVITY_NAME = "pi-harness-control-task-v1"
    RESULT_STATES = frozenset({TaskState.VERIFYING, TaskState.FAILED})

    def __init__(
        self,
        store: DurableStore,
        backend: TaskExecutionBackend,
        *,
        actor_id: str,
        max_running_tasks: int = 3,
    ) -> None:
        self.store = store
        self.backend = backend
        self.actor_id = require_nonempty(actor_id, "actor_id", 256)
        if max_running_tasks < 1:
            raise ValueError("max_running_tasks must be positive")
        self.max_running_tasks = max_running_tasks

    async def execute(
        self,
        raw_value: Mapping[str, Any],
        *,
        heartbeat: Heartbeat | None = None,
    ) -> dict[str, Any]:
        value = TaskWorkflowInput.from_dict(raw_value)
        heartbeat = heartbeat or (lambda _details: None)
        idempotency_key = f"temporal:{value.execution_id}:{value.request_digest}"
        executor = ExecutorIdentity(value.executor_id, value.executor_generation)

        task = self._validate_context(value, require_active_executor=True)

        replay = self._completed_result(value, idempotency_key, task["status"])
        if replay is not None:
            return replay | {"replayed": True}
        if task["status"] == TaskState.QUEUED.value:
            self.store.transition_task(
                value.tenant_id,
                value.task_id,
                TaskState.RUNNING,
                idempotency_key=f"{idempotency_key}:running",
                actor_id=self.actor_id,
                payload={
                    "workflow_execution_id": value.execution_id,
                    "request_digest": value.request_digest,
                    "executor_id": value.executor_id,
                    "executor_generation": value.executor_generation,
                },
                max_running_tasks=self.max_running_tasks,
            )
        elif task["status"] != TaskState.RUNNING.value:
            raise ConflictError(
                f"task state {task['status']} is not executable by the activity"
            )

        heartbeat(
            {
                "phase": "EXECUTING",
                "task_id": value.task_id,
                "request_digest": value.request_digest,
                "executor_generation": value.executor_generation,
            }
        )
        candidate = self.backend.execute(
            value,
            idempotency_key=idempotency_key,
            heartbeat=heartbeat,
        )
        if inspect.isawaitable(candidate):
            candidate = await candidate
        result = self._validate_result(value, candidate)
        self.store.assert_active_executor(
            value.tenant_id, value.environment_id, executor
        )
        self.store.transition_task(
            value.tenant_id,
            value.task_id,
            result["status"],
            idempotency_key=f"{idempotency_key}:result",
            actor_id=self.actor_id,
            payload={
                "activity_idempotency_key": idempotency_key,
                "activity_result": result,
            },
            max_running_tasks=self.max_running_tasks,
        )
        heartbeat(
            {
                "phase": "PERSISTED",
                "task_id": value.task_id,
                "evidence_digest": result["evidence_digest"],
            }
        )
        return result | {"replayed": False}

    async def control(self, raw_control: Mapping[str, Any]) -> dict[str, Any]:
        expected = {"value", "action", "control_sequence"}
        if set(raw_control) != expected:
            raise ValueError("invalid Temporal control activity fields")
        raw_value = raw_control["value"]
        if not isinstance(raw_value, Mapping):
            raise TypeError("Temporal control value must be an object")
        value = TaskWorkflowInput.from_dict(raw_value)
        action = require_nonempty(raw_control["action"], "action", 32).upper()
        sequence = raw_control["control_sequence"]
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise ValueError("control_sequence must be a positive integer")
        task = self._validate_context(value, require_active_executor=action == "RESUME")
        key = f"temporal:{value.execution_id}:control:{sequence}:{action.lower()}"
        state = TaskState(task["status"])
        payload = {
            "workflow_execution_id": value.execution_id,
            "request_digest": value.request_digest,
            "control_sequence": sequence,
        }
        if action == "PAUSE":
            if state is TaskState.PAUSED:
                return {"status": state.value, "replayed": True}
            if state is not TaskState.RUNNING:
                raise ConflictError(f"task state {state.value} cannot be paused")
            return self.store.transition_task(
                value.tenant_id,
                value.task_id,
                TaskState.PAUSED,
                idempotency_key=key,
                actor_id=self.actor_id,
                payload=payload,
                max_running_tasks=self.max_running_tasks,
            )
        if action == "RESUME":
            if state is TaskState.RUNNING:
                return {"status": state.value, "replayed": True}
            if state is not TaskState.PAUSED:
                raise ConflictError(f"task state {state.value} cannot be resumed")
            return self.store.transition_task(
                value.tenant_id,
                value.task_id,
                TaskState.RUNNING,
                idempotency_key=key,
                actor_id=self.actor_id,
                payload=payload,
                max_running_tasks=self.max_running_tasks,
            )
        if action == "CANCEL":
            if state is TaskState.CANCELLED:
                return {"status": state.value, "replayed": True}
            if state in {TaskState.SUCCEEDED, TaskState.FAILED}:
                raise ConflictError(
                    f"terminal task state {state.value} cannot be cancelled"
                )
            if state is not TaskState.CANCEL_REQUESTED:
                self.store.transition_task(
                    value.tenant_id,
                    value.task_id,
                    TaskState.CANCEL_REQUESTED,
                    idempotency_key=f"{key}:request",
                    actor_id=self.actor_id,
                    payload=payload,
                    max_running_tasks=self.max_running_tasks,
                )
            return self.store.transition_task(
                value.tenant_id,
                value.task_id,
                TaskState.CANCELLED,
                idempotency_key=f"{key}:complete",
                actor_id=self.actor_id,
                payload=payload,
                max_running_tasks=self.max_running_tasks,
            )
        raise ValueError("Temporal control action must be PAUSE, RESUME, or CANCEL")

    def _validate_context(
        self, value: TaskWorkflowInput, *, require_active_executor: bool
    ) -> dict[str, Any]:
        task = self.store.get_task(value.tenant_id, value.task_id)
        if task["project_id"] != value.project_id:
            raise ConflictError("workflow project does not match the durable task")
        if task["request"] != dict(value.request):
            raise ConflictError("workflow request does not match the durable task")
        environment = self.store.get_environment(value.tenant_id, value.environment_id)
        if environment["execution_id"] != value.execution_id:
            raise ConflictError("workflow execution does not own the environment")
        authority = self.store.get_authority_snapshot(
            value.tenant_id, value.authority_snapshot_id
        )
        if authority.environment_id != value.environment_id:
            raise ConflictError("workflow authority does not bind the environment")
        if require_active_executor:
            self.store.assert_active_executor(
                value.tenant_id,
                value.environment_id,
                ExecutorIdentity(value.executor_id, value.executor_generation),
            )
        return task

    def _completed_result(
        self, value: TaskWorkflowInput, idempotency_key: str, task_state: str
    ) -> dict[str, Any] | None:
        if task_state not in {state.value for state in self.RESULT_STATES}:
            return None
        page = self.store.events(value.tenant_id, value.task_id, limit=1000)
        for event in reversed(page["items"]):
            payload = event["payload"]
            if payload.get("activity_idempotency_key") != idempotency_key:
                continue
            result = payload.get("activity_result")
            if not isinstance(result, Mapping):
                raise ConflictError("persisted Temporal activity result is invalid")
            return self._validate_result(value, result)
        raise ConflictError("terminal activity state has no replayable result")

    @classmethod
    def _validate_result(
        cls, value: TaskWorkflowInput, candidate: Mapping[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(candidate, Mapping):
            raise TypeError("task execution result must be an object")
        result = dict(candidate)
        try:
            state = TaskState(result.get("status"))
        except ValueError as exc:
            raise ValueError("task execution result has an invalid state") from exc
        if state not in cls.RESULT_STATES:
            raise ValueError("activity may only return VERIFYING or FAILED")
        expected = {
            "task_id": value.task_id,
            "request_digest": value.request_digest,
            "executor_id": value.executor_id,
            "executor_generation": value.executor_generation,
        }
        for field, expected_value in expected.items():
            if result.get(field) != expected_value:
                raise ConflictError(f"activity result {field} binding failed")
        evidence_digest = require_nonempty(
            result.get("evidence_digest"), "evidence_digest", 71
        )
        if not evidence_digest.startswith("sha256:") or len(evidence_digest) != 71:
            raise ValueError("activity evidence_digest must be a SHA-256 digest")
        canonical_bytes(result)
        return result


def build_temporal_activity(service: TemporalTaskActivity) -> Any:
    """Return the SDK-decorated activity callable consumed by ``run_worker``."""
    try:
        from temporalio import activity
    except ImportError as exc:  # pragma: no cover - optional production extra
        raise RuntimeError(
            "temporalio is required; install elmos-pi-harness[temporal]"
        ) from exc

    @activity.defn(name=TemporalTaskActivity.ACTIVITY_NAME)
    async def execute_task(value: Mapping[str, Any]) -> dict[str, Any]:
        return await service.execute(value, heartbeat=activity.heartbeat)

    return execute_task


def build_temporal_activities(service: TemporalTaskActivity) -> tuple[Any, Any]:
    """Return both execution and durable lifecycle-control activities."""
    try:
        from temporalio import activity
    except ImportError as exc:  # pragma: no cover - optional production extra
        raise RuntimeError(
            "temporalio is required; install elmos-pi-harness[temporal]"
        ) from exc

    execute_task = build_temporal_activity(service)

    @activity.defn(name=TemporalTaskActivity.CONTROL_ACTIVITY_NAME)
    async def control_task(value: Mapping[str, Any]) -> dict[str, Any]:
        return await service.control(value)

    return execute_task, control_task
