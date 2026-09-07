"""Typed durable port for the v3.1 runtime-assurance delta.

This module intentionally does not import :mod:`elmos_proof_harness.delta`.
The in-memory orchestration model and the durable PostgreSQL boundary may be
loaded independently and cannot create an import cycle.  Every persisted DTO
contains its authoritative tenant/project/actor binding, and scope snapshots
also bind the exact run, epoch, fence, and revision used to rehydrate them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import hmac
from typing import Any, ContextManager, Mapping, Protocol, Sequence, runtime_checkable

from .canonical import digest_object, freeze_json, require_sha256_digest
from .contracts import SecurityContext
from .errors import ValidationError


def _text(value: str, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValidationError(f"{field} is invalid", details={"field": field})
    return value


def _positive(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError(
            f"{field} must be a positive integer", details={"field": field}
        )
    return value


def _aware(
    value: datetime | None, field: str, *, optional: bool = False
) -> datetime | None:
    if value is None:
        if optional:
            return None
        raise ValidationError(f"{field} is required", details={"field": field})
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValidationError(
            f"{field} must be timezone-aware", details={"field": field}
        )
    return value


def _text_tuple(
    value: Sequence[str], field: str, *, maximum_items: int = 256
) -> tuple[str, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) > maximum_items
    ):
        raise ValidationError(f"{field} is invalid", details={"field": field})
    normalized = tuple(_text(item, field) for item in value)
    if len(normalized) != len(set(normalized)):
        raise ValidationError(f"{field} contains duplicates", details={"field": field})
    return normalized


def _record_scope(
    tenant_id: str,
    project_id: str,
    run_id: str,
    actor_id: str,
    execution_epoch: int,
    fencing_generation: int,
    authority_revision: str,
    revision_set_id: str,
) -> None:
    _text(tenant_id, "tenant_id", maximum=255)
    _text(project_id, "project_id", maximum=255)
    _text(run_id, "run_id", maximum=512)
    _text(actor_id, "actor_id", maximum=512)
    _positive(execution_epoch, "execution_epoch")
    _positive(fencing_generation, "fencing_generation")
    require_sha256_digest(authority_revision, field="authority_revision")
    require_sha256_digest(revision_set_id, field="revision_set_id")


def _decimal_budget(value: str) -> str:
    _text(value, "cost_budget", maximum=128)
    integer, separator, fraction = value.partition(".")
    if (
        not integer.isdigit()
        or (len(integer) > 1 and integer.startswith("0"))
        or (separator and (not fraction or not fraction.isdigit()))
    ):
        raise ValidationError("cost_budget must be canonical non-exponent decimal text")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValidationError("cost_budget is invalid") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValidationError("cost_budget must be positive and finite")
    return value


def _wire_time(value: datetime) -> str:
    aware = _aware(value, "wall_clock_deadline")
    assert aware is not None
    return (
        aware.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _workspace_scopes(value: Sequence[str]) -> tuple[str, ...]:
    scopes = _text_tuple(value, "write_scopes")
    for scope in scopes:
        if (
            scope != scope.strip()
            or scope.startswith("/")
            or "\\" in scope
            or any(part in {"", ".", ".."} for part in scope.split("/"))
        ):
            raise ValidationError(
                "write_scopes must be canonical repository-relative paths"
            )
    return scopes


class ToolResultCommitState(StrEnum):
    RAW_CAPTURED = "RAW_CAPTURED"
    INTERCEPTING = "INTERCEPTING"
    COMMITTED = "COMMITTED"
    PUBLISHED = "PUBLISHED"
    ABORTED = "ABORTED"


class ToolResultFailureKind(StrEnum):
    INTERCEPTOR_REJECTED = "INTERCEPTOR_REJECTED"
    INTERCEPTOR_ERROR = "INTERCEPTOR_ERROR"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    AUTHORITY_REVOKED = "AUTHORITY_REVOKED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class PendingToolCallBindingState(StrEnum):
    PENDING = "PENDING"
    RECONCILED = "RECONCILED"


class StepPlanState(StrEnum):
    CANDIDATE = "CANDIDATE"
    FINALIZED = "FINALIZED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class CapabilityLeaseState(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class CapabilityRevocationReason(StrEnum):
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    TURN_ABORTED = "TURN_ABORTED"
    EXECUTOR_REPLACED = "EXECUTOR_REPLACED"
    AUTHORITY_REVOKED = "AUTHORITY_REVOKED"
    COMPLETED = "COMPLETED"


class CapabilityUseDenialReason(StrEnum):
    UNKNOWN_LEASE = "UNKNOWN_LEASE"
    INVOCATION_MISMATCH = "INVOCATION_MISMATCH"
    CAPABILITY_NOT_GRANTED = "CAPABILITY_NOT_GRANTED"
    LEASE_NOT_ACTIVE = "LEASE_NOT_ACTIVE"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    ENVIRONMENT_MISMATCH = "ENVIRONMENT_MISMATCH"
    AUTHORITY_SNAPSHOT_MISMATCH = "AUTHORITY_SNAPSHOT_MISMATCH"
    AUTHORITY_CAPABILITY_MISMATCH = "AUTHORITY_CAPABILITY_MISMATCH"


class SubagentBudgetReservationState(StrEnum):
    RESERVED = "RESERVED"
    CONSUMED = "CONSUMED"


@dataclass(frozen=True, slots=True)
class HostSignedEnvelope:
    """Host-issued signature and independent-verification metadata.

    The envelope is distinct from a base-Skill execution receipt: its
    signature covers the exact runtime authority or reservation payload that
    a privileged authority writer may persist.  Local self-attestation is
    explicit and is never production evidence.
    """

    payload_digest: str
    envelope_digest: str
    issuer: str
    signing_key_id: str
    signature_algorithm: str
    signature: str
    issued_at: datetime
    verifier_id: str
    verification_evidence_ref: str
    verification_evidence_digest: str
    verified_at: datetime

    _ALGORITHMS = frozenset(
        {
            "ED25519",
            "ECDSA_P256_SHA256",
            "RSA_PSS_SHA256",
            "LOCAL_SELF_ATTESTED",
        }
    )

    @staticmethod
    def _timestamp(value: datetime) -> str:
        checked = _aware(value, "host envelope timestamp")
        assert checked is not None
        return checked.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @classmethod
    def payload_hash(cls, kind: str, payload: Mapping[str, Any]) -> str:
        return digest_object(
            {
                "kind": _text(kind, "host envelope kind"),
                "payload": freeze_json(payload),
            },
            domain="delta-host-envelope-payload",
        )

    @classmethod
    def digest_for(
        cls,
        *,
        kind: str,
        payload_digest: str,
        issuer: str,
        signing_key_id: str,
        signature_algorithm: str,
        issued_at: datetime,
    ) -> str:
        require_sha256_digest(payload_digest, field="payload_digest")
        return digest_object(
            {
                "kind": _text(kind, "host envelope kind"),
                "payloadDigest": payload_digest,
                "issuer": _text(issuer, "host envelope issuer"),
                "signingKeyId": _text(signing_key_id, "host envelope signing_key_id"),
                "signatureAlgorithm": _text(
                    signature_algorithm, "host envelope signature_algorithm"
                ),
                "issuedAt": cls._timestamp(issued_at),
            },
            domain="delta-host-signed-envelope",
        )

    @classmethod
    def local_self_attested(
        cls,
        *,
        kind: str,
        payload: Mapping[str, Any],
        now: datetime | None = None,
    ) -> "HostSignedEnvelope":
        issued_at = (now or datetime.now(UTC)).astimezone(UTC)
        payload_digest = cls.payload_hash(kind, payload)
        envelope_digest = cls.digest_for(
            kind=kind,
            payload_digest=payload_digest,
            issuer="local-self-attested-host",
            signing_key_id="local-self-attested",
            signature_algorithm="LOCAL_SELF_ATTESTED",
            issued_at=issued_at,
        )
        signature = f"LOCAL_SELF_ATTESTED:{envelope_digest}"
        verification_evidence_digest = digest_object(
            {
                "envelopeDigest": envelope_digest,
                "signature": signature,
                "verifierId": "local-self-attested",
                "verifiedAt": cls._timestamp(issued_at),
            },
            domain="delta-host-envelope-verification",
        )
        return cls(
            payload_digest=payload_digest,
            envelope_digest=envelope_digest,
            issuer="local-self-attested-host",
            signing_key_id="local-self-attested",
            signature_algorithm="LOCAL_SELF_ATTESTED",
            signature=signature,
            issued_at=issued_at,
            verifier_id="local-self-attested",
            verification_evidence_ref=(
                f"local:self-attested:{verification_evidence_digest}"
            ),
            verification_evidence_digest=verification_evidence_digest,
            verified_at=issued_at,
        )

    def __post_init__(self) -> None:
        require_sha256_digest(self.payload_digest, field="payload_digest")
        require_sha256_digest(self.envelope_digest, field="envelope_digest")
        require_sha256_digest(
            self.verification_evidence_digest,
            field="verification_evidence_digest",
        )
        for field in (
            "issuer",
            "signing_key_id",
            "signature_algorithm",
            "signature",
            "verifier_id",
            "verification_evidence_ref",
        ):
            _text(getattr(self, field), field)
        if self.signature_algorithm not in self._ALGORITHMS:
            raise ValidationError("host envelope signature algorithm is unsupported")
        _aware(self.issued_at, "issued_at")
        _aware(self.verified_at, "verified_at")
        if self.verified_at < self.issued_at:
            raise ValidationError("host envelope verification predates issuance")
        expected_verification = digest_object(
            {
                "envelopeDigest": self.envelope_digest,
                "signature": self.signature,
                "verifierId": self.verifier_id,
                "verifiedAt": self._timestamp(self.verified_at),
            },
            domain="delta-host-envelope-verification",
        )
        if not hmac.compare_digest(
            self.verification_evidence_digest,
            expected_verification,
        ):
            raise ValidationError(
                "host envelope verification evidence digest is invalid"
            )

    def verify_payload(self, *, kind: str, payload: Mapping[str, Any]) -> None:
        expected_payload = self.payload_hash(kind, payload)
        expected_envelope = self.digest_for(
            kind=kind,
            payload_digest=expected_payload,
            issuer=self.issuer,
            signing_key_id=self.signing_key_id,
            signature_algorithm=self.signature_algorithm,
            issued_at=self.issued_at,
        )
        if not hmac.compare_digest(self.payload_digest, expected_payload) or not (
            hmac.compare_digest(self.envelope_digest, expected_envelope)
        ):
            raise ValidationError(
                "host signed envelope does not bind the exact payload"
            )


class ExecutorGenerationState(StrEnum):
    CONNECTING = "CONNECTING"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    FAILED = "FAILED"


class EnvironmentAttachmentState(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class ExecutorReplacementEffectKind(StrEnum):
    CAPABILITY_REVOCATION = "CAPABILITY_REVOCATION"
    WORKSPACE_RECONCILIATION = "WORKSPACE_RECONCILIATION"
    EXTERNAL_EFFECT_RECONCILIATION = "EXTERNAL_EFFECT_RECONCILIATION"


class ExecutorReplacementEffectState(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class WorkspaceLeaseState(StrEnum):
    ACTIVE = "ACTIVE"
    HANDOFF_PENDING = "HANDOFF_PENDING"
    RETIRED = "RETIRED"
    TAKEOVER_PENDING = "TAKEOVER_PENDING"


class DurableEventSemantics(StrEnum):
    OPTIONAL_OBSERVATION = "OPTIONAL_OBSERVATION"
    REQUIRED_STATE = "REQUIRED_STATE"


class EventCompatibility(StrEnum):
    STRICT = "STRICT"
    BACKWARD = "BACKWARD"
    FORWARD = "FORWARD"
    FULL = "FULL"


class DurableEventInstanceState(StrEnum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    SKIPPED = "SKIPPED"


class EventCompatibilityDecision(StrEnum):
    EXACT = "EXACT"
    UPGRADED = "UPGRADED"
    SKIPPED = "SKIPPED"


class EventOwnerChangeAction(StrEnum):
    UNINSTALL = "UNINSTALL"
    DOWNGRADE = "DOWNGRADE"


class TypedIngressKind(StrEnum):
    USER_INPUT = "USER_INPUT"
    TOOL_RESULT = "TOOL_RESULT"
    EXTERNAL_EVENT = "EXTERNAL_EVENT"
    APPROVAL_INPUT = "APPROVAL_INPUT"
    CONTROL_INPUT = "CONTROL_INPUT"


class SubagentExecutionSpecState(StrEnum):
    RESERVED = "RESERVED"
    CONSUMED = "CONSUMED"


class RuntimeAssuranceInvocationState(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class RuntimeAssuranceClaimDisposition(StrEnum):
    ACQUIRED = "ACQUIRED"
    COMPLETED = "COMPLETED"
    COMPLETED_REPLAY = "COMPLETED_REPLAY"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass(frozen=True, slots=True)
class InterceptorCommitRecord:
    interceptor_id: str
    version: str
    decision_hash: str

    def __post_init__(self) -> None:
        _text(self.interceptor_id, "interceptor_id", maximum=512)
        _text(self.version, "version", maximum=128)
        require_sha256_digest(self.decision_hash, field="decision_hash")


@dataclass(frozen=True, slots=True)
class PendingToolCallBindingRecord:
    """Host-minted durable identity required before RAW_RESULT persistence."""

    tenant_id: str
    project_id: str
    run_id: str
    actor_id: str
    invocation_id: str
    call_id: str
    attempt: int
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    execution_plan_hash: str
    environment_id: str
    tool_id: str
    authority_snapshot_id: str
    state: PendingToolCallBindingState
    created_at: datetime
    updated_at: datetime
    reconciled_at: datetime | None = None

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        for field in (
            "tenant_id",
            "project_id",
            "run_id",
            "actor_id",
            "invocation_id",
            "call_id",
            "environment_id",
            "tool_id",
            "authority_snapshot_id",
        ):
            _text(getattr(self, field), field)
        _positive(self.attempt, "attempt")
        require_sha256_digest(self.execution_plan_hash, field="execution_plan_hash")
        require_sha256_digest(
            self.authority_snapshot_id,
            field="authority_snapshot_id",
        )
        if not hmac.compare_digest(self.authority_snapshot_id, self.authority_revision):
            raise ValidationError(
                "authority_snapshot_id does not match authority_revision"
            )
        if not isinstance(self.state, PendingToolCallBindingState):
            raise ValidationError("pending tool-call binding state must be typed")
        _aware(self.created_at, "created_at")
        _aware(self.updated_at, "updated_at")
        _aware(self.reconciled_at, "reconciled_at", optional=True)
        if self.updated_at < self.created_at:
            raise ValidationError("updated_at cannot precede created_at")
        if (self.state is PendingToolCallBindingState.RECONCILED) is (
            self.reconciled_at is None
        ):
            raise ValidationError(
                "reconciled_at does not match pending tool-call binding state"
            )
        if self.reconciled_at is not None and self.reconciled_at < self.created_at:
            raise ValidationError("reconciled_at cannot precede created_at")


@dataclass(frozen=True, slots=True)
class ToolResultCommitRecord:
    tenant_id: str
    project_id: str
    run_id: str
    actor_id: str
    invocation_id: str
    call_id: str
    attempt: int
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    execution_plan_hash: str
    environment_id: str
    authority_snapshot_id: str
    raw_result_ref: str
    effective_result_ref: str
    interceptor_chain: tuple[InterceptorCommitRecord, ...]
    mutation_provenance_ref: str | None
    failure_kind: ToolResultFailureKind | None
    failure_reason: str | None
    state: ToolResultCommitState
    created_at: datetime
    updated_at: datetime
    committed_at: datetime | None = None
    published_at: datetime | None = None
    aborted_at: datetime | None = None
    recovery_evidence_ref: str | None = None

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        for field in (
            "tenant_id",
            "project_id",
            "run_id",
            "actor_id",
            "invocation_id",
            "call_id",
            "environment_id",
            "authority_snapshot_id",
            "raw_result_ref",
            "effective_result_ref",
        ):
            _text(getattr(self, field), field)
        _positive(self.attempt, "attempt")
        _positive(self.execution_epoch, "execution_epoch")
        require_sha256_digest(self.execution_plan_hash, field="execution_plan_hash")
        require_sha256_digest(
            self.authority_snapshot_id,
            field="authority_snapshot_id",
        )
        if not hmac.compare_digest(self.authority_snapshot_id, self.authority_revision):
            raise ValidationError(
                "authority_snapshot_id does not match authority_revision"
            )
        if (
            not isinstance(self.state, ToolResultCommitState)
            or not isinstance(self.interceptor_chain, tuple)
            or any(
                not isinstance(item, InterceptorCommitRecord)
                for item in self.interceptor_chain
            )
            or len(self.interceptor_chain) > 64
            or len(
                {(item.interceptor_id, item.version) for item in self.interceptor_chain}
            )
            != len(self.interceptor_chain)
        ):
            raise ValidationError("interceptor_chain is invalid")
        if self.mutation_provenance_ref is not None:
            _text(self.mutation_provenance_ref, "mutation_provenance_ref")
        if self.recovery_evidence_ref is not None:
            _text(self.recovery_evidence_ref, "recovery_evidence_ref")
            if self.state is not ToolResultCommitState.ABORTED:
                raise ValidationError(
                    "recovery_evidence_ref is only valid for an aborted tool result"
                )
        if (self.state is ToolResultCommitState.ABORTED) is (self.failure_kind is None):
            raise ValidationError("failure_kind does not match tool result state")
        if (self.state is ToolResultCommitState.ABORTED) is (
            self.failure_reason is None
        ):
            raise ValidationError("failure_reason does not match tool result state")
        if self.failure_kind is not None and not isinstance(
            self.failure_kind,
            ToolResultFailureKind,
        ):
            raise ValidationError("failure_kind must be typed")
        if self.failure_reason is not None:
            _text(self.failure_reason, "failure_reason")
        _aware(self.created_at, "created_at")
        _aware(self.updated_at, "updated_at")
        _aware(self.committed_at, "committed_at", optional=True)
        _aware(self.published_at, "published_at", optional=True)
        _aware(self.aborted_at, "aborted_at", optional=True)
        if self.updated_at < self.created_at:
            raise ValidationError("updated_at cannot precede created_at")
        if (
            self.state
            in {
                ToolResultCommitState.COMMITTED,
                ToolResultCommitState.PUBLISHED,
            }
            and self.committed_at is None
        ):
            raise ValidationError("committed tool result state requires committed_at")
        if (
            self.state
            in {
                ToolResultCommitState.RAW_CAPTURED,
                ToolResultCommitState.INTERCEPTING,
            }
            and self.committed_at is not None
        ):
            raise ValidationError(
                "pre-commit tool result state cannot have committed_at"
            )
        if (self.state is ToolResultCommitState.PUBLISHED) is (
            self.published_at is None
        ):
            raise ValidationError("published_at does not match tool result state")
        if (self.state is ToolResultCommitState.ABORTED) is (self.aborted_at is None):
            raise ValidationError("aborted_at does not match tool result state")
        if self.committed_at is not None and self.committed_at < self.created_at:
            raise ValidationError("committed_at cannot precede created_at")
        if self.published_at is not None and (
            self.committed_at is None or self.published_at < self.committed_at
        ):
            raise ValidationError("published_at cannot precede committed_at")
        if self.aborted_at is not None and self.aborted_at < self.created_at:
            raise ValidationError("aborted_at cannot precede created_at")
        if (
            self.aborted_at is not None
            and self.committed_at is not None
            and self.aborted_at < self.committed_at
        ):
            raise ValidationError("aborted_at cannot precede committed_at")


@dataclass(frozen=True, slots=True)
class StepExecutionPlanRecord:
    tenant_id: str
    project_id: str
    run_id: str
    actor_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    plan_id: str
    step_id: str
    plan_hash: str
    model_snapshot: Mapping[str, Any]
    tool_plan: Mapping[str, Any]
    tool_contracts: Mapping[str, Any]
    handler_digests: Mapping[str, str]
    capabilities: tuple[str, ...]
    tool_mode: str
    environment_snapshot_id: str
    authority_snapshot_id: str
    state: StepPlanState
    created_at: datetime
    updated_at: datetime
    finalized_at: datetime | None = None
    activated_at: datetime | None = None
    retired_at: datetime | None = None

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        for field in (
            "tenant_id",
            "project_id",
            "run_id",
            "actor_id",
            "plan_id",
            "step_id",
            "environment_snapshot_id",
            "authority_snapshot_id",
        ):
            _text(getattr(self, field), field)
        require_sha256_digest(self.plan_hash, field="plan_hash")
        require_sha256_digest(
            self.authority_snapshot_id,
            field="authority_snapshot_id",
        )
        if not hmac.compare_digest(self.authority_snapshot_id, self.authority_revision):
            raise ValidationError(
                "authority_snapshot_id does not match authority_revision"
            )
        required_model_keys = {"provider", "model", "revision"}
        model_keys = (
            set(self.model_snapshot)
            if isinstance(self.model_snapshot, Mapping)
            else set()
        )
        if (
            not required_model_keys <= model_keys
            or not model_keys <= required_model_keys | {"reasoningEffort"}
        ):
            raise ValidationError("model_snapshot has an unsupported shape")
        for field in required_model_keys:
            _text(self.model_snapshot[field], f"model_snapshot.{field}")
        if "reasoningEffort" in self.model_snapshot:
            _text(
                self.model_snapshot["reasoningEffort"],
                "model_snapshot.reasoningEffort",
            )
        if not isinstance(self.tool_plan, Mapping) or set(self.tool_plan) != {"tools"}:
            raise ValidationError("tool_plan has an unsupported shape")
        tools = _text_tuple(self.tool_plan["tools"], "tool_plan.tools")
        if not isinstance(self.tool_contracts, Mapping) or set(
            self.tool_contracts
        ) != set(tools):
            raise ValidationError("tool_contracts must exactly bind every planned tool")
        if any(
            not isinstance(value, Mapping) for value in self.tool_contracts.values()
        ):
            raise ValidationError("tool_contracts values must be objects")
        if not isinstance(self.handler_digests, Mapping) or set(
            self.handler_digests
        ) != set(tools):
            raise ValidationError(
                "handler_digests must exactly bind every planned tool"
            )
        for tool, digest in self.handler_digests.items():
            _text(tool, "handler_digests key", maximum=512)
            require_sha256_digest(digest, field=f"handler_digests.{tool}")
        capabilities = _text_tuple(self.capabilities, "capabilities")
        mode = _text(self.tool_mode, "tool_mode", maximum=128)
        expected_plan_hash = digest_object(
            {
                "modelSnapshot": self.model_snapshot,
                "tools": list(tools),
                "toolContracts": self.tool_contracts,
                "handlerDigests": self.handler_digests,
                "environmentSnapshotId": self.environment_snapshot_id,
                "authoritySnapshotId": self.authority_snapshot_id,
                "mode": mode,
                "capabilities": list(capabilities),
            },
            domain="delta-execution-plan",
        )
        if not hmac.compare_digest(expected_plan_hash, self.plan_hash):
            raise ValidationError("plan_hash does not bind the exact execution plan")
        object.__setattr__(self, "model_snapshot", freeze_json(self.model_snapshot))
        object.__setattr__(self, "tool_plan", freeze_json(self.tool_plan))
        object.__setattr__(self, "tool_contracts", freeze_json(self.tool_contracts))
        object.__setattr__(self, "handler_digests", freeze_json(self.handler_digests))
        object.__setattr__(self, "capabilities", capabilities)
        if not isinstance(self.state, StepPlanState):
            raise ValidationError("step plan state must be typed")
        for field in ("created_at", "updated_at"):
            _aware(getattr(self, field), field)
        for field in ("finalized_at", "activated_at", "retired_at"):
            _aware(getattr(self, field), field, optional=True)
        if self.updated_at < self.created_at:
            raise ValidationError("updated_at cannot precede created_at")
        finalized = self.state in {
            StepPlanState.FINALIZED,
            StepPlanState.ACTIVE,
            StepPlanState.RETIRED,
        }
        activated = self.state in {StepPlanState.ACTIVE, StepPlanState.RETIRED}
        retired = self.state is StepPlanState.RETIRED
        if finalized is (self.finalized_at is None):
            raise ValidationError("finalized_at does not match step plan state")
        if activated is (self.activated_at is None):
            raise ValidationError("activated_at does not match step plan state")
        if retired is (self.retired_at is None):
            raise ValidationError("retired_at does not match step plan state")
        if self.finalized_at is not None and self.finalized_at < self.created_at:
            raise ValidationError("finalized_at cannot precede created_at")
        if self.activated_at is not None and (
            self.finalized_at is None or self.activated_at < self.finalized_at
        ):
            raise ValidationError("activated_at cannot precede finalized_at")
        if self.retired_at is not None and (
            self.activated_at is None or self.retired_at < self.activated_at
        ):
            raise ValidationError("retired_at cannot precede activated_at")


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityCapabilityReceiptRecord:
    """Durable exact capability ceiling for one Host-authorized operation."""

    tenant_id: str
    project_id: str
    run_id: str
    actor_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    operation_invocation_id: str
    environment_id: str
    authority_snapshot_id: str
    capabilities: tuple[str, ...]
    delegation_allowed: bool
    authority_digest: str
    origin_skill_id: str
    origin_skill_name: str
    origin_owner_kernel: str
    origin_execution_id: str
    origin_step_id: str
    extension_skill: str
    origin_receipt_ref: str
    origin_receipt_state: str
    origin_receipt_digest: str
    origin_signing_key_id: str
    origin_signature_algorithm: str
    origin_signature: str
    host_envelope: HostSignedEnvelope

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        for field in (
            "operation_invocation_id",
            "environment_id",
            "authority_snapshot_id",
            "origin_skill_id",
            "origin_skill_name",
            "origin_owner_kernel",
            "origin_execution_id",
            "origin_step_id",
            "extension_skill",
            "origin_receipt_ref",
            "origin_receipt_state",
            "origin_signing_key_id",
            "origin_signature_algorithm",
            "origin_signature",
        ):
            _text(getattr(self, field), field)
        require_sha256_digest(
            self.authority_snapshot_id,
            field="authority_snapshot_id",
        )
        if not hmac.compare_digest(self.authority_snapshot_id, self.authority_revision):
            raise ValidationError(
                "authority_snapshot_id does not match authority_revision"
            )
        capabilities = _text_tuple(self.capabilities, "capabilities")
        object.__setattr__(self, "capabilities", tuple(sorted(capabilities)))
        if not isinstance(self.delegation_allowed, bool):
            raise ValidationError("delegation_allowed must be boolean")
        require_sha256_digest(self.authority_digest, field="authority_digest")
        require_sha256_digest(
            self.origin_receipt_digest,
            field="origin_receipt_digest",
        )
        if self.origin_owner_kernel not in {f"K{index}" for index in range(1, 9)}:
            raise ValidationError("origin_owner_kernel is invalid")
        if self.origin_receipt_state not in {
            "PLANNING",
            "EXECUTING",
            "RESUMING",
            "VERIFYING",
            "CERTIFYING",
        }:
            raise ValidationError("origin_receipt_state is not active")
        if self.origin_signature_algorithm not in HostSignedEnvelope._ALGORITHMS:
            raise ValidationError("origin signature algorithm is unsupported")
        if not isinstance(self.host_envelope, HostSignedEnvelope):
            raise ValidationError("runtime authority host envelope must be typed")
        self.host_envelope.verify_payload(
            kind="RUNTIME_AUTHORITY_CAPABILITY",
            payload=self.envelope_payload(),
        )

    def envelope_payload(self) -> Mapping[str, Any]:
        return {
            "tenantId": self.tenant_id,
            "projectId": self.project_id,
            "runId": self.run_id,
            "actorId": self.actor_id,
            "executionEpoch": self.execution_epoch,
            "fencingGeneration": self.fencing_generation,
            "authorityRevision": self.authority_revision,
            "revisionSetId": self.revision_set_id,
            "operationInvocationId": self.operation_invocation_id,
            "environmentId": self.environment_id,
            "authoritySnapshotId": self.authority_snapshot_id,
            "capabilities": list(self.capabilities),
            "delegationAllowed": self.delegation_allowed,
            "authorityDigest": self.authority_digest,
            "originSkillId": self.origin_skill_id,
            "originSkillName": self.origin_skill_name,
            "originOwnerKernel": self.origin_owner_kernel,
            "originExecutionId": self.origin_execution_id,
            "originStepId": self.origin_step_id,
            "extensionSkill": self.extension_skill,
            "originReceiptRef": self.origin_receipt_ref,
            "originReceiptState": self.origin_receipt_state,
            "originReceiptDigest": self.origin_receipt_digest,
            "originSigningKeyId": self.origin_signing_key_id,
            "originSignatureAlgorithm": self.origin_signature_algorithm,
            "originSignature": self.origin_signature,
        }


@dataclass(frozen=True, slots=True)
class CapabilityLeaseRecord:
    tenant_id: str
    project_id: str
    run_id: str
    actor_id: str
    lease_id: str
    invocation_id: str
    environment_id: str
    authority_snapshot_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    capabilities: tuple[str, ...]
    delegation_allowed: bool
    state: CapabilityLeaseState
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    revocation_reason: CapabilityRevocationReason | None
    updated_at: datetime

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        for field in (
            "tenant_id",
            "project_id",
            "run_id",
            "actor_id",
            "lease_id",
            "invocation_id",
            "environment_id",
            "authority_snapshot_id",
        ):
            _text(getattr(self, field), field)
        _positive(self.execution_epoch, "execution_epoch")
        require_sha256_digest(
            self.authority_snapshot_id,
            field="authority_snapshot_id",
        )
        if not hmac.compare_digest(self.authority_snapshot_id, self.authority_revision):
            raise ValidationError(
                "authority_snapshot_id does not match authority_revision"
            )
        object.__setattr__(
            self, "capabilities", _text_tuple(self.capabilities, "capabilities")
        )
        if not self.capabilities:
            raise ValidationError("capabilities must not be empty")
        if not isinstance(self.delegation_allowed, bool):
            raise ValidationError("delegation_allowed must be boolean")
        if not isinstance(self.state, CapabilityLeaseState):
            raise ValidationError("capability lease state must be typed")
        issued = _aware(self.issued_at, "issued_at")
        expires = _aware(self.expires_at, "expires_at")
        _aware(self.updated_at, "updated_at")
        _aware(self.revoked_at, "revoked_at", optional=True)
        if expires is not None and issued is not None and expires <= issued:
            raise ValidationError("expires_at must follow issued_at")
        if issued is not None and self.updated_at < issued:
            raise ValidationError("updated_at cannot precede issued_at")
        if (self.state is CapabilityLeaseState.REVOKED) is (self.revoked_at is None):
            raise ValidationError("revoked_at does not match capability lease state")
        if (self.state is CapabilityLeaseState.REVOKED) is (
            self.revocation_reason is None
        ):
            raise ValidationError(
                "revocation_reason does not match capability lease state"
            )
        if self.revocation_reason is not None and not isinstance(
            self.revocation_reason,
            CapabilityRevocationReason,
        ):
            raise ValidationError("revocation_reason must be typed")
        if (
            self.revoked_at is not None
            and issued is not None
            and self.revoked_at < issued
        ):
            raise ValidationError("revoked_at cannot precede issued_at")
        if (
            self.state is CapabilityLeaseState.EXPIRED
            and expires is not None
            and self.updated_at < expires
        ):
            raise ValidationError("expired capability lease predates expires_at")


@dataclass(frozen=True, slots=True)
class ExecutorGenerationRecord:
    tenant_id: str
    project_id: str
    actor_id: str
    run_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    environment_id: str
    executor_identity: str
    executor_generation: int
    connection_epoch: int
    state: ExecutorGenerationState
    live_probe_evidence_ref: str | None
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None = None
    retired_at: datetime | None = None
    failed_at: datetime | None = None

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        for field in (
            "tenant_id",
            "project_id",
            "actor_id",
            "environment_id",
            "executor_identity",
        ):
            _text(getattr(self, field), field)
        _positive(self.executor_generation, "executor_generation")
        _positive(self.connection_epoch, "connection_epoch")
        if not isinstance(self.state, ExecutorGenerationState):
            raise ValidationError("executor generation state must be typed")
        if self.live_probe_evidence_ref is not None:
            _text(self.live_probe_evidence_ref, "live_probe_evidence_ref")
        for field in ("created_at", "updated_at"):
            _aware(getattr(self, field), field)
        for field in ("activated_at", "retired_at", "failed_at"):
            _aware(getattr(self, field), field, optional=True)
        if self.updated_at < self.created_at:
            raise ValidationError("updated_at cannot precede created_at")
        if self.state is ExecutorGenerationState.CONNECTING and any(
            value is not None
            for value in (self.activated_at, self.retired_at, self.failed_at)
        ):
            raise ValidationError("connecting executor has terminal timestamps")
        if self.state is ExecutorGenerationState.ACTIVE and (
            self.activated_at is None
            or self.retired_at is not None
            or self.failed_at is not None
            or self.live_probe_evidence_ref is None
        ):
            raise ValidationError("active executor lifecycle is invalid")
        if self.state is ExecutorGenerationState.RETIRED and (
            self.activated_at is None
            or self.retired_at is None
            or self.failed_at is not None
        ):
            raise ValidationError("retired executor lifecycle is invalid")
        if self.state is ExecutorGenerationState.FAILED and (
            self.failed_at is None or self.retired_at is not None
        ):
            raise ValidationError("failed executor lifecycle is invalid")
        for field in ("activated_at", "retired_at", "failed_at"):
            value = getattr(self, field)
            if value is not None and value < self.created_at:
                raise ValidationError(f"{field} cannot precede created_at")


@dataclass(frozen=True, slots=True)
class EnvironmentAttachmentRecord:
    tenant_id: str
    project_id: str
    actor_id: str
    run_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    server_id: str
    environment_id: str
    snapshot_id: str
    previous_snapshot_id: str | None
    generation: int
    owner_authority_ref: str
    parent_authority_ref: str
    effective_permissions: tuple[str, ...]
    settings_authority: Mapping[str, Any]
    settings_digest: str
    state: EnvironmentAttachmentState
    created_at: datetime
    updated_at: datetime
    superseded_at: datetime | None = None

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        for field in ("server_id", "environment_id"):
            _text(getattr(self, field), field, maximum=512)
        for field in (
            "snapshot_id",
            "owner_authority_ref",
            "parent_authority_ref",
            "settings_digest",
        ):
            require_sha256_digest(getattr(self, field), field=field)
        if self.previous_snapshot_id is not None:
            require_sha256_digest(
                self.previous_snapshot_id,
                field="previous_snapshot_id",
            )
        generation = _positive(self.generation, "generation")
        if (generation == 1) is (self.previous_snapshot_id is not None):
            raise ValidationError(
                "previous_snapshot_id does not match attachment generation"
            )
        if not hmac.compare_digest(self.owner_authority_ref, self.authority_revision):
            raise ValidationError(
                "owner_authority_ref does not match authority_revision"
            )
        permissions = tuple(
            sorted(_text_tuple(self.effective_permissions, "effective_permissions"))
        )
        object.__setattr__(self, "effective_permissions", permissions)
        if not isinstance(self.settings_authority, Mapping):
            raise ValidationError("settings_authority must be an object")
        expected_settings_digest = digest_object(
            self.settings_authority,
            domain="delta-environment-settings-authority",
        )
        if not hmac.compare_digest(expected_settings_digest, self.settings_digest):
            raise ValidationError("settings_digest does not bind settings_authority")
        object.__setattr__(
            self, "settings_authority", freeze_json(self.settings_authority)
        )
        if not isinstance(self.state, EnvironmentAttachmentState):
            raise ValidationError("environment attachment state must be typed")
        _aware(self.created_at, "created_at")
        _aware(self.updated_at, "updated_at")
        _aware(self.superseded_at, "superseded_at", optional=True)
        if self.updated_at < self.created_at:
            raise ValidationError("attachment updated_at precedes created_at")
        if (self.state is EnvironmentAttachmentState.SUPERSEDED) is (
            self.superseded_at is None
        ):
            raise ValidationError("superseded_at does not match attachment state")


@dataclass(frozen=True, slots=True)
class ExecutorReplacementEffectRecord:
    tenant_id: str
    project_id: str
    actor_id: str
    run_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    effect_id: str
    environment_id: str
    executor_generation: int
    connection_epoch: int
    kind: ExecutorReplacementEffectKind
    state: ExecutorReplacementEffectState
    evidence_ref: str | None
    created_at: datetime
    updated_at: datetime
    reconciled_at: datetime | None = None

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        _text(self.effect_id, "effect_id", maximum=512)
        _text(self.environment_id, "environment_id", maximum=512)
        _positive(self.executor_generation, "executor_generation")
        _positive(self.connection_epoch, "connection_epoch")
        if not isinstance(self.kind, ExecutorReplacementEffectKind):
            raise ValidationError("executor replacement effect kind must be typed")
        if not isinstance(self.state, ExecutorReplacementEffectState):
            raise ValidationError("executor replacement effect state must be typed")
        if self.evidence_ref is not None:
            _text(self.evidence_ref, "evidence_ref")
        for field in ("created_at", "updated_at"):
            _aware(getattr(self, field), field)
        _aware(self.reconciled_at, "reconciled_at", optional=True)
        terminal = self.state is not ExecutorReplacementEffectState.PENDING
        if terminal is (self.reconciled_at is None) or terminal is (
            self.evidence_ref is None
        ):
            raise ValidationError("executor replacement effect lifecycle is invalid")


@dataclass(frozen=True, slots=True)
class WorkspaceLeaseRecord:
    tenant_id: str
    project_id: str
    actor_id: str
    run_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    workspace_id: str
    owner_execution_id: str
    generation: int
    repository_id: str
    base_revision: str
    write_scopes: tuple[str, ...]
    state: WorkspaceLeaseState
    takeover_evidence_ref: str | None
    created_at: datetime
    updated_at: datetime
    retired_at: datetime | None = None

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        for field in (
            "tenant_id",
            "project_id",
            "actor_id",
            "workspace_id",
            "owner_execution_id",
            "repository_id",
            "base_revision",
        ):
            _text(getattr(self, field), field)
        _positive(self.generation, "generation")
        object.__setattr__(self, "write_scopes", _workspace_scopes(self.write_scopes))
        if not self.write_scopes:
            raise ValidationError("write_scopes must not be empty")
        if not isinstance(self.state, WorkspaceLeaseState):
            raise ValidationError("workspace lease state must be typed")
        if self.takeover_evidence_ref is not None:
            _text(self.takeover_evidence_ref, "takeover_evidence_ref")
        if (
            self.state is WorkspaceLeaseState.TAKEOVER_PENDING
            and self.takeover_evidence_ref is None
        ):
            raise ValidationError(
                "takeover-pending workspace requires crash/fence evidence"
            )
        if (
            self.state
            in {
                WorkspaceLeaseState.ACTIVE,
                WorkspaceLeaseState.HANDOFF_PENDING,
            }
            and self.takeover_evidence_ref is not None
        ):
            raise ValidationError(
                "non-crash workspace state cannot contain takeover evidence"
            )
        for field in ("created_at", "updated_at"):
            _aware(getattr(self, field), field)
        _aware(self.retired_at, "retired_at", optional=True)
        if self.updated_at < self.created_at:
            raise ValidationError("updated_at cannot precede created_at")
        if (self.state is WorkspaceLeaseState.RETIRED) is (self.retired_at is None):
            raise ValidationError("retired_at does not match workspace state")
        if self.retired_at is not None and self.retired_at < self.created_at:
            raise ValidationError("retired_at cannot precede created_at")


@dataclass(frozen=True, slots=True)
class DurableEventRegistrationRecord:
    tenant_id: str
    project_id: str
    actor_id: str
    run_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    event_type: str
    owner: str
    schema_version: int
    semantics: DurableEventSemantics
    compatibility: EventCompatibility
    validator_ref: str
    upgrader_ref: str
    projections: tuple[str, ...]
    registration_hash: str
    registered_at: datetime

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        for field in (
            "tenant_id",
            "project_id",
            "actor_id",
            "event_type",
            "owner",
            "validator_ref",
            "upgrader_ref",
        ):
            _text(getattr(self, field), field)
        _positive(self.schema_version, "schema_version")
        if not isinstance(self.semantics, DurableEventSemantics):
            raise ValidationError("durable event semantics must be typed")
        if not isinstance(self.compatibility, EventCompatibility):
            raise ValidationError("durable event compatibility must be typed")
        object.__setattr__(
            self,
            "projections",
            _text_tuple(self.projections, "projections", maximum_items=128),
        )
        require_sha256_digest(self.registration_hash, field="registration_hash")
        expected_registration_hash = digest_object(
            {
                "type": self.event_type,
                "owner": self.owner,
                "schemaVersion": self.schema_version,
                "semantics": self.semantics.value,
                "validator": self.validator_ref,
                "upgrader": self.upgrader_ref,
                "projections": list(self.projections),
                "compatibility": self.compatibility.value,
            },
            domain="delta-event-registration",
        )
        if not hmac.compare_digest(expected_registration_hash, self.registration_hash):
            raise ValidationError(
                "registration_hash does not bind the exact event registration"
            )
        _aware(self.registered_at, "registered_at")


@dataclass(frozen=True, slots=True)
class DurableEventInstanceRecord:
    tenant_id: str
    project_id: str
    actor_id: str
    run_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    event_id: str
    event_type: str
    schema_version: int
    payload_ref: str
    payload_digest: str
    causation_id: str | None
    correlation_id: str
    parent_event_id: str | None
    source_scope: Mapping[str, Any]
    fork_lineage: tuple[str, ...]
    compatibility_decision: EventCompatibilityDecision
    state: DurableEventInstanceState
    skip_reason: str | None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None = None

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        for field in ("event_id", "event_type", "payload_ref", "correlation_id"):
            _text(getattr(self, field), field)
        _positive(self.schema_version, "schema_version")
        require_sha256_digest(self.payload_digest, field="payload_digest")
        if self.causation_id is not None:
            _text(self.causation_id, "causation_id", maximum=512)
        if self.parent_event_id is not None:
            _text(self.parent_event_id, "parent_event_id", maximum=512)
        exact_source_scope = {
            "tenantId": self.tenant_id,
            "projectId": self.project_id,
            "runId": self.run_id,
            "actorId": self.actor_id,
            "executionEpoch": self.execution_epoch,
            "fencingGeneration": self.fencing_generation,
            "authorityRevision": self.authority_revision,
            "revisionSetId": self.revision_set_id,
        }
        if not isinstance(self.source_scope, Mapping) or dict(self.source_scope) != (
            exact_source_scope
        ):
            raise ValidationError(
                "event source_scope does not match its exact durable scope"
            )
        object.__setattr__(self, "source_scope", freeze_json(self.source_scope))
        lineage = _text_tuple(self.fork_lineage, "fork_lineage")
        if self.parent_event_id is None and lineage:
            raise ValidationError("root durable event cannot have fork lineage")
        if self.parent_event_id is not None and (
            not lineage or lineage[-1] != self.parent_event_id
        ):
            raise ValidationError("fork_lineage must terminate at parent_event_id")
        object.__setattr__(self, "fork_lineage", lineage)
        if not isinstance(self.compatibility_decision, EventCompatibilityDecision):
            raise ValidationError("event compatibility decision must be typed")
        if not isinstance(self.state, DurableEventInstanceState):
            raise ValidationError("durable event instance state must be typed")
        if self.skip_reason is not None:
            _text(self.skip_reason, "skip_reason")
        if (self.state is DurableEventInstanceState.SKIPPED) is (
            self.skip_reason is None
        ):
            raise ValidationError("skip_reason does not match event state")
        for field in ("created_at", "updated_at"):
            _aware(getattr(self, field), field)
        _aware(self.processed_at, "processed_at", optional=True)
        terminal = self.state is not DurableEventInstanceState.PENDING
        if terminal is (self.processed_at is None):
            raise ValidationError("processed_at does not match event state")


@dataclass(frozen=True, slots=True)
class DurableEventOwnerChangePreflight:
    action: EventOwnerChangeAction
    owner: str
    target_version: int | None
    allowed: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.action, EventOwnerChangeAction):
            raise ValidationError("event owner change action must be typed")
        _text(self.owner, "owner", maximum=512)
        if self.action is EventOwnerChangeAction.DOWNGRADE:
            if self.target_version is None:
                raise ValidationError("event owner downgrade requires target_version")
            _positive(self.target_version, "target_version")
        elif self.target_version is not None:
            raise ValidationError("event owner uninstall cannot have target_version")
        if not isinstance(self.allowed, bool):
            raise ValidationError("event owner preflight allowed must be boolean")
        blockers = _text_tuple(self.blockers, "blockers")
        object.__setattr__(self, "blockers", blockers)
        if self.allowed is bool(blockers):
            raise ValidationError("event owner preflight blockers contradict decision")


@dataclass(frozen=True, slots=True)
class TypedIngressRecord:
    tenant_id: str
    project_id: str
    run_id: str
    actor_id: str
    ingress_id: str
    producer_execution_id: str
    deduplication_key: str
    kind: TypedIngressKind
    envelope_digest: str
    payload_ref: str
    originating_call_id: str | None
    causation_id: str | None
    correlation_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    occurred_at: datetime
    recorded_at: datetime
    persisted_sequence: int

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        for field in (
            "tenant_id",
            "project_id",
            "run_id",
            "actor_id",
            "ingress_id",
            "producer_execution_id",
            "deduplication_key",
            "payload_ref",
            "correlation_id",
        ):
            _text(getattr(self, field), field)
        if not isinstance(self.kind, TypedIngressKind):
            raise ValidationError("typed ingress kind must be typed")
        require_sha256_digest(self.envelope_digest, field="envelope_digest")
        if self.originating_call_id is not None:
            _text(self.originating_call_id, "originating_call_id", maximum=512)
        if (
            self.kind is TypedIngressKind.TOOL_RESULT
            and self.originating_call_id is None
        ):
            raise ValidationError("tool result ingress requires originating_call_id")
        if self.causation_id is not None:
            _text(self.causation_id, "causation_id", maximum=512)
        _positive(self.execution_epoch, "execution_epoch")
        _positive(self.persisted_sequence, "persisted_sequence")
        _aware(self.occurred_at, "occurred_at")
        _aware(self.recorded_at, "recorded_at")
        if self.recorded_at < self.occurred_at:
            raise ValidationError("typed ingress recorded_at precedes occurred_at")


@dataclass(frozen=True, slots=True)
class TypedIngressPage:
    records: tuple[TypedIngressRecord, ...]
    next_cursor: tuple[datetime, str] | None

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple) or any(
            not isinstance(record, TypedIngressRecord) for record in self.records
        ):
            raise ValidationError("typed ingress page records must be typed")
        keys = tuple((record.occurred_at, record.ingress_id) for record in self.records)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValidationError("typed ingress page ordering is unstable")
        if self.next_cursor is not None:
            if (
                not isinstance(self.next_cursor, tuple)
                or len(self.next_cursor) != 2
                or not isinstance(self.next_cursor[1], str)
            ):
                raise ValidationError("typed ingress cursor is invalid")
            _aware(self.next_cursor[0], "next_cursor.occurred_at")
            _text(self.next_cursor[1], "next_cursor.ingress_id", maximum=512)


@dataclass(frozen=True, slots=True)
class SubagentBudgetReservationBindingRecord:
    tenant_id: str
    project_id: str
    run_id: str
    actor_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    reservation_id: str
    operation_invocation_id: str
    parent_execution_id: str
    environment_id: str
    authority_snapshot_id: str
    provider: str
    model: str
    reasoning_effort: str
    child_authority: tuple[str, ...]
    child_tools: tuple[str, ...]
    max_output_tokens: int
    max_cost_budget: str
    wall_clock_deadline: datetime
    tool_plan_hash: str
    authority_envelope_digest: str
    host_envelope: HostSignedEnvelope
    state: SubagentBudgetReservationState
    created_at: datetime
    updated_at: datetime
    consumed_at: datetime | None = None

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        for field in (
            "reservation_id",
            "operation_invocation_id",
            "parent_execution_id",
            "environment_id",
            "authority_snapshot_id",
            "provider",
            "model",
            "reasoning_effort",
        ):
            _text(getattr(self, field), field)
        require_sha256_digest(
            self.authority_snapshot_id,
            field="authority_snapshot_id",
        )
        if not hmac.compare_digest(self.authority_snapshot_id, self.authority_revision):
            raise ValidationError(
                "authority_snapshot_id does not match authority_revision"
            )
        object.__setattr__(
            self,
            "child_authority",
            tuple(sorted(_text_tuple(self.child_authority, "child_authority"))),
        )
        object.__setattr__(
            self,
            "child_tools",
            tuple(sorted(_text_tuple(self.child_tools, "child_tools"))),
        )
        _positive(self.max_output_tokens, "max_output_tokens")
        object.__setattr__(
            self,
            "max_cost_budget",
            _decimal_budget(self.max_cost_budget),
        )
        _aware(self.wall_clock_deadline, "wall_clock_deadline")
        require_sha256_digest(self.tool_plan_hash, field="tool_plan_hash")
        require_sha256_digest(
            self.authority_envelope_digest,
            field="authority_envelope_digest",
        )
        if not isinstance(self.host_envelope, HostSignedEnvelope):
            raise ValidationError("subagent reservation host envelope must be typed")
        self.host_envelope.verify_payload(
            kind="SUBAGENT_BUDGET_RESERVATION",
            payload=self.envelope_payload(),
        )
        if not isinstance(self.state, SubagentBudgetReservationState):
            raise ValidationError("subagent budget reservation state must be typed")
        _aware(self.created_at, "created_at")
        _aware(self.updated_at, "updated_at")
        _aware(self.consumed_at, "consumed_at", optional=True)
        if self.updated_at < self.created_at:
            raise ValidationError("updated_at cannot precede created_at")
        if (self.state is SubagentBudgetReservationState.CONSUMED) is (
            self.consumed_at is None
        ):
            raise ValidationError(
                "consumed_at does not match subagent budget reservation state"
            )
        if self.consumed_at is not None and self.consumed_at < self.created_at:
            raise ValidationError("consumed_at cannot precede created_at")

    def envelope_payload(self) -> Mapping[str, Any]:
        return {
            "tenantId": self.tenant_id,
            "projectId": self.project_id,
            "runId": self.run_id,
            "actorId": self.actor_id,
            "executionEpoch": self.execution_epoch,
            "fencingGeneration": self.fencing_generation,
            "authorityRevision": self.authority_revision,
            "revisionSetId": self.revision_set_id,
            "reservationId": self.reservation_id,
            "operationInvocationId": self.operation_invocation_id,
            "parentExecutionId": self.parent_execution_id,
            "environmentId": self.environment_id,
            "authoritySnapshotId": self.authority_snapshot_id,
            "provider": self.provider,
            "model": self.model,
            "reasoningEffort": self.reasoning_effort,
            "childAuthority": list(self.child_authority),
            "childTools": list(self.child_tools),
            "maxOutputTokens": self.max_output_tokens,
            "maxCostBudget": self.max_cost_budget,
            "wallClockDeadline": self.wall_clock_deadline.astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "toolPlanHash": self.tool_plan_hash,
            "authorityEnvelopeDigest": self.authority_envelope_digest,
        }


@dataclass(frozen=True, slots=True)
class SubagentExecutionSpecRecord:
    tenant_id: str
    project_id: str
    run_id: str
    actor_id: str
    invocation_id: str
    parent_execution_id: str
    provider: str
    model: str
    reasoning_effort: str
    authority_snapshot_id: str
    environment_id: str
    budget_reservation_id: str
    max_output_tokens: int
    tool_plan_hash: str
    child_authority: tuple[str, ...]
    child_tools: tuple[str, ...]
    cost_budget: str
    wall_clock_deadline: datetime
    spec_hash: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    recorded_at: datetime
    state: SubagentExecutionSpecState = SubagentExecutionSpecState.RESERVED
    consumer_execution_id: str | None = None
    consumed_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        for field in (
            "tenant_id",
            "project_id",
            "run_id",
            "actor_id",
            "invocation_id",
            "parent_execution_id",
            "provider",
            "model",
            "reasoning_effort",
            "authority_snapshot_id",
            "environment_id",
            "budget_reservation_id",
        ):
            _text(getattr(self, field), field)
        require_sha256_digest(
            self.authority_snapshot_id,
            field="authority_snapshot_id",
        )
        if not hmac.compare_digest(self.authority_snapshot_id, self.authority_revision):
            raise ValidationError(
                "authority_snapshot_id does not match authority_revision"
            )
        tokens = _positive(self.max_output_tokens, "max_output_tokens")
        if tokens > 1_000_000:
            raise ValidationError("max_output_tokens exceeds the supported bound")
        if self.reasoning_effort not in {
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
            "ultra",
        }:
            raise ValidationError("reasoning_effort is unsupported")
        require_sha256_digest(self.tool_plan_hash, field="tool_plan_hash")
        child_authority = tuple(
            sorted(_text_tuple(self.child_authority, "child_authority"))
        )
        child_tools = tuple(sorted(_text_tuple(self.child_tools, "child_tools")))
        object.__setattr__(self, "child_authority", child_authority)
        object.__setattr__(self, "child_tools", child_tools)
        cost_budget = _decimal_budget(self.cost_budget)
        deadline = _aware(self.wall_clock_deadline, "wall_clock_deadline")
        require_sha256_digest(self.spec_hash, field="spec_hash")
        _positive(self.execution_epoch, "execution_epoch")
        recorded_at = _aware(self.recorded_at, "recorded_at")
        if deadline is not None and recorded_at is not None and deadline <= recorded_at:
            raise ValidationError("wall_clock_deadline must follow recorded_at")
        expected_spec_hash = digest_object(
            {
                "invocationId": self.invocation_id,
                "parentExecutionId": self.parent_execution_id,
                "provider": self.provider,
                "model": self.model,
                "reasoningEffort": self.reasoning_effort,
                "authoritySnapshotId": self.authority_snapshot_id,
                "environmentId": self.environment_id,
                "budgetReservationId": self.budget_reservation_id,
                "maxOutputTokens": self.max_output_tokens,
                "toolPlanHash": self.tool_plan_hash,
                "childAuthority": list(child_authority),
                "childTools": list(child_tools),
                "costBudget": cost_budget,
                "wallClockDeadline": _wire_time(self.wall_clock_deadline),
            },
            domain="delta-subagent-execution-spec",
        )
        if not hmac.compare_digest(expected_spec_hash, self.spec_hash):
            raise ValidationError(
                "spec_hash does not bind the exact subagent specification"
            )
        if not isinstance(self.state, SubagentExecutionSpecState):
            raise ValidationError("subagent execution spec state must be typed")
        consumed_at = _aware(self.consumed_at, "consumed_at", optional=True)
        updated_at = _aware(
            self.recorded_at if self.updated_at is None else self.updated_at,
            "updated_at",
        )
        object.__setattr__(self, "updated_at", updated_at)
        if (
            updated_at is not None
            and recorded_at is not None
            and updated_at < recorded_at
        ):
            raise ValidationError("subagent spec updated_at precedes recorded_at")
        if self.state is SubagentExecutionSpecState.RESERVED:
            if self.consumer_execution_id is not None or consumed_at is not None:
                raise ValidationError(
                    "reserved subagent spec cannot have consumption data"
                )
        else:
            if self.consumer_execution_id is None or consumed_at is None:
                raise ValidationError(
                    "consumed subagent spec requires exact consumer and time"
                )
            _text(self.consumer_execution_id, "consumer_execution_id", maximum=512)
            if recorded_at is not None and consumed_at < recorded_at:
                raise ValidationError("subagent spec consumed_at precedes recorded_at")


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceInvocationClaimRecord:
    tenant_id: str
    project_id: str
    run_id: str
    actor_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    invocation_id: str
    request_digest: str
    claim_epoch: int
    state: RuntimeAssuranceInvocationState
    disposition: RuntimeAssuranceClaimDisposition
    result_ref: str | None
    result_digest: str | None
    claimed_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    recovery_evidence_ref: str | None = None

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        _text(self.invocation_id, "invocation_id", maximum=512)
        require_sha256_digest(self.request_digest, field="request_digest")
        _positive(self.claim_epoch, "claim_epoch")
        if not isinstance(self.state, RuntimeAssuranceInvocationState):
            raise ValidationError("invocation claim state must be typed")
        if not isinstance(self.disposition, RuntimeAssuranceClaimDisposition):
            raise ValidationError("invocation claim disposition must be typed")
        allowed_dispositions = {
            RuntimeAssuranceInvocationState.IN_PROGRESS: {
                RuntimeAssuranceClaimDisposition.ACQUIRED
            },
            RuntimeAssuranceInvocationState.COMPLETED: {
                RuntimeAssuranceClaimDisposition.COMPLETED,
                RuntimeAssuranceClaimDisposition.COMPLETED_REPLAY,
            },
            RuntimeAssuranceInvocationState.RECOVERY_REQUIRED: {
                RuntimeAssuranceClaimDisposition.RECOVERY_REQUIRED
            },
        }
        if self.disposition not in allowed_dispositions[self.state]:
            raise ValidationError("invocation claim disposition contradicts state")
        for field in ("claimed_at", "updated_at"):
            _aware(getattr(self, field), field)
        _aware(self.completed_at, "completed_at", optional=True)
        if self.updated_at < self.claimed_at:
            raise ValidationError("invocation claim updated_at precedes claimed_at")
        completed = self.state is RuntimeAssuranceInvocationState.COMPLETED
        if completed is (self.completed_at is None):
            raise ValidationError("completed_at does not match invocation claim state")
        if completed:
            if self.result_ref is None or self.result_digest is None:
                raise ValidationError("completed invocation claim requires a result")
            _text(self.result_ref, "result_ref")
            require_sha256_digest(self.result_digest, field="result_digest")
            if self.completed_at is not None and self.completed_at < self.claimed_at:
                raise ValidationError("completed_at precedes invocation claim")
        elif self.result_ref is not None or self.result_digest is not None:
            raise ValidationError("unfinished invocation claim cannot contain a result")
        if self.recovery_evidence_ref is not None:
            _text(self.recovery_evidence_ref, "recovery_evidence_ref")
            if not completed:
                raise ValidationError(
                    "unfinished invocation claim cannot contain recovery evidence"
                )

    @property
    def execute_allowed(self) -> bool:
        return self.disposition is RuntimeAssuranceClaimDisposition.ACQUIRED

    @property
    def replay(self) -> bool:
        return self.disposition is RuntimeAssuranceClaimDisposition.COMPLETED_REPLAY


@dataclass(frozen=True, slots=True)
class RuntimeAssuranceScopeSnapshot:
    tenant_id: str
    project_id: str
    actor_id: str
    run_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    pending_tool_calls: tuple[PendingToolCallBindingRecord, ...]
    tool_results: tuple[ToolResultCommitRecord, ...]
    step_plans: tuple[StepExecutionPlanRecord, ...]
    runtime_authority_receipts: tuple[RuntimeAuthorityCapabilityReceiptRecord, ...]
    capability_leases: tuple[CapabilityLeaseRecord, ...]
    executor_generations: tuple[ExecutorGenerationRecord, ...]
    environment_attachments: tuple[EnvironmentAttachmentRecord, ...]
    executor_replacement_effects: tuple[ExecutorReplacementEffectRecord, ...]
    workspace_leases: tuple[WorkspaceLeaseRecord, ...]
    event_registrations: tuple[DurableEventRegistrationRecord, ...]
    durable_events: tuple[DurableEventInstanceRecord, ...]
    typed_ingress: tuple[TypedIngressRecord, ...]
    subagent_budget_reservations: tuple[SubagentBudgetReservationBindingRecord, ...]
    subagent_execution_specs: tuple[SubagentExecutionSpecRecord, ...]

    def __post_init__(self) -> None:
        _record_scope(
            self.tenant_id,
            self.project_id,
            self.run_id,
            self.actor_id,
            self.execution_epoch,
            self.fencing_generation,
            self.authority_revision,
            self.revision_set_id,
        )
        collections: tuple[tuple[str, tuple[Any, ...], type[Any]], ...] = (
            (
                "pending_tool_calls",
                self.pending_tool_calls,
                PendingToolCallBindingRecord,
            ),
            ("tool_results", self.tool_results, ToolResultCommitRecord),
            ("step_plans", self.step_plans, StepExecutionPlanRecord),
            (
                "runtime_authority_receipts",
                self.runtime_authority_receipts,
                RuntimeAuthorityCapabilityReceiptRecord,
            ),
            ("capability_leases", self.capability_leases, CapabilityLeaseRecord),
            (
                "executor_generations",
                self.executor_generations,
                ExecutorGenerationRecord,
            ),
            (
                "environment_attachments",
                self.environment_attachments,
                EnvironmentAttachmentRecord,
            ),
            (
                "executor_replacement_effects",
                self.executor_replacement_effects,
                ExecutorReplacementEffectRecord,
            ),
            ("workspace_leases", self.workspace_leases, WorkspaceLeaseRecord),
            (
                "event_registrations",
                self.event_registrations,
                DurableEventRegistrationRecord,
            ),
            ("durable_events", self.durable_events, DurableEventInstanceRecord),
            ("typed_ingress", self.typed_ingress, TypedIngressRecord),
            (
                "subagent_budget_reservations",
                self.subagent_budget_reservations,
                SubagentBudgetReservationBindingRecord,
            ),
            (
                "subagent_execution_specs",
                self.subagent_execution_specs,
                SubagentExecutionSpecRecord,
            ),
        )
        for field, records, record_type in collections:
            if not isinstance(records, tuple) or any(
                not isinstance(record, record_type) for record in records
            ):
                raise ValidationError(f"{field} is not a typed immutable tuple")
        scoped_records: tuple[Any, ...] = (
            *self.pending_tool_calls,
            *self.tool_results,
            *self.step_plans,
            *self.runtime_authority_receipts,
            *self.capability_leases,
            *self.executor_generations,
            *self.environment_attachments,
            *self.executor_replacement_effects,
            *self.workspace_leases,
            *self.event_registrations,
            *self.durable_events,
            *self.typed_ingress,
            *self.subagent_budget_reservations,
            *self.subagent_execution_specs,
        )
        if any(
            (
                record.tenant_id,
                record.project_id,
                record.actor_id,
                record.run_id,
                record.execution_epoch,
                record.fencing_generation,
                record.authority_revision,
                record.revision_set_id,
            )
            != (
                self.tenant_id,
                self.project_id,
                self.actor_id,
                self.run_id,
                self.execution_epoch,
                self.fencing_generation,
                self.authority_revision,
                self.revision_set_id,
            )
            for record in scoped_records
        ):
            raise ValidationError(
                "runtime-assurance record escaped exact snapshot scope"
            )
        identities: tuple[tuple[str, tuple[Any, ...]], ...] = (
            (
                "pending_tool_calls",
                tuple(record.call_id for record in self.pending_tool_calls),
            ),
            (
                "tool_results",
                tuple(
                    (
                        record.invocation_id,
                        record.call_id,
                        record.attempt,
                        record.execution_epoch,
                    )
                    for record in self.tool_results
                ),
            ),
            ("step_plans", tuple(record.plan_id for record in self.step_plans)),
            (
                "runtime_authority_receipts",
                tuple(
                    record.operation_invocation_id
                    for record in self.runtime_authority_receipts
                ),
            ),
            (
                "capability_leases",
                tuple(record.lease_id for record in self.capability_leases),
            ),
            (
                "executor_generations",
                tuple(
                    (
                        record.environment_id,
                        record.executor_generation,
                        record.connection_epoch,
                    )
                    for record in self.executor_generations
                ),
            ),
            (
                "workspace_leases",
                tuple(
                    (record.workspace_id, record.generation)
                    for record in self.workspace_leases
                ),
            ),
            (
                "environment_attachments",
                tuple(
                    (record.server_id, record.environment_id, record.generation)
                    for record in self.environment_attachments
                ),
            ),
            (
                "executor_replacement_effects",
                tuple(record.effect_id for record in self.executor_replacement_effects),
            ),
            (
                "event_registrations",
                tuple(
                    (record.event_type, record.schema_version)
                    for record in self.event_registrations
                ),
            ),
            (
                "typed_ingress",
                tuple(record.ingress_id for record in self.typed_ingress),
            ),
            (
                "durable_events",
                tuple(record.event_id for record in self.durable_events),
            ),
            (
                "typed_ingress_deduplication",
                tuple(
                    (record.producer_execution_id, record.deduplication_key)
                    for record in self.typed_ingress
                ),
            ),
            (
                "subagent_execution_specs",
                tuple(record.invocation_id for record in self.subagent_execution_specs),
            ),
            (
                "subagent_budget_reservation_bindings",
                tuple(
                    record.reservation_id
                    for record in self.subagent_budget_reservations
                ),
            ),
            (
                "subagent_budget_reservations",
                tuple(
                    record.budget_reservation_id
                    for record in self.subagent_execution_specs
                ),
            ),
        )
        for field, keys in identities:
            if len(keys) != len(set(keys)):
                raise ValidationError(f"{field} contains duplicate durable identities")


@runtime_checkable
class RuntimeAssuranceStore(Protocol):
    """Exact durable interface implemented by the PostgreSQL 17 store."""

    def claim_runtime_assurance_invocation(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        request_digest: str,
        now: datetime | None = None,
    ) -> ContextManager[RuntimeAssuranceInvocationClaimRecord]: ...

    def complete_runtime_assurance_invocation(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        request_digest: str,
        expected_claim_epoch: int,
        result_ref: str,
        result_digest: str,
        now: datetime | None = None,
    ) -> RuntimeAssuranceInvocationClaimRecord: ...

    def reconcile_runtime_assurance_invocation(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        request_digest: str,
        expected_claim_epoch: int,
        result_ref: str,
        result_digest: str,
        recovery_evidence_ref: str,
        now: datetime | None = None,
    ) -> RuntimeAssuranceInvocationClaimRecord: ...

    def load_runtime_assurance_scope(
        self, context: SecurityContext, *, revision_set_id: str
    ) -> RuntimeAssuranceScopeSnapshot: ...

    def bind_runtime_authority_capability_receipt(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        operation_invocation_id: str,
        environment_id: str,
        authority_snapshot_id: str,
        capabilities: Sequence[str],
        delegation_allowed: bool,
        authority_digest: str,
        origin_skill_id: str,
        origin_skill_name: str,
        origin_owner_kernel: str,
        origin_execution_id: str,
        origin_step_id: str,
        extension_skill: str,
        origin_receipt_ref: str,
        origin_receipt_state: str,
        origin_receipt_digest: str,
        origin_signing_key_id: str,
        origin_signature_algorithm: str,
        origin_signature: str,
        host_envelope: HostSignedEnvelope,
        now: datetime | None = None,
    ) -> RuntimeAuthorityCapabilityReceiptRecord: ...

    def bind_pending_tool_call(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        call_id: str,
        attempt: int,
        execution_plan_hash: str,
        environment_id: str,
        tool_id: str,
        authority_snapshot_id: str,
        now: datetime | None = None,
    ) -> PendingToolCallBindingRecord: ...

    def begin_tool_result(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        call_id: str,
        attempt: int,
        execution_plan_hash: str,
        environment_id: str,
        authority_snapshot_id: str,
        raw_result_ref: str,
        now: datetime | None = None,
    ) -> ToolResultCommitRecord: ...

    def mark_tool_result_intercepting(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        call_id: str,
        attempt: int,
        execution_epoch: int,
        expected_state: ToolResultCommitState = ToolResultCommitState.RAW_CAPTURED,
        now: datetime | None = None,
    ) -> ToolResultCommitRecord: ...

    def commit_tool_result(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        call_id: str,
        attempt: int,
        execution_plan_hash: str,
        environment_id: str,
        authority_snapshot_id: str,
        raw_result_ref: str,
        effective_result_ref: str,
        interceptor_chain: Sequence[InterceptorCommitRecord],
        mutation_provenance_ref: str | None = None,
        now: datetime | None = None,
    ) -> ToolResultCommitRecord: ...

    def transition_tool_result(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        subject_invocation_id: str,
        operation_invocation_id: str,
        call_id: str,
        attempt: int,
        execution_epoch: int,
        expected_execution_plan_hash: str,
        expected_environment_id: str,
        expected_authority_snapshot_id: str,
        expected_state: ToolResultCommitState,
        target_state: ToolResultCommitState,
        failure_kind: ToolResultFailureKind | None = None,
        failure_reason: str | None = None,
        now: datetime | None = None,
    ) -> ToolResultCommitRecord: ...

    def abort_tool_result(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        subject_invocation_id: str,
        operation_invocation_id: str,
        call_id: str,
        attempt: int,
        execution_plan_hash: str,
        environment_id: str,
        authority_snapshot_id: str,
        raw_result_ref: str,
        effective_result_ref: str,
        interceptor_chain: Sequence[InterceptorCommitRecord],
        failure_kind: ToolResultFailureKind,
        failure_reason: str,
        mutation_provenance_ref: str | None = None,
        now: datetime | None = None,
    ) -> ToolResultCommitRecord: ...

    def reconcile_tool_result_abort(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        call_id: str,
        attempt: int,
        expected_claim_epoch: int,
        execution_plan_hash: str,
        environment_id: str,
        authority_snapshot_id: str,
        raw_result_ref: str,
        effective_result_ref: str,
        recovery_evidence_ref: str,
        interceptor_chain: Sequence[InterceptorCommitRecord],
        failure_kind: ToolResultFailureKind,
        failure_reason: str,
        mutation_provenance_ref: str | None = None,
        expected_state: ToolResultCommitState,
        now: datetime | None = None,
    ) -> ToolResultCommitRecord: ...

    def record_step_plan(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        plan_id: str,
        step_id: str,
        plan_hash: str,
        model_snapshot: Mapping[str, Any],
        tool_plan: Mapping[str, Any],
        tool_contracts: Mapping[str, Any],
        handler_digests: Mapping[str, str],
        capabilities: Sequence[str],
        environment_snapshot_id: str,
        authority_snapshot_id: str,
        tool_mode: str,
        now: datetime | None = None,
    ) -> StepExecutionPlanRecord: ...

    def transition_step_plan(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        plan_id: str,
        expected_state: StepPlanState,
        target_state: StepPlanState,
        now: datetime | None = None,
    ) -> StepExecutionPlanRecord: ...

    def activate_step_plan(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        plan_id: str,
        expected_state: StepPlanState = StepPlanState.FINALIZED,
        now: datetime | None = None,
    ) -> StepExecutionPlanRecord: ...

    def issue_capability_lease(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        lease_id: str,
        invocation_id: str,
        environment_id: str,
        authority_snapshot_id: str,
        capabilities: Sequence[str],
        expires_at: datetime,
        delegation_allowed: bool = False,
        now: datetime | None = None,
    ) -> CapabilityLeaseRecord: ...

    def revoke_capability_lease(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        lease_id: str,
        subject_invocation_id: str,
        operation_invocation_id: str,
        expected_environment_id: str,
        expected_authority_snapshot_id: str,
        authorized_capabilities: Sequence[str],
        reason: CapabilityRevocationReason,
        now: datetime | None = None,
    ) -> CapabilityLeaseRecord: ...

    def revoke_invocation_capability_leases(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str | None,
        reason: CapabilityRevocationReason,
        environment_id: str | None = None,
        now: datetime | None = None,
    ) -> tuple[CapabilityLeaseRecord, ...]: ...

    def revoke_run_capability_leases(
        self,
        context: SecurityContext,
        *,
        reason: CapabilityRevocationReason,
        now: datetime | None = None,
    ) -> tuple[CapabilityLeaseRecord, ...]: ...

    def record_capability_lease_use(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        lease_id: str,
        invocation_id: str,
        operation_invocation_id: str,
        expected_environment_id: str,
        expected_authority_snapshot_id: str,
        authorized_capabilities: Sequence[str],
        capability: str,
        now: datetime | None = None,
    ) -> CapabilityLeaseRecord: ...

    def audit_capability_use_denial(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        lease_id: str,
        subject_invocation_id: str | None,
        operation_invocation_id: str,
        capability: str,
        reason: CapabilityUseDenialReason,
        now: datetime | None = None,
    ) -> str: ...

    def expire_capability_lease(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        lease_id: str,
        now: datetime | None = None,
    ) -> CapabilityLeaseRecord: ...

    def record_executor_generation(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        environment_id: str,
        executor_identity: str,
        executor_generation: int,
        connection_epoch: int,
        now: datetime | None = None,
    ) -> ExecutorGenerationRecord: ...

    def transition_executor_generation(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        environment_id: str,
        executor_generation: int,
        connection_epoch: int,
        expected_state: ExecutorGenerationState,
        target_state: ExecutorGenerationState,
        live_probe_evidence_ref: str | None = None,
        now: datetime | None = None,
    ) -> ExecutorGenerationRecord: ...

    def advance_executor_generation(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        environment_id: str,
        executor_identity: str,
        expected_generation: int,
        expected_connection_epoch: int,
        replace_identity: bool,
        now: datetime | None = None,
    ) -> ExecutorGenerationRecord: ...

    def record_environment_attachment(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        server_id: str,
        environment_id: str,
        snapshot_id: str,
        owner_authority_ref: str,
        parent_authority_ref: str,
        effective_permissions: Sequence[str],
        settings_authority: Mapping[str, Any],
        settings_digest: str,
        now: datetime | None = None,
    ) -> EnvironmentAttachmentRecord: ...

    def refresh_environment_attachment(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        server_id: str,
        environment_id: str,
        expected_snapshot_id: str,
        expected_generation: int,
        snapshot_id: str,
        owner_authority_ref: str,
        parent_authority_ref: str,
        effective_permissions: Sequence[str],
        settings_authority: Mapping[str, Any],
        settings_digest: str,
        now: datetime | None = None,
    ) -> EnvironmentAttachmentRecord: ...

    def record_executor_replacement_effect(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        effect_id: str,
        environment_id: str,
        executor_generation: int,
        connection_epoch: int,
        kind: ExecutorReplacementEffectKind,
        now: datetime | None = None,
    ) -> ExecutorReplacementEffectRecord: ...

    def reconcile_executor_replacement_effect(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        effect_id: str,
        expected_state: ExecutorReplacementEffectState,
        target_state: ExecutorReplacementEffectState,
        evidence_ref: str,
        now: datetime | None = None,
    ) -> ExecutorReplacementEffectRecord: ...

    def bind_workspace(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        workspace_id: str,
        owner_execution_id: str,
        generation: int,
        repository_id: str,
        base_revision: str,
        write_scopes: Sequence[str],
        now: datetime | None = None,
    ) -> WorkspaceLeaseRecord: ...

    def request_workspace_handoff(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        workspace_id: str,
        expected_generation: int,
        now: datetime | None = None,
    ) -> WorkspaceLeaseRecord: ...

    def mark_workspace_takeover_pending(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        workspace_id: str,
        expected_generation: int,
        crash_evidence_ref: str,
        now: datetime | None = None,
    ) -> WorkspaceLeaseRecord: ...

    def takeover_workspace(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        workspace_id: str,
        expected_generation: int,
        new_owner_execution_id: str,
        base_revision: str | None = None,
        write_scopes: Sequence[str] | None = None,
        now: datetime | None = None,
    ) -> WorkspaceLeaseRecord: ...

    def retire_workspace(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        workspace_id: str,
        expected_generation: int,
        expected_state: WorkspaceLeaseState,
        now: datetime | None = None,
    ) -> WorkspaceLeaseRecord: ...

    def register_durable_event(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        event_type: str,
        owner: str,
        schema_version: int,
        semantics: DurableEventSemantics,
        compatibility: EventCompatibility,
        validator_ref: str,
        upgrader_ref: str,
        projections: Sequence[str],
        registration_hash: str,
        now: datetime | None = None,
    ) -> DurableEventRegistrationRecord: ...

    def append_durable_event(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        event_id: str,
        event_type: str,
        schema_version: int,
        payload_ref: str,
        payload_digest: str,
        correlation_id: str,
        causation_id: str | None = None,
        parent_event_id: str | None = None,
        fork_lineage: Sequence[str] = (),
        compatibility_decision: EventCompatibilityDecision = EventCompatibilityDecision.EXACT,
        now: datetime | None = None,
    ) -> DurableEventInstanceRecord: ...

    def replay_durable_event(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        event_id: str,
        expected_state: DurableEventInstanceState,
        target_state: DurableEventInstanceState,
        compatibility_decision: EventCompatibilityDecision,
        skip_reason: str | None = None,
        now: datetime | None = None,
    ) -> DurableEventInstanceRecord: ...

    def migrate_durable_event(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        source_event_id: str,
        event_id: str,
        target_schema_version: int,
        payload_ref: str,
        payload_digest: str,
        now: datetime | None = None,
    ) -> DurableEventInstanceRecord: ...

    def preflight_event_owner_change(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        action: EventOwnerChangeAction,
        owner: str,
        target_version: int | None = None,
        now: datetime | None = None,
    ) -> DurableEventOwnerChangePreflight: ...

    def fork_durable_event_lineage(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        parent_event_id: str,
        event_id: str,
        payload_ref: str,
        payload_digest: str,
        now: datetime | None = None,
    ) -> DurableEventInstanceRecord: ...

    def record_typed_ingress(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        ingress_id: str,
        producer_execution_id: str,
        deduplication_key: str,
        kind: TypedIngressKind,
        envelope_digest: str,
        payload_ref: str,
        correlation_id: str,
        causation_id: str | None = None,
        originating_call_id: str | None = None,
        occurred_at: datetime | None = None,
        now: datetime | None = None,
    ) -> tuple[TypedIngressRecord, bool]: ...

    def page_typed_ingress(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        correlation_id: str,
        after: tuple[datetime, str] | None = None,
        limit: int = 100,
    ) -> TypedIngressPage: ...

    def bind_subagent_budget_reservation(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        reservation_id: str,
        operation_invocation_id: str,
        parent_execution_id: str,
        environment_id: str,
        authority_snapshot_id: str,
        provider: str,
        model: str,
        reasoning_effort: str,
        child_authority: Sequence[str],
        child_tools: Sequence[str],
        max_output_tokens: int,
        max_cost_budget: str,
        wall_clock_deadline: datetime,
        tool_plan_hash: str,
        authority_envelope_digest: str,
        host_envelope: HostSignedEnvelope,
        now: datetime | None = None,
    ) -> SubagentBudgetReservationBindingRecord: ...

    def record_subagent_execution_spec(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        parent_execution_id: str,
        provider: str,
        model: str,
        reasoning_effort: str,
        authority_snapshot_id: str,
        environment_id: str,
        budget_reservation_id: str,
        max_output_tokens: int,
        tool_plan_hash: str,
        child_authority: Sequence[str],
        child_tools: Sequence[str],
        cost_budget: str,
        wall_clock_deadline: datetime,
        spec_hash: str,
        now: datetime | None = None,
    ) -> SubagentExecutionSpecRecord: ...

    def consume_subagent_execution_spec(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        budget_reservation_id: str,
        consumer_execution_id: str,
        now: datetime | None = None,
    ) -> SubagentExecutionSpecRecord: ...
