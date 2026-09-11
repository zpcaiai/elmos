"""ChinaDB Industrial Benchmarks Suite.

Contains 52 enterprise-grade complex procedural benchmarks across 5 key industry domains:
1. Core Banking & Double-Entry Settlement (12)
2. Telecom Rating & Real-Time Billing (10)
3. Insurance & Actuarial IFRS 17 (10)
4. Logistics, Supply Chain & WMS (10)
5. Government, Tax & Enterprise ERP (10)

Covers autonomous transactions, package state management, dynamic cursors,
complex triggers with pseudo-records, multi-tier exception hierarchies, and savepoints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from elmos_sql_dialect.models import Dialect


@dataclass
class IndustrialBenchmarkCase:
    id: str
    domain: str
    name: str
    source_dialect: Dialect
    kind: str  # "PROCEDURE" | "FUNCTION" | "TRIGGER" | "PACKAGE"
    source_sql: str
    spec_sql: str | None = None
    body_sql: str | None = None
    complexity: str = "HIGH"
    features: list[str] = field(default_factory=list)


BENCHMARKS: list[IndustrialBenchmarkCase] = [
    # =========================================================================
    # 1. CORE BANKING & DOUBLE-ENTRY SETTLEMENT (12 CASES)
    # =========================================================================
    IndustrialBenchmarkCase(
        id="FIN-01-DOUBLE-ENTRY",
        domain="Core Banking",
        name="Double-entry journal transfer with ledger balance check",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="CRITICAL",
        features=["TRANSACTION_ACID", "SAVEPOINT", "EXCEPTION_HIERARCHY", "FOR_UPDATE"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_cbs_transfer_funds (
            p_src_acc IN VARCHAR2,
            p_dst_acc IN VARCHAR2,
            p_amount IN NUMBER,
            p_curr IN VARCHAR2,
            p_channel IN VARCHAR2,
            p_out_status OUT VARCHAR2
        ) IS
            v_src_bal NUMBER(18, 4);
            v_src_od NUMBER(18, 4);
            v_dst_stat VARCHAR2(16);
            v_journal_id VARCHAR2(64);
        BEGIN
            IF p_amount <= 0 THEN
                p_out_status := 'ERR_INVALID_AMOUNT';
                RETURN;
            END IF;

            SAVEPOINT sv_transfer;

            SELECT balance, overdraft_limit INTO v_src_bal, v_src_od
            FROM cbs_accounts WHERE account_no = p_src_acc FOR UPDATE;

            IF (v_src_bal + v_src_od) < p_amount THEN
                p_out_status := 'ERR_INSUFFICIENT_FUNDS';
                ROLLBACK TO sv_transfer;
                RETURN;
            END IF;

            SELECT status INTO v_dst_stat
            FROM cbs_accounts WHERE account_no = p_dst_acc FOR UPDATE;

            IF v_dst_stat <> 'ACTIVE' THEN
                p_out_status := 'ERR_TARGET_ACCOUNT_INACTIVE';
                ROLLBACK TO sv_transfer;
                RETURN;
            END IF;

            UPDATE cbs_accounts SET balance = balance - p_amount, updated_at = CURRENT_TIMESTAMP WHERE account_no = p_src_acc;
            UPDATE cbs_accounts SET balance = balance + p_amount, updated_at = CURRENT_TIMESTAMP WHERE account_no = p_dst_acc;

            COMMIT;
            p_out_status := 'SUCCESS';
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK TO sv_transfer;
                p_out_status := 'ERR_ACCOUNT_NOT_FOUND';
            WHEN OTHERS THEN
                ROLLBACK;
                p_out_status := 'ERR_SYSTEM_EXCEPTION';
        END sp_cbs_transfer_funds;
        """,
    ),
    IndustrialBenchmarkCase(
        id="FIN-02-AUTONOMOUS-AUDIT",
        domain="Core Banking",
        name="Autonomous transaction compliance audit logger",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["PRAGMA_AUTONOMOUS_TRANSACTION", "ISOLATED_COMMIT"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_cbs_log_audit_event (
            p_event_type IN VARCHAR2,
            p_actor_id IN VARCHAR2,
            p_target_id IN VARCHAR2,
            p_payload IN VARCHAR2,
            p_risk_score IN NUMBER
        ) IS
            PRAGMA AUTONOMOUS_TRANSACTION;
        BEGIN
            INSERT INTO cbs_audit_log (
                event_type, actor_id, target_id, payload, risk_score, created_at
            ) VALUES (
                p_event_type, p_actor_id, p_target_id, p_payload, p_risk_score, CURRENT_TIMESTAMP
            );
            COMMIT;
        END sp_cbs_log_audit_event;
        """,
    ),
    IndustrialBenchmarkCase(
        id="FIN-03-LOAN-AMORTIZATION",
        domain="Core Banking",
        name="Loan repayment schedule calculator with monthly compound interest",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="CRITICAL",
        features=["FOR_LOOP", "NUMERIC_DECIMAL", "DYNAMIC_INSERT"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_cbs_generate_loan_schedule (
            p_contract_no IN VARCHAR2,
            p_principal IN NUMBER,
            p_annual_rate IN NUMBER,
            p_tenor_months IN NUMBER
        ) IS
            v_monthly_rate NUMBER(14, 8);
            v_annuity NUMBER(18, 4);
            v_rem_principal NUMBER(18, 4);
            v_interest_part NUMBER(18, 4);
            v_principal_part NUMBER(18, 4);
            v_month INTEGER;
        BEGIN
            v_monthly_rate := p_annual_rate / 12.0;
            v_annuity := (p_principal * v_monthly_rate) / (1.0 - 1.0 / ((1.0 + v_monthly_rate) ** p_tenor_months));
            v_rem_principal := p_principal;

            FOR v_month IN 1..p_tenor_months LOOP
                v_interest_part := v_rem_principal * v_monthly_rate;
                v_principal_part := v_annuity - v_interest_part;
                v_rem_principal := v_rem_principal - v_principal_part;

                INSERT INTO cbs_loan_repayment_schedule (
                    contract_no, installment_no, due_principal, due_interest, rem_principal
                ) VALUES (
                    p_contract_no, v_month, v_principal_part, v_interest_part, v_rem_principal
                );
            END LOOP;
            COMMIT;
        END sp_cbs_generate_loan_schedule;
        """,
    ),
    IndustrialBenchmarkCase(
        id="FIN-04-DAILY-INTEREST-ACCRUAL",
        domain="Core Banking",
        name="EOD deposit daily interest accrual with cursor loop",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="CRITICAL",
        features=["CURSOR_FOR_LOOP", "ACTUAL_365", "BATCH_UPDATE"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_cbs_accrue_daily_interest (
            p_branch_code IN VARCHAR2,
            p_out_count OUT NUMBER
        ) IS
            CURSOR cur_accounts IS
                SELECT account_no, balance, interest_rate
                FROM cbs_accounts
                WHERE branch_code = p_branch_code AND status = 'ACTIVE' AND balance > 0;
            v_accrued NUMBER(18, 4);
            v_count NUMBER := 0;
        BEGIN
            FOR rec IN cur_accounts LOOP
                v_accrued := rec.balance * (rec.interest_rate / 365.0);
                IF v_accrued > 0.0001 THEN
                    UPDATE cbs_accounts
                    SET balance = balance + v_accrued,
                        last_interest_date = CURRENT_TIMESTAMP
                    WHERE account_no = rec.account_no;
                    v_count := v_count + 1;
                END IF;
            END LOOP;
            COMMIT;
            p_out_count := v_count;
        END sp_cbs_accrue_daily_interest;
        """,
    ),
    IndustrialBenchmarkCase(
        id="FIN-05-FX-REVALUATION",
        domain="Core Banking",
        name="Multi-currency Nostro account foreign exchange revaluation",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["EXCEPTION_OTHERS", "MULTI_JOIN", "PRECISION_DECIMAL"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_cbs_revalue_fx (
            p_base_curr IN VARCHAR2,
            p_target_curr IN VARCHAR2,
            p_out_diff OUT NUMBER
        ) IS
            v_fx_rate NUMBER(14, 6);
            v_foreign_bal NUMBER(18, 4);
            v_cny_equiv NUMBER(18, 4);
        BEGIN
            SELECT middle_rate INTO v_fx_rate
            FROM cbs_fx_rates
            WHERE base_currency = p_base_curr AND target_currency = p_target_curr AND status = 'ACTIVE';

            SELECT COALESCE(SUM(balance), 0) INTO v_foreign_bal
            FROM cbs_accounts
            WHERE currency_code = p_target_curr AND status = 'ACTIVE';

            v_cny_equiv := v_foreign_bal * v_fx_rate;
            p_out_diff := v_cny_equiv;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                p_out_diff := 0;
            WHEN OTHERS THEN
                p_out_diff := -1;
        END sp_cbs_revalue_fx;
        """,
    ),
    IndustrialBenchmarkCase(
        id="FIN-06-AML-RISK-EVALUATOR",
        domain="Core Banking",
        name="Anti-money laundering velocity monitoring rule engine",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["DYNAMIC_SQL", "EXECUTE_IMMEDIATE", "AGGREGATION"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_cbs_evaluate_aml_risk (
            p_customer_id IN VARCHAR2,
            p_window_hours IN NUMBER,
            p_out_risk_level OUT VARCHAR2
        ) IS
            v_tx_count NUMBER := 0;
            v_total_vol NUMBER(18, 4) := 0;
            v_query VARCHAR2(500);
        BEGIN
            v_query := 'SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM cbs_settlement_transactions WHERE source_account IN (SELECT account_no FROM cbs_accounts WHERE customer_id = :1)';
            EXECUTE IMMEDIATE v_query INTO v_tx_count, v_total_vol USING p_customer_id;

            IF v_total_vol > 500000 OR v_tx_count > 50 THEN
                p_out_risk_level := 'CRITICAL_HIGH';
                INSERT INTO cbs_suspicious_tx_alerts(customer_id, risk_score, alert_time)
                VALUES (p_customer_id, 95, CURRENT_TIMESTAMP);
            ELSIF v_total_vol > 100000 OR v_tx_count > 20 THEN
                p_out_risk_level := 'MEDIUM_ELEVATED';
            ELSE
                p_out_risk_level := 'NORMAL';
            END IF;
            COMMIT;
        END sp_cbs_evaluate_aml_risk;
        """,
    ),
    IndustrialBenchmarkCase(
        id="FIN-07-STANDING-ORDER-BATCH",
        domain="Core Banking",
        name="Batch execution of recurring scheduled standing orders",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["CURSOR_LOOP", "NESTED_PROC_CALL", "IDEMPOTENT"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_cbs_process_standing_orders (
            p_batch_date IN DATE,
            p_out_success OUT NUMBER,
            p_out_failure OUT NUMBER
        ) IS
            CURSOR cur_orders IS
                SELECT order_id, source_account, target_account, transfer_amount
                FROM cbs_standing_orders
                WHERE active_flag = 1 AND next_execution_date <= p_batch_date;
            v_status VARCHAR2(32);
        BEGIN
            p_out_success := 0;
            p_out_failure := 0;
            FOR rec IN cur_orders LOOP
                sp_cbs_transfer_funds(rec.source_account, rec.target_account, rec.transfer_amount, 'CNY', 'AUTO', v_status);
                IF v_status = 'SUCCESS' THEN
                    p_out_success := p_out_success + 1;
                    UPDATE cbs_standing_orders SET last_execution_status = 'SUCCESS' WHERE order_id = rec.order_id;
                ELSE
                    p_out_failure := p_out_failure + 1;
                    UPDATE cbs_standing_orders SET last_execution_status = v_status WHERE order_id = rec.order_id;
                END IF;
            END LOOP;
            COMMIT;
        END sp_cbs_process_standing_orders;
        """,
    ),
    IndustrialBenchmarkCase(
        id="FIN-08-ACCOUNT-HOLD-CONTROL",
        domain="Core Banking",
        name="Judicial freeze and compliance hold enforcement",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["TRIGGER_SAFETY", "ATOMIC_FREEZE", "RECORD_LOCK"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_cbs_apply_account_hold (
            p_acc_no IN VARCHAR2,
            p_amount IN NUMBER,
            p_reason IN VARCHAR2,
            p_authority IN VARCHAR2,
            p_out_hold_id OUT VARCHAR2
        ) IS
            v_curr_frozen NUMBER(18, 4);
        BEGIN
            SELECT frozen_balance INTO v_curr_frozen
            FROM cbs_accounts WHERE account_no = p_acc_no FOR UPDATE;

            UPDATE cbs_accounts
            SET frozen_balance = frozen_balance + p_amount,
                updated_at = CURRENT_TIMESTAMP
            WHERE account_no = p_acc_no;

            p_out_hold_id := 'HLD_' || TO_CHAR(CURRENT_TIMESTAMP, 'YYYYMMDDHH24MISS');
            INSERT INTO cbs_account_holds(hold_id, account_no, hold_amount, hold_reason, issuing_authority)
            VALUES (p_out_hold_id, p_acc_no, p_amount, p_reason, p_authority);
            COMMIT;
        END sp_cbs_apply_account_hold;
        """,
    ),
    IndustrialBenchmarkCase(
        id="FIN-09-TRIAL-BALANCE-EOD",
        domain="Core Banking",
        name="End-of-day general ledger trial balance verification",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["TRIAL_BALANCE", "DEBIT_CREDIT_EQUALITY", "ZERO_DIFFERENCE"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_cbs_reconcile_eod (
            p_branch_code IN VARCHAR2,
            p_out_is_balanced OUT NUMBER,
            p_out_diff OUT NUMBER
        ) IS
            v_total_debits NUMBER(18, 4) := 0;
            v_total_credits NUMBER(18, 4) := 0;
        BEGIN
            SELECT COALESCE(SUM(amount), 0) INTO v_total_debits
            FROM cbs_general_ledger
            WHERE branch_code = p_branch_code AND entry_type = 'DEBIT';

            SELECT COALESCE(SUM(amount), 0) INTO v_total_credits
            FROM cbs_general_ledger
            WHERE branch_code = p_branch_code AND entry_type = 'CREDIT';

            p_out_diff := v_total_debits - v_total_credits;
            IF ABS(p_out_diff) < 0.0001 THEN
                p_out_is_balanced := 1;
            ELSE
                p_out_is_balanced := 0;
            END IF;
        END sp_cbs_reconcile_eod;
        """,
    ),
    IndustrialBenchmarkCase(
        id="FIN-10-MERCHANT-BATCH-SETTLE",
        domain="Core Banking",
        name="Merchant POS transaction batch clearing and fee deduction",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["FEE_SCHEDULE", "MULTI_TIER", "SETTLEMENT"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_cbs_merchant_batch_settle (
            p_merchant_id IN VARCHAR2,
            p_gross_amount IN NUMBER,
            p_fee_rate IN NUMBER,
            p_out_net OUT NUMBER
        ) IS
            v_fee NUMBER(18, 4);
        BEGIN
            v_fee := p_gross_amount * p_fee_rate;
            p_out_net := p_gross_amount - v_fee;

            UPDATE cbs_accounts
            SET balance = balance + p_out_net
            WHERE customer_id = p_merchant_id AND account_type = 'MERCHANT';

            COMMIT;
        END sp_cbs_merchant_batch_settle;
        """,
    ),
    IndustrialBenchmarkCase(
        id="FIN-11-AUDIT-TRIGGER-ROW",
        domain="Core Banking",
        name="Row-level balance change tamper-proof audit trigger",
        source_dialect=Dialect.ORACLE,
        kind="TRIGGER",
        complexity="CRITICAL",
        features=["TRIGGER_PSEUDO_RECORDS", "NEW_OLD_COMPARE", "FOR_EACH_ROW"],
        source_sql="""
        CREATE OR REPLACE TRIGGER trg_cbs_account_balance_audit
        AFTER UPDATE OF balance ON cbs_accounts
        FOR EACH ROW
        DECLARE
            v_diff NUMBER(18, 4);
        BEGIN
            v_diff := :NEW.balance - :OLD.balance;
            IF v_diff <> 0 THEN
                INSERT INTO cbs_audit_log (
                    event_type, actor_id, target_id, payload, risk_score, created_at
                ) VALUES (
                    'BALANCE_CHANGE', USER, :NEW.account_no, 'DELTA=' || TO_CHAR(v_diff), 10, CURRENT_TIMESTAMP
                );
            END IF;
        END;
        """,
    ),
    IndustrialBenchmarkCase(
        id="FIN-12-PACKAGE-CBS-OPS",
        domain="Core Banking",
        name="Core Banking Operations Package (Spec and Body)",
        source_dialect=Dialect.ORACLE,
        kind="PACKAGE",
        complexity="CRITICAL",
        features=["PACKAGE_SPEC_BODY", "SESSION_STATE", "INITIALIZATION_BLOCK"],
        source_sql="",
        spec_sql="""
        CREATE OR REPLACE PACKAGE cbs_ops_pkg IS
            c_clearing_house_code CONSTANT VARCHAR2(16) := 'PBOC_HVPS';
            g_teller_id VARCHAR2(32);
            g_workstation_ip VARCHAR2(45);

            PROCEDURE init_teller_session(p_teller IN VARCHAR2, p_ip IN VARCHAR2);
            FUNCTION get_fee_rate(p_tier IN VARCHAR2) RETURN NUMBER;
            PROCEDURE debit_account(p_acc IN VARCHAR2, p_amount IN NUMBER);
        END cbs_ops_pkg;
        """,
        body_sql="""
        CREATE OR REPLACE PACKAGE BODY cbs_ops_pkg IS
            v_session_login_time DATE;

            PROCEDURE init_teller_session(p_teller IN VARCHAR2, p_ip IN VARCHAR2) IS
            BEGIN
                g_teller_id := p_teller;
                g_workstation_ip := p_ip;
                v_session_login_time := CURRENT_TIMESTAMP;
            END init_teller_session;

            FUNCTION get_fee_rate(p_tier IN VARCHAR2) RETURN NUMBER IS
            BEGIN
                IF p_tier = 'VIP' THEN
                    RETURN 0.0005;
                ELSIF p_tier = 'STANDARD' THEN
                    RETURN 0.0015;
                ELSE
                    RETURN 0.0030;
                END IF;
            END get_fee_rate;

            PROCEDURE debit_account(p_acc IN VARCHAR2, p_amount IN NUMBER) IS
            BEGIN
                UPDATE cbs_accounts SET balance = balance - p_amount WHERE account_no = p_acc;
            END debit_account;

        BEGIN
            g_teller_id := 'SYSTEM';
            v_session_login_time := CURRENT_TIMESTAMP;
        END cbs_ops_pkg;
        """,
    ),

    # =========================================================================
    # 2. TELECOM RATING & REAL-TIME BILLING (10 CASES)
    # =========================================================================
    IndustrialBenchmarkCase(
        id="TEL-01-VOICE-CDR-RATING",
        domain="Telecom Billing",
        name="Voice Call Detail Record (CDR) duration and distance rating",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="CRITICAL",
        features=["DURATION_BUCKETING", "PEAK_OFFPEAK", "TARIFF_EVAL"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_tel_rate_voice_cdr (
            p_cdr_id IN VARCHAR2,
            p_caller IN VARCHAR2,
            p_duration_sec IN NUMBER,
            p_call_type IN VARCHAR2,
            p_out_charge OUT NUMBER
        ) IS
            v_rate_per_min NUMBER(8, 4);
            v_billable_min NUMBER;
        BEGIN
            v_billable_min := CEIL(p_duration_sec / 60.0);
            IF p_call_type = 'LOCAL' THEN
                v_rate_per_min := 0.1500;
            ELSIF p_call_type = 'NATIONAL_LD' THEN
                v_rate_per_min := 0.3500;
            ELSE
                v_rate_per_min := 1.8000;
            END IF;

            p_out_charge := v_billable_min * v_rate_per_min;
            UPDATE tel_cdr_records
            SET rated_charge = p_out_charge, rating_status = 'RATED'
            WHERE cdr_id = p_cdr_id;
            COMMIT;
        END sp_tel_rate_voice_cdr;
        """,
    ),
    IndustrialBenchmarkCase(
        id="TEL-02-DATA-STEPDOWN-RATING",
        domain="Telecom Billing",
        name="Data roaming stepped pricing with tier boundary conditions",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["TIERED_STEPDOWN", "STEP_LOGIC", "MATH_ROUNDING"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_tel_rate_data_cdr (
            p_cdr_id IN VARCHAR2,
            p_bytes_used IN NUMBER,
            p_out_charge OUT NUMBER
        ) IS
            v_mb_used NUMBER;
        BEGIN
            v_mb_used := CEIL(p_bytes_used / (1024.0 * 1024.0));
            IF v_mb_used <= 1000 THEN
                p_out_charge := v_mb_used * 0.05;
            ELSIF v_mb_used <= 5000 THEN
                p_out_charge := (1000 * 0.05) + ((v_mb_used - 1000) * 0.03);
            ELSE
                p_out_charge := (1000 * 0.05) + (4000 * 0.03) + ((v_mb_used - 5000) * 0.01);
            END IF;
            COMMIT;
        END sp_tel_rate_data_cdr;
        """,
    ),
    IndustrialBenchmarkCase(
        id="TEL-03-OCS-CREDIT-RESERVATION",
        domain="Telecom Billing",
        name="Online Charging System (OCS) diameter credit reservation",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="CRITICAL",
        features=["OCS_RESERVATION", "LOCK_BALANCE", "EXPIRY_TS"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_tel_reserve_ocs_credit (
            p_sub_id IN VARCHAR2,
            p_units_req IN NUMBER,
            p_unit_price IN NUMBER,
            p_out_session_id OUT VARCHAR2,
            p_out_granted_units OUT NUMBER
        ) IS
            v_cost NUMBER(14, 4);
            v_rem_bal NUMBER(14, 4);
        BEGIN
            v_cost := p_units_req * p_unit_price;
            SELECT balance INTO v_rem_bal
            FROM tel_subscriber_wallets WHERE subscriber_id = p_sub_id FOR UPDATE;

            IF v_rem_bal >= v_cost THEN
                p_out_granted_units := p_units_req;
                UPDATE tel_subscriber_wallets
                SET reserved_balance = reserved_balance + v_cost
                WHERE subscriber_id = p_sub_id;
            ELSE
                p_out_granted_units := FLOOR(v_rem_bal / p_unit_price);
            END IF;
            p_out_session_id := 'OCS_' || p_sub_id || '_' || TO_CHAR(CURRENT_TIMESTAMP, 'HH24MISS');
            COMMIT;
        END sp_tel_reserve_ocs_credit;
        """,
    ),
    IndustrialBenchmarkCase(
        id="TEL-04-MONTHLY-BILL-GENERATOR",
        domain="Telecom Billing",
        name="Subscriber monthly bill aggregation with VAT calculation",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["INVOICE_AGGREGATION", "TAX_BREAKDOWN", "DATE_TRUNC"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_tel_generate_monthly_invoice (
            p_sub_id IN VARCHAR2,
            p_billing_cycle IN VARCHAR2,
            p_out_invoice_total OUT NUMBER
        ) IS
            v_voice_charge NUMBER(14, 4) := 0;
            v_data_charge NUMBER(14, 4) := 0;
            v_vat_amount NUMBER(14, 4);
        BEGIN
            SELECT COALESCE(SUM(rated_charge), 0) INTO v_voice_charge
            FROM tel_cdr_records
            WHERE subscriber_id = p_sub_id AND billing_cycle = p_billing_cycle AND service_type = 'VOICE';

            SELECT COALESCE(SUM(rated_charge), 0) INTO v_data_charge
            FROM tel_cdr_records
            WHERE subscriber_id = p_sub_id AND billing_cycle = p_billing_cycle AND service_type = 'DATA';

            v_vat_amount := (v_voice_charge + v_data_charge) * 0.06;
            p_out_invoice_total := v_voice_charge + v_data_charge + v_vat_amount;
            COMMIT;
        END sp_tel_generate_monthly_invoice;
        """,
    ),
    IndustrialBenchmarkCase(
        id="TEL-05-PREPAID-VOUCHER-RECHARGE",
        domain="Telecom Billing",
        name="Prepaid scratch-card voucher redemption with hash verification",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["VOUCHER_REDEMPTION", "HASH_CHECK", "STATUS_TRANSITION"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_tel_redeem_voucher (
            p_sub_id IN VARCHAR2,
            p_voucher_pin IN VARCHAR2,
            p_out_status OUT VARCHAR2
        ) IS
            v_face_value NUMBER(10, 2);
            v_state VARCHAR2(16);
        BEGIN
            SELECT face_value, status INTO v_face_value, v_state
            FROM tel_vouchers WHERE pin_code = p_voucher_pin FOR UPDATE;

            IF v_state <> 'AVAILABLE' THEN
                p_out_status := 'ERR_VOUCHER_ALREADY_USED';
                RETURN;
            END IF;

            UPDATE tel_vouchers SET status = 'CONSUMED', redeemed_by = p_sub_id, redeemed_time = CURRENT_TIMESTAMP WHERE pin_code = p_voucher_pin;
            UPDATE tel_subscriber_wallets SET balance = balance + v_face_value WHERE subscriber_id = p_sub_id;
            p_out_status := 'SUCCESS';
            COMMIT;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                p_out_status := 'ERR_INVALID_PIN';
        END sp_tel_redeem_voucher;
        """,
    ),
    IndustrialBenchmarkCase(
        id="TEL-06-BALANCE-THRESHOLD-TRIGGER",
        domain="Telecom Billing",
        name="Subscriber low-balance real-time alert trigger",
        source_dialect=Dialect.ORACLE,
        kind="TRIGGER",
        complexity="HIGH",
        features=["AFTER_UPDATE_TRIGGER", "THRESHOLD_EVENT", "NOTIFICATION_QUEUE"],
        source_sql="""
        CREATE OR REPLACE TRIGGER trg_tel_low_balance_alert
        AFTER UPDATE OF balance ON tel_subscriber_wallets
        FOR EACH ROW
        DECLARE
            v_threshold NUMBER := 10.00;
        BEGIN
            IF :OLD.balance >= v_threshold AND :NEW.balance < v_threshold THEN
                INSERT INTO tel_notification_queue(subscriber_id, alert_msg, priority, queued_at)
                VALUES (:NEW.subscriber_id, 'Your prepaid balance is below $10. Please recharge.', 1, CURRENT_TIMESTAMP);
            END IF;
        END;
        """,
    ),
    IndustrialBenchmarkCase(
        id="TEL-07-FAMILY-PLAN-POOLING",
        domain="Telecom Billing",
        name="Family shared data pool quota reallocation procedure",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["HIERARCHICAL_ACCOUNT", "QUOTA_DEDUCTION", "POOLING"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_tel_family_pool_deduct (
            p_pool_id IN VARCHAR2,
            p_member_sub_id IN VARCHAR2,
            p_bytes IN NUMBER,
            p_out_allowed OUT NUMBER
        ) IS
            v_rem_pool NUMBER(18, 0);
        BEGIN
            SELECT rem_bytes INTO v_rem_pool
            FROM tel_shared_pools WHERE pool_id = p_pool_id FOR UPDATE;

            IF v_rem_pool >= p_bytes THEN
                UPDATE tel_shared_pools SET rem_bytes = rem_bytes - p_bytes WHERE pool_id = p_pool_id;
                p_out_allowed := 1;
            ELSE
                p_out_allowed := 0;
            END IF;
            COMMIT;
        END sp_tel_family_pool_deduct;
        """,
    ),
    IndustrialBenchmarkCase(
        id="TEL-08-SERVICE-SUSPEND-CASCADE",
        domain="Telecom Billing",
        name="Delinquent account automated service suspension cascade",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["CASCADE_UPDATE", "SERVICE_PROVISIONING", "AUDIT_TRACKING"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_tel_suspend_delinquent_accounts (
            p_grace_period_days IN NUMBER,
            p_out_suspended_count OUT NUMBER
        ) IS
            CURSOR cur_delinquents IS
                SELECT subscriber_id FROM tel_subscriber_wallets
                WHERE balance < 0 AND overdue_days > p_grace_period_days AND account_status = 'ACTIVE';
            v_count NUMBER := 0;
        BEGIN
            FOR rec IN cur_delinquents LOOP
                UPDATE tel_subscriber_wallets SET account_status = 'SUSPENDED' WHERE subscriber_id = rec.subscriber_id;
                UPDATE tel_services SET provision_status = 'BARRED' WHERE subscriber_id = rec.subscriber_id;
                v_count := v_count + 1;
            END LOOP;
            COMMIT;
            p_out_suspended_count := v_count;
        END sp_tel_suspend_delinquent_accounts;
        """,
    ),
    IndustrialBenchmarkCase(
        id="TEL-09-ROAMING-SETTLEMENT",
        domain="Telecom Billing",
        name="Inter-carrier wholesale roaming TAP3 file settlement calculation",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["SDR_CURRENCY", "WHOLESALE_DISCOUNT", "TAP3_RECON"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_tel_roaming_carrier_settle (
            p_partner_carrier IN VARCHAR2,
            p_settle_period IN VARCHAR2,
            p_out_net_sdr OUT NUMBER
        ) IS
            v_inbound_sdr NUMBER(18, 4) := 0;
            v_outbound_sdr NUMBER(18, 4) := 0;
        BEGIN
            SELECT COALESCE(SUM(charge_sdr), 0) INTO v_inbound_sdr
            FROM tel_roaming_tap3_records
            WHERE visiting_carrier = p_partner_carrier AND period = p_settle_period;

            SELECT COALESCE(SUM(charge_sdr), 0) INTO v_outbound_sdr
            FROM tel_roaming_tap3_records
            WHERE home_carrier = p_partner_carrier AND period = p_settle_period;

            p_out_net_sdr := v_inbound_sdr - v_outbound_sdr;
        END sp_tel_roaming_carrier_settle;
        """,
    ),
    IndustrialBenchmarkCase(
        id="TEL-10-PACKAGE-OCS-RATING",
        domain="Telecom Billing",
        name="Online Charging & Tariff Rating Engine Package",
        source_dialect=Dialect.ORACLE,
        kind="PACKAGE",
        complexity="CRITICAL",
        features=["PACKAGE_SPEC_BODY", "STATEFUL_CACHE", "TARIFF_MATH"],
        source_sql="",
        spec_sql="""
        CREATE OR REPLACE PACKAGE tel_rating_pkg IS
            g_peak_start_hour CONSTANT NUMBER := 8;
            g_peak_end_hour CONSTANT NUMBER := 22;
            g_active_session_count NUMBER := 0;

            FUNCTION is_peak_time(p_timestamp IN TIMESTAMP) RETURN NUMBER;
            PROCEDURE rate_session(p_sub_id IN VARCHAR2, p_service IN VARCHAR2, p_units IN NUMBER, p_out_charge OUT NUMBER);
        END tel_rating_pkg;
        """,
        body_sql="""
        CREATE OR REPLACE PACKAGE BODY tel_rating_pkg IS
            v_last_rate_update TIMESTAMP;

            FUNCTION is_peak_time(p_timestamp IN TIMESTAMP) RETURN NUMBER IS
                v_hour NUMBER;
            BEGIN
                v_hour := EXTRACT(HOUR FROM p_timestamp);
                IF v_hour >= g_peak_start_hour AND v_hour < g_peak_end_hour THEN
                    RETURN 1;
                ELSE
                    RETURN 0;
                END IF;
            END is_peak_time;

            PROCEDURE rate_session(p_sub_id IN VARCHAR2, p_service IN VARCHAR2, p_units IN NUMBER, p_out_charge OUT NUMBER) IS
            BEGIN
                IF p_service = 'DATA' THEN
                    p_out_charge := p_units * 0.0001;
                ELSE
                    p_out_charge := p_units * 0.0020;
                END IF;
                g_active_session_count := g_active_session_count + 1;
            END rate_session;

        BEGIN
            v_last_rate_update := CURRENT_TIMESTAMP;
        END tel_rating_pkg;
        """,
    ),

    # =========================================================================
    # 3. INSURANCE & ACTUARIAL IFRS 17 (10 CASES)
    # =========================================================================
    IndustrialBenchmarkCase(
        id="INS-01-IFRS17-DCF-VALUATION",
        domain="Insurance IFRS 17",
        name="Discounted Cash Flow (DCF) fulfillment cash flow calculation",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="CRITICAL",
        features=["DISCOUNT_CURVE", "ACTUARIAL_SUM", "TENOR_LOOP"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_ins_ifrs17_dcf_valuation (
            p_cohort_id IN VARCHAR2,
            p_discount_rate IN NUMBER,
            p_out_fulfilment_cf OUT NUMBER
        ) IS
            CURSOR cur_cashflows IS
                SELECT period_year, expected_claims, expected_expenses
                FROM ins_projected_cashflows
                WHERE cohort_id = p_cohort_id ORDER BY period_year;
            v_pv_total NUMBER(18, 4) := 0;
            v_pv_step NUMBER(18, 4);
        BEGIN
            FOR rec IN cur_cashflows LOOP
                v_pv_step := (rec.expected_claims + rec.expected_expenses) / ((1.0 + p_discount_rate) ** rec.period_year);
                v_pv_total := v_pv_total + v_pv_step;
            END LOOP;
            p_out_fulfilment_cf := v_pv_total;
            UPDATE ins_cohort_valuation
            SET fulfilment_cashflow = v_pv_total, valuation_date = CURRENT_TIMESTAMP
            WHERE cohort_id = p_cohort_id;
            COMMIT;
        END sp_ins_ifrs17_dcf_valuation;
        """,
    ),
    IndustrialBenchmarkCase(
        id="INS-02-CSM-AMORTIZATION",
        domain="Insurance IFRS 17",
        name="Contractual Service Margin (CSM) coverage units amortization",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="CRITICAL",
        features=["COVERAGE_UNITS", "CSM_RELEASE", "LOSS_COMPONENT"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_ins_amortize_csm (
            p_group_id IN VARCHAR2,
            p_current_period_units IN NUMBER,
            p_future_units IN NUMBER,
            p_out_csm_release OUT NUMBER
        ) IS
            v_beg_csm NUMBER(18, 4);
            v_ratio NUMBER(12, 8);
        BEGIN
            SELECT csm_balance INTO v_beg_csm
            FROM ins_csm_ledger WHERE group_id = p_group_id FOR UPDATE;

            IF (p_current_period_units + p_future_units) > 0 THEN
                v_ratio := p_current_period_units / (p_current_period_units + p_future_units);
                p_out_csm_release := v_beg_csm * v_ratio;
            ELSE
                p_out_csm_release := v_beg_csm;
            END IF;

            UPDATE ins_csm_ledger
            SET csm_balance = csm_balance - p_out_csm_release,
                cumulative_released = cumulative_released + p_out_csm_release
            WHERE group_id = p_group_id;
            COMMIT;
        END sp_ins_amortize_csm;
        """,
    ),
    IndustrialBenchmarkCase(
        id="INS-03-CHAIN-LADDER-IBNR",
        domain="Insurance IFRS 17",
        name="Actuarial Chain Ladder Incurred But Not Reported (IBNR) reserve",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="CRITICAL",
        features=["TRIANGLE_DEVELOPMENT", "FACTOR_LINK", "RESERVE_ALLOC"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_ins_calculate_ibnr_chain_ladder (
            p_lob_code IN VARCHAR2,
            p_dev_factor IN NUMBER,
            p_out_ibnr_reserve OUT NUMBER
        ) IS
            v_cum_paid NUMBER(18, 4);
            v_ult_loss NUMBER(18, 4);
        BEGIN
            SELECT COALESCE(SUM(paid_loss_amount), 0) INTO v_cum_paid
            FROM ins_claims_triangle WHERE lob_code = p_lob_code;

            v_ult_loss := v_cum_paid * p_dev_factor;
            p_out_ibnr_reserve := v_ult_loss - v_cum_paid;

            UPDATE ins_actuarial_reserves
            SET ibnr_amount = p_out_ibnr_reserve, updated_at = CURRENT_TIMESTAMP
            WHERE lob_code = p_lob_code;
            COMMIT;
        END sp_ins_calculate_ibnr_chain_ladder;
        """,
    ),
    IndustrialBenchmarkCase(
        id="INS-04-CLAIM-ADJUDICATION",
        domain="Insurance IFRS 17",
        name="Automated health/auto claim deductible and copay adjudication",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["DEDUCTIBLE_MATH", "LIMIT_CHECK", "POLICY_STATUS"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_ins_adjudicate_claim (
            p_claim_id IN VARCHAR2,
            p_policy_id IN VARCHAR2,
            p_billed_amount IN NUMBER,
            p_out_payable OUT NUMBER,
            p_out_status OUT VARCHAR2
        ) IS
            v_deductible NUMBER(10, 2);
            v_copay_rate NUMBER(4, 2);
            v_max_limit NUMBER(14, 2);
            v_policy_stat VARCHAR2(16);
            v_net NUMBER(14, 2);
        BEGIN
            SELECT status, deductible, copay_ratio, coverage_limit
            INTO v_policy_stat, v_deductible, v_copay_rate, v_max_limit
            FROM ins_policies WHERE policy_id = p_policy_id;

            IF v_policy_stat <> 'ACTIVE' THEN
                p_out_payable := 0;
                p_out_status := 'REJECTED_POLICY_INACTIVE';
                RETURN;
            END IF;

            IF p_billed_amount <= v_deductible THEN
                p_out_payable := 0;
                p_out_status := 'WITHIN_DEDUCTIBLE';
                RETURN;
            END IF;

            v_net := (p_billed_amount - v_deductible) * (1.0 - v_copay_rate);
            IF v_net > v_max_limit THEN
                v_net := v_max_limit;
            END IF;

            p_out_payable := v_net;
            p_out_status := 'APPROVED';
            UPDATE ins_claims SET approved_amount = v_net, claim_status = 'APPROVED' WHERE claim_id = p_claim_id;
            COMMIT;
        END sp_ins_adjudicate_claim;
        """,
    ),
    IndustrialBenchmarkCase(
        id="INS-05-REINSURANCE-CESSION",
        domain="Insurance IFRS 17",
        name="Quota share & excess of loss reinsurance cession allocation",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["QUOTA_SHARE", "XOL_LIMIT", "CESSION_CALC"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_ins_process_reinsurance_cession (
            p_treaty_id IN VARCHAR2,
            p_gross_premium IN NUMBER,
            p_cession_pct IN NUMBER,
            p_out_ceded_premium OUT NUMBER,
            p_out_retained_premium OUT NUMBER
        ) IS
        BEGIN
            p_out_ceded_premium := p_gross_premium * (p_cession_pct / 100.0);
            p_out_retained_premium := p_gross_premium - p_out_ceded_premium;

            INSERT INTO ins_reinsurance_ledger(treaty_id, gross_prem, ceded_prem, retained_prem, processed_at)
            VALUES (p_treaty_id, p_gross_premium, p_out_ceded_premium, p_out_retained_premium, CURRENT_TIMESTAMP);
            COMMIT;
        END sp_ins_process_reinsurance_cession;
        """,
    ),
    IndustrialBenchmarkCase(
        id="INS-06-SURRENDER-VALUE-CALC",
        domain="Insurance IFRS 17",
        name="Life policy cash surrender value with mortality penalty table",
        source_dialect=Dialect.ORACLE,
        kind="FUNCTION",
        complexity="HIGH",
        features=["ACTUARIAL_FUNCTION", "CASH_VALUE", "PENALTY_CURVE"],
        source_sql="""
        CREATE OR REPLACE FUNCTION fn_ins_calc_surrender_value (
            p_policy_id IN VARCHAR2,
            p_elapsed_years IN INTEGER
        ) RETURN NUMBER IS
            v_reserve NUMBER(14, 2);
            v_penalty_pct NUMBER(4, 2);
            v_surrender NUMBER(14, 2);
        BEGIN
            SELECT actuarial_reserve INTO v_reserve
            FROM ins_policies WHERE policy_id = p_policy_id;

            IF p_elapsed_years < 1 THEN
                v_penalty_pct := 0.50;
            ELSIF p_elapsed_years < 3 THEN
                v_penalty_pct := 0.20;
            ELSIF p_elapsed_years < 5 THEN
                v_penalty_pct := 0.05;
            ELSE
                v_penalty_pct := 0.00;
            END IF;

            v_surrender := v_reserve * (1.0 - v_penalty_pct);
            RETURN v_surrender;
        END fn_ins_calc_surrender_value;
        """,
    ),
    IndustrialBenchmarkCase(
        id="INS-07-UNDERWRITING-SCORECARD",
        domain="Insurance IFRS 17",
        name="Underwriting multi-factor risk scorecard matrix",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["SCORECARD_MATRIX", "BMI_EVAL", "RISK_LOAD"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_ins_score_underwriting (
            p_applicant_id IN VARCHAR2,
            p_age IN NUMBER,
            p_bmi IN NUMBER,
            p_smoker IN NUMBER,
            p_out_decision OUT VARCHAR2
        ) IS
            v_score NUMBER := 100;
        BEGIN
            IF p_age > 50 THEN
                v_score := v_score + 25;
            END IF;
            IF p_bmi > 30 THEN
                v_score := v_score + 30;
            END IF;
            IF p_smoker = 1 THEN
                v_score := v_score + 50;
            END IF;

            IF v_score > 160 THEN
                p_out_decision := 'DECLINED_HIGH_RISK';
            ELSIF v_score > 120 THEN
                p_out_decision := 'APPROVED_WITH_RATING';
            ELSE
                p_out_decision := 'STANDARD_ACCEPTANCE';
            END IF;
        END sp_ins_score_underwriting;
        """,
    ),
    IndustrialBenchmarkCase(
        id="INS-08-POLICY-LAPSE-TRIGGER",
        domain="Insurance IFRS 17",
        name="Unpaid premium grace period expiration auto-lapse trigger",
        source_dialect=Dialect.ORACLE,
        kind="TRIGGER",
        complexity="HIGH",
        features=["AUTO_LAPSE", "GRACE_PERIOD", "BEFORE_UPDATE"],
        source_sql="""
        CREATE OR REPLACE TRIGGER trg_ins_policy_lapse_check
        BEFORE UPDATE OF overdue_days ON ins_policies
        FOR EACH ROW
        BEGIN
            IF :NEW.overdue_days > 60 AND :OLD.status = 'ACTIVE' THEN
                :NEW.status := 'LAPSED';
                :NEW.lapsed_at := CURRENT_TIMESTAMP;
            END IF;
        END;
        """,
    ),
    IndustrialBenchmarkCase(
        id="INS-09-ANNUITY-DISBURSEMENT",
        domain="Insurance IFRS 17",
        name="Pension retirement annuity payment batch distribution",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["BATCH_PAYOUT", "LIFETIME_ANNUITY", "ESCROW_LEDGER"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_ins_disburse_annuity_batch (
            p_disburse_date IN DATE,
            p_out_total_paid OUT NUMBER
        ) IS
            CURSOR cur_annuitants IS
                SELECT policy_id, monthly_annuity_amount, beneficiary_acc
                FROM ins_annuity_contracts
                WHERE status = 'PAYING' AND next_due_date <= p_disburse_date;
            v_total NUMBER(18, 4) := 0;
        BEGIN
            FOR rec IN cur_annuitants LOOP
                v_total := v_total + rec.monthly_annuity_amount;
                UPDATE ins_annuity_contracts
                SET last_paid_date = p_disburse_date,
                    next_due_date = ADD_MONTHS(next_due_date, 1)
                WHERE policy_id = rec.policy_id;
            END LOOP;
            COMMIT;
            p_out_total_paid := v_total;
        END sp_ins_disburse_annuity_batch;
        """,
    ),
    IndustrialBenchmarkCase(
        id="INS-10-PACKAGE-ACTUARIAL-ENGINE",
        domain="Insurance IFRS 17",
        name="IFRS 17 Actuarial Valuation and Reserve Package",
        source_dialect=Dialect.ORACLE,
        kind="PACKAGE",
        complexity="CRITICAL",
        features=["PACKAGE_SPEC_BODY", "YIELD_CURVE", "MORTALITY_TABLE"],
        source_sql="",
        spec_sql="""
        CREATE OR REPLACE PACKAGE ins_actuarial_pkg IS
            g_risk_free_rate NUMBER := 0.0250;
            g_illiquidity_premium NUMBER := 0.0050;

            FUNCTION get_effective_discount_rate RETURN NUMBER;
            PROCEDURE evaluate_risk_adjustment(p_cohort IN VARCHAR2, p_confidence_level IN NUMBER, p_out_ra OUT NUMBER);
        END ins_actuarial_pkg;
        """,
        body_sql="""
        CREATE OR REPLACE PACKAGE BODY ins_actuarial_pkg IS
            v_last_curve_date DATE;

            FUNCTION get_effective_discount_rate RETURN NUMBER IS
            BEGIN
                RETURN g_risk_free_rate + g_illiquidity_premium;
            END get_effective_discount_rate;

            PROCEDURE evaluate_risk_adjustment(p_cohort IN VARCHAR2, p_confidence_level IN NUMBER, p_out_ra OUT NUMBER) IS
                v_std_dev NUMBER(14, 2);
            BEGIN
                SELECT std_dev_claims INTO v_std_dev
                FROM ins_cohort_statistics WHERE cohort_id = p_cohort;
                IF p_confidence_level >= 0.90 THEN
                    p_out_ra := v_std_dev * 1.645;
                ELSE
                    p_out_ra := v_std_dev * 1.282;
                END IF;
            END evaluate_risk_adjustment;

        BEGIN
            v_last_curve_date := CURRENT_TIMESTAMP;
        END ins_actuarial_pkg;
        """,
    ),

    # =========================================================================
    # 4. LOGISTICS, SUPPLY CHAIN & WMS (10 CASES)
    # =========================================================================
    IndustrialBenchmarkCase(
        id="SCM-01-FIFO-BIN-ALLOCATION",
        domain="Supply Chain & WMS",
        name="Warehouse FIFO / FEFO inventory allocation cursor algorithm",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="CRITICAL",
        features=["FIFO_CURSOR", "BATCH_EXPIRY", "MULTI_BIN_DEDUCT"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_scm_allocate_order_inventory (
            p_order_id IN VARCHAR2,
            p_sku IN VARCHAR2,
            p_qty_required IN NUMBER,
            p_out_allocated OUT NUMBER
        ) IS
            CURSOR cur_bins IS
                SELECT bin_id, lot_number, available_qty
                FROM wms_inventory
                WHERE sku = p_sku AND available_qty > 0
                ORDER BY expiry_date ASC, created_at ASC;
            v_rem_qty NUMBER := p_qty_required;
            v_take NUMBER;
        BEGIN
            p_out_allocated := 0;
            FOR rec IN cur_bins LOOP
                EXIT WHEN v_rem_qty <= 0;
                IF rec.available_qty >= v_rem_qty THEN
                    v_take := v_rem_qty;
                ELSE
                    v_take := rec.available_qty;
                END IF;

                UPDATE wms_inventory
                SET available_qty = available_qty - v_take,
                    allocated_qty = allocated_qty + v_take
                WHERE bin_id = rec.bin_id AND lot_number = rec.lot_number;

                v_rem_qty := v_rem_qty - v_take;
                p_out_allocated := p_out_allocated + v_take;
            END LOOP;
            COMMIT;
        END sp_scm_allocate_order_inventory;
        """,
    ),
    IndustrialBenchmarkCase(
        id="SCM-02-AUTO-REORDER-TRIGGER",
        domain="Supply Chain & WMS",
        name="Automated Purchase Requisition trigger on safety stock breach",
        source_dialect=Dialect.ORACLE,
        kind="TRIGGER",
        complexity="HIGH",
        features=["SAFETY_STOCK", "REORDER_POINT", "PO_GENERATION"],
        source_sql="""
        CREATE OR REPLACE TRIGGER trg_scm_safety_stock_reorder
        AFTER UPDATE OF available_qty ON wms_inventory
        FOR EACH ROW
        DECLARE
            v_safety_stock NUMBER := 50;
            v_eoq NUMBER := 200;
        BEGIN
            IF :OLD.available_qty >= v_safety_stock AND :NEW.available_qty < v_safety_stock THEN
                INSERT INTO wms_purchase_requisitions (sku, req_qty, status, created_at)
                VALUES (:NEW.sku, v_eoq, 'PENDING_APPROVAL', CURRENT_TIMESTAMP);
            END IF;
        END;
        """,
    ),
    IndustrialBenchmarkCase(
        id="SCM-03-CROSS-DOCKING-ROUTE",
        domain="Supply Chain & WMS",
        name="Inbound ASN cross-docking direct route dispatch",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["CROSS_DOCKING", "ASN_MATCHING", "BAY_ASSIGNMENT"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_scm_receive_asn (
            p_asn_no IN VARCHAR2,
            p_dock_bay IN VARCHAR2,
            p_out_cross_docked_count OUT NUMBER
        ) IS
            CURSOR cur_items IS
                SELECT sku, arrived_qty FROM wms_asn_items WHERE asn_no = p_asn_no;
            v_count NUMBER := 0;
            v_demand NUMBER;
        BEGIN
            FOR rec IN cur_items LOOP
                SELECT COALESCE(SUM(backlog_qty), 0) INTO v_demand
                FROM wms_order_backlogs WHERE sku = rec.sku;

                IF v_demand > 0 THEN
                    UPDATE wms_asn_items SET cross_dock_flag = 1 WHERE asn_no = p_asn_no AND sku = rec.sku;
                    v_count := v_count + 1;
                END IF;
            END LOOP;
            COMMIT;
            p_out_cross_docked_count := v_count;
        END sp_scm_receive_asn;
        """,
    ),
    IndustrialBenchmarkCase(
        id="SCM-04-FREIGHT-RATE-CALC",
        domain="Supply Chain & WMS",
        name="Carrier freight cost calculation by cubic volume and dimensional weight",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["DIMENSIONAL_WEIGHT", "DISTANCE_RATE", "FUEL_SURCHARGE"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_scm_calculate_freight_charge (
            p_weight_kg IN NUMBER,
            p_volume_cbm IN NUMBER,
            p_distance_km IN NUMBER,
            p_out_freight OUT NUMBER
        ) IS
            v_dim_weight NUMBER;
            v_billable_wt NUMBER;
            v_base_rate NUMBER := 0.85;
            v_fuel_surcharge NUMBER := 1.15;
        BEGIN
            v_dim_weight := p_volume_cbm * 167.0;
            IF p_weight_kg > v_dim_weight THEN
                v_billable_wt := p_weight_kg;
            ELSE
                v_billable_wt := v_dim_weight;
            END IF;

            p_out_freight := v_billable_wt * (p_distance_km / 100.0) * v_base_rate * v_fuel_surcharge;
        END sp_scm_calculate_freight_charge;
        """,
    ),
    IndustrialBenchmarkCase(
        id="SCM-05-COLD-CHAIN-TRIGGER",
        domain="Supply Chain & WMS",
        name="Cold chain sensor temperature excursion quarantine trigger",
        source_dialect=Dialect.ORACLE,
        kind="TRIGGER",
        complexity="HIGH",
        features=["IOT_TELEMETRY", "BATCH_QUARANTINE", "CRITICAL_ALERT"],
        source_sql="""
        CREATE OR REPLACE TRIGGER trg_scm_cold_chain_alarm
        AFTER INSERT ON wms_pallet_telemetry
        FOR EACH ROW
        BEGIN
            IF :NEW.temperature_celsius > 8.0 OR :NEW.temperature_celsius < 2.0 THEN
                INSERT INTO wms_quarantine_lots(pallet_id, sensor_id, temp_recorded, incident_time, status)
                VALUES (:NEW.pallet_id, :NEW.sensor_id, :NEW.temperature_celsius, CURRENT_TIMESTAMP, 'QUARANTINED');
            END IF;
        END;
        """,
    ),
    IndustrialBenchmarkCase(
        id="SCM-06-RMA-RESTOCK-PROC",
        domain="Supply Chain & WMS",
        name="Return Merchandise Authorization (RMA) inspection and restock",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["RESTOCK_INVENTORY", "REFUND_TRIGGER", "CONDITION_EVAL"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_scm_process_rma (
            p_rma_id IN VARCHAR2,
            p_inspect_result IN VARCHAR2,
            p_out_refund_status OUT VARCHAR2
        ) IS
            v_sku VARCHAR2(32);
            v_qty NUMBER;
        BEGIN
            SELECT sku, return_qty INTO v_sku, v_qty
            FROM wms_rma_records WHERE rma_id = p_rma_id FOR UPDATE;

            IF p_inspect_result = 'RESTOCKABLE' THEN
                UPDATE wms_inventory SET available_qty = available_qty + v_qty WHERE sku = v_sku AND bin_id = 'RETURNS_BIN';
                p_out_refund_status := 'FULL_REFUND_APPROVED';
            ELSE
                p_out_refund_status := 'SCRAP_NO_REFUND';
            END IF;
            COMMIT;
        END sp_scm_process_rma;
        """,
    ),
    IndustrialBenchmarkCase(
        id="SCM-07-PALLET-PACKING-SOLVER",
        domain="Supply Chain & WMS",
        name="Outbound carton pallet packing weight and volume constraint solver",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["KNAPSACK_GREEDY", "PALLET_LIMITS", "VOLUME_CALC"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_scm_pack_pallet (
            p_shipment_id IN VARCHAR2,
            p_max_wt_kg IN NUMBER,
            p_max_vol_cbm IN NUMBER,
            p_out_pallet_count OUT NUMBER
        ) IS
            CURSOR cur_cartons IS
                SELECT carton_id, weight_kg, volume_cbm
                FROM wms_shipment_cartons
                WHERE shipment_id = p_shipment_id AND pallet_id IS NULL;
            v_curr_wt NUMBER := 0;
            v_curr_vol NUMBER := 0;
            v_pallet_no NUMBER := 1;
        BEGIN
            FOR rec IN cur_cartons LOOP
                IF (v_curr_wt + rec.weight_kg > p_max_wt_kg) OR (v_curr_vol + rec.volume_cbm > p_max_vol_cbm) THEN
                    v_pallet_no := v_pallet_no + 1;
                    v_curr_wt := 0;
                    v_curr_vol := 0;
                END IF;
                v_curr_wt := v_curr_wt + rec.weight_kg;
                v_curr_vol := v_curr_vol + rec.volume_cbm;
                UPDATE wms_shipment_cartons SET pallet_id = 'PLT_' || TO_CHAR(v_pallet_no) WHERE carton_id = rec.carton_id;
            END LOOP;
            COMMIT;
            p_out_pallet_count := v_pallet_no;
        END sp_scm_pack_pallet;
        """,
    ),
    IndustrialBenchmarkCase(
        id="SCM-08-SUPPLIER-SCORECARD",
        domain="Supply Chain & WMS",
        name="Vendor On-Time In-Full (OTIF) monthly performance rating",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["OTIF_PERCENTAGE", "KPI_AGGREGATION", "GRADE_CLASSIFY"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_scm_eval_vendor_otif (
            p_vendor_id IN VARCHAR2,
            p_month IN VARCHAR2,
            p_out_otif_pct OUT NUMBER,
            p_out_grade OUT VARCHAR2
        ) IS
            v_total_po NUMBER := 0;
            v_on_time_po NUMBER := 0;
        BEGIN
            SELECT COUNT(*), COALESCE(SUM(CASE WHEN actual_deliver_date <= promised_date AND defect_qty = 0 THEN 1 ELSE 0 END), 0)
            INTO v_total_po, v_on_time_po
            FROM wms_po_deliveries
            WHERE vendor_id = p_vendor_id AND delivery_month = p_month;

            IF v_total_po > 0 THEN
                p_out_otif_pct := (v_on_time_po / v_total_po) * 100.0;
            ELSE
                p_out_otif_pct := 100.0;
            END IF;

            IF p_out_otif_pct >= 98.0 THEN
                p_out_grade := 'CLASS_A_PREFERRED';
            ELSIF p_out_otif_pct >= 90.0 THEN
                p_out_grade := 'CLASS_B_STANDARD';
            ELSE
                p_out_grade := 'CLASS_C_PROBATION';
            END IF;
        END sp_scm_eval_vendor_otif;
        """,
    ),
    IndustrialBenchmarkCase(
        id="SCM-09-CYCLE-COUNT-VARIANCE",
        domain="Supply Chain & WMS",
        name="Physical inventory cycle count discrepancy reconciliation",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["CYCLE_COUNT", "VARIANCE_THRESHOLD", "GL_ADJUSTMENT"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_scm_reconcile_cycle_count (
            p_bin_id IN VARCHAR2,
            p_sku IN VARCHAR2,
            p_counted_qty IN NUMBER,
            p_out_diff OUT NUMBER
        ) IS
            v_system_qty NUMBER;
        BEGIN
            SELECT available_qty INTO v_system_qty
            FROM wms_inventory WHERE bin_id = p_bin_id AND sku = p_sku FOR UPDATE;

            p_out_diff := p_counted_qty - v_system_qty;
            IF p_out_diff <> 0 THEN
                UPDATE wms_inventory SET available_qty = p_counted_qty WHERE bin_id = p_bin_id AND sku = p_sku;
                INSERT INTO wms_inventory_adjustments (bin_id, sku, system_qty, counted_qty, diff_qty, adjusted_at)
                VALUES (p_bin_id, p_sku, v_system_qty, p_counted_qty, p_out_diff, CURRENT_TIMESTAMP);
            END IF;
            COMMIT;
        END sp_scm_reconcile_cycle_count;
        """,
    ),
    IndustrialBenchmarkCase(
        id="SCM-10-PACKAGE-WMS-ROUTING",
        domain="Supply Chain & WMS",
        name="Warehouse Logistics & Wave Dispatch Package",
        source_dialect=Dialect.ORACLE,
        kind="PACKAGE",
        complexity="CRITICAL",
        features=["PACKAGE_SPEC_BODY", "WAREHOUSE_ZONES", "BATCH_DISPATCH"],
        source_sql="",
        spec_sql="""
        CREATE OR REPLACE PACKAGE wms_dispatch_pkg IS
            g_default_zone CONSTANT VARCHAR2(8) := 'ZONE_A';
            g_active_waves NUMBER := 0;

            PROCEDURE start_wave(p_wave_id IN VARCHAR2);
            FUNCTION get_zone_capacity(p_zone IN VARCHAR2) RETURN NUMBER;
        END wms_dispatch_pkg;
        """,
        body_sql="""
        CREATE OR REPLACE PACKAGE BODY wms_dispatch_pkg IS
            v_last_wave_time TIMESTAMP;

            PROCEDURE start_wave(p_wave_id IN VARCHAR2) IS
            BEGIN
                g_active_waves := g_active_waves + 1;
                UPDATE wms_waves SET status = 'IN_PROGRESS', started_at = CURRENT_TIMESTAMP WHERE wave_id = p_wave_id;
            END start_wave;

            FUNCTION get_zone_capacity(p_zone IN VARCHAR2) RETURN NUMBER IS
                v_cap NUMBER;
            BEGIN
                SELECT max_pallet_capacity INTO v_cap FROM wms_zone_specs WHERE zone_id = p_zone;
                RETURN v_cap;
            EXCEPTION
                WHEN NO_DATA_FOUND THEN
                    RETURN 100;
            END get_zone_capacity;

        BEGIN
            v_last_wave_time := CURRENT_TIMESTAMP;
        END wms_dispatch_pkg;
        """,
    ),

    # =========================================================================
    # 5. GOVERNMENT, TAX & ENTERPRISE ERP (10 CASES)
    # =========================================================================
    IndustrialBenchmarkCase(
        id="ERP-01-PROGRESSIVE-IIT",
        domain="Government & ERP",
        name="Progressive Individual Income Tax (IIT) with 7-bracket deduction",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="CRITICAL",
        features=["7_BRACKET_TAX", "QUICK_DEDUCTION", "CUMULATIVE_WITHHOLD"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_erp_calculate_employee_payroll (
            p_emp_id IN VARCHAR2,
            p_base_salary IN NUMBER,
            p_allowance IN NUMBER,
            p_out_net_salary OUT NUMBER,
            p_out_iit OUT NUMBER
        ) IS
            v_social_sec NUMBER(10, 2);
            v_taxable NUMBER(10, 2);
            v_tax_rate NUMBER(4, 2);
            v_quick_deduct NUMBER(10, 2);
        BEGIN
            v_social_sec := p_base_salary * 0.105;
            v_taxable := (p_base_salary + p_allowance) - v_social_sec - 5000.00;

            IF v_taxable <= 0 THEN
                p_out_iit := 0;
            ELSIF v_taxable <= 3000 THEN
                p_out_iit := v_taxable * 0.03;
            ELSIF v_taxable <= 12000 THEN
                p_out_iit := v_taxable * 0.10 - 210.00;
            ELSIF v_taxable <= 25000 THEN
                p_out_iit := v_taxable * 0.20 - 1410.00;
            ELSIF v_taxable <= 35000 THEN
                p_out_iit := v_taxable * 0.25 - 2660.00;
            ELSIF v_taxable <= 55000 THEN
                p_out_iit := v_taxable * 0.30 - 4410.00;
            ELSIF v_taxable <= 80000 THEN
                p_out_iit := v_taxable * 0.35 - 7160.00;
            ELSE
                p_out_iit := v_taxable * 0.45 - 15160.00;
            END IF;

            p_out_net_salary := (p_base_salary + p_allowance) - v_social_sec - p_out_iit;
        END sp_erp_calculate_employee_payroll;
        """,
    ),
    IndustrialBenchmarkCase(
        id="ERP-02-VAT-OFFSET-RECON",
        domain="Government & ERP",
        name="Corporate Value Added Tax (VAT) Input/Output credit offset",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["INPUT_OUTPUT_VAT", "TAX_CREDIT", "RECONCILIATION"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_erp_reconcile_vat (
            p_tax_period IN VARCHAR2,
            p_out_vat_payable OUT NUMBER,
            p_out_retained_credit OUT NUMBER
        ) IS
            v_output_vat NUMBER(18, 4) := 0;
            v_input_vat NUMBER(18, 4) := 0;
            v_diff NUMBER(18, 4);
        BEGIN
            SELECT COALESCE(SUM(vat_amount), 0) INTO v_output_vat
            FROM erp_sales_invoices WHERE tax_period = p_tax_period AND status = 'CERTIFIED';

            SELECT COALESCE(SUM(vat_amount), 0) INTO v_input_vat
            FROM erp_purchase_invoices WHERE tax_period = p_tax_period AND status = 'VERIFIED';

            v_diff := v_output_vat - v_input_vat;
            IF v_diff >= 0 THEN
                p_out_vat_payable := v_diff;
                p_out_retained_credit := 0;
            ELSE
                p_out_vat_payable := 0;
                p_out_retained_credit := ABS(v_diff);
            END IF;
            COMMIT;
        END sp_erp_reconcile_vat;
        """,
    ),
    IndustrialBenchmarkCase(
        id="ERP-03-FIXED-ASSET-DEPRECIATION",
        domain="Government & ERP",
        name="Fixed asset double declining balance depreciation monthly batch",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["DEPRECIATION_MATH", "SALVAGE_VALUE", "ASSET_BOOK"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_erp_depreciate_assets_batch (
            p_period IN VARCHAR2,
            p_out_total_depr OUT NUMBER
        ) IS
            CURSOR cur_assets IS
                SELECT asset_id, original_cost, salvage_value, useful_life_months, accumulated_depr
                FROM erp_fixed_assets
                WHERE status = 'IN_SERVICE' AND accumulated_depr < (original_cost - salvage_value);
            v_monthly_depr NUMBER(14, 2);
            v_total NUMBER(18, 2) := 0;
        BEGIN
            FOR rec IN cur_assets LOOP
                v_monthly_depr := (rec.original_cost - rec.salvage_value) / rec.useful_life_months;
                UPDATE erp_fixed_assets
                SET accumulated_depr = accumulated_depr + v_monthly_depr,
                    last_depr_period = p_period
                WHERE asset_id = rec.asset_id;
                v_total := v_total + v_monthly_depr;
            END LOOP;
            COMMIT;
            p_out_total_depr := v_total;
        END sp_erp_depreciate_assets_batch;
        """,
    ),
    IndustrialBenchmarkCase(
        id="ERP-04-LEAVE-ACCRUAL-CALC",
        domain="Government & ERP",
        name="Employee tenure statutory annual leave accrual calculator",
        source_dialect=Dialect.ORACLE,
        kind="FUNCTION",
        complexity="HIGH",
        features=["TENURE_TIER", "CARRY_FORWARD", "STATUTORY_RULES"],
        source_sql="""
        CREATE OR REPLACE FUNCTION fn_erp_calc_leave_days (
            p_tenure_years IN NUMBER
        ) RETURN NUMBER IS
        BEGIN
            IF p_tenure_years < 1 THEN
                RETURN 0;
            ELSIF p_tenure_years < 10 THEN
                RETURN 5;
            ELSIF p_tenure_years < 20 THEN
                RETURN 10;
            ELSE
                RETURN 15;
            END IF;
        END fn_erp_calc_leave_days;
        """,
    ),
    IndustrialBenchmarkCase(
        id="ERP-05-INTERCOMPANY-COST-ALLOCATION",
        domain="Government & ERP",
        name="Multi-entity corporate shared service cost allocation",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["MULTI_ENTITY", "HEADCOUNT_RATIO", "INTERCOMPANY_GL"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_erp_allocate_shared_cost (
            p_shared_cost_amount IN NUMBER,
            p_period IN VARCHAR2
        ) IS
            v_total_hc NUMBER;
            CURSOR cur_subs IS
                SELECT entity_id, headcount FROM erp_legal_entities WHERE is_active = 1;
            v_allocated NUMBER(18, 4);
        BEGIN
            SELECT COALESCE(SUM(headcount), 1) INTO v_total_hc FROM erp_legal_entities WHERE is_active = 1;
            FOR rec IN cur_subs LOOP
                v_allocated := p_shared_cost_amount * (rec.headcount / v_total_hc);
                INSERT INTO erp_intercompany_ledger(entity_id, period, allocated_amount, created_at)
                VALUES (rec.entity_id, p_period, v_allocated, CURRENT_TIMESTAMP);
            END LOOP;
            COMMIT;
        END sp_erp_allocate_shared_cost;
        """,
    ),
    IndustrialBenchmarkCase(
        id="ERP-06-PURCHASE-APPROVAL-HIERARCHY",
        domain="Government & ERP",
        name="Purchase requisition financial delegation limit approval routing",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["DELEGATION_OF_AUTHORITY", "MULTI_TIER_SIGN", "STATUS_FLOW"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_erp_route_po_approval (
            p_req_id IN VARCHAR2,
            p_total_amount IN NUMBER,
            p_out_required_level OUT VARCHAR2
        ) IS
        BEGIN
            IF p_total_amount <= 5000 THEN
                p_out_required_level := 'LINE_MANAGER';
            ELSIF p_total_amount <= 50000 THEN
                p_out_required_level := 'DEPARTMENT_DIRECTOR';
            ELSIF p_total_amount <= 200000 THEN
                p_out_required_level := 'VP_OPERATIONS';
            ELSE
                p_out_required_level := 'CFO_BOARD';
            END IF;

            UPDATE erp_purchase_requisitions
            SET pending_level = p_out_required_level, status = 'UNDER_APPROVAL'
            WHERE req_id = p_req_id;
            COMMIT;
        END sp_erp_route_po_approval;
        """,
    ),
    IndustrialBenchmarkCase(
        id="ERP-07-BUDGET-OVERRUN-TRIGGER",
        domain="Government & ERP",
        name="Department GL expense budget overrun blocker trigger",
        source_dialect=Dialect.ORACLE,
        kind="TRIGGER",
        complexity="HIGH",
        features=["BUDGET_GUARD", "BEFORE_INSERT", "ERROR_APPLICATION"],
        source_sql="""
        CREATE OR REPLACE TRIGGER trg_erp_budget_check
        BEFORE INSERT ON erp_expense_claims
        FOR EACH ROW
        DECLARE
            v_rem_budget NUMBER(14, 2);
        BEGIN
            SELECT (budget_allocated - budget_spent) INTO v_rem_budget
            FROM erp_dept_budgets
            WHERE dept_id = :NEW.dept_id AND fiscal_year = :NEW.fiscal_year;

            IF :NEW.claim_amount > v_rem_budget THEN
                RAISE_APPLICATION_ERROR(-20005, 'Department budget exceeded');
            END IF;
        END;
        """,
    ),
    IndustrialBenchmarkCase(
        id="ERP-08-DISBURSE-PAYROLL-BATCH",
        domain="Government & ERP",
        name="Company-wide payroll direct deposit settlement batch",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["BULK_DISBURSEMENT", "BANK_FILE_GEN", "IDEMPOTENT_RUN"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_erp_disburse_company_payroll (
            p_pay_month IN VARCHAR2,
            p_out_disbursed_count OUT NUMBER,
            p_out_total_net OUT NUMBER
        ) IS
            CURSOR cur_payroll IS
                SELECT employee_id, net_salary, bank_account_no
                FROM erp_payroll_records
                WHERE pay_month = p_pay_month AND payment_status = 'PENDING';
            v_count NUMBER := 0;
            v_total NUMBER(18, 2) := 0;
        BEGIN
            FOR rec IN cur_payroll LOOP
                v_count := v_count + 1;
                v_total := v_total + rec.net_salary;
                UPDATE erp_payroll_records SET payment_status = 'PAID', paid_at = CURRENT_TIMESTAMP WHERE employee_id = rec.employee_id AND pay_month = p_pay_month;
            END LOOP;
            COMMIT;
            p_out_disbursed_count := v_count;
            p_out_total_net := v_total;
        END sp_erp_disburse_company_payroll;
        """,
    ),
    IndustrialBenchmarkCase(
        id="ERP-09-CUSTOMS-DUTY-CALC",
        domain="Government & ERP",
        name="Cross-border import customs duty and consumption tax calculator",
        source_dialect=Dialect.ORACLE,
        kind="PROCEDURE",
        complexity="HIGH",
        features=["TARIFF_LOOKUP", "DUTY_COMPOUND", "CUSTOMS_CIF"],
        source_sql="""
        CREATE OR REPLACE PROCEDURE sp_erp_calc_customs_duty (
            p_hs_code IN VARCHAR2,
            p_cif_value IN NUMBER,
            p_out_duty OUT NUMBER,
            p_out_consumption_tax OUT NUMBER
        ) IS
            v_duty_rate NUMBER(6, 4);
            v_ct_rate NUMBER(6, 4);
        BEGIN
            SELECT duty_rate, consumption_tax_rate INTO v_duty_rate, v_ct_rate
            FROM erp_customs_tariff WHERE hs_code = p_hs_code;

            p_out_duty := p_cif_value * v_duty_rate;
            p_out_consumption_tax := (p_cif_value + p_out_duty) / (1.0 - v_ct_rate) * v_ct_rate;
        END sp_erp_calc_customs_duty;
        """,
    ),
    IndustrialBenchmarkCase(
        id="ERP-10-PACKAGE-FINANCIAL-CLOSING",
        domain="Government & ERP",
        name="Fiscal Month-End Period Closing and General Ledger Lock Package",
        source_dialect=Dialect.ORACLE,
        kind="PACKAGE",
        complexity="CRITICAL",
        features=["PACKAGE_SPEC_BODY", "PERIOD_LOCK", "CLOSING_ORCHESTRATION"],
        source_sql="",
        spec_sql="""
        CREATE OR REPLACE PACKAGE erp_closing_pkg IS
            g_active_period VARCHAR2(7);
            g_is_period_locked NUMBER := 0;

            PROCEDURE lock_period(p_period IN VARCHAR2);
            PROCEDURE unlock_period(p_period IN VARCHAR2, p_auth_token IN VARCHAR2);
            FUNCTION is_posting_allowed(p_period IN VARCHAR2) RETURN NUMBER;
        END erp_closing_pkg;
        """,
        body_sql="""
        CREATE OR REPLACE PACKAGE BODY erp_closing_pkg IS
            v_last_lock_by VARCHAR2(32);

            PROCEDURE lock_period(p_period IN VARCHAR2) IS
            BEGIN
                g_active_period := p_period;
                g_is_period_locked := 1;
                v_last_lock_by := USER;
                UPDATE erp_fiscal_periods SET is_locked = 1, locked_at = CURRENT_TIMESTAMP WHERE period_id = p_period;
            END lock_period;

            PROCEDURE unlock_period(p_period IN VARCHAR2, p_auth_token IN VARCHAR2) IS
            BEGIN
                IF p_auth_token = 'SUPER_CFO_OVERRIDE' THEN
                    g_is_period_locked := 0;
                    UPDATE erp_fiscal_periods SET is_locked = 0 WHERE period_id = p_period;
                END IF;
            END unlock_period;

            FUNCTION is_posting_allowed(p_period IN VARCHAR2) RETURN NUMBER IS
            BEGIN
                IF g_is_period_locked = 1 AND g_active_period = p_period THEN
                    RETURN 0;
                ELSE
                    RETURN 1;
                END IF;
            END is_posting_allowed;

        BEGIN
            g_is_period_locked := 0;
        END erp_closing_pkg;
        """,
    ),
]


def get_all_industrial_benchmarks() -> list[IndustrialBenchmarkCase]:
    """Return all 52 industrial benchmark cases."""
    return list(BENCHMARKS)


def get_benchmarks_by_domain(domain_prefix: str) -> list[IndustrialBenchmarkCase]:
    """Filter benchmarks by domain name substring."""
    d_lower = domain_prefix.lower()
    return [b for b in BENCHMARKS if d_lower in b.domain.lower()]
