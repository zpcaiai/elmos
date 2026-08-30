"""Versioned, immutable-ish contract values shared by every runtime boundary."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .errors import ContractViolation

SCHEMA_VERSION = "1.0"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest_of(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ContractViolation(f"{field_name} must be a bounded identifier")
    return value


class RunStatus(StrEnum):
    QUEUED = "queued"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class RiskLevel(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    R5 = "R5"
    R6 = "R6"


@dataclass(frozen=True, slots=True)
class Identity:
    tenant_id: str
    project_id: str
    task_id: str
    run_id: str
    node_id: str = "root"
    agent_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("tenant_id", "project_id", "task_id", "run_id", "node_id"):
            validate_id(getattr(self, name), name)
        if self.agent_id is not None:
            validate_id(self.agent_id, "agent_id")

    def scope(self) -> tuple[str, str, str, str, str]:
        return self.tenant_id, self.project_id, self.task_id, self.run_id, self.node_id


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    tenant_id: str
    digest: str
    size_bytes: int
    media_type: str = "application/octet-stream"
    kind: str = "artifact"

    def __post_init__(self) -> None:
        validate_id(self.tenant_id, "tenant_id")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.digest):
            raise ContractViolation("artifact digest must be sha256: plus 64 lowercase hex characters")
        if self.size_bytes < 0:
            raise ContractViolation("artifact size cannot be negative")
        validate_id(self.kind, "artifact.kind")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExecutionManifest:
    repo_revision: str
    policy_version: str
    provider: str
    model: str
    package_versions: Mapping[str, str] = field(default_factory=dict)
    tool_versions: Mapping[str, str] = field(default_factory=dict)
    isolation_class: str = "L0"
    region: str = "local"
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("repo_revision", "policy_version", "provider", "model", "isolation_class", "region"):
            if not getattr(self, name):
                raise ContractViolation(f"manifest.{name} is required")
        if self.schema_version != SCHEMA_VERSION:
            raise ContractViolation(f"unsupported manifest schema version: {self.schema_version}")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def digest(self) -> str:
        return digest_of(self.as_dict())


@dataclass(frozen=True, slots=True)
class Budget:
    max_wall_seconds: float = 900.0
    max_input_tokens: int = 100_000
    max_output_tokens: int = 50_000
    max_tool_calls: int = 100
    max_cost_micros: int = 10_000_000

    def __post_init__(self) -> None:
        if self.max_wall_seconds <= 0 or any(
            value < 0
            for value in (
                self.max_input_tokens,
                self.max_output_tokens,
                self.max_tool_calls,
                self.max_cost_micros,
            )
        ):
            raise ContractViolation("budget limits must be positive or zero")


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0
    cost_micros: int = 0
    provider_latency_ms: int = 0

    def __post_init__(self) -> None:
        if any(value < 0 for value in (self.input_tokens, self.output_tokens, self.cached_input_tokens, self.reasoning_tokens, self.cost_micros, self.provider_latency_ms)):
            raise ContractViolation("usage values cannot be negative")

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Action:
    action_id: str
    tool: str
    args: Mapping[str, Any]
    risk_context: Mapping[str, Any]
    idempotency_key: str
    read_scope: tuple[str, ...] = ()
    write_scope: tuple[str, ...] = ()
    expected_side_effects: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    timeout_seconds: float = 30.0
    risk_hint: RiskLevel | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_id(self.action_id, "action_id")
        validate_id(self.tool, "tool")
        validate_id(self.idempotency_key, "idempotency_key")
        if not isinstance(self.args, Mapping) or not isinstance(self.risk_context, Mapping):
            raise ContractViolation("action args and risk_context must be objects")
        for field_name in ("read_scope", "write_scope", "expected_side_effects", "required_capabilities"):
            value = getattr(self, field_name)
            if isinstance(value, str) or not all(isinstance(item, str) and item for item in value):
                raise ContractViolation(f"action.{field_name} must be a tuple of non-empty strings")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 86_400:
            raise ContractViolation("action timeout must be in (0, 86400]")
        if self.schema_version != SCHEMA_VERSION:
            raise ContractViolation("unsupported action schema version")

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["kind"] = "action"
        if self.risk_hint is not None:
            result["risk_hint"] = self.risk_hint.value
        return result


@dataclass(frozen=True, slots=True)
class Observation:
    action_id: str
    status: ActionStatus
    result: Any = None
    artifacts: tuple[ArtifactRef, ...] = ()
    metrics: Mapping[str, Any] = field(default_factory=dict)
    error: Mapping[str, Any] | None = None
    changed_resources: tuple[str, ...] = ()
    reconciliation_hint: str | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_id(self.action_id, "action_id")
        if self.schema_version != SCHEMA_VERSION:
            raise ContractViolation("unsupported observation schema version")

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "observation",
            "action_id": self.action_id,
            "status": self.status.value,
            "result": self.result,
            "artifacts": [ref.as_dict() for ref in self.artifacts],
            "metrics": dict(self.metrics),
            "error": self.error,
            "changed_resources": list(self.changed_resources),
            "reconciliation_hint": self.reconciliation_hint,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class CompletionProposal:
    run_id: str
    summary: str
    claimed_status: str = "succeeded"
    evidence_refs: tuple[ArtifactRef, ...] = ()
    requirement_refs: tuple[str, ...] = ()
    test_refs: tuple[str, ...] = ()
    provider_text: str | None = None

    def __post_init__(self) -> None:
        validate_id(self.run_id, "run_id")
        if self.claimed_status not in {"succeeded", "failed", "blocked"}:
            raise ContractViolation("completion proposal status is invalid")


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    tenant_id: str
    run_id: str
    seq: int
    event_type: str
    payload: Mapping[str, Any]
    timestamp: str
    node_id: str | None = None
    agent_id: str | None = None
    causation_event_id: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    artifact_refs: tuple[ArtifactRef, ...] = ()
    policy_decision: Mapping[str, Any] | None = None
    usage: Usage | None = None
    cost: Mapping[str, Any] | None = None
    previous_digest: str | None = None
    digest: str | None = None
    schema_version: str = SCHEMA_VERSION

    def body(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "run_id": self.run_id,
            "seq": self.seq,
            "event_type": self.event_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "causation_event_id": self.causation_event_id,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "artifact_refs": [ref.as_dict() for ref in self.artifact_refs],
            "policy_decision": self.policy_decision,
            "usage": None if self.usage is None else self.usage.as_dict(),
            "cost": self.cost,
            "previous_digest": self.previous_digest,
            "schema_version": self.schema_version,
        }

    def computed_digest(self) -> str:
        return digest_of(self.body())

    def as_dict(self) -> dict[str, Any]:
        value = self.body()
        value["digest"] = self.digest or self.computed_digest()
        return value


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision_id: str
    decision: str
    risk_level: RiskLevel
    rules: tuple[str, ...]
    reasons: tuple[str, ...]
    policy_version: str
    approved_by: str | None = None

    def __post_init__(self) -> None:
        if self.decision not in {"allow", "deny", "require_approval"}:
            raise ContractViolation("policy decision is invalid")

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["risk_level"] = self.risk_level.value
        return result


def new_id() -> str:
    return str(uuid.uuid4())
