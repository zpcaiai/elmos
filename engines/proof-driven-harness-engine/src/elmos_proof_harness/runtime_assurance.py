"""Durable, internal-only control plane for the v3.1 assurance delta.

The archive that declares the thirteen delta Skills is never imported or
executed.  This module binds the repository-owned exact handlers to the
existing content-addressed evidence service and to the PostgreSQL 17 durable
port.  It intentionally exposes no HTTP route: authenticated host code must
mint and register the exact authority snapshot for each invocation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hmac
import json
from pathlib import Path
import threading
import time
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

from .assurance_policies import (
    HostSecurityContextSigner,
    ManagedWorktreeRegistry,
    PrivilegedPathPolicy,
    SkillTrustDomainPolicy,
)
from .canonical import (
    canonical_json_bytes,
    digest_bytes,
    digest_object,
    freeze_json,
    require_sha256_digest,
)
from .contracts import EvidenceClass, EvidenceProducer, SecurityContext
from .delta import (
    DELTA_API_VERSION,
    DELTA_SKILL_REGISTRY,
    BaseSkillOriginBinding,
    CallIdentity,
    ContractError,
    DeltaInvocation,
    DeltaResult,
    DeltaSkillDescriptor,
    DeltaSkillRuntime,
    PermissionProfile,
    ProtocolCapabilities,
    ResultStatus,
    RuntimeAssuranceAuthority,
    ToolResult,
    _tool_result_commit_key,
)
from .delta_storage import (
    CapabilityLeaseRecord,
    CapabilityLeaseState,
    CapabilityRevocationReason,
    CapabilityUseDenialReason,
    DurableEventInstanceRecord,
    DurableEventInstanceState,
    DurableEventSemantics,
    EventCompatibility,
    EventCompatibilityDecision,
    EventOwnerChangeAction,
    ExecutorGenerationState,
    ExecutorReplacementEffectRecord,
    ExecutorReplacementEffectKind,
    ExecutorReplacementEffectState,
    InterceptorCommitRecord,
    HostSignedEnvelope,
    PendingToolCallBindingState,
    RuntimeAuthorityCapabilityReceiptRecord,
    RuntimeAssuranceClaimDisposition,
    RuntimeAssuranceInvocationClaimRecord,
    RuntimeAssuranceInvocationState,
    RuntimeAssuranceStore,
    StepPlanState,
    SubagentBudgetReservationBindingRecord,
    SubagentBudgetReservationState,
    SubagentExecutionSpecState,
    ToolResultCommitState,
    ToolResultCommitRecord,
    ToolResultFailureKind,
    TypedIngressKind,
    TypedIngressRecord,
    WorkspaceLeaseState,
)
from .errors import (
    AuthorizationError,
    ConflictError,
    IntegrityError,
    NotFoundError,
    ValidationError,
)
from .evidence import EvidenceService


RUNTIME_ASSURANCE_TOOL_DIGEST = digest_bytes(
    b"elmos-proof-driven-harness-engine:3.1.0:runtime-assurance-control-plane",
    domain="tool-identity",
)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValidationError(f"{field} is invalid", details={"field": field})
    return value


def _positive(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError(
            f"{field} must be a positive integer", details={"field": field}
        )
    return int(value)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValidationError(f"{field} must be an object", details={"field": field})
    return value


def _timestamp(value: Any, field: str) -> datetime:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field} is invalid", details={"field": field}) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _strict_json_object(content: bytes) -> Mapping[str, Any]:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise IntegrityError(
                    "durable delta evidence contains a duplicate key",
                    code="DELTA_EVIDENCE_NON_CANONICAL",
                )
            result[key] = value
        return result

    try:
        value = json.loads(content.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrityError(
            "durable delta evidence is not canonical JSON",
            code="DELTA_EVIDENCE_NON_CANONICAL",
        ) from exc
    if not isinstance(value, Mapping):
        raise IntegrityError(
            "durable delta evidence is not an object",
            code="DELTA_EVIDENCE_NON_CANONICAL",
        )
    if canonical_json_bytes(value) != content:
        raise IntegrityError(
            "durable delta evidence bytes are not canonical",
            code="DELTA_EVIDENCE_NON_CANONICAL",
        )
    return value


class EvidenceBackedDeltaStore:
    """Adapt :class:`EvidenceService` to the delta's CAS put/get contract."""

    def __init__(self, evidence: EvidenceService, *, durable: bool) -> None:
        if not isinstance(evidence, EvidenceService):
            raise TypeError("evidence must be an EvidenceService")
        if not isinstance(durable, bool):
            raise TypeError("durable must be boolean")
        self._evidence = evidence
        self.durable = durable

    @staticmethod
    def _reference(value: Mapping[str, Any], domain: str) -> str:
        return "cas:" + digest_object(value, domain=domain)

    def put(
        self,
        context: SecurityContext,
        record: Mapping[str, Any],
        *,
        domain: str = "delta-runtime-result",
    ) -> str:
        if not isinstance(context, SecurityContext):
            raise ContractError(
                "trusted SecurityContext is required for delta evidence"
            )
        frozen = freeze_json(_mapping(record, "delta evidence record"))
        content = canonical_json_bytes(frozen)
        reference = self._reference(frozen, domain)
        try:
            _, existing = self._evidence.read_verified(context, reference)
        except NotFoundError:
            existing = None
        if existing is not None:
            if not hmac.compare_digest(existing, content):
                raise IntegrityError(
                    "content-addressed delta evidence collision",
                    code="DELTA_EVIDENCE_COLLISION",
                )
            return reference

        invocation = record.get("invocation")
        subject_revision = context.authority_revision
        execution_id = context.run_id or "runtime-assurance"
        if isinstance(invocation, Mapping):
            subject_revision = invocation.get("revisionSetId", subject_revision)
            execution_id = str(invocation.get("invocationId", execution_id))
        if subject_revision is None:
            raise ContractError("delta evidence requires an exact subject revision")
        require_sha256_digest(subject_revision, field="subject_revision")
        environment_revision = context.authority_revision or subject_revision
        producer = EvidenceProducer(
            execution_id=_text(execution_id, "execution_id"),
            source="elmos-runtime-assurance-control-plane",
            tool_name="elmos-runtime-assurance-control-plane",
            tool_digest=RUNTIME_ASSURANCE_TOOL_DIGEST,
            environment_revision=environment_revision,
            independent=False,
        )
        try:
            self._evidence.record_bytes(
                context,
                subject_revision=subject_revision,
                kind=str(record.get("kind", "DELTA_RUNTIME_RESULT")),
                evidence_class=EvidenceClass.AUDIT.value,
                scope=f"runtime-assurance:{context.run_id or 'unbound'}",
                content=content,
                media_type="application/vnd.elmos.runtime-assurance+json",
                producer=producer,
                evidence_id=reference,
                artifact_id="artifact:" + reference.removeprefix("cas:"),
                idempotency_key="delta-evidence:" + reference,
            )
        except (ConflictError, IntegrityError):
            # A concurrent writer may have won.  Only exact bytes make that an
            # idempotent replay; every divergence remains an integrity error.
            _, existing = self._evidence.read_verified(context, reference)
            if not hmac.compare_digest(existing, content):
                raise IntegrityError(
                    "content-addressed delta evidence collision",
                    code="DELTA_EVIDENCE_COLLISION",
                )
        return reference

    def get(self, context: SecurityContext, reference: str) -> Mapping[str, Any]:
        candidate = _text(reference, "delta evidence reference")
        _, content = self._evidence.read_verified(context, candidate)
        value = _strict_json_object(content)
        expected = self._reference(value, "delta-runtime-result")
        if not hmac.compare_digest(candidate, expected):
            raise IntegrityError(
                "delta evidence reference digest mismatch",
                code="DELTA_EVIDENCE_DIGEST_MISMATCH",
            )
        frozen = freeze_json(value)
        if not isinstance(frozen, Mapping):  # defensive for static analyzers
            raise IntegrityError("delta evidence did not freeze to an object")
        return MappingProxyType(dict(frozen))


class RegisteredRuntimeAssuranceAuthorityProvider:
    """Host-only immutable authority registry used by internal invocations."""

    # This process-local registry is deliberately an engineering fixture.  A
    # production provider must persist/reconcile authority snapshots across
    # worker restart and advertise that property explicitly.
    trusted_for_production = False
    durable = False
    deadline_enforced = True
    base_origin_receipt_verified = False
    host_envelope_signatures_verified = False
    host_envelope_issuer_durable = False

    def __init__(self) -> None:
        self._authorities: dict[tuple[Any, ...], RuntimeAssuranceAuthority] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _key(
        context: SecurityContext,
        invocation: DeltaInvocation,
    ) -> tuple[Any, ...]:
        return (
            context.tenant_id,
            context.project_id,
            context.actor_id,
            context.run_id,
            context.execution_epoch,
            context.fencing_generation,
            context.authority_revision,
            invocation.revision_set_id,
            invocation.step_id,
            invocation.invocation_id,
        )

    def register(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
        authority: RuntimeAssuranceAuthority,
    ) -> None:
        if not isinstance(invocation, DeltaInvocation) or not isinstance(
            authority, RuntimeAssuranceAuthority
        ):
            raise TypeError("typed invocation and authority are required")
        authority.verify_binding(context, invocation)
        key = self._key(context, invocation)
        with self._lock:
            current = self._authorities.get(key)
            if current is not None and current != authority:
                raise ConflictError(
                    "runtime-assurance authority registration conflicts",
                    code="RUNTIME_AUTHORITY_CONFLICT",
                )
            self._authorities[key] = authority

    def revoke(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
    ) -> None:
        with self._lock:
            self._authorities.pop(self._key(context, invocation), None)

    def __call__(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
    ) -> RuntimeAssuranceAuthority:
        return self.resolve(context, invocation, deadline=None)

    def resolve(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
        *,
        deadline: datetime | None,
    ) -> RuntimeAssuranceAuthority:
        if deadline is not None:
            if deadline.tzinfo is None or deadline.utcoffset() is None:
                raise ContractError("authority lookup deadline must be timezone-aware")
            if datetime.now(UTC) >= deadline.astimezone(UTC):
                raise TimeoutError("runtime-assurance authority lookup timed out")
        with self._lock:
            authority = self._authorities.get(self._key(context, invocation))
        if deadline is not None and datetime.now(UTC) >= deadline.astimezone(UTC):
            raise TimeoutError("runtime-assurance authority lookup timed out")
        if authority is None:
            raise ContractError(
                "host-minted runtime-assurance authority is unavailable or revoked"
            )
        authority.verify_binding(context, invocation)
        return authority

    def verify_origin_receipt(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
        origin: BaseSkillOriginBinding,
        *,
        deadline: datetime | None,
    ) -> bool:
        """Bounded local check; production must replace it with durable lookup."""

        authority = self.resolve(context, invocation, deadline=deadline)
        return authority.originating_base_skill == origin

    def issue_host_envelope(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any],
    ) -> HostSignedEnvelope:
        """Create explicit local engineering evidence, never production proof."""

        return HostSignedEnvelope.local_self_attested(kind=kind, payload=payload)

    def verify_host_envelope(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any],
        envelope: HostSignedEnvelope,
    ) -> bool:
        envelope.verify_payload(kind=kind, payload=payload)
        return (
            envelope.signature_algorithm == "LOCAL_SELF_ATTESTED"
            and envelope.signature == f"LOCAL_SELF_ATTESTED:{envelope.envelope_digest}"
        )


class RuntimeAssuranceDurableCommitter:
    """Map exact handler outcomes to the durable state port."""

    _STATEFUL = frozenset(
        {
            "elmos-tool-result-interception-commit",
            "elmos-step-finalized-execution-plan",
            "elmos-invocation-scoped-capability-lease",
            "elmos-environment-attachment-authority",
            "elmos-executor-generation-fencing",
            "elmos-workspace-ownership-lease",
            "elmos-registered-durable-plugin-events",
            "elmos-typed-external-ingress",
            "elmos-subagent-model-execution-spec",
        }
    )

    def __init__(
        self,
        store: RuntimeAssuranceStore,
        evidence: EvidenceBackedDeltaStore,
        host_envelope_issuer: Any | None = None,
    ) -> None:
        if not isinstance(store, RuntimeAssuranceStore):
            raise TypeError("store does not implement RuntimeAssuranceStore")
        self.store = store
        self.evidence = evidence
        self._host_envelope_issuer = host_envelope_issuer

    def _issue_host_envelope(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any],
    ) -> HostSignedEnvelope:
        issuer = getattr(self._host_envelope_issuer, "issue_host_envelope", None)
        if issuer is None:
            envelope = HostSignedEnvelope.local_self_attested(
                kind=kind,
                payload=payload,
            )
        else:
            envelope = issuer(kind=kind, payload=payload)
        if not isinstance(envelope, HostSignedEnvelope):
            raise IntegrityError(
                "Host envelope issuer returned an invalid signed envelope",
                code="HOST_SIGNED_ENVELOPE_INVALID",
            )
        envelope.verify_payload(kind=kind, payload=payload)
        verifier = getattr(self._host_envelope_issuer, "verify_host_envelope", None)
        verified = (
            verifier(kind=kind, payload=payload, envelope=envelope)
            if callable(verifier)
            else self._host_envelope_issuer is None
        )
        if verified is not True:
            raise IntegrityError(
                "Host signed envelope verification failed closed",
                code="HOST_SIGNED_ENVELOPE_UNVERIFIED",
            )
        if (
            bool(
                getattr(
                    self._host_envelope_issuer,
                    "host_envelope_signatures_verified",
                    False,
                )
            )
            and envelope.signature_algorithm == "LOCAL_SELF_ATTESTED"
        ):
            raise IntegrityError(
                "production Host envelope issuer returned self-attested evidence",
                code="HOST_SIGNED_ENVELOPE_UNTRUSTED",
            )
        return envelope

    def _bind_capability_authority(
        self,
        context: SecurityContext,
        authority: RuntimeAssuranceAuthority,
        invocation: DeltaInvocation,
    ) -> RuntimeAuthorityCapabilityReceiptRecord:
        """Persist the exact Host capability ceiling for this active operation."""

        origin = authority.originating_base_skill
        capabilities = tuple(sorted(authority.capabilities))
        delegation_allowed = (
            invocation.invocation_id in authority.delegation_allowed_invocations
        )
        payload = {
            "tenantId": context.tenant_id,
            "projectId": context.project_id,
            "runId": context.run_id,
            "actorId": context.actor_id,
            "executionEpoch": context.execution_epoch,
            "fencingGeneration": context.fencing_generation,
            "authorityRevision": context.authority_revision,
            "revisionSetId": invocation.revision_set_id,
            "operationInvocationId": invocation.invocation_id,
            "environmentId": authority.security_bindings["environmentId"],
            "authoritySnapshotId": authority.authority_revision,
            "capabilities": list(capabilities),
            "delegationAllowed": delegation_allowed,
            "authorityDigest": authority.authority_digest,
            "originSkillId": origin.skill_id,
            "originSkillName": origin.skill_name,
            "originOwnerKernel": origin.owner_kernel,
            "originExecutionId": origin.execution_id,
            "originStepId": origin.step_id,
            "extensionSkill": origin.extension_skill,
            "originReceiptRef": origin.receipt_ref,
            "originReceiptState": origin.receipt_state,
            "originReceiptDigest": origin.receipt_digest,
            "originSigningKeyId": origin.signing_key_id,
            "originSignatureAlgorithm": origin.signature_algorithm,
            "originSignature": origin.signature,
        }
        host_envelope = self._issue_host_envelope(
            kind="RUNTIME_AUTHORITY_CAPABILITY",
            payload=payload,
        )
        record = self.store.bind_runtime_authority_capability_receipt(
            context,
            revision_set_id=invocation.revision_set_id,
            operation_invocation_id=invocation.invocation_id,
            environment_id=_text(
                authority.security_bindings.get("environmentId"),
                "authority environmentId",
            ),
            authority_snapshot_id=authority.authority_revision,
            capabilities=capabilities,
            delegation_allowed=delegation_allowed,
            authority_digest=authority.authority_digest,
            origin_skill_id=origin.skill_id,
            origin_skill_name=origin.skill_name,
            origin_owner_kernel=origin.owner_kernel,
            origin_execution_id=origin.execution_id,
            origin_step_id=origin.step_id,
            extension_skill=origin.extension_skill,
            origin_receipt_ref=origin.receipt_ref,
            origin_receipt_state=origin.receipt_state,
            origin_receipt_digest=origin.receipt_digest,
            origin_signing_key_id=origin.signing_key_id,
            origin_signature_algorithm=origin.signature_algorithm,
            origin_signature=origin.signature,
            host_envelope=host_envelope,
        )
        expected = (
            context.tenant_id,
            context.project_id,
            context.run_id,
            context.actor_id,
            context.execution_epoch,
            context.fencing_generation,
            context.authority_revision,
            invocation.revision_set_id,
            invocation.invocation_id,
            authority.security_bindings["environmentId"],
            authority.authority_revision,
            capabilities,
            delegation_allowed,
            authority.authority_digest,
            origin.skill_id,
            origin.skill_name,
            origin.owner_kernel,
            origin.execution_id,
            origin.step_id,
            origin.extension_skill,
            origin.receipt_ref,
            origin.receipt_state,
            origin.receipt_digest,
            origin.signing_key_id,
            origin.signature_algorithm,
            origin.signature,
            host_envelope,
        )
        observed = (
            record.tenant_id,
            record.project_id,
            record.run_id,
            record.actor_id,
            record.execution_epoch,
            record.fencing_generation,
            record.authority_revision,
            record.revision_set_id,
            record.operation_invocation_id,
            record.environment_id,
            record.authority_snapshot_id,
            record.capabilities,
            record.delegation_allowed,
            record.authority_digest,
            record.origin_skill_id,
            record.origin_skill_name,
            record.origin_owner_kernel,
            record.origin_execution_id,
            record.origin_step_id,
            record.extension_skill,
            record.origin_receipt_ref,
            record.origin_receipt_state,
            record.origin_receipt_digest,
            record.origin_signing_key_id,
            record.origin_signature_algorithm,
            record.origin_signature,
            record.host_envelope,
        )
        if observed != expected:
            raise IntegrityError(
                "durable capability authority receipt diverged from Host authority",
                code="CAPABILITY_AUTHORITY_RECEIPT_DRIFT",
            )
        return record

    def _bind_subagent_reservation(
        self,
        context: SecurityContext,
        authority: RuntimeAssuranceAuthority,
        invocation: DeltaInvocation,
        reservation_id: str,
        *,
        authority_receipt: RuntimeAuthorityCapabilityReceiptRecord | None = None,
    ) -> SubagentBudgetReservationBindingRecord:
        """Persist the complete Host reservation before consuming a child spec."""

        if authority_receipt is None:
            authority_receipt = self._bind_capability_authority(
                context,
                authority,
                invocation,
            )
        reservation = authority.subagent_reservation(reservation_id)
        child_authority = tuple(sorted(reservation.child_authority))
        child_tools = tuple(sorted(reservation.child_tools))
        payload = {
            "tenantId": context.tenant_id,
            "projectId": context.project_id,
            "runId": context.run_id,
            "actorId": context.actor_id,
            "executionEpoch": context.execution_epoch,
            "fencingGeneration": context.fencing_generation,
            "authorityRevision": context.authority_revision,
            "revisionSetId": invocation.revision_set_id,
            "reservationId": reservation.reservation_id,
            "operationInvocationId": invocation.invocation_id,
            "parentExecutionId": reservation.parent_execution_id,
            "environmentId": reservation.environment_id,
            "authoritySnapshotId": reservation.authority_snapshot_id,
            "provider": reservation.provider,
            "model": reservation.model,
            "reasoningEffort": reservation.reasoning_effort,
            "childAuthority": list(child_authority),
            "childTools": list(child_tools),
            "maxOutputTokens": reservation.max_output_tokens,
            "maxCostBudget": reservation.max_cost_budget,
            "wallClockDeadline": reservation.wall_clock_deadline.astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "toolPlanHash": reservation.tool_plan_hash,
            "authorityEnvelopeDigest": authority_receipt.host_envelope.envelope_digest,
        }
        host_envelope = self._issue_host_envelope(
            kind="SUBAGENT_BUDGET_RESERVATION",
            payload=payload,
        )
        record = self.store.bind_subagent_budget_reservation(
            context,
            revision_set_id=invocation.revision_set_id,
            reservation_id=reservation.reservation_id,
            operation_invocation_id=invocation.invocation_id,
            parent_execution_id=reservation.parent_execution_id,
            environment_id=reservation.environment_id,
            authority_snapshot_id=reservation.authority_snapshot_id,
            provider=reservation.provider,
            model=reservation.model,
            reasoning_effort=reservation.reasoning_effort,
            child_authority=child_authority,
            child_tools=child_tools,
            max_output_tokens=reservation.max_output_tokens,
            max_cost_budget=reservation.max_cost_budget,
            wall_clock_deadline=reservation.wall_clock_deadline,
            tool_plan_hash=reservation.tool_plan_hash,
            authority_envelope_digest=(authority_receipt.host_envelope.envelope_digest),
            host_envelope=host_envelope,
        )
        expected = (
            context.tenant_id,
            context.project_id,
            context.run_id,
            context.actor_id,
            context.execution_epoch,
            context.fencing_generation,
            context.authority_revision,
            invocation.revision_set_id,
            reservation.reservation_id,
            invocation.invocation_id,
            reservation.parent_execution_id,
            reservation.environment_id,
            reservation.authority_snapshot_id,
            reservation.provider,
            reservation.model,
            reservation.reasoning_effort,
            child_authority,
            child_tools,
            reservation.max_output_tokens,
            reservation.max_cost_budget,
            reservation.wall_clock_deadline,
            reservation.tool_plan_hash,
            authority_receipt.host_envelope.envelope_digest,
            host_envelope,
            SubagentBudgetReservationState.RESERVED,
        )
        observed = (
            record.tenant_id,
            record.project_id,
            record.run_id,
            record.actor_id,
            record.execution_epoch,
            record.fencing_generation,
            record.authority_revision,
            record.revision_set_id,
            record.reservation_id,
            record.operation_invocation_id,
            record.parent_execution_id,
            record.environment_id,
            record.authority_snapshot_id,
            record.provider,
            record.model,
            record.reasoning_effort,
            record.child_authority,
            record.child_tools,
            record.max_output_tokens,
            record.max_cost_budget,
            record.wall_clock_deadline,
            record.tool_plan_hash,
            record.authority_envelope_digest,
            record.host_envelope,
            record.state,
        )
        if observed != expected:
            raise IntegrityError(
                "durable subagent reservation diverged from Host authority",
                code="SUBAGENT_BUDGET_RESERVATION_DRIFT",
            )
        return record

    def prepare_operation_authority(
        self,
        context: SecurityContext,
        authority: RuntimeAssuranceAuthority,
        invocation: DeltaInvocation,
    ) -> None:
        """Persist Host authority before any handler can succeed or deny."""

        if invocation.extension_skill == "elmos-invocation-scoped-capability-lease":
            self._bind_capability_authority(context, authority, invocation)
        elif invocation.extension_skill == "elmos-subagent-model-execution-spec":
            authority_receipt = self._bind_capability_authority(
                context,
                authority,
                invocation,
            )
            raw_reservation_id = invocation.payload.get("budgetReservationId")
            if (
                not isinstance(raw_reservation_id, str)
                or not raw_reservation_id.strip()
            ):
                return
            try:
                reservation_id = _text(raw_reservation_id, "budgetReservationId")
                authority.subagent_reservation(reservation_id)
            except (ContractError, ValidationError):
                return
            self._bind_subagent_reservation(
                context,
                authority,
                invocation,
                reservation_id,
                authority_receipt=authority_receipt,
            )

    def begin_tool_result(
        self,
        context: SecurityContext,
        authority: RuntimeAssuranceAuthority,
        invocation: DeltaInvocation,
        identity: CallIdentity,
        attempt: int,
        raw_result_ref: str,
    ) -> ToolResultCommitRecord:
        """Persist RAW_CAPTURED and INTERCEPTING before any callback executes."""

        if not isinstance(identity, CallIdentity):
            raise TypeError("typed tool call identity is required")
        call_id = identity.call_id
        plan_hash = identity.execution_plan_hash
        environment_id = identity.environment_id
        authority_snapshot_id = identity.authority_snapshot_id
        invocation_id = identity.invocation_id
        checked_attempt = _positive(attempt, "attempt")
        binding = authority.pending_call_binding(call_id)
        expected_binding = (
            invocation.invocation_id,
            plan_hash,
            environment_id,
            authority_snapshot_id,
        )
        observed_binding = (
            getattr(binding, "invocation_id", None),
            getattr(binding, "execution_plan_hash", None),
            getattr(binding, "environment_id", None),
            getattr(binding, "authority_snapshot_id", None),
        )
        if (
            invocation_id != invocation.invocation_id
            or observed_binding != expected_binding
        ):
            raise IntegrityError(
                "tool-result begin binding diverged from Host authority",
                code="TOOL_RESULT_BEGIN_BINDING_DRIFT",
            )
        if binding.attempt != checked_attempt:
            raise IntegrityError(
                "tool-result attempt diverged from Host authority",
                code="TOOL_RESULT_BEGIN_BINDING_DRIFT",
            )
        durable_binding = self.store.bind_pending_tool_call(
            context,
            revision_set_id=invocation.revision_set_id,
            invocation_id=invocation.invocation_id,
            call_id=call_id,
            attempt=checked_attempt,
            execution_plan_hash=plan_hash,
            environment_id=environment_id,
            tool_id=_text(binding.tool_id, "tool_id"),
            authority_snapshot_id=authority_snapshot_id,
        )
        if durable_binding.state is not PendingToolCallBindingState.PENDING:
            raise ConflictError(
                "tool call was already durably reconciled",
                code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
            )
        captured = self.store.begin_tool_result(
            context,
            revision_set_id=invocation.revision_set_id,
            invocation_id=invocation.invocation_id,
            call_id=call_id,
            attempt=checked_attempt,
            execution_plan_hash=plan_hash,
            environment_id=environment_id,
            authority_snapshot_id=authority_snapshot_id,
            raw_result_ref=_text(raw_result_ref, "raw_result_ref"),
        )
        if captured.state is ToolResultCommitState.INTERCEPTING:
            raise ConflictError(
                "tool result is already intercepting and requires explicit recovery",
                code="TOOL_RESULT_RECOVERY_REQUIRED",
            )
        if captured.state is not ToolResultCommitState.RAW_CAPTURED:
            raise ConflictError(
                "tool result cannot restart from a terminal durable state",
                code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
            )
        intercepting = self.store.mark_tool_result_intercepting(
            context,
            revision_set_id=invocation.revision_set_id,
            invocation_id=invocation.invocation_id,
            call_id=call_id,
            attempt=checked_attempt,
            execution_epoch=invocation.execution_epoch,
            expected_state=ToolResultCommitState.RAW_CAPTURED,
        )
        if intercepting.state is not ToolResultCommitState.INTERCEPTING:
            raise IntegrityError(
                "tool result did not durably enter INTERCEPTING",
                code="TOOL_RESULT_BEGIN_STATE_DRIFT",
            )
        return intercepting

    @staticmethod
    def _event_identity(
        value: Mapping[str, Any],
    ) -> tuple[str, str, int, str, str | None]:
        return (
            _text(value.get("eventId"), "eventId"),
            _text(value.get("type"), "type"),
            _positive(value.get("schemaVersion"), "schemaVersion"),
            _text(value.get("correlationId"), "correlationId"),
            (
                _text(value.get("causationId"), "causationId")
                if value.get("causationId") is not None
                else None
            ),
        )

    def _event_payload_ref(
        self,
        context: SecurityContext,
        event: Mapping[str, Any],
        *,
        operation: str,
    ) -> tuple[str, str]:
        event_id, event_type, schema_version, correlation_id, causation_id = (
            self._event_identity(event)
        )
        payload = _mapping(event.get("payload"), "event payload")
        payload_digest = digest_object(payload, domain="delta-durable-event-payload")
        payload_ref = self.evidence.put(
            context,
            {
                "kind": "DURABLE_EVENT_PAYLOAD",
                "operation": _text(operation, "event operation"),
                "eventId": event_id,
                "type": event_type,
                "schemaVersion": schema_version,
                "correlationId": correlation_id,
                "causationId": causation_id,
                "payloadDigest": payload_digest,
                "content": dict(payload),
            },
        )
        return payload_ref, payload_digest

    def _verify_persisted_event(
        self,
        context: SecurityContext,
        record: DurableEventInstanceRecord,
        event: Mapping[str, Any],
    ) -> None:
        event_id, event_type, schema_version, correlation_id, causation_id = (
            self._event_identity(event)
        )
        if (
            record.event_id != event_id
            or record.event_type != event_type
            or record.schema_version != schema_version
            or record.correlation_id != correlation_id
            or record.causation_id != causation_id
        ):
            raise IntegrityError(
                "durable event input diverged from its persisted identity",
                code="DURABLE_EVENT_INPUT_DRIFT",
            )
        evidence_record = self.evidence.get(context, record.payload_ref)
        if evidence_record.get("kind") != "DURABLE_EVENT_PAYLOAD":
            raise IntegrityError(
                "durable event payload evidence has an invalid kind",
                code="DURABLE_EVENT_INPUT_DRIFT",
            )
        evidence_identity = (
            evidence_record.get("eventId"),
            evidence_record.get("type"),
            evidence_record.get("schemaVersion"),
            evidence_record.get("correlationId"),
            evidence_record.get("causationId"),
            evidence_record.get("payloadDigest"),
        )
        persisted_identity = (
            record.event_id,
            record.event_type,
            record.schema_version,
            record.correlation_id,
            record.causation_id,
            record.payload_digest,
        )
        if evidence_identity != persisted_identity:
            raise IntegrityError(
                "durable event evidence metadata diverged from its persisted identity",
                code="DURABLE_EVENT_INPUT_DRIFT",
            )
        content = _mapping(evidence_record.get("content"), "durable event payload")
        supplied = _mapping(event.get("payload"), "event payload")
        observed_digest = digest_object(content, domain="delta-durable-event-payload")
        supplied_digest = digest_object(supplied, domain="delta-durable-event-payload")
        if (
            not hmac.compare_digest(observed_digest, record.payload_digest)
            or not hmac.compare_digest(supplied_digest, record.payload_digest)
            or dict(content) != dict(supplied)
        ):
            raise IntegrityError(
                "durable event payload diverged from content-addressed evidence",
                code="DURABLE_EVENT_INPUT_DRIFT",
            )

    @staticmethod
    def _find_event(
        events: Iterable[DurableEventInstanceRecord],
        event_id: str,
    ) -> DurableEventInstanceRecord:
        candidates = tuple(item for item in events if item.event_id == event_id)
        if len(candidates) != 1:
            raise ConflictError(
                "durable event identity is not uniquely available",
                code="DURABLE_EVENT_STATE_CONFLICT",
            )
        return candidates[0]

    @staticmethod
    def _derived_event_id(operation_id: str, source_event_id: str, kind: str) -> str:
        digest = digest_object(
            {
                "operationId": _text(operation_id, "event operation id"),
                "sourceEventId": _text(source_event_id, "source event id"),
                "kind": _text(kind, "event operation kind"),
            },
            domain="delta-durable-event-derived-identity",
        )
        return f"{kind.lower()}-{digest.removeprefix('sha256:')[:48]}"

    def _typed_ingress_wire(
        self,
        context: SecurityContext,
        record: TypedIngressRecord,
    ) -> Mapping[str, Any]:
        evidence_record = self.evidence.get(context, record.payload_ref)
        if evidence_record.get("kind") != "TYPED_INGRESS":
            raise IntegrityError(
                "typed ingress evidence has an invalid kind",
                code="TYPED_INGRESS_EVIDENCE_DRIFT",
            )
        ingress = _mapping(evidence_record.get("content"), "typed ingress content")
        deduplication_key = ingress.get("deduplicationKey") or ingress.get("eventId")
        if (
            ingress.get("ingressId") != record.ingress_id
            or ingress.get("producerExecutionId") != record.producer_execution_id
            or ingress.get("kind") != record.kind.value
            or ingress.get("correlationId") != record.correlation_id
            or ingress.get("causationId") != record.causation_id
            or ingress.get("originatingCallId") != record.originating_call_id
            or deduplication_key != record.deduplication_key
            or not hmac.compare_digest(
                digest_object(ingress, domain="delta-typed-ingress"),
                record.envelope_digest,
            )
        ):
            raise IntegrityError(
                "typed ingress evidence diverged from the durable record",
                code="TYPED_INGRESS_EVIDENCE_DRIFT",
            )
        return MappingProxyType(dict(ingress))

    def __call__(
        self,
        context: SecurityContext,
        authority: RuntimeAssuranceAuthority,
        descriptor: DeltaSkillDescriptor,
        invocation: DeltaInvocation,
        output: Any,
    ) -> Any:
        if descriptor.name not in DELTA_SKILL_REGISTRY:
            raise ContractError("durable commit descriptor is not allowlisted")
        if descriptor.name not in self._STATEFUL:
            return output
        value = _mapping(output, "delta handler output")
        payload = invocation.payload
        revision = invocation.revision_set_id

        if descriptor.name == "elmos-tool-result-interception-commit":
            action = str(payload.get("action", "commit"))
            identity = _mapping(value.get("callIdentity"), "callIdentity")
            attempt = _positive(payload.get("attempt"), "attempt")
            call_id = _text(identity.get("callId"), "callId")
            subject_invocation_id = _text(
                identity.get("invocationId"), "callIdentity.invocationId"
            )
            execution_plan_hash = _text(
                identity.get("executionPlanHash"), "executionPlanHash"
            )
            environment_id = _text(identity.get("environmentId"), "environmentId")
            authority_snapshot_id = _text(
                identity.get("authoritySnapshotId"),
                "authoritySnapshotId",
            )
            if action == "commit":
                chain_value = value.get("interceptorChain")
                if not isinstance(chain_value, list):
                    raise ValidationError("interceptorChain must be an array")
                chain = tuple(
                    InterceptorCommitRecord(
                        _text(item.get("interceptorId"), "interceptorId"),
                        _text(item.get("version"), "version"),
                        _text(item.get("decisionHash"), "decisionHash"),
                    )
                    for item in (
                        _mapping(entry, "interceptorChain item")
                        for entry in chain_value
                    )
                )
                raw_result_ref = _text(value.get("rawResultRef"), "rawResultRef")
                effective_result_ref = _text(
                    value.get("effectiveResultRef"), "effectiveResultRef"
                )
                mutation_provenance_ref = _text(
                    value.get("mutationProvenanceRef"),
                    "mutationProvenanceRef",
                )
                if value.get("commitState") == ToolResultCommitState.ABORTED.value:
                    self.store.abort_tool_result(
                        context,
                        revision_set_id=revision,
                        subject_invocation_id=subject_invocation_id,
                        operation_invocation_id=invocation.invocation_id,
                        call_id=call_id,
                        attempt=attempt,
                        execution_plan_hash=execution_plan_hash,
                        environment_id=environment_id,
                        authority_snapshot_id=authority_snapshot_id,
                        raw_result_ref=raw_result_ref,
                        effective_result_ref=effective_result_ref,
                        interceptor_chain=chain,
                        mutation_provenance_ref=mutation_provenance_ref,
                        failure_kind=ToolResultFailureKind(
                            _text(value.get("failureKind"), "failureKind")
                        ),
                        failure_reason=_text(
                            value.get("failureReason"), "failureReason"
                        ),
                    )
                else:
                    self.store.commit_tool_result(
                        context,
                        revision_set_id=revision,
                        invocation_id=subject_invocation_id,
                        call_id=call_id,
                        attempt=attempt,
                        execution_plan_hash=execution_plan_hash,
                        environment_id=environment_id,
                        authority_snapshot_id=authority_snapshot_id,
                        raw_result_ref=raw_result_ref,
                        effective_result_ref=effective_result_ref,
                        interceptor_chain=chain,
                        mutation_provenance_ref=mutation_provenance_ref,
                    )
            elif action in {"publish", "abort"}:
                expected_key = _tool_result_commit_key(
                    subject_invocation_id,
                    call_id,
                    attempt,
                    invocation.execution_epoch,
                )
                if not hmac.compare_digest(
                    _text(payload.get("commitKey"), "commitKey"), expected_key
                ):
                    raise IntegrityError(
                        "durable tool-result lifecycle identity diverged",
                        code="TOOL_RESULT_LIFECYCLE_BINDING_DRIFT",
                    )
                target = (
                    ToolResultCommitState.PUBLISHED
                    if action == "publish"
                    else ToolResultCommitState.ABORTED
                )
                self.store.transition_tool_result(
                    context,
                    revision_set_id=revision,
                    subject_invocation_id=subject_invocation_id,
                    operation_invocation_id=invocation.invocation_id,
                    call_id=call_id,
                    attempt=attempt,
                    execution_epoch=invocation.execution_epoch,
                    expected_execution_plan_hash=execution_plan_hash,
                    expected_environment_id=environment_id,
                    expected_authority_snapshot_id=authority_snapshot_id,
                    expected_state=ToolResultCommitState.COMMITTED,
                    target_state=target,
                    failure_kind=(
                        ToolResultFailureKind(
                            _text(value.get("failureKind"), "failureKind")
                        )
                        if target is ToolResultCommitState.ABORTED
                        else None
                    ),
                    failure_reason=(
                        _text(value.get("failureReason"), "failureReason")
                        if target is ToolResultCommitState.ABORTED
                        else None
                    ),
                )
            else:
                raise ValidationError("unsupported durable tool-result action")
            return output

        if descriptor.name == "elmos-step-finalized-execution-plan":
            plan_id = _text(value.get("planId"), "planId")
            record = self.store.record_step_plan(
                context,
                revision_set_id=revision,
                plan_id=plan_id,
                step_id=invocation.step_id,
                plan_hash=_text(value.get("planHash"), "planHash"),
                model_snapshot=_mapping(value.get("modelSnapshot"), "modelSnapshot"),
                tool_plan=_mapping(value.get("toolPlan"), "toolPlan"),
                tool_contracts=_mapping(value.get("toolContracts"), "toolContracts"),
                handler_digests={
                    _text(key, "handler digest tool"): _text(digest, "handler digest")
                    for key, digest in _mapping(
                        value.get("handlerDigests"), "handlerDigests"
                    ).items()
                },
                capabilities=tuple(value.get("capabilities", ())),
                environment_snapshot_id=_text(
                    value.get("environmentSnapshotId"), "environmentSnapshotId"
                ),
                authority_snapshot_id=_text(
                    value.get("authoritySnapshotId"), "authoritySnapshotId"
                ),
                tool_mode=_text(value.get("toolMode"), "toolMode"),
            )
            if record.state is StepPlanState.RETIRED:
                raise ConflictError("retired execution plan cannot be reactivated")
            if record.state is StepPlanState.CANDIDATE:
                record = self.store.transition_step_plan(
                    context,
                    revision_set_id=revision,
                    plan_id=plan_id,
                    expected_state=StepPlanState.CANDIDATE,
                    target_state=StepPlanState.FINALIZED,
                )
            if record.state is StepPlanState.FINALIZED:
                record = self.store.activate_step_plan(
                    context,
                    revision_set_id=revision,
                    plan_id=plan_id,
                    expected_state=StepPlanState.FINALIZED,
                )
            if record.state is not StepPlanState.ACTIVE:
                raise IntegrityError("durable execution plan did not become active")
            return output

        if descriptor.name == "elmos-invocation-scoped-capability-lease":
            action = str(payload.get("action", "issue"))
            lease_id = _text(value.get("leaseId"), "leaseId")
            subject_invocation_id = _text(
                value.get("invocationId"), "capability lease invocationId"
            )
            if action == "issue":
                if subject_invocation_id != invocation.invocation_id:
                    raise IntegrityError(
                        "issued capability lease escaped its request invocation",
                        code="CAPABILITY_LEASE_BINDING_DRIFT",
                    )
                self.store.issue_capability_lease(
                    context,
                    revision_set_id=revision,
                    lease_id=lease_id,
                    invocation_id=invocation.invocation_id,
                    environment_id=_text(value.get("environmentId"), "environmentId"),
                    authority_snapshot_id=_text(
                        value.get("authoritySnapshotId"), "authoritySnapshotId"
                    ),
                    capabilities=tuple(value.get("capabilities", ())),
                    expires_at=_timestamp(value.get("expiresAt"), "expiresAt"),
                    delegation_allowed=value.get("delegationAllowed") is True,
                    now=_timestamp(value.get("issuedAt"), "issuedAt"),
                )
            elif action == "revoke":
                self.store.revoke_capability_lease(
                    context,
                    revision_set_id=revision,
                    lease_id=lease_id,
                    subject_invocation_id=subject_invocation_id,
                    operation_invocation_id=invocation.invocation_id,
                    expected_environment_id=authority.security_bindings[
                        "environmentId"
                    ],
                    expected_authority_snapshot_id=context.authority_revision,
                    authorized_capabilities=tuple(sorted(authority.capabilities)),
                    reason=CapabilityRevocationReason(
                        _text(value.get("revocationReason"), "revocationReason")
                    ),
                )
            elif action == "use":
                if (
                    _text(value.get("environmentId"), "environmentId")
                    != authority.security_bindings["environmentId"]
                    or _text(value.get("authoritySnapshotId"), "authoritySnapshotId")
                    != context.authority_revision
                ):
                    raise IntegrityError(
                        "capability lease use escaped the current Host authority",
                        code="CAPABILITY_LEASE_BINDING_DRIFT",
                    )
                self.store.record_capability_lease_use(
                    context,
                    revision_set_id=revision,
                    lease_id=lease_id,
                    invocation_id=subject_invocation_id,
                    operation_invocation_id=invocation.invocation_id,
                    expected_environment_id=authority.security_bindings[
                        "environmentId"
                    ],
                    expected_authority_snapshot_id=context.authority_revision,
                    authorized_capabilities=tuple(sorted(authority.capabilities)),
                    capability=_text(payload.get("capability"), "capability"),
                )
            else:
                raise ValidationError("unsupported durable capability-lease action")
            return output

        if descriptor.name == "elmos-environment-attachment-authority":
            action = _text(value.get("action"), "action")
            server_id = _text(value.get("serverId"), "serverId")
            environment_id = _text(value.get("environmentId"), "environmentId")
            snapshot_id = _text(value.get("snapshotId"), "snapshotId")
            generation = _positive(value.get("generation"), "generation")
            calculated = _mapping(value.get("authority"), "authority")
            turn_environment = _mapping(value.get("turnEnvironment"), "turnEnvironment")
            if (
                _text(turn_environment.get("serverId"), "turnEnvironment.serverId")
                != server_id
                or _text(
                    turn_environment.get("environmentId"),
                    "turnEnvironment.environmentId",
                )
                != environment_id
            ):
                raise IntegrityError("environment attachment output scope diverged")
            settings_authority = _mapping(
                turn_environment.get("settingsAuthority"),
                "turnEnvironment.settingsAuthority",
            )
            settings_digest = _text(value.get("settingsDigest"), "settingsDigest")
            if (
                _text(
                    turn_environment.get("settingsDigest"),
                    "turnEnvironment.settingsDigest",
                )
                != settings_digest
            ):
                raise IntegrityError("environment settings digest diverged")
            permissions = tuple(calculated.get("permissions", ()))
            if action == "attach":
                attachment = self.store.record_environment_attachment(
                    context,
                    revision_set_id=revision,
                    server_id=server_id,
                    environment_id=environment_id,
                    snapshot_id=snapshot_id,
                    owner_authority_ref=authority.owner_authority.snapshot_id,
                    parent_authority_ref=authority.parent_authority_snapshot.snapshot_id,
                    effective_permissions=permissions,
                    settings_authority=settings_authority,
                    settings_digest=settings_digest,
                )
            elif action == "refresh":
                previous_snapshot_id = _text(
                    value.get("previousSnapshotId"), "previousSnapshotId"
                )
                attachment = self.store.refresh_environment_attachment(
                    context,
                    revision_set_id=revision,
                    server_id=server_id,
                    environment_id=environment_id,
                    expected_snapshot_id=previous_snapshot_id,
                    expected_generation=_positive(
                        payload.get("expectedGeneration"), "expectedGeneration"
                    ),
                    snapshot_id=snapshot_id,
                    owner_authority_ref=authority.owner_authority.snapshot_id,
                    parent_authority_ref=authority.parent_authority_snapshot.snapshot_id,
                    effective_permissions=permissions,
                    settings_authority=settings_authority,
                    settings_digest=settings_digest,
                )
            else:
                raise ValidationError("unsupported durable environment action")
            if (
                attachment.server_id != server_id
                or attachment.environment_id != environment_id
                or attachment.snapshot_id != snapshot_id
                or attachment.generation != generation
                or attachment.settings_digest != settings_digest
            ):
                raise IntegrityError("durable environment attachment diverged")
            return output

        if descriptor.name == "elmos-executor-generation-fencing":
            action = _text(payload.get("action"), "action")
            if action == "replace":
                replacement = _mapping(value.get("replacement"), "replacement")
                environment_id = _text(
                    replacement.get("environmentId"), "environmentId"
                )
                executor_identity = _text(
                    replacement.get("executorIdentity"), "executorIdentity"
                )
                generation = _positive(
                    replacement.get("executorGeneration"), "executorGeneration"
                )
                connection_epoch = _positive(
                    replacement.get("connectionEpoch"), "connectionEpoch"
                )
                executor_record = self.store.advance_executor_generation(
                    context,
                    revision_set_id=revision,
                    environment_id=environment_id,
                    executor_identity=executor_identity,
                    expected_generation=_positive(
                        payload.get("generation"), "generation"
                    ),
                    expected_connection_epoch=_positive(
                        payload.get("connectionEpoch"), "connectionEpoch"
                    ),
                    replace_identity=True,
                )
                if (
                    executor_record.executor_generation,
                    executor_record.connection_epoch,
                ) != (
                    generation,
                    connection_epoch,
                ):
                    raise IntegrityError("durable executor advancement diverged")
                raw_effects = value.get("reconciliationEffects")
                if not isinstance(raw_effects, (tuple, list)):
                    raise ValidationError("reconciliationEffects must be an array")
                declared_effects = tuple(
                    _mapping(item, "reconciliation effect") for item in raw_effects
                )
                if len(declared_effects) != 3:
                    raise IntegrityError("executor replacement effects are not exact")
                declared_kinds = {
                    _text(item.get("kind"), "effect kind") for item in declared_effects
                }
                required_kinds = {item.value for item in ExecutorReplacementEffectKind}
                if declared_kinds != required_kinds:
                    raise IntegrityError("executor replacement effects are not exact")

                snapshot = self.store.load_runtime_assurance_scope(
                    context, revision_set_id=revision
                )
                persisted_effects: list[dict[str, Any]] = []
                for item in declared_effects:
                    effect_id = _text(item.get("effectId"), "effectId")
                    kind = ExecutorReplacementEffectKind(
                        _text(item.get("kind"), "effect kind")
                    )
                    if (
                        item.get("state")
                        != ExecutorReplacementEffectState.PENDING.value
                    ):
                        raise IntegrityError(
                            "new executor replacement effect is not pending"
                        )
                    if kind is ExecutorReplacementEffectKind.CAPABILITY_REVOCATION:
                        effect_record = next(
                            (
                                candidate
                                for candidate in snapshot.executor_replacement_effects
                                if candidate.effect_id == effect_id
                            ),
                            None,
                        )
                        if (
                            effect_record is None
                            or effect_record.kind is not kind
                            or effect_record.state
                            is not ExecutorReplacementEffectState.SUCCEEDED
                        ):
                            raise IntegrityError(
                                "atomic executor capability revocation is missing"
                            )
                    else:
                        effect_record = self.store.record_executor_replacement_effect(
                            context,
                            revision_set_id=revision,
                            effect_id=effect_id,
                            environment_id=environment_id,
                            executor_generation=generation,
                            connection_epoch=connection_epoch,
                            kind=kind,
                        )
                    persisted_effects.append(
                        {
                            "effectId": effect_record.effect_id,
                            "kind": effect_record.kind.value,
                            "state": effect_record.state.value,
                            "evidenceRef": effect_record.evidence_ref,
                        }
                    )
                durable_output = dict(value)
                durable_output["reconciliationEffects"] = persisted_effects
                durable_output["activationAllowed"] = all(
                    item["state"] == ExecutorReplacementEffectState.SUCCEEDED.value
                    for item in persisted_effects
                )
                if durable_output["activationAllowed"]:
                    raise IntegrityError(
                        "replacement activated before workspace/external reconciliation"
                    )
                return durable_output

            environment_id = _text(value.get("environmentId"), "environmentId")
            executor_identity = _text(value.get("executorIdentity"), "executorIdentity")
            generation = _positive(
                value.get("executorGeneration"), "executorGeneration"
            )
            connection_epoch = _positive(
                value.get("connectionEpoch"), "connectionEpoch"
            )
            if action == "reconnect":
                executor_record = self.store.advance_executor_generation(
                    context,
                    revision_set_id=revision,
                    environment_id=environment_id,
                    executor_identity=executor_identity,
                    expected_generation=_positive(
                        payload.get("generation"), "generation"
                    ),
                    expected_connection_epoch=_positive(
                        payload.get("connectionEpoch"), "connectionEpoch"
                    ),
                    replace_identity=False,
                )
                if (
                    executor_record.executor_generation,
                    executor_record.connection_epoch,
                ) != (generation, connection_epoch):
                    raise IntegrityError("durable executor advancement diverged")
                return output

            snapshot = self.store.load_runtime_assurance_scope(
                context, revision_set_id=revision
            )
            current = next(
                (
                    item
                    for item in snapshot.executor_generations
                    if item.environment_id == environment_id
                    and item.executor_identity == executor_identity
                    and item.executor_generation == generation
                    and item.connection_epoch == connection_epoch
                ),
                None,
            )
            if current is None:
                current = self.store.record_executor_generation(
                    context,
                    revision_set_id=revision,
                    environment_id=environment_id,
                    executor_identity=executor_identity,
                    executor_generation=generation,
                    connection_epoch=connection_epoch,
                )
            if action == "accept":
                if current.state is not ExecutorGenerationState.ACTIVE:
                    raise ConflictError("durable executor is not active")
                return output
            executor_target = {
                "activate": ExecutorGenerationState.ACTIVE,
                "retire": ExecutorGenerationState.RETIRED,
                "fail": ExecutorGenerationState.FAILED,
            }.get(action)
            if executor_target is None:
                raise ValidationError("unsupported durable executor action")
            if current.state is executor_target:
                if executor_target is ExecutorGenerationState.ACTIVE:
                    replay_probe = _text(
                        value.get("liveProbeEvidenceRef"),
                        "liveProbeEvidenceRef",
                    )
                    if current.live_probe_evidence_ref != replay_probe:
                        raise ConflictError(
                            "executor activation replay changed live probe evidence"
                        )
                return output
            self.store.transition_executor_generation(
                context,
                revision_set_id=revision,
                environment_id=environment_id,
                executor_generation=generation,
                connection_epoch=connection_epoch,
                expected_state=current.state,
                target_state=executor_target,
                live_probe_evidence_ref=(
                    _text(value.get("liveProbeEvidenceRef"), "liveProbeEvidenceRef")
                    if executor_target is ExecutorGenerationState.ACTIVE
                    else None
                ),
            )
            return output

        if descriptor.name == "elmos-workspace-ownership-lease":
            action = _text(payload.get("action"), "action")
            workspace_id = _text(value.get("workspaceId"), "workspaceId")
            generation = _positive(value.get("generation"), "generation")
            if action == "bind":
                workspace = self.store.bind_workspace(
                    context,
                    revision_set_id=revision,
                    workspace_id=workspace_id,
                    owner_execution_id=_text(
                        value.get("ownerExecutionId"), "ownerExecutionId"
                    ),
                    generation=generation,
                    repository_id=_text(value.get("repositoryId"), "repositoryId"),
                    base_revision=_text(value.get("baseRevision"), "baseRevision"),
                    write_scopes=tuple(value.get("writeScopes", ())),
                )
            elif action == "handoff":
                workspace = self.store.request_workspace_handoff(
                    context,
                    revision_set_id=revision,
                    workspace_id=workspace_id,
                    expected_generation=generation,
                )
            elif action == "resume":
                snapshot = self.store.load_runtime_assurance_scope(
                    context,
                    revision_set_id=revision,
                )
                matches = tuple(
                    item
                    for item in snapshot.workspace_leases
                    if item.workspace_id == workspace_id
                    and item.generation == generation
                )
                if len(matches) != 1:
                    raise ConflictError(
                        "durable workspace generation is not uniquely available"
                    )
                workspace = matches[0]
                if workspace.state is not WorkspaceLeaseState.ACTIVE:
                    raise ConflictError("durable workspace is not active")
            elif action == "markTakeoverPending":
                workspace = self.store.mark_workspace_takeover_pending(
                    context,
                    revision_set_id=revision,
                    workspace_id=workspace_id,
                    expected_generation=generation,
                    crash_evidence_ref=_text(
                        value.get("crashEvidenceRef"), "crashEvidenceRef"
                    ),
                )
            elif action in {"takeover", "acceptHandoff"}:
                workspace = self.store.takeover_workspace(
                    context,
                    revision_set_id=revision,
                    workspace_id=workspace_id,
                    expected_generation=_positive(
                        payload.get("generation"), "generation"
                    ),
                    new_owner_execution_id=_text(
                        value.get("ownerExecutionId"), "ownerExecutionId"
                    ),
                    base_revision=_text(value.get("baseRevision"), "baseRevision"),
                    write_scopes=tuple(value.get("writeScopes", ())),
                )
            elif action == "retire":
                snapshot = self.store.load_runtime_assurance_scope(
                    context,
                    revision_set_id=revision,
                )
                workspace_current = next(
                    (
                        item
                        for item in snapshot.workspace_leases
                        if item.workspace_id == workspace_id
                        and item.generation == generation
                    ),
                    None,
                )
                if workspace_current is None:
                    raise ConflictError("durable workspace generation is unavailable")
                if workspace_current.state is WorkspaceLeaseState.RETIRED:
                    return output
                workspace = self.store.retire_workspace(
                    context,
                    revision_set_id=revision,
                    workspace_id=workspace_id,
                    expected_generation=generation,
                    expected_state=workspace_current.state,
                )
            else:
                raise ValidationError("unsupported durable workspace action")
            if (
                workspace.workspace_id != workspace_id
                or workspace.generation != generation
                or workspace.owner_execution_id
                != _text(value.get("ownerExecutionId"), "ownerExecutionId")
                or workspace.repository_id
                != _text(value.get("repositoryId"), "repositoryId")
                or workspace.base_revision
                != _text(value.get("baseRevision"), "baseRevision")
                or workspace.write_scopes != tuple(value.get("writeScopes", ()))
                or workspace.state.value != _text(value.get("state"), "state")
                or workspace.takeover_evidence_ref != value.get("crashEvidenceRef")
            ):
                raise IntegrityError("durable workspace lifecycle output diverged")
            return output

        if descriptor.name == "elmos-registered-durable-plugin-events":
            action = _text(payload.get("action"), "action")
            if action == "register":
                registration = _mapping(value.get("registration"), "registration")
                registration_hash = digest_object(
                    registration,
                    domain="delta-event-registration",
                )
                registration_record = self.store.register_durable_event(
                    context,
                    revision_set_id=revision,
                    event_type=_text(registration.get("type"), "type"),
                    owner=_text(registration.get("owner"), "owner"),
                    schema_version=_positive(
                        registration.get("schemaVersion"), "schemaVersion"
                    ),
                    semantics=DurableEventSemantics(
                        _text(registration.get("semantics"), "semantics")
                    ),
                    compatibility=EventCompatibility(
                        _text(registration.get("compatibility"), "compatibility")
                    ),
                    validator_ref=_text(registration.get("validator"), "validator"),
                    upgrader_ref=_text(registration.get("upgrader"), "upgrader"),
                    projections=tuple(registration.get("projections", ())),
                    registration_hash=registration_hash,
                )
                if not hmac.compare_digest(
                    registration_record.registration_hash, registration_hash
                ):
                    raise IntegrityError("durable event registration diverged")
                return output

            snapshot = self.store.load_runtime_assurance_scope(
                context,
                revision_set_id=revision,
            )
            if action == "append":
                event = _mapping(value.get("event"), "event")
                event_id, event_type, schema_version, correlation_id, causation_id = (
                    self._event_identity(event)
                )
                payload_ref, payload_digest = self._event_payload_ref(
                    context,
                    event,
                    operation="APPEND",
                )
                appended_record = self.store.append_durable_event(
                    context,
                    revision_set_id=revision,
                    event_id=event_id,
                    event_type=event_type,
                    schema_version=schema_version,
                    payload_ref=payload_ref,
                    payload_digest=payload_digest,
                    correlation_id=correlation_id,
                    causation_id=causation_id,
                )
                if appended_record.state is not DurableEventInstanceState.PENDING:
                    raise IntegrityError("appended durable event is not pending")
                return output

            if action == "replay":
                source_event = _mapping(payload.get("event"), "event")
                source_id, _event_type, source_version, _correlation, _causation = (
                    self._event_identity(source_event)
                )
                replayed_value = value.get("event")
                if replayed_value is None:
                    if value.get("state") != DurableEventInstanceState.SKIPPED.value:
                        raise IntegrityError(
                            "optional durable event skip state diverged"
                        )
                    skip_ref = self.evidence.put(
                        context,
                        {
                            "kind": "DURABLE_EVENT_OPTIONAL_SKIP",
                            "invocation": invocation.to_wire(),
                            "event": dict(source_event),
                            "decision": EventCompatibilityDecision.SKIPPED.value,
                        },
                    )
                    durable_output = dict(value)
                    durable_output["skipEvidenceRef"] = skip_ref
                    return durable_output

                replayed = _mapping(replayed_value, "replayed event")
                source = self._find_event(snapshot.durable_events, source_id)
                self._verify_persisted_event(context, source, source_event)
                target_version = _positive(
                    replayed.get("schemaVersion"), "schemaVersion"
                )
                if target_version < source_version:
                    raise IntegrityError("durable event replay attempted a downgrade")
                if target_version == source_version:
                    terminal = self.store.replay_durable_event(
                        context,
                        revision_set_id=revision,
                        event_id=source_id,
                        expected_state=DurableEventInstanceState.PENDING,
                        target_state=DurableEventInstanceState.PROCESSED,
                        compatibility_decision=EventCompatibilityDecision.EXACT,
                    )
                    if terminal.state is not DurableEventInstanceState.PROCESSED:
                        raise IntegrityError("durable event replay did not terminate")
                    return output

                target_id = self._derived_event_id(
                    invocation.invocation_id,
                    source_id,
                    "MIGRATION",
                )
                target_event = dict(replayed)
                target_event["eventId"] = target_id
                target_event["causationId"] = source_id
                payload_ref, payload_digest = self._event_payload_ref(
                    context,
                    target_event,
                    operation="REPLAY_UPGRADE",
                )
                migrated = self.store.migrate_durable_event(
                    context,
                    revision_set_id=revision,
                    source_event_id=source_id,
                    event_id=target_id,
                    target_schema_version=target_version,
                    payload_ref=payload_ref,
                    payload_digest=payload_digest,
                )
                if (
                    migrated.parent_event_id != source_id
                    or migrated.state is not DurableEventInstanceState.PENDING
                ):
                    raise IntegrityError("durable event upgrade result diverged")
                durable_output = dict(value)
                durable_output["event"] = target_event
                return durable_output

            if action == "preflightOwnerChange":
                event_type = _text(payload.get("eventType"), "eventType")
                registrations = tuple(
                    item
                    for item in snapshot.event_registrations
                    if item.event_type == event_type
                )
                owners = {item.owner for item in registrations}
                if len(owners) != 1:
                    raise ConflictError(
                        "durable event owner is not uniquely registered",
                        code="EVENT_REGISTRATION_CONFLICT",
                    )
                operation = EventOwnerChangeAction(
                    _text(payload.get("operation"), "operation")
                )
                owner_target_version = (
                    _positive(payload.get("targetVersion"), "targetVersion")
                    if operation is EventOwnerChangeAction.DOWNGRADE
                    else None
                )
                preflight = self.store.preflight_event_owner_change(
                    context,
                    revision_set_id=revision,
                    action=operation,
                    owner=next(iter(owners)),
                    target_version=owner_target_version,
                )
                handler_preflight = _mapping(value.get("preflight"), "preflight")
                if (
                    not preflight.allowed
                    or handler_preflight.get("decision") != "ALLOW"
                    or handler_preflight.get("type") != event_type
                ):
                    raise ConflictError(
                        "authoritative durable event owner-change preflight blocked",
                        code="DURABLE_EVENT_OWNER_CHANGE_BLOCKED",
                        details={"blockers": preflight.blockers},
                    )
                durable_output = dict(value)
                durable_output["durablePreflight"] = {
                    "operation": preflight.action.value,
                    "owner": preflight.owner,
                    "targetVersion": preflight.target_version,
                    "allowed": preflight.allowed,
                    "blockers": list(preflight.blockers),
                }
                return durable_output

            raw_inputs = payload.get("events")
            raw_outputs = value.get("events")
            if not isinstance(raw_inputs, (tuple, list)) or not isinstance(
                raw_outputs, (tuple, list)
            ):
                raise ValidationError("durable causal replay requires event arrays")
            inputs = {
                _text(item.get("eventId"), "eventId"): item
                for item in (
                    _mapping(candidate, "input event") for candidate in raw_inputs
                )
            }
            if len(inputs) != len(raw_inputs):
                raise IntegrityError("durable causal replay input IDs are not unique")
            transformed: list[dict[str, Any]] = []
            emitted: set[str] = set()
            for raw_event in raw_outputs:
                replayed = _mapping(raw_event, "replayed event")
                source_id = _text(replayed.get("eventId"), "eventId")
                if source_id in emitted or source_id not in inputs:
                    raise IntegrityError(
                        "durable causal replay output identity diverged"
                    )
                emitted.add(source_id)
                source_event = inputs[source_id]
                source = self._find_event(snapshot.durable_events, source_id)
                self._verify_persisted_event(context, source, source_event)
                if action == "forkReplay":
                    operation_id = _text(value.get("forkId"), "forkId")
                    target_id = self._derived_event_id(operation_id, source_id, "FORK")
                    target_event = dict(replayed)
                    target_event["eventId"] = target_id
                    target_event["causationId"] = source_id
                    payload_ref, payload_digest = self._event_payload_ref(
                        context,
                        target_event,
                        operation="FORK_REPLAY",
                    )
                    derived_record = self.store.fork_durable_event_lineage(
                        context,
                        revision_set_id=revision,
                        parent_event_id=source_id,
                        event_id=target_id,
                        payload_ref=payload_ref,
                        payload_digest=payload_digest,
                    )
                elif action == "migrationReplay":
                    operation_id = _text(value.get("migrationId"), "migrationId")
                    target_version = _positive(
                        replayed.get("schemaVersion"), "schemaVersion"
                    )
                    if target_version < source.schema_version:
                        raise IntegrityError("migration replay attempted a downgrade")
                    if target_version == source.schema_version:
                        exact_record = self.store.replay_durable_event(
                            context,
                            revision_set_id=revision,
                            event_id=source_id,
                            expected_state=DurableEventInstanceState.PENDING,
                            target_state=DurableEventInstanceState.PROCESSED,
                            compatibility_decision=EventCompatibilityDecision.EXACT,
                        )
                        if (
                            exact_record.state
                            is not DurableEventInstanceState.PROCESSED
                        ):
                            raise IntegrityError(
                                "migration replay did not process the exact event"
                            )
                        transformed.append(dict(replayed))
                        continue
                    target_id = self._derived_event_id(
                        operation_id,
                        source_id,
                        "MIGRATION",
                    )
                    target_event = dict(replayed)
                    target_event["eventId"] = target_id
                    target_event["causationId"] = source_id
                    payload_ref, payload_digest = self._event_payload_ref(
                        context,
                        target_event,
                        operation="MIGRATION_REPLAY",
                    )
                    derived_record = self.store.migrate_durable_event(
                        context,
                        revision_set_id=revision,
                        source_event_id=source_id,
                        event_id=target_id,
                        target_schema_version=target_version,
                        payload_ref=payload_ref,
                        payload_digest=payload_digest,
                    )
                else:
                    raise ValidationError("unsupported durable event action")
                if derived_record.state is not DurableEventInstanceState.PENDING:
                    raise IntegrityError("derived durable event is not pending")
                transformed.append(target_event)

            skipped = sorted(set(inputs) - emitted)
            skip_refs = [
                self.evidence.put(
                    context,
                    {
                        "kind": "DURABLE_EVENT_OPTIONAL_SKIP",
                        "invocation": invocation.to_wire(),
                        "event": dict(inputs[event_id]),
                        "decision": EventCompatibilityDecision.SKIPPED.value,
                    },
                )
                for event_id in skipped
            ]
            durable_output = dict(value)
            durable_output["events"] = transformed
            durable_output["skippedEventIds"] = skipped
            durable_output["skipEvidenceRefs"] = skip_refs
            return durable_output

        if descriptor.name == "elmos-typed-external-ingress":
            action = _text(payload.get("action"), "action")
            if action == "page":
                cursor_value = _mapping(value.get("keysetCursor"), "keysetCursor")
                after_time = cursor_value.get("afterOccurredAt")
                after_id = cursor_value.get("afterIngressId")
                after = (
                    (
                        _timestamp(after_time, "afterOccurredAt"),
                        _text(after_id, "afterIngressId"),
                    )
                    if after_time is not None and after_id is not None
                    else None
                )
                page = self.store.page_typed_ingress(
                    context,
                    revision_set_id=revision,
                    correlation_id=_text(value.get("correlationId"), "correlationId"),
                    after=after,
                    limit=_positive(value.get("limit"), "limit"),
                )
                records = [
                    dict(self._typed_ingress_wire(context, record))
                    for record in page.records
                ]
                next_cursor = (
                    {
                        "afterOccurredAt": page.next_cursor[0]
                        .astimezone(UTC)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "afterIngressId": page.next_cursor[1],
                    }
                    if page.next_cursor is not None
                    else None
                )
                durable_output = dict(value)
                durable_output["records"] = records
                durable_output["nextCursor"] = next_cursor
                return durable_output
            if action != "ingest":
                raise ValidationError("unsupported durable typed ingress action")
            ingress = _mapping(value.get("ingress"), "ingress")
            payload_ref = self.evidence.put(
                context,
                {"kind": "TYPED_INGRESS", "content": dict(ingress)},
            )
            ingress_record, accepted = self.store.record_typed_ingress(
                context,
                revision_set_id=revision,
                ingress_id=_text(ingress.get("ingressId"), "ingressId"),
                producer_execution_id=_text(
                    ingress.get("producerExecutionId"), "producerExecutionId"
                ),
                deduplication_key=_text(
                    ingress.get("deduplicationKey") or ingress.get("eventId"),
                    "deduplicationKey",
                ),
                kind=TypedIngressKind(_text(ingress.get("kind"), "kind")),
                envelope_digest=digest_object(ingress, domain="delta-typed-ingress"),
                payload_ref=payload_ref,
                correlation_id=_text(ingress.get("correlationId"), "correlationId"),
                causation_id=ingress.get("causationId"),
                originating_call_id=ingress.get("originatingCallId"),
            )
            if ingress_record.ingress_id != ingress.get("ingressId"):
                raise IntegrityError("durable ingress identity diverged")
            output_accepted = value.get("accepted")
            if not isinstance(output_accepted, bool) or accepted is not output_accepted:
                raise IntegrityError("durable ingress deduplication result diverged")
            durable_output = dict(value)
            durable_output["accepted"] = accepted
            return durable_output

        if descriptor.name == "elmos-subagent-model-execution-spec":
            reservation_id = _text(
                value.get("budgetReservationId"), "budgetReservationId"
            )
            spec_hash = digest_object(
                value,
                domain="delta-subagent-execution-spec",
            )
            recorded = self.store.record_subagent_execution_spec(
                context,
                revision_set_id=revision,
                invocation_id=invocation.invocation_id,
                parent_execution_id=_text(
                    value.get("parentExecutionId"), "parentExecutionId"
                ),
                provider=_text(value.get("provider"), "provider"),
                model=_text(value.get("model"), "model"),
                reasoning_effort=_text(value.get("reasoningEffort"), "reasoningEffort"),
                authority_snapshot_id=_text(
                    value.get("authoritySnapshotId"), "authoritySnapshotId"
                ),
                environment_id=_text(value.get("environmentId"), "environmentId"),
                budget_reservation_id=_text(reservation_id, "budgetReservationId"),
                max_output_tokens=_positive(
                    value.get("maxOutputTokens"), "maxOutputTokens"
                ),
                tool_plan_hash=_text(value.get("toolPlanHash"), "toolPlanHash"),
                child_authority=tuple(value.get("childAuthority", ())),
                child_tools=tuple(value.get("childTools", ())),
                cost_budget=_text(value.get("costBudget"), "costBudget"),
                wall_clock_deadline=_timestamp(
                    value.get("wallClockDeadline"), "wallClockDeadline"
                ),
                spec_hash=spec_hash,
            )
            consumed = self.store.consume_subagent_execution_spec(
                context,
                revision_set_id=revision,
                invocation_id=invocation.invocation_id,
                budget_reservation_id=recorded.budget_reservation_id,
                consumer_execution_id=invocation.invocation_id,
            )
            if (
                consumed.state is not SubagentExecutionSpecState.CONSUMED
                or consumed.consumer_execution_id != invocation.invocation_id
                or not hmac.compare_digest(consumed.spec_hash, spec_hash)
            ):
                raise IntegrityError(
                    "durable subagent reservation consumption diverged"
                )
            durable_output = dict(value)
            durable_output["state"] = consumed.state.value
            durable_output["consumerExecutionId"] = consumed.consumer_execution_id
            return durable_output

        raise ContractError("stateful delta Skill lacks an exact durable binding")


class RuntimeAssuranceControlPlane:
    """Serialize durable restore/execute/commit for internal delta Skills."""

    def __init__(
        self,
        store: RuntimeAssuranceStore,
        evidence: EvidenceService,
        *,
        authority_provider: Callable[
            [SecurityContext, DeltaInvocation], RuntimeAssuranceAuthority
        ],
        durable_evidence: bool = True,
        permission_profiles: Mapping[tuple[str, str], Mapping[str, PermissionProfile]]
        | None = None,
        protocol_profiles: Mapping[tuple[str, str], ProtocolCapabilities] | None = None,
        authorized_producers: Mapping[tuple[str, str], Iterable[str]] | None = None,
        allowed_subagent_models: Iterable[tuple[str, str]] = (),
        trusted_skill_root: Path | None = None,
        skill_trust_policy: SkillTrustDomainPolicy | None = None,
        skill_signature_verifier: Callable[[bytes, str], bool] | None = None,
        host_security_signer: HostSecurityContextSigner | None = None,
        privileged_path_policy: PrivilegedPathPolicy | None = None,
        managed_worktree_registry: ManagedWorktreeRegistry | None = None,
        interceptors: Mapping[str, tuple[str, Callable[[ToolResult], ToolResult]]]
        | None = None,
        event_validators: Mapping[str, Callable[[Mapping[str, Any]], bool]]
        | None = None,
        event_upgraders: Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]]
        | None = None,
        optional_unknown_event_types: Iterable[str] = (),
        invocation_timeout_seconds: float = 30.0,
        authority_lookup_timeout_seconds: float = 5.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(store, RuntimeAssuranceStore):
            raise TypeError("store does not implement RuntimeAssuranceStore")
        if not callable(authority_provider):
            raise TypeError("a trusted authority provider is required")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        for value, field, maximum in (
            (invocation_timeout_seconds, "invocation_timeout_seconds", 300.0),
            (
                authority_lookup_timeout_seconds,
                "authority_lookup_timeout_seconds",
                60.0,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0.05 <= float(value) <= maximum
            ):
                raise ValueError(f"{field} is outside the safe range")
        if authority_lookup_timeout_seconds > invocation_timeout_seconds:
            raise ValueError(
                "authority lookup timeout cannot exceed the invocation timeout"
            )
        self.store = store
        self.authority_provider = authority_provider
        self.invocation_timeout_seconds = float(invocation_timeout_seconds)
        self.authority_lookup_timeout_seconds = float(authority_lookup_timeout_seconds)
        self._clock = clock or (lambda: datetime.now(UTC))
        self.evidence = EvidenceBackedDeltaStore(
            evidence,
            durable=durable_evidence,
        )
        self.committer = RuntimeAssuranceDurableCommitter(
            store,
            self.evidence,
            authority_provider,
        )
        self.runtime = DeltaSkillRuntime(
            permission_profiles=permission_profiles,
            protocol_profiles=protocol_profiles,
            authorized_producers=authorized_producers,
            allowed_subagent_models=allowed_subagent_models,
            trusted_skill_root=trusted_skill_root,
            skill_trust_policy=skill_trust_policy,
            skill_signature_verifier=skill_signature_verifier,
            host_security_signer=host_security_signer,
            privileged_path_policy=privileged_path_policy,
            managed_worktree_registry=managed_worktree_registry,
            interceptors=interceptors,
            event_validators=event_validators,
            event_upgraders=event_upgraders,
            optional_unknown_event_types=optional_unknown_event_types,
            authority_provider=authority_provider,
            evidence_store=self.evidence,
            tool_result_begin_hook=self.committer.begin_tool_result,
            tool_result_terminal_hook=self.committer,
            durable_commit_hook=self.committer,
        )
        self._locks: dict[tuple[Any, ...], threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def _now(self) -> datetime:
        observed = self._clock()
        if (
            not isinstance(observed, datetime)
            or observed.tzinfo is None
            or observed.utcoffset() is None
        ):
            raise ContractError("runtime-assurance clock must be timezone-aware")
        return observed.astimezone(UTC)

    @staticmethod
    def _scope_key(
        context: SecurityContext,
        invocation: DeltaInvocation,
    ) -> tuple[Any, ...]:
        return (
            context.tenant_id,
            context.project_id,
            context.actor_id,
            context.run_id,
            context.execution_epoch,
            context.fencing_generation,
            context.authority_revision,
            invocation.revision_set_id,
        )

    def _scope_lock(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
    ) -> threading.RLock:
        key = self._scope_key(context, invocation)
        with self._locks_guard:
            return self._locks.setdefault(key, threading.RLock())

    def ready(self, *, production: bool = False) -> tuple[bool, str]:
        try:
            storage = self.store.readiness()  # type: ignore[attr-defined]
        except Exception:
            return False, "runtime-assurance durable store readiness failed"
        if not storage.ready:
            return False, storage.reason
        if production and storage.backend != "postgresql":
            return False, "production runtime assurance requires PostgreSQL"
        if production and not bool(
            getattr(self.authority_provider, "trusted_for_production", False)
        ):
            return (
                False,
                "production runtime assurance requires a trusted authority provider",
            )
        if production and not bool(
            getattr(self.authority_provider, "deadline_enforced", False)
        ):
            return (
                False,
                "production runtime assurance requires deadline-enforced authority lookup",
            )
        if production and not bool(getattr(self.authority_provider, "durable", False)):
            return (
                False,
                "production runtime assurance requires durable authority reconciliation",
            )
        if production and not callable(
            getattr(self.authority_provider, "resolve", None)
        ):
            return (
                False,
                "production authority provider must implement resolve(..., deadline=...)",
            )
        if production and not bool(
            getattr(
                self.authority_provider,
                "base_origin_receipt_verified",
                False,
            )
        ):
            return (
                False,
                "production authority provider must verify durable base Skill origin receipts",
            )
        if production and not callable(
            getattr(self.authority_provider, "verify_origin_receipt", None)
        ):
            return (
                False,
                "production authority provider must implement base origin receipt verification",
            )
        if production and not bool(
            getattr(
                self.authority_provider,
                "host_envelope_signatures_verified",
                False,
            )
        ):
            return (
                False,
                "production authority provider must verify Host envelope signatures",
            )
        if production and not bool(
            getattr(
                self.authority_provider,
                "host_envelope_issuer_durable",
                False,
            )
        ):
            return (
                False,
                "production authority provider requires a durable Host envelope issuer",
            )
        if production and not callable(
            getattr(self.authority_provider, "issue_host_envelope", None)
        ):
            return (
                False,
                "production authority provider must issue exact signed Host envelopes",
            )
        if production and not callable(
            getattr(self.authority_provider, "verify_host_envelope", None)
        ):
            return (
                False,
                "production authority provider must verify signed Host envelopes",
            )
        runtime_ready, reason = self.runtime.readiness(production=production)
        if not runtime_ready:
            return False, reason
        return True, "durable runtime-assurance control plane is ready"

    def _effective_deadline(self, deadline: datetime | None) -> datetime:
        now = self._now()
        configured = now + timedelta(seconds=self.invocation_timeout_seconds)
        if deadline is None:
            return configured
        if (
            not isinstance(deadline, datetime)
            or deadline.tzinfo is None
            or deadline.utcoffset() is None
        ):
            raise ContractError("runtime-assurance deadline must be timezone-aware")
        requested = deadline.astimezone(UTC)
        return min(configured, requested)

    def _resolve_authority(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
        *,
        deadline: datetime,
    ) -> RuntimeAssuranceAuthority:
        now = self._now()
        if now >= deadline:
            raise TimeoutError("runtime-assurance invocation deadline expired")
        lookup_deadline = min(
            deadline,
            now + timedelta(seconds=self.authority_lookup_timeout_seconds),
        )
        started = time.monotonic()
        resolver = getattr(self.authority_provider, "resolve", None)
        try:
            if callable(resolver):
                authority = resolver(
                    context,
                    invocation,
                    deadline=lookup_deadline,
                )
            else:
                authority = self.authority_provider(context, invocation)
        except TimeoutError:
            raise
        except ContractError:
            raise
        except Exception as exc:
            raise ContractError(
                "host-minted runtime-assurance authority resolution failed"
            ) from exc
        elapsed = time.monotonic() - started
        if (
            elapsed > self.authority_lookup_timeout_seconds
            or self._now() >= lookup_deadline
        ):
            raise TimeoutError("runtime-assurance authority lookup timed out")
        if not isinstance(authority, RuntimeAssuranceAuthority):
            raise ContractError("authority provider returned an invalid host snapshot")
        authority.verify_binding(context, invocation)
        origin_verifier = getattr(
            self.authority_provider,
            "verify_origin_receipt",
            None,
        )
        if callable(origin_verifier):
            verified = origin_verifier(
                context,
                invocation,
                authority.originating_base_skill,
                deadline=lookup_deadline,
            )
            if verified is not True:
                raise ContractError(
                    "base Skill execution receipt could not be verified"
                )
        return authority

    def _preflight_unknown(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
        *,
        message: str,
    ) -> DeltaResult:
        descriptor = DELTA_SKILL_REGISTRY[invocation.extension_skill or ""]
        record: dict[str, Any] = {
            "apiVersion": DELTA_API_VERSION,
            "tenantId": context.tenant_id,
            "projectId": context.project_id,
            "actorId": context.actor_id,
            "authorityRevision": context.authority_revision,
            "skillId": descriptor.skill_id,
            "skillName": descriptor.name,
            "invocation": invocation.to_wire(),
            "status": ResultStatus.UNKNOWN.value,
            "output": None,
            "message": message,
            "proofObligationRefs": [],
        }
        reference = self.evidence.put(context, record)
        return DeltaResult(
            invocation.invocation_id,
            ResultStatus.UNKNOWN,
            (reference,),
            (),
            message,
        )

    @staticmethod
    def _request_digest(
        context: SecurityContext,
        invocation: DeltaInvocation,
        authority: RuntimeAssuranceAuthority,
    ) -> str:
        return digest_object(
            {
                "apiVersion": DELTA_API_VERSION,
                "tenantId": context.tenant_id,
                "projectId": context.project_id,
                "actorId": context.actor_id,
                "executionEpoch": context.execution_epoch,
                "fencingGeneration": context.fencing_generation,
                "authorityRevision": context.authority_revision,
                "authorityDigest": authority.authority_digest,
                "invocation": invocation.to_wire(),
            },
            domain="delta-runtime-assurance-invocation",
        )

    @staticmethod
    def _invocation_matches(
        observed: Any,
        invocation: DeltaInvocation,
    ) -> bool:
        if not isinstance(observed, Mapping):
            return False
        return hmac.compare_digest(
            digest_object(observed, domain="delta-invocation-wire"),
            digest_object(invocation.to_wire(), domain="delta-invocation-wire"),
        )

    def register_authority(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
        authority: RuntimeAssuranceAuthority,
    ) -> None:
        register = getattr(self.authority_provider, "register", None)
        if not callable(register):
            raise ContractError("configured authority provider is externally managed")
        register(context, invocation, authority)

    def terminate_invocation_capabilities(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        reason: CapabilityRevocationReason,
    ) -> tuple[CapabilityLeaseRecord, ...]:
        """Monotonically revoke all borrowed authority for one invocation.

        Host cancellation, timeout, turn-abort, authority revocation and normal
        completion paths call this boundary.  The durable store performs the
        update and audit/outbox append atomically; a caller cannot manufacture
        an active capability by retaining or deserializing a Python object.
        """

        if not isinstance(reason, CapabilityRevocationReason):
            raise TypeError("capability termination reason must be typed")
        return self.store.revoke_invocation_capability_leases(
            context,
            revision_set_id=revision_set_id,
            invocation_id=_text(invocation_id, "invocation_id"),
            reason=reason,
        )

    def reconcile_executor_replacement_effect(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        effect_id: str,
        target_state: ExecutorReplacementEffectState,
        observations: Mapping[str, Any],
    ) -> ExecutorReplacementEffectRecord:
        """Record one Host-observed replacement side effect without widening rights.

        Capability revocation is deliberately excluded because it is completed
        atomically by ``advance_executor_generation``.  Workspace and external
        reconciliation may only move from PENDING to a terminal typed state and
        always carry immutable evidence.  A later activation invocation reloads
        the exact three durable effects before the executor can become ACTIVE.
        """

        if not isinstance(context, SecurityContext):
            raise TypeError("typed security context is required")
        revision = _text(revision_set_id, "revision_set_id")
        require_sha256_digest(revision, field="revision_set_id")
        identifier = _text(effect_id, "effect_id")
        if target_state not in {
            ExecutorReplacementEffectState.SUCCEEDED,
            ExecutorReplacementEffectState.FAILED,
            ExecutorReplacementEffectState.UNKNOWN,
        }:
            raise ValidationError("executor replacement target state is not terminal")
        evidence_values = _mapping(observations, "observations")
        if not evidence_values:
            raise ValidationError("executor replacement observations must not be empty")
        snapshot = self.store.load_runtime_assurance_scope(
            context,
            revision_set_id=revision,
        )
        matches = tuple(
            item
            for item in snapshot.executor_replacement_effects
            if item.effect_id == identifier
        )
        if len(matches) != 1:
            raise ConflictError(
                "executor replacement effect is not uniquely available",
                code="EXECUTOR_REPLACEMENT_EFFECT_CONFLICT",
            )
        current = matches[0]
        if current.kind is ExecutorReplacementEffectKind.CAPABILITY_REVOCATION:
            raise AuthorizationError(
                "capability revocation reconciliation is storage-owned",
                code="EXECUTOR_REPLACEMENT_EFFECT_FORBIDDEN",
            )
        if current.state not in {
            ExecutorReplacementEffectState.PENDING,
            target_state,
        }:
            raise ConflictError(
                "executor replacement effect is already terminal with another state",
                code="EXECUTOR_REPLACEMENT_EFFECT_CONFLICT",
            )
        evidence_ref = self.evidence.put(
            context,
            {
                "apiVersion": DELTA_API_VERSION,
                "kind": "EXECUTOR_REPLACEMENT_EFFECT_RECONCILIATION",
                "tenantId": context.tenant_id,
                "projectId": context.project_id,
                "actorId": context.actor_id,
                "runId": context.run_id,
                "authorityRevision": context.authority_revision,
                "revisionSetId": revision,
                "effectId": current.effect_id,
                "environmentId": current.environment_id,
                "executorGeneration": current.executor_generation,
                "connectionEpoch": current.connection_epoch,
                "effectKind": current.kind.value,
                "targetState": target_state.value,
                "observations": dict(evidence_values),
            },
        )
        reconciled = self.store.reconcile_executor_replacement_effect(
            context,
            revision_set_id=revision,
            effect_id=identifier,
            expected_state=ExecutorReplacementEffectState.PENDING,
            target_state=target_state,
            evidence_ref=evidence_ref,
        )
        if (
            reconciled.state is not target_state
            or reconciled.evidence_ref != evidence_ref
            or reconciled.kind is not current.kind
        ):
            raise IntegrityError(
                "executor replacement effect reconciliation diverged",
                code="EXECUTOR_REPLACEMENT_EFFECT_DRIFT",
            )
        return reconciled

    def _replay_completed_result(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
        *,
        result_ref: str | None,
        result_digest: str | None,
    ) -> DeltaResult:
        if result_ref is None or result_digest is None:
            raise IntegrityError("completed runtime-assurance receipt lacks a result")
        record = self.runtime.read_evidence(context, result_ref)
        if (
            record.get("apiVersion") != DELTA_API_VERSION
            or record.get("tenantId") != context.tenant_id
            or record.get("projectId") != context.project_id
            or record.get("actorId") != context.actor_id
            or record.get("authorityRevision") != context.authority_revision
            or record.get("skillName") != invocation.extension_skill
            or not self._invocation_matches(record.get("invocation"), invocation)
        ):
            raise IntegrityError(
                "completed runtime-assurance result escaped its exact scope",
                code="DELTA_INVOCATION_RESULT_SCOPE_DRIFT",
            )
        try:
            status = ResultStatus(_text(record.get("status"), "status"))
        except ValueError as exc:
            raise IntegrityError(
                "completed runtime-assurance result has an invalid status"
            ) from exc
        raw_proof_refs = record.get("proofObligationRefs", ())
        if not isinstance(raw_proof_refs, (list, tuple)):
            raise IntegrityError(
                "completed runtime-assurance proof references are invalid"
            )
        proof_refs = tuple(
            _text(item, "proof obligation reference") for item in raw_proof_refs
        )
        if len(proof_refs) != len(set(proof_refs)):
            raise IntegrityError(
                "completed runtime-assurance proof references contain duplicates"
            )
        message_value = record.get("message")
        message = _text(message_value, "message") if message_value is not None else None
        result = DeltaResult(
            invocation.invocation_id,
            status,
            (result_ref,),
            proof_refs,
            message,
        )
        observed_digest = digest_object(
            result.to_wire(),
            domain="delta-invocation-result-receipt",
        )
        if not hmac.compare_digest(observed_digest, result_digest):
            raise IntegrityError(
                "completed runtime-assurance result receipt digest diverged",
                code="DELTA_INVOCATION_RESULT_DIGEST_MISMATCH",
            )
        return result

    def reconcile_invocation(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
        *,
        expected_claim_epoch: int,
        recovered_result_ref: str,
        recovery_evidence: Mapping[str, Any],
        deadline: datetime | None = None,
    ) -> RuntimeAssuranceInvocationClaimRecord:
        """Reconcile one crash-fenced invocation without rerunning its handler.

        Recovery is intentionally an internal, evidence-bound operation.  The
        caller supplies the already-written content-addressed result reference
        and structured recovery observations.  This method re-resolves the
        exact host authority, validates the result against the original
        invocation scope, writes an immutable recovery record, and delegates
        the final compare-and-swap to the durable store.
        """

        if not isinstance(context, SecurityContext) or not isinstance(
            invocation, DeltaInvocation
        ):
            raise TypeError("typed security context and delta invocation are required")
        if invocation.extension_skill not in DELTA_SKILL_REGISTRY:
            raise ContractError(
                "runtime-assurance recovery must select an exact internal Skill"
            )
        claim_epoch = _positive(expected_claim_epoch, "expected_claim_epoch")
        result_ref = _text(recovered_result_ref, "recovered_result_ref")
        observations = _mapping(recovery_evidence, "recovery_evidence")
        if not observations:
            raise ValidationError("recovery_evidence must not be empty")
        effective_deadline = self._effective_deadline(deadline)
        authority = self._resolve_authority(
            context,
            invocation,
            deadline=effective_deadline,
        )
        request_digest = self._request_digest(context, invocation, authority)

        # Parse and scope-check the durable result before allowing storage to
        # advance RECOVERY_REQUIRED.  A placeholder digest is never accepted:
        # the exact DeltaResult receipt digest is recomputed from verified CAS
        # bytes and becomes part of both recovery evidence and the CAS update.
        record = self.runtime.read_evidence(context, result_ref)
        if (
            record.get("apiVersion") != DELTA_API_VERSION
            or record.get("tenantId") != context.tenant_id
            or record.get("projectId") != context.project_id
            or record.get("actorId") != context.actor_id
            or record.get("authorityRevision") != context.authority_revision
            or record.get("skillName") != invocation.extension_skill
            or not self._invocation_matches(record.get("invocation"), invocation)
        ):
            raise IntegrityError(
                "recovery result escaped its exact invocation scope",
                code="DELTA_INVOCATION_RESULT_SCOPE_DRIFT",
            )
        try:
            status = ResultStatus(_text(record.get("status"), "status"))
        except ValueError as exc:
            raise IntegrityError("recovery result has an invalid status") from exc
        raw_proof_refs = record.get("proofObligationRefs", ())
        if not isinstance(raw_proof_refs, (list, tuple)):
            raise IntegrityError("recovery result proof references are invalid")
        proof_refs = tuple(
            _text(item, "proof obligation reference") for item in raw_proof_refs
        )
        if len(proof_refs) != len(set(proof_refs)):
            raise IntegrityError("recovery result proof references contain duplicates")
        message_value = record.get("message")
        message = _text(message_value, "message") if message_value is not None else None
        recovered_result = DeltaResult(
            invocation.invocation_id,
            status,
            (result_ref,),
            proof_refs,
            message,
        )
        result_digest = digest_object(
            recovered_result.to_wire(),
            domain="delta-invocation-result-receipt",
        )
        recovery_ref = self.evidence.put(
            context,
            {
                "apiVersion": DELTA_API_VERSION,
                "kind": "RUNTIME_ASSURANCE_INVOCATION_RECOVERY",
                "tenantId": context.tenant_id,
                "projectId": context.project_id,
                "actorId": context.actor_id,
                "authorityRevision": context.authority_revision,
                "invocation": invocation.to_wire(),
                "requestDigest": request_digest,
                "expectedClaimEpoch": claim_epoch,
                "recoveredResultRef": result_ref,
                "recoveredResultDigest": result_digest,
                "decision": "RECONCILE_EXISTING_RESULT_NO_REEXECUTION",
                "observations": dict(observations),
            },
        )
        reconciled = self.store.reconcile_runtime_assurance_invocation(
            context,
            revision_set_id=invocation.revision_set_id,
            invocation_id=invocation.invocation_id,
            request_digest=request_digest,
            expected_claim_epoch=claim_epoch,
            result_ref=result_ref,
            result_digest=result_digest,
            recovery_evidence_ref=recovery_ref,
        )
        if (
            reconciled.state is not RuntimeAssuranceInvocationState.COMPLETED
            or reconciled.result_ref != result_ref
            or reconciled.result_digest != result_digest
            or reconciled.recovery_evidence_ref != recovery_ref
        ):
            raise IntegrityError(
                "runtime-assurance reconciliation receipt diverged",
                code="DELTA_INVOCATION_RECOVERY_DRIFT",
            )
        return reconciled

    def reconcile_interrupted_tool_result(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        call_id: str,
        attempt: int,
        expected_claim_epoch: int,
        recovery_evidence: Mapping[str, Any],
    ) -> ToolResultCommitRecord:
        """Abort a crash-fenced pre-commit result without invoking interceptors.

        Only a uniquely scoped ``RAW_CAPTURED`` or ``INTERCEPTING`` record may
        be reconciled.  The original raw CAS is verified first; the recovery
        then creates immutable effective-result and provenance artifacts and
        advances the durable row with a compare-and-swap on its current state.
        """

        if not isinstance(context, SecurityContext):
            raise TypeError("typed security context is required")
        revision = _text(revision_set_id, "revision_set_id")
        require_sha256_digest(revision, field="revision_set_id")
        invocation_key = _text(invocation_id, "invocation_id")
        call_key = _text(call_id, "call_id")
        checked_attempt = _positive(attempt, "attempt")
        claim_epoch = _positive(expected_claim_epoch, "expected_claim_epoch")
        observations = _mapping(recovery_evidence, "recovery_evidence")
        if not observations:
            raise ValidationError("recovery_evidence must not be empty")
        snapshot = self.store.load_runtime_assurance_scope(
            context,
            revision_set_id=revision,
        )
        candidates = tuple(
            record
            for record in snapshot.tool_results
            if record.invocation_id == invocation_key
            and record.call_id == call_key
            and record.attempt == checked_attempt
        )
        if len(candidates) != 1:
            raise ConflictError(
                "interrupted tool result is not uniquely recoverable",
                code="TOOL_RESULT_RECOVERY_CONFLICT",
            )
        current = candidates[0]
        if current.state not in {
            ToolResultCommitState.RAW_CAPTURED,
            ToolResultCommitState.INTERCEPTING,
        }:
            raise ConflictError(
                "tool result is not awaiting pre-commit recovery",
                code="TOOL_RESULT_RECOVERY_CONFLICT",
            )
        raw_record = self.runtime.read_evidence(context, current.raw_result_ref)
        if raw_record.get("kind") != "RAW_TOOL_RESULT":
            raise IntegrityError(
                "tool-result recovery raw evidence has an invalid kind",
                code="TOOL_RESULT_RECOVERY_EVIDENCE_DRIFT",
            )
        raw_content = _mapping(raw_record.get("content"), "raw tool result content")
        raw_identity = _mapping(raw_content.get("identity"), "raw tool result identity")
        expected_identity = {
            "invocationId": current.invocation_id,
            "callId": current.call_id,
            "executionPlanHash": current.execution_plan_hash,
            "environmentId": current.environment_id,
            "authoritySnapshotId": current.authority_snapshot_id,
        }
        if not hmac.compare_digest(
            digest_object(raw_identity, domain="delta-tool-call-identity"),
            digest_object(expected_identity, domain="delta-tool-call-identity"),
        ):
            raise IntegrityError(
                "tool-result recovery raw identity diverged",
                code="TOOL_RESULT_RECOVERY_EVIDENCE_DRIFT",
            )
        artifact_binding = {
            "apiVersion": DELTA_API_VERSION,
            "tenantId": context.tenant_id,
            "projectId": context.project_id,
            "runId": context.run_id,
            "invocationId": current.invocation_id,
            "callId": current.call_id,
            "commitKey": _tool_result_commit_key(
                current.invocation_id,
                current.call_id,
                current.attempt,
                current.execution_epoch,
            ),
        }
        recovery_ref = self.evidence.put(
            context,
            artifact_binding
            | {
                "kind": "TOOL_RESULT_PRECOMMIT_RECOVERY",
                "priorState": current.state.value,
                "expectedClaimEpoch": claim_epoch,
                "rawResultRef": current.raw_result_ref,
                "decision": "ABORT_WITHOUT_INTERCEPTOR_REEXECUTION",
                "observations": dict(observations),
            },
        )
        effective_ref = self.evidence.put(
            context,
            artifact_binding
            | {
                "kind": "EFFECTIVE_TOOL_RESULT",
                "recoveryEvidenceRef": recovery_ref,
                "content": dict(raw_content),
            },
        )
        mutation_ref = self.evidence.put(
            context,
            artifact_binding
            | {
                "kind": "INTERCEPTOR_DECISIONS",
                "recoveryEvidenceRef": recovery_ref,
                "content": [],
            },
        )
        failure_reason = (
            "worker terminated before interceptor completion; "
            "reconciled without interceptor re-execution"
        )
        aborted = self.store.reconcile_tool_result_abort(
            context,
            revision_set_id=revision,
            invocation_id=current.invocation_id,
            call_id=current.call_id,
            attempt=current.attempt,
            expected_claim_epoch=claim_epoch,
            execution_plan_hash=current.execution_plan_hash,
            environment_id=current.environment_id,
            authority_snapshot_id=current.authority_snapshot_id,
            raw_result_ref=current.raw_result_ref,
            effective_result_ref=effective_ref,
            recovery_evidence_ref=recovery_ref,
            interceptor_chain=(),
            failure_kind=ToolResultFailureKind.CANCELLED,
            failure_reason=failure_reason,
            mutation_provenance_ref=mutation_ref,
            expected_state=current.state,
        )
        if (
            aborted.state is not ToolResultCommitState.ABORTED
            or aborted.raw_result_ref != current.raw_result_ref
            or aborted.effective_result_ref != effective_ref
            or aborted.mutation_provenance_ref != mutation_ref
            or aborted.recovery_evidence_ref != recovery_ref
            or aborted.failure_kind is not ToolResultFailureKind.CANCELLED
            or aborted.failure_reason != failure_reason
        ):
            raise IntegrityError(
                "tool-result recovery receipt diverged",
                code="TOOL_RESULT_RECOVERY_DRIFT",
            )
        return aborted

    def execute_internal(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
        *,
        deadline: datetime | None = None,
    ) -> DeltaResult:
        if not isinstance(context, SecurityContext) or not isinstance(
            invocation, DeltaInvocation
        ):
            raise TypeError("typed security context and delta invocation are required")
        if invocation.extension_skill not in DELTA_SKILL_REGISTRY:
            raise ContractError(
                "internal runtime-assurance invocation must select an exact Skill"
            )
        effective_deadline = self._effective_deadline(deadline)
        try:
            authority = self._resolve_authority(
                context,
                invocation,
                deadline=effective_deadline,
            )
        except TimeoutError:
            return self._preflight_unknown(
                context,
                invocation,
                message="host security context lookup exhausted the invocation budget",
            )
        request_digest = self._request_digest(context, invocation, authority)
        lock = self._scope_lock(context, invocation)
        with lock:
            with self.store.claim_runtime_assurance_invocation(
                context,
                revision_set_id=invocation.revision_set_id,
                invocation_id=invocation.invocation_id,
                request_digest=request_digest,
            ) as claim:
                observed_claim_scope = (
                    claim.tenant_id,
                    claim.project_id,
                    claim.actor_id,
                    claim.run_id,
                    claim.execution_epoch,
                    claim.fencing_generation,
                    claim.authority_revision,
                    claim.revision_set_id,
                    claim.invocation_id,
                    claim.request_digest,
                )
                expected_claim_scope = (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    context.run_id,
                    context.execution_epoch,
                    context.fencing_generation,
                    context.authority_revision,
                    invocation.revision_set_id,
                    invocation.invocation_id,
                    request_digest,
                )
                if observed_claim_scope != expected_claim_scope:
                    raise IntegrityError(
                        "runtime-assurance invocation claim escaped its exact scope",
                        code="RUNTIME_ASSURANCE_CLAIM_SCOPE_DRIFT",
                    )
                if claim.state is RuntimeAssuranceInvocationState.RECOVERY_REQUIRED:
                    raise ConflictError(
                        "runtime-assurance invocation requires explicit recovery",
                        code="RUNTIME_ASSURANCE_RECOVERY_REQUIRED",
                    )
                if (
                    claim.disposition
                    is RuntimeAssuranceClaimDisposition.COMPLETED_REPLAY
                ):
                    return self._replay_completed_result(
                        context,
                        invocation,
                        result_ref=claim.result_ref,
                        result_digest=claim.result_digest,
                    )
                if not claim.execute_allowed:
                    raise ConflictError(
                        "runtime-assurance invocation is not executable",
                        code="RUNTIME_ASSURANCE_INVOCATION_NOT_ACQUIRED",
                    )
                self.committer.prepare_operation_authority(
                    context,
                    authority,
                    invocation,
                )
                snapshot = self.store.load_runtime_assurance_scope(
                    context,
                    revision_set_id=invocation.revision_set_id,
                )
                if (
                    snapshot.revision_set_id != invocation.revision_set_id
                    or snapshot.authority_revision != context.authority_revision
                ):
                    raise IntegrityError(
                        "durable runtime-assurance snapshot scope diverged",
                        code="DELTA_STORAGE_SCOPE_DRIFT",
                    )
                now = self._now()
                expired = False
                for lease in snapshot.capability_leases:
                    if (
                        lease.state is CapabilityLeaseState.ACTIVE
                        and now >= lease.expires_at
                    ):
                        self.store.expire_capability_lease(
                            context,
                            revision_set_id=invocation.revision_set_id,
                            lease_id=lease.lease_id,
                            now=now,
                        )
                        expired = True
                if expired:
                    snapshot = self.store.load_runtime_assurance_scope(
                        context,
                        revision_set_id=invocation.revision_set_id,
                    )
                self.runtime.restore_scope(context, snapshot)
                if self._now() >= effective_deadline:
                    result = self._preflight_unknown(
                        context,
                        invocation,
                        message="runtime-assurance invocation deadline expired before execution",
                    )
                else:
                    result = self.runtime.execute(
                        invocation,
                        context=context,
                        trusted_authority=authority,
                        deadline=effective_deadline,
                    )
                    if (
                        invocation.extension_skill
                        == "elmos-invocation-scoped-capability-lease"
                        and invocation.payload.get("action") == "use"
                        and result.status is ResultStatus.DENIED
                        and isinstance(invocation.payload.get("leaseId"), str)
                        and isinstance(invocation.payload.get("capability"), str)
                    ):
                        try:
                            lease_id = _text(
                                invocation.payload.get("leaseId"), "leaseId"
                            )
                            capability = _text(
                                invocation.payload.get("capability"), "capability"
                            )
                        except ValidationError:
                            pass
                        else:
                            observed_at = self._now()
                            matching_leases = tuple(
                                lease
                                for lease in snapshot.capability_leases
                                if lease.lease_id == lease_id
                            )
                            denied_lease = (
                                matching_leases[0]
                                if len(matching_leases) == 1
                                else None
                            )
                            use_denial_reason: CapabilityUseDenialReason | None
                            if denied_lease is None:
                                use_denial_reason = (
                                    CapabilityUseDenialReason.UNKNOWN_LEASE
                                )
                            elif (
                                denied_lease.state is CapabilityLeaseState.EXPIRED
                                or observed_at >= denied_lease.expires_at
                            ):
                                use_denial_reason = (
                                    CapabilityUseDenialReason.LEASE_EXPIRED
                                )
                                if denied_lease.state is CapabilityLeaseState.ACTIVE:
                                    self.store.expire_capability_lease(
                                        context,
                                        revision_set_id=invocation.revision_set_id,
                                        lease_id=denied_lease.lease_id,
                                        now=observed_at,
                                    )
                            elif denied_lease.state is not CapabilityLeaseState.ACTIVE:
                                use_denial_reason = (
                                    CapabilityUseDenialReason.LEASE_NOT_ACTIVE
                                )
                            elif capability not in denied_lease.capabilities:
                                use_denial_reason = (
                                    CapabilityUseDenialReason.CAPABILITY_NOT_GRANTED
                                )
                            elif (
                                denied_lease.environment_id
                                != authority.security_bindings["environmentId"]
                            ):
                                use_denial_reason = (
                                    CapabilityUseDenialReason.ENVIRONMENT_MISMATCH
                                )
                            elif (
                                denied_lease.authority_snapshot_id
                                != context.authority_revision
                            ):
                                use_denial_reason = CapabilityUseDenialReason.AUTHORITY_SNAPSHOT_MISMATCH
                            elif capability not in authority.capabilities:
                                use_denial_reason = CapabilityUseDenialReason.AUTHORITY_CAPABILITY_MISMATCH
                            else:
                                # A syntactic or unrelated contract denial is
                                # not rewritten as a capability-use decision.
                                use_denial_reason = None
                            if use_denial_reason is not None:
                                self.store.audit_capability_use_denial(
                                    context,
                                    revision_set_id=invocation.revision_set_id,
                                    lease_id=lease_id,
                                    subject_invocation_id=(
                                        None
                                        if denied_lease is None
                                        else denied_lease.invocation_id
                                    ),
                                    operation_invocation_id=invocation.invocation_id,
                                    capability=capability,
                                    reason=use_denial_reason,
                                )
                    if self._now() >= effective_deadline:
                        self.terminate_invocation_capabilities(
                            context,
                            revision_set_id=invocation.revision_set_id,
                            invocation_id=invocation.invocation_id,
                            reason=CapabilityRevocationReason.TIMED_OUT,
                        )
                        # A content-addressed durable commit is authoritative
                        # even when the caller's budget expires immediately
                        # afterwards.  Replacing it with UNKNOWN would create
                        # a split-brain receipt and invite an unsafe retry.
                        if result.status is not ResultStatus.COMMITTED:
                            result = self._preflight_unknown(
                                context,
                                invocation,
                                message=(
                                    "runtime-assurance invocation exhausted its budget; "
                                    "borrowed capabilities were revoked"
                                ),
                            )
                if len(result.evidence_refs) != 1:
                    raise IntegrityError(
                        "runtime-assurance invocation lacks one durable result"
                    )
                for reference in result.evidence_refs:
                    self.runtime.read_evidence(context, reference)
                result_ref = result.evidence_refs[0]
                result_digest = digest_object(
                    result.to_wire(),
                    domain="delta-invocation-result-receipt",
                )
                completed = self.store.complete_runtime_assurance_invocation(
                    context,
                    revision_set_id=invocation.revision_set_id,
                    invocation_id=invocation.invocation_id,
                    request_digest=request_digest,
                    expected_claim_epoch=claim.claim_epoch,
                    result_ref=result_ref,
                    result_digest=result_digest,
                )
                if (
                    completed.state is not RuntimeAssuranceInvocationState.COMPLETED
                    or completed.result_ref != result_ref
                    or completed.result_digest != result_digest
                ):
                    raise IntegrityError(
                        "runtime-assurance completion receipt diverged"
                    )
                return result


__all__ = [
    "EvidenceBackedDeltaStore",
    "RUNTIME_ASSURANCE_TOOL_DIGEST",
    "RegisteredRuntimeAssuranceAuthorityProvider",
    "RuntimeAssuranceControlPlane",
    "RuntimeAssuranceDurableCommitter",
]
