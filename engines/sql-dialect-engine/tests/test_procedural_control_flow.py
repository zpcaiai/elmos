from __future__ import annotations

import pytest

from elmos_sql_dialect.advanced import emit_procedure, parse_procedure
from elmos_sql_dialect.models import Dialect, DialectError


def test_procedure_if_else_statement_cross_dialects() -> None:
    sql_pg = """
    CREATE PROCEDURE update_limit(p_status VARCHAR, p_amount OUT INT)
    LANGUAGE plpgsql
    AS $$
    BEGIN
        IF p_status = 'VIP' THEN
            p_amount := 10000;
        ELSIF p_status = 'REGULAR' THEN
            p_amount := 5000;
        ELSE
            p_amount := 1000;
        END IF;
    END;
    $$;
    """
    proc = parse_procedure(sql_pg, Dialect.POSTGRES)
    assert len(proc.if_statements) == 1
    stmt = proc.if_statements[0]
    assert len(stmt.branches) == 2
    assert stmt.branches[0].condition == "p_status = 'VIP'"
    assert stmt.branches[1].condition == "p_status = 'REGULAR'"
    assert stmt.else_statements == ("p_amount := 1000;",)

    # Emit to Oracle
    emitted_oracle = emit_procedure(proc, Dialect.ORACLE)
    assert "IF p_status = 'VIP' THEN" in emitted_oracle
    assert "ELSIF p_status = 'REGULAR' THEN" in emitted_oracle
    assert "ELSE p_amount := 1000;; END IF;" in emitted_oracle

    # Emit to MySQL
    emitted_mysql = emit_procedure(proc, Dialect.MYSQL)
    assert "IF p_status = 'VIP' THEN" in emitted_mysql
    assert "ELSEIF p_status = 'REGULAR' THEN" in emitted_mysql
    assert "END IF;" in emitted_mysql

    # Emit to T-SQL
    emitted_tsql = emit_procedure(proc, Dialect.TSQL)
    assert "IF p_status = 'VIP' BEGIN" in emitted_tsql
    assert "ELSE IF p_status = 'REGULAR' BEGIN" in emitted_tsql
    assert "ELSE BEGIN" in emitted_tsql


def test_procedure_while_loop_cross_dialects() -> None:
    sql_pg = """
    CREATE PROCEDURE count_down(p_limit OUT INT)
    LANGUAGE plpgsql
    AS $$
    BEGIN
        WHILE p_limit > 0 LOOP
            p_limit := p_limit - 1;
        END LOOP;
    END;
    $$;
    """
    proc = parse_procedure(sql_pg, Dialect.POSTGRES)
    assert len(proc.while_loops) == 1
    assert proc.while_loops[0].condition == "p_limit > 0"

    emitted_oracle = emit_procedure(proc, Dialect.ORACLE)
    assert "WHILE p_limit > 0 LOOP" in emitted_oracle
    assert "END LOOP;" in emitted_oracle

    emitted_tsql = emit_procedure(proc, Dialect.TSQL)
    assert "WHILE p_limit > 0 BEGIN" in emitted_tsql
    assert "END" in emitted_tsql


def test_procedure_dynamic_execute_cross_dialects() -> None:
    sql_pg = """
    CREATE PROCEDURE run_dyn(p_res OUT INT)
    LANGUAGE plpgsql
    AS $$
    BEGIN
        EXECUTE 'SELECT 42' INTO p_res;
    END;
    $$;
    """
    # By default, dynamic SQL fails closed
    with pytest.raises(DialectError) as exc:
        parse_procedure(sql_pg, Dialect.POSTGRES)
    assert exc.value.code == "CERTIFIED_ROUTINE_UNSUPPORTED_BODY"

    # With allow_dynamic_sql=True, transpilation succeeds
    proc = parse_procedure(sql_pg, Dialect.POSTGRES, allow_dynamic_sql=True)
    assert len(proc.dynamic_executes) == 1
    dyn = proc.dynamic_executes[0]
    assert dyn.query_expression == "'SELECT 42'"
    assert dyn.into_variable == "p_res"

    emitted_oracle = emit_procedure(proc, Dialect.ORACLE)
    assert "EXECUTE IMMEDIATE 'SELECT 42' INTO p_res;" in emitted_oracle

    emitted_tsql = emit_procedure(proc, Dialect.TSQL)
    assert "EXEC sp_executesql 'SELECT 42';" in emitted_tsql

    emitted_mysql = emit_procedure(proc, Dialect.MYSQL)
    assert "PREPARE stmt FROM @dyn_stmt; EXECUTE stmt; DEALLOCATE PREPARE stmt;" in emitted_mysql


def test_procedure_or_replace_fails_closed_on_mysql_tsql() -> None:
    sql_pg = "CREATE OR REPLACE PROCEDURE p(x OUT INT) AS $$ BEGIN x := 1; END; $$;"
    proc = parse_procedure(sql_pg, Dialect.POSTGRES)
    with pytest.raises(DialectError) as exc_tsql:
        emit_procedure(proc, Dialect.TSQL)
    assert exc_tsql.value.code == "CERTIFIED_ROUTINE_REPLACE_UNSUPPORTED_BY_TARGET"

    with pytest.raises(DialectError) as exc_mysql:
        emit_procedure(proc, Dialect.MYSQL)
    assert exc_mysql.value.code == "CERTIFIED_ROUTINE_REPLACE_UNSUPPORTED_BY_TARGET"
