from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
from typing import Any, ContextManager
from unittest.mock import MagicMock
import unittest

from elmos_proof_harness.assurance_policies import (
    HostSecurityContextSigner,
    ManagedWorktreeRegistry,
    PrivilegedPathPolicy,
    SkillTrustDomainPolicy,
)
from elmos_proof_harness.canonical import digest_bytes, digest_object
from elmos_proof_harness.contracts import SecurityContext
from elmos_proof_harness.delta import (
    DELTA_SKILL_REGISTRY,
    AuthoritySnapshot,
    BaseSkillOriginBinding,
    CallIdentity,
    ContractError,
    DeltaInvocation,
    DeltaSkillRuntime,
    EnvironmentSettingsBinding,
    ExecutionPlan,
    ModelSnapshot,
    PendingToolCallBinding,
    PermissionProfile,
    ResultStatus,
    RuntimeAssuranceAuthority,
    SubagentBudgetReservation,
    ToolResult,
    _tool_result_commit_key,
)
from elmos_proof_harness.delta_storage import (
    CapabilityLeaseRecord,
    CapabilityLeaseState,
    CapabilityRevocationReason,
    CapabilityUseDenialReason,
    DurableEventInstanceRecord,
    DurableEventInstanceState,
    DurableEventOwnerChangePreflight,
    DurableEventRegistrationRecord,
    DurableEventSemantics,
    EnvironmentAttachmentRecord,
    EventCompatibility,
    EventCompatibilityDecision,
    EventOwnerChangeAction,
    ExecutorGenerationRecord,
    ExecutorGenerationState,
    ExecutorReplacementEffectKind,
    ExecutorReplacementEffectRecord,
    ExecutorReplacementEffectState,
    HostSignedEnvelope,
    InterceptorCommitRecord,
    PendingToolCallBindingRecord,
    PendingToolCallBindingState,
    RuntimeAuthorityCapabilityReceiptRecord,
    RuntimeAssuranceScopeSnapshot,
    RuntimeAssuranceClaimDisposition,
    RuntimeAssuranceInvocationClaimRecord,
    RuntimeAssuranceInvocationState,
    RuntimeAssuranceStore,
    StepExecutionPlanRecord,
    StepPlanState,
    SubagentBudgetReservationBindingRecord,
    SubagentBudgetReservationState,
    SubagentExecutionSpecRecord,
    SubagentExecutionSpecState,
    ToolResultCommitRecord,
    ToolResultCommitState,
    ToolResultFailureKind,
    TypedIngressKind,
    TypedIngressPage,
    TypedIngressRecord,
    WorkspaceLeaseRecord,
    WorkspaceLeaseState,
)
from elmos_proof_harness.errors import (
    AuthorizationError,
    ConflictError,
    IntegrityError,
    NotFoundError,
    ValidationError,
)
from elmos_proof_harness.evidence import EvidenceService
from elmos_proof_harness.runtime_assurance import (
    EvidenceBackedDeltaStore,
    RegisteredRuntimeAssuranceAuthorityProvider,
    RuntimeAssuranceControlPlane,
    RuntimeAssuranceDurableCommitter,
)
from elmos_proof_harness.storage import StorageReadiness, StorageStatus
from elmos_proof_harness.store import SQLiteStore


NOW = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)


class _ProductionAuthorityProvider:
    trusted_for_production = True
    durable = True
    deadline_enforced = True
    base_origin_receipt_verified = True
    host_envelope_signatures_verified = True
    host_envelope_issuer_durable = True

    def __call__(
        self, context: SecurityContext, invocation: DeltaInvocation
    ) -> RuntimeAssuranceAuthority:
        del context, invocation
        raise ContractError("readiness probe does not resolve authority")

    def resolve(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
        *,
        deadline: datetime | None,
    ) -> RuntimeAssuranceAuthority:
        del context, invocation, deadline
        raise ContractError("readiness probe does not resolve authority")

    def verify_origin_receipt(
        self,
        context: SecurityContext,
        invocation: DeltaInvocation,
        origin: BaseSkillOriginBinding,
        *,
        deadline: datetime | None,
    ) -> bool:
        del context, invocation, origin, deadline
        return True

    def issue_host_envelope(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
    ) -> HostSignedEnvelope:
        del kind, payload
        raise AssertionError("readiness probe does not issue envelopes")

    def verify_host_envelope(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        envelope: HostSignedEnvelope,
    ) -> bool:
        del kind, payload, envelope
        return True


class _TrustedInterceptor:
    trusted_for_production = True
    deadline_enforced = True

    def __call__(self, result: ToolResult) -> ToolResult:
        return result


class RuntimeAssuranceControlPlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.authority_revision = digest_bytes(
            b"runtime-authority-v1", domain="authority-revision"
        )
        self.revision_set_id = digest_bytes(
            b"repository-revision-v1", domain="revision-set"
        )
        self.context = SecurityContext(
            "tenant-alpha",
            "project-alpha",
            "actor-alpha",
            "run-9999",
            1,
            1,
            self.authority_revision,
        )
        self.other_context = SecurityContext(
            "tenant-other",
            "project-alpha",
            "actor-alpha",
            "run-9999",
            1,
            1,
            self.authority_revision,
        )
        self.sqlite = SQLiteStore(":memory:")
        self.sqlite.register_scope(self.context, now=NOW)
        self.sqlite.register_scope(self.other_context, now=NOW)
        self.evidence = EvidenceService(self.sqlite)
        self.temporary = tempfile.TemporaryDirectory()
        self.trusted_skill_root = Path(self.temporary.name)
        self.tool_contract = {
            "toolId": "read_file",
            "inputSchema": {"type": "object", "additionalProperties": False},
        }
        self.handler_digest = digest_bytes(b"read_file-handler-v1", domain="handler")
        self.invocation = DeltaInvocation(
            "tenant-alpha",
            "goal-001",
            "run-9999",
            1,
            "step-001",
            "inv-12345",
            self.revision_set_id,
            "elmos-step-finalized-execution-plan",
            {
                "modelSnapshot": {
                    "provider": "openai",
                    "model": "gpt-5",
                    "revision": "2026-08-30",
                },
                "tools": ["read_file"],
                "toolContracts": {"read_file": self.tool_contract},
                "handlerDigests": {"read_file": self.handler_digest},
                "capabilities": ["fs.read"],
                "environmentSnapshotId": "env-snap-1",
                "authoritySnapshotId": self.authority_revision,
                "toolMode": "NATIVE",
                "planId": "plan-1",
            },
        )
        self.authority = self._authority()

    def tearDown(self) -> None:
        self.sqlite.close()
        self.temporary.cleanup()

    def _authority(self) -> RuntimeAssuranceAuthority:
        owner = AuthoritySnapshot(
            self.authority_revision,
            frozenset({"fs.read"}),
            "actor-alpha",
            "env-001",
            "profile-v1",
            digest_bytes(b"owner-policy", domain="policy"),
        )
        parent = AuthoritySnapshot(
            digest_bytes(b"parent-authority-v1", domain="authority-revision"),
            frozenset({"fs.read"}),
            "root-actor",
            "env-001",
            "profile-v1",
            digest_bytes(b"parent-policy", domain="policy"),
        )
        receipt_ref = "base-origin-receipt"
        assert self.invocation.extension_skill is not None
        origin = self._origin(
            self.invocation.invocation_id,
            self.invocation.extension_skill,
            receipt_ref=receipt_ref,
        )
        return RuntimeAssuranceAuthority(
            tenant_id="tenant-alpha",
            project_id="project-alpha",
            actor_id="actor-alpha",
            run_id="run-9999",
            execution_epoch=1,
            fencing_generation=1,
            authority_revision=self.authority_revision,
            revision_set_id=self.revision_set_id,
            step_id="step-001",
            execution_id="execution-001",
            originating_base_skill=origin,
            environment_ids=frozenset({"env-001"}),
            environment_snapshot_ids=frozenset({"env-snap-1"}),
            permission_profile_versions=frozenset({"profile-v1"}),
            capabilities=frozenset({"fs.read"}),
            tools=frozenset({"read_file"}),
            tool_modes=frozenset({"NATIVE"}),
            selected_models=frozenset({ModelSnapshot("openai", "gpt-5", "2026-08-30")}),
            originating_plan_hashes=frozenset(),
            security_eligible=True,
            account_stable=True,
            security_bindings={
                "pluginId": "plugin-1",
                "toolId": "tool-1",
                "accountId": "account-1",
                "tenantId": "tenant-alpha",
                "environmentId": "env-001",
                "invocationId": "inv-12345",
                "policyVersion": self.authority_revision,
            },
            entitlements={"role": "operator"},
            owner_authority=owner,
            parent_authority_snapshot=parent,
            policy_permissions=frozenset({"fs.read"}),
            authority_result_snapshot_id=digest_bytes(
                b"authority-result-v1", domain="authority-result"
            ),
            authorized_producers=frozenset(),
            pending_calls=frozenset(),
            verified_evidence_refs=frozenset({receipt_ref}),
            executor_bindings=frozenset(),
            event_registrations=(),
            parent_execution_id="parent-execution-1",
            parent_authority=frozenset({"fs.read"}),
            parent_tools=frozenset({"read_file"}),
            parent_max_output_tokens=4096,
            budget_reservations=(),
            allowed_subagent_models=frozenset(),
            delegation_allowed_invocations=frozenset(),
            workspace_authorities=(),
            tool_contracts={"read_file": self.tool_contract},
            handler_digests={"read_file": self.handler_digest},
        )

    def _origin(
        self,
        invocation_id: str,
        extension_skill: str,
        *,
        environment_id: str = "env-001",
        revision_set_id: str | None = None,
        receipt_ref: str = "base-origin-receipt",
    ) -> BaseSkillOriginBinding:
        return BaseSkillOriginBinding.bind_host_receipt(
            skill_id="ELMOS-V3-007",
            skill_name="elmos-harness-runtime-kernel",
            owner_kernel="K7",
            execution_id="execution-001",
            tenant_id=self.context.tenant_id,
            project_id=self.context.project_id,
            actor_id=self.context.actor_id,
            run_id=self.context.run_id or "",
            execution_epoch=self.context.execution_epoch,
            fencing_generation=self.context.fencing_generation,
            authority_revision=self.authority_revision,
            revision_set_id=revision_set_id or self.revision_set_id,
            step_id="step-001",
            invocation_id=invocation_id,
            extension_skill=extension_skill,
            environment_id=environment_id,
            receipt_ref=receipt_ref,
            receipt_state="EXECUTING",
        )

    def _empty_snapshot(
        self, *, revision_set_id: str | None = None
    ) -> RuntimeAssuranceScopeSnapshot:
        return RuntimeAssuranceScopeSnapshot(
            tenant_id=self.context.tenant_id,
            project_id=self.context.project_id,
            actor_id=self.context.actor_id,
            run_id=self.context.run_id or "",
            execution_epoch=self.context.execution_epoch,
            fencing_generation=self.context.fencing_generation,
            authority_revision=self.authority_revision,
            revision_set_id=revision_set_id or self.revision_set_id,
            pending_tool_calls=(),
            tool_results=(),
            step_plans=(),
            runtime_authority_receipts=(),
            capability_leases=(),
            executor_generations=(),
            environment_attachments=(),
            executor_replacement_effects=(),
            workspace_leases=(),
            event_registrations=(),
            durable_events=(),
            typed_ingress=(),
            subagent_budget_reservations=(),
            subagent_execution_specs=(),
        )

    def _store(self) -> MagicMock:
        store = MagicMock(spec=RuntimeAssuranceStore)
        store.readiness = MagicMock(
            return_value=StorageReadiness(
                StorageStatus.READY,
                "test PostgreSQL 17 store is ready",
                "postgresql",
                schema_version=304,
                server_version="17.6",
            )
        )
        completed: dict[str, RuntimeAssuranceInvocationClaimRecord] = {}

        def claim(
            context: SecurityContext,
            *,
            revision_set_id: str,
            invocation_id: str,
            request_digest: str,
            now: datetime | None = None,
        ) -> ContextManager[RuntimeAssuranceInvocationClaimRecord]:
            del now
            current = completed.get(invocation_id)
            if current is not None:
                return nullcontext(
                    replace(
                        current,
                        disposition=RuntimeAssuranceClaimDisposition.COMPLETED_REPLAY,
                    )
                )
            return nullcontext(
                RuntimeAssuranceInvocationClaimRecord(
                    tenant_id=context.tenant_id,
                    project_id=context.project_id,
                    run_id=context.run_id or "",
                    actor_id=context.actor_id,
                    execution_epoch=context.execution_epoch,
                    fencing_generation=context.fencing_generation,
                    authority_revision=context.authority_revision or "",
                    revision_set_id=revision_set_id,
                    invocation_id=invocation_id,
                    request_digest=request_digest,
                    claim_epoch=1,
                    state=RuntimeAssuranceInvocationState.IN_PROGRESS,
                    disposition=RuntimeAssuranceClaimDisposition.ACQUIRED,
                    result_ref=None,
                    result_digest=None,
                    claimed_at=NOW,
                    updated_at=NOW,
                )
            )

        def complete(
            context: SecurityContext,
            *,
            revision_set_id: str,
            invocation_id: str,
            request_digest: str,
            expected_claim_epoch: int,
            result_ref: str,
            result_digest: str,
            now: datetime | None = None,
        ) -> RuntimeAssuranceInvocationClaimRecord:
            del now
            record = RuntimeAssuranceInvocationClaimRecord(
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                run_id=context.run_id or "",
                actor_id=context.actor_id,
                execution_epoch=context.execution_epoch,
                fencing_generation=context.fencing_generation,
                authority_revision=context.authority_revision or "",
                revision_set_id=revision_set_id,
                invocation_id=invocation_id,
                request_digest=request_digest,
                claim_epoch=expected_claim_epoch,
                state=RuntimeAssuranceInvocationState.COMPLETED,
                disposition=RuntimeAssuranceClaimDisposition.COMPLETED,
                result_ref=result_ref,
                result_digest=result_digest,
                claimed_at=NOW,
                updated_at=NOW,
                completed_at=NOW,
            )
            completed[invocation_id] = record
            return record

        store.claim_runtime_assurance_invocation.side_effect = claim
        store.complete_runtime_assurance_invocation.side_effect = complete

        def bind_pending(
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
        ) -> PendingToolCallBindingRecord:
            timestamp = now or NOW
            return PendingToolCallBindingRecord(
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                run_id=context.run_id or "",
                actor_id=context.actor_id,
                invocation_id=invocation_id,
                call_id=call_id,
                attempt=attempt,
                execution_epoch=context.execution_epoch,
                fencing_generation=context.fencing_generation,
                authority_revision=context.authority_revision or "",
                revision_set_id=revision_set_id,
                execution_plan_hash=execution_plan_hash,
                environment_id=environment_id,
                tool_id=tool_id,
                authority_snapshot_id=authority_snapshot_id,
                state=PendingToolCallBindingState.PENDING,
                created_at=timestamp,
                updated_at=timestamp,
            )

        store.bind_pending_tool_call.side_effect = bind_pending

        def bind_authority(
            context: SecurityContext,
            *,
            revision_set_id: str,
            operation_invocation_id: str,
            environment_id: str,
            authority_snapshot_id: str,
            capabilities: tuple[str, ...],
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
        ) -> RuntimeAuthorityCapabilityReceiptRecord:
            return RuntimeAuthorityCapabilityReceiptRecord(
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                run_id=context.run_id or "",
                actor_id=context.actor_id,
                execution_epoch=context.execution_epoch,
                fencing_generation=context.fencing_generation,
                authority_revision=context.authority_revision or "",
                revision_set_id=revision_set_id,
                operation_invocation_id=operation_invocation_id,
                environment_id=environment_id,
                authority_snapshot_id=authority_snapshot_id,
                capabilities=tuple(capabilities),
                delegation_allowed=delegation_allowed,
                authority_digest=authority_digest,
                origin_skill_id=origin_skill_id,
                origin_skill_name=origin_skill_name,
                origin_owner_kernel=origin_owner_kernel,
                origin_execution_id=origin_execution_id,
                origin_step_id=origin_step_id,
                extension_skill=extension_skill,
                origin_receipt_ref=origin_receipt_ref,
                origin_receipt_state=origin_receipt_state,
                origin_receipt_digest=origin_receipt_digest,
                origin_signing_key_id=origin_signing_key_id,
                origin_signature_algorithm=origin_signature_algorithm,
                origin_signature=origin_signature,
                host_envelope=host_envelope,
            )

        def bind_reservation(
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
            child_authority: tuple[str, ...],
            child_tools: tuple[str, ...],
            max_output_tokens: int,
            max_cost_budget: str,
            wall_clock_deadline: datetime,
            tool_plan_hash: str,
            authority_envelope_digest: str,
            host_envelope: HostSignedEnvelope,
            now: datetime | None = None,
        ) -> SubagentBudgetReservationBindingRecord:
            timestamp = now or NOW
            return SubagentBudgetReservationBindingRecord(
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                run_id=context.run_id or "",
                actor_id=context.actor_id,
                execution_epoch=context.execution_epoch,
                fencing_generation=context.fencing_generation,
                authority_revision=context.authority_revision or "",
                revision_set_id=revision_set_id,
                reservation_id=reservation_id,
                operation_invocation_id=operation_invocation_id,
                parent_execution_id=parent_execution_id,
                environment_id=environment_id,
                authority_snapshot_id=authority_snapshot_id,
                provider=provider,
                model=model,
                reasoning_effort=reasoning_effort,
                child_authority=tuple(child_authority),
                child_tools=tuple(child_tools),
                max_output_tokens=max_output_tokens,
                max_cost_budget=max_cost_budget,
                wall_clock_deadline=wall_clock_deadline,
                tool_plan_hash=tool_plan_hash,
                authority_envelope_digest=authority_envelope_digest,
                host_envelope=host_envelope,
                state=SubagentBudgetReservationState.RESERVED,
                created_at=timestamp,
                updated_at=timestamp,
            )

        store.bind_runtime_authority_capability_receipt.side_effect = bind_authority
        store.bind_subagent_budget_reservation.side_effect = bind_reservation
        return store

    @staticmethod
    def _typed_record(record_type: type[Any], **values: Any) -> MagicMock:
        record = MagicMock(spec=record_type)
        for name, value in values.items():
            setattr(record, name, value)
        return record

    def _snapshot_mock(self, **values: Any) -> MagicMock:
        snapshot = self._typed_record(RuntimeAssuranceScopeSnapshot)
        for name in (
            "pending_tool_calls",
            "tool_results",
            "step_plans",
            "runtime_authority_receipts",
            "capability_leases",
            "executor_generations",
            "environment_attachments",
            "executor_replacement_effects",
            "workspace_leases",
            "event_registrations",
            "durable_events",
            "typed_ingress",
            "subagent_budget_reservations",
            "subagent_execution_specs",
        ):
            setattr(snapshot, name, ())
        for name, value in values.items():
            setattr(snapshot, name, value)
        return snapshot

    def _committer(self, store: MagicMock) -> RuntimeAssuranceDurableCommitter:
        return RuntimeAssuranceDurableCommitter(
            store,
            EvidenceBackedDeltaStore(self.evidence, durable=True),
        )

    def _durable_call(
        self,
        committer: RuntimeAssuranceDurableCommitter,
        *,
        skill: str,
        payload: dict[str, Any],
        output: dict[str, Any],
        authority: RuntimeAssuranceAuthority | None = None,
    ) -> Any:
        invocation = replace(
            self.invocation,
            extension_skill=skill,
            payload=payload,
        )
        selected_authority = authority or self.authority
        if skill == "elmos-subagent-model-execution-spec":
            committer.prepare_operation_authority(
                self.context,
                selected_authority,
                invocation,
            )
        return committer(
            self.context,
            selected_authority,
            DELTA_SKILL_REGISTRY[skill],
            invocation,
            output,
        )

    def _operation_authority(
        self,
        invocation_id: str,
        *,
        extension_skill: str = "elmos-invocation-scoped-capability-lease",
        environment_id: str = "env-001",
        revision_set_id: str | None = None,
        call_id: str | None = None,
        plan_hash: str | None = None,
    ) -> RuntimeAssuranceAuthority:
        bindings = {
            **dict(self.authority.security_bindings),
            "invocationId": invocation_id,
            "environmentId": environment_id,
        }
        origin = self._origin(
            invocation_id,
            extension_skill,
            environment_id=environment_id,
            revision_set_id=revision_set_id,
        )
        if call_id is None:
            return replace(
                self.authority,
                security_bindings=bindings,
                originating_base_skill=origin,
            )
        if plan_hash is None:
            raise AssertionError("plan_hash is required for a pending call")
        return replace(
            self.authority,
            security_bindings=bindings,
            originating_base_skill=origin,
            originating_plan_hashes=frozenset({plan_hash}),
            pending_calls=frozenset({call_id}),
            pending_call_bindings=(
                PendingToolCallBinding(
                    call_id,
                    1,
                    invocation_id,
                    plan_hash,
                    "env-001",
                    "read_file",
                    self.authority_revision,
                ),
            ),
        )

    def _production_control(
        self, *, omit: str | None = None
    ) -> RuntimeAssuranceControlPlane:
        provider = _ProductionAuthorityProvider()
        if omit == "authority trust":
            provider.trusted_for_production = False
        elif omit == "authority durability":
            provider.durable = False
        elif omit == "authority deadline":
            provider.deadline_enforced = False
        elif omit == "base Skill origin receipt verifier":
            provider.base_origin_receipt_verified = False
        elif omit == "Host envelope signature verifier":
            provider.host_envelope_signatures_verified = False
        elif omit == "durable Host envelope issuer":
            provider.host_envelope_issuer_durable = False
        trust_policy = SkillTrustDomainPolicy(
            {"REPOSITORY": self.trusted_skill_root},
            publishers={"REPOSITORY": {"elmos"}},
        )
        return RuntimeAssuranceControlPlane(
            self._store(),
            self.evidence,
            authority_provider=provider,
            permission_profiles=(
                None
                if omit == "permission profiles"
                else {
                    ("codex", "1.0.0"): {
                        "sandbox-locked": PermissionProfile(
                            ("/workspace",),
                            "deny",
                            False,
                            working_directory="/workspace",
                        )
                    }
                }
            ),
            authorized_producers=(
                None
                if omit == "typed-ingress producer policy"
                else {(self.context.tenant_id, self.context.project_id): {"producer-1"}}
            ),
            allowed_subagent_models=(
                () if omit == "subagent model allowlist" else (("openai", "gpt-5"),)
            ),
            trusted_skill_root=self.trusted_skill_root,
            skill_trust_policy=(
                None if omit == "trusted Skill trust-domain policy" else trust_policy
            ),
            skill_signature_verifier=(
                None
                if omit == "Skill signature verifier"
                else lambda content, signature: bool(content and signature)
            ),
            host_security_signer=(
                None
                if omit == "restart-safe Host security-context signer"
                else HostSecurityContextSigner(
                    b"production-readiness-test-key-32-bytes",
                    key_id="test-key",
                    issuer="test-host",
                )
            ),
            privileged_path_policy=(
                None
                if omit == "trusted privileged path policy"
                else PrivilegedPathPolicy()
            ),
            managed_worktree_registry=(
                None
                if omit == "live managed-worktree registry"
                else ManagedWorktreeRegistry()
            ),
            interceptors=(
                None
                if omit == "tool-result interceptor registry"
                else {"preserve": ("1.0.0", _TrustedInterceptor())}
            ),
        )

    def _plan_records(
        self,
        *,
        plan_id: str = "plan-1",
        tools: tuple[str, ...] = ("read_file",),
    ) -> tuple[
        StepExecutionPlanRecord,
        StepExecutionPlanRecord,
        StepExecutionPlanRecord,
    ]:
        tool_contracts = {
            tool: (
                self.tool_contract
                if tool == "read_file"
                else {"toolId": tool, "inputSchema": {"type": "object"}}
            )
            for tool in tools
        }
        handler_digests = {
            tool: (
                self.handler_digest
                if tool == "read_file"
                else digest_bytes(tool.encode("utf-8"), domain="handler")
            )
            for tool in tools
        }
        plan_hash = ExecutionPlan(
            ModelSnapshot("openai", "gpt-5", "2026-08-30"),
            tools,
            "env-snap-1",
            self.authority_revision,
            "NATIVE",
            capabilities=("fs.read",),
            plan_id=plan_id,
            tool_contracts=tool_contracts,
            handler_digests=handler_digests,
        ).plan_hash
        candidate = StepExecutionPlanRecord(
            tenant_id=self.context.tenant_id,
            project_id=self.context.project_id,
            run_id=self.context.run_id or "",
            actor_id=self.context.actor_id,
            execution_epoch=self.context.execution_epoch,
            fencing_generation=self.context.fencing_generation,
            authority_revision=self.authority_revision,
            revision_set_id=self.revision_set_id,
            plan_id=plan_id,
            step_id="step-001",
            plan_hash=plan_hash,
            model_snapshot={
                "provider": "openai",
                "model": "gpt-5",
                "revision": "2026-08-30",
            },
            tool_plan={"tools": list(tools)},
            tool_contracts=tool_contracts,
            handler_digests=handler_digests,
            capabilities=("fs.read",),
            tool_mode="NATIVE",
            environment_snapshot_id="env-snap-1",
            authority_snapshot_id=self.authority_revision,
            state=StepPlanState.CANDIDATE,
            created_at=NOW,
            updated_at=NOW,
        )
        finalized = replace(
            candidate,
            state=StepPlanState.FINALIZED,
            finalized_at=NOW,
        )
        active = replace(
            finalized,
            state=StepPlanState.ACTIVE,
            activated_at=NOW,
        )
        return candidate, finalized, active

    def test_evidence_adapter_survives_reconstruction_and_is_tenant_scoped(
        self,
    ) -> None:
        first = EvidenceBackedDeltaStore(self.evidence, durable=True)
        value = {
            "kind": "DELTA_RUNTIME_RESULT",
            "content": {"decision": "COMMITTED"},
        }
        reference = first.put(self.context, value)
        second = EvidenceBackedDeltaStore(self.evidence, durable=True)

        self.assertEqual(second.get(self.context, reference), value)
        self.assertEqual(second.put(self.context, value), reference)
        with self.assertRaises(NotFoundError):
            second.get(self.other_context, reference)

    def test_host_signed_envelope_binds_payload_and_verification_metadata(
        self,
    ) -> None:
        payload = {"operationInvocationId": "inv-1", "capabilities": ["fs.read"]}
        envelope = HostSignedEnvelope.local_self_attested(
            kind="RUNTIME_AUTHORITY_CAPABILITY",
            payload=payload,
            now=NOW,
        )

        envelope.verify_payload(
            kind="RUNTIME_AUTHORITY_CAPABILITY",
            payload=payload,
        )
        with self.assertRaisesRegex(ValidationError, "exact payload"):
            envelope.verify_payload(
                kind="RUNTIME_AUTHORITY_CAPABILITY",
                payload={**payload, "capabilities": ["fs.write"]},
            )
        with self.assertRaisesRegex(ValidationError, "verification evidence"):
            replace(envelope, signature=envelope.signature + "-tampered")

    def test_completed_invocation_replays_without_handler_or_state_transition(
        self,
    ) -> None:
        store = self._store()
        candidate, finalized, active = self._plan_records()
        store.load_runtime_assurance_scope.side_effect = [
            self._empty_snapshot(),
            self._empty_snapshot(),
        ]
        store.record_step_plan.return_value = candidate
        store.transition_step_plan.return_value = finalized
        store.activate_step_plan.return_value = active
        provider = RegisteredRuntimeAssuranceAuthorityProvider()
        provider.register(self.context, self.invocation, self.authority)

        first = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
        )
        first_result = first.execute_internal(self.context, self.invocation)
        second = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
        )
        second_result = second.execute_internal(self.context, self.invocation)

        self.assertEqual(first_result.status, ResultStatus.COMMITTED)
        self.assertEqual(second_result.status, ResultStatus.COMMITTED)
        self.assertEqual(first_result.evidence_refs, second_result.evidence_refs)
        self.assertEqual(store.record_step_plan.call_count, 1)
        self.assertEqual(store.transition_step_plan.call_count, 1)
        self.assertEqual(store.activate_step_plan.call_count, 1)

    def test_active_plan_restores_in_a_new_process_without_state_regression(
        self,
    ) -> None:
        store = self._store()
        _, _, active = self._plan_records()
        store.load_runtime_assurance_scope.return_value = replace(
            self._empty_snapshot(), step_plans=(active,)
        )
        store.record_step_plan.return_value = active
        invocation = replace(self.invocation, invocation_id="inv-67890")
        authority = self._operation_authority(
            invocation.invocation_id,
            extension_skill="elmos-step-finalized-execution-plan",
        )
        provider = RegisteredRuntimeAssuranceAuthorityProvider()
        provider.register(self.context, invocation, authority)
        restarted = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
        )

        result = restarted.execute_internal(self.context, invocation)

        self.assertEqual(result.status, ResultStatus.COMMITTED)
        store.record_step_plan.assert_called_once()
        store.transition_step_plan.assert_not_called()
        store.activate_step_plan.assert_not_called()

    def test_new_plan_retires_old_active_plan_before_activation(self) -> None:
        store = self._store()
        _, _, old_active = self._plan_records()
        new_candidate, new_finalized, new_active = self._plan_records(
            plan_id="plan-2",
            tools=(),
        )
        store.load_runtime_assurance_scope.return_value = replace(
            self._empty_snapshot(), step_plans=(old_active,)
        )
        store.record_step_plan.return_value = new_candidate
        store.transition_step_plan.return_value = new_finalized
        store.activate_step_plan.return_value = new_active
        invocation = replace(
            self.invocation,
            invocation_id="inv-plan-2",
            payload={
                **dict(self.invocation.payload),
                "planId": "plan-2",
                "tools": [],
                "toolContracts": {},
                "handlerDigests": {},
            },
        )
        authority = self._operation_authority(
            invocation.invocation_id,
            extension_skill="elmos-step-finalized-execution-plan",
        )
        provider = RegisteredRuntimeAssuranceAuthorityProvider()
        provider.register(self.context, invocation, authority)
        control = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
        )

        result = control.execute_internal(self.context, invocation)

        self.assertEqual(result.status, ResultStatus.COMMITTED)
        store.transition_step_plan.assert_called_once()
        store.activate_step_plan.assert_called_once()
        self.assertEqual(store.activate_step_plan.call_args.kwargs["plan_id"], "plan-2")

    def test_recovery_required_claim_never_executes_the_handler(self) -> None:
        store = self._store()

        def recovery_claim(
            context: SecurityContext,
            *,
            revision_set_id: str,
            invocation_id: str,
            request_digest: str,
            now: datetime | None = None,
        ) -> ContextManager[RuntimeAssuranceInvocationClaimRecord]:
            del now
            return nullcontext(
                RuntimeAssuranceInvocationClaimRecord(
                    tenant_id=context.tenant_id,
                    project_id=context.project_id,
                    run_id=context.run_id or "",
                    actor_id=context.actor_id,
                    execution_epoch=context.execution_epoch,
                    fencing_generation=context.fencing_generation,
                    authority_revision=context.authority_revision or "",
                    revision_set_id=revision_set_id,
                    invocation_id=invocation_id,
                    request_digest=request_digest,
                    claim_epoch=1,
                    state=RuntimeAssuranceInvocationState.RECOVERY_REQUIRED,
                    disposition=RuntimeAssuranceClaimDisposition.RECOVERY_REQUIRED,
                    result_ref=None,
                    result_digest=None,
                    claimed_at=NOW,
                    updated_at=NOW,
                )
            )

        store.claim_runtime_assurance_invocation.side_effect = recovery_claim
        provider = RegisteredRuntimeAssuranceAuthorityProvider()
        provider.register(self.context, self.invocation, self.authority)
        control = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
        )

        with self.assertRaisesRegex(ConflictError, "explicit recovery"):
            control.execute_internal(self.context, self.invocation)
        store.load_runtime_assurance_scope.assert_not_called()
        store.record_step_plan.assert_not_called()

    def test_explicit_recovery_reconciles_existing_result_without_handler(self) -> None:
        store = self._store()
        provider = RegisteredRuntimeAssuranceAuthorityProvider()
        provider.register(self.context, self.invocation, self.authority)
        control = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
        )
        recovered = control._preflight_unknown(
            self.context,
            self.invocation,
            message="verified result captured before worker crash",
        )

        def reconcile(
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
        ) -> RuntimeAssuranceInvocationClaimRecord:
            del now
            return RuntimeAssuranceInvocationClaimRecord(
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                run_id=context.run_id or "",
                actor_id=context.actor_id,
                execution_epoch=context.execution_epoch,
                fencing_generation=context.fencing_generation,
                authority_revision=context.authority_revision or "",
                revision_set_id=revision_set_id,
                invocation_id=invocation_id,
                request_digest=request_digest,
                claim_epoch=expected_claim_epoch,
                state=RuntimeAssuranceInvocationState.COMPLETED,
                disposition=RuntimeAssuranceClaimDisposition.COMPLETED,
                result_ref=result_ref,
                result_digest=result_digest,
                claimed_at=NOW,
                updated_at=NOW,
                completed_at=NOW,
                recovery_evidence_ref=recovery_evidence_ref,
            )

        store.reconcile_runtime_assurance_invocation.side_effect = reconcile
        receipt = control.reconcile_invocation(
            self.context,
            self.invocation,
            expected_claim_epoch=1,
            recovered_result_ref=recovered.evidence_refs[0],
            recovery_evidence={
                "workerExit": "SIGKILL",
                "resultCasVerified": True,
            },
        )

        self.assertEqual(receipt.state, RuntimeAssuranceInvocationState.COMPLETED)
        self.assertEqual(receipt.result_ref, recovered.evidence_refs[0])
        self.assertIsNotNone(receipt.recovery_evidence_ref)
        store.claim_runtime_assurance_invocation.assert_not_called()
        store.load_runtime_assurance_scope.assert_not_called()
        store.record_step_plan.assert_not_called()

    def test_explicit_recovery_rejects_result_from_another_invocation(self) -> None:
        store = self._store()
        provider = RegisteredRuntimeAssuranceAuthorityProvider()
        provider.register(self.context, self.invocation, self.authority)
        control = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
        )
        wrong_invocation = replace(self.invocation, invocation_id="inv-other")
        wrong_result = control._preflight_unknown(
            self.context,
            wrong_invocation,
            message="wrong invocation result",
        )

        with self.assertRaisesRegex(IntegrityError, "exact invocation scope"):
            control.reconcile_invocation(
                self.context,
                self.invocation,
                expected_claim_epoch=1,
                recovered_result_ref=wrong_result.evidence_refs[0],
                recovery_evidence={"workerExit": "SIGKILL"},
            )
        store.reconcile_runtime_assurance_invocation.assert_not_called()

    def test_precommit_recovery_aborts_without_reinvoking_interceptors(self) -> None:
        store = self._store()
        provider = RegisteredRuntimeAssuranceAuthorityProvider()
        provider.register(self.context, self.invocation, self.authority)
        control = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
        )
        call_id = "call-1"
        raw = ToolResult(
            identity=CallIdentity(
                self.invocation.invocation_id,
                call_id,
                self._plan_records()[2].plan_hash,
                "env-001",
                self.authority_revision,
            ),
            ok=True,
            content={"value": 7},
        )
        artifact_binding = {
            "apiVersion": "elmos.ai/v3delta1",
            "tenantId": self.context.tenant_id,
            "projectId": self.context.project_id,
            "runId": self.context.run_id,
            "invocationId": self.invocation.invocation_id,
            "callId": call_id,
            "commitKey": _tool_result_commit_key(
                self.invocation.invocation_id,
                call_id,
                1,
                self.invocation.execution_epoch,
            ),
        }
        raw_ref = control.evidence.put(
            self.context,
            artifact_binding | {"kind": "RAW_TOOL_RESULT", "content": raw.to_wire()},
        )
        partial = ToolResultCommitRecord(
            tenant_id=self.context.tenant_id,
            project_id=self.context.project_id,
            run_id=self.context.run_id or "",
            actor_id=self.context.actor_id,
            invocation_id=self.invocation.invocation_id,
            call_id=call_id,
            attempt=1,
            execution_epoch=self.context.execution_epoch,
            fencing_generation=self.context.fencing_generation,
            authority_revision=self.authority_revision,
            revision_set_id=self.revision_set_id,
            execution_plan_hash=self._plan_records()[2].plan_hash,
            environment_id="env-001",
            authority_snapshot_id=self.authority_revision,
            raw_result_ref=raw_ref,
            effective_result_ref=raw_ref,
            interceptor_chain=(),
            mutation_provenance_ref=None,
            failure_kind=None,
            failure_reason=None,
            state=ToolResultCommitState.INTERCEPTING,
            created_at=NOW,
            updated_at=NOW,
        )
        store.load_runtime_assurance_scope.return_value = replace(
            self._empty_snapshot(), tool_results=(partial,)
        )

        def abort(
            context: SecurityContext,
            **kwargs: object,
        ) -> ToolResultCommitRecord:
            del context
            failure_kind = kwargs["failure_kind"]
            if not isinstance(failure_kind, ToolResultFailureKind):
                raise TypeError("test store received an invalid failure kind")
            return replace(
                partial,
                effective_result_ref=str(kwargs["effective_result_ref"]),
                mutation_provenance_ref=str(kwargs["mutation_provenance_ref"]),
                recovery_evidence_ref=str(kwargs["recovery_evidence_ref"]),
                failure_kind=failure_kind,
                failure_reason=str(kwargs["failure_reason"]),
                state=ToolResultCommitState.ABORTED,
                aborted_at=NOW,
            )

        store.reconcile_tool_result_abort.side_effect = abort
        result = control.reconcile_interrupted_tool_result(
            self.context,
            revision_set_id=self.revision_set_id,
            invocation_id=self.invocation.invocation_id,
            call_id=call_id,
            attempt=1,
            expected_claim_epoch=1,
            recovery_evidence={"workerExit": "SIGKILL", "rawCasVerified": True},
        )

        self.assertEqual(result.state, ToolResultCommitState.ABORTED)
        self.assertEqual(result.failure_kind, ToolResultFailureKind.CANCELLED)
        provenance = control.runtime.read_evidence(
            self.context, result.mutation_provenance_ref or ""
        )
        self.assertEqual(provenance["kind"], "INTERCEPTOR_DECISIONS")
        self.assertEqual(provenance["content"], ())
        store.reconcile_tool_result_abort.assert_called_once()
        self.assertEqual(
            store.reconcile_tool_result_abort.call_args.kwargs["expected_claim_epoch"],
            1,
        )
        store.abort_tool_result.assert_not_called()

    def test_tool_result_begin_binds_host_attempt_and_call_identity(self) -> None:
        store = self._store()
        committer = self._committer(store)
        plan_hash = self._plan_records()[2].plan_hash
        identity = CallIdentity(
            self.invocation.invocation_id,
            "call-1",
            plan_hash,
            "env-001",
            self.authority_revision,
        )
        authority = replace(
            self.authority,
            originating_plan_hashes=frozenset({plan_hash}),
            pending_calls=frozenset({"call-1"}),
            pending_call_bindings=(
                PendingToolCallBinding(
                    "call-1",
                    1,
                    self.invocation.invocation_id,
                    plan_hash,
                    "env-001",
                    "read_file",
                    self.authority_revision,
                ),
            ),
        )
        captured = self._typed_record(
            ToolResultCommitRecord,
            state=ToolResultCommitState.RAW_CAPTURED,
        )
        intercepting = self._typed_record(
            ToolResultCommitRecord,
            state=ToolResultCommitState.INTERCEPTING,
        )
        store.begin_tool_result.return_value = captured
        store.mark_tool_result_intercepting.return_value = intercepting

        result = committer.begin_tool_result(
            self.context,
            authority,
            self.invocation,
            identity,
            1,
            "cas:raw-result",
        )

        self.assertIs(result, intercepting)
        store.begin_tool_result.assert_called_once_with(
            self.context,
            revision_set_id=self.revision_set_id,
            invocation_id=self.invocation.invocation_id,
            call_id="call-1",
            attempt=1,
            execution_plan_hash=plan_hash,
            environment_id="env-001",
            authority_snapshot_id=self.authority_revision,
            raw_result_ref="cas:raw-result",
        )
        store.mark_tool_result_intercepting.assert_called_once_with(
            self.context,
            revision_set_id=self.revision_set_id,
            invocation_id=self.invocation.invocation_id,
            call_id="call-1",
            attempt=1,
            execution_epoch=1,
            expected_state=ToolResultCommitState.RAW_CAPTURED,
        )

        store.reset_mock()
        with self.assertRaisesRegex(IntegrityError, "attempt diverged"):
            committer.begin_tool_result(
                self.context,
                authority,
                self.invocation,
                identity,
                2,
                "cas:raw-result",
            )
        store.begin_tool_result.assert_not_called()

        drifted = replace(identity, environment_id="env-other")
        with self.assertRaisesRegex(IntegrityError, "binding diverged"):
            committer.begin_tool_result(
                self.context,
                authority,
                self.invocation,
                drifted,
                1,
                "cas:raw-result",
            )
        store.begin_tool_result.assert_not_called()

    def test_capability_resource_identity_survives_distinct_operation_invocations(
        self,
    ) -> None:
        store = self._store()
        provider = RegisteredRuntimeAssuranceAuthorityProvider()
        control = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
        )
        issued_at = datetime.now(UTC)
        expires_at = issued_at + timedelta(minutes=5)
        active_lease = CapabilityLeaseRecord(
            tenant_id=self.context.tenant_id,
            project_id=self.context.project_id,
            run_id=self.context.run_id or "",
            actor_id=self.context.actor_id,
            lease_id="lease-1",
            invocation_id="inv-A",
            environment_id="env-001",
            authority_snapshot_id=self.authority_revision,
            execution_epoch=1,
            fencing_generation=1,
            authority_revision=self.authority_revision,
            revision_set_id=self.revision_set_id,
            capabilities=("fs.read",),
            delegation_allowed=False,
            state=CapabilityLeaseState.ACTIVE,
            issued_at=issued_at,
            expires_at=expires_at,
            revoked_at=None,
            revocation_reason=None,
            updated_at=issued_at,
        )
        issue = replace(
            self.invocation,
            invocation_id="inv-A",
            extension_skill="elmos-invocation-scoped-capability-lease",
            payload={
                "action": "issue",
                "leaseId": "lease-1",
                "environmentId": "env-001",
                "authoritySnapshotId": self.authority_revision,
                "capabilities": ["fs.read"],
                "delegationAllowed": False,
                "expiresAt": expires_at.isoformat().replace("+00:00", "Z"),
            },
        )
        issue_authority = self._operation_authority("inv-A")
        provider.register(self.context, issue, issue_authority)
        store.load_runtime_assurance_scope.return_value = self._empty_snapshot()

        issued = control.execute_internal(self.context, issue)

        self.assertEqual(issued.status, ResultStatus.COMMITTED)
        self.assertEqual(
            store.issue_capability_lease.call_args.kwargs["invocation_id"], "inv-A"
        )

        use = replace(
            issue,
            invocation_id="inv-B",
            payload={"action": "use", "leaseId": "lease-1", "capability": "fs.read"},
        )
        use_authority = self._operation_authority("inv-B")
        provider.register(self.context, use, use_authority)
        store.load_runtime_assurance_scope.return_value = replace(
            self._empty_snapshot(), capability_leases=(active_lease,)
        )

        used = control.execute_internal(self.context, use)

        self.assertEqual(used.status, ResultStatus.COMMITTED)
        self.assertEqual(use_authority.security_bindings["invocationId"], "inv-B")
        store.record_capability_lease_use.assert_called_once_with(
            self.context,
            revision_set_id=self.revision_set_id,
            lease_id="lease-1",
            invocation_id="inv-A",
            operation_invocation_id="inv-B",
            expected_environment_id="env-001",
            expected_authority_snapshot_id=self.authority_revision,
            authorized_capabilities=("fs.read",),
            capability="fs.read",
        )
        store.audit_capability_use_denial.assert_not_called()

        revoke = replace(
            issue,
            invocation_id="inv-C",
            payload={
                "action": "revoke",
                "leaseId": "lease-1",
                "reason": CapabilityRevocationReason.CANCELLED.value,
            },
        )
        revoke_authority = self._operation_authority("inv-C")
        provider.register(self.context, revoke, revoke_authority)
        store.load_runtime_assurance_scope.return_value = replace(
            self._empty_snapshot(), capability_leases=(active_lease,)
        )

        revoked = control.execute_internal(self.context, revoke)

        self.assertEqual(revoked.status, ResultStatus.COMMITTED)
        self.assertEqual(revoke_authority.security_bindings["invocationId"], "inv-C")
        store.revoke_capability_lease.assert_called_once_with(
            self.context,
            revision_set_id=self.revision_set_id,
            lease_id="lease-1",
            subject_invocation_id="inv-A",
            operation_invocation_id="inv-C",
            expected_environment_id="env-001",
            expected_authority_snapshot_id=self.authority_revision,
            authorized_capabilities=("fs.read",),
            reason=CapabilityRevocationReason.CANCELLED,
        )

    def test_capability_use_denials_are_audited_without_recording_success(
        self,
    ) -> None:
        store = self._store()
        provider = RegisteredRuntimeAssuranceAuthorityProvider()
        control = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
        )
        issued_at = datetime.now(UTC)
        active_lease = CapabilityLeaseRecord(
            tenant_id=self.context.tenant_id,
            project_id=self.context.project_id,
            run_id=self.context.run_id or "",
            actor_id=self.context.actor_id,
            lease_id="lease-1",
            invocation_id="inv-A",
            environment_id="env-001",
            authority_snapshot_id=self.authority_revision,
            execution_epoch=1,
            fencing_generation=1,
            authority_revision=self.authority_revision,
            revision_set_id=self.revision_set_id,
            capabilities=("fs.read",),
            delegation_allowed=False,
            state=CapabilityLeaseState.ACTIVE,
            issued_at=issued_at,
            expires_at=issued_at + timedelta(minutes=5),
            revoked_at=None,
            revocation_reason=None,
            updated_at=issued_at,
        )
        snapshot = replace(self._empty_snapshot(), capability_leases=(active_lease,))
        store.load_runtime_assurance_scope.return_value = snapshot

        environment_mismatch = replace(
            self.invocation,
            invocation_id="inv-B",
            extension_skill="elmos-invocation-scoped-capability-lease",
            payload={
                "action": "use",
                "leaseId": "lease-1",
                "capability": "fs.read",
            },
        )
        environment_authority = replace(
            self._operation_authority(
                "inv-B",
                environment_id="env-B",
            ),
            environment_ids=frozenset({"env-B"}),
        )
        provider.register(
            self.context,
            environment_mismatch,
            environment_authority,
        )

        denied_environment = control.execute_internal(
            self.context,
            environment_mismatch,
        )

        self.assertEqual(denied_environment.status, ResultStatus.DENIED)
        store.bind_runtime_authority_capability_receipt.assert_called_once()
        self.assertEqual(
            store.bind_runtime_authority_capability_receipt.call_args.kwargs[
                "operation_invocation_id"
            ],
            "inv-B",
        )
        store.audit_capability_use_denial.assert_called_once_with(
            self.context,
            revision_set_id=self.revision_set_id,
            lease_id="lease-1",
            subject_invocation_id="inv-A",
            operation_invocation_id="inv-B",
            capability="fs.read",
            reason=CapabilityUseDenialReason.ENVIRONMENT_MISMATCH,
        )
        store.record_capability_lease_use.assert_not_called()

        store.reset_mock()
        store.load_runtime_assurance_scope.return_value = snapshot
        missing_authority_capability = replace(
            environment_mismatch,
            invocation_id="inv-C",
        )
        capability_authority = replace(
            self._operation_authority("inv-C"),
            capabilities=frozenset(),
        )
        provider.register(
            self.context,
            missing_authority_capability,
            capability_authority,
        )

        denied_capability = control.execute_internal(
            self.context,
            missing_authority_capability,
        )

        self.assertEqual(denied_capability.status, ResultStatus.DENIED)
        store.bind_runtime_authority_capability_receipt.assert_called_once()
        self.assertEqual(
            store.bind_runtime_authority_capability_receipt.call_args.kwargs[
                "operation_invocation_id"
            ],
            "inv-C",
        )
        store.audit_capability_use_denial.assert_called_once_with(
            self.context,
            revision_set_id=self.revision_set_id,
            lease_id="lease-1",
            subject_invocation_id="inv-A",
            operation_invocation_id="inv-C",
            capability="fs.read",
            reason=CapabilityUseDenialReason.AUTHORITY_CAPABILITY_MISMATCH,
        )
        store.record_capability_lease_use.assert_not_called()

    def test_capability_expiry_crossing_handler_boundary_is_expired_and_audited(
        self,
    ) -> None:
        store = self._store()
        provider = RegisteredRuntimeAssuranceAuthorityProvider()
        started = datetime.now(UTC)
        crossed = started + timedelta(seconds=3)
        timeline = iter((started, started, started, started, started, crossed, crossed))
        control = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
            clock=lambda: next(timeline, crossed),
        )
        lease = CapabilityLeaseRecord(
            tenant_id=self.context.tenant_id,
            project_id=self.context.project_id,
            run_id=self.context.run_id or "",
            actor_id=self.context.actor_id,
            lease_id="lease-expiry-race",
            invocation_id="inv-A",
            environment_id="env-001",
            authority_snapshot_id=self.authority_revision,
            execution_epoch=1,
            fencing_generation=1,
            authority_revision=self.authority_revision,
            revision_set_id=self.revision_set_id,
            capabilities=("fs.write",),
            delegation_allowed=False,
            state=CapabilityLeaseState.ACTIVE,
            issued_at=started - timedelta(seconds=1),
            expires_at=started + timedelta(seconds=2),
            revoked_at=None,
            revocation_reason=None,
            updated_at=started,
        )
        invocation = replace(
            self.invocation,
            invocation_id="inv-expiry-race",
            extension_skill="elmos-invocation-scoped-capability-lease",
            payload={
                "action": "use",
                "leaseId": lease.lease_id,
                "capability": "fs.read",
            },
        )
        authority = self._operation_authority(invocation.invocation_id)
        provider.register(self.context, invocation, authority)
        store.load_runtime_assurance_scope.return_value = replace(
            self._empty_snapshot(), capability_leases=(lease,)
        )

        result = control.execute_internal(self.context, invocation)

        self.assertEqual(result.status, ResultStatus.DENIED)
        store.bind_runtime_authority_capability_receipt.assert_called_once()
        store.expire_capability_lease.assert_called_once_with(
            self.context,
            revision_set_id=self.revision_set_id,
            lease_id=lease.lease_id,
            now=crossed,
        )
        store.audit_capability_use_denial.assert_called_once_with(
            self.context,
            revision_set_id=self.revision_set_id,
            lease_id=lease.lease_id,
            subject_invocation_id="inv-A",
            operation_invocation_id=invocation.invocation_id,
            capability="fs.read",
            reason=CapabilityUseDenialReason.LEASE_EXPIRED,
        )
        store.record_capability_lease_use.assert_not_called()

    def test_tool_result_resource_identity_survives_publish_and_abort_operations(
        self,
    ) -> None:
        store = self._store()
        provider = RegisteredRuntimeAssuranceAuthorityProvider()
        control = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
        )
        call_id = "call-resource-1"
        plan_hash = self._plan_records()[2].plan_hash
        commit = replace(
            self.invocation,
            invocation_id="inv-A",
            extension_skill="elmos-tool-result-interception-commit",
            payload={
                "action": "commit",
                "attempt": 1,
                "rawResult": {
                    "identity": {
                        "invocationId": "inv-A",
                        "callId": call_id,
                        "executionPlanHash": plan_hash,
                        "environmentId": "env-001",
                        "authoritySnapshotId": self.authority_revision,
                    },
                    "ok": True,
                    "content": {"value": 7},
                },
                "interceptorIds": [],
            },
        )
        commit_authority = self._operation_authority(
            "inv-A",
            extension_skill="elmos-tool-result-interception-commit",
            call_id=call_id,
            plan_hash=plan_hash,
        )
        provider.register(self.context, commit, commit_authority)
        store.load_runtime_assurance_scope.return_value = self._empty_snapshot()
        store.begin_tool_result.return_value = self._typed_record(
            ToolResultCommitRecord,
            state=ToolResultCommitState.RAW_CAPTURED,
        )
        store.mark_tool_result_intercepting.return_value = self._typed_record(
            ToolResultCommitRecord,
            state=ToolResultCommitState.INTERCEPTING,
        )

        committed_result = control.execute_internal(self.context, commit)

        self.assertEqual(committed_result.status, ResultStatus.COMMITTED)
        committed_call = store.commit_tool_result.call_args
        committed_record = ToolResultCommitRecord(
            tenant_id=self.context.tenant_id,
            project_id=self.context.project_id,
            run_id=self.context.run_id or "",
            actor_id=self.context.actor_id,
            invocation_id="inv-A",
            call_id=call_id,
            attempt=1,
            execution_epoch=1,
            fencing_generation=1,
            authority_revision=self.authority_revision,
            revision_set_id=self.revision_set_id,
            execution_plan_hash=plan_hash,
            environment_id="env-001",
            authority_snapshot_id=self.authority_revision,
            raw_result_ref=committed_call.kwargs["raw_result_ref"],
            effective_result_ref=committed_call.kwargs["effective_result_ref"],
            interceptor_chain=tuple(
                item
                for item in committed_call.kwargs["interceptor_chain"]
                if isinstance(item, InterceptorCommitRecord)
            ),
            mutation_provenance_ref=committed_call.kwargs["mutation_provenance_ref"],
            failure_kind=None,
            failure_reason=None,
            state=ToolResultCommitState.COMMITTED,
            created_at=NOW,
            updated_at=NOW,
            committed_at=NOW,
        )
        commit_key = _tool_result_commit_key(
            "inv-A",
            call_id,
            1,
            commit.execution_epoch,
        )

        for action, operation_id, target in (
            ("publish", "inv-B", ToolResultCommitState.PUBLISHED),
            ("abort", "inv-C", ToolResultCommitState.ABORTED),
        ):
            with self.subTest(action=action):
                payload: dict[str, Any] = {
                    "action": action,
                    "commitKey": commit_key,
                    "callId": call_id,
                    "attempt": 1,
                    "executionEpoch": 1,
                }
                if action == "abort":
                    payload |= {
                        "failureKind": ToolResultFailureKind.CANCELLED.value,
                        "failureReason": "host cancelled operation",
                    }
                operation = replace(
                    commit,
                    invocation_id=operation_id,
                    payload=payload,
                )
                operation_authority = self._operation_authority(
                    operation_id,
                    extension_skill="elmos-tool-result-interception-commit",
                    call_id=call_id,
                    plan_hash=plan_hash,
                )
                provider.register(self.context, operation, operation_authority)
                store.load_runtime_assurance_scope.return_value = replace(
                    self._empty_snapshot(), tool_results=(committed_record,)
                )
                store.transition_tool_result.reset_mock()

                lifecycle_result = control.execute_internal(self.context, operation)

                self.assertEqual(lifecycle_result.status, ResultStatus.COMMITTED)
                self.assertEqual(
                    operation_authority.security_bindings["invocationId"],
                    operation_id,
                )
                transition = store.transition_tool_result.call_args
                self.assertEqual(transition.kwargs["subject_invocation_id"], "inv-A")
                self.assertEqual(
                    transition.kwargs["operation_invocation_id"], operation_id
                )
                self.assertEqual(
                    transition.kwargs["expected_execution_plan_hash"], plan_hash
                )
                self.assertEqual(
                    transition.kwargs["expected_environment_id"], "env-001"
                )
                self.assertEqual(
                    transition.kwargs["expected_authority_snapshot_id"],
                    self.authority_revision,
                )
                self.assertEqual(transition.kwargs["target_state"], target)
                self.assertEqual(
                    transition.kwargs["execution_epoch"],
                    operation.execution_epoch,
                )

        drifted_plan = digest_bytes(b"drifted-plan", domain="execution-plan")
        drifted = replace(
            commit,
            invocation_id="inv-D",
            payload={
                "action": "publish",
                "commitKey": commit_key,
                "callId": call_id,
                "attempt": 1,
                "executionEpoch": 1,
            },
        )
        drifted_authority = self._operation_authority(
            "inv-D",
            extension_skill="elmos-tool-result-interception-commit",
            call_id=call_id,
            plan_hash=drifted_plan,
        )
        provider.register(self.context, drifted, drifted_authority)
        store.load_runtime_assurance_scope.return_value = replace(
            self._empty_snapshot(), tool_results=(committed_record,)
        )
        store.transition_tool_result.reset_mock()

        denied = control.execute_internal(self.context, drifted)

        self.assertEqual(denied.status, ResultStatus.DENIED)
        store.transition_tool_result.assert_not_called()

    def test_environment_attach_and_refresh_use_host_authority_snapshots(self) -> None:
        settings = {"filesystem": {"read": ["/workspace"]}}
        settings_digest = digest_object(
            settings,
            domain="delta-environment-settings-authority",
        )
        base_output = {
            "serverId": "server-1",
            "environmentId": "env-001",
            "snapshotId": self.authority.authority_result_snapshot_id,
            "authority": {"permissions": ["fs.read"]},
            "turnEnvironment": {
                "serverId": "server-1",
                "environmentId": "env-001",
                "settingsAuthority": settings,
                "settingsDigest": settings_digest,
            },
            "settingsDigest": settings_digest,
        }
        for action, generation in (("attach", 1), ("refresh", 2)):
            with self.subTest(action=action):
                store = self._store()
                committer = self._committer(store)
                previous = (
                    digest_bytes(b"environment-snapshot-v1", domain="snapshot")
                    if action == "refresh"
                    else None
                )
                record = self._typed_record(
                    EnvironmentAttachmentRecord,
                    server_id="server-1",
                    environment_id="env-001",
                    snapshot_id=self.authority.authority_result_snapshot_id,
                    generation=generation,
                    settings_digest=settings_digest,
                )
                if action == "attach":
                    store.record_environment_attachment.return_value = record
                else:
                    store.refresh_environment_attachment.return_value = record
                output = {
                    **base_output,
                    "action": action,
                    "generation": generation,
                    "previousSnapshotId": previous,
                }
                payload: dict[str, Any] = {"action": action}
                if action == "refresh":
                    payload["expectedGeneration"] = 1

                self.assertEqual(
                    self._durable_call(
                        committer,
                        skill="elmos-environment-attachment-authority",
                        payload=payload,
                        output=output,
                    ),
                    output,
                )

                mapped = (
                    store.record_environment_attachment
                    if action == "attach"
                    else store.refresh_environment_attachment
                )
                self.assertEqual(
                    mapped.call_args.kwargs["owner_authority_ref"],
                    self.authority.owner_authority.snapshot_id,
                )
                self.assertEqual(
                    mapped.call_args.kwargs["parent_authority_ref"],
                    self.authority.parent_authority_snapshot.snapshot_id,
                )
                self.assertEqual(
                    mapped.call_args.kwargs["settings_authority"], settings
                )
                if action == "refresh":
                    self.assertEqual(
                        mapped.call_args.kwargs["expected_snapshot_id"], previous
                    )

        settings_binding = EnvironmentSettingsBinding(
            "server-1",
            "env-001",
            settings,
            settings_digest,
        )
        authority = replace(
            self.authority,
            originating_base_skill=self._origin(
                self.invocation.invocation_id,
                "elmos-environment-attachment-authority",
            ),
            environment_settings_bindings=(settings_binding,),
        )
        runtime = DeltaSkillRuntime(
            authority_provider=lambda _context, _request: authority
        )
        attach_payload = {
            "action": "attach",
            "serverId": "server-1",
            "settingsAuthority": settings,
            "settingsDigest": settings_digest,
            "expectedSnapshotId": None,
            "expectedGeneration": 0,
            "ownerSnapshotId": authority.owner_authority.snapshot_id,
            "ownerPermissions": sorted(authority.owner_authority.permissions),
            "ownerId": authority.owner_authority.owner_id,
            "parentSnapshotId": authority.parent_authority_snapshot.snapshot_id,
            "parentPermissions": sorted(
                authority.parent_authority_snapshot.permissions
            ),
            "parentOwnerId": authority.parent_authority_snapshot.owner_id,
            "environmentId": "env-001",
            "permissionProfileVersion": "profile-v1",
            "ownerEffectivePolicyHash": (
                authority.owner_authority.effective_policy_hash
            ),
            "parentEffectivePolicyHash": (
                authority.parent_authority_snapshot.effective_policy_hash
            ),
            "policyPermissions": sorted(authority.policy_permissions),
            "snapshotId": authority.authority_result_snapshot_id,
        }
        valid = replace(
            self.invocation,
            extension_skill="elmos-environment-attachment-authority",
            payload=attach_payload,
        )
        self.assertEqual(
            runtime.execute(
                valid,
                context=self.context,
                trusted_authority=authority,
            ).status,
            ResultStatus.COMMITTED,
        )
        spoofed = replace(
            valid,
            payload={
                **attach_payload,
                "settingsAuthority": {"filesystem": {"read": ["/"]}},
            },
        )
        self.assertEqual(
            runtime.execute(
                spoofed,
                context=self.context,
                trusted_authority=authority,
            ).status,
            ResultStatus.DENIED,
        )

    def test_executor_replace_requires_exact_effects_and_host_reconciliation(
        self,
    ) -> None:
        store = self._store()
        committer = self._committer(store)
        replacement = self._typed_record(
            ExecutorGenerationRecord,
            executor_generation=2,
            connection_epoch=2,
        )
        store.advance_executor_generation.return_value = replacement
        effects = [
            {
                "effectId": "effect-capability",
                "kind": ExecutorReplacementEffectKind.CAPABILITY_REVOCATION.value,
                "state": ExecutorReplacementEffectState.PENDING.value,
                "evidenceRef": None,
            },
            {
                "effectId": "effect-workspace",
                "kind": ExecutorReplacementEffectKind.WORKSPACE_RECONCILIATION.value,
                "state": ExecutorReplacementEffectState.PENDING.value,
                "evidenceRef": None,
            },
            {
                "effectId": "effect-external",
                "kind": ExecutorReplacementEffectKind.EXTERNAL_EFFECT_RECONCILIATION.value,
                "state": ExecutorReplacementEffectState.PENDING.value,
                "evidenceRef": None,
            },
        ]
        capability = self._typed_record(
            ExecutorReplacementEffectRecord,
            effect_id="effect-capability",
            kind=ExecutorReplacementEffectKind.CAPABILITY_REVOCATION,
            state=ExecutorReplacementEffectState.SUCCEEDED,
            evidence_ref="cas:atomic-revocation",
        )
        workspace = self._typed_record(
            ExecutorReplacementEffectRecord,
            effect_id="effect-workspace",
            environment_id="env-001",
            executor_generation=2,
            connection_epoch=2,
            kind=ExecutorReplacementEffectKind.WORKSPACE_RECONCILIATION,
            state=ExecutorReplacementEffectState.PENDING,
            evidence_ref=None,
        )
        external = self._typed_record(
            ExecutorReplacementEffectRecord,
            effect_id="effect-external",
            kind=ExecutorReplacementEffectKind.EXTERNAL_EFFECT_RECONCILIATION,
            state=ExecutorReplacementEffectState.PENDING,
            evidence_ref=None,
        )
        store.load_runtime_assurance_scope.return_value = self._snapshot_mock(
            executor_replacement_effects=(capability,)
        )
        store.record_executor_replacement_effect.side_effect = [workspace, external]
        output = {
            "replacement": {
                "environmentId": "env-001",
                "executorIdentity": "executor-new",
                "executorGeneration": 2,
                "connectionEpoch": 2,
            },
            "reconciliationEffects": effects,
            "activationAllowed": False,
        }

        durable = self._durable_call(
            committer,
            skill="elmos-executor-generation-fencing",
            payload={"action": "replace", "generation": 1, "connectionEpoch": 1},
            output=output,
        )

        self.assertFalse(durable["activationAllowed"])
        self.assertEqual(store.record_executor_replacement_effect.call_count, 2)
        self.assertEqual(
            {
                call.kwargs["kind"]
                for call in store.record_executor_replacement_effect.call_args_list
            },
            {
                ExecutorReplacementEffectKind.WORKSPACE_RECONCILIATION,
                ExecutorReplacementEffectKind.EXTERNAL_EFFECT_RECONCILIATION,
            },
        )

        with self.assertRaisesRegex(IntegrityError, "effects are not exact"):
            self._durable_call(
                committer,
                skill="elmos-executor-generation-fencing",
                payload={
                    "action": "replace",
                    "generation": 1,
                    "connectionEpoch": 1,
                },
                output={**output, "reconciliationEffects": effects[:2]},
            )

        provider = RegisteredRuntimeAssuranceAuthorityProvider()
        control = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
        )
        pending = workspace
        store.load_runtime_assurance_scope.return_value = self._snapshot_mock(
            executor_replacement_effects=(pending,)
        )

        def reconcile_effect(
            context: SecurityContext, **kwargs: Any
        ) -> ExecutorReplacementEffectRecord:
            del context
            return self._typed_record(
                ExecutorReplacementEffectRecord,
                effect_id="effect-workspace",
                kind=ExecutorReplacementEffectKind.WORKSPACE_RECONCILIATION,
                state=kwargs["target_state"],
                evidence_ref=kwargs["evidence_ref"],
            )

        store.reconcile_executor_replacement_effect.side_effect = reconcile_effect
        reconciled = control.reconcile_executor_replacement_effect(
            self.context,
            revision_set_id=self.revision_set_id,
            effect_id="effect-workspace",
            target_state=ExecutorReplacementEffectState.SUCCEEDED,
            observations={"workspaceOwnerVerified": True},
        )
        self.assertEqual(reconciled.state, ExecutorReplacementEffectState.SUCCEEDED)
        self.assertIsNotNone(reconciled.evidence_ref)
        assert reconciled.evidence_ref is not None
        evidence = control.runtime.read_evidence(self.context, reconciled.evidence_ref)
        self.assertEqual(evidence["kind"], "EXECUTOR_REPLACEMENT_EFFECT_RECONCILIATION")

        store.load_runtime_assurance_scope.return_value = self._snapshot_mock(
            executor_replacement_effects=(capability,)
        )
        with self.assertRaisesRegex(AuthorizationError, "storage-owned"):
            control.reconcile_executor_replacement_effect(
                self.context,
                revision_set_id=self.revision_set_id,
                effect_id="effect-capability",
                target_state=ExecutorReplacementEffectState.SUCCEEDED,
                observations={"requestedBy": "host"},
            )

    def test_executor_replace_cannot_report_activation_before_all_effects_finish(
        self,
    ) -> None:
        store = self._store()
        committer = self._committer(store)
        store.advance_executor_generation.return_value = self._typed_record(
            ExecutorGenerationRecord,
            executor_generation=2,
            connection_epoch=2,
        )
        effect_rows: list[dict[str, Any]] = []
        for kind in ExecutorReplacementEffectKind:
            effect_rows.append(
                {
                    "effectId": f"effect-{kind.value.lower()}",
                    "kind": kind.value,
                    "state": ExecutorReplacementEffectState.PENDING.value,
                    "evidenceRef": None,
                }
            )
        succeeded = tuple(
            self._typed_record(
                ExecutorReplacementEffectRecord,
                effect_id=row["effectId"],
                kind=ExecutorReplacementEffectKind(row["kind"]),
                state=ExecutorReplacementEffectState.SUCCEEDED,
                evidence_ref=f"cas:{row['effectId']}",
            )
            for row in effect_rows
        )
        store.load_runtime_assurance_scope.return_value = self._snapshot_mock(
            executor_replacement_effects=(succeeded[0],)
        )
        store.record_executor_replacement_effect.side_effect = succeeded[1:]

        with self.assertRaisesRegex(
            IntegrityError, "activated before workspace/external reconciliation"
        ):
            self._durable_call(
                committer,
                skill="elmos-executor-generation-fencing",
                payload={
                    "action": "replace",
                    "generation": 1,
                    "connectionEpoch": 1,
                },
                output={
                    "replacement": {
                        "environmentId": "env-001",
                        "executorIdentity": "executor-new",
                        "executorGeneration": 2,
                        "connectionEpoch": 2,
                    },
                    "reconciliationEffects": effect_rows,
                    "activationAllowed": False,
                },
            )

    def test_executor_activation_is_denied_while_reconciliation_is_pending(
        self,
    ) -> None:
        store = self._store()
        provider = RegisteredRuntimeAssuranceAuthorityProvider()
        control = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
        )
        executor = ExecutorGenerationRecord(
            tenant_id=self.context.tenant_id,
            project_id=self.context.project_id,
            actor_id=self.context.actor_id,
            run_id=self.context.run_id or "",
            execution_epoch=1,
            fencing_generation=1,
            authority_revision=self.authority_revision,
            revision_set_id=self.revision_set_id,
            environment_id="env-001",
            executor_identity="executor-new",
            executor_generation=2,
            connection_epoch=2,
            state=ExecutorGenerationState.CONNECTING,
            live_probe_evidence_ref=None,
            created_at=NOW,
            updated_at=NOW,
        )
        effects = tuple(
            ExecutorReplacementEffectRecord(
                tenant_id=self.context.tenant_id,
                project_id=self.context.project_id,
                actor_id=self.context.actor_id,
                run_id=self.context.run_id or "",
                execution_epoch=1,
                fencing_generation=1,
                authority_revision=self.authority_revision,
                revision_set_id=self.revision_set_id,
                effect_id=f"effect-{kind.value.lower()}",
                environment_id="env-001",
                executor_generation=2,
                connection_epoch=2,
                kind=kind,
                state=(
                    ExecutorReplacementEffectState.SUCCEEDED
                    if kind is ExecutorReplacementEffectKind.CAPABILITY_REVOCATION
                    else ExecutorReplacementEffectState.PENDING
                ),
                evidence_ref=(
                    "cas:atomic-capability-revocation"
                    if kind is ExecutorReplacementEffectKind.CAPABILITY_REVOCATION
                    else None
                ),
                created_at=NOW,
                updated_at=NOW,
                reconciled_at=(
                    NOW
                    if kind is ExecutorReplacementEffectKind.CAPABILITY_REVOCATION
                    else None
                ),
            )
            for kind in ExecutorReplacementEffectKind
        )
        snapshot = replace(
            self._empty_snapshot(),
            executor_generations=(executor,),
            executor_replacement_effects=effects,
        )
        invocation = replace(
            self.invocation,
            invocation_id="inv-executor-activate",
            extension_skill="elmos-executor-generation-fencing",
            payload={
                "action": "activate",
                "environmentId": "env-001",
                "executorIdentity": "executor-new",
                "generation": 2,
                "connectionEpoch": 2,
                "liveProbeEvidenceRef": "cas:live-probe",
            },
        )
        authority = replace(
            self._operation_authority(
                invocation.invocation_id,
                extension_skill="elmos-executor-generation-fencing",
            ),
            executor_bindings=frozenset({("env-001", "executor-new")}),
            verified_evidence_refs=frozenset({"cas:live-probe", "base-origin-receipt"}),
        )
        provider.register(self.context, invocation, authority)
        store.load_runtime_assurance_scope.return_value = snapshot

        denied = control.execute_internal(self.context, invocation)

        self.assertEqual(denied.status, ResultStatus.DENIED)
        store.transition_executor_generation.assert_not_called()

    def test_workspace_lifecycle_actions_map_to_exact_store_operations(self) -> None:
        scenarios = (
            ("bind", "bind_workspace", 1, "owner-a", "ACTIVE", None),
            (
                "handoff",
                "request_workspace_handoff",
                1,
                "owner-a",
                "HANDOFF_PENDING",
                None,
            ),
            ("resume", None, 1, "owner-a", "ACTIVE", None),
            (
                "markTakeoverPending",
                "mark_workspace_takeover_pending",
                1,
                "owner-a",
                "TAKEOVER_PENDING",
                "cas:crash-evidence",
            ),
            ("takeover", "takeover_workspace", 2, "owner-b", "ACTIVE", None),
            (
                "acceptHandoff",
                "takeover_workspace",
                2,
                "owner-b",
                "ACTIVE",
                None,
            ),
            ("retire", "retire_workspace", 1, "owner-a", "RETIRED", None),
        )
        for action, method, generation, owner, state, crash_ref in scenarios:
            with self.subTest(action=action):
                store = self._store()
                committer = self._committer(store)
                workspace = self._typed_record(
                    WorkspaceLeaseRecord,
                    workspace_id="workspace-1",
                    generation=generation,
                    owner_execution_id=owner,
                    repository_id="repository-1",
                    base_revision="a" * 40,
                    write_scopes=("src",),
                    state=WorkspaceLeaseState(state),
                    takeover_evidence_ref=crash_ref,
                )
                if method is not None:
                    getattr(store, method).return_value = workspace
                if action in {"resume", "retire"}:
                    current = workspace
                    if action == "retire":
                        current = self._typed_record(
                            WorkspaceLeaseRecord,
                            workspace_id="workspace-1",
                            generation=1,
                            owner_execution_id="owner-a",
                            repository_id="repository-1",
                            base_revision="a" * 40,
                            write_scopes=("src",),
                            state=WorkspaceLeaseState.ACTIVE,
                            takeover_evidence_ref=None,
                        )
                    store.load_runtime_assurance_scope.return_value = (
                        self._snapshot_mock(workspace_leases=(current,))
                    )
                payload_generation = 1
                output = {
                    "workspaceId": "workspace-1",
                    "generation": generation,
                    "ownerExecutionId": owner,
                    "repositoryId": "repository-1",
                    "baseRevision": "a" * 40,
                    "writeScopes": ["src"],
                    "state": state,
                    "crashEvidenceRef": crash_ref,
                }

                result = self._durable_call(
                    committer,
                    skill="elmos-workspace-ownership-lease",
                    payload={"action": action, "generation": payload_generation},
                    output=output,
                )

                self.assertEqual(result, output)
                if method is not None:
                    getattr(store, method).assert_called_once()
                if action in {"takeover", "acceptHandoff"}:
                    self.assertEqual(
                        store.takeover_workspace.call_args.kwargs[
                            "expected_generation"
                        ],
                        1,
                    )

    def test_durable_event_register_append_and_exact_replay_are_store_bound(
        self,
    ) -> None:
        store = self._store()
        committer = self._committer(store)
        registration = {
            "type": "plugin.updated",
            "owner": "plugin-1",
            "schemaVersion": 1,
            "semantics": DurableEventSemantics.REQUIRED_STATE.value,
            "validator": "validate-plugin-updated",
            "upgrader": "upgrade-plugin-updated",
            "projections": ["plugin-state"],
            "compatibility": EventCompatibility.BACKWARD.value,
        }
        registration_hash = digest_object(
            registration,
            domain="delta-event-registration",
        )
        store.register_durable_event.return_value = self._typed_record(
            DurableEventRegistrationRecord,
            registration_hash=registration_hash,
        )
        register_output = {"registration": registration}

        self.assertEqual(
            self._durable_call(
                committer,
                skill="elmos-registered-durable-plugin-events",
                payload={"action": "register"},
                output=register_output,
            ),
            register_output,
        )
        self.assertEqual(
            store.register_durable_event.call_args.kwargs["registration_hash"],
            registration_hash,
        )

        event = {
            "eventId": "event-1",
            "type": "plugin.updated",
            "schemaVersion": 1,
            "correlationId": "correlation-1",
            "causationId": None,
            "payload": {"version": 1},
        }
        store.load_runtime_assurance_scope.return_value = self._snapshot_mock()
        store.append_durable_event.return_value = self._typed_record(
            DurableEventInstanceRecord,
            state=DurableEventInstanceState.PENDING,
        )
        append_output = {"event": event}
        self._durable_call(
            committer,
            skill="elmos-registered-durable-plugin-events",
            payload={"action": "append"},
            output=append_output,
        )
        append_call = store.append_durable_event.call_args
        self.assertEqual(append_call.kwargs["event_id"], "event-1")
        self.assertEqual(
            append_call.kwargs["payload_digest"],
            digest_object(event["payload"], domain="delta-durable-event-payload"),
        )
        payload_evidence = committer.evidence.get(
            self.context, append_call.kwargs["payload_ref"]
        )
        self.assertEqual(payload_evidence["kind"], "DURABLE_EVENT_PAYLOAD")

        source = self._typed_record(
            DurableEventInstanceRecord,
            event_id="event-1",
            event_type="plugin.updated",
            schema_version=1,
            correlation_id="correlation-1",
            causation_id=None,
            payload_ref=append_call.kwargs["payload_ref"],
            payload_digest=append_call.kwargs["payload_digest"],
        )
        store.load_runtime_assurance_scope.return_value = self._snapshot_mock(
            durable_events=(source,)
        )
        store.replay_durable_event.return_value = self._typed_record(
            DurableEventInstanceRecord,
            state=DurableEventInstanceState.PROCESSED,
        )
        replay_output = {"event": event}
        self._durable_call(
            committer,
            skill="elmos-registered-durable-plugin-events",
            payload={"action": "replay", "event": event},
            output=replay_output,
        )
        store.replay_durable_event.assert_called_once_with(
            self.context,
            revision_set_id=self.revision_set_id,
            event_id="event-1",
            expected_state=DurableEventInstanceState.PENDING,
            target_state=DurableEventInstanceState.PROCESSED,
            compatibility_decision=EventCompatibilityDecision.EXACT,
        )

        store.append_durable_event.return_value = self._typed_record(
            DurableEventInstanceRecord,
            state=DurableEventInstanceState.PROCESSED,
        )
        with self.assertRaisesRegex(IntegrityError, "not pending"):
            self._durable_call(
                committer,
                skill="elmos-registered-durable-plugin-events",
                payload={"action": "append"},
                output=append_output,
            )

    def test_durable_event_optional_skip_and_owner_preflight_fail_closed(self) -> None:
        store = self._store()
        committer = self._committer(store)
        event = {
            "eventId": "optional-1",
            "type": "plugin.observation",
            "schemaVersion": 1,
            "correlationId": "correlation-1",
            "causationId": None,
            "payload": {"seen": True},
        }
        store.load_runtime_assurance_scope.return_value = self._snapshot_mock()
        skipped = self._durable_call(
            committer,
            skill="elmos-registered-durable-plugin-events",
            payload={"action": "replay", "event": event},
            output={"event": None, "state": DurableEventInstanceState.SKIPPED.value},
        )
        self.assertIn("skipEvidenceRef", skipped)
        skip_evidence = committer.evidence.get(self.context, skipped["skipEvidenceRef"])
        self.assertEqual(skip_evidence["kind"], "DURABLE_EVENT_OPTIONAL_SKIP")
        store.replay_durable_event.assert_not_called()

        registration = self._typed_record(
            DurableEventRegistrationRecord,
            event_type="plugin.observation",
            owner="plugin-1",
        )
        store.load_runtime_assurance_scope.return_value = self._snapshot_mock(
            event_registrations=(registration,)
        )
        store.preflight_event_owner_change.return_value = (
            DurableEventOwnerChangePreflight(
                EventOwnerChangeAction.UNINSTALL,
                "plugin-1",
                None,
                False,
                ("persisted event history remains",),
            )
        )
        with self.assertRaisesRegex(ConflictError, "preflight blocked"):
            self._durable_call(
                committer,
                skill="elmos-registered-durable-plugin-events",
                payload={
                    "action": "preflightOwnerChange",
                    "eventType": "plugin.observation",
                    "operation": EventOwnerChangeAction.UNINSTALL.value,
                },
                output={
                    "preflight": {
                        "decision": "ALLOW",
                        "type": "plugin.observation",
                    }
                },
            )

        store.preflight_event_owner_change.return_value = (
            DurableEventOwnerChangePreflight(
                EventOwnerChangeAction.UNINSTALL,
                "plugin-1",
                None,
                True,
                (),
            )
        )
        allowed = self._durable_call(
            committer,
            skill="elmos-registered-durable-plugin-events",
            payload={
                "action": "preflightOwnerChange",
                "eventType": "plugin.observation",
                "operation": EventOwnerChangeAction.UNINSTALL.value,
            },
            output={
                "preflight": {
                    "decision": "ALLOW",
                    "type": "plugin.observation",
                }
            },
        )
        self.assertTrue(allowed["durablePreflight"]["allowed"])

    def test_durable_fork_and_migration_replay_use_derived_event_ids(self) -> None:
        for action, operation_field, operation_id, store_method, target_version in (
            ("forkReplay", "forkId", "fork-1", "fork_durable_event_lineage", 1),
            (
                "migrationReplay",
                "migrationId",
                "migration-1",
                "migrate_durable_event",
                2,
            ),
        ):
            with self.subTest(action=action):
                store = self._store()
                committer = self._committer(store)
                source_event = {
                    "eventId": "event-1",
                    "type": "plugin.updated",
                    "schemaVersion": 1,
                    "correlationId": "correlation-1",
                    "causationId": None,
                    "payload": {"version": 1},
                }
                payload_ref, payload_digest = committer._event_payload_ref(
                    self.context,
                    source_event,
                    operation="APPEND",
                )
                source = self._typed_record(
                    DurableEventInstanceRecord,
                    event_id="event-1",
                    event_type="plugin.updated",
                    schema_version=1,
                    correlation_id="correlation-1",
                    causation_id=None,
                    payload_ref=payload_ref,
                    payload_digest=payload_digest,
                )
                store.load_runtime_assurance_scope.return_value = self._snapshot_mock(
                    durable_events=(source,)
                )
                derived = self._typed_record(
                    DurableEventInstanceRecord,
                    state=DurableEventInstanceState.PENDING,
                    parent_event_id="event-1",
                )
                getattr(store, store_method).return_value = derived
                replayed = {**source_event, "schemaVersion": target_version}
                expected_kind = "FORK" if action == "forkReplay" else "MIGRATION"
                expected_id = RuntimeAssuranceDurableCommitter._derived_event_id(
                    operation_id,
                    "event-1",
                    expected_kind,
                )

                result = self._durable_call(
                    committer,
                    skill="elmos-registered-durable-plugin-events",
                    payload={"action": action, "events": [source_event]},
                    output={"events": [replayed], operation_field: operation_id},
                )

                self.assertEqual(result["events"][0]["eventId"], expected_id)
                self.assertEqual(
                    getattr(store, store_method).call_args.kwargs["event_id"],
                    expected_id,
                )
                self.assertEqual(result["events"][0]["causationId"], "event-1")

    def test_typed_ingress_ingest_and_page_verify_durable_evidence(self) -> None:
        store = self._store()
        committer = self._committer(store)
        ingress = {
            "ingressId": "ingress-1",
            "producerExecutionId": "producer-1",
            "kind": TypedIngressKind.EXTERNAL_EVENT.value,
            "eventId": "external-1",
            "deduplicationKey": "dedup-1",
            "correlationId": "correlation-1",
            "causationId": "cause-1",
            "originatingCallId": None,
            "content": "payload",
        }
        recorded = self._typed_record(
            TypedIngressRecord,
            ingress_id="ingress-1",
        )
        store.record_typed_ingress.return_value = (recorded, True)

        result = self._durable_call(
            committer,
            skill="elmos-typed-external-ingress",
            payload={"action": "ingest"},
            output={"ingress": ingress, "accepted": True},
        )

        self.assertTrue(result["accepted"])
        ingress_call = store.record_typed_ingress.call_args
        self.assertEqual(
            ingress_call.kwargs["envelope_digest"],
            digest_object(ingress, domain="delta-typed-ingress"),
        )
        ingress_ref = ingress_call.kwargs["payload_ref"]
        self.assertEqual(
            committer.evidence.get(self.context, ingress_ref)["kind"],
            "TYPED_INGRESS",
        )

        page_record = self._typed_record(
            TypedIngressRecord,
            ingress_id="ingress-1",
            producer_execution_id="producer-1",
            kind=TypedIngressKind.EXTERNAL_EVENT,
            correlation_id="correlation-1",
            causation_id="cause-1",
            originating_call_id=None,
            deduplication_key="dedup-1",
            envelope_digest=digest_object(ingress, domain="delta-typed-ingress"),
            payload_ref=ingress_ref,
        )
        next_time = NOW + timedelta(seconds=1)
        store.page_typed_ingress.return_value = self._typed_record(
            TypedIngressPage,
            records=(page_record,),
            next_cursor=(next_time, "ingress-1"),
        )
        page = self._durable_call(
            committer,
            skill="elmos-typed-external-ingress",
            payload={"action": "page"},
            output={
                "correlationId": "correlation-1",
                "limit": 10,
                "keysetCursor": {
                    "afterOccurredAt": None,
                    "afterIngressId": None,
                },
            },
        )
        self.assertEqual(page["records"], [ingress])
        self.assertEqual(page["nextCursor"]["afterIngressId"], "ingress-1")

        tampered_ref = committer.evidence.put(
            self.context,
            {"kind": "WRONG_KIND", "content": ingress},
        )
        page_record.payload_ref = tampered_ref
        with self.assertRaisesRegex(IntegrityError, "invalid kind"):
            self._durable_call(
                committer,
                skill="elmos-typed-external-ingress",
                payload={"action": "page"},
                output={
                    "correlationId": "correlation-1",
                    "limit": 10,
                    "keysetCursor": {
                        "afterOccurredAt": None,
                        "afterIngressId": None,
                    },
                },
            )

    def test_subagent_spec_is_recorded_then_consumed_with_exact_hash(self) -> None:
        store = self._store()
        committer = self._committer(store)
        tool_plan_hash = self._plan_records()[2].plan_hash
        wall_clock_deadline = NOW + timedelta(minutes=5)
        output = {
            "parentExecutionId": "parent-execution-1",
            "provider": "openai",
            "model": "gpt-5",
            "reasoningEffort": "high",
            "authoritySnapshotId": self.authority_revision,
            "environmentId": "env-001",
            "budgetReservationId": "reservation-1",
            "maxOutputTokens": 1024,
            "toolPlanHash": tool_plan_hash,
            "childAuthority": ["fs.read"],
            "childTools": ["read_file"],
            "costBudget": "1.50",
            "wallClockDeadline": wall_clock_deadline.isoformat().replace("+00:00", "Z"),
        }
        expected_hash = digest_object(output, domain="delta-subagent-execution-spec")
        recorded = self._typed_record(
            SubagentExecutionSpecRecord,
            budget_reservation_id="reservation-1",
        )
        consumed = self._typed_record(
            SubagentExecutionSpecRecord,
            state=SubagentExecutionSpecState.CONSUMED,
            consumer_execution_id=self.invocation.invocation_id,
            spec_hash=expected_hash,
        )
        store.record_subagent_execution_spec.return_value = recorded
        store.consume_subagent_execution_spec.return_value = consumed

        reservation = SubagentBudgetReservation(
            reservation_id="reservation-1",
            invocation_id=self.invocation.invocation_id,
            parent_execution_id="parent-execution-1",
            environment_id="env-001",
            authority_snapshot_id=self.authority_revision,
            provider="openai",
            model="gpt-5",
            reasoning_effort="high",
            child_authority=frozenset({"fs.read"}),
            child_tools=frozenset({"read_file"}),
            max_output_tokens=1024,
            max_cost_budget="1.50",
            wall_clock_deadline=wall_clock_deadline,
            tool_plan_hash=tool_plan_hash,
        )
        reservation_authority = replace(
            self.authority,
            originating_plan_hashes=frozenset({tool_plan_hash}),
            budget_reservations=(("reservation-1", 1024),),
            allowed_subagent_models=frozenset({("openai", "gpt-5")}),
            subagent_budget_reservations=(reservation,),
        )
        result = self._durable_call(
            committer,
            skill="elmos-subagent-model-execution-spec",
            payload={"budgetReservationId": "reservation-1"},
            output=output,
            authority=reservation_authority,
        )

        self.assertEqual(result["state"], SubagentExecutionSpecState.CONSUMED.value)
        self.assertEqual(
            store.record_subagent_execution_spec.call_args.kwargs["spec_hash"],
            expected_hash,
        )
        store.consume_subagent_execution_spec.assert_called_once_with(
            self.context,
            revision_set_id=self.revision_set_id,
            invocation_id=self.invocation.invocation_id,
            budget_reservation_id="reservation-1",
            consumer_execution_id=self.invocation.invocation_id,
        )

        consumed.spec_hash = digest_bytes(b"drift", domain="spec")
        with self.assertRaisesRegex(IntegrityError, "consumption diverged"):
            self._durable_call(
                committer,
                skill="elmos-subagent-model-execution-spec",
                payload={"budgetReservationId": "reservation-1"},
                output=output,
                authority=reservation_authority,
            )

    def test_snapshot_revision_drift_fails_before_runtime_execution(self) -> None:
        store = self._store()
        store.load_runtime_assurance_scope.return_value = self._empty_snapshot(
            revision_set_id=digest_bytes(b"wrong-revision", domain="revision-set")
        )
        provider = RegisteredRuntimeAssuranceAuthorityProvider()
        provider.register(self.context, self.invocation, self.authority)
        control = RuntimeAssuranceControlPlane(
            store,
            self.evidence,
            authority_provider=provider,
        )

        with self.assertRaisesRegex(IntegrityError, "snapshot scope diverged"):
            control.execute_internal(self.context, self.invocation)
        store.record_step_plan.assert_not_called()

    def test_process_state_is_isolated_between_revision_sets(self) -> None:
        def authority_provider(
            context: SecurityContext, invocation: DeltaInvocation
        ) -> RuntimeAssuranceAuthority:
            del context
            assert invocation.extension_skill is not None
            return replace(
                self.authority,
                revision_set_id=invocation.revision_set_id,
                originating_base_skill=self._origin(
                    invocation.invocation_id,
                    invocation.extension_skill,
                    revision_set_id=invocation.revision_set_id,
                ),
                authorized_producers=frozenset({"producer-1"}),
            )

        runtime = DeltaSkillRuntime(
            authority_provider=authority_provider,
            authorized_producers={
                (self.context.tenant_id, self.context.project_id): {"producer-1"}
            },
        )

        def ingress(revision: str, content: str) -> DeltaInvocation:
            return replace(
                self.invocation,
                revision_set_id=revision,
                extension_skill="elmos-typed-external-ingress",
                payload={
                    "action": "ingest",
                    "ingress": {
                        "ingressId": "ingress-1",
                        "kind": "EXTERNAL_EVENT",
                        "producerExecutionId": "producer-1",
                        "eventId": "event-1",
                        "deduplicationKey": "dedup-1",
                        "causationId": "cause-1",
                        "correlationId": "correlation-1",
                        "content": content,
                    },
                },
            )

        first = runtime.execute(
            ingress(self.revision_set_id, "revision-one"), context=self.context
        )
        second = runtime.execute(
            ingress(
                digest_bytes(b"repository-revision-v2", domain="revision-set"),
                "revision-two",
            ),
            context=self.context,
        )

        self.assertEqual(first.status, ResultStatus.COMMITTED)
        self.assertEqual(second.status, ResultStatus.COMMITTED)

    def test_production_readiness_binds_every_policy_and_fails_on_omission(
        self,
    ) -> None:
        ready, reason = self._production_control().ready(production=True)
        self.assertTrue(ready, reason)

        omissions = (
            "permission profiles",
            "typed-ingress producer policy",
            "subagent model allowlist",
            "trusted Skill trust-domain policy",
            "Skill signature verifier",
            "restart-safe Host security-context signer",
            "trusted privileged path policy",
            "live managed-worktree registry",
            "tool-result interceptor registry",
            "authority trust",
            "authority durability",
            "authority deadline",
            "base Skill origin receipt verifier",
            "Host envelope signature verifier",
            "durable Host envelope issuer",
        )
        for omission in omissions:
            with self.subTest(omission=omission):
                ready, reason = self._production_control(omit=omission).ready(
                    production=True
                )
                self.assertFalse(ready)
                if omission.startswith("authority "):
                    expected = {
                        "authority trust": "trusted authority provider",
                        "authority durability": "durable authority reconciliation",
                        "authority deadline": "deadline-enforced authority lookup",
                    }[omission]
                    self.assertIn(expected, reason)
                elif omission == "base Skill origin receipt verifier":
                    self.assertIn("base Skill origin receipt", reason)
                elif omission == "Host envelope signature verifier":
                    self.assertIn("Host envelope signatures", reason)
                elif omission == "durable Host envelope issuer":
                    self.assertIn("durable Host envelope issuer", reason)
                else:
                    self.assertIn(omission, reason)


if __name__ == "__main__":
    unittest.main()
