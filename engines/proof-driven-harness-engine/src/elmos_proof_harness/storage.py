"""Storage contracts shared by local and production control planes.

``ControlPlaneStore`` is deliberately resource-scoped: every operation accepts
an authenticated :class:`SecurityContext`.  A production implementation must
derive that context from trusted identity middleware and set database session
scope before touching tenant data.  Request payload fields are never authority.

SQLite is the dependency-free, single-process local-engineering backend.
PostgreSQL 17 with forced tenant/project RLS is the production backend.  The
protocol keeps workflow and evidence services independent of either driver.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping, Protocol, runtime_checkable

from .contracts import (
    CheckpointRecord,
    EvidenceRecord,
    LeaseGrant,
    MetricPoint,
    SecurityContext,
)


MAX_INLINE_EVIDENCE_BYTES = 16 * 1024 * 1024
MAX_INLINE_CHECKPOINT_BYTES = 16 * 1024 * 1024
MAX_INLINE_CERTIFICATION_BYTES = 4 * 1024 * 1024
POSTGRES_SCHEMA_VERSION = 1
# Detached digest of the complete V001 SQL file.  Unlike a digest embedded in
# the migration itself this is not self-referential; the migration runner
# records the same value in ``migration_digest_ledger`` after applying V001.
# This value is finalized whenever V001 changes.
# Detached digest of the complete migration bytes, using the same domain as
# tools/apply_postgres_migration.py.  It is intentionally computed after the
# SQL source is finalized; embedding it in the migration would be recursive.
POSTGRES_MIGRATION_SOURCE_DIGEST = (
    "sha256:bdddb1ff1a962df931df57e4d8d428e08c232b4ac88e5189bf8c2ccde34e388f"
)
# V304 deliberately uses a separate runtime-assurance ledger so applying the
# optional v3.1 delta does not change the core V001 schema version observed by
# existing stores.  The applicator requires this exact name, version, digest,
# and the V001 prerequisite before it can mutate a database.
POSTGRES_DELTA_SCHEMA_VERSION = 304
POSTGRES_DELTA_MIGRATION_NAME = "V304__harness_runtime_assurance_delta.sql"
POSTGRES_DELTA_MIGRATION_SOURCE_DIGEST = (
    "sha256:e80c79db5ee6105bb551b487f1dd07c81bcb953f1f5b8adbb6ed176402f7a09c"
)


class StorageStatus(StrEnum):
    READY = "READY"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_READY = "NOT_READY"


@dataclass(frozen=True, slots=True)
class StorageReadiness:
    status: StorageStatus
    reason: str
    backend: str
    schema_version: int | None = None
    server_version: str | None = None

    @property
    def ready(self) -> bool:
        return self.status is StorageStatus.READY


@dataclass(frozen=True, slots=True)
class ControlPlaneReceipt:
    actor_id: str
    operation: str
    idempotency_key: str
    request_sha256: str
    run_id: str
    request: Mapping[str, Any]
    response: Mapping[str, Any] | None
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class ControlPlaneJobClaim:
    """One globally claimed admission job returned only to a scheduler.

    PostgreSQL creates this through a least-privileged SECURITY DEFINER
    function, never through tenant-wide table access.  ``lease_token`` is
    returned once while only its domain-separated digest is persisted.
    """

    tenant_id: str
    project_id: str
    actor_id: str
    operation: str
    idempotency_key: str
    request_sha256: str
    run_id: str
    request: Mapping[str, Any]
    scheduler_role: str
    worker_instance_id: str
    lease_token: str
    lease_generation: int
    lease_expires_at: datetime


@runtime_checkable
class SchedulerStore(Protocol):
    """Independent global scheduler boundary; ordinary app stores omit it."""

    def readiness(self) -> StorageReadiness: ...

    def close(self) -> None: ...

    def claim_next_control_plane_job(
        self,
        *,
        worker_instance_id: str,
        ttl_seconds: int = 60,
        now: datetime | None = None,
    ) -> ControlPlaneJobClaim | None: ...


@runtime_checkable
class ControlPlaneStore(Protocol):
    """Exact durable interface consumed by workflow/evidence orchestration.

    Implementations must atomically bind mutations to tenant, project and
    actor, preserve optimistic sequence and fencing checks, and commit audit
    plus outbox records in the same transaction as the aggregate mutation.
    """

    @property
    def schema_version(self) -> int: ...

    def readiness(self) -> StorageReadiness: ...

    def close(self) -> None: ...

    def register_scope(
        self, context: SecurityContext, *, now: datetime | None = None
    ) -> None: ...

    def assert_scope(self, context: SecurityContext) -> None: ...

    def create_run(
        self,
        context: SecurityContext,
        *,
        run_id: str,
        revision_set_id: str,
        initial_state: str = "CREATED",
        deadline_at: datetime | None = None,
        idempotency_key: str | None = None,
        now: datetime | None = None,
    ) -> Any: ...

    def get_run(self, context: SecurityContext, run_id: str | None = None) -> Any: ...

    def acquire_lease(
        self,
        context: SecurityContext,
        *,
        owner_id: str,
        ttl_seconds: int,
        expected_sequence: int,
        now: datetime | None = None,
    ) -> LeaseGrant: ...

    def transition_run(
        self,
        context: SecurityContext,
        *,
        target_state: str,
        expected_sequence: int,
        lease_token: str,
        now: datetime | None = None,
    ) -> Any: ...

    def append_checkpoint(
        self,
        context: SecurityContext,
        payload: bytes,
        *,
        expected_sequence: int,
        lease_token: str,
        checkpoint_id: str | None = None,
        now: datetime | None = None,
    ) -> CheckpointRecord: ...

    def get_checkpoint(
        self, context: SecurityContext, checkpoint_id: str
    ) -> tuple[CheckpointRecord, bytes]: ...

    def recover_run(
        self,
        context: SecurityContext,
        *,
        owner_id: str,
        expected_sequence: int,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> tuple[Any, LeaseGrant, CheckpointRecord, bytes]: ...

    def append_evidence(
        self,
        context: SecurityContext,
        record: EvidenceRecord,
        content: bytes,
        *,
        idempotency_key: str | None = None,
    ) -> EvidenceRecord: ...

    def get_evidence(
        self, context: SecurityContext, evidence_id: str
    ) -> tuple[EvidenceRecord, bytes]: ...

    def revoke_evidence(
        self,
        context: SecurityContext,
        evidence_id: str,
        *,
        reason: str,
        revocation_id: str | None = None,
        now: datetime | None = None,
    ) -> str: ...

    def evidence_revoked(self, context: SecurityContext, evidence_id: str) -> bool: ...

    def unsettled_side_effect_count(
        self, context: SecurityContext, *, run_id: str | None = None
    ) -> int: ...

    def start_external_effect(
        self,
        context: SecurityContext,
        *,
        effect_id: str,
        provider: str,
        operation: str,
        idempotency_key: str,
        request: Mapping[str, Any],
        reconciliation_strategy: str,
        lease_token: str,
        now: datetime | None = None,
    ) -> Any: ...

    def reconcile_external_effect(
        self,
        context: SecurityContext,
        *,
        effect_id: str,
        target_state: str,
        expected_version: int,
        detail: Mapping[str, Any],
        lease_token: str,
        external_reference: str | None = None,
        now: datetime | None = None,
    ) -> Any: ...

    def record_outbox_delivery(
        self,
        context: SecurityContext,
        *,
        event_id: str,
        destination: str,
        state: str,
        detail: bytes | None = None,
    ) -> str: ...

    def record_metric(self, context: SecurityContext, point: MetricPoint) -> str: ...

    def metric_totals(self, context: SecurityContext) -> dict[str, float]: ...

    def claim_control_plane_receipt(
        self,
        context: SecurityContext,
        *,
        operation: str,
        idempotency_key: str,
        request_sha256: str,
        run_id: str,
        request: Mapping[str, Any],
        now: datetime | None = None,
    ) -> tuple[bool, ControlPlaneReceipt]: ...

    def complete_control_plane_receipt(
        self,
        context: SecurityContext,
        *,
        operation: str,
        idempotency_key: str,
        request_sha256: str,
        response: Mapping[str, Any],
        now: datetime | None = None,
    ) -> ControlPlaneReceipt: ...

    def get_control_plane_receipt(
        self,
        context: SecurityContext,
        *,
        operation: str,
        idempotency_key: str,
        request_sha256: str,
    ) -> ControlPlaneReceipt | None: ...

    def list_pending_control_plane_receipts(
        self,
        context: SecurityContext,
        *,
        limit: int = 100,
    ) -> tuple[ControlPlaneReceipt, ...]: ...

    def abandon_control_plane_receipt(
        self,
        context: SecurityContext,
        *,
        operation: str,
        idempotency_key: str,
        request_sha256: str,
    ) -> bool: ...
