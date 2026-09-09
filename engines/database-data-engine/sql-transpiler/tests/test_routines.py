from __future__ import annotations

import pytest

from elmos_sql_transpiler.models import TranspileRequest
from elmos_sql_transpiler.routines import ROUTINE_DUCKDB_MACRO, ROUTINE_SQL_FUNCTION
from elmos_sql_transpiler.transpiler import transpile

_PG_FUNCTION = (
    "CREATE FUNCTION add_one(x INTEGER) RETURNS INTEGER LANGUAGE SQL AS $$ SELECT x + 1 $$"
)
_MYSQL_FUNCTION = "CREATE FUNCTION add_one(x INT) RETURNS INT DETERMINISTIC RETURN x + 1"
_PG_PROCEDURE = (
    "CREATE PROCEDURE bump_status() LANGUAGE SQL AS $$ UPDATE orders SET status = 'CLOSED' $$"
)
_PG_TRIGGER = (
    "CREATE TRIGGER audit_trg AFTER INSERT ON audits FOR EACH ROW EXECUTE FUNCTION log_action()"
)
_PG_CONTROL_FLOW = (
    "CREATE FUNCTION guarded(p INTEGER) RETURNS INTEGER LANGUAGE plpgsql AS $$ "
    "BEGIN RETURN p; END; $$"
)

_ROUTINE_TARGETS = (
    "mysql-8.4.10-lts",
    "sqlserver-2022-cu26",
    "oracle-26ai-ee",
    "postgresql-18.4",
    "duckdb-1.5.4",
)


def _transpile(source: str, target: str, sql: str):
    return transpile(
        TranspileRequest(
            query_id="routine-test",
            source_profile=source,
            target_profile=target,
            sql=sql,
        )
    )


@pytest.mark.parametrize("target", _ROUTINE_TARGETS)
def test_postgres_sql_function_emits_native_target_syntax(target: str) -> None:
    result = _transpile("postgresql-17.5", target, _PG_FUNCTION)
    assert result.state == "SYNTAX_READY", result.diagnostics
    assert result.target_sql is not None
    assert "add_one" in result.target_sql
    assert ROUTINE_SQL_FUNCTION in result.statements[0].obligations
    if target == "duckdb-1.5.4":
        assert "CREATE MACRO" in result.target_sql
        assert ROUTINE_DUCKDB_MACRO in result.statements[0].obligations
    elif target == "mysql-8.4.10-lts":
        assert "RETURN" in result.target_sql.upper()
        assert "$$" not in result.target_sql
    elif target == "sqlserver-2022-cu26":
        assert "@x" in result.target_sql
        assert "BEGIN RETURN" in result.target_sql
    elif target == "oracle-26ai-ee":
        assert "RETURN" in result.target_sql
        assert "BEGIN" in result.target_sql
    assert result.certification == "NOT_CERTIFIED"
    assert result.source_execution == "NOT_RUN"


def test_postgres_sql_function_stays_blocked_for_sqlite() -> None:
    result = _transpile("postgresql-17.5", "sqlite-3.53.3", _PG_FUNCTION)
    assert result.state == "BLOCKED"
    assert result.target_sql is None
    assert {item.code for item in result.diagnostics} >= {"ROUTINE_TARGET_UNSUPPORTED"}


def test_mysql_sql_function_reaches_postgres_and_records_dropped_determinism() -> None:
    result = _transpile("mysql-8.4.10-lts", "postgresql-17.5", _MYSQL_FUNCTION)
    assert result.state == "SYNTAX_READY", result.diagnostics
    assert result.target_sql is not None
    assert "LANGUAGE SQL" in result.target_sql
    assert "ROUTINE_STABILITY_NOT_PORTED" in result.statements[0].obligations


def test_sql_procedure_emits_across_servers() -> None:
    result = _transpile("postgresql-17.5", "mysql-8.4.10-lts", _PG_PROCEDURE)
    assert result.state == "SYNTAX_READY", result.diagnostics
    assert result.target_sql is not None
    assert "CREATE PROCEDURE bump_status" in result.target_sql
    assert "UPDATE orders" in result.target_sql
    assert "ROUTINE_SQL_SINGLE_DML_PROCEDURE" in result.statements[0].obligations


def test_sql_procedure_blocked_for_sqlite_and_duckdb() -> None:
    for target in ("sqlite-3.53.3", "duckdb-1.5.4"):
        result = _transpile("postgresql-17.5", target, _PG_PROCEDURE)
        assert result.state == "BLOCKED"
        assert result.target_sql is None
        assert "ROUTINE_TARGET_UNSUPPORTED" in {item.code for item in result.diagnostics}


def test_named_function_row_trigger_emits_postgres_and_shims() -> None:
    pg = _transpile("postgresql-17.5", "postgresql-18.4", _PG_TRIGGER)
    assert pg.state == "SYNTAX_READY", pg.diagnostics
    assert pg.target_sql is not None
    assert "EXECUTE FUNCTION log_action()" in pg.target_sql

    mysql = _transpile("postgresql-17.5", "mysql-8.4.10-lts", _PG_TRIGGER)
    assert mysql.state == "SYNTAX_READY", mysql.diagnostics
    assert mysql.target_sql is not None
    assert "CALL log_action()" in mysql.target_sql

    sqlite = _transpile("postgresql-17.5", "sqlite-3.53.3", _PG_TRIGGER)
    assert sqlite.state == "SYNTAX_READY", sqlite.diagnostics
    assert sqlite.target_sql is not None
    assert "SELECT log_action()" in sqlite.target_sql


def test_trigger_blocked_for_duckdb() -> None:
    result = _transpile("postgresql-17.5", "duckdb-1.5.4", _PG_TRIGGER)
    assert result.state == "BLOCKED"
    assert "ROUTINE_TARGET_UNSUPPORTED" in {item.code for item in result.diagnostics}


def test_plpgsql_control_flow_stays_fail_closed() -> None:
    result = _transpile("postgresql-17.5", "mysql-8.4.10-lts", _PG_CONTROL_FLOW)
    assert result.state == "BLOCKED"
    assert result.target_sql is None
    codes = {item.code for item in result.diagnostics}
    assert "ROUTINE_LANGUAGE_UNSUPPORTED" in codes or "UNSUPPORTED_SEMANTICS" in codes


def test_oracle_function_command_is_typed_not_left_opaque() -> None:
    result = _transpile(
        "oracle-26ai-ee",
        "postgresql-17.5",
        "CREATE FUNCTION add_one(x INTEGER) RETURN INTEGER AS BEGIN RETURN x + 1; END;",
    )
    assert result.state == "SYNTAX_READY", result.diagnostics
    assert result.target_sql is not None
    assert "CREATE FUNCTION add_one" in result.target_sql
    assert "LANGUAGE SQL" in result.target_sql
