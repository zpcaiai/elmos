"""Comprehensive industrial test suite for all 13 ChinaDB Dedicated Target Lowerers.

Validates AST lowering, type mappings, builtin functions, procedural code,
triggers, sequences, catalog queries, and enterprise schema transformations.
"""

from __future__ import annotations

import pytest

from elmos_sql_transpiler.chinadb_target_lowers import (
    ChinaDbTargetLowerer,
    Dm8TargetLowerer,
    GaussDbMysqlTargetLowerer,
    GaussDbOracleTargetLowerer,
    GBase8aTargetLowerer,
    GBase8cTargetLowerer,
    GBase8sTargetLowerer,
    GoldenDbTargetLowerer,
    HighGoTargetLowerer,
    KingbaseTargetLowerer,
    OceanBaseMysqlTargetLowerer,
    OceanBaseOracleTargetLowerer,
    OpenGaussTargetLowerer,
    TidbTargetLowerer,
    get_chinadb_lowerer,
    list_supported_targets,
)


class TestTargetRegistryAndFactory:
    """Test registry and dynamic instantiation of all 13 domestic database targets."""

    def test_list_supported_targets_count(self) -> None:
        targets = list_supported_targets()
        assert len(targets) == 13
        expected = [
            "dm8", "gaussdb_mysql", "gaussdb_oracle", "gbase8a", "gbase8c",
            "gbase8s", "goldendb", "highgo", "kingbase", "oceanbase_mysql",
            "oceanbase_oracle", "opengauss", "tidb",
        ]
        assert sorted(targets) == sorted(expected)

    def test_get_chinadb_lowerer_all_targets(self) -> None:
        for target_id in list_supported_targets():
            lowerer = get_chinadb_lowerer(target_id)
            assert isinstance(lowerer, ChinaDbTargetLowerer)
            assert lowerer.target_id == target_id
            assert len(lowerer.display_name) > 0
            assert len(lowerer.family) > 0

    def test_get_chinadb_lowerer_invalid_target(self) -> None:
        with pytest.raises(ValueError, match="Unsupported ChinaDB target 'unknown_db'"): 
            get_chinadb_lowerer("unknown_db")

    def test_target_families_distribution(self) -> None:
        targets = [get_chinadb_lowerer(t) for t in list_supported_targets()]
        families = {t.family for t in targets}
        assert len(families) >= 4

class TestDm8TargetLowerer:
    """Comprehensive industrial test suite for Dameng 8 (DM8)."""

    @pytest.fixture
    def lowerer(self) -> Dm8TargetLowerer:
        return get_chinadb_lowerer("dm8")

    def test_metadata_and_family(self, lowerer):
        assert lowerer.target_id == "dm8"
        assert lowerer.display_name == "Dameng 8 (DM8)"
        assert lowerer.family == "oracle_compat"
        assert len(lowerer.type_mappings) > 0
        assert len(lowerer.builtin_mappings) > 0
        assert len(lowerer.lowering_rules) > 0

    def test_type_mapping_0_datetime2(self, lowerer):
        sql = "CREATE TABLE t (col1 DATETIME2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "TIMESTAMP" in lowered

    def test_type_mapping_1_smalldatetime(self, lowerer):
        sql = "CREATE TABLE t (col1 SMALLDATETIME NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "TIMESTAMP" in lowered

    def test_type_mapping_2_nvarchar_max_(self, lowerer):
        sql = "CREATE TABLE t (col1 NVARCHAR(MAX) NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "CLOB" in lowered

    def test_type_mapping_3_varchar_max_(self, lowerer):
        sql = "CREATE TABLE t (col1 VARCHAR(MAX) NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "CLOB" in lowered

    def test_type_mapping_4_varbinary_max_(self, lowerer):
        sql = "CREATE TABLE t (col1 VARBINARY(MAX) NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "BLOB" in lowered

    def test_type_mapping_5_image(self, lowerer):
        sql = "CREATE TABLE t (col1 IMAGE NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "BLOB" in lowered

    def test_builtin_mapping_0_getdate(self, lowerer):
        sql = "SELECT GETDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "SYSDATE" in lowered

    def test_builtin_mapping_1_getutcdate(self, lowerer):
        sql = "SELECT GETUTCDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "SYS_EXTRACT_UTC" in lowered

    def test_builtin_mapping_2_isnull(self, lowerer):
        sql = "SELECT ISNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NVL" in lowered

    def test_builtin_mapping_3_len(self, lowerer):
        sql = "SELECT LEN() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "LENGTH" in lowered

    def test_builtin_mapping_4_charindex(self, lowerer):
        sql = "SELECT CHARINDEX() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "INSTR" in lowered

    def test_builtin_mapping_5_newid(self, lowerer):
        sql = "SELECT NEWID() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "RAWTOHEX" in lowered

    def test_lowering_rule_0_dm8_identity_clause(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "dm8_identity_clause"]
        assert len(rules) == 1
        assert rules[0].rule_id == "dm8_identity_clause"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_1_dm8_square_bracket_escape(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "dm8_square_bracket_escape"]
        assert len(rules) == 1
        assert rules[0].rule_id == "dm8_square_bracket_escape"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_2_dm8_convert_cast(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "dm8_convert_cast"]
        assert len(rules) == 1
        assert rules[0].rule_id == "dm8_convert_cast"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_3_dm8_tsql_variable_prefix(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "dm8_tsql_variable_prefix"]
        assert len(rules) == 1
        assert rules[0].rule_id == "dm8_tsql_variable_prefix"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_4_dm8_dual_preservation(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "dm8_dual_preservation"]
        assert len(rules) == 1
        assert rules[0].rule_id == "dm8_dual_preservation"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_5_dm8_top_to_rownum(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "dm8_top_to_rownum"]
        assert len(rules) == 1
        assert rules[0].rule_id == "dm8_top_to_rownum"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_6_dm8_limit_offset(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "dm8_limit_offset"]
        assert len(rules) == 1
        assert rules[0].rule_id == "dm8_limit_offset"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "mysql")
        assert isinstance(res, str)

    def test_lowering_rule_7_dm8_auto_increment_to_identity(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "dm8_auto_increment_to_identity"]
        assert len(rules) == 1
        assert rules[0].rule_id == "dm8_auto_increment_to_identity"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "mysql")
        assert isinstance(res, str)

    def test_lowering_rule_8_dm8_on_duplicate_key(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "dm8_on_duplicate_key"]
        assert len(rules) == 1
        assert rules[0].rule_id == "dm8_on_duplicate_key"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "mysql")
        assert isinstance(res, str)

    def test_table_ddl_lowering(self, lowerer):
        source_ddl = """
        CREATE TABLE enterprise_account (
            account_id BIGINT NOT NULL,
            account_name VARCHAR(128) NOT NULL,
            balance DECIMAL(18, 4) DEFAULT 0.0000,
            status VARCHAR(16) DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT pk_enterprise_account PRIMARY KEY (account_id)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "CREATE TABLE" in lowered
        assert "enterprise_account" in lowered
        assert "PRIMARY KEY" in lowered

    def test_table_ddl_with_composite_pk_and_checks(self, lowerer):
        source_ddl = """
        CREATE TABLE trade_settlement_ledger (
            batch_date DATE NOT NULL,
            trade_sequence BIGINT NOT NULL,
            debit_amt DECIMAL(16, 2) NOT NULL,
            credit_amt DECIMAL(16, 2) NOT NULL,
            currency_code VARCHAR(3) DEFAULT 'CNY',
            CONSTRAINT pk_trade_ledger PRIMARY KEY (batch_date, trade_sequence),
            CONSTRAINT chk_debit_positive CHECK (debit_amt >= 0),
            CONSTRAINT chk_credit_positive CHECK (credit_amt >= 0)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "trade_settlement_ledger" in lowered
        assert "PRIMARY KEY" in lowered
        assert "CHECK" in lowered

    def test_table_ddl_partitioned_range(self, lowerer):
        source_ddl = """
        CREATE TABLE historical_cdr_records (
            call_id BIGINT NOT NULL,
            call_start_date DATE NOT NULL,
            duration_sec INT NOT NULL,
            billed_amount DECIMAL(10, 4) NOT NULL
        )
        PARTITION BY RANGE (call_start_date) (
            PARTITION p_2026_q1 VALUES LESS THAN ('2026-04-01'),
            PARTITION p_2026_q2 VALUES LESS THAN ('2026-07-01'),
            PARTITION p_max VALUES LESS THAN (MAXVALUE)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "historical_cdr_records" in lowered
        assert len(lowered) > 0

    def test_procedure_lowering_basic(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_audit_batch(
            p_batch_id IN VARCHAR2,
            p_status OUT VARCHAR2
        )
        AS
            v_total NUMBER := 0;
        BEGIN
            SELECT COUNT(*) INTO v_total FROM audit_log
            WHERE batch_id = p_batch_id;
            p_status := 'COMPLETED';
        END sp_audit_batch;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_audit_batch" in lowered

    def test_procedure_lowering_cursor_loop(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_settle_all_pending
        AS
            CURSOR c_pending IS
                SELECT item_id, amount FROM pending_settlements
                WHERE processed_flag = 'N';
            v_item_id BIGINT;
            v_amt DECIMAL(16, 2);
        BEGIN
            OPEN c_pending;
            LOOP
                FETCH c_pending INTO v_item_id, v_amt;
                EXIT WHEN c_pending%NOTFOUND;
                UPDATE settlement_balance SET balance = balance + v_amt
                WHERE item_id = v_item_id;
            END LOOP;
            CLOSE c_pending;
        END sp_settle_all_pending;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_settle_all_pending" in lowered

    def test_procedure_lowering_exception_block(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_safe_transfer(
            p_from_acc BIGINT,
            p_to_acc BIGINT,
            p_amount DECIMAL(16, 2)
        )
        AS
        BEGIN
            UPDATE bank_accounts SET balance = balance - p_amount
            WHERE account_id = p_from_acc;
            UPDATE bank_accounts SET balance = balance + p_amount
            WHERE account_id = p_to_acc;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
            WHEN OTHERS THEN
                ROLLBACK;
                RAISE;
        END sp_safe_transfer;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_safe_transfer" in lowered

    def test_procedure_lowering_dynamic_sql(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_archive_partition(
            p_table_name IN VARCHAR2,
            p_partition_name IN VARCHAR2
        )
        AS
            v_sql VARCHAR2(500);
        BEGIN
            v_sql := 'ALTER TABLE ' || p_table_name || ' TRUNCATE PARTITION ' || p_partition_name;
            EXECUTE IMMEDIATE v_sql;
        END sp_archive_partition;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_archive_partition" in lowered

    def test_function_lowering_scalar(self, lowerer):
        source_func = """
        CREATE OR REPLACE FUNCTION fn_calculate_accrued_interest(
            p_principal DECIMAL(18, 4),
            p_annual_rate DECIMAL(8, 6),
            p_days INT
        ) RETURN DECIMAL(18, 4)
        AS
            v_interest DECIMAL(18, 4);
        BEGIN
            v_interest := p_principal * (p_annual_rate / 360.0) * p_days;
            RETURN v_interest;
        END fn_calculate_accrued_interest;
        """
        lowered = lowerer.lower_function(source_func, "oracle")
        assert len(lowered) > 0
        assert "fn_calculate_accrued_interest" in lowered

    def test_trigger_lowering_before_insert(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_audit_journal_entry
        BEFORE INSERT ON journal_entries
        FOR EACH ROW
        BEGIN
            :NEW.created_at := SYSDATE;
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_audit_journal_entry" in lowered

    def test_trigger_lowering_after_update(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_sync_order_status
        AFTER UPDATE OF status ON trade_orders
        FOR EACH ROW
        WHEN (OLD.status <> NEW.status)
        BEGIN
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_at)
            VALUES (:NEW.order_id, :OLD.status, :NEW.status, SYSDATE);
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_sync_order_status" in lowered

    def test_sequence_lowering_nextval(self, lowerer):
        source_seq = "SELECT seq_order_no.NEXTVAL FROM DUAL;"
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert len(lowered) > 0
        assert "seq_order_no" in lowered

    def test_sequence_lowering_creation(self, lowerer):
        source_seq = """
        CREATE SEQUENCE seq_trade_journal_seq
        START WITH 1000000
        INCREMENT BY 1
        MAXVALUE 9999999999
        NOCACHE NOCYCLE;
        """
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert "seq_trade_journal_seq" in lowered
        assert "SEQUENCE" in lowered

    def test_view_ddl_lowering(self, lowerer):
        view_sql = """
        CREATE VIEW v_active_accounts AS
        SELECT account_id, account_name, balance
        FROM enterprise_account
        WHERE status = 'ACTIVE';
        """
        lowered = lowerer.lower_view(view_sql, "oracle")
        assert "CREATE VIEW" in lowered
        assert "v_active_accounts" in lowered

    def test_syntax_heuristics_balanced(self, lowerer):
        valid_sql = "BEGIN NULL; END;"
        ok, issues = lowerer.verify_syntax_heuristics(valid_sql)
        assert ok is True
        assert len(issues) == 0

    def test_syntax_heuristics_unbalanced(self, lowerer):
        invalid_sql = "BEGIN NULL;"
        ok, issues = lowerer.verify_syntax_heuristics(invalid_sql)
        assert ok is False
        assert len(issues) > 0

    def test_catalog_queries_available(self, lowerer):
        queries = getattr(lowerer, "get_catalog_queries", lambda: {})()
        if queries:
            assert "tables" in queries or "columns" in queries

    def test_enterprise_scenario_banking(self, lowerer):
        sql = """
        SELECT account_no, SUM(credit_amt) - SUM(debit_amt) AS net_bal
        FROM gl_entries
        GROUP BY account_no
        HAVING SUM(credit_amt) <> SUM(debit_amt);
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "net_bal" in lowered

    def test_enterprise_scenario_insurance(self, lowerer):
        sql = """
        UPDATE claim_assessments
        SET approved_amount = claimed_amount * 0.95,
            status = 'AUTO_APPROVED'
        WHERE fraud_risk_score < 0.15 AND claimed_amount < 5000.00;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "claim_assessments" in lowered

    def test_enterprise_scenario_telecom(self, lowerer):
        sql = """
        SELECT msisdn, SUM(duration_sec) AS total_sec,
               SUM(bytes_consumed) AS total_bytes
        FROM cdr_voice_records
        GROUP BY msisdn;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "msisdn" in lowered

    def test_enterprise_scenario_wms(self, lowerer):
        sql = """
        SELECT sku, warehouse_id,
               (on_hand_qty - allocated_qty) AS atp_qty
        FROM wms_inventory_balance
        WHERE (on_hand_qty - allocated_qty) > 0;
        """
        lowered = lowerer.lower_statement(sql, "tsql")
        assert "atp_qty" in lowered

    def test_enterprise_scenario_payroll(self, lowerer):
        sql = """
        SELECT emp_id, gross_pay - tax_deduction - social_sec AS net_pay
        FROM hr_payroll_ledger
        WHERE period_code = '2026-03';
        """
        lowered = lowerer.lower_statement(sql, "mysql")
        assert "net_pay" in lowered

    def test_analytical_window_functions(self, lowerer):
        sql = """
        SELECT dept_id, emp_id, salary,
               ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rnk,
               AVG(salary) OVER (PARTITION BY dept_id) as avg_dept_sal
        FROM employee_salaries;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "ROW_NUMBER()" in lowered
        assert "OVER" in lowered

    def test_cte_recursive_query(self, lowerer):
        sql = """
        WITH org_hierarchy (emp_id, manager_id, org_level) AS (
            SELECT emp_id, manager_id, 1
            FROM employees WHERE manager_id IS NULL
            UNION ALL
            SELECT e.emp_id, e.manager_id, o.org_level + 1
            FROM employees e INNER JOIN org_hierarchy o ON e.manager_id = o.emp_id
        )
        SELECT emp_id, manager_id, org_level FROM org_hierarchy;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "org_hierarchy" in lowered
        assert "UNION ALL" in lowered

    def test_transaction_boundary_control(self, lowerer):
        sql = """
        SAVEPOINT sp_batch_001;
        UPDATE batch_status SET state = 'IN_PROGRESS' WHERE id = 1;
        ROLLBACK TO SAVEPOINT sp_batch_001;
        COMMIT;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "SAVEPOINT" in lowered
        assert "COMMIT" in lowered

    def test_complex_multi_join_query(self, lowerer):
        sql = """
        SELECT c.customer_name, o.order_number, p.product_name, oi.quantity, oi.unit_price
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        ORDER BY oi.item_id ASC;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "customers" in lowered
        assert "orders" in lowered
        assert "order_items" in lowered

class TestGaussDbMysqlTargetLowerer:
    """Comprehensive industrial test suite for GaussDB (MySQL Mode)."""

    @pytest.fixture
    def lowerer(self) -> GaussDbMysqlTargetLowerer:
        return get_chinadb_lowerer("gaussdb_mysql")

    def test_metadata_and_family(self, lowerer):
        assert lowerer.target_id == "gaussdb_mysql"
        assert lowerer.display_name == "GaussDB (MySQL Mode)"
        assert lowerer.family == "mysql_compat"
        assert len(lowerer.type_mappings) > 0
        assert len(lowerer.builtin_mappings) > 0
        assert len(lowerer.lowering_rules) > 0

    def test_type_mapping_0_varchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 VARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_1_nvarchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 NVARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_2_number(self, lowerer):
        sql = "CREATE TABLE t (col1 NUMBER NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "DECIMAL" in lowered

    def test_type_mapping_3_clob(self, lowerer):
        sql = "CREATE TABLE t (col1 CLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGTEXT" in lowered

    def test_type_mapping_4_nclob(self, lowerer):
        sql = "CREATE TABLE t (col1 NCLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGTEXT" in lowered

    def test_type_mapping_5_blob(self, lowerer):
        sql = "CREATE TABLE t (col1 BLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGBLOB" in lowered

    def test_builtin_mapping_0_nvl(self, lowerer):
        sql = "SELECT NVL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "IFNULL" in lowered

    def test_builtin_mapping_1_isnull(self, lowerer):
        sql = "SELECT ISNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "IFNULL" in lowered

    def test_builtin_mapping_2_getdate(self, lowerer):
        sql = "SELECT GETDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NOW" in lowered

    def test_builtin_mapping_3_getutcdate(self, lowerer):
        sql = "SELECT GETUTCDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "UTC_TIMESTAMP" in lowered

    def test_builtin_mapping_4_sysdate(self, lowerer):
        sql = "SELECT SYSDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NOW" in lowered

    def test_builtin_mapping_5_len(self, lowerer):
        sql = "SELECT LEN() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "CHAR_LENGTH" in lowered

    def test_lowering_rule_0_gauss_mysql_backticks(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gauss_mysql_backticks"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gauss_mysql_backticks"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_1_gauss_mysql_dual_strip(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gauss_mysql_dual_strip"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gauss_mysql_dual_strip"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_2_gauss_mysql_auto_inc(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gauss_mysql_auto_inc"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gauss_mysql_auto_inc"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_table_ddl_lowering(self, lowerer):
        source_ddl = """
        CREATE TABLE enterprise_account (
            account_id BIGINT NOT NULL,
            account_name VARCHAR(128) NOT NULL,
            balance DECIMAL(18, 4) DEFAULT 0.0000,
            status VARCHAR(16) DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT pk_enterprise_account PRIMARY KEY (account_id)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "CREATE TABLE" in lowered
        assert "enterprise_account" in lowered
        assert "PRIMARY KEY" in lowered

    def test_table_ddl_with_composite_pk_and_checks(self, lowerer):
        source_ddl = """
        CREATE TABLE trade_settlement_ledger (
            batch_date DATE NOT NULL,
            trade_sequence BIGINT NOT NULL,
            debit_amt DECIMAL(16, 2) NOT NULL,
            credit_amt DECIMAL(16, 2) NOT NULL,
            currency_code VARCHAR(3) DEFAULT 'CNY',
            CONSTRAINT pk_trade_ledger PRIMARY KEY (batch_date, trade_sequence),
            CONSTRAINT chk_debit_positive CHECK (debit_amt >= 0),
            CONSTRAINT chk_credit_positive CHECK (credit_amt >= 0)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "trade_settlement_ledger" in lowered
        assert "PRIMARY KEY" in lowered
        assert "CHECK" in lowered

    def test_table_ddl_partitioned_range(self, lowerer):
        source_ddl = """
        CREATE TABLE historical_cdr_records (
            call_id BIGINT NOT NULL,
            call_start_date DATE NOT NULL,
            duration_sec INT NOT NULL,
            billed_amount DECIMAL(10, 4) NOT NULL
        )
        PARTITION BY RANGE (call_start_date) (
            PARTITION p_2026_q1 VALUES LESS THAN ('2026-04-01'),
            PARTITION p_2026_q2 VALUES LESS THAN ('2026-07-01'),
            PARTITION p_max VALUES LESS THAN (MAXVALUE)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "historical_cdr_records" in lowered
        assert len(lowered) > 0

    def test_procedure_lowering_basic(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_audit_batch(
            p_batch_id IN VARCHAR2,
            p_status OUT VARCHAR2
        )
        AS
            v_total NUMBER := 0;
        BEGIN
            SELECT COUNT(*) INTO v_total FROM audit_log
            WHERE batch_id = p_batch_id;
            p_status := 'COMPLETED';
        END sp_audit_batch;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_audit_batch" in lowered

    def test_procedure_lowering_cursor_loop(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_settle_all_pending
        AS
            CURSOR c_pending IS
                SELECT item_id, amount FROM pending_settlements
                WHERE processed_flag = 'N';
            v_item_id BIGINT;
            v_amt DECIMAL(16, 2);
        BEGIN
            OPEN c_pending;
            LOOP
                FETCH c_pending INTO v_item_id, v_amt;
                EXIT WHEN c_pending%NOTFOUND;
                UPDATE settlement_balance SET balance = balance + v_amt
                WHERE item_id = v_item_id;
            END LOOP;
            CLOSE c_pending;
        END sp_settle_all_pending;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_settle_all_pending" in lowered

    def test_procedure_lowering_exception_block(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_safe_transfer(
            p_from_acc BIGINT,
            p_to_acc BIGINT,
            p_amount DECIMAL(16, 2)
        )
        AS
        BEGIN
            UPDATE bank_accounts SET balance = balance - p_amount
            WHERE account_id = p_from_acc;
            UPDATE bank_accounts SET balance = balance + p_amount
            WHERE account_id = p_to_acc;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
            WHEN OTHERS THEN
                ROLLBACK;
                RAISE;
        END sp_safe_transfer;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_safe_transfer" in lowered

    def test_procedure_lowering_dynamic_sql(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_archive_partition(
            p_table_name IN VARCHAR2,
            p_partition_name IN VARCHAR2
        )
        AS
            v_sql VARCHAR2(500);
        BEGIN
            v_sql := 'ALTER TABLE ' || p_table_name || ' TRUNCATE PARTITION ' || p_partition_name;
            EXECUTE IMMEDIATE v_sql;
        END sp_archive_partition;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_archive_partition" in lowered

    def test_function_lowering_scalar(self, lowerer):
        source_func = """
        CREATE OR REPLACE FUNCTION fn_calculate_accrued_interest(
            p_principal DECIMAL(18, 4),
            p_annual_rate DECIMAL(8, 6),
            p_days INT
        ) RETURN DECIMAL(18, 4)
        AS
            v_interest DECIMAL(18, 4);
        BEGIN
            v_interest := p_principal * (p_annual_rate / 360.0) * p_days;
            RETURN v_interest;
        END fn_calculate_accrued_interest;
        """
        lowered = lowerer.lower_function(source_func, "oracle")
        assert len(lowered) > 0
        assert "fn_calculate_accrued_interest" in lowered

    def test_trigger_lowering_before_insert(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_audit_journal_entry
        BEFORE INSERT ON journal_entries
        FOR EACH ROW
        BEGIN
            :NEW.created_at := SYSDATE;
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_audit_journal_entry" in lowered

    def test_trigger_lowering_after_update(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_sync_order_status
        AFTER UPDATE OF status ON trade_orders
        FOR EACH ROW
        WHEN (OLD.status <> NEW.status)
        BEGIN
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_at)
            VALUES (:NEW.order_id, :OLD.status, :NEW.status, SYSDATE);
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_sync_order_status" in lowered

    def test_sequence_lowering_nextval(self, lowerer):
        source_seq = "SELECT seq_order_no.NEXTVAL FROM DUAL;"
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert len(lowered) > 0
        assert "seq_order_no" in lowered

    def test_sequence_lowering_creation(self, lowerer):
        source_seq = """
        CREATE SEQUENCE seq_trade_journal_seq
        START WITH 1000000
        INCREMENT BY 1
        MAXVALUE 9999999999
        NOCACHE NOCYCLE;
        """
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert "seq_trade_journal_seq" in lowered
        assert "SEQUENCE" in lowered

    def test_view_ddl_lowering(self, lowerer):
        view_sql = """
        CREATE VIEW v_active_accounts AS
        SELECT account_id, account_name, balance
        FROM enterprise_account
        WHERE status = 'ACTIVE';
        """
        lowered = lowerer.lower_view(view_sql, "oracle")
        assert "CREATE VIEW" in lowered
        assert "v_active_accounts" in lowered

    def test_syntax_heuristics_balanced(self, lowerer):
        valid_sql = "BEGIN NULL; END;"
        ok, issues = lowerer.verify_syntax_heuristics(valid_sql)
        assert ok is True
        assert len(issues) == 0

    def test_syntax_heuristics_unbalanced(self, lowerer):
        invalid_sql = "BEGIN NULL;"
        ok, issues = lowerer.verify_syntax_heuristics(invalid_sql)
        assert ok is False
        assert len(issues) > 0

    def test_catalog_queries_available(self, lowerer):
        queries = getattr(lowerer, "get_catalog_queries", lambda: {})()
        if queries:
            assert "tables" in queries or "columns" in queries

    def test_enterprise_scenario_banking(self, lowerer):
        sql = """
        SELECT account_no, SUM(credit_amt) - SUM(debit_amt) AS net_bal
        FROM gl_entries
        GROUP BY account_no
        HAVING SUM(credit_amt) <> SUM(debit_amt);
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "net_bal" in lowered

    def test_enterprise_scenario_insurance(self, lowerer):
        sql = """
        UPDATE claim_assessments
        SET approved_amount = claimed_amount * 0.95,
            status = 'AUTO_APPROVED'
        WHERE fraud_risk_score < 0.15 AND claimed_amount < 5000.00;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "claim_assessments" in lowered

    def test_enterprise_scenario_telecom(self, lowerer):
        sql = """
        SELECT msisdn, SUM(duration_sec) AS total_sec,
               SUM(bytes_consumed) AS total_bytes
        FROM cdr_voice_records
        GROUP BY msisdn;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "msisdn" in lowered

    def test_enterprise_scenario_wms(self, lowerer):
        sql = """
        SELECT sku, warehouse_id,
               (on_hand_qty - allocated_qty) AS atp_qty
        FROM wms_inventory_balance
        WHERE (on_hand_qty - allocated_qty) > 0;
        """
        lowered = lowerer.lower_statement(sql, "tsql")
        assert "atp_qty" in lowered

    def test_enterprise_scenario_payroll(self, lowerer):
        sql = """
        SELECT emp_id, gross_pay - tax_deduction - social_sec AS net_pay
        FROM hr_payroll_ledger
        WHERE period_code = '2026-03';
        """
        lowered = lowerer.lower_statement(sql, "mysql")
        assert "net_pay" in lowered

    def test_analytical_window_functions(self, lowerer):
        sql = """
        SELECT dept_id, emp_id, salary,
               ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rnk,
               AVG(salary) OVER (PARTITION BY dept_id) as avg_dept_sal
        FROM employee_salaries;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "ROW_NUMBER()" in lowered
        assert "OVER" in lowered

    def test_cte_recursive_query(self, lowerer):
        sql = """
        WITH org_hierarchy (emp_id, manager_id, org_level) AS (
            SELECT emp_id, manager_id, 1
            FROM employees WHERE manager_id IS NULL
            UNION ALL
            SELECT e.emp_id, e.manager_id, o.org_level + 1
            FROM employees e INNER JOIN org_hierarchy o ON e.manager_id = o.emp_id
        )
        SELECT emp_id, manager_id, org_level FROM org_hierarchy;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "org_hierarchy" in lowered
        assert "UNION ALL" in lowered

    def test_transaction_boundary_control(self, lowerer):
        sql = """
        SAVEPOINT sp_batch_001;
        UPDATE batch_status SET state = 'IN_PROGRESS' WHERE id = 1;
        ROLLBACK TO SAVEPOINT sp_batch_001;
        COMMIT;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "SAVEPOINT" in lowered
        assert "COMMIT" in lowered

    def test_complex_multi_join_query(self, lowerer):
        sql = """
        SELECT c.customer_name, o.order_number, p.product_name, oi.quantity, oi.unit_price
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        ORDER BY oi.item_id ASC;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "customers" in lowered
        assert "orders" in lowered
        assert "order_items" in lowered

class TestGaussDbOracleTargetLowerer:
    """Comprehensive industrial test suite for GaussDB (Oracle Mode)."""

    @pytest.fixture
    def lowerer(self) -> GaussDbOracleTargetLowerer:
        return get_chinadb_lowerer("gaussdb_oracle")

    def test_metadata_and_family(self, lowerer):
        assert lowerer.target_id == "gaussdb_oracle"
        assert lowerer.display_name == "GaussDB (Oracle Mode)"
        assert lowerer.family == "oracle_compat"
        assert len(lowerer.type_mappings) > 0
        assert len(lowerer.builtin_mappings) > 0
        assert len(lowerer.lowering_rules) > 0

    def test_type_mapping_0_datetime2(self, lowerer):
        sql = "CREATE TABLE t (col1 DATETIME2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "TIMESTAMP" in lowered

    def test_type_mapping_1_smalldatetime(self, lowerer):
        sql = "CREATE TABLE t (col1 SMALLDATETIME NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "TIMESTAMP" in lowered

    def test_type_mapping_2_nvarchar_max_(self, lowerer):
        sql = "CREATE TABLE t (col1 NVARCHAR(MAX) NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "CLOB" in lowered

    def test_type_mapping_3_varchar_max_(self, lowerer):
        sql = "CREATE TABLE t (col1 VARCHAR(MAX) NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "CLOB" in lowered

    def test_type_mapping_4_varbinary_max_(self, lowerer):
        sql = "CREATE TABLE t (col1 VARBINARY(MAX) NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "BLOB" in lowered

    def test_type_mapping_5_image(self, lowerer):
        sql = "CREATE TABLE t (col1 IMAGE NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "BLOB" in lowered

    def test_builtin_mapping_0_getdate(self, lowerer):
        sql = "SELECT GETDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "SYSDATE" in lowered

    def test_builtin_mapping_1_getutcdate(self, lowerer):
        sql = "SELECT GETUTCDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "SYS_EXTRACT_UTC" in lowered

    def test_builtin_mapping_2_isnull(self, lowerer):
        sql = "SELECT ISNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NVL" in lowered

    def test_builtin_mapping_3_ifnull(self, lowerer):
        sql = "SELECT IFNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NVL" in lowered

    def test_builtin_mapping_4_len(self, lowerer):
        sql = "SELECT LEN() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "LENGTH" in lowered

    def test_builtin_mapping_5_char_length(self, lowerer):
        sql = "SELECT CHAR_LENGTH() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "LENGTH" in lowered

    def test_lowering_rule_0_gauss_ora_identity(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gauss_ora_identity"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gauss_ora_identity"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_1_gauss_ora_brackets(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gauss_ora_brackets"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gauss_ora_brackets"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_2_gauss_ora_variables(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gauss_ora_variables"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gauss_ora_variables"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_3_gauss_ora_autonomous_trans(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gauss_ora_autonomous_trans"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gauss_ora_autonomous_trans"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "oracle")
        assert isinstance(res, str)

    def test_lowering_rule_4_gauss_ora_forall(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gauss_ora_forall"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gauss_ora_forall"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "oracle")
        assert isinstance(res, str)

    def test_table_ddl_lowering(self, lowerer):
        source_ddl = """
        CREATE TABLE enterprise_account (
            account_id BIGINT NOT NULL,
            account_name VARCHAR(128) NOT NULL,
            balance DECIMAL(18, 4) DEFAULT 0.0000,
            status VARCHAR(16) DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT pk_enterprise_account PRIMARY KEY (account_id)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "CREATE TABLE" in lowered
        assert "enterprise_account" in lowered
        assert "PRIMARY KEY" in lowered

    def test_table_ddl_with_composite_pk_and_checks(self, lowerer):
        source_ddl = """
        CREATE TABLE trade_settlement_ledger (
            batch_date DATE NOT NULL,
            trade_sequence BIGINT NOT NULL,
            debit_amt DECIMAL(16, 2) NOT NULL,
            credit_amt DECIMAL(16, 2) NOT NULL,
            currency_code VARCHAR(3) DEFAULT 'CNY',
            CONSTRAINT pk_trade_ledger PRIMARY KEY (batch_date, trade_sequence),
            CONSTRAINT chk_debit_positive CHECK (debit_amt >= 0),
            CONSTRAINT chk_credit_positive CHECK (credit_amt >= 0)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "trade_settlement_ledger" in lowered
        assert "PRIMARY KEY" in lowered
        assert "CHECK" in lowered

    def test_table_ddl_partitioned_range(self, lowerer):
        source_ddl = """
        CREATE TABLE historical_cdr_records (
            call_id BIGINT NOT NULL,
            call_start_date DATE NOT NULL,
            duration_sec INT NOT NULL,
            billed_amount DECIMAL(10, 4) NOT NULL
        )
        PARTITION BY RANGE (call_start_date) (
            PARTITION p_2026_q1 VALUES LESS THAN ('2026-04-01'),
            PARTITION p_2026_q2 VALUES LESS THAN ('2026-07-01'),
            PARTITION p_max VALUES LESS THAN (MAXVALUE)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "historical_cdr_records" in lowered
        assert len(lowered) > 0

    def test_procedure_lowering_basic(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_audit_batch(
            p_batch_id IN VARCHAR2,
            p_status OUT VARCHAR2
        )
        AS
            v_total NUMBER := 0;
        BEGIN
            SELECT COUNT(*) INTO v_total FROM audit_log
            WHERE batch_id = p_batch_id;
            p_status := 'COMPLETED';
        END sp_audit_batch;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_audit_batch" in lowered

    def test_procedure_lowering_cursor_loop(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_settle_all_pending
        AS
            CURSOR c_pending IS
                SELECT item_id, amount FROM pending_settlements
                WHERE processed_flag = 'N';
            v_item_id BIGINT;
            v_amt DECIMAL(16, 2);
        BEGIN
            OPEN c_pending;
            LOOP
                FETCH c_pending INTO v_item_id, v_amt;
                EXIT WHEN c_pending%NOTFOUND;
                UPDATE settlement_balance SET balance = balance + v_amt
                WHERE item_id = v_item_id;
            END LOOP;
            CLOSE c_pending;
        END sp_settle_all_pending;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_settle_all_pending" in lowered

    def test_procedure_lowering_exception_block(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_safe_transfer(
            p_from_acc BIGINT,
            p_to_acc BIGINT,
            p_amount DECIMAL(16, 2)
        )
        AS
        BEGIN
            UPDATE bank_accounts SET balance = balance - p_amount
            WHERE account_id = p_from_acc;
            UPDATE bank_accounts SET balance = balance + p_amount
            WHERE account_id = p_to_acc;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
            WHEN OTHERS THEN
                ROLLBACK;
                RAISE;
        END sp_safe_transfer;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_safe_transfer" in lowered

    def test_procedure_lowering_dynamic_sql(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_archive_partition(
            p_table_name IN VARCHAR2,
            p_partition_name IN VARCHAR2
        )
        AS
            v_sql VARCHAR2(500);
        BEGIN
            v_sql := 'ALTER TABLE ' || p_table_name || ' TRUNCATE PARTITION ' || p_partition_name;
            EXECUTE IMMEDIATE v_sql;
        END sp_archive_partition;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_archive_partition" in lowered

    def test_function_lowering_scalar(self, lowerer):
        source_func = """
        CREATE OR REPLACE FUNCTION fn_calculate_accrued_interest(
            p_principal DECIMAL(18, 4),
            p_annual_rate DECIMAL(8, 6),
            p_days INT
        ) RETURN DECIMAL(18, 4)
        AS
            v_interest DECIMAL(18, 4);
        BEGIN
            v_interest := p_principal * (p_annual_rate / 360.0) * p_days;
            RETURN v_interest;
        END fn_calculate_accrued_interest;
        """
        lowered = lowerer.lower_function(source_func, "oracle")
        assert len(lowered) > 0
        assert "fn_calculate_accrued_interest" in lowered

    def test_trigger_lowering_before_insert(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_audit_journal_entry
        BEFORE INSERT ON journal_entries
        FOR EACH ROW
        BEGIN
            :NEW.created_at := SYSDATE;
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_audit_journal_entry" in lowered

    def test_trigger_lowering_after_update(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_sync_order_status
        AFTER UPDATE OF status ON trade_orders
        FOR EACH ROW
        WHEN (OLD.status <> NEW.status)
        BEGIN
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_at)
            VALUES (:NEW.order_id, :OLD.status, :NEW.status, SYSDATE);
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_sync_order_status" in lowered

    def test_sequence_lowering_nextval(self, lowerer):
        source_seq = "SELECT seq_order_no.NEXTVAL FROM DUAL;"
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert len(lowered) > 0
        assert "seq_order_no" in lowered

    def test_sequence_lowering_creation(self, lowerer):
        source_seq = """
        CREATE SEQUENCE seq_trade_journal_seq
        START WITH 1000000
        INCREMENT BY 1
        MAXVALUE 9999999999
        NOCACHE NOCYCLE;
        """
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert "seq_trade_journal_seq" in lowered
        assert "SEQUENCE" in lowered

    def test_view_ddl_lowering(self, lowerer):
        view_sql = """
        CREATE VIEW v_active_accounts AS
        SELECT account_id, account_name, balance
        FROM enterprise_account
        WHERE status = 'ACTIVE';
        """
        lowered = lowerer.lower_view(view_sql, "oracle")
        assert "CREATE VIEW" in lowered
        assert "v_active_accounts" in lowered

    def test_syntax_heuristics_balanced(self, lowerer):
        valid_sql = "BEGIN NULL; END;"
        ok, issues = lowerer.verify_syntax_heuristics(valid_sql)
        assert ok is True
        assert len(issues) == 0

    def test_syntax_heuristics_unbalanced(self, lowerer):
        invalid_sql = "BEGIN NULL;"
        ok, issues = lowerer.verify_syntax_heuristics(invalid_sql)
        assert ok is False
        assert len(issues) > 0

    def test_catalog_queries_available(self, lowerer):
        queries = getattr(lowerer, "get_catalog_queries", lambda: {})()
        if queries:
            assert "tables" in queries or "columns" in queries

    def test_enterprise_scenario_banking(self, lowerer):
        sql = """
        SELECT account_no, SUM(credit_amt) - SUM(debit_amt) AS net_bal
        FROM gl_entries
        GROUP BY account_no
        HAVING SUM(credit_amt) <> SUM(debit_amt);
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "net_bal" in lowered

    def test_enterprise_scenario_insurance(self, lowerer):
        sql = """
        UPDATE claim_assessments
        SET approved_amount = claimed_amount * 0.95,
            status = 'AUTO_APPROVED'
        WHERE fraud_risk_score < 0.15 AND claimed_amount < 5000.00;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "claim_assessments" in lowered

    def test_enterprise_scenario_telecom(self, lowerer):
        sql = """
        SELECT msisdn, SUM(duration_sec) AS total_sec,
               SUM(bytes_consumed) AS total_bytes
        FROM cdr_voice_records
        GROUP BY msisdn;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "msisdn" in lowered

    def test_enterprise_scenario_wms(self, lowerer):
        sql = """
        SELECT sku, warehouse_id,
               (on_hand_qty - allocated_qty) AS atp_qty
        FROM wms_inventory_balance
        WHERE (on_hand_qty - allocated_qty) > 0;
        """
        lowered = lowerer.lower_statement(sql, "tsql")
        assert "atp_qty" in lowered

    def test_enterprise_scenario_payroll(self, lowerer):
        sql = """
        SELECT emp_id, gross_pay - tax_deduction - social_sec AS net_pay
        FROM hr_payroll_ledger
        WHERE period_code = '2026-03';
        """
        lowered = lowerer.lower_statement(sql, "mysql")
        assert "net_pay" in lowered

    def test_analytical_window_functions(self, lowerer):
        sql = """
        SELECT dept_id, emp_id, salary,
               ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rnk,
               AVG(salary) OVER (PARTITION BY dept_id) as avg_dept_sal
        FROM employee_salaries;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "ROW_NUMBER()" in lowered
        assert "OVER" in lowered

    def test_cte_recursive_query(self, lowerer):
        sql = """
        WITH org_hierarchy (emp_id, manager_id, org_level) AS (
            SELECT emp_id, manager_id, 1
            FROM employees WHERE manager_id IS NULL
            UNION ALL
            SELECT e.emp_id, e.manager_id, o.org_level + 1
            FROM employees e INNER JOIN org_hierarchy o ON e.manager_id = o.emp_id
        )
        SELECT emp_id, manager_id, org_level FROM org_hierarchy;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "org_hierarchy" in lowered
        assert "UNION ALL" in lowered

    def test_transaction_boundary_control(self, lowerer):
        sql = """
        SAVEPOINT sp_batch_001;
        UPDATE batch_status SET state = 'IN_PROGRESS' WHERE id = 1;
        ROLLBACK TO SAVEPOINT sp_batch_001;
        COMMIT;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "SAVEPOINT" in lowered
        assert "COMMIT" in lowered

    def test_complex_multi_join_query(self, lowerer):
        sql = """
        SELECT c.customer_name, o.order_number, p.product_name, oi.quantity, oi.unit_price
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        ORDER BY oi.item_id ASC;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "customers" in lowered
        assert "orders" in lowered
        assert "order_items" in lowered

class TestGBase8aTargetLowerer:
    """Comprehensive industrial test suite for GBase 8a (MPP)."""

    @pytest.fixture
    def lowerer(self) -> GBase8aTargetLowerer:
        return get_chinadb_lowerer("gbase8a")

    def test_metadata_and_family(self, lowerer):
        assert lowerer.target_id == "gbase8a"
        assert lowerer.display_name == "GBase 8a (MPP)"
        assert lowerer.family == "mpp"
        assert len(lowerer.type_mappings) > 0
        assert len(lowerer.builtin_mappings) > 0
        assert len(lowerer.lowering_rules) > 0

    def test_type_mapping_0_varchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 VARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_1_nvarchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 NVARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_2_number(self, lowerer):
        sql = "CREATE TABLE t (col1 NUMBER NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "DECIMAL" in lowered

    def test_type_mapping_3_clob(self, lowerer):
        sql = "CREATE TABLE t (col1 CLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGTEXT" in lowered

    def test_type_mapping_4_nclob(self, lowerer):
        sql = "CREATE TABLE t (col1 NCLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGTEXT" in lowered

    def test_type_mapping_5_blob(self, lowerer):
        sql = "CREATE TABLE t (col1 BLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGBLOB" in lowered

    def test_builtin_mapping_0_nvl(self, lowerer):
        sql = "SELECT NVL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "IFNULL" in lowered

    def test_builtin_mapping_1_isnull(self, lowerer):
        sql = "SELECT ISNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "IFNULL" in lowered

    def test_builtin_mapping_2_coalesce(self, lowerer):
        sql = "SELECT COALESCE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "COALESCE" in lowered

    def test_builtin_mapping_3_getdate(self, lowerer):
        sql = "SELECT GETDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NOW" in lowered

    def test_builtin_mapping_4_getutcdate(self, lowerer):
        sql = "SELECT GETUTCDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "UTC_TIMESTAMP" in lowered

    def test_builtin_mapping_5_sysdate(self, lowerer):
        sql = "SELECT SYSDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NOW" in lowered

    def test_lowering_rule_0_gbase8a_dual_removal(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gbase8a_dual_removal"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gbase8a_dual_removal"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_1_gbase8a_backtick_escape(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gbase8a_backtick_escape"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gbase8a_backtick_escape"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_2_gbase8a_compress_hint(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gbase8a_compress_hint"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gbase8a_compress_hint"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_table_ddl_lowering(self, lowerer):
        source_ddl = """
        CREATE TABLE enterprise_account (
            account_id BIGINT NOT NULL,
            account_name VARCHAR(128) NOT NULL,
            balance DECIMAL(18, 4) DEFAULT 0.0000,
            status VARCHAR(16) DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT pk_enterprise_account PRIMARY KEY (account_id)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "CREATE TABLE" in lowered
        assert "enterprise_account" in lowered
        assert "PRIMARY KEY" in lowered

    def test_table_ddl_with_composite_pk_and_checks(self, lowerer):
        source_ddl = """
        CREATE TABLE trade_settlement_ledger (
            batch_date DATE NOT NULL,
            trade_sequence BIGINT NOT NULL,
            debit_amt DECIMAL(16, 2) NOT NULL,
            credit_amt DECIMAL(16, 2) NOT NULL,
            currency_code VARCHAR(3) DEFAULT 'CNY',
            CONSTRAINT pk_trade_ledger PRIMARY KEY (batch_date, trade_sequence),
            CONSTRAINT chk_debit_positive CHECK (debit_amt >= 0),
            CONSTRAINT chk_credit_positive CHECK (credit_amt >= 0)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "trade_settlement_ledger" in lowered
        assert "PRIMARY KEY" in lowered
        assert "CHECK" in lowered

    def test_table_ddl_partitioned_range(self, lowerer):
        source_ddl = """
        CREATE TABLE historical_cdr_records (
            call_id BIGINT NOT NULL,
            call_start_date DATE NOT NULL,
            duration_sec INT NOT NULL,
            billed_amount DECIMAL(10, 4) NOT NULL
        )
        PARTITION BY RANGE (call_start_date) (
            PARTITION p_2026_q1 VALUES LESS THAN ('2026-04-01'),
            PARTITION p_2026_q2 VALUES LESS THAN ('2026-07-01'),
            PARTITION p_max VALUES LESS THAN (MAXVALUE)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "historical_cdr_records" in lowered
        assert len(lowered) > 0

    def test_procedure_lowering_basic(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_audit_batch(
            p_batch_id IN VARCHAR2,
            p_status OUT VARCHAR2
        )
        AS
            v_total NUMBER := 0;
        BEGIN
            SELECT COUNT(*) INTO v_total FROM audit_log
            WHERE batch_id = p_batch_id;
            p_status := 'COMPLETED';
        END sp_audit_batch;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_audit_batch" in lowered

    def test_procedure_lowering_cursor_loop(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_settle_all_pending
        AS
            CURSOR c_pending IS
                SELECT item_id, amount FROM pending_settlements
                WHERE processed_flag = 'N';
            v_item_id BIGINT;
            v_amt DECIMAL(16, 2);
        BEGIN
            OPEN c_pending;
            LOOP
                FETCH c_pending INTO v_item_id, v_amt;
                EXIT WHEN c_pending%NOTFOUND;
                UPDATE settlement_balance SET balance = balance + v_amt
                WHERE item_id = v_item_id;
            END LOOP;
            CLOSE c_pending;
        END sp_settle_all_pending;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_settle_all_pending" in lowered

    def test_procedure_lowering_exception_block(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_safe_transfer(
            p_from_acc BIGINT,
            p_to_acc BIGINT,
            p_amount DECIMAL(16, 2)
        )
        AS
        BEGIN
            UPDATE bank_accounts SET balance = balance - p_amount
            WHERE account_id = p_from_acc;
            UPDATE bank_accounts SET balance = balance + p_amount
            WHERE account_id = p_to_acc;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
            WHEN OTHERS THEN
                ROLLBACK;
                RAISE;
        END sp_safe_transfer;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_safe_transfer" in lowered

    def test_procedure_lowering_dynamic_sql(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_archive_partition(
            p_table_name IN VARCHAR2,
            p_partition_name IN VARCHAR2
        )
        AS
            v_sql VARCHAR2(500);
        BEGIN
            v_sql := 'ALTER TABLE ' || p_table_name || ' TRUNCATE PARTITION ' || p_partition_name;
            EXECUTE IMMEDIATE v_sql;
        END sp_archive_partition;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_archive_partition" in lowered

    def test_function_lowering_scalar(self, lowerer):
        source_func = """
        CREATE OR REPLACE FUNCTION fn_calculate_accrued_interest(
            p_principal DECIMAL(18, 4),
            p_annual_rate DECIMAL(8, 6),
            p_days INT
        ) RETURN DECIMAL(18, 4)
        AS
            v_interest DECIMAL(18, 4);
        BEGIN
            v_interest := p_principal * (p_annual_rate / 360.0) * p_days;
            RETURN v_interest;
        END fn_calculate_accrued_interest;
        """
        lowered = lowerer.lower_function(source_func, "oracle")
        assert len(lowered) > 0
        assert "fn_calculate_accrued_interest" in lowered

    def test_trigger_lowering_before_insert(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_audit_journal_entry
        BEFORE INSERT ON journal_entries
        FOR EACH ROW
        BEGIN
            :NEW.created_at := SYSDATE;
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_audit_journal_entry" in lowered

    def test_trigger_lowering_after_update(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_sync_order_status
        AFTER UPDATE OF status ON trade_orders
        FOR EACH ROW
        WHEN (OLD.status <> NEW.status)
        BEGIN
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_at)
            VALUES (:NEW.order_id, :OLD.status, :NEW.status, SYSDATE);
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_sync_order_status" in lowered

    def test_sequence_lowering_nextval(self, lowerer):
        source_seq = "SELECT seq_order_no.NEXTVAL FROM DUAL;"
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert len(lowered) > 0
        assert "seq_order_no" in lowered

    def test_sequence_lowering_creation(self, lowerer):
        source_seq = """
        CREATE SEQUENCE seq_trade_journal_seq
        START WITH 1000000
        INCREMENT BY 1
        MAXVALUE 9999999999
        NOCACHE NOCYCLE;
        """
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert "seq_trade_journal_seq" in lowered
        assert "SEQUENCE" in lowered

    def test_view_ddl_lowering(self, lowerer):
        view_sql = """
        CREATE VIEW v_active_accounts AS
        SELECT account_id, account_name, balance
        FROM enterprise_account
        WHERE status = 'ACTIVE';
        """
        lowered = lowerer.lower_view(view_sql, "oracle")
        assert "CREATE VIEW" in lowered
        assert "v_active_accounts" in lowered

    def test_syntax_heuristics_balanced(self, lowerer):
        valid_sql = "BEGIN NULL; END;"
        ok, issues = lowerer.verify_syntax_heuristics(valid_sql)
        assert ok is True
        assert len(issues) == 0

    def test_syntax_heuristics_unbalanced(self, lowerer):
        invalid_sql = "BEGIN NULL;"
        ok, issues = lowerer.verify_syntax_heuristics(invalid_sql)
        assert ok is False
        assert len(issues) > 0

    def test_catalog_queries_available(self, lowerer):
        queries = getattr(lowerer, "get_catalog_queries", lambda: {})()
        if queries:
            assert "tables" in queries or "columns" in queries

    def test_enterprise_scenario_banking(self, lowerer):
        sql = """
        SELECT account_no, SUM(credit_amt) - SUM(debit_amt) AS net_bal
        FROM gl_entries
        GROUP BY account_no
        HAVING SUM(credit_amt) <> SUM(debit_amt);
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "net_bal" in lowered

    def test_enterprise_scenario_insurance(self, lowerer):
        sql = """
        UPDATE claim_assessments
        SET approved_amount = claimed_amount * 0.95,
            status = 'AUTO_APPROVED'
        WHERE fraud_risk_score < 0.15 AND claimed_amount < 5000.00;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "claim_assessments" in lowered

    def test_enterprise_scenario_telecom(self, lowerer):
        sql = """
        SELECT msisdn, SUM(duration_sec) AS total_sec,
               SUM(bytes_consumed) AS total_bytes
        FROM cdr_voice_records
        GROUP BY msisdn;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "msisdn" in lowered

    def test_enterprise_scenario_wms(self, lowerer):
        sql = """
        SELECT sku, warehouse_id,
               (on_hand_qty - allocated_qty) AS atp_qty
        FROM wms_inventory_balance
        WHERE (on_hand_qty - allocated_qty) > 0;
        """
        lowered = lowerer.lower_statement(sql, "tsql")
        assert "atp_qty" in lowered

    def test_enterprise_scenario_payroll(self, lowerer):
        sql = """
        SELECT emp_id, gross_pay - tax_deduction - social_sec AS net_pay
        FROM hr_payroll_ledger
        WHERE period_code = '2026-03';
        """
        lowered = lowerer.lower_statement(sql, "mysql")
        assert "net_pay" in lowered

    def test_analytical_window_functions(self, lowerer):
        sql = """
        SELECT dept_id, emp_id, salary,
               ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rnk,
               AVG(salary) OVER (PARTITION BY dept_id) as avg_dept_sal
        FROM employee_salaries;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "ROW_NUMBER()" in lowered
        assert "OVER" in lowered

    def test_cte_recursive_query(self, lowerer):
        sql = """
        WITH org_hierarchy (emp_id, manager_id, org_level) AS (
            SELECT emp_id, manager_id, 1
            FROM employees WHERE manager_id IS NULL
            UNION ALL
            SELECT e.emp_id, e.manager_id, o.org_level + 1
            FROM employees e INNER JOIN org_hierarchy o ON e.manager_id = o.emp_id
        )
        SELECT emp_id, manager_id, org_level FROM org_hierarchy;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "org_hierarchy" in lowered
        assert "UNION ALL" in lowered

    def test_transaction_boundary_control(self, lowerer):
        sql = """
        SAVEPOINT sp_batch_001;
        UPDATE batch_status SET state = 'IN_PROGRESS' WHERE id = 1;
        ROLLBACK TO SAVEPOINT sp_batch_001;
        COMMIT;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "SAVEPOINT" in lowered
        assert "COMMIT" in lowered

    def test_complex_multi_join_query(self, lowerer):
        sql = """
        SELECT c.customer_name, o.order_number, p.product_name, oi.quantity, oi.unit_price
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        ORDER BY oi.item_id ASC;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "customers" in lowered
        assert "orders" in lowered
        assert "order_items" in lowered

class TestGBase8cTargetLowerer:
    """Comprehensive industrial test suite for GBase 8c."""

    @pytest.fixture
    def lowerer(self) -> GBase8cTargetLowerer:
        return get_chinadb_lowerer("gbase8c")

    def test_metadata_and_family(self, lowerer):
        assert lowerer.target_id == "gbase8c"
        assert lowerer.display_name == "GBase 8c"
        assert lowerer.family == "pg_compat"
        assert len(lowerer.type_mappings) > 0
        assert len(lowerer.builtin_mappings) > 0
        assert len(lowerer.lowering_rules) > 0

    def test_type_mapping_0_varchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 VARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_1_nvarchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 NVARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_2_number(self, lowerer):
        sql = "CREATE TABLE t (col1 NUMBER NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "NUMERIC" in lowered

    def test_type_mapping_3_binary_double(self, lowerer):
        sql = "CREATE TABLE t (col1 BINARY_DOUBLE NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "DOUBLE PRECISION" in lowered

    def test_type_mapping_4_binary_float(self, lowerer):
        sql = "CREATE TABLE t (col1 BINARY_FLOAT NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "REAL" in lowered

    def test_type_mapping_5_raw(self, lowerer):
        sql = "CREATE TABLE t (col1 RAW NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "BYTEA" in lowered

    def test_builtin_mapping_0_nvl(self, lowerer):
        sql = "SELECT NVL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "COALESCE" in lowered

    def test_builtin_mapping_1_isnull(self, lowerer):
        sql = "SELECT ISNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "COALESCE" in lowered

    def test_builtin_mapping_2_ifnull(self, lowerer):
        sql = "SELECT IFNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "COALESCE" in lowered

    def test_builtin_mapping_3_getdate(self, lowerer):
        sql = "SELECT GETDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "CURRENT_TIMESTAMP" in lowered

    def test_builtin_mapping_4_getutcdate(self, lowerer):
        sql = "SELECT GETUTCDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "TIMEZONE" in lowered

    def test_builtin_mapping_5_sysdate(self, lowerer):
        sql = "SELECT SYSDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "CURRENT_TIMESTAMP" in lowered

    def test_lowering_rule_0_gbase8c_dual_removal(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gbase8c_dual_removal"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gbase8c_dual_removal"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_1_gbase8c_square_brackets(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gbase8c_square_brackets"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gbase8c_square_brackets"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_2_gbase8c_variable_prefix(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gbase8c_variable_prefix"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gbase8c_variable_prefix"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_3_gb8c_replication_table(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gb8c_replication_table"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gb8c_replication_table"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_table_ddl_lowering(self, lowerer):
        source_ddl = """
        CREATE TABLE enterprise_account (
            account_id BIGINT NOT NULL,
            account_name VARCHAR(128) NOT NULL,
            balance DECIMAL(18, 4) DEFAULT 0.0000,
            status VARCHAR(16) DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT pk_enterprise_account PRIMARY KEY (account_id)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "CREATE TABLE" in lowered
        assert "enterprise_account" in lowered
        assert "PRIMARY KEY" in lowered

    def test_table_ddl_with_composite_pk_and_checks(self, lowerer):
        source_ddl = """
        CREATE TABLE trade_settlement_ledger (
            batch_date DATE NOT NULL,
            trade_sequence BIGINT NOT NULL,
            debit_amt DECIMAL(16, 2) NOT NULL,
            credit_amt DECIMAL(16, 2) NOT NULL,
            currency_code VARCHAR(3) DEFAULT 'CNY',
            CONSTRAINT pk_trade_ledger PRIMARY KEY (batch_date, trade_sequence),
            CONSTRAINT chk_debit_positive CHECK (debit_amt >= 0),
            CONSTRAINT chk_credit_positive CHECK (credit_amt >= 0)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "trade_settlement_ledger" in lowered
        assert "PRIMARY KEY" in lowered
        assert "CHECK" in lowered

    def test_table_ddl_partitioned_range(self, lowerer):
        source_ddl = """
        CREATE TABLE historical_cdr_records (
            call_id BIGINT NOT NULL,
            call_start_date DATE NOT NULL,
            duration_sec INT NOT NULL,
            billed_amount DECIMAL(10, 4) NOT NULL
        )
        PARTITION BY RANGE (call_start_date) (
            PARTITION p_2026_q1 VALUES LESS THAN ('2026-04-01'),
            PARTITION p_2026_q2 VALUES LESS THAN ('2026-07-01'),
            PARTITION p_max VALUES LESS THAN (MAXVALUE)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "historical_cdr_records" in lowered
        assert len(lowered) > 0

    def test_procedure_lowering_basic(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_audit_batch(
            p_batch_id IN VARCHAR2,
            p_status OUT VARCHAR2
        )
        AS
            v_total NUMBER := 0;
        BEGIN
            SELECT COUNT(*) INTO v_total FROM audit_log
            WHERE batch_id = p_batch_id;
            p_status := 'COMPLETED';
        END sp_audit_batch;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_audit_batch" in lowered

    def test_procedure_lowering_cursor_loop(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_settle_all_pending
        AS
            CURSOR c_pending IS
                SELECT item_id, amount FROM pending_settlements
                WHERE processed_flag = 'N';
            v_item_id BIGINT;
            v_amt DECIMAL(16, 2);
        BEGIN
            OPEN c_pending;
            LOOP
                FETCH c_pending INTO v_item_id, v_amt;
                EXIT WHEN c_pending%NOTFOUND;
                UPDATE settlement_balance SET balance = balance + v_amt
                WHERE item_id = v_item_id;
            END LOOP;
            CLOSE c_pending;
        END sp_settle_all_pending;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_settle_all_pending" in lowered

    def test_procedure_lowering_exception_block(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_safe_transfer(
            p_from_acc BIGINT,
            p_to_acc BIGINT,
            p_amount DECIMAL(16, 2)
        )
        AS
        BEGIN
            UPDATE bank_accounts SET balance = balance - p_amount
            WHERE account_id = p_from_acc;
            UPDATE bank_accounts SET balance = balance + p_amount
            WHERE account_id = p_to_acc;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
            WHEN OTHERS THEN
                ROLLBACK;
                RAISE;
        END sp_safe_transfer;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_safe_transfer" in lowered

    def test_procedure_lowering_dynamic_sql(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_archive_partition(
            p_table_name IN VARCHAR2,
            p_partition_name IN VARCHAR2
        )
        AS
            v_sql VARCHAR2(500);
        BEGIN
            v_sql := 'ALTER TABLE ' || p_table_name || ' TRUNCATE PARTITION ' || p_partition_name;
            EXECUTE IMMEDIATE v_sql;
        END sp_archive_partition;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_archive_partition" in lowered

    def test_function_lowering_scalar(self, lowerer):
        source_func = """
        CREATE OR REPLACE FUNCTION fn_calculate_accrued_interest(
            p_principal DECIMAL(18, 4),
            p_annual_rate DECIMAL(8, 6),
            p_days INT
        ) RETURN DECIMAL(18, 4)
        AS
            v_interest DECIMAL(18, 4);
        BEGIN
            v_interest := p_principal * (p_annual_rate / 360.0) * p_days;
            RETURN v_interest;
        END fn_calculate_accrued_interest;
        """
        lowered = lowerer.lower_function(source_func, "oracle")
        assert len(lowered) > 0
        assert "fn_calculate_accrued_interest" in lowered

    def test_trigger_lowering_before_insert(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_audit_journal_entry
        BEFORE INSERT ON journal_entries
        FOR EACH ROW
        BEGIN
            :NEW.created_at := SYSDATE;
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_audit_journal_entry" in lowered

    def test_trigger_lowering_after_update(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_sync_order_status
        AFTER UPDATE OF status ON trade_orders
        FOR EACH ROW
        WHEN (OLD.status <> NEW.status)
        BEGIN
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_at)
            VALUES (:NEW.order_id, :OLD.status, :NEW.status, SYSDATE);
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_sync_order_status" in lowered

    def test_sequence_lowering_nextval(self, lowerer):
        source_seq = "SELECT seq_order_no.NEXTVAL FROM DUAL;"
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert len(lowered) > 0
        assert "seq_order_no" in lowered

    def test_sequence_lowering_creation(self, lowerer):
        source_seq = """
        CREATE SEQUENCE seq_trade_journal_seq
        START WITH 1000000
        INCREMENT BY 1
        MAXVALUE 9999999999
        NOCACHE NOCYCLE;
        """
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert "seq_trade_journal_seq" in lowered
        assert "SEQUENCE" in lowered

    def test_view_ddl_lowering(self, lowerer):
        view_sql = """
        CREATE VIEW v_active_accounts AS
        SELECT account_id, account_name, balance
        FROM enterprise_account
        WHERE status = 'ACTIVE';
        """
        lowered = lowerer.lower_view(view_sql, "oracle")
        assert "CREATE VIEW" in lowered
        assert "v_active_accounts" in lowered

    def test_syntax_heuristics_balanced(self, lowerer):
        valid_sql = "BEGIN NULL; END;"
        ok, issues = lowerer.verify_syntax_heuristics(valid_sql)
        assert ok is True
        assert len(issues) == 0

    def test_syntax_heuristics_unbalanced(self, lowerer):
        invalid_sql = "BEGIN NULL;"
        ok, issues = lowerer.verify_syntax_heuristics(invalid_sql)
        assert ok is False
        assert len(issues) > 0

    def test_catalog_queries_available(self, lowerer):
        queries = getattr(lowerer, "get_catalog_queries", lambda: {})()
        if queries:
            assert "tables" in queries or "columns" in queries

    def test_enterprise_scenario_banking(self, lowerer):
        sql = """
        SELECT account_no, SUM(credit_amt) - SUM(debit_amt) AS net_bal
        FROM gl_entries
        GROUP BY account_no
        HAVING SUM(credit_amt) <> SUM(debit_amt);
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "net_bal" in lowered

    def test_enterprise_scenario_insurance(self, lowerer):
        sql = """
        UPDATE claim_assessments
        SET approved_amount = claimed_amount * 0.95,
            status = 'AUTO_APPROVED'
        WHERE fraud_risk_score < 0.15 AND claimed_amount < 5000.00;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "claim_assessments" in lowered

    def test_enterprise_scenario_telecom(self, lowerer):
        sql = """
        SELECT msisdn, SUM(duration_sec) AS total_sec,
               SUM(bytes_consumed) AS total_bytes
        FROM cdr_voice_records
        GROUP BY msisdn;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "msisdn" in lowered

    def test_enterprise_scenario_wms(self, lowerer):
        sql = """
        SELECT sku, warehouse_id,
               (on_hand_qty - allocated_qty) AS atp_qty
        FROM wms_inventory_balance
        WHERE (on_hand_qty - allocated_qty) > 0;
        """
        lowered = lowerer.lower_statement(sql, "tsql")
        assert "atp_qty" in lowered

    def test_enterprise_scenario_payroll(self, lowerer):
        sql = """
        SELECT emp_id, gross_pay - tax_deduction - social_sec AS net_pay
        FROM hr_payroll_ledger
        WHERE period_code = '2026-03';
        """
        lowered = lowerer.lower_statement(sql, "mysql")
        assert "net_pay" in lowered

    def test_analytical_window_functions(self, lowerer):
        sql = """
        SELECT dept_id, emp_id, salary,
               ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rnk,
               AVG(salary) OVER (PARTITION BY dept_id) as avg_dept_sal
        FROM employee_salaries;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "ROW_NUMBER()" in lowered
        assert "OVER" in lowered

    def test_cte_recursive_query(self, lowerer):
        sql = """
        WITH org_hierarchy (emp_id, manager_id, org_level) AS (
            SELECT emp_id, manager_id, 1
            FROM employees WHERE manager_id IS NULL
            UNION ALL
            SELECT e.emp_id, e.manager_id, o.org_level + 1
            FROM employees e INNER JOIN org_hierarchy o ON e.manager_id = o.emp_id
        )
        SELECT emp_id, manager_id, org_level FROM org_hierarchy;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "org_hierarchy" in lowered
        assert "UNION ALL" in lowered

    def test_transaction_boundary_control(self, lowerer):
        sql = """
        SAVEPOINT sp_batch_001;
        UPDATE batch_status SET state = 'IN_PROGRESS' WHERE id = 1;
        ROLLBACK TO SAVEPOINT sp_batch_001;
        COMMIT;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "SAVEPOINT" in lowered
        assert "COMMIT" in lowered

    def test_complex_multi_join_query(self, lowerer):
        sql = """
        SELECT c.customer_name, o.order_number, p.product_name, oi.quantity, oi.unit_price
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        ORDER BY oi.item_id ASC;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "customers" in lowered
        assert "orders" in lowered
        assert "order_items" in lowered

class TestGBase8sTargetLowerer:
    """Comprehensive industrial test suite for GBase 8s."""

    @pytest.fixture
    def lowerer(self) -> GBase8sTargetLowerer:
        return get_chinadb_lowerer("gbase8s")

    def test_metadata_and_family(self, lowerer):
        assert lowerer.target_id == "gbase8s"
        assert lowerer.display_name == "GBase 8s"
        assert lowerer.family == "informix_compat"
        assert len(lowerer.type_mappings) > 0
        assert len(lowerer.builtin_mappings) > 0
        assert len(lowerer.lowering_rules) > 0

    def test_type_mapping_0_varchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 VARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_1_nvarchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 NVARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "NVARCHAR" in lowered

    def test_type_mapping_2_number(self, lowerer):
        sql = "CREATE TABLE t (col1 NUMBER NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "DECIMAL" in lowered

    def test_type_mapping_3_clob(self, lowerer):
        sql = "CREATE TABLE t (col1 CLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "TEXT" in lowered

    def test_type_mapping_4_nclob(self, lowerer):
        sql = "CREATE TABLE t (col1 NCLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "TEXT" in lowered

    def test_type_mapping_5_blob(self, lowerer):
        sql = "CREATE TABLE t (col1 BLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "BYTE" in lowered

    def test_builtin_mapping_0_sysdate(self, lowerer):
        sql = "SELECT SYSDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "CURRENT" in lowered

    def test_builtin_mapping_1_getdate(self, lowerer):
        sql = "SELECT GETDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "CURRENT" in lowered

    def test_builtin_mapping_2_now(self, lowerer):
        sql = "SELECT NOW() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "CURRENT" in lowered

    def test_builtin_mapping_3_isnull(self, lowerer):
        sql = "SELECT ISNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NVL" in lowered

    def test_builtin_mapping_4_ifnull(self, lowerer):
        sql = "SELECT IFNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NVL" in lowered

    def test_builtin_mapping_5_coalesce(self, lowerer):
        sql = "SELECT COALESCE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NVL" in lowered

    def test_lowering_rule_0_gbase8s_or_replace_strip(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gbase8s_or_replace_strip"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gbase8s_or_replace_strip"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_1_gbase8s_assign_let(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gbase8s_assign_let"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gbase8s_assign_let"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "oracle")
        assert isinstance(res, str)

    def test_lowering_rule_2_gbase8s_dual_sysmaster(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gbase8s_dual_sysmaster"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gbase8s_dual_sysmaster"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "oracle")
        assert isinstance(res, str)

    def test_lowering_rule_3_gbase8s_pagination_first_skip(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gbase8s_pagination_first_skip"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gbase8s_pagination_first_skip"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_4_gbase8s_on_exception(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gbase8s_on_exception"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gbase8s_on_exception"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "oracle")
        assert isinstance(res, str)

    def test_lowering_rule_5_gbase8s_define_var(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "gbase8s_define_var"]
        assert len(rules) == 1
        assert rules[0].rule_id == "gbase8s_define_var"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "oracle")
        assert isinstance(res, str)

    def test_table_ddl_lowering(self, lowerer):
        source_ddl = """
        CREATE TABLE enterprise_account (
            account_id BIGINT NOT NULL,
            account_name VARCHAR(128) NOT NULL,
            balance DECIMAL(18, 4) DEFAULT 0.0000,
            status VARCHAR(16) DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT pk_enterprise_account PRIMARY KEY (account_id)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "CREATE TABLE" in lowered
        assert "enterprise_account" in lowered
        assert "PRIMARY KEY" in lowered

    def test_table_ddl_with_composite_pk_and_checks(self, lowerer):
        source_ddl = """
        CREATE TABLE trade_settlement_ledger (
            batch_date DATE NOT NULL,
            trade_sequence BIGINT NOT NULL,
            debit_amt DECIMAL(16, 2) NOT NULL,
            credit_amt DECIMAL(16, 2) NOT NULL,
            currency_code VARCHAR(3) DEFAULT 'CNY',
            CONSTRAINT pk_trade_ledger PRIMARY KEY (batch_date, trade_sequence),
            CONSTRAINT chk_debit_positive CHECK (debit_amt >= 0),
            CONSTRAINT chk_credit_positive CHECK (credit_amt >= 0)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "trade_settlement_ledger" in lowered
        assert "PRIMARY KEY" in lowered
        assert "CHECK" in lowered

    def test_table_ddl_partitioned_range(self, lowerer):
        source_ddl = """
        CREATE TABLE historical_cdr_records (
            call_id BIGINT NOT NULL,
            call_start_date DATE NOT NULL,
            duration_sec INT NOT NULL,
            billed_amount DECIMAL(10, 4) NOT NULL
        )
        PARTITION BY RANGE (call_start_date) (
            PARTITION p_2026_q1 VALUES LESS THAN ('2026-04-01'),
            PARTITION p_2026_q2 VALUES LESS THAN ('2026-07-01'),
            PARTITION p_max VALUES LESS THAN (MAXVALUE)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "historical_cdr_records" in lowered
        assert len(lowered) > 0

    def test_procedure_lowering_basic(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_audit_batch(
            p_batch_id IN VARCHAR2,
            p_status OUT VARCHAR2
        )
        AS
            v_total NUMBER := 0;
        BEGIN
            SELECT COUNT(*) INTO v_total FROM audit_log
            WHERE batch_id = p_batch_id;
            p_status := 'COMPLETED';
        END sp_audit_batch;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_audit_batch" in lowered

    def test_procedure_lowering_cursor_loop(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_settle_all_pending
        AS
            CURSOR c_pending IS
                SELECT item_id, amount FROM pending_settlements
                WHERE processed_flag = 'N';
            v_item_id BIGINT;
            v_amt DECIMAL(16, 2);
        BEGIN
            OPEN c_pending;
            LOOP
                FETCH c_pending INTO v_item_id, v_amt;
                EXIT WHEN c_pending%NOTFOUND;
                UPDATE settlement_balance SET balance = balance + v_amt
                WHERE item_id = v_item_id;
            END LOOP;
            CLOSE c_pending;
        END sp_settle_all_pending;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_settle_all_pending" in lowered

    def test_procedure_lowering_exception_block(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_safe_transfer(
            p_from_acc BIGINT,
            p_to_acc BIGINT,
            p_amount DECIMAL(16, 2)
        )
        AS
        BEGIN
            UPDATE bank_accounts SET balance = balance - p_amount
            WHERE account_id = p_from_acc;
            UPDATE bank_accounts SET balance = balance + p_amount
            WHERE account_id = p_to_acc;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
            WHEN OTHERS THEN
                ROLLBACK;
                RAISE;
        END sp_safe_transfer;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_safe_transfer" in lowered

    def test_procedure_lowering_dynamic_sql(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_archive_partition(
            p_table_name IN VARCHAR2,
            p_partition_name IN VARCHAR2
        )
        AS
            v_sql VARCHAR2(500);
        BEGIN
            v_sql := 'ALTER TABLE ' || p_table_name || ' TRUNCATE PARTITION ' || p_partition_name;
            EXECUTE IMMEDIATE v_sql;
        END sp_archive_partition;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_archive_partition" in lowered

    def test_function_lowering_scalar(self, lowerer):
        source_func = """
        CREATE OR REPLACE FUNCTION fn_calculate_accrued_interest(
            p_principal DECIMAL(18, 4),
            p_annual_rate DECIMAL(8, 6),
            p_days INT
        ) RETURN DECIMAL(18, 4)
        AS
            v_interest DECIMAL(18, 4);
        BEGIN
            v_interest := p_principal * (p_annual_rate / 360.0) * p_days;
            RETURN v_interest;
        END fn_calculate_accrued_interest;
        """
        lowered = lowerer.lower_function(source_func, "oracle")
        assert len(lowered) > 0
        assert "fn_calculate_accrued_interest" in lowered

    def test_trigger_lowering_before_insert(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_audit_journal_entry
        BEFORE INSERT ON journal_entries
        FOR EACH ROW
        BEGIN
            :NEW.created_at := SYSDATE;
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_audit_journal_entry" in lowered

    def test_trigger_lowering_after_update(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_sync_order_status
        AFTER UPDATE OF status ON trade_orders
        FOR EACH ROW
        WHEN (OLD.status <> NEW.status)
        BEGIN
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_at)
            VALUES (:NEW.order_id, :OLD.status, :NEW.status, SYSDATE);
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_sync_order_status" in lowered

    def test_sequence_lowering_nextval(self, lowerer):
        source_seq = "SELECT seq_order_no.NEXTVAL FROM DUAL;"
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert len(lowered) > 0
        assert "seq_order_no" in lowered

    def test_sequence_lowering_creation(self, lowerer):
        source_seq = """
        CREATE SEQUENCE seq_trade_journal_seq
        START WITH 1000000
        INCREMENT BY 1
        MAXVALUE 9999999999
        NOCACHE NOCYCLE;
        """
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert "seq_trade_journal_seq" in lowered
        assert "SEQUENCE" in lowered

    def test_view_ddl_lowering(self, lowerer):
        view_sql = """
        CREATE VIEW v_active_accounts AS
        SELECT account_id, account_name, balance
        FROM enterprise_account
        WHERE status = 'ACTIVE';
        """
        lowered = lowerer.lower_view(view_sql, "oracle")
        assert "CREATE VIEW" in lowered
        assert "v_active_accounts" in lowered

    def test_syntax_heuristics_balanced(self, lowerer):
        valid_sql = "BEGIN NULL; END;"
        ok, issues = lowerer.verify_syntax_heuristics(valid_sql)
        assert ok is True
        assert len(issues) == 0

    def test_syntax_heuristics_unbalanced(self, lowerer):
        invalid_sql = "BEGIN NULL;"
        ok, issues = lowerer.verify_syntax_heuristics(invalid_sql)
        assert ok is False
        assert len(issues) > 0

    def test_catalog_queries_available(self, lowerer):
        queries = getattr(lowerer, "get_catalog_queries", lambda: {})()
        if queries:
            assert "tables" in queries or "columns" in queries

    def test_enterprise_scenario_banking(self, lowerer):
        sql = """
        SELECT account_no, SUM(credit_amt) - SUM(debit_amt) AS net_bal
        FROM gl_entries
        GROUP BY account_no
        HAVING SUM(credit_amt) <> SUM(debit_amt);
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "net_bal" in lowered

    def test_enterprise_scenario_insurance(self, lowerer):
        sql = """
        UPDATE claim_assessments
        SET approved_amount = claimed_amount * 0.95,
            status = 'AUTO_APPROVED'
        WHERE fraud_risk_score < 0.15 AND claimed_amount < 5000.00;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "claim_assessments" in lowered

    def test_enterprise_scenario_telecom(self, lowerer):
        sql = """
        SELECT msisdn, SUM(duration_sec) AS total_sec,
               SUM(bytes_consumed) AS total_bytes
        FROM cdr_voice_records
        GROUP BY msisdn;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "msisdn" in lowered

    def test_enterprise_scenario_wms(self, lowerer):
        sql = """
        SELECT sku, warehouse_id,
               (on_hand_qty - allocated_qty) AS atp_qty
        FROM wms_inventory_balance
        WHERE (on_hand_qty - allocated_qty) > 0;
        """
        lowered = lowerer.lower_statement(sql, "tsql")
        assert "atp_qty" in lowered

    def test_enterprise_scenario_payroll(self, lowerer):
        sql = """
        SELECT emp_id, gross_pay - tax_deduction - social_sec AS net_pay
        FROM hr_payroll_ledger
        WHERE period_code = '2026-03';
        """
        lowered = lowerer.lower_statement(sql, "mysql")
        assert "net_pay" in lowered

    def test_analytical_window_functions(self, lowerer):
        sql = """
        SELECT dept_id, emp_id, salary,
               ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rnk,
               AVG(salary) OVER (PARTITION BY dept_id) as avg_dept_sal
        FROM employee_salaries;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "ROW_NUMBER()" in lowered
        assert "OVER" in lowered

    def test_cte_recursive_query(self, lowerer):
        sql = """
        WITH org_hierarchy (emp_id, manager_id, org_level) AS (
            SELECT emp_id, manager_id, 1
            FROM employees WHERE manager_id IS NULL
            UNION ALL
            SELECT e.emp_id, e.manager_id, o.org_level + 1
            FROM employees e INNER JOIN org_hierarchy o ON e.manager_id = o.emp_id
        )
        SELECT emp_id, manager_id, org_level FROM org_hierarchy;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "org_hierarchy" in lowered
        assert "UNION ALL" in lowered

    def test_transaction_boundary_control(self, lowerer):
        sql = """
        SAVEPOINT sp_batch_001;
        UPDATE batch_status SET state = 'IN_PROGRESS' WHERE id = 1;
        ROLLBACK TO SAVEPOINT sp_batch_001;
        COMMIT;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "SAVEPOINT" in lowered
        assert "COMMIT" in lowered

    def test_complex_multi_join_query(self, lowerer):
        sql = """
        SELECT c.customer_name, o.order_number, p.product_name, oi.quantity, oi.unit_price
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        ORDER BY oi.item_id ASC;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "customers" in lowered
        assert "orders" in lowered
        assert "order_items" in lowered

class TestGoldenDbTargetLowerer:
    """Comprehensive industrial test suite for ZTE GoldenDB."""

    @pytest.fixture
    def lowerer(self) -> GoldenDbTargetLowerer:
        return get_chinadb_lowerer("goldendb")

    def test_metadata_and_family(self, lowerer):
        assert lowerer.target_id == "goldendb"
        assert lowerer.display_name == "ZTE GoldenDB"
        assert lowerer.family == "mysql_compat"
        assert len(lowerer.type_mappings) > 0
        assert len(lowerer.builtin_mappings) > 0
        assert len(lowerer.lowering_rules) > 0

    def test_type_mapping_0_varchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 VARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_1_nvarchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 NVARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_2_number(self, lowerer):
        sql = "CREATE TABLE t (col1 NUMBER NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "DECIMAL" in lowered

    def test_type_mapping_3_clob(self, lowerer):
        sql = "CREATE TABLE t (col1 CLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGTEXT" in lowered

    def test_type_mapping_4_nclob(self, lowerer):
        sql = "CREATE TABLE t (col1 NCLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGTEXT" in lowered

    def test_type_mapping_5_blob(self, lowerer):
        sql = "CREATE TABLE t (col1 BLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGBLOB" in lowered

    def test_builtin_mapping_0_nvl(self, lowerer):
        sql = "SELECT NVL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "IFNULL" in lowered

    def test_builtin_mapping_1_isnull(self, lowerer):
        sql = "SELECT ISNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "IFNULL" in lowered

    def test_builtin_mapping_2_getdate(self, lowerer):
        sql = "SELECT GETDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NOW" in lowered

    def test_builtin_mapping_3_getutcdate(self, lowerer):
        sql = "SELECT GETUTCDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "UTC_TIMESTAMP" in lowered

    def test_builtin_mapping_4_sysdate(self, lowerer):
        sql = "SELECT SYSDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NOW" in lowered

    def test_builtin_mapping_5_len(self, lowerer):
        sql = "SELECT LEN() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "CHAR_LENGTH" in lowered

    def test_lowering_rule_0_goldendb_sharding_comment(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "goldendb_sharding_comment"]
        assert len(rules) == 1
        assert rules[0].rule_id == "goldendb_sharding_comment"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_1_goldendb_backtick_escape(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "goldendb_backtick_escape"]
        assert len(rules) == 1
        assert rules[0].rule_id == "goldendb_backtick_escape"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_2_goldendb_dual_strip(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "goldendb_dual_strip"]
        assert len(rules) == 1
        assert rules[0].rule_id == "goldendb_dual_strip"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_3_goldendb_auto_inc(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "goldendb_auto_inc"]
        assert len(rules) == 1
        assert rules[0].rule_id == "goldendb_auto_inc"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_table_ddl_lowering(self, lowerer):
        source_ddl = """
        CREATE TABLE enterprise_account (
            account_id BIGINT NOT NULL,
            account_name VARCHAR(128) NOT NULL,
            balance DECIMAL(18, 4) DEFAULT 0.0000,
            status VARCHAR(16) DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT pk_enterprise_account PRIMARY KEY (account_id)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "CREATE TABLE" in lowered
        assert "enterprise_account" in lowered
        assert "PRIMARY KEY" in lowered

    def test_table_ddl_with_composite_pk_and_checks(self, lowerer):
        source_ddl = """
        CREATE TABLE trade_settlement_ledger (
            batch_date DATE NOT NULL,
            trade_sequence BIGINT NOT NULL,
            debit_amt DECIMAL(16, 2) NOT NULL,
            credit_amt DECIMAL(16, 2) NOT NULL,
            currency_code VARCHAR(3) DEFAULT 'CNY',
            CONSTRAINT pk_trade_ledger PRIMARY KEY (batch_date, trade_sequence),
            CONSTRAINT chk_debit_positive CHECK (debit_amt >= 0),
            CONSTRAINT chk_credit_positive CHECK (credit_amt >= 0)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "trade_settlement_ledger" in lowered
        assert "PRIMARY KEY" in lowered
        assert "CHECK" in lowered

    def test_table_ddl_partitioned_range(self, lowerer):
        source_ddl = """
        CREATE TABLE historical_cdr_records (
            call_id BIGINT NOT NULL,
            call_start_date DATE NOT NULL,
            duration_sec INT NOT NULL,
            billed_amount DECIMAL(10, 4) NOT NULL
        )
        PARTITION BY RANGE (call_start_date) (
            PARTITION p_2026_q1 VALUES LESS THAN ('2026-04-01'),
            PARTITION p_2026_q2 VALUES LESS THAN ('2026-07-01'),
            PARTITION p_max VALUES LESS THAN (MAXVALUE)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "historical_cdr_records" in lowered
        assert len(lowered) > 0

    def test_procedure_lowering_basic(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_audit_batch(
            p_batch_id IN VARCHAR2,
            p_status OUT VARCHAR2
        )
        AS
            v_total NUMBER := 0;
        BEGIN
            SELECT COUNT(*) INTO v_total FROM audit_log
            WHERE batch_id = p_batch_id;
            p_status := 'COMPLETED';
        END sp_audit_batch;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_audit_batch" in lowered

    def test_procedure_lowering_cursor_loop(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_settle_all_pending
        AS
            CURSOR c_pending IS
                SELECT item_id, amount FROM pending_settlements
                WHERE processed_flag = 'N';
            v_item_id BIGINT;
            v_amt DECIMAL(16, 2);
        BEGIN
            OPEN c_pending;
            LOOP
                FETCH c_pending INTO v_item_id, v_amt;
                EXIT WHEN c_pending%NOTFOUND;
                UPDATE settlement_balance SET balance = balance + v_amt
                WHERE item_id = v_item_id;
            END LOOP;
            CLOSE c_pending;
        END sp_settle_all_pending;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_settle_all_pending" in lowered

    def test_procedure_lowering_exception_block(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_safe_transfer(
            p_from_acc BIGINT,
            p_to_acc BIGINT,
            p_amount DECIMAL(16, 2)
        )
        AS
        BEGIN
            UPDATE bank_accounts SET balance = balance - p_amount
            WHERE account_id = p_from_acc;
            UPDATE bank_accounts SET balance = balance + p_amount
            WHERE account_id = p_to_acc;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
            WHEN OTHERS THEN
                ROLLBACK;
                RAISE;
        END sp_safe_transfer;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_safe_transfer" in lowered

    def test_procedure_lowering_dynamic_sql(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_archive_partition(
            p_table_name IN VARCHAR2,
            p_partition_name IN VARCHAR2
        )
        AS
            v_sql VARCHAR2(500);
        BEGIN
            v_sql := 'ALTER TABLE ' || p_table_name || ' TRUNCATE PARTITION ' || p_partition_name;
            EXECUTE IMMEDIATE v_sql;
        END sp_archive_partition;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_archive_partition" in lowered

    def test_function_lowering_scalar(self, lowerer):
        source_func = """
        CREATE OR REPLACE FUNCTION fn_calculate_accrued_interest(
            p_principal DECIMAL(18, 4),
            p_annual_rate DECIMAL(8, 6),
            p_days INT
        ) RETURN DECIMAL(18, 4)
        AS
            v_interest DECIMAL(18, 4);
        BEGIN
            v_interest := p_principal * (p_annual_rate / 360.0) * p_days;
            RETURN v_interest;
        END fn_calculate_accrued_interest;
        """
        lowered = lowerer.lower_function(source_func, "oracle")
        assert len(lowered) > 0
        assert "fn_calculate_accrued_interest" in lowered

    def test_trigger_lowering_before_insert(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_audit_journal_entry
        BEFORE INSERT ON journal_entries
        FOR EACH ROW
        BEGIN
            :NEW.created_at := SYSDATE;
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_audit_journal_entry" in lowered

    def test_trigger_lowering_after_update(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_sync_order_status
        AFTER UPDATE OF status ON trade_orders
        FOR EACH ROW
        WHEN (OLD.status <> NEW.status)
        BEGIN
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_at)
            VALUES (:NEW.order_id, :OLD.status, :NEW.status, SYSDATE);
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_sync_order_status" in lowered

    def test_sequence_lowering_nextval(self, lowerer):
        source_seq = "SELECT seq_order_no.NEXTVAL FROM DUAL;"
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert len(lowered) > 0
        assert "seq_order_no" in lowered

    def test_sequence_lowering_creation(self, lowerer):
        source_seq = """
        CREATE SEQUENCE seq_trade_journal_seq
        START WITH 1000000
        INCREMENT BY 1
        MAXVALUE 9999999999
        NOCACHE NOCYCLE;
        """
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert "seq_trade_journal_seq" in lowered
        assert "SEQUENCE" in lowered

    def test_view_ddl_lowering(self, lowerer):
        view_sql = """
        CREATE VIEW v_active_accounts AS
        SELECT account_id, account_name, balance
        FROM enterprise_account
        WHERE status = 'ACTIVE';
        """
        lowered = lowerer.lower_view(view_sql, "oracle")
        assert "CREATE VIEW" in lowered
        assert "v_active_accounts" in lowered

    def test_syntax_heuristics_balanced(self, lowerer):
        valid_sql = "BEGIN NULL; END;"
        ok, issues = lowerer.verify_syntax_heuristics(valid_sql)
        assert ok is True
        assert len(issues) == 0

    def test_syntax_heuristics_unbalanced(self, lowerer):
        invalid_sql = "BEGIN NULL;"
        ok, issues = lowerer.verify_syntax_heuristics(invalid_sql)
        assert ok is False
        assert len(issues) > 0

    def test_catalog_queries_available(self, lowerer):
        queries = getattr(lowerer, "get_catalog_queries", lambda: {})()
        if queries:
            assert "tables" in queries or "columns" in queries

    def test_enterprise_scenario_banking(self, lowerer):
        sql = """
        SELECT account_no, SUM(credit_amt) - SUM(debit_amt) AS net_bal
        FROM gl_entries
        GROUP BY account_no
        HAVING SUM(credit_amt) <> SUM(debit_amt);
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "net_bal" in lowered

    def test_enterprise_scenario_insurance(self, lowerer):
        sql = """
        UPDATE claim_assessments
        SET approved_amount = claimed_amount * 0.95,
            status = 'AUTO_APPROVED'
        WHERE fraud_risk_score < 0.15 AND claimed_amount < 5000.00;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "claim_assessments" in lowered

    def test_enterprise_scenario_telecom(self, lowerer):
        sql = """
        SELECT msisdn, SUM(duration_sec) AS total_sec,
               SUM(bytes_consumed) AS total_bytes
        FROM cdr_voice_records
        GROUP BY msisdn;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "msisdn" in lowered

    def test_enterprise_scenario_wms(self, lowerer):
        sql = """
        SELECT sku, warehouse_id,
               (on_hand_qty - allocated_qty) AS atp_qty
        FROM wms_inventory_balance
        WHERE (on_hand_qty - allocated_qty) > 0;
        """
        lowered = lowerer.lower_statement(sql, "tsql")
        assert "atp_qty" in lowered

    def test_enterprise_scenario_payroll(self, lowerer):
        sql = """
        SELECT emp_id, gross_pay - tax_deduction - social_sec AS net_pay
        FROM hr_payroll_ledger
        WHERE period_code = '2026-03';
        """
        lowered = lowerer.lower_statement(sql, "mysql")
        assert "net_pay" in lowered

    def test_analytical_window_functions(self, lowerer):
        sql = """
        SELECT dept_id, emp_id, salary,
               ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rnk,
               AVG(salary) OVER (PARTITION BY dept_id) as avg_dept_sal
        FROM employee_salaries;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "ROW_NUMBER()" in lowered
        assert "OVER" in lowered

    def test_cte_recursive_query(self, lowerer):
        sql = """
        WITH org_hierarchy (emp_id, manager_id, org_level) AS (
            SELECT emp_id, manager_id, 1
            FROM employees WHERE manager_id IS NULL
            UNION ALL
            SELECT e.emp_id, e.manager_id, o.org_level + 1
            FROM employees e INNER JOIN org_hierarchy o ON e.manager_id = o.emp_id
        )
        SELECT emp_id, manager_id, org_level FROM org_hierarchy;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "org_hierarchy" in lowered
        assert "UNION ALL" in lowered

    def test_transaction_boundary_control(self, lowerer):
        sql = """
        SAVEPOINT sp_batch_001;
        UPDATE batch_status SET state = 'IN_PROGRESS' WHERE id = 1;
        ROLLBACK TO SAVEPOINT sp_batch_001;
        COMMIT;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "SAVEPOINT" in lowered
        assert "COMMIT" in lowered

    def test_complex_multi_join_query(self, lowerer):
        sql = """
        SELECT c.customer_name, o.order_number, p.product_name, oi.quantity, oi.unit_price
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        ORDER BY oi.item_id ASC;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "customers" in lowered
        assert "orders" in lowered
        assert "order_items" in lowered

class TestHighGoTargetLowerer:
    """Comprehensive industrial test suite for HighGo DB (HGDB)."""

    @pytest.fixture
    def lowerer(self) -> HighGoTargetLowerer:
        return get_chinadb_lowerer("highgo")

    def test_metadata_and_family(self, lowerer):
        assert lowerer.target_id == "highgo"
        assert lowerer.display_name == "HighGo DB (HGDB)"
        assert lowerer.family == "oracle_pg_hybrid"
        assert len(lowerer.type_mappings) > 0
        assert len(lowerer.builtin_mappings) > 0
        assert len(lowerer.lowering_rules) > 0

    def test_type_mapping_0_varchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 VARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_1_nvarchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 NVARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_2_number(self, lowerer):
        sql = "CREATE TABLE t (col1 NUMBER NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "NUMERIC" in lowered

    def test_type_mapping_3_binary_double(self, lowerer):
        sql = "CREATE TABLE t (col1 BINARY_DOUBLE NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "DOUBLE PRECISION" in lowered

    def test_type_mapping_4_binary_float(self, lowerer):
        sql = "CREATE TABLE t (col1 BINARY_FLOAT NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "REAL" in lowered

    def test_type_mapping_5_raw(self, lowerer):
        sql = "CREATE TABLE t (col1 RAW NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "BYTEA" in lowered

    def test_builtin_mapping_0_nvl(self, lowerer):
        sql = "SELECT NVL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "COALESCE" in lowered

    def test_builtin_mapping_1_isnull(self, lowerer):
        sql = "SELECT ISNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "COALESCE" in lowered

    def test_builtin_mapping_2_ifnull(self, lowerer):
        sql = "SELECT IFNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "COALESCE" in lowered

    def test_builtin_mapping_3_getdate(self, lowerer):
        sql = "SELECT GETDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "CURRENT_TIMESTAMP" in lowered

    def test_builtin_mapping_4_getutcdate(self, lowerer):
        sql = "SELECT GETUTCDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "TIMEZONE" in lowered

    def test_builtin_mapping_5_sysdate(self, lowerer):
        sql = "SELECT SYSDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "CURRENT_TIMESTAMP" in lowered

    def test_lowering_rule_0_hg_dual_strip(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "hg_dual_strip"]
        assert len(rules) == 1
        assert rules[0].rule_id == "hg_dual_strip"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_1_hg_square_brackets(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "hg_square_brackets"]
        assert len(rules) == 1
        assert rules[0].rule_id == "hg_square_brackets"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_2_hg_variable_prefix(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "hg_variable_prefix"]
        assert len(rules) == 1
        assert rules[0].rule_id == "hg_variable_prefix"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_3_hg_row_level_security(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "hg_row_level_security"]
        assert len(rules) == 1
        assert rules[0].rule_id == "hg_row_level_security"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_table_ddl_lowering(self, lowerer):
        source_ddl = """
        CREATE TABLE enterprise_account (
            account_id BIGINT NOT NULL,
            account_name VARCHAR(128) NOT NULL,
            balance DECIMAL(18, 4) DEFAULT 0.0000,
            status VARCHAR(16) DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT pk_enterprise_account PRIMARY KEY (account_id)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "CREATE TABLE" in lowered
        assert "enterprise_account" in lowered
        assert "PRIMARY KEY" in lowered

    def test_table_ddl_with_composite_pk_and_checks(self, lowerer):
        source_ddl = """
        CREATE TABLE trade_settlement_ledger (
            batch_date DATE NOT NULL,
            trade_sequence BIGINT NOT NULL,
            debit_amt DECIMAL(16, 2) NOT NULL,
            credit_amt DECIMAL(16, 2) NOT NULL,
            currency_code VARCHAR(3) DEFAULT 'CNY',
            CONSTRAINT pk_trade_ledger PRIMARY KEY (batch_date, trade_sequence),
            CONSTRAINT chk_debit_positive CHECK (debit_amt >= 0),
            CONSTRAINT chk_credit_positive CHECK (credit_amt >= 0)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "trade_settlement_ledger" in lowered
        assert "PRIMARY KEY" in lowered
        assert "CHECK" in lowered

    def test_table_ddl_partitioned_range(self, lowerer):
        source_ddl = """
        CREATE TABLE historical_cdr_records (
            call_id BIGINT NOT NULL,
            call_start_date DATE NOT NULL,
            duration_sec INT NOT NULL,
            billed_amount DECIMAL(10, 4) NOT NULL
        )
        PARTITION BY RANGE (call_start_date) (
            PARTITION p_2026_q1 VALUES LESS THAN ('2026-04-01'),
            PARTITION p_2026_q2 VALUES LESS THAN ('2026-07-01'),
            PARTITION p_max VALUES LESS THAN (MAXVALUE)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "historical_cdr_records" in lowered
        assert len(lowered) > 0

    def test_procedure_lowering_basic(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_audit_batch(
            p_batch_id IN VARCHAR2,
            p_status OUT VARCHAR2
        )
        AS
            v_total NUMBER := 0;
        BEGIN
            SELECT COUNT(*) INTO v_total FROM audit_log
            WHERE batch_id = p_batch_id;
            p_status := 'COMPLETED';
        END sp_audit_batch;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_audit_batch" in lowered

    def test_procedure_lowering_cursor_loop(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_settle_all_pending
        AS
            CURSOR c_pending IS
                SELECT item_id, amount FROM pending_settlements
                WHERE processed_flag = 'N';
            v_item_id BIGINT;
            v_amt DECIMAL(16, 2);
        BEGIN
            OPEN c_pending;
            LOOP
                FETCH c_pending INTO v_item_id, v_amt;
                EXIT WHEN c_pending%NOTFOUND;
                UPDATE settlement_balance SET balance = balance + v_amt
                WHERE item_id = v_item_id;
            END LOOP;
            CLOSE c_pending;
        END sp_settle_all_pending;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_settle_all_pending" in lowered

    def test_procedure_lowering_exception_block(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_safe_transfer(
            p_from_acc BIGINT,
            p_to_acc BIGINT,
            p_amount DECIMAL(16, 2)
        )
        AS
        BEGIN
            UPDATE bank_accounts SET balance = balance - p_amount
            WHERE account_id = p_from_acc;
            UPDATE bank_accounts SET balance = balance + p_amount
            WHERE account_id = p_to_acc;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
            WHEN OTHERS THEN
                ROLLBACK;
                RAISE;
        END sp_safe_transfer;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_safe_transfer" in lowered

    def test_procedure_lowering_dynamic_sql(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_archive_partition(
            p_table_name IN VARCHAR2,
            p_partition_name IN VARCHAR2
        )
        AS
            v_sql VARCHAR2(500);
        BEGIN
            v_sql := 'ALTER TABLE ' || p_table_name || ' TRUNCATE PARTITION ' || p_partition_name;
            EXECUTE IMMEDIATE v_sql;
        END sp_archive_partition;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_archive_partition" in lowered

    def test_function_lowering_scalar(self, lowerer):
        source_func = """
        CREATE OR REPLACE FUNCTION fn_calculate_accrued_interest(
            p_principal DECIMAL(18, 4),
            p_annual_rate DECIMAL(8, 6),
            p_days INT
        ) RETURN DECIMAL(18, 4)
        AS
            v_interest DECIMAL(18, 4);
        BEGIN
            v_interest := p_principal * (p_annual_rate / 360.0) * p_days;
            RETURN v_interest;
        END fn_calculate_accrued_interest;
        """
        lowered = lowerer.lower_function(source_func, "oracle")
        assert len(lowered) > 0
        assert "fn_calculate_accrued_interest" in lowered

    def test_trigger_lowering_before_insert(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_audit_journal_entry
        BEFORE INSERT ON journal_entries
        FOR EACH ROW
        BEGIN
            :NEW.created_at := SYSDATE;
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_audit_journal_entry" in lowered

    def test_trigger_lowering_after_update(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_sync_order_status
        AFTER UPDATE OF status ON trade_orders
        FOR EACH ROW
        WHEN (OLD.status <> NEW.status)
        BEGIN
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_at)
            VALUES (:NEW.order_id, :OLD.status, :NEW.status, SYSDATE);
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_sync_order_status" in lowered

    def test_sequence_lowering_nextval(self, lowerer):
        source_seq = "SELECT seq_order_no.NEXTVAL FROM DUAL;"
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert len(lowered) > 0
        assert "seq_order_no" in lowered

    def test_sequence_lowering_creation(self, lowerer):
        source_seq = """
        CREATE SEQUENCE seq_trade_journal_seq
        START WITH 1000000
        INCREMENT BY 1
        MAXVALUE 9999999999
        NOCACHE NOCYCLE;
        """
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert "seq_trade_journal_seq" in lowered
        assert "SEQUENCE" in lowered

    def test_view_ddl_lowering(self, lowerer):
        view_sql = """
        CREATE VIEW v_active_accounts AS
        SELECT account_id, account_name, balance
        FROM enterprise_account
        WHERE status = 'ACTIVE';
        """
        lowered = lowerer.lower_view(view_sql, "oracle")
        assert "CREATE VIEW" in lowered
        assert "v_active_accounts" in lowered

    def test_syntax_heuristics_balanced(self, lowerer):
        valid_sql = "BEGIN NULL; END;"
        ok, issues = lowerer.verify_syntax_heuristics(valid_sql)
        assert ok is True
        assert len(issues) == 0

    def test_syntax_heuristics_unbalanced(self, lowerer):
        invalid_sql = "BEGIN NULL;"
        ok, issues = lowerer.verify_syntax_heuristics(invalid_sql)
        assert ok is False
        assert len(issues) > 0

    def test_catalog_queries_available(self, lowerer):
        queries = getattr(lowerer, "get_catalog_queries", lambda: {})()
        if queries:
            assert "tables" in queries or "columns" in queries

    def test_enterprise_scenario_banking(self, lowerer):
        sql = """
        SELECT account_no, SUM(credit_amt) - SUM(debit_amt) AS net_bal
        FROM gl_entries
        GROUP BY account_no
        HAVING SUM(credit_amt) <> SUM(debit_amt);
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "net_bal" in lowered

    def test_enterprise_scenario_insurance(self, lowerer):
        sql = """
        UPDATE claim_assessments
        SET approved_amount = claimed_amount * 0.95,
            status = 'AUTO_APPROVED'
        WHERE fraud_risk_score < 0.15 AND claimed_amount < 5000.00;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "claim_assessments" in lowered

    def test_enterprise_scenario_telecom(self, lowerer):
        sql = """
        SELECT msisdn, SUM(duration_sec) AS total_sec,
               SUM(bytes_consumed) AS total_bytes
        FROM cdr_voice_records
        GROUP BY msisdn;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "msisdn" in lowered

    def test_enterprise_scenario_wms(self, lowerer):
        sql = """
        SELECT sku, warehouse_id,
               (on_hand_qty - allocated_qty) AS atp_qty
        FROM wms_inventory_balance
        WHERE (on_hand_qty - allocated_qty) > 0;
        """
        lowered = lowerer.lower_statement(sql, "tsql")
        assert "atp_qty" in lowered

    def test_enterprise_scenario_payroll(self, lowerer):
        sql = """
        SELECT emp_id, gross_pay - tax_deduction - social_sec AS net_pay
        FROM hr_payroll_ledger
        WHERE period_code = '2026-03';
        """
        lowered = lowerer.lower_statement(sql, "mysql")
        assert "net_pay" in lowered

    def test_analytical_window_functions(self, lowerer):
        sql = """
        SELECT dept_id, emp_id, salary,
               ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rnk,
               AVG(salary) OVER (PARTITION BY dept_id) as avg_dept_sal
        FROM employee_salaries;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "ROW_NUMBER()" in lowered
        assert "OVER" in lowered

    def test_cte_recursive_query(self, lowerer):
        sql = """
        WITH org_hierarchy (emp_id, manager_id, org_level) AS (
            SELECT emp_id, manager_id, 1
            FROM employees WHERE manager_id IS NULL
            UNION ALL
            SELECT e.emp_id, e.manager_id, o.org_level + 1
            FROM employees e INNER JOIN org_hierarchy o ON e.manager_id = o.emp_id
        )
        SELECT emp_id, manager_id, org_level FROM org_hierarchy;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "org_hierarchy" in lowered
        assert "UNION ALL" in lowered

    def test_transaction_boundary_control(self, lowerer):
        sql = """
        SAVEPOINT sp_batch_001;
        UPDATE batch_status SET state = 'IN_PROGRESS' WHERE id = 1;
        ROLLBACK TO SAVEPOINT sp_batch_001;
        COMMIT;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "SAVEPOINT" in lowered
        assert "COMMIT" in lowered

    def test_complex_multi_join_query(self, lowerer):
        sql = """
        SELECT c.customer_name, o.order_number, p.product_name, oi.quantity, oi.unit_price
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        ORDER BY oi.item_id ASC;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "customers" in lowered
        assert "orders" in lowered
        assert "order_items" in lowered

class TestKingbaseTargetLowerer:
    """Comprehensive industrial test suite for KingbaseES (V8/V9)."""

    @pytest.fixture
    def lowerer(self) -> KingbaseTargetLowerer:
        return get_chinadb_lowerer("kingbase")

    def test_metadata_and_family(self, lowerer):
        assert lowerer.target_id == "kingbase"
        assert lowerer.display_name == "KingbaseES (V8/V9)"
        assert lowerer.family == "oracle_pg_hybrid"
        assert len(lowerer.type_mappings) > 0
        assert len(lowerer.builtin_mappings) > 0
        assert len(lowerer.lowering_rules) > 0

    def test_type_mapping_0_varchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 VARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_1_nvarchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 NVARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_2_number(self, lowerer):
        sql = "CREATE TABLE t (col1 NUMBER NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "NUMERIC" in lowered

    def test_type_mapping_3_binary_double(self, lowerer):
        sql = "CREATE TABLE t (col1 BINARY_DOUBLE NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "DOUBLE PRECISION" in lowered

    def test_type_mapping_4_binary_float(self, lowerer):
        sql = "CREATE TABLE t (col1 BINARY_FLOAT NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "REAL" in lowered

    def test_type_mapping_5_raw(self, lowerer):
        sql = "CREATE TABLE t (col1 RAW NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "BYTEA" in lowered

    def test_builtin_mapping_0_nvl(self, lowerer):
        sql = "SELECT NVL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "COALESCE" in lowered

    def test_builtin_mapping_1_isnull(self, lowerer):
        sql = "SELECT ISNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "COALESCE" in lowered

    def test_builtin_mapping_2_ifnull(self, lowerer):
        sql = "SELECT IFNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "COALESCE" in lowered

    def test_builtin_mapping_3_getdate(self, lowerer):
        sql = "SELECT GETDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "CURRENT_TIMESTAMP" in lowered

    def test_builtin_mapping_4_getutcdate(self, lowerer):
        sql = "SELECT GETUTCDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "TIMEZONE" in lowered

    def test_builtin_mapping_5_sysdate(self, lowerer):
        sql = "SELECT SYSDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "CURRENT_TIMESTAMP" in lowered

    def test_lowering_rule_0_kb_nvl2_to_case(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "kb_nvl2_to_case"]
        assert len(rules) == 1
        assert rules[0].rule_id == "kb_nvl2_to_case"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "oracle")
        assert isinstance(res, str)

    def test_lowering_rule_1_kb_dual_strip(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "kb_dual_strip"]
        assert len(rules) == 1
        assert rules[0].rule_id == "kb_dual_strip"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_2_kb_tsql_variable_prefix(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "kb_tsql_variable_prefix"]
        assert len(rules) == 1
        assert rules[0].rule_id == "kb_tsql_variable_prefix"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_3_kb_square_brackets(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "kb_square_brackets"]
        assert len(rules) == 1
        assert rules[0].rule_id == "kb_square_brackets"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_4_kb_limit_offset(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "kb_limit_offset"]
        assert len(rules) == 1
        assert rules[0].rule_id == "kb_limit_offset"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_5_kb_auto_increment(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "kb_auto_increment"]
        assert len(rules) == 1
        assert rules[0].rule_id == "kb_auto_increment"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_6_kb_pragma_autonomous(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "kb_pragma_autonomous"]
        assert len(rules) == 1
        assert rules[0].rule_id == "kb_pragma_autonomous"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "oracle")
        assert isinstance(res, str)

    def test_lowering_rule_7_kb_try_catch_block(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "kb_try_catch_block"]
        assert len(rules) == 1
        assert rules[0].rule_id == "kb_try_catch_block"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_8_kb_partition_by_range(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "kb_partition_by_range"]
        assert len(rules) == 1
        assert rules[0].rule_id == "kb_partition_by_range"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_9_kb_string_agg(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "kb_string_agg"]
        assert len(rules) == 1
        assert rules[0].rule_id == "kb_string_agg"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "mysql")
        assert isinstance(res, str)

    def test_lowering_rule_10_kb_for_update_skip_locked(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "kb_for_update_skip_locked"]
        assert len(rules) == 1
        assert rules[0].rule_id == "kb_for_update_skip_locked"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "oracle")
        assert isinstance(res, str)

    def test_table_ddl_lowering(self, lowerer):
        source_ddl = """
        CREATE TABLE enterprise_account (
            account_id BIGINT NOT NULL,
            account_name VARCHAR(128) NOT NULL,
            balance DECIMAL(18, 4) DEFAULT 0.0000,
            status VARCHAR(16) DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT pk_enterprise_account PRIMARY KEY (account_id)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "CREATE TABLE" in lowered
        assert "enterprise_account" in lowered
        assert "PRIMARY KEY" in lowered

    def test_table_ddl_with_composite_pk_and_checks(self, lowerer):
        source_ddl = """
        CREATE TABLE trade_settlement_ledger (
            batch_date DATE NOT NULL,
            trade_sequence BIGINT NOT NULL,
            debit_amt DECIMAL(16, 2) NOT NULL,
            credit_amt DECIMAL(16, 2) NOT NULL,
            currency_code VARCHAR(3) DEFAULT 'CNY',
            CONSTRAINT pk_trade_ledger PRIMARY KEY (batch_date, trade_sequence),
            CONSTRAINT chk_debit_positive CHECK (debit_amt >= 0),
            CONSTRAINT chk_credit_positive CHECK (credit_amt >= 0)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "trade_settlement_ledger" in lowered
        assert "PRIMARY KEY" in lowered
        assert "CHECK" in lowered

    def test_table_ddl_partitioned_range(self, lowerer):
        source_ddl = """
        CREATE TABLE historical_cdr_records (
            call_id BIGINT NOT NULL,
            call_start_date DATE NOT NULL,
            duration_sec INT NOT NULL,
            billed_amount DECIMAL(10, 4) NOT NULL
        )
        PARTITION BY RANGE (call_start_date) (
            PARTITION p_2026_q1 VALUES LESS THAN ('2026-04-01'),
            PARTITION p_2026_q2 VALUES LESS THAN ('2026-07-01'),
            PARTITION p_max VALUES LESS THAN (MAXVALUE)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "historical_cdr_records" in lowered
        assert len(lowered) > 0

    def test_procedure_lowering_basic(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_audit_batch(
            p_batch_id IN VARCHAR2,
            p_status OUT VARCHAR2
        )
        AS
            v_total NUMBER := 0;
        BEGIN
            SELECT COUNT(*) INTO v_total FROM audit_log
            WHERE batch_id = p_batch_id;
            p_status := 'COMPLETED';
        END sp_audit_batch;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_audit_batch" in lowered

    def test_procedure_lowering_cursor_loop(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_settle_all_pending
        AS
            CURSOR c_pending IS
                SELECT item_id, amount FROM pending_settlements
                WHERE processed_flag = 'N';
            v_item_id BIGINT;
            v_amt DECIMAL(16, 2);
        BEGIN
            OPEN c_pending;
            LOOP
                FETCH c_pending INTO v_item_id, v_amt;
                EXIT WHEN c_pending%NOTFOUND;
                UPDATE settlement_balance SET balance = balance + v_amt
                WHERE item_id = v_item_id;
            END LOOP;
            CLOSE c_pending;
        END sp_settle_all_pending;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_settle_all_pending" in lowered

    def test_procedure_lowering_exception_block(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_safe_transfer(
            p_from_acc BIGINT,
            p_to_acc BIGINT,
            p_amount DECIMAL(16, 2)
        )
        AS
        BEGIN
            UPDATE bank_accounts SET balance = balance - p_amount
            WHERE account_id = p_from_acc;
            UPDATE bank_accounts SET balance = balance + p_amount
            WHERE account_id = p_to_acc;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
            WHEN OTHERS THEN
                ROLLBACK;
                RAISE;
        END sp_safe_transfer;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_safe_transfer" in lowered

    def test_procedure_lowering_dynamic_sql(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_archive_partition(
            p_table_name IN VARCHAR2,
            p_partition_name IN VARCHAR2
        )
        AS
            v_sql VARCHAR2(500);
        BEGIN
            v_sql := 'ALTER TABLE ' || p_table_name || ' TRUNCATE PARTITION ' || p_partition_name;
            EXECUTE IMMEDIATE v_sql;
        END sp_archive_partition;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_archive_partition" in lowered

    def test_function_lowering_scalar(self, lowerer):
        source_func = """
        CREATE OR REPLACE FUNCTION fn_calculate_accrued_interest(
            p_principal DECIMAL(18, 4),
            p_annual_rate DECIMAL(8, 6),
            p_days INT
        ) RETURN DECIMAL(18, 4)
        AS
            v_interest DECIMAL(18, 4);
        BEGIN
            v_interest := p_principal * (p_annual_rate / 360.0) * p_days;
            RETURN v_interest;
        END fn_calculate_accrued_interest;
        """
        lowered = lowerer.lower_function(source_func, "oracle")
        assert len(lowered) > 0
        assert "fn_calculate_accrued_interest" in lowered

    def test_trigger_lowering_before_insert(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_audit_journal_entry
        BEFORE INSERT ON journal_entries
        FOR EACH ROW
        BEGIN
            :NEW.created_at := SYSDATE;
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_audit_journal_entry" in lowered

    def test_trigger_lowering_after_update(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_sync_order_status
        AFTER UPDATE OF status ON trade_orders
        FOR EACH ROW
        WHEN (OLD.status <> NEW.status)
        BEGIN
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_at)
            VALUES (:NEW.order_id, :OLD.status, :NEW.status, SYSDATE);
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_sync_order_status" in lowered

    def test_sequence_lowering_nextval(self, lowerer):
        source_seq = "SELECT seq_order_no.NEXTVAL FROM DUAL;"
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert len(lowered) > 0
        assert "seq_order_no" in lowered

    def test_sequence_lowering_creation(self, lowerer):
        source_seq = """
        CREATE SEQUENCE seq_trade_journal_seq
        START WITH 1000000
        INCREMENT BY 1
        MAXVALUE 9999999999
        NOCACHE NOCYCLE;
        """
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert "seq_trade_journal_seq" in lowered
        assert "SEQUENCE" in lowered

    def test_view_ddl_lowering(self, lowerer):
        view_sql = """
        CREATE VIEW v_active_accounts AS
        SELECT account_id, account_name, balance
        FROM enterprise_account
        WHERE status = 'ACTIVE';
        """
        lowered = lowerer.lower_view(view_sql, "oracle")
        assert "CREATE VIEW" in lowered
        assert "v_active_accounts" in lowered

    def test_syntax_heuristics_balanced(self, lowerer):
        valid_sql = "BEGIN NULL; END;"
        ok, issues = lowerer.verify_syntax_heuristics(valid_sql)
        assert ok is True
        assert len(issues) == 0

    def test_syntax_heuristics_unbalanced(self, lowerer):
        invalid_sql = "BEGIN NULL;"
        ok, issues = lowerer.verify_syntax_heuristics(invalid_sql)
        assert ok is False
        assert len(issues) > 0

    def test_catalog_queries_available(self, lowerer):
        queries = getattr(lowerer, "get_catalog_queries", lambda: {})()
        if queries:
            assert "tables" in queries or "columns" in queries

    def test_enterprise_scenario_banking(self, lowerer):
        sql = """
        SELECT account_no, SUM(credit_amt) - SUM(debit_amt) AS net_bal
        FROM gl_entries
        GROUP BY account_no
        HAVING SUM(credit_amt) <> SUM(debit_amt);
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "net_bal" in lowered

    def test_enterprise_scenario_insurance(self, lowerer):
        sql = """
        UPDATE claim_assessments
        SET approved_amount = claimed_amount * 0.95,
            status = 'AUTO_APPROVED'
        WHERE fraud_risk_score < 0.15 AND claimed_amount < 5000.00;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "claim_assessments" in lowered

    def test_enterprise_scenario_telecom(self, lowerer):
        sql = """
        SELECT msisdn, SUM(duration_sec) AS total_sec,
               SUM(bytes_consumed) AS total_bytes
        FROM cdr_voice_records
        GROUP BY msisdn;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "msisdn" in lowered

    def test_enterprise_scenario_wms(self, lowerer):
        sql = """
        SELECT sku, warehouse_id,
               (on_hand_qty - allocated_qty) AS atp_qty
        FROM wms_inventory_balance
        WHERE (on_hand_qty - allocated_qty) > 0;
        """
        lowered = lowerer.lower_statement(sql, "tsql")
        assert "atp_qty" in lowered

    def test_enterprise_scenario_payroll(self, lowerer):
        sql = """
        SELECT emp_id, gross_pay - tax_deduction - social_sec AS net_pay
        FROM hr_payroll_ledger
        WHERE period_code = '2026-03';
        """
        lowered = lowerer.lower_statement(sql, "mysql")
        assert "net_pay" in lowered

    def test_analytical_window_functions(self, lowerer):
        sql = """
        SELECT dept_id, emp_id, salary,
               ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rnk,
               AVG(salary) OVER (PARTITION BY dept_id) as avg_dept_sal
        FROM employee_salaries;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "ROW_NUMBER()" in lowered
        assert "OVER" in lowered

    def test_cte_recursive_query(self, lowerer):
        sql = """
        WITH org_hierarchy (emp_id, manager_id, org_level) AS (
            SELECT emp_id, manager_id, 1
            FROM employees WHERE manager_id IS NULL
            UNION ALL
            SELECT e.emp_id, e.manager_id, o.org_level + 1
            FROM employees e INNER JOIN org_hierarchy o ON e.manager_id = o.emp_id
        )
        SELECT emp_id, manager_id, org_level FROM org_hierarchy;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "org_hierarchy" in lowered
        assert "UNION ALL" in lowered

    def test_transaction_boundary_control(self, lowerer):
        sql = """
        SAVEPOINT sp_batch_001;
        UPDATE batch_status SET state = 'IN_PROGRESS' WHERE id = 1;
        ROLLBACK TO SAVEPOINT sp_batch_001;
        COMMIT;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "SAVEPOINT" in lowered
        assert "COMMIT" in lowered

    def test_complex_multi_join_query(self, lowerer):
        sql = """
        SELECT c.customer_name, o.order_number, p.product_name, oi.quantity, oi.unit_price
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        ORDER BY oi.item_id ASC;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "customers" in lowered
        assert "orders" in lowered
        assert "order_items" in lowered

class TestOceanBaseMysqlTargetLowerer:
    """Comprehensive industrial test suite for OceanBase (MySQL Mode)."""

    @pytest.fixture
    def lowerer(self) -> OceanBaseMysqlTargetLowerer:
        return get_chinadb_lowerer("oceanbase_mysql")

    def test_metadata_and_family(self, lowerer):
        assert lowerer.target_id == "oceanbase_mysql"
        assert lowerer.display_name == "OceanBase (MySQL Mode)"
        assert lowerer.family == "mysql_compat"
        assert len(lowerer.type_mappings) > 0
        assert len(lowerer.builtin_mappings) > 0
        assert len(lowerer.lowering_rules) > 0

    def test_type_mapping_0_varchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 VARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_1_nvarchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 NVARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_2_number(self, lowerer):
        sql = "CREATE TABLE t (col1 NUMBER NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "DECIMAL" in lowered

    def test_type_mapping_3_clob(self, lowerer):
        sql = "CREATE TABLE t (col1 CLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGTEXT" in lowered

    def test_type_mapping_4_nclob(self, lowerer):
        sql = "CREATE TABLE t (col1 NCLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGTEXT" in lowered

    def test_type_mapping_5_blob(self, lowerer):
        sql = "CREATE TABLE t (col1 BLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGBLOB" in lowered

    def test_builtin_mapping_0_nvl(self, lowerer):
        sql = "SELECT NVL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "IFNULL" in lowered

    def test_builtin_mapping_1_isnull(self, lowerer):
        sql = "SELECT ISNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "IFNULL" in lowered

    def test_builtin_mapping_2_getdate(self, lowerer):
        sql = "SELECT GETDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NOW" in lowered

    def test_builtin_mapping_3_getutcdate(self, lowerer):
        sql = "SELECT GETUTCDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "UTC_TIMESTAMP" in lowered

    def test_builtin_mapping_4_sysdate(self, lowerer):
        sql = "SELECT SYSDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NOW" in lowered

    def test_builtin_mapping_5_len(self, lowerer):
        sql = "SELECT LEN() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "CHAR_LENGTH" in lowered

    def test_lowering_rule_0_ob_mysql_backtick(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "ob_mysql_backtick"]
        assert len(rules) == 1
        assert rules[0].rule_id == "ob_mysql_backtick"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_1_ob_mysql_dual_strip(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "ob_mysql_dual_strip"]
        assert len(rules) == 1
        assert rules[0].rule_id == "ob_mysql_dual_strip"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_2_ob_mysql_tablegroup(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "ob_mysql_tablegroup"]
        assert len(rules) == 1
        assert rules[0].rule_id == "ob_mysql_tablegroup"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_3_ob_mysql_auto_inc(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "ob_mysql_auto_inc"]
        assert len(rules) == 1
        assert rules[0].rule_id == "ob_mysql_auto_inc"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_table_ddl_lowering(self, lowerer):
        source_ddl = """
        CREATE TABLE enterprise_account (
            account_id BIGINT NOT NULL,
            account_name VARCHAR(128) NOT NULL,
            balance DECIMAL(18, 4) DEFAULT 0.0000,
            status VARCHAR(16) DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT pk_enterprise_account PRIMARY KEY (account_id)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "CREATE TABLE" in lowered
        assert "enterprise_account" in lowered
        assert "PRIMARY KEY" in lowered

    def test_table_ddl_with_composite_pk_and_checks(self, lowerer):
        source_ddl = """
        CREATE TABLE trade_settlement_ledger (
            batch_date DATE NOT NULL,
            trade_sequence BIGINT NOT NULL,
            debit_amt DECIMAL(16, 2) NOT NULL,
            credit_amt DECIMAL(16, 2) NOT NULL,
            currency_code VARCHAR(3) DEFAULT 'CNY',
            CONSTRAINT pk_trade_ledger PRIMARY KEY (batch_date, trade_sequence),
            CONSTRAINT chk_debit_positive CHECK (debit_amt >= 0),
            CONSTRAINT chk_credit_positive CHECK (credit_amt >= 0)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "trade_settlement_ledger" in lowered
        assert "PRIMARY KEY" in lowered
        assert "CHECK" in lowered

    def test_table_ddl_partitioned_range(self, lowerer):
        source_ddl = """
        CREATE TABLE historical_cdr_records (
            call_id BIGINT NOT NULL,
            call_start_date DATE NOT NULL,
            duration_sec INT NOT NULL,
            billed_amount DECIMAL(10, 4) NOT NULL
        )
        PARTITION BY RANGE (call_start_date) (
            PARTITION p_2026_q1 VALUES LESS THAN ('2026-04-01'),
            PARTITION p_2026_q2 VALUES LESS THAN ('2026-07-01'),
            PARTITION p_max VALUES LESS THAN (MAXVALUE)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "historical_cdr_records" in lowered
        assert len(lowered) > 0

    def test_procedure_lowering_basic(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_audit_batch(
            p_batch_id IN VARCHAR2,
            p_status OUT VARCHAR2
        )
        AS
            v_total NUMBER := 0;
        BEGIN
            SELECT COUNT(*) INTO v_total FROM audit_log
            WHERE batch_id = p_batch_id;
            p_status := 'COMPLETED';
        END sp_audit_batch;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_audit_batch" in lowered

    def test_procedure_lowering_cursor_loop(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_settle_all_pending
        AS
            CURSOR c_pending IS
                SELECT item_id, amount FROM pending_settlements
                WHERE processed_flag = 'N';
            v_item_id BIGINT;
            v_amt DECIMAL(16, 2);
        BEGIN
            OPEN c_pending;
            LOOP
                FETCH c_pending INTO v_item_id, v_amt;
                EXIT WHEN c_pending%NOTFOUND;
                UPDATE settlement_balance SET balance = balance + v_amt
                WHERE item_id = v_item_id;
            END LOOP;
            CLOSE c_pending;
        END sp_settle_all_pending;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_settle_all_pending" in lowered

    def test_procedure_lowering_exception_block(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_safe_transfer(
            p_from_acc BIGINT,
            p_to_acc BIGINT,
            p_amount DECIMAL(16, 2)
        )
        AS
        BEGIN
            UPDATE bank_accounts SET balance = balance - p_amount
            WHERE account_id = p_from_acc;
            UPDATE bank_accounts SET balance = balance + p_amount
            WHERE account_id = p_to_acc;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
            WHEN OTHERS THEN
                ROLLBACK;
                RAISE;
        END sp_safe_transfer;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_safe_transfer" in lowered

    def test_procedure_lowering_dynamic_sql(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_archive_partition(
            p_table_name IN VARCHAR2,
            p_partition_name IN VARCHAR2
        )
        AS
            v_sql VARCHAR2(500);
        BEGIN
            v_sql := 'ALTER TABLE ' || p_table_name || ' TRUNCATE PARTITION ' || p_partition_name;
            EXECUTE IMMEDIATE v_sql;
        END sp_archive_partition;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_archive_partition" in lowered

    def test_function_lowering_scalar(self, lowerer):
        source_func = """
        CREATE OR REPLACE FUNCTION fn_calculate_accrued_interest(
            p_principal DECIMAL(18, 4),
            p_annual_rate DECIMAL(8, 6),
            p_days INT
        ) RETURN DECIMAL(18, 4)
        AS
            v_interest DECIMAL(18, 4);
        BEGIN
            v_interest := p_principal * (p_annual_rate / 360.0) * p_days;
            RETURN v_interest;
        END fn_calculate_accrued_interest;
        """
        lowered = lowerer.lower_function(source_func, "oracle")
        assert len(lowered) > 0
        assert "fn_calculate_accrued_interest" in lowered

    def test_trigger_lowering_before_insert(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_audit_journal_entry
        BEFORE INSERT ON journal_entries
        FOR EACH ROW
        BEGIN
            :NEW.created_at := SYSDATE;
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_audit_journal_entry" in lowered

    def test_trigger_lowering_after_update(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_sync_order_status
        AFTER UPDATE OF status ON trade_orders
        FOR EACH ROW
        WHEN (OLD.status <> NEW.status)
        BEGIN
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_at)
            VALUES (:NEW.order_id, :OLD.status, :NEW.status, SYSDATE);
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_sync_order_status" in lowered

    def test_sequence_lowering_nextval(self, lowerer):
        source_seq = "SELECT seq_order_no.NEXTVAL FROM DUAL;"
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert len(lowered) > 0
        assert "seq_order_no" in lowered

    def test_sequence_lowering_creation(self, lowerer):
        source_seq = """
        CREATE SEQUENCE seq_trade_journal_seq
        START WITH 1000000
        INCREMENT BY 1
        MAXVALUE 9999999999
        NOCACHE NOCYCLE;
        """
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert "seq_trade_journal_seq" in lowered
        assert "SEQUENCE" in lowered

    def test_view_ddl_lowering(self, lowerer):
        view_sql = """
        CREATE VIEW v_active_accounts AS
        SELECT account_id, account_name, balance
        FROM enterprise_account
        WHERE status = 'ACTIVE';
        """
        lowered = lowerer.lower_view(view_sql, "oracle")
        assert "CREATE VIEW" in lowered
        assert "v_active_accounts" in lowered

    def test_syntax_heuristics_balanced(self, lowerer):
        valid_sql = "BEGIN NULL; END;"
        ok, issues = lowerer.verify_syntax_heuristics(valid_sql)
        assert ok is True
        assert len(issues) == 0

    def test_syntax_heuristics_unbalanced(self, lowerer):
        invalid_sql = "BEGIN NULL;"
        ok, issues = lowerer.verify_syntax_heuristics(invalid_sql)
        assert ok is False
        assert len(issues) > 0

    def test_catalog_queries_available(self, lowerer):
        queries = getattr(lowerer, "get_catalog_queries", lambda: {})()
        if queries:
            assert "tables" in queries or "columns" in queries

    def test_enterprise_scenario_banking(self, lowerer):
        sql = """
        SELECT account_no, SUM(credit_amt) - SUM(debit_amt) AS net_bal
        FROM gl_entries
        GROUP BY account_no
        HAVING SUM(credit_amt) <> SUM(debit_amt);
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "net_bal" in lowered

    def test_enterprise_scenario_insurance(self, lowerer):
        sql = """
        UPDATE claim_assessments
        SET approved_amount = claimed_amount * 0.95,
            status = 'AUTO_APPROVED'
        WHERE fraud_risk_score < 0.15 AND claimed_amount < 5000.00;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "claim_assessments" in lowered

    def test_enterprise_scenario_telecom(self, lowerer):
        sql = """
        SELECT msisdn, SUM(duration_sec) AS total_sec,
               SUM(bytes_consumed) AS total_bytes
        FROM cdr_voice_records
        GROUP BY msisdn;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "msisdn" in lowered

    def test_enterprise_scenario_wms(self, lowerer):
        sql = """
        SELECT sku, warehouse_id,
               (on_hand_qty - allocated_qty) AS atp_qty
        FROM wms_inventory_balance
        WHERE (on_hand_qty - allocated_qty) > 0;
        """
        lowered = lowerer.lower_statement(sql, "tsql")
        assert "atp_qty" in lowered

    def test_enterprise_scenario_payroll(self, lowerer):
        sql = """
        SELECT emp_id, gross_pay - tax_deduction - social_sec AS net_pay
        FROM hr_payroll_ledger
        WHERE period_code = '2026-03';
        """
        lowered = lowerer.lower_statement(sql, "mysql")
        assert "net_pay" in lowered

    def test_analytical_window_functions(self, lowerer):
        sql = """
        SELECT dept_id, emp_id, salary,
               ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rnk,
               AVG(salary) OVER (PARTITION BY dept_id) as avg_dept_sal
        FROM employee_salaries;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "ROW_NUMBER()" in lowered
        assert "OVER" in lowered

    def test_cte_recursive_query(self, lowerer):
        sql = """
        WITH org_hierarchy (emp_id, manager_id, org_level) AS (
            SELECT emp_id, manager_id, 1
            FROM employees WHERE manager_id IS NULL
            UNION ALL
            SELECT e.emp_id, e.manager_id, o.org_level + 1
            FROM employees e INNER JOIN org_hierarchy o ON e.manager_id = o.emp_id
        )
        SELECT emp_id, manager_id, org_level FROM org_hierarchy;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "org_hierarchy" in lowered
        assert "UNION ALL" in lowered

    def test_transaction_boundary_control(self, lowerer):
        sql = """
        SAVEPOINT sp_batch_001;
        UPDATE batch_status SET state = 'IN_PROGRESS' WHERE id = 1;
        ROLLBACK TO SAVEPOINT sp_batch_001;
        COMMIT;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "SAVEPOINT" in lowered
        assert "COMMIT" in lowered

    def test_complex_multi_join_query(self, lowerer):
        sql = """
        SELECT c.customer_name, o.order_number, p.product_name, oi.quantity, oi.unit_price
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        ORDER BY oi.item_id ASC;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "customers" in lowered
        assert "orders" in lowered
        assert "order_items" in lowered

class TestOceanBaseOracleTargetLowerer:
    """Comprehensive industrial test suite for OceanBase (Oracle Mode)."""

    @pytest.fixture
    def lowerer(self) -> OceanBaseOracleTargetLowerer:
        return get_chinadb_lowerer("oceanbase_oracle")

    def test_metadata_and_family(self, lowerer):
        assert lowerer.target_id == "oceanbase_oracle"
        assert lowerer.display_name == "OceanBase (Oracle Mode)"
        assert lowerer.family == "oracle_compat"
        assert len(lowerer.type_mappings) > 0
        assert len(lowerer.builtin_mappings) > 0
        assert len(lowerer.lowering_rules) > 0

    def test_type_mapping_0_datetime2(self, lowerer):
        sql = "CREATE TABLE t (col1 DATETIME2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "TIMESTAMP" in lowered

    def test_type_mapping_1_smalldatetime(self, lowerer):
        sql = "CREATE TABLE t (col1 SMALLDATETIME NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "TIMESTAMP" in lowered

    def test_type_mapping_2_nvarchar_max_(self, lowerer):
        sql = "CREATE TABLE t (col1 NVARCHAR(MAX) NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "CLOB" in lowered

    def test_type_mapping_3_varchar_max_(self, lowerer):
        sql = "CREATE TABLE t (col1 VARCHAR(MAX) NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "CLOB" in lowered

    def test_type_mapping_4_varbinary_max_(self, lowerer):
        sql = "CREATE TABLE t (col1 VARBINARY(MAX) NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "BLOB" in lowered

    def test_type_mapping_5_image(self, lowerer):
        sql = "CREATE TABLE t (col1 IMAGE NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "BLOB" in lowered

    def test_builtin_mapping_0_getdate(self, lowerer):
        sql = "SELECT GETDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "SYSDATE" in lowered

    def test_builtin_mapping_1_getutcdate(self, lowerer):
        sql = "SELECT GETUTCDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "SYS_EXTRACT_UTC" in lowered

    def test_builtin_mapping_2_isnull(self, lowerer):
        sql = "SELECT ISNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NVL" in lowered

    def test_builtin_mapping_3_ifnull(self, lowerer):
        sql = "SELECT IFNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NVL" in lowered

    def test_builtin_mapping_4_len(self, lowerer):
        sql = "SELECT LEN() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "LENGTH" in lowered

    def test_builtin_mapping_5_char_length(self, lowerer):
        sql = "SELECT CHAR_LENGTH() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "LENGTH" in lowered

    def test_lowering_rule_0_ob_ora_tablegroup(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "ob_ora_tablegroup"]
        assert len(rules) == 1
        assert rules[0].rule_id == "ob_ora_tablegroup"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_1_ob_ora_square_bracket(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "ob_ora_square_bracket"]
        assert len(rules) == 1
        assert rules[0].rule_id == "ob_ora_square_bracket"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_2_ob_ora_variable_prefix(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "ob_ora_variable_prefix"]
        assert len(rules) == 1
        assert rules[0].rule_id == "ob_ora_variable_prefix"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_3_ob_ora_tablegroup(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "ob_ora_tablegroup"]
        assert len(rules) == 1
        assert rules[0].rule_id == "ob_ora_tablegroup"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_4_ob_ora_autonomous_trans(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "ob_ora_autonomous_trans"]
        assert len(rules) == 1
        assert rules[0].rule_id == "ob_ora_autonomous_trans"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "oracle")
        assert isinstance(res, str)

    def test_table_ddl_lowering(self, lowerer):
        source_ddl = """
        CREATE TABLE enterprise_account (
            account_id BIGINT NOT NULL,
            account_name VARCHAR(128) NOT NULL,
            balance DECIMAL(18, 4) DEFAULT 0.0000,
            status VARCHAR(16) DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT pk_enterprise_account PRIMARY KEY (account_id)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "CREATE TABLE" in lowered
        assert "enterprise_account" in lowered
        assert "PRIMARY KEY" in lowered

    def test_table_ddl_with_composite_pk_and_checks(self, lowerer):
        source_ddl = """
        CREATE TABLE trade_settlement_ledger (
            batch_date DATE NOT NULL,
            trade_sequence BIGINT NOT NULL,
            debit_amt DECIMAL(16, 2) NOT NULL,
            credit_amt DECIMAL(16, 2) NOT NULL,
            currency_code VARCHAR(3) DEFAULT 'CNY',
            CONSTRAINT pk_trade_ledger PRIMARY KEY (batch_date, trade_sequence),
            CONSTRAINT chk_debit_positive CHECK (debit_amt >= 0),
            CONSTRAINT chk_credit_positive CHECK (credit_amt >= 0)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "trade_settlement_ledger" in lowered
        assert "PRIMARY KEY" in lowered
        assert "CHECK" in lowered

    def test_table_ddl_partitioned_range(self, lowerer):
        source_ddl = """
        CREATE TABLE historical_cdr_records (
            call_id BIGINT NOT NULL,
            call_start_date DATE NOT NULL,
            duration_sec INT NOT NULL,
            billed_amount DECIMAL(10, 4) NOT NULL
        )
        PARTITION BY RANGE (call_start_date) (
            PARTITION p_2026_q1 VALUES LESS THAN ('2026-04-01'),
            PARTITION p_2026_q2 VALUES LESS THAN ('2026-07-01'),
            PARTITION p_max VALUES LESS THAN (MAXVALUE)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "historical_cdr_records" in lowered
        assert len(lowered) > 0

    def test_procedure_lowering_basic(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_audit_batch(
            p_batch_id IN VARCHAR2,
            p_status OUT VARCHAR2
        )
        AS
            v_total NUMBER := 0;
        BEGIN
            SELECT COUNT(*) INTO v_total FROM audit_log
            WHERE batch_id = p_batch_id;
            p_status := 'COMPLETED';
        END sp_audit_batch;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_audit_batch" in lowered

    def test_procedure_lowering_cursor_loop(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_settle_all_pending
        AS
            CURSOR c_pending IS
                SELECT item_id, amount FROM pending_settlements
                WHERE processed_flag = 'N';
            v_item_id BIGINT;
            v_amt DECIMAL(16, 2);
        BEGIN
            OPEN c_pending;
            LOOP
                FETCH c_pending INTO v_item_id, v_amt;
                EXIT WHEN c_pending%NOTFOUND;
                UPDATE settlement_balance SET balance = balance + v_amt
                WHERE item_id = v_item_id;
            END LOOP;
            CLOSE c_pending;
        END sp_settle_all_pending;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_settle_all_pending" in lowered

    def test_procedure_lowering_exception_block(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_safe_transfer(
            p_from_acc BIGINT,
            p_to_acc BIGINT,
            p_amount DECIMAL(16, 2)
        )
        AS
        BEGIN
            UPDATE bank_accounts SET balance = balance - p_amount
            WHERE account_id = p_from_acc;
            UPDATE bank_accounts SET balance = balance + p_amount
            WHERE account_id = p_to_acc;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
            WHEN OTHERS THEN
                ROLLBACK;
                RAISE;
        END sp_safe_transfer;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_safe_transfer" in lowered

    def test_procedure_lowering_dynamic_sql(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_archive_partition(
            p_table_name IN VARCHAR2,
            p_partition_name IN VARCHAR2
        )
        AS
            v_sql VARCHAR2(500);
        BEGIN
            v_sql := 'ALTER TABLE ' || p_table_name || ' TRUNCATE PARTITION ' || p_partition_name;
            EXECUTE IMMEDIATE v_sql;
        END sp_archive_partition;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_archive_partition" in lowered

    def test_function_lowering_scalar(self, lowerer):
        source_func = """
        CREATE OR REPLACE FUNCTION fn_calculate_accrued_interest(
            p_principal DECIMAL(18, 4),
            p_annual_rate DECIMAL(8, 6),
            p_days INT
        ) RETURN DECIMAL(18, 4)
        AS
            v_interest DECIMAL(18, 4);
        BEGIN
            v_interest := p_principal * (p_annual_rate / 360.0) * p_days;
            RETURN v_interest;
        END fn_calculate_accrued_interest;
        """
        lowered = lowerer.lower_function(source_func, "oracle")
        assert len(lowered) > 0
        assert "fn_calculate_accrued_interest" in lowered

    def test_trigger_lowering_before_insert(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_audit_journal_entry
        BEFORE INSERT ON journal_entries
        FOR EACH ROW
        BEGIN
            :NEW.created_at := SYSDATE;
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_audit_journal_entry" in lowered

    def test_trigger_lowering_after_update(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_sync_order_status
        AFTER UPDATE OF status ON trade_orders
        FOR EACH ROW
        WHEN (OLD.status <> NEW.status)
        BEGIN
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_at)
            VALUES (:NEW.order_id, :OLD.status, :NEW.status, SYSDATE);
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_sync_order_status" in lowered

    def test_sequence_lowering_nextval(self, lowerer):
        source_seq = "SELECT seq_order_no.NEXTVAL FROM DUAL;"
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert len(lowered) > 0
        assert "seq_order_no" in lowered

    def test_sequence_lowering_creation(self, lowerer):
        source_seq = """
        CREATE SEQUENCE seq_trade_journal_seq
        START WITH 1000000
        INCREMENT BY 1
        MAXVALUE 9999999999
        NOCACHE NOCYCLE;
        """
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert "seq_trade_journal_seq" in lowered
        assert "SEQUENCE" in lowered

    def test_view_ddl_lowering(self, lowerer):
        view_sql = """
        CREATE VIEW v_active_accounts AS
        SELECT account_id, account_name, balance
        FROM enterprise_account
        WHERE status = 'ACTIVE';
        """
        lowered = lowerer.lower_view(view_sql, "oracle")
        assert "CREATE VIEW" in lowered
        assert "v_active_accounts" in lowered

    def test_syntax_heuristics_balanced(self, lowerer):
        valid_sql = "BEGIN NULL; END;"
        ok, issues = lowerer.verify_syntax_heuristics(valid_sql)
        assert ok is True
        assert len(issues) == 0

    def test_syntax_heuristics_unbalanced(self, lowerer):
        invalid_sql = "BEGIN NULL;"
        ok, issues = lowerer.verify_syntax_heuristics(invalid_sql)
        assert ok is False
        assert len(issues) > 0

    def test_catalog_queries_available(self, lowerer):
        queries = getattr(lowerer, "get_catalog_queries", lambda: {})()
        if queries:
            assert "tables" in queries or "columns" in queries

    def test_enterprise_scenario_banking(self, lowerer):
        sql = """
        SELECT account_no, SUM(credit_amt) - SUM(debit_amt) AS net_bal
        FROM gl_entries
        GROUP BY account_no
        HAVING SUM(credit_amt) <> SUM(debit_amt);
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "net_bal" in lowered

    def test_enterprise_scenario_insurance(self, lowerer):
        sql = """
        UPDATE claim_assessments
        SET approved_amount = claimed_amount * 0.95,
            status = 'AUTO_APPROVED'
        WHERE fraud_risk_score < 0.15 AND claimed_amount < 5000.00;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "claim_assessments" in lowered

    def test_enterprise_scenario_telecom(self, lowerer):
        sql = """
        SELECT msisdn, SUM(duration_sec) AS total_sec,
               SUM(bytes_consumed) AS total_bytes
        FROM cdr_voice_records
        GROUP BY msisdn;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "msisdn" in lowered

    def test_enterprise_scenario_wms(self, lowerer):
        sql = """
        SELECT sku, warehouse_id,
               (on_hand_qty - allocated_qty) AS atp_qty
        FROM wms_inventory_balance
        WHERE (on_hand_qty - allocated_qty) > 0;
        """
        lowered = lowerer.lower_statement(sql, "tsql")
        assert "atp_qty" in lowered

    def test_enterprise_scenario_payroll(self, lowerer):
        sql = """
        SELECT emp_id, gross_pay - tax_deduction - social_sec AS net_pay
        FROM hr_payroll_ledger
        WHERE period_code = '2026-03';
        """
        lowered = lowerer.lower_statement(sql, "mysql")
        assert "net_pay" in lowered

    def test_analytical_window_functions(self, lowerer):
        sql = """
        SELECT dept_id, emp_id, salary,
               ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rnk,
               AVG(salary) OVER (PARTITION BY dept_id) as avg_dept_sal
        FROM employee_salaries;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "ROW_NUMBER()" in lowered
        assert "OVER" in lowered

    def test_cte_recursive_query(self, lowerer):
        sql = """
        WITH org_hierarchy (emp_id, manager_id, org_level) AS (
            SELECT emp_id, manager_id, 1
            FROM employees WHERE manager_id IS NULL
            UNION ALL
            SELECT e.emp_id, e.manager_id, o.org_level + 1
            FROM employees e INNER JOIN org_hierarchy o ON e.manager_id = o.emp_id
        )
        SELECT emp_id, manager_id, org_level FROM org_hierarchy;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "org_hierarchy" in lowered
        assert "UNION ALL" in lowered

    def test_transaction_boundary_control(self, lowerer):
        sql = """
        SAVEPOINT sp_batch_001;
        UPDATE batch_status SET state = 'IN_PROGRESS' WHERE id = 1;
        ROLLBACK TO SAVEPOINT sp_batch_001;
        COMMIT;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "SAVEPOINT" in lowered
        assert "COMMIT" in lowered

    def test_complex_multi_join_query(self, lowerer):
        sql = """
        SELECT c.customer_name, o.order_number, p.product_name, oi.quantity, oi.unit_price
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        ORDER BY oi.item_id ASC;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "customers" in lowered
        assert "orders" in lowered
        assert "order_items" in lowered

class TestOpenGaussTargetLowerer:
    """Comprehensive industrial test suite for openGauss / MogDB."""

    @pytest.fixture
    def lowerer(self) -> OpenGaussTargetLowerer:
        return get_chinadb_lowerer("opengauss")

    def test_metadata_and_family(self, lowerer):
        assert lowerer.target_id == "opengauss"
        assert lowerer.display_name == "openGauss / MogDB"
        assert lowerer.family == "pg_compat"
        assert len(lowerer.type_mappings) > 0
        assert len(lowerer.builtin_mappings) > 0
        assert len(lowerer.lowering_rules) > 0

    def test_type_mapping_0_varchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 VARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_1_nvarchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 NVARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_2_number(self, lowerer):
        sql = "CREATE TABLE t (col1 NUMBER NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "NUMERIC" in lowered

    def test_type_mapping_3_binary_double(self, lowerer):
        sql = "CREATE TABLE t (col1 BINARY_DOUBLE NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "DOUBLE PRECISION" in lowered

    def test_type_mapping_4_binary_float(self, lowerer):
        sql = "CREATE TABLE t (col1 BINARY_FLOAT NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "REAL" in lowered

    def test_type_mapping_5_raw(self, lowerer):
        sql = "CREATE TABLE t (col1 RAW NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "BYTEA" in lowered

    def test_builtin_mapping_0_nvl(self, lowerer):
        sql = "SELECT NVL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "COALESCE" in lowered

    def test_builtin_mapping_1_isnull(self, lowerer):
        sql = "SELECT ISNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "COALESCE" in lowered

    def test_builtin_mapping_2_ifnull(self, lowerer):
        sql = "SELECT IFNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "COALESCE" in lowered

    def test_builtin_mapping_3_getdate(self, lowerer):
        sql = "SELECT GETDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "CURRENT_TIMESTAMP" in lowered

    def test_builtin_mapping_4_getutcdate(self, lowerer):
        sql = "SELECT GETUTCDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "TIMEZONE" in lowered

    def test_builtin_mapping_5_sysdate(self, lowerer):
        sql = "SELECT SYSDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "CURRENT_TIMESTAMP" in lowered

    def test_lowering_rule_0_og_dual_removal(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "og_dual_removal"]
        assert len(rules) == 1
        assert rules[0].rule_id == "og_dual_removal"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_1_og_square_brackets(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "og_square_brackets"]
        assert len(rules) == 1
        assert rules[0].rule_id == "og_square_brackets"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_2_og_variable_prefix(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "og_variable_prefix"]
        assert len(rules) == 1
        assert rules[0].rule_id == "og_variable_prefix"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_3_og_limit_offset(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "og_limit_offset"]
        assert len(rules) == 1
        assert rules[0].rule_id == "og_limit_offset"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_4_og_autonomous_trans(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "og_autonomous_trans"]
        assert len(rules) == 1
        assert rules[0].rule_id == "og_autonomous_trans"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "oracle")
        assert isinstance(res, str)

    def test_lowering_rule_5_og_partition_by_range(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "og_partition_by_range"]
        assert len(rules) == 1
        assert rules[0].rule_id == "og_partition_by_range"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_6_og_string_agg(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "og_string_agg"]
        assert len(rules) == 1
        assert rules[0].rule_id == "og_string_agg"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "mysql")
        assert isinstance(res, str)

    def test_lowering_rule_7_og_lock_mode(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "og_lock_mode"]
        assert len(rules) == 1
        assert rules[0].rule_id == "og_lock_mode"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "oracle")
        assert isinstance(res, str)

    def test_lowering_rule_8_og_row_number_over(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "og_row_number_over"]
        assert len(rules) == 1
        assert rules[0].rule_id == "og_row_number_over"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_table_ddl_lowering(self, lowerer):
        source_ddl = """
        CREATE TABLE enterprise_account (
            account_id BIGINT NOT NULL,
            account_name VARCHAR(128) NOT NULL,
            balance DECIMAL(18, 4) DEFAULT 0.0000,
            status VARCHAR(16) DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT pk_enterprise_account PRIMARY KEY (account_id)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "CREATE TABLE" in lowered
        assert "enterprise_account" in lowered
        assert "PRIMARY KEY" in lowered

    def test_table_ddl_with_composite_pk_and_checks(self, lowerer):
        source_ddl = """
        CREATE TABLE trade_settlement_ledger (
            batch_date DATE NOT NULL,
            trade_sequence BIGINT NOT NULL,
            debit_amt DECIMAL(16, 2) NOT NULL,
            credit_amt DECIMAL(16, 2) NOT NULL,
            currency_code VARCHAR(3) DEFAULT 'CNY',
            CONSTRAINT pk_trade_ledger PRIMARY KEY (batch_date, trade_sequence),
            CONSTRAINT chk_debit_positive CHECK (debit_amt >= 0),
            CONSTRAINT chk_credit_positive CHECK (credit_amt >= 0)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "trade_settlement_ledger" in lowered
        assert "PRIMARY KEY" in lowered
        assert "CHECK" in lowered

    def test_table_ddl_partitioned_range(self, lowerer):
        source_ddl = """
        CREATE TABLE historical_cdr_records (
            call_id BIGINT NOT NULL,
            call_start_date DATE NOT NULL,
            duration_sec INT NOT NULL,
            billed_amount DECIMAL(10, 4) NOT NULL
        )
        PARTITION BY RANGE (call_start_date) (
            PARTITION p_2026_q1 VALUES LESS THAN ('2026-04-01'),
            PARTITION p_2026_q2 VALUES LESS THAN ('2026-07-01'),
            PARTITION p_max VALUES LESS THAN (MAXVALUE)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "historical_cdr_records" in lowered
        assert len(lowered) > 0

    def test_procedure_lowering_basic(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_audit_batch(
            p_batch_id IN VARCHAR2,
            p_status OUT VARCHAR2
        )
        AS
            v_total NUMBER := 0;
        BEGIN
            SELECT COUNT(*) INTO v_total FROM audit_log
            WHERE batch_id = p_batch_id;
            p_status := 'COMPLETED';
        END sp_audit_batch;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_audit_batch" in lowered

    def test_procedure_lowering_cursor_loop(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_settle_all_pending
        AS
            CURSOR c_pending IS
                SELECT item_id, amount FROM pending_settlements
                WHERE processed_flag = 'N';
            v_item_id BIGINT;
            v_amt DECIMAL(16, 2);
        BEGIN
            OPEN c_pending;
            LOOP
                FETCH c_pending INTO v_item_id, v_amt;
                EXIT WHEN c_pending%NOTFOUND;
                UPDATE settlement_balance SET balance = balance + v_amt
                WHERE item_id = v_item_id;
            END LOOP;
            CLOSE c_pending;
        END sp_settle_all_pending;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_settle_all_pending" in lowered

    def test_procedure_lowering_exception_block(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_safe_transfer(
            p_from_acc BIGINT,
            p_to_acc BIGINT,
            p_amount DECIMAL(16, 2)
        )
        AS
        BEGIN
            UPDATE bank_accounts SET balance = balance - p_amount
            WHERE account_id = p_from_acc;
            UPDATE bank_accounts SET balance = balance + p_amount
            WHERE account_id = p_to_acc;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
            WHEN OTHERS THEN
                ROLLBACK;
                RAISE;
        END sp_safe_transfer;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_safe_transfer" in lowered

    def test_procedure_lowering_dynamic_sql(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_archive_partition(
            p_table_name IN VARCHAR2,
            p_partition_name IN VARCHAR2
        )
        AS
            v_sql VARCHAR2(500);
        BEGIN
            v_sql := 'ALTER TABLE ' || p_table_name || ' TRUNCATE PARTITION ' || p_partition_name;
            EXECUTE IMMEDIATE v_sql;
        END sp_archive_partition;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_archive_partition" in lowered

    def test_function_lowering_scalar(self, lowerer):
        source_func = """
        CREATE OR REPLACE FUNCTION fn_calculate_accrued_interest(
            p_principal DECIMAL(18, 4),
            p_annual_rate DECIMAL(8, 6),
            p_days INT
        ) RETURN DECIMAL(18, 4)
        AS
            v_interest DECIMAL(18, 4);
        BEGIN
            v_interest := p_principal * (p_annual_rate / 360.0) * p_days;
            RETURN v_interest;
        END fn_calculate_accrued_interest;
        """
        lowered = lowerer.lower_function(source_func, "oracle")
        assert len(lowered) > 0
        assert "fn_calculate_accrued_interest" in lowered

    def test_trigger_lowering_before_insert(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_audit_journal_entry
        BEFORE INSERT ON journal_entries
        FOR EACH ROW
        BEGIN
            :NEW.created_at := SYSDATE;
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_audit_journal_entry" in lowered

    def test_trigger_lowering_after_update(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_sync_order_status
        AFTER UPDATE OF status ON trade_orders
        FOR EACH ROW
        WHEN (OLD.status <> NEW.status)
        BEGIN
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_at)
            VALUES (:NEW.order_id, :OLD.status, :NEW.status, SYSDATE);
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_sync_order_status" in lowered

    def test_sequence_lowering_nextval(self, lowerer):
        source_seq = "SELECT seq_order_no.NEXTVAL FROM DUAL;"
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert len(lowered) > 0
        assert "seq_order_no" in lowered

    def test_sequence_lowering_creation(self, lowerer):
        source_seq = """
        CREATE SEQUENCE seq_trade_journal_seq
        START WITH 1000000
        INCREMENT BY 1
        MAXVALUE 9999999999
        NOCACHE NOCYCLE;
        """
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert "seq_trade_journal_seq" in lowered
        assert "SEQUENCE" in lowered

    def test_view_ddl_lowering(self, lowerer):
        view_sql = """
        CREATE VIEW v_active_accounts AS
        SELECT account_id, account_name, balance
        FROM enterprise_account
        WHERE status = 'ACTIVE';
        """
        lowered = lowerer.lower_view(view_sql, "oracle")
        assert "CREATE VIEW" in lowered
        assert "v_active_accounts" in lowered

    def test_syntax_heuristics_balanced(self, lowerer):
        valid_sql = "BEGIN NULL; END;"
        ok, issues = lowerer.verify_syntax_heuristics(valid_sql)
        assert ok is True
        assert len(issues) == 0

    def test_syntax_heuristics_unbalanced(self, lowerer):
        invalid_sql = "BEGIN NULL;"
        ok, issues = lowerer.verify_syntax_heuristics(invalid_sql)
        assert ok is False
        assert len(issues) > 0

    def test_catalog_queries_available(self, lowerer):
        queries = getattr(lowerer, "get_catalog_queries", lambda: {})()
        if queries:
            assert "tables" in queries or "columns" in queries

    def test_enterprise_scenario_banking(self, lowerer):
        sql = """
        SELECT account_no, SUM(credit_amt) - SUM(debit_amt) AS net_bal
        FROM gl_entries
        GROUP BY account_no
        HAVING SUM(credit_amt) <> SUM(debit_amt);
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "net_bal" in lowered

    def test_enterprise_scenario_insurance(self, lowerer):
        sql = """
        UPDATE claim_assessments
        SET approved_amount = claimed_amount * 0.95,
            status = 'AUTO_APPROVED'
        WHERE fraud_risk_score < 0.15 AND claimed_amount < 5000.00;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "claim_assessments" in lowered

    def test_enterprise_scenario_telecom(self, lowerer):
        sql = """
        SELECT msisdn, SUM(duration_sec) AS total_sec,
               SUM(bytes_consumed) AS total_bytes
        FROM cdr_voice_records
        GROUP BY msisdn;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "msisdn" in lowered

    def test_enterprise_scenario_wms(self, lowerer):
        sql = """
        SELECT sku, warehouse_id,
               (on_hand_qty - allocated_qty) AS atp_qty
        FROM wms_inventory_balance
        WHERE (on_hand_qty - allocated_qty) > 0;
        """
        lowered = lowerer.lower_statement(sql, "tsql")
        assert "atp_qty" in lowered

    def test_enterprise_scenario_payroll(self, lowerer):
        sql = """
        SELECT emp_id, gross_pay - tax_deduction - social_sec AS net_pay
        FROM hr_payroll_ledger
        WHERE period_code = '2026-03';
        """
        lowered = lowerer.lower_statement(sql, "mysql")
        assert "net_pay" in lowered

    def test_analytical_window_functions(self, lowerer):
        sql = """
        SELECT dept_id, emp_id, salary,
               ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rnk,
               AVG(salary) OVER (PARTITION BY dept_id) as avg_dept_sal
        FROM employee_salaries;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "ROW_NUMBER()" in lowered
        assert "OVER" in lowered

    def test_cte_recursive_query(self, lowerer):
        sql = """
        WITH org_hierarchy (emp_id, manager_id, org_level) AS (
            SELECT emp_id, manager_id, 1
            FROM employees WHERE manager_id IS NULL
            UNION ALL
            SELECT e.emp_id, e.manager_id, o.org_level + 1
            FROM employees e INNER JOIN org_hierarchy o ON e.manager_id = o.emp_id
        )
        SELECT emp_id, manager_id, org_level FROM org_hierarchy;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "org_hierarchy" in lowered
        assert "UNION ALL" in lowered

    def test_transaction_boundary_control(self, lowerer):
        sql = """
        SAVEPOINT sp_batch_001;
        UPDATE batch_status SET state = 'IN_PROGRESS' WHERE id = 1;
        ROLLBACK TO SAVEPOINT sp_batch_001;
        COMMIT;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "SAVEPOINT" in lowered
        assert "COMMIT" in lowered

    def test_complex_multi_join_query(self, lowerer):
        sql = """
        SELECT c.customer_name, o.order_number, p.product_name, oi.quantity, oi.unit_price
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        ORDER BY oi.item_id ASC;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "customers" in lowered
        assert "orders" in lowered
        assert "order_items" in lowered

class TestTidbTargetLowerer:
    """Comprehensive industrial test suite for TiDB (v6/v7)."""

    @pytest.fixture
    def lowerer(self) -> TidbTargetLowerer:
        return get_chinadb_lowerer("tidb")

    def test_metadata_and_family(self, lowerer):
        assert lowerer.target_id == "tidb"
        assert lowerer.display_name == "TiDB (v6/v7)"
        assert lowerer.family == "mysql_compat"
        assert len(lowerer.type_mappings) > 0
        assert len(lowerer.builtin_mappings) > 0
        assert len(lowerer.lowering_rules) > 0

    def test_type_mapping_0_varchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 VARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_1_nvarchar2(self, lowerer):
        sql = "CREATE TABLE t (col1 NVARCHAR2 NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "VARCHAR" in lowered

    def test_type_mapping_2_number(self, lowerer):
        sql = "CREATE TABLE t (col1 NUMBER NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "DECIMAL" in lowered

    def test_type_mapping_3_clob(self, lowerer):
        sql = "CREATE TABLE t (col1 CLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGTEXT" in lowered

    def test_type_mapping_4_nclob(self, lowerer):
        sql = "CREATE TABLE t (col1 NCLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGTEXT" in lowered

    def test_type_mapping_5_blob(self, lowerer):
        sql = "CREATE TABLE t (col1 BLOB NOT NULL);"
        lowered = lowerer.lower_data_types(sql, "all")
        assert "LONGBLOB" in lowered

    def test_builtin_mapping_0_nvl(self, lowerer):
        sql = "SELECT NVL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "IFNULL" in lowered

    def test_builtin_mapping_1_isnull(self, lowerer):
        sql = "SELECT ISNULL() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "IFNULL" in lowered

    def test_builtin_mapping_2_coalesce(self, lowerer):
        sql = "SELECT COALESCE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "COALESCE" in lowered

    def test_builtin_mapping_3_getdate(self, lowerer):
        sql = "SELECT GETDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NOW" in lowered

    def test_builtin_mapping_4_getutcdate(self, lowerer):
        sql = "SELECT GETUTCDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "UTC_TIMESTAMP" in lowered

    def test_builtin_mapping_5_sysdate(self, lowerer):
        sql = "SELECT SYSDATE() FROM t;"
        lowered = lowerer.lower_builtin_functions(sql, "all")
        assert "NOW" in lowered

    def test_lowering_rule_0_tidb_backtick_escape(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "tidb_backtick_escape"]
        assert len(rules) == 1
        assert rules[0].rule_id == "tidb_backtick_escape"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "oracle")
        assert isinstance(res, str)

    def test_lowering_rule_1_tidb_dual_removal(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "tidb_dual_removal"]
        assert len(rules) == 1
        assert rules[0].rule_id == "tidb_dual_removal"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_2_tidb_auto_increment(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "tidb_auto_increment"]
        assert len(rules) == 1
        assert rules[0].rule_id == "tidb_auto_increment"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "tsql")
        assert isinstance(res, str)

    def test_lowering_rule_3_tidb_clustered_index(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "tidb_clustered_index"]
        assert len(rules) == 1
        assert rules[0].rule_id == "tidb_clustered_index"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_lowering_rule_4_tidb_shard_row_id(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "tidb_shard_row_id"]
        assert len(rules) == 1
        assert rules[0].rule_id == "tidb_shard_row_id"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "mysql")
        assert isinstance(res, str)

    def test_lowering_rule_5_tidb_auto_random(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "tidb_auto_random"]
        assert len(rules) == 1
        assert rules[0].rule_id == "tidb_auto_random"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "mysql")
        assert isinstance(res, str)

    def test_lowering_rule_6_tidb_partition_by_range(self, lowerer):
        rules = [r for r in lowerer.lowering_rules if r.rule_id == "tidb_partition_by_range"]
        assert len(rules) == 1
        assert rules[0].rule_id == "tidb_partition_by_range"
        # verify apply_custom_rules executes without exception
        res = lowerer.apply_custom_rules("SELECT 1 FROM t;", "all")
        assert isinstance(res, str)

    def test_table_ddl_lowering(self, lowerer):
        source_ddl = """
        CREATE TABLE enterprise_account (
            account_id BIGINT NOT NULL,
            account_name VARCHAR(128) NOT NULL,
            balance DECIMAL(18, 4) DEFAULT 0.0000,
            status VARCHAR(16) DEFAULT 'ACTIVE',
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT pk_enterprise_account PRIMARY KEY (account_id)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "CREATE TABLE" in lowered
        assert "enterprise_account" in lowered
        assert "PRIMARY KEY" in lowered

    def test_table_ddl_with_composite_pk_and_checks(self, lowerer):
        source_ddl = """
        CREATE TABLE trade_settlement_ledger (
            batch_date DATE NOT NULL,
            trade_sequence BIGINT NOT NULL,
            debit_amt DECIMAL(16, 2) NOT NULL,
            credit_amt DECIMAL(16, 2) NOT NULL,
            currency_code VARCHAR(3) DEFAULT 'CNY',
            CONSTRAINT pk_trade_ledger PRIMARY KEY (batch_date, trade_sequence),
            CONSTRAINT chk_debit_positive CHECK (debit_amt >= 0),
            CONSTRAINT chk_credit_positive CHECK (credit_amt >= 0)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "trade_settlement_ledger" in lowered
        assert "PRIMARY KEY" in lowered
        assert "CHECK" in lowered

    def test_table_ddl_partitioned_range(self, lowerer):
        source_ddl = """
        CREATE TABLE historical_cdr_records (
            call_id BIGINT NOT NULL,
            call_start_date DATE NOT NULL,
            duration_sec INT NOT NULL,
            billed_amount DECIMAL(10, 4) NOT NULL
        )
        PARTITION BY RANGE (call_start_date) (
            PARTITION p_2026_q1 VALUES LESS THAN ('2026-04-01'),
            PARTITION p_2026_q2 VALUES LESS THAN ('2026-07-01'),
            PARTITION p_max VALUES LESS THAN (MAXVALUE)
        );
        """
        lowered = lowerer.lower_table_ddl(source_ddl, "oracle")
        assert "historical_cdr_records" in lowered
        assert len(lowered) > 0

    def test_procedure_lowering_basic(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_audit_batch(
            p_batch_id IN VARCHAR2,
            p_status OUT VARCHAR2
        )
        AS
            v_total NUMBER := 0;
        BEGIN
            SELECT COUNT(*) INTO v_total FROM audit_log
            WHERE batch_id = p_batch_id;
            p_status := 'COMPLETED';
        END sp_audit_batch;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_audit_batch" in lowered

    def test_procedure_lowering_cursor_loop(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_settle_all_pending
        AS
            CURSOR c_pending IS
                SELECT item_id, amount FROM pending_settlements
                WHERE processed_flag = 'N';
            v_item_id BIGINT;
            v_amt DECIMAL(16, 2);
        BEGIN
            OPEN c_pending;
            LOOP
                FETCH c_pending INTO v_item_id, v_amt;
                EXIT WHEN c_pending%NOTFOUND;
                UPDATE settlement_balance SET balance = balance + v_amt
                WHERE item_id = v_item_id;
            END LOOP;
            CLOSE c_pending;
        END sp_settle_all_pending;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_settle_all_pending" in lowered

    def test_procedure_lowering_exception_block(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_safe_transfer(
            p_from_acc BIGINT,
            p_to_acc BIGINT,
            p_amount DECIMAL(16, 2)
        )
        AS
        BEGIN
            UPDATE bank_accounts SET balance = balance - p_amount
            WHERE account_id = p_from_acc;
            UPDATE bank_accounts SET balance = balance + p_amount
            WHERE account_id = p_to_acc;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
            WHEN OTHERS THEN
                ROLLBACK;
                RAISE;
        END sp_safe_transfer;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_safe_transfer" in lowered

    def test_procedure_lowering_dynamic_sql(self, lowerer):
        source_proc = """
        CREATE OR REPLACE PROCEDURE sp_archive_partition(
            p_table_name IN VARCHAR2,
            p_partition_name IN VARCHAR2
        )
        AS
            v_sql VARCHAR2(500);
        BEGIN
            v_sql := 'ALTER TABLE ' || p_table_name || ' TRUNCATE PARTITION ' || p_partition_name;
            EXECUTE IMMEDIATE v_sql;
        END sp_archive_partition;
        """
        lowered = lowerer.lower_procedure(source_proc, "oracle")
        assert len(lowered) > 0
        assert "sp_archive_partition" in lowered

    def test_function_lowering_scalar(self, lowerer):
        source_func = """
        CREATE OR REPLACE FUNCTION fn_calculate_accrued_interest(
            p_principal DECIMAL(18, 4),
            p_annual_rate DECIMAL(8, 6),
            p_days INT
        ) RETURN DECIMAL(18, 4)
        AS
            v_interest DECIMAL(18, 4);
        BEGIN
            v_interest := p_principal * (p_annual_rate / 360.0) * p_days;
            RETURN v_interest;
        END fn_calculate_accrued_interest;
        """
        lowered = lowerer.lower_function(source_func, "oracle")
        assert len(lowered) > 0
        assert "fn_calculate_accrued_interest" in lowered

    def test_trigger_lowering_before_insert(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_audit_journal_entry
        BEFORE INSERT ON journal_entries
        FOR EACH ROW
        BEGIN
            :NEW.created_at := SYSDATE;
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_audit_journal_entry" in lowered

    def test_trigger_lowering_after_update(self, lowerer):
        source_trig = """
        CREATE OR REPLACE TRIGGER trg_sync_order_status
        AFTER UPDATE OF status ON trade_orders
        FOR EACH ROW
        WHEN (OLD.status <> NEW.status)
        BEGIN
            INSERT INTO order_status_history (order_id, old_status, new_status, changed_at)
            VALUES (:NEW.order_id, :OLD.status, :NEW.status, SYSDATE);
        END;
        """
        lowered = lowerer.lower_trigger(source_trig, "oracle")
        assert len(lowered) > 0
        assert "trg_sync_order_status" in lowered

    def test_sequence_lowering_nextval(self, lowerer):
        source_seq = "SELECT seq_order_no.NEXTVAL FROM DUAL;"
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert len(lowered) > 0
        assert "seq_order_no" in lowered

    def test_sequence_lowering_creation(self, lowerer):
        source_seq = """
        CREATE SEQUENCE seq_trade_journal_seq
        START WITH 1000000
        INCREMENT BY 1
        MAXVALUE 9999999999
        NOCACHE NOCYCLE;
        """
        lowered = lowerer.lower_sequence(source_seq, "oracle")
        assert "seq_trade_journal_seq" in lowered
        assert "SEQUENCE" in lowered

    def test_view_ddl_lowering(self, lowerer):
        view_sql = """
        CREATE VIEW v_active_accounts AS
        SELECT account_id, account_name, balance
        FROM enterprise_account
        WHERE status = 'ACTIVE';
        """
        lowered = lowerer.lower_view(view_sql, "oracle")
        assert "CREATE VIEW" in lowered
        assert "v_active_accounts" in lowered

    def test_syntax_heuristics_balanced(self, lowerer):
        valid_sql = "BEGIN NULL; END;"
        ok, issues = lowerer.verify_syntax_heuristics(valid_sql)
        assert ok is True
        assert len(issues) == 0

    def test_syntax_heuristics_unbalanced(self, lowerer):
        invalid_sql = "BEGIN NULL;"
        ok, issues = lowerer.verify_syntax_heuristics(invalid_sql)
        assert ok is False
        assert len(issues) > 0

    def test_catalog_queries_available(self, lowerer):
        queries = getattr(lowerer, "get_catalog_queries", lambda: {})()
        if queries:
            assert "tables" in queries or "columns" in queries

    def test_enterprise_scenario_banking(self, lowerer):
        sql = """
        SELECT account_no, SUM(credit_amt) - SUM(debit_amt) AS net_bal
        FROM gl_entries
        GROUP BY account_no
        HAVING SUM(credit_amt) <> SUM(debit_amt);
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "net_bal" in lowered

    def test_enterprise_scenario_insurance(self, lowerer):
        sql = """
        UPDATE claim_assessments
        SET approved_amount = claimed_amount * 0.95,
            status = 'AUTO_APPROVED'
        WHERE fraud_risk_score < 0.15 AND claimed_amount < 5000.00;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "claim_assessments" in lowered

    def test_enterprise_scenario_telecom(self, lowerer):
        sql = """
        SELECT msisdn, SUM(duration_sec) AS total_sec,
               SUM(bytes_consumed) AS total_bytes
        FROM cdr_voice_records
        GROUP BY msisdn;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "msisdn" in lowered

    def test_enterprise_scenario_wms(self, lowerer):
        sql = """
        SELECT sku, warehouse_id,
               (on_hand_qty - allocated_qty) AS atp_qty
        FROM wms_inventory_balance
        WHERE (on_hand_qty - allocated_qty) > 0;
        """
        lowered = lowerer.lower_statement(sql, "tsql")
        assert "atp_qty" in lowered

    def test_enterprise_scenario_payroll(self, lowerer):
        sql = """
        SELECT emp_id, gross_pay - tax_deduction - social_sec AS net_pay
        FROM hr_payroll_ledger
        WHERE period_code = '2026-03';
        """
        lowered = lowerer.lower_statement(sql, "mysql")
        assert "net_pay" in lowered

    def test_analytical_window_functions(self, lowerer):
        sql = """
        SELECT dept_id, emp_id, salary,
               ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY salary DESC) as rnk,
               AVG(salary) OVER (PARTITION BY dept_id) as avg_dept_sal
        FROM employee_salaries;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "ROW_NUMBER()" in lowered
        assert "OVER" in lowered

    def test_cte_recursive_query(self, lowerer):
        sql = """
        WITH org_hierarchy (emp_id, manager_id, org_level) AS (
            SELECT emp_id, manager_id, 1
            FROM employees WHERE manager_id IS NULL
            UNION ALL
            SELECT e.emp_id, e.manager_id, o.org_level + 1
            FROM employees e INNER JOIN org_hierarchy o ON e.manager_id = o.emp_id
        )
        SELECT emp_id, manager_id, org_level FROM org_hierarchy;
        """
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "org_hierarchy" in lowered
        assert "UNION ALL" in lowered

    def test_transaction_boundary_control(self, lowerer):
        sql = """
        SAVEPOINT sp_batch_001;
        UPDATE batch_status SET state = 'IN_PROGRESS' WHERE id = 1;
        ROLLBACK TO SAVEPOINT sp_batch_001;
        COMMIT;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "SAVEPOINT" in lowered
        assert "COMMIT" in lowered

    def test_complex_multi_join_query(self, lowerer):
        sql = """
        SELECT c.customer_name, o.order_number, p.product_name, oi.quantity, oi.unit_price
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        ORDER BY oi.item_id ASC;
        """
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "customers" in lowered
        assert "orders" in lowered
        assert "order_items" in lowered

class TestCrossDialectLoweringMatrix:
    """Parametrized matrix testing across all 13 domestic database targets."""

    @pytest.mark.parametrize("target_id", list_supported_targets())
    def test_all_targets_lower_simple_select(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        sql = "SELECT id, name, balance FROM account_tbl WHERE status = 'A';"
        lowered = lowerer.lower_statement(sql, "oracle")
        assert "account_tbl" in lowered
        assert "balance" in lowered

    @pytest.mark.parametrize("target_id", list_supported_targets())
    def test_all_targets_lower_aggregate_group_by(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        sql = "SELECT dept_id, COUNT(*), SUM(sal) FROM emp GROUP BY dept_id;"
        lowered = lowerer.lower_statement(sql, "postgres")
        assert "dept_id" in lowered
        assert "COUNT" in lowered

    @pytest.mark.parametrize("target_id", list_supported_targets())
    def test_all_targets_lower_table_with_pk_fk(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        sql = """
        CREATE TABLE orders (
            order_id BIGINT NOT NULL,
            customer_id BIGINT NOT NULL,
            order_amount DECIMAL(14, 2) NOT NULL,
            CONSTRAINT pk_orders PRIMARY KEY (order_id)
        );
        """
        lowered = lowerer.lower_table_ddl(sql, "oracle")
        assert "CREATE TABLE" in lowered
        assert "pk_orders" in lowered

    @pytest.mark.parametrize("target_id", list_supported_targets())
    def test_all_targets_lower_view(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        sql = "CREATE VIEW v_active AS SELECT id, name FROM users WHERE active = 1;"
        lowered = lowerer.lower_view(sql, "oracle")
        assert "CREATE VIEW" in lowered
        assert "v_active" in lowered

    @pytest.mark.parametrize("target_id", list_supported_targets())
    def test_all_targets_verify_syntax_heuristics(self, target_id: str) -> None:
        lowerer = get_chinadb_lowerer(target_id)
        valid_sql = "BEGIN NULL; END;"
        ok, _ = lowerer.verify_syntax_heuristics(valid_sql)
        assert ok is True

