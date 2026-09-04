from __future__ import annotations

import pytest

from elmos_sql_dialect.advanced import emit_procedure, emit_trigger, parse_procedure, parse_trigger
from elmos_sql_dialect.models import (
    CursorLoop,
    Dialect,
    ExceptionHandler,
    RollbackSavepointStatement,
    SavepointStatement,
)


def test_procedure_with_savepoint_and_rollback() -> None:
    sql = """
    CREATE PROCEDURE process_batch(OUT status INT)
    LANGUAGE plpgsql AS $$
    BEGIN
        SAVEPOINT batch_start;
        SET status = 1;
        ROLLBACK TO SAVEPOINT batch_start;
    END;
    $$
    """
    proc = parse_procedure(sql, Dialect.POSTGRES)
    assert len(proc.savepoints) == 1
    assert proc.savepoints[0].name == "batch_start"
    assert len(proc.rollback_savepoints) == 1
    assert proc.rollback_savepoints[0].name == "batch_start"
    assert len(proc.assignments) == 1

    # PostgreSQL emission
    pg_sql = emit_procedure(proc, Dialect.POSTGRES)
    assert "SAVEPOINT batch_start;" in pg_sql
    assert "ROLLBACK TO SAVEPOINT batch_start;" in pg_sql

    # Oracle emission
    ora_sql = emit_procedure(proc, Dialect.ORACLE)
    assert "SAVEPOINT batch_start;" in ora_sql
    assert "ROLLBACK TO batch_start;" in ora_sql

    # T-SQL emission
    tsql_sql = emit_procedure(proc, Dialect.TSQL)
    assert "SAVE TRANSACTION batch_start;" in tsql_sql
    assert "ROLLBACK TRANSACTION batch_start;" in tsql_sql


def test_procedure_with_cursor_loop() -> None:
    sql = """
    CREATE PROCEDURE sync_users(OUT synced_count INT)
    LANGUAGE plpgsql AS $$
    BEGIN
        FOR rec IN (SELECT id FROM users) LOOP
            SET synced_count = 1;
        END LOOP;
    END;
    $$
    """
    proc = parse_procedure(sql, Dialect.POSTGRES)
    assert len(proc.cursor_loops) == 1
    assert proc.cursor_loops[0].cursor_name == "rec"
    assert "SELECT id FROM users" in proc.cursor_loops[0].query_sql

    pg_sql = emit_procedure(proc, Dialect.POSTGRES)
    assert "FOR rec IN (SELECT id FROM users) LOOP" in pg_sql

    ora_sql = emit_procedure(proc, Dialect.ORACLE)
    assert "FOR rec IN (SELECT id FROM users) LOOP" in ora_sql

    tsql_sql = emit_procedure(proc, Dialect.TSQL)
    assert "DECLARE rec_cur CURSOR FOR SELECT id FROM users" in tsql_sql


def test_procedure_with_exception_handler() -> None:
    sql = """
    CREATE PROCEDURE safe_update(OUT err_flag INT)
    LANGUAGE plpgsql AS $$
    BEGIN
        SET err_flag = 0;
        EXCEPTION WHEN OTHERS THEN
            SET err_flag = 1;
    END;
    $$
    """
    proc = parse_procedure(sql, Dialect.POSTGRES)
    assert len(proc.exception_handlers) == 1
    assert proc.exception_handlers[0].condition == "OTHERS"

    pg_sql = emit_procedure(proc, Dialect.POSTGRES)
    assert "EXCEPTION WHEN OTHERS THEN" in pg_sql

    tsql_sql = emit_procedure(proc, Dialect.TSQL)
    assert "BEGIN TRY" in tsql_sql
    assert "BEGIN CATCH" in tsql_sql


def test_trigger_shims_across_targets() -> None:
    sql = """
    CREATE TRIGGER audit_trg AFTER INSERT ON audits
    FOR EACH ROW EXECUTE FUNCTION log_action()
    """
    trg = parse_trigger(sql, Dialect.POSTGRES)

    # Postgres
    pg_sql = emit_trigger(trg, Dialect.POSTGRES)
    assert "EXECUTE FUNCTION log_action()" in pg_sql

    # Oracle shim
    ora_sql = emit_trigger(trg, Dialect.ORACLE, allow_trigger_shim=True)
    assert "CREATE OR REPLACE TRIGGER" in ora_sql
    assert "BEGIN log_action(); END;" in ora_sql

    # MySQL shim
    my_sql = emit_trigger(trg, Dialect.MYSQL, allow_trigger_shim=True)
    assert "CREATE TRIGGER" in my_sql
    assert "BEGIN CALL log_action(); END" in my_sql

    # T-SQL shim
    tsql_sql = emit_trigger(trg, Dialect.TSQL, allow_trigger_shim=True)
    assert "CREATE TRIGGER" in tsql_sql
    assert "AS BEGIN EXEC log_action; END" in tsql_sql
