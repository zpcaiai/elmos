"""Typed domain contracts for the PI Harness boundary.

These types are intentionally provider-neutral.  Adapters may translate their
native payloads at the edge, but the kernel only accepts these representations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .canonical import digest, json_object, require_nonempty, require_uuid


class HarnessError(RuntimeError):
    """Base error which is safe to map to an API problem response."""


class NotFoundError(HarnessError):
    pass


class ConflictError(HarnessError):
    pass


class PolicyDeniedError(HarnessError):
    pass


class StaleGenerationError(ConflictError):
    pass


class LeaseConflictError(ConflictError):
    pass


class QuotaExceededError(ConflictError):
    pass


class InvalidTransitionError(ConflictError):
    pass


class TaskState(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    PAUSED = "PAUSED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    RETRY_QUEUED = "RETRY_QUEUED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


TASK_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.CREATED: frozenset({TaskState.QUEUED, TaskState.CANCEL_REQUESTED}),
    TaskState.QUEUED: frozenset({TaskState.PLANNING, TaskState.RUNNING, TaskState.CANCEL_REQUESTED, TaskState.CANCELLED}),
    TaskState.PLANNING: frozenset({TaskState.RUNNING, TaskState.PAUSED, TaskState.CANCEL_REQUESTED}),
    TaskState.RUNNING: frozenset({TaskState.VERIFYING, TaskState.PAUSED, TaskState.WAITING_APPROVAL, TaskState.CANCEL_REQUESTED, TaskState.FAILED}),
    TaskState.VERIFYING: frozenset({TaskState.RUNNING, TaskState.SUCCEEDED, TaskState.RETRY_QUEUED, TaskState.FAILED, TaskState.CANCEL_REQUESTED}),
    TaskState.WAITING_APPROVAL: frozenset({TaskState.RUNNING, TaskState.CANCEL_REQUESTED, TaskState.CANCELLED}),
    TaskState.PAUSED: frozenset({TaskState.QUEUED, TaskState.RUNNING, TaskState.CANCEL_REQUESTED, TaskState.CANCELLED}),
    TaskState.CANCEL_REQUESTED: frozenset({TaskState.CANCELLED}),
    TaskState.RETRY_QUEUED: frozenset({TaskState.RUNNING, TaskState.CANCELLED}),
    TaskState.CANCELLED: frozenset(),
    TaskState.SUCCEEDED: frozenset(),
    TaskState.FAILED: frozenset({TaskState.RETRY_QUEUED}),
}


TERMINAL_TASK_STATES = frozenset({TaskState.CANCELLED, TaskState.SUCCEEDED, TaskState.FAILED})


@dataclass(frozen=True)
class EnvironmentRef:
    environment_id: str
    owner_execution_id: str
    generation: int
    environment_type: str

    def __post_init__(self) -> None:
        require_uuid(self.environment_id, "environment_id")
        require_uuid(self.owner_execution_id, "owner_execution_id")
        if self.generation < 0:
            raise ValueError("generation must be non-negative")
        require_nonempty(self.environment_type, "environment_type", 64)

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "owner_execution_id": self.owner_execution_id,
            "generation": self.generation,
            "environment_type": self.environment_type,
        }


@dataclass(frozen=True)
class AuthoritySnapshot:
    authority_owner_id: str
    environment_id: str
    permission_profile_version: str
    allowed_capabilities: frozenset[str]
    denied_capabilities: frozenset[str] = frozenset()
    sandbox_overrides: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_uuid(self.authority_owner_id, "authority_owner_id")
        require_uuid(self.environment_id, "environment_id")
        require_nonempty(self.permission_profile_version, "permission_profile_version", 128)
        if not self.allowed_capabilities:
            raise ValueError("allowed_capabilities cannot be empty")
        if not all(isinstance(item, str) and item for item in self.allowed_capabilities | self.denied_capabilities):
            raise ValueError("capabilities must be non-empty strings")
        json_object(dict(self.sandbox_overrides), "sandbox_overrides")

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_owner_id": self.authority_owner_id,
            "environment_id": self.environment_id,
            "permission_profile_version": self.permission_profile_version,
            "allowed_capabilities": sorted(self.allowed_capabilities),
            "denied_capabilities": sorted(self.denied_capabilities),
            "sandbox_overrides": dict(self.sandbox_overrides),
        }

    @property
    def snapshot_digest(self) -> str:
        return digest(self.to_dict())


@dataclass(frozen=True)
class EffectivePolicy:
    allowed_capabilities: frozenset[str]
    denied_capabilities: frozenset[str]
    sandbox_overrides: Mapping[str, Any]
    authority_snapshot_digest: str

    def permits(self, required: set[str] | frozenset[str]) -> bool:
        return set(required).issubset(self.allowed_capabilities - self.denied_capabilities)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": sorted(self.allowed_capabilities),
            "denied": sorted(self.denied_capabilities),
            "sandbox_overrides": dict(self.sandbox_overrides),
            "authority_snapshot_digest": self.authority_snapshot_digest,
        }


@dataclass(frozen=True)
class ExecutorIdentity:
    executor_id: str
    generation: int
    registry_revision: str | None = None

    def __post_init__(self) -> None:
        require_nonempty(self.executor_id, "executor_id", 256)
        if self.generation < 0:
            raise ValueError("generation must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "executor_id": self.executor_id,
            "generation": self.generation,
            "registry_revision": self.registry_revision,
        }


@dataclass(frozen=True)
class WorkspaceLease:
    workspace_id: str
    owner_execution_id: str
    generation: int
    repository_id: str
    base_revision: str
    lifecycle_state: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_nonempty(self.workspace_id, "workspace_id", 256)
        require_uuid(self.owner_execution_id, "owner_execution_id")
        if self.generation < 0:
            raise ValueError("generation must be non-negative")
        require_nonempty(self.repository_id, "repository_id", 2048)
        require_nonempty(self.base_revision, "base_revision", 256)
        require_nonempty(self.lifecycle_state, "lifecycle_state", 64)
        json_object(dict(self.metadata), "metadata")

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "owner_execution_id": self.owner_execution_id,
            "generation": self.generation,
            "repository_id": self.repository_id,
            "base_revision": self.base_revision,
            "lifecycle_state": self.lifecycle_state,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ProtocolCapabilities:
    history_mode: str
    pagination: bool
    typed_tool_result: bool
    schema_dialect: str
    consistency_model: str
    protocol_version: str
    supports_active_turn_lookup: bool = False

    def __post_init__(self) -> None:
        require_nonempty(self.history_mode, "history_mode", 32)
        require_nonempty(self.schema_dialect, "schema_dialect", 256)
        require_nonempty(self.consistency_model, "consistency_model", 64)
        require_nonempty(self.protocol_version, "protocol_version", 64)

    def to_dict(self) -> dict[str, Any]:
        return {
            "history_mode": self.history_mode,
            "pagination": self.pagination,
            "typed_tool_result": self.typed_tool_result,
            "schema_dialect": self.schema_dialect,
            "consistency_model": self.consistency_model,
            "protocol_version": self.protocol_version,
            "supports_active_turn_lookup": self.supports_active_turn_lookup,
        }


@dataclass(frozen=True)
class InstructionEnvelope:
    text: str
    source: str
    scope: str
    provenance: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_nonempty(self.text, "text", 1_000_000)
        require_nonempty(self.source, "source", 256)
        require_nonempty(self.scope, "scope", 256)
        json_object(dict(self.provenance), "provenance")

    @property
    def envelope_digest(self) -> str:
        return digest({"text": self.text, "source": self.source, "scope": self.scope, "provenance": dict(self.provenance)})


@dataclass(frozen=True)
class ToolInvocation:
    call_id: str
    task_id: str
    environment_id: str
    authority_snapshot_id: str
    capability: str
    args: Mapping[str, Any]
    idempotency_key: str
    timeout_ms: int
    sandbox_profile: str
    required_capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        require_uuid(self.call_id, "call_id")
        require_uuid(self.task_id, "task_id")
        require_uuid(self.environment_id, "environment_id")
        require_uuid(self.authority_snapshot_id, "authority_snapshot_id")
        require_nonempty(self.capability, "capability", 256)
        require_nonempty(self.idempotency_key, "idempotency_key", 256)
        require_nonempty(self.sandbox_profile, "sandbox_profile", 128)
        if not 1 <= self.timeout_ms <= 86_400_000:
            raise ValueError("timeout_ms must be between 1 and 86400000")
        json_object(dict(self.args), "args")

    @property
    def request_digest(self) -> str:
        return digest({
            "task_id": self.task_id,
            "environment_id": self.environment_id,
            "authority_snapshot_id": self.authority_snapshot_id,
            "capability": self.capability,
            "args": dict(self.args),
            "timeout_ms": self.timeout_ms,
            "sandbox_profile": self.sandbox_profile,
            "required_capabilities": sorted(self.required_capabilities),
        })


@dataclass(frozen=True)
class TextContent:
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


@dataclass(frozen=True)
class MediaContent:
    media_type: str
    uri: str | None = None
    data_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.uri and not self.data_ref:
            raise ValueError("media content requires uri or data_ref")

    def to_dict(self) -> dict[str, Any]:
        return {"type": "media", "media_type": self.media_type, "uri": self.uri, "data_ref": self.data_ref}


@dataclass(frozen=True)
class EncryptedContent:
    ciphertext_ref: str
    algorithm: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": "encrypted", "ciphertext_ref": self.ciphertext_ref, "algorithm": self.algorithm}


@dataclass(frozen=True)
class UnknownContent:
    raw: Any

    def to_dict(self) -> dict[str, Any]:
        return {"type": "unknown", "raw": self.raw}


TypedContent = TextContent | MediaContent | EncryptedContent | UnknownContent


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    items: tuple[TypedContent, ...]
    status: str = "completed"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_uuid(self.call_id, "call_id")
        if self.status not in {"completed", "failed", "cancelled", "timed_out", "authentication_required", "stale"}:
            raise ValueError("invalid tool result status")
        json_object(dict(self.metadata), "metadata")

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "items": [item.to_dict() for item in self.items],
            "status": self.status,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ToolResult:
        items: list[TypedContent] = []
        for raw in value.get("items", []):
            if not isinstance(raw, Mapping):
                items.append(UnknownContent(raw))
                continue
            kind = raw.get("type")
            if kind == "text":
                items.append(TextContent(str(raw.get("text", ""))))
            elif kind == "media":
                items.append(MediaContent(str(raw.get("media_type", "application/octet-stream")), raw.get("uri"), raw.get("data_ref")))
            elif kind == "encrypted":
                items.append(EncryptedContent(str(raw.get("ciphertext_ref", "")), str(raw.get("algorithm", ""))))
            else:
                items.append(UnknownContent(dict(raw)))
        return cls(str(value["call_id"]), tuple(items), str(value.get("status", "completed")), dict(value.get("metadata", {})))
