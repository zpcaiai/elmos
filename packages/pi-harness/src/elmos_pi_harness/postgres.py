"""PostgreSQL 16+ durable-store adapter with transaction-local tenant RLS.

The adapter reuses the kernel's domain transitions while translating only its
fixed repository-owned SQL identifiers. It is not a general SQL converter.
Every public tenant operation establishes ``elmos.tenant_id`` with
``set_config(..., true)`` inside the same transaction as the query.
"""

from __future__ import annotations

import contextlib
import json
import re
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Self

from .canonical import digest_bytes, require_nonempty, require_uuid
from .models import HarnessError
from .persistence import DurableStore


@dataclass(frozen=True)
class PostgresConfig:
    dsn: str
    required_server_major: int = 16
    minimum_pool_size: int = 2
    maximum_pool_size: int = 20
    statement_timeout_ms: int = 30_000
    lock_timeout_ms: int = 5_000
    application_name: str = "elmos-pi-harness"

    def __post_init__(self) -> None:
        require_nonempty(self.dsn, "dsn", 8192)
        if not self.dsn.startswith(("postgresql://", "postgres://", "service=")):
            raise ValueError("PostgreSQL DSN must be a URI or libpq service reference")
        if self.required_server_major < 16:
            raise ValueError("production profile requires PostgreSQL 16 or newer")
        if not 1 <= self.minimum_pool_size <= self.maximum_pool_size <= 200:
            raise ValueError("invalid PostgreSQL pool size")
        if not 100 <= self.statement_timeout_ms <= 3_600_000:
            raise ValueError("invalid PostgreSQL statement timeout")
        if not 100 <= self.lock_timeout_ms <= self.statement_timeout_ms:
            raise ValueError("invalid PostgreSQL lock timeout")
        require_nonempty(self.application_name, "application_name", 64)


@dataclass(frozen=True)
class MigrationRecord:
    version: str
    path: Path
    sha256: str
    sql: str


class PostgresMigrator:
    ADVISORY_LOCK_KEY = 5_104_510_016

    def __init__(
        self,
        config: PostgresConfig,
        migration_root: Path,
        *,
        connection_factory: Any | None = None,
    ) -> None:
        if (
            not migration_root.is_absolute()
            or not migration_root.is_dir()
            or migration_root.is_symlink()
        ):
            raise ValueError("migration_root must be an absolute regular directory")
        self.config = config
        self.migration_root = migration_root
        self.connection_factory = connection_factory

    def discover(self) -> tuple[MigrationRecord, ...]:
        records: list[MigrationRecord] = []
        for path in sorted(self.migration_root.glob("[0-9][0-9][0-9]_*.sql")):
            if path.is_symlink() or not path.is_file():
                raise HarnessError("migration path is unsafe")
            raw = path.read_bytes()
            records.append(
                MigrationRecord(
                    path.name.split("_", 1)[0],
                    path,
                    digest_bytes(raw),
                    raw.decode("utf-8"),
                )
            )
        if not records or len({item.version for item in records}) != len(records):
            raise HarnessError(
                "PostgreSQL migration versions are missing or duplicated"
            )
        return tuple(records)

    def apply(self) -> dict[str, Any]:
        records = self.discover()
        factory = self.connection_factory or self._default_connection
        applied: list[str] = []
        already_applied: list[str] = []
        with factory() as connection:
            connection.execute("SELECT pg_advisory_lock(%s)", (self.ADVISORY_LOCK_KEY,))
            try:
                server_version = int(
                    connection.execute("SHOW server_version_num").fetchone()[0]
                )
                if server_version // 10_000 < self.config.required_server_major:
                    raise HarnessError(
                        "PostgreSQL server is older than the pinned production profile"
                    )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS public.pi_schema_migration(version text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL, application_name text NOT NULL)"
                )
                connection.commit()
                for record in records:
                    with connection.transaction():
                        connection.execute(
                            "SELECT set_config('search_path','public,pg_catalog',true)"
                        )
                        existing = connection.execute(
                            "SELECT sha256 FROM public.pi_schema_migration WHERE version=%s FOR UPDATE",
                            (record.version,),
                        ).fetchone()
                        if existing:
                            existing_digest = (
                                existing[0]
                                if not isinstance(existing, dict)
                                else existing["sha256"]
                            )
                            if existing_digest != record.sha256:
                                raise HarnessError(
                                    f"applied migration digest drift: {record.path.name}"
                                )
                            already_applied.append(record.version)
                            continue
                        connection.execute(record.sql)
                        connection.execute(
                            "INSERT INTO public.pi_schema_migration(version,sha256,applied_at,application_name) VALUES(%s,%s,now(),%s)",
                            (
                                record.version,
                                record.sha256,
                                self.config.application_name,
                            ),
                        )
                        applied.append(record.version)
            finally:
                connection.execute(
                    "SELECT pg_advisory_unlock(%s)", (self.ADVISORY_LOCK_KEY,)
                )
                connection.commit()
        return {
            "status": "APPLIED",
            "applied": applied,
            "already_applied": already_applied,
            "migration_digests": {item.version: item.sha256 for item in records},
        }

    @contextlib.contextmanager
    def _default_connection(self) -> Iterator[Any]:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - optional production extra
            raise RuntimeError(
                "psycopg is required; install elmos-pi-harness[postgres]"
            ) from exc
        with psycopg.connect(
            self.config.dsn,
            autocommit=False,
            application_name=self.config.application_name,
        ) as connection:
            yield connection


TABLE_NAMES = {
    "tenant": "pi_tenant",
    "project": "pi_project",
    "task": "pi_task",
    "task_event": "pi_task_event",
    "idempotency_key": "pi_idempotency_key",
    "execution_environment": "pi_execution_environment",
    "authority_snapshot": "pi_authority_snapshot",
    "executor_connection": "pi_executor_connection",
    "workspace_lease": "pi_workspace_lease",
    "checkpoint": "pi_checkpoint",
    "tool_call": "pi_tool_call",
    "effect_journal": "pi_effect_journal",
    "artifact": "pi_artifact",
    "campaign": "pi_campaign",
    "benchmark_run": "pi_benchmark_run",
}

COLUMN_NAMES = {
    "payload_json": "payload",
    "config_json": "config",
    "sandbox_overrides_json": "sandbox_overrides",
    "allowed_capabilities_json": "allowed_capabilities",
    "denied_capabilities_json": "denied_capabilities",
    "metadata_json": "metadata",
}


def _translate_kernel_sql(statement: str) -> str:
    value = statement
    for source, target in sorted(
        TABLE_NAMES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        for keyword in ("FROM", "INTO", "UPDATE", "JOIN"):
            value = re.sub(
                rf"\b{keyword}\s+{re.escape(source)}\b",
                f"{keyword} {target}",
                value,
                flags=re.IGNORECASE,
            )
    for source, target in COLUMN_NAMES.items():
        value = re.sub(rf"\b{re.escape(source)}\b", target, value)
    value = value.replace("?", "%s")
    return value


def _normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return (
            value.astimezone(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


class _CursorProxy:
    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor

    def fetchone(self) -> Any:
        row = self.cursor.fetchone()
        return self._row(row)

    def fetchall(self) -> list[Any]:
        return [self._row(row) for row in self.cursor.fetchall()]

    @staticmethod
    def _row(row: Any) -> Any:
        if row is None:
            return None
        if isinstance(row, dict):
            result = {key: _normalize_value(value) for key, value in row.items()}
            for source, target in COLUMN_NAMES.items():
                if target in result and source not in result:
                    result[source] = result[target]
            return result
        if hasattr(row, "keys"):
            result = {key: _normalize_value(row[key]) for key in row}
            for source, target in COLUMN_NAMES.items():
                if target in result and source not in result:
                    result[source] = result[target]
            return result
        return tuple(_normalize_value(value) for value in row)


class _ConnectionProxy:
    def __init__(self, owner: PostgresStore) -> None:
        self.owner = owner

    def execute(self, statement: str, parameters: tuple[Any, ...] = ()) -> _CursorProxy:
        connection = self.owner._active_connection()
        return _CursorProxy(
            connection.execute(_translate_kernel_sql(statement), parameters)
        )


class PostgresStore(DurableStore):
    """Full DurableStore interface backed by PostgreSQL and RLS."""

    def __init__(
        self,
        config: PostgresConfig,
        artifact_root: str | Path,
        *,
        pool: Any | None = None,
        artifact_backend: Any | None = None,
    ) -> None:
        self.config = config
        root = Path(artifact_root)
        if not root.is_absolute() or root.is_symlink():
            raise ValueError("artifact_root must be an absolute non-symlink path")
        root.mkdir(parents=True, exist_ok=True)
        self._artifact_root = root.resolve()
        self._artifact_backend = artifact_backend
        self.path = config.dsn
        self._local = threading.local()
        self._lock = threading.RLock()
        if pool is None:
            try:
                from psycopg.rows import dict_row
                from psycopg_pool import ConnectionPool
            except ImportError as exc:  # pragma: no cover - optional production extra
                raise RuntimeError(
                    "psycopg and psycopg_pool are required; install elmos-pi-harness[postgres]"
                ) from exc
            pool = ConnectionPool(
                conninfo=config.dsn,
                min_size=config.minimum_pool_size,
                max_size=config.maximum_pool_size,
                kwargs={
                    "autocommit": False,
                    "application_name": config.application_name,
                    "row_factory": dict_row,
                },
                open=True,
            )
        self._pool = pool
        self._connection = _ConnectionProxy(self)
        self.health()

    @contextlib.contextmanager
    def tenant_scope(self, tenant_id: str) -> Iterator[None]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        previous = getattr(self._local, "tenant_id", None)
        if previous is not None and previous != tenant_id:
            raise HarnessError("nested PostgreSQL tenant scope cannot change tenant")
        self._local.tenant_id = tenant_id
        try:
            yield
        finally:
            self._local.tenant_id = previous

    @contextlib.contextmanager
    def _write(self) -> Iterator[_ConnectionProxy]:
        with self._transaction(read_only=False):
            yield self._connection

    @contextlib.contextmanager
    def _read(self) -> Iterator[_ConnectionProxy]:
        with self._transaction(read_only=True):
            yield self._connection

    @contextlib.contextmanager
    def _transaction(self, *, read_only: bool) -> Iterator[None]:
        active = getattr(self._local, "connection", None)
        if active is not None:
            yield
            return
        tenant_id = getattr(self._local, "tenant_id", None)
        if tenant_id is None:
            raise HarnessError("PostgreSQL tenant scope is required")
        with self._pool.connection() as connection:
            self._local.connection = connection
            try:
                with connection.transaction():
                    connection.execute(
                        "SELECT set_config('elmos.tenant_id', %s, true)", (tenant_id,)
                    )
                    connection.execute(
                        "SELECT set_config('statement_timeout', %s, true)",
                        (str(self.config.statement_timeout_ms),),
                    )
                    connection.execute(
                        "SELECT set_config('lock_timeout', %s, true)",
                        (str(self.config.lock_timeout_ms),),
                    )
                    connection.execute(
                        "SELECT set_config('search_path', 'public,pg_catalog', true)"
                    )
                    if read_only:
                        connection.execute("SET TRANSACTION READ ONLY")
                    yield
            finally:
                self._local.connection = None

    def _active_connection(self) -> Any:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            raise HarnessError(
                "PostgreSQL query attempted outside a managed transaction"
            )
        return connection

    @staticmethod
    def _decode(value: Any) -> Any:
        if value is None or isinstance(value, (dict, list, int, float, bool)):
            return value
        return json.loads(value)

    def health(self) -> dict[str, Any]:
        with self._pool.connection() as connection:
            version_row = connection.execute("SHOW server_version_num").fetchone()
            server_version = int(
                version_row[0]
                if not isinstance(version_row, dict)
                else next(iter(version_row.values()))
            )
            recovery_row = connection.execute("SELECT pg_is_in_recovery()").fetchone()
            in_recovery = bool(
                recovery_row[0]
                if not isinstance(recovery_row, dict)
                else next(iter(recovery_row.values()))
            )
            role_row = connection.execute(
                "SELECT rolsuper,rolbypassrls FROM pg_catalog.pg_roles WHERE rolname=current_user"
            ).fetchone()
            role_values = (
                list(role_row.values())
                if isinstance(role_row, dict)
                else list(role_row)
            )
            if bool(role_values[0]) or bool(role_values[1]):
                raise HarnessError(
                    "PostgreSQL service role must not be superuser or BYPASSRLS"
                )
            owner_row = connection.execute(
                "SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_roles r ON r.oid=c.relowner WHERE r.rolname=current_user AND c.relname LIKE 'pi_%' AND c.relkind='r'"
            ).fetchone()
            owned_tables = int(
                next(iter(owner_row.values()))
                if isinstance(owner_row, dict)
                else owner_row[0]
            )
            if owned_tables:
                raise HarnessError(
                    "PostgreSQL service role must not own PI Harness tables"
                )
            schema_row = connection.execute(
                "SELECT to_regclass('public.pi_task'),to_regclass('public.pi_tool_call'),to_regclass('public.pi_artifact')"
            ).fetchone()
            schema_values = (
                list(schema_row.values())
                if isinstance(schema_row, dict)
                else list(schema_row)
            )
            if any(value is None for value in schema_values):
                raise HarnessError("PostgreSQL schema migrations are incomplete")
            if server_version // 10_000 < self.config.required_server_major:
                raise HarnessError("PostgreSQL server is outside the pinned profile")
            return {
                "status": "ready",
                "backend": "postgresql",
                "server_version_num": server_version,
                "in_recovery": in_recovery,
                "rls_tenant_binding": "transaction_local",
                "service_role_bypassrls": False,
                "service_role_owns_tables": False,
            }

    def close(self) -> None:
        self._pool.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, _exc_type: object, _exc_value: object, _traceback: object
    ) -> None:
        self.close()


TENANT_METHODS = (
    "create_task",
    "get_task",
    "transition_task",
    "set_required_verifications",
    "record_verification",
    "events",
    "branch_task",
    "create_environment",
    "get_environment",
    "create_authority_snapshot",
    "get_authority_snapshot",
    "register_executor",
    "assert_active_executor",
    "acquire_workspace",
    "heartbeat_workspace",
    "takeover_workspace",
    "record_checkpoint",
    "begin_tool_call",
    "mark_tool_executing",
    "complete_tool_call",
    "begin_effect",
    "resolve_effect",
    "put_artifact",
    "artifacts",
    "create_campaign",
    "record_benchmark_run",
)


def _install_tenant_method(method_name: str) -> None:
    base_method = getattr(DurableStore, method_name)

    def wrapped(self: PostgresStore, tenant_id: str, *args: Any, **kwargs: Any) -> Any:
        with self.tenant_scope(tenant_id):
            return base_method(self, tenant_id, *args, **kwargs)

    wrapped.__name__ = method_name
    wrapped.__qualname__ = f"PostgresStore.{method_name}"
    setattr(PostgresStore, method_name, wrapped)


for _method_name in TENANT_METHODS:
    _install_tenant_method(_method_name)
