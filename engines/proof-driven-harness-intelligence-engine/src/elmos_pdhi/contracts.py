"""Immutable typed contracts for Proof-Driven Harness Intelligence v1.

The eight source-declared contracts are represented without permissive
``Any`` payload shortcuts at authoritative fields. Repository, tenant, actor,
revision, workspace, lease and fence bindings are carried by ``ResourceScope``
and ``ExecutionContext`` and can be required by mutating runtime operations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

from .canonical import (
    canonical_json_bytes,
    digest_object,
    freeze_json,
    require_sha256_digest,
    strict_json_loads,
    utc_now,
)
from .errors import AuthorizationError, ValidationError


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class FailureClass(StrEnum):
    TRANSIENT_PROVIDER = "TRANSIENT_PROVIDER"
    QUOTA_PROVIDER = "QUOTA_PROVIDER"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    STALE_STATE = "STALE_STATE"
    POLICY = "POLICY"
    SEMANTIC = "SEMANTIC"
    COMPILE = "COMPILE"
    TEST = "TEST"
    RUNTIME_EQUIVALENCE = "RUNTIME_EQUIVALENCE"
    SECURITY = "SECURITY"
    PERFORMANCE = "PERFORMANCE"
    MERGE_CONFLICT = "MERGE_CONFLICT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    USER_CANCELLED = "USER_CANCELLED"
    UNKNOWN = "UNKNOWN"


class AgentResultStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    QUARANTINED = "QUARANTINED"


class VerificationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_RUN = "NOT_RUN"
    UNKNOWN = "UNKNOWN"


class PatchTransactionStatus(StrEnum):
    PREPARED = "PREPARED"
    PRECONDITIONS_VALID = "PRECONDITIONS_VALID"
    APPLIED = "APPLIED"
    VERIFIED = "VERIFIED"
    COMMITTED = "COMMITTED"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    APPLY_FAILED = "APPLY_FAILED"
    POSTCONDITION_FAILED = "POSTCONDITION_FAILED"
    CONFLICTED = "CONFLICTED"
    ROLLED_BACK = "ROLLED_BACK"
    QUARANTINED = "QUARANTINED"


class DurableJobStatus(StrEnum):
    QUEUED = "QUEUED"
    PREFLIGHT = "PREFLIGHT"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    CERTIFYING = "CERTIFYING"
    READY_TO_RELEASE = "READY_TO_RELEASE"
    RELEASED = "RELEASED"
    PAUSED = "PAUSED"
    BLOCKED = "BLOCKED"
    RETRYING = "RETRYING"
    ROLLING_BACK = "ROLLING_BACK"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    QUARANTINED = "QUARANTINED"


class EvidenceStatus(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    STALE = "STALE"
    REVOKED = "REVOKED"
    NOT_RUN = "NOT_RUN"


class AuthorityLevel(StrEnum):
    FORMAL_PROOF = "formal_proof"
    COMPILER = "compiler"
    LSP = "lsp"
    SEMANTIC_IR = "semantic_ir"
    AST = "ast"
    RUNTIME_EVIDENCE = "runtime_evidence"
    TEXT_SEARCH = "text_search"
    LLM_INFERENCE = "llm_inference"


class RuleEnforcement(StrEnum):
    CONTEXT = "CONTEXT"
    JIT_GUARD = "JIT_GUARD"
    INTERRUPT = "INTERRUPT"
    BLOCK = "BLOCK"
    AUTO_REPAIR = "AUTO_REPAIR"
    AUDIT = "AUDIT"


class SkillLifecycleStatus(StrEnum):
    DRAFT = "DRAFT"
    EXPERIMENTAL = "EXPERIMENTAL"
    REGRESSION_TESTED = "REGRESSION_TESTED"
    GOLDEN_ROUTE_TESTED = "GOLDEN_ROUTE_TESTED"
    CERTIFIED = "CERTIFIED"
    PRODUCTION = "PRODUCTION"
    DEPRECATED = "DEPRECATED"


class CertificationLevel(StrEnum):
    E0 = "E0"
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"
    E5 = "E5"


class GateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_REQUIRED = "NOT_REQUIRED"


class CertificationVerdict(StrEnum):
    PASS = "PASS"
    CONDITIONAL_PASS = "CONDITIONAL_PASS"
    FAIL = "FAIL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


def _require_text(
    value: object,
    field_name: str,
    *,
    max_length: int = 16_384,
    identifier: bool = False,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(
            f"{field_name} is required",
            code="INVALID_TEXT",
            details={"field": field_name},
        )
    if "\x00" in value or len(value) > max_length:
        raise ValidationError(
            f"{field_name} is invalid",
            code="INVALID_TEXT",
            details={"field": field_name},
        )
    if identifier and _IDENTIFIER.fullmatch(value) is None:
        raise ValidationError(
            f"{field_name} is not a canonical identifier",
            code="INVALID_IDENTIFIER",
            details={"field": field_name},
        )
    return value


def _require_enum(value: object, enum_type: type[StrEnum], field_name: str) -> None:
    if not isinstance(value, enum_type):
        raise ValidationError(
            f"{field_name} must be {enum_type.__name__}",
            code="INVALID_ENUM",
            details={"field": field_name},
        )


def _require_text_tuple(
    value: object,
    field_name: str,
    *,
    nonempty: bool = False,
    identifiers: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValidationError(
            f"{field_name} must be a tuple",
            code="INVALID_SEQUENCE",
            details={"field": field_name},
        )
    if nonempty and not value:
        raise ValidationError(
            f"{field_name} cannot be empty",
            code="EMPTY_SEQUENCE",
            details={"field": field_name},
        )
    for item in value:
        _require_text(item, field_name, identifier=identifiers)
    if len(set(value)) != len(value):
        raise ValidationError(
            f"{field_name} contains duplicates",
            code="DUPLICATE_VALUE",
            details={"field": field_name},
        )
    return value


def _require_mapping(
    value: object,
    field_name: str,
    *,
    nonempty: bool = False,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(
            f"{field_name} must be an object",
            code="INVALID_OBJECT",
            details={"field": field_name},
        )
    if nonempty and not value:
        raise ValidationError(
            f"{field_name} cannot be empty",
            code="EMPTY_OBJECT",
            details={"field": field_name},
        )
    frozen = freeze_json(value)
    if not isinstance(frozen, Mapping):  # defensive type narrowing
        raise ValidationError(f"{field_name} must be an object")
    return frozen


def _require_decimal(
    value: object,
    field_name: str,
    *,
    minimum: Decimal = Decimal("0"),
    maximum: Decimal | None = None,
) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValidationError(
            f"{field_name} must be a finite Decimal",
            code="INVALID_DECIMAL",
            details={"field": field_name},
        )
    if value < minimum or (maximum is not None and value > maximum):
        raise ValidationError(
            f"{field_name} is outside its allowed range",
            code="DECIMAL_OUT_OF_RANGE",
            details={"field": field_name},
        )
    return value


def _require_aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(
            f"{field_name} must be a timezone-aware datetime",
            code="INVALID_TIMESTAMP",
            details={"field": field_name},
        )
    return value


def _scope_path(value: str, field_name: str, *, allow_root: bool = True) -> str:
    _require_text(value, field_name, max_length=2048)
    if "\\" in value or any(ord(char) < 32 for char in value):
        raise ValidationError(
            f"{field_name} is not a canonical POSIX scope",
            code="INVALID_SCOPE",
        )
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValidationError(
            f"{field_name} escapes the repository",
            code="SCOPE_ESCAPE",
        )
    normalized = path.as_posix()
    if normalized == "." and not allow_root:
        raise ValidationError(f"{field_name} cannot be repository root")
    if normalized != value.rstrip("/") and not (value == "." and normalized == "."):
        raise ValidationError(
            f"{field_name} is not normalized",
            code="NON_CANONICAL_SCOPE",
        )
    if any(char in normalized for char in "*?[]{}"):
        raise ValidationError(
            f"{field_name} cannot use wildcard authority",
            code="WILDCARD_SCOPE",
        )
    return normalized


def _within_scope(target: str, allowed: str) -> bool:
    return allowed == "." or target == allowed or target.startswith(allowed + "/")


class CanonicalContract:
    """Common canonical serialization for immutable contracts."""

    def to_dict(self) -> dict[str, Any]:
        value = strict_json_loads(canonical_json_bytes(self), source=type(self).__name__)
        if not isinstance(value, dict):
            raise AssertionError("contract canonical form must be an object")
        return value

    def content_digest(self) -> str:
        return digest_object(self, domain=f"contract:{type(self).__name__}")


@dataclass(frozen=True, slots=True)
class ResourceScope(CanonicalContract):
    tenant_id: str
    project_id: str
    repository_id: str
    input_revision: str
    read_scope: tuple[str, ...]
    write_scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("tenant_id", "project_id", "repository_id", "input_revision"):
            _require_text(getattr(self, name), name, identifier=True)
        _require_text_tuple(self.read_scope, "read_scope", nonempty=True)
        _require_text_tuple(self.write_scope, "write_scope")
        for scope in self.read_scope:
            _scope_path(scope, "read_scope")
        for scope in self.write_scope:
            _scope_path(scope, "write_scope")
            if not any(_within_scope(scope, readable) for readable in self.read_scope):
                raise ValidationError(
                    "write scope must be contained by read scope",
                    code="WRITE_SCOPE_NOT_READABLE",
                    details={"scope": scope},
                )

    def require_read(self, target: str) -> str:
        normalized = _scope_path(target, "target")
        if not any(_within_scope(normalized, allowed) for allowed in self.read_scope):
            raise AuthorizationError(
                "target is outside read scope",
                code="READ_SCOPE_DENIED",
                details={"target": normalized},
            )
        return normalized

    def require_write(self, target: str) -> str:
        normalized = _scope_path(target, "target")
        if not any(_within_scope(normalized, allowed) for allowed in self.write_scope):
            raise AuthorizationError(
                "target is outside write scope",
                code="WRITE_SCOPE_DENIED",
                details={"target": normalized},
            )
        return normalized


@dataclass(frozen=True, slots=True)
class ExecutionContext(CanonicalContract):
    scope: ResourceScope
    actor_id: str
    job_id: str
    task_id: str
    authority_profile: str
    idempotency_key: str
    workspace_id: str | None = None
    lease_id: str | None = None
    fence_token: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ResourceScope):
            raise ValidationError("scope must be ResourceScope", code="INVALID_SCOPE")
        for name in (
            "actor_id",
            "job_id",
            "task_id",
            "authority_profile",
            "idempotency_key",
        ):
            _require_text(getattr(self, name), name, identifier=True)
        bindings = (self.workspace_id, self.lease_id, self.fence_token)
        if self.scope.write_scope and any(item is None for item in bindings):
            raise ValidationError(
                "write-capable context requires workspace, lease and fence",
                code="INCOMPLETE_WRITE_AUTHORITY",
            )
        if not self.scope.write_scope and any(item is not None for item in bindings):
            raise ValidationError(
                "read-only context cannot carry partial write authority",
                code="UNEXPECTED_WRITE_AUTHORITY",
            )
        if self.workspace_id is not None:
            _require_text(self.workspace_id, "workspace_id", identifier=True)
            _require_text(self.lease_id, "lease_id", identifier=True)
            if isinstance(self.fence_token, bool) or not isinstance(self.fence_token, int) or self.fence_token < 1:
                raise ValidationError(
                    "fence_token must be a positive integer",
                    code="INVALID_FENCE_TOKEN",
                )

    def require_read(self, target: str) -> str:
        return self.scope.require_read(target)

    def require_write(self, target: str) -> str:
        if self.workspace_id is None or self.lease_id is None or self.fence_token is None:
            raise AuthorizationError(
                "context has no write authority", code="WRITE_AUTHORITY_REQUIRED"
            )
        return self.scope.require_write(target)


@dataclass(frozen=True, slots=True)
class AgentTask(CanonicalContract):
    task_id: str
    project_id: str
    job_id: str
    goal: str
    input_revision: str
    read_scope: tuple[str, ...]
    write_scope: tuple[str, ...]
    authority_profile: str
    output_schema: Mapping[str, Any]
    invariants: tuple[str, ...]
    model_role: str | None = None
    model_candidates: tuple[str, ...] = ()
    effort_ceiling: int | None = None
    token_budget: int | None = None
    cost_budget: Decimal | None = None
    wall_clock_budget: int | None = None
    dependencies: tuple[str, ...] = ()
    workspace_id: str | None = None
    lease_id: str | None = None
    fence_token: int | None = None
    certification_target: CertificationLevel | None = None

    def __post_init__(self) -> None:
        for name in ("task_id", "project_id", "job_id", "input_revision", "authority_profile"):
            _require_text(getattr(self, name), name, identifier=True)
        _require_text(self.goal, "goal")
        _require_text_tuple(self.read_scope, "read_scope", nonempty=True)
        _require_text_tuple(self.write_scope, "write_scope")
        for scope in self.read_scope:
            _scope_path(scope, "read_scope")
        for scope in self.write_scope:
            _scope_path(scope, "write_scope")
            if not any(_within_scope(scope, readable) for readable in self.read_scope):
                raise ValidationError(
                    "write scope must be contained by read scope",
                    code="WRITE_SCOPE_NOT_READABLE",
                    details={"scope": scope},
                )
        object.__setattr__(self, "output_schema", _require_mapping(self.output_schema, "output_schema", nonempty=True))
        _require_text_tuple(self.invariants, "invariants", nonempty=True)
        _require_text_tuple(self.model_candidates, "model_candidates")
        _require_text_tuple(self.dependencies, "dependencies", identifiers=True)
        if self.model_role is not None:
            _require_text(self.model_role, "model_role", identifier=True)
        for name in ("effort_ceiling", "token_budget", "wall_clock_budget"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
                raise ValidationError(f"{name} must be a positive integer", code="INVALID_BUDGET")
        if self.cost_budget is not None:
            _require_decimal(self.cost_budget, "cost_budget")
        bindings = (self.workspace_id, self.lease_id, self.fence_token)
        if self.write_scope and any(item is None for item in bindings):
            raise ValidationError(
                "write-capable task requires workspace, lease and fence",
                code="INCOMPLETE_WRITE_AUTHORITY",
            )
        if not self.write_scope and any(item is not None for item in bindings):
            raise ValidationError(
                "read-only task cannot carry write authority",
                code="UNEXPECTED_WRITE_AUTHORITY",
            )
        if self.workspace_id is not None:
            _require_text(self.workspace_id, "workspace_id", identifier=True)
            _require_text(self.lease_id, "lease_id", identifier=True)
            if isinstance(self.fence_token, bool) or not isinstance(self.fence_token, int) or self.fence_token < 1:
                raise ValidationError("fence_token must be positive", code="INVALID_FENCE_TOKEN")
        if self.certification_target is not None:
            _require_enum(self.certification_target, CertificationLevel, "certification_target")


@dataclass(frozen=True, slots=True)
class ProofCarryingAgentResult(CanonicalContract):
    task_id: str
    status: AgentResultStatus
    changed_artifacts: tuple[str, ...]
    evidence: tuple[str, ...]
    findings: tuple[str, ...]
    unresolved: tuple[str, ...]
    verification_status: VerificationStatus
    assumptions: tuple[str, ...] = ()
    semantic_diff: Mapping[str, Any] | None = None
    runtime_diff: Mapping[str, Any] | None = None
    tests: tuple[str, ...] = ()
    proofs: tuple[str, ...] = ()
    confidence: Decimal | None = None
    rollback_token: str | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.task_id, "task_id", identifier=True)
        _require_enum(self.status, AgentResultStatus, "status")
        _require_enum(self.verification_status, VerificationStatus, "verification_status")
        for name in ("changed_artifacts", "evidence", "findings", "unresolved", "assumptions", "tests", "proofs"):
            _require_text_tuple(getattr(self, name), name)
        if self.status is AgentResultStatus.SUCCEEDED:
            if self.verification_status is not VerificationStatus.PASS or not self.evidence:
                raise ValidationError(
                    "successful result requires PASS verification and evidence",
                    code="UNPROVED_SUCCESS",
                )
        if self.semantic_diff is not None:
            object.__setattr__(self, "semantic_diff", _require_mapping(self.semantic_diff, "semantic_diff"))
        if self.runtime_diff is not None:
            object.__setattr__(self, "runtime_diff", _require_mapping(self.runtime_diff, "runtime_diff"))
        if self.confidence is not None:
            _require_decimal(self.confidence, "confidence", maximum=Decimal("1"))
        if self.rollback_token is not None:
            _require_text(self.rollback_token, "rollback_token", identifier=True)
        object.__setattr__(self, "metrics", _require_mapping(self.metrics, "metrics"))


@dataclass(frozen=True, slots=True)
class PatchTransaction(CanonicalContract):
    transaction_id: str
    base_revision: str
    target_scope: tuple[str, ...]
    intent: str
    preconditions: tuple[str, ...]
    read_set: tuple[str, ...]
    write_set: tuple[str, ...]
    postconditions: tuple[str, ...]
    rollback: Mapping[str, Any]
    syntax_anchor: str | None = None
    semantic_anchor: str | None = None
    rule_ids: tuple[str, ...] = ()
    expected_reference_count: int | None = None
    status: PatchTransactionStatus = PatchTransactionStatus.PREPARED

    def __post_init__(self) -> None:
        for name in ("transaction_id", "base_revision"):
            _require_text(getattr(self, name), name, identifier=True)
        _require_text(self.intent, "intent")
        for name, nonempty in (("target_scope", True), ("preconditions", True), ("read_set", False), ("write_set", True), ("postconditions", True), ("rule_ids", False)):
            _require_text_tuple(getattr(self, name), name, nonempty=nonempty)
        for scope in self.target_scope:
            _scope_path(scope, "target_scope")
        for path in self.read_set:
            _scope_path(path, "read_set")
        for path in self.write_set:
            _scope_path(path, "write_set")
            if not any(_within_scope(path, scope) for scope in self.target_scope):
                raise ValidationError(
                    "write_set path is outside target_scope",
                    code="WRITE_SET_OUTSIDE_TARGET",
                    details={"path": path},
                )
        object.__setattr__(self, "rollback", _require_mapping(self.rollback, "rollback", nonempty=True))
        for name in ("syntax_anchor", "semantic_anchor"):
            value = getattr(self, name)
            if value is not None:
                _require_text(value, name, identifier=True)
        if self.expected_reference_count is not None and (
            isinstance(self.expected_reference_count, bool)
            or not isinstance(self.expected_reference_count, int)
            or self.expected_reference_count < 0
        ):
            raise ValidationError("expected_reference_count must be non-negative")
        _require_enum(self.status, PatchTransactionStatus, "status")


@dataclass(frozen=True, slots=True)
class EvidenceRecord(CanonicalContract):
    evidence_id: str
    evidence_type: str
    producer: str
    produced_at: datetime
    input_digests: tuple[str, ...]
    artifact_digest: str
    tool_version: str
    model: str | None = None
    runtime: str | None = None
    environment: str | None = None
    confidence: Decimal | None = None
    related_findings: tuple[str, ...] = ()
    scope: ResourceScope | None = None
    status: EvidenceStatus = EvidenceStatus.VALID

    def __post_init__(self) -> None:
        for name in ("evidence_id", "evidence_type", "producer", "tool_version"):
            _require_text(getattr(self, name), name, identifier=True)
        _require_aware(self.produced_at, "produced_at")
        _require_text_tuple(self.input_digests, "input_digests", nonempty=True)
        for index, digest in enumerate(self.input_digests):
            require_sha256_digest(digest, field=f"input_digests[{index}]")
        require_sha256_digest(self.artifact_digest, field="artifact_digest")
        for name in ("model", "runtime", "environment"):
            value = getattr(self, name)
            if value is not None:
                _require_text(value, name)
        if self.confidence is not None:
            _require_decimal(self.confidence, "confidence", maximum=Decimal("1"))
        _require_text_tuple(self.related_findings, "related_findings")
        if self.scope is not None and not isinstance(self.scope, ResourceScope):
            raise ValidationError("scope must be ResourceScope", code="INVALID_SCOPE")
        _require_enum(self.status, EvidenceStatus, "status")


@dataclass(frozen=True, slots=True)
class DurableJobState(CanonicalContract):
    job_id: str
    state: DurableJobStatus
    version: int
    last_durable_checkpoint: str
    completed_effects: tuple[str, ...]
    pending_effects: tuple[str, ...]
    active_agents: tuple[str, ...] = ()
    leases: tuple[str, ...] = ()
    retries: Mapping[str, int] = field(default_factory=dict)
    provider_sessions: tuple[str, ...] = ()
    cost: Decimal = Decimal("0")
    tokens: int = 0
    wall_clock: int = 0

    def __post_init__(self) -> None:
        _require_text(self.job_id, "job_id", identifier=True)
        _require_enum(self.state, DurableJobStatus, "state")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValidationError("version must be positive", code="INVALID_VERSION")
        _require_text(self.last_durable_checkpoint, "last_durable_checkpoint", identifier=True)
        for name in ("completed_effects", "pending_effects", "active_agents", "leases", "provider_sessions"):
            _require_text_tuple(getattr(self, name), name)
        if not isinstance(self.retries, Mapping):
            raise ValidationError("retries must be an object")
        normalized_retries: dict[str, int] = {}
        for key, value in self.retries.items():
            _require_text(key, "retries.key", identifier=True)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValidationError("retry count must be non-negative")
            normalized_retries[key] = value
        object.__setattr__(self, "retries", MappingProxyType(dict(sorted(normalized_retries.items()))))
        _require_decimal(self.cost, "cost")
        for name in ("tokens", "wall_clock"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValidationError(f"{name} must be non-negative")


@dataclass(frozen=True, slots=True)
class RuleIR(CanonicalContract):
    rule_id: str
    namespace: str
    name: str
    version: str
    authority: AuthorityLevel
    scope: tuple[str, ...]
    enforcement: RuleEnforcement
    trigger: Mapping[str, Any] | None = None
    invariant: str | None = None
    evidence_requirement: tuple[str, ...] = ()
    remediation: str | None = None
    compatibility: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for name in ("rule_id", "namespace", "name"):
            _require_text(getattr(self, name), name, identifier=True)
        _require_text(self.version, "version")
        if _SEMVER.fullmatch(self.version) is None:
            raise ValidationError("version must be semantic version", code="INVALID_VERSION")
        _require_enum(self.authority, AuthorityLevel, "authority")
        _require_enum(self.enforcement, RuleEnforcement, "enforcement")
        _require_text_tuple(self.scope, "scope", nonempty=True)
        for item in self.scope:
            _scope_path(item, "scope")
        if self.trigger is not None:
            object.__setattr__(self, "trigger", _require_mapping(self.trigger, "trigger", nonempty=True))
        if self.invariant is not None:
            _require_text(self.invariant, "invariant")
        _require_text_tuple(self.evidence_requirement, "evidence_requirement")
        if self.remediation is not None:
            _require_text(self.remediation, "remediation")
        if self.compatibility is not None:
            object.__setattr__(self, "compatibility", _require_mapping(self.compatibility, "compatibility"))


@dataclass(frozen=True, slots=True)
class SkillManifest(CanonicalContract):
    skill_id: str
    namespace: str
    name: str
    version: str
    status: SkillLifecycleStatus
    triggers: tuple[str, ...]
    inputs: Mapping[str, Any]
    outputs: Mapping[str, Any]
    acceptance: tuple[str, ...]
    fixtures: tuple[str, ...] = ()
    golden_routes: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    deprecation: str | None = None
    lineage: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("skill_id", "namespace", "name"):
            _require_text(getattr(self, name), name, identifier=True)
        _require_text(self.version, "version")
        if _SEMVER.fullmatch(self.version) is None:
            raise ValidationError("version must be semantic version", code="INVALID_VERSION")
        _require_enum(self.status, SkillLifecycleStatus, "status")
        for name, nonempty in (("triggers", True), ("acceptance", True), ("fixtures", False), ("golden_routes", False), ("dependencies", False), ("conflicts", False), ("lineage", False)):
            _require_text_tuple(getattr(self, name), name, nonempty=nonempty)
        object.__setattr__(self, "inputs", _require_mapping(self.inputs, "inputs", nonempty=True))
        object.__setattr__(self, "outputs", _require_mapping(self.outputs, "outputs", nonempty=True))
        if self.deprecation is not None:
            _require_text(self.deprecation, "deprecation")


@dataclass(frozen=True, slots=True)
class CertificationBundle(CanonicalContract):
    project_id: str
    job_id: str
    source_revision: str
    target_revision: str
    target_level: CertificationLevel
    gates: Mapping[str, GateStatus]
    findings: tuple[str, ...]
    residual_risks: tuple[str, ...]
    verdict: CertificationVerdict
    evidence_index: Mapping[str, str]

    def __post_init__(self) -> None:
        for name in ("project_id", "job_id", "source_revision", "target_revision"):
            _require_text(getattr(self, name), name, identifier=True)
        _require_enum(self.target_level, CertificationLevel, "target_level")
        _require_enum(self.verdict, CertificationVerdict, "verdict")
        if not isinstance(self.gates, Mapping) or set(self.gates) != {level.value for level in CertificationLevel}:
            raise ValidationError(
                "gates must contain exactly E0 through E5",
                code="INCOMPLETE_GATES",
            )
        normalized_gates: dict[str, GateStatus] = {}
        for level in CertificationLevel:
            value = self.gates[level.value]
            _require_enum(value, GateStatus, f"gates.{level.value}")
            normalized_gates[level.value] = value
        object.__setattr__(self, "gates", MappingProxyType(normalized_gates))
        _require_text_tuple(self.findings, "findings")
        _require_text_tuple(self.residual_risks, "residual_risks")
        if not isinstance(self.evidence_index, Mapping):
            raise ValidationError("evidence_index must be an object")
        normalized_index: dict[str, str] = {}
        for evidence_id, digest in self.evidence_index.items():
            _require_text(evidence_id, "evidence_index.key", identifier=True)
            require_sha256_digest(digest, field=f"evidence_index.{evidence_id}")
            normalized_index[evidence_id] = digest
        object.__setattr__(self, "evidence_index", MappingProxyType(dict(sorted(normalized_index.items()))))
        statuses = tuple(normalized_gates.values())
        if self.verdict in {CertificationVerdict.PASS, CertificationVerdict.CONDITIONAL_PASS}:
            if any(status not in {GateStatus.PASS, GateStatus.NOT_REQUIRED} for status in statuses):
                raise ValidationError(
                    "pass verdict cannot contain a failing or insufficient gate",
                    code="INVALID_PASS_VERDICT",
                )
            if not normalized_index:
                raise ValidationError(
                    "pass verdict requires evidence",
                    code="EVIDENCE_REQUIRED",
                )
        if self.verdict is CertificationVerdict.CONDITIONAL_PASS and not self.residual_risks:
            raise ValidationError(
                "conditional pass requires explicit residual risk",
                code="RESIDUAL_RISK_REQUIRED",
            )
        if self.verdict is CertificationVerdict.INSUFFICIENT_EVIDENCE and GateStatus.INSUFFICIENT_EVIDENCE not in statuses:
            raise ValidationError(
                "insufficient-evidence verdict requires an insufficient gate",
                code="INVALID_INSUFFICIENT_VERDICT",
            )


__all__ = [
    "AgentResultStatus",
    "AgentTask",
    "AuthorityLevel",
    "CertificationBundle",
    "CertificationLevel",
    "CertificationVerdict",
    "DurableJobState",
    "DurableJobStatus",
    "EvidenceRecord",
    "EvidenceStatus",
    "ExecutionContext",
    "FailureClass",
    "GateStatus",
    "PatchTransaction",
    "PatchTransactionStatus",
    "ProofCarryingAgentResult",
    "ResourceScope",
    "RuleEnforcement",
    "RuleIR",
    "SkillLifecycleStatus",
    "SkillManifest",
    "VerificationStatus",
    "utc_now",
]
