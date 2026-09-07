"""Strict authority, execution, artifact and evidence contracts.

Trusted :class:`Scope` and :class:`CapabilityLease` values are minted by the
host control plane and passed separately from untrusted Skill inputs.  No
factory in this module derives either value from a handler payload.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, cast

from .canonical import digest_object, freeze_json, require_digest, to_jsonable
from .errors import AuthorizationError, ContractError

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/+\-]{0,199}$")
_RESERVED_INPUT_KEYS = frozenset(
    {
        "_runtime_context",
        "trusted_scope",
        "scope",
        "authority",
        "capability_lease",
        "lease",
        "tenant_id",
        "project_id",
        "actor_id",
        "revision",
        "revision_digest",
        "skill_id",
        "action",
    }
)
_SECRET_REFERENCE_KEY = "$secret_ref"
_SENSITIVE_KEY_PARTS = frozenset(
    {
        "apikey",
        "credential",
        "credentials",
        "password",
        "privatekey",
        "secret",
        "secrets",
        "sessioncookie",
        "token",
        "tokens",
    }
)
_SAFE_SENSITIVE_METADATA_SUFFIXES = frozenset(
    {
        "budget",
        "consumed",
        "count",
        "digest",
        "digests",
        "enabled",
        "mode",
        "policy",
        "ref",
        "reference",
        "references",
        "refs",
        "required",
        "scan",
        "status",
    }
)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\b(?:gh[oprsu]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|credential|password|secret|token)\s*[:=]\s*[^\s,;]{6,}"),
    re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^/@:\s]+:[^/@\s]+@"),
)
_RAW_OUTPUT_KEYS = frozenset(
    {
        "command",
        "commands",
        "content",
        "databaseir",
        "evidence",
        "payload",
        "query",
        "raw",
        "rows",
        "source_rows",
        "sourcerows",
        "sql",
        "statement",
        "target_rows",
        "targetrows",
        "typedplan",
        "typed_plan",
    }
)
_NORMALIZED_RAW_OUTPUT_KEYS = frozenset(re.sub(r"[^a-z0-9]", "", item.lower()) for item in _RAW_OUTPUT_KEYS)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_text(value: Any, field_name: str, *, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise ContractError(f"{field_name} must be a non-empty bounded string")
    if _IDENTIFIER_RE.fullmatch(value) is None or ".." in value or "//" in value:
        raise ContractError(f"{field_name} contains unsupported characters")
    return value


def _require_description(value: Any, field_name: str, *, maximum: int = 4_096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > maximum:
        raise ContractError(f"{field_name} must be non-empty bounded text")
    return value


def _require_aware(value: Any, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ContractError(f"{field_name} must be a timezone-aware datetime", code="INVALID_TIMESTAMP")
    return value


def _require_unique_text(values: tuple[str, ...] | frozenset[str], field_name: str) -> None:
    if isinstance(values, tuple) and len(set(values)) != len(values):
        raise ContractError(f"{field_name} contains duplicates")
    for value in values:
        _require_text(value, field_name)


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _key_parts(value: str) -> tuple[str, ...]:
    return tuple(part for part in re.split(r"[^a-z0-9]+", value.lower()) if part)


def _is_sensitive_input_key(value: str) -> bool:
    parts = _key_parts(value)
    normalized = _normalized_key(value)
    sensitive = normalized in _SENSITIVE_KEY_PARTS or bool(set(parts) & _SENSITIVE_KEY_PARTS)
    return sensitive and (not parts or parts[-1] not in _SAFE_SENSITIVE_METADATA_SUFFIXES)


def _is_secret_reference(value: Any) -> bool:
    return isinstance(value, Mapping) and set(value) == {_SECRET_REFERENCE_KEY}


def _scan_secret_boundary(
    value: Any,
    *,
    path: str,
    references: set[str],
    ephemeral_sensitive_fields: frozenset[str] = frozenset(),
    top_level: bool = False,
) -> None:
    if isinstance(value, Mapping):
        if _SECRET_REFERENCE_KEY in value:
            if not _is_secret_reference(value):
                raise ContractError(
                    "SecretReference objects must contain exactly $secret_ref",
                    code="INVALID_SECRET_REFERENCE",
                    details={"path": path},
                )
            reference = value[_SECRET_REFERENCE_KEY]
            _require_text(reference, f"{path}.$secret_ref")
            references.add(reference)
            return
        for key, child in value.items():
            if top_level and key in ephemeral_sensitive_fields:
                # The exact contract owns this narrowly scoped in-memory scan
                # boundary.  The value is never persisted by the runtime.
                continue
            if _is_sensitive_input_key(key) and not _is_secret_reference(child):
                raise ContractError(
                    "raw secret-like input is forbidden; use an exact SecretReference object",
                    code="RAW_SECRET_INPUT_FORBIDDEN",
                    details={"path": f"{path}.{key}"},
                )
            _scan_secret_boundary(
                child,
                path=f"{path}.{key}",
                references=references,
                ephemeral_sensitive_fields=ephemeral_sensitive_fields,
            )
        return
    if isinstance(value, (tuple, list)):
        for index, child in enumerate(value):
            _scan_secret_boundary(
                child,
                path=f"{path}[{index}]",
                references=references,
                ephemeral_sensitive_fields=ephemeral_sensitive_fields,
            )
        return
    if isinstance(value, str) and any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS):
        raise ContractError(
            "raw secret-shaped value is forbidden; use a SecretReference",
            code="RAW_SECRET_INPUT_FORBIDDEN",
            details={"path": path},
        )


def _scan_secret_values(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        if _SECRET_REFERENCE_KEY in value:
            references: set[str] = set()
            _scan_secret_boundary(value, path=path, references=references)
            return
        for key, child in value.items():
            _scan_secret_values(child, path=f"{path}.{key}")
    elif isinstance(value, (tuple, list)):
        for index, child in enumerate(value):
            _scan_secret_values(child, path=f"{path}[{index}]")
    elif isinstance(value, str) and any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS):
        raise ContractError(
            "handler output contains a raw secret-shaped value",
            code="RAW_SECRET_OUTPUT_FORBIDDEN",
            details={"path": path},
        )


def _assert_safe_handler_output(value: Any, *, path: str = "handler_result.output") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normalized_key(key)
            if normalized in _NORMALIZED_RAW_OUTPUT_KEYS:
                raise ContractError(
                    "handler output must retain only digests, counts, or references for raw payloads",
                    code="RAW_HANDLER_OUTPUT_FORBIDDEN",
                    details={"path": f"{path}.{key}"},
                )
            _assert_safe_handler_output(child, path=f"{path}.{key}")
    elif isinstance(value, (tuple, list)):
        for index, child in enumerate(value):
            _assert_safe_handler_output(child, path=f"{path}[{index}]")


def referenced_secret_refs(
    inputs: Mapping[str, Any],
    *,
    ephemeral_sensitive_fields: frozenset[str] = frozenset(),
) -> frozenset[str]:
    references: set[str] = set()
    _scan_secret_boundary(
        inputs,
        path="inputs",
        references=references,
        ephemeral_sensitive_fields=ephemeral_sensitive_fields,
        top_level=True,
    )
    return frozenset(references)


class PolicyEffect(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class EvidenceStatus(str, Enum):
    VERIFIED = "VERIFIED"
    LOCAL_EXECUTED_SELF_ATTESTED = "LOCAL_EXECUTED_SELF_ATTESTED"
    SELF_ATTESTED = "SELF_ATTESTED"
    FAILED = "FAILED"
    NOT_RUN = "NOT_RUN"
    UNKNOWN = "UNKNOWN"
    INCONCLUSIVE = "INCONCLUSIVE"
    REVOKED = "REVOKED"


class ObligationStatus(str, Enum):
    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    NOT_RUN = "NOT_RUN"
    UNKNOWN = "UNKNOWN"
    INCONCLUSIVE = "INCONCLUSIVE"


class GateLevel(str, Enum):
    E0 = "E0"
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"
    E5 = "E5"


class Outcome(str, Enum):
    """Handler/runtime outcomes; local execution never claims certification."""

    LOCAL_EXECUTED_SELF_ATTESTED = "LOCAL_EXECUTED_SELF_ATTESTED"
    EXTERNAL_ADAPTER_REQUIRED = "EXTERNAL_ADAPTER_REQUIRED"
    BLOCKED = "BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"
    DENIED = "DENIED"
    FAILED = "FAILED"
    CONFLICT = "CONFLICT"
    NOT_RUN = "NOT_RUN"
    UNKNOWN = "UNKNOWN"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class SkillInputContract:
    """Registry-owned exact input field contract for one Skill."""

    required: frozenset[str]
    optional: frozenset[str] = frozenset()
    ephemeral_sensitive_fields: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _require_unique_text(self.required, "skill_input.required")
        _require_unique_text(self.optional, "skill_input.optional")
        _require_unique_text(
            self.ephemeral_sensitive_fields,
            "skill_input.ephemeral_sensitive_fields",
        )
        if self.required & self.optional:
            raise ContractError("Skill input required and optional fields must be disjoint")
        if not self.ephemeral_sensitive_fields <= self.allowed:
            raise ContractError("ephemeral sensitive fields must belong to the exact input contract")

    @property
    def allowed(self) -> frozenset[str]:
        return self.required | self.optional

    def validate(self, inputs: Mapping[str, Any], *, require_all: bool = False) -> None:
        unknown = sorted(set(inputs) - self.allowed)
        if unknown:
            raise ContractError(
                "handler input contains fields outside the exact Skill contract",
                code="UNKNOWN_INPUT_FIELD",
                details={"fields": unknown},
            )
        if require_all:
            missing = sorted(self.required - set(inputs))
            if missing:
                raise ContractError(
                    "handler input is missing exact Skill contract fields",
                    code="MISSING_INPUT_FIELD",
                    details={"fields": missing},
                )


@dataclass(frozen=True, slots=True)
class Scope:
    tenant_id: str
    project_id: str
    actor_id: str
    revision: str
    environment_id: str = "local"

    def __post_init__(self) -> None:
        _require_text(self.tenant_id, "scope.tenant_id")
        _require_text(self.project_id, "scope.project_id")
        _require_text(self.actor_id, "scope.actor_id")
        require_digest(self.revision, "scope.revision")
        _require_text(self.environment_id, "scope.environment_id")

    @property
    def digest(self) -> str:
        return digest_object(self, domain="trusted-scope")

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], to_jsonable(self))


@dataclass(frozen=True, slots=True)
class Invocation:
    invocation_id: str
    scope: Scope
    skill_id: str
    action: str
    idempotency_key: str
    request_digest: str
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.invocation_id, "invocation.invocation_id")
        if not isinstance(self.scope, Scope):
            raise ContractError("invocation.scope must be a trusted Scope")
        _require_text(self.skill_id, "invocation.skill_id")
        _require_text(self.action, "invocation.action")
        _require_text(self.idempotency_key, "invocation.idempotency_key")
        require_digest(self.request_digest, "invocation.request_digest")
        _require_aware(self.issued_at, "invocation.issued_at")
        _require_aware(self.expires_at, "invocation.expires_at")
        if self.expires_at <= self.issued_at:
            raise ContractError("invocation.expires_at must follow issued_at")

    @property
    def digest(self) -> str:
        return digest_object(self, domain="invocation")

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], to_jsonable(self))


@dataclass(frozen=True, slots=True)
class Obligation:
    obligation_id: str
    kind: str
    description: str
    status: ObligationStatus = ObligationStatus.NOT_RUN
    evidence_ids: tuple[str, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)
    mandatory: bool = True

    def __post_init__(self) -> None:
        _require_text(self.obligation_id, "obligation.obligation_id")
        _require_text(self.kind, "obligation.kind")
        _require_description(self.description, "obligation.description")
        if not isinstance(self.status, ObligationStatus):
            raise ContractError("obligation.status must be ObligationStatus")
        _require_unique_text(self.evidence_ids, "obligation.evidence_ids")
        object.__setattr__(self, "parameters", freeze_json(self.parameters))

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], to_jsonable(self))


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision_id: str
    invocation_id: str
    scope_digest: str
    skill_id: str
    action: str
    effect: PolicyEffect
    policy_revision: str
    decided_at: datetime
    expires_at: datetime
    obligations: tuple[Obligation, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.decision_id, "policy.decision_id")
        _require_text(self.invocation_id, "policy.invocation_id")
        require_digest(self.scope_digest, "policy.scope_digest")
        _require_text(self.skill_id, "policy.skill_id")
        _require_text(self.action, "policy.action")
        if not isinstance(self.effect, PolicyEffect):
            raise ContractError("policy.effect must be PolicyEffect")
        require_digest(self.policy_revision, "policy.policy_revision")
        _require_aware(self.decided_at, "policy.decided_at")
        _require_aware(self.expires_at, "policy.expires_at")
        if self.expires_at <= self.decided_at:
            raise ContractError("policy.expires_at must follow decided_at")
        if any(not isinstance(item, Obligation) for item in self.obligations):
            raise ContractError("policy.obligations must contain Obligation values")
        _require_unique_text(self.reason_codes, "policy.reason_codes")
        if self.effect is PolicyEffect.ALLOW and self.reason_codes:
            raise ContractError("allow decisions cannot contain denial reason codes")

    @property
    def allowed(self) -> bool:
        return self.effect is PolicyEffect.ALLOW

    @property
    def digest(self) -> str:
        return digest_object(self, domain="policy-decision")

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], to_jsonable(self))


@dataclass(frozen=True, slots=True)
class CapabilityLease:
    lease_id: str
    invocation_id: str
    scope: Scope
    skill_id: str
    action: str
    request_digest: str
    policy_decision_id: str
    policy_decision_digest: str
    issued_at: datetime
    expires_at: datetime
    network: frozenset[str] = frozenset()
    secret_refs: frozenset[str] = frozenset()
    side_effects: frozenset[str] = frozenset()
    revoked_at: datetime | None = None
    revocation_reason: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.lease_id, "lease.lease_id")
        _require_text(self.invocation_id, "lease.invocation_id")
        if not isinstance(self.scope, Scope):
            raise ContractError("lease.scope must be a trusted Scope")
        _require_text(self.skill_id, "lease.skill_id")
        _require_text(self.action, "lease.action")
        require_digest(self.request_digest, "lease.request_digest")
        _require_text(self.policy_decision_id, "lease.policy_decision_id")
        require_digest(self.policy_decision_digest, "lease.policy_decision_digest")
        _require_aware(self.issued_at, "lease.issued_at")
        _require_aware(self.expires_at, "lease.expires_at")
        if self.expires_at <= self.issued_at:
            raise ContractError("lease.expires_at must follow issued_at")
        _require_unique_text(self.network, "lease.network")
        _require_unique_text(self.secret_refs, "lease.secret_refs")
        _require_unique_text(self.side_effects, "lease.side_effects")
        if self.revoked_at is not None:
            _require_aware(self.revoked_at, "lease.revoked_at")
            if self.revoked_at < self.issued_at:
                raise ContractError("lease.revoked_at precedes issue time")
            _require_description(self.revocation_reason, "lease.revocation_reason")
        elif self.revocation_reason is not None:
            raise ContractError("lease.revocation_reason requires revoked_at")

    @property
    def digest(self) -> str:
        return digest_object(self, domain="capability-lease")

    def assert_authorized(self, invocation: Invocation, *, now: datetime | None = None) -> None:
        current = now or utc_now()
        _require_aware(current, "now")
        if self.revoked_at is not None:
            raise AuthorizationError("capability lease is revoked", code="LEASE_REVOKED")
        if current < self.issued_at or current >= self.expires_at:
            raise AuthorizationError("capability lease is not active", code="LEASE_EXPIRED")
        expected = (
            self.invocation_id,
            self.scope,
            self.skill_id,
            self.action,
            self.request_digest,
        )
        observed = (
            invocation.invocation_id,
            invocation.scope,
            invocation.skill_id,
            invocation.action,
            invocation.request_digest,
        )
        if expected != observed:
            raise AuthorizationError("capability lease binding mismatch", code="LEASE_BINDING_MISMATCH")
        if current < invocation.issued_at or current >= invocation.expires_at:
            raise AuthorizationError("invocation is not active", code="INVOCATION_EXPIRED")

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], to_jsonable(self))


@dataclass(frozen=True, slots=True)
class Artifact:
    digest: str
    media_type: str
    size_bytes: int
    kind: str
    producer_id: str
    created_at: datetime
    uri: str | None = None

    def __post_init__(self) -> None:
        require_digest(self.digest, "artifact.digest")
        _require_text(self.media_type, "artifact.media_type")
        if not isinstance(self.size_bytes, int) or isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ContractError("artifact.size_bytes must be a non-negative integer")
        _require_text(self.kind, "artifact.kind")
        _require_text(self.producer_id, "artifact.producer_id")
        _require_aware(self.created_at, "artifact.created_at")
        if self.uri is not None:
            _require_description(self.uri, "artifact.uri", maximum=2_048)

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], to_jsonable(self))


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    scope: Scope
    invocation_id: str
    category: str
    subject_digest: str
    content_digest: str
    status: EvidenceStatus
    producer_id: str
    verifier_id: str | None
    authorization_id: str | None
    produced_at: datetime
    expires_at: datetime | None = None
    artifact_digests: tuple[str, ...] = ()
    revoked_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.evidence_id, "evidence.evidence_id")
        if not isinstance(self.scope, Scope):
            raise ContractError("evidence.scope must be Scope")
        _require_text(self.invocation_id, "evidence.invocation_id")
        _require_text(self.category, "evidence.category")
        require_digest(self.subject_digest, "evidence.subject_digest")
        require_digest(self.content_digest, "evidence.content_digest")
        if not isinstance(self.status, EvidenceStatus):
            raise ContractError("evidence.status must be EvidenceStatus")
        _require_text(self.producer_id, "evidence.producer_id")
        if self.verifier_id is not None:
            _require_text(self.verifier_id, "evidence.verifier_id")
        if self.authorization_id is not None:
            _require_text(self.authorization_id, "evidence.authorization_id")
        _require_aware(self.produced_at, "evidence.produced_at")
        if self.expires_at is not None:
            _require_aware(self.expires_at, "evidence.expires_at")
            if self.expires_at <= self.produced_at:
                raise ContractError("evidence.expires_at must follow produced_at")
        if self.revoked_at is not None:
            _require_aware(self.revoked_at, "evidence.revoked_at")
            if self.revoked_at < self.produced_at:
                raise ContractError("evidence.revoked_at precedes produced_at")
        _require_unique_text(self.artifact_digests, "evidence.artifact_digests")
        for digest in self.artifact_digests:
            require_digest(digest, "evidence.artifact_digests[]")
        frozen_metadata = freeze_json(self.metadata)
        _scan_secret_values(frozen_metadata, path="evidence.metadata")
        object.__setattr__(self, "metadata", frozen_metadata)

    @property
    def digest(self) -> str:
        return digest_object(self, domain="evidence-record")

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], to_jsonable(self))


def _execution_capability_boundary() -> tuple[
    Callable[[Invocation, frozenset[str]], object],
    Callable[[object, Invocation], frozenset[str]],
]:
    """Keep the capability type and constructor outside the module namespace."""

    class RuntimeExecutionCapability:
        __slots__ = ("ephemeral_sensitive_fields", "invocation_digest", "skill_id")

        def __init__(
            self,
            invocation: Invocation,
            ephemeral_sensitive_fields: frozenset[str],
        ) -> None:
            self.invocation_digest = invocation.digest
            self.skill_id = invocation.skill_id
            self.ephemeral_sensitive_fields = ephemeral_sensitive_fields

    def issue(
        invocation: Invocation,
        ephemeral_sensitive_fields: frozenset[str],
    ) -> object:
        return RuntimeExecutionCapability(invocation, ephemeral_sensitive_fields)

    def validate(candidate: object, invocation: Invocation) -> frozenset[str]:
        if not isinstance(candidate, RuntimeExecutionCapability):
            raise AuthorizationError(
                "handler requests can only be minted by the authenticated runtime",
                code="RUNTIME_EXECUTION_CAPABILITY_REQUIRED",
            )
        if candidate.invocation_digest != invocation.digest or candidate.skill_id != invocation.skill_id:
            raise AuthorizationError(
                "handler execution capability binding mismatch",
                code="RUNTIME_EXECUTION_CAPABILITY_MISMATCH",
            )
        return candidate.ephemeral_sensitive_fields

    return issue, validate


_issue_execution_capability, _validate_execution_capability = _execution_capability_boundary()


@dataclass(frozen=True, slots=True)
class HandlerRequest:
    invocation: Invocation
    lease: CapabilityLease
    inputs: Mapping[str, Any]
    context: Mapping[str, Any] = field(default_factory=dict)
    _execution_capability: object = field(default=None, repr=False, compare=False, kw_only=True)

    def __post_init__(self) -> None:
        if not isinstance(self.invocation, Invocation):
            raise ContractError("handler request requires Invocation")
        if not isinstance(self.lease, CapabilityLease):
            raise ContractError("handler request requires CapabilityLease")
        ephemeral_sensitive_fields = _validate_execution_capability(
            self._execution_capability,
            self.invocation,
        )
        frozen_inputs = validate_handler_inputs(
            self.inputs,
            ephemeral_sensitive_fields=ephemeral_sensitive_fields,
        )
        frozen_context = freeze_json(self.context)
        if not isinstance(frozen_context, Mapping):
            raise ContractError("handler request context must be an object")
        self.lease.assert_authorized(self.invocation)
        object.__setattr__(self, "inputs", frozen_inputs)
        object.__setattr__(self, "context", frozen_context)

    @property
    def skill_id(self) -> str:
        return self.invocation.skill_id

    @property
    def operation(self) -> str:
        return self.invocation.action

    @property
    def scope(self) -> Scope:
        return self.invocation.scope

    def assert_runtime_execution(self, expected_skill_id: str) -> None:
        """Verify the non-serializable runtime capability and exact Skill binding."""

        _validate_execution_capability(self._execution_capability, self.invocation)
        if self.skill_id != expected_skill_id:
            raise AuthorizationError(
                "handler execution capability is bound to a different exact Skill",
                code="RUNTIME_EXECUTION_CAPABILITY_MISMATCH",
            )

    def to_dict(self) -> dict[str, Any]:
        raise AuthorizationError(
            "internal handler requests and execution capabilities are not serializable",
            code="HANDLER_REQUEST_INTERNAL",
        )


def _mint_handler_request(
    *,
    invocation: Invocation,
    lease: CapabilityLease,
    inputs: Mapping[str, Any],
    context: Mapping[str, Any],
    ephemeral_sensitive_fields: frozenset[str],
) -> HandlerRequest:
    """Runtime-internal request factory called only after authority verification."""

    capability = _issue_execution_capability(invocation, ephemeral_sensitive_fields)
    return HandlerRequest(
        invocation=invocation,
        lease=lease,
        inputs=inputs,
        context=context,
        _execution_capability=capability,
    )


@dataclass(frozen=True, slots=True)
class HandlerResult:
    skill_id: str
    status: Outcome
    output: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[Artifact, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    unresolved: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()
    metrics: Mapping[str, int | float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.skill_id, "handler_result.skill_id")
        if not isinstance(self.status, Outcome):
            raise ContractError("handler_result.status must be Outcome")
        frozen_output = freeze_json(self.output)
        if not isinstance(frozen_output, Mapping):
            raise ContractError("handler_result.output must be an object")
        _scan_secret_values(frozen_output, path="handler_result.output")
        _assert_safe_handler_output(frozen_output)
        if any(not isinstance(item, Artifact) for item in self.artifacts):
            raise ContractError("handler_result.artifacts must contain Artifact values")
        if any(not isinstance(item, Evidence) for item in self.evidence):
            raise ContractError("handler_result.evidence must contain Evidence values")
        _require_unique_text(self.unresolved, "handler_result.unresolved")
        _require_unique_text(self.side_effects, "handler_result.side_effects")
        frozen_metrics = freeze_json(self.metrics)
        if not isinstance(frozen_metrics, Mapping):
            raise ContractError("handler_result.metrics must be an object")
        for name, value in frozen_metrics.items():
            _require_text(name, "handler_result.metrics key")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ContractError("handler_result.metrics values must be numeric")
        if self.status is Outcome.LOCAL_EXECUTED_SELF_ATTESTED and self.unresolved:
            raise ContractError("a completed local result cannot contain unresolved items")
        object.__setattr__(self, "output", frozen_output)
        object.__setattr__(self, "metrics", frozen_metrics)

    @property
    def digest(self) -> str:
        return digest_object(self, domain="handler-result")

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], to_jsonable(self))


def deny_by_default(
    invocation: Invocation,
    *,
    policy_revision: str,
    decision_id: str,
    reason_code: str = "NO_EXPLICIT_ALLOW",
) -> PolicyDecision:
    """Construct the only implicit policy decision: a short-lived denial."""

    return PolicyDecision(
        decision_id=decision_id,
        invocation_id=invocation.invocation_id,
        scope_digest=invocation.scope.digest,
        skill_id=invocation.skill_id,
        action=invocation.action,
        effect=PolicyEffect.DENY,
        policy_revision=policy_revision,
        decided_at=invocation.issued_at,
        expires_at=invocation.expires_at,
        reason_codes=(reason_code,),
    )


def validate_handler_inputs(
    inputs: Mapping[str, Any],
    *,
    ephemeral_sensitive_fields: frozenset[str] = frozenset(),
) -> Mapping[str, Any]:
    """Validate untrusted Skill inputs without deriving any trusted context."""

    frozen_inputs = freeze_json(inputs)
    if not isinstance(frozen_inputs, Mapping):
        raise ContractError("handler request inputs must be an object")
    forbidden = sorted(set(frozen_inputs).intersection(_RESERVED_INPUT_KEYS))
    if forbidden:
        raise AuthorizationError(
            "handler inputs attempt to override trusted runtime fields",
            code="TRUSTED_SCOPE_OVERRIDE",
            details={"fields": forbidden},
        )
    referenced_secret_refs(
        frozen_inputs,
        ephemeral_sensitive_fields=ephemeral_sensitive_fields,
    )
    return frozen_inputs


def assert_lease_secret_refs(
    inputs: Mapping[str, Any],
    lease: CapabilityLease,
    *,
    ephemeral_sensitive_fields: frozenset[str] = frozenset(),
) -> None:
    """Require every JSON SecretReference to be explicitly leased by the host."""

    used = referenced_secret_refs(
        inputs,
        ephemeral_sensitive_fields=ephemeral_sensitive_fields,
    )
    unauthorized = used - lease.secret_refs
    if unauthorized:
        raise AuthorizationError(
            "handler input references secrets outside the capability lease",
            code="SECRET_REFERENCE_NOT_AUTHORIZED",
            details={"references": sorted(unauthorized)},
        )
