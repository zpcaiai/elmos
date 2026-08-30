from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterator, Mapping, Sequence
import unittest

from elmos_proof_harness.contracts import SecurityContext
from elmos_proof_harness.canonical import canonical_json, digest_bytes, digest_object
from elmos_proof_harness.delta import _tool_result_commit_key
from elmos_proof_harness.delta_storage import (
    CapabilityLeaseState,
    CapabilityRevocationReason,
    CapabilityUseDenialReason,
    DurableEventSemantics,
    EventCompatibility,
    ExecutorGenerationState,
    ExecutorReplacementEffectKind,
    ExecutorReplacementEffectState,
    InterceptorCommitRecord,
    RuntimeAssuranceClaimDisposition,
    RuntimeAssuranceInvocationState,
    RuntimeAssuranceStore,
    StepPlanState,
    SubagentExecutionSpecState,
    ToolResultCommitState,
    ToolResultFailureKind,
    TypedIngressKind,
    WorkspaceLeaseRecord,
    WorkspaceLeaseState,
    HostSignedEnvelope,
)
from elmos_proof_harness.errors import (
    AuthorizationError,
    ConflictError,
    IntegrityError,
    NotFoundError,
    StoreError,
    ValidationError,
)
from elmos_proof_harness.postgres import PostgresStore


NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=1)
EXPIRY = NOW + timedelta(minutes=5)
REVISION = "sha256:" + "a" * 64
AUTHORITY = "sha256:" + "b" * 64
DIGEST = "sha256:" + "c" * 64
OTHER_DIGEST = "sha256:" + "d" * 64
MODEL_SNAPSHOT = {
    "provider": "provider-a",
    "model": "model-a",
    "revision": "revision-a",
}
TOOL_PLAN = {"tools": ["tool-a"]}
TOOL_CONTRACTS = {"tool-a": {"input": DIGEST, "output": OTHER_DIGEST}}
HANDLER_DIGESTS = {"tool-a": DIGEST}
PLAN_DIGEST = digest_object(
    {
        "modelSnapshot": MODEL_SNAPSHOT,
        "tools": ["tool-a"],
        "toolContracts": TOOL_CONTRACTS,
        "handlerDigests": HANDLER_DIGESTS,
        "environmentSnapshotId": "environment-snapshot-a",
        "authoritySnapshotId": AUTHORITY,
        "mode": "AUTO",
        "capabilities": ["read", "write"],
    },
    domain="delta-execution-plan",
)
EVENT_REGISTRATION_HASH = digest_object(
    {
        "type": "plugin.updated",
        "owner": "plugin-a",
        "schemaVersion": 1,
        "semantics": DurableEventSemantics.REQUIRED_STATE.value,
        "validator": "validator://a",
        "upgrader": "upgrader://a",
        "projections": ["projection-a"],
        "compatibility": EventCompatibility.STRICT.value,
    },
    domain="delta-event-registration",
)
SUBAGENT_DEADLINE = NOW + timedelta(minutes=10)


def _subagent_spec_hash(invocation_id: str) -> str:
    return digest_object(
        {
            "invocationId": invocation_id,
            "parentExecutionId": "parent-a",
            "provider": "provider-a",
            "model": "model-a",
            "reasoningEffort": "high",
            "authoritySnapshotId": AUTHORITY,
            "environmentId": "environment-a",
            "budgetReservationId": "budget-a",
            "maxOutputTokens": 4096,
            "toolPlanHash": DIGEST,
            "childAuthority": ["read"],
            "childTools": ["tool-a"],
            "costBudget": "12.50",
            "wallClockDeadline": SUBAGENT_DEADLINE.isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
        },
        domain="delta-subagent-execution-spec",
    )


SUBAGENT_SPEC_HASH = _subagent_spec_hash("subagent-a")
CONTEXT = SecurityContext(
    "tenant-a",
    "project-a",
    "actor-a",
    "run-a",
    execution_epoch=7,
    fencing_generation=3,
    authority_revision=AUTHORITY,
)
_UNSET = object()


@dataclass(frozen=True)
class _Step:
    contains: str
    one: object = _UNSET
    all_rows: object = _UNSET
    rowcount: int = 0


class _FakeCursor:
    def __init__(self, steps: Sequence[_Step]) -> None:
        self.steps = list(steps)
        self.current: _Step | None = None
        self.executions: list[tuple[str, Any]] = []
        self.audit_events: list[dict[str, Any]] | None = None
        self.subagent_consumed = False
        self.pending_reconciled = False
        self.audit_owner: Any | None = None

    def execute(self, statement: str, parameters: Any = None) -> _FakeCursor:
        expected_parameters = statement.count("?") + statement.count("%s")
        observed_parameters = 0 if parameters is None else len(parameters)
        if expected_parameters != observed_parameters:
            raise AssertionError(
                "placeholder/parameter mismatch: "
                f"expected {expected_parameters}, observed {observed_parameters}: "
                f"{statement!r}"
            )
        if "set_config('app.revision_set_id'" in statement:
            self.current = _Step("set_config", rowcount=1)
            self.executions.append((statement, parameters))
            return self
        # The delta port now validates durable dependency rows before each
        # lifecycle mutation.  Keep legacy fake scripts readable by supplying
        # canonical fixtures only when a test has not explicitly scripted the
        # new dependency query; explicit steps still win and retain ordering
        # assertions for the original SQL contract.
        if self.steps and self.steps[0].contains in statement:
            step = self.steps.pop(0)
            self.current = step
            self.executions.append((statement, parameters))
            return self
        if "claim_runtime_assurance_invocation(" in statement:
            disposition = "ACQUIRED"
            if self.steps and self.steps[0].all_rows is not _UNSET:
                rows = self.steps.pop(0).all_rows
                if rows:
                    state = str(rows[0].get("state"))
                    request_digest = parameters[9] if parameters else None
                    stored_digest = rows[0].get("request_digest")
                    if state == RuntimeAssuranceInvocationState.COMPLETED.value:
                        if stored_digest != request_digest:
                            raise ConflictError(
                                "invocation id was reused with a different request digest",
                                code="INVOCATION_REQUEST_CONFLICT",
                            )
                        disposition = "COMPLETED_REPLAY"
                    else:
                        disposition = "RECOVERY_REQUIRED"
                # Legacy scripts modeled the helper's internal INSERT/UPDATE
                # as an externally visible step.  Consume that obsolete
                # bookkeeping while retaining the receipt row used by the
                # public helper contract.
            if self.steps and self.steps[0].contains in {
                "INSERT INTO runtime_assurance_invocation_receipts",
                "UPDATE runtime_assurance_invocation_receipts",
            }:
                self.steps.pop(0)
            if self.audit_events is not None and disposition in {
                "ACQUIRED",
                "RECOVERY_REQUIRED",
            }:
                self.audit_events.append(
                    {
                        "event_type": (
                            "INVOCATION_CLAIMED"
                            if disposition == "ACQUIRED"
                            else "INVOCATION_RECOVERY_REQUIRED"
                        ),
                        "payload": {"revision_set_id": REVISION},
                    }
                )
            self.current = _Step("claim_runtime_assurance_invocation", one={"disposition": disposition})
            self.executions.append((statement, parameters))
            return self
        if "consume_subagent_reservation_and_spec(" in statement:
            replayed = self.subagent_consumed
            self.subagent_consumed = True
            if self.steps and self.steps[0].contains == "UPDATE subagent_execution_specs":
                self.steps.pop(0)
            self.current = _Step(
                "consume_subagent_reservation_and_spec",
                one={"replayed": replayed},
            )
            if self.audit_owner is not None and not replayed:
                self.audit_owner.events.append(
                    {
                        "cursor": self,
                        "context": None,
                        "event_type": "SUBAGENT_EXECUTION_SPEC_CONSUMED",
                        "subject_id": "subagent-a",
                        "payload": {"revision_set_id": REVISION},
                    }
                )
            self.executions.append((statement, parameters))
            return self
        if "FROM pending_tool_call_bindings" in statement:
            if "ORDER BY call_id" in statement:
                self.current = _Step(
                    "FROM pending_tool_call_bindings",
                    all_rows=[_pending_row(reconciled=self.pending_reconciled)],
                )
            else:
                self.current = _Step(
                    "FROM pending_tool_call_bindings",
                    one=_pending_row(reconciled=self.pending_reconciled),
                )
            self.executions.append((statement, parameters))
            return self
        if "FROM step_execution_plans" in statement:
            if "ORDER BY plan_id" in statement:
                self.current = _Step(
                    "FROM step_execution_plans",
                    all_rows=[_step_row(StepPlanState.ACTIVE)],
                )
            else:
                self.current = _Step(
                    "FROM step_execution_plans",
                    one=_step_row(StepPlanState.ACTIVE),
                )
            self.executions.append((statement, parameters))
            return self
        if "FROM step_plan_tool_bindings" in statement:
            binding = {
                "tool_id": "tool-a",
                "tool_contract": TOOL_CONTRACTS["tool-a"],
                "contract_digest": digest_object(
                    TOOL_CONTRACTS["tool-a"], domain="delta-step-plan-tool-contract"
                ),
                "handler_digest": DIGEST,
            }
            self.current = _Step(
                "FROM step_plan_tool_bindings",
                all_rows=[binding]
                if "SELECT tool_id,tool_contract" in statement
                else _UNSET,
                one=(
                    _UNSET
                    if "SELECT tool_id,tool_contract" in statement
                    else binding
                ),
            )
            self.executions.append((statement, parameters))
            return self
        if "FROM runtime_authority_capability_receipts" in statement:
            operation_invocation_id = (
                str(parameters[-1])
                if parameters
                else "operation-a"
            )
            self.current = _Step(
                "FROM runtime_authority_capability_receipts",
                all_rows=[_authority_row(operation_invocation_id=operation_invocation_id)]
                if "ORDER BY operation_invocation_id" in statement
                else _UNSET,
                one=(
                    _UNSET
                    if "ORDER BY operation_invocation_id" in statement
                    else _authority_row(operation_invocation_id=operation_invocation_id)
                ),
            )
            self.executions.append((statement, parameters))
            return self
        if "FROM subagent_budget_reservation_bindings" in statement:
            operation_invocation_id = str(parameters[-1]) if parameters else "subagent-a"
            scripted_spec = next(
                (
                    step.one
                    for step in self.steps
                    if step.contains == "FROM subagent_execution_specs"
                    and isinstance(step.one, Mapping)
                ),
                None,
            )
            if scripted_spec is not None:
                self.subagent_consumed = (
                    scripted_spec.get("state") == "CONSUMED"
                )
            reservation = _reservation_row(
                operation_invocation_id=operation_invocation_id,
                consumed=self.subagent_consumed,
            )
            self.current = _Step(
                "FROM subagent_budget_reservation_bindings",
                all_rows=(
                    [reservation]
                    if "ORDER BY reservation_id" in statement
                    else _UNSET
                ),
                one=(
                    _UNSET
                    if "ORDER BY reservation_id" in statement
                    else reservation
                ),
            )
            self.executions.append((statement, parameters))
            return self
        if "FROM subagent_execution_specs" in statement:
            if self.steps and self.steps[0].contains in statement:
                step = self.steps.pop(0)
                self.current = step
                self.executions.append((statement, parameters))
                return self
            self.current = _Step(
                "FROM subagent_execution_specs",
                one=_subagent_row(SubagentExecutionSpecState.CONSUMED),
            )
            self.executions.append((statement, parameters))
            return self
        if "FROM environment_attachments" in statement:
            self.current = _Step(
                "FROM environment_attachments",
                all_rows=[
                    {
                        "server_id": "server-a",
                        "environment_id": "environment-a",
                        "snapshot_id": "environment-snapshot-a",
                        "owner_authority_ref": AUTHORITY,
                        "state": "ACTIVE",
                    }
                ],
            )
            self.executions.append((statement, parameters))
            return self
        if "INSERT INTO step_plan_tool_bindings" in statement:
            self.current = _Step("INSERT INTO step_plan_tool_bindings", rowcount=1)
            self.executions.append((statement, parameters))
            return self
        if "UPDATE pending_tool_call_bindings" in statement:
            self.pending_reconciled = True
            self.current = _Step("UPDATE pending_tool_call_bindings", rowcount=1)
            self.executions.append((statement, parameters))
            return self
        if not self.steps:
            raise AssertionError(f"unexpected SQL: {statement}")
        step = self.steps.pop(0)
        if step.contains not in statement:
            raise AssertionError(
                f"expected SQL containing {step.contains!r}, observed {statement!r}"
            )
        self.current = step
        self.executions.append((statement, parameters))
        return self

    @property
    def rowcount(self) -> int:
        if self.current is None:
            raise AssertionError("rowcount read before execute")
        return self.current.rowcount

    def fetchone(self) -> Mapping[str, Any] | None:
        if self.current is None or self.current.one is _UNSET:
            raise AssertionError("unexpected fetchone")
        value = self.current.one
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise AssertionError("scripted fetchone row is not a mapping")
        return value

    def fetchall(self) -> list[Mapping[str, Any]]:
        if self.current is None or self.current.all_rows is _UNSET:
            raise AssertionError("unexpected fetchall")
        value = self.current.all_rows
        if not isinstance(value, Sequence):
            raise AssertionError("scripted fetchall rows are not a sequence")
        return list(value)

    def close(self) -> None:
        return None


class _ClaimConnection:
    def __init__(self, steps: Sequence[_Step]) -> None:
        self.raw_cursor = _FakeCursor(steps)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.fail_next_cursor = False

    def cursor(self) -> _FakeCursor:
        if self.fail_next_cursor:
            self.fail_next_cursor = False
            raise ConnectionError("simulated terminated PostgreSQL backend")
        return self.raw_cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class _ClaimStore(PostgresStore):
    def __init__(self, connections: Sequence[_ClaimConnection]) -> None:
        self.connections = list(connections)
        self.events: list[dict[str, Any]] = []
        for connection in self.connections:
            connection.raw_cursor.audit_events = self.events

    def _connect(self) -> _ClaimConnection:
        if not self.connections:
            raise AssertionError("unexpected claim connection")
        return self.connections.pop(0)

    def _append_audit_outbox(
        self,
        cursor: Any,
        context: SecurityContext,
        *,
        event_type: str,
        subject_id: str,
        payload: Mapping[str, Any],
    ) -> str:
        self.events.append(
            {
                "cursor": cursor,
                "context": context,
                "event_type": event_type,
                "subject_id": subject_id,
                "payload": dict(payload),
            }
        )
        return f"evt-{len(self.events)}"


class _FakeStore(PostgresStore):
    def __init__(
        self,
        steps: Sequence[_Step],
        *,
        typed_ingress_policy: Mapping[str, Sequence[TypedIngressKind]] | None = None,
    ) -> None:
        self.cursor = _FakeCursor(steps)
        self.events: list[dict[str, Any]] = []
        self.cursor.audit_owner = self
        self._active_cursor: _FakeCursor | None = None
        self._typed_ingress_policy = {
            producer: frozenset(kinds)
            for producer, kinds in (typed_ingress_policy or {}).items()
        }

    @staticmethod
    def _require_active_invocation_operation(
        operation_invocation_id: str,
    ) -> None:
        if not operation_invocation_id:
            raise AssertionError("test operation invocation must be non-empty")

    @contextmanager
    def transaction(
        self,
        context: SecurityContext | None = None,
    ) -> Iterator[_FakeCursor]:
        if context is None:
            raise AssertionError("runtime-assurance transaction lost SecurityContext")
        if self._active_cursor is not None:
            raise AssertionError("nested fake transaction")
        self._active_cursor = self.cursor
        try:
            yield self.cursor
        finally:
            self._active_cursor = None

    @contextmanager
    def _authority_transaction(
        self,
        context: SecurityContext,
    ) -> Iterator[_FakeCursor]:
        if context is None:
            raise AssertionError("authority transaction lost SecurityContext")
        if self._active_cursor is not None:
            raise AssertionError("nested fake authority transaction")
        self._active_cursor = self.cursor
        try:
            yield self.cursor
        finally:
            self._active_cursor = None

    def _append_audit_outbox(
        self,
        cursor: Any,
        context: SecurityContext,
        *,
        event_type: str,
        subject_id: str,
        payload: Mapping[str, Any],
    ) -> str:
        if cursor is not self._active_cursor:
            raise AssertionError("audit/outbox escaped the mutation transaction")
        self.events.append(
            {
                "cursor": cursor,
                "context": context,
                "event_type": event_type,
                "subject_id": subject_id,
                "payload": dict(payload),
            }
        )
        return f"evt-{len(self.events)}"

    def assert_consumed(self) -> None:
        if self.cursor.steps:
            raise AssertionError(f"unconsumed SQL steps: {self.cursor.steps!r}")


def _scope_row(**changes: Any) -> dict[str, Any]:
    row = {
        "run_id": CONTEXT.run_id,
        "actor_id": CONTEXT.actor_id,
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": CONTEXT.authority_revision,
        "revision_set_id": REVISION,
    }
    row.update(changes)
    return row


def _scope_step(row: Mapping[str, Any] | None = None) -> _Step:
    return _Step("FROM runs", one=_scope_row() if row is None else row)


def _pending_row(*, reconciled: bool = False) -> dict[str, Any]:
    return {
        "tenant_id": CONTEXT.tenant_id,
        "project_id": CONTEXT.project_id,
        "run_id": CONTEXT.run_id,
        "actor_id": CONTEXT.actor_id,
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": CONTEXT.authority_revision,
        "revision_set_id": REVISION,
        "invocation_id": "invocation-a",
        "call_id": "call-a",
        "attempt": 1,
        "execution_plan_hash": PLAN_DIGEST,
        "environment_id": "environment-a",
        "tool_id": "tool-a",
        "authority_snapshot_id": AUTHORITY,
        "state": "RECONCILED" if reconciled else "PENDING",
        "created_at": NOW,
        "updated_at": LATER if reconciled else NOW,
        "reconciled_at": LATER if reconciled else None,
    }


def _authority_row(*, operation_invocation_id: str = "operation-a") -> dict[str, Any]:
    payload = {
        "tenantId": CONTEXT.tenant_id,
        "projectId": CONTEXT.project_id,
        "runId": CONTEXT.run_id,
        "actorId": CONTEXT.actor_id,
        "executionEpoch": CONTEXT.execution_epoch,
        "fencingGeneration": CONTEXT.fencing_generation,
        "authorityRevision": AUTHORITY,
        "revisionSetId": REVISION,
        "operationInvocationId": operation_invocation_id,
        "environmentId": "environment-a",
        "authoritySnapshotId": AUTHORITY,
        "capabilities": ["read", "write"],
        "delegationAllowed": False,
        "authorityDigest": AUTHORITY,
        "originSkillId": "skill-a",
        "originSkillName": "skill-a",
        "originOwnerKernel": "K1",
        "originExecutionId": "execution-a",
        "originStepId": "step-a",
        "extensionSkill": "skill-a",
        "originReceiptRef": "receipt://a",
        "originReceiptState": "EXECUTING",
        "originReceiptDigest": DIGEST,
        "originSigningKeyId": "local-key",
        "originSignatureAlgorithm": "LOCAL_SELF_ATTESTED",
        "originSignature": "LOCAL_SELF_ATTESTED",
    }
    envelope = HostSignedEnvelope.local_self_attested(
        kind="RUNTIME_AUTHORITY_CAPABILITY",
        payload=payload,
        now=NOW,
    )
    return {
        "tenant_id": CONTEXT.tenant_id,
        "project_id": CONTEXT.project_id,
        "run_id": CONTEXT.run_id,
        "actor_id": CONTEXT.actor_id,
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": AUTHORITY,
        "revision_set_id": REVISION,
        "operation_invocation_id": operation_invocation_id,
        "environment_id": "environment-a",
        "authority_snapshot_id": AUTHORITY,
        "capability_set": ["read", "write"],
        "delegation_allowed": False,
        "authority_digest": AUTHORITY,
        "origin_skill_id": "skill-a",
        "origin_skill_name": "skill-a",
        "origin_owner_kernel": "K1",
        "origin_execution_id": "execution-a",
        "origin_step_id": "step-a",
        "extension_skill": "skill-a",
        "origin_receipt_ref": "receipt://a",
        "origin_receipt_state": "EXECUTING",
        "origin_receipt_digest": DIGEST,
        "origin_signing_key_id": "local-key",
        "origin_signature_algorithm": "LOCAL_SELF_ATTESTED",
        "origin_signature": "LOCAL_SELF_ATTESTED",
        "host_envelope_payload_digest": envelope.payload_digest,
        "host_envelope_digest": envelope.envelope_digest,
        "host_envelope_issuer": envelope.issuer,
        "host_envelope_signing_key_id": envelope.signing_key_id,
        "host_envelope_signature_algorithm": envelope.signature_algorithm,
        "host_envelope_signature": envelope.signature,
        "host_envelope_issued_at": envelope.issued_at,
        "host_envelope_verifier_id": envelope.verifier_id,
        "host_envelope_verification_evidence_ref": envelope.verification_evidence_ref,
        "host_envelope_verification_evidence_digest": envelope.verification_evidence_digest,
        "host_envelope_verified_at": envelope.verified_at,
    }


def _reservation_row(
    *, operation_invocation_id: str = "subagent-a", consumed: bool = False
) -> dict[str, Any]:
    authority_envelope_digest = _authority_row(
        operation_invocation_id=operation_invocation_id
    )["host_envelope_digest"]
    payload = {
        "tenantId": CONTEXT.tenant_id,
        "projectId": CONTEXT.project_id,
        "runId": CONTEXT.run_id,
        "actorId": CONTEXT.actor_id,
        "executionEpoch": CONTEXT.execution_epoch,
        "fencingGeneration": CONTEXT.fencing_generation,
        "authorityRevision": AUTHORITY,
        "revisionSetId": REVISION,
        "reservationId": "budget-a",
        "operationInvocationId": operation_invocation_id,
        "parentExecutionId": "parent-a",
        "environmentId": "environment-a",
        "authoritySnapshotId": AUTHORITY,
        "provider": "provider-a",
        "model": "model-a",
        "reasoningEffort": "high",
        "childAuthority": ["read"],
        "childTools": ["tool-a"],
        "maxOutputTokens": 4096,
        "maxCostBudget": "12.50",
        "wallClockDeadline": SUBAGENT_DEADLINE.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "toolPlanHash": DIGEST,
        "authorityEnvelopeDigest": authority_envelope_digest,
    }
    envelope = HostSignedEnvelope.local_self_attested(
        kind="SUBAGENT_BUDGET_RESERVATION",
        payload=payload,
        now=NOW,
    )
    consume_payload = {
        "run_id": CONTEXT.run_id,
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": CONTEXT.authority_revision,
        "revision_set_id": REVISION,
        "detail": {
            "invocation_id": operation_invocation_id,
            "budget_reservation_id": "budget-a",
            "consumer_execution_id": "child-execution-a",
            "spec_hash": SUBAGENT_SPEC_HASH,
            "max_output_tokens": 4096,
            "cost_budget": "12.50",
            "authority_envelope_digest": authority_envelope_digest,
        },
    }
    consume_payload_sha256 = digest_bytes(
        canonical_json(consume_payload).encode("utf-8"),
        domain="event-payload",
    )
    return {
        "tenant_id": CONTEXT.tenant_id,
        "project_id": CONTEXT.project_id,
        "run_id": CONTEXT.run_id,
        "actor_id": CONTEXT.actor_id,
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": AUTHORITY,
        "revision_set_id": REVISION,
        "reservation_id": "budget-a",
        "operation_invocation_id": operation_invocation_id,
        "parent_execution_id": "parent-a",
        "environment_id": "environment-a",
        "authority_snapshot_id": AUTHORITY,
        "provider": "provider-a",
        "model": "model-a",
        "reasoning_effort": "high",
        "child_authority": ["read"],
        "child_tools": ["tool-a"],
        "max_output_tokens": 4096,
        "max_cost_budget": "12.50",
        "wall_clock_deadline": SUBAGENT_DEADLINE,
        "tool_plan_hash": DIGEST,
        "authority_envelope_digest": authority_envelope_digest,
        "host_envelope_payload_digest": envelope.payload_digest,
        "host_envelope_digest": envelope.envelope_digest,
        "host_envelope_issuer": envelope.issuer,
        "host_envelope_signing_key_id": envelope.signing_key_id,
        "host_envelope_signature_algorithm": envelope.signature_algorithm,
        "host_envelope_signature": envelope.signature,
        "host_envelope_issued_at": envelope.issued_at,
        "host_envelope_verifier_id": envelope.verifier_id,
        "host_envelope_verification_evidence_ref": envelope.verification_evidence_ref,
        "host_envelope_verification_evidence_digest": envelope.verification_evidence_digest,
        "host_envelope_verified_at": envelope.verified_at,
        "state": "CONSUMED" if consumed else "RESERVED",
        "created_at": NOW,
        "updated_at": LATER if consumed else NOW,
        "consumed_at": LATER if consumed else None,
        "consumer_execution_id": "child-execution-a" if consumed else None,
        "consume_event_id": "evt-consume" if consumed else None,
        "consume_payload_sha256": consume_payload_sha256 if consumed else None,
    }


def _tool_row(
    state: ToolResultCommitState = ToolResultCommitState.COMMITTED,
) -> dict[str, Any]:
    captured = state in {
        ToolResultCommitState.RAW_CAPTURED,
        ToolResultCommitState.INTERCEPTING,
    }
    return {
        "tenant_id": CONTEXT.tenant_id,
        "project_id": CONTEXT.project_id,
        "run_id": CONTEXT.run_id,
        "actor_id": CONTEXT.actor_id,
        "invocation_id": "invocation-a",
        "call_id": "call-a",
        "attempt": 1,
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": CONTEXT.authority_revision,
        "revision_set_id": REVISION,
        "execution_plan_hash": PLAN_DIGEST,
        "environment_id": "environment-a",
        "authority_snapshot_id": AUTHORITY,
        "raw_result_ref": "cas://raw",
        "effective_result_ref": "cas://raw" if captured else "cas://effective",
        "interceptor_chain": []
        if captured
        else [
            {
                "interceptorId": "sanitize",
                "version": "1",
                "decisionHash": DIGEST,
            }
        ],
        "mutation_provenance_ref": None if captured else "cas://mutation",
        "failure_kind": "CANCELLED" if state is ToolResultCommitState.ABORTED else None,
        "failure_reason": "cancelled"
        if state is ToolResultCommitState.ABORTED
        else None,
        "state": state.value,
        "created_at": NOW,
        "updated_at": NOW if state is ToolResultCommitState.COMMITTED else LATER,
        "committed_at": None if captured else NOW,
        "published_at": LATER if state is ToolResultCommitState.PUBLISHED else None,
        "aborted_at": LATER if state is ToolResultCommitState.ABORTED else None,
        "recovery_evidence_ref": None,
    }


def _step_row(
    state: StepPlanState = StepPlanState.CANDIDATE,
    *,
    plan_id: str = "plan-a",
) -> dict[str, Any]:
    finalized = state in {
        StepPlanState.FINALIZED,
        StepPlanState.ACTIVE,
        StepPlanState.RETIRED,
    }
    activated = state in {StepPlanState.ACTIVE, StepPlanState.RETIRED}
    retired = state is StepPlanState.RETIRED
    return {
        "tenant_id": CONTEXT.tenant_id,
        "project_id": CONTEXT.project_id,
        "run_id": CONTEXT.run_id,
        "actor_id": CONTEXT.actor_id,
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": CONTEXT.authority_revision,
        "revision_set_id": REVISION,
        "plan_id": plan_id,
        "step_id": "step-a",
        "plan_hash": PLAN_DIGEST,
        "model_snapshot": MODEL_SNAPSHOT,
        "tool_plan": TOOL_PLAN,
        "tool_contracts": TOOL_CONTRACTS,
        "handler_digests": HANDLER_DIGESTS,
        "capabilities": ["read", "write"],
        "tool_mode": "AUTO",
        "environment_snapshot_id": "environment-snapshot-a",
        "authority_snapshot_id": AUTHORITY,
        "state": state.value,
        "created_at": NOW,
        "updated_at": LATER if state is not StepPlanState.CANDIDATE else NOW,
        "finalized_at": NOW if finalized else None,
        "activated_at": LATER if activated else None,
        "retired_at": LATER if retired else None,
    }


def _capability_row(
    state: CapabilityLeaseState = CapabilityLeaseState.ACTIVE,
    *,
    delegation_allowed: object = False,
    **changes: Any,
) -> dict[str, Any]:
    terminal = state is not CapabilityLeaseState.ACTIVE
    row = {
        "tenant_id": CONTEXT.tenant_id,
        "project_id": CONTEXT.project_id,
        "run_id": CONTEXT.run_id,
        "actor_id": CONTEXT.actor_id,
        "lease_id": "lease-a",
        "invocation_id": "invocation-a",
        "environment_id": "environment-a",
        "authority_snapshot_id": AUTHORITY,
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": CONTEXT.authority_revision,
        "revision_set_id": REVISION,
        "capability_set": ["read", "write"],
        "delegation_allowed": delegation_allowed,
        "state": state.value,
        "issued_at": NOW,
        "expires_at": EXPIRY,
        "revoked_at": LATER if state is CapabilityLeaseState.REVOKED else None,
        "revocation_reason": (
            CapabilityRevocationReason.CANCELLED.value
            if state is CapabilityLeaseState.REVOKED
            else None
        ),
        "updated_at": EXPIRY
        if state is CapabilityLeaseState.EXPIRED
        else (LATER if terminal else NOW),
    }
    row.update(changes)
    return row


def _executor_row(
    state: ExecutorGenerationState = ExecutorGenerationState.CONNECTING,
    *,
    identity: str = "executor-a",
    generation: int = 1,
    connection_epoch: int = 1,
) -> dict[str, Any]:
    active_or_later = state in {
        ExecutorGenerationState.ACTIVE,
        ExecutorGenerationState.RETIRED,
    }
    return {
        "tenant_id": CONTEXT.tenant_id,
        "project_id": CONTEXT.project_id,
        "actor_id": CONTEXT.actor_id,
        "run_id": CONTEXT.run_id,
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": CONTEXT.authority_revision,
        "revision_set_id": REVISION,
        "environment_id": "environment-a",
        "executor_identity": identity,
        "executor_generation": generation,
        "connection_epoch": connection_epoch,
        "state": state.value,
        "live_probe_evidence_ref": "evidence://probe" if active_or_later else None,
        "created_at": NOW,
        "updated_at": LATER if state is not ExecutorGenerationState.CONNECTING else NOW,
        "activated_at": NOW if active_or_later else None,
        "retired_at": LATER if state is ExecutorGenerationState.RETIRED else None,
        "failed_at": LATER if state is ExecutorGenerationState.FAILED else None,
    }


def _replacement_effect_row(
    *,
    generation: int = 1,
    connection_epoch: int = 2,
    kind: ExecutorReplacementEffectKind = ExecutorReplacementEffectKind.CAPABILITY_REVOCATION,
    state: ExecutorReplacementEffectState = ExecutorReplacementEffectState.SUCCEEDED,
    effect_id: str | None = None,
) -> dict[str, Any]:
    effect_digest = digest_object(
        {
            "environmentId": "environment-a",
            "executorGeneration": generation,
            "connectionEpoch": connection_epoch,
            "kind": kind.value,
        },
        domain="delta-executor-replacement-effect",
    )
    return {
        "tenant_id": CONTEXT.tenant_id,
        "project_id": CONTEXT.project_id,
        "actor_id": CONTEXT.actor_id,
        "run_id": CONTEXT.run_id,
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": CONTEXT.authority_revision,
        "revision_set_id": REVISION,
        "effect_id": effect_id
        or f"effect-{effect_digest.removeprefix('sha256:')[:40]}",
        "environment_id": "environment-a",
        "executor_generation": generation,
        "connection_epoch": connection_epoch,
        "kind": kind.value,
        "state": state.value,
        "evidence_ref": None
        if state is ExecutorReplacementEffectState.PENDING
        else f"internal://{kind.value.lower()}",
        "created_at": LATER,
        "updated_at": LATER,
        "reconciled_at": None
        if state is ExecutorReplacementEffectState.PENDING
        else LATER,
    }


def _successful_replacement_effect_rows(
    *, generation: int = 1, connection_epoch: int = 2
) -> list[dict[str, Any]]:
    return [
        _replacement_effect_row(
            generation=generation,
            connection_epoch=connection_epoch,
            kind=kind,
        )
        for kind in (
            ExecutorReplacementEffectKind.CAPABILITY_REVOCATION,
            ExecutorReplacementEffectKind.WORKSPACE_RECONCILIATION,
            ExecutorReplacementEffectKind.EXTERNAL_EFFECT_RECONCILIATION,
        )
    ]


def _workspace_row(
    state: WorkspaceLeaseState = WorkspaceLeaseState.ACTIVE,
    *,
    owner: str = "execution-a",
    generation: int = 1,
    write_scopes: Sequence[str] = ("src",),
) -> dict[str, Any]:
    return {
        "tenant_id": CONTEXT.tenant_id,
        "project_id": CONTEXT.project_id,
        "actor_id": CONTEXT.actor_id,
        "run_id": CONTEXT.run_id,
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": CONTEXT.authority_revision,
        "revision_set_id": REVISION,
        "workspace_id": "workspace-a",
        "owner_execution_id": owner,
        "generation": generation,
        "repository_id": "repository-a",
        "base_revision": "revision-a",
        "write_scopes": list(write_scopes),
        "state": state.value,
        "takeover_evidence_ref": (
            "evidence://crash"
            if state is WorkspaceLeaseState.TAKEOVER_PENDING
            else None
        ),
        "created_at": NOW,
        "updated_at": LATER if state is not WorkspaceLeaseState.ACTIVE else NOW,
        "retired_at": LATER if state is WorkspaceLeaseState.RETIRED else None,
    }


def _event_row() -> dict[str, Any]:
    return {
        "tenant_id": CONTEXT.tenant_id,
        "project_id": CONTEXT.project_id,
        "actor_id": CONTEXT.actor_id,
        "run_id": CONTEXT.run_id,
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": CONTEXT.authority_revision,
        "revision_set_id": REVISION,
        "event_type": "plugin.updated",
        "owner": "plugin-a",
        "schema_version": 1,
        "semantics": DurableEventSemantics.REQUIRED_STATE.value,
        "compatibility": EventCompatibility.STRICT.value,
        "validator_ref": "validator://a",
        "upgrader_ref": "upgrader://a",
        "projections": ["projection-a"],
        "registration_hash": EVENT_REGISTRATION_HASH,
        "registered_at": NOW,
    }


def _ingress_row() -> dict[str, Any]:
    return {
        "tenant_id": CONTEXT.tenant_id,
        "project_id": CONTEXT.project_id,
        "run_id": CONTEXT.run_id,
        "actor_id": CONTEXT.actor_id,
        "ingress_id": "ingress-a",
        "producer_execution_id": "producer-a",
        "deduplication_key": "dedup-a",
        "kind": TypedIngressKind.TOOL_RESULT.value,
        "envelope_digest": DIGEST,
        "payload_ref": "cas://ingress",
        "originating_call_id": "call-a",
        "causation_id": "cause-a",
        "correlation_id": "correlation-a",
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": CONTEXT.authority_revision,
        "revision_set_id": REVISION,
        "occurred_at": NOW,
        "recorded_at": NOW,
        "persisted_sequence": 1,
    }


def _subagent_row(
    state: SubagentExecutionSpecState = SubagentExecutionSpecState.RESERVED,
) -> dict[str, Any]:
    return {
        "tenant_id": CONTEXT.tenant_id,
        "project_id": CONTEXT.project_id,
        "run_id": CONTEXT.run_id,
        "actor_id": CONTEXT.actor_id,
        "invocation_id": "subagent-a",
        "parent_execution_id": "parent-a",
        "provider": "provider-a",
        "model": "model-a",
        "reasoning_effort": "high",
        "authority_snapshot_id": AUTHORITY,
        "environment_id": "environment-a",
        "budget_reservation_id": "budget-a",
        "max_output_tokens": 4096,
        "tool_plan_hash": DIGEST,
        "child_authority": ["read"],
        "child_tools": ["tool-a"],
        "cost_budget": "12.50",
        "wall_clock_deadline": SUBAGENT_DEADLINE,
        "spec_hash": SUBAGENT_SPEC_HASH,
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": CONTEXT.authority_revision,
        "revision_set_id": REVISION,
        "recorded_at": NOW,
        "state": state.value,
        "consumer_execution_id": (
            "child-execution-a"
            if state is SubagentExecutionSpecState.CONSUMED
            else None
        ),
        "consumed_at": LATER if state is SubagentExecutionSpecState.CONSUMED else None,
        "updated_at": LATER if state is SubagentExecutionSpecState.CONSUMED else NOW,
    }


def _claim_row(
    state: RuntimeAssuranceInvocationState = RuntimeAssuranceInvocationState.IN_PROGRESS,
    *,
    request_digest: str = DIGEST,
) -> dict[str, Any]:
    completed = state is RuntimeAssuranceInvocationState.COMPLETED
    return {
        "tenant_id": CONTEXT.tenant_id,
        "project_id": CONTEXT.project_id,
        "run_id": CONTEXT.run_id,
        "actor_id": CONTEXT.actor_id,
        "execution_epoch": CONTEXT.execution_epoch,
        "fencing_generation": CONTEXT.fencing_generation,
        "authority_revision": CONTEXT.authority_revision,
        "revision_set_id": REVISION,
        "invocation_id": "invocation-a",
        "request_digest": request_digest,
        "claim_epoch": 1,
        "state": state.value,
        "result_ref": "cas://result" if completed else None,
        "result_digest": OTHER_DIGEST if completed else None,
        "claimed_at": NOW,
        "updated_at": LATER
        if state is not RuntimeAssuranceInvocationState.IN_PROGRESS
        else NOW,
        "completed_at": LATER if completed else None,
        "recovery_evidence_ref": None,
    }


def _assert_one_event(
    test: unittest.TestCase, store: _FakeStore, event_type: str
) -> None:
    store.assert_consumed()
    test.assertEqual([item["event_type"] for item in store.events], [event_type])
    test.assertIs(store.events[0]["cursor"], store.cursor)
    test.assertEqual(store.events[0]["payload"]["revision_set_id"], REVISION)


class RuntimeAssurancePostgresPortTests(unittest.TestCase):
    def test_invocation_claim_commits_before_yield_and_busy_session_fails_closed(
        self,
    ) -> None:
        first = _ClaimConnection(
            [
                _Step("SET TRANSACTION"),
                _Step("set_config('app.tenant_id'"),
                _Step("SET LOCAL search_path"),
                _Step("pg_try_advisory_lock", one={"acquired": True}),
                _scope_step(),
                _Step("FROM runtime_assurance_invocation_receipts", all_rows=[]),
                _Step("INSERT INTO runtime_assurance_invocation_receipts", rowcount=1),
                _Step(
                    "FROM runtime_assurance_invocation_receipts",
                    one=_claim_row(),
                ),
                _Step("pg_advisory_unlock", one={"unlocked": True}),
            ]
        )
        second = _ClaimConnection(
            [
                _Step("SET TRANSACTION"),
                _Step("set_config('app.tenant_id'"),
                _Step("SET LOCAL search_path"),
                _Step("pg_try_advisory_lock", one={"acquired": False}),
            ]
        )
        store = _ClaimStore([first, second])
        with store.claim_runtime_assurance_invocation(
            CONTEXT,
            revision_set_id=REVISION,
            invocation_id="invocation-a",
            request_digest=DIGEST,
            now=NOW,
        ) as claim:
            self.assertEqual(
                claim.disposition,
                RuntimeAssuranceClaimDisposition.ACQUIRED,
            )
            self.assertTrue(claim.execute_allowed)
            self.assertEqual(first.commits, 1)
            self.assertFalse(first.closed)
            with self.assertRaisesRegex(ConflictError, "already executing"):
                with store.claim_runtime_assurance_invocation(
                    CONTEXT,
                    revision_set_id=REVISION,
                    invocation_id="invocation-a",
                    request_digest=OTHER_DIGEST,
                    now=NOW,
                ):
                    self.fail("busy invocation must never yield")
        self.assertEqual(first.commits, 2)
        self.assertTrue(first.closed)
        self.assertEqual(second.rollbacks, 1)
        self.assertTrue(second.closed)
        self.assertEqual(
            [event["event_type"] for event in store.events],
            ["INVOCATION_CLAIMED"],
        )
        self.assertEqual(first.raw_cursor.steps, [])
        self.assertEqual(second.raw_cursor.steps, [])

    def test_stale_invocation_is_fenced_for_reconciliation_without_reexecution(
        self,
    ) -> None:
        connection = _ClaimConnection(
            [
                _Step("SET TRANSACTION"),
                _Step("set_config('app.tenant_id'"),
                _Step("SET LOCAL search_path"),
                _Step("pg_try_advisory_lock", one={"acquired": True}),
                _scope_step(),
                _Step(
                    "FROM runtime_assurance_invocation_receipts",
                    all_rows=[_claim_row()],
                ),
                _Step("UPDATE runtime_assurance_invocation_receipts", rowcount=1),
                _Step(
                    "FROM runtime_assurance_invocation_receipts",
                    one=_claim_row(RuntimeAssuranceInvocationState.RECOVERY_REQUIRED),
                ),
                _Step("pg_advisory_unlock", one={"unlocked": True}),
            ]
        )
        store = _ClaimStore([connection])
        with store.claim_runtime_assurance_invocation(
            CONTEXT,
            revision_set_id=REVISION,
            invocation_id="invocation-a",
            request_digest=DIGEST,
            now=LATER,
        ) as claim:
            self.assertEqual(
                claim.disposition,
                RuntimeAssuranceClaimDisposition.RECOVERY_REQUIRED,
            )
            self.assertFalse(claim.execute_allowed)
            self.assertFalse(claim.replay)
        self.assertEqual(
            [event["event_type"] for event in store.events],
            ["INVOCATION_RECOVERY_REQUIRED"],
        )
        self.assertEqual(connection.raw_cursor.steps, [])

    def test_invocation_id_rejects_every_different_request_digest_replay(
        self,
    ) -> None:
        connection = _ClaimConnection(
            [
                _Step("SET TRANSACTION"),
                _Step("set_config('app.tenant_id'"),
                _Step("SET LOCAL search_path"),
                _Step("pg_try_advisory_lock", one={"acquired": True}),
                _scope_step(),
                _Step(
                    "FROM runtime_assurance_invocation_receipts",
                    all_rows=[
                        _claim_row(RuntimeAssuranceInvocationState.COMPLETED)
                    ],
                ),
                _Step("pg_advisory_unlock", one={"unlocked": True}),
            ]
        )
        store = _ClaimStore([connection])
        with self.assertRaisesRegex(ConflictError, "different request digest"):
            with store.claim_runtime_assurance_invocation(
                CONTEXT,
                revision_set_id=REVISION,
                invocation_id="invocation-a",
                request_digest=OTHER_DIGEST,
                now=LATER,
            ):
                self.fail("digest-conflicting invocation must never yield")
        self.assertEqual(connection.raw_cursor.steps, [])
        self.assertEqual(store.events, [])

    def test_disconnected_claim_is_fenced_before_old_worker_mutation(self) -> None:
        connection = _ClaimConnection(
            [
                _Step("SET TRANSACTION"),
                _Step("set_config('app.tenant_id'"),
                _Step("SET LOCAL search_path"),
                _Step("pg_try_advisory_lock", one={"acquired": True}),
                _scope_step(),
                _Step("FROM runtime_assurance_invocation_receipts", all_rows=[]),
                _Step("INSERT INTO runtime_assurance_invocation_receipts", rowcount=1),
                _Step("FROM runtime_assurance_invocation_receipts", one=_claim_row()),
                _Step("pg_advisory_unlock", one={"unlocked": True}),
            ]
        )
        claims = _ClaimStore([connection])
        with claims.claim_runtime_assurance_invocation(
            CONTEXT,
            revision_set_id=REVISION,
            invocation_id="invocation-a",
            request_digest=DIGEST,
            now=NOW,
        ):
            connection.fail_next_cursor = True
            with self.assertRaises(StoreError) as captured:
                claims.audit_capability_use_denial(
                    CONTEXT,
                    revision_set_id=REVISION,
                    lease_id="lease-a",
                    subject_invocation_id="invocation-a",
                    operation_invocation_id="invocation-a",
                    capability="read",
                    reason=CapabilityUseDenialReason.UNKNOWN_LEASE,
                    now=LATER,
                )
            self.assertEqual(
                captured.exception.code,
                "POSTGRES_OPERATION_FAILED",
            )
            self.assertEqual(claims.connections, [])
            self.assertEqual(
                [event["event_type"] for event in claims.events],
                ["INVOCATION_CLAIMED"],
            )
        self.assertEqual(connection.raw_cursor.steps, [])

    def test_operation_identity_cannot_escape_or_bypass_active_claim(self) -> None:
        with self.assertRaises(AuthorizationError) as missing:
            PostgresStore._require_active_invocation_operation("invocation-a")
        self.assertEqual(missing.exception.code, "INVOCATION_CLAIM_REQUIRED")

        connection = _ClaimConnection(
            [
                _Step("SET TRANSACTION"),
                _Step("set_config('app.tenant_id'"),
                _Step("SET LOCAL search_path"),
                _Step("pg_try_advisory_lock", one={"acquired": True}),
                _scope_step(),
                _Step("FROM runtime_assurance_invocation_receipts", all_rows=[]),
                _Step("INSERT INTO runtime_assurance_invocation_receipts", rowcount=1),
                _Step("FROM runtime_assurance_invocation_receipts", one=_claim_row()),
                _Step("pg_advisory_unlock", one={"unlocked": True}),
            ]
        )
        claims = _ClaimStore([connection])
        with claims.claim_runtime_assurance_invocation(
            CONTEXT,
            revision_set_id=REVISION,
            invocation_id="invocation-a",
            request_digest=DIGEST,
            now=NOW,
        ):
            with self.assertRaises(AuthorizationError) as mismatch:
                claims.audit_capability_use_denial(
                    CONTEXT,
                    revision_set_id=REVISION,
                    lease_id="lease-a",
                    subject_invocation_id="invocation-a",
                    operation_invocation_id="invocation-b",
                    capability="read",
                    reason=CapabilityUseDenialReason.UNKNOWN_LEASE,
                    now=LATER,
                )
            self.assertEqual(
                mismatch.exception.code,
                "INVOCATION_OPERATION_MISMATCH",
            )
            self.assertEqual(
                [event["event_type"] for event in claims.events],
                ["INVOCATION_CLAIMED"],
            )
        self.assertEqual(connection.raw_cursor.steps, [])

    def test_protocol_and_scope_rehydration_cover_all_twelve_relations(self) -> None:
        store = _FakeStore(
            [
                _scope_step(),
                _Step("FROM tool_result_commits", all_rows=[_tool_row()]),
                _Step("FROM step_execution_plans", all_rows=[_step_row()]),
                _Step("FROM capability_leases", all_rows=[_capability_row()]),
                _Step("FROM executor_generations", all_rows=[_executor_row()]),
                _Step("FROM environment_attachments", all_rows=[]),
                _Step("FROM executor_replacement_effects", all_rows=[]),
                _Step("FROM workspace_leases", all_rows=[_workspace_row()]),
                _Step("FROM durable_event_registrations", all_rows=[_event_row()]),
                _Step("FROM durable_event_instances", all_rows=[]),
                _Step("FROM typed_ingress_records", all_rows=[_ingress_row()]),
                _Step("FROM subagent_execution_specs", all_rows=[_subagent_row()]),
            ]
        )
        self.assertIsInstance(store, RuntimeAssuranceStore)

        snapshot = store.load_runtime_assurance_scope(CONTEXT, revision_set_id=REVISION)

        self.assertEqual(snapshot.execution_epoch, CONTEXT.execution_epoch)
        self.assertEqual(
            snapshot.tool_results[0].state, ToolResultCommitState.COMMITTED
        )
        self.assertEqual(snapshot.typed_ingress[0].ingress_id, "ingress-a")
        self.assertEqual(
            snapshot.subagent_execution_specs[0].budget_reservation_id, "budget-a"
        )
        store.assert_consumed()

    def test_scope_fences_fail_closed_before_any_delta_read(self) -> None:
        cases: tuple[
            tuple[str, Mapping[str, Any] | None, type[Exception], str], ...
        ] = (
            ("missing", None, NotFoundError, "DELTA_SCOPE_NOT_FOUND"),
            (
                "actor",
                _scope_row(actor_id="actor-b"),
                AuthorizationError,
                "DELTA_ACTOR_MISMATCH",
            ),
            ("epoch", _scope_row(execution_epoch=8), ConflictError, "STALE_EPOCH"),
            ("fence", _scope_row(fencing_generation=4), ConflictError, "STALE_FENCE"),
            (
                "revision",
                _scope_row(revision_set_id=OTHER_DIGEST),
                ConflictError,
                "STALE_REVISION",
            ),
        )
        for label, row, error_type, code in cases:
            with self.subTest(label=label):
                store = _FakeStore([_Step("FROM runs", one=row)])
                with self.assertRaises(error_type) as captured:
                    store.load_runtime_assurance_scope(
                        CONTEXT, revision_set_id=REVISION
                    )
                self.assertEqual(getattr(captured.exception, "code"), code)
                store.assert_consumed()

    def test_rehydrate_rejects_cross_actor_rows_and_lossy_boolean_coercion(
        self,
    ) -> None:
        cross_actor = _tool_row()
        cross_actor["actor_id"] = "actor-b"
        store = _FakeStore(
            [
                _scope_step(),
                _Step("FROM tool_result_commits", all_rows=[cross_actor]),
                _Step("FROM step_execution_plans", all_rows=[]),
                _Step("FROM capability_leases", all_rows=[]),
                _Step("FROM executor_generations", all_rows=[]),
                _Step("FROM environment_attachments", all_rows=[]),
                _Step("FROM executor_replacement_effects", all_rows=[]),
                _Step("FROM workspace_leases", all_rows=[]),
                _Step("FROM durable_event_registrations", all_rows=[]),
                _Step("FROM durable_event_instances", all_rows=[]),
                _Step("FROM typed_ingress_records", all_rows=[]),
                _Step("FROM subagent_execution_specs", all_rows=[]),
            ]
        )
        with self.assertRaisesRegex(ValidationError, "exact snapshot scope"):
            store.load_runtime_assurance_scope(CONTEXT, revision_set_id=REVISION)
        store.assert_consumed()

        lossy = _FakeStore(
            [
                _scope_step(),
                _Step("FROM tool_result_commits", all_rows=[]),
                _Step("FROM step_execution_plans", all_rows=[]),
                _Step(
                    "FROM capability_leases",
                    all_rows=[_capability_row(delegation_allowed="false")],
                ),
            ]
        )
        with self.assertRaisesRegex(IntegrityError, "not boolean"):
            lossy.load_runtime_assurance_scope(CONTEXT, revision_set_id=REVISION)
        lossy.assert_consumed()

    def test_tool_result_commit_publish_abort_and_replay_are_atomic(self) -> None:
        chain = (InterceptorCommitRecord("sanitize", "1", DIGEST),)
        arguments = {
            "revision_set_id": REVISION,
            "invocation_id": "invocation-a",
            "call_id": "call-a",
            "attempt": 1,
            "execution_plan_hash": PLAN_DIGEST,
            "environment_id": "environment-a",
            "authority_snapshot_id": AUTHORITY,
            "raw_result_ref": "cas://raw",
            "effective_result_ref": "cas://effective",
            "interceptor_chain": chain,
            "mutation_provenance_ref": "cas://mutation",
            "now": NOW,
        }
        capture = _FakeStore(
            [
                _scope_step(),
                _Step("INSERT INTO tool_result_commits", rowcount=1),
                _Step(
                    "FROM tool_result_commits",
                    one=_tool_row(ToolResultCommitState.RAW_CAPTURED),
                ),
            ]
        )
        raw = capture.begin_tool_result(
            CONTEXT,
            revision_set_id=REVISION,
            invocation_id="invocation-a",
            call_id="call-a",
            attempt=1,
            execution_plan_hash=PLAN_DIGEST,
            environment_id="environment-a",
            authority_snapshot_id=AUTHORITY,
            raw_result_ref="cas://raw",
            now=NOW,
        )
        self.assertEqual(raw.state, ToolResultCommitState.RAW_CAPTURED)
        _assert_one_event(self, capture, "TOOL_RESULT_RAW_CAPTURED")

        intercept = _FakeStore(
            [
                _scope_step(),
                _Step(
                    "FROM tool_result_commits",
                    one=_tool_row(ToolResultCommitState.RAW_CAPTURED),
                ),
                _Step("UPDATE tool_result_commits", rowcount=1),
                _Step(
                    "FROM tool_result_commits",
                    one=_tool_row(ToolResultCommitState.INTERCEPTING),
                ),
            ]
        )
        claimed = intercept.mark_tool_result_intercepting(
            CONTEXT,
            revision_set_id=REVISION,
            invocation_id="invocation-a",
            call_id="call-a",
            attempt=1,
            execution_epoch=7,
            now=NOW,
        )
        self.assertEqual(claimed.state, ToolResultCommitState.INTERCEPTING)
        _assert_one_event(self, intercept, "TOOL_RESULT_INTERCEPTING")

        store = _FakeStore(
            [
                _scope_step(),
                _Step(
                    "FROM tool_result_commits",
                    one=_tool_row(ToolResultCommitState.INTERCEPTING),
                ),
                _Step("UPDATE tool_result_commits", rowcount=1),
                _Step("FROM tool_result_commits", one=_tool_row()),
            ]
        )
        self.assertEqual(
            store.commit_tool_result(CONTEXT, **arguments).state,
            ToolResultCommitState.COMMITTED,
        )
        _assert_one_event(self, store, "TOOL_RESULT_COMMITTED")

        replay = _FakeStore(
            [
                _scope_step(),
                _Step(
                    "FROM tool_result_commits",
                    one=_tool_row(ToolResultCommitState.PUBLISHED),
                ),
            ]
        )
        self.assertEqual(
            replay.commit_tool_result(CONTEXT, **arguments).state,
            ToolResultCommitState.PUBLISHED,
        )
        replay.assert_consumed()
        self.assertEqual(replay.events, [])

        publish = _FakeStore(
            [
                _scope_step(),
                _Step("FROM tool_result_commits", one=_tool_row()),
                _Step("UPDATE tool_result_commits", rowcount=1),
                _Step(
                    "FROM tool_result_commits",
                    one=_tool_row(ToolResultCommitState.PUBLISHED),
                ),
            ]
        )
        published = publish.transition_tool_result(
            CONTEXT,
            revision_set_id=REVISION,
            subject_invocation_id="invocation-a",
            operation_invocation_id="operation-a",
            call_id="call-a",
            attempt=1,
            execution_epoch=7,
            expected_execution_plan_hash=PLAN_DIGEST,
            expected_environment_id="environment-a",
            expected_authority_snapshot_id=AUTHORITY,
            expected_state=ToolResultCommitState.COMMITTED,
            target_state=ToolResultCommitState.PUBLISHED,
            now=LATER,
        )
        self.assertEqual(published.state, ToolResultCommitState.PUBLISHED)
        _assert_one_event(self, publish, "TOOL_RESULT_PUBLISHED")

        terminal = _FakeStore(
            [
                _scope_step(),
                _Step(
                    "FROM tool_result_commits",
                    one=_tool_row(ToolResultCommitState.ABORTED),
                ),
            ]
        )
        with self.assertRaises(ConflictError):
            terminal.transition_tool_result(
                CONTEXT,
                revision_set_id=REVISION,
                subject_invocation_id="invocation-a",
                operation_invocation_id="operation-a",
                call_id="call-a",
                attempt=1,
                execution_epoch=7,
                expected_execution_plan_hash=PLAN_DIGEST,
                expected_environment_id="environment-a",
                expected_authority_snapshot_id=AUTHORITY,
                expected_state=ToolResultCommitState.COMMITTED,
                target_state=ToolResultCommitState.PUBLISHED,
                now=LATER,
            )
        terminal.assert_consumed()
        self.assertEqual(terminal.events, [])

        abort = _FakeStore(
            [
                _scope_step(),
                _Step(
                    "FROM tool_result_commits",
                    one=_tool_row(ToolResultCommitState.INTERCEPTING),
                ),
                _Step("UPDATE tool_result_commits", rowcount=1),
                _Step(
                    "FROM tool_result_commits",
                    one=_tool_row(ToolResultCommitState.ABORTED),
                ),
            ]
        )
        aborted = abort.abort_tool_result(
            CONTEXT,
            revision_set_id=REVISION,
            subject_invocation_id="invocation-a",
            operation_invocation_id="operation-a",
            call_id="call-a",
            attempt=1,
            execution_plan_hash=PLAN_DIGEST,
            environment_id="environment-a",
            authority_snapshot_id=AUTHORITY,
            raw_result_ref="cas://raw",
            effective_result_ref="cas://effective",
            interceptor_chain=chain,
            mutation_provenance_ref="cas://mutation",
            failure_kind=ToolResultFailureKind.CANCELLED,
            failure_reason="cancelled",
            now=LATER,
        )
        self.assertEqual(aborted.state, ToolResultCommitState.ABORTED)
        _assert_one_event(self, abort, "TOOL_RESULT_ABORTED")
        self.assertEqual(
            abort.events[0]["payload"]["detail"]["commitKey"],
            _tool_result_commit_key("invocation-a", "call-a", 1, 7),
        )

    def test_step_and_capability_mutations_emit_once_and_stale_states_fail(
        self,
    ) -> None:
        step_store = _FakeStore(
            [
                _scope_step(),
                _Step("INSERT INTO step_execution_plans", rowcount=1),
                _Step("FROM step_execution_plans", one=_step_row()),
            ]
        )
        step_store.record_step_plan(
            CONTEXT,
            revision_set_id=REVISION,
            plan_id="plan-a",
            step_id="step-a",
            plan_hash=PLAN_DIGEST,
            model_snapshot=MODEL_SNAPSHOT,
            tool_plan=TOOL_PLAN,
            tool_contracts=TOOL_CONTRACTS,
            handler_digests=HANDLER_DIGESTS,
            capabilities=("read", "write"),
            tool_mode="AUTO",
            environment_snapshot_id="environment-snapshot-a",
            authority_snapshot_id=AUTHORITY,
            now=NOW,
        )
        _assert_one_event(self, step_store, "STEP_PLAN_RECORDED")

        activate = _FakeStore(
            [
                _scope_step(),
                _Step(
                    "FROM step_execution_plans",
                    one=_step_row(StepPlanState.FINALIZED, plan_id="plan-b"),
                ),
                _Step(
                    "FROM step_execution_plans",
                    all_rows=[_step_row(StepPlanState.ACTIVE)],
                ),
                _Step("UPDATE step_execution_plans", rowcount=1),
                _Step("UPDATE step_execution_plans", rowcount=1),
                _Step(
                    "FROM step_execution_plans",
                    one=_step_row(StepPlanState.ACTIVE, plan_id="plan-b"),
                ),
            ]
        )
        active = activate.activate_step_plan(
            CONTEXT,
            revision_set_id=REVISION,
            plan_id="plan-b",
            now=LATER,
        )
        self.assertEqual(active.plan_id, "plan-b")
        _assert_one_event(self, activate, "STEP_PLAN_ACTIVATED")
        self.assertEqual(
            activate.events[0]["payload"]["detail"]["retired_plan_id"],
            "plan-a",
        )

        transition = _FakeStore(
            [
                _scope_step(),
                _Step("FROM step_execution_plans", one=_step_row()),
                _Step("UPDATE step_execution_plans", rowcount=1),
                _Step(
                    "FROM step_execution_plans", one=_step_row(StepPlanState.FINALIZED)
                ),
            ]
        )
        transition.transition_step_plan(
            CONTEXT,
            revision_set_id=REVISION,
            plan_id="plan-a",
            expected_state=StepPlanState.CANDIDATE,
            target_state=StepPlanState.FINALIZED,
            now=LATER,
        )
        _assert_one_event(self, transition, "STEP_PLAN_FINALIZED")

        lease = _FakeStore(
            [
                _scope_step(),
                _Step("FROM capability_leases", one=None),
                _Step("INSERT INTO capability_leases", rowcount=1),
                _Step("FROM capability_leases", one=_capability_row()),
            ]
        )
        lease.issue_capability_lease(
            CONTEXT,
            revision_set_id=REVISION,
            lease_id="lease-a",
            invocation_id="invocation-a",
            environment_id="environment-a",
            authority_snapshot_id=AUTHORITY,
            capabilities=("read", "write"),
            expires_at=EXPIRY,
            now=NOW,
        )
        _assert_one_event(self, lease, "CAPABILITY_LEASE_ISSUED")

        revoke = _FakeStore(
            [
                _scope_step(),
                _Step("FROM capability_leases", one=_capability_row()),
                _Step("UPDATE capability_leases", rowcount=1),
                _Step(
                    "FROM capability_leases",
                    one=_capability_row(CapabilityLeaseState.REVOKED),
                ),
            ]
        )
        revoke.revoke_capability_lease(
            CONTEXT,
            revision_set_id=REVISION,
            lease_id="lease-a",
            subject_invocation_id="invocation-a",
            operation_invocation_id="operation-a",
            expected_environment_id="environment-a",
            expected_authority_snapshot_id=AUTHORITY,
            authorized_capabilities=("read", "write"),
            reason=CapabilityRevocationReason.CANCELLED,
            now=LATER,
        )
        _assert_one_event(self, revoke, "CAPABILITY_LEASE_REVOKED")
        self.assertEqual(
            revoke.events[0]["payload"]["detail"]["subject_invocation_id"],
            "invocation-a",
        )
        self.assertEqual(
            revoke.events[0]["payload"]["detail"]["operation_invocation_id"],
            "operation-a",
        )

        use = _FakeStore(
            [_scope_step(), _Step("FROM capability_leases", one=_capability_row())]
        )
        used = use.record_capability_lease_use(
            CONTEXT,
            revision_set_id=REVISION,
            lease_id="lease-a",
            invocation_id="invocation-a",
            operation_invocation_id="operation-a",
            expected_environment_id="environment-a",
            expected_authority_snapshot_id=AUTHORITY,
            authorized_capabilities=("read", "write"),
            capability="read",
            now=LATER,
        )
        self.assertEqual(used.lease_id, "lease-a")
        _assert_one_event(self, use, "CAPABILITY_LEASE_USED")
        self.assertEqual(
            use.events[0]["payload"]["detail"]["subject_invocation_id"],
            "invocation-a",
        )
        self.assertEqual(
            use.events[0]["payload"]["detail"]["operation_invocation_id"],
            "operation-a",
        )

        denied = _FakeStore(
            [
                _scope_step(),
                _Step(
                    "FROM capability_leases",
                    one=_capability_row(CapabilityLeaseState.REVOKED),
                ),
            ]
        )
        with self.assertRaisesRegex(ConflictError, "not active"):
            denied.record_capability_lease_use(
                CONTEXT,
                revision_set_id=REVISION,
                lease_id="lease-a",
                invocation_id="invocation-a",
                operation_invocation_id="operation-a",
                expected_environment_id="environment-a",
                expected_authority_snapshot_id=AUTHORITY,
                authorized_capabilities=("read", "write"),
                capability="read",
                now=LATER,
            )
        _assert_one_event(self, denied, "CAPABILITY_LEASE_USE_DENIED")

        early = _FakeStore(
            [_scope_step(), _Step("FROM capability_leases", one=_capability_row())]
        )
        with self.assertRaisesRegex(ConflictError, "has not expired"):
            early.expire_capability_lease(
                CONTEXT,
                revision_set_id=REVISION,
                lease_id="lease-a",
                now=LATER,
            )
        early.assert_consumed()
        self.assertEqual(early.events, [])

    def test_capability_use_binds_host_environment_authority_and_operation(self) -> None:
        cases = (
            (
                {"environment_id": "environment-b"},
                ("read", "write"),
                CapabilityUseDenialReason.ENVIRONMENT_MISMATCH,
                "environment binding",
            ),
            (
                {},
                ("write",),
                CapabilityUseDenialReason.AUTHORITY_CAPABILITY_MISMATCH,
                "current Host authority",
            ),
        )
        for changes, authorized, expected_reason, message in cases:
            with self.subTest(reason=expected_reason.value):
                store = _FakeStore(
                    [
                        _scope_step(),
                        _Step(
                            "FROM capability_leases",
                            one=_capability_row(**changes),
                        ),
                    ]
                )
                with self.assertRaisesRegex(AuthorizationError, message):
                    store.record_capability_lease_use(
                        CONTEXT,
                        revision_set_id=REVISION,
                        lease_id="lease-a",
                        invocation_id="invocation-a",
                        operation_invocation_id="operation-a",
                        expected_environment_id="environment-a",
                        expected_authority_snapshot_id=AUTHORITY,
                        authorized_capabilities=authorized,
                        capability="read",
                        now=LATER,
                    )
                _assert_one_event(store=store, test=self, event_type="CAPABILITY_LEASE_USE_DENIED")
                detail = store.events[0]["payload"]["detail"]
                self.assertEqual(detail["reason"], expected_reason.value)
                self.assertEqual(detail["subject_invocation_id"], "invocation-a")
                self.assertEqual(detail["operation_invocation_id"], "operation-a")

        audit = _FakeStore([_scope_step()])
        audit.audit_capability_use_denial(
            CONTEXT,
            revision_set_id=REVISION,
            lease_id="lease-missing",
            subject_invocation_id=None,
            operation_invocation_id="operation-a",
            capability="read",
            reason=CapabilityUseDenialReason.UNKNOWN_LEASE,
            now=LATER,
        )
        _assert_one_event(self, audit, "CAPABILITY_LEASE_USE_DENIED")
        detail = audit.events[0]["payload"]["detail"]
        self.assertIsNone(detail["subject_invocation_id"])
        self.assertEqual(detail["operation_invocation_id"], "operation-a")

        revoke_denied = _FakeStore(
            [_scope_step(), _Step("FROM capability_leases", one=_capability_row())]
        )
        with self.assertRaisesRegex(
            AuthorizationError,
            "exceeds the current Host authority",
        ):
            revoke_denied.revoke_capability_lease(
                CONTEXT,
                revision_set_id=REVISION,
                lease_id="lease-a",
                subject_invocation_id="invocation-a",
                operation_invocation_id="operation-a",
                expected_environment_id="environment-a",
                expected_authority_snapshot_id=AUTHORITY,
                authorized_capabilities=("read",),
                reason=CapabilityRevocationReason.CANCELLED,
                now=LATER,
            )
        _assert_one_event(
            self,
            revoke_denied,
            "CAPABILITY_LEASE_REVOCATION_DENIED",
        )
        denial_detail = revoke_denied.events[0]["payload"]["detail"]
        self.assertEqual(
            denial_detail["reason"],
            CapabilityUseDenialReason.AUTHORITY_CAPABILITY_MISMATCH.value,
        )
        self.assertEqual(denial_detail["subject_invocation_id"], "invocation-a")
        self.assertEqual(denial_detail["operation_invocation_id"], "operation-a")

    def test_run_wide_capability_revoke_sets_exact_revision_scope(self) -> None:
        store = _FakeStore(
            [
                _scope_step(),
                _scope_step(),
                _Step("FROM capability_leases", all_rows=[_capability_row()]),
                _Step("UPDATE capability_leases", rowcount=1),
                _Step(
                    "FROM capability_leases",
                    all_rows=[_capability_row(CapabilityLeaseState.REVOKED)],
                ),
            ]
        )
        records = store.revoke_run_capability_leases(
            CONTEXT,
            reason=CapabilityRevocationReason.CANCELLED,
            now=LATER,
        )
        self.assertEqual(
            tuple(record.state for record in records),
            (CapabilityLeaseState.REVOKED,),
        )
        _assert_one_event(self, store, "RUN_CAPABILITY_LEASES_REVOKED")
        capability_sql = " ".join(
            statement
            for statement, _parameters in store.cursor.executions
            if "capability_leases" in statement
        )
        self.assertIn("revision_set_id=?", capability_sql)
        self.assertIn("authority_revision=?", capability_sql)

    def test_executor_record_transition_and_atomic_advance_are_idempotent(self) -> None:
        record = _FakeStore(
            [
                _scope_step(),
                _Step("INSERT INTO executor_generations", rowcount=1),
                _Step("FROM executor_generations", one=_executor_row()),
            ]
        )
        record.record_executor_generation(
            CONTEXT,
            revision_set_id=REVISION,
            environment_id="environment-a",
            executor_identity="executor-a",
            executor_generation=1,
            connection_epoch=1,
            now=NOW,
        )
        _assert_one_event(self, record, "EXECUTOR_GENERATION_RECORDED")

        activate = _FakeStore(
            [
                _scope_step(),
                _Step("FROM executor_generations", one=_executor_row()),
                _Step("FROM executor_replacement_effects", all_rows=[]),
                _Step("FROM executor_generations", one=None),
                _Step("UPDATE executor_generations", rowcount=1),
                _Step(
                    "FROM executor_generations",
                    one=_executor_row(ExecutorGenerationState.ACTIVE),
                ),
            ]
        )
        activate.transition_executor_generation(
            CONTEXT,
            revision_set_id=REVISION,
            environment_id="environment-a",
            executor_generation=1,
            connection_epoch=1,
            expected_state=ExecutorGenerationState.CONNECTING,
            target_state=ExecutorGenerationState.ACTIVE,
            live_probe_evidence_ref="evidence://probe",
            now=LATER,
        )
        _assert_one_event(self, activate, "EXECUTOR_GENERATION_ACTIVE")

        successor = _executor_row(connection_epoch=2)
        advance = _FakeStore(
            [
                _scope_step(),
                _Step(
                    "FROM executor_generations",
                    one=_executor_row(ExecutorGenerationState.ACTIVE),
                ),
                _Step("UPDATE executor_generations", rowcount=1),
                _Step("INSERT INTO executor_generations", rowcount=1),
                _Step("FROM executor_generations", one=successor),
                _Step("FROM capability_leases", all_rows=[]),
                _Step("INSERT INTO executor_replacement_effects", rowcount=1),
            ]
        )
        advanced = advance.advance_executor_generation(
            CONTEXT,
            revision_set_id=REVISION,
            environment_id="environment-a",
            executor_identity="executor-a",
            expected_generation=1,
            expected_connection_epoch=1,
            replace_identity=False,
            now=LATER,
        )
        self.assertEqual(
            (advanced.executor_generation, advanced.connection_epoch), (1, 2)
        )
        advance.assert_consumed()
        self.assertEqual(
            [item["event_type"] for item in advance.events],
            [
                "EXECUTOR_REPLACEMENT_CAPABILITIES_REVOKED",
                "EXECUTOR_GENERATION_ADVANCED",
            ],
        )

        replay = _FakeStore(
            [
                _scope_step(),
                _Step(
                    "FROM executor_generations",
                    one=_executor_row(ExecutorGenerationState.RETIRED),
                ),
                _Step("FROM executor_generations", one=successor),
                _Step(
                    "FROM executor_replacement_effects",
                    all_rows=_successful_replacement_effect_rows(),
                ),
            ]
        )
        replay.advance_executor_generation(
            CONTEXT,
            revision_set_id=REVISION,
            environment_id="environment-a",
            executor_identity="executor-a",
            expected_generation=1,
            expected_connection_epoch=1,
            replace_identity=False,
            now=LATER,
        )
        replay.assert_consumed()
        self.assertEqual(replay.events, [])

        drifted_replay = _FakeStore(
            [
                _scope_step(),
                _Step(
                    "FROM executor_generations",
                    one=_executor_row(ExecutorGenerationState.RETIRED),
                ),
                _Step("FROM executor_generations", one=successor),
                _Step(
                    "FROM executor_replacement_effects",
                    all_rows=[_replacement_effect_row()],
                ),
            ]
        )
        with self.assertRaisesRegex(IntegrityError, "exactly three"):
            drifted_replay.advance_executor_generation(
                CONTEXT,
                revision_set_id=REVISION,
                environment_id="environment-a",
                executor_identity="executor-a",
                expected_generation=1,
                expected_connection_epoch=1,
                replace_identity=False,
                now=LATER,
            )
        drifted_replay.assert_consumed()

        preactive = _FakeStore(
            [_scope_step(), _Step("FROM executor_generations", one=_executor_row())]
        )
        with self.assertRaisesRegex(ConflictError, "only an active executor"):
            preactive.advance_executor_generation(
                CONTEXT,
                revision_set_id=REVISION,
                environment_id="environment-a",
                executor_identity="executor-a",
                expected_generation=1,
                expected_connection_epoch=1,
                replace_identity=False,
                now=LATER,
            )
        preactive.assert_consumed()

    def test_advanced_executor_activation_requires_exact_succeeded_effect_set(
        self,
    ) -> None:
        effects = _successful_replacement_effect_rows()
        activate = _FakeStore(
            [
                _scope_step(),
                _Step("FROM executor_generations", one=_executor_row(connection_epoch=2)),
                _Step("FROM executor_replacement_effects", all_rows=effects),
                _Step("FROM executor_generations", one=None),
                _Step("UPDATE executor_generations", rowcount=1),
                _Step(
                    "FROM executor_generations",
                    one=_executor_row(
                        ExecutorGenerationState.ACTIVE,
                        connection_epoch=2,
                    ),
                ),
            ]
        )
        activated = activate.transition_executor_generation(
            CONTEXT,
            revision_set_id=REVISION,
            environment_id="environment-a",
            executor_generation=1,
            connection_epoch=2,
            expected_state=ExecutorGenerationState.CONNECTING,
            target_state=ExecutorGenerationState.ACTIVE,
            live_probe_evidence_ref="evidence://probe",
            now=LATER,
        )
        self.assertEqual(activated.state, ExecutorGenerationState.ACTIVE)
        _assert_one_event(self, activate, "EXECUTOR_GENERATION_ACTIVE")

        malformed_sets: tuple[tuple[str, list[dict[str, Any]]], ...] = (
            ("missing", effects[:2]),
            (
                "duplicate",
                [
                    effects[0],
                    _replacement_effect_row(effect_id="effect-duplicate"),
                    effects[1],
                ],
            ),
            ("extra", [*effects, _replacement_effect_row(effect_id="effect-extra")]),
            (
                "pending",
                [
                    effects[0],
                    effects[1],
                    _replacement_effect_row(
                        kind=ExecutorReplacementEffectKind.EXTERNAL_EFFECT_RECONCILIATION,
                        state=ExecutorReplacementEffectState.PENDING,
                    ),
                ],
            ),
        )
        for label, malformed in malformed_sets:
            with self.subTest(label=label):
                rejected = _FakeStore(
                    [
                        _scope_step(),
                        _Step(
                            "FROM executor_generations",
                            one=_executor_row(connection_epoch=2),
                        ),
                        _Step(
                            "FROM executor_replacement_effects",
                            all_rows=malformed,
                        ),
                    ]
                )
                with self.assertRaises(ConflictError) as captured:
                    rejected.transition_executor_generation(
                        CONTEXT,
                        revision_set_id=REVISION,
                        environment_id="environment-a",
                        executor_generation=1,
                        connection_epoch=2,
                        expected_state=ExecutorGenerationState.CONNECTING,
                        target_state=ExecutorGenerationState.ACTIVE,
                        live_probe_evidence_ref="evidence://probe",
                        now=LATER,
                    )
                self.assertEqual(
                    captured.exception.code,
                    "EXECUTOR_REPLACEMENT_UNRESOLVED",
                )
                rejected.assert_consumed()

        replay = _FakeStore(
            [
                _scope_step(),
                _Step(
                    "FROM executor_generations",
                    one=_executor_row(
                        ExecutorGenerationState.ACTIVE,
                        connection_epoch=2,
                    ),
                ),
                _Step("FROM executor_replacement_effects", all_rows=effects[:1]),
            ]
        )
        with self.assertRaises(ConflictError) as captured:
            replay.transition_executor_generation(
                CONTEXT,
                revision_set_id=REVISION,
                environment_id="environment-a",
                executor_generation=1,
                connection_epoch=2,
                expected_state=ExecutorGenerationState.CONNECTING,
                target_state=ExecutorGenerationState.ACTIVE,
                live_probe_evidence_ref="evidence://probe",
                now=LATER,
            )
        self.assertEqual(captured.exception.code, "EXECUTOR_REPLACEMENT_UNRESOLVED")
        replay.assert_consumed()

    def test_workspace_lifecycle_preserves_repository_base_and_write_scope(
        self,
    ) -> None:
        empty = _FakeStore([])
        with self.assertRaisesRegex(ValidationError, "must not be empty"):
            empty.bind_workspace(
                CONTEXT,
                revision_set_id=REVISION,
                workspace_id="workspace-a",
                owner_execution_id="execution-a",
                generation=1,
                repository_id="repository-a",
                base_revision="revision-a",
                write_scopes=(),
                now=NOW,
            )
        empty.assert_consumed()

        bind = _FakeStore(
            [
                _scope_step(),
                _Step("pg_advisory_xact_lock"),
                _Step("FROM workspace_leases", all_rows=[]),
                _Step("FROM workspace_leases", one=None),
                _Step("INSERT INTO workspace_leases", rowcount=1),
                _Step("FROM workspace_leases", one=_workspace_row()),
            ]
        )
        bind.bind_workspace(
            CONTEXT,
            revision_set_id=REVISION,
            workspace_id="workspace-a",
            owner_execution_id="execution-a",
            generation=1,
            repository_id="repository-a",
            base_revision="revision-a",
            write_scopes=("src",),
            now=NOW,
        )
        _assert_one_event(self, bind, "WORKSPACE_BOUND")
        overlap_query = next(
            statement
            for statement, _parameters in bind.cursor.executions
            if "ORDER BY workspace_id,generation FOR UPDATE" in statement
        )
        self.assertIn("tenant_id=? AND project_id=?", overlap_query)
        self.assertNotIn("authority_revision=?", overlap_query)

        handoff = _FakeStore(
            [
                _scope_step(),
                _Step("FROM workspace_leases", one=_workspace_row()),
                _Step("UPDATE workspace_leases", rowcount=1),
                _Step(
                    "FROM workspace_leases",
                    one=_workspace_row(WorkspaceLeaseState.HANDOFF_PENDING),
                ),
            ]
        )
        handoff.request_workspace_handoff(
            CONTEXT,
            revision_set_id=REVISION,
            workspace_id="workspace-a",
            expected_generation=1,
            now=LATER,
        )
        _assert_one_event(self, handoff, "WORKSPACE_HANDOFF_REQUESTED")

        expansion = _FakeStore(
            [
                _scope_step(),
                _Step(
                    "FROM workspace_leases",
                    one=_workspace_row(WorkspaceLeaseState.HANDOFF_PENDING),
                ),
            ]
        )
        with self.assertRaisesRegex(ConflictError, "cannot change write scopes"):
            expansion.takeover_workspace(
                CONTEXT,
                revision_set_id=REVISION,
                workspace_id="workspace-a",
                expected_generation=1,
                new_owner_execution_id="execution-b",
                write_scopes=("src", "secrets"),
                now=LATER,
            )
        expansion.assert_consumed()
        self.assertEqual(expansion.events, [])

        successor = _workspace_row(owner="execution-b", generation=2)
        takeover = _FakeStore(
            [
                _scope_step(),
                _Step(
                    "FROM workspace_leases",
                    one=_workspace_row(WorkspaceLeaseState.HANDOFF_PENDING),
                ),
                _Step("UPDATE workspace_leases", rowcount=1),
                _Step("INSERT INTO workspace_leases", rowcount=1),
                _Step("FROM workspace_leases", one=successor),
            ]
        )
        takeover.takeover_workspace(
            CONTEXT,
            revision_set_id=REVISION,
            workspace_id="workspace-a",
            expected_generation=1,
            new_owner_execution_id="execution-b",
            base_revision="revision-a",
            write_scopes=("src",),
            now=LATER,
        )
        _assert_one_event(self, takeover, "WORKSPACE_TAKEN_OVER")

        retire = _FakeStore(
            [
                _scope_step(),
                _Step(
                    "FROM workspace_leases",
                    one=_workspace_row(WorkspaceLeaseState.TAKEOVER_PENDING),
                ),
                _Step("UPDATE workspace_leases", rowcount=1),
                _Step(
                    "FROM workspace_leases",
                    one=_workspace_row(WorkspaceLeaseState.RETIRED),
                ),
            ]
        )
        retired = retire.retire_workspace(
            CONTEXT,
            revision_set_id=REVISION,
            workspace_id="workspace-a",
            expected_generation=1,
            expected_state=WorkspaceLeaseState.TAKEOVER_PENDING,
            now=LATER,
        )
        self.assertIsNone(retired.takeover_evidence_ref)
        retire_update = next(
            statement
            for statement, _parameters in retire.cursor.executions
            if statement.startswith("UPDATE workspace_leases")
        )
        self.assertIn("takeover_evidence_ref=NULL", retire_update)
        _assert_one_event(self, retire, "WORKSPACE_RETIRED")

    def test_event_ingress_and_subagent_records_are_immutable_deduplicated_and_journaled(
        self,
    ) -> None:
        event = _FakeStore(
            [
                _scope_step(),
                _Step("INSERT INTO durable_event_registrations", rowcount=1),
                _Step("FROM durable_event_registrations", one=_event_row()),
            ]
        )
        event.register_durable_event(
            CONTEXT,
            revision_set_id=REVISION,
            event_type="plugin.updated",
            owner="plugin-a",
            schema_version=1,
            semantics=DurableEventSemantics.REQUIRED_STATE,
            compatibility=EventCompatibility.STRICT,
            validator_ref="validator://a",
            upgrader_ref="upgrader://a",
            projections=("projection-a",),
            registration_hash=EVENT_REGISTRATION_HASH,
            now=NOW,
        )
        _assert_one_event(self, event, "DURABLE_EVENT_REGISTERED")

        ingress = _FakeStore(
            [
                _scope_step(),
                _Step("FROM typed_ingress_records", all_rows=[]),
                _Step("INSERT INTO typed_ingress_records", rowcount=1),
                _Step("FROM typed_ingress_records", one=_ingress_row()),
            ],
            typed_ingress_policy={"producer-a": (TypedIngressKind.TOOL_RESULT,)},
        )
        record, accepted = ingress.record_typed_ingress(
            CONTEXT,
            revision_set_id=REVISION,
            ingress_id="ingress-a",
            producer_execution_id="producer-a",
            deduplication_key="dedup-a",
            kind=TypedIngressKind.TOOL_RESULT,
            envelope_digest=DIGEST,
            payload_ref="cas://ingress",
            correlation_id="correlation-a",
            causation_id="cause-a",
            originating_call_id="call-a",
            occurred_at=NOW,
            now=NOW,
        )
        self.assertTrue(accepted)
        self.assertEqual(record.ingress_id, "ingress-a")
        _assert_one_event(self, ingress, "TYPED_INGRESS_ACCEPTED")

        ingress_replay = _FakeStore(
            [
                _scope_step(),
                _Step("FROM typed_ingress_records", all_rows=[_ingress_row()]),
            ],
            typed_ingress_policy={"producer-a": (TypedIngressKind.TOOL_RESULT,)},
        )
        _record, accepted = ingress_replay.record_typed_ingress(
            CONTEXT,
            revision_set_id=REVISION,
            ingress_id="ingress-a",
            producer_execution_id="producer-a",
            deduplication_key="dedup-a",
            kind=TypedIngressKind.TOOL_RESULT,
            envelope_digest=DIGEST,
            payload_ref="cas://ingress",
            correlation_id="correlation-a",
            causation_id="cause-a",
            originating_call_id="call-a",
            occurred_at=NOW,
            now=NOW,
        )
        self.assertFalse(accepted)
        ingress_replay.assert_consumed()
        self.assertEqual(ingress_replay.events, [])

        ingress_conflict = _FakeStore(
            [
                _scope_step(),
                _Step("FROM typed_ingress_records", all_rows=[_ingress_row()]),
            ],
            typed_ingress_policy={"producer-a": (TypedIngressKind.TOOL_RESULT,)},
        )
        with self.assertRaisesRegex(ConflictError, "diverges"):
            ingress_conflict.record_typed_ingress(
                CONTEXT,
                revision_set_id=REVISION,
                ingress_id="ingress-a",
                producer_execution_id="producer-a",
                deduplication_key="dedup-a",
                kind=TypedIngressKind.TOOL_RESULT,
                envelope_digest=OTHER_DIGEST,
                payload_ref="cas://ingress",
                correlation_id="correlation-a",
                causation_id="cause-a",
                originating_call_id="call-a",
                occurred_at=NOW,
                now=NOW,
            )
        ingress_conflict.assert_consumed()

        subagent = _FakeStore(
            [
                _scope_step(),
                _Step("FROM subagent_execution_specs", all_rows=[]),
                _Step("INSERT INTO subagent_execution_specs", rowcount=1),
                _Step("FROM subagent_execution_specs", one=_subagent_row()),
            ]
        )
        subagent.record_subagent_execution_spec(
            CONTEXT,
            revision_set_id=REVISION,
            invocation_id="subagent-a",
            parent_execution_id="parent-a",
            provider="provider-a",
            model="model-a",
            reasoning_effort="high",
            authority_snapshot_id=AUTHORITY,
            environment_id="environment-a",
            budget_reservation_id="budget-a",
            max_output_tokens=4096,
            tool_plan_hash=DIGEST,
            child_authority=("read",),
            child_tools=("tool-a",),
            cost_budget="12.50",
            wall_clock_deadline=SUBAGENT_DEADLINE,
            spec_hash=SUBAGENT_SPEC_HASH,
            now=NOW,
        )
        _assert_one_event(self, subagent, "SUBAGENT_EXECUTION_SPEC_RECORDED")

        reused = _subagent_row()
        reused["invocation_id"] = "subagent-other"
        reused["spec_hash"] = _subagent_spec_hash("subagent-other")
        subagent_conflict = _FakeStore(
            [_scope_step(), _Step("FROM subagent_execution_specs", all_rows=[reused])]
        )
        with self.assertRaisesRegex(ConflictError, "reservation reuse"):
            subagent_conflict.record_subagent_execution_spec(
                CONTEXT,
                revision_set_id=REVISION,
                invocation_id="subagent-a",
                parent_execution_id="parent-a",
                provider="provider-a",
                model="model-a",
                reasoning_effort="high",
                authority_snapshot_id=AUTHORITY,
                environment_id="environment-a",
                budget_reservation_id="budget-a",
                max_output_tokens=4096,
                tool_plan_hash=DIGEST,
                child_authority=("read",),
                child_tools=("tool-a",),
                cost_budget="12.50",
                wall_clock_deadline=SUBAGENT_DEADLINE,
                spec_hash=SUBAGENT_SPEC_HASH,
                now=NOW,
            )
        subagent_conflict.assert_consumed()
        self.assertEqual(subagent_conflict.events, [])

        consumed_row = _subagent_row(SubagentExecutionSpecState.CONSUMED)
        consume = _FakeStore(
            [
                _scope_step(),
                _Step("FROM subagent_execution_specs", one=_subagent_row()),
                _Step("UPDATE subagent_execution_specs", rowcount=1),
                _Step("FROM subagent_execution_specs", one=consumed_row),
            ]
        )
        consumed = consume.consume_subagent_execution_spec(
            CONTEXT,
            revision_set_id=REVISION,
            invocation_id="subagent-a",
            budget_reservation_id="budget-a",
            consumer_execution_id="child-execution-a",
            now=LATER,
        )
        self.assertEqual(consumed.state, SubagentExecutionSpecState.CONSUMED)
        _assert_one_event(self, consume, "SUBAGENT_EXECUTION_SPEC_CONSUMED")

        consume_replay = _FakeStore(
            [_scope_step(), _Step("FROM subagent_execution_specs", one=consumed_row)]
        )
        consume_replay.consume_subagent_execution_spec(
            CONTEXT,
            revision_set_id=REVISION,
            invocation_id="subagent-a",
            budget_reservation_id="budget-a",
            consumer_execution_id="child-execution-a",
            now=SUBAGENT_DEADLINE + timedelta(seconds=1),
        )
        consume_replay.assert_consumed()
        self.assertEqual(consume_replay.events, [])

        consume_conflict = _FakeStore(
            [_scope_step(), _Step("FROM subagent_execution_specs", one=consumed_row)]
        )
        with self.assertRaisesRegex(ConflictError, "another execution"):
            consume_conflict.consume_subagent_execution_spec(
                CONTEXT,
                revision_set_id=REVISION,
                invocation_id="subagent-a",
                budget_reservation_id="budget-a",
                consumer_execution_id="child-execution-b",
                now=LATER,
            )
        consume_conflict.assert_consumed()
        self.assertEqual(consume_conflict.events, [])

        expired = _FakeStore(
            [_scope_step(), _Step("FROM subagent_execution_specs", one=_subagent_row())]
        )
        with self.assertRaises(ConflictError) as captured:
            expired.consume_subagent_execution_spec(
                CONTEXT,
                revision_set_id=REVISION,
                invocation_id="subagent-a",
                budget_reservation_id="budget-a",
                consumer_execution_id="child-execution-a",
                now=SUBAGENT_DEADLINE,
            )
        self.assertEqual(captured.exception.code, "SUBAGENT_DEADLINE_EXPIRED")
        expired.assert_consumed()
        self.assertEqual(expired.events, [])

    def test_workspace_record_rejects_empty_scope_even_during_rehydration(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must not be empty"):
            WorkspaceLeaseRecord(
                tenant_id="tenant-a",
                project_id="project-a",
                actor_id="actor-a",
                run_id="run-a",
                execution_epoch=7,
                fencing_generation=3,
                authority_revision=AUTHORITY,
                revision_set_id=REVISION,
                workspace_id="workspace-a",
                owner_execution_id="execution-a",
                generation=1,
                repository_id="repository-a",
                base_revision="revision-a",
                write_scopes=(),
                state=WorkspaceLeaseState.ACTIVE,
                takeover_evidence_ref=None,
                created_at=NOW,
                updated_at=NOW,
            )


if __name__ == "__main__":
    unittest.main()
