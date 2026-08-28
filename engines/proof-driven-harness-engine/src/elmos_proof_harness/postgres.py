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
import hmac
import json
import os
import sqlite3
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from .contracts import SecurityContext
from .errors import AuthorizationError, ConflictError, HarnessError, IntegrityError, StoreError, ValidationError
from .storage import (
    POSTGRES_MIGRATION_SOURCE_DIGEST,
    POSTGRES_SCHEMA_VERSION,
    StorageReadiness,
    StorageStatus,
)
from .store import SQLiteStore, _iso


_RUNTIME_TABLE_COUNT = 22
_DRIVER_MAJOR_MINOR = (3, 2)


class _PostgresRow(Mapping[str, Any]):
    """Small sqlite-row-compatible wrapper around a psycopg dict row."""

    def __init__(self, values: Mapping[str, Any]) -> None:
        self._values = values

    def __getitem__(self, key: str) -> Any:
        value = self._values[key]
        # SQLite returns JSON columns as text.  Normalizing here lets the common
        # Store implementation perform one canonical decoding path.
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
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
        raise AuthorizationError("PostgreSQL RLS or privilege check denied the operation", details=details) from exc
    if sqlstate == "55000":
        raise IntegrityError("append-only PostgreSQL relation rejected mutation", code="IMMUTABLE_RELATION", details=details) from exc
    raise StoreError("PostgreSQL operation failed", code="POSTGRES_OPERATION_FAILED", details=details) from exc


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
        health_context: SecurityContext | None = None,
        connect_timeout_seconds: int = 5,
    ) -> None:
        if not isinstance(dsn, str) or not dsn.strip():
            raise StoreError(
                "PostgreSQL DSN is required in production",
                code="POSTGRES_NOT_CONFIGURED",
            )
        if connect_timeout_seconds < 1 or connect_timeout_seconds > 60:
            raise ValidationError("PostgreSQL connect timeout is outside the safe range")
        availability = postgres_driver_readiness()
        if not availability.ready:
            raise StoreError(availability.reason, code=availability.status.value)
        driver = importlib.import_module("psycopg")
        rows = importlib.import_module("psycopg.rows")
        self._driver = driver
        self._dict_row = rows.dict_row
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds
        self._health_context = health_context or SecurityContext(
            tenant_id="__proof_harness_health__",
            project_id="__proof_harness_health__",
            actor_id="__proof_harness_service__",
        )
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
        return cls(dsn)

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

    @contextmanager
    def transaction(self, context: SecurityContext | None = None) -> Iterator[_PostgresCursor]:
        if context is None:
            raise AuthorizationError(
                "trusted tenant/project/actor context is required for every PostgreSQL transaction",
                code="TRUSTED_CONTEXT_REQUIRED",
            )
        connection = self._connect()
        cursor = connection.cursor()
        adapted = _PostgresCursor(cursor)
        try:
            # SET TRANSACTION must be first.  set_config(..., true) is LOCAL to
            # this transaction and is parameterized to prevent SQL injection.
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true), "
                "set_config('app.project_id', %s, true), "
                "set_config('app.actor_id', %s, true)",
                (context.tenant_id, context.project_id, context.actor_id),
            )
            cursor.execute("SET LOCAL search_path = proof_harness_runtime, proof_harness, pg_catalog")
            yield adapted
            connection.commit()
        except HarnessError:
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            _raise_mapped_database_error(exc)
        finally:
            cursor.close()
            connection.close()

    @property
    def schema_version(self) -> int:
        with self.transaction(self._health_context) as cursor:
            row = cursor.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").fetchone()
        return int(row["version"]) if row is not None else 0

    def readiness(self) -> StorageReadiness:
        try:
            with self.transaction(self._health_context) as cursor:
                role = cursor.execute(
                    "SELECT r.rolsuper, r.rolbypassrls, current_setting('server_version_num') AS server_version_num, current_setting('server_version') AS server_version FROM pg_roles r WHERE r.rolname=current_user"
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
                    "SELECT COUNT(*) AS count FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname IN ('proof_harness_runtime','proof_harness') AND pg_get_userbyid(c.relowner)=current_user"
                ).fetchone()
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
        if role is None or bool(role["rolsuper"]) or bool(role["rolbypassrls"]):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="application role must be NOSUPERUSER and NOBYPASSRLS",
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
                reason="ordinary application role must not own proof-harness relations",
                backend="postgresql",
                schema_version=schema_version,
                server_version=server_version,
            )
        return StorageReadiness(
            status=StorageStatus.READY,
            reason="PostgreSQL 17 schema, role and forced RLS are ready",
            backend="postgresql",
            schema_version=schema_version,
            server_version=server_version,
        )

    def register_scope(self, context: SecurityContext, *, now: datetime | None = None) -> None:
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
