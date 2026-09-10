"""Tests for Procedural SQL AST Lowerer across dialects."""

from __future__ import annotations

import tempfile
from pathlib import Path

from elmos_sql_dialect.models import Dialect
from elmos_sql_dialect.procedural_ast_lowerer import (
    ParamMode,
    ProceduralAstLowerer,
    RoutineKind,
)
from elmos_sql_dialect.scan import scan_repository


def test_oracle_plsql_procedure_lowering_to_postgres():
    lowerer = ProceduralAstLowerer(target_dialect=Dialect.POSTGRES)
    oracle_sql = """
    CREATE OR REPLACE PROCEDURE transfer_funds(
        p_from_acc IN VARCHAR2,
        p_to_acc IN VARCHAR2,
        p_amount IN NUMBER,
        p_status OUT VARCHAR2
    ) IS
        v_balance NUMBER(12, 2);
        v_fee CONSTANT NUMBER := 2.50;
        CURSOR cur_acct IS SELECT balance FROM accounts WHERE acc_num = p_from_acc FOR UPDATE;
    BEGIN
        OPEN cur_acct;
        FETCH cur_acct INTO v_balance;
        CLOSE cur_acct;

        IF v_balance < p_amount THEN
            p_status := 'INSUFFICIENT_FUNDS';
            RETURN;
        END IF;

        UPDATE accounts SET balance = balance - p_amount - v_fee WHERE acc_num = p_from_acc;
        UPDATE accounts SET balance = balance + p_amount WHERE acc_num = p_to_acc;

        COMMIT;
        p_status := 'SUCCESS';
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            ROLLBACK;
            p_status := 'ACCOUNT_NOT_FOUND';
        WHEN OTHERS THEN
            ROLLBACK;
            RAISE;
    END transfer_funds;
    """
    routine = lowerer.parse_routine(oracle_sql, source_dialect=Dialect.ORACLE)
    assert routine.name == "transfer_funds"
    assert routine.kind == RoutineKind.PROCEDURE
    assert len(routine.parameters) == 4
    assert routine.parameters[0].mode == ParamMode.IN
    assert routine.parameters[3].mode == ParamMode.OUT
    assert len(routine.body.declarations) == 3
    assert len(routine.body.statements) >= 5
    assert routine.body.exception_section is not None
    assert len(routine.body.exception_section.handlers) >= 1

    lowered_pg = lowerer.lower_routine(routine, target_dialect=Dialect.POSTGRES)
    assert "CREATE OR REPLACE PROCEDURE transfer_funds" in lowered_pg
    assert "LANGUAGE plpgsql" in lowered_pg
    assert "p_status OUT VARCHAR(255)" in lowered_pg or "p_status OUT text" in lowered_pg
    assert "v_balance NUMERIC(12, 2)" in lowered_pg
    assert "OPEN cur_acct;" in lowered_pg
    assert "FETCH cur_acct INTO v_balance;" in lowered_pg
    assert "CLOSE cur_acct;" in lowered_pg
    assert "EXCEPTION" in lowered_pg
    assert "WHEN NO_DATA_FOUND THEN" in lowered_pg


def test_oracle_plsql_function_with_loops():
    lowerer = ProceduralAstLowerer(target_dialect=Dialect.POSTGRES)
    oracle_sql = """
    CREATE OR REPLACE FUNCTION compute_compound_interest(
        p_principal IN NUMBER,
        p_rate IN NUMBER,
        p_years IN INTEGER
    ) RETURN NUMBER IS
        v_total NUMBER := p_principal;
        v_idx INTEGER;
    BEGIN
        FOR v_idx IN 1..p_years LOOP
            v_total := v_total * (1 + p_rate / 100);
        END LOOP;
        RETURN v_total;
    END;
    """
    routine = lowerer.parse_routine(oracle_sql, source_dialect=Dialect.ORACLE)
    assert routine.name == "compute_compound_interest"
    assert routine.kind == RoutineKind.FUNCTION
    assert routine.return_type is not None

    lowered_pg = lowerer.lower_routine(routine, target_dialect=Dialect.POSTGRES)
    assert "CREATE OR REPLACE FUNCTION compute_compound_interest" in lowered_pg
    assert "RETURNS NUMERIC" in lowered_pg.upper()
    assert "FOR v_idx IN 1..p_years LOOP" in lowered_pg
    assert "RETURN v_total;" in lowered_pg


def test_tsql_procedure_lowering():
    lowerer = ProceduralAstLowerer(target_dialect=Dialect.POSTGRES)
    tsql = """
    CREATE PROCEDURE sp_process_orders
        @batch_id INT,
        @updated_count INT OUTPUT
    AS
    BEGIN
        DECLARE @current_id INT = 0;
        DECLARE @max_id INT = 100;

        WHILE @current_id < @max_id
        BEGIN
            UPDATE orders SET status = 'PROCESSED' WHERE order_id = @current_id;
            SET @current_id = @current_id + 1;
        END

        SELECT @updated_count = COUNT(*) FROM orders WHERE status = 'PROCESSED';
    END
    """
    routine = lowerer.parse_routine(tsql, source_dialect=Dialect.TSQL)
    assert routine.name == "sp_process_orders"
    assert len(routine.parameters) == 2
    assert routine.parameters[1].mode == ParamMode.OUT

    lowered_pg = lowerer.lower_routine(routine, target_dialect=Dialect.POSTGRES)
    assert "CREATE PROCEDURE sp_process_orders" in lowered_pg
    assert "WHILE" in lowered_pg


def test_trigger_lowering():
    lowerer = ProceduralAstLowerer(target_dialect=Dialect.POSTGRES)
    oracle_trig = """
    CREATE OR REPLACE TRIGGER trg_audit_employees
    BEFORE INSERT OR UPDATE ON employees
    FOR EACH ROW
    DECLARE
        v_user VARCHAR2(50);
    BEGIN
        v_user := USER;
        :NEW.updated_by := v_user;
        :NEW.updated_at := SYSDATE;
    END;
    """
    trig = lowerer.parse_trigger(oracle_trig, source_dialect=Dialect.ORACLE)
    assert trig.name == "trg_audit_employees"
    assert trig.table_name == "employees"
    assert trig.timing == "BEFORE"
    assert "INSERT" in trig.events
    assert "UPDATE" in trig.events
    assert trig.for_each_row is True

    lowered_pg = lowerer.lower_trigger(trig, target_dialect=Dialect.POSTGRES)
    assert "CREATE OR REPLACE FUNCTION fn_trg_audit_employees()" in lowered_pg
    assert "RETURNS trigger" in lowered_pg
    assert "CREATE TRIGGER trg_audit_employees" in lowered_pg
    assert "BEFORE INSERT OR UPDATE ON employees" in lowered_pg
    assert "EXECUTE FUNCTION fn_trg_audit_employees()" in lowered_pg


def test_scanner_with_procedural_lowering_eliminates_blockers():
    sql_content = """
    CREATE TABLE accounts (
        acc_num VARCHAR(32) PRIMARY KEY,
        balance NUMERIC(14, 2) NOT NULL
    );

    CREATE OR REPLACE PROCEDURE update_balance(p_acc VARCHAR, p_delta NUMERIC) IS
        v_current NUMERIC;
    BEGIN
        SELECT balance INTO v_current FROM accounts WHERE acc_num = p_acc;
        v_current := v_current + p_delta;
        UPDATE accounts SET balance = v_current WHERE acc_num = p_acc;
    EXCEPTION
        WHEN OTHERS THEN
            RAISE;
    END;
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        sql_file = Path(tmpdir) / "test.sql"
        sql_file.write_text(sql_content, encoding="utf-8")

        # Without procedural lowering: procedure is blocked or out of subset
        rep_standard = scan_repository(tmpdir, source_dialect=Dialect.ORACLE, enable_procedural_lowering=False)
        assert rep_standard.totals["outOfSubset"] >= 1

        # With procedural lowering: procedure is fully lowered into AST and admitted
        rep_lowered = scan_repository(tmpdir, source_dialect=Dialect.ORACLE, enable_procedural_lowering=True)

        assert rep_lowered.disposition_coverage == 1.0
        assert rep_lowered.totals["outOfSubset"] == 0
        assert rep_lowered.disposition_counts["AUTOMATED_TRANSLATION_CANDIDATE"] == rep_lowered.totals["discovered"]


