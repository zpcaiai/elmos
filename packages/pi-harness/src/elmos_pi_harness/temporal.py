"""Temporal client/worker boundary for durable PI Harness execution."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .canonical import digest, require_nonempty, require_uuid
from .models import PolicyDeniedError


@dataclass(frozen=True)
class TemporalConfig:
    target: str
    namespace: str
    task_queue: str
    deployment_version: str
    worker_identity: str
    server_name: str
    ca_certificate: Path
    client_certificate: Path
    client_private_key: Path

    def __post_init__(self) -> None:
        require_nonempty(self.target, "target", 512)
        require_nonempty(self.namespace, "namespace", 256)
        require_nonempty(self.task_queue, "task_queue", 256)
        require_nonempty(self.deployment_version, "deployment_version", 128)
        require_nonempty(self.worker_identity, "worker_identity", 256)
        require_nonempty(self.server_name, "server_name", 253)
        if ":" not in self.target:
            raise ValueError("Temporal target must include an explicit port")
        for path in (
            self.ca_certificate,
            self.client_certificate,
            self.client_private_key,
        ):
            if not path.is_absolute():
                raise ValueError("Temporal TLS paths must be absolute")


@dataclass(frozen=True)
class TaskWorkflowInput:
    tenant_id: str
    project_id: str
    task_id: str
    execution_id: str
    environment_id: str
    authority_snapshot_id: str
    executor_id: str
    executor_generation: int
    request: Mapping[str, Any]
    request_digest: str

    def __post_init__(self) -> None:
        for name in (
            "tenant_id",
            "project_id",
            "task_id",
            "execution_id",
            "environment_id",
            "authority_snapshot_id",
        ):
            require_uuid(getattr(self, name), name)
        require_nonempty(self.executor_id, "executor_id", 256)
        if self.executor_generation < 0:
            raise ValueError("executor_generation must be non-negative")
        if digest(dict(self.request)) != self.request_digest:
            raise ValueError("workflow request digest mismatch")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TaskWorkflowInput:
        expected = {
            "tenant_id",
            "project_id",
            "task_id",
            "execution_id",
            "environment_id",
            "authority_snapshot_id",
            "executor_id",
            "executor_generation",
            "request",
            "request_digest",
        }
        if set(value) != expected:
            missing = sorted(expected - set(value))
            unexpected = sorted(set(value) - expected)
            raise ValueError(
                f"invalid workflow input fields: missing={missing}, unexpected={unexpected}"
            )
        request = value["request"]
        if not isinstance(request, Mapping):
            raise TypeError("workflow request must be an object")
        return cls(
            tenant_id=value["tenant_id"],
            project_id=value["project_id"],
            task_id=value["task_id"],
            execution_id=value["execution_id"],
            environment_id=value["environment_id"],
            authority_snapshot_id=value["authority_snapshot_id"],
            executor_id=value["executor_id"],
            executor_generation=value["executor_generation"],
            request=dict(request),
            request_digest=value["request_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "execution_id": self.execution_id,
            "environment_id": self.environment_id,
            "authority_snapshot_id": self.authority_snapshot_id,
            "executor_id": self.executor_id,
            "executor_generation": self.executor_generation,
            "request": dict(self.request),
            "request_digest": self.request_digest,
        }


class WorkflowHandle(Protocol):
    async def signal(self, signal: str, arg: Any = None) -> None: ...
    async def cancel(self) -> None: ...
    async def result(self) -> Any: ...
    async def describe(self) -> Any: ...


class TemporalClient(Protocol):
    async def start_workflow(
        self, workflow: str, arg: Any, **kwargs: Any
    ) -> WorkflowHandle: ...
    def get_workflow_handle(
        self, workflow_id: str, *, run_id: str | None = None
    ) -> WorkflowHandle: ...


class TemporalGateway:
    """Typed gateway. Every workflow id is tenant/task-bound and idempotent."""

    WORKFLOW_NAME = "pi-harness-task-v1"

    def __init__(self, client: TemporalClient, config: TemporalConfig) -> None:
        self.client = client
        self.config = config

    @staticmethod
    def workflow_id(value: TaskWorkflowInput) -> str:
        return f"pi:{value.tenant_id}:{value.task_id}"

    async def start_task(self, value: TaskWorkflowInput) -> dict[str, Any]:
        handle = await self.client.start_workflow(
            self.WORKFLOW_NAME,
            value.to_dict(),
            id=self.workflow_id(value),
            task_queue=self.config.task_queue,
            memo={
                "tenant_id": value.tenant_id,
                "task_id": value.task_id,
                "request_digest": value.request_digest,
            },
        )
        return {
            "workflow_id": self.workflow_id(value),
            "run_id": getattr(handle, "first_execution_run_id", None),
            "request_digest": value.request_digest,
            "state": "SUBMITTED",
        }

    async def pause(self, workflow_id: str, *, reason: str) -> None:
        await self._handle(workflow_id).signal(
            "pause", require_nonempty(reason, "reason", 1000)
        )

    async def resume(
        self, workflow_id: str, *, expected_executor_generation: int
    ) -> None:
        if expected_executor_generation < 0:
            raise ValueError("expected_executor_generation must be non-negative")
        await self._handle(workflow_id).signal("resume", expected_executor_generation)

    async def request_cancel(self, workflow_id: str, *, reason: str) -> None:
        await self._handle(workflow_id).signal(
            "request_cancel", require_nonempty(reason, "reason", 1000)
        )

    async def terminate_after_grace(self, workflow_id: str) -> None:
        await self._handle(workflow_id).cancel()

    async def result(self, workflow_id: str) -> Any:
        return await self._handle(workflow_id).result()

    async def describe(self, workflow_id: str) -> Any:
        return await self._handle(workflow_id).describe()

    def _handle(self, workflow_id: str) -> WorkflowHandle:
        value = require_nonempty(workflow_id, "workflow_id", 512)
        if not value.startswith("pi:") or value.count(":") != 2:
            raise PolicyDeniedError("workflow id is outside the PI Harness namespace")
        return self.client.get_workflow_handle(value)


async def connect_temporal(config: TemporalConfig) -> TemporalGateway:
    """Connect to a real TLS-enabled Temporal service using the optional SDK."""
    try:
        from temporalio.client import Client, TLSConfig
    except ImportError as exc:  # pragma: no cover - optional production extra
        raise RuntimeError(
            "temporalio is required; install elmos-pi-harness[temporal]"
        ) from exc
    for path in (
        config.ca_certificate,
        config.client_certificate,
        config.client_private_key,
    ):
        if not path.is_file() or path.is_symlink():
            raise PolicyDeniedError(
                f"Temporal TLS material is unavailable or unsafe: {path}"
            )
    tls = TLSConfig(
        server_root_ca_cert=config.ca_certificate.read_bytes(),
        client_cert=config.client_certificate.read_bytes(),
        client_private_key=config.client_private_key.read_bytes(),
        domain=config.server_name,
    )
    client = await Client.connect(
        config.target,
        namespace=config.namespace,
        tls=tls,
        identity=config.worker_identity,
    )
    return TemporalGateway(client, config)


async def run_worker(config: TemporalConfig, activities: Sequence[Any]) -> None:
    """Run the versioned workflow worker; activity implementations are injected."""
    if not activities:
        raise ValueError("at least one registered activity is required")
    gateway = await connect_temporal(config)
    try:
        from temporalio.worker import Worker

        from .temporal_workflows import PIHarnessTaskWorkflow
    except ImportError as exc:  # pragma: no cover - optional production extra
        raise RuntimeError(
            "temporalio is required; install elmos-pi-harness[temporal]"
        ) from exc
    worker = Worker(
        gateway.client,
        task_queue=config.task_queue,
        workflows=[PIHarnessTaskWorkflow],
        activities=list(activities),
        identity=config.worker_identity,
        build_id=config.deployment_version,
        use_worker_versioning=True,
    )
    await worker.run()


async def run_task_worker(config: TemporalConfig, service: Any) -> None:
    """Run the complete PI task worker with execute and control activities."""
    from .temporal_activities import build_temporal_activities

    await run_worker(config, build_temporal_activities(service))


async def replay_histories(histories: Sequence[Any]) -> dict[str, Any]:
    """Replay exported Temporal histories against the current workflow code."""
    if not histories:
        return {"status": "NOT_RUN", "replayed": 0, "failures": []}
    try:
        from temporalio.worker import Replayer

        from .temporal_workflows import PIHarnessTaskWorkflow
    except ImportError as exc:  # pragma: no cover - optional production extra
        raise RuntimeError(
            "temporalio is required; install elmos-pi-harness[temporal]"
        ) from exc
    failures: list[dict[str, str]] = []
    replayer = Replayer(workflows=[PIHarnessTaskWorkflow])
    for index, history in enumerate(histories):
        try:
            await replayer.replay_workflow(history)
        except Exception as exc:  # noqa: BLE001 - replay must report every incompatible history
            failures.append(
                {
                    "history_index": str(index),
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:1000],
                }
            )
    return {
        "status": "PASS" if not failures else "FAIL",
        "replayed": len(histories),
        "failures": failures,
    }


def run_worker_sync(config: TemporalConfig, activities: Sequence[Any]) -> None:
    try:
        asyncio.run(run_worker(config, activities))
    except KeyboardInterrupt:
        return
