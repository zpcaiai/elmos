"""Independent PostgreSQL scheduler claim client.

The scheduler DSN is never shared with the HTTP application or certifier.  It
has no direct table privileges; its only authority is EXECUTE on the audited
``proof_harness.claim_next_control_plane_job`` SECURITY DEFINER function.  The
function atomically claims one row with ``FOR UPDATE SKIP LOCKED``, rotates a
lease generation/token, sets the selected tenant scope, and returns exactly one
complete authenticated receipt binding.
"""

from __future__ import annotations

import importlib
import json
import os
import threading
from datetime import datetime
from typing import Mapping

from .contracts import SecurityContext
from .errors import AuthorizationError, StoreError, ValidationError
from .postgres import postgres_driver_readiness
from .storage import (
    POSTGRES_MIGRATION_SOURCE_DIGEST,
    POSTGRES_SCHEMA_VERSION,
    ControlPlaneJobClaim,
    StorageReadiness,
    StorageStatus,
)


class PostgresScheduler:
    """Least-privileged global admission/recovery job claimer."""

    def __init__(self, dsn: str, *, connect_timeout_seconds: int = 5) -> None:
        if not isinstance(dsn, str) or not dsn.strip():
            raise StoreError("scheduler PostgreSQL DSN is required", code=StorageStatus.NOT_CONFIGURED.value)
        if connect_timeout_seconds < 1 or connect_timeout_seconds > 60:
            raise ValidationError("scheduler connect timeout is outside the safe range")
        driver_state = postgres_driver_readiness()
        if not driver_state.ready:
            raise StoreError(driver_state.reason, code=driver_state.status.value)
        self._driver = importlib.import_module("psycopg")
        self._dict_row = importlib.import_module("psycopg.rows").dict_row
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds
        self._lock = threading.RLock()
        self._closed = False

    @classmethod
    def from_environment(
        cls,
        *,
        variable: str = "ELMOS_SCHEDULER_POSTGRES_DSN",
        environment: Mapping[str, str] | None = None,
    ) -> "PostgresScheduler":
        values = os.environ if environment is None else environment
        dsn = values.get(variable, "")
        if not dsn.strip():
            raise StoreError(
                f"{variable} is required for the production scheduler",
                code=StorageStatus.NOT_CONFIGURED.value,
            )
        return cls(dsn)

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def _connect(self):  # type: ignore[no-untyped-def]
        with self._lock:
            if self._closed:
                raise StoreError("PostgreSQL scheduler is closed", code="STORE_CLOSED")
        try:
            return self._driver.connect(
                self._dsn,
                autocommit=False,
                connect_timeout=self._connect_timeout_seconds,
                row_factory=self._dict_row,
            )
        except Exception as exc:
            raise StoreError("scheduler PostgreSQL connection failed", code="POSTGRES_UNAVAILABLE") from exc

    def readiness(self) -> StorageReadiness:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_user AS role_name,r.rolsuper,r.rolbypassrls,"
                    "current_setting('server_version_num') AS server_version_num,"
                    "current_setting('server_version') AS server_version,"
                    "pg_has_role(session_user,'proof_harness_scheduler_authority','MEMBER') AS authority,"
                    "has_function_privilege(current_user,"
                    "'proof_harness.claim_next_control_plane_job(text,integer)','EXECUTE') AS can_execute "
                    "FROM pg_roles r WHERE r.rolname=current_user"
                )
                role = cursor.fetchone()
                cursor.execute(
                    "SELECT content_sha256 FROM proof_harness_runtime.migration_digest_ledger "
                    "WHERE version=%s AND migration_name='V001__proof_harness_core.sql'",
                    (POSTGRES_SCHEMA_VERSION,),
                )
                migration = cursor.fetchone()
                cursor.execute(
                    "SELECT bool_or(has_table_privilege(current_user,'proof_harness_runtime.'||name,"
                    "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')) AS direct_access "
                    "FROM unnest(ARRAY['scheduler_jobs','scheduler_claim_events','control_plane_receipts',"
                    "'runs','evidence','certification_assessments']::text[]) AS name"
                )
                privileges = cursor.fetchone()
                connection.rollback()
        except Exception:
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="scheduler PostgreSQL readiness probe failed",
                backend="postgresql-scheduler",
            )
        if role is None or bool(role["rolsuper"]) or bool(role["rolbypassrls"]):
            reason = "scheduler role must be NOSUPERUSER and NOBYPASSRLS"
        elif not (170000 <= int(role["server_version_num"]) < 180000):
            reason = "scheduler requires PostgreSQL 17.x"
        elif not bool(role["authority"]) or not bool(role["can_execute"]):
            reason = "scheduler role lacks the exact function authority"
        elif privileges is None or bool(privileges["direct_access"]):
            reason = "scheduler role must not have direct proof-harness table access"
        elif migration is None or str(migration["content_sha256"]) != POSTGRES_MIGRATION_SOURCE_DIGEST:
            reason = "scheduler migration digest ledger is missing or drifted"
        else:
            return StorageReadiness(
                status=StorageStatus.READY,
                reason="scheduler role and atomic claim function are ready",
                backend="postgresql-scheduler",
                schema_version=POSTGRES_SCHEMA_VERSION,
                server_version=str(role["server_version"]),
            )
        return StorageReadiness(
            status=StorageStatus.NOT_READY,
            reason=reason,
            backend="postgresql-scheduler",
            schema_version=POSTGRES_SCHEMA_VERSION,
            server_version=None if role is None else str(role["server_version"]),
        )

    def claim_next_control_plane_job(
        self,
        *,
        worker_instance_id: str,
        ttl_seconds: int = 60,
        now: datetime | None = None,
    ) -> ControlPlaneJobClaim | None:
        if now is not None:
            raise ValidationError("PostgreSQL scheduler leases use the authoritative database clock")
        if not isinstance(worker_instance_id, str) or not worker_instance_id.strip():
            raise ValidationError("worker_instance_id is required")
        if ttl_seconds < 5 or ttl_seconds > 900:
            raise ValidationError("scheduler lease ttl is outside the safe range")
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM proof_harness.claim_next_control_plane_job(%s,%s)",
                    (worker_instance_id, ttl_seconds),
                )
                row = cursor.fetchone()
                connection.commit()
        except Exception as exc:
            sqlstate = str(getattr(exc, "sqlstate", "") or "")
            if sqlstate == "42501":
                raise AuthorizationError("scheduler claim authority was denied") from exc
            raise StoreError(
                "scheduler claim failed closed",
                code="SCHEDULER_CLAIM_FAILED",
                details={"sqlstate": sqlstate} if sqlstate else {},
            ) from exc
        if row is None:
            return None
        request = row["request_json"]
        if isinstance(request, str):
            request = json.loads(request)
        if not isinstance(request, dict):
            raise StoreError("scheduler function returned an invalid request", code="SCHEDULER_CLAIM_INVALID")
        return ControlPlaneJobClaim(
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            actor_id=str(row["actor_id"]),
            operation=str(row["operation"]),
            idempotency_key=str(row["idempotency_key"]),
            request_sha256=str(row["request_sha256"]),
            run_id=str(row["run_id"]),
            request=request,
            scheduler_role=str(row["scheduler_role"]),
            worker_instance_id=str(row["worker_instance_id"]),
            lease_token=str(row["lease_token"]),
            lease_generation=int(row["lease_generation"]),
            lease_expires_at=row["lease_expires_at"],
        )

    @staticmethod
    def scoped_context(claim: ControlPlaneJobClaim) -> SecurityContext:
        """Build a resource scope from a DB-authenticated scheduler claim."""

        return SecurityContext(
            tenant_id=claim.tenant_id,
            project_id=claim.project_id,
            actor_id=claim.actor_id,
            run_id=claim.run_id,
        )
