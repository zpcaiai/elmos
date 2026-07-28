"""Two independent validation legs for emitted certified-ddl-v1 DDL.

1. `validate_syntax`: always runs. Re-parses the emitted DDL with sqlglot in
   strict target-dialect mode. This proves the output is well-formed SQL for
   that dialect's grammar; it does NOT prove a real server would accept it
   (e.g. it cannot catch a duplicate object name, an out-of-range identifier
   length limit, or a permissions error).
2. `validate_execution`: only runs when the caller supplies a reachable DSN
   for a dialect this environment can actually speak to (PostgreSQL via
   psycopg2, MySQL via PyMySQL -- see `models.EXECUTABLE_DIALECTS`). Runs the
   emitted `CREATE TABLE` for real inside a rolled-back transaction (or a
   throwaway schema/database) against that real server. Oracle and SQL Server
   have no freely available root-less local server, so execution validation
   for those two dialects is always reported as `EXECUTION_NOT_AVAILABLE`
   unless the caller supplies their own reachable instance.

Both legs report independently in `ValidationReport` -- a syntax pass never
gets silently upgraded to "execution verified".
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlglot

from .models import Dialect, EXECUTABLE_DIALECTS


@dataclass(frozen=True)
class ValidationReport:
    syntax_status: str  # PASSED | FAILED
    syntax_diagnostics: tuple[str, ...]
    execution_status: str  # PASSED | FAILED | EXECUTION_NOT_AVAILABLE | EXECUTION_NOT_ATTEMPTED
    execution_diagnostics: tuple[str, ...]

    def passed(self) -> bool:
        return self.syntax_status == "PASSED"


def validate_syntax(sql: str, dialect: Dialect) -> tuple[str, tuple[str, ...]]:
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect.value) if s is not None]
    except sqlglot.errors.SqlglotError as exc:
        return "FAILED", (f"target-dialect re-parse failed: {exc}",)
    if len(statements) != 1:
        return "FAILED", (f"target-dialect re-parse produced {len(statements)} statements, expected 1",)
    return "PASSED", ()


def validate_execution(sql: str, dialect: Dialect, dsn: str | None) -> tuple[str, tuple[str, ...]]:
    if dsn is None:
        return "EXECUTION_NOT_ATTEMPTED", ("no --dsn supplied; execution-level evidence stays NOT_RUN",)
    if dialect not in EXECUTABLE_DIALECTS:
        return "EXECUTION_NOT_AVAILABLE", (
            f"{dialect.value} has no freely available root-less local server in this environment; "
            "supply your own reachable instance and driver to obtain real execution evidence",
        )
    if dialect == Dialect.POSTGRES:
        return _validate_postgres(sql, dsn)
    if dialect == Dialect.MYSQL:
        return _validate_mysql(sql, dsn)
    raise AssertionError(f"unreachable: {dialect} listed as executable but not handled")  # pragma: no cover


def _validate_postgres(sql: str, dsn: str) -> tuple[str, tuple[str, ...]]:
    try:
        import psycopg2
    except ImportError:
        return "FAILED", ("psycopg2-binary is not installed; install the [execution] extra to run real Postgres validation",)
    schema_name = f"elmos_sql_dialect_check_{uuid.uuid4().hex[:12]}"
    try:
        conn = psycopg2.connect(dsn)
    except Exception as exc:  # noqa: BLE001 - report any connection failure as evidence, not a crash
        return "FAILED", (f"could not connect to {dsn}: {exc}",)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema_name}"')
            cur.execute(f'SET search_path TO "{schema_name}"')
            cur.execute(sql)
        conn.rollback()  # the CREATE SCHEMA + CREATE TABLE never persists; this is a real syntax+semantics check only
        return "PASSED", ()
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        return "FAILED", (f"PostgreSQL rejected the emitted DDL: {exc}",)
    finally:
        conn.close()


def _validate_mysql(sql: str, dsn_json: str) -> tuple[str, tuple[str, ...]]:
    """`dsn_json` is a JSON object with host/port/user/password (MySQL has no
    single DSN string convention as portable as libpq's), e.g.
    `{"host": "127.0.0.1", "port": 3306, "user": "root", "password": ""}`."""
    try:
        import json

        import pymysql  # type: ignore[import-untyped]
    except ImportError:
        return "FAILED", ("PyMySQL is not installed; install the [execution] extra to run real MySQL validation",)
    try:
        params = json.loads(dsn_json)
    except (json.JSONDecodeError, TypeError) as exc:
        return "FAILED", (f"--dsn for mysql must be a JSON object (host/port/user/password): {exc}",)
    database_name = f"elmos_sql_dialect_check_{uuid.uuid4().hex[:12]}"
    try:
        conn = pymysql.connect(**params)
    except Exception as exc:  # noqa: BLE001
        return "FAILED", (f"could not connect with the supplied MySQL parameters: {exc}",)
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE `{database_name}`")
            try:
                cur.execute(f"USE `{database_name}`")
                cur.execute(sql)
                status = "PASSED"
                diagnostics: tuple[str, ...] = ()
            except Exception as exc:  # noqa: BLE001
                status = "FAILED"
                diagnostics = (f"MySQL rejected the emitted DDL: {exc}",)
            finally:
                cur.execute(f"DROP DATABASE `{database_name}`")
        return status, diagnostics
    except Exception as exc:  # noqa: BLE001
        return "FAILED", (f"MySQL execution validation failed: {exc}",)
    finally:
        conn.close()


def validate(sql: str, dialect: Dialect, dsn: str | None) -> ValidationReport:
    syntax_status, syntax_diagnostics = validate_syntax(sql, dialect)
    execution_status, execution_diagnostics = validate_execution(sql, dialect, dsn) if syntax_status == "PASSED" else (
        "EXECUTION_NOT_ATTEMPTED", ("skipped because syntax validation failed first",)
    )
    return ValidationReport(syntax_status, syntax_diagnostics, execution_status, execution_diagnostics)
