"""PostgreSQL 17 session, migration and disaster-recovery integration.

The module imports psycopg lazily and accepts injected connection/command
factories so local tests never need credentials or a running database.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .errors import AuthorizationError, ContractError, StaleStateError
from .models import bytes_digest, digest, relative_path, require_sha256_digest, require_string, utc_now

MIGRATION_PATTERN = re.compile(r"^V(?P<version>[0-9]{3})__(?P<name>[a-z0-9_]+)\.sql$")


class PgResult(Protocol):
    def fetchall(self) -> Sequence[Sequence[Any]]: ...

    def fetchone(self) -> Sequence[Any] | None: ...


class PgConnection(Protocol):
    def execute(self, query: str, params: Sequence[Any] | None = None) -> PgResult: ...

    def transaction(self) -> Any: ...

    def close(self) -> None: ...


ConnectFactory = Callable[[], PgConnection]


class PostgresSessionFactory:
    """Create short PostgreSQL sessions with transaction-local tenant scope."""

    def __init__(self, *, service_name: str | None = None, connect: ConnectFactory | None = None) -> None:
        if connect is None and not service_name:
            raise ContractError("POSTGRES_CONFIG_REQUIRED", "service_name or a connection factory is required")
        self.service_name = service_name
        self._connect = connect

    def connect(self) -> PgConnection:
        if self._connect is not None:
            return self._connect()
        try:
            import psycopg  # type: ignore[import-not-found]
            from psycopg.rows import dict_row  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ContractError(
                "POSTGRES_DRIVER_UNAVAILABLE",
                "install the package with the postgres extra to use PostgreSQL",
            ) from exc
        return psycopg.connect(f"service={self.service_name}", row_factory=dict_row)

    @contextmanager
    def tenant_transaction(self, *, tenant_id: str, account_id: str) -> Iterator[PgConnection]:
        tenant = require_string(tenant_id, "tenant_id")
        account = require_string(account_id, "account_id")
        connection = self.connect()
        try:
            with connection.transaction():
                connection.execute("select set_config('search_path', 'pg_catalog,public', true)")
                connection.execute("select set_config('row_security', 'on', true)")
                connection.execute("select set_config('app.tenant_id', %s, true)", (tenant,))
                connection.execute("select set_config('app.account_id', %s, true)", (account,))
                observed = connection.execute(
                    "select current_setting('app.tenant_id', true) as tenant_setting, "
                    "current_setting('app.account_id', true) as account_setting"
                ).fetchone()
                if isinstance(observed, Mapping):
                    observed_identity = (observed.get("tenant_setting"), observed.get("account_setting"))
                else:
                    observed_identity = tuple(observed[:2]) if observed is not None else ()
                if observed_identity != (tenant, account):
                    raise AuthorizationError("POSTGRES_TENANT_SCOPE_FAILED", "transaction-local identity was not bound")
                yield connection
        finally:
            connection.close()


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str
    sql: str


class PostgresMigrationRunner:
    """Apply exact ordered migrations under an advisory transaction lock."""

    def __init__(self, sessions: PostgresSessionFactory, migration_root: str) -> None:
        self.sessions = sessions
        self.migration_root = Path(migration_root).resolve()

    def inventory(self) -> tuple[Migration, ...]:
        if not self.migration_root.is_dir():
            raise ContractError("MIGRATION_ROOT_INVALID", "migration root is unavailable")
        rows: list[Migration] = []
        for path in sorted(self.migration_root.glob("V*.sql")):
            match = MIGRATION_PATTERN.fullmatch(path.name)
            if match is None:
                raise ContractError("MIGRATION_NAME_INVALID", f"invalid migration filename: {path.name}")
            raw = path.read_bytes()
            rows.append(
                Migration(
                    version=int(match.group("version")),
                    name=match.group("name"),
                    path=path,
                    checksum=bytes_digest(raw),
                    sql=raw.decode("utf-8"),
                )
            )
        versions = [row.version for row in rows]
        if not rows or versions != list(range(1, len(rows) + 1)):
            raise ContractError("MIGRATION_SEQUENCE_INVALID", "migration versions must be contiguous from V001")
        return tuple(rows)

    def apply(self, *, operator_id: str, authorization_receipt: str) -> dict[str, Any]:
        require_string(operator_id, "operator_id")
        require_sha256_digest(authorization_receipt, "authorization_receipt")
        migrations = self.inventory()
        connection = self.sessions.connect()
        applied: list[int] = []
        try:
            with connection.transaction():
                connection.execute("select set_config('search_path', 'pg_catalog,public', true)")
                connection.execute("select pg_advisory_xact_lock(hashtext('elmos-autonomy-migrations'))")
                connection.execute(
                    "create table if not exists autonomy_schema_migrations ("
                    "version integer primary key, name text not null, checksum text not null, "
                    "operator_id text not null, authorization_receipt text not null, applied_at timestamptz not null default now())"
                )
                connection.execute("revoke all on autonomy_schema_migrations from public")
                existing_rows = connection.execute(
                    "select version, checksum from autonomy_schema_migrations order by version"
                ).fetchall()
                existing = {int(row[0]): str(row[1]) for row in existing_rows}
                known_versions = {migration.version for migration in migrations}
                if not set(existing).issubset(known_versions) or sorted(existing) != list(range(1, len(existing) + 1)):
                    raise StaleStateError("MIGRATION_HISTORY_DIVERGED", "database migration history is not a known prefix")
                for migration in migrations:
                    prior = existing.get(migration.version)
                    if prior is not None and prior != migration.checksum:
                        raise StaleStateError(
                            "MIGRATION_CHECKSUM_DRIFT",
                            f"applied migration V{migration.version:03d} differs from repository bytes",
                        )
                    if prior is not None:
                        continue
                    connection.execute(migration.sql)
                    connection.execute(
                        "insert into autonomy_schema_migrations(version,name,checksum,operator_id,authorization_receipt) "
                        "values (%s,%s,%s,%s,%s)",
                        (
                            migration.version,
                            migration.name,
                            migration.checksum,
                            operator_id,
                            authorization_receipt,
                        ),
                    )
                    applied.append(migration.version)
        finally:
            connection.close()
        return {
            "status": "APPLIED" if applied else "CURRENT",
            "applied_versions": applied,
            "inventory_digest": digest(
                [{"version": row.version, "name": row.name, "checksum": row.checksum} for row in migrations]
            ),
            "authorization_receipt": authorization_receipt,
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }


class PgCommandRunner(Protocol):
    evidence_class: str

    def run(self, argv: Sequence[str], *, environment: Mapping[str, str], timeout_seconds: int) -> Mapping[str, Any]: ...


class SubprocessPgCommandRunner:
    evidence_class = "EXTERNAL_EXECUTED"

    def run(self, argv: Sequence[str], *, environment: Mapping[str, str], timeout_seconds: int) -> Mapping[str, Any]:
        import subprocess

        completed = subprocess.run(
            list(argv), check=False, capture_output=True, text=True, timeout=timeout_seconds, env=dict(environment)
        )
        return {
            "returncode": completed.returncode,
            "stdout_hash": bytes_digest(completed.stdout.encode()),
            "stderr_hash": bytes_digest(completed.stderr.encode()),
            "argv_digest": digest(list(argv)),
        }


class PostgresDisasterRecovery:
    """Authorized pg_dump/pg_restore workflow using credential-free service refs."""

    def __init__(self, *, allowed_backup_root: str, runner: PgCommandRunner | None = None) -> None:
        self.allowed_backup_root = Path(allowed_backup_root).resolve()
        self.runner = runner or SubprocessPgCommandRunner()

    def _backup_path(self, path: str) -> Path:
        relative = relative_path(path, "backup_path")
        target = (self.allowed_backup_root / relative).resolve()
        if not target.is_relative_to(self.allowed_backup_root):
            raise AuthorizationError("BACKUP_SCOPE_DENIED", "backup path escapes approved root")
        return target

    @staticmethod
    def _file_digest(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        return "sha256:" + hasher.hexdigest()

    @staticmethod
    def _environment(service_name: str) -> dict[str, str]:
        service = require_string(service_name, "service_name")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", service):
            raise ContractError("POSTGRES_SERVICE_INVALID", "service name contains unsafe characters")
        return {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C", "PGSERVICE": service}

    def backup(self, *, service_name: str, backup_path: str, authorization_receipt: str) -> dict[str, Any]:
        require_sha256_digest(authorization_receipt, "authorization_receipt")
        target = self._backup_path(backup_path)
        if target.exists():
            raise StaleStateError("BACKUP_EXISTS", "backup target already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        response = self.runner.run(
            ["pg_dump", "--format=custom", "--no-owner", "--no-acl", f"--file={target}"],
            environment=self._environment(service_name),
            timeout_seconds=3600,
        )
        if int(response.get("returncode", 1)) != 0 or not target.is_file():
            target.unlink(missing_ok=True)
            raise ContractError("POSTGRES_BACKUP_FAILED", "pg_dump failed or produced no archive")
        return {
            "status": "BACKUP_CREATED",
            "backup_path": str(target),
            "backup_hash": self._file_digest(target),
            "size_bytes": target.stat().st_size,
            "authorization_receipt": authorization_receipt,
            "command_evidence": dict(response),
            "created_at": utc_now(),
            "certification": "NOT_CERTIFIED",
        }

    def restore(
        self, *, service_name: str, backup_path: str, authorization_receipt: str,
        disposable_target: bool, replay_validator: Callable[[], Mapping[str, Any]],
    ) -> dict[str, Any]:
        if not disposable_target:
            raise AuthorizationError("RESTORE_TARGET_DENIED", "restore is restricted to an authorized disposable target")
        require_sha256_digest(authorization_receipt, "authorization_receipt")
        source = self._backup_path(backup_path)
        if not source.is_file():
            raise ContractError("BACKUP_NOT_FOUND", "backup archive is unavailable")
        before_hash = self._file_digest(source)
        response = self.runner.run(
            ["pg_restore", "--clean", "--if-exists", "--no-owner", "--no-acl", str(source)],
            environment=self._environment(service_name),
            timeout_seconds=3600,
        )
        if int(response.get("returncode", 1)) != 0 or self._file_digest(source) != before_hash:
            raise ContractError("POSTGRES_RESTORE_FAILED", "restore failed or backup bytes changed")
        replay = dict(replay_validator())
        replay_passed = replay.get("status") == "PASS" and bool(replay.get("raw_evidence"))
        return {
            "status": "RESTORED_AND_REPLAYED" if replay_passed else "RESTORE_REPLAY_BLOCKED",
            "backup_hash": before_hash,
            "authorization_receipt": authorization_receipt,
            "command_evidence": dict(response),
            "replay": replay,
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
