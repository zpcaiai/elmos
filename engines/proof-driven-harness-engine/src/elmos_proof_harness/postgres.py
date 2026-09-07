"""PostgreSQL 17 production implementation of the durable Store Protocol.

The psycopg 3 dependency is loaded only when this backend is constructed.
Importing the package and running the local SQLite test suite therefore remains
dependency-free.  Production startup must call :meth:`readiness` and fail
closed unless the driver, PostgreSQL 17 schema, forced RLS and a
``NOSUPERUSER``/``NOBYPASSRLS`` application role are all present.

Every application transaction sets ``app.tenant_id``, ``app.project_id`` and
``app.actor_id`` using a trusted :class:`SecurityContext` before tenant tables
are touched.  No value is extracted from a request payload.  The class reuses
the dialect-neutral, resource-qualified operations of :class:`SQLiteStore`;
only connection, transaction, bootstrap and error adaptation differ.
"""

from __future__ import annotations

import importlib
import hashlib
import hmac
import json
import os
import sqlite3
import threading
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .canonical import canonical_json, digest_bytes, digest_object, require_sha256_digest
from .contracts import SecurityContext
from .delta import _tool_result_commit_key
from .delta_storage import (
    CapabilityLeaseRecord,
    CapabilityLeaseState,
    CapabilityRevocationReason,
    CapabilityUseDenialReason,
    DurableEventRegistrationRecord,
    DurableEventInstanceRecord,
    DurableEventInstanceState,
    DurableEventSemantics,
    EnvironmentAttachmentRecord,
    EnvironmentAttachmentState,
    EventCompatibility,
    EventCompatibilityDecision,
    EventOwnerChangeAction,
    DurableEventOwnerChangePreflight,
    ExecutorGenerationRecord,
    ExecutorGenerationState,
    ExecutorReplacementEffectKind,
    ExecutorReplacementEffectRecord,
    ExecutorReplacementEffectState,
    InterceptorCommitRecord,
    HostSignedEnvelope,
    PendingToolCallBindingRecord,
    PendingToolCallBindingState,
    RuntimeAuthorityCapabilityReceiptRecord,
    RuntimeAssuranceClaimDisposition,
    RuntimeAssuranceInvocationClaimRecord,
    RuntimeAssuranceInvocationState,
    RuntimeAssuranceScopeSnapshot,
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
from .errors import (
    AuthorizationError,
    ConflictError,
    HarnessError,
    IntegrityError,
    NotFoundError,
    StoreError,
    ValidationError,
)
from .storage import (
    POSTGRES_DELTA_MIGRATION_NAME,
    POSTGRES_DELTA_MIGRATION_SOURCE_DIGEST,
    POSTGRES_DELTA_SCHEMA_VERSION,
    POSTGRES_MIGRATION_SOURCE_DIGEST,
    POSTGRES_SCHEMA_VERSION,
    StorageReadiness,
    StorageStatus,
)
from .store import SQLiteStore, _iso


_RUNTIME_TABLE_COUNT = 22
_DELTA_RELATION_NAMES = (
    "tool_result_commits",
    "step_execution_plans",
    "step_plan_tool_bindings",
    "pending_tool_call_bindings",
    "runtime_authority_capability_receipts",
    "subagent_budget_reservation_bindings",
    "capability_leases",
    "executor_generations",
    "environment_attachments",
    "executor_replacement_effects",
    "workspace_leases",
    "durable_event_registrations",
    "durable_event_instances",
    "typed_ingress_records",
    "subagent_execution_specs",
    "runtime_assurance_invocation_receipts",
)
_DELTA_RUNTIME_TABLE_COUNT = len(_DELTA_RELATION_NAMES)
_DELTA_CONTROL_FUNCTION_NAMES = (
    "is_bounded_text_array",
    "is_valid_interceptor_chain",
    "is_valid_workspace_scopes",
    "canonical_jsonb_text",
    "append_runtime_assurance_event",
    "runtime_assurance_event_is_exact",
    "is_live_runtime_assurance_claim",
    "assert_runtime_application_writer",
    "guard_runtime_run_actor_identity",
    "assert_runtime_assurance_scope",
    "claim_runtime_assurance_invocation",
    "complete_runtime_assurance_invocation",
    "reconcile_runtime_assurance_invocation",
    "guard_tool_result_commit",
    "guard_step_execution_plan",
    "guard_step_plan_tool_binding",
    "guard_runtime_authority_capability_receipt",
    "guard_pending_tool_call_binding",
    "guard_subagent_budget_reservation",
    "guard_capability_lease",
    "guard_executor_generation",
    "guard_environment_attachment",
    "guard_executor_replacement_effect",
    "guard_workspace_lease",
    "guard_runtime_assurance_invocation_receipt",
    "guard_durable_event_instance",
    "guard_subagent_execution_spec",
    "consume_subagent_reservation_and_spec",
)
_SUBAGENT_CONSUME_FUNCTION_SIGNATURE = (
    "proof_harness_runtime.consume_subagent_reservation_and_spec("
    "text,text,text,text,bigint,bigint,text,text,text,text,text,text,text,"
    "timestamp with time zone,text,text,text)"
)
_DELTA_FUNCTION_SIGNATURES = (
    "proof_harness.current_tenant_key()",
    "proof_harness.current_project_key()",
    "proof_harness_runtime.is_bounded_text_array(jsonb,integer,integer)",
    "proof_harness_runtime.is_valid_interceptor_chain(jsonb)",
    "proof_harness_runtime.is_valid_workspace_scopes(jsonb)",
    "proof_harness_runtime.claim_runtime_assurance_invocation(text,text,text,text,bigint,bigint,text,text,text,text,bigint,timestamp with time zone)",
    "proof_harness_runtime.complete_runtime_assurance_invocation(text,text,text,text,bigint,bigint,text,text,text,text,bigint,text,text,timestamp with time zone)",
    "proof_harness_runtime.reconcile_runtime_assurance_invocation(text,text,text,text,bigint,bigint,text,text,text,text,bigint,text,text,text,timestamp with time zone)",
    _SUBAGENT_CONSUME_FUNCTION_SIGNATURE,
)
_APP_EXECUTE_FUNCTION_SIGNATURES = frozenset(
    {
        "proof_harness.current_tenant_key()",
        "proof_harness.current_project_key()",
        "proof_harness_runtime.is_bounded_text_array(jsonb,integer,integer)",
        "proof_harness_runtime.is_valid_interceptor_chain(jsonb)",
        "proof_harness_runtime.is_valid_workspace_scopes(jsonb)",
        "proof_harness_runtime.claim_runtime_assurance_invocation(text,text,text,text,bigint,bigint,text,text,text,text,bigint,timestamp with time zone)",
        "proof_harness_runtime.complete_runtime_assurance_invocation(text,text,text,text,bigint,bigint,text,text,text,text,bigint,text,text,timestamp with time zone)",
        "proof_harness_runtime.reconcile_runtime_assurance_invocation(text,text,text,text,bigint,bigint,text,text,text,text,bigint,text,text,text,timestamp with time zone)",
    }
)
_AUTHORITY_EXECUTE_FUNCTION_SIGNATURES = frozenset(
    {
        *(_DELTA_FUNCTION_SIGNATURES[:5]),
        _SUBAGENT_CONSUME_FUNCTION_SIGNATURE,
    }
)
_MIGRATION_METADATA_RELATIONS = frozenset(
    {
        "schema_migrations",
        "migration_digest_ledger",
        "runtime_assurance_migrations",
        "runtime_assurance_migration_digest_ledger",
    }
)
_APP_BASE_INSERT_RELATIONS = frozenset(
    {
        "tenants",
        "projects",
        "actors",
        "runs",
        "control_plane_receipts",
        "external_effects",
        "idempotency_receipts",
        "evidence",
        "evidence_revocations",
        "audit_events",
        "outbox_events",
        "outbox_deliveries",
        "run_checkpoints",
        "effect_events",
        "metric_points",
    }
)
_APP_BASE_UPDATE_RELATIONS = frozenset(
    {"runs", "control_plane_receipts", "external_effects"}
)
_APP_BASE_DELETE_RELATIONS = frozenset({"control_plane_receipts"})
_APP_DELTA_INSERT_RELATIONS = frozenset(
    {
        "tool_result_commits",
        "step_execution_plans",
        "step_plan_tool_bindings",
        "pending_tool_call_bindings",
        "capability_leases",
        "executor_generations",
        "environment_attachments",
        "executor_replacement_effects",
        "workspace_leases",
        "durable_event_registrations",
        "durable_event_instances",
        "typed_ingress_records",
        "subagent_execution_specs",
        "runtime_assurance_invocation_receipts",
    }
)
_APP_DELTA_UPDATE_RELATIONS = frozenset(
    {
        "tool_result_commits",
        "step_execution_plans",
        "pending_tool_call_bindings",
        "capability_leases",
        "executor_generations",
        "environment_attachments",
        "executor_replacement_effects",
        "workspace_leases",
        "durable_event_instances",
        "runtime_assurance_invocation_receipts",
    }
)
_APP_BASE_SELECT_RELATIONS = frozenset(
    {
        "tenants",
        "projects",
        "actors",
        "runs",
        "control_plane_receipts",
        "external_effects",
        "idempotency_receipts",
        "evidence",
        "evidence_revocations",
        "audit_events",
        "outbox_events",
        "outbox_deliveries",
        "run_checkpoints",
        "effect_events",
        "metric_points",
    }
)
_APP_SELECT_RELATIONS = frozenset(
    {*_MIGRATION_METADATA_RELATIONS, *_APP_BASE_SELECT_RELATIONS, *_DELTA_RELATION_NAMES}
)
_APP_INSERT_RELATIONS = frozenset(
    {*_APP_BASE_INSERT_RELATIONS, *_APP_DELTA_INSERT_RELATIONS}
)
_APP_UPDATE_RELATIONS = frozenset(
    {*_APP_BASE_UPDATE_RELATIONS, *_APP_DELTA_UPDATE_RELATIONS}
)
_APP_DELETE_RELATIONS = _APP_BASE_DELETE_RELATIONS
_APP_RELATION_NAMES = tuple(sorted(_APP_SELECT_RELATIONS))
_AUTHORITY_SELECT_RELATIONS = frozenset(
    {
        "runs",
        "runtime_authority_capability_receipts",
        "subagent_budget_reservation_bindings",
        "step_execution_plans",
        "environment_attachments",
        "runtime_assurance_invocation_receipts",
        "subagent_execution_specs",
    }
)
_AUTHORITY_INSERT_RELATIONS = frozenset(
    {
        "runtime_authority_capability_receipts",
        "subagent_budget_reservation_bindings",
    }
)
_AUTHORITY_RELATION_NAMES = tuple((*_DELTA_RELATION_NAMES, "runs"))
_OWNER_ONLY_RUNTIME_RELATIONS = frozenset(
    {
        "scheduler_jobs",
        "scheduler_claim_events",
        "certification_assessments",
        "certification_gate_results",
        "certification_evidence_links",
        "certification_external_receipts",
        "certification_external_decisions",
        "certification_signature_revocations",
        "certification_events",
    }
)
_RAW_ACL_RELATION_NAMES = tuple(
    sorted(
        {
            *_APP_RELATION_NAMES,
            *_AUTHORITY_RELATION_NAMES,
            *_OWNER_ONLY_RUNTIME_RELATIONS,
        }
    )
)
_DELTA_PACKAGE_VERSION = "3.1.0"
_DRIVER_MAJOR_MINOR = (3, 2)
_MAX_CAPABILITY_LEASE_SECONDS = 15 * 60
_REQUIRED_EXECUTOR_REPLACEMENT_EFFECT_KINDS = frozenset(
    {
        ExecutorReplacementEffectKind.CAPABILITY_REVOCATION,
        ExecutorReplacementEffectKind.WORKSPACE_RECONCILIATION,
        ExecutorReplacementEffectKind.EXTERNAL_EFFECT_RECONCILIATION,
    }
)
_DELTA_RLS_CANONICAL_EXPRESSION = (
    "tenant_id=proof_harness.current_tenant_keyAND"
    "project_id=proof_harness.current_project_keyAND"
    "actor_id=current_setting'app.actor_id',trueAND"
    "run_id=current_setting'app.run_id',trueAND"
    "execution_epoch=current_setting'app.execution_epoch',trueAND"
    "fencing_generation=current_setting'app.fencing_generation',trueAND"
    "authority_revision=current_setting'app.authority_revision',trueAND"
    "revision_set_id=current_setting'app.revision_set_id',true"
)
_CATALOG_FINGERPRINT_KEYS = frozenset(
    {
        "relations",
        "columns",
        "constraints",
        "functions",
        "triggers",
        "indexes",
        "policies",
    }
)
_CATALOG_FINGERPRINT_SQL = """
WITH target_relations AS (
  SELECT c.oid,c.relname,c.relkind,c.relrowsecurity,c.relforcerowsecurity,
         pg_get_userbyid(c.relowner) AS owner_name
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='proof_harness_runtime' AND c.relname=ANY(?)
), target_functions AS (
  SELECT p.oid,p.proname,p.provolatile,p.proisstrict,p.prosecdef,p.proleakproof,
         p.proparallel,p.proconfig,l.lanname,
         pg_get_userbyid(p.proowner) AS owner_name
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  JOIN pg_language l ON l.oid=p.prolang
  WHERE n.nspname='proof_harness_runtime' AND p.proname=ANY(?)
)
SELECT jsonb_build_object(
  'relations',COALESCE((
    SELECT jsonb_agg(jsonb_build_array(relname,relkind,relrowsecurity,
                                      relforcerowsecurity,owner_name) ORDER BY relname)
    FROM target_relations
  ),'[]'::jsonb),
  'columns',COALESCE((
    SELECT jsonb_agg(jsonb_build_array(r.relname,a.attnum,a.attname,
             format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,
             a.attgenerated,COALESCE(pg_get_expr(d.adbin,d.adrelid,true),''),
             COALESCE(coll.collname,'')) ORDER BY r.relname,a.attnum)
    FROM target_relations r JOIN pg_attribute a ON a.attrelid=r.oid
    LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
    LEFT JOIN pg_collation coll ON coll.oid=a.attcollation
    WHERE a.attnum>0 AND NOT a.attisdropped
  ),'[]'::jsonb),
  'constraints',COALESCE((
    SELECT jsonb_agg(jsonb_build_array(r.relname,con.conname,con.contype,
             con.convalidated,con.condeferrable,con.condeferred,
             pg_get_constraintdef(con.oid,true)) ORDER BY r.relname,con.conname)
    FROM target_relations r JOIN pg_constraint con ON con.conrelid=r.oid
  ),'[]'::jsonb),
  'functions',COALESCE((
    SELECT jsonb_agg(jsonb_build_array(f.proname,
             pg_get_function_identity_arguments(f.oid),
             pg_get_function_result(f.oid),f.lanname,f.provolatile,f.proisstrict,
             f.prosecdef,f.proleakproof,f.proparallel,COALESCE(f.proconfig,ARRAY[]::text[]),
             f.owner_name,
             pg_get_functiondef(f.oid)) ORDER BY f.proname,f.oid)
    FROM target_functions f
  ),'[]'::jsonb),
  'triggers',COALESCE((
    SELECT jsonb_agg(jsonb_build_array(r.relname,t.tgname,t.tgenabled,
             pg_get_triggerdef(t.oid,true)) ORDER BY r.relname,t.tgname)
    FROM target_relations r JOIN pg_trigger t ON t.tgrelid=r.oid
    WHERE NOT t.tgisinternal
  ),'[]'::jsonb),
  'indexes',COALESCE((
    SELECT jsonb_agg(jsonb_build_array(r.relname,i.relname,x.indisprimary,
             x.indisunique,x.indisvalid,x.indisready,pg_get_indexdef(i.oid))
             ORDER BY r.relname,i.relname)
    FROM target_relations r JOIN pg_index x ON x.indrelid=r.oid
    JOIN pg_class i ON i.oid=x.indexrelid
  ),'[]'::jsonb),
  'policies',COALESCE((
    SELECT jsonb_agg(jsonb_build_array(p.tablename,p.policyname,p.permissive,
             p.roles,p.cmd,p.qual,p.with_check) ORDER BY p.tablename,p.policyname)
    FROM pg_policies p
    WHERE p.schemaname='proof_harness_runtime' AND p.tablename=ANY(?)
  ),'[]'::jsonb)
) AS catalog
"""
_RUNTIME_SCOPE_SQL = (
    "tenant_id=? AND project_id=? AND run_id=? AND actor_id=? "
    "AND execution_epoch=? AND fencing_generation=? "
    "AND authority_revision=? AND revision_set_id=?"
)

_TOOL_RESULT_COLUMNS = (
    "tenant_id,project_id,run_id,actor_id,invocation_id,call_id,attempt,"
    "execution_epoch,fencing_generation,authority_revision,revision_set_id,"
    "execution_plan_hash,environment_id,authority_snapshot_id,"
    "raw_result_ref,effective_result_ref,interceptor_chain,mutation_provenance_ref,"
    "failure_kind,failure_reason,state,created_at,updated_at,committed_at,"
    "published_at,aborted_at,recovery_evidence_ref"
)
_STEP_PLAN_COLUMNS = (
    "tenant_id,project_id,run_id,actor_id,execution_epoch,fencing_generation,"
    "authority_revision,revision_set_id,plan_id,step_id,plan_hash,model_snapshot,"
    "tool_plan,tool_contracts,handler_digests,capabilities,tool_mode,"
    "environment_snapshot_id,authority_snapshot_id,state,created_at,updated_at,"
    "finalized_at,activated_at,retired_at"
)
_PENDING_TOOL_CALL_COLUMNS = (
    "tenant_id,project_id,run_id,actor_id,execution_epoch,fencing_generation,"
    "authority_revision,revision_set_id,invocation_id,call_id,attempt,"
    "execution_plan_hash,environment_id,tool_id,authority_snapshot_id,state,"
    "created_at,updated_at,reconciled_at"
)
_AUTHORITY_RECEIPT_COLUMNS = (
    "tenant_id,project_id,run_id,actor_id,execution_epoch,fencing_generation,"
    "authority_revision,revision_set_id,operation_invocation_id,environment_id,"
    "authority_snapshot_id,capability_set,delegation_allowed,authority_digest,origin_skill_id,"
    "origin_skill_name,origin_owner_kernel,origin_execution_id,origin_step_id,"
    "extension_skill,origin_receipt_ref,origin_receipt_state,origin_receipt_digest,"
    "origin_signing_key_id,origin_signature_algorithm,origin_signature,"
    "host_envelope_payload_digest,host_envelope_digest,host_envelope_issuer,"
    "host_envelope_signing_key_id,host_envelope_signature_algorithm,"
    "host_envelope_signature,host_envelope_issued_at,host_envelope_verifier_id,"
    "host_envelope_verification_evidence_ref,"
    "host_envelope_verification_evidence_digest,host_envelope_verified_at"
)
_SUBAGENT_RESERVATION_COLUMNS = (
    "tenant_id,project_id,run_id,actor_id,execution_epoch,fencing_generation,"
    "authority_revision,revision_set_id,reservation_id,operation_invocation_id,"
    "parent_execution_id,environment_id,authority_snapshot_id,provider,model,"
    "reasoning_effort,child_authority,child_tools,max_output_tokens,max_cost_budget,"
    "wall_clock_deadline,tool_plan_hash,authority_envelope_digest,"
    "host_envelope_payload_digest,host_envelope_digest,host_envelope_issuer,"
    "host_envelope_signing_key_id,host_envelope_signature_algorithm,"
    "host_envelope_signature,host_envelope_issued_at,host_envelope_verifier_id,"
    "host_envelope_verification_evidence_ref,"
    "host_envelope_verification_evidence_digest,host_envelope_verified_at,"
    "state,created_at,updated_at,consumed_at,consumer_execution_id,"
    "consume_event_id,consume_payload_sha256"
)
_CAPABILITY_COLUMNS = (
    "tenant_id,project_id,run_id,actor_id,lease_id,invocation_id,environment_id,"
    "authority_snapshot_id,execution_epoch,fencing_generation,authority_revision,"
    "revision_set_id,capability_set,delegation_allowed,state,"
    "issued_at,expires_at,revoked_at,revocation_reason,updated_at"
)
_EXECUTOR_COLUMNS = (
    "tenant_id,project_id,actor_id,run_id,execution_epoch,fencing_generation,"
    "authority_revision,revision_set_id,environment_id,executor_identity,"
    "executor_generation,connection_epoch,state,live_probe_evidence_ref,created_at,"
    "updated_at,activated_at,retired_at,failed_at"
)
_ENVIRONMENT_ATTACHMENT_COLUMNS = (
    "tenant_id,project_id,actor_id,run_id,execution_epoch,fencing_generation,"
    "authority_revision,revision_set_id,server_id,environment_id,snapshot_id,"
    "previous_snapshot_id,generation,owner_authority_ref,parent_authority_ref,"
    "effective_permissions,settings_authority,settings_digest,state,created_at,"
    "updated_at,superseded_at"
)
_EXECUTOR_REPLACEMENT_EFFECT_COLUMNS = (
    "tenant_id,project_id,actor_id,run_id,execution_epoch,fencing_generation,"
    "authority_revision,revision_set_id,effect_id,environment_id,executor_generation,"
    "connection_epoch,kind,state,evidence_ref,created_at,updated_at,reconciled_at"
)
_WORKSPACE_COLUMNS = (
    "tenant_id,project_id,actor_id,run_id,execution_epoch,fencing_generation,"
    "authority_revision,revision_set_id,workspace_id,owner_execution_id,generation,"
    "repository_id,base_revision,write_scopes,state,takeover_evidence_ref,"
    "created_at,updated_at,retired_at"
)
_EVENT_REGISTRATION_COLUMNS = (
    "tenant_id,project_id,actor_id,run_id,execution_epoch,fencing_generation,"
    "authority_revision,revision_set_id,event_type,owner,schema_version,semantics,"
    "compatibility,validator_ref,upgrader_ref,projections,registration_hash,registered_at"
)
_DURABLE_EVENT_INSTANCE_COLUMNS = (
    "tenant_id,project_id,actor_id,run_id,execution_epoch,fencing_generation,"
    "authority_revision,revision_set_id,event_id,event_type,schema_version,payload_ref,"
    "payload_digest,causation_id,correlation_id,parent_event_id,source_scope,fork_lineage,"
    "compatibility_decision,state,skip_reason,created_at,updated_at,processed_at"
)
_TYPED_INGRESS_COLUMNS = (
    "tenant_id,project_id,run_id,actor_id,ingress_id,producer_execution_id,"
    "deduplication_key,kind,envelope_digest,payload_ref,originating_call_id,"
    "causation_id,correlation_id,execution_epoch,fencing_generation,authority_revision,"
    "revision_set_id,occurred_at,recorded_at,persisted_sequence"
)
_TYPED_INGRESS_INSERT_COLUMNS = (
    "tenant_id,project_id,run_id,actor_id,ingress_id,producer_execution_id,"
    "deduplication_key,kind,envelope_digest,payload_ref,originating_call_id,"
    "causation_id,correlation_id,execution_epoch,fencing_generation,authority_revision,"
    "revision_set_id,occurred_at,recorded_at"
)
_SUBAGENT_SPEC_COLUMNS = (
    "tenant_id,project_id,run_id,actor_id,invocation_id,parent_execution_id,"
    "provider,model,reasoning_effort,authority_snapshot_id,environment_id,"
    "budget_reservation_id,max_output_tokens,tool_plan_hash,child_authority,child_tools,"
    "cost_budget,wall_clock_deadline,spec_hash,execution_epoch,fencing_generation,"
    "authority_revision,revision_set_id,recorded_at,state,consumer_execution_id,"
    "consumed_at,updated_at"
)
_INVOCATION_RECEIPT_COLUMNS = (
    "tenant_id,project_id,run_id,actor_id,execution_epoch,fencing_generation,"
    "authority_revision,revision_set_id,invocation_id,request_digest,claim_epoch,"
    "claim_backend_pid,claim_lock_key,state,result_ref,result_digest,"
    "claimed_at,updated_at,completed_at,"
    "recovery_evidence_ref"
)


@dataclass(frozen=True, slots=True)
class _ActiveInvocationFence:
    tenant_id: str
    project_id: str
    actor_id: str
    run_id: str
    execution_epoch: int
    fencing_generation: int
    authority_revision: str
    revision_set_id: str
    invocation_id: str
    request_digest: str
    claim_epoch: int
    connection: Any


_ACTIVE_INVOCATION_FENCE: ContextVar[_ActiveInvocationFence | None] = ContextVar(
    "elmos_active_runtime_assurance_invocation_fence",
    default=None,
)


def _port_text(value: str, field: str, *, maximum: int = 2048) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.encode("utf-8")) > maximum
    ):
        raise ValidationError(f"{field} is invalid", details={"field": field})
    return value


def _port_positive(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError(
            f"{field} must be a positive integer", details={"field": field}
        )
    return value


def _port_time(
    value: datetime | None, field: str, *, default_now: bool = False
) -> datetime:
    candidate = datetime.now(UTC) if value is None and default_now else value
    if (
        not isinstance(candidate, datetime)
        or candidate.tzinfo is None
        or candidate.utcoffset() is None
    ):
        raise ValidationError(
            f"{field} must be timezone-aware", details={"field": field}
        )
    return candidate.astimezone(UTC)


def _port_strings(
    value: Sequence[str],
    field: str,
    *,
    maximum_items: int = 256,
    maximum_item_bytes: int = 512,
) -> tuple[str, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) > maximum_items
    ):
        raise ValidationError(f"{field} is invalid", details={"field": field})
    normalized = tuple(
        _port_text(item, field, maximum=maximum_item_bytes) for item in value
    )
    if len(normalized) != len(set(normalized)):
        raise ValidationError(f"{field} contains duplicates", details={"field": field})
    return normalized


def _port_workspace_scopes(value: Sequence[str]) -> tuple[str, ...]:
    scopes = _port_strings(
        value,
        "write_scopes",
        maximum_item_bytes=2048,
    )
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


def _workspace_scopes_overlap(left: Sequence[str], right: Sequence[str]) -> bool:
    return any(
        left_scope == right_scope
        or left_scope.startswith(right_scope.rstrip("/") + "/")
        or right_scope.startswith(left_scope.rstrip("/") + "/")
        for left_scope in left
        for right_scope in right
    )


def _exact_succeeded_executor_replacement_effect_ids(
    rows: Sequence[Mapping[str, Any]],
) -> dict[ExecutorReplacementEffectKind, str] | None:
    if len(rows) != len(_REQUIRED_EXECUTOR_REPLACEMENT_EFFECT_KINDS):
        return None
    observed: dict[ExecutorReplacementEffectKind, str] = {}
    for row in rows:
        try:
            kind = ExecutorReplacementEffectKind(str(row["kind"]))
            state = ExecutorReplacementEffectState(str(row["state"]))
            effect_id = str(row["effect_id"])
        except (KeyError, TypeError, ValueError):
            return None
        if (
            not effect_id
            or kind in observed
            or state is not ExecutorReplacementEffectState.SUCCEEDED
        ):
            return None
        observed[kind] = effect_id
    if frozenset(observed) != _REQUIRED_EXECUTOR_REPLACEMENT_EFFECT_KINDS:
        return None
    return observed


def _control_catalog_fingerprint(cursor: Any) -> str:
    relation_names = (
        "runtime_assurance_migrations",
        "runtime_assurance_migration_digest_ledger",
        *_DELTA_RELATION_NAMES,
    )
    row = cursor.execute(
        _CATALOG_FINGERPRINT_SQL,
        (
            list(relation_names),
            list(_DELTA_CONTROL_FUNCTION_NAMES),
            list(relation_names),
        ),
    ).fetchone()
    if row is None:
        raise IntegrityError(
            "PostgreSQL returned no runtime-assurance control catalog",
            code="DELTA_STORAGE_DRIFT",
        )
    candidate: Any = row["catalog"]
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise IntegrityError(
                "PostgreSQL runtime-assurance control catalog is invalid JSON",
                code="DELTA_STORAGE_DRIFT",
            ) from exc
    if not isinstance(candidate, dict) or set(candidate) != _CATALOG_FINGERPRINT_KEYS:
        raise IntegrityError(
            "PostgreSQL runtime-assurance control catalog shape drifted",
            code="DELTA_STORAGE_DRIFT",
        )
    if any(not isinstance(candidate[key], list) for key in _CATALOG_FINGERPRINT_KEYS):
        raise IntegrityError(
            "PostgreSQL runtime-assurance control catalog collections drifted",
            code="DELTA_STORAGE_DRIFT",
        )
    if (
        len(candidate["relations"]) != len(relation_names)
        or len(candidate["functions"]) != len(_DELTA_CONTROL_FUNCTION_NAMES)
        or len(candidate["triggers"]) != 2 * len(_DELTA_RELATION_NAMES)
        or len(candidate["policies"]) != len(_DELTA_RELATION_NAMES)
        or not candidate["columns"]
        or not candidate["constraints"]
        or not candidate["indexes"]
    ):
        raise IntegrityError(
            "PostgreSQL runtime-assurance control catalog inventory is incomplete",
            code="DELTA_STORAGE_DRIFT",
        )
    encoded = canonical_json(candidate).encode("utf-8")
    return "sha256:" + hashlib.sha256(
        b"elmos.proof-harness.v3.1\0postgres-control-catalog\0" + encoded
    ).hexdigest()


def _port_run_context(context: SecurityContext) -> None:
    if not isinstance(context, SecurityContext):
        raise AuthorizationError(
            "trusted security context is required",
            code="TRUSTED_CONTEXT_REQUIRED",
        )
    if context.run_id is None:
        raise ValidationError(
            "runtime-assurance operations require a run-bound context"
        )
    _port_text(context.tenant_id, "tenant_id", maximum=255)
    _port_text(context.project_id, "project_id", maximum=255)
    _port_text(context.actor_id, "actor_id", maximum=512)
    _port_text(context.run_id, "run_id", maximum=512)
    _port_positive(context.execution_epoch, "execution_epoch")
    _port_positive(context.fencing_generation, "fencing_generation")
    if context.authority_revision is None:
        raise AuthorizationError(
            "runtime-assurance persistence requires an authority revision",
            code="AUTHORITY_REVISION_REQUIRED",
        )
    require_sha256_digest(
        context.authority_revision,
        field="authority_revision",
    )


def _port_context(context: SecurityContext, revision_set_id: str) -> None:
    _port_run_context(context)
    require_sha256_digest(revision_set_id, field="revision_set_id")


def _port_authority_snapshot(context: SecurityContext, value: str) -> str:
    authority_snapshot_id = _port_text(
        value,
        "authority_snapshot_id",
        maximum=512,
    )
    require_sha256_digest(
        authority_snapshot_id,
        field="authority_snapshot_id",
    )
    assert context.authority_revision is not None
    if not hmac.compare_digest(authority_snapshot_id, context.authority_revision):
        raise ConflictError(
            "authority snapshot does not match the trusted context",
            code="STALE_AUTHORITY",
        )
    return authority_snapshot_id


def _runtime_scope_parameters(
    context: SecurityContext,
    revision_set_id: str,
) -> tuple[Any, ...]:
    assert context.run_id is not None
    assert context.authority_revision is not None
    return (
        context.tenant_id,
        context.project_id,
        context.run_id,
        context.actor_id,
        context.execution_epoch,
        context.fencing_generation,
        context.authority_revision,
        revision_set_id,
    )


def _invocation_lock_key(
    context: SecurityContext,
    revision_set_id: str,
    invocation_id: str,
) -> int:
    lock_digest = digest_object(
        {
            "tenantId": context.tenant_id,
            "projectId": context.project_id,
            "runId": context.run_id,
            "actorId": context.actor_id,
            "executionEpoch": context.execution_epoch,
            "fencingGeneration": context.fencing_generation,
            "authorityRevision": context.authority_revision,
            "revisionSetId": revision_set_id,
            "invocationId": invocation_id,
        },
        domain="delta-runtime-invocation-lock",
    )
    unsigned = int(lock_digest.removeprefix("sha256:")[:16], 16)
    return unsigned if unsigned < 2**63 else unsigned - 2**64


def _workspace_lock_key(
    context: SecurityContext,
    repository_id: str,
    base_revision: str,
) -> int:
    lock_digest = digest_object(
        {
            "tenantId": context.tenant_id,
            "projectId": context.project_id,
            "repositoryId": repository_id,
            "baseRevision": base_revision,
        },
        domain="delta-workspace-authority-lock",
    )
    unsigned = int(lock_digest.removeprefix("sha256:")[:16], 16)
    return unsigned if unsigned < 2**63 else unsigned - 2**64


def _decoded_json(value: Any, field: str) -> Any:
    candidate = value
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise IntegrityError(
                f"stored {field} is not valid JSON", code="DELTA_STORAGE_DRIFT"
            ) from exc
    return candidate


def _json_object(value: Any, field: str) -> Mapping[str, Any]:
    candidate = _decoded_json(value, field)
    if not isinstance(candidate, Mapping):
        raise IntegrityError(
            f"stored {field} is not an object", code="DELTA_STORAGE_DRIFT"
        )
    return candidate


def _json_array(value: Any, field: str) -> tuple[Any, ...]:
    candidate = _decoded_json(value, field)
    if not isinstance(candidate, (list, tuple)):
        raise IntegrityError(
            f"stored {field} is not an array", code="DELTA_STORAGE_DRIFT"
        )
    return tuple(candidate)


def _stored_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise IntegrityError(
            f"stored {field} is not boolean", code="DELTA_STORAGE_DRIFT"
        )
    return value


def _host_envelope_record(row: Mapping[str, Any]) -> HostSignedEnvelope:
    return HostSignedEnvelope(
        payload_digest=str(row["host_envelope_payload_digest"]),
        envelope_digest=str(row["host_envelope_digest"]),
        issuer=str(row["host_envelope_issuer"]),
        signing_key_id=str(row["host_envelope_signing_key_id"]),
        signature_algorithm=str(row["host_envelope_signature_algorithm"]),
        signature=str(row["host_envelope_signature"]),
        issued_at=row["host_envelope_issued_at"],
        verifier_id=str(row["host_envelope_verifier_id"]),
        verification_evidence_ref=str(
            row["host_envelope_verification_evidence_ref"]
        ),
        verification_evidence_digest=str(
            row["host_envelope_verification_evidence_digest"]
        ),
        verified_at=row["host_envelope_verified_at"],
    )


def _tool_result_record(row: Mapping[str, Any]) -> ToolResultCommitRecord:
    chain: list[InterceptorCommitRecord] = []
    for item in _json_array(row["interceptor_chain"], "interceptor_chain"):
        if not isinstance(item, Mapping) or set(item) != {
            "interceptorId",
            "version",
            "decisionHash",
        }:
            raise IntegrityError(
                "stored interceptor chain is invalid", code="DELTA_STORAGE_DRIFT"
            )
        chain.append(
            InterceptorCommitRecord(
                str(item["interceptorId"]),
                str(item["version"]),
                str(item["decisionHash"]),
            )
        )
    return ToolResultCommitRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        run_id=str(row["run_id"]),
        actor_id=str(row["actor_id"]),
        invocation_id=str(row["invocation_id"]),
        call_id=str(row["call_id"]),
        attempt=int(row["attempt"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        execution_plan_hash=str(row["execution_plan_hash"]),
        environment_id=str(row["environment_id"]),
        authority_snapshot_id=str(row["authority_snapshot_id"]),
        raw_result_ref=str(row["raw_result_ref"]),
        effective_result_ref=str(row["effective_result_ref"]),
        interceptor_chain=tuple(chain),
        mutation_provenance_ref=(
            None
            if row["mutation_provenance_ref"] is None
            else str(row["mutation_provenance_ref"])
        ),
        failure_kind=(
            None
            if row["failure_kind"] is None
            else ToolResultFailureKind(str(row["failure_kind"]))
        ),
        failure_reason=(
            None if row["failure_reason"] is None else str(row["failure_reason"])
        ),
        state=ToolResultCommitState(str(row["state"])),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        committed_at=row["committed_at"],
        published_at=row["published_at"],
        aborted_at=row["aborted_at"],
        recovery_evidence_ref=(
            None
            if row["recovery_evidence_ref"] is None
            else str(row["recovery_evidence_ref"])
        ),
    )


def _pending_tool_call_record(
    row: Mapping[str, Any],
) -> PendingToolCallBindingRecord:
    return PendingToolCallBindingRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        run_id=str(row["run_id"]),
        actor_id=str(row["actor_id"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        invocation_id=str(row["invocation_id"]),
        call_id=str(row["call_id"]),
        attempt=int(row["attempt"]),
        execution_plan_hash=str(row["execution_plan_hash"]),
        environment_id=str(row["environment_id"]),
        tool_id=str(row["tool_id"]),
        authority_snapshot_id=str(row["authority_snapshot_id"]),
        state=PendingToolCallBindingState(str(row["state"])),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        reconciled_at=row["reconciled_at"],
    )


def _authority_receipt_record(
    row: Mapping[str, Any],
) -> RuntimeAuthorityCapabilityReceiptRecord:
    return RuntimeAuthorityCapabilityReceiptRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        run_id=str(row["run_id"]),
        actor_id=str(row["actor_id"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        operation_invocation_id=str(row["operation_invocation_id"]),
        environment_id=str(row["environment_id"]),
        authority_snapshot_id=str(row["authority_snapshot_id"]),
        capabilities=tuple(
            str(item) for item in _json_array(row["capability_set"], "capability_set")
        ),
        delegation_allowed=bool(row["delegation_allowed"]),
        authority_digest=str(row["authority_digest"]),
        origin_skill_id=str(row["origin_skill_id"]),
        origin_skill_name=str(row["origin_skill_name"]),
        origin_owner_kernel=str(row["origin_owner_kernel"]),
        origin_execution_id=str(row["origin_execution_id"]),
        origin_step_id=str(row["origin_step_id"]),
        extension_skill=str(row["extension_skill"]),
        origin_receipt_ref=str(row["origin_receipt_ref"]),
        origin_receipt_state=str(row["origin_receipt_state"]),
        origin_receipt_digest=str(row["origin_receipt_digest"]),
        origin_signing_key_id=str(row["origin_signing_key_id"]),
        origin_signature_algorithm=str(row["origin_signature_algorithm"]),
        origin_signature=str(row["origin_signature"]),
        host_envelope=_host_envelope_record(row),
    )


def _subagent_reservation_record(
    row: Mapping[str, Any],
) -> SubagentBudgetReservationBindingRecord:
    return SubagentBudgetReservationBindingRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        run_id=str(row["run_id"]),
        actor_id=str(row["actor_id"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        reservation_id=str(row["reservation_id"]),
        operation_invocation_id=str(row["operation_invocation_id"]),
        parent_execution_id=str(row["parent_execution_id"]),
        environment_id=str(row["environment_id"]),
        authority_snapshot_id=str(row["authority_snapshot_id"]),
        provider=str(row["provider"]),
        model=str(row["model"]),
        reasoning_effort=str(row["reasoning_effort"]),
        child_authority=tuple(
            str(item)
            for item in _json_array(row["child_authority"], "child_authority")
        ),
        child_tools=tuple(
            str(item) for item in _json_array(row["child_tools"], "child_tools")
        ),
        max_output_tokens=int(row["max_output_tokens"]),
        max_cost_budget=str(row["max_cost_budget"]),
        wall_clock_deadline=row["wall_clock_deadline"],
        tool_plan_hash=str(row["tool_plan_hash"]),
        authority_envelope_digest=str(row["authority_envelope_digest"]),
        host_envelope=_host_envelope_record(row),
        state=SubagentBudgetReservationState(str(row["state"])),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        consumed_at=row["consumed_at"],
    )


def _step_plan_record(row: Mapping[str, Any]) -> StepExecutionPlanRecord:
    return StepExecutionPlanRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        run_id=str(row["run_id"]),
        actor_id=str(row["actor_id"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        plan_id=str(row["plan_id"]),
        step_id=str(row["step_id"]),
        plan_hash=str(row["plan_hash"]),
        model_snapshot=_json_object(row["model_snapshot"], "model_snapshot"),
        tool_plan=_json_object(row["tool_plan"], "tool_plan"),
        tool_contracts=_json_object(row["tool_contracts"], "tool_contracts"),
        handler_digests={
            str(key): str(value)
            for key, value in _json_object(
                row["handler_digests"],
                "handler_digests",
            ).items()
        },
        capabilities=tuple(
            str(item) for item in _json_array(row["capabilities"], "capabilities")
        ),
        tool_mode=str(row["tool_mode"]),
        environment_snapshot_id=str(row["environment_snapshot_id"]),
        authority_snapshot_id=str(row["authority_snapshot_id"]),
        state=StepPlanState(str(row["state"])),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        finalized_at=row["finalized_at"],
        activated_at=row["activated_at"],
        retired_at=row["retired_at"],
    )


def _capability_record(row: Mapping[str, Any]) -> CapabilityLeaseRecord:
    return CapabilityLeaseRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        run_id=str(row["run_id"]),
        actor_id=str(row["actor_id"]),
        lease_id=str(row["lease_id"]),
        invocation_id=str(row["invocation_id"]),
        environment_id=str(row["environment_id"]),
        authority_snapshot_id=str(row["authority_snapshot_id"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        capabilities=tuple(
            str(item) for item in _json_array(row["capability_set"], "capability_set")
        ),
        delegation_allowed=_stored_bool(
            row["delegation_allowed"], "delegation_allowed"
        ),
        state=CapabilityLeaseState(str(row["state"])),
        issued_at=row["issued_at"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
        revocation_reason=(
            None
            if row["revocation_reason"] is None
            else CapabilityRevocationReason(str(row["revocation_reason"]))
        ),
        updated_at=row["updated_at"],
    )


def _executor_record(row: Mapping[str, Any]) -> ExecutorGenerationRecord:
    return ExecutorGenerationRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        actor_id=str(row["actor_id"]),
        run_id=str(row["run_id"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        environment_id=str(row["environment_id"]),
        executor_identity=str(row["executor_identity"]),
        executor_generation=int(row["executor_generation"]),
        connection_epoch=int(row["connection_epoch"]),
        state=ExecutorGenerationState(str(row["state"])),
        live_probe_evidence_ref=(
            None
            if row["live_probe_evidence_ref"] is None
            else str(row["live_probe_evidence_ref"])
        ),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        activated_at=row["activated_at"],
        retired_at=row["retired_at"],
        failed_at=row["failed_at"],
    )


def _environment_attachment_record(
    row: Mapping[str, Any],
) -> EnvironmentAttachmentRecord:
    return EnvironmentAttachmentRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        actor_id=str(row["actor_id"]),
        run_id=str(row["run_id"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        server_id=str(row["server_id"]),
        environment_id=str(row["environment_id"]),
        snapshot_id=str(row["snapshot_id"]),
        previous_snapshot_id=(
            None
            if row["previous_snapshot_id"] is None
            else str(row["previous_snapshot_id"])
        ),
        generation=int(row["generation"]),
        owner_authority_ref=str(row["owner_authority_ref"]),
        parent_authority_ref=str(row["parent_authority_ref"]),
        effective_permissions=tuple(
            str(item)
            for item in _json_array(
                row["effective_permissions"],
                "effective_permissions",
            )
        ),
        settings_authority=_json_object(
            row["settings_authority"], "settings_authority"
        ),
        settings_digest=str(row["settings_digest"]),
        state=EnvironmentAttachmentState(str(row["state"])),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        superseded_at=row["superseded_at"],
    )


def _executor_replacement_effect_record(
    row: Mapping[str, Any],
) -> ExecutorReplacementEffectRecord:
    return ExecutorReplacementEffectRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        actor_id=str(row["actor_id"]),
        run_id=str(row["run_id"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        effect_id=str(row["effect_id"]),
        environment_id=str(row["environment_id"]),
        executor_generation=int(row["executor_generation"]),
        connection_epoch=int(row["connection_epoch"]),
        kind=ExecutorReplacementEffectKind(str(row["kind"])),
        state=ExecutorReplacementEffectState(str(row["state"])),
        evidence_ref=None if row["evidence_ref"] is None else str(row["evidence_ref"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        reconciled_at=row["reconciled_at"],
    )


def _workspace_record(row: Mapping[str, Any]) -> WorkspaceLeaseRecord:
    return WorkspaceLeaseRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        actor_id=str(row["actor_id"]),
        run_id=str(row["run_id"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        workspace_id=str(row["workspace_id"]),
        owner_execution_id=str(row["owner_execution_id"]),
        generation=int(row["generation"]),
        repository_id=str(row["repository_id"]),
        base_revision=str(row["base_revision"]),
        write_scopes=tuple(
            str(item) for item in _json_array(row["write_scopes"], "write_scopes")
        ),
        state=WorkspaceLeaseState(str(row["state"])),
        takeover_evidence_ref=(
            None
            if row["takeover_evidence_ref"] is None
            else str(row["takeover_evidence_ref"])
        ),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        retired_at=row["retired_at"],
    )


def _event_registration_record(
    row: Mapping[str, Any],
) -> DurableEventRegistrationRecord:
    return DurableEventRegistrationRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        actor_id=str(row["actor_id"]),
        run_id=str(row["run_id"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        event_type=str(row["event_type"]),
        owner=str(row["owner"]),
        schema_version=int(row["schema_version"]),
        semantics=DurableEventSemantics(str(row["semantics"])),
        compatibility=EventCompatibility(str(row["compatibility"])),
        validator_ref=str(row["validator_ref"]),
        upgrader_ref=str(row["upgrader_ref"]),
        projections=tuple(
            str(item) for item in _json_array(row["projections"], "projections")
        ),
        registration_hash=str(row["registration_hash"]),
        registered_at=row["registered_at"],
    )


def _durable_event_instance_record(
    row: Mapping[str, Any],
) -> DurableEventInstanceRecord:
    return DurableEventInstanceRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        actor_id=str(row["actor_id"]),
        run_id=str(row["run_id"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        event_id=str(row["event_id"]),
        event_type=str(row["event_type"]),
        schema_version=int(row["schema_version"]),
        payload_ref=str(row["payload_ref"]),
        payload_digest=str(row["payload_digest"]),
        causation_id=None if row["causation_id"] is None else str(row["causation_id"]),
        correlation_id=str(row["correlation_id"]),
        parent_event_id=(
            None if row["parent_event_id"] is None else str(row["parent_event_id"])
        ),
        source_scope=_json_object(row["source_scope"], "source_scope"),
        fork_lineage=tuple(
            str(item) for item in _json_array(row["fork_lineage"], "fork_lineage")
        ),
        compatibility_decision=EventCompatibilityDecision(
            str(row["compatibility_decision"])
        ),
        state=DurableEventInstanceState(str(row["state"])),
        skip_reason=None if row["skip_reason"] is None else str(row["skip_reason"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        processed_at=row["processed_at"],
    )


def _typed_ingress_record(row: Mapping[str, Any]) -> TypedIngressRecord:
    return TypedIngressRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        run_id=str(row["run_id"]),
        actor_id=str(row["actor_id"]),
        ingress_id=str(row["ingress_id"]),
        producer_execution_id=str(row["producer_execution_id"]),
        deduplication_key=str(row["deduplication_key"]),
        kind=TypedIngressKind(str(row["kind"])),
        envelope_digest=str(row["envelope_digest"]),
        payload_ref=str(row["payload_ref"]),
        originating_call_id=(
            None
            if row["originating_call_id"] is None
            else str(row["originating_call_id"])
        ),
        causation_id=None if row["causation_id"] is None else str(row["causation_id"]),
        correlation_id=str(row["correlation_id"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        occurred_at=row["occurred_at"],
        recorded_at=row["recorded_at"],
        persisted_sequence=int(row["persisted_sequence"]),
    )


def _subagent_spec_record(row: Mapping[str, Any]) -> SubagentExecutionSpecRecord:
    return SubagentExecutionSpecRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        run_id=str(row["run_id"]),
        actor_id=str(row["actor_id"]),
        invocation_id=str(row["invocation_id"]),
        parent_execution_id=str(row["parent_execution_id"]),
        provider=str(row["provider"]),
        model=str(row["model"]),
        reasoning_effort=str(row["reasoning_effort"]),
        authority_snapshot_id=str(row["authority_snapshot_id"]),
        environment_id=str(row["environment_id"]),
        budget_reservation_id=str(row["budget_reservation_id"]),
        max_output_tokens=int(row["max_output_tokens"]),
        tool_plan_hash=str(row["tool_plan_hash"]),
        child_authority=tuple(
            str(item) for item in _json_array(row["child_authority"], "child_authority")
        ),
        child_tools=tuple(
            str(item) for item in _json_array(row["child_tools"], "child_tools")
        ),
        cost_budget=str(row["cost_budget"]),
        wall_clock_deadline=row["wall_clock_deadline"],
        spec_hash=str(row["spec_hash"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        recorded_at=row["recorded_at"],
        state=SubagentExecutionSpecState(str(row["state"])),
        consumer_execution_id=(
            None
            if row["consumer_execution_id"] is None
            else str(row["consumer_execution_id"])
        ),
        consumed_at=row["consumed_at"],
        updated_at=row["updated_at"],
    )


def _invocation_claim_record(
    row: Mapping[str, Any],
    disposition: RuntimeAssuranceClaimDisposition,
) -> RuntimeAssuranceInvocationClaimRecord:
    return RuntimeAssuranceInvocationClaimRecord(
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        run_id=str(row["run_id"]),
        actor_id=str(row["actor_id"]),
        execution_epoch=int(row["execution_epoch"]),
        fencing_generation=int(row["fencing_generation"]),
        authority_revision=str(row["authority_revision"]),
        revision_set_id=str(row["revision_set_id"]),
        invocation_id=str(row["invocation_id"]),
        request_digest=str(row["request_digest"]),
        claim_epoch=int(row["claim_epoch"]),
        state=RuntimeAssuranceInvocationState(str(row["state"])),
        disposition=disposition,
        result_ref=None if row["result_ref"] is None else str(row["result_ref"]),
        result_digest=(
            None if row["result_digest"] is None else str(row["result_digest"])
        ),
        claimed_at=row["claimed_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
        recovery_evidence_ref=(
            None
            if row["recovery_evidence_ref"] is None
            else str(row["recovery_evidence_ref"])
        ),
    )


class _PostgresRow(Mapping[str, Any]):
    """Small sqlite-row-compatible wrapper around a psycopg dict row."""

    def __init__(self, values: Mapping[str, Any]) -> None:
        self._values = values

    def __getitem__(self, key: str) -> Any:
        value = self._values[key]
        # SQLite returns JSON columns as text.  Normalizing here lets the common
        # Store implementation perform one canonical decoding path.
        if isinstance(value, (dict, list)):
            return json.dumps(
                value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            )
        return value

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


class _PostgresCursor:
    """Translate DB-API parameter markers and expose sqlite-compatible rows."""

    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount)

    def execute(self, statement: str, parameters: Any = None) -> "_PostgresCursor":
        sql = statement.replace("?", "%s")
        try:
            self._cursor.execute(sql, parameters)
        except HarnessError:
            # Preserve domain failures raised by deterministic test/fake
            # cursors and by adapter layers; only translate DB-API failures.
            raise
        except Exception as exc:  # psycopg is intentionally an optional import
            _raise_mapped_database_error(exc)
        return self

    def fetchone(self) -> _PostgresRow | None:
        row = self._cursor.fetchone()
        return None if row is None else _PostgresRow(row)

    def fetchall(self) -> list[_PostgresRow]:
        return [_PostgresRow(row) for row in self._cursor.fetchall()]

    def close(self) -> None:
        self._cursor.close()


def _raise_mapped_database_error(exc: Exception) -> None:
    """Map psycopg failures without importing psycopg exception classes."""

    sqlstate = str(getattr(exc, "sqlstate", "") or "")
    details = {"sqlstate": sqlstate} if sqlstate else {}
    if sqlstate == "40001" or sqlstate == "40P01":
        raise ConflictError(
            "PostgreSQL transaction must be retried",
            code="TRANSACTION_CONFLICT",
            details=details,
        ) from exc
    if sqlstate.startswith("23"):
        # Common store methods already translate expected FK/unique failures
        # from sqlite3.IntegrityError into stable domain errors.
        raise sqlite3.IntegrityError("PostgreSQL integrity constraint failed") from exc
    if sqlstate == "42501":
        raise AuthorizationError(
            "PostgreSQL RLS or privilege check denied the operation", details=details
        ) from exc
    if sqlstate == "55000":
        raise IntegrityError(
            "append-only PostgreSQL relation rejected mutation",
            code="IMMUTABLE_RELATION",
            details=details,
        ) from exc
    raise StoreError(
        "PostgreSQL operation failed", code="POSTGRES_OPERATION_FAILED", details=details
    ) from exc


def postgres_driver_readiness() -> StorageReadiness:
    """Report optional-driver availability without raising or opening a socket."""

    try:
        driver = importlib.import_module("psycopg")
    except ImportError:
        return StorageReadiness(
            status=StorageStatus.NOT_CONFIGURED,
            reason="optional psycopg 3.2 driver is not installed; install the 'postgres' extra",
            backend="postgresql",
        )
    version = str(getattr(driver, "__version__", "unknown"))
    try:
        major_minor = tuple(int(part) for part in version.split(".")[:2])
    except ValueError:
        major_minor = ()
    if major_minor != _DRIVER_MAJOR_MINOR:
        return StorageReadiness(
            status=StorageStatus.NOT_READY,
            reason="unsupported psycopg version; production requires the pinned 3.2 line",
            backend="postgresql",
            server_version=f"psycopg/{version}",
        )
    return StorageReadiness(
        status=StorageStatus.READY,
        reason="optional psycopg driver is available",
        backend="postgresql",
        server_version=f"psycopg/{version}",
    )


class PostgresStore(SQLiteStore):
    """Production PostgreSQL 17 store with serializable scoped transactions.

    ``dsn`` and the optional health identity are trusted deployment
    configuration.  Callers must never construct a ``SecurityContext`` from
    JSON fields; the HTTP service derives it from its authenticated principal.
    The schema is never auto-created by the application role.
    """

    def __init__(
        self,
        dsn: str,
        *,
        authority_dsn: str | None = None,
        health_context: SecurityContext | None = None,
        connect_timeout_seconds: int = 5,
        typed_ingress_policy: Mapping[str, Sequence[TypedIngressKind]] | None = None,
    ) -> None:
        if not isinstance(dsn, str) or not dsn.strip():
            raise StoreError(
                "PostgreSQL DSN is required in production",
                code="POSTGRES_NOT_CONFIGURED",
            )
        if connect_timeout_seconds < 1 or connect_timeout_seconds > 60:
            raise ValidationError(
                "PostgreSQL connect timeout is outside the safe range"
            )
        availability = postgres_driver_readiness()
        if not availability.ready:
            raise StoreError(availability.reason, code=availability.status.value)
        driver = importlib.import_module("psycopg")
        rows = importlib.import_module("psycopg.rows")
        self._driver = driver
        self._dict_row = rows.dict_row
        self._dsn = dsn
        if authority_dsn is not None and not authority_dsn.strip():
            raise ValidationError("authority_dsn must be non-empty when configured")
        if authority_dsn is not None and hmac.compare_digest(authority_dsn, dsn):
            raise ValidationError(
                "authority writer must use a distinct database identity"
            )
        self._authority_dsn = authority_dsn
        self._connect_timeout_seconds = connect_timeout_seconds
        self._health_context = health_context or SecurityContext(
            tenant_id="__proof_harness_health__",
            project_id="__proof_harness_health__",
            actor_id="__proof_harness_service__",
        )
        normalized_ingress_policy: dict[str, frozenset[TypedIngressKind]] = {}
        for producer_id, kinds in (typed_ingress_policy or {}).items():
            producer = _port_text(
                producer_id, "typed_ingress_policy producer", maximum=512
            )
            if (
                not isinstance(kinds, Sequence)
                or isinstance(kinds, (str, bytes))
                or any(not isinstance(kind, TypedIngressKind) for kind in kinds)
            ):
                raise ValidationError("typed_ingress_policy kinds must be typed")
            allowed = frozenset(kinds)
            if not allowed:
                raise ValidationError("typed_ingress_policy entry must not be empty")
            normalized_ingress_policy[producer] = allowed
        self._typed_ingress_policy = normalized_ingress_policy
        self._state_lock = threading.RLock()
        self._closed = False

    @classmethod
    def from_environment(
        cls,
        *,
        variable: str = "ELMOS_POSTGRES_DSN",
        environment: Mapping[str, str] | None = None,
    ) -> "PostgresStore":
        values = os.environ if environment is None else environment
        dsn = values.get(variable, "")
        if not dsn.strip():
            raise StoreError(
                f"{variable} is required for the production PostgreSQL backend",
                code="POSTGRES_NOT_CONFIGURED",
            )
        authority_dsn = values.get("ELMOS_POSTGRES_AUTHORITY_DSN", "")
        if not authority_dsn.strip():
            raise StoreError(
                "ELMOS_POSTGRES_AUTHORITY_DSN is required for the production PostgreSQL backend",
                code="AUTHORITY_WRITER_NOT_CONFIGURED",
            )
        return cls(dsn, authority_dsn=authority_dsn)

    def __enter__(self) -> "PostgresStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        # Connections are transaction-scoped, so closing prevents new work and
        # never strands a process-global driver connection.
        with self._state_lock:
            self._closed = True

    def _connect(self) -> Any:
        with self._state_lock:
            if self._closed:
                raise StoreError("PostgreSQL store is closed", code="STORE_CLOSED")
        try:
            return self._driver.connect(
                self._dsn,
                autocommit=False,
                connect_timeout=self._connect_timeout_seconds,
                row_factory=self._dict_row,
            )
        except Exception as exc:
            sqlstate = str(getattr(exc, "sqlstate", "") or "")
            raise StoreError(
                "PostgreSQL connection failed",
                code="POSTGRES_UNAVAILABLE",
                details={"sqlstate": sqlstate} if sqlstate else {},
            ) from exc

    def _connect_authority(self) -> Any:
        if self._authority_dsn is None:
            raise StoreError(
                "independent authority-writer DSN is required",
                code="AUTHORITY_WRITER_NOT_CONFIGURED",
            )
        with self._state_lock:
            if self._closed:
                raise StoreError("PostgreSQL store is closed", code="STORE_CLOSED")
        try:
            return self._driver.connect(
                self._authority_dsn,
                autocommit=False,
                connect_timeout=self._connect_timeout_seconds,
                row_factory=self._dict_row,
            )
        except Exception as exc:
            sqlstate = str(getattr(exc, "sqlstate", "") or "")
            raise StoreError(
                "PostgreSQL authority-writer connection failed",
                code="AUTHORITY_WRITER_UNAVAILABLE",
                details={"sqlstate": sqlstate} if sqlstate else {},
            ) from exc

    @contextmanager
    def _authority_transaction(
        self,
        context: SecurityContext,
    ) -> Iterator[_PostgresCursor]:
        connection = self._connect_authority()
        cursor: Any | None = None
        try:
            cursor = connection.cursor()
            adapted = _PostgresCursor(cursor)
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            active_fence = _ACTIVE_INVOCATION_FENCE.get()
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true), "
                "set_config('app.project_id', %s, true), "
                "set_config('app.actor_id', %s, true), "
                "set_config('app.run_id', %s, true), "
                "set_config('app.execution_epoch', %s, true), "
                "set_config('app.fencing_generation', %s, true), "
                "set_config('app.authority_revision', %s, true), "
                "set_config('app.operation_invocation_id', %s, true)",
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    context.run_id or "",
                    str(context.execution_epoch),
                    str(context.fencing_generation),
                    context.authority_revision or "",
                    active_fence.invocation_id if active_fence is not None else "",
                ),
            )
            cursor.execute(
                "SET LOCAL search_path = proof_harness_runtime, proof_harness, pg_catalog"
            )
            yield adapted
            connection.commit()
        except HarnessError:
            try:
                connection.rollback()
            except Exception:
                pass
            raise
        except Exception as exc:
            try:
                connection.rollback()
            except Exception:
                pass
            _raise_mapped_database_error(exc)
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

    @contextmanager
    def transaction(
        self, context: SecurityContext | None = None
    ) -> Iterator[_PostgresCursor]:
        if context is None:
            raise AuthorizationError(
                "trusted tenant/project/actor context is required for every PostgreSQL transaction",
                code="TRUSTED_CONTEXT_REQUIRED",
            )
        active_fence = _ACTIVE_INVOCATION_FENCE.get()
        borrowed_claim_connection = active_fence is not None
        if active_fence is not None:
            expected_context = (
                active_fence.tenant_id,
                active_fence.project_id,
                active_fence.actor_id,
                active_fence.run_id,
                active_fence.execution_epoch,
                active_fence.fencing_generation,
                active_fence.authority_revision,
            )
            observed_context = (
                context.tenant_id,
                context.project_id,
                context.actor_id,
                context.run_id,
                context.execution_epoch,
                context.fencing_generation,
                context.authority_revision,
            )
            if observed_context != expected_context:
                raise AuthorizationError(
                    "active invocation claim cannot authorize a different runtime scope",
                    code="INVOCATION_SCOPE_MISMATCH",
                )
            # Every mutation executed for an acquired invocation deliberately
            # reuses the PostgreSQL session that owns its advisory claim lock.
            # A terminated backend therefore makes the old worker's next write
            # fail before SQL is issued; it can never reconnect behind the
            # claim fence while another worker performs recovery.
            connection = active_fence.connection
        else:
            connection = self._connect()
        cursor: Any | None = None
        try:
            cursor = connection.cursor()
            adapted = _PostgresCursor(cursor)
            # SET TRANSACTION must be first.  set_config(..., true) is LOCAL to
            # this transaction and is parameterized to prevent SQL injection.
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true), "
                "set_config('app.project_id', %s, true), "
                "set_config('app.actor_id', %s, true), "
                "set_config('app.run_id', %s, true), "
                "set_config('app.execution_epoch', %s, true), "
                "set_config('app.fencing_generation', %s, true), "
                "set_config('app.authority_revision', %s, true), "
                "set_config('app.operation_invocation_id', %s, true)",
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    context.run_id or "",
                    str(context.execution_epoch),
                    str(context.fencing_generation),
                    context.authority_revision or "",
                    active_fence.invocation_id if active_fence is not None else "",
                ),
            )
            cursor.execute(
                "SET LOCAL search_path = proof_harness_runtime, proof_harness, pg_catalog"
            )
            yield adapted
            connection.commit()
        except HarnessError:
            try:
                connection.rollback()
            except Exception:
                # Preserve the domain failure when the claim-owning backend was
                # concurrently terminated; the session close below is the
                # unconditional transaction/lock cleanup.
                pass
            raise
        except Exception as exc:
            try:
                connection.rollback()
            except Exception:
                pass
            _raise_mapped_database_error(exc)
        finally:
            if cursor is not None:
                cursor.close()
            if not borrowed_claim_connection:
                connection.close()

    @property
    def schema_version(self) -> int:
        with self.transaction(self._health_context) as cursor:
            row = cursor.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
            ).fetchone()
        return int(row["version"]) if row is not None else 0

    def readiness(self) -> StorageReadiness:
        try:
            with self.transaction(self._health_context) as cursor:
                role = cursor.execute(
                    "SELECT current_user AS role_name,session_user AS session_role,"
                    "r.rolsuper,r.rolbypassrls,"
                    "r.rolcreatedb,r.rolcreaterole,r.rolreplication,r.rolcanlogin,"
                    "current_database() AS database_name,"
                    "(SELECT system_identifier::text FROM pg_control_system()) "
                    "AS system_identifier,pg_is_in_recovery() AS in_recovery,"
                    "current_setting('transaction_read_only') AS transaction_read_only,"
                    "current_setting('server_version_num') AS server_version_num,"
                    "current_setting('server_version') AS server_version "
                    "FROM pg_roles r WHERE r.rolname=current_user"
                ).fetchone()
                version = cursor.execute(
                    "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
                ).fetchone()
                migration_digest = cursor.execute(
                    "SELECT content_sha256 FROM migration_digest_ledger "
                    "WHERE version=? AND migration_name=?",
                    (POSTGRES_SCHEMA_VERSION, "V001__proof_harness_core.sql"),
                ).fetchone()
                rls = cursor.execute(
                    "SELECT COUNT(*) AS count FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='proof_harness_runtime' AND c.relname IN ('tenants','projects','actors','runs','idempotency_receipts','control_plane_receipts','evidence','evidence_revocations','audit_events','outbox_events','outbox_deliveries','run_checkpoints','external_effects','effect_events','metric_points','certification_assessments','certification_gate_results','certification_evidence_links','certification_external_receipts','certification_external_decisions','certification_signature_revocations','certification_events') AND c.relrowsecurity AND c.relforcerowsecurity"
                ).fetchone()
                policies = cursor.execute(
                    "SELECT COUNT(*) AS count FROM pg_policies WHERE schemaname='proof_harness_runtime' "
                    "AND tablename IN ('tenants','projects','actors','runs','idempotency_receipts','control_plane_receipts','evidence','evidence_revocations','audit_events','outbox_events','outbox_deliveries','run_checkpoints','external_effects','effect_events','metric_points','certification_assessments','certification_gate_results','certification_evidence_links','certification_external_receipts','certification_external_decisions','certification_signature_revocations','certification_events')"
                ).fetchone()
                app_cert_writes = cursor.execute(
                    "SELECT bool_or(has_table_privilege(current_user,'proof_harness_runtime.'||name,'INSERT,UPDATE,DELETE,TRUNCATE')) AS writable "
                    "FROM unnest(ARRAY['certification_assessments','certification_gate_results','certification_evidence_links','certification_external_receipts','certification_external_decisions','certification_signature_revocations','certification_events']::text[]) AS name"
                ).fetchone()
                ownership = cursor.execute(
                    "SELECT ((SELECT COUNT(*) FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname IN ('proof_harness_runtime','proof_harness') "
                    "AND pg_get_userbyid(c.relowner)=current_user) + "
                    "(SELECT COUNT(*) FROM pg_namespace n "
                    "WHERE n.nspname IN ('proof_harness_runtime','proof_harness') "
                    "AND pg_get_userbyid(n.nspowner)=current_user)) AS count"
                ).fetchone()
                delta_migration = cursor.execute(
                    "SELECT m.version,m.migration_name,m.package_version,"
                    "m.required_base_version,m.required_base_sha256,"
                    "m.control_fingerprint_sha256,l.content_sha256,"
                    "(SELECT COUNT(*) FROM runtime_assurance_migrations) AS migration_count,"
                    "(SELECT COUNT(*) FROM runtime_assurance_migration_digest_ledger) AS ledger_count "
                    "FROM runtime_assurance_migrations m "
                    "JOIN runtime_assurance_migration_digest_ledger l "
                    "ON l.version=m.version AND l.migration_name=m.migration_name "
                    "WHERE m.version=? AND m.migration_name=?",
                    (POSTGRES_DELTA_SCHEMA_VERSION, POSTGRES_DELTA_MIGRATION_NAME),
                ).fetchone()
                delta_rls = cursor.execute(
                    "SELECT COUNT(*) AS count FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='proof_harness_runtime' "
                    "AND c.relkind IN ('r','p') "
                    "AND c.relname=ANY(?) "
                    "AND c.relrowsecurity AND c.relforcerowsecurity",
                    (list(_DELTA_RELATION_NAMES),),
                ).fetchone()
                delta_policies = cursor.execute(
                    "SELECT COUNT(*) AS count,COUNT(DISTINCT tablename) AS table_count,"
                    "COALESCE(bool_and(COALESCE("
                    "policyname='runtime_assurance_trusted_scope_isolation' "
                    "AND permissive='PERMISSIVE' AND cmd='ALL' "
                    "AND roles=ARRAY['public']::name[] "
                    "AND regexp_replace(regexp_replace(qual,'[[:space:]()]','','g'),"
                    "'::text','','g')=? "
                    "AND regexp_replace(regexp_replace(with_check,'[[:space:]()]','','g'),"
                    "'::text','','g')=?"
                    ",false)),false) AS exact "
                    "FROM pg_policies WHERE schemaname='proof_harness_runtime' "
                    "AND tablename=ANY(?)"
                    ,
                    (
                        _DELTA_RLS_CANONICAL_EXPRESSION,
                        _DELTA_RLS_CANONICAL_EXPRESSION,
                        list(_DELTA_RELATION_NAMES),
                    ),
                ).fetchone()
                observed_control_fingerprint = _control_catalog_fingerprint(cursor)
                delta_acl = cursor.execute(
                    "SELECT "
                    "bool_and("
                    "COALESCE(has_table_privilege(current_user,"
                    "format('%I.%I','proof_harness_runtime',name),'SELECT'),false) "
                    "AND COALESCE(has_table_privilege(current_user,"
                    "format('%I.%I','proof_harness_runtime',name),'INSERT'),false)="
                    "(name=ANY(?::text[])) "
                    "AND COALESCE(has_table_privilege(current_user,"
                    "format('%I.%I','proof_harness_runtime',name),'UPDATE'),false)="
                    "(name=ANY(?::text[])) "
                    "AND NOT COALESCE(has_table_privilege(current_user,"
                    "format('%I.%I','proof_harness_runtime',name),'DELETE'),false) "
                    "AND NOT COALESCE(has_table_privilege(current_user,"
                    "format('%I.%I','proof_harness_runtime',name),'TRUNCATE'),false)) AS exact "
                    "FROM unnest(?::text[]) AS name",
                    (
                        sorted(_APP_INSERT_RELATIONS),
                        sorted(_APP_UPDATE_RELATIONS),
                        list(_DELTA_RELATION_NAMES),
                    ),
                ).fetchone()
                app_function_acl = cursor.execute(
                    "SELECT bool_and(COALESCE(has_function_privilege("
                    "current_user,signature,'EXECUTE'),false)="
                    "(signature=ANY(?::text[]))) AS exact "
                    "FROM unnest(?::text[]) AS signature",
                    (
                        sorted(_APP_EXECUTE_FUNCTION_SIGNATURES),
                        list(_DELTA_FUNCTION_SIGNATURES),
                    ),
                ).fetchone()
                delta_support_acl = cursor.execute(
                    "SELECT "
                    "has_schema_privilege(current_user,'proof_harness_runtime','USAGE') "
                    "AND has_schema_privilege(current_user,'proof_harness','USAGE') "
                    "AND has_sequence_privilege(current_user,"
                    "'proof_harness_runtime.typed_ingress_records_persisted_sequence_seq',"
                    "'USAGE') AND has_sequence_privilege(current_user,"
                    "'proof_harness_runtime.typed_ingress_records_persisted_sequence_seq',"
                    "'SELECT') AND NOT has_sequence_privilege(current_user,"
                    "'proof_harness_runtime.typed_ingress_records_persisted_sequence_seq',"
                    "'UPDATE') "
                    "AND has_table_privilege(current_user,"
                    "'proof_harness_runtime.runs','SELECT') "
                    "AND has_table_privilege(current_user,"
                    "'proof_harness_runtime.runs','INSERT') "
                    "AND has_table_privilege(current_user,"
                    "'proof_harness_runtime.runs','UPDATE') "
                    "AND has_table_privilege(current_user,"
                    "'proof_harness_runtime.audit_events','INSERT') "
                    "AND has_table_privilege(current_user,"
                    "'proof_harness_runtime.audit_events','SELECT') "
                    "AND has_table_privilege(current_user,"
                    "'proof_harness_runtime.outbox_events','INSERT') "
                    "AND has_table_privilege(current_user,"
                    "'proof_harness_runtime.outbox_events','SELECT') "
                    "AND has_table_privilege(current_user,"
                    "'proof_harness_runtime.evidence','SELECT') "
                    "AND has_table_privilege(current_user,"
                    "'proof_harness_runtime.evidence','INSERT') "
                    "AND has_table_privilege(current_user,"
                    "'proof_harness_runtime.evidence_revocations','SELECT') "
                    "AND has_table_privilege(current_user,"
                    "'proof_harness_runtime.evidence_revocations','INSERT') "
                    "AND NOT has_table_privilege(current_user,"
                    "'proof_harness_runtime.runs','DELETE') "
                    "AND NOT has_table_privilege(current_user,"
                    "'proof_harness_runtime.runs','TRUNCATE') "
                    "AND NOT has_table_privilege(current_user,"
                    "'proof_harness_runtime.audit_events','UPDATE,DELETE,TRUNCATE') "
                    "AND NOT has_table_privilege(current_user,"
                    "'proof_harness_runtime.outbox_events','UPDATE,DELETE,TRUNCATE') "
                    "AND NOT has_table_privilege(current_user,"
                    "'proof_harness_runtime.evidence','UPDATE,DELETE,TRUNCATE') "
                    "AND NOT has_table_privilege(current_user,"
                    "'proof_harness_runtime.evidence_revocations','UPDATE,DELETE,TRUNCATE') "
                    "AS exact"
                ).fetchone()
                owner_boundary = cursor.execute(
                    "WITH owners AS ("
                    "SELECT pg_get_userbyid(datdba) AS owner_name FROM pg_database "
                    "WHERE datname=current_database() UNION "
                    "SELECT pg_get_userbyid(nspowner) FROM pg_namespace "
                    "WHERE nspname IN ('proof_harness','proof_harness_runtime') UNION "
                    "SELECT pg_get_userbyid(c.relowner) FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='proof_harness_runtime' AND "
                    "c.relname=ANY(?)) "
                    "SELECT NOT has_database_privilege(current_user,current_database(),'CREATE') "
                    "AND NOT has_schema_privilege(current_user,'proof_harness','CREATE') "
                    "AND NOT has_schema_privilege(current_user,'proof_harness_runtime','CREATE') "
                    "AND bool_and(NOT pg_has_role(current_user,owner_name,'SET')) "
                    "AND NOT EXISTS (SELECT 1 FROM pg_default_acl d "
                    "CROSS JOIN LATERAL aclexplode(d.defaclacl) acl "
                    "WHERE acl.grantee<>d.defaclrole "
                    "AND pg_get_userbyid(d.defaclrole) IN (SELECT owner_name FROM owners) "
                    "AND (d.defaclnamespace=0 OR d.defaclnamespace IN ("
                    "SELECT oid FROM pg_namespace WHERE nspname IN ("
                    "'proof_harness','proof_harness_runtime')))) AS exact "
                    "FROM owners",
                    (
                        [
                            "runtime_assurance_migrations",
                            "runtime_assurance_migration_digest_ledger",
                            *_DELTA_RELATION_NAMES,
                        ],
                    ),
                ).fetchone()
                delta_metadata_security = cursor.execute(
                    "SELECT COUNT(*) AS count,"
                    "COALESCE(bool_or(has_table_privilege(current_user,"
                    "format('%I.%I',n.nspname,c.relname),"
                    "'INSERT,UPDATE,DELETE,TRUNCATE') OR "
                    "has_any_column_privilege(current_user,"
                    "format('%I.%I',n.nspname,c.relname),'INSERT,UPDATE')),false) AS writable,"
                    "COALESCE(bool_or(pg_get_userbyid(c.relowner)=current_user),false) AS owned "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='proof_harness_runtime' AND c.relkind IN ('r','p') "
                    "AND c.relname IN ('runtime_assurance_migrations',"
                    "'runtime_assurance_migration_digest_ledger')"
                ).fetchone()
            if self._authority_dsn is None:
                raise StoreError(
                    "independent authority-writer DSN is required",
                    code="AUTHORITY_WRITER_NOT_CONFIGURED",
                )
            authority_connection = self._connect_authority()
            authority_raw_cursor: Any | None = None
            try:
                authority_raw_cursor = authority_connection.cursor()
                authority_cursor = _PostgresCursor(authority_raw_cursor)
                authority_raw_cursor.execute(
                    "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"
                )
                authority_raw_cursor.execute(
                    "SET LOCAL search_path = proof_harness_runtime, proof_harness, pg_catalog"
                )
                authority_role = authority_cursor.execute(
                    "SELECT current_user AS role_name,session_user AS session_role,"
                    "r.rolsuper,r.rolbypassrls,"
                    "r.rolcreatedb,r.rolcreaterole,r.rolreplication,r.rolcanlogin,"
                    "current_database() AS database_name,"
                    "(SELECT system_identifier::text FROM pg_control_system()) "
                    "AS system_identifier,pg_is_in_recovery() AS in_recovery,"
                    "current_setting('transaction_read_only') AS transaction_read_only "
                    "FROM pg_roles r WHERE r.rolname=current_user"
                ).fetchone()
                authority_acl = authority_cursor.execute(
                    "SELECT bool_and("
                    "COALESCE(has_table_privilege(current_user,"
                    "format('%I.%I','proof_harness_runtime',name),'SELECT'),false)="
                    "(name=ANY(?::text[])) "
                    "AND COALESCE(has_table_privilege(current_user,"
                    "format('%I.%I','proof_harness_runtime',name),'INSERT'),false)="
                    "(name=ANY(?::text[])) "
                    "AND NOT COALESCE(has_table_privilege(current_user,"
                    "format('%I.%I','proof_harness_runtime',name),'UPDATE'),false) "
                    "AND NOT COALESCE(has_table_privilege(current_user,"
                    "format('%I.%I','proof_harness_runtime',name),'DELETE'),false) "
                    "AND NOT COALESCE(has_table_privilege(current_user,"
                    "format('%I.%I','proof_harness_runtime',name),'TRUNCATE'),false)) "
                    "AS exact FROM unnest(?::text[]) AS name",
                    (
                        sorted(_AUTHORITY_SELECT_RELATIONS),
                        sorted(_AUTHORITY_INSERT_RELATIONS),
                        list(_AUTHORITY_RELATION_NAMES),
                    ),
                ).fetchone()
                authority_function_acl = authority_cursor.execute(
                    "SELECT bool_and(COALESCE(has_function_privilege("
                    "current_user,signature,'EXECUTE'),false)="
                    "(signature=ANY(?::text[]))) AS exact "
                    "FROM unnest(?::text[]) AS signature",
                    (
                        sorted(_AUTHORITY_EXECUTE_FUNCTION_SIGNATURES),
                        list(_DELTA_FUNCTION_SIGNATURES),
                    ),
                ).fetchone()
                authority_support_acl = authority_cursor.execute(
                    "SELECT "
                    "has_schema_privilege(current_user,'proof_harness','USAGE') "
                    "AND has_schema_privilege(current_user,'proof_harness_runtime','USAGE') "
                    "AND has_table_privilege(current_user,"
                    "'proof_harness_runtime.runs','SELECT') "
                    "AND NOT has_table_privilege(current_user,"
                    "'proof_harness_runtime.runs','INSERT') "
                    "AND NOT has_table_privilege(current_user,"
                    "'proof_harness_runtime.runs','UPDATE') "
                    "AND NOT has_table_privilege(current_user,"
                    "'proof_harness_runtime.runs','DELETE') "
                    "AND NOT has_table_privilege(current_user,"
                    "'proof_harness_runtime.runs','TRUNCATE') "
                    "AND NOT has_table_privilege(current_user,"
                    "'proof_harness_runtime.audit_events','INSERT') "
                    "AND NOT has_table_privilege(current_user,"
                    "'proof_harness_runtime.outbox_events','INSERT') AS exact"
                ).fetchone()
                authority_owner_boundary = authority_cursor.execute(
                    "WITH owners AS ("
                    "SELECT pg_get_userbyid(datdba) AS owner_name FROM pg_database "
                    "WHERE datname=current_database() UNION "
                    "SELECT pg_get_userbyid(nspowner) FROM pg_namespace "
                    "WHERE nspname IN ('proof_harness','proof_harness_runtime') UNION "
                    "SELECT pg_get_userbyid(c.relowner) FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='proof_harness_runtime' AND c.relname=ANY(?)) "
                    "SELECT has_schema_privilege(current_user,'proof_harness','USAGE') "
                    "AND has_schema_privilege(current_user,'proof_harness_runtime','USAGE') "
                    "AND NOT has_database_privilege(current_user,current_database(),'CREATE') "
                    "AND NOT has_schema_privilege(current_user,'proof_harness','CREATE') "
                    "AND NOT has_schema_privilege(current_user,'proof_harness_runtime','CREATE') "
                    "AND bool_and(NOT pg_has_role(current_user,owner_name,'SET')) "
                    "AND NOT EXISTS (SELECT 1 FROM pg_default_acl d "
                    "CROSS JOIN LATERAL aclexplode(d.defaclacl) acl "
                    "WHERE acl.grantee<>d.defaclrole "
                    "AND pg_get_userbyid(d.defaclrole) IN (SELECT owner_name FROM owners) "
                    "AND (d.defaclnamespace=0 OR d.defaclnamespace IN ("
                    "SELECT oid FROM pg_namespace WHERE nspname IN ("
                    "'proof_harness','proof_harness_runtime')))) AS exact FROM owners",
                    (
                        [
                            "runtime_assurance_migrations",
                            "runtime_assurance_migration_digest_ledger",
                            *_DELTA_RELATION_NAMES,
                        ],
                    ),
                ).fetchone()
                authority_cross_role_boundary = authority_cursor.execute(
                    "SELECT NOT pg_has_role(current_user,?,'SET') "
                    "AND NOT pg_has_role(?,current_user,'SET') AS exact",
                    (
                        str(role["role_name"]),
                        str(role["role_name"]),
                    ),
                ).fetchone()
                authority_membership_boundary = authority_cursor.execute(
                    "WITH identities AS (SELECT oid FROM pg_roles "
                    "WHERE rolname IN (?,current_user)) "
                    "SELECT NOT EXISTS (SELECT 1 FROM pg_auth_members membership "
                    "WHERE membership.roleid IN (SELECT oid FROM identities) "
                    "OR membership.member IN (SELECT oid FROM identities)) AS exact",
                    (str(role["role_name"]),),
                ).fetchone()
                authority_sensitive_acl = authority_cursor.execute(
                    "WITH identities AS (SELECT "
                    "(SELECT oid FROM pg_roles WHERE rolname=?) AS app_oid,"
                    "(SELECT oid FROM pg_roles WHERE rolname=current_user) AS authority_oid),"
                    "secured AS (SELECT c.oid,c.relowner,c.relacl FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='proof_harness_runtime' AND c.relname=ANY(?)),"
                    "relation_acl AS (SELECT s.oid,s.relowner,a.grantee,"
                    "a.privilege_type,a.is_grantable FROM secured s "
                    "CROSS JOIN LATERAL aclexplode(COALESCE(s.relacl,"
                    "acldefault('r',s.relowner))) a),"
                    "helper AS (SELECT p.oid,p.proowner,p.proacl,p.prosecdef,p.proconfig "
                    "FROM pg_proc p WHERE p.oid=?::regprocedure),"
                    "helper_acl AS (SELECT h.proowner,a.grantee,a.privilege_type,"
                    "a.is_grantable FROM helper h CROSS JOIN LATERAL "
                    "aclexplode(COALESCE(h.proacl,acldefault('f',h.proowner))) a) "
                    "SELECT (SELECT count(*) FROM secured)=2 "
                    "AND (SELECT count(DISTINCT relowner) FROM secured)=1 "
                    "AND NOT EXISTS (SELECT 1 FROM relation_acl a CROSS JOIN identities i "
                    "WHERE NOT (a.grantee=a.relowner "
                    "OR (a.grantee=i.app_oid AND a.privilege_type='SELECT' "
                    "AND NOT a.is_grantable) "
                    "OR (a.grantee=i.authority_oid "
                    "AND a.privilege_type IN ('SELECT','INSERT') "
                    "AND NOT a.is_grantable))) "
                    "AND NOT EXISTS (SELECT 1 FROM secured s CROSS JOIN identities i "
                    "WHERE NOT EXISTS (SELECT 1 FROM relation_acl a "
                    "WHERE a.oid=s.oid AND a.grantee=i.app_oid "
                    "AND a.privilege_type='SELECT' AND NOT a.is_grantable) "
                    "OR NOT EXISTS (SELECT 1 FROM relation_acl a "
                    "WHERE a.oid=s.oid AND a.grantee=i.authority_oid "
                    "AND a.privilege_type='SELECT' AND NOT a.is_grantable) "
                    "OR NOT EXISTS (SELECT 1 FROM relation_acl a "
                    "WHERE a.oid=s.oid AND a.grantee=i.authority_oid "
                    "AND a.privilege_type='INSERT' AND NOT a.is_grantable)) "
                    "AND (SELECT count(*)=1 AND bool_and(prosecdef "
                    "AND proowner=(SELECT relowner FROM secured LIMIT 1) "
                    "AND proconfig=ARRAY['search_path=pg_catalog, proof_harness_runtime']::text[]) "
                    "FROM helper) "
                    "AND NOT EXISTS (SELECT 1 FROM helper_acl a CROSS JOIN identities i "
                    "WHERE NOT (a.grantee=a.proowner "
                    "OR (a.grantee=i.authority_oid AND a.privilege_type='EXECUTE' "
                    "AND NOT a.is_grantable))) "
                    "AND EXISTS (SELECT 1 FROM helper_acl a CROSS JOIN identities i "
                    "WHERE a.grantee=i.authority_oid AND a.privilege_type='EXECUTE' "
                    "AND NOT a.is_grantable) AS exact",
                    (
                        str(role["role_name"]),
                        [
                            "runtime_authority_capability_receipts",
                            "subagent_budget_reservation_bindings",
                        ],
                        _SUBAGENT_CONSUME_FUNCTION_SIGNATURE,
                    ),
                ).fetchone()
                deployment_acl_boundary = authority_cursor.execute(
                    "WITH identities AS (SELECT "
                    "(SELECT oid FROM pg_roles WHERE rolname=?) AS app_oid,"
                    "(SELECT oid FROM pg_roles WHERE rolname=current_user) AS authority_oid),"
                    "relations AS (SELECT c.oid,c.relname,c.relowner,c.relacl "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='proof_harness_runtime' AND c.relkind IN ('r','p') "
                    "AND c.relname=ANY(?::text[])),"
                    "relation_acl AS (SELECT r.oid,r.relname,r.relowner,a.grantee,"
                    "a.privilege_type,a.is_grantable FROM relations r CROSS JOIN LATERAL "
                    "aclexplode(COALESCE(r.relacl,acldefault('r',r.relowner))) a),"
                    "schemas AS (SELECT n.oid,n.nspowner,n.nspacl FROM pg_namespace n "
                    "WHERE n.nspname IN ('proof_harness','proof_harness_runtime')) ,"
                    "schema_acl AS (SELECT s.oid,s.nspowner,a.grantee,a.privilege_type,"
                    "a.is_grantable FROM schemas s CROSS JOIN LATERAL "
                    "aclexplode(COALESCE(s.nspacl,acldefault('n',s.nspowner))) a),"
                    "ingress_sequence AS (SELECT c.oid,c.relowner,c.relacl FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='proof_harness_runtime' "
                    "AND c.relname='typed_ingress_records_persisted_sequence_seq' "
                    "AND c.relkind='S'),"
                    "sequence_acl AS (SELECT s.relowner,a.grantee,a.privilege_type,"
                    "a.is_grantable FROM ingress_sequence s CROSS JOIN LATERAL "
                    "aclexplode(COALESCE(s.relacl,acldefault('S',s.relowner))) a),"
                    "functions AS (SELECT p.oid,p.proowner,p.proacl,e.signature "
                    "FROM unnest(?::text[]) AS e(signature) "
                    "JOIN pg_proc p ON p.oid=e.signature::regprocedure),"
                    "function_acl AS (SELECT f.oid,f.proowner,f.signature,a.grantee,"
                    "a.privilege_type,a.is_grantable FROM functions f CROSS JOIN LATERAL "
                    "aclexplode(COALESCE(f.proacl,acldefault('f',f.proowner))) a) "
                    "SELECT (SELECT count(*) FROM relations)=? "
                    "AND NOT EXISTS (SELECT 1 FROM relation_acl a CROSS JOIN identities i "
                    "WHERE NOT (a.grantee=a.relowner OR (NOT a.is_grantable AND ("
                    "(a.grantee=i.app_oid AND ((a.privilege_type='SELECT' "
                    "AND a.relname=ANY(?::text[])) OR (a.privilege_type='INSERT' "
                    "AND a.relname=ANY(?::text[])) OR (a.privilege_type='UPDATE' "
                    "AND a.relname=ANY(?::text[])) OR (a.privilege_type='DELETE' "
                    "AND a.relname=ANY(?::text[])))) OR "
                    "(a.grantee=i.authority_oid AND ((a.privilege_type='SELECT' "
                    "AND a.relname=ANY(?::text[])) OR (a.privilege_type='INSERT' "
                    "AND a.relname=ANY(?::text[]))))))) "
                    "AND NOT EXISTS (SELECT 1 FROM unnest(?::text[]) e(name) "
                    "CROSS JOIN identities i WHERE NOT EXISTS (SELECT 1 FROM relation_acl a "
                    "WHERE a.relname=e.name AND a.grantee=i.app_oid "
                    "AND a.privilege_type='SELECT' AND NOT a.is_grantable)) "
                    "AND NOT EXISTS (SELECT 1 FROM unnest(?::text[]) e(name) "
                    "CROSS JOIN identities i WHERE NOT EXISTS (SELECT 1 FROM relation_acl a "
                    "WHERE a.relname=e.name AND a.grantee=i.app_oid "
                    "AND a.privilege_type='INSERT' AND NOT a.is_grantable)) "
                    "AND NOT EXISTS (SELECT 1 FROM unnest(?::text[]) e(name) "
                    "CROSS JOIN identities i WHERE NOT EXISTS (SELECT 1 FROM relation_acl a "
                    "WHERE a.relname=e.name AND a.grantee=i.app_oid "
                    "AND a.privilege_type='UPDATE' AND NOT a.is_grantable)) "
                    "AND NOT EXISTS (SELECT 1 FROM unnest(?::text[]) e(name) "
                    "CROSS JOIN identities i WHERE NOT EXISTS (SELECT 1 FROM relation_acl a "
                    "WHERE a.relname=e.name AND a.grantee=i.app_oid "
                    "AND a.privilege_type='DELETE' AND NOT a.is_grantable)) "
                    "AND NOT EXISTS (SELECT 1 FROM unnest(?::text[]) e(name) "
                    "CROSS JOIN identities i WHERE NOT EXISTS (SELECT 1 FROM relation_acl a "
                    "WHERE a.relname=e.name AND a.grantee=i.authority_oid "
                    "AND a.privilege_type='SELECT' AND NOT a.is_grantable)) "
                    "AND NOT EXISTS (SELECT 1 FROM unnest(?::text[]) e(name) "
                    "CROSS JOIN identities i WHERE NOT EXISTS (SELECT 1 FROM relation_acl a "
                    "WHERE a.relname=e.name AND a.grantee=i.authority_oid "
                    "AND a.privilege_type='INSERT' AND NOT a.is_grantable)) "
                    "AND NOT EXISTS (SELECT 1 FROM pg_attribute a "
                    "WHERE a.attrelid IN (SELECT oid FROM relations) AND a.attnum>0 "
                    "AND NOT a.attisdropped AND a.attacl IS NOT NULL) "
                    "AND (SELECT count(*) FROM schemas)=2 "
                    "AND NOT EXISTS (SELECT 1 FROM schema_acl a CROSS JOIN identities i "
                    "WHERE NOT (a.grantee=a.nspowner OR (NOT a.is_grantable "
                    "AND a.privilege_type='USAGE' "
                    "AND a.grantee IN (i.app_oid,i.authority_oid)))) "
                    "AND NOT EXISTS (SELECT 1 FROM schemas s CROSS JOIN identities i "
                    "WHERE NOT EXISTS (SELECT 1 FROM schema_acl a WHERE a.oid=s.oid "
                    "AND a.grantee=i.app_oid AND a.privilege_type='USAGE' "
                    "AND NOT a.is_grantable) OR NOT EXISTS (SELECT 1 FROM schema_acl a "
                    "WHERE a.oid=s.oid AND a.grantee=i.authority_oid "
                    "AND a.privilege_type='USAGE' AND NOT a.is_grantable)) "
                    "AND (SELECT count(*) FROM ingress_sequence)=1 "
                    "AND NOT EXISTS (SELECT 1 FROM sequence_acl a CROSS JOIN identities i "
                    "WHERE NOT (a.grantee=a.relowner OR (a.grantee=i.app_oid "
                    "AND a.privilege_type IN ('USAGE','SELECT') AND NOT a.is_grantable))) "
                    "AND EXISTS (SELECT 1 FROM sequence_acl a CROSS JOIN identities i "
                    "WHERE a.grantee=i.app_oid AND a.privilege_type='USAGE' "
                    "AND NOT a.is_grantable) "
                    "AND EXISTS (SELECT 1 FROM sequence_acl a CROSS JOIN identities i "
                    "WHERE a.grantee=i.app_oid AND a.privilege_type='SELECT' "
                    "AND NOT a.is_grantable) "
                    "AND (SELECT count(*) FROM functions)=? "
                    "AND NOT EXISTS (SELECT 1 FROM function_acl a CROSS JOIN identities i "
                    "WHERE NOT (a.grantee=a.proowner OR (a.privilege_type='EXECUTE' "
                    "AND NOT a.is_grantable AND ((a.grantee=i.app_oid "
                    "AND a.signature=ANY(?::text[])) OR (a.grantee=i.authority_oid "
                    "AND a.signature=ANY(?::text[])))))) "
                    "AND NOT EXISTS (SELECT 1 FROM unnest(?::text[]) e(signature) "
                    "CROSS JOIN identities i WHERE NOT EXISTS (SELECT 1 FROM function_acl a "
                    "WHERE a.signature=e.signature AND a.grantee=i.app_oid "
                    "AND a.privilege_type='EXECUTE' AND NOT a.is_grantable)) "
                    "AND NOT EXISTS (SELECT 1 FROM unnest(?::text[]) e(signature) "
                    "CROSS JOIN identities i WHERE NOT EXISTS (SELECT 1 FROM function_acl a "
                    "WHERE a.signature=e.signature AND a.grantee=i.authority_oid "
                    "AND a.privilege_type='EXECUTE' AND NOT a.is_grantable)) AS exact",
                    (
                        str(role["role_name"]),
                        list(_RAW_ACL_RELATION_NAMES),
                        list(_DELTA_FUNCTION_SIGNATURES),
                        len(_RAW_ACL_RELATION_NAMES),
                        sorted(_APP_SELECT_RELATIONS),
                        sorted(_APP_INSERT_RELATIONS),
                        sorted(_APP_UPDATE_RELATIONS),
                        sorted(_APP_DELETE_RELATIONS),
                        sorted(_AUTHORITY_SELECT_RELATIONS),
                        sorted(_AUTHORITY_INSERT_RELATIONS),
                        sorted(_APP_SELECT_RELATIONS),
                        sorted(_APP_INSERT_RELATIONS),
                        sorted(_APP_UPDATE_RELATIONS),
                        sorted(_APP_DELETE_RELATIONS),
                        sorted(_AUTHORITY_SELECT_RELATIONS),
                        sorted(_AUTHORITY_INSERT_RELATIONS),
                        len(_DELTA_FUNCTION_SIGNATURES),
                        sorted(_APP_EXECUTE_FUNCTION_SIGNATURES),
                        sorted(_AUTHORITY_EXECUTE_FUNCTION_SIGNATURES),
                        sorted(_APP_EXECUTE_FUNCTION_SIGNATURES),
                        sorted(_AUTHORITY_EXECUTE_FUNCTION_SIGNATURES),
                    ),
                ).fetchone()
                authority_connection.rollback()
            finally:
                if authority_raw_cursor is not None:
                    authority_raw_cursor.close()
                authority_connection.close()
        except HarnessError as exc:
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason=f"PostgreSQL readiness probe failed ({exc.code})",
                backend="postgresql",
            )
        except Exception:
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="PostgreSQL readiness probe failed",
                backend="postgresql",
            )
        if (
            role is None
            or bool(role["rolsuper"])
            or bool(role["rolbypassrls"])
            or bool(role["rolcreatedb"])
            or bool(role["rolcreaterole"])
            or bool(role["rolreplication"])
            or not bool(role["rolcanlogin"])
            or not hmac.compare_digest(
                str(role["role_name"]),
                str(role["session_role"]),
            )
            or bool(role["in_recovery"])
            or str(role["transaction_read_only"]) != "off"
        ):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="application role must be a least-privileged read-write login",
                backend="postgresql",
            )
        if (
            authority_role is None
            or bool(authority_role["rolsuper"])
            or bool(authority_role["rolbypassrls"])
            or bool(authority_role["rolcreatedb"])
            or bool(authority_role["rolcreaterole"])
            or bool(authority_role["rolreplication"])
            or not bool(authority_role["rolcanlogin"])
            or not hmac.compare_digest(
                str(authority_role["role_name"]),
                str(authority_role["session_role"]),
            )
            or bool(authority_role["in_recovery"])
            or str(authority_role["transaction_read_only"]) != "off"
            or hmac.compare_digest(
                str(role["role_name"]),
                str(authority_role["role_name"]),
            )
            or str(role["database_name"]) != str(authority_role["database_name"])
            or not hmac.compare_digest(
                str(role["system_identifier"]),
                str(authority_role["system_identifier"]),
            )
        ):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="authority writer must be a distinct NOSUPERUSER/NOBYPASSRLS role",
                backend="postgresql",
            )
        server_version_num = int(role["server_version_num"])
        server_version = str(role["server_version"])
        schema_version = int(version["version"]) if version is not None else 0
        if server_version_num < 170000 or server_version_num >= 180000:
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="production backend requires PostgreSQL 17.x",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if schema_version != POSTGRES_SCHEMA_VERSION:
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="required PostgreSQL migration is not installed",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if migration_digest is None or not hmac.compare_digest(
            str(migration_digest["content_sha256"]), POSTGRES_MIGRATION_SOURCE_DIGEST
        ):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="PostgreSQL migration digest ledger is missing or drifted",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if rls is None or int(rls["count"]) != _RUNTIME_TABLE_COUNT:
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="forced RLS is incomplete on PostgreSQL runtime tables",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if policies is None or int(policies["count"]) != _RUNTIME_TABLE_COUNT:
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="PostgreSQL runtime RLS policy set is incomplete or drifted",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if app_cert_writes is None or bool(app_cert_writes["writable"]):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="ordinary application role must not write certifier relations",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if ownership is None or int(ownership["count"]) != 0:
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="ordinary application role must not own proof-harness schemas or relations",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if (
            delta_migration is None
            or int(delta_migration["migration_count"]) != 1
            or int(delta_migration["ledger_count"]) != 1
            or int(delta_migration["version"]) != POSTGRES_DELTA_SCHEMA_VERSION
            or str(delta_migration["migration_name"]) != POSTGRES_DELTA_MIGRATION_NAME
            or str(delta_migration["package_version"]) != _DELTA_PACKAGE_VERSION
            or int(delta_migration["required_base_version"]) != POSTGRES_SCHEMA_VERSION
            or not hmac.compare_digest(
                str(delta_migration["required_base_sha256"]),
                POSTGRES_MIGRATION_SOURCE_DIGEST,
            )
            or not hmac.compare_digest(
                str(delta_migration["content_sha256"]),
                POSTGRES_DELTA_MIGRATION_SOURCE_DIGEST,
            )
            or not hmac.compare_digest(
                str(delta_migration["control_fingerprint_sha256"]),
                observed_control_fingerprint,
            )
        ):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="PostgreSQL V304 runtime-assurance ledger is missing or drifted",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if delta_rls is None or int(delta_rls["count"]) != _DELTA_RUNTIME_TABLE_COUNT:
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="forced RLS is incomplete on PostgreSQL runtime-assurance tables",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if (
            delta_policies is None
            or int(delta_policies["count"]) != _DELTA_RUNTIME_TABLE_COUNT
            or int(delta_policies["table_count"]) != _DELTA_RUNTIME_TABLE_COUNT
            or not bool(delta_policies["exact"])
        ):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="PostgreSQL runtime-assurance RLS policy set is incomplete or drifted",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if (
            delta_metadata_security is None
            or int(delta_metadata_security["count"]) != 2
            or bool(delta_metadata_security["writable"])
            or bool(delta_metadata_security["owned"])
        ):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="ordinary application role must not own or write runtime-assurance ledgers",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if delta_acl is None or not bool(delta_acl["exact"]):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="ordinary application role has incomplete or excessive runtime-assurance relation ACLs",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if app_function_acl is None or not bool(app_function_acl["exact"]):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="ordinary application role has incomplete or excessive helper EXECUTE ACLs",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if delta_support_acl is None or not bool(delta_support_acl["exact"]):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="ordinary application role has incomplete or excessive runtime support ACLs",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if owner_boundary is None or not bool(owner_boundary["exact"]):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="ordinary application role can assume ownership or create database objects",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if authority_acl is None or not bool(authority_acl["exact"]):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="authority writer has incomplete or excessive signed-receipt ACLs",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if authority_function_acl is None or not bool(
            authority_function_acl["exact"]
        ):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="authority writer has incomplete or excessive helper EXECUTE ACLs",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if authority_support_acl is None or not bool(authority_support_acl["exact"]):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="authority writer has incomplete or excessive runtime support ACLs",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if authority_owner_boundary is None or not bool(
            authority_owner_boundary["exact"]
        ):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="authority writer can assume ownership or create database objects",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if authority_cross_role_boundary is None or not bool(
            authority_cross_role_boundary["exact"]
        ):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="application and authority roles must not assume one another",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if authority_membership_boundary is None or not bool(
            authority_membership_boundary["exact"]
        ):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="application and authority roles must have no role-membership edges",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if authority_sensitive_acl is None or not bool(
            authority_sensitive_acl["exact"]
        ):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="signed authority tables or consume helper have unexpected ACL grantees",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        if deployment_acl_boundary is None or not bool(
            deployment_acl_boundary["exact"]
        ):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="database schema, relation, column, sequence or function ACLs are not exact",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        return StorageReadiness(
            status=StorageStatus.READY,
            reason="PostgreSQL 17 composite v3.1 schema, role and forced RLS are ready",
            backend="postgresql",
            schema_version=schema_version,
            server_version=server_version,
        )

    def register_scope(
        self, context: SecurityContext, *, now: datetime | None = None
    ) -> None:
        """Register a scope already established by trusted authentication."""

        timestamp = _iso(now or datetime.now(UTC))
        with self.transaction(context) as cursor:
            cursor.execute(
                "INSERT INTO tenants(tenant_id,created_at) VALUES (?,?) ON CONFLICT (tenant_id) DO NOTHING",
                (context.tenant_id, timestamp),
            )
            cursor.execute(
                "INSERT INTO projects(tenant_id,project_id,created_at) VALUES (?,?,?) ON CONFLICT (tenant_id,project_id) DO NOTHING",
                (context.tenant_id, context.project_id, timestamp),
            )
            cursor.execute(
                "INSERT INTO actors(tenant_id,project_id,actor_id,created_at) VALUES (?,?,?,?) ON CONFLICT (tenant_id,project_id,actor_id) DO NOTHING",
                (context.tenant_id, context.project_id, context.actor_id, timestamp),
            )

    @staticmethod
    def _assert_runtime_assurance_run_scope(
        cursor: _PostgresCursor,
        context: SecurityContext,
    ) -> Mapping[str, Any]:
        _port_run_context(context)
        row = cursor.execute(
            "SELECT actor_id,execution_epoch,fencing_generation,revision_set_id "
            "FROM runs WHERE tenant_id=? AND project_id=? AND run_id=? FOR KEY SHARE",
            (context.tenant_id, context.project_id, context.run_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(
                "runtime-assurance run scope was not found",
                code="DELTA_SCOPE_NOT_FOUND",
            )
        if str(row["actor_id"]) != context.actor_id:
            raise AuthorizationError(
                "runtime-assurance actor binding does not match the run",
                code="DELTA_ACTOR_MISMATCH",
            )
        if int(row["execution_epoch"]) != context.execution_epoch:
            raise ConflictError(
                "runtime-assurance execution epoch is stale", code="STALE_EPOCH"
            )
        if int(row["fencing_generation"]) != context.fencing_generation:
            raise ConflictError(
                "runtime-assurance generation fence is stale", code="STALE_FENCE"
            )
        return row

    @classmethod
    def _assert_runtime_assurance_scope(
        cls,
        cursor: _PostgresCursor,
        context: SecurityContext,
        revision_set_id: str,
    ) -> None:
        _port_context(context, revision_set_id)
        cursor.execute(
            "SELECT set_config('app.revision_set_id', ?, true)",
            (revision_set_id,),
        )
        row = cls._assert_runtime_assurance_run_scope(cursor, context)
        if not hmac.compare_digest(str(row["revision_set_id"]), revision_set_id):
            raise ConflictError(
                "runtime-assurance revision is stale", code="STALE_REVISION"
            )
        active_fence = _ACTIVE_INVOCATION_FENCE.get()
        if active_fence is None:
            return
        expected_scope = (
            context.tenant_id,
            context.project_id,
            context.actor_id,
            context.run_id,
            context.execution_epoch,
            context.fencing_generation,
            context.authority_revision,
            revision_set_id,
        )
        observed_scope = (
            active_fence.tenant_id,
            active_fence.project_id,
            active_fence.actor_id,
            active_fence.run_id,
            active_fence.execution_epoch,
            active_fence.fencing_generation,
            active_fence.authority_revision,
            active_fence.revision_set_id,
        )
        if observed_scope != expected_scope:
            raise AuthorizationError(
                "active invocation claim cannot authorize a different runtime scope",
                code="INVOCATION_SCOPE_MISMATCH",
            )
        scope = _runtime_scope_parameters(context, revision_set_id)
        claim_row = cursor.execute(
            "SELECT request_digest,claim_epoch,claim_backend_pid,claim_lock_key,state "
            "FROM runtime_assurance_invocation_receipts "
            f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? FOR UPDATE",
            (*scope, active_fence.invocation_id),
        ).fetchone()
        if claim_row is None:
            raise ConflictError(
                "active invocation claim disappeared",
                code="INVOCATION_RECOVERY_REQUIRED",
            )
        if not (
            hmac.compare_digest(
                str(claim_row["request_digest"]),
                active_fence.request_digest,
            )
            and int(claim_row["claim_epoch"]) == active_fence.claim_epoch
            and str(claim_row["state"])
            == RuntimeAssuranceInvocationState.IN_PROGRESS.value
        ):
            raise ConflictError(
                "active invocation claim was fenced and requires explicit recovery",
                code="INVOCATION_RECOVERY_REQUIRED",
            )
        lock_row = cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_locks AS held "
            "WHERE held.locktype='advisory' "
            "AND held.mode='ExclusiveLock' "
            "AND held.database=(SELECT oid FROM pg_catalog.pg_database "
            "WHERE datname=current_database()) "
            "AND held.pid=? "
            "AND held.classid=(((?::bigint >> 32) & 4294967295)::oid) "
            "AND held.objid=((?::bigint & 4294967295)::oid) "
            "AND held.objsubid=1 AND held.granted) AS live",
            (
                int(claim_row["claim_backend_pid"]),
                int(claim_row["claim_lock_key"]),
                int(claim_row["claim_lock_key"]),
            ),
        ).fetchone()
        if lock_row is None or lock_row["live"] is not True:
            raise ConflictError(
                "active invocation claim session lock was lost and requires explicit recovery",
                code="INVOCATION_RECOVERY_REQUIRED",
            )

    @staticmethod
    def _require_active_invocation_operation(operation_invocation_id: str) -> None:
        active_fence = _ACTIVE_INVOCATION_FENCE.get()
        if active_fence is None:
            raise AuthorizationError(
                "runtime-assurance mutation requires an active invocation claim",
                code="INVOCATION_CLAIM_REQUIRED",
            )
        if not hmac.compare_digest(
            active_fence.invocation_id,
            operation_invocation_id,
        ):
            raise AuthorizationError(
                "operation invocation does not match the active claim",
                code="INVOCATION_OPERATION_MISMATCH",
            )

    def _append_runtime_assurance_outbox(
        self,
        cursor: _PostgresCursor,
        context: SecurityContext,
        *,
        revision_set_id: str,
        event_type: str,
        subject_id: str,
        payload: Mapping[str, Any],
    ) -> str:
        """Atomically journal a delta mutation through the base durable outbox."""

        if context.run_id is None:
            raise ValidationError("runtime-assurance persistence requires run_id")
        return self._append_audit_outbox(
            cursor,
            context,
            event_type=event_type,
            subject_id=subject_id,
            payload={
                "run_id": context.run_id,
                "execution_epoch": context.execution_epoch,
                "fencing_generation": context.fencing_generation,
                "authority_revision": context.authority_revision,
                "revision_set_id": revision_set_id,
                "detail": dict(payload),
            },
        )

    @contextmanager
    def claim_runtime_assurance_invocation(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        request_digest: str,
        now: datetime | None = None,
    ) -> Iterator[RuntimeAssuranceInvocationClaimRecord]:
        """Serialize one invocation while keeping claim state visible to a second connection.

        The session advisory lock spans the caller's handler execution, while
        the receipt mutation is committed before yielding.  Finding a durable
        ``IN_PROGRESS`` receipt after acquiring the lock proves that its former
        PostgreSQL session ended; it is fenced as ``RECOVERY_REQUIRED`` and is
        never automatically executed again.
        """

        _port_context(context, revision_set_id)
        invocation_id = _port_text(invocation_id, "invocation_id", maximum=512)
        require_sha256_digest(request_digest, field="request_digest")
        timestamp = _port_time(now, "now", default_now=True)
        lock_key = _invocation_lock_key(context, revision_set_id, invocation_id)
        scope = _runtime_scope_parameters(context, revision_set_id)
        connection = self._connect()
        raw_cursor = connection.cursor()
        cursor = _PostgresCursor(raw_cursor)
        lock_acquired = False
        fence_token: Token[_ActiveInvocationFence | None] | None = None
        claim: RuntimeAssuranceInvocationClaimRecord
        try:
            try:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                cursor.execute(
                    "SELECT set_config('app.tenant_id', ?, true), "
                    "set_config('app.project_id', ?, true), "
                    "set_config('app.actor_id', ?, true), "
                    "set_config('app.run_id', ?, true), "
                    "set_config('app.execution_epoch', ?, true), "
                    "set_config('app.fencing_generation', ?, true), "
                    "set_config('app.authority_revision', ?, true), "
                    "set_config('app.operation_invocation_id', ?, true)",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        context.run_id,
                        str(context.execution_epoch),
                        str(context.fencing_generation),
                        context.authority_revision,
                        invocation_id,
                    ),
                )
                cursor.execute(
                    "SET LOCAL search_path = proof_harness_runtime, proof_harness, pg_catalog"
                )
                lock_row = cursor.execute(
                    "SELECT pg_try_advisory_lock(?) AS acquired",
                    (lock_key,),
                ).fetchone()
                if lock_row is None or lock_row["acquired"] is not True:
                    raise ConflictError(
                        "runtime-assurance invocation is already executing",
                        code="INVOCATION_BUSY",
                    )
                lock_acquired = True
                self._assert_runtime_assurance_scope(
                    cursor,
                    context,
                    revision_set_id,
                )
                disposition_row = cursor.execute(
                    "SELECT proof_harness_runtime.claim_runtime_assurance_invocation("
                    "?,?,?,?,?,?,?,?,?,?,?,?) AS disposition",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        context.run_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        invocation_id,
                        request_digest,
                        lock_key,
                        _iso(timestamp),
                    ),
                ).fetchone()
                if disposition_row is None:
                    raise IntegrityError(
                        "invocation claim helper returned no disposition",
                        code="DELTA_STORAGE_DRIFT",
                    )
                try:
                    disposition = RuntimeAssuranceClaimDisposition(
                        str(disposition_row["disposition"])
                    )
                except ValueError as exc:
                    raise IntegrityError(
                        "invocation claim helper returned an unknown disposition",
                        code="DELTA_STORAGE_DRIFT",
                    ) from exc
                claimed_row = cursor.execute(
                    f"SELECT {_INVOCATION_RECEIPT_COLUMNS} "
                    "FROM runtime_assurance_invocation_receipts "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=?",
                    (*scope, invocation_id),
                ).fetchone()
                if claimed_row is None:
                    raise IntegrityError(
                        "invocation claim helper persisted no receipt",
                        code="DELTA_STORAGE_DRIFT",
                    )
                claim = _invocation_claim_record(claimed_row, disposition)
                connection.commit()
            except HarnessError:
                connection.rollback()
                raise
            except Exception as exc:
                connection.rollback()
                _raise_mapped_database_error(exc)
            if claim.disposition is RuntimeAssuranceClaimDisposition.ACQUIRED:
                fence_token = _ACTIVE_INVOCATION_FENCE.set(
                    _ActiveInvocationFence(
                        tenant_id=claim.tenant_id,
                        project_id=claim.project_id,
                        actor_id=claim.actor_id,
                        run_id=claim.run_id,
                        execution_epoch=claim.execution_epoch,
                        fencing_generation=claim.fencing_generation,
                        authority_revision=claim.authority_revision,
                        revision_set_id=claim.revision_set_id,
                        invocation_id=claim.invocation_id,
                        request_digest=claim.request_digest,
                        claim_epoch=claim.claim_epoch,
                        connection=connection,
                    )
                )
            yield claim
        finally:
            if fence_token is not None:
                _ACTIVE_INVOCATION_FENCE.reset(fence_token)
            if lock_acquired:
                try:
                    connection.rollback()
                    cursor.execute(
                        "SELECT pg_advisory_unlock(?) AS unlocked",
                        (lock_key,),
                    )
                    connection.commit()
                except Exception:
                    # Closing the PostgreSQL session is itself an unconditional
                    # release of every session-level advisory lock.
                    try:
                        connection.rollback()
                    except Exception:
                        pass
            try:
                cursor.close()
            finally:
                connection.close()

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
    ) -> RuntimeAssuranceInvocationClaimRecord:
        _port_context(context, revision_set_id)
        invocation_id = _port_text(invocation_id, "invocation_id", maximum=512)
        require_sha256_digest(request_digest, field="request_digest")
        expected_claim_epoch = _port_positive(
            expected_claim_epoch,
            "expected_claim_epoch",
        )
        result_ref = _port_text(result_ref, "result_ref")
        require_sha256_digest(result_digest, field="result_digest")
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        parameters = (*scope, invocation_id)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            helper_result = cursor.execute(
                "SELECT proof_harness_runtime.complete_runtime_assurance_invocation("
                "?,?,?,?,?,?,?,?,?,?,?,?,?,?) AS replayed",
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    context.run_id,
                    context.execution_epoch,
                    context.fencing_generation,
                    context.authority_revision,
                    revision_set_id,
                    invocation_id,
                    request_digest,
                    expected_claim_epoch,
                    result_ref,
                    result_digest,
                    _iso(timestamp),
                ),
            ).fetchone()
            if helper_result is None:
                raise IntegrityError(
                    "invocation completion helper returned no result",
                    code="DELTA_STORAGE_DRIFT",
                )
            completed = cursor.execute(
                f"SELECT {_INVOCATION_RECEIPT_COLUMNS} "
                "FROM runtime_assurance_invocation_receipts "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=?",
                parameters,
            ).fetchone()
            if completed is None:
                raise IntegrityError(
                    "invocation completion receipt disappeared",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _invocation_claim_record(
                completed,
                (
                    RuntimeAssuranceClaimDisposition.COMPLETED_REPLAY
                    if bool(helper_result["replayed"])
                    else RuntimeAssuranceClaimDisposition.COMPLETED
                ),
            )
            return record

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
    ) -> RuntimeAssuranceInvocationClaimRecord:
        """Resolve a crash-fenced command without ever rerunning its handler."""

        _port_context(context, revision_set_id)
        invocation_id = _port_text(invocation_id, "invocation_id", maximum=512)
        require_sha256_digest(request_digest, field="request_digest")
        expected_claim_epoch = _port_positive(
            expected_claim_epoch,
            "expected_claim_epoch",
        )
        result_ref = _port_text(result_ref, "result_ref")
        require_sha256_digest(result_digest, field="result_digest")
        recovery_evidence_ref = _port_text(
            recovery_evidence_ref,
            "recovery_evidence_ref",
        )
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        parameters = (*scope, invocation_id)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            helper_result = cursor.execute(
                "SELECT proof_harness_runtime.reconcile_runtime_assurance_invocation("
                "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) AS replayed",
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    context.run_id,
                    context.execution_epoch,
                    context.fencing_generation,
                    context.authority_revision,
                    revision_set_id,
                    invocation_id,
                    request_digest,
                    expected_claim_epoch,
                    result_ref,
                    result_digest,
                    recovery_evidence_ref,
                    _iso(timestamp),
                ),
            ).fetchone()
            if helper_result is None:
                raise IntegrityError(
                    "invocation recovery helper returned no result",
                    code="DELTA_STORAGE_DRIFT",
                )
            completed = cursor.execute(
                f"SELECT {_INVOCATION_RECEIPT_COLUMNS} "
                "FROM runtime_assurance_invocation_receipts "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=?",
                parameters,
            ).fetchone()
            if completed is None:
                raise IntegrityError(
                    "invocation reconciliation receipt disappeared",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _invocation_claim_record(
                completed,
                (
                    RuntimeAssuranceClaimDisposition.COMPLETED_REPLAY
                    if bool(helper_result["replayed"])
                    else RuntimeAssuranceClaimDisposition.COMPLETED
                ),
            )
            return record

    def load_runtime_assurance_scope(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
    ) -> RuntimeAssuranceScopeSnapshot:
        _port_context(context, revision_set_id)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            scope = _runtime_scope_parameters(context, revision_set_id)
            pending_tool_calls = tuple(
                _pending_tool_call_record(row)
                for row in cursor.execute(
                    f"SELECT {_PENDING_TOOL_CALL_COLUMNS} "
                    "FROM pending_tool_call_bindings "
                    f"WHERE {_RUNTIME_SCOPE_SQL} ORDER BY call_id",
                    scope,
                ).fetchall()
            )
            tool_results = tuple(
                _tool_result_record(row)
                for row in cursor.execute(
                    f"SELECT {_TOOL_RESULT_COLUMNS} FROM tool_result_commits "
                    f"WHERE {_RUNTIME_SCOPE_SQL} "
                    "ORDER BY invocation_id,call_id,attempt",
                    scope,
                ).fetchall()
            )
            step_plans = tuple(
                _step_plan_record(row)
                for row in cursor.execute(
                    f"SELECT {_STEP_PLAN_COLUMNS} FROM step_execution_plans "
                    f"WHERE {_RUNTIME_SCOPE_SQL} "
                    "ORDER BY plan_id",
                    scope,
                ).fetchall()
            )
            runtime_authority_receipts = tuple(
                _authority_receipt_record(row)
                for row in cursor.execute(
                    f"SELECT {_AUTHORITY_RECEIPT_COLUMNS} "
                    "FROM runtime_authority_capability_receipts "
                    f"WHERE {_RUNTIME_SCOPE_SQL} "
                    "ORDER BY operation_invocation_id",
                    scope,
                ).fetchall()
            )
            capability_leases = tuple(
                _capability_record(row)
                for row in cursor.execute(
                    f"SELECT {_CAPABILITY_COLUMNS} FROM capability_leases "
                    f"WHERE {_RUNTIME_SCOPE_SQL} "
                    "ORDER BY lease_id",
                    scope,
                ).fetchall()
            )
            executor_generations = tuple(
                _executor_record(row)
                for row in cursor.execute(
                    f"SELECT {_EXECUTOR_COLUMNS} FROM executor_generations "
                    f"WHERE {_RUNTIME_SCOPE_SQL} "
                    "ORDER BY environment_id,executor_generation,connection_epoch",
                    scope,
                ).fetchall()
            )
            environment_attachments = tuple(
                _environment_attachment_record(row)
                for row in cursor.execute(
                    f"SELECT {_ENVIRONMENT_ATTACHMENT_COLUMNS} "
                    "FROM environment_attachments "
                    f"WHERE {_RUNTIME_SCOPE_SQL} "
                    "ORDER BY server_id,environment_id,generation",
                    scope,
                ).fetchall()
            )
            executor_replacement_effects = tuple(
                _executor_replacement_effect_record(row)
                for row in cursor.execute(
                    f"SELECT {_EXECUTOR_REPLACEMENT_EFFECT_COLUMNS} "
                    "FROM executor_replacement_effects "
                    f"WHERE {_RUNTIME_SCOPE_SQL} "
                    "ORDER BY created_at,effect_id",
                    scope,
                ).fetchall()
            )
            workspace_leases = tuple(
                _workspace_record(row)
                for row in cursor.execute(
                    f"SELECT {_WORKSPACE_COLUMNS} FROM workspace_leases "
                    f"WHERE {_RUNTIME_SCOPE_SQL} "
                    "ORDER BY workspace_id,generation",
                    scope,
                ).fetchall()
            )
            event_registrations = tuple(
                _event_registration_record(row)
                for row in cursor.execute(
                    f"SELECT {_EVENT_REGISTRATION_COLUMNS} FROM durable_event_registrations "
                    f"WHERE {_RUNTIME_SCOPE_SQL} "
                    "ORDER BY event_type,schema_version",
                    scope,
                ).fetchall()
            )
            durable_events = tuple(
                _durable_event_instance_record(row)
                for row in cursor.execute(
                    f"SELECT {_DURABLE_EVENT_INSTANCE_COLUMNS} "
                    "FROM durable_event_instances "
                    f"WHERE {_RUNTIME_SCOPE_SQL} "
                    "ORDER BY created_at,event_id",
                    scope,
                ).fetchall()
            )
            typed_ingress = tuple(
                _typed_ingress_record(row)
                for row in cursor.execute(
                    f"SELECT {_TYPED_INGRESS_COLUMNS} FROM typed_ingress_records "
                    f"WHERE {_RUNTIME_SCOPE_SQL} "
                    "ORDER BY recorded_at,ingress_id",
                    scope,
                ).fetchall()
            )
            subagent_budget_reservations = tuple(
                _subagent_reservation_record(row)
                for row in cursor.execute(
                    f"SELECT {_SUBAGENT_RESERVATION_COLUMNS} "
                    "FROM subagent_budget_reservation_bindings "
                    f"WHERE {_RUNTIME_SCOPE_SQL} "
                    "ORDER BY reservation_id",
                    scope,
                ).fetchall()
            )
            subagent_execution_specs = tuple(
                _subagent_spec_record(row)
                for row in cursor.execute(
                    f"SELECT {_SUBAGENT_SPEC_COLUMNS} FROM subagent_execution_specs "
                    f"WHERE {_RUNTIME_SCOPE_SQL} "
                    "ORDER BY recorded_at,invocation_id",
                    scope,
                ).fetchall()
            )
        assert context.run_id is not None
        return RuntimeAssuranceScopeSnapshot(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            actor_id=context.actor_id,
            run_id=context.run_id,
            execution_epoch=context.execution_epoch,
            fencing_generation=context.fencing_generation,
            authority_revision=context.authority_revision,
            revision_set_id=revision_set_id,
            pending_tool_calls=pending_tool_calls,
            tool_results=tool_results,
            step_plans=step_plans,
            runtime_authority_receipts=runtime_authority_receipts,
            capability_leases=capability_leases,
            executor_generations=executor_generations,
            environment_attachments=environment_attachments,
            executor_replacement_effects=executor_replacement_effects,
            workspace_leases=workspace_leases,
            event_registrations=event_registrations,
            durable_events=durable_events,
            typed_ingress=typed_ingress,
            subagent_budget_reservations=subagent_budget_reservations,
            subagent_execution_specs=subagent_execution_specs,
        )

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
    ) -> RuntimeAuthorityCapabilityReceiptRecord:
        _port_context(context, revision_set_id)
        operation_invocation_id = _port_text(
            operation_invocation_id,
            "operation_invocation_id",
            maximum=512,
        )
        self._require_active_invocation_operation(operation_invocation_id)
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        authority_snapshot_id = _port_authority_snapshot(
            context,
            authority_snapshot_id,
        )
        normalized_capabilities = tuple(
            sorted(_port_strings(capabilities, "capabilities"))
        )
        if not isinstance(delegation_allowed, bool):
            raise ValidationError("delegation_allowed must be boolean")
        require_sha256_digest(authority_digest, field="authority_digest")
        origin_skill_id = _port_text(origin_skill_id, "origin_skill_id", maximum=512)
        origin_skill_name = _port_text(
            origin_skill_name,
            "origin_skill_name",
            maximum=512,
        )
        origin_owner_kernel = _port_text(
            origin_owner_kernel,
            "origin_owner_kernel",
            maximum=2,
        )
        if origin_owner_kernel not in {f"K{index}" for index in range(1, 9)}:
            raise ValidationError("origin_owner_kernel is invalid")
        origin_execution_id = _port_text(
            origin_execution_id,
            "origin_execution_id",
            maximum=512,
        )
        origin_step_id = _port_text(origin_step_id, "origin_step_id", maximum=512)
        extension_skill = _port_text(
            extension_skill,
            "extension_skill",
            maximum=512,
        )
        origin_receipt_ref = _port_text(
            origin_receipt_ref,
            "origin_receipt_ref",
        )
        origin_receipt_state = _port_text(
            origin_receipt_state,
            "origin_receipt_state",
            maximum=16,
        )
        if origin_receipt_state not in {
            "PLANNING",
            "EXECUTING",
            "RESUMING",
            "VERIFYING",
            "CERTIFYING",
        }:
            raise ValidationError("origin_receipt_state is not active")
        require_sha256_digest(
            origin_receipt_digest,
            field="origin_receipt_digest",
        )
        origin_signing_key_id = _port_text(
            origin_signing_key_id,
            "origin_signing_key_id",
            maximum=512,
        )
        origin_signature_algorithm = _port_text(
            origin_signature_algorithm,
            "origin_signature_algorithm",
            maximum=32,
        )
        if origin_signature_algorithm not in HostSignedEnvelope._ALGORITHMS:
            raise ValidationError("origin signature algorithm is unsupported")
        origin_signature = _port_text(
            origin_signature,
            "origin_signature",
            maximum=4096,
        )
        if not isinstance(host_envelope, HostSignedEnvelope):
            raise ValidationError("host_envelope must be typed")
        _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        identity = (*scope, operation_invocation_id)
        with self._authority_transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            attachments = cursor.execute(
                "SELECT environment_id,owner_authority_ref,state "
                "FROM environment_attachments "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? AND state='ACTIVE' "
                "ORDER BY server_id FOR KEY SHARE",
                (*scope, environment_id),
            ).fetchall()
            if len(attachments) != 1 or not hmac.compare_digest(
                str(attachments[0]["owner_authority_ref"]),
                authority_snapshot_id,
            ):
                raise ConflictError(
                    "authority receipt requires its exact active environment",
                    code="AUTHORITY_RECEIPT_ENVIRONMENT_NOT_ACTIVE",
                )
            existing = cursor.execute(
                f"SELECT {_AUTHORITY_RECEIPT_COLUMNS} "
                "FROM runtime_authority_capability_receipts "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND operation_invocation_id=? FOR UPDATE",
                identity,
            ).fetchone()
            if existing is not None:
                record = _authority_receipt_record(existing)
                if not (
                    record.environment_id == environment_id
                    and hmac.compare_digest(
                        record.authority_snapshot_id,
                        authority_snapshot_id,
                    )
                    and record.capabilities == normalized_capabilities
                    and record.delegation_allowed is delegation_allowed
                    and hmac.compare_digest(record.authority_digest, authority_digest)
                    and record.origin_skill_id == origin_skill_id
                    and record.origin_skill_name == origin_skill_name
                    and record.origin_owner_kernel == origin_owner_kernel
                    and record.origin_execution_id == origin_execution_id
                    and record.origin_step_id == origin_step_id
                    and record.extension_skill == extension_skill
                    and record.origin_receipt_ref == origin_receipt_ref
                    and record.origin_receipt_state == origin_receipt_state
                    and hmac.compare_digest(
                        record.origin_receipt_digest,
                        origin_receipt_digest,
                    )
                    and record.origin_signing_key_id == origin_signing_key_id
                    and record.origin_signature_algorithm
                    == origin_signature_algorithm
                    and hmac.compare_digest(
                        record.origin_signature,
                        origin_signature,
                    )
                    and record.host_envelope == host_envelope
                ):
                    raise ConflictError(
                        "authority capability receipt replay diverges",
                        code="AUTHORITY_RECEIPT_CONFLICT",
                    )
                return record
            inserted = cursor.execute(
                "INSERT INTO runtime_authority_capability_receipts("
                f"{_AUTHORITY_RECEIPT_COLUMNS}) VALUES ("
                "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT DO NOTHING",
                (
                    context.tenant_id,
                    context.project_id,
                    context.run_id,
                    context.actor_id,
                    context.execution_epoch,
                    context.fencing_generation,
                    context.authority_revision,
                    revision_set_id,
                    operation_invocation_id,
                    environment_id,
                    authority_snapshot_id,
                    canonical_json(list(normalized_capabilities)),
                    delegation_allowed,
                    authority_digest,
                    origin_skill_id,
                    origin_skill_name,
                    origin_owner_kernel,
                    origin_execution_id,
                    origin_step_id,
                    extension_skill,
                    origin_receipt_ref,
                    origin_receipt_state,
                    origin_receipt_digest,
                    origin_signing_key_id,
                    origin_signature_algorithm,
                    origin_signature,
                    host_envelope.payload_digest,
                    host_envelope.envelope_digest,
                    host_envelope.issuer,
                    host_envelope.signing_key_id,
                    host_envelope.signature_algorithm,
                    host_envelope.signature,
                    _iso(host_envelope.issued_at),
                    host_envelope.verifier_id,
                    host_envelope.verification_evidence_ref,
                    host_envelope.verification_evidence_digest,
                    _iso(host_envelope.verified_at),
                ),
            )
            if inserted.rowcount != 1:
                raise ConflictError(
                    "authority capability receipt was concurrently bound",
                    code="AUTHORITY_RECEIPT_CONFLICT",
                )
            row = cursor.execute(
                f"SELECT {_AUTHORITY_RECEIPT_COLUMNS} "
                "FROM runtime_authority_capability_receipts "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND operation_invocation_id=?",
                identity,
            ).fetchone()
            if row is None:
                raise IntegrityError(
                    "authority capability receipt disappeared after persistence",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _authority_receipt_record(row)
            return record

    @staticmethod
    def _lock_authority_capability_receipt(
        cursor: _PostgresCursor,
        context: SecurityContext,
        *,
        revision_set_id: str,
        operation_invocation_id: str,
    ) -> RuntimeAuthorityCapabilityReceiptRecord:
        scope = _runtime_scope_parameters(context, revision_set_id)
        row = cursor.execute(
            f"SELECT {_AUTHORITY_RECEIPT_COLUMNS} "
            "FROM runtime_authority_capability_receipts "
            f"WHERE {_RUNTIME_SCOPE_SQL} AND operation_invocation_id=? FOR UPDATE",
            (*scope, operation_invocation_id),
        ).fetchone()
        if row is None:
            raise ConflictError(
                "operation has no durable authority capability receipt",
                code="AUTHORITY_RECEIPT_NOT_FOUND",
            )
        # Construction revalidates the complete owner attribution and signed
        # Host envelope.  A structurally valid digest alone is never accepted.
        return _authority_receipt_record(row)

    @classmethod
    def _require_authority_capability_receipt(
        cls,
        cursor: _PostgresCursor,
        context: SecurityContext,
        *,
        revision_set_id: str,
        operation_invocation_id: str,
        expected_environment_id: str,
        expected_authority_snapshot_id: str,
        authorized_capabilities: Sequence[str],
    ) -> RuntimeAuthorityCapabilityReceiptRecord:
        receipt = cls._lock_authority_capability_receipt(
            cursor,
            context,
            revision_set_id=revision_set_id,
            operation_invocation_id=operation_invocation_id,
        )
        normalized_authorized = frozenset(authorized_capabilities)
        if (
            receipt.environment_id != expected_environment_id
            or not hmac.compare_digest(
                receipt.authority_snapshot_id,
                expected_authority_snapshot_id,
            )
            or not normalized_authorized.issubset(receipt.capabilities)
        ):
            raise AuthorizationError(
                "operation authority receipt diverges from the trusted authority",
                code="AUTHORITY_CAPABILITY_MISMATCH",
            )
        return receipt

    @staticmethod
    def _assert_active_tool_call_dependencies(
        cursor: _PostgresCursor,
        context: SecurityContext,
        *,
        revision_set_id: str,
        execution_plan_hash: str,
        environment_id: str,
        tool_id: str,
        authority_snapshot_id: str,
    ) -> None:
        scope = _runtime_scope_parameters(context, revision_set_id)
        plan = cursor.execute(
            "SELECT plan_hash,environment_snapshot_id,authority_snapshot_id,state,"
            "tool_plan,tool_contracts,handler_digests "
            "FROM step_execution_plans "
            f"WHERE {_RUNTIME_SCOPE_SQL} AND plan_hash=? FOR KEY SHARE",
            (*scope, execution_plan_hash),
        ).fetchone()
        if (
            plan is None
            or str(plan["state"]) != StepPlanState.ACTIVE.value
            or not hmac.compare_digest(str(plan["plan_hash"]), execution_plan_hash)
            or not hmac.compare_digest(
                str(plan["authority_snapshot_id"]),
                authority_snapshot_id,
            )
        ):
            raise ConflictError(
                "tool call requires its exact active execution plan",
                code="TOOL_CALL_PLAN_NOT_ACTIVE",
            )
        tool_plan = _json_object(plan["tool_plan"], "tool_plan")
        tool_contracts = _json_object(plan["tool_contracts"], "tool_contracts")
        handler_digests = _json_object(plan["handler_digests"], "handler_digests")
        planned_tools = _port_strings(tool_plan.get("tools", ()), "tool_plan.tools")
        if (
            set(tool_plan) != {"tools"}
            or tool_id not in planned_tools
            or set(tool_contracts) != set(planned_tools)
            or set(handler_digests) != set(planned_tools)
            or not isinstance(tool_contracts.get(tool_id), Mapping)
        ):
            raise ConflictError(
                "tool call is not present in the exact active execution plan",
                code="TOOL_CALL_NOT_PLANNED",
            )
        tool_binding = cursor.execute(
            "SELECT tool_contract,contract_digest,handler_digest "
            "FROM step_plan_tool_bindings "
            f"WHERE {_RUNTIME_SCOPE_SQL} AND plan_hash=? AND tool_id=? FOR KEY SHARE",
            (*scope, execution_plan_hash, tool_id),
        ).fetchone()
        expected_contract_digest = digest_object(
            tool_contracts[tool_id],
            domain="delta-step-plan-tool-contract",
        )
        if (
            tool_binding is None
            or canonical_json(
                _json_object(tool_binding["tool_contract"], "tool_contract")
            )
            != canonical_json(tool_contracts[tool_id])
            or not hmac.compare_digest(
                str(tool_binding["contract_digest"]),
                expected_contract_digest,
            )
            or str(tool_binding["handler_digest"]) != str(handler_digests[tool_id])
        ):
            raise ConflictError(
                "tool call binding diverges from the exact active execution plan",
                code="TOOL_CALL_BINDING_DRIFT",
            )
        attachments = cursor.execute(
            "SELECT snapshot_id,owner_authority_ref,state "
            "FROM environment_attachments "
            f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? AND state='ACTIVE' "
            "ORDER BY server_id FOR KEY SHARE",
            (*scope, environment_id),
        ).fetchall()
        if len(attachments) != 1:
            raise ConflictError(
                "tool call requires one exact active environment attachment",
                code="TOOL_CALL_ENVIRONMENT_NOT_ACTIVE",
            )
        attachment = attachments[0]
        if (
            str(attachment["state"]) != EnvironmentAttachmentState.ACTIVE.value
            or not hmac.compare_digest(
                str(attachment["owner_authority_ref"]),
                authority_snapshot_id,
            )
            or str(attachment["snapshot_id"])
            != str(plan["environment_snapshot_id"])
        ):
            raise ConflictError(
                "tool call environment attachment diverges from its active plan",
                code="TOOL_CALL_ENVIRONMENT_DRIFT",
            )

    @staticmethod
    def _reconcile_pending_tool_call(
        cursor: _PostgresCursor,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        call_id: str,
        attempt: int,
        execution_plan_hash: str,
        environment_id: str,
        authority_snapshot_id: str,
        reconciled_at: datetime,
    ) -> PendingToolCallBindingRecord:
        scope = _runtime_scope_parameters(context, revision_set_id)
        identity = (*scope, call_id)
        row = cursor.execute(
            f"SELECT {_PENDING_TOOL_CALL_COLUMNS} "
            "FROM pending_tool_call_bindings "
            f"WHERE {_RUNTIME_SCOPE_SQL} AND call_id=? FOR UPDATE",
            identity,
        ).fetchone()
        if row is None:
            raise ConflictError(
                "tool result has no durable pending call binding",
                code="PENDING_TOOL_CALL_NOT_FOUND",
            )
        current = _pending_tool_call_record(row)
        if (
            current.invocation_id != invocation_id
            or current.attempt != attempt
            or not hmac.compare_digest(
                current.execution_plan_hash,
                execution_plan_hash,
            )
            or current.environment_id != environment_id
            or not hmac.compare_digest(
                current.authority_snapshot_id,
                authority_snapshot_id,
            )
        ):
            raise ConflictError(
                "tool result diverges from its durable pending call binding",
                code="PENDING_TOOL_CALL_CONFLICT",
            )
        if current.state is PendingToolCallBindingState.RECONCILED:
            return current
        changed = cursor.execute(
            "UPDATE pending_tool_call_bindings SET state='RECONCILED',"
            "reconciled_at=?,updated_at=? "
            f"WHERE {_RUNTIME_SCOPE_SQL} AND call_id=? AND state='PENDING'",
            (_iso(reconciled_at), _iso(reconciled_at), *identity),
        )
        if changed.rowcount != 1:
            raise ConflictError(
                "pending tool-call reconciliation compare-and-swap failed",
                code="PENDING_TOOL_CALL_CONFLICT",
            )
        updated = cursor.execute(
            f"SELECT {_PENDING_TOOL_CALL_COLUMNS} "
            "FROM pending_tool_call_bindings "
            f"WHERE {_RUNTIME_SCOPE_SQL} AND call_id=?",
            identity,
        ).fetchone()
        if updated is None:
            raise IntegrityError(
                "pending tool-call binding disappeared after reconciliation",
                code="DELTA_STORAGE_DRIFT",
            )
        record = _pending_tool_call_record(updated)
        if record.state is not PendingToolCallBindingState.RECONCILED:
            raise IntegrityError(
                "pending tool-call binding did not reconcile",
                code="DELTA_STORAGE_DRIFT",
            )
        return record

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
    ) -> PendingToolCallBindingRecord:
        _port_context(context, revision_set_id)
        invocation_id = _port_text(invocation_id, "invocation_id", maximum=512)
        self._require_active_invocation_operation(invocation_id)
        call_id = _port_text(call_id, "call_id", maximum=512)
        attempt = _port_positive(attempt, "attempt")
        require_sha256_digest(execution_plan_hash, field="execution_plan_hash")
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        tool_id = _port_text(tool_id, "tool_id", maximum=512)
        authority_snapshot_id = _port_authority_snapshot(
            context,
            authority_snapshot_id,
        )
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        identity = (*scope, call_id)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            self._assert_active_tool_call_dependencies(
                cursor,
                context,
                revision_set_id=revision_set_id,
                execution_plan_hash=execution_plan_hash,
                environment_id=environment_id,
                tool_id=tool_id,
                authority_snapshot_id=authority_snapshot_id,
            )
            existing = cursor.execute(
                f"SELECT {_PENDING_TOOL_CALL_COLUMNS} "
                "FROM pending_tool_call_bindings "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND call_id=? FOR UPDATE",
                identity,
            ).fetchone()
            if existing is not None:
                record = _pending_tool_call_record(existing)
                if (
                    record.invocation_id != invocation_id
                    or record.attempt != attempt
                    or not hmac.compare_digest(
                        record.execution_plan_hash,
                        execution_plan_hash,
                    )
                    or record.environment_id != environment_id
                    or record.tool_id != tool_id
                    or not hmac.compare_digest(
                        record.authority_snapshot_id,
                        authority_snapshot_id,
                    )
                ):
                    raise ConflictError(
                        "pending tool-call identity is bound to different content",
                        code="PENDING_TOOL_CALL_CONFLICT",
                    )
                return record
            try:
                inserted = cursor.execute(
                    "INSERT INTO pending_tool_call_bindings("
                    f"{_PENDING_TOOL_CALL_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'PENDING',?,?,NULL) "
                    "ON CONFLICT DO NOTHING",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        context.actor_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        invocation_id,
                        call_id,
                        attempt,
                        execution_plan_hash,
                        environment_id,
                        tool_id,
                        authority_snapshot_id,
                        _iso(timestamp),
                        _iso(timestamp),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "pending tool-call identity conflicts",
                    code="PENDING_TOOL_CALL_CONFLICT",
                ) from exc
            if inserted.rowcount != 1:
                raise ConflictError(
                    "pending tool-call identity was concurrently claimed",
                    code="PENDING_TOOL_CALL_CONFLICT",
                )
            row = cursor.execute(
                f"SELECT {_PENDING_TOOL_CALL_COLUMNS} "
                "FROM pending_tool_call_bindings "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND call_id=? FOR UPDATE",
                identity,
            ).fetchone()
            if row is None:
                raise IntegrityError(
                    "pending tool-call binding disappeared after persistence",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _pending_tool_call_record(row)
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="PENDING_TOOL_CALL_BOUND",
                subject_id=call_id,
                payload={
                    "invocation_id": invocation_id,
                    "call_id": call_id,
                    "attempt": attempt,
                    "execution_plan_hash": execution_plan_hash,
                    "environment_id": environment_id,
                    "tool_id": tool_id,
                    "authority_snapshot_id": authority_snapshot_id,
                },
            )
            return record

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
    ) -> ToolResultCommitRecord:
        """Durably capture the raw result before any interceptor can execute."""

        _port_context(context, revision_set_id)
        invocation_id = _port_text(invocation_id, "invocation_id", maximum=512)
        self._require_active_invocation_operation(invocation_id)
        call_id = _port_text(call_id, "call_id", maximum=512)
        attempt = _port_positive(attempt, "attempt")
        require_sha256_digest(execution_plan_hash, field="execution_plan_hash")
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        authority_snapshot_id = _port_authority_snapshot(
            context,
            authority_snapshot_id,
        )
        raw_result_ref = _port_text(raw_result_ref, "raw_result_ref")
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        parameters = (*scope, invocation_id, call_id, attempt)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            assert context.run_id is not None
            assert context.authority_revision is not None
            pending = cursor.execute(
                f"SELECT {_PENDING_TOOL_CALL_COLUMNS} "
                "FROM pending_tool_call_bindings "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND call_id=? FOR UPDATE",
                (*scope, call_id),
            ).fetchone()
            if pending is None:
                raise ConflictError(
                    "tool result has no durable pending call binding",
                    code="PENDING_TOOL_CALL_NOT_FOUND",
                )
            binding = _pending_tool_call_record(pending)
            if (
                binding.state is not PendingToolCallBindingState.PENDING
                or binding.invocation_id != invocation_id
                or binding.attempt != attempt
                or not hmac.compare_digest(
                    binding.execution_plan_hash,
                    execution_plan_hash,
                )
                or binding.environment_id != environment_id
                or not hmac.compare_digest(
                    binding.authority_snapshot_id,
                    authority_snapshot_id,
                )
            ):
                raise ConflictError(
                    "tool result diverges from its durable pending call binding",
                    code="PENDING_TOOL_CALL_CONFLICT",
                )
            self._assert_active_tool_call_dependencies(
                cursor,
                context,
                revision_set_id=revision_set_id,
                execution_plan_hash=execution_plan_hash,
                environment_id=environment_id,
                tool_id=binding.tool_id,
                authority_snapshot_id=authority_snapshot_id,
            )
            try:
                inserted = cursor.execute(
                    "INSERT INTO tool_result_commits("
                    f"{_TOOL_RESULT_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                    "'RAW_CAPTURED',?,?,?,?,?,NULL) "
                    "ON CONFLICT (tenant_id,project_id,run_id,execution_epoch,"
                    "fencing_generation,authority_revision,revision_set_id,"
                    "invocation_id,call_id,attempt) DO NOTHING",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        context.actor_id,
                        invocation_id,
                        call_id,
                        attempt,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        execution_plan_hash,
                        environment_id,
                        authority_snapshot_id,
                        raw_result_ref,
                        raw_result_ref,
                        "[]",
                        None,
                        None,
                        None,
                        _iso(timestamp),
                        _iso(timestamp),
                        None,
                        None,
                        None,
                    ),
                )
                inserted_count = inserted.rowcount
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "tool result raw-capture identity conflicts",
                    code="TOOL_RESULT_COMMIT_CONFLICT",
                ) from exc
            row = cursor.execute(
                f"SELECT {_TOOL_RESULT_COLUMNS} FROM tool_result_commits "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=? FOR UPDATE",
                parameters,
            ).fetchone()
            if row is None:
                raise ConflictError(
                    "tool result raw-capture identity is occupied outside scope",
                    code="TOOL_RESULT_COMMIT_CONFLICT",
                )
            record = _tool_result_record(row)
            if not (
                record.execution_plan_hash == execution_plan_hash
                and record.environment_id == environment_id
                and record.authority_snapshot_id == authority_snapshot_id
                and record.raw_result_ref == raw_result_ref
            ):
                raise ConflictError(
                    "tool result raw-capture replay diverges",
                    code="TOOL_RESULT_COMMIT_CONFLICT",
                )
            if inserted_count == 1:
                self._append_runtime_assurance_outbox(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    event_type="TOOL_RESULT_RAW_CAPTURED",
                    subject_id=canonical_json(
                        [invocation_id, call_id, attempt, context.execution_epoch]
                    ),
                    payload={
                        "commitKey": _tool_result_commit_key(
                            invocation_id,
                            call_id,
                            attempt,
                            context.execution_epoch,
                        ),
                        "invocation_id": invocation_id,
                        "call_id": call_id,
                        "attempt": attempt,
                        "execution_plan_hash": execution_plan_hash,
                        "environment_id": environment_id,
                        "authority_snapshot_id": authority_snapshot_id,
                        "raw_result_ref": raw_result_ref,
                        "effective_result_ref": raw_result_ref,
                    },
                )
            return record

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
    ) -> ToolResultCommitRecord:
        _port_context(context, revision_set_id)
        invocation_id = _port_text(invocation_id, "invocation_id", maximum=512)
        self._require_active_invocation_operation(invocation_id)
        call_id = _port_text(call_id, "call_id", maximum=512)
        attempt = _port_positive(attempt, "attempt")
        execution_epoch = _port_positive(execution_epoch, "execution_epoch")
        if execution_epoch != context.execution_epoch:
            raise ConflictError(
                "tool result execution epoch is stale", code="STALE_EPOCH"
            )
        if expected_state is not ToolResultCommitState.RAW_CAPTURED:
            raise ValidationError(
                "tool result interception requires expected_state RAW_CAPTURED"
            )
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        parameters = (*scope, invocation_id, call_id, attempt)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            row = cursor.execute(
                f"SELECT {_TOOL_RESULT_COLUMNS} FROM tool_result_commits "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=? FOR UPDATE",
                parameters,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "tool result raw capture was not found",
                    code="TOOL_RESULT_COMMIT_NOT_FOUND",
                )
            current = _tool_result_record(row)
            if current.state is ToolResultCommitState.INTERCEPTING:
                return current
            if current.state is not expected_state:
                raise ConflictError(
                    "tool result interception state is stale",
                    code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
                )
            changed = cursor.execute(
                "UPDATE tool_result_commits SET state='INTERCEPTING',updated_at=? "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=? AND state='RAW_CAPTURED'",
                (_iso(timestamp), *parameters),
            )
            if changed.rowcount != 1:
                raise ConflictError(
                    "tool result interception compare-and-swap failed",
                    code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
                )
            updated = cursor.execute(
                f"SELECT {_TOOL_RESULT_COLUMNS} FROM tool_result_commits "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=?",
                parameters,
            ).fetchone()
            if updated is None:
                raise IntegrityError(
                    "tool result disappeared after interception claim",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _tool_result_record(updated)
            if record.state is not ToolResultCommitState.INTERCEPTING:
                raise IntegrityError(
                    "tool result interception claim did not persist",
                    code="DELTA_STORAGE_DRIFT",
                )
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="TOOL_RESULT_INTERCEPTING",
                subject_id=canonical_json(
                    [invocation_id, call_id, attempt, execution_epoch]
                ),
                payload={
                    "commitKey": _tool_result_commit_key(
                        invocation_id,
                        call_id,
                        attempt,
                        execution_epoch,
                    ),
                    "invocation_id": invocation_id,
                    "call_id": call_id,
                    "attempt": attempt,
                    "execution_plan_hash": record.execution_plan_hash,
                    "environment_id": record.environment_id,
                    "authority_snapshot_id": record.authority_snapshot_id,
                    "raw_result_ref": record.raw_result_ref,
                },
            )
            return record

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
    ) -> ToolResultCommitRecord:
        _port_context(context, revision_set_id)
        invocation_id = _port_text(invocation_id, "invocation_id", maximum=512)
        self._require_active_invocation_operation(invocation_id)
        call_id = _port_text(call_id, "call_id", maximum=512)
        attempt = _port_positive(attempt, "attempt")
        require_sha256_digest(execution_plan_hash, field="execution_plan_hash")
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        authority_snapshot_id = _port_authority_snapshot(
            context,
            authority_snapshot_id,
        )
        raw_result_ref = _port_text(raw_result_ref, "raw_result_ref")
        effective_result_ref = _port_text(effective_result_ref, "effective_result_ref")
        chain = tuple(interceptor_chain)
        if len(chain) > 64 or any(
            not isinstance(item, InterceptorCommitRecord) for item in chain
        ):
            raise ValidationError("interceptor_chain is invalid")
        identities = {(item.interceptor_id, item.version) for item in chain}
        if len(identities) != len(chain):
            raise ValidationError("interceptor_chain contains duplicates")
        if mutation_provenance_ref is not None:
            mutation_provenance_ref = _port_text(
                mutation_provenance_ref,
                "mutation_provenance_ref",
            )
        timestamp = _port_time(now, "now", default_now=True)
        serialized_chain = canonical_json(
            [
                {
                    "interceptorId": item.interceptor_id,
                    "version": item.version,
                    "decisionHash": item.decision_hash,
                }
                for item in chain
            ]
        )
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            scope = _runtime_scope_parameters(context, revision_set_id)
            parameters = (*scope, invocation_id, call_id, attempt)
            row = cursor.execute(
                f"SELECT {_TOOL_RESULT_COLUMNS} FROM tool_result_commits "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=? FOR UPDATE",
                parameters,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "tool result interception record was not found",
                    code="TOOL_RESULT_COMMIT_NOT_FOUND",
                )
            current = _tool_result_record(row)
            immutable_exact = (
                current.execution_plan_hash == execution_plan_hash
                and current.environment_id == environment_id
                and current.authority_snapshot_id == authority_snapshot_id
                and current.raw_result_ref == raw_result_ref
            )
            if not immutable_exact:
                raise ConflictError(
                    "tool result commit replay diverges from durable content",
                    code="TOOL_RESULT_COMMIT_CONFLICT",
                )
            terminal_exact = (
                current.effective_result_ref == effective_result_ref
                and current.interceptor_chain == chain
                and current.mutation_provenance_ref == mutation_provenance_ref
            )
            if current.state in {
                ToolResultCommitState.COMMITTED,
                ToolResultCommitState.PUBLISHED,
            }:
                if not terminal_exact:
                    raise ConflictError(
                        "tool result commit replay changed terminal content",
                        code="TOOL_RESULT_COMMIT_CONFLICT",
                    )
                self._reconcile_pending_tool_call(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    invocation_id=invocation_id,
                    call_id=call_id,
                    attempt=attempt,
                    execution_plan_hash=execution_plan_hash,
                    environment_id=environment_id,
                    authority_snapshot_id=authority_snapshot_id,
                    reconciled_at=timestamp,
                )
                return current
            if current.state is not ToolResultCommitState.INTERCEPTING:
                raise ConflictError(
                    "tool result must be durably intercepting before commit",
                    code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
                )
            changed = cursor.execute(
                "UPDATE tool_result_commits SET state='COMMITTED',"
                "effective_result_ref=?,interceptor_chain=?,"
                "mutation_provenance_ref=?,failure_kind=NULL,failure_reason=NULL,"
                "updated_at=?,committed_at=?,published_at=NULL,aborted_at=NULL "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=? AND state='INTERCEPTING'",
                (
                    effective_result_ref,
                    serialized_chain,
                    mutation_provenance_ref,
                    _iso(timestamp),
                    _iso(timestamp),
                    *parameters,
                ),
            )
            if changed.rowcount != 1:
                raise ConflictError(
                    "tool result commit compare-and-swap failed",
                    code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
                )
            updated = cursor.execute(
                f"SELECT {_TOOL_RESULT_COLUMNS} FROM tool_result_commits "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=?",
                parameters,
            ).fetchone()
            if updated is None:
                raise IntegrityError(
                    "tool result disappeared after durable commit",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _tool_result_record(updated)
            if record.state is not ToolResultCommitState.COMMITTED or not (
                record.effective_result_ref == effective_result_ref
                and record.interceptor_chain == chain
                and record.mutation_provenance_ref == mutation_provenance_ref
            ):
                raise IntegrityError(
                    "tool result commit did not persist exact terminal content",
                    code="DELTA_STORAGE_DRIFT",
                )
            self._reconcile_pending_tool_call(
                cursor,
                context,
                revision_set_id=revision_set_id,
                invocation_id=invocation_id,
                call_id=call_id,
                attempt=attempt,
                execution_plan_hash=execution_plan_hash,
                environment_id=environment_id,
                authority_snapshot_id=authority_snapshot_id,
                reconciled_at=timestamp,
            )
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="TOOL_RESULT_COMMITTED",
                subject_id=canonical_json(
                    [invocation_id, call_id, attempt, context.execution_epoch]
                ),
                payload={
                    "commitKey": _tool_result_commit_key(
                        invocation_id,
                        call_id,
                        attempt,
                        context.execution_epoch,
                    ),
                    "invocation_id": invocation_id,
                    "call_id": call_id,
                    "attempt": attempt,
                    "execution_plan_hash": execution_plan_hash,
                    "environment_id": environment_id,
                    "authority_snapshot_id": authority_snapshot_id,
                    "raw_result_ref": raw_result_ref,
                    "effective_result_ref": effective_result_ref,
                    "mutation_provenance_ref": mutation_provenance_ref,
                },
            )
            return record

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
    ) -> ToolResultCommitRecord:
        _port_context(context, revision_set_id)
        subject_invocation_id = _port_text(
            subject_invocation_id,
            "subject_invocation_id",
            maximum=512,
        )
        operation_invocation_id = _port_text(
            operation_invocation_id,
            "operation_invocation_id",
            maximum=512,
        )
        self._require_active_invocation_operation(operation_invocation_id)
        call_id = _port_text(call_id, "call_id", maximum=512)
        attempt = _port_positive(attempt, "attempt")
        execution_epoch = _port_positive(execution_epoch, "execution_epoch")
        if execution_epoch != context.execution_epoch:
            raise ConflictError(
                "tool result execution epoch is stale", code="STALE_EPOCH"
            )
        require_sha256_digest(
            expected_execution_plan_hash,
            field="expected_execution_plan_hash",
        )
        expected_environment_id = _port_text(
            expected_environment_id,
            "expected_environment_id",
            maximum=512,
        )
        expected_authority_snapshot_id = _port_authority_snapshot(
            context,
            expected_authority_snapshot_id,
        )
        if not isinstance(expected_state, ToolResultCommitState) or not isinstance(
            target_state,
            ToolResultCommitState,
        ):
            raise ValidationError("tool result states must be typed")
        if (
            expected_state is not ToolResultCommitState.COMMITTED
            or target_state
            not in {
                ToolResultCommitState.PUBLISHED,
                ToolResultCommitState.ABORTED,
            }
        ):
            raise ValidationError("tool result transition is not allowed")
        if target_state is ToolResultCommitState.ABORTED:
            if not isinstance(failure_kind, ToolResultFailureKind):
                raise ValidationError("aborted tool result requires typed failure_kind")
            if failure_reason is None:
                raise ValidationError("aborted tool result requires failure_reason")
            failure_reason = _port_text(failure_reason, "failure_reason")
        elif failure_kind is not None or failure_reason is not None:
            raise ValidationError(
                "published tool result cannot contain failure details"
            )
        timestamp = _port_time(now, "now", default_now=True)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            assert context.run_id is not None
            scope = _runtime_scope_parameters(context, revision_set_id)
            parameters = (
                *scope,
                subject_invocation_id,
                call_id,
                attempt,
            )
            row = cursor.execute(
                f"SELECT {_TOOL_RESULT_COLUMNS} FROM tool_result_commits "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=? FOR UPDATE",
                parameters,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "tool result commit was not found",
                    code="TOOL_RESULT_COMMIT_NOT_FOUND",
                )
            current = _tool_result_record(row)
            if not (
                hmac.compare_digest(
                    current.execution_plan_hash,
                    expected_execution_plan_hash,
                )
                and current.environment_id == expected_environment_id
                and hmac.compare_digest(
                    current.authority_snapshot_id,
                    expected_authority_snapshot_id,
                )
            ):
                raise ConflictError(
                    "tool result transition diverges from its durable binding",
                    code="TOOL_RESULT_COMMIT_CONFLICT",
                )
            if current.state is target_state:
                if target_state is ToolResultCommitState.ABORTED and not (
                    current.failure_kind is failure_kind
                    and current.failure_reason == failure_reason
                ):
                    raise ConflictError(
                        "tool result abort replay changed failure details",
                        code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
                    )
                self._reconcile_pending_tool_call(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    invocation_id=subject_invocation_id,
                    call_id=call_id,
                    attempt=attempt,
                    execution_plan_hash=current.execution_plan_hash,
                    environment_id=current.environment_id,
                    authority_snapshot_id=current.authority_snapshot_id,
                    reconciled_at=timestamp,
                )
                return current
            if current.state is not expected_state:
                raise ConflictError(
                    "tool result commit state is stale",
                    code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
                )
            published_at = (
                _iso(timestamp)
                if target_state is ToolResultCommitState.PUBLISHED
                else None
            )
            aborted_at = (
                _iso(timestamp)
                if target_state is ToolResultCommitState.ABORTED
                else None
            )
            update = cursor.execute(
                "UPDATE tool_result_commits SET state=?,updated_at=?,published_at=?,"
                "aborted_at=?,failure_kind=?,failure_reason=? "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=? AND state=?",
                (
                    target_state.value,
                    _iso(timestamp),
                    published_at,
                    aborted_at,
                    None if failure_kind is None else failure_kind.value,
                    failure_reason,
                    *parameters,
                    expected_state.value,
                ),
            )
            if update.rowcount != 1:
                raise ConflictError(
                    "tool result compare-and-swap failed",
                    code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
                )
            updated = cursor.execute(
                f"SELECT {_TOOL_RESULT_COLUMNS} FROM tool_result_commits "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=?",
                parameters,
            ).fetchone()
            if updated is None:
                raise IntegrityError(
                    "tool result disappeared after transition",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _tool_result_record(updated)
            if record.state is not target_state:
                raise IntegrityError(
                    "tool result transition did not persist the target state",
                    code="DELTA_STORAGE_DRIFT",
                )
            self._reconcile_pending_tool_call(
                cursor,
                context,
                revision_set_id=revision_set_id,
                invocation_id=subject_invocation_id,
                call_id=call_id,
                attempt=attempt,
                execution_plan_hash=record.execution_plan_hash,
                environment_id=record.environment_id,
                authority_snapshot_id=record.authority_snapshot_id,
                reconciled_at=timestamp,
            )
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type=f"TOOL_RESULT_{target_state.value}",
                subject_id=canonical_json(
                    [subject_invocation_id, call_id, attempt, execution_epoch]
                ),
                payload={
                    "commitKey": _tool_result_commit_key(
                        subject_invocation_id,
                        call_id,
                        attempt,
                        execution_epoch,
                    ),
                    "subject_invocation_id": subject_invocation_id,
                    "operation_invocation_id": operation_invocation_id,
                    "call_id": call_id,
                    "attempt": attempt,
                    "execution_plan_hash": record.execution_plan_hash,
                    "environment_id": record.environment_id,
                    "authority_snapshot_id": record.authority_snapshot_id,
                    "raw_result_ref": record.raw_result_ref,
                    "effective_result_ref": record.effective_result_ref,
                    "mutation_provenance_ref": record.mutation_provenance_ref,
                    "from_state": expected_state.value,
                    "to_state": target_state.value,
                    "failure_kind": (
                        None if failure_kind is None else failure_kind.value
                    ),
                    "failure_reason": failure_reason,
                },
            )
            return record

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
    ) -> ToolResultCommitRecord:
        """Abort one existing INTERCEPTING result under an active operation claim."""

        _port_context(context, revision_set_id)
        subject_invocation_id = _port_text(
            subject_invocation_id,
            "subject_invocation_id",
            maximum=512,
        )
        operation_invocation_id = _port_text(
            operation_invocation_id,
            "operation_invocation_id",
            maximum=512,
        )
        self._require_active_invocation_operation(operation_invocation_id)
        call_id = _port_text(call_id, "call_id", maximum=512)
        attempt = _port_positive(attempt, "attempt")
        require_sha256_digest(execution_plan_hash, field="execution_plan_hash")
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        authority_snapshot_id = _port_authority_snapshot(context, authority_snapshot_id)
        raw_result_ref = _port_text(raw_result_ref, "raw_result_ref")
        effective_result_ref = _port_text(effective_result_ref, "effective_result_ref")
        chain = tuple(interceptor_chain)
        if len(chain) > 64 or any(
            not isinstance(item, InterceptorCommitRecord) for item in chain
        ):
            raise ValidationError("interceptor_chain is invalid")
        if len({(item.interceptor_id, item.version) for item in chain}) != len(chain):
            raise ValidationError("interceptor_chain contains duplicates")
        if not isinstance(failure_kind, ToolResultFailureKind):
            raise ValidationError("failure_kind must be typed")
        failure_reason = _port_text(failure_reason, "failure_reason")
        if mutation_provenance_ref is not None:
            mutation_provenance_ref = _port_text(
                mutation_provenance_ref,
                "mutation_provenance_ref",
            )
        timestamp = _port_time(now, "now", default_now=True)
        serialized_chain = canonical_json(
            [
                {
                    "interceptorId": item.interceptor_id,
                    "version": item.version,
                    "decisionHash": item.decision_hash,
                }
                for item in chain
            ]
        )
        scope = _runtime_scope_parameters(context, revision_set_id)
        parameters = (*scope, subject_invocation_id, call_id, attempt)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            row = cursor.execute(
                f"SELECT {_TOOL_RESULT_COLUMNS} FROM tool_result_commits "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=? FOR UPDATE",
                parameters,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "tool result expected for abort was not found",
                    code="TOOL_RESULT_COMMIT_NOT_FOUND",
                )
            current = _tool_result_record(row)
            immutable_exact = (
                current.execution_plan_hash == execution_plan_hash
                and current.environment_id == environment_id
                and current.authority_snapshot_id == authority_snapshot_id
                and current.raw_result_ref == raw_result_ref
            )
            terminal_exact = (
                current.effective_result_ref == effective_result_ref
                and current.interceptor_chain == chain
                and current.mutation_provenance_ref == mutation_provenance_ref
            )
            if not immutable_exact:
                raise ConflictError(
                    "tool result abort content diverges from durable content",
                    code="TOOL_RESULT_COMMIT_CONFLICT",
                )
            if current.state is ToolResultCommitState.ABORTED:
                if (
                    terminal_exact
                    and current.failure_kind is failure_kind
                    and current.failure_reason == failure_reason
                    and current.recovery_evidence_ref is None
                ):
                    self._reconcile_pending_tool_call(
                        cursor,
                        context,
                        revision_set_id=revision_set_id,
                        invocation_id=subject_invocation_id,
                        call_id=call_id,
                        attempt=attempt,
                        execution_plan_hash=execution_plan_hash,
                        environment_id=environment_id,
                        authority_snapshot_id=authority_snapshot_id,
                        reconciled_at=timestamp,
                    )
                    return current
                raise ConflictError(
                    "tool result abort replay changed terminal content",
                    code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
                )
            if current.state is not ToolResultCommitState.INTERCEPTING:
                raise ConflictError(
                    "normal tool-result abort requires INTERCEPTING",
                    code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
                )
            changed = cursor.execute(
                "UPDATE tool_result_commits SET state='ABORTED',updated_at=?,"
                "aborted_at=?,failure_kind=?,failure_reason=?,"
                "effective_result_ref=?,interceptor_chain=?,"
                "mutation_provenance_ref=?,recovery_evidence_ref=NULL "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=? AND state='INTERCEPTING'",
                (
                    _iso(timestamp),
                    _iso(timestamp),
                    failure_kind.value,
                    failure_reason,
                    effective_result_ref,
                    serialized_chain,
                    mutation_provenance_ref,
                    *parameters,
                ),
            )
            if changed.rowcount != 1:
                raise ConflictError(
                    "tool result abort compare-and-swap failed",
                    code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
                )
            aborted = cursor.execute(
                f"SELECT {_TOOL_RESULT_COLUMNS} FROM tool_result_commits "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=?",
                parameters,
            ).fetchone()
            if aborted is None:
                raise IntegrityError(
                    "tool result abort disappeared",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _tool_result_record(aborted)
            if record.state is not ToolResultCommitState.ABORTED:
                raise IntegrityError(
                    "tool result abort did not persist",
                    code="DELTA_STORAGE_DRIFT",
                )
            self._reconcile_pending_tool_call(
                cursor,
                context,
                revision_set_id=revision_set_id,
                invocation_id=subject_invocation_id,
                call_id=call_id,
                attempt=attempt,
                execution_plan_hash=record.execution_plan_hash,
                environment_id=record.environment_id,
                authority_snapshot_id=record.authority_snapshot_id,
                reconciled_at=timestamp,
            )
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="TOOL_RESULT_ABORTED",
                subject_id=canonical_json(
                    [subject_invocation_id, call_id, attempt, context.execution_epoch]
                ),
                payload={
                    "commitKey": _tool_result_commit_key(
                        subject_invocation_id,
                        call_id,
                        attempt,
                        context.execution_epoch,
                    ),
                    "subject_invocation_id": subject_invocation_id,
                    "operation_invocation_id": operation_invocation_id,
                    "call_id": call_id,
                    "attempt": attempt,
                    "execution_plan_hash": record.execution_plan_hash,
                    "environment_id": record.environment_id,
                    "authority_snapshot_id": record.authority_snapshot_id,
                    "raw_result_ref": record.raw_result_ref,
                    "effective_result_ref": record.effective_result_ref,
                    "mutation_provenance_ref": record.mutation_provenance_ref,
                    "failure_kind": failure_kind.value,
                    "failure_reason": failure_reason,
                },
            )
            return record

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
    ) -> ToolResultCommitRecord:
        """Recover one precommit result only behind an exact recovery claim epoch."""

        _port_context(context, revision_set_id)
        invocation_id = _port_text(invocation_id, "invocation_id", maximum=512)
        call_id = _port_text(call_id, "call_id", maximum=512)
        attempt = _port_positive(attempt, "attempt")
        expected_claim_epoch = _port_positive(
            expected_claim_epoch,
            "expected_claim_epoch",
        )
        require_sha256_digest(execution_plan_hash, field="execution_plan_hash")
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        authority_snapshot_id = _port_authority_snapshot(context, authority_snapshot_id)
        raw_result_ref = _port_text(raw_result_ref, "raw_result_ref")
        effective_result_ref = _port_text(effective_result_ref, "effective_result_ref")
        recovery_evidence_ref = _port_text(
            recovery_evidence_ref,
            "recovery_evidence_ref",
        )
        if expected_state not in {
            ToolResultCommitState.RAW_CAPTURED,
            ToolResultCommitState.INTERCEPTING,
        }:
            raise ValidationError("recovery expected_state is not precommit")
        if not isinstance(failure_kind, ToolResultFailureKind):
            raise ValidationError("failure_kind must be typed")
        failure_reason = _port_text(failure_reason, "failure_reason")
        if mutation_provenance_ref is not None:
            mutation_provenance_ref = _port_text(
                mutation_provenance_ref,
                "mutation_provenance_ref",
            )
        chain = tuple(interceptor_chain)
        if len(chain) > 64 or any(
            not isinstance(item, InterceptorCommitRecord) for item in chain
        ) or len({(item.interceptor_id, item.version) for item in chain}) != len(chain):
            raise ValidationError("interceptor_chain is invalid")
        serialized_chain = canonical_json(
            [
                {
                    "interceptorId": item.interceptor_id,
                    "version": item.version,
                    "decisionHash": item.decision_hash,
                }
                for item in chain
            ]
        )
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        identity = (*scope, invocation_id, call_id, attempt)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            claim = cursor.execute(
                f"SELECT {_INVOCATION_RECEIPT_COLUMNS} "
                "FROM runtime_assurance_invocation_receipts "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? FOR UPDATE",
                (*scope, invocation_id),
            ).fetchone()
            if (
                claim is None
                or str(claim["state"])
                != RuntimeAssuranceInvocationState.RECOVERY_REQUIRED.value
                or int(claim["claim_epoch"]) != expected_claim_epoch
            ):
                raise ConflictError(
                    "tool-result recovery claim is absent or stale",
                    code="INVOCATION_RECOVERY_REQUIRED",
                )
            row = cursor.execute(
                f"SELECT {_TOOL_RESULT_COLUMNS} FROM tool_result_commits "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=? FOR UPDATE",
                identity,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "tool result expected for recovery was not found",
                    code="TOOL_RESULT_COMMIT_NOT_FOUND",
                )
            current = _tool_result_record(row)
            immutable_exact = (
                current.execution_plan_hash == execution_plan_hash
                and current.environment_id == environment_id
                and current.authority_snapshot_id == authority_snapshot_id
                and current.raw_result_ref == raw_result_ref
            )
            terminal_exact = (
                current.effective_result_ref == effective_result_ref
                and current.interceptor_chain == chain
                and current.mutation_provenance_ref == mutation_provenance_ref
                and current.failure_kind is failure_kind
                and current.failure_reason == failure_reason
                and current.recovery_evidence_ref == recovery_evidence_ref
            )
            if not immutable_exact:
                raise ConflictError(
                    "tool-result recovery diverges from durable content",
                    code="TOOL_RESULT_COMMIT_CONFLICT",
                )
            if current.state is ToolResultCommitState.ABORTED:
                if terminal_exact:
                    self._reconcile_pending_tool_call(
                        cursor,
                        context,
                        revision_set_id=revision_set_id,
                        invocation_id=invocation_id,
                        call_id=call_id,
                        attempt=attempt,
                        execution_plan_hash=execution_plan_hash,
                        environment_id=environment_id,
                        authority_snapshot_id=authority_snapshot_id,
                        reconciled_at=timestamp,
                    )
                    return current
                raise ConflictError(
                    "tool-result recovery replay changed terminal content",
                    code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
                )
            if current.state is not expected_state:
                raise ConflictError(
                    "tool-result recovery state is stale",
                    code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
                )
            changed = cursor.execute(
                "UPDATE tool_result_commits SET state='ABORTED',updated_at=?,"
                "aborted_at=?,failure_kind=?,failure_reason=?,effective_result_ref=?,"
                "interceptor_chain=?,mutation_provenance_ref=?,recovery_evidence_ref=? "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=? AND state=?",
                (
                    _iso(timestamp),
                    _iso(timestamp),
                    failure_kind.value,
                    failure_reason,
                    effective_result_ref,
                    serialized_chain,
                    mutation_provenance_ref,
                    recovery_evidence_ref,
                    *identity,
                    expected_state.value,
                ),
            )
            if changed.rowcount != 1:
                raise ConflictError(
                    "tool-result recovery compare-and-swap failed",
                    code="TOOL_RESULT_COMMIT_STATE_CONFLICT",
                )
            updated = cursor.execute(
                f"SELECT {_TOOL_RESULT_COLUMNS} FROM tool_result_commits "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? AND call_id=? "
                "AND attempt=?",
                identity,
            ).fetchone()
            if updated is None:
                raise IntegrityError(
                    "tool result disappeared after recovery",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _tool_result_record(updated)
            persisted_exact = (
                record.state is ToolResultCommitState.ABORTED
                and record.effective_result_ref == effective_result_ref
                and record.interceptor_chain == chain
                and record.mutation_provenance_ref == mutation_provenance_ref
                and record.failure_kind is failure_kind
                and record.failure_reason == failure_reason
                and record.recovery_evidence_ref == recovery_evidence_ref
            )
            if not persisted_exact:
                raise IntegrityError(
                    "tool-result recovery did not persist exact terminal content",
                    code="DELTA_STORAGE_DRIFT",
                )
            self._reconcile_pending_tool_call(
                cursor,
                context,
                revision_set_id=revision_set_id,
                invocation_id=invocation_id,
                call_id=call_id,
                attempt=attempt,
                execution_plan_hash=execution_plan_hash,
                environment_id=environment_id,
                authority_snapshot_id=authority_snapshot_id,
                reconciled_at=timestamp,
            )
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="TOOL_RESULT_ABORTED_RECOVERY",
                subject_id=canonical_json(
                    [invocation_id, call_id, attempt, context.execution_epoch]
                ),
                payload={
                    "commitKey": _tool_result_commit_key(
                        invocation_id,
                        call_id,
                        attempt,
                        context.execution_epoch,
                    ),
                    "subject_invocation_id": invocation_id,
                    "claim_epoch": expected_claim_epoch,
                    "call_id": call_id,
                    "attempt": attempt,
                    "execution_plan_hash": execution_plan_hash,
                    "environment_id": environment_id,
                    "authority_snapshot_id": authority_snapshot_id,
                    "raw_result_ref": raw_result_ref,
                    "effective_result_ref": effective_result_ref,
                    "mutation_provenance_ref": mutation_provenance_ref,
                    "recovery_evidence_ref": recovery_evidence_ref,
                    "failure_kind": failure_kind.value,
                    "failure_reason": failure_reason,
                },
            )
            return record

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
    ) -> StepExecutionPlanRecord:
        _port_context(context, revision_set_id)
        plan_id = _port_text(plan_id, "plan_id", maximum=512)
        step_id = _port_text(step_id, "step_id", maximum=512)
        require_sha256_digest(plan_hash, field="plan_hash")
        if not isinstance(model_snapshot, Mapping) or not isinstance(
            tool_plan, Mapping
        ):
            raise ValidationError("step plan snapshots must be objects")
        if set(tool_plan) != {"tools"}:
            raise ValidationError("tool_plan has an unsupported shape")
        tools = _port_strings(tool_plan["tools"], "tool_plan.tools")
        if not isinstance(tool_contracts, Mapping) or set(tool_contracts) != set(tools):
            raise ValidationError("tool_contracts must exactly bind every planned tool")
        if any(not isinstance(value, Mapping) for value in tool_contracts.values()):
            raise ValidationError("tool_contracts values must be objects")
        if not isinstance(handler_digests, Mapping) or set(handler_digests) != set(
            tools
        ):
            raise ValidationError(
                "handler_digests must exactly bind every planned tool"
            )
        for tool, digest in handler_digests.items():
            _port_text(tool, "handler_digests key", maximum=512)
            require_sha256_digest(digest, field=f"handler_digests.{tool}")
        model_json = canonical_json(model_snapshot)
        tool_json = canonical_json(tool_plan)
        tool_contracts_json = canonical_json(tool_contracts)
        handler_digests_json = canonical_json(handler_digests)
        normalized_capabilities = _port_strings(capabilities, "capabilities")
        environment_snapshot_id = _port_text(
            environment_snapshot_id,
            "environment_snapshot_id",
            maximum=512,
        )
        authority_snapshot_id = _port_authority_snapshot(
            context,
            authority_snapshot_id,
        )
        tool_mode = _port_text(tool_mode, "tool_mode", maximum=128)
        expected_plan_hash = digest_object(
            {
                "modelSnapshot": model_snapshot,
                "tools": list(tools),
                "toolContracts": tool_contracts,
                "handlerDigests": handler_digests,
                "environmentSnapshotId": environment_snapshot_id,
                "authoritySnapshotId": authority_snapshot_id,
                "mode": tool_mode,
                "capabilities": list(normalized_capabilities),
            },
            domain="delta-execution-plan",
        )
        if not hmac.compare_digest(expected_plan_hash, plan_hash):
            raise ValidationError("plan_hash does not bind the exact execution plan")
        timestamp = _port_time(now, "now", default_now=True)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            assert context.run_id is not None
            assert context.authority_revision is not None
            scope = _runtime_scope_parameters(context, revision_set_id)
            try:
                cursor.execute(
                    "INSERT INTO step_execution_plans("
                    f"{_STEP_PLAN_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'CANDIDATE',?,?,?,?,?) "
                    "ON CONFLICT (tenant_id,project_id,run_id,execution_epoch,"
                    "fencing_generation,authority_revision,revision_set_id,plan_id) "
                    "DO NOTHING",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        context.actor_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        plan_id,
                        step_id,
                        plan_hash,
                        model_json,
                        tool_json,
                        tool_contracts_json,
                        handler_digests_json,
                        canonical_json(list(normalized_capabilities)),
                        tool_mode,
                        environment_snapshot_id,
                        authority_snapshot_id,
                        _iso(timestamp),
                        _iso(timestamp),
                        None,
                        None,
                        None,
                    ),
                )
                inserted_count = cursor.rowcount
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "step plan identity or hash conflicts", code="STEP_PLAN_CONFLICT"
                ) from exc
            row = cursor.execute(
                f"SELECT {_STEP_PLAN_COLUMNS} FROM step_execution_plans "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND plan_id=? FOR UPDATE",
                (
                    *scope,
                    plan_id,
                ),
            ).fetchone()
            if row is None:
                raise ConflictError(
                    "step plan identity is occupied outside the bound scope",
                    code="STEP_PLAN_CONFLICT",
                )
            record = _step_plan_record(row)
            if not (
                record.step_id == step_id
                and record.plan_hash == plan_hash
                and canonical_json(record.model_snapshot) == model_json
                and canonical_json(record.tool_plan) == tool_json
                and canonical_json(record.tool_contracts) == tool_contracts_json
                and canonical_json(record.handler_digests) == handler_digests_json
                and record.capabilities == normalized_capabilities
                and record.tool_mode == tool_mode
                and record.environment_snapshot_id == environment_snapshot_id
                and record.authority_snapshot_id == authority_snapshot_id
            ):
                raise ConflictError(
                    "step plan replay diverges from durable content",
                    code="STEP_PLAN_CONFLICT",
                )
            for tool in tools:
                contract = tool_contracts[tool]
                contract_json = canonical_json(contract)
                contract_digest = digest_object(
                    contract,
                    domain="delta-step-plan-tool-contract",
                )
                binding = cursor.execute(
                    "INSERT INTO step_plan_tool_bindings("
                    "tenant_id,project_id,run_id,actor_id,execution_epoch,"
                    "fencing_generation,authority_revision,revision_set_id,plan_hash,"
                    "tool_id,tool_contract,contract_digest,handler_digest,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        context.actor_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        plan_hash,
                        tool,
                        contract_json,
                        contract_digest,
                        handler_digests[tool],
                        _iso(timestamp),
                    ),
                )
                if binding.rowcount not in {0, 1}:
                    raise IntegrityError(
                        "step-plan tool binding returned an invalid row count",
                        code="DELTA_STORAGE_DRIFT",
                    )
            persisted_bindings = cursor.execute(
                "SELECT tool_id,tool_contract,contract_digest,handler_digest "
                "FROM step_plan_tool_bindings "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND plan_hash=? ORDER BY tool_id FOR KEY SHARE",
                (*scope, plan_hash),
            ).fetchall()
            expected_bindings = tuple(
                (
                    tool,
                    canonical_json(tool_contracts[tool]),
                    digest_object(
                        tool_contracts[tool],
                        domain="delta-step-plan-tool-contract",
                    ),
                    handler_digests[tool],
                )
                for tool in sorted(tools)
            )
            observed_bindings = tuple(
                (
                    str(binding["tool_id"]),
                    canonical_json(
                        _json_object(binding["tool_contract"], "tool_contract")
                    ),
                    str(binding["contract_digest"]),
                    str(binding["handler_digest"]),
                )
                for binding in persisted_bindings
            )
            if observed_bindings != expected_bindings:
                raise ConflictError(
                    "step-plan tool bindings diverge from the canonical plan",
                    code="STEP_PLAN_TOOL_BINDING_CONFLICT",
                )
            if inserted_count == 1:
                self._append_runtime_assurance_outbox(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    event_type="STEP_PLAN_RECORDED",
                    subject_id=plan_id,
                    payload={
                        "plan_id": plan_id,
                        "step_id": step_id,
                        "plan_hash": plan_hash,
                        "state": StepPlanState.CANDIDATE.value,
                    },
                )
            return record

    def transition_step_plan(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        plan_id: str,
        expected_state: StepPlanState,
        target_state: StepPlanState,
        now: datetime | None = None,
    ) -> StepExecutionPlanRecord:
        _port_context(context, revision_set_id)
        plan_id = _port_text(plan_id, "plan_id", maximum=512)
        if not isinstance(expected_state, StepPlanState) or not isinstance(
            target_state, StepPlanState
        ):
            raise ValidationError("step plan states must be typed")
        allowed = {
            (StepPlanState.CANDIDATE, StepPlanState.FINALIZED),
            (StepPlanState.ACTIVE, StepPlanState.RETIRED),
        }
        if (expected_state, target_state) not in allowed:
            raise ValidationError("step plan transition is not allowed")
        timestamp = _port_time(now, "now", default_now=True)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            assert context.run_id is not None
            scope = _runtime_scope_parameters(context, revision_set_id)
            parameters = (
                *scope,
                plan_id,
            )
            row = cursor.execute(
                f"SELECT {_STEP_PLAN_COLUMNS} FROM step_execution_plans "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND plan_id=? FOR UPDATE",
                parameters,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "step plan was not found", code="STEP_PLAN_NOT_FOUND"
                )
            current = _step_plan_record(row)
            if current.state is target_state:
                return current
            if current.state is not expected_state:
                raise ConflictError(
                    "step plan state is stale", code="STEP_PLAN_STATE_CONFLICT"
                )
            finalized_at = (
                _iso(timestamp) if target_state is StepPlanState.FINALIZED else None
            )
            activated_at = None
            retired_at = (
                _iso(timestamp) if target_state is StepPlanState.RETIRED else None
            )
            update = cursor.execute(
                "UPDATE step_execution_plans SET state=?,updated_at=?,"
                "finalized_at=COALESCE(finalized_at,?),"
                "activated_at=COALESCE(activated_at,?),retired_at=COALESCE(retired_at,?) "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND plan_id=? AND state=?",
                (
                    target_state.value,
                    _iso(timestamp),
                    finalized_at,
                    activated_at,
                    retired_at,
                    *parameters,
                    expected_state.value,
                ),
            )
            if update.rowcount != 1:
                raise ConflictError(
                    "step plan compare-and-swap failed", code="STEP_PLAN_STATE_CONFLICT"
                )
            updated = cursor.execute(
                f"SELECT {_STEP_PLAN_COLUMNS} FROM step_execution_plans "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND plan_id=?",
                parameters,
            ).fetchone()
            if updated is None:
                raise IntegrityError(
                    "step plan disappeared after transition", code="DELTA_STORAGE_DRIFT"
                )
            record = _step_plan_record(updated)
            if record.state is not target_state:
                raise IntegrityError(
                    "step plan transition did not persist the target state",
                    code="DELTA_STORAGE_DRIFT",
                )
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type=f"STEP_PLAN_{target_state.value}",
                subject_id=plan_id,
                payload={
                    "plan_id": plan_id,
                    "from_state": expected_state.value,
                    "to_state": target_state.value,
                },
            )
            return record

    def activate_step_plan(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        plan_id: str,
        expected_state: StepPlanState = StepPlanState.FINALIZED,
        now: datetime | None = None,
    ) -> StepExecutionPlanRecord:
        """Atomically replace the active plan within one exact runtime scope."""

        _port_context(context, revision_set_id)
        plan_id = _port_text(plan_id, "plan_id", maximum=512)
        if expected_state is not StepPlanState.FINALIZED:
            raise ValidationError(
                "step plan activation requires expected_state FINALIZED"
            )
        timestamp = _port_time(now, "now", default_now=True)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            scope = _runtime_scope_parameters(context, revision_set_id)
            parameters = (*scope, plan_id)
            target_row = cursor.execute(
                f"SELECT {_STEP_PLAN_COLUMNS} FROM step_execution_plans "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND plan_id=? FOR UPDATE",
                parameters,
            ).fetchone()
            if target_row is None:
                raise NotFoundError(
                    "step plan was not found", code="STEP_PLAN_NOT_FOUND"
                )
            target = _step_plan_record(target_row)
            active_rows = cursor.execute(
                f"SELECT {_STEP_PLAN_COLUMNS} FROM step_execution_plans "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND state='ACTIVE' "
                "ORDER BY plan_id FOR UPDATE",
                scope,
            ).fetchall()
            if len(active_rows) > 1:
                raise IntegrityError(
                    "multiple active step plans violate the durable invariant",
                    code="DELTA_STORAGE_DRIFT",
                )
            active = _step_plan_record(active_rows[0]) if active_rows else None
            if target.state is StepPlanState.ACTIVE:
                if active is None or active.plan_id != target.plan_id:
                    raise IntegrityError(
                        "active step plan index and target state diverged",
                        code="DELTA_STORAGE_DRIFT",
                    )
                return target
            if target.state is not expected_state:
                raise ConflictError(
                    "step plan activation state is stale",
                    code="STEP_PLAN_STATE_CONFLICT",
                )
            if target.finalized_at is None or timestamp < target.finalized_at:
                raise ValidationError(
                    "step plan activation cannot precede finalization"
                )

            retired_plan_id: str | None = None
            if active is not None:
                retired_plan_id = active.plan_id
                if active.plan_id == target.plan_id:
                    raise IntegrityError(
                        "step plan state changed during activation",
                        code="DELTA_STORAGE_DRIFT",
                    )
                retired = cursor.execute(
                    "UPDATE step_execution_plans SET state='RETIRED',updated_at=?,retired_at=? "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND plan_id=? AND state='ACTIVE'",
                    (_iso(timestamp), _iso(timestamp), *scope, active.plan_id),
                )
                if retired.rowcount != 1:
                    raise ConflictError(
                        "active step plan retirement compare-and-swap failed",
                        code="STEP_PLAN_ACTIVE_CONFLICT",
                    )

            activated = cursor.execute(
                "UPDATE step_execution_plans SET state='ACTIVE',updated_at=?,activated_at=? "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND plan_id=? AND state='FINALIZED'",
                (_iso(timestamp), _iso(timestamp), *parameters),
            )
            if activated.rowcount != 1:
                raise ConflictError(
                    "step plan activation compare-and-swap failed",
                    code="STEP_PLAN_STATE_CONFLICT",
                )
            updated = cursor.execute(
                f"SELECT {_STEP_PLAN_COLUMNS} FROM step_execution_plans "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND plan_id=?",
                parameters,
            ).fetchone()
            if updated is None:
                raise IntegrityError(
                    "step plan disappeared after activation",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _step_plan_record(updated)
            if record.state is not StepPlanState.ACTIVE:
                raise IntegrityError(
                    "step plan activation did not persist",
                    code="DELTA_STORAGE_DRIFT",
                )
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="STEP_PLAN_ACTIVATED",
                subject_id=plan_id,
                payload={
                    "plan_id": plan_id,
                    "from_state": expected_state.value,
                    "to_state": StepPlanState.ACTIVE.value,
                    "retired_plan_id": retired_plan_id,
                },
            )
            return record

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
    ) -> CapabilityLeaseRecord:
        _port_context(context, revision_set_id)
        lease_id = _port_text(lease_id, "lease_id", maximum=512)
        invocation_id = _port_text(invocation_id, "invocation_id", maximum=512)
        self._require_active_invocation_operation(invocation_id)
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        authority_snapshot_id = _port_authority_snapshot(
            context,
            authority_snapshot_id,
        )
        normalized_capabilities = _port_strings(capabilities, "capabilities")
        if not normalized_capabilities:
            raise ValidationError("capabilities must not be empty")
        if not isinstance(delegation_allowed, bool):
            raise ValidationError("delegation_allowed must be boolean")
        issued = _port_time(now, "now", default_now=True)
        expiry = _port_time(expires_at, "expires_at")
        if (
            expiry <= issued
            or (expiry - issued).total_seconds() > _MAX_CAPABILITY_LEASE_SECONDS
        ):
            raise ValidationError("capability lease validity window is invalid")
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            assert context.run_id is not None
            assert context.authority_revision is not None
            scope = _runtime_scope_parameters(context, revision_set_id)
            authority_receipt = self._lock_authority_capability_receipt(
                cursor,
                context,
                revision_set_id=revision_set_id,
                operation_invocation_id=invocation_id,
            )
            if (
                authority_receipt.environment_id != environment_id
                or not hmac.compare_digest(
                    authority_receipt.authority_snapshot_id,
                    authority_snapshot_id,
                )
                or not frozenset(normalized_capabilities).issubset(
                    authority_receipt.capabilities
                )
                or (delegation_allowed and not authority_receipt.delegation_allowed)
            ):
                raise ConflictError(
                    "capability lease exceeds its exact operation authority receipt",
                    code="AUTHORITY_RECEIPT_CONFLICT",
                )
            attachments = cursor.execute(
                "SELECT environment_id,owner_authority_ref,state "
                "FROM environment_attachments "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? AND state='ACTIVE' "
                "ORDER BY server_id FOR KEY SHARE",
                (*scope, environment_id),
            ).fetchall()
            if len(attachments) != 1 or not hmac.compare_digest(
                str(attachments[0]["owner_authority_ref"]),
                authority_snapshot_id,
            ):
                raise ConflictError(
                    "capability lease requires its exact active environment",
                    code="CAPABILITY_LEASE_ENVIRONMENT_NOT_ACTIVE",
                )
            active = cursor.execute(
                "SELECT lease_id FROM capability_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? "
                "AND state='ACTIVE' FOR UPDATE",
                (*scope, invocation_id),
            ).fetchone()
            if active is not None and str(active["lease_id"]) != lease_id:
                raise ConflictError(
                    "invocation already has an active capability lease",
                    code="CAPABILITY_LEASE_CONFLICT",
                )
            try:
                cursor.execute(
                    "INSERT INTO capability_leases("
                    f"{_CAPABILITY_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',?,?,?,?,?) "
                    "ON CONFLICT (tenant_id,project_id,run_id,execution_epoch,"
                    "fencing_generation,authority_revision,revision_set_id,lease_id) "
                    "DO NOTHING",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        context.actor_id,
                        lease_id,
                        invocation_id,
                        environment_id,
                        authority_snapshot_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        canonical_json(list(normalized_capabilities)),
                        delegation_allowed,
                        _iso(issued),
                        _iso(expiry),
                        None,
                        None,
                        _iso(issued),
                    ),
                )
                inserted_count = cursor.rowcount
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "capability lease identity conflicts",
                    code="CAPABILITY_LEASE_CONFLICT",
                ) from exc
            row = cursor.execute(
                f"SELECT {_CAPABILITY_COLUMNS} FROM capability_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND lease_id=? FOR UPDATE",
                (
                    *scope,
                    lease_id,
                ),
            ).fetchone()
            if row is None:
                raise ConflictError(
                    "capability lease identity is occupied outside the bound scope",
                    code="CAPABILITY_LEASE_CONFLICT",
                )
            record = _capability_record(row)
            if not (
                record.invocation_id == invocation_id
                and record.environment_id == environment_id
                and record.authority_snapshot_id == authority_snapshot_id
                and record.execution_epoch == context.execution_epoch
                and record.capabilities == normalized_capabilities
                and record.delegation_allowed is delegation_allowed
                and record.expires_at == expiry
            ):
                raise ConflictError(
                    "capability lease replay diverges from durable content",
                    code="CAPABILITY_LEASE_CONFLICT",
                )
            if inserted_count == 1:
                self._append_runtime_assurance_outbox(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    event_type="CAPABILITY_LEASE_ISSUED",
                    subject_id=lease_id,
                    payload={
                        "lease_id": lease_id,
                        "invocation_id": invocation_id,
                        "environment_id": environment_id,
                        "expires_at": expiry,
                        "authority_envelope_digest": (
                            authority_receipt.host_envelope.envelope_digest
                        ),
                    },
                )
            return record

    def _transition_capability_lease(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        lease_id: str,
        target_state: CapabilityLeaseState,
        reason: CapabilityRevocationReason | None,
        now: datetime | None,
    ) -> CapabilityLeaseRecord:
        _port_context(context, revision_set_id)
        lease_id = _port_text(lease_id, "lease_id", maximum=512)
        if target_state not in {
            CapabilityLeaseState.REVOKED,
            CapabilityLeaseState.EXPIRED,
        }:
            raise ValidationError("capability lease target state is invalid")
        if target_state is CapabilityLeaseState.REVOKED:
            if not isinstance(reason, CapabilityRevocationReason):
                raise ValidationError("capability revocation reason must be typed")
        elif reason is not None:
            raise ValidationError(
                "expired capability lease cannot have a revocation reason"
            )
        timestamp = _port_time(now, "now", default_now=True)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            assert context.run_id is not None
            scope = _runtime_scope_parameters(context, revision_set_id)
            parameters = (
                *scope,
                lease_id,
            )
            row = cursor.execute(
                f"SELECT {_CAPABILITY_COLUMNS} FROM capability_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND lease_id=? FOR UPDATE",
                parameters,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "capability lease was not found", code="CAPABILITY_LEASE_NOT_FOUND"
                )
            current = _capability_record(row)
            if current.state is target_state:
                if (
                    target_state is CapabilityLeaseState.REVOKED
                    and current.revocation_reason is not reason
                ):
                    raise ConflictError(
                        "capability revocation replay changed its reason",
                        code="CAPABILITY_LEASE_STATE_CONFLICT",
                    )
                return current
            if current.state is not CapabilityLeaseState.ACTIVE:
                raise ConflictError(
                    "capability lease state is stale",
                    code="CAPABILITY_LEASE_STATE_CONFLICT",
                )
            if (
                target_state is CapabilityLeaseState.EXPIRED
                and timestamp < current.expires_at
            ):
                raise ConflictError(
                    "capability lease has not expired",
                    code="CAPABILITY_LEASE_NOT_EXPIRED",
                )
            revoked_at = (
                _iso(timestamp)
                if target_state is CapabilityLeaseState.REVOKED
                else None
            )
            update = cursor.execute(
                "UPDATE capability_leases SET state=?,revoked_at=?,revocation_reason=?,updated_at=? "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND lease_id=? AND state='ACTIVE'",
                (
                    target_state.value,
                    revoked_at,
                    None if reason is None else reason.value,
                    _iso(timestamp),
                    *parameters,
                ),
            )
            if update.rowcount != 1:
                raise ConflictError(
                    "capability lease compare-and-swap failed",
                    code="CAPABILITY_LEASE_STATE_CONFLICT",
                )
            updated = cursor.execute(
                f"SELECT {_CAPABILITY_COLUMNS} FROM capability_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND lease_id=?",
                parameters,
            ).fetchone()
            if updated is None:
                raise IntegrityError(
                    "capability lease disappeared after transition",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _capability_record(updated)
            if record.state is not target_state:
                raise IntegrityError(
                    "capability lease transition did not persist the target state",
                    code="DELTA_STORAGE_DRIFT",
                )
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type=f"CAPABILITY_LEASE_{target_state.value}",
                subject_id=lease_id,
                payload={
                    "lease_id": lease_id,
                    "from_state": CapabilityLeaseState.ACTIVE.value,
                    "to_state": target_state.value,
                    "reason": None if reason is None else reason.value,
                },
            )
            return record

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
    ) -> CapabilityLeaseRecord:
        _port_context(context, revision_set_id)
        lease_id = _port_text(lease_id, "lease_id", maximum=512)
        subject_invocation_id = _port_text(
            subject_invocation_id,
            "subject_invocation_id",
            maximum=512,
        )
        operation_invocation_id = _port_text(
            operation_invocation_id,
            "operation_invocation_id",
            maximum=512,
        )
        self._require_active_invocation_operation(operation_invocation_id)
        expected_environment_id = _port_text(
            expected_environment_id,
            "expected_environment_id",
            maximum=512,
        )
        expected_authority_snapshot_id = _port_authority_snapshot(
            context,
            expected_authority_snapshot_id,
        )
        normalized_authorized_capabilities = frozenset(
            _port_strings(
                authorized_capabilities,
                "authorized_capabilities",
            )
        )
        if not isinstance(reason, CapabilityRevocationReason):
            raise ValidationError("capability revocation reason must be typed")
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        denial: HarnessError | None = None
        record: CapabilityLeaseRecord | None = None
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            authority_receipt = self._require_authority_capability_receipt(
                cursor,
                context,
                revision_set_id=revision_set_id,
                operation_invocation_id=operation_invocation_id,
                expected_environment_id=expected_environment_id,
                expected_authority_snapshot_id=expected_authority_snapshot_id,
                authorized_capabilities=normalized_authorized_capabilities,
            )
            parameters = (*scope, lease_id)
            row = cursor.execute(
                f"SELECT {_CAPABILITY_COLUMNS} FROM capability_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND lease_id=? FOR UPDATE",
                parameters,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "capability lease was not found",
                    code="CAPABILITY_LEASE_NOT_FOUND",
                )
            record = _capability_record(row)
            denial_reason: CapabilityUseDenialReason | None = None
            if record.invocation_id != subject_invocation_id:
                denial_reason = CapabilityUseDenialReason.INVOCATION_MISMATCH
                denial = AuthorizationError(
                    "capability lease invocation binding does not match",
                    code="CAPABILITY_LEASE_SCOPE_MISMATCH",
                )
            elif record.environment_id != expected_environment_id:
                denial_reason = CapabilityUseDenialReason.ENVIRONMENT_MISMATCH
                denial = AuthorizationError(
                    "capability lease environment binding does not match",
                    code="CAPABILITY_LEASE_ENVIRONMENT_MISMATCH",
                )
            elif not hmac.compare_digest(
                record.authority_snapshot_id,
                expected_authority_snapshot_id,
            ):
                denial_reason = CapabilityUseDenialReason.AUTHORITY_SNAPSHOT_MISMATCH
                denial = AuthorizationError(
                    "capability lease authority snapshot binding does not match",
                    code="CAPABILITY_LEASE_AUTHORITY_MISMATCH",
                )
            elif not frozenset(record.capabilities).issubset(
                normalized_authorized_capabilities
            ):
                denial_reason = (
                    CapabilityUseDenialReason.AUTHORITY_CAPABILITY_MISMATCH
                )
                denial = AuthorizationError(
                    "capability lease exceeds the current Host authority",
                    code="AUTHORITY_CAPABILITY_MISMATCH",
                )
            if denial is not None:
                assert denial_reason is not None
                self._append_runtime_assurance_outbox(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    event_type="CAPABILITY_LEASE_REVOCATION_DENIED",
                    subject_id=lease_id,
                    payload={
                        "lease_id": lease_id,
                        "subject_invocation_id": subject_invocation_id,
                        "operation_invocation_id": operation_invocation_id,
                        "reason": denial_reason.value,
                        "observed_at": timestamp,
                        "authority_envelope_digest": (
                            authority_receipt.host_envelope.envelope_digest
                        ),
                    },
                )
            elif record.state is CapabilityLeaseState.REVOKED:
                if record.revocation_reason is not reason:
                    raise ConflictError(
                        "capability revocation replay changed its reason",
                        code="CAPABILITY_LEASE_STATE_CONFLICT",
                    )
            elif record.state is not CapabilityLeaseState.ACTIVE:
                raise ConflictError(
                    "capability lease state is stale",
                    code="CAPABILITY_LEASE_STATE_CONFLICT",
                )
            else:
                update = cursor.execute(
                    "UPDATE capability_leases SET state='REVOKED',revoked_at=?,"
                    "revocation_reason=?,updated_at=? "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND lease_id=? AND state='ACTIVE'",
                    (
                        _iso(timestamp),
                        reason.value,
                        _iso(timestamp),
                        *parameters,
                    ),
                )
                if update.rowcount != 1:
                    raise ConflictError(
                        "capability lease compare-and-swap failed",
                        code="CAPABILITY_LEASE_STATE_CONFLICT",
                    )
                updated = cursor.execute(
                    f"SELECT {_CAPABILITY_COLUMNS} FROM capability_leases "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND lease_id=?",
                    parameters,
                ).fetchone()
                if updated is None:
                    raise IntegrityError(
                        "capability lease disappeared after transition",
                        code="DELTA_STORAGE_DRIFT",
                    )
                record = _capability_record(updated)
                if record.state is not CapabilityLeaseState.REVOKED:
                    raise IntegrityError(
                        "capability lease transition did not persist the target state",
                        code="DELTA_STORAGE_DRIFT",
                    )
                self._append_runtime_assurance_outbox(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    event_type="CAPABILITY_LEASE_REVOKED",
                    subject_id=lease_id,
                    payload={
                        "lease_id": lease_id,
                        "subject_invocation_id": subject_invocation_id,
                        "operation_invocation_id": operation_invocation_id,
                        "from_state": CapabilityLeaseState.ACTIVE.value,
                        "to_state": CapabilityLeaseState.REVOKED.value,
                        "reason": reason.value,
                        "authority_envelope_digest": (
                            authority_receipt.host_envelope.envelope_digest
                        ),
                    },
                )
        if denial is not None:
            raise denial
        assert record is not None
        return record

    def expire_capability_lease(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        lease_id: str,
        now: datetime | None = None,
    ) -> CapabilityLeaseRecord:
        return self._transition_capability_lease(
            context,
            revision_set_id=revision_set_id,
            lease_id=lease_id,
            target_state=CapabilityLeaseState.EXPIRED,
            reason=None,
            now=now,
        )

    def revoke_invocation_capability_leases(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str | None,
        reason: CapabilityRevocationReason,
        environment_id: str | None = None,
        now: datetime | None = None,
    ) -> tuple[CapabilityLeaseRecord, ...]:
        _port_context(context, revision_set_id)
        if invocation_id is not None:
            invocation_id = _port_text(invocation_id, "invocation_id", maximum=512)
        if not isinstance(reason, CapabilityRevocationReason):
            raise ValidationError("capability revocation reason must be typed")
        if environment_id is not None:
            environment_id = _port_text(environment_id, "environment_id", maximum=512)
        if invocation_id is None and environment_id is None:
            raise ValidationError(
                "capability batch revocation requires invocation_id or environment_id"
            )
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        invocation_clause = "" if invocation_id is None else " AND invocation_id=?"
        environment_clause = "" if environment_id is None else " AND environment_id=?"
        query_parameters: tuple[Any, ...] = scope
        if invocation_id is not None:
            query_parameters = (*query_parameters, invocation_id)
        if environment_id is not None:
            query_parameters = (*query_parameters, environment_id)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            rows = cursor.execute(
                f"SELECT {_CAPABILITY_COLUMNS} FROM capability_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL}{invocation_clause}{environment_clause} "
                "ORDER BY lease_id FOR UPDATE",
                query_parameters,
            ).fetchall()
            records = tuple(_capability_record(row) for row in rows)
            active_ids = tuple(
                record.lease_id
                for record in records
                if record.state is CapabilityLeaseState.ACTIVE
            )
            if not active_ids:
                if all(
                    record.state is CapabilityLeaseState.REVOKED
                    and record.revocation_reason is reason
                    for record in records
                ):
                    return records
                if records:
                    raise ConflictError(
                        "capability batch revocation conflicts with terminal leases",
                        code="CAPABILITY_LEASE_STATE_CONFLICT",
                    )
                return ()
            if active_ids:
                updated = cursor.execute(
                    "UPDATE capability_leases SET state='REVOKED',revoked_at=?,"
                    "revocation_reason=?,updated_at=? "
                    f"WHERE {_RUNTIME_SCOPE_SQL}{invocation_clause}{environment_clause} "
                    "AND state='ACTIVE'",
                    (
                        _iso(timestamp),
                        reason.value,
                        _iso(timestamp),
                        *query_parameters,
                    ),
                )
                if updated.rowcount != len(active_ids):
                    raise ConflictError(
                        "capability batch revocation compare-and-swap failed",
                        code="CAPABILITY_LEASE_STATE_CONFLICT",
                    )
                self._append_runtime_assurance_outbox(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    event_type="SCOPED_CAPABILITY_LEASES_REVOKED",
                    subject_id=invocation_id or environment_id or "invalid-filter",
                    payload={
                        "invocation_id": invocation_id,
                        "environment_id": environment_id,
                        "lease_ids": active_ids,
                        "reason": reason.value,
                    },
                )
                rows = cursor.execute(
                    f"SELECT {_CAPABILITY_COLUMNS} FROM capability_leases "
                    f"WHERE {_RUNTIME_SCOPE_SQL}{invocation_clause}{environment_clause} "
                    "AND state='REVOKED' AND revocation_reason=? ORDER BY lease_id",
                    (*query_parameters, reason.value),
                ).fetchall()
                records = tuple(_capability_record(row) for row in rows)
            return records

    def revoke_run_capability_leases(
        self,
        context: SecurityContext,
        *,
        reason: CapabilityRevocationReason,
        now: datetime | None = None,
    ) -> tuple[CapabilityLeaseRecord, ...]:
        _port_run_context(context)
        if not isinstance(reason, CapabilityRevocationReason):
            raise ValidationError("capability revocation reason must be typed")
        timestamp = _port_time(now, "now", default_now=True)
        with self.transaction(context) as cursor:
            run = self._assert_runtime_assurance_run_scope(cursor, context)
            revision_set_id = str(run["revision_set_id"])
            require_sha256_digest(revision_set_id, field="revision_set_id")
            self._assert_runtime_assurance_scope(
                cursor,
                context,
                revision_set_id,
            )
            scope = _runtime_scope_parameters(context, revision_set_id)
            rows = cursor.execute(
                f"SELECT {_CAPABILITY_COLUMNS} FROM capability_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND state='ACTIVE' "
                "ORDER BY lease_id FOR UPDATE",
                scope,
            ).fetchall()
            records = tuple(_capability_record(row) for row in rows)
            if not records:
                replay_rows = cursor.execute(
                    f"SELECT {_CAPABILITY_COLUMNS} FROM capability_leases "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND state='REVOKED' "
                    "AND revocation_reason=? ORDER BY lease_id",
                    (*scope, reason.value),
                ).fetchall()
                return tuple(_capability_record(row) for row in replay_rows)
            updated = cursor.execute(
                "UPDATE capability_leases SET state='REVOKED',revoked_at=?,"
                "revocation_reason=?,updated_at=? "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND state='ACTIVE'",
                (_iso(timestamp), reason.value, _iso(timestamp), *scope),
            )
            if updated.rowcount != len(records):
                raise ConflictError(
                    "run capability revocation compare-and-swap failed",
                    code="CAPABILITY_LEASE_STATE_CONFLICT",
                )
            lease_ids = tuple(record.lease_id for record in records)
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="RUN_CAPABILITY_LEASES_REVOKED",
                subject_id=context.run_id or "missing-run",
                payload={
                    "run_id": context.run_id,
                    "lease_ids": lease_ids,
                    "reason": reason.value,
                },
            )
            rows = cursor.execute(
                f"SELECT {_CAPABILITY_COLUMNS} FROM capability_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND state='REVOKED' "
                "AND revocation_reason=? ORDER BY lease_id",
                (*scope, reason.value),
            ).fetchall()
            return tuple(_capability_record(row) for row in rows)

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
    ) -> str:
        _port_context(context, revision_set_id)
        lease_id = _port_text(lease_id, "lease_id", maximum=512)
        if subject_invocation_id is not None:
            subject_invocation_id = _port_text(
                subject_invocation_id,
                "subject_invocation_id",
                maximum=512,
            )
        operation_invocation_id = _port_text(
            operation_invocation_id,
            "operation_invocation_id",
            maximum=512,
        )
        self._require_active_invocation_operation(operation_invocation_id)
        capability = _port_text(capability, "capability", maximum=512)
        if not isinstance(reason, CapabilityUseDenialReason):
            raise ValidationError("capability denial reason must be typed")
        timestamp = _port_time(now, "now", default_now=True)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            authority_receipt = self._lock_authority_capability_receipt(
                cursor,
                context,
                revision_set_id=revision_set_id,
                operation_invocation_id=operation_invocation_id,
            )
            return self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="CAPABILITY_LEASE_USE_DENIED",
                subject_id=lease_id,
                payload={
                    "lease_id": lease_id,
                    "subject_invocation_id": subject_invocation_id,
                    "operation_invocation_id": operation_invocation_id,
                    "capability": capability,
                    "reason": reason.value,
                    "observed_at": timestamp,
                    "authority_envelope_digest": (
                        authority_receipt.host_envelope.envelope_digest
                    ),
                },
            )

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
    ) -> CapabilityLeaseRecord:
        _port_context(context, revision_set_id)
        lease_id = _port_text(lease_id, "lease_id", maximum=512)
        invocation_id = _port_text(invocation_id, "invocation_id", maximum=512)
        operation_invocation_id = _port_text(
            operation_invocation_id,
            "operation_invocation_id",
            maximum=512,
        )
        self._require_active_invocation_operation(operation_invocation_id)
        expected_environment_id = _port_text(
            expected_environment_id,
            "expected_environment_id",
            maximum=512,
        )
        expected_authority_snapshot_id = _port_authority_snapshot(
            context,
            expected_authority_snapshot_id,
        )
        normalized_authorized_capabilities = frozenset(
            _port_strings(
                authorized_capabilities,
                "authorized_capabilities",
            )
        )
        capability = _port_text(capability, "capability", maximum=512)
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        denial: HarnessError | None = None
        record: CapabilityLeaseRecord | None = None
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            authority_receipt = self._require_authority_capability_receipt(
                cursor,
                context,
                revision_set_id=revision_set_id,
                operation_invocation_id=operation_invocation_id,
                expected_environment_id=expected_environment_id,
                expected_authority_snapshot_id=expected_authority_snapshot_id,
                authorized_capabilities=normalized_authorized_capabilities,
            )
            row = cursor.execute(
                f"SELECT {_CAPABILITY_COLUMNS} FROM capability_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND lease_id=? FOR UPDATE",
                (*scope, lease_id),
            ).fetchone()
            if row is None:
                denial_reason = CapabilityUseDenialReason.UNKNOWN_LEASE
                denial = NotFoundError(
                    "capability lease was not found",
                    code="CAPABILITY_LEASE_NOT_FOUND",
                )
            else:
                record = _capability_record(row)
                if record.invocation_id != invocation_id:
                    denial_reason = CapabilityUseDenialReason.INVOCATION_MISMATCH
                    denial = AuthorizationError(
                        "capability lease invocation binding does not match",
                        code="CAPABILITY_LEASE_SCOPE_MISMATCH",
                    )
                elif record.environment_id != expected_environment_id:
                    denial_reason = CapabilityUseDenialReason.ENVIRONMENT_MISMATCH
                    denial = AuthorizationError(
                        "capability lease environment binding does not match",
                        code="CAPABILITY_LEASE_ENVIRONMENT_MISMATCH",
                    )
                elif not hmac.compare_digest(
                    record.authority_snapshot_id,
                    expected_authority_snapshot_id,
                ):
                    denial_reason = (
                        CapabilityUseDenialReason.AUTHORITY_SNAPSHOT_MISMATCH
                    )
                    denial = AuthorizationError(
                        "capability lease authority snapshot binding does not match",
                        code="CAPABILITY_LEASE_AUTHORITY_MISMATCH",
                    )
                elif record.state is not CapabilityLeaseState.ACTIVE:
                    denial_reason = CapabilityUseDenialReason.LEASE_NOT_ACTIVE
                    denial = ConflictError(
                        "capability lease is not active",
                        code="CAPABILITY_LEASE_NOT_ACTIVE",
                    )
                elif timestamp >= record.expires_at:
                    denial_reason = CapabilityUseDenialReason.LEASE_EXPIRED
                    denial = ConflictError(
                        "capability lease has expired",
                        code="CAPABILITY_LEASE_EXPIRED",
                    )
                elif capability not in normalized_authorized_capabilities:
                    denial_reason = (
                        CapabilityUseDenialReason.AUTHORITY_CAPABILITY_MISMATCH
                    )
                    denial = AuthorizationError(
                        "capability is absent from the current Host authority",
                        code="AUTHORITY_CAPABILITY_MISMATCH",
                    )
                elif capability not in record.capabilities:
                    denial_reason = CapabilityUseDenialReason.CAPABILITY_NOT_GRANTED
                    denial = AuthorizationError(
                        "capability is not granted by the lease",
                        code="CAPABILITY_NOT_GRANTED",
                    )
                else:
                    denial_reason = None
            if denial is not None:
                assert denial_reason is not None
                self._append_runtime_assurance_outbox(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    event_type="CAPABILITY_LEASE_USE_DENIED",
                    subject_id=lease_id,
                    payload={
                        "lease_id": lease_id,
                        "subject_invocation_id": invocation_id,
                        "operation_invocation_id": operation_invocation_id,
                        "capability": capability,
                        "reason": denial_reason.value,
                        "observed_at": timestamp,
                        "authority_envelope_digest": (
                            authority_receipt.host_envelope.envelope_digest
                        ),
                    },
                )
            else:
                assert record is not None
                self._append_runtime_assurance_outbox(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    event_type="CAPABILITY_LEASE_USED",
                    subject_id=lease_id,
                    payload={
                        "lease_id": lease_id,
                        "subject_invocation_id": invocation_id,
                        "operation_invocation_id": operation_invocation_id,
                        "capability": capability,
                        "observed_at": timestamp,
                        "authority_envelope_digest": (
                            authority_receipt.host_envelope.envelope_digest
                        ),
                    },
                )
        if denial is not None:
            raise denial
        assert record is not None
        return record

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
    ) -> ExecutorGenerationRecord:
        _port_context(context, revision_set_id)
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        executor_identity = _port_text(
            executor_identity, "executor_identity", maximum=1024
        )
        executor_generation = _port_positive(executor_generation, "executor_generation")
        connection_epoch = _port_positive(connection_epoch, "connection_epoch")
        if executor_generation != 1 or connection_epoch != 1:
            raise ValidationError(
                "initial executor generation and connection epoch must both be 1"
            )
        timestamp = _port_time(now, "now", default_now=True)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            assert context.run_id is not None
            assert context.authority_revision is not None
            scope = _runtime_scope_parameters(context, revision_set_id)
            try:
                cursor.execute(
                    "INSERT INTO executor_generations("
                    f"{_EXECUTOR_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,'CONNECTING',?,?,?,?,?,?) "
                    "ON CONFLICT (tenant_id,project_id,run_id,execution_epoch,"
                    "fencing_generation,authority_revision,revision_set_id,environment_id,"
                    "executor_generation,connection_epoch) "
                    "DO NOTHING",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        context.run_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        environment_id,
                        executor_identity,
                        executor_generation,
                        connection_epoch,
                        None,
                        _iso(timestamp),
                        _iso(timestamp),
                        None,
                        None,
                        None,
                    ),
                )
                inserted_count = cursor.rowcount
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "executor generation identity conflicts",
                    code="EXECUTOR_GENERATION_CONFLICT",
                ) from exc
            row = cursor.execute(
                f"SELECT {_EXECUTOR_COLUMNS} FROM executor_generations "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? "
                "AND executor_generation=? AND connection_epoch=? FOR UPDATE",
                (
                    *scope,
                    environment_id,
                    executor_generation,
                    connection_epoch,
                ),
            ).fetchone()
            if row is None:
                raise ConflictError(
                    "executor generation identity is occupied outside the actor scope",
                    code="EXECUTOR_GENERATION_CONFLICT",
                )
            record = _executor_record(row)
            if record.executor_identity != executor_identity:
                raise ConflictError(
                    "executor generation replay diverges from durable content",
                    code="EXECUTOR_GENERATION_CONFLICT",
                )
            if inserted_count == 1:
                self._append_runtime_assurance_outbox(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    event_type="EXECUTOR_GENERATION_RECORDED",
                    subject_id=environment_id,
                    payload={
                        "environment_id": environment_id,
                        "executor_generation": executor_generation,
                        "connection_epoch": connection_epoch,
                        "state": ExecutorGenerationState.CONNECTING.value,
                    },
                )
            return record

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
    ) -> ExecutorGenerationRecord:
        _port_context(context, revision_set_id)
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        executor_generation = _port_positive(executor_generation, "executor_generation")
        connection_epoch = _port_positive(connection_epoch, "connection_epoch")
        if not isinstance(expected_state, ExecutorGenerationState) or not isinstance(
            target_state,
            ExecutorGenerationState,
        ):
            raise ValidationError("executor states must be typed")
        allowed = {
            (ExecutorGenerationState.CONNECTING, ExecutorGenerationState.ACTIVE),
            (ExecutorGenerationState.CONNECTING, ExecutorGenerationState.FAILED),
            (ExecutorGenerationState.ACTIVE, ExecutorGenerationState.RETIRED),
            (ExecutorGenerationState.ACTIVE, ExecutorGenerationState.FAILED),
        }
        if (expected_state, target_state) not in allowed:
            raise ValidationError("executor state transition is not allowed")
        if live_probe_evidence_ref is not None:
            live_probe_evidence_ref = _port_text(
                live_probe_evidence_ref,
                "live_probe_evidence_ref",
            )
        if (
            target_state is ExecutorGenerationState.ACTIVE
            and live_probe_evidence_ref is None
        ):
            raise ValidationError("activation requires live probe evidence")
        timestamp = _port_time(now, "now", default_now=True)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            scope = _runtime_scope_parameters(context, revision_set_id)
            parameters = (
                *scope,
                environment_id,
                executor_generation,
                connection_epoch,
            )
            row = cursor.execute(
                f"SELECT {_EXECUTOR_COLUMNS} FROM executor_generations "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? "
                "AND executor_generation=? AND connection_epoch=? FOR UPDATE",
                parameters,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "executor generation was not found",
                    code="EXECUTOR_GENERATION_NOT_FOUND",
                )
            current = _executor_record(row)
            if target_state is ExecutorGenerationState.ACTIVE:
                effects = cursor.execute(
                    f"SELECT {_EXECUTOR_REPLACEMENT_EFFECT_COLUMNS} "
                    "FROM executor_replacement_effects "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? "
                    "AND executor_generation=? AND connection_epoch=? "
                    "ORDER BY kind,effect_id FOR UPDATE",
                    (
                        *scope,
                        environment_id,
                        executor_generation,
                        connection_epoch,
                    ),
                ).fetchall()
                unresolved = tuple(
                    str(effect["effect_id"])
                    for effect in effects
                    if str(effect["state"])
                    != ExecutorReplacementEffectState.SUCCEEDED.value
                )
                if unresolved:
                    raise ConflictError(
                        "executor replacement has unresolved side effects",
                        code="EXECUTOR_REPLACEMENT_UNRESOLVED",
                        details={"effect_ids": unresolved},
                    )
                if (
                    executor_generation,
                    connection_epoch,
                ) != (1, 1) and _exact_succeeded_executor_replacement_effect_ids(
                    effects
                ) is None:
                    raise ConflictError(
                        "advanced executor activation requires exactly three succeeded reconciliation effects",
                        code="EXECUTOR_REPLACEMENT_UNRESOLVED",
                        details={
                            "effect_ids": tuple(
                                str(effect.get("effect_id", "")) for effect in effects
                            )
                        },
                    )
            if current.state is target_state:
                if (
                    live_probe_evidence_ref is not None
                    and current.live_probe_evidence_ref != live_probe_evidence_ref
                ):
                    raise ConflictError(
                        "executor activation replay changed live probe evidence",
                        code="EXECUTOR_GENERATION_CONFLICT",
                    )
                return current
            if current.state is not expected_state:
                raise ConflictError(
                    "executor generation state is stale",
                    code="EXECUTOR_GENERATION_CONFLICT",
                )
            if (
                current.state is ExecutorGenerationState.ACTIVE
                and live_probe_evidence_ref is not None
                and current.live_probe_evidence_ref != live_probe_evidence_ref
            ):
                raise ConflictError(
                    "active executor live probe evidence is immutable",
                    code="EXECUTOR_GENERATION_CONFLICT",
                )
            if target_state is ExecutorGenerationState.ACTIVE:
                other = cursor.execute(
                    "SELECT executor_generation,connection_epoch FROM executor_generations "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? AND state='ACTIVE' "
                    "AND NOT (executor_generation=? AND connection_epoch=?) FOR UPDATE",
                    (
                        *scope,
                        environment_id,
                        executor_generation,
                        connection_epoch,
                    ),
                ).fetchone()
                if other is not None:
                    raise ConflictError(
                        "another executor generation is already active",
                        code="EXECUTOR_ACTIVE_CONFLICT",
                    )
            activated_at = (
                _iso(timestamp)
                if target_state is ExecutorGenerationState.ACTIVE
                else None
            )
            retired_at = (
                _iso(timestamp)
                if target_state is ExecutorGenerationState.RETIRED
                else None
            )
            failed_at = (
                _iso(timestamp)
                if target_state is ExecutorGenerationState.FAILED
                else None
            )
            update = cursor.execute(
                "UPDATE executor_generations SET state=?,"
                "live_probe_evidence_ref=COALESCE(?,live_probe_evidence_ref),updated_at=?,"
                "activated_at=COALESCE(activated_at,?),retired_at=COALESCE(retired_at,?),"
                "failed_at=COALESCE(failed_at,?) "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? "
                "AND executor_generation=? AND connection_epoch=? AND state=?",
                (
                    target_state.value,
                    live_probe_evidence_ref,
                    _iso(timestamp),
                    activated_at,
                    retired_at,
                    failed_at,
                    *parameters,
                    expected_state.value,
                ),
            )
            if update.rowcount != 1:
                raise ConflictError(
                    "executor generation compare-and-swap failed",
                    code="EXECUTOR_GENERATION_CONFLICT",
                )
            updated = cursor.execute(
                f"SELECT {_EXECUTOR_COLUMNS} FROM executor_generations "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? "
                "AND executor_generation=? AND connection_epoch=?",
                parameters,
            ).fetchone()
            if updated is None:
                raise IntegrityError(
                    "executor generation disappeared after transition",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _executor_record(updated)
            if record.state is not target_state:
                raise IntegrityError(
                    "executor transition did not persist the target state",
                    code="DELTA_STORAGE_DRIFT",
                )
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type=f"EXECUTOR_GENERATION_{target_state.value}",
                subject_id=environment_id,
                payload={
                    "environment_id": environment_id,
                    "executor_generation": executor_generation,
                    "connection_epoch": connection_epoch,
                    "from_state": expected_state.value,
                    "to_state": target_state.value,
                },
            )
            return record

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
    ) -> ExecutorGenerationRecord:
        _port_context(context, revision_set_id)
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        executor_identity = _port_text(
            executor_identity, "executor_identity", maximum=1024
        )
        expected_generation = _port_positive(expected_generation, "expected_generation")
        expected_connection_epoch = _port_positive(
            expected_connection_epoch,
            "expected_connection_epoch",
        )
        if not isinstance(replace_identity, bool):
            raise ValidationError("replace_identity must be boolean")
        timestamp = _port_time(now, "now", default_now=True)
        next_generation = expected_generation + (1 if replace_identity else 0)
        next_connection_epoch = expected_connection_epoch + 1
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            assert context.run_id is not None
            assert context.authority_revision is not None
            scope = _runtime_scope_parameters(context, revision_set_id)
            old_parameters = (
                *scope,
                environment_id,
                expected_generation,
                expected_connection_epoch,
            )
            row = cursor.execute(
                f"SELECT {_EXECUTOR_COLUMNS} FROM executor_generations "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? "
                "AND executor_generation=? AND connection_epoch=? FOR UPDATE",
                old_parameters,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "executor generation was not found",
                    code="EXECUTOR_GENERATION_NOT_FOUND",
                )
            current = _executor_record(row)
            if replace_identity:
                if hmac.compare_digest(current.executor_identity, executor_identity):
                    raise ConflictError(
                        "executor replacement requires a new identity",
                        code="EXECUTOR_GENERATION_CONFLICT",
                    )
            elif not hmac.compare_digest(current.executor_identity, executor_identity):
                raise ConflictError(
                    "executor reconnect identity does not match the current fence",
                    code="EXECUTOR_GENERATION_CONFLICT",
                )
            next_parameters = (
                *scope,
                environment_id,
                next_generation,
                next_connection_epoch,
            )
            effect_digest = digest_object(
                {
                    "environmentId": environment_id,
                    "executorGeneration": next_generation,
                    "connectionEpoch": next_connection_epoch,
                    "kind": ExecutorReplacementEffectKind.CAPABILITY_REVOCATION.value,
                },
                domain="delta-executor-replacement-effect",
            )
            effect_id = f"effect-{effect_digest.removeprefix('sha256:')[:40]}"
            if current.state is ExecutorGenerationState.RETIRED:
                replay_row = cursor.execute(
                    f"SELECT {_EXECUTOR_COLUMNS} FROM executor_generations "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? "
                    "AND executor_generation=? AND connection_epoch=? FOR UPDATE",
                    next_parameters,
                ).fetchone()
                if replay_row is None:
                    raise ConflictError(
                        "retired executor has no exact successor",
                        code="EXECUTOR_GENERATION_CONFLICT",
                    )
                replay = _executor_record(replay_row)
                if not hmac.compare_digest(replay.executor_identity, executor_identity):
                    raise ConflictError(
                        "executor advance replay diverges",
                        code="EXECUTOR_GENERATION_CONFLICT",
                    )
                effect_rows = cursor.execute(
                    f"SELECT {_EXECUTOR_REPLACEMENT_EFFECT_COLUMNS} "
                    "FROM executor_replacement_effects "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? "
                    "AND executor_generation=? AND connection_epoch=? "
                    "ORDER BY kind,effect_id FOR UPDATE",
                    next_parameters,
                ).fetchall()
                effect_ids = _exact_succeeded_executor_replacement_effect_ids(
                    effect_rows
                )
                if effect_ids is None:
                    raise IntegrityError(
                        "executor advance replay requires exactly three succeeded reconciliation effects",
                        code="DELTA_STORAGE_DRIFT",
                    )
                if not hmac.compare_digest(
                    effect_ids[ExecutorReplacementEffectKind.CAPABILITY_REVOCATION],
                    effect_id,
                ):
                    raise IntegrityError(
                        "executor advance replay capability effect identity drifted",
                        code="DELTA_STORAGE_DRIFT",
                    )
                return replay
            if current.state is not ExecutorGenerationState.ACTIVE:
                raise ConflictError(
                    "only an active executor can be atomically advanced",
                    code="EXECUTOR_GENERATION_CONFLICT",
                )
            retired = cursor.execute(
                "UPDATE executor_generations SET state='RETIRED',updated_at=?,retired_at=? "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? "
                "AND executor_generation=? AND connection_epoch=? AND state='ACTIVE'",
                (_iso(timestamp), _iso(timestamp), *old_parameters),
            )
            if retired.rowcount != 1:
                raise ConflictError(
                    "executor advance compare-and-swap failed",
                    code="EXECUTOR_GENERATION_CONFLICT",
                )
            try:
                cursor.execute(
                    "INSERT INTO executor_generations("
                    f"{_EXECUTOR_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,'CONNECTING',?,?,?,?,?,?)",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        context.run_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        environment_id,
                        executor_identity,
                        next_generation,
                        next_connection_epoch,
                        None,
                        _iso(timestamp),
                        _iso(timestamp),
                        None,
                        None,
                        None,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "executor successor fence conflicts",
                    code="EXECUTOR_GENERATION_CONFLICT",
                ) from exc
            successor_row = cursor.execute(
                f"SELECT {_EXECUTOR_COLUMNS} FROM executor_generations "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? "
                "AND executor_generation=? AND connection_epoch=?",
                next_parameters,
            ).fetchone()
            if successor_row is None:
                raise IntegrityError(
                    "executor successor was not persisted",
                    code="DELTA_STORAGE_DRIFT",
                )
            successor = _executor_record(successor_row)
            if (
                successor.state is not ExecutorGenerationState.CONNECTING
                or not hmac.compare_digest(
                    successor.executor_identity, executor_identity
                )
            ):
                raise IntegrityError(
                    "executor successor content drifted",
                    code="DELTA_STORAGE_DRIFT",
                )
            active_lease_rows = cursor.execute(
                "SELECT lease_id FROM capability_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? "
                "AND state='ACTIVE' ORDER BY lease_id FOR UPDATE",
                (*scope, environment_id),
            ).fetchall()
            revoked_lease_ids = tuple(
                str(item["lease_id"]) for item in active_lease_rows
            )
            if revoked_lease_ids:
                revoked = cursor.execute(
                    "UPDATE capability_leases SET state='REVOKED',revoked_at=?,"
                    "revocation_reason='EXECUTOR_REPLACED',updated_at=? "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? AND state='ACTIVE'",
                    (_iso(timestamp), _iso(timestamp), *scope, environment_id),
                )
                if revoked.rowcount != len(revoked_lease_ids):
                    raise ConflictError(
                        "executor replacement capability revocation conflicted",
                        code="CAPABILITY_LEASE_STATE_CONFLICT",
                    )
            evidence_ref = f"urn:elmos:capability-revocation:{effect_digest}"
            try:
                cursor.execute(
                    "INSERT INTO executor_replacement_effects("
                    f"{_EXECUTOR_REPLACEMENT_EFFECT_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,'SUCCEEDED',?,?,?,?)",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        context.run_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        effect_id,
                        environment_id,
                        next_generation,
                        next_connection_epoch,
                        ExecutorReplacementEffectKind.CAPABILITY_REVOCATION.value,
                        evidence_ref,
                        _iso(timestamp),
                        _iso(timestamp),
                        _iso(timestamp),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "executor replacement effect conflicts",
                    code="EXECUTOR_REPLACEMENT_EFFECT_CONFLICT",
                ) from exc
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="EXECUTOR_REPLACEMENT_CAPABILITIES_REVOKED",
                subject_id=environment_id,
                payload={
                    "environment_id": environment_id,
                    "executor_generation": next_generation,
                    "connection_epoch": next_connection_epoch,
                    "effect_id": effect_id,
                    "lease_ids": revoked_lease_ids,
                    "reason": CapabilityRevocationReason.EXECUTOR_REPLACED.value,
                },
            )
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="EXECUTOR_GENERATION_ADVANCED",
                subject_id=environment_id,
                payload={
                    "environment_id": environment_id,
                    "previous_generation": expected_generation,
                    "previous_connection_epoch": expected_connection_epoch,
                    "executor_generation": next_generation,
                    "connection_epoch": next_connection_epoch,
                    "identity_replaced": replace_identity,
                },
            )
            return successor

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
    ) -> EnvironmentAttachmentRecord:
        _port_context(context, revision_set_id)
        server_id = _port_text(server_id, "server_id", maximum=512)
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        require_sha256_digest(snapshot_id, field="snapshot_id")
        owner_authority_ref = _port_authority_snapshot(context, owner_authority_ref)
        require_sha256_digest(parent_authority_ref, field="parent_authority_ref")
        permissions = tuple(
            sorted(_port_strings(effective_permissions, "effective_permissions"))
        )
        if not isinstance(settings_authority, Mapping):
            raise ValidationError("settings_authority must be an object")
        require_sha256_digest(settings_digest, field="settings_digest")
        timestamp = _port_time(now, "now", default_now=True)
        assert context.run_id is not None
        assert context.authority_revision is not None
        candidate = EnvironmentAttachmentRecord(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            actor_id=context.actor_id,
            run_id=context.run_id,
            execution_epoch=context.execution_epoch,
            fencing_generation=context.fencing_generation,
            authority_revision=context.authority_revision,
            revision_set_id=revision_set_id,
            server_id=server_id,
            environment_id=environment_id,
            snapshot_id=snapshot_id,
            previous_snapshot_id=None,
            generation=1,
            owner_authority_ref=owner_authority_ref,
            parent_authority_ref=parent_authority_ref,
            effective_permissions=permissions,
            settings_authority=settings_authority,
            settings_digest=settings_digest,
            state=EnvironmentAttachmentState.ACTIVE,
            created_at=timestamp,
            updated_at=timestamp,
        )
        scope = _runtime_scope_parameters(context, revision_set_id)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            active = cursor.execute(
                f"SELECT {_ENVIRONMENT_ATTACHMENT_COLUMNS} FROM environment_attachments "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND server_id=? AND environment_id=? "
                "AND state='ACTIVE' FOR UPDATE",
                (*scope, server_id, environment_id),
            ).fetchone()
            if active is not None:
                replay = _environment_attachment_record(active)
                if replay.snapshot_id == snapshot_id and replay.generation == 1:
                    if (
                        replay.owner_authority_ref == owner_authority_ref
                        and replay.parent_authority_ref == parent_authority_ref
                        and replay.effective_permissions == permissions
                        and replay.settings_authority == candidate.settings_authority
                        and replay.settings_digest == settings_digest
                    ):
                        return replay
                raise ConflictError(
                    "environment already has a different active attachment",
                    code="ENVIRONMENT_ATTACHMENT_CONFLICT",
                )
            try:
                cursor.execute(
                    "INSERT INTO environment_attachments("
                    f"{_ENVIRONMENT_ATTACHMENT_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',?,?,?)",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        context.run_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        server_id,
                        environment_id,
                        snapshot_id,
                        None,
                        1,
                        owner_authority_ref,
                        parent_authority_ref,
                        canonical_json(list(permissions)),
                        canonical_json(settings_authority),
                        settings_digest,
                        _iso(timestamp),
                        _iso(timestamp),
                        None,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "environment attachment identity conflicts",
                    code="ENVIRONMENT_ATTACHMENT_CONFLICT",
                ) from exc
            row = cursor.execute(
                f"SELECT {_ENVIRONMENT_ATTACHMENT_COLUMNS} FROM environment_attachments "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND server_id=? AND environment_id=? "
                "AND generation=1",
                (*scope, server_id, environment_id),
            ).fetchone()
            if row is None:
                raise IntegrityError(
                    "environment attachment disappeared after persistence",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _environment_attachment_record(row)
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="ENVIRONMENT_ATTACHED",
                subject_id=environment_id,
                payload={
                    "server_id": server_id,
                    "environment_id": environment_id,
                    "snapshot_id": snapshot_id,
                    "generation": 1,
                    "settings_digest": settings_digest,
                },
            )
            return record

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
    ) -> EnvironmentAttachmentRecord:
        _port_context(context, revision_set_id)
        server_id = _port_text(server_id, "server_id", maximum=512)
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        require_sha256_digest(expected_snapshot_id, field="expected_snapshot_id")
        expected_generation = _port_positive(expected_generation, "expected_generation")
        require_sha256_digest(snapshot_id, field="snapshot_id")
        if hmac.compare_digest(expected_snapshot_id, snapshot_id):
            raise ValidationError("attachment refresh requires a new snapshot")
        owner_authority_ref = _port_authority_snapshot(context, owner_authority_ref)
        require_sha256_digest(parent_authority_ref, field="parent_authority_ref")
        permissions = tuple(
            sorted(_port_strings(effective_permissions, "effective_permissions"))
        )
        if not isinstance(settings_authority, Mapping):
            raise ValidationError("settings_authority must be an object")
        require_sha256_digest(settings_digest, field="settings_digest")
        timestamp = _port_time(now, "now", default_now=True)
        next_generation = expected_generation + 1
        assert context.run_id is not None
        assert context.authority_revision is not None
        candidate = EnvironmentAttachmentRecord(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            actor_id=context.actor_id,
            run_id=context.run_id,
            execution_epoch=context.execution_epoch,
            fencing_generation=context.fencing_generation,
            authority_revision=context.authority_revision,
            revision_set_id=revision_set_id,
            server_id=server_id,
            environment_id=environment_id,
            snapshot_id=snapshot_id,
            previous_snapshot_id=expected_snapshot_id,
            generation=next_generation,
            owner_authority_ref=owner_authority_ref,
            parent_authority_ref=parent_authority_ref,
            effective_permissions=permissions,
            settings_authority=settings_authority,
            settings_digest=settings_digest,
            state=EnvironmentAttachmentState.ACTIVE,
            created_at=timestamp,
            updated_at=timestamp,
        )
        scope = _runtime_scope_parameters(context, revision_set_id)
        old_parameters = (*scope, server_id, environment_id, expected_generation)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            old_row = cursor.execute(
                f"SELECT {_ENVIRONMENT_ATTACHMENT_COLUMNS} FROM environment_attachments "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND server_id=? AND environment_id=? "
                "AND generation=? FOR UPDATE",
                old_parameters,
            ).fetchone()
            if old_row is None:
                raise NotFoundError(
                    "environment attachment generation was not found",
                    code="ENVIRONMENT_ATTACHMENT_NOT_FOUND",
                )
            current = _environment_attachment_record(old_row)
            if not hmac.compare_digest(current.snapshot_id, expected_snapshot_id):
                raise ConflictError(
                    "environment attachment snapshot is stale",
                    code="ENVIRONMENT_ATTACHMENT_CONFLICT",
                )
            if current.state is EnvironmentAttachmentState.SUPERSEDED:
                replay_row = cursor.execute(
                    f"SELECT {_ENVIRONMENT_ATTACHMENT_COLUMNS} FROM environment_attachments "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND server_id=? AND environment_id=? "
                    "AND generation=? FOR UPDATE",
                    (*scope, server_id, environment_id, next_generation),
                ).fetchone()
                if replay_row is None:
                    raise ConflictError(
                        "superseded attachment has no exact successor",
                        code="ENVIRONMENT_ATTACHMENT_CONFLICT",
                    )
                replay = _environment_attachment_record(replay_row)
                if not (
                    replay.snapshot_id == snapshot_id
                    and replay.previous_snapshot_id == expected_snapshot_id
                    and replay.owner_authority_ref == owner_authority_ref
                    and replay.parent_authority_ref == parent_authority_ref
                    and replay.effective_permissions == permissions
                    and replay.settings_authority == candidate.settings_authority
                    and replay.settings_digest == settings_digest
                ):
                    raise ConflictError(
                        "environment attachment refresh replay diverges",
                        code="ENVIRONMENT_ATTACHMENT_CONFLICT",
                    )
                return replay
            if current.state is not EnvironmentAttachmentState.ACTIVE:
                raise ConflictError(
                    "environment attachment is not refreshable",
                    code="ENVIRONMENT_ATTACHMENT_CONFLICT",
                )
            if current.parent_authority_ref != parent_authority_ref:
                raise ConflictError(
                    "environment attachment parent authority is immutable",
                    code="ENVIRONMENT_AUTHORITY_WIDENING",
                )
            if not set(permissions) <= set(current.effective_permissions):
                raise ConflictError(
                    "environment attachment permissions cannot widen",
                    code="ENVIRONMENT_AUTHORITY_WIDENING",
                )
            if any(
                key not in current.settings_authority
                or current.settings_authority[key] != value
                for key, value in candidate.settings_authority.items()
            ):
                raise ConflictError(
                    "environment attachment settings authority cannot widen or mutate",
                    code="ENVIRONMENT_AUTHORITY_WIDENING",
                )
            superseded = cursor.execute(
                "UPDATE environment_attachments SET state='SUPERSEDED',updated_at=?,"
                "superseded_at=? "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND server_id=? AND environment_id=? "
                "AND generation=? AND state='ACTIVE'",
                (_iso(timestamp), _iso(timestamp), *old_parameters),
            )
            if superseded.rowcount != 1:
                raise ConflictError(
                    "environment attachment refresh compare-and-swap failed",
                    code="ENVIRONMENT_ATTACHMENT_CONFLICT",
                )
            try:
                cursor.execute(
                    "INSERT INTO environment_attachments("
                    f"{_ENVIRONMENT_ATTACHMENT_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',?,?,?)",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        context.run_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        server_id,
                        environment_id,
                        snapshot_id,
                        expected_snapshot_id,
                        next_generation,
                        owner_authority_ref,
                        parent_authority_ref,
                        canonical_json(list(permissions)),
                        canonical_json(settings_authority),
                        settings_digest,
                        _iso(timestamp),
                        _iso(timestamp),
                        None,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "environment attachment successor conflicts",
                    code="ENVIRONMENT_ATTACHMENT_CONFLICT",
                ) from exc
            row = cursor.execute(
                f"SELECT {_ENVIRONMENT_ATTACHMENT_COLUMNS} FROM environment_attachments "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND server_id=? AND environment_id=? "
                "AND generation=?",
                (*scope, server_id, environment_id, next_generation),
            ).fetchone()
            if row is None:
                raise IntegrityError(
                    "environment attachment successor disappeared",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _environment_attachment_record(row)
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="ENVIRONMENT_ATTACHMENT_REFRESHED",
                subject_id=environment_id,
                payload={
                    "server_id": server_id,
                    "environment_id": environment_id,
                    "previous_snapshot_id": expected_snapshot_id,
                    "snapshot_id": snapshot_id,
                    "generation": next_generation,
                    "settings_digest": settings_digest,
                },
            )
            return record

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
    ) -> ExecutorReplacementEffectRecord:
        _port_context(context, revision_set_id)
        effect_id = _port_text(effect_id, "effect_id", maximum=512)
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        executor_generation = _port_positive(executor_generation, "executor_generation")
        connection_epoch = _port_positive(connection_epoch, "connection_epoch")
        if not isinstance(kind, ExecutorReplacementEffectKind):
            raise ValidationError("executor replacement effect kind must be typed")
        timestamp = _port_time(now, "now", default_now=True)
        assert context.run_id is not None
        assert context.authority_revision is not None
        scope = _runtime_scope_parameters(context, revision_set_id)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            executor = cursor.execute(
                "SELECT 1 AS present FROM executor_generations "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? "
                "AND executor_generation=? AND connection_epoch=? FOR KEY SHARE",
                (*scope, environment_id, executor_generation, connection_epoch),
            ).fetchone()
            if executor is None:
                raise NotFoundError(
                    "executor generation for replacement effect was not found",
                    code="EXECUTOR_GENERATION_NOT_FOUND",
                )
            try:
                cursor.execute(
                    "INSERT INTO executor_replacement_effects("
                    f"{_EXECUTOR_REPLACEMENT_EFFECT_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,'PENDING',NULL,?,?,NULL) "
                    "ON CONFLICT (tenant_id,project_id,run_id,execution_epoch,"
                    "fencing_generation,authority_revision,revision_set_id,effect_id) "
                    "DO NOTHING",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        context.run_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        effect_id,
                        environment_id,
                        executor_generation,
                        connection_epoch,
                        kind.value,
                        _iso(timestamp),
                        _iso(timestamp),
                    ),
                )
                inserted_count = cursor.rowcount
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "executor replacement effect identity conflicts",
                    code="EXECUTOR_REPLACEMENT_EFFECT_CONFLICT",
                ) from exc
            row = cursor.execute(
                f"SELECT {_EXECUTOR_REPLACEMENT_EFFECT_COLUMNS} "
                "FROM executor_replacement_effects "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND effect_id=? FOR UPDATE",
                (*scope, effect_id),
            ).fetchone()
            if row is None:
                raise ConflictError(
                    "executor replacement effect is occupied outside scope",
                    code="EXECUTOR_REPLACEMENT_EFFECT_CONFLICT",
                )
            record = _executor_replacement_effect_record(row)
            if not (
                record.environment_id == environment_id
                and record.executor_generation == executor_generation
                and record.connection_epoch == connection_epoch
                and record.kind is kind
            ):
                raise ConflictError(
                    "executor replacement effect replay diverges",
                    code="EXECUTOR_REPLACEMENT_EFFECT_CONFLICT",
                )
            if inserted_count == 1:
                self._append_runtime_assurance_outbox(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    event_type="EXECUTOR_REPLACEMENT_EFFECT_RECORDED",
                    subject_id=effect_id,
                    payload={
                        "effect_id": effect_id,
                        "environment_id": environment_id,
                        "executor_generation": executor_generation,
                        "connection_epoch": connection_epoch,
                        "kind": kind.value,
                    },
                )
            return record

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
    ) -> ExecutorReplacementEffectRecord:
        _port_context(context, revision_set_id)
        effect_id = _port_text(effect_id, "effect_id", maximum=512)
        if (
            expected_state is not ExecutorReplacementEffectState.PENDING
            or target_state
            not in {
                ExecutorReplacementEffectState.SUCCEEDED,
                ExecutorReplacementEffectState.FAILED,
                ExecutorReplacementEffectState.UNKNOWN,
            }
        ):
            raise ValidationError("executor replacement effect transition is invalid")
        evidence_ref = _port_text(evidence_ref, "evidence_ref")
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            row = cursor.execute(
                f"SELECT {_EXECUTOR_REPLACEMENT_EFFECT_COLUMNS} "
                "FROM executor_replacement_effects "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND effect_id=? FOR UPDATE",
                (*scope, effect_id),
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "executor replacement effect was not found",
                    code="EXECUTOR_REPLACEMENT_EFFECT_NOT_FOUND",
                )
            current = _executor_replacement_effect_record(row)
            if current.state is target_state:
                if current.evidence_ref != evidence_ref:
                    raise ConflictError(
                        "executor replacement reconciliation replay changed evidence",
                        code="EXECUTOR_REPLACEMENT_EFFECT_CONFLICT",
                    )
                return current
            if current.state is not expected_state:
                raise ConflictError(
                    "executor replacement effect state is stale",
                    code="EXECUTOR_REPLACEMENT_EFFECT_CONFLICT",
                )
            changed = cursor.execute(
                "UPDATE executor_replacement_effects SET state=?,evidence_ref=?,"
                "updated_at=?,reconciled_at=? "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND effect_id=? AND state='PENDING'",
                (
                    target_state.value,
                    evidence_ref,
                    _iso(timestamp),
                    _iso(timestamp),
                    *scope,
                    effect_id,
                ),
            )
            if changed.rowcount != 1:
                raise ConflictError(
                    "executor replacement effect compare-and-swap failed",
                    code="EXECUTOR_REPLACEMENT_EFFECT_CONFLICT",
                )
            updated = cursor.execute(
                f"SELECT {_EXECUTOR_REPLACEMENT_EFFECT_COLUMNS} "
                "FROM executor_replacement_effects "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND effect_id=?",
                (*scope, effect_id),
            ).fetchone()
            if updated is None:
                raise IntegrityError(
                    "executor replacement effect disappeared",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _executor_replacement_effect_record(updated)
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type=f"EXECUTOR_REPLACEMENT_EFFECT_{target_state.value}",
                subject_id=effect_id,
                payload={
                    "effect_id": effect_id,
                    "from_state": expected_state.value,
                    "to_state": target_state.value,
                    "evidence_ref": evidence_ref,
                },
            )
            return record

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
    ) -> WorkspaceLeaseRecord:
        _port_context(context, revision_set_id)
        workspace_id = _port_text(workspace_id, "workspace_id", maximum=512)
        owner_execution_id = _port_text(
            owner_execution_id, "owner_execution_id", maximum=512
        )
        generation = _port_positive(generation, "generation")
        repository_id = _port_text(repository_id, "repository_id", maximum=1024)
        base_revision = _port_text(base_revision, "base_revision", maximum=512)
        normalized_scopes = _port_workspace_scopes(write_scopes)
        if not normalized_scopes:
            raise ValidationError("write_scopes must not be empty")
        timestamp = _port_time(now, "now", default_now=True)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            assert context.run_id is not None
            assert context.authority_revision is not None
            scope = _runtime_scope_parameters(context, revision_set_id)
            cursor.execute(
                "SELECT pg_advisory_xact_lock(?)",
                (_workspace_lock_key(context, repository_id, base_revision),),
            )
            overlapping_rows = cursor.execute(
                f"SELECT {_WORKSPACE_COLUMNS} FROM workspace_leases "
                "WHERE tenant_id=? AND project_id=? "
                "AND repository_id=? AND base_revision=? "
                "AND state IN ('ACTIVE','HANDOFF_PENDING','TAKEOVER_PENDING') "
                "ORDER BY workspace_id,generation FOR UPDATE",
                (
                    context.tenant_id,
                    context.project_id,
                    repository_id,
                    base_revision,
                ),
            ).fetchall()
            for overlapping_row in overlapping_rows:
                existing = _workspace_record(overlapping_row)
                if existing.workspace_id != workspace_id and _workspace_scopes_overlap(
                    existing.write_scopes,
                    normalized_scopes,
                ):
                    raise ConflictError(
                        "repository checkout has overlapping live write authority",
                        code="WORKSPACE_SCOPE_CONFLICT",
                    )
            live = cursor.execute(
                "SELECT workspace_id,generation FROM workspace_leases "
                "WHERE tenant_id=? AND project_id=? AND workspace_id=? "
                "AND state IN ('ACTIVE','HANDOFF_PENDING','TAKEOVER_PENDING') FOR UPDATE",
                (context.tenant_id, context.project_id, workspace_id),
            ).fetchone()
            if live is not None and int(live["generation"]) != generation:
                raise ConflictError(
                    "workspace already has a live owner",
                    code="WORKSPACE_OWNER_CONFLICT",
                )
            try:
                cursor.execute(
                    "INSERT INTO workspace_leases("
                    f"{_WORKSPACE_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',?,?,?,?) "
                    "ON CONFLICT (tenant_id,project_id,run_id,execution_epoch,"
                    "fencing_generation,authority_revision,revision_set_id,workspace_id,generation) "
                    "DO NOTHING",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        context.run_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        workspace_id,
                        owner_execution_id,
                        generation,
                        repository_id,
                        base_revision,
                        canonical_json(list(normalized_scopes)),
                        None,
                        _iso(timestamp),
                        _iso(timestamp),
                        None,
                    ),
                )
                inserted_count = cursor.rowcount
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "workspace binding conflicts", code="WORKSPACE_OWNER_CONFLICT"
                ) from exc
            row = cursor.execute(
                f"SELECT {_WORKSPACE_COLUMNS} FROM workspace_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND workspace_id=? AND generation=? FOR UPDATE",
                (*scope, workspace_id, generation),
            ).fetchone()
            if row is None:
                raise ConflictError(
                    "workspace generation is occupied outside the actor scope",
                    code="WORKSPACE_OWNER_CONFLICT",
                )
            record = _workspace_record(row)
            if not (
                record.owner_execution_id == owner_execution_id
                and record.repository_id == repository_id
                and record.base_revision == base_revision
                and record.write_scopes == normalized_scopes
            ):
                raise ConflictError(
                    "workspace binding replay diverges from durable content",
                    code="WORKSPACE_OWNER_CONFLICT",
                )
            if inserted_count == 1:
                self._append_runtime_assurance_outbox(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    event_type="WORKSPACE_BOUND",
                    subject_id=workspace_id,
                    payload={
                        "workspace_id": workspace_id,
                        "owner_execution_id": owner_execution_id,
                        "generation": generation,
                        "repository_id": repository_id,
                        "base_revision": base_revision,
                        "write_scopes": normalized_scopes,
                    },
                )
            return record

    def request_workspace_handoff(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        workspace_id: str,
        expected_generation: int,
        now: datetime | None = None,
    ) -> WorkspaceLeaseRecord:
        _port_context(context, revision_set_id)
        workspace_id = _port_text(workspace_id, "workspace_id", maximum=512)
        expected_generation = _port_positive(expected_generation, "expected_generation")
        timestamp = _port_time(now, "now", default_now=True)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            scope = _runtime_scope_parameters(context, revision_set_id)
            parameters = (
                *scope,
                workspace_id,
                expected_generation,
            )
            row = cursor.execute(
                f"SELECT {_WORKSPACE_COLUMNS} FROM workspace_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND workspace_id=? AND generation=? FOR UPDATE",
                parameters,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "workspace generation was not found", code="WORKSPACE_NOT_FOUND"
                )
            current = _workspace_record(row)
            if current.state is WorkspaceLeaseState.HANDOFF_PENDING:
                return current
            if current.state is not WorkspaceLeaseState.ACTIVE:
                raise ConflictError(
                    "workspace is not eligible for handoff",
                    code="WORKSPACE_STATE_CONFLICT",
                )
            update = cursor.execute(
                "UPDATE workspace_leases SET state='HANDOFF_PENDING',updated_at=? "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND workspace_id=? "
                "AND generation=? AND state='ACTIVE'",
                (_iso(timestamp), *parameters),
            )
            if update.rowcount != 1:
                raise ConflictError(
                    "workspace handoff compare-and-swap failed",
                    code="WORKSPACE_STATE_CONFLICT",
                )
            updated = cursor.execute(
                f"SELECT {_WORKSPACE_COLUMNS} FROM workspace_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND workspace_id=? AND generation=?",
                parameters,
            ).fetchone()
            if updated is None:
                raise IntegrityError(
                    "workspace disappeared after handoff", code="DELTA_STORAGE_DRIFT"
                )
            record = _workspace_record(updated)
            if record.state is not WorkspaceLeaseState.HANDOFF_PENDING:
                raise IntegrityError(
                    "workspace handoff did not persist",
                    code="DELTA_STORAGE_DRIFT",
                )
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="WORKSPACE_HANDOFF_REQUESTED",
                subject_id=workspace_id,
                payload={
                    "workspace_id": workspace_id,
                    "generation": expected_generation,
                    "from_state": WorkspaceLeaseState.ACTIVE.value,
                    "to_state": WorkspaceLeaseState.HANDOFF_PENDING.value,
                },
            )
            return record

    def mark_workspace_takeover_pending(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        workspace_id: str,
        expected_generation: int,
        crash_evidence_ref: str,
        now: datetime | None = None,
    ) -> WorkspaceLeaseRecord:
        _port_context(context, revision_set_id)
        workspace_id = _port_text(workspace_id, "workspace_id", maximum=512)
        expected_generation = _port_positive(expected_generation, "expected_generation")
        crash_evidence_ref = _port_text(crash_evidence_ref, "crash_evidence_ref")
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        parameters = (*scope, workspace_id, expected_generation)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            row = cursor.execute(
                f"SELECT {_WORKSPACE_COLUMNS} FROM workspace_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND workspace_id=? "
                "AND generation=? FOR UPDATE",
                parameters,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "workspace generation was not found", code="WORKSPACE_NOT_FOUND"
                )
            current = _workspace_record(row)
            if current.state is WorkspaceLeaseState.TAKEOVER_PENDING:
                if current.takeover_evidence_ref != crash_evidence_ref:
                    raise ConflictError(
                        "workspace crash takeover replay changed its evidence",
                        code="WORKSPACE_STATE_CONFLICT",
                    )
                return current
            if current.state is not WorkspaceLeaseState.ACTIVE:
                raise ConflictError(
                    "workspace is not eligible for crash takeover",
                    code="WORKSPACE_STATE_CONFLICT",
                )
            changed = cursor.execute(
                "UPDATE workspace_leases SET state='TAKEOVER_PENDING',updated_at=?,"
                "takeover_evidence_ref=? "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND workspace_id=? "
                "AND generation=? AND state='ACTIVE'",
                (_iso(timestamp), crash_evidence_ref, *parameters),
            )
            if changed.rowcount != 1:
                raise ConflictError(
                    "workspace crash takeover compare-and-swap failed",
                    code="WORKSPACE_STATE_CONFLICT",
                )
            updated = cursor.execute(
                f"SELECT {_WORKSPACE_COLUMNS} FROM workspace_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND workspace_id=? AND generation=?",
                parameters,
            ).fetchone()
            if updated is None:
                raise IntegrityError(
                    "workspace disappeared after crash takeover marking",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _workspace_record(updated)
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="WORKSPACE_TAKEOVER_PENDING",
                subject_id=workspace_id,
                payload={
                    "workspace_id": workspace_id,
                    "generation": expected_generation,
                    "crash_evidence_ref": crash_evidence_ref,
                },
            )
            return record

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
    ) -> WorkspaceLeaseRecord:
        _port_context(context, revision_set_id)
        workspace_id = _port_text(workspace_id, "workspace_id", maximum=512)
        expected_generation = _port_positive(expected_generation, "expected_generation")
        new_owner_execution_id = _port_text(
            new_owner_execution_id,
            "new_owner_execution_id",
            maximum=512,
        )
        if base_revision is not None:
            base_revision = _port_text(base_revision, "base_revision", maximum=512)
        normalized_scopes = (
            None if write_scopes is None else _port_workspace_scopes(write_scopes)
        )
        if normalized_scopes is not None and not normalized_scopes:
            raise ValidationError("write_scopes must not be empty")
        timestamp = _port_time(now, "now", default_now=True)
        new_generation = expected_generation + 1
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            assert context.run_id is not None
            assert context.authority_revision is not None
            scope = _runtime_scope_parameters(context, revision_set_id)
            old_parameters = (
                *scope,
                workspace_id,
                expected_generation,
            )
            row = cursor.execute(
                f"SELECT {_WORKSPACE_COLUMNS} FROM workspace_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND workspace_id=? AND generation=? FOR UPDATE",
                old_parameters,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "workspace generation was not found", code="WORKSPACE_NOT_FOUND"
                )
            current = _workspace_record(row)
            if base_revision is not None and not hmac.compare_digest(
                base_revision,
                current.base_revision,
            ):
                raise ConflictError(
                    "workspace takeover cannot change base revision",
                    code="WORKSPACE_AUTHORITY_EXPANSION",
                )
            if (
                normalized_scopes is not None
                and normalized_scopes != current.write_scopes
            ):
                raise ConflictError(
                    "workspace takeover cannot change write scopes",
                    code="WORKSPACE_AUTHORITY_EXPANSION",
                )
            desired_base = current.base_revision
            desired_scopes = current.write_scopes
            if current.owner_execution_id == new_owner_execution_id:
                raise ConflictError(
                    "workspace takeover requires a different owner",
                    code="WORKSPACE_OWNER_CONFLICT",
                )
            if current.state is WorkspaceLeaseState.RETIRED:
                replay_row = cursor.execute(
                    f"SELECT {_WORKSPACE_COLUMNS} FROM workspace_leases "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND workspace_id=? "
                    "AND generation=? FOR UPDATE",
                    (*scope, workspace_id, new_generation),
                ).fetchone()
                if replay_row is None:
                    raise ConflictError(
                        "retired workspace has no takeover generation",
                        code="WORKSPACE_STATE_CONFLICT",
                    )
                replay = _workspace_record(replay_row)
                if not (
                    replay.owner_execution_id == new_owner_execution_id
                    and replay.repository_id == current.repository_id
                    and replay.base_revision == desired_base
                    and replay.write_scopes == desired_scopes
                ):
                    raise ConflictError(
                        "workspace takeover replay diverges",
                        code="WORKSPACE_OWNER_CONFLICT",
                    )
                return replay
            if current.state not in {
                WorkspaceLeaseState.HANDOFF_PENDING,
                WorkspaceLeaseState.TAKEOVER_PENDING,
            }:
                raise ConflictError(
                    "workspace takeover requires pending handoff or crash evidence",
                    code="WORKSPACE_STATE_CONFLICT",
                )
            update = cursor.execute(
                "UPDATE workspace_leases SET state='RETIRED',updated_at=?,retired_at=?,"
                "takeover_evidence_ref=NULL "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND workspace_id=? "
                "AND generation=? AND state=?",
                (
                    _iso(timestamp),
                    _iso(timestamp),
                    *old_parameters,
                    current.state.value,
                ),
            )
            if update.rowcount != 1:
                raise ConflictError(
                    "workspace takeover compare-and-swap failed",
                    code="WORKSPACE_STATE_CONFLICT",
                )
            try:
                cursor.execute(
                    "INSERT INTO workspace_leases("
                    f"{_WORKSPACE_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',?,?,?,?)",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        context.run_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        workspace_id,
                        new_owner_execution_id,
                        new_generation,
                        current.repository_id,
                        desired_base,
                        canonical_json(list(desired_scopes)),
                        None,
                        _iso(timestamp),
                        _iso(timestamp),
                        None,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "workspace takeover generation conflicts",
                    code="WORKSPACE_OWNER_CONFLICT",
                ) from exc
            replacement = cursor.execute(
                f"SELECT {_WORKSPACE_COLUMNS} FROM workspace_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND workspace_id=? AND generation=?",
                (*scope, workspace_id, new_generation),
            ).fetchone()
            if replacement is None:
                raise IntegrityError(
                    "workspace takeover generation was not persisted",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _workspace_record(replacement)
            if not (
                record.owner_execution_id == new_owner_execution_id
                and record.repository_id == current.repository_id
                and record.base_revision == current.base_revision
                and record.write_scopes == current.write_scopes
                and record.state is WorkspaceLeaseState.ACTIVE
            ):
                raise IntegrityError(
                    "workspace takeover successor content drifted",
                    code="DELTA_STORAGE_DRIFT",
                )
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="WORKSPACE_TAKEN_OVER",
                subject_id=workspace_id,
                payload={
                    "workspace_id": workspace_id,
                    "previous_generation": expected_generation,
                    "generation": new_generation,
                    "owner_execution_id": new_owner_execution_id,
                    "repository_id": current.repository_id,
                    "base_revision": current.base_revision,
                    "write_scopes": current.write_scopes,
                },
            )
            return record

    def retire_workspace(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        workspace_id: str,
        expected_generation: int,
        expected_state: WorkspaceLeaseState,
        now: datetime | None = None,
    ) -> WorkspaceLeaseRecord:
        _port_context(context, revision_set_id)
        workspace_id = _port_text(workspace_id, "workspace_id", maximum=512)
        expected_generation = _port_positive(expected_generation, "expected_generation")
        if expected_state not in {
            WorkspaceLeaseState.ACTIVE,
            WorkspaceLeaseState.HANDOFF_PENDING,
            WorkspaceLeaseState.TAKEOVER_PENDING,
        }:
            raise ValidationError("workspace expected state is invalid")
        timestamp = _port_time(now, "now", default_now=True)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            scope = _runtime_scope_parameters(context, revision_set_id)
            parameters = (
                *scope,
                workspace_id,
                expected_generation,
            )
            row = cursor.execute(
                f"SELECT {_WORKSPACE_COLUMNS} FROM workspace_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND workspace_id=? AND generation=? FOR UPDATE",
                parameters,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "workspace generation was not found", code="WORKSPACE_NOT_FOUND"
                )
            current = _workspace_record(row)
            if current.state is WorkspaceLeaseState.RETIRED:
                return current
            if current.state is not expected_state:
                raise ConflictError(
                    "workspace generation state is stale",
                    code="WORKSPACE_STATE_CONFLICT",
                )
            update = cursor.execute(
                "UPDATE workspace_leases SET state='RETIRED',updated_at=?,retired_at=?,"
                "takeover_evidence_ref=NULL "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND workspace_id=? "
                "AND generation=? AND state=?",
                (_iso(timestamp), _iso(timestamp), *parameters, expected_state.value),
            )
            if update.rowcount != 1:
                raise ConflictError(
                    "workspace retire compare-and-swap failed",
                    code="WORKSPACE_STATE_CONFLICT",
                )
            updated = cursor.execute(
                f"SELECT {_WORKSPACE_COLUMNS} FROM workspace_leases "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND workspace_id=? AND generation=?",
                parameters,
            ).fetchone()
            if updated is None:
                raise IntegrityError(
                    "workspace disappeared after retirement", code="DELTA_STORAGE_DRIFT"
                )
            record = _workspace_record(updated)
            if record.state is not WorkspaceLeaseState.RETIRED:
                raise IntegrityError(
                    "workspace retirement did not persist",
                    code="DELTA_STORAGE_DRIFT",
                )
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="WORKSPACE_RETIRED",
                subject_id=workspace_id,
                payload={
                    "workspace_id": workspace_id,
                    "generation": expected_generation,
                    "from_state": expected_state.value,
                    "to_state": WorkspaceLeaseState.RETIRED.value,
                },
            )
            return record

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
    ) -> DurableEventRegistrationRecord:
        _port_context(context, revision_set_id)
        event_type = _port_text(event_type, "event_type", maximum=255)
        owner = _port_text(owner, "owner", maximum=512)
        schema_version = _port_positive(schema_version, "schema_version")
        if not isinstance(semantics, DurableEventSemantics):
            raise ValidationError("event semantics must be typed")
        if not isinstance(compatibility, EventCompatibility):
            raise ValidationError("event compatibility must be typed")
        validator_ref = _port_text(validator_ref, "validator_ref")
        upgrader_ref = _port_text(upgrader_ref, "upgrader_ref")
        normalized_projections = _port_strings(
            projections,
            "projections",
            maximum_items=128,
        )
        require_sha256_digest(registration_hash, field="registration_hash")
        expected_registration_hash = digest_object(
            {
                "type": event_type,
                "owner": owner,
                "schemaVersion": schema_version,
                "semantics": semantics.value,
                "validator": validator_ref,
                "upgrader": upgrader_ref,
                "projections": list(normalized_projections),
                "compatibility": compatibility.value,
            },
            domain="delta-event-registration",
        )
        if not hmac.compare_digest(expected_registration_hash, registration_hash):
            raise ValidationError(
                "registration_hash does not bind the exact event registration"
            )
        timestamp = _port_time(now, "now", default_now=True)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            assert context.run_id is not None
            assert context.authority_revision is not None
            scope = _runtime_scope_parameters(context, revision_set_id)
            try:
                cursor.execute(
                    "INSERT INTO durable_event_registrations("
                    f"{_EVENT_REGISTRATION_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT (tenant_id,project_id,run_id,execution_epoch,"
                    "fencing_generation,authority_revision,revision_set_id,event_type,"
                    "schema_version) DO NOTHING",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        context.run_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        event_type,
                        owner,
                        schema_version,
                        semantics.value,
                        compatibility.value,
                        validator_ref,
                        upgrader_ref,
                        canonical_json(list(normalized_projections)),
                        registration_hash,
                        _iso(timestamp),
                    ),
                )
                inserted_count = cursor.rowcount
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "durable event registration identity or digest conflicts",
                    code="EVENT_REGISTRATION_CONFLICT",
                ) from exc
            row = cursor.execute(
                f"SELECT {_EVENT_REGISTRATION_COLUMNS} FROM durable_event_registrations "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND event_type=? "
                "AND schema_version=? FOR UPDATE",
                (*scope, event_type, schema_version),
            ).fetchone()
            if row is None:
                raise ConflictError(
                    "event registration identity is occupied outside the actor scope",
                    code="EVENT_REGISTRATION_CONFLICT",
                )
            record = _event_registration_record(row)
            if not (
                record.owner == owner
                and record.semantics is semantics
                and record.compatibility is compatibility
                and record.validator_ref == validator_ref
                and record.upgrader_ref == upgrader_ref
                and record.projections == normalized_projections
                and hmac.compare_digest(record.registration_hash, registration_hash)
            ):
                raise ConflictError(
                    "durable event registration replay diverges from immutable content",
                    code="EVENT_REGISTRATION_CONFLICT",
                )
            if inserted_count == 1:
                self._append_runtime_assurance_outbox(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    event_type="DURABLE_EVENT_REGISTERED",
                    subject_id=event_type,
                    payload={
                        "event_type": event_type,
                        "schema_version": schema_version,
                        "registration_hash": registration_hash,
                    },
                )
            return record

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
    ) -> DurableEventInstanceRecord:
        _port_context(context, revision_set_id)
        event_id = _port_text(event_id, "event_id", maximum=512)
        event_type = _port_text(event_type, "event_type", maximum=255)
        schema_version = _port_positive(schema_version, "schema_version")
        payload_ref = _port_text(payload_ref, "payload_ref")
        require_sha256_digest(payload_digest, field="payload_digest")
        correlation_id = _port_text(correlation_id, "correlation_id", maximum=512)
        if causation_id is not None:
            causation_id = _port_text(causation_id, "causation_id", maximum=512)
        if parent_event_id is not None:
            parent_event_id = _port_text(
                parent_event_id, "parent_event_id", maximum=512
            )
        lineage = _port_strings(fork_lineage, "fork_lineage")
        if parent_event_id is None and lineage:
            raise ValidationError("root durable event cannot have fork lineage")
        if parent_event_id is not None and (
            not lineage or lineage[-1] != parent_event_id
        ):
            raise ValidationError("fork_lineage must terminate at parent_event_id")
        if not isinstance(compatibility_decision, EventCompatibilityDecision):
            raise ValidationError("event compatibility decision must be typed")
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        source_scope = {
            "tenantId": context.tenant_id,
            "projectId": context.project_id,
            "runId": context.run_id,
            "actorId": context.actor_id,
            "executionEpoch": context.execution_epoch,
            "fencingGeneration": context.fencing_generation,
            "authorityRevision": context.authority_revision,
            "revisionSetId": revision_set_id,
        }
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            registration = cursor.execute(
                "SELECT 1 AS present FROM durable_event_registrations "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND event_type=? AND schema_version=? "
                "FOR KEY SHARE",
                (*scope, event_type, schema_version),
            ).fetchone()
            if registration is None:
                raise NotFoundError(
                    "durable event registration was not found",
                    code="EVENT_REGISTRATION_NOT_FOUND",
                )
            if parent_event_id is not None:
                parent_row = cursor.execute(
                    f"SELECT {_DURABLE_EVENT_INSTANCE_COLUMNS} "
                    "FROM durable_event_instances "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND event_id=? FOR KEY SHARE",
                    (*scope, parent_event_id),
                ).fetchone()
                if parent_row is None:
                    raise NotFoundError(
                        "durable event parent was not found",
                        code="DURABLE_EVENT_PARENT_NOT_FOUND",
                    )
                parent = _durable_event_instance_record(parent_row)
                if parent.correlation_id != correlation_id or lineage != (
                    *parent.fork_lineage,
                    parent.event_id,
                ):
                    raise ConflictError(
                        "durable event fork lineage or correlation diverges",
                        code="DURABLE_EVENT_LINEAGE_CONFLICT",
                    )
            try:
                cursor.execute(
                    "INSERT INTO durable_event_instances("
                    f"{_DURABLE_EVENT_INSTANCE_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'PENDING',NULL,?,?,NULL) "
                    "ON CONFLICT (tenant_id,project_id,run_id,execution_epoch,"
                    "fencing_generation,authority_revision,revision_set_id,event_id) "
                    "DO NOTHING",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        context.run_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        event_id,
                        event_type,
                        schema_version,
                        payload_ref,
                        payload_digest,
                        causation_id,
                        correlation_id,
                        parent_event_id,
                        canonical_json(source_scope),
                        canonical_json(list(lineage)),
                        compatibility_decision.value,
                        _iso(timestamp),
                        _iso(timestamp),
                    ),
                )
                inserted_count = cursor.rowcount
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "durable event identity or lineage conflicts",
                    code="DURABLE_EVENT_CONFLICT",
                ) from exc
            row = cursor.execute(
                f"SELECT {_DURABLE_EVENT_INSTANCE_COLUMNS} "
                "FROM durable_event_instances "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND event_id=? FOR UPDATE",
                (*scope, event_id),
            ).fetchone()
            if row is None:
                raise ConflictError(
                    "durable event identity is occupied outside scope",
                    code="DURABLE_EVENT_CONFLICT",
                )
            record = _durable_event_instance_record(row)
            if not (
                record.event_type == event_type
                and record.schema_version == schema_version
                and record.payload_ref == payload_ref
                and hmac.compare_digest(record.payload_digest, payload_digest)
                and record.causation_id == causation_id
                and record.correlation_id == correlation_id
                and record.parent_event_id == parent_event_id
                and record.fork_lineage == lineage
                and record.compatibility_decision is compatibility_decision
            ):
                raise ConflictError(
                    "durable event replay diverges from immutable content",
                    code="DURABLE_EVENT_CONFLICT",
                )
            if inserted_count == 1:
                self._append_runtime_assurance_outbox(
                    cursor,
                    context,
                    revision_set_id=revision_set_id,
                    event_type="DURABLE_EVENT_APPENDED",
                    subject_id=event_id,
                    payload={
                        "event_id": event_id,
                        "event_type": event_type,
                        "schema_version": schema_version,
                        "payload_digest": payload_digest,
                        "correlation_id": correlation_id,
                        "causation_id": causation_id,
                        "parent_event_id": parent_event_id,
                    },
                )
            return record

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
    ) -> DurableEventInstanceRecord:
        _port_context(context, revision_set_id)
        event_id = _port_text(event_id, "event_id", maximum=512)
        if (
            expected_state is not DurableEventInstanceState.PENDING
            or target_state
            not in {
                DurableEventInstanceState.PROCESSED,
                DurableEventInstanceState.SKIPPED,
            }
        ):
            raise ValidationError("durable event replay transition is invalid")
        if not isinstance(compatibility_decision, EventCompatibilityDecision):
            raise ValidationError("event compatibility decision must be typed")
        if target_state is DurableEventInstanceState.SKIPPED:
            if compatibility_decision is not EventCompatibilityDecision.SKIPPED:
                raise ValidationError(
                    "skipped event requires SKIPPED compatibility decision"
                )
            if skip_reason is None:
                raise ValidationError("skipped event requires skip_reason")
            skip_reason = _port_text(skip_reason, "skip_reason")
        elif (
            skip_reason is not None
            or compatibility_decision is EventCompatibilityDecision.SKIPPED
        ):
            raise ValidationError("processed event cannot contain skip metadata")
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            row = cursor.execute(
                f"SELECT {_DURABLE_EVENT_INSTANCE_COLUMNS} "
                "FROM durable_event_instances "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND event_id=? FOR UPDATE",
                (*scope, event_id),
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "durable event was not found", code="DURABLE_EVENT_NOT_FOUND"
                )
            current = _durable_event_instance_record(row)
            if current.state is target_state:
                if not (
                    current.compatibility_decision is compatibility_decision
                    and current.skip_reason == skip_reason
                ):
                    raise ConflictError(
                        "durable event replay changed terminal decision",
                        code="DURABLE_EVENT_STATE_CONFLICT",
                    )
                return current
            if current.state is not expected_state:
                raise ConflictError(
                    "durable event state is stale",
                    code="DURABLE_EVENT_STATE_CONFLICT",
                )
            changed = cursor.execute(
                "UPDATE durable_event_instances SET state=?,compatibility_decision=?,"
                "skip_reason=?,updated_at=?,processed_at=? "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND event_id=? AND state='PENDING'",
                (
                    target_state.value,
                    compatibility_decision.value,
                    skip_reason,
                    _iso(timestamp),
                    _iso(timestamp),
                    *scope,
                    event_id,
                ),
            )
            if changed.rowcount != 1:
                raise ConflictError(
                    "durable event replay compare-and-swap failed",
                    code="DURABLE_EVENT_STATE_CONFLICT",
                )
            updated = cursor.execute(
                f"SELECT {_DURABLE_EVENT_INSTANCE_COLUMNS} "
                "FROM durable_event_instances "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND event_id=?",
                (*scope, event_id),
            ).fetchone()
            if updated is None:
                raise IntegrityError(
                    "durable event disappeared", code="DELTA_STORAGE_DRIFT"
                )
            record = _durable_event_instance_record(updated)
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type=f"DURABLE_EVENT_{target_state.value}",
                subject_id=event_id,
                payload={
                    "event_id": event_id,
                    "from_state": expected_state.value,
                    "to_state": target_state.value,
                    "compatibility_decision": compatibility_decision.value,
                    "skip_reason": skip_reason,
                },
            )
            return record

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
    ) -> DurableEventInstanceRecord:
        """Atomically consume one pending event into a registered newer schema."""

        _port_context(context, revision_set_id)
        source_event_id = _port_text(
            source_event_id,
            "source_event_id",
            maximum=512,
        )
        event_id = _port_text(event_id, "event_id", maximum=512)
        if hmac.compare_digest(source_event_id, event_id):
            raise ValidationError("event migration requires a distinct target event_id")
        target_schema_version = _port_positive(
            target_schema_version,
            "target_schema_version",
        )
        payload_ref = _port_text(payload_ref, "payload_ref")
        require_sha256_digest(payload_digest, field="payload_digest")
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        source_scope = {
            "tenantId": context.tenant_id,
            "projectId": context.project_id,
            "runId": context.run_id,
            "actorId": context.actor_id,
            "executionEpoch": context.execution_epoch,
            "fencingGeneration": context.fencing_generation,
            "authorityRevision": context.authority_revision,
            "revisionSetId": revision_set_id,
        }
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            source_row = cursor.execute(
                f"SELECT {_DURABLE_EVENT_INSTANCE_COLUMNS} "
                "FROM durable_event_instances "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND event_id=? FOR UPDATE",
                (*scope, source_event_id),
            ).fetchone()
            if source_row is None:
                raise NotFoundError(
                    "durable event migration source was not found",
                    code="DURABLE_EVENT_NOT_FOUND",
                )
            source = _durable_event_instance_record(source_row)
            if target_schema_version <= source.schema_version:
                raise ValidationError(
                    "event migration target schema must be newer than its source"
                )
            registration = cursor.execute(
                "SELECT upgrader_ref FROM durable_event_registrations "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND event_type=? AND schema_version=? "
                "FOR KEY SHARE",
                (*scope, source.event_type, target_schema_version),
            ).fetchone()
            if registration is None:
                raise NotFoundError(
                    "durable event target registration was not found",
                    code="EVENT_REGISTRATION_NOT_FOUND",
                )
            lineage = (*source.fork_lineage, source.event_id)
            target_row = cursor.execute(
                f"SELECT {_DURABLE_EVENT_INSTANCE_COLUMNS} "
                "FROM durable_event_instances "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND event_id=? FOR UPDATE",
                (*scope, event_id),
            ).fetchone()
            if target_row is not None:
                target = _durable_event_instance_record(target_row)
                if not (
                    source.state is DurableEventInstanceState.PROCESSED
                    and source.compatibility_decision
                    is EventCompatibilityDecision.UPGRADED
                    and target.event_type == source.event_type
                    and target.schema_version == target_schema_version
                    and target.payload_ref == payload_ref
                    and hmac.compare_digest(target.payload_digest, payload_digest)
                    and target.causation_id == source_event_id
                    and target.correlation_id == source.correlation_id
                    and target.parent_event_id == source_event_id
                    and target.fork_lineage == lineage
                    and target.compatibility_decision
                    is EventCompatibilityDecision.UPGRADED
                ):
                    raise ConflictError(
                        "durable event migration replay diverges",
                        code="DURABLE_EVENT_CONFLICT",
                    )
                return target
            if source.state is not DurableEventInstanceState.PENDING:
                raise ConflictError(
                    "durable event migration source is not pending",
                    code="DURABLE_EVENT_STATE_CONFLICT",
                )
            try:
                cursor.execute(
                    "INSERT INTO durable_event_instances("
                    f"{_DURABLE_EVENT_INSTANCE_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'PENDING',NULL,?,?,NULL)",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        context.run_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        event_id,
                        source.event_type,
                        target_schema_version,
                        payload_ref,
                        payload_digest,
                        source_event_id,
                        source.correlation_id,
                        source_event_id,
                        canonical_json(source_scope),
                        canonical_json(list(lineage)),
                        EventCompatibilityDecision.UPGRADED.value,
                        _iso(timestamp),
                        _iso(timestamp),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "durable event migration target conflicts",
                    code="DURABLE_EVENT_CONFLICT",
                ) from exc
            consumed = cursor.execute(
                "UPDATE durable_event_instances SET state='PROCESSED',"
                "compatibility_decision='UPGRADED',updated_at=?,processed_at=? "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND event_id=? AND state='PENDING'",
                (_iso(timestamp), _iso(timestamp), *scope, source_event_id),
            )
            if consumed.rowcount != 1:
                raise ConflictError(
                    "durable event migration source compare-and-swap failed",
                    code="DURABLE_EVENT_STATE_CONFLICT",
                )
            migrated_row = cursor.execute(
                f"SELECT {_DURABLE_EVENT_INSTANCE_COLUMNS} "
                "FROM durable_event_instances "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND event_id=?",
                (*scope, event_id),
            ).fetchone()
            if migrated_row is None:
                raise IntegrityError(
                    "durable event migration target disappeared",
                    code="DELTA_STORAGE_DRIFT",
                )
            migrated = _durable_event_instance_record(migrated_row)
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="DURABLE_EVENT_MIGRATED",
                subject_id=event_id,
                payload={
                    "source_event_id": source_event_id,
                    "event_id": event_id,
                    "event_type": source.event_type,
                    "source_schema_version": source.schema_version,
                    "target_schema_version": target_schema_version,
                    "payload_ref": payload_ref,
                    "payload_digest": payload_digest,
                    "correlation_id": source.correlation_id,
                    "upgrader_ref": str(registration["upgrader_ref"]),
                },
            )
            return migrated

    def preflight_event_owner_change(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        action: EventOwnerChangeAction,
        owner: str,
        target_version: int | None = None,
        now: datetime | None = None,
    ) -> DurableEventOwnerChangePreflight:
        _port_context(context, revision_set_id)
        if not isinstance(action, EventOwnerChangeAction):
            raise ValidationError("event owner change action must be typed")
        owner = _port_text(owner, "owner", maximum=512)
        if action is EventOwnerChangeAction.DOWNGRADE:
            if target_version is None:
                raise ValidationError("event owner downgrade requires target_version")
            target_version = _port_positive(target_version, "target_version")
        elif target_version is not None:
            raise ValidationError("event owner uninstall cannot have target_version")
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            registrations = cursor.execute(
                "SELECT event_type,schema_version,semantics,compatibility "
                "FROM durable_event_registrations "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND owner=? "
                "ORDER BY event_type,schema_version FOR UPDATE",
                (*scope, owner),
            ).fetchall()
            blockers: list[str] = []
            if not registrations:
                blockers.append("OWNER_NOT_REGISTERED")
            for registration in registrations:
                event_type = str(registration["event_type"])
                version = int(registration["schema_version"])
                pending = cursor.execute(
                    "SELECT 1 AS present FROM durable_event_instances "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND event_type=? AND schema_version=? "
                    "AND state='PENDING' LIMIT 1 FOR UPDATE",
                    (*scope, event_type, version),
                ).fetchone()
                if (
                    pending is not None
                    and str(registration["semantics"])
                    == DurableEventSemantics.REQUIRED_STATE.value
                ):
                    blockers.append(f"PENDING_REQUIRED_EVENT:{event_type}:{version}")
                if (
                    action is EventOwnerChangeAction.DOWNGRADE
                    and target_version is not None
                    and version > target_version
                ):
                    blockers.append(f"VERSION_ABOVE_TARGET:{event_type}:{version}")
            preflight = DurableEventOwnerChangePreflight(
                action=action,
                owner=owner,
                target_version=target_version,
                allowed=not blockers,
                blockers=tuple(blockers),
            )
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="DURABLE_EVENT_OWNER_CHANGE_PREFLIGHT",
                subject_id=owner,
                payload={
                    "action": action.value,
                    "owner": owner,
                    "target_version": target_version,
                    "allowed": preflight.allowed,
                    "blockers": preflight.blockers,
                    "evaluated_at": timestamp,
                },
            )
            return preflight

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
    ) -> DurableEventInstanceRecord:
        _port_context(context, revision_set_id)
        parent_event_id = _port_text(parent_event_id, "parent_event_id", maximum=512)
        scope = _runtime_scope_parameters(context, revision_set_id)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            row = cursor.execute(
                f"SELECT {_DURABLE_EVENT_INSTANCE_COLUMNS} "
                "FROM durable_event_instances "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND event_id=? FOR KEY SHARE",
                (*scope, parent_event_id),
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "durable event parent was not found",
                    code="DURABLE_EVENT_PARENT_NOT_FOUND",
                )
            parent = _durable_event_instance_record(row)
        return self.append_durable_event(
            context,
            revision_set_id=revision_set_id,
            event_id=event_id,
            event_type=parent.event_type,
            schema_version=parent.schema_version,
            payload_ref=payload_ref,
            payload_digest=payload_digest,
            correlation_id=parent.correlation_id,
            causation_id=parent.event_id,
            parent_event_id=parent.event_id,
            fork_lineage=(*parent.fork_lineage, parent.event_id),
            compatibility_decision=EventCompatibilityDecision.EXACT,
            now=now,
        )

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
    ) -> tuple[TypedIngressRecord, bool]:
        _port_context(context, revision_set_id)
        ingress_id = _port_text(ingress_id, "ingress_id", maximum=512)
        producer_execution_id = _port_text(
            producer_execution_id,
            "producer_execution_id",
            maximum=512,
        )
        deduplication_key = _port_text(
            deduplication_key,
            "deduplication_key",
            maximum=512,
        )
        if not isinstance(kind, TypedIngressKind):
            raise ValidationError("typed ingress kind must be typed")
        allowed_kinds = self._typed_ingress_policy.get(producer_execution_id)
        if allowed_kinds is None or kind not in allowed_kinds:
            raise AuthorizationError(
                "typed ingress producer is not configured for this kind",
                code="TYPED_INGRESS_KIND_DENIED",
            )
        require_sha256_digest(envelope_digest, field="envelope_digest")
        payload_ref = _port_text(payload_ref, "payload_ref")
        correlation_id = _port_text(correlation_id, "correlation_id", maximum=512)
        if causation_id is not None:
            causation_id = _port_text(causation_id, "causation_id", maximum=512)
        if originating_call_id is not None:
            originating_call_id = _port_text(
                originating_call_id,
                "originating_call_id",
                maximum=512,
            )
        if kind is TypedIngressKind.TOOL_RESULT and originating_call_id is None:
            raise ValidationError("tool result ingress requires originating_call_id")
        timestamp = _port_time(now, "now", default_now=True)
        occurred = (
            timestamp if occurred_at is None else _port_time(occurred_at, "occurred_at")
        )
        if occurred > timestamp:
            raise ValidationError("occurred_at cannot follow recorded_at")
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            assert context.run_id is not None
            assert context.authority_revision is not None
            scope = _runtime_scope_parameters(context, revision_set_id)
            if kind is TypedIngressKind.TOOL_RESULT:
                assert originating_call_id is not None
                pending_call = cursor.execute(
                    f"SELECT {_PENDING_TOOL_CALL_COLUMNS} "
                    "FROM pending_tool_call_bindings "
                    f"WHERE {_RUNTIME_SCOPE_SQL} AND call_id=? FOR KEY SHARE",
                    (*scope, originating_call_id),
                ).fetchone()
                if pending_call is None:
                    raise ConflictError(
                        "tool-result ingress references an unknown durable call",
                        code="TYPED_INGRESS_CALL_NOT_FOUND",
                    )
                call_binding = _pending_tool_call_record(pending_call)
                if call_binding.state not in {
                    PendingToolCallBindingState.PENDING,
                    PendingToolCallBindingState.RECONCILED,
                }:
                    raise IntegrityError(
                        "tool-result ingress call binding has an invalid state",
                        code="DELTA_STORAGE_DRIFT",
                    )
            identity_rows = cursor.execute(
                f"SELECT {_TYPED_INGRESS_COLUMNS} FROM typed_ingress_records "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND "
                "(ingress_id=? OR (producer_execution_id=? AND deduplication_key=?)) "
                "FOR UPDATE",
                (
                    *scope,
                    ingress_id,
                    producer_execution_id,
                    deduplication_key,
                ),
            ).fetchall()
            if len(identity_rows) > 1:
                raise ConflictError(
                    "typed ingress identities resolve to different records",
                    code="TYPED_INGRESS_CONFLICT",
                )
            if identity_rows:
                replay = _typed_ingress_record(identity_rows[0])
                if not (
                    replay.run_id == context.run_id
                    and replay.actor_id == context.actor_id
                    and replay.ingress_id == ingress_id
                    and replay.producer_execution_id == producer_execution_id
                    and replay.deduplication_key == deduplication_key
                    and replay.kind is kind
                    and hmac.compare_digest(replay.envelope_digest, envelope_digest)
                    and replay.payload_ref == payload_ref
                    and replay.originating_call_id == originating_call_id
                    and replay.causation_id == causation_id
                    and replay.correlation_id == correlation_id
                    and replay.occurred_at == occurred
                ):
                    raise ConflictError(
                        "typed ingress replay diverges from durable content",
                        code="TYPED_INGRESS_CONFLICT",
                    )
                return replay, False
            try:
                inserted = cursor.execute(
                    "INSERT INTO typed_ingress_records("
                    f"{_TYPED_INGRESS_INSERT_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT DO NOTHING",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        context.actor_id,
                        ingress_id,
                        producer_execution_id,
                        deduplication_key,
                        kind.value,
                        envelope_digest,
                        payload_ref,
                        originating_call_id,
                        causation_id,
                        correlation_id,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        _iso(occurred),
                        _iso(timestamp),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "typed ingress identity or deduplication key conflicts",
                    code="TYPED_INGRESS_CONFLICT",
                ) from exc
            if inserted.rowcount != 1:
                raise ConflictError(
                    "typed ingress was concurrently claimed",
                    code="TYPED_INGRESS_CONFLICT",
                )
            row = cursor.execute(
                f"SELECT {_TYPED_INGRESS_COLUMNS} FROM typed_ingress_records "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND ingress_id=? FOR UPDATE",
                (*scope, ingress_id),
            ).fetchone()
            if row is None:
                raise IntegrityError(
                    "typed ingress disappeared after acceptance",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _typed_ingress_record(row)
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="TYPED_INGRESS_ACCEPTED",
                subject_id=ingress_id,
                payload={
                    "ingress_id": ingress_id,
                    "producer_execution_id": producer_execution_id,
                    "deduplication_key": deduplication_key,
                    "kind": kind.value,
                    "envelope_digest": envelope_digest,
                    "causation_id": causation_id,
                    "correlation_id": correlation_id,
                    "occurred_at": occurred,
                },
            )
            return record, True

    def page_typed_ingress(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        correlation_id: str,
        after: tuple[datetime, str] | None = None,
        limit: int = 100,
    ) -> TypedIngressPage:
        _port_context(context, revision_set_id)
        correlation_id = _port_text(correlation_id, "correlation_id", maximum=512)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 200
        ):
            raise ValidationError("typed ingress page limit must be between 1 and 200")
        cursor_clause = ""
        cursor_parameters: tuple[Any, ...] = ()
        if after is not None:
            if not isinstance(after, tuple) or len(after) != 2:
                raise ValidationError("typed ingress page cursor is invalid")
            after_time = _port_time(after[0], "after.occurred_at")
            after_id = _port_text(after[1], "after.ingress_id", maximum=512)
            cursor_clause = " AND (occurred_at,ingress_id)>(?,?)"
            cursor_parameters = (_iso(after_time), after_id)
        scope = _runtime_scope_parameters(context, revision_set_id)
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            rows = cursor.execute(
                f"SELECT {_TYPED_INGRESS_COLUMNS} FROM typed_ingress_records "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND correlation_id=?{cursor_clause} "
                "ORDER BY occurred_at,ingress_id LIMIT ?",
                (*scope, correlation_id, *cursor_parameters, limit + 1),
            ).fetchall()
        records = tuple(_typed_ingress_record(row) for row in rows[:limit])
        next_cursor = None
        if len(rows) > limit and records:
            next_cursor = (records[-1].occurred_at, records[-1].ingress_id)
        return TypedIngressPage(records=records, next_cursor=next_cursor)

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
    ) -> SubagentBudgetReservationBindingRecord:
        _port_context(context, revision_set_id)
        reservation_id = _port_text(reservation_id, "reservation_id", maximum=512)
        operation_invocation_id = _port_text(
            operation_invocation_id,
            "operation_invocation_id",
            maximum=512,
        )
        self._require_active_invocation_operation(operation_invocation_id)
        parent_execution_id = _port_text(
            parent_execution_id,
            "parent_execution_id",
            maximum=512,
        )
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        authority_snapshot_id = _port_authority_snapshot(
            context,
            authority_snapshot_id,
        )
        provider = _port_text(provider, "provider", maximum=255)
        model = _port_text(model, "model", maximum=512)
        reasoning_effort = _port_text(
            reasoning_effort,
            "reasoning_effort",
            maximum=16,
        )
        normalized_child_authority = tuple(
            sorted(_port_strings(child_authority, "child_authority"))
        )
        normalized_child_tools = tuple(
            sorted(_port_strings(child_tools, "child_tools"))
        )
        max_output_tokens = _port_positive(max_output_tokens, "max_output_tokens")
        deadline = _port_time(wall_clock_deadline, "wall_clock_deadline")
        require_sha256_digest(tool_plan_hash, field="tool_plan_hash")
        require_sha256_digest(
            authority_envelope_digest,
            field="authority_envelope_digest",
        )
        if not isinstance(host_envelope, HostSignedEnvelope):
            raise ValidationError("host_envelope must be typed")
        timestamp = _port_time(now, "now", default_now=True)
        if deadline <= timestamp:
            raise ValidationError("subagent reservation deadline has expired")
        assert context.run_id is not None
        assert context.authority_revision is not None
        candidate = SubagentBudgetReservationBindingRecord(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            run_id=context.run_id,
            actor_id=context.actor_id,
            execution_epoch=context.execution_epoch,
            fencing_generation=context.fencing_generation,
            authority_revision=context.authority_revision,
            revision_set_id=revision_set_id,
            reservation_id=reservation_id,
            operation_invocation_id=operation_invocation_id,
            parent_execution_id=parent_execution_id,
            environment_id=environment_id,
            authority_snapshot_id=authority_snapshot_id,
            provider=provider,
            model=model,
            reasoning_effort=reasoning_effort,
            child_authority=normalized_child_authority,
            child_tools=normalized_child_tools,
            max_output_tokens=max_output_tokens,
            max_cost_budget=max_cost_budget,
            wall_clock_deadline=deadline,
            tool_plan_hash=tool_plan_hash,
            authority_envelope_digest=authority_envelope_digest,
            host_envelope=host_envelope,
            state=SubagentBudgetReservationState.RESERVED,
            created_at=timestamp,
            updated_at=timestamp,
        )
        scope = _runtime_scope_parameters(context, revision_set_id)
        identity = (*scope, reservation_id)
        with self._authority_transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            existing = cursor.execute(
                f"SELECT {_SUBAGENT_RESERVATION_COLUMNS} "
                "FROM subagent_budget_reservation_bindings "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND reservation_id=? FOR UPDATE",
                identity,
            ).fetchone()
            if existing is not None:
                record = _subagent_reservation_record(existing)
                comparable = (
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
                )
                expected = (
                    candidate.operation_invocation_id,
                    candidate.parent_execution_id,
                    candidate.environment_id,
                    candidate.authority_snapshot_id,
                    candidate.provider,
                    candidate.model,
                    candidate.reasoning_effort,
                    candidate.child_authority,
                    candidate.child_tools,
                    candidate.max_output_tokens,
                    candidate.max_cost_budget,
                    candidate.wall_clock_deadline,
                    candidate.tool_plan_hash,
                    candidate.authority_envelope_digest,
                    candidate.host_envelope,
                )
                if comparable != expected:
                    raise ConflictError(
                        "subagent reservation replay diverges",
                        code="SUBAGENT_RESERVATION_CONFLICT",
                    )
                return record
            values = (
                context.tenant_id,
                context.project_id,
                context.run_id,
                context.actor_id,
                context.execution_epoch,
                context.fencing_generation,
                context.authority_revision,
                revision_set_id,
                reservation_id,
                operation_invocation_id,
                parent_execution_id,
                environment_id,
                authority_snapshot_id,
                provider,
                model,
                reasoning_effort,
                canonical_json(list(normalized_child_authority)),
                canonical_json(list(normalized_child_tools)),
                max_output_tokens,
                candidate.max_cost_budget,
                _iso(deadline),
                tool_plan_hash,
                authority_envelope_digest,
                host_envelope.payload_digest,
                host_envelope.envelope_digest,
                host_envelope.issuer,
                host_envelope.signing_key_id,
                host_envelope.signature_algorithm,
                host_envelope.signature,
                _iso(host_envelope.issued_at),
                host_envelope.verifier_id,
                host_envelope.verification_evidence_ref,
                host_envelope.verification_evidence_digest,
                _iso(host_envelope.verified_at),
                _iso(timestamp),
                _iso(timestamp),
            )
            inserted = cursor.execute(
                "INSERT INTO subagent_budget_reservation_bindings("
                f"{_SUBAGENT_RESERVATION_COLUMNS}) VALUES ("
                + ",".join("?" for _ in range(34))
                + ",'RESERVED',?,?,NULL,NULL,NULL,NULL) ON CONFLICT DO NOTHING",
                values,
            )
            if inserted.rowcount != 1:
                raise ConflictError(
                    "subagent reservation was concurrently bound",
                    code="SUBAGENT_RESERVATION_CONFLICT",
                )
            row = cursor.execute(
                f"SELECT {_SUBAGENT_RESERVATION_COLUMNS} "
                "FROM subagent_budget_reservation_bindings "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND reservation_id=?",
                identity,
            ).fetchone()
            if row is None:
                raise IntegrityError(
                    "subagent reservation disappeared after persistence",
                    code="DELTA_STORAGE_DRIFT",
                )
            return _subagent_reservation_record(row)

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
    ) -> SubagentExecutionSpecRecord:
        _port_context(context, revision_set_id)
        invocation_id = _port_text(invocation_id, "invocation_id", maximum=512)
        self._require_active_invocation_operation(invocation_id)
        parent_execution_id = _port_text(
            parent_execution_id,
            "parent_execution_id",
            maximum=512,
        )
        provider = _port_text(provider, "provider", maximum=255)
        model = _port_text(model, "model", maximum=512)
        reasoning_effort = _port_text(
            reasoning_effort,
            "reasoning_effort",
            maximum=32,
        )
        if reasoning_effort not in {
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
        authority_snapshot_id = _port_authority_snapshot(
            context,
            authority_snapshot_id,
        )
        environment_id = _port_text(environment_id, "environment_id", maximum=512)
        budget_reservation_id = _port_text(
            budget_reservation_id,
            "budget_reservation_id",
            maximum=512,
        )
        max_output_tokens = _port_positive(max_output_tokens, "max_output_tokens")
        if max_output_tokens > 1_000_000:
            raise ValidationError("max_output_tokens exceeds the supported bound")
        require_sha256_digest(tool_plan_hash, field="tool_plan_hash")
        normalized_child_authority = tuple(
            sorted(_port_strings(child_authority, "child_authority"))
        )
        normalized_child_tools = tuple(
            sorted(_port_strings(child_tools, "child_tools"))
        )
        deadline = _port_time(wall_clock_deadline, "wall_clock_deadline")
        require_sha256_digest(spec_hash, field="spec_hash")
        timestamp = _port_time(now, "now", default_now=True)
        if deadline <= timestamp:
            raise ValidationError("wall_clock_deadline must follow recorded_at")
        assert context.run_id is not None
        assert context.authority_revision is not None
        # The typed DTO is the single canonical validator for the decimal
        # budget, deadline, authority and exact spec hash.
        candidate = SubagentExecutionSpecRecord(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            run_id=context.run_id,
            actor_id=context.actor_id,
            invocation_id=invocation_id,
            parent_execution_id=parent_execution_id,
            provider=provider,
            model=model,
            reasoning_effort=reasoning_effort,
            authority_snapshot_id=authority_snapshot_id,
            environment_id=environment_id,
            budget_reservation_id=budget_reservation_id,
            max_output_tokens=max_output_tokens,
            tool_plan_hash=tool_plan_hash,
            child_authority=normalized_child_authority,
            child_tools=normalized_child_tools,
            cost_budget=cost_budget,
            wall_clock_deadline=deadline,
            spec_hash=spec_hash,
            execution_epoch=context.execution_epoch,
            fencing_generation=context.fencing_generation,
            authority_revision=context.authority_revision,
            revision_set_id=revision_set_id,
            recorded_at=timestamp,
        )
        with self.transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            scope = _runtime_scope_parameters(context, revision_set_id)
            reservation_row = cursor.execute(
                f"SELECT {_SUBAGENT_RESERVATION_COLUMNS} "
                "FROM subagent_budget_reservation_bindings "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND reservation_id=? "
                "AND operation_invocation_id=? FOR KEY SHARE",
                (*scope, budget_reservation_id, invocation_id),
            ).fetchone()
            if reservation_row is None:
                raise ConflictError(
                    "subagent execution spec has no exact durable reservation",
                    code="SUBAGENT_RESERVATION_NOT_FOUND",
                )
            reservation = _subagent_reservation_record(reservation_row)
            authority_receipt = self._lock_authority_capability_receipt(
                cursor,
                context,
                revision_set_id=revision_set_id,
                operation_invocation_id=invocation_id,
            )
            reservation_exact = (
                reservation.state is SubagentBudgetReservationState.RESERVED
                and reservation.parent_execution_id == parent_execution_id
                and reservation.environment_id == environment_id
                and hmac.compare_digest(
                    reservation.authority_snapshot_id,
                    authority_snapshot_id,
                )
                and reservation.provider == provider
                and reservation.model == model
                and reservation.reasoning_effort == reasoning_effort
                and hmac.compare_digest(reservation.tool_plan_hash, tool_plan_hash)
                and max_output_tokens <= reservation.max_output_tokens
                and Decimal(candidate.cost_budget)
                <= Decimal(reservation.max_cost_budget)
                and deadline <= reservation.wall_clock_deadline
                and set(normalized_child_authority).issubset(
                    reservation.child_authority
                )
                and set(normalized_child_tools).issubset(reservation.child_tools)
                and hmac.compare_digest(
                    reservation.authority_envelope_digest,
                    authority_receipt.host_envelope.envelope_digest,
                )
                and authority_receipt.environment_id == environment_id
                and hmac.compare_digest(
                    authority_receipt.authority_snapshot_id,
                    authority_snapshot_id,
                )
            )
            if not reservation_exact:
                raise ConflictError(
                    "subagent execution spec exceeds its exact durable reservation",
                    code="SUBAGENT_RESERVATION_CONFLICT",
                )
            plan = cursor.execute(
                "SELECT plan_hash,state,authority_snapshot_id "
                "FROM step_execution_plans "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND plan_hash=? FOR KEY SHARE",
                (*scope, tool_plan_hash),
            ).fetchone()
            attachments = cursor.execute(
                "SELECT owner_authority_ref,state FROM environment_attachments "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND environment_id=? AND state='ACTIVE' "
                "ORDER BY server_id FOR KEY SHARE",
                (*scope, environment_id),
            ).fetchall()
            if (
                plan is None
                or str(plan["state"]) != StepPlanState.ACTIVE.value
                or not hmac.compare_digest(
                    str(plan["authority_snapshot_id"]), authority_snapshot_id
                )
                or len(attachments) != 1
                or not hmac.compare_digest(
                    str(attachments[0]["owner_authority_ref"]),
                    authority_snapshot_id,
                )
            ):
                raise ConflictError(
                    "subagent execution spec requires its active plan and environment",
                    code="SUBAGENT_PARENT_NOT_ACTIVE",
                )
            identity_rows = cursor.execute(
                f"SELECT {_SUBAGENT_SPEC_COLUMNS} FROM subagent_execution_specs "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND "
                "(invocation_id=? OR budget_reservation_id=?) FOR UPDATE",
                (
                    *scope,
                    invocation_id,
                    budget_reservation_id,
                ),
            ).fetchall()
            if len(identity_rows) > 1:
                raise ConflictError(
                    "subagent invocation and reservation resolve to different records",
                    code="SUBAGENT_SPEC_CONFLICT",
                )
            if identity_rows:
                replay = _subagent_spec_record(identity_rows[0])
                if not (
                    replay.run_id == context.run_id
                    and replay.actor_id == context.actor_id
                    and replay.invocation_id == invocation_id
                    and replay.parent_execution_id == parent_execution_id
                    and replay.provider == provider
                    and replay.model == model
                    and replay.reasoning_effort == reasoning_effort
                    and replay.authority_snapshot_id == authority_snapshot_id
                    and replay.environment_id == environment_id
                    and replay.budget_reservation_id == budget_reservation_id
                    and replay.max_output_tokens == max_output_tokens
                    and replay.tool_plan_hash == tool_plan_hash
                    and replay.child_authority == normalized_child_authority
                    and replay.child_tools == normalized_child_tools
                    and replay.cost_budget == candidate.cost_budget
                    and replay.wall_clock_deadline == deadline
                    and hmac.compare_digest(replay.spec_hash, spec_hash)
                ):
                    raise ConflictError(
                        "subagent execution spec replay or reservation reuse diverges",
                        code="SUBAGENT_SPEC_CONFLICT",
                    )
                return replay
            try:
                inserted = cursor.execute(
                    "INSERT INTO subagent_execution_specs("
                    f"{_SUBAGENT_SPEC_COLUMNS}) VALUES ("
                    "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT DO NOTHING",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        context.actor_id,
                        invocation_id,
                        parent_execution_id,
                        provider,
                        model,
                        reasoning_effort,
                        authority_snapshot_id,
                        environment_id,
                        budget_reservation_id,
                        max_output_tokens,
                        tool_plan_hash,
                        canonical_json(list(normalized_child_authority)),
                        canonical_json(list(normalized_child_tools)),
                        candidate.cost_budget,
                        _iso(deadline),
                        spec_hash,
                        context.execution_epoch,
                        context.fencing_generation,
                        context.authority_revision,
                        revision_set_id,
                        _iso(timestamp),
                        SubagentExecutionSpecState.RESERVED.value,
                        None,
                        None,
                        _iso(timestamp),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "subagent invocation or budget reservation conflicts",
                    code="SUBAGENT_SPEC_CONFLICT",
                ) from exc
            if inserted.rowcount != 1:
                raise ConflictError(
                    "subagent invocation or reservation was concurrently claimed",
                    code="SUBAGENT_SPEC_CONFLICT",
                )
            row = cursor.execute(
                f"SELECT {_SUBAGENT_SPEC_COLUMNS} FROM subagent_execution_specs "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? FOR UPDATE",
                (*scope, invocation_id),
            ).fetchone()
            if row is None:
                raise IntegrityError(
                    "subagent execution spec disappeared after persistence",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _subagent_spec_record(row)
            self._append_runtime_assurance_outbox(
                cursor,
                context,
                revision_set_id=revision_set_id,
                event_type="SUBAGENT_EXECUTION_SPEC_RECORDED",
                subject_id=invocation_id,
                payload={
                    "invocation_id": invocation_id,
                    "parent_execution_id": parent_execution_id,
                    "environment_id": environment_id,
                    "budget_reservation_id": budget_reservation_id,
                    "max_output_tokens": max_output_tokens,
                    "provider": provider,
                    "model": model,
                    "reasoning_effort": reasoning_effort,
                    "tool_plan_hash": tool_plan_hash,
                    "child_authority": normalized_child_authority,
                    "child_tools": normalized_child_tools,
                    "cost_budget": candidate.cost_budget,
                    "wall_clock_deadline": deadline,
                    "spec_hash": spec_hash,
                },
            )
            return record

    def consume_subagent_execution_spec(
        self,
        context: SecurityContext,
        *,
        revision_set_id: str,
        invocation_id: str,
        budget_reservation_id: str,
        consumer_execution_id: str,
        now: datetime | None = None,
    ) -> SubagentExecutionSpecRecord:
        """Consume an exact reservation once before starting the child execution."""

        _port_context(context, revision_set_id)
        invocation_id = _port_text(invocation_id, "invocation_id", maximum=512)
        self._require_active_invocation_operation(invocation_id)
        budget_reservation_id = _port_text(
            budget_reservation_id,
            "budget_reservation_id",
            maximum=512,
        )
        consumer_execution_id = _port_text(
            consumer_execution_id,
            "consumer_execution_id",
            maximum=512,
        )
        timestamp = _port_time(now, "now", default_now=True)
        scope = _runtime_scope_parameters(context, revision_set_id)
        parameters = (*scope, invocation_id, budget_reservation_id)
        with self._authority_transaction(context) as cursor:
            self._assert_runtime_assurance_scope(cursor, context, revision_set_id)
            reservation_row = cursor.execute(
                f"SELECT {_SUBAGENT_RESERVATION_COLUMNS} "
                "FROM subagent_budget_reservation_bindings "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND reservation_id=? "
                "AND operation_invocation_id=? FOR KEY SHARE",
                (*scope, budget_reservation_id, invocation_id),
            ).fetchone()
            if reservation_row is None:
                raise NotFoundError(
                    "subagent budget reservation was not found",
                    code="SUBAGENT_RESERVATION_NOT_FOUND",
                )
            reservation = _subagent_reservation_record(reservation_row)
            authority_receipt = self._lock_authority_capability_receipt(
                cursor,
                context,
                revision_set_id=revision_set_id,
                operation_invocation_id=invocation_id,
            )
            if not hmac.compare_digest(
                reservation.authority_envelope_digest,
                authority_receipt.host_envelope.envelope_digest,
            ):
                raise ConflictError(
                    "subagent reservation authority envelope diverges",
                    code="SUBAGENT_RESERVATION_CONFLICT",
                )
            row = cursor.execute(
                f"SELECT {_SUBAGENT_SPEC_COLUMNS} FROM subagent_execution_specs "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? "
                "AND budget_reservation_id=? FOR KEY SHARE",
                parameters,
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "subagent execution spec reservation was not found",
                    code="SUBAGENT_SPEC_NOT_FOUND",
                )
            current = _subagent_spec_record(row)
            if (
                reservation.state is SubagentBudgetReservationState.RESERVED
                and current.state is SubagentExecutionSpecState.RESERVED
                and timestamp >= current.wall_clock_deadline
            ):
                raise ConflictError(
                    "subagent execution spec deadline has expired",
                    code="SUBAGENT_DEADLINE_EXPIRED",
                )
            if reservation.state is SubagentBudgetReservationState.CONSUMED:
                if (
                    reservation_row["consumer_execution_id"]
                    != consumer_execution_id
                    or current.state is not SubagentExecutionSpecState.CONSUMED
                    or current.consumer_execution_id != consumer_execution_id
                    or reservation_row["consume_event_id"] is None
                    or reservation_row["consume_payload_sha256"] is None
                    or reservation.consumed_at is None
                ):
                    raise ConflictError(
                        "subagent reservation replay diverges from its first consumer; "
                        "another execution is not allowed",
                        code="SUBAGENT_SPEC_CONFLICT",
                    )
                consume_timestamp = reservation.consumed_at
                event_id = str(reservation_row["consume_event_id"])
                persisted_payload_sha256 = str(
                    reservation_row["consume_payload_sha256"]
                )
            else:
                consume_timestamp = timestamp
                event_id = f"evt-{uuid.uuid4()}"
                persisted_payload_sha256 = None
            payload = {
                "run_id": context.run_id,
                "execution_epoch": context.execution_epoch,
                "fencing_generation": context.fencing_generation,
                "authority_revision": context.authority_revision,
                "revision_set_id": revision_set_id,
                "detail": {
                    "invocation_id": invocation_id,
                    "budget_reservation_id": budget_reservation_id,
                    "consumer_execution_id": consumer_execution_id,
                    "spec_hash": current.spec_hash,
                    "max_output_tokens": current.max_output_tokens,
                    "cost_budget": current.cost_budget,
                    "authority_envelope_digest": (
                        reservation.authority_envelope_digest
                    ),
                },
            }
            payload_json = canonical_json(payload)
            payload_sha256 = digest_bytes(
                payload_json.encode("utf-8"),
                domain="event-payload",
            )
            if (
                persisted_payload_sha256 is not None
                and not hmac.compare_digest(
                    persisted_payload_sha256,
                    payload_sha256,
                )
            ):
                raise IntegrityError(
                    "subagent consume replay payload digest drifted",
                    code="DELTA_STORAGE_DRIFT",
                )
            helper = cursor.execute(
                "SELECT replayed FROM consume_subagent_reservation_and_spec("
                "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    context.run_id,
                    context.execution_epoch,
                    context.fencing_generation,
                    context.authority_revision,
                    revision_set_id,
                    invocation_id,
                    budget_reservation_id,
                    consumer_execution_id,
                    current.spec_hash,
                    reservation.authority_envelope_digest,
                    _iso(consume_timestamp),
                    event_id,
                    payload_json,
                    payload_sha256,
                ),
            ).fetchone()
            if helper is None or not isinstance(helper.get("replayed"), bool):
                raise IntegrityError(
                    "subagent atomic consume helper returned an invalid result",
                    code="DELTA_STORAGE_DRIFT",
                )
            updated = cursor.execute(
                f"SELECT {_SUBAGENT_SPEC_COLUMNS} FROM subagent_execution_specs "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND invocation_id=? "
                "AND budget_reservation_id=?",
                parameters,
            ).fetchone()
            if updated is None:
                raise IntegrityError(
                    "subagent execution spec disappeared after consumption",
                    code="DELTA_STORAGE_DRIFT",
                )
            record = _subagent_spec_record(updated)
            if not (
                record.state is SubagentExecutionSpecState.CONSUMED
                and record.consumer_execution_id == consumer_execution_id
            ):
                raise IntegrityError(
                    "subagent execution spec consumption did not persist",
                    code="DELTA_STORAGE_DRIFT",
                )
            consumed_reservation = cursor.execute(
                f"SELECT {_SUBAGENT_RESERVATION_COLUMNS} "
                "FROM subagent_budget_reservation_bindings "
                f"WHERE {_RUNTIME_SCOPE_SQL} AND reservation_id=? "
                "AND operation_invocation_id=?",
                (*scope, budget_reservation_id, invocation_id),
            ).fetchone()
            if (
                consumed_reservation is None
                or _subagent_reservation_record(consumed_reservation).state
                is not SubagentBudgetReservationState.CONSUMED
            ):
                raise IntegrityError(
                    "subagent reservation did not atomically consume with its spec",
                    code="DELTA_STORAGE_DRIFT",
                )
            return record
