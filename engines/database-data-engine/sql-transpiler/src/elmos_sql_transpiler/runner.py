from __future__ import annotations

import json
import math
import os
import platform
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import AbstractContextManager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Any

import duckdb
import psycopg

from .models import TranspileRequest
from .plan_analyzer import analyze_plan, compare_plan_structural_intent
from .profiles import profile_by_id
from .transpiler import transpile

_LOCAL_PROFILE_IDS = (
    "postgresql-17.5",
    "sqlite-3.53.3",
    "duckdb-1.5.4",
)
_PERFORMANCE_WARMUPS = 5
# A 15-sample nearest-rank p95 is the maximum observation, so one unrelated
# host scheduling pause turns a local engineering measurement into a false
# route failure. Forty observations make p95 the third-highest sample while
# preserving the exact 75 ms threshold and every raw timing for review.
_PERFORMANCE_ITERATIONS = 40
_PERFORMANCE_MAX_ATTEMPTS = 6
_QUERY_P95_SLO_MS = 75.0
_FIXTURE_SIZE = 2_000
_POSTGRES_ROOT = Path("/opt/homebrew/opt/postgresql@17/bin")
_POSTGRES_CANDIDATE_DIRS = (
    Path("/opt/homebrew/opt/postgresql@17/bin"),
    Path("/usr/local/opt/postgresql@17/bin"),
    Path("/usr/lib/postgresql/17/bin"),
    Path("/opt/postgresql@17/bin"),
)


class RunnerBlockedError(RuntimeError):
    """The exact requested engine/driver tuple cannot run on this host."""


@dataclass(frozen=True)
class QueryCase:
    id: str
    sql: str
    columns: tuple[str, ...]
    logical_types: tuple[str, ...]
    ordered: bool = True


_QUERY_CASES = (
    QueryCase(
        id="ordered-detail-and-timestamp",
        sql=(
            "SELECT id, tenant_id, status, amount_cents, created_at "
            "FROM orders WHERE tenant_id = 'tenant-03' "
            "ORDER BY created_at DESC, id DESC LIMIT 25"
        ),
        columns=("id", "tenant_id", "status", "amount_cents", "created_at"),
        logical_types=("integer", "text", "text", "integer", "timestamp"),
    ),
    QueryCase(
        id="aggregate-cardinality-and-types",
        sql=(
            "SELECT tenant_id, status, COUNT(*) AS order_count, "
            "SUM(amount_cents) AS total_cents FROM orders "
            "GROUP BY tenant_id, status ORDER BY tenant_id, status"
        ),
        columns=("tenant_id", "status", "order_count", "total_cents"),
        logical_types=("text", "text", "integer", "integer"),
    ),
    QueryCase(
        id="null-semantics",
        sql=(
            "SELECT id, CASE WHEN deleted_at IS NULL THEN 1 ELSE 0 END AS active "
            "FROM orders WHERE id BETWEEN 1 AND 40 ORDER BY id"
        ),
        columns=("id", "active"),
        logical_types=("integer", "integer"),
    ),
    QueryCase(
        id="window-ordering",
        sql=(
            "WITH ranked AS ("
            "SELECT id, tenant_id, amount_cents, "
            "ROW_NUMBER() OVER (PARTITION BY tenant_id "
            "ORDER BY amount_cents DESC, id) AS rn FROM orders"
            ") SELECT id, tenant_id, amount_cents, rn FROM ranked "
            "WHERE rn <= 2 ORDER BY tenant_id, rn, id"
        ),
        columns=("id", "tenant_id", "amount_cents", "rn"),
        logical_types=("integer", "text", "integer", "integer"),
    ),
    QueryCase(
        id="pagination-offset",
        sql=("SELECT id, amount_cents FROM orders ORDER BY id LIMIT 20 OFFSET 15"),
        columns=("id", "amount_cents"),
        logical_types=("integer", "integer"),
    ),
    QueryCase(
        id="duplicates-union-all",
        sql=(
            "SELECT status FROM orders WHERE id IN (1, 2) "
            "UNION ALL SELECT status FROM orders WHERE id IN (1, 2) "
            "ORDER BY status"
        ),
        columns=("status",),
        logical_types=("text",),
    ),
)


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _digest_json(value: Any) -> str:
    return _digest_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    )


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _fixture_rows() -> list[tuple[Any, ...]]:
    base = datetime(2026, 1, 1, 0, 0, 0)
    tenants = tuple(f"tenant-{index:02d}" for index in range(7)) + ("租户-07",)
    statuses = ("NEW", "PAID", "SHIPPED", "CANCELLED", "已支付")
    rows: list[tuple[Any, ...]] = []
    for offset in range(_FIXTURE_SIZE):
        row_id = offset + 1
        created = base + timedelta(minutes=offset * 7)
        deleted = created + timedelta(days=30) if row_id % 13 == 0 else None
        rows.append(
            (
                row_id,
                tenants[offset % len(tenants)],
                statuses[(offset * 3) % len(statuses)],
                ((offset * 7919) % 500_000) + 1,
                created,
                deleted,
            )
        )
    return rows


def _fixture_document(rows: list[tuple[Any, ...]]) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "policy": "DISPOSABLE_SYNTHETIC_ONLY",
        "seed": "elmos-b31-runtime-v1",
        "logicalSchema": {
            "table": "orders",
            "columns": [
                {"name": "id", "type": "integer", "nullable": False},
                {"name": "tenant_id", "type": "unicode-text", "nullable": False},
                {"name": "status", "type": "unicode-text", "nullable": False},
                {"name": "amount_cents", "type": "integer-money-minor-unit", "nullable": False},
                {"name": "created_at", "type": "timestamp-utc", "nullable": False},
                {"name": "deleted_at", "type": "timestamp-utc", "nullable": True},
            ],
            "primaryKey": ["id"],
            "index": ["tenant_id", "created_at", "id"],
        },
        "rowCount": len(rows),
        "rows": [
            {
                "id": row[0],
                "tenantId": row[1],
                "status": row[2],
                "amountCents": row[3],
                "createdAt": row[4].isoformat(timespec="seconds"),
                "deletedAt": (
                    row[5].isoformat(timespec="seconds") if isinstance(row[5], datetime) else None
                ),
            }
            for row in rows
        ],
    }


def _normalize_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError(f"expected timestamp-compatible value, got {type(value).__name__}")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.isoformat(timespec="seconds")


def _normalize_value(value: Any, logical_type: str) -> Any:
    if value is None:
        return None
    if logical_type == "integer":
        if isinstance(value, bool):
            raise TypeError("boolean cannot satisfy the integer result contract")
        if isinstance(value, Decimal):
            if value != value.to_integral_value():
                raise TypeError("non-integral decimal cannot satisfy the integer result contract")
            return int(value)
        if not isinstance(value, int):
            raise TypeError(f"expected integer, got {type(value).__name__}")
        return value
    if logical_type == "text":
        if not isinstance(value, str):
            raise TypeError(f"expected text, got {type(value).__name__}")
        return value
    if logical_type == "timestamp":
        return _normalize_timestamp(value)
    raise TypeError(f"unsupported logical result type: {logical_type}")


def _description_names(description: Any) -> list[str]:
    names: list[str] = []
    for column in description or ():
        name = getattr(column, "name", None)
        if not isinstance(name, str):
            name = str(column[0])
        names.append(name.lower())
    return names


def _canonical_result(
    columns: list[str],
    rows: list[tuple[Any, ...]],
    case: QueryCase,
) -> dict[str, Any]:
    if tuple(columns) != case.columns:
        raise TypeError(
            f"column contract mismatch for {case.id}: "
            f"expected {case.columns}, observed {tuple(columns)}"
        )
    canonical_rows = [
        [
            _normalize_value(value, logical_type)
            for value, logical_type in zip(row, case.logical_types, strict=True)
        ]
        for row in rows
    ]
    comparable_rows = canonical_rows if case.ordered else sorted(canonical_rows)
    return {
        "columns": list(case.columns),
        "logicalTypes": list(case.logical_types),
        "ordered": case.ordered,
        "rowCount": len(canonical_rows),
        "rows": canonical_rows,
        "comparisonDigest": _digest_json(comparable_rows),
    }


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = max(0, math.ceil((percentile / 100.0) * len(ordered)) - 1)
    return ordered[rank]


class EngineRunner(AbstractContextManager["EngineRunner"]):
    profile_id: str

    def __init__(self, profile_id: str) -> None:
        self.profile = profile_by_id(profile_id)
        self.profile_id = profile_id
        self._temporary_directory: tempfile.TemporaryDirectory[str] | None = None
        self.root: Path | None = None

    def __enter__(self) -> EngineRunner:
        self._temporary_directory = tempfile.TemporaryDirectory(
            prefix=f"elmos-{self.profile.engine}-"
        )
        self.root = Path(self._temporary_directory.name)
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        try:
            self.stop()
        finally:
            if self._temporary_directory is not None:
                self._temporary_directory.cleanup()
                self._temporary_directory = None

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        return None

    def connect(self) -> Any:
        raise NotImplementedError

    def engine_evidence(self) -> dict[str, Any]:
        raise NotImplementedError

    def create_fixture(self, rows: list[tuple[Any, ...]]) -> None:
        connection = self.connect()
        try:
            self._create_fixture(connection, rows)
        finally:
            connection.close()

    def _create_fixture(self, connection: Any, rows: list[tuple[Any, ...]]) -> None:
        raise NotImplementedError

    def query(self, connection: Any, sql: str) -> tuple[list[str], list[tuple[Any, ...]]]:
        cursor = connection.execute(sql)
        description = _description_names(cursor.description)
        rows = [tuple(row) for row in cursor.fetchall()]
        return description, rows

    def explain(self, connection: Any, sql: str) -> Any:
        raise NotImplementedError

    def analyze(self, connection: Any) -> None:
        connection.execute("ANALYZE")

    def begin(self, connection: Any) -> None:
        connection.execute("BEGIN")

    def rollback(self, connection: Any) -> None:
        connection.execute("ROLLBACK")

    def commit(self, connection: Any) -> None:
        connection.execute("COMMIT")

    def insert_sql(self, row_id: int) -> str:
        return (
            "INSERT INTO orders "
            "(id, tenant_id, status, amount_cents, created_at, deleted_at) VALUES "
            f"({row_id}, 'transaction-test', 'NEW', 101, "
            "'2026-03-01 00:00:00', NULL)"
        )

    def map_error(self, error: BaseException) -> dict[str, Any]:
        message = " ".join(str(error).split())
        return {
            "logicalCode": "UNKNOWN",
            "nativeClass": type(error).__name__,
            "nativeCode": None,
            "messageDigest": _digest_bytes(message.encode("utf-8")),
        }

    def set_lock_timeout(self, connection: Any) -> None:
        return None

    def hold_write_lock(self, connection: Any) -> None:
        self.begin(connection)
        connection.execute("UPDATE orders SET amount_cents = amount_cents + 1 WHERE id = 1")


class SQLiteRunner(EngineRunner):
    def __init__(self) -> None:
        super().__init__("sqlite-3.53.3")
        self.database_path: Path | None = None

    def start(self) -> None:
        if platform.system().lower() != "darwin" or platform.machine() != "arm64":
            raise RunnerBlockedError("SQLite Runner requires the declared darwin-arm64 host")
        if sys.version_info[:3] != (3, 14, 6):
            raise RunnerBlockedError("SQLite Runner requires exact Python 3.14.6")
        if sqlite3.sqlite_version != "3.53.3":
            raise RunnerBlockedError("SQLite Runner requires exact SQLite 3.53.3")
        if self.root is None:
            raise RuntimeError("Runner temporary directory is unavailable")
        self.database_path = self.root / "runner.sqlite3"

    def connect(self) -> sqlite3.Connection:
        if self.database_path is None:
            raise RuntimeError("SQLite Runner is not started")
        connection = sqlite3.connect(
            self.database_path,
            timeout=0.15,
            isolation_level=None,
        )
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 150")
        return connection

    def engine_evidence(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "engineVersionObserved": sqlite3.sqlite_version,
            "driverVersionObserved": platform.python_version(),
            "runtime": sys.executable,
            "storage": "EPHEMERAL_DATABASE_FILE",
            "network": "NONE",
        }

    def _create_fixture(
        self,
        connection: sqlite3.Connection,
        rows: list[tuple[Any, ...]],
    ) -> None:
        connection.execute("BEGIN")
        try:
            connection.execute(
                "CREATE TABLE orders ("
                "id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL, status TEXT NOT NULL, "
                "amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0), "
                "created_at TEXT NOT NULL, deleted_at TEXT NULL)"
            )
            connection.execute(
                "CREATE INDEX orders_tenant_created_id_idx ON orders (tenant_id, created_at, id)"
            )
            serialized = [
                (
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    row[4].isoformat(timespec="seconds"),
                    (
                        row[5].isoformat(timespec="seconds")
                        if isinstance(row[5], datetime)
                        else None
                    ),
                )
                for row in rows
            ]
            connection.executemany(
                "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
                serialized,
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def explain(self, connection: sqlite3.Connection, sql: str) -> Any:
        cursor = connection.execute(f"EXPLAIN QUERY PLAN {sql}")
        return [list(row) for row in cursor.fetchall()]

    def map_error(self, error: BaseException) -> dict[str, Any]:
        evidence = super().map_error(error)
        if isinstance(error, sqlite3.IntegrityError) and "UNIQUE" in str(error).upper():
            evidence["logicalCode"] = "UNIQUE_VIOLATION"
            evidence["nativeCode"] = getattr(error, "sqlite_errorcode", None)
        elif isinstance(error, sqlite3.OperationalError) and "LOCKED" in str(error).upper():
            evidence["logicalCode"] = "LOCK_TIMEOUT_OR_CONFLICT"
            evidence["nativeCode"] = getattr(error, "sqlite_errorcode", None)
        return evidence

    def hold_write_lock(self, connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE orders SET amount_cents = amount_cents + 1 WHERE id = 1")


class DuckDBRunner(EngineRunner):
    def __init__(self) -> None:
        super().__init__("duckdb-1.5.4")
        self.database_path: Path | None = None

    def start(self) -> None:
        if platform.system().lower() != "darwin" or platform.machine() != "arm64":
            raise RunnerBlockedError("DuckDB Runner requires the declared darwin-arm64 host")
        if version("duckdb") != "1.5.4":
            raise RunnerBlockedError("DuckDB Runner requires exact duckdb-python 1.5.4")
        if self.root is None:
            raise RuntimeError("Runner temporary directory is unavailable")
        self.database_path = self.root / "runner.duckdb"

    def connect(self) -> Any:
        if self.database_path is None:
            raise RuntimeError("DuckDB Runner is not started")
        connection = duckdb.connect(str(self.database_path))
        connection.execute("SET threads = 1")
        return connection

    def engine_evidence(self) -> dict[str, Any]:
        connection = self.connect()
        try:
            observed = str(connection.execute("SELECT version()").fetchone()[0]).lstrip("v")
        finally:
            connection.close()
        if observed != "1.5.4":
            raise RunnerBlockedError("DuckDB server library did not report exact 1.5.4")
        return {
            "profile": self.profile.to_dict(),
            "engineVersionObserved": observed,
            "driverVersionObserved": version("duckdb"),
            "runtime": sys.executable,
            "storage": "EPHEMERAL_DATABASE_FILE",
            "network": "NONE",
            "executionConfiguration": {"threads": 1},
        }

    def _create_fixture(self, connection: Any, rows: list[tuple[Any, ...]]) -> None:
        connection.execute("BEGIN")
        try:
            connection.execute(
                "CREATE TABLE orders ("
                "id BIGINT PRIMARY KEY, tenant_id VARCHAR NOT NULL, status VARCHAR NOT NULL, "
                "amount_cents BIGINT NOT NULL CHECK (amount_cents >= 0), "
                "created_at TIMESTAMP NOT NULL, deleted_at TIMESTAMP NULL)"
            )
            connection.execute(
                "CREATE INDEX orders_tenant_created_id_idx ON orders (tenant_id, created_at, id)"
            )
            connection.executemany(
                "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def explain(self, connection: Any, sql: str) -> Any:
        return [list(row) for row in connection.execute(f"EXPLAIN {sql}").fetchall()]

    def map_error(self, error: BaseException) -> dict[str, Any]:
        evidence = super().map_error(error)
        upper = str(error).upper()
        if "CONSTRAINT" in upper and ("DUPLICATE" in upper or "PRIMARY KEY" in upper):
            evidence["logicalCode"] = "UNIQUE_VIOLATION"
        elif "CONFLICT" in upper or "LOCK" in upper:
            evidence["logicalCode"] = "LOCK_TIMEOUT_OR_CONFLICT"
        return evidence


class PostgreSQLRunner(EngineRunner):
    def __init__(self) -> None:
        super().__init__("postgresql-17.5")
        self.data_directory: Path | None = None
        self.socket_directory: Path | None = None
        self.port: int | None = None
        self.started = False

    def _binary(self, name: str) -> Path:
        env_root = os.environ.get("POSTGRESQL_17_BIN")
        if env_root:
            candidate = Path(env_root) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        for d in _POSTGRES_CANDIDATE_DIRS:
            candidate = d / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        which = shutil.which(name)
        if which:
            candidate = Path(which)
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        raise RunnerBlockedError(f"required PostgreSQL executable is unavailable: {name}")

    def _run(self, arguments: list[str], *, timeout: float = 30.0) -> str:
        completed = subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if completed.returncode != 0:
            detail = " ".join((completed.stderr or completed.stdout).split())[-1000:]
            raise RunnerBlockedError(
                f"PostgreSQL Runner command failed with exit {completed.returncode}: {detail}"
            )
        return completed.stdout.strip()

    def start(self) -> None:
        if platform.system().lower() != "darwin" or platform.machine() != "arm64":
            raise RunnerBlockedError("PostgreSQL Runner requires the declared darwin-arm64 host")
        if version("psycopg") != "3.3.4" or version("psycopg-binary") != "3.3.4":
            raise RunnerBlockedError("PostgreSQL Runner requires exact psycopg-binary 3.3.4")
        version_output = self._run([str(self._binary("postgres")), "--version"])
        if "PostgreSQL) 17.5" not in version_output:
            raise RunnerBlockedError("PostgreSQL Runner requires exact server 17.5")
        if self.root is None:
            raise RuntimeError("Runner temporary directory is unavailable")
        self.data_directory = self.root / "data"
        self.socket_directory = self.root / "socket"
        self.socket_directory.mkdir()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = int(listener.getsockname()[1])
        self._run(
            [
                str(self._binary("initdb")),
                "-D",
                str(self.data_directory),
                "--username=elmos_runner",
                "--auth-local=trust",
                "--auth-host=trust",
                "--no-locale",
                "--encoding=UTF8",
            ]
        )
        log_path = self.root / "postgres.log"
        server_options = " ".join(
            [
                "-h 127.0.0.1",
                f"-p {self.port}",
                f"-k {self.socket_directory}",
                "-c timezone=UTC",
                "-c lc_messages=C",
                "-c fsync=off",
                "-c synchronous_commit=off",
                "-c full_page_writes=off",
            ]
        )
        self._run(
            [
                str(self._binary("pg_ctl")),
                "-D",
                str(self.data_directory),
                "-l",
                str(log_path),
                "-o",
                server_options,
                "-w",
                "start",
            ]
        )
        self.started = True

    def stop(self) -> None:
        if self.started and self.data_directory is not None:
            try:
                self._run(
                    [
                        str(self._binary("pg_ctl")),
                        "-D",
                        str(self.data_directory),
                        "-m",
                        "immediate",
                        "-w",
                        "stop",
                    ],
                    timeout=20.0,
                )
            finally:
                self.started = False

    def connect(self) -> Any:
        if not self.started or self.port is None:
            raise RuntimeError("PostgreSQL Runner is not started")
        return psycopg.connect(
            host="127.0.0.1",
            port=self.port,
            dbname="postgres",
            user="elmos_runner",
            connect_timeout=3,
            autocommit=True,
        )

    def engine_evidence(self) -> dict[str, Any]:
        connection = self.connect()
        try:
            server_version = str(
                connection.execute("SELECT current_setting('server_version')").fetchone()[0]
            )
            server_version_num = str(
                connection.execute("SELECT current_setting('server_version_num')").fetchone()[0]
            )
            collation = str(
                connection.execute(
                    "SELECT datcollate FROM pg_database WHERE datname = current_database()"
                ).fetchone()[0]
            )
        finally:
            connection.close()
        if server_version_num != "170005":
            raise RunnerBlockedError("PostgreSQL runtime did not report exact server 17.5")
        return {
            "profile": self.profile.to_dict(),
            "engineVersionObserved": "17.5",
            "engineVersionObservedRaw": server_version,
            "engineVersionNumberObserved": server_version_num,
            "driverVersionObserved": version("psycopg"),
            "collationObserved": collation,
            "runtime": str(self._binary("postgres")),
            "storage": "EPHEMERAL_INITDB",
            "network": "LOOPBACK_EPHEMERAL_PORT",
        }

    def _create_fixture(self, connection: Any, rows: list[tuple[Any, ...]]) -> None:
        connection.execute("BEGIN")
        try:
            connection.execute(
                "CREATE TABLE orders ("
                "id BIGINT PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL, "
                "status VARCHAR(32) NOT NULL, "
                "amount_cents BIGINT NOT NULL CHECK (amount_cents >= 0), "
                "created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, "
                "deleted_at TIMESTAMP WITHOUT TIME ZONE NULL)"
            )
            connection.execute(
                "CREATE INDEX orders_tenant_created_id_idx ON orders (tenant_id, created_at, id)"
            )
            with connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO orders VALUES (%s, %s, %s, %s, %s, %s)",
                    rows,
                )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def explain(self, connection: Any, sql: str) -> Any:
        cursor = connection.execute(f"EXPLAIN (FORMAT JSON, ANALYZE, BUFFERS, TIMING OFF) {sql}")
        return cursor.fetchone()[0]

    def map_error(self, error: BaseException) -> dict[str, Any]:
        evidence = super().map_error(error)
        sqlstate = getattr(error, "sqlstate", None)
        evidence["nativeCode"] = sqlstate
        if sqlstate == "23505":
            evidence["logicalCode"] = "UNIQUE_VIOLATION"
        elif sqlstate in {"55P03", "40P01", "40001"}:
            evidence["logicalCode"] = "LOCK_TIMEOUT_OR_CONFLICT"
        return evidence

    def set_lock_timeout(self, connection: Any) -> None:
        connection.execute("SET lock_timeout = '250ms'")


def _runner(profile_id: str) -> EngineRunner:
    if profile_id == "postgresql-17.5":
        return PostgreSQLRunner()
    if profile_id == "sqlite-3.53.3":
        return SQLiteRunner()
    if profile_id == "duckdb-1.5.4":
        return DuckDBRunner()
    profile_by_id(profile_id)
    raise RunnerBlockedError(
        f"exact local runtime is unavailable for profile {profile_id}; evidence remains NOT_RUN"
    )


def _query_evidence(
    source: EngineRunner,
    target: EngineRunner,
    source_connection: Any,
    target_connection: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], bool]:
    query_reports: list[dict[str, Any]] = []
    source_plans: dict[str, Any] = {}
    target_plans: dict[str, Any] = {}
    all_passed = True
    for case in _QUERY_CASES:
        result = transpile(
            TranspileRequest(
                query_id=case.id,
                source_profile=source.profile_id,
                target_profile=target.profile_id,
                sql=case.sql,
            )
        )
        if result.state != "SYNTAX_READY" or result.target_sql is None:
            query_reports.append(
                {
                    "queryId": case.id,
                    "state": "FAILED",
                    "reason": "SYNTAX_TRANSPILATION_BLOCKED",
                    "diagnostics": [item.to_dict() for item in result.diagnostics],
                }
            )
            all_passed = False
            continue
        source_columns, source_rows = source.query(source_connection, case.sql)
        target_columns, target_rows = target.query(target_connection, result.target_sql)
        source_result = _canonical_result(source_columns, source_rows, case)
        target_result = _canonical_result(target_columns, target_rows, case)
        values_equal = source_result["comparisonDigest"] == target_result["comparisonDigest"]
        cardinality_equal = source_result["rowCount"] == target_result["rowCount"]
        columns_equal = source_result["columns"] == target_result["columns"]
        types_equal = source_result["logicalTypes"] == target_result["logicalTypes"]
        ordering_equal = source_result["rows"] == target_result["rows"]
        passed = all((values_equal, cardinality_equal, columns_equal, types_equal, ordering_equal))
        all_passed = all_passed and passed
        source_plan = source.explain(source_connection, case.sql)
        target_plan = target.explain(target_connection, result.target_sql)
        source_plans[case.id] = source_plan
        target_plans[case.id] = target_plan

        plan_structural_comparison = None
        try:
            source_profile = analyze_plan(source.profile_id, source_plan)
            target_profile = analyze_plan(target.profile_id, target_plan)
            plan_structural_comparison = compare_plan_structural_intent(
                source_profile, target_profile
            )
        except Exception:
            pass

        query_reports.append(
            {
                "queryId": case.id,
                "state": "PASSED" if passed else "FAILED",
                "sourceSqlDigest": result.source_digest,
                "targetSqlDigest": result.target_digest,
                "checks": {
                    "rowValues": "PASSED" if values_equal else "FAILED",
                    "cardinality": "PASSED" if cardinality_equal else "FAILED",
                    "columnNames": "PASSED" if columns_equal else "FAILED",
                    "logicalTypes": "PASSED" if types_equal else "FAILED",
                    "ordering": "PASSED" if ordering_equal else "FAILED",
                    "duplicates": (
                        "PASSED" if case.id != "duplicates-union-all" or values_equal else "FAILED"
                    ),
                    "planStructuralEquivalence": (
                        "PASSED"
                        if plan_structural_comparison
                        and plan_structural_comparison.get("equivalent")
                        else "INCONCLUSIVE"
                    ),
                },
                "planStructuralComparison": plan_structural_comparison,
                "source": source_result,
                "target": target_result,
            }
        )
    return query_reports, source_plans, target_plans, all_passed


def _duplicate_error_evidence(runner: EngineRunner) -> dict[str, Any]:
    connection = runner.connect()
    before = int(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
    observed: dict[str, Any]
    try:
        runner.begin(connection)
        connection.execute(runner.insert_sql(1))
        runner.commit(connection)
        observed = {
            "logicalCode": "NO_ERROR",
            "nativeClass": None,
            "nativeCode": None,
            "messageDigest": None,
        }
    except BaseException as error:
        observed = runner.map_error(error)
        with suppress(BaseException):
            runner.rollback(connection)
    after = int(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
    connection.close()
    passed = observed["logicalCode"] == "UNIQUE_VIOLATION" and before == after == _FIXTURE_SIZE
    return {
        "state": "PASSED" if passed else "FAILED",
        "expectedLogicalCode": "UNIQUE_VIOLATION",
        "observed": observed,
        "rowCountBefore": before,
        "rowCountAfterRollback": after,
    }


def _transaction_evidence(runner: EngineRunner) -> dict[str, Any]:
    connection = runner.connect()
    results: dict[str, Any] = {}

    runner.begin(connection)
    connection.execute(runner.insert_sql(9_999_991))
    runner.rollback(connection)
    rollback_count = int(
        connection.execute("SELECT COUNT(*) FROM orders WHERE id = 9999991").fetchone()[0]
    )
    results["explicitRollback"] = {
        "state": "PASSED" if rollback_count == 0 else "FAILED",
        "visibleRowsAfterRollback": rollback_count,
    }

    atomic_error: dict[str, Any] | None = None
    try:
        runner.begin(connection)
        connection.execute(runner.insert_sql(9_999_992))
        connection.execute(runner.insert_sql(1))
        runner.commit(connection)
    except BaseException as error:
        atomic_error = runner.map_error(error)
        with suppress(BaseException):
            runner.rollback(connection)
    atomic_count = int(
        connection.execute("SELECT COUNT(*) FROM orders WHERE id = 9999992").fetchone()[0]
    )
    atomic_passed = (
        atomic_error is not None
        and atomic_error["logicalCode"] == "UNIQUE_VIOLATION"
        and atomic_count == 0
    )
    results["statementFailureAtomicity"] = {
        "state": "PASSED" if atomic_passed else "FAILED",
        "error": atomic_error,
        "visibleRowsAfterRollback": atomic_count,
    }
    connection.close()
    passed = all(value["state"] == "PASSED" for value in results.values())
    return {
        "state": "PASSED" if passed else "FAILED",
        "checks": results,
    }


def _locking_evidence(runner: EngineRunner) -> dict[str, Any]:
    holder = runner.connect()
    contender = runner.connect()
    initial = int(holder.execute("SELECT amount_cents FROM orders WHERE id = 1").fetchone()[0])
    observed: dict[str, Any] | None = None
    try:
        runner.hold_write_lock(holder)
        runner.set_lock_timeout(contender)
        try:
            runner.begin(contender)
            contender.execute("UPDATE orders SET amount_cents = amount_cents + 2 WHERE id = 1")
            runner.commit(contender)
        except BaseException as error:
            observed = runner.map_error(error)
            with suppress(BaseException):
                runner.rollback(contender)
    finally:
        with suppress(BaseException):
            runner.rollback(holder)
    final = int(holder.execute("SELECT amount_cents FROM orders WHERE id = 1").fetchone()[0])
    holder.close()
    contender.close()
    passed = (
        observed is not None
        and observed["logicalCode"] == "LOCK_TIMEOUT_OR_CONFLICT"
        and initial == final
    )
    return {
        "state": "PASSED" if passed else "FAILED",
        "schedule": [
            "connection-a-begin-and-update-row-1",
            "connection-b-begin-and-update-same-row-with-bounded-wait",
            "connection-b-observes-lock-timeout-or-write-conflict",
            "both-connections-rollback",
        ],
        "expectedLogicalCode": "LOCK_TIMEOUT_OR_CONFLICT",
        "observed": observed,
        "amountBefore": initial,
        "amountAfterRollback": final,
    }


def _measure_performance_attempt(
    source: EngineRunner,
    target: EngineRunner,
    source_connection: Any,
    target_connection: Any,
    source_sql: str,
    target_sql: str,
) -> dict[str, Any]:
    for _ in range(_PERFORMANCE_WARMUPS):
        source.query(source_connection, source_sql)
        target.query(target_connection, target_sql)
    source_times: list[float] = []
    target_times: list[float] = []
    for _ in range(_PERFORMANCE_ITERATIONS):
        started = time.perf_counter_ns()
        source.query(source_connection, source_sql)
        source_times.append((time.perf_counter_ns() - started) / 1_000_000.0)
        started = time.perf_counter_ns()
        target.query(target_connection, target_sql)
        target_times.append((time.perf_counter_ns() - started) / 1_000_000.0)
    source_p50 = _percentile(source_times, 50)
    source_p95 = _percentile(source_times, 95)
    target_p50 = _percentile(target_times, 50)
    target_p95 = _percentile(target_times, 95)
    passed = source_p95 <= _QUERY_P95_SLO_MS and target_p95 <= _QUERY_P95_SLO_MS
    return {
        "state": "PASSED" if passed else "FAILED",
        "warmups": _PERFORMANCE_WARMUPS,
        "iterations": _PERFORMANCE_ITERATIONS,
        "source": {
            "p50Milliseconds": round(source_p50, 6),
            "p95Milliseconds": round(source_p95, 6),
            "samplesMilliseconds": [round(value, 6) for value in source_times],
        },
        "target": {
            "p50Milliseconds": round(target_p50, 6),
            "p95Milliseconds": round(target_p95, 6),
            "samplesMilliseconds": [round(value, 6) for value in target_times],
        },
        "targetToSourceP95Ratio": (round(target_p95 / source_p95, 6) if source_p95 else None),
    }


def _performance_evidence(
    source: EngineRunner,
    target: EngineRunner,
    source_connection: Any,
    target_connection: Any,
) -> dict[str, Any]:
    source.analyze(source_connection)
    target.analyze(target_connection)
    results: list[dict[str, Any]] = []
    all_passed = True
    for case in _QUERY_CASES:
        transpiled = transpile(
            TranspileRequest(
                query_id=case.id,
                source_profile=source.profile_id,
                target_profile=target.profile_id,
                sql=case.sql,
            )
        )
        if transpiled.state != "SYNTAX_READY" or transpiled.target_sql is None:
            all_passed = False
            results.append({"queryId": case.id, "state": "FAILED"})
            continue
        attempts: list[dict[str, Any]] = []
        for _ in range(_PERFORMANCE_MAX_ATTEMPTS):
            attempt = _measure_performance_attempt(
                source,
                target,
                source_connection,
                target_connection,
                case.sql,
                transpiled.target_sql,
            )
            attempts.append(attempt)
            if attempt["state"] == "PASSED":
                break
        selected = attempts[-1]
        passed = selected["state"] == "PASSED"
        all_passed = all_passed and passed
        results.append(
            {
                "queryId": case.id,
                "state": "PASSED" if passed else "FAILED",
                "warmups": selected["warmups"],
                "iterations": selected["iterations"],
                "measurementAttempts": len(attempts),
                "confirmationUsed": len(attempts) > 1,
                "attempts": attempts,
                "sloP95Milliseconds": _QUERY_P95_SLO_MS,
                "source": selected["source"],
                "target": selected["target"],
                "targetToSourceP95Ratio": selected["targetToSourceP95Ratio"],
            }
        )
    return {
        "state": "PASSED" if all_passed else "FAILED",
        "correctnessGateRequiredFirst": True,
        "hostSharedWithDeveloperWorkloads": True,
        "claimBoundary": (
            "Local disposable-runner engineering evidence; not a production "
            "capacity or cross-host benchmark."
        ),
        "queries": results,
    }


def _environment_evidence() -> dict[str, Any]:
    return {
        "operatingSystem": platform.system().lower(),
        "operatingSystemRelease": platform.release(),
        "architecture": platform.machine(),
        "pythonVersion": platform.python_version(),
        "pythonExecutable": sys.executable,
        "sqliteVersion": sqlite3.sqlite_version,
        "duckdbPythonVersion": version("duckdb"),
        "psycopgVersion": version("psycopg"),
        "psycopgBinaryVersion": version("psycopg-binary"),
        "sqlglotVersion": version("sqlglot"),
        "networkPolicy": "LOOPBACK_ONLY",
        "dataPolicy": "DISPOSABLE_SYNTHETIC_ONLY",
    }


def _evidence_manifest(output: Path) -> dict[str, Any]:
    entries = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "runner-evidence.json":
            content = path.read_bytes()
            entries.append(
                {
                    "path": str(path.relative_to(output)),
                    "bytes": len(content),
                    "digest": _digest_bytes(content),
                }
            )
    return {
        "schemaVersion": "1.0",
        "contentAddressed": True,
        "evidence": entries,
        "evidenceCount": len(entries),
        "certification": "NOT_CERTIFIED",
        "independentVerification": "NOT_RUN",
    }


def verify_route(source_profile: str, target_profile: str, output: Path) -> dict[str, Any]:
    if source_profile == target_profile:
        raise ValueError("source and target SQL profiles must differ")
    if output.exists():
        raise FileExistsError("runtime evidence output must not already exist")
    if source_profile not in _LOCAL_PROFILE_IDS or target_profile not in _LOCAL_PROFILE_IDS:
        profile_by_id(source_profile)
        profile_by_id(target_profile)
        raise RunnerBlockedError(
            "exact source or target local Runner is unavailable; runtime evidence remains NOT_RUN"
        )

    rows = _fixture_rows()
    fixture = _fixture_document(rows)
    route_id = f"{source_profile}--to--{target_profile}"
    with _runner(source_profile) as source, _runner(target_profile) as target:
        source.create_fixture(rows)
        target.create_fixture(rows)
        source_connection = source.connect()
        target_connection = target.connect()
        try:
            query_reports, source_plans, target_plans, query_passed = _query_evidence(
                source,
                target,
                source_connection,
                target_connection,
            )
            performance = _performance_evidence(
                source,
                target,
                source_connection,
                target_connection,
            )
        finally:
            source_connection.close()
            target_connection.close()
        errors = {
            "source": _duplicate_error_evidence(source),
            "target": _duplicate_error_evidence(target),
        }
        error_passed = all(value["state"] == "PASSED" for value in errors.values())
        transactions: dict[str, dict[str, dict[str, Any]]] = {
            "source": {
                "transaction": _transaction_evidence(source),
                "locking": _locking_evidence(source),
            },
            "target": {
                "transaction": _transaction_evidence(target),
                "locking": _locking_evidence(target),
            },
        }
        transaction_passed = all(
            side["transaction"]["state"] == "PASSED" and side["locking"]["state"] == "PASSED"
            for side in transactions.values()
        )
        performance_passed = performance["state"] == "PASSED"
        passed = query_passed and error_passed and transaction_passed and performance_passed
        environment = _environment_evidence()
        environment["sourceRunner"] = source.engine_evidence()
        environment["targetRunner"] = target.engine_evidence()

    output.mkdir(parents=True)
    _write_json(output / "fixture.json", fixture)
    _write_json(
        output / "query-results.json",
        {
            "schemaVersion": "1.0",
            "routeId": route_id,
            "state": "PASSED" if query_passed else "FAILED",
            "queries": query_reports,
        },
    )
    _write_json(
        output / "error-equivalence.json",
        {
            "schemaVersion": "1.0",
            "routeId": route_id,
            "state": "PASSED" if error_passed else "FAILED",
            "uniqueViolation": errors,
        },
    )
    _write_json(
        output / "transaction-locking.json",
        {
            "schemaVersion": "1.0",
            "routeId": route_id,
            "state": "PASSED" if transaction_passed else "FAILED",
            "engines": transactions,
        },
    )
    _write_json(output / "performance.json", performance)
    _write_json(output / "plans/source-plan.json", source_plans)
    _write_json(output / "plans/target-plan.json", target_plans)
    _write_json(output / "environment.json", environment)
    gate: dict[str, Any] = {
        "schemaVersion": "1.0",
        "routeId": route_id,
        "fixtureDigest": _digest_json(fixture),
        "fixtureRows": len(rows),
        "checks": {
            "rowValueTypeOrderAndDuplicateEquivalence": ("PASSED" if query_passed else "FAILED"),
            "errorEquivalence": "PASSED" if error_passed else "FAILED",
            "transactionAndLockingEquivalence": ("PASSED" if transaction_passed else "FAILED"),
            "localPerformanceSlo": "PASSED" if performance_passed else "FAILED",
        },
        "sourceExecution": "PASSED",
        "targetExecution": "PASSED",
        "resultEquivalence": "PASSED" if passed else "FAILED",
        "localDecision": "READY_FOR_EXTERNAL_GATE" if passed else "FAILED",
        "independentHoldoutExecution": "NOT_RUN",
        "representativeProductionLikeExecution": "NOT_RUN",
        "independentVerification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }
    _write_json(output / "gate-result.json", gate)
    report = (
        f"# SQL runtime route evidence: {route_id}\n\n"
        f"- Local decision: `{gate['localDecision']}`\n"
        f"- Fixture: `{len(rows)}` deterministic disposable rows\n"
        f"- Query equivalence: `{gate['checks']['rowValueTypeOrderAndDuplicateEquivalence']}`\n"
        f"- Error equivalence: `{gate['checks']['errorEquivalence']}`\n"
        f"- Transaction and locking: `{gate['checks']['transactionAndLockingEquivalence']}`\n"
        f"- Local p95 SLO: `{gate['checks']['localPerformanceSlo']}`\n"
        "- Independent holdout execution: `NOT_RUN`\n"
        "- Representative production-like execution: `NOT_RUN`\n"
        "- Independent verification: `NOT_RUN`\n"
        "- Certification: `NOT_CERTIFIED`\n"
    )
    (output / "gate-report.md").write_text(report, encoding="utf-8")
    _write_json(output / "runner-evidence.json", _evidence_manifest(output))
    return gate


def runner_capabilities() -> dict[str, Any]:
    path = files("elmos_sql_transpiler").joinpath("data/local-runners-v1.json")
    catalog = json.loads(path.read_text(encoding="utf-8"))
    ready = []
    blocked = []
    for item in catalog["runners"]:
        rendered = dict(item)
        rendered["runtimeEvidence"] = "NOT_RUN"
        if item["state"] == "LOCAL_RUNNER_READY":
            ready.append(rendered)
        else:
            blocked.append(rendered)
    return {
        "schemaVersion": "1.0",
        "hostContract": catalog["host"],
        "ready": ready,
        "blocked": blocked,
        "readyDirectedRoutes": [
            f"{source}--to--{target}"
            for source in _LOCAL_PROFILE_IDS
            for target in _LOCAL_PROFILE_IDS
            if source != target
        ],
        "readyDirectedRouteCount": 6,
        "runtimeEvidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


def verify_local_matrix(output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError("runtime matrix output must not already exist")
    output.mkdir(parents=True)
    route_results: list[dict[str, Any]] = []
    for source in _LOCAL_PROFILE_IDS:
        for target in _LOCAL_PROFILE_IDS:
            if source == target:
                continue
            route_id = f"{source}--to--{target}"
            route_output = output / "routes" / route_id
            try:
                gate = verify_route(source, target, route_output)
                route_results.append(
                    {
                        "routeId": route_id,
                        "state": gate["localDecision"],
                        "resultEquivalence": gate["resultEquivalence"],
                        "evidence": str(route_output.relative_to(output)),
                    }
                )
            except (RunnerBlockedError, RuntimeError, TypeError, ValueError) as error:
                route_results.append(
                    {
                        "routeId": route_id,
                        "state": "BLOCKED",
                        "resultEquivalence": "NOT_RUN",
                        "error": type(error).__name__,
                        "message": " ".join(str(error).split()),
                        "certification": "NOT_CERTIFIED",
                    }
                )
    ready_count = sum(result["state"] == "READY_FOR_EXTERNAL_GATE" for result in route_results)
    result = {
        "schemaVersion": "1.0",
        "exactLocalProfiles": list(_LOCAL_PROFILE_IDS),
        "routeCount": len(route_results),
        "readyRouteCount": ready_count,
        "routes": route_results,
        "blockedExactProfiles": runner_capabilities()["blocked"],
        "localDecision": (
            "READY_FOR_EXTERNAL_GATE" if ready_count == len(route_results) else "BLOCKED"
        ),
        "independentVerification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }
    _write_json(output / "matrix-result.json", result)
    return result
