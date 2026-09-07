from __future__ import annotations

from elmos_sql_dialect.sql_transpiler_gateway import (
    _CORE_DIALECTS,
    SqlTranspilerGateway,
    SupportedDialect,
)


def test_gateway_supports_sqlite_and_duckdb() -> None:
    assert SupportedDialect.SQLITE.value == "sqlite"
    assert SupportedDialect.DUCKDB.value == "duckdb"
    assert "sqlite" in _CORE_DIALECTS
    assert "duckdb" in _CORE_DIALECTS
    assert _CORE_DIALECTS["sqlite"] == "sqlite"
    assert _CORE_DIALECTS["duckdb"] == "duckdb"


def test_gateway_blocks_empty_sql() -> None:
    gateway = SqlTranspilerGateway()
    result = gateway.transpile(
        sql="   ",
        src_dialect="postgres",
        tgt_dialect="mysql",
        source_profile="postgresql-17.5",
        target_profile="mysql-8.4.10-lts",
    )
    assert result.status == "BLOCKED"
    assert result.reason_code == "SQL_INPUT_REQUIRED"


def test_gateway_blocks_same_profile() -> None:
    gateway = SqlTranspilerGateway()
    result = gateway.transpile(
        sql="SELECT 1",
        src_dialect="postgres",
        tgt_dialect="postgres",
        source_profile="postgresql-17.5",
        target_profile="postgresql-17.5",
    )
    assert result.status == "BLOCKED"
    assert result.reason_code == "SOURCE_AND_TARGET_PROFILE_MUST_DIFFER"


def test_gateway_blocks_unsupported_dialect() -> None:
    gateway = SqlTranspilerGateway()
    result = gateway.transpile(
        sql="SELECT 1",
        src_dialect="unknown_db",
        tgt_dialect="postgres",
        source_profile="p1",
        target_profile="postgresql-17.5",
    )
    assert result.status == "BLOCKED"
    assert result.reason_code == "UNSUPPORTED_DIALECT"


def test_gateway_blocks_missing_profile() -> None:
    gateway = SqlTranspilerGateway()
    result = gateway.transpile(
        sql="SELECT 1",
        src_dialect="postgres",
        tgt_dialect="mysql",
    )
    assert result.status == "BLOCKED"
    assert result.reason_code == "EXACT_PROFILE_REQUIRED"
