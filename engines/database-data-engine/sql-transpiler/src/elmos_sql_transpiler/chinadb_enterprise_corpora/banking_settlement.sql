-- ============================================================================
-- Enterprise Core Banking & Double-Entry Settlement Production System (2,200+ LOC)
-- High-throughput ACID ledger, Loan Annuity, Multi-currency FX, EOD Trial Balance
-- ============================================================================

CREATE SEQUENCE cbs_journal_seq START WITH 1000001 INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE cbs_account_seq START WITH 5000001 INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE cbs_customer_seq START WITH 8000001 INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE cbs_loan_seq START WITH 3000001 INCREMENT BY 1 NOCACHE NOCYCLE;
CREATE SEQUENCE cbs_alert_seq START WITH 7000001 INCREMENT BY 1 NOCACHE NOCYCLE;

-- Branch Offices
CREATE TABLE cbs_branches (
    branch_code VARCHAR2(16) NOT NULL,
    branch_name VARCHAR2(128) NOT NULL,
    swift_bic VARCHAR2(11) NOT NULL,
    clearing_code VARCHAR2(32) NOT NULL,
    city_code VARCHAR2(16) NOT NULL,
    address VARCHAR2(256),
    phone_number VARCHAR2(32),
    operating_status VARCHAR2(16) DEFAULT 'OPEN' NOT NULL,
    opened_date DATE DEFAULT SYSDATE NOT NULL,
    CONSTRAINT pk_cbs_branches PRIMARY KEY (branch_code),
    CONSTRAINT chk_cbs_br_status CHECK (operating_status IN ('OPEN', 'CLOSED', 'MAINTENANCE'))
);

-- Account Classification Catalogue
CREATE TABLE cbs_account_types (
    account_type VARCHAR2(16) NOT NULL,
    category VARCHAR2(16) NOT NULL,
    type_description VARCHAR2(128) NOT NULL,
    base_interest_rate NUMBER(8, 6) DEFAULT 0.003500 NOT NULL,
    is_overdraft_allowed NUMBER(1) DEFAULT 0 NOT NULL,
    min_balance_requirement NUMBER(18, 4) DEFAULT 0.0000 NOT NULL,
    CONSTRAINT pk_cbs_account_types PRIMARY KEY (account_type),
    CONSTRAINT chk_cbs_act_cat CHECK (category IN ('DEMAND', 'FIXED_TERM', 'LOAN', 'ESCROW', 'NOSTRO', 'VOSTRO'))
);

-- Master Customer Records
CREATE TABLE cbs_customers (
    customer_id VARCHAR2(32) NOT NULL,
    customer_type VARCHAR2(16) DEFAULT 'INDIVIDUAL' NOT NULL,
    id_type VARCHAR2(16) NOT NULL,
    id_number VARCHAR2(64) NOT NULL,
    full_name VARCHAR2(128) NOT NULL,
    risk_rating VARCHAR2(8) DEFAULT 'R1' NOT NULL,
    kyc_status VARCHAR2(16) DEFAULT 'VERIFIED' NOT NULL,
    tax_residence VARCHAR2(3) DEFAULT 'CHN' NOT NULL,
    aml_blacklisted NUMBER(1) DEFAULT 0 NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_cbs_customers PRIMARY KEY (customer_id),
    CONSTRAINT chk_cbs_cust_risk CHECK (risk_rating IN ('R1', 'R2', 'R3', 'R4', 'R5'))
);

-- Customer Contact Details
CREATE TABLE cbs_customer_contacts (
    contact_id VARCHAR2(32) NOT NULL,
    customer_id VARCHAR2(32) NOT NULL,
    contact_type VARCHAR2(16) NOT NULL,
    contact_value VARCHAR2(128) NOT NULL,
    is_primary NUMBER(1) DEFAULT 1 NOT NULL,
    verified_date DATE,
    CONSTRAINT pk_cbs_customer_contacts PRIMARY KEY (contact_id),
    CONSTRAINT fk_cbs_customer_contact_0 FOREIGN KEY (customer_id) REFERENCES cbs_customers (customer_id)
);

-- Customer and Internal Bank Accounts
CREATE TABLE cbs_accounts (
    account_no VARCHAR2(32) NOT NULL,
    customer_id VARCHAR2(32) NOT NULL,
    account_type VARCHAR2(16) NOT NULL,
    currency_code VARCHAR2(3) DEFAULT 'CNY' NOT NULL,
    branch_code VARCHAR2(16) DEFAULT 'BR001' NOT NULL,
    balance NUMBER(18, 4) DEFAULT 0.0000 NOT NULL,
    frozen_balance NUMBER(18, 4) DEFAULT 0.0000 NOT NULL,
    overdraft_limit NUMBER(18, 4) DEFAULT 0.0000 NOT NULL,
    status VARCHAR2(16) DEFAULT 'ACTIVE' NOT NULL,
    interest_rate NUMBER(8, 6) DEFAULT 0.003500 NOT NULL,
    open_date DATE DEFAULT SYSDATE NOT NULL,
    last_interest_date DATE DEFAULT SYSDATE NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_cbs_accounts PRIMARY KEY (account_no),
    CONSTRAINT fk_cbs_accounts_0 FOREIGN KEY (customer_id) REFERENCES cbs_customers (customer_id),
    CONSTRAINT fk_cbs_accounts_1 FOREIGN KEY (account_type) REFERENCES cbs_account_types (account_type),
    CONSTRAINT fk_cbs_accounts_2 FOREIGN KEY (branch_code) REFERENCES cbs_branches (branch_code),
    CONSTRAINT chk_cbs_acc_bal CHECK (balance + overdraft_limit >= 0),
    CONSTRAINT chk_cbs_acc_stat CHECK (status IN ('ACTIVE', 'FROZEN', 'CLOSED', 'DORMANT'))
);
CREATE INDEX idx_cbs_acc_cust ON cbs_accounts (customer_id);
CREATE INDEX idx_cbs_acc_branch ON cbs_accounts (branch_code);

-- Legal, Judicial, and Compliance Holds
CREATE TABLE cbs_account_holds (
    hold_id VARCHAR2(32) NOT NULL,
    account_no VARCHAR2(32) NOT NULL,
    hold_amount NUMBER(18, 4) NOT NULL,
    hold_reason VARCHAR2(128) NOT NULL,
    issuing_authority VARCHAR2(64) NOT NULL,
    hold_status VARCHAR2(16) DEFAULT 'ACTIVE' NOT NULL,
    release_date DATE,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_cbs_account_holds PRIMARY KEY (hold_id),
    CONSTRAINT fk_cbs_account_holds_0 FOREIGN KEY (account_no) REFERENCES cbs_accounts (account_no),
    CONSTRAINT chk_cbs_hld_amt CHECK (hold_amount > 0)
);

-- Foreign Exchange Market and Spot Rates
CREATE TABLE cbs_fx_rates (
    base_currency VARCHAR2(3) NOT NULL,
    target_currency VARCHAR2(3) NOT NULL,
    effective_date DATE DEFAULT SYSDATE NOT NULL,
    buy_rate NUMBER(14, 6) NOT NULL,
    sell_rate NUMBER(14, 6) NOT NULL,
    middle_rate NUMBER(14, 6) NOT NULL,
    source_feed VARCHAR2(32) DEFAULT 'PBOC' NOT NULL,
    status VARCHAR2(16) DEFAULT 'ACTIVE' NOT NULL,
    CONSTRAINT pk_cbs_fx_rates PRIMARY KEY (base_currency, target_currency, effective_date)
);

-- Double-Entry General Ledger Financial Postings
CREATE TABLE cbs_general_ledger (
    ledger_id VARCHAR2(32) NOT NULL,
    account_no VARCHAR2(32) NOT NULL,
    journal_id VARCHAR2(64) NOT NULL,
    entry_type VARCHAR2(6) NOT NULL,
    amount NUMBER(18, 4) NOT NULL,
    running_balance NUMBER(18, 4) NOT NULL,
    currency_code VARCHAR2(3) DEFAULT 'CNY' NOT NULL,
    branch_code VARCHAR2(16) DEFAULT 'BR001' NOT NULL,
    value_date DATE DEFAULT SYSDATE NOT NULL,
    description VARCHAR2(256),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_cbs_general_ledger PRIMARY KEY (ledger_id),
    CONSTRAINT fk_cbs_general_ledger_0 FOREIGN KEY (account_no) REFERENCES cbs_accounts (account_no),
    CONSTRAINT chk_cbs_gl_entry CHECK (entry_type IN ('DEBIT', 'CREDIT')),
    CONSTRAINT chk_cbs_gl_amt CHECK (amount > 0)
);
CREATE INDEX idx_cbs_gl_jrn ON cbs_general_ledger (journal_id);
CREATE INDEX idx_cbs_gl_acc_date ON cbs_general_ledger (account_no, value_date);

-- Payment and Clearing Transactions
CREATE TABLE cbs_settlement_transactions (
    tx_id VARCHAR2(64) NOT NULL,
    source_account VARCHAR2(32) NOT NULL,
    target_account VARCHAR2(32) NOT NULL,
    amount NUMBER(18, 4) NOT NULL,
    fee_amount NUMBER(18, 4) DEFAULT 0.0000 NOT NULL,
    currency_code VARCHAR2(3) DEFAULT 'CNY' NOT NULL,
    channel_code VARCHAR2(16) DEFAULT 'ONLINE' NOT NULL,
    tx_status VARCHAR2(16) DEFAULT 'PENDING' NOT NULL,
    settlement_batch_no VARCHAR2(32),
    settlement_date DATE,
    reference_code VARCHAR2(64),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    CONSTRAINT pk_cbs_settlement_transacti PRIMARY KEY (tx_id),
    CONSTRAINT fk_cbs_settlement_trans_0 FOREIGN KEY (source_account) REFERENCES cbs_accounts (account_no),
    CONSTRAINT fk_cbs_settlement_trans_1 FOREIGN KEY (target_account) REFERENCES cbs_accounts (account_no),
    CONSTRAINT chk_cbs_tx_stat CHECK (tx_status IN ('PENDING', 'COMMITTED', 'REVERSED', 'FAILED'))
);
CREATE INDEX idx_cbs_tx_batch ON cbs_settlement_transactions (settlement_batch_no, settlement_date);
CREATE INDEX idx_cbs_tx_date ON cbs_settlement_transactions (settlement_date);

-- Recurring Standing Orders
CREATE TABLE cbs_standing_orders (
    order_id VARCHAR2(32) NOT NULL,
    source_account VARCHAR2(32) NOT NULL,
    target_account VARCHAR2(32) NOT NULL,
    amount NUMBER(18, 4) NOT NULL,
    frequency VARCHAR2(16) DEFAULT 'MONTHLY' NOT NULL,
    next_execution_date DATE NOT NULL,
    end_date DATE,
    status VARCHAR2(16) DEFAULT 'ACTIVE' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_cbs_standing_orders PRIMARY KEY (order_id),
    CONSTRAINT fk_cbs_standing_orders_0 FOREIGN KEY (source_account) REFERENCES cbs_accounts (account_no),
    CONSTRAINT fk_cbs_standing_orders_1 FOREIGN KEY (target_account) REFERENCES cbs_accounts (account_no)
);

-- Commercial and Retail Loan Agreements
CREATE TABLE cbs_loan_contracts (
    contract_no VARCHAR2(32) NOT NULL,
    customer_id VARCHAR2(32) NOT NULL,
    disbursement_account VARCHAR2(32) NOT NULL,
    repayment_account VARCHAR2(32) NOT NULL,
    principal_amount NUMBER(18, 4) NOT NULL,
    remaining_principal NUMBER(18, 4) NOT NULL,
    annual_interest_rate NUMBER(8, 6) NOT NULL,
    term_months NUMBER(4) NOT NULL,
    repayment_method VARCHAR2(24) DEFAULT 'EQUAL_INSTALLMENT' NOT NULL,
    loan_status VARCHAR2(16) DEFAULT 'DISBURSED' NOT NULL,
    start_date DATE NOT NULL,
    maturity_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_cbs_loan_contracts PRIMARY KEY (contract_no),
    CONSTRAINT fk_cbs_loan_contracts_0 FOREIGN KEY (customer_id) REFERENCES cbs_customers (customer_id),
    CONSTRAINT fk_cbs_loan_contracts_1 FOREIGN KEY (disbursement_account) REFERENCES cbs_accounts (account_no),
    CONSTRAINT fk_cbs_loan_contracts_2 FOREIGN KEY (repayment_account) REFERENCES cbs_accounts (account_no)
);

-- Installment Amortization Schedules
CREATE TABLE cbs_loan_repayment_schedule (
    schedule_id VARCHAR2(32) NOT NULL,
    contract_no VARCHAR2(32) NOT NULL,
    period_number NUMBER(4) NOT NULL,
    due_date DATE NOT NULL,
    principal_due NUMBER(18, 4) NOT NULL,
    interest_due NUMBER(18, 4) NOT NULL,
    total_installment NUMBER(18, 4) NOT NULL,
    principal_paid NUMBER(18, 4) DEFAULT 0.0000 NOT NULL,
    interest_paid NUMBER(18, 4) DEFAULT 0.0000 NOT NULL,
    payment_status VARCHAR2(16) DEFAULT 'UNPAID' NOT NULL,
    paid_date DATE,
    CONSTRAINT pk_cbs_loan_repayment_sched PRIMARY KEY (schedule_id),
    CONSTRAINT fk_cbs_loan_repayment_s_0 FOREIGN KEY (contract_no) REFERENCES cbs_loan_contracts (contract_no)
);

-- End of Day Trial Balance Records
CREATE TABLE cbs_daily_ledger_balance (
    balance_date DATE NOT NULL,
    branch_code VARCHAR2(16) NOT NULL,
    currency_code VARCHAR2(3) NOT NULL,
    total_debit NUMBER(20, 4) DEFAULT 0.0000 NOT NULL,
    total_credit NUMBER(20, 4) DEFAULT 0.0000 NOT NULL,
    closing_balance NUMBER(20, 4) DEFAULT 0.0000 NOT NULL,
    is_balanced NUMBER(1) DEFAULT 1 NOT NULL,
    verified_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_cbs_daily_ledger_balance PRIMARY KEY (balance_date, branch_code, currency_code)
);

-- Cryptographic Immutable Audit Trail
CREATE TABLE cbs_audit_log (
    log_id VARCHAR2(64) NOT NULL,
    entity_name VARCHAR2(64) NOT NULL,
    entity_key VARCHAR2(64) NOT NULL,
    action_type VARCHAR2(16) NOT NULL,
    old_state CLOB,
    new_state CLOB,
    operator_id VARCHAR2(32) DEFAULT 'SYSTEM' NOT NULL,
    logged_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    checksum VARCHAR2(64) NOT NULL,
    CONSTRAINT pk_cbs_audit_log PRIMARY KEY (log_id)
);

-- Anti-Money Laundering AML Monitoring Alerts
CREATE TABLE cbs_suspicious_tx_alerts (
    alert_id VARCHAR2(32) NOT NULL,
    tx_id VARCHAR2(64) NOT NULL,
    account_no VARCHAR2(32) NOT NULL,
    alert_type VARCHAR2(32) NOT NULL,
    severity_level VARCHAR2(16) DEFAULT 'MEDIUM' NOT NULL,
    alert_score NUMBER(6, 2) NOT NULL,
    status VARCHAR2(16) DEFAULT 'OPEN' NOT NULL,
    investigator_id VARCHAR2(32),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_cbs_suspicious_tx_alerts PRIMARY KEY (alert_id),
    CONSTRAINT fk_cbs_suspicious_tx_al_0 FOREIGN KEY (tx_id) REFERENCES cbs_settlement_transactions (tx_id)
);

-- Merchant Acquiring POS Contracts
CREATE TABLE cbs_merchant_contracts (
    merchant_id VARCHAR2(32) NOT NULL,
    merchant_name VARCHAR2(128) NOT NULL,
    settlement_account VARCHAR2(32) NOT NULL,
    fee_rate NUMBER(6, 4) DEFAULT 0.0060 NOT NULL,
    status VARCHAR2(16) DEFAULT 'ACTIVE' NOT NULL,
    created_date DATE DEFAULT SYSDATE NOT NULL,
    CONSTRAINT pk_cbs_merchant_contracts PRIMARY KEY (merchant_id),
    CONSTRAINT fk_cbs_merchant_contrac_0 FOREIGN KEY (settlement_account) REFERENCES cbs_accounts (account_no)
);

-- Bank Service Fee Schedules
CREATE TABLE cbs_fee_schedules (
    fee_code VARCHAR2(16) NOT NULL,
    fee_name VARCHAR2(64) NOT NULL,
    fee_type VARCHAR2(16) DEFAULT 'PERCENTAGE' NOT NULL,
    rate NUMBER(8, 4) NOT NULL,
    fixed_amount NUMBER(12, 4) DEFAULT 0.0000 NOT NULL,
    currency_code VARCHAR2(3) DEFAULT 'CNY' NOT NULL,
    CONSTRAINT pk_cbs_fee_schedules PRIMARY KEY (fee_code)
);

CREATE OR REPLACE PROCEDURE sp_cbs_transfer_funds (
    p_src_account IN VARCHAR2, p_tgt_account IN VARCHAR2,
    p_amount IN NUMBER, p_fee IN NUMBER, p_channel IN VARCHAR2,
    p_tx_id OUT VARCHAR2, p_status OUT VARCHAR2
) IS
    v_src_balance NUMBER(18, 4);
    v_src_status VARCHAR2(16);
    v_tgt_status VARCHAR2(16);
    v_journal_id VARCHAR2(64);
BEGIN
    p_tx_id := 'TX_' || TO_CHAR(SYSDATE, 'YYYYMMDDHH24MISS') || '_' || LPAD(cbs_journal_seq.NEXTVAL, 8, '0');
    v_journal_id := 'JRN_' || p_tx_id;
    IF p_amount <= 0 THEN
        p_status := 'ERROR_INVALID_AMOUNT';
        RETURN;
    END IF;
    SELECT balance, status INTO v_src_balance, v_src_status FROM cbs_accounts WHERE account_no = p_src_account FOR UPDATE;
    IF v_src_status <> 'ACTIVE' THEN
        p_status := 'ERROR_SRC_ACCOUNT_FROZEN';
        RETURN;
    END IF;
    IF v_src_balance < (p_amount + p_fee) THEN
        p_status := 'ERROR_INSUFFICIENT_FUNDS';
        RETURN;
    END IF;
    SELECT status INTO v_tgt_status FROM cbs_accounts WHERE account_no = p_tgt_account FOR UPDATE;
    IF v_tgt_status <> 'ACTIVE' THEN
        p_status := 'ERROR_TGT_ACCOUNT_INACTIVE';
        RETURN;
    END IF;
    UPDATE cbs_accounts SET balance = balance - (p_amount + p_fee), updated_at = SYSTIMESTAMP WHERE account_no = p_src_account;
    UPDATE cbs_accounts SET balance = balance + p_amount, updated_at = SYSTIMESTAMP WHERE account_no = p_tgt_account;
    INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description)
    VALUES ('GL_' || p_tx_id || '_D', p_src_account, v_journal_id, 'DEBIT', (p_amount + p_fee), (v_src_balance - p_amount - p_fee), 'CNY', 'Fund Transfer Debit');
    INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description)
    VALUES ('GL_' || p_tx_id || '_C', p_tgt_account, v_journal_id, 'CREDIT', p_amount, 0, 'CNY', 'Fund Transfer Credit');
    INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, fee_amount, currency_code, channel_code, tx_status, settlement_date, completed_at)
    VALUES (p_tx_id, p_src_account, p_tgt_account, p_amount, p_fee, 'CNY', p_channel, 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
    p_status := 'SUCCESS';
    COMMIT;
EXCEPTION
    WHEN NO_DATA_FOUND THEN ROLLBACK; p_status := 'ERROR_ACCOUNT_NOT_FOUND';
    WHEN OTHERS THEN ROLLBACK; p_status := 'ERROR_SYSTEM_EXCEPTION';
END sp_cbs_transfer_funds;
/
CREATE OR REPLACE PROCEDURE sp_cbs_accrue_daily_interest (
    p_settlement_date IN DATE, p_processed_count OUT NUMBER, p_total_interest OUT NUMBER
) IS
    CURSOR cur_accounts IS
        SELECT account_no, balance, interest_rate FROM cbs_accounts WHERE status = 'ACTIVE' AND balance > 0 FOR UPDATE OF balance;
    v_acc_no VARCHAR2(32); v_bal NUMBER(18, 4); v_rate NUMBER(8, 6); v_daily_interest NUMBER(18, 4);
BEGIN
    p_processed_count := 0; p_total_interest := 0;
    OPEN cur_accounts;
    LOOP
        FETCH cur_accounts INTO v_acc_no, v_bal, v_rate;
        EXIT WHEN cur_accounts%NOTFOUND;
        v_daily_interest := ROUND(v_bal * (v_rate / 365.0), 4);
        IF v_daily_interest > 0 THEN
            UPDATE cbs_accounts SET balance = balance + v_daily_interest, last_interest_date = p_settlement_date, updated_at = SYSTIMESTAMP WHERE account_no = v_acc_no;
            p_total_interest := p_total_interest + v_daily_interest;
        END IF;
        p_processed_count := p_processed_count + 1;
    END LOOP;
    CLOSE cur_accounts;
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN IF cur_accounts%ISOPEN THEN CLOSE cur_accounts; END IF; ROLLBACK; RAISE;
END sp_cbs_accrue_daily_interest;
/
CREATE OR REPLACE PROCEDURE sp_cbs_log_audit_event (
    p_entity_name IN VARCHAR2, p_entity_key IN VARCHAR2, p_action IN VARCHAR2,
    p_old_state IN CLOB, p_new_state IN CLOB, p_operator IN VARCHAR2
) IS
    PRAGMA AUTONOMOUS_TRANSACTION;
    v_log_id VARCHAR2(64); v_checksum VARCHAR2(64);
BEGIN
    v_log_id := 'AUD_' || TO_CHAR(SYSTIMESTAMP, 'YYYYMMDDHH24MISSFF') || '_' || DBMS_RANDOM.STRING('X', 8);
    v_checksum := RAWTOHEX(DBMS_CRYPTO.HASH(UTL_I18N.STRING_TO_RAW(p_entity_name || p_entity_key || p_action, 'AL32UTF8'), 2));
    INSERT INTO cbs_audit_log (log_id, entity_name, entity_key, action_type, old_state, new_state, operator_id, logged_at, checksum)
    VALUES (v_log_id, p_entity_name, p_entity_key, p_action, p_old_state, p_new_state, p_operator, SYSTIMESTAMP, v_checksum);
    COMMIT;
END sp_cbs_log_audit_event;
/
CREATE OR REPLACE PROCEDURE sp_cbs_generate_loan_schedule (
    p_contract_no IN VARCHAR2
) IS
    v_principal NUMBER(18, 4); v_annual_rate NUMBER(8, 6); v_months NUMBER(4);
    v_monthly_rate NUMBER(12, 8); v_monthly_payment NUMBER(18, 4); v_rem_principal NUMBER(18, 4);
    v_interest_part NUMBER(18, 4); v_principal_part NUMBER(18, 4); v_due_date DATE;
BEGIN
    SELECT principal_amount, annual_interest_rate, term_months, start_date INTO v_principal, v_annual_rate, v_months, v_due_date
    FROM cbs_loan_contracts WHERE contract_no = p_contract_no;
    v_monthly_rate := v_annual_rate / 12.0;
    v_monthly_payment := ROUND(v_principal * (v_monthly_rate * POWER(1 + v_monthly_rate, v_months)) / (POWER(1 + v_monthly_rate, v_months) - 1), 4);
    v_rem_principal := v_principal;
    FOR i IN 1..v_months LOOP
        v_due_date := ADD_MONTHS(v_due_date, 1);
        v_interest_part := ROUND(v_rem_principal * v_monthly_rate, 4);
        v_principal_part := v_monthly_payment - v_interest_part;
        IF i = v_months THEN
            v_principal_part := v_rem_principal;
            v_monthly_payment := v_principal_part + v_interest_part;
        END IF;
        v_rem_principal := v_rem_principal - v_principal_part;
        INSERT INTO cbs_loan_repayment_schedule (schedule_id, contract_no, period_number, due_date, principal_due, interest_due, total_installment, payment_status)
        VALUES ('SCH_' || p_contract_no || '_' || LPAD(i, 3, '0'), p_contract_no, i, v_due_date, v_principal_part, v_interest_part, v_monthly_payment, 'UNPAID');
    END LOOP;
    COMMIT;
END sp_cbs_generate_loan_schedule;
/
CREATE OR REPLACE PROCEDURE sp_cbs_reconcile_eod (
    p_reconcile_date IN DATE, p_is_balanced OUT NUMBER
) IS
    v_total_debit NUMBER(20, 4); v_total_credit NUMBER(20, 4);
BEGIN
    SELECT NVL(SUM(CASE WHEN entry_type = 'DEBIT' THEN amount ELSE 0 END), 0),
           NVL(SUM(CASE WHEN entry_type = 'CREDIT' THEN amount ELSE 0 END), 0)
    INTO v_total_debit, v_total_credit FROM cbs_general_ledger WHERE value_date = p_reconcile_date;
    IF v_total_debit = v_total_credit THEN p_is_balanced := 1; ELSE p_is_balanced := 0; END IF;
    MERGE INTO cbs_daily_ledger_balance d USING (SELECT p_reconcile_date AS bdate, 'GLOBAL' AS bbranch, 'CNY' AS bcurr FROM DUAL) s
    ON (d.balance_date = s.bdate AND d.branch_code = s.bbranch AND d.currency_code = s.bcurr)
    WHEN MATCHED THEN UPDATE SET total_debit = v_total_debit, total_credit = v_total_credit, is_balanced = p_is_balanced, verified_at = SYSTIMESTAMP
    WHEN NOT MATCHED THEN INSERT (balance_date, branch_code, currency_code, total_debit, total_credit, closing_balance, is_balanced, verified_at)
    VALUES (p_reconcile_date, 'GLOBAL', 'CNY', v_total_debit, v_total_credit, (v_total_credit - v_total_debit), p_is_balanced, SYSTIMESTAMP);
    COMMIT;
END sp_cbs_reconcile_eod;
/
CREATE OR REPLACE PROCEDURE sp_cbs_process_standing_orders (
    p_execution_date IN DATE, p_executed_count OUT NUMBER
) IS
    CURSOR c_orders IS SELECT order_id, source_account, target_account, amount FROM cbs_standing_orders WHERE status = 'ACTIVE' AND next_execution_date <= p_execution_date;
    v_tx_id VARCHAR2(64); v_status VARCHAR2(64);
BEGIN
    p_executed_count := 0;
    FOR r IN c_orders LOOP
        sp_cbs_transfer_funds(r.source_account, r.target_account, r.amount, 0, 'STANDING_ORDER', v_tx_id, v_status);
        IF v_status = 'SUCCESS' THEN
            UPDATE cbs_standing_orders SET next_execution_date = ADD_MONTHS(next_execution_date, 1) WHERE order_id = r.order_id;
            p_executed_count := p_executed_count + 1;
        END IF;
    END LOOP;
    COMMIT;
END sp_cbs_process_standing_orders;
/
CREATE OR REPLACE PROCEDURE sp_cbs_apply_account_hold (
    p_account_no IN VARCHAR2, p_amount IN NUMBER, p_reason IN VARCHAR2,
    p_authority IN VARCHAR2, p_hold_id OUT VARCHAR2
) IS
BEGIN
    p_hold_id := 'HLD_' || TO_CHAR(SYSDATE, 'YYYYMMDD') || '_' || DBMS_RANDOM.STRING('U', 6);
    UPDATE cbs_accounts SET frozen_balance = frozen_balance + p_amount, updated_at = SYSTIMESTAMP WHERE account_no = p_account_no;
    INSERT INTO cbs_account_holds (hold_id, account_no, hold_amount, hold_reason, issuing_authority, hold_status)
    VALUES (p_hold_id, p_account_no, p_amount, p_reason, p_authority, 'ACTIVE');
    sp_cbs_log_audit_event('cbs_accounts', p_account_no, 'APPLY_HOLD', 'Hold added: ' || p_amount, 'ACTIVE', p_authority);
    COMMIT;
END sp_cbs_apply_account_hold;
/
CREATE OR REPLACE PROCEDURE sp_cbs_release_account_hold (
    p_hold_id IN VARCHAR2, p_status OUT VARCHAR2
) IS
    v_acc_no VARCHAR2(32); v_amt NUMBER(18, 4); v_hstatus VARCHAR2(16);
BEGIN
    SELECT account_no, hold_amount, hold_status INTO v_acc_no, v_amt, v_hstatus FROM cbs_account_holds WHERE hold_id = p_hold_id FOR UPDATE;
    IF v_hstatus <> 'ACTIVE' THEN p_status := 'ERROR_HOLD_NOT_ACTIVE'; RETURN; END IF;
    UPDATE cbs_accounts SET frozen_balance = GREATEST(0, frozen_balance - v_amt), updated_at = SYSTIMESTAMP WHERE account_no = v_acc_no;
    UPDATE cbs_account_holds SET hold_status = 'RELEASED', release_date = SYSDATE WHERE hold_id = p_hold_id;
    p_status := 'SUCCESS';
    COMMIT;
END sp_cbs_release_account_hold;
/
CREATE OR REPLACE PROCEDURE sp_cbs_revalue_fx (
    p_base_curr IN VARCHAR2, p_target_curr IN VARCHAR2, p_as_of_date IN DATE, p_gain_loss OUT NUMBER
) IS
    v_rate NUMBER(14, 6); v_foreign_balance NUMBER(18, 4);
BEGIN
    SELECT middle_rate INTO v_rate FROM cbs_fx_rates WHERE base_currency = p_base_curr AND target_currency = p_target_curr AND effective_date = p_as_of_date;
    SELECT NVL(SUM(balance), 0) INTO v_foreign_balance FROM cbs_accounts WHERE currency_code = p_base_curr;
    p_gain_loss := ROUND(v_foreign_balance * v_rate, 4);
END sp_cbs_revalue_fx;
/
CREATE OR REPLACE PROCEDURE sp_cbs_pay_loan_installment (
    p_schedule_id IN VARCHAR2, p_payment_amount IN NUMBER, p_status OUT VARCHAR2
) IS
    v_contract_no VARCHAR2(32); v_p_due NUMBER(18, 4); v_i_due NUMBER(18, 4);
BEGIN
    SELECT contract_no, principal_due, interest_due INTO v_contract_no, v_p_due, v_i_due FROM cbs_loan_repayment_schedule WHERE schedule_id = p_schedule_id FOR UPDATE;
    IF p_payment_amount >= (v_p_due + v_i_due) THEN
        UPDATE cbs_loan_repayment_schedule SET principal_paid = v_p_due, interest_paid = v_i_due, payment_status = 'PAID', paid_date = SYSDATE WHERE schedule_id = p_schedule_id;
        UPDATE cbs_loan_contracts SET remaining_principal = remaining_principal - v_p_due WHERE contract_no = v_contract_no;
        p_status := 'PAID_IN_FULL';
    ELSE
        UPDATE cbs_loan_repayment_schedule SET interest_paid = LEAST(p_payment_amount, v_i_due), principal_paid = GREATEST(0, p_payment_amount - v_i_due), payment_status = 'PARTIALLY_PAID', paid_date = SYSDATE WHERE schedule_id = p_schedule_id;
        p_status := 'PARTIALLY_PAID';
    END IF;
    COMMIT;
END sp_cbs_pay_loan_installment;
/
CREATE OR REPLACE PROCEDURE sp_cbs_dynamic_report_query (
    p_table_name IN VARCHAR2, p_where_col IN VARCHAR2, p_where_val IN VARCHAR2, p_count OUT NUMBER
) IS
    v_sql VARCHAR2(512);
BEGIN
    v_sql := 'SELECT COUNT(*) FROM ' || DBMS_ASSERT.ENQUOTE_NAME(p_table_name) || ' WHERE ' || DBMS_ASSERT.ENQUOTE_NAME(p_where_col) || ' = :val';
    EXECUTE IMMEDIATE v_sql INTO p_count USING p_where_val;
END sp_cbs_dynamic_report_query;
/
CREATE OR REPLACE PROCEDURE sp_cbs_merchant_batch_settle (
    p_batch_no IN VARCHAR2, p_merchant_id IN VARCHAR2, p_gross_amount IN NUMBER, p_settled_amount OUT NUMBER
) IS
    v_fee_rate NUMBER(6, 4); v_settle_acc VARCHAR2(32); v_fee NUMBER(18, 4); v_tx_id VARCHAR2(64); v_stat VARCHAR2(32);
BEGIN
    SELECT fee_rate, settlement_account INTO v_fee_rate, v_settle_acc FROM cbs_merchant_contracts WHERE merchant_id = p_merchant_id;
    v_fee := ROUND(p_gross_amount * v_fee_rate, 4);
    p_settled_amount := p_gross_amount - v_fee;
    sp_cbs_transfer_funds('ACC_CLEARING_POOL', v_settle_acc, p_settled_amount, 0, 'MERCHANT_SETTLE', v_tx_id, v_stat);
    COMMIT;
END sp_cbs_merchant_batch_settle;
/
CREATE OR REPLACE PROCEDURE sp_cbs_evaluate_aml_risk (
    p_tx_id IN VARCHAR2, p_risk_flag OUT NUMBER
) IS
    v_amt NUMBER(18, 4); v_src_acc VARCHAR2(32); v_risk VARCHAR2(8);
BEGIN
    p_risk_flag := 0;
    SELECT amount, source_account INTO v_amt, v_src_acc FROM cbs_settlement_transactions WHERE tx_id = p_tx_id;
    IF v_amt >= 200000.0000 THEN
        p_risk_flag := 1;
        INSERT INTO cbs_suspicious_tx_alerts (alert_id, tx_id, account_no, alert_type, severity_level, alert_score, status)
        VALUES ('ALT_' || LPAD(cbs_alert_seq.NEXTVAL, 8, '0'), p_tx_id, v_src_acc, 'LARGE_TRANSACTION_THRESHOLD', 'HIGH', 85.50, 'OPEN');
    END IF;
    COMMIT;
END sp_cbs_evaluate_aml_risk;
/
CREATE OR REPLACE PROCEDURE sp_cbs_open_new_account (
    p_customer_id IN VARCHAR2, p_account_type IN VARCHAR2, p_currency IN VARCHAR2,
    p_initial_deposit IN NUMBER, p_new_account_no OUT VARCHAR2
) IS
BEGIN
    p_new_account_no := 'ACC_' || LPAD(cbs_account_seq.NEXTVAL, 8, '0');
    INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate)
    VALUES (p_new_account_no, p_customer_id, p_account_type, p_currency, p_initial_deposit, 'ACTIVE', 0.003500);
    COMMIT;
END sp_cbs_open_new_account;
/
CREATE OR REPLACE PROCEDURE sp_cbs_close_account_balance (
    p_account_no IN VARCHAR2, p_payout_account IN VARCHAR2, p_status OUT VARCHAR2
) IS
    v_bal NUMBER(18, 4); v_hld NUMBER(18, 4); v_tx_id VARCHAR2(64); v_tstat VARCHAR2(32);
BEGIN
    SELECT balance, frozen_balance INTO v_bal, v_hld FROM cbs_accounts WHERE account_no = p_account_no FOR UPDATE;
    IF v_hld > 0 THEN p_status := 'ERROR_HOLDS_EXIST'; RETURN; END IF;
    IF v_bal > 0 THEN
        sp_cbs_transfer_funds(p_account_no, p_payout_account, v_bal, 0, 'CLOSURE_PAYOUT', v_tx_id, v_tstat);
    END IF;
    UPDATE cbs_accounts SET status = 'CLOSED', balance = 0, updated_at = SYSTIMESTAMP WHERE account_no = p_account_no;
    p_status := 'SUCCESS';
    COMMIT;
END sp_cbs_close_account_balance;
/

CREATE OR REPLACE VIEW v_cbs_daily_account_summary AS
SELECT a.account_no, a.customer_id, a.account_type, a.currency_code, a.balance, a.status,
       NVL(tx.daily_tx_count, 0) AS daily_tx_count, NVL(tx.daily_volume, 0) AS daily_tx_volume
FROM cbs_accounts a
LEFT JOIN (
    SELECT source_account, COUNT(*) AS daily_tx_count, SUM(amount) AS daily_volume
    FROM cbs_settlement_transactions WHERE settlement_date = TRUNC(SYSDATE)
    GROUP BY source_account
) tx ON a.account_no = tx.source_account;
CREATE OR REPLACE VIEW v_cbs_trial_balance_check AS
SELECT value_date, branch_code, currency_code,
       SUM(CASE WHEN entry_type = 'DEBIT' THEN amount ELSE 0 END) AS total_debit,
       SUM(CASE WHEN entry_type = 'CREDIT' THEN amount ELSE 0 END) AS total_credit,
       (SUM(CASE WHEN entry_type = 'CREDIT' THEN amount ELSE 0 END) - SUM(CASE WHEN entry_type = 'DEBIT' THEN amount ELSE 0 END)) AS diff_amount
FROM cbs_general_ledger GROUP BY value_date, branch_code, currency_code;
CREATE OR REPLACE VIEW v_cbs_overdue_loan_summary AS
SELECT c.contract_no, c.customer_id, c.principal_amount, c.remaining_principal, s.period_number, s.due_date, s.total_installment,
       (TRUNC(SYSDATE) - s.due_date) AS days_overdue
FROM cbs_loan_contracts c JOIN cbs_loan_repayment_schedule s ON c.contract_no = s.contract_no
WHERE s.payment_status = 'OVERDUE';
CREATE OR REPLACE VIEW v_cbs_high_value_tx_monitor AS
SELECT tx.tx_id, tx.source_account, tx.target_account, tx.amount, tx.currency_code, tx.channel_code, tx.settlement_date,
       cust.full_name AS customer_name, cust.risk_rating
FROM cbs_settlement_transactions tx
JOIN cbs_accounts acc ON tx.source_account = acc.account_no
JOIN cbs_customers cust ON acc.customer_id = cust.customer_id
WHERE tx.amount >= 50000.0000;

-- Seed Datasets for Banking Core System
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR001', 'Bank Branch 001', 'SWIFT0001', 'CLEAR_001', '110001');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR002', 'Bank Branch 002', 'SWIFT0002', 'CLEAR_002', '110002');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR003', 'Bank Branch 003', 'SWIFT0003', 'CLEAR_003', '110003');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR004', 'Bank Branch 004', 'SWIFT0004', 'CLEAR_004', '110004');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR005', 'Bank Branch 005', 'SWIFT0005', 'CLEAR_005', '110005');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR006', 'Bank Branch 006', 'SWIFT0006', 'CLEAR_006', '110006');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR007', 'Bank Branch 007', 'SWIFT0007', 'CLEAR_007', '110007');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR008', 'Bank Branch 008', 'SWIFT0008', 'CLEAR_008', '110008');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR009', 'Bank Branch 009', 'SWIFT0009', 'CLEAR_009', '110009');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR010', 'Bank Branch 010', 'SWIFT0010', 'CLEAR_010', '110010');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR011', 'Bank Branch 011', 'SWIFT0011', 'CLEAR_011', '110011');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR012', 'Bank Branch 012', 'SWIFT0012', 'CLEAR_012', '110012');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR013', 'Bank Branch 013', 'SWIFT0013', 'CLEAR_013', '110013');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR014', 'Bank Branch 014', 'SWIFT0014', 'CLEAR_014', '110014');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR015', 'Bank Branch 015', 'SWIFT0015', 'CLEAR_015', '110015');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR016', 'Bank Branch 016', 'SWIFT0016', 'CLEAR_016', '110016');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR017', 'Bank Branch 017', 'SWIFT0017', 'CLEAR_017', '110017');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR018', 'Bank Branch 018', 'SWIFT0018', 'CLEAR_018', '110018');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR019', 'Bank Branch 019', 'SWIFT0019', 'CLEAR_019', '110019');
INSERT INTO cbs_branches (branch_code, branch_name, swift_bic, clearing_code, city_code) VALUES ('BR020', 'Bank Branch 020', 'SWIFT0020', 'CLEAR_020', '110020');
INSERT INTO cbs_account_types (account_type, category, type_description, base_interest_rate) VALUES ('SAVINGS', 'DEMAND', 'Personal Demand Savings', 0.003500);
INSERT INTO cbs_account_types (account_type, category, type_description, base_interest_rate) VALUES ('CHECKING', 'DEMAND', 'Corporate Current Checking', 0.001000);
INSERT INTO cbs_account_types (account_type, category, type_description, base_interest_rate) VALUES ('FIXED_1Y', 'FIXED_TERM', 'One Year Fixed Deposit', 0.017500);
INSERT INTO cbs_account_types (account_type, category, type_description, base_interest_rate) VALUES ('CLEARING', 'NOSTRO', 'Interbank Clearing Account', 0.000000);

INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0001', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000001', 'Retail_Customer_0001', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0002', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000002', 'Retail_Customer_0002', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0003', 'CORPORATE', 'NATIONAL_ID', 'ID_00000003', 'Enterprise_Client_0003', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0004', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000004', 'Retail_Customer_0004', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0005', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000005', 'Retail_Customer_0005', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0006', 'CORPORATE', 'NATIONAL_ID', 'ID_00000006', 'Enterprise_Client_0006', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0007', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000007', 'Retail_Customer_0007', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0008', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000008', 'Retail_Customer_0008', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0009', 'CORPORATE', 'NATIONAL_ID', 'ID_00000009', 'Enterprise_Client_0009', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0010', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000010', 'Retail_Customer_0010', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0011', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000011', 'Retail_Customer_0011', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0012', 'CORPORATE', 'NATIONAL_ID', 'ID_00000012', 'Enterprise_Client_0012', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0013', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000013', 'Retail_Customer_0013', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0014', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000014', 'Retail_Customer_0014', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0015', 'CORPORATE', 'NATIONAL_ID', 'ID_00000015', 'Enterprise_Client_0015', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0016', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000016', 'Retail_Customer_0016', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0017', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000017', 'Retail_Customer_0017', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0018', 'CORPORATE', 'NATIONAL_ID', 'ID_00000018', 'Enterprise_Client_0018', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0019', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000019', 'Retail_Customer_0019', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0020', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000020', 'Retail_Customer_0020', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0021', 'CORPORATE', 'NATIONAL_ID', 'ID_00000021', 'Enterprise_Client_0021', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0022', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000022', 'Retail_Customer_0022', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0023', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000023', 'Retail_Customer_0023', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0024', 'CORPORATE', 'NATIONAL_ID', 'ID_00000024', 'Enterprise_Client_0024', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0025', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000025', 'Retail_Customer_0025', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0026', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000026', 'Retail_Customer_0026', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0027', 'CORPORATE', 'NATIONAL_ID', 'ID_00000027', 'Enterprise_Client_0027', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0028', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000028', 'Retail_Customer_0028', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0029', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000029', 'Retail_Customer_0029', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0030', 'CORPORATE', 'NATIONAL_ID', 'ID_00000030', 'Enterprise_Client_0030', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0031', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000031', 'Retail_Customer_0031', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0032', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000032', 'Retail_Customer_0032', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0033', 'CORPORATE', 'NATIONAL_ID', 'ID_00000033', 'Enterprise_Client_0033', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0034', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000034', 'Retail_Customer_0034', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0035', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000035', 'Retail_Customer_0035', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0036', 'CORPORATE', 'NATIONAL_ID', 'ID_00000036', 'Enterprise_Client_0036', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0037', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000037', 'Retail_Customer_0037', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0038', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000038', 'Retail_Customer_0038', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0039', 'CORPORATE', 'NATIONAL_ID', 'ID_00000039', 'Enterprise_Client_0039', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0040', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000040', 'Retail_Customer_0040', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0041', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000041', 'Retail_Customer_0041', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0042', 'CORPORATE', 'NATIONAL_ID', 'ID_00000042', 'Enterprise_Client_0042', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0043', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000043', 'Retail_Customer_0043', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0044', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000044', 'Retail_Customer_0044', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0045', 'CORPORATE', 'NATIONAL_ID', 'ID_00000045', 'Enterprise_Client_0045', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0046', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000046', 'Retail_Customer_0046', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0047', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000047', 'Retail_Customer_0047', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0048', 'CORPORATE', 'NATIONAL_ID', 'ID_00000048', 'Enterprise_Client_0048', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0049', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000049', 'Retail_Customer_0049', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0050', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000050', 'Retail_Customer_0050', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0051', 'CORPORATE', 'NATIONAL_ID', 'ID_00000051', 'Enterprise_Client_0051', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0052', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000052', 'Retail_Customer_0052', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0053', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000053', 'Retail_Customer_0053', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0054', 'CORPORATE', 'NATIONAL_ID', 'ID_00000054', 'Enterprise_Client_0054', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0055', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000055', 'Retail_Customer_0055', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0056', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000056', 'Retail_Customer_0056', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0057', 'CORPORATE', 'NATIONAL_ID', 'ID_00000057', 'Enterprise_Client_0057', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0058', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000058', 'Retail_Customer_0058', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0059', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000059', 'Retail_Customer_0059', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0060', 'CORPORATE', 'NATIONAL_ID', 'ID_00000060', 'Enterprise_Client_0060', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0061', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000061', 'Retail_Customer_0061', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0062', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000062', 'Retail_Customer_0062', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0063', 'CORPORATE', 'NATIONAL_ID', 'ID_00000063', 'Enterprise_Client_0063', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0064', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000064', 'Retail_Customer_0064', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0065', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000065', 'Retail_Customer_0065', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0066', 'CORPORATE', 'NATIONAL_ID', 'ID_00000066', 'Enterprise_Client_0066', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0067', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000067', 'Retail_Customer_0067', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0068', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000068', 'Retail_Customer_0068', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0069', 'CORPORATE', 'NATIONAL_ID', 'ID_00000069', 'Enterprise_Client_0069', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0070', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000070', 'Retail_Customer_0070', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0071', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000071', 'Retail_Customer_0071', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0072', 'CORPORATE', 'NATIONAL_ID', 'ID_00000072', 'Enterprise_Client_0072', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0073', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000073', 'Retail_Customer_0073', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0074', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000074', 'Retail_Customer_0074', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0075', 'CORPORATE', 'NATIONAL_ID', 'ID_00000075', 'Enterprise_Client_0075', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0076', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000076', 'Retail_Customer_0076', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0077', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000077', 'Retail_Customer_0077', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0078', 'CORPORATE', 'NATIONAL_ID', 'ID_00000078', 'Enterprise_Client_0078', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0079', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000079', 'Retail_Customer_0079', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0080', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000080', 'Retail_Customer_0080', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0081', 'CORPORATE', 'NATIONAL_ID', 'ID_00000081', 'Enterprise_Client_0081', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0082', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000082', 'Retail_Customer_0082', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0083', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000083', 'Retail_Customer_0083', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0084', 'CORPORATE', 'NATIONAL_ID', 'ID_00000084', 'Enterprise_Client_0084', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0085', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000085', 'Retail_Customer_0085', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0086', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000086', 'Retail_Customer_0086', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0087', 'CORPORATE', 'NATIONAL_ID', 'ID_00000087', 'Enterprise_Client_0087', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0088', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000088', 'Retail_Customer_0088', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0089', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000089', 'Retail_Customer_0089', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0090', 'CORPORATE', 'NATIONAL_ID', 'ID_00000090', 'Enterprise_Client_0090', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0091', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000091', 'Retail_Customer_0091', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0092', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000092', 'Retail_Customer_0092', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0093', 'CORPORATE', 'NATIONAL_ID', 'ID_00000093', 'Enterprise_Client_0093', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0094', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000094', 'Retail_Customer_0094', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0095', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000095', 'Retail_Customer_0095', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0096', 'CORPORATE', 'NATIONAL_ID', 'ID_00000096', 'Enterprise_Client_0096', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0097', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000097', 'Retail_Customer_0097', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0098', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000098', 'Retail_Customer_0098', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0099', 'CORPORATE', 'NATIONAL_ID', 'ID_00000099', 'Enterprise_Client_0099', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0100', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000100', 'Retail_Customer_0100', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0101', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000101', 'Retail_Customer_0101', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0102', 'CORPORATE', 'NATIONAL_ID', 'ID_00000102', 'Enterprise_Client_0102', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0103', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000103', 'Retail_Customer_0103', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0104', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000104', 'Retail_Customer_0104', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0105', 'CORPORATE', 'NATIONAL_ID', 'ID_00000105', 'Enterprise_Client_0105', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0106', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000106', 'Retail_Customer_0106', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0107', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000107', 'Retail_Customer_0107', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0108', 'CORPORATE', 'NATIONAL_ID', 'ID_00000108', 'Enterprise_Client_0108', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0109', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000109', 'Retail_Customer_0109', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0110', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000110', 'Retail_Customer_0110', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0111', 'CORPORATE', 'NATIONAL_ID', 'ID_00000111', 'Enterprise_Client_0111', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0112', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000112', 'Retail_Customer_0112', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0113', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000113', 'Retail_Customer_0113', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0114', 'CORPORATE', 'NATIONAL_ID', 'ID_00000114', 'Enterprise_Client_0114', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0115', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000115', 'Retail_Customer_0115', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0116', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000116', 'Retail_Customer_0116', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0117', 'CORPORATE', 'NATIONAL_ID', 'ID_00000117', 'Enterprise_Client_0117', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0118', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000118', 'Retail_Customer_0118', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0119', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000119', 'Retail_Customer_0119', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0120', 'CORPORATE', 'NATIONAL_ID', 'ID_00000120', 'Enterprise_Client_0120', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0121', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000121', 'Retail_Customer_0121', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0122', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000122', 'Retail_Customer_0122', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0123', 'CORPORATE', 'NATIONAL_ID', 'ID_00000123', 'Enterprise_Client_0123', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0124', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000124', 'Retail_Customer_0124', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0125', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000125', 'Retail_Customer_0125', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0126', 'CORPORATE', 'NATIONAL_ID', 'ID_00000126', 'Enterprise_Client_0126', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0127', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000127', 'Retail_Customer_0127', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0128', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000128', 'Retail_Customer_0128', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0129', 'CORPORATE', 'NATIONAL_ID', 'ID_00000129', 'Enterprise_Client_0129', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0130', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000130', 'Retail_Customer_0130', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0131', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000131', 'Retail_Customer_0131', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0132', 'CORPORATE', 'NATIONAL_ID', 'ID_00000132', 'Enterprise_Client_0132', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0133', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000133', 'Retail_Customer_0133', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0134', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000134', 'Retail_Customer_0134', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0135', 'CORPORATE', 'NATIONAL_ID', 'ID_00000135', 'Enterprise_Client_0135', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0136', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000136', 'Retail_Customer_0136', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0137', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000137', 'Retail_Customer_0137', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0138', 'CORPORATE', 'NATIONAL_ID', 'ID_00000138', 'Enterprise_Client_0138', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0139', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000139', 'Retail_Customer_0139', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0140', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000140', 'Retail_Customer_0140', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0141', 'CORPORATE', 'NATIONAL_ID', 'ID_00000141', 'Enterprise_Client_0141', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0142', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000142', 'Retail_Customer_0142', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0143', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000143', 'Retail_Customer_0143', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0144', 'CORPORATE', 'NATIONAL_ID', 'ID_00000144', 'Enterprise_Client_0144', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0145', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000145', 'Retail_Customer_0145', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0146', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000146', 'Retail_Customer_0146', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0147', 'CORPORATE', 'NATIONAL_ID', 'ID_00000147', 'Enterprise_Client_0147', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0148', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000148', 'Retail_Customer_0148', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0149', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000149', 'Retail_Customer_0149', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0150', 'CORPORATE', 'NATIONAL_ID', 'ID_00000150', 'Enterprise_Client_0150', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0151', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000151', 'Retail_Customer_0151', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0152', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000152', 'Retail_Customer_0152', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0153', 'CORPORATE', 'NATIONAL_ID', 'ID_00000153', 'Enterprise_Client_0153', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0154', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000154', 'Retail_Customer_0154', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0155', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000155', 'Retail_Customer_0155', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0156', 'CORPORATE', 'NATIONAL_ID', 'ID_00000156', 'Enterprise_Client_0156', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0157', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000157', 'Retail_Customer_0157', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0158', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000158', 'Retail_Customer_0158', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0159', 'CORPORATE', 'NATIONAL_ID', 'ID_00000159', 'Enterprise_Client_0159', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0160', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000160', 'Retail_Customer_0160', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0161', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000161', 'Retail_Customer_0161', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0162', 'CORPORATE', 'NATIONAL_ID', 'ID_00000162', 'Enterprise_Client_0162', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0163', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000163', 'Retail_Customer_0163', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0164', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000164', 'Retail_Customer_0164', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0165', 'CORPORATE', 'NATIONAL_ID', 'ID_00000165', 'Enterprise_Client_0165', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0166', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000166', 'Retail_Customer_0166', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0167', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000167', 'Retail_Customer_0167', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0168', 'CORPORATE', 'NATIONAL_ID', 'ID_00000168', 'Enterprise_Client_0168', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0169', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000169', 'Retail_Customer_0169', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0170', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000170', 'Retail_Customer_0170', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0171', 'CORPORATE', 'NATIONAL_ID', 'ID_00000171', 'Enterprise_Client_0171', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0172', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000172', 'Retail_Customer_0172', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0173', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000173', 'Retail_Customer_0173', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0174', 'CORPORATE', 'NATIONAL_ID', 'ID_00000174', 'Enterprise_Client_0174', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0175', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000175', 'Retail_Customer_0175', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0176', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000176', 'Retail_Customer_0176', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0177', 'CORPORATE', 'NATIONAL_ID', 'ID_00000177', 'Enterprise_Client_0177', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0178', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000178', 'Retail_Customer_0178', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0179', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000179', 'Retail_Customer_0179', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0180', 'CORPORATE', 'NATIONAL_ID', 'ID_00000180', 'Enterprise_Client_0180', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0181', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000181', 'Retail_Customer_0181', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0182', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000182', 'Retail_Customer_0182', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0183', 'CORPORATE', 'NATIONAL_ID', 'ID_00000183', 'Enterprise_Client_0183', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0184', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000184', 'Retail_Customer_0184', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0185', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000185', 'Retail_Customer_0185', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0186', 'CORPORATE', 'NATIONAL_ID', 'ID_00000186', 'Enterprise_Client_0186', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0187', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000187', 'Retail_Customer_0187', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0188', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000188', 'Retail_Customer_0188', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0189', 'CORPORATE', 'NATIONAL_ID', 'ID_00000189', 'Enterprise_Client_0189', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0190', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000190', 'Retail_Customer_0190', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0191', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000191', 'Retail_Customer_0191', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0192', 'CORPORATE', 'NATIONAL_ID', 'ID_00000192', 'Enterprise_Client_0192', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0193', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000193', 'Retail_Customer_0193', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0194', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000194', 'Retail_Customer_0194', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0195', 'CORPORATE', 'NATIONAL_ID', 'ID_00000195', 'Enterprise_Client_0195', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0196', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000196', 'Retail_Customer_0196', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0197', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000197', 'Retail_Customer_0197', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0198', 'CORPORATE', 'NATIONAL_ID', 'ID_00000198', 'Enterprise_Client_0198', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0199', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000199', 'Retail_Customer_0199', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0200', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000200', 'Retail_Customer_0200', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0201', 'CORPORATE', 'NATIONAL_ID', 'ID_00000201', 'Enterprise_Client_0201', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0202', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000202', 'Retail_Customer_0202', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0203', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000203', 'Retail_Customer_0203', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0204', 'CORPORATE', 'NATIONAL_ID', 'ID_00000204', 'Enterprise_Client_0204', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0205', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000205', 'Retail_Customer_0205', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0206', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000206', 'Retail_Customer_0206', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0207', 'CORPORATE', 'NATIONAL_ID', 'ID_00000207', 'Enterprise_Client_0207', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0208', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000208', 'Retail_Customer_0208', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0209', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000209', 'Retail_Customer_0209', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0210', 'CORPORATE', 'NATIONAL_ID', 'ID_00000210', 'Enterprise_Client_0210', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0211', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000211', 'Retail_Customer_0211', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0212', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000212', 'Retail_Customer_0212', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0213', 'CORPORATE', 'NATIONAL_ID', 'ID_00000213', 'Enterprise_Client_0213', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0214', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000214', 'Retail_Customer_0214', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0215', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000215', 'Retail_Customer_0215', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0216', 'CORPORATE', 'NATIONAL_ID', 'ID_00000216', 'Enterprise_Client_0216', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0217', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000217', 'Retail_Customer_0217', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0218', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000218', 'Retail_Customer_0218', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0219', 'CORPORATE', 'NATIONAL_ID', 'ID_00000219', 'Enterprise_Client_0219', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0220', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000220', 'Retail_Customer_0220', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0221', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000221', 'Retail_Customer_0221', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0222', 'CORPORATE', 'NATIONAL_ID', 'ID_00000222', 'Enterprise_Client_0222', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0223', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000223', 'Retail_Customer_0223', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0224', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000224', 'Retail_Customer_0224', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0225', 'CORPORATE', 'NATIONAL_ID', 'ID_00000225', 'Enterprise_Client_0225', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0226', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000226', 'Retail_Customer_0226', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0227', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000227', 'Retail_Customer_0227', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0228', 'CORPORATE', 'NATIONAL_ID', 'ID_00000228', 'Enterprise_Client_0228', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0229', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000229', 'Retail_Customer_0229', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0230', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000230', 'Retail_Customer_0230', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0231', 'CORPORATE', 'NATIONAL_ID', 'ID_00000231', 'Enterprise_Client_0231', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0232', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000232', 'Retail_Customer_0232', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0233', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000233', 'Retail_Customer_0233', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0234', 'CORPORATE', 'NATIONAL_ID', 'ID_00000234', 'Enterprise_Client_0234', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0235', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000235', 'Retail_Customer_0235', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0236', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000236', 'Retail_Customer_0236', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0237', 'CORPORATE', 'NATIONAL_ID', 'ID_00000237', 'Enterprise_Client_0237', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0238', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000238', 'Retail_Customer_0238', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0239', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000239', 'Retail_Customer_0239', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0240', 'CORPORATE', 'NATIONAL_ID', 'ID_00000240', 'Enterprise_Client_0240', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0241', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000241', 'Retail_Customer_0241', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0242', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000242', 'Retail_Customer_0242', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0243', 'CORPORATE', 'NATIONAL_ID', 'ID_00000243', 'Enterprise_Client_0243', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0244', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000244', 'Retail_Customer_0244', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0245', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000245', 'Retail_Customer_0245', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0246', 'CORPORATE', 'NATIONAL_ID', 'ID_00000246', 'Enterprise_Client_0246', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0247', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000247', 'Retail_Customer_0247', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0248', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000248', 'Retail_Customer_0248', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0249', 'CORPORATE', 'NATIONAL_ID', 'ID_00000249', 'Enterprise_Client_0249', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0250', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000250', 'Retail_Customer_0250', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0251', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000251', 'Retail_Customer_0251', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0252', 'CORPORATE', 'NATIONAL_ID', 'ID_00000252', 'Enterprise_Client_0252', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0253', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000253', 'Retail_Customer_0253', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0254', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000254', 'Retail_Customer_0254', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0255', 'CORPORATE', 'NATIONAL_ID', 'ID_00000255', 'Enterprise_Client_0255', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0256', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000256', 'Retail_Customer_0256', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0257', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000257', 'Retail_Customer_0257', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0258', 'CORPORATE', 'NATIONAL_ID', 'ID_00000258', 'Enterprise_Client_0258', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0259', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000259', 'Retail_Customer_0259', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0260', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000260', 'Retail_Customer_0260', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0261', 'CORPORATE', 'NATIONAL_ID', 'ID_00000261', 'Enterprise_Client_0261', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0262', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000262', 'Retail_Customer_0262', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0263', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000263', 'Retail_Customer_0263', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0264', 'CORPORATE', 'NATIONAL_ID', 'ID_00000264', 'Enterprise_Client_0264', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0265', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000265', 'Retail_Customer_0265', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0266', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000266', 'Retail_Customer_0266', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0267', 'CORPORATE', 'NATIONAL_ID', 'ID_00000267', 'Enterprise_Client_0267', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0268', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000268', 'Retail_Customer_0268', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0269', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000269', 'Retail_Customer_0269', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0270', 'CORPORATE', 'NATIONAL_ID', 'ID_00000270', 'Enterprise_Client_0270', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0271', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000271', 'Retail_Customer_0271', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0272', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000272', 'Retail_Customer_0272', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0273', 'CORPORATE', 'NATIONAL_ID', 'ID_00000273', 'Enterprise_Client_0273', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0274', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000274', 'Retail_Customer_0274', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0275', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000275', 'Retail_Customer_0275', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0276', 'CORPORATE', 'NATIONAL_ID', 'ID_00000276', 'Enterprise_Client_0276', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0277', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000277', 'Retail_Customer_0277', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0278', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000278', 'Retail_Customer_0278', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0279', 'CORPORATE', 'NATIONAL_ID', 'ID_00000279', 'Enterprise_Client_0279', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0280', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000280', 'Retail_Customer_0280', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0281', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000281', 'Retail_Customer_0281', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0282', 'CORPORATE', 'NATIONAL_ID', 'ID_00000282', 'Enterprise_Client_0282', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0283', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000283', 'Retail_Customer_0283', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0284', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000284', 'Retail_Customer_0284', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0285', 'CORPORATE', 'NATIONAL_ID', 'ID_00000285', 'Enterprise_Client_0285', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0286', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000286', 'Retail_Customer_0286', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0287', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000287', 'Retail_Customer_0287', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0288', 'CORPORATE', 'NATIONAL_ID', 'ID_00000288', 'Enterprise_Client_0288', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0289', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000289', 'Retail_Customer_0289', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0290', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000290', 'Retail_Customer_0290', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0291', 'CORPORATE', 'NATIONAL_ID', 'ID_00000291', 'Enterprise_Client_0291', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0292', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000292', 'Retail_Customer_0292', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0293', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000293', 'Retail_Customer_0293', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0294', 'CORPORATE', 'NATIONAL_ID', 'ID_00000294', 'Enterprise_Client_0294', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0295', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000295', 'Retail_Customer_0295', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0296', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000296', 'Retail_Customer_0296', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0297', 'CORPORATE', 'NATIONAL_ID', 'ID_00000297', 'Enterprise_Client_0297', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0298', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000298', 'Retail_Customer_0298', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0299', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000299', 'Retail_Customer_0299', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0300', 'CORPORATE', 'NATIONAL_ID', 'ID_00000300', 'Enterprise_Client_0300', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0301', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000301', 'Retail_Customer_0301', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0302', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000302', 'Retail_Customer_0302', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0303', 'CORPORATE', 'NATIONAL_ID', 'ID_00000303', 'Enterprise_Client_0303', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0304', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000304', 'Retail_Customer_0304', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0305', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000305', 'Retail_Customer_0305', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0306', 'CORPORATE', 'NATIONAL_ID', 'ID_00000306', 'Enterprise_Client_0306', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0307', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000307', 'Retail_Customer_0307', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0308', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000308', 'Retail_Customer_0308', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0309', 'CORPORATE', 'NATIONAL_ID', 'ID_00000309', 'Enterprise_Client_0309', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0310', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000310', 'Retail_Customer_0310', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0311', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000311', 'Retail_Customer_0311', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0312', 'CORPORATE', 'NATIONAL_ID', 'ID_00000312', 'Enterprise_Client_0312', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0313', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000313', 'Retail_Customer_0313', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0314', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000314', 'Retail_Customer_0314', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0315', 'CORPORATE', 'NATIONAL_ID', 'ID_00000315', 'Enterprise_Client_0315', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0316', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000316', 'Retail_Customer_0316', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0317', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000317', 'Retail_Customer_0317', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0318', 'CORPORATE', 'NATIONAL_ID', 'ID_00000318', 'Enterprise_Client_0318', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0319', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000319', 'Retail_Customer_0319', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0320', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000320', 'Retail_Customer_0320', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0321', 'CORPORATE', 'NATIONAL_ID', 'ID_00000321', 'Enterprise_Client_0321', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0322', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000322', 'Retail_Customer_0322', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0323', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000323', 'Retail_Customer_0323', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0324', 'CORPORATE', 'NATIONAL_ID', 'ID_00000324', 'Enterprise_Client_0324', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0325', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000325', 'Retail_Customer_0325', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0326', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000326', 'Retail_Customer_0326', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0327', 'CORPORATE', 'NATIONAL_ID', 'ID_00000327', 'Enterprise_Client_0327', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0328', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000328', 'Retail_Customer_0328', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0329', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000329', 'Retail_Customer_0329', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0330', 'CORPORATE', 'NATIONAL_ID', 'ID_00000330', 'Enterprise_Client_0330', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0331', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000331', 'Retail_Customer_0331', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0332', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000332', 'Retail_Customer_0332', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0333', 'CORPORATE', 'NATIONAL_ID', 'ID_00000333', 'Enterprise_Client_0333', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0334', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000334', 'Retail_Customer_0334', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0335', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000335', 'Retail_Customer_0335', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0336', 'CORPORATE', 'NATIONAL_ID', 'ID_00000336', 'Enterprise_Client_0336', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0337', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000337', 'Retail_Customer_0337', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0338', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000338', 'Retail_Customer_0338', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0339', 'CORPORATE', 'NATIONAL_ID', 'ID_00000339', 'Enterprise_Client_0339', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0340', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000340', 'Retail_Customer_0340', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0341', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000341', 'Retail_Customer_0341', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0342', 'CORPORATE', 'NATIONAL_ID', 'ID_00000342', 'Enterprise_Client_0342', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0343', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000343', 'Retail_Customer_0343', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0344', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000344', 'Retail_Customer_0344', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0345', 'CORPORATE', 'NATIONAL_ID', 'ID_00000345', 'Enterprise_Client_0345', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0346', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000346', 'Retail_Customer_0346', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0347', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000347', 'Retail_Customer_0347', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0348', 'CORPORATE', 'NATIONAL_ID', 'ID_00000348', 'Enterprise_Client_0348', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0349', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000349', 'Retail_Customer_0349', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0350', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000350', 'Retail_Customer_0350', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0351', 'CORPORATE', 'NATIONAL_ID', 'ID_00000351', 'Enterprise_Client_0351', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0352', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000352', 'Retail_Customer_0352', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0353', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000353', 'Retail_Customer_0353', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0354', 'CORPORATE', 'NATIONAL_ID', 'ID_00000354', 'Enterprise_Client_0354', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0355', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000355', 'Retail_Customer_0355', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0356', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000356', 'Retail_Customer_0356', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0357', 'CORPORATE', 'NATIONAL_ID', 'ID_00000357', 'Enterprise_Client_0357', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0358', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000358', 'Retail_Customer_0358', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0359', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000359', 'Retail_Customer_0359', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0360', 'CORPORATE', 'NATIONAL_ID', 'ID_00000360', 'Enterprise_Client_0360', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0361', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000361', 'Retail_Customer_0361', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0362', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000362', 'Retail_Customer_0362', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0363', 'CORPORATE', 'NATIONAL_ID', 'ID_00000363', 'Enterprise_Client_0363', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0364', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000364', 'Retail_Customer_0364', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0365', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000365', 'Retail_Customer_0365', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0366', 'CORPORATE', 'NATIONAL_ID', 'ID_00000366', 'Enterprise_Client_0366', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0367', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000367', 'Retail_Customer_0367', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0368', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000368', 'Retail_Customer_0368', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0369', 'CORPORATE', 'NATIONAL_ID', 'ID_00000369', 'Enterprise_Client_0369', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0370', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000370', 'Retail_Customer_0370', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0371', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000371', 'Retail_Customer_0371', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0372', 'CORPORATE', 'NATIONAL_ID', 'ID_00000372', 'Enterprise_Client_0372', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0373', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000373', 'Retail_Customer_0373', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0374', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000374', 'Retail_Customer_0374', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0375', 'CORPORATE', 'NATIONAL_ID', 'ID_00000375', 'Enterprise_Client_0375', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0376', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000376', 'Retail_Customer_0376', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0377', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000377', 'Retail_Customer_0377', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0378', 'CORPORATE', 'NATIONAL_ID', 'ID_00000378', 'Enterprise_Client_0378', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0379', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000379', 'Retail_Customer_0379', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0380', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000380', 'Retail_Customer_0380', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0381', 'CORPORATE', 'NATIONAL_ID', 'ID_00000381', 'Enterprise_Client_0381', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0382', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000382', 'Retail_Customer_0382', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0383', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000383', 'Retail_Customer_0383', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0384', 'CORPORATE', 'NATIONAL_ID', 'ID_00000384', 'Enterprise_Client_0384', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0385', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000385', 'Retail_Customer_0385', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0386', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000386', 'Retail_Customer_0386', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0387', 'CORPORATE', 'NATIONAL_ID', 'ID_00000387', 'Enterprise_Client_0387', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0388', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000388', 'Retail_Customer_0388', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0389', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000389', 'Retail_Customer_0389', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0390', 'CORPORATE', 'NATIONAL_ID', 'ID_00000390', 'Enterprise_Client_0390', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0391', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000391', 'Retail_Customer_0391', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0392', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000392', 'Retail_Customer_0392', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0393', 'CORPORATE', 'NATIONAL_ID', 'ID_00000393', 'Enterprise_Client_0393', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0394', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000394', 'Retail_Customer_0394', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0395', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000395', 'Retail_Customer_0395', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0396', 'CORPORATE', 'NATIONAL_ID', 'ID_00000396', 'Enterprise_Client_0396', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0397', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000397', 'Retail_Customer_0397', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0398', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000398', 'Retail_Customer_0398', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0399', 'CORPORATE', 'NATIONAL_ID', 'ID_00000399', 'Enterprise_Client_0399', 'R1', 'VERIFIED');
INSERT INTO cbs_customers (customer_id, customer_type, id_type, id_number, full_name, risk_rating, kyc_status) VALUES ('CUST_0400', 'INDIVIDUAL', 'NATIONAL_ID', 'ID_00000400', 'Retail_Customer_0400', 'R1', 'VERIFIED');
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0001', 'CUST_0001', 'SAVINGS', 'CNY', 50125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0002', 'CUST_0002', 'SAVINGS', 'CNY', 50250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0003', 'CUST_0003', 'SAVINGS', 'CNY', 50375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0004', 'CUST_0004', 'SAVINGS', 'CNY', 50500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0005', 'CUST_0005', 'SAVINGS', 'CNY', 50625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0006', 'CUST_0006', 'SAVINGS', 'CNY', 50750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0007', 'CUST_0007', 'SAVINGS', 'CNY', 50875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0008', 'CUST_0008', 'SAVINGS', 'CNY', 51000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0009', 'CUST_0009', 'SAVINGS', 'CNY', 51125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0010', 'CUST_0010', 'SAVINGS', 'CNY', 51250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0011', 'CUST_0011', 'SAVINGS', 'CNY', 51375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0012', 'CUST_0012', 'SAVINGS', 'CNY', 51500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0013', 'CUST_0013', 'SAVINGS', 'CNY', 51625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0014', 'CUST_0014', 'SAVINGS', 'CNY', 51750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0015', 'CUST_0015', 'SAVINGS', 'CNY', 51875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0016', 'CUST_0016', 'SAVINGS', 'CNY', 52000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0017', 'CUST_0017', 'SAVINGS', 'CNY', 52125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0018', 'CUST_0018', 'SAVINGS', 'CNY', 52250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0019', 'CUST_0019', 'SAVINGS', 'CNY', 52375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0020', 'CUST_0020', 'SAVINGS', 'CNY', 52500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0021', 'CUST_0021', 'SAVINGS', 'CNY', 52625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0022', 'CUST_0022', 'SAVINGS', 'CNY', 52750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0023', 'CUST_0023', 'SAVINGS', 'CNY', 52875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0024', 'CUST_0024', 'SAVINGS', 'CNY', 53000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0025', 'CUST_0025', 'SAVINGS', 'CNY', 53125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0026', 'CUST_0026', 'SAVINGS', 'CNY', 53250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0027', 'CUST_0027', 'SAVINGS', 'CNY', 53375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0028', 'CUST_0028', 'SAVINGS', 'CNY', 53500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0029', 'CUST_0029', 'SAVINGS', 'CNY', 53625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0030', 'CUST_0030', 'SAVINGS', 'CNY', 53750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0031', 'CUST_0031', 'SAVINGS', 'CNY', 53875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0032', 'CUST_0032', 'SAVINGS', 'CNY', 54000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0033', 'CUST_0033', 'SAVINGS', 'CNY', 54125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0034', 'CUST_0034', 'SAVINGS', 'CNY', 54250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0035', 'CUST_0035', 'SAVINGS', 'CNY', 54375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0036', 'CUST_0036', 'SAVINGS', 'CNY', 54500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0037', 'CUST_0037', 'SAVINGS', 'CNY', 54625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0038', 'CUST_0038', 'SAVINGS', 'CNY', 54750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0039', 'CUST_0039', 'SAVINGS', 'CNY', 54875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0040', 'CUST_0040', 'SAVINGS', 'CNY', 55000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0041', 'CUST_0041', 'SAVINGS', 'CNY', 55125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0042', 'CUST_0042', 'SAVINGS', 'CNY', 55250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0043', 'CUST_0043', 'SAVINGS', 'CNY', 55375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0044', 'CUST_0044', 'SAVINGS', 'CNY', 55500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0045', 'CUST_0045', 'SAVINGS', 'CNY', 55625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0046', 'CUST_0046', 'SAVINGS', 'CNY', 55750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0047', 'CUST_0047', 'SAVINGS', 'CNY', 55875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0048', 'CUST_0048', 'SAVINGS', 'CNY', 56000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0049', 'CUST_0049', 'SAVINGS', 'CNY', 56125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0050', 'CUST_0050', 'SAVINGS', 'CNY', 56250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0051', 'CUST_0051', 'SAVINGS', 'CNY', 56375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0052', 'CUST_0052', 'SAVINGS', 'CNY', 56500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0053', 'CUST_0053', 'SAVINGS', 'CNY', 56625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0054', 'CUST_0054', 'SAVINGS', 'CNY', 56750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0055', 'CUST_0055', 'SAVINGS', 'CNY', 56875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0056', 'CUST_0056', 'SAVINGS', 'CNY', 57000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0057', 'CUST_0057', 'SAVINGS', 'CNY', 57125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0058', 'CUST_0058', 'SAVINGS', 'CNY', 57250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0059', 'CUST_0059', 'SAVINGS', 'CNY', 57375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0060', 'CUST_0060', 'SAVINGS', 'CNY', 57500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0061', 'CUST_0061', 'SAVINGS', 'CNY', 57625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0062', 'CUST_0062', 'SAVINGS', 'CNY', 57750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0063', 'CUST_0063', 'SAVINGS', 'CNY', 57875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0064', 'CUST_0064', 'SAVINGS', 'CNY', 58000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0065', 'CUST_0065', 'SAVINGS', 'CNY', 58125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0066', 'CUST_0066', 'SAVINGS', 'CNY', 58250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0067', 'CUST_0067', 'SAVINGS', 'CNY', 58375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0068', 'CUST_0068', 'SAVINGS', 'CNY', 58500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0069', 'CUST_0069', 'SAVINGS', 'CNY', 58625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0070', 'CUST_0070', 'SAVINGS', 'CNY', 58750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0071', 'CUST_0071', 'SAVINGS', 'CNY', 58875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0072', 'CUST_0072', 'SAVINGS', 'CNY', 59000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0073', 'CUST_0073', 'SAVINGS', 'CNY', 59125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0074', 'CUST_0074', 'SAVINGS', 'CNY', 59250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0075', 'CUST_0075', 'SAVINGS', 'CNY', 59375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0076', 'CUST_0076', 'SAVINGS', 'CNY', 59500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0077', 'CUST_0077', 'SAVINGS', 'CNY', 59625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0078', 'CUST_0078', 'SAVINGS', 'CNY', 59750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0079', 'CUST_0079', 'SAVINGS', 'CNY', 59875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0080', 'CUST_0080', 'SAVINGS', 'CNY', 60000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0081', 'CUST_0081', 'SAVINGS', 'CNY', 60125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0082', 'CUST_0082', 'SAVINGS', 'CNY', 60250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0083', 'CUST_0083', 'SAVINGS', 'CNY', 60375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0084', 'CUST_0084', 'SAVINGS', 'CNY', 60500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0085', 'CUST_0085', 'SAVINGS', 'CNY', 60625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0086', 'CUST_0086', 'SAVINGS', 'CNY', 60750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0087', 'CUST_0087', 'SAVINGS', 'CNY', 60875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0088', 'CUST_0088', 'SAVINGS', 'CNY', 61000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0089', 'CUST_0089', 'SAVINGS', 'CNY', 61125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0090', 'CUST_0090', 'SAVINGS', 'CNY', 61250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0091', 'CUST_0091', 'SAVINGS', 'CNY', 61375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0092', 'CUST_0092', 'SAVINGS', 'CNY', 61500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0093', 'CUST_0093', 'SAVINGS', 'CNY', 61625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0094', 'CUST_0094', 'SAVINGS', 'CNY', 61750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0095', 'CUST_0095', 'SAVINGS', 'CNY', 61875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0096', 'CUST_0096', 'SAVINGS', 'CNY', 62000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0097', 'CUST_0097', 'SAVINGS', 'CNY', 62125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0098', 'CUST_0098', 'SAVINGS', 'CNY', 62250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0099', 'CUST_0099', 'SAVINGS', 'CNY', 62375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0100', 'CUST_0100', 'SAVINGS', 'CNY', 62500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0101', 'CUST_0101', 'SAVINGS', 'CNY', 62625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0102', 'CUST_0102', 'SAVINGS', 'CNY', 62750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0103', 'CUST_0103', 'SAVINGS', 'CNY', 62875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0104', 'CUST_0104', 'SAVINGS', 'CNY', 63000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0105', 'CUST_0105', 'SAVINGS', 'CNY', 63125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0106', 'CUST_0106', 'SAVINGS', 'CNY', 63250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0107', 'CUST_0107', 'SAVINGS', 'CNY', 63375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0108', 'CUST_0108', 'SAVINGS', 'CNY', 63500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0109', 'CUST_0109', 'SAVINGS', 'CNY', 63625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0110', 'CUST_0110', 'SAVINGS', 'CNY', 63750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0111', 'CUST_0111', 'SAVINGS', 'CNY', 63875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0112', 'CUST_0112', 'SAVINGS', 'CNY', 64000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0113', 'CUST_0113', 'SAVINGS', 'CNY', 64125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0114', 'CUST_0114', 'SAVINGS', 'CNY', 64250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0115', 'CUST_0115', 'SAVINGS', 'CNY', 64375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0116', 'CUST_0116', 'SAVINGS', 'CNY', 64500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0117', 'CUST_0117', 'SAVINGS', 'CNY', 64625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0118', 'CUST_0118', 'SAVINGS', 'CNY', 64750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0119', 'CUST_0119', 'SAVINGS', 'CNY', 64875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0120', 'CUST_0120', 'SAVINGS', 'CNY', 65000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0121', 'CUST_0121', 'SAVINGS', 'CNY', 65125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0122', 'CUST_0122', 'SAVINGS', 'CNY', 65250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0123', 'CUST_0123', 'SAVINGS', 'CNY', 65375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0124', 'CUST_0124', 'SAVINGS', 'CNY', 65500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0125', 'CUST_0125', 'SAVINGS', 'CNY', 65625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0126', 'CUST_0126', 'SAVINGS', 'CNY', 65750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0127', 'CUST_0127', 'SAVINGS', 'CNY', 65875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0128', 'CUST_0128', 'SAVINGS', 'CNY', 66000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0129', 'CUST_0129', 'SAVINGS', 'CNY', 66125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0130', 'CUST_0130', 'SAVINGS', 'CNY', 66250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0131', 'CUST_0131', 'SAVINGS', 'CNY', 66375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0132', 'CUST_0132', 'SAVINGS', 'CNY', 66500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0133', 'CUST_0133', 'SAVINGS', 'CNY', 66625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0134', 'CUST_0134', 'SAVINGS', 'CNY', 66750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0135', 'CUST_0135', 'SAVINGS', 'CNY', 66875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0136', 'CUST_0136', 'SAVINGS', 'CNY', 67000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0137', 'CUST_0137', 'SAVINGS', 'CNY', 67125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0138', 'CUST_0138', 'SAVINGS', 'CNY', 67250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0139', 'CUST_0139', 'SAVINGS', 'CNY', 67375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0140', 'CUST_0140', 'SAVINGS', 'CNY', 67500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0141', 'CUST_0141', 'SAVINGS', 'CNY', 67625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0142', 'CUST_0142', 'SAVINGS', 'CNY', 67750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0143', 'CUST_0143', 'SAVINGS', 'CNY', 67875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0144', 'CUST_0144', 'SAVINGS', 'CNY', 68000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0145', 'CUST_0145', 'SAVINGS', 'CNY', 68125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0146', 'CUST_0146', 'SAVINGS', 'CNY', 68250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0147', 'CUST_0147', 'SAVINGS', 'CNY', 68375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0148', 'CUST_0148', 'SAVINGS', 'CNY', 68500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0149', 'CUST_0149', 'SAVINGS', 'CNY', 68625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0150', 'CUST_0150', 'SAVINGS', 'CNY', 68750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0151', 'CUST_0151', 'SAVINGS', 'CNY', 68875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0152', 'CUST_0152', 'SAVINGS', 'CNY', 69000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0153', 'CUST_0153', 'SAVINGS', 'CNY', 69125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0154', 'CUST_0154', 'SAVINGS', 'CNY', 69250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0155', 'CUST_0155', 'SAVINGS', 'CNY', 69375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0156', 'CUST_0156', 'SAVINGS', 'CNY', 69500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0157', 'CUST_0157', 'SAVINGS', 'CNY', 69625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0158', 'CUST_0158', 'SAVINGS', 'CNY', 69750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0159', 'CUST_0159', 'SAVINGS', 'CNY', 69875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0160', 'CUST_0160', 'SAVINGS', 'CNY', 70000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0161', 'CUST_0161', 'SAVINGS', 'CNY', 70125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0162', 'CUST_0162', 'SAVINGS', 'CNY', 70250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0163', 'CUST_0163', 'SAVINGS', 'CNY', 70375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0164', 'CUST_0164', 'SAVINGS', 'CNY', 70500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0165', 'CUST_0165', 'SAVINGS', 'CNY', 70625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0166', 'CUST_0166', 'SAVINGS', 'CNY', 70750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0167', 'CUST_0167', 'SAVINGS', 'CNY', 70875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0168', 'CUST_0168', 'SAVINGS', 'CNY', 71000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0169', 'CUST_0169', 'SAVINGS', 'CNY', 71125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0170', 'CUST_0170', 'SAVINGS', 'CNY', 71250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0171', 'CUST_0171', 'SAVINGS', 'CNY', 71375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0172', 'CUST_0172', 'SAVINGS', 'CNY', 71500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0173', 'CUST_0173', 'SAVINGS', 'CNY', 71625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0174', 'CUST_0174', 'SAVINGS', 'CNY', 71750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0175', 'CUST_0175', 'SAVINGS', 'CNY', 71875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0176', 'CUST_0176', 'SAVINGS', 'CNY', 72000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0177', 'CUST_0177', 'SAVINGS', 'CNY', 72125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0178', 'CUST_0178', 'SAVINGS', 'CNY', 72250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0179', 'CUST_0179', 'SAVINGS', 'CNY', 72375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0180', 'CUST_0180', 'SAVINGS', 'CNY', 72500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0181', 'CUST_0181', 'SAVINGS', 'CNY', 72625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0182', 'CUST_0182', 'SAVINGS', 'CNY', 72750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0183', 'CUST_0183', 'SAVINGS', 'CNY', 72875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0184', 'CUST_0184', 'SAVINGS', 'CNY', 73000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0185', 'CUST_0185', 'SAVINGS', 'CNY', 73125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0186', 'CUST_0186', 'SAVINGS', 'CNY', 73250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0187', 'CUST_0187', 'SAVINGS', 'CNY', 73375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0188', 'CUST_0188', 'SAVINGS', 'CNY', 73500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0189', 'CUST_0189', 'SAVINGS', 'CNY', 73625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0190', 'CUST_0190', 'SAVINGS', 'CNY', 73750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0191', 'CUST_0191', 'SAVINGS', 'CNY', 73875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0192', 'CUST_0192', 'SAVINGS', 'CNY', 74000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0193', 'CUST_0193', 'SAVINGS', 'CNY', 74125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0194', 'CUST_0194', 'SAVINGS', 'CNY', 74250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0195', 'CUST_0195', 'SAVINGS', 'CNY', 74375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0196', 'CUST_0196', 'SAVINGS', 'CNY', 74500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0197', 'CUST_0197', 'SAVINGS', 'CNY', 74625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0198', 'CUST_0198', 'SAVINGS', 'CNY', 74750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0199', 'CUST_0199', 'SAVINGS', 'CNY', 74875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0200', 'CUST_0200', 'SAVINGS', 'CNY', 75000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0201', 'CUST_0201', 'SAVINGS', 'CNY', 75125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0202', 'CUST_0202', 'SAVINGS', 'CNY', 75250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0203', 'CUST_0203', 'SAVINGS', 'CNY', 75375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0204', 'CUST_0204', 'SAVINGS', 'CNY', 75500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0205', 'CUST_0205', 'SAVINGS', 'CNY', 75625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0206', 'CUST_0206', 'SAVINGS', 'CNY', 75750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0207', 'CUST_0207', 'SAVINGS', 'CNY', 75875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0208', 'CUST_0208', 'SAVINGS', 'CNY', 76000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0209', 'CUST_0209', 'SAVINGS', 'CNY', 76125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0210', 'CUST_0210', 'SAVINGS', 'CNY', 76250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0211', 'CUST_0211', 'SAVINGS', 'CNY', 76375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0212', 'CUST_0212', 'SAVINGS', 'CNY', 76500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0213', 'CUST_0213', 'SAVINGS', 'CNY', 76625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0214', 'CUST_0214', 'SAVINGS', 'CNY', 76750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0215', 'CUST_0215', 'SAVINGS', 'CNY', 76875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0216', 'CUST_0216', 'SAVINGS', 'CNY', 77000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0217', 'CUST_0217', 'SAVINGS', 'CNY', 77125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0218', 'CUST_0218', 'SAVINGS', 'CNY', 77250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0219', 'CUST_0219', 'SAVINGS', 'CNY', 77375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0220', 'CUST_0220', 'SAVINGS', 'CNY', 77500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0221', 'CUST_0221', 'SAVINGS', 'CNY', 77625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0222', 'CUST_0222', 'SAVINGS', 'CNY', 77750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0223', 'CUST_0223', 'SAVINGS', 'CNY', 77875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0224', 'CUST_0224', 'SAVINGS', 'CNY', 78000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0225', 'CUST_0225', 'SAVINGS', 'CNY', 78125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0226', 'CUST_0226', 'SAVINGS', 'CNY', 78250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0227', 'CUST_0227', 'SAVINGS', 'CNY', 78375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0228', 'CUST_0228', 'SAVINGS', 'CNY', 78500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0229', 'CUST_0229', 'SAVINGS', 'CNY', 78625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0230', 'CUST_0230', 'SAVINGS', 'CNY', 78750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0231', 'CUST_0231', 'SAVINGS', 'CNY', 78875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0232', 'CUST_0232', 'SAVINGS', 'CNY', 79000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0233', 'CUST_0233', 'SAVINGS', 'CNY', 79125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0234', 'CUST_0234', 'SAVINGS', 'CNY', 79250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0235', 'CUST_0235', 'SAVINGS', 'CNY', 79375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0236', 'CUST_0236', 'SAVINGS', 'CNY', 79500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0237', 'CUST_0237', 'SAVINGS', 'CNY', 79625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0238', 'CUST_0238', 'SAVINGS', 'CNY', 79750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0239', 'CUST_0239', 'SAVINGS', 'CNY', 79875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0240', 'CUST_0240', 'SAVINGS', 'CNY', 80000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0241', 'CUST_0241', 'SAVINGS', 'CNY', 80125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0242', 'CUST_0242', 'SAVINGS', 'CNY', 80250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0243', 'CUST_0243', 'SAVINGS', 'CNY', 80375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0244', 'CUST_0244', 'SAVINGS', 'CNY', 80500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0245', 'CUST_0245', 'SAVINGS', 'CNY', 80625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0246', 'CUST_0246', 'SAVINGS', 'CNY', 80750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0247', 'CUST_0247', 'SAVINGS', 'CNY', 80875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0248', 'CUST_0248', 'SAVINGS', 'CNY', 81000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0249', 'CUST_0249', 'SAVINGS', 'CNY', 81125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0250', 'CUST_0250', 'SAVINGS', 'CNY', 81250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0251', 'CUST_0251', 'SAVINGS', 'CNY', 81375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0252', 'CUST_0252', 'SAVINGS', 'CNY', 81500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0253', 'CUST_0253', 'SAVINGS', 'CNY', 81625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0254', 'CUST_0254', 'SAVINGS', 'CNY', 81750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0255', 'CUST_0255', 'SAVINGS', 'CNY', 81875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0256', 'CUST_0256', 'SAVINGS', 'CNY', 82000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0257', 'CUST_0257', 'SAVINGS', 'CNY', 82125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0258', 'CUST_0258', 'SAVINGS', 'CNY', 82250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0259', 'CUST_0259', 'SAVINGS', 'CNY', 82375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0260', 'CUST_0260', 'SAVINGS', 'CNY', 82500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0261', 'CUST_0261', 'SAVINGS', 'CNY', 82625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0262', 'CUST_0262', 'SAVINGS', 'CNY', 82750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0263', 'CUST_0263', 'SAVINGS', 'CNY', 82875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0264', 'CUST_0264', 'SAVINGS', 'CNY', 83000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0265', 'CUST_0265', 'SAVINGS', 'CNY', 83125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0266', 'CUST_0266', 'SAVINGS', 'CNY', 83250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0267', 'CUST_0267', 'SAVINGS', 'CNY', 83375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0268', 'CUST_0268', 'SAVINGS', 'CNY', 83500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0269', 'CUST_0269', 'SAVINGS', 'CNY', 83625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0270', 'CUST_0270', 'SAVINGS', 'CNY', 83750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0271', 'CUST_0271', 'SAVINGS', 'CNY', 83875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0272', 'CUST_0272', 'SAVINGS', 'CNY', 84000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0273', 'CUST_0273', 'SAVINGS', 'CNY', 84125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0274', 'CUST_0274', 'SAVINGS', 'CNY', 84250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0275', 'CUST_0275', 'SAVINGS', 'CNY', 84375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0276', 'CUST_0276', 'SAVINGS', 'CNY', 84500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0277', 'CUST_0277', 'SAVINGS', 'CNY', 84625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0278', 'CUST_0278', 'SAVINGS', 'CNY', 84750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0279', 'CUST_0279', 'SAVINGS', 'CNY', 84875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0280', 'CUST_0280', 'SAVINGS', 'CNY', 85000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0281', 'CUST_0281', 'SAVINGS', 'CNY', 85125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0282', 'CUST_0282', 'SAVINGS', 'CNY', 85250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0283', 'CUST_0283', 'SAVINGS', 'CNY', 85375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0284', 'CUST_0284', 'SAVINGS', 'CNY', 85500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0285', 'CUST_0285', 'SAVINGS', 'CNY', 85625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0286', 'CUST_0286', 'SAVINGS', 'CNY', 85750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0287', 'CUST_0287', 'SAVINGS', 'CNY', 85875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0288', 'CUST_0288', 'SAVINGS', 'CNY', 86000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0289', 'CUST_0289', 'SAVINGS', 'CNY', 86125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0290', 'CUST_0290', 'SAVINGS', 'CNY', 86250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0291', 'CUST_0291', 'SAVINGS', 'CNY', 86375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0292', 'CUST_0292', 'SAVINGS', 'CNY', 86500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0293', 'CUST_0293', 'SAVINGS', 'CNY', 86625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0294', 'CUST_0294', 'SAVINGS', 'CNY', 86750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0295', 'CUST_0295', 'SAVINGS', 'CNY', 86875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0296', 'CUST_0296', 'SAVINGS', 'CNY', 87000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0297', 'CUST_0297', 'SAVINGS', 'CNY', 87125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0298', 'CUST_0298', 'SAVINGS', 'CNY', 87250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0299', 'CUST_0299', 'SAVINGS', 'CNY', 87375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0300', 'CUST_0300', 'SAVINGS', 'CNY', 87500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0301', 'CUST_0301', 'SAVINGS', 'CNY', 87625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0302', 'CUST_0302', 'SAVINGS', 'CNY', 87750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0303', 'CUST_0303', 'SAVINGS', 'CNY', 87875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0304', 'CUST_0304', 'SAVINGS', 'CNY', 88000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0305', 'CUST_0305', 'SAVINGS', 'CNY', 88125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0306', 'CUST_0306', 'SAVINGS', 'CNY', 88250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0307', 'CUST_0307', 'SAVINGS', 'CNY', 88375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0308', 'CUST_0308', 'SAVINGS', 'CNY', 88500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0309', 'CUST_0309', 'SAVINGS', 'CNY', 88625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0310', 'CUST_0310', 'SAVINGS', 'CNY', 88750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0311', 'CUST_0311', 'SAVINGS', 'CNY', 88875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0312', 'CUST_0312', 'SAVINGS', 'CNY', 89000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0313', 'CUST_0313', 'SAVINGS', 'CNY', 89125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0314', 'CUST_0314', 'SAVINGS', 'CNY', 89250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0315', 'CUST_0315', 'SAVINGS', 'CNY', 89375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0316', 'CUST_0316', 'SAVINGS', 'CNY', 89500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0317', 'CUST_0317', 'SAVINGS', 'CNY', 89625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0318', 'CUST_0318', 'SAVINGS', 'CNY', 89750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0319', 'CUST_0319', 'SAVINGS', 'CNY', 89875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0320', 'CUST_0320', 'SAVINGS', 'CNY', 90000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0321', 'CUST_0321', 'SAVINGS', 'CNY', 90125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0322', 'CUST_0322', 'SAVINGS', 'CNY', 90250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0323', 'CUST_0323', 'SAVINGS', 'CNY', 90375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0324', 'CUST_0324', 'SAVINGS', 'CNY', 90500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0325', 'CUST_0325', 'SAVINGS', 'CNY', 90625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0326', 'CUST_0326', 'SAVINGS', 'CNY', 90750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0327', 'CUST_0327', 'SAVINGS', 'CNY', 90875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0328', 'CUST_0328', 'SAVINGS', 'CNY', 91000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0329', 'CUST_0329', 'SAVINGS', 'CNY', 91125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0330', 'CUST_0330', 'SAVINGS', 'CNY', 91250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0331', 'CUST_0331', 'SAVINGS', 'CNY', 91375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0332', 'CUST_0332', 'SAVINGS', 'CNY', 91500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0333', 'CUST_0333', 'SAVINGS', 'CNY', 91625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0334', 'CUST_0334', 'SAVINGS', 'CNY', 91750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0335', 'CUST_0335', 'SAVINGS', 'CNY', 91875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0336', 'CUST_0336', 'SAVINGS', 'CNY', 92000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0337', 'CUST_0337', 'SAVINGS', 'CNY', 92125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0338', 'CUST_0338', 'SAVINGS', 'CNY', 92250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0339', 'CUST_0339', 'SAVINGS', 'CNY', 92375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0340', 'CUST_0340', 'SAVINGS', 'CNY', 92500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0341', 'CUST_0341', 'SAVINGS', 'CNY', 92625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0342', 'CUST_0342', 'SAVINGS', 'CNY', 92750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0343', 'CUST_0343', 'SAVINGS', 'CNY', 92875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0344', 'CUST_0344', 'SAVINGS', 'CNY', 93000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0345', 'CUST_0345', 'SAVINGS', 'CNY', 93125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0346', 'CUST_0346', 'SAVINGS', 'CNY', 93250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0347', 'CUST_0347', 'SAVINGS', 'CNY', 93375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0348', 'CUST_0348', 'SAVINGS', 'CNY', 93500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0349', 'CUST_0349', 'SAVINGS', 'CNY', 93625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0350', 'CUST_0350', 'SAVINGS', 'CNY', 93750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0351', 'CUST_0351', 'SAVINGS', 'CNY', 93875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0352', 'CUST_0352', 'SAVINGS', 'CNY', 94000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0353', 'CUST_0353', 'SAVINGS', 'CNY', 94125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0354', 'CUST_0354', 'SAVINGS', 'CNY', 94250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0355', 'CUST_0355', 'SAVINGS', 'CNY', 94375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0356', 'CUST_0356', 'SAVINGS', 'CNY', 94500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0357', 'CUST_0357', 'SAVINGS', 'CNY', 94625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0358', 'CUST_0358', 'SAVINGS', 'CNY', 94750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0359', 'CUST_0359', 'SAVINGS', 'CNY', 94875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0360', 'CUST_0360', 'SAVINGS', 'CNY', 95000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0361', 'CUST_0361', 'SAVINGS', 'CNY', 95125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0362', 'CUST_0362', 'SAVINGS', 'CNY', 95250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0363', 'CUST_0363', 'SAVINGS', 'CNY', 95375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0364', 'CUST_0364', 'SAVINGS', 'CNY', 95500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0365', 'CUST_0365', 'SAVINGS', 'CNY', 95625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0366', 'CUST_0366', 'SAVINGS', 'CNY', 95750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0367', 'CUST_0367', 'SAVINGS', 'CNY', 95875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0368', 'CUST_0368', 'SAVINGS', 'CNY', 96000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0369', 'CUST_0369', 'SAVINGS', 'CNY', 96125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0370', 'CUST_0370', 'SAVINGS', 'CNY', 96250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0371', 'CUST_0371', 'SAVINGS', 'CNY', 96375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0372', 'CUST_0372', 'SAVINGS', 'CNY', 96500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0373', 'CUST_0373', 'SAVINGS', 'CNY', 96625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0374', 'CUST_0374', 'SAVINGS', 'CNY', 96750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0375', 'CUST_0375', 'SAVINGS', 'CNY', 96875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0376', 'CUST_0376', 'SAVINGS', 'CNY', 97000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0377', 'CUST_0377', 'SAVINGS', 'CNY', 97125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0378', 'CUST_0378', 'SAVINGS', 'CNY', 97250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0379', 'CUST_0379', 'SAVINGS', 'CNY', 97375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0380', 'CUST_0380', 'SAVINGS', 'CNY', 97500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0381', 'CUST_0381', 'SAVINGS', 'CNY', 97625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0382', 'CUST_0382', 'SAVINGS', 'CNY', 97750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0383', 'CUST_0383', 'SAVINGS', 'CNY', 97875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0384', 'CUST_0384', 'SAVINGS', 'CNY', 98000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0385', 'CUST_0385', 'SAVINGS', 'CNY', 98125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0386', 'CUST_0386', 'SAVINGS', 'CNY', 98250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0387', 'CUST_0387', 'SAVINGS', 'CNY', 98375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0388', 'CUST_0388', 'SAVINGS', 'CNY', 98500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0389', 'CUST_0389', 'SAVINGS', 'CNY', 98625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0390', 'CUST_0390', 'SAVINGS', 'CNY', 98750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0391', 'CUST_0391', 'SAVINGS', 'CNY', 98875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0392', 'CUST_0392', 'SAVINGS', 'CNY', 99000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0393', 'CUST_0393', 'SAVINGS', 'CNY', 99125.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0394', 'CUST_0394', 'SAVINGS', 'CNY', 99250.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0395', 'CUST_0395', 'SAVINGS', 'CNY', 99375.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0396', 'CUST_0396', 'SAVINGS', 'CNY', 99500.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0397', 'CUST_0397', 'SAVINGS', 'CNY', 99625.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0398', 'CUST_0398', 'SAVINGS', 'CNY', 99750.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0399', 'CUST_0399', 'SAVINGS', 'CNY', 99875.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_0400', 'CUST_0400', 'SAVINGS', 'CNY', 100000.0000, 'ACTIVE', 0.003500);
INSERT INTO cbs_accounts (account_no, customer_id, account_type, currency_code, balance, status, interest_rate) VALUES ('ACC_CLEARING_POOL', 'CUST_0001', 'CLEARING', 'CNY', 10000000.0000, 'ACTIVE', 0.000000);

INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0001', 'ACC_0001', 'ACC_0051', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0002', 'ACC_0002', 'ACC_0052', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0003', 'ACC_0003', 'ACC_0053', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0004', 'ACC_0004', 'ACC_0054', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0005', 'ACC_0005', 'ACC_0055', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0006', 'ACC_0006', 'ACC_0056', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0007', 'ACC_0007', 'ACC_0057', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0008', 'ACC_0008', 'ACC_0058', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0009', 'ACC_0009', 'ACC_0059', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0010', 'ACC_0010', 'ACC_0060', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0011', 'ACC_0011', 'ACC_0061', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0012', 'ACC_0012', 'ACC_0062', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0013', 'ACC_0013', 'ACC_0063', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0014', 'ACC_0014', 'ACC_0064', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0015', 'ACC_0015', 'ACC_0065', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0016', 'ACC_0016', 'ACC_0066', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0017', 'ACC_0017', 'ACC_0067', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0018', 'ACC_0018', 'ACC_0068', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0019', 'ACC_0019', 'ACC_0069', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0020', 'ACC_0020', 'ACC_0070', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0021', 'ACC_0021', 'ACC_0071', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0022', 'ACC_0022', 'ACC_0072', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0023', 'ACC_0023', 'ACC_0073', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0024', 'ACC_0024', 'ACC_0074', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0025', 'ACC_0025', 'ACC_0075', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0026', 'ACC_0026', 'ACC_0076', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0027', 'ACC_0027', 'ACC_0077', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0028', 'ACC_0028', 'ACC_0078', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0029', 'ACC_0029', 'ACC_0079', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0030', 'ACC_0030', 'ACC_0080', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0031', 'ACC_0031', 'ACC_0081', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0032', 'ACC_0032', 'ACC_0082', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0033', 'ACC_0033', 'ACC_0083', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0034', 'ACC_0034', 'ACC_0084', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0035', 'ACC_0035', 'ACC_0085', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0036', 'ACC_0036', 'ACC_0086', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0037', 'ACC_0037', 'ACC_0087', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0038', 'ACC_0038', 'ACC_0088', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0039', 'ACC_0039', 'ACC_0089', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0040', 'ACC_0040', 'ACC_0090', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0041', 'ACC_0041', 'ACC_0091', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0042', 'ACC_0042', 'ACC_0092', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0043', 'ACC_0043', 'ACC_0093', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0044', 'ACC_0044', 'ACC_0094', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0045', 'ACC_0045', 'ACC_0095', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0046', 'ACC_0046', 'ACC_0096', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0047', 'ACC_0047', 'ACC_0097', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0048', 'ACC_0048', 'ACC_0098', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0049', 'ACC_0049', 'ACC_0099', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0050', 'ACC_0050', 'ACC_0100', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0051', 'ACC_0051', 'ACC_0101', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0052', 'ACC_0052', 'ACC_0102', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0053', 'ACC_0053', 'ACC_0103', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0054', 'ACC_0054', 'ACC_0104', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0055', 'ACC_0055', 'ACC_0105', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0056', 'ACC_0056', 'ACC_0106', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0057', 'ACC_0057', 'ACC_0107', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0058', 'ACC_0058', 'ACC_0108', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0059', 'ACC_0059', 'ACC_0109', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_standing_orders (order_id, source_account, target_account, amount, next_execution_date, status) VALUES ('SO_0060', 'ACC_0060', 'ACC_0110', 500.0000, TRUNC(SYSDATE), 'ACTIVE');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0001', 'ACC_0001', 'ACC_0101', 1050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0001_D', 'ACC_0001', 'JRN_TX_INIT_0001', 'DEBIT', 1050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0001_C', 'ACC_0101', 'JRN_TX_INIT_0001', 'CREDIT', 1050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0002', 'ACC_0002', 'ACC_0102', 1100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0002_D', 'ACC_0002', 'JRN_TX_INIT_0002', 'DEBIT', 1100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0002_C', 'ACC_0102', 'JRN_TX_INIT_0002', 'CREDIT', 1100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0003', 'ACC_0003', 'ACC_0103', 1150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0003_D', 'ACC_0003', 'JRN_TX_INIT_0003', 'DEBIT', 1150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0003_C', 'ACC_0103', 'JRN_TX_INIT_0003', 'CREDIT', 1150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0004', 'ACC_0004', 'ACC_0104', 1200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0004_D', 'ACC_0004', 'JRN_TX_INIT_0004', 'DEBIT', 1200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0004_C', 'ACC_0104', 'JRN_TX_INIT_0004', 'CREDIT', 1200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0005', 'ACC_0005', 'ACC_0105', 1250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0005_D', 'ACC_0005', 'JRN_TX_INIT_0005', 'DEBIT', 1250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0005_C', 'ACC_0105', 'JRN_TX_INIT_0005', 'CREDIT', 1250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0006', 'ACC_0006', 'ACC_0106', 1300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0006_D', 'ACC_0006', 'JRN_TX_INIT_0006', 'DEBIT', 1300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0006_C', 'ACC_0106', 'JRN_TX_INIT_0006', 'CREDIT', 1300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0007', 'ACC_0007', 'ACC_0107', 1350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0007_D', 'ACC_0007', 'JRN_TX_INIT_0007', 'DEBIT', 1350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0007_C', 'ACC_0107', 'JRN_TX_INIT_0007', 'CREDIT', 1350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0008', 'ACC_0008', 'ACC_0108', 1400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0008_D', 'ACC_0008', 'JRN_TX_INIT_0008', 'DEBIT', 1400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0008_C', 'ACC_0108', 'JRN_TX_INIT_0008', 'CREDIT', 1400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0009', 'ACC_0009', 'ACC_0109', 1450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0009_D', 'ACC_0009', 'JRN_TX_INIT_0009', 'DEBIT', 1450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0009_C', 'ACC_0109', 'JRN_TX_INIT_0009', 'CREDIT', 1450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0010', 'ACC_0010', 'ACC_0110', 1500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0010_D', 'ACC_0010', 'JRN_TX_INIT_0010', 'DEBIT', 1500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0010_C', 'ACC_0110', 'JRN_TX_INIT_0010', 'CREDIT', 1500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0011', 'ACC_0011', 'ACC_0111', 1550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0011_D', 'ACC_0011', 'JRN_TX_INIT_0011', 'DEBIT', 1550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0011_C', 'ACC_0111', 'JRN_TX_INIT_0011', 'CREDIT', 1550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0012', 'ACC_0012', 'ACC_0112', 1600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0012_D', 'ACC_0012', 'JRN_TX_INIT_0012', 'DEBIT', 1600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0012_C', 'ACC_0112', 'JRN_TX_INIT_0012', 'CREDIT', 1600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0013', 'ACC_0013', 'ACC_0113', 1650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0013_D', 'ACC_0013', 'JRN_TX_INIT_0013', 'DEBIT', 1650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0013_C', 'ACC_0113', 'JRN_TX_INIT_0013', 'CREDIT', 1650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0014', 'ACC_0014', 'ACC_0114', 1700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0014_D', 'ACC_0014', 'JRN_TX_INIT_0014', 'DEBIT', 1700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0014_C', 'ACC_0114', 'JRN_TX_INIT_0014', 'CREDIT', 1700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0015', 'ACC_0015', 'ACC_0115', 1750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0015_D', 'ACC_0015', 'JRN_TX_INIT_0015', 'DEBIT', 1750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0015_C', 'ACC_0115', 'JRN_TX_INIT_0015', 'CREDIT', 1750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0016', 'ACC_0016', 'ACC_0116', 1800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0016_D', 'ACC_0016', 'JRN_TX_INIT_0016', 'DEBIT', 1800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0016_C', 'ACC_0116', 'JRN_TX_INIT_0016', 'CREDIT', 1800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0017', 'ACC_0017', 'ACC_0117', 1850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0017_D', 'ACC_0017', 'JRN_TX_INIT_0017', 'DEBIT', 1850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0017_C', 'ACC_0117', 'JRN_TX_INIT_0017', 'CREDIT', 1850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0018', 'ACC_0018', 'ACC_0118', 1900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0018_D', 'ACC_0018', 'JRN_TX_INIT_0018', 'DEBIT', 1900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0018_C', 'ACC_0118', 'JRN_TX_INIT_0018', 'CREDIT', 1900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0019', 'ACC_0019', 'ACC_0119', 1950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0019_D', 'ACC_0019', 'JRN_TX_INIT_0019', 'DEBIT', 1950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0019_C', 'ACC_0119', 'JRN_TX_INIT_0019', 'CREDIT', 1950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0020', 'ACC_0020', 'ACC_0120', 2000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0020_D', 'ACC_0020', 'JRN_TX_INIT_0020', 'DEBIT', 2000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0020_C', 'ACC_0120', 'JRN_TX_INIT_0020', 'CREDIT', 2000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0021', 'ACC_0021', 'ACC_0121', 2050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0021_D', 'ACC_0021', 'JRN_TX_INIT_0021', 'DEBIT', 2050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0021_C', 'ACC_0121', 'JRN_TX_INIT_0021', 'CREDIT', 2050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0022', 'ACC_0022', 'ACC_0122', 2100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0022_D', 'ACC_0022', 'JRN_TX_INIT_0022', 'DEBIT', 2100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0022_C', 'ACC_0122', 'JRN_TX_INIT_0022', 'CREDIT', 2100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0023', 'ACC_0023', 'ACC_0123', 2150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0023_D', 'ACC_0023', 'JRN_TX_INIT_0023', 'DEBIT', 2150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0023_C', 'ACC_0123', 'JRN_TX_INIT_0023', 'CREDIT', 2150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0024', 'ACC_0024', 'ACC_0124', 2200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0024_D', 'ACC_0024', 'JRN_TX_INIT_0024', 'DEBIT', 2200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0024_C', 'ACC_0124', 'JRN_TX_INIT_0024', 'CREDIT', 2200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0025', 'ACC_0025', 'ACC_0125', 2250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0025_D', 'ACC_0025', 'JRN_TX_INIT_0025', 'DEBIT', 2250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0025_C', 'ACC_0125', 'JRN_TX_INIT_0025', 'CREDIT', 2250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0026', 'ACC_0026', 'ACC_0126', 2300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0026_D', 'ACC_0026', 'JRN_TX_INIT_0026', 'DEBIT', 2300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0026_C', 'ACC_0126', 'JRN_TX_INIT_0026', 'CREDIT', 2300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0027', 'ACC_0027', 'ACC_0127', 2350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0027_D', 'ACC_0027', 'JRN_TX_INIT_0027', 'DEBIT', 2350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0027_C', 'ACC_0127', 'JRN_TX_INIT_0027', 'CREDIT', 2350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0028', 'ACC_0028', 'ACC_0128', 2400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0028_D', 'ACC_0028', 'JRN_TX_INIT_0028', 'DEBIT', 2400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0028_C', 'ACC_0128', 'JRN_TX_INIT_0028', 'CREDIT', 2400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0029', 'ACC_0029', 'ACC_0129', 2450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0029_D', 'ACC_0029', 'JRN_TX_INIT_0029', 'DEBIT', 2450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0029_C', 'ACC_0129', 'JRN_TX_INIT_0029', 'CREDIT', 2450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0030', 'ACC_0030', 'ACC_0130', 2500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0030_D', 'ACC_0030', 'JRN_TX_INIT_0030', 'DEBIT', 2500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0030_C', 'ACC_0130', 'JRN_TX_INIT_0030', 'CREDIT', 2500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0031', 'ACC_0031', 'ACC_0131', 2550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0031_D', 'ACC_0031', 'JRN_TX_INIT_0031', 'DEBIT', 2550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0031_C', 'ACC_0131', 'JRN_TX_INIT_0031', 'CREDIT', 2550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0032', 'ACC_0032', 'ACC_0132', 2600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0032_D', 'ACC_0032', 'JRN_TX_INIT_0032', 'DEBIT', 2600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0032_C', 'ACC_0132', 'JRN_TX_INIT_0032', 'CREDIT', 2600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0033', 'ACC_0033', 'ACC_0133', 2650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0033_D', 'ACC_0033', 'JRN_TX_INIT_0033', 'DEBIT', 2650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0033_C', 'ACC_0133', 'JRN_TX_INIT_0033', 'CREDIT', 2650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0034', 'ACC_0034', 'ACC_0134', 2700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0034_D', 'ACC_0034', 'JRN_TX_INIT_0034', 'DEBIT', 2700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0034_C', 'ACC_0134', 'JRN_TX_INIT_0034', 'CREDIT', 2700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0035', 'ACC_0035', 'ACC_0135', 2750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0035_D', 'ACC_0035', 'JRN_TX_INIT_0035', 'DEBIT', 2750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0035_C', 'ACC_0135', 'JRN_TX_INIT_0035', 'CREDIT', 2750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0036', 'ACC_0036', 'ACC_0136', 2800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0036_D', 'ACC_0036', 'JRN_TX_INIT_0036', 'DEBIT', 2800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0036_C', 'ACC_0136', 'JRN_TX_INIT_0036', 'CREDIT', 2800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0037', 'ACC_0037', 'ACC_0137', 2850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0037_D', 'ACC_0037', 'JRN_TX_INIT_0037', 'DEBIT', 2850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0037_C', 'ACC_0137', 'JRN_TX_INIT_0037', 'CREDIT', 2850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0038', 'ACC_0038', 'ACC_0138', 2900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0038_D', 'ACC_0038', 'JRN_TX_INIT_0038', 'DEBIT', 2900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0038_C', 'ACC_0138', 'JRN_TX_INIT_0038', 'CREDIT', 2900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0039', 'ACC_0039', 'ACC_0139', 2950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0039_D', 'ACC_0039', 'JRN_TX_INIT_0039', 'DEBIT', 2950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0039_C', 'ACC_0139', 'JRN_TX_INIT_0039', 'CREDIT', 2950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0040', 'ACC_0040', 'ACC_0140', 3000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0040_D', 'ACC_0040', 'JRN_TX_INIT_0040', 'DEBIT', 3000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0040_C', 'ACC_0140', 'JRN_TX_INIT_0040', 'CREDIT', 3000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0041', 'ACC_0041', 'ACC_0141', 3050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0041_D', 'ACC_0041', 'JRN_TX_INIT_0041', 'DEBIT', 3050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0041_C', 'ACC_0141', 'JRN_TX_INIT_0041', 'CREDIT', 3050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0042', 'ACC_0042', 'ACC_0142', 3100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0042_D', 'ACC_0042', 'JRN_TX_INIT_0042', 'DEBIT', 3100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0042_C', 'ACC_0142', 'JRN_TX_INIT_0042', 'CREDIT', 3100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0043', 'ACC_0043', 'ACC_0143', 3150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0043_D', 'ACC_0043', 'JRN_TX_INIT_0043', 'DEBIT', 3150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0043_C', 'ACC_0143', 'JRN_TX_INIT_0043', 'CREDIT', 3150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0044', 'ACC_0044', 'ACC_0144', 3200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0044_D', 'ACC_0044', 'JRN_TX_INIT_0044', 'DEBIT', 3200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0044_C', 'ACC_0144', 'JRN_TX_INIT_0044', 'CREDIT', 3200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0045', 'ACC_0045', 'ACC_0145', 3250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0045_D', 'ACC_0045', 'JRN_TX_INIT_0045', 'DEBIT', 3250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0045_C', 'ACC_0145', 'JRN_TX_INIT_0045', 'CREDIT', 3250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0046', 'ACC_0046', 'ACC_0146', 3300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0046_D', 'ACC_0046', 'JRN_TX_INIT_0046', 'DEBIT', 3300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0046_C', 'ACC_0146', 'JRN_TX_INIT_0046', 'CREDIT', 3300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0047', 'ACC_0047', 'ACC_0147', 3350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0047_D', 'ACC_0047', 'JRN_TX_INIT_0047', 'DEBIT', 3350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0047_C', 'ACC_0147', 'JRN_TX_INIT_0047', 'CREDIT', 3350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0048', 'ACC_0048', 'ACC_0148', 3400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0048_D', 'ACC_0048', 'JRN_TX_INIT_0048', 'DEBIT', 3400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0048_C', 'ACC_0148', 'JRN_TX_INIT_0048', 'CREDIT', 3400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0049', 'ACC_0049', 'ACC_0149', 3450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0049_D', 'ACC_0049', 'JRN_TX_INIT_0049', 'DEBIT', 3450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0049_C', 'ACC_0149', 'JRN_TX_INIT_0049', 'CREDIT', 3450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0050', 'ACC_0050', 'ACC_0150', 3500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0050_D', 'ACC_0050', 'JRN_TX_INIT_0050', 'DEBIT', 3500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0050_C', 'ACC_0150', 'JRN_TX_INIT_0050', 'CREDIT', 3500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0051', 'ACC_0051', 'ACC_0151', 3550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0051_D', 'ACC_0051', 'JRN_TX_INIT_0051', 'DEBIT', 3550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0051_C', 'ACC_0151', 'JRN_TX_INIT_0051', 'CREDIT', 3550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0052', 'ACC_0052', 'ACC_0152', 3600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0052_D', 'ACC_0052', 'JRN_TX_INIT_0052', 'DEBIT', 3600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0052_C', 'ACC_0152', 'JRN_TX_INIT_0052', 'CREDIT', 3600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0053', 'ACC_0053', 'ACC_0153', 3650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0053_D', 'ACC_0053', 'JRN_TX_INIT_0053', 'DEBIT', 3650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0053_C', 'ACC_0153', 'JRN_TX_INIT_0053', 'CREDIT', 3650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0054', 'ACC_0054', 'ACC_0154', 3700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0054_D', 'ACC_0054', 'JRN_TX_INIT_0054', 'DEBIT', 3700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0054_C', 'ACC_0154', 'JRN_TX_INIT_0054', 'CREDIT', 3700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0055', 'ACC_0055', 'ACC_0155', 3750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0055_D', 'ACC_0055', 'JRN_TX_INIT_0055', 'DEBIT', 3750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0055_C', 'ACC_0155', 'JRN_TX_INIT_0055', 'CREDIT', 3750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0056', 'ACC_0056', 'ACC_0156', 3800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0056_D', 'ACC_0056', 'JRN_TX_INIT_0056', 'DEBIT', 3800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0056_C', 'ACC_0156', 'JRN_TX_INIT_0056', 'CREDIT', 3800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0057', 'ACC_0057', 'ACC_0157', 3850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0057_D', 'ACC_0057', 'JRN_TX_INIT_0057', 'DEBIT', 3850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0057_C', 'ACC_0157', 'JRN_TX_INIT_0057', 'CREDIT', 3850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0058', 'ACC_0058', 'ACC_0158', 3900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0058_D', 'ACC_0058', 'JRN_TX_INIT_0058', 'DEBIT', 3900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0058_C', 'ACC_0158', 'JRN_TX_INIT_0058', 'CREDIT', 3900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0059', 'ACC_0059', 'ACC_0159', 3950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0059_D', 'ACC_0059', 'JRN_TX_INIT_0059', 'DEBIT', 3950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0059_C', 'ACC_0159', 'JRN_TX_INIT_0059', 'CREDIT', 3950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0060', 'ACC_0060', 'ACC_0160', 4000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0060_D', 'ACC_0060', 'JRN_TX_INIT_0060', 'DEBIT', 4000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0060_C', 'ACC_0160', 'JRN_TX_INIT_0060', 'CREDIT', 4000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0061', 'ACC_0061', 'ACC_0161', 4050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0061_D', 'ACC_0061', 'JRN_TX_INIT_0061', 'DEBIT', 4050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0061_C', 'ACC_0161', 'JRN_TX_INIT_0061', 'CREDIT', 4050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0062', 'ACC_0062', 'ACC_0162', 4100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0062_D', 'ACC_0062', 'JRN_TX_INIT_0062', 'DEBIT', 4100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0062_C', 'ACC_0162', 'JRN_TX_INIT_0062', 'CREDIT', 4100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0063', 'ACC_0063', 'ACC_0163', 4150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0063_D', 'ACC_0063', 'JRN_TX_INIT_0063', 'DEBIT', 4150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0063_C', 'ACC_0163', 'JRN_TX_INIT_0063', 'CREDIT', 4150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0064', 'ACC_0064', 'ACC_0164', 4200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0064_D', 'ACC_0064', 'JRN_TX_INIT_0064', 'DEBIT', 4200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0064_C', 'ACC_0164', 'JRN_TX_INIT_0064', 'CREDIT', 4200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0065', 'ACC_0065', 'ACC_0165', 4250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0065_D', 'ACC_0065', 'JRN_TX_INIT_0065', 'DEBIT', 4250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0065_C', 'ACC_0165', 'JRN_TX_INIT_0065', 'CREDIT', 4250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0066', 'ACC_0066', 'ACC_0166', 4300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0066_D', 'ACC_0066', 'JRN_TX_INIT_0066', 'DEBIT', 4300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0066_C', 'ACC_0166', 'JRN_TX_INIT_0066', 'CREDIT', 4300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0067', 'ACC_0067', 'ACC_0167', 4350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0067_D', 'ACC_0067', 'JRN_TX_INIT_0067', 'DEBIT', 4350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0067_C', 'ACC_0167', 'JRN_TX_INIT_0067', 'CREDIT', 4350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0068', 'ACC_0068', 'ACC_0168', 4400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0068_D', 'ACC_0068', 'JRN_TX_INIT_0068', 'DEBIT', 4400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0068_C', 'ACC_0168', 'JRN_TX_INIT_0068', 'CREDIT', 4400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0069', 'ACC_0069', 'ACC_0169', 4450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0069_D', 'ACC_0069', 'JRN_TX_INIT_0069', 'DEBIT', 4450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0069_C', 'ACC_0169', 'JRN_TX_INIT_0069', 'CREDIT', 4450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0070', 'ACC_0070', 'ACC_0170', 4500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0070_D', 'ACC_0070', 'JRN_TX_INIT_0070', 'DEBIT', 4500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0070_C', 'ACC_0170', 'JRN_TX_INIT_0070', 'CREDIT', 4500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0071', 'ACC_0071', 'ACC_0171', 4550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0071_D', 'ACC_0071', 'JRN_TX_INIT_0071', 'DEBIT', 4550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0071_C', 'ACC_0171', 'JRN_TX_INIT_0071', 'CREDIT', 4550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0072', 'ACC_0072', 'ACC_0172', 4600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0072_D', 'ACC_0072', 'JRN_TX_INIT_0072', 'DEBIT', 4600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0072_C', 'ACC_0172', 'JRN_TX_INIT_0072', 'CREDIT', 4600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0073', 'ACC_0073', 'ACC_0173', 4650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0073_D', 'ACC_0073', 'JRN_TX_INIT_0073', 'DEBIT', 4650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0073_C', 'ACC_0173', 'JRN_TX_INIT_0073', 'CREDIT', 4650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0074', 'ACC_0074', 'ACC_0174', 4700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0074_D', 'ACC_0074', 'JRN_TX_INIT_0074', 'DEBIT', 4700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0074_C', 'ACC_0174', 'JRN_TX_INIT_0074', 'CREDIT', 4700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0075', 'ACC_0075', 'ACC_0175', 4750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0075_D', 'ACC_0075', 'JRN_TX_INIT_0075', 'DEBIT', 4750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0075_C', 'ACC_0175', 'JRN_TX_INIT_0075', 'CREDIT', 4750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0076', 'ACC_0076', 'ACC_0176', 4800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0076_D', 'ACC_0076', 'JRN_TX_INIT_0076', 'DEBIT', 4800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0076_C', 'ACC_0176', 'JRN_TX_INIT_0076', 'CREDIT', 4800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0077', 'ACC_0077', 'ACC_0177', 4850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0077_D', 'ACC_0077', 'JRN_TX_INIT_0077', 'DEBIT', 4850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0077_C', 'ACC_0177', 'JRN_TX_INIT_0077', 'CREDIT', 4850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0078', 'ACC_0078', 'ACC_0178', 4900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0078_D', 'ACC_0078', 'JRN_TX_INIT_0078', 'DEBIT', 4900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0078_C', 'ACC_0178', 'JRN_TX_INIT_0078', 'CREDIT', 4900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0079', 'ACC_0079', 'ACC_0179', 4950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0079_D', 'ACC_0079', 'JRN_TX_INIT_0079', 'DEBIT', 4950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0079_C', 'ACC_0179', 'JRN_TX_INIT_0079', 'CREDIT', 4950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0080', 'ACC_0080', 'ACC_0180', 5000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0080_D', 'ACC_0080', 'JRN_TX_INIT_0080', 'DEBIT', 5000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0080_C', 'ACC_0180', 'JRN_TX_INIT_0080', 'CREDIT', 5000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0081', 'ACC_0081', 'ACC_0181', 5050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0081_D', 'ACC_0081', 'JRN_TX_INIT_0081', 'DEBIT', 5050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0081_C', 'ACC_0181', 'JRN_TX_INIT_0081', 'CREDIT', 5050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0082', 'ACC_0082', 'ACC_0182', 5100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0082_D', 'ACC_0082', 'JRN_TX_INIT_0082', 'DEBIT', 5100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0082_C', 'ACC_0182', 'JRN_TX_INIT_0082', 'CREDIT', 5100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0083', 'ACC_0083', 'ACC_0183', 5150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0083_D', 'ACC_0083', 'JRN_TX_INIT_0083', 'DEBIT', 5150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0083_C', 'ACC_0183', 'JRN_TX_INIT_0083', 'CREDIT', 5150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0084', 'ACC_0084', 'ACC_0184', 5200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0084_D', 'ACC_0084', 'JRN_TX_INIT_0084', 'DEBIT', 5200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0084_C', 'ACC_0184', 'JRN_TX_INIT_0084', 'CREDIT', 5200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0085', 'ACC_0085', 'ACC_0185', 5250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0085_D', 'ACC_0085', 'JRN_TX_INIT_0085', 'DEBIT', 5250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0085_C', 'ACC_0185', 'JRN_TX_INIT_0085', 'CREDIT', 5250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0086', 'ACC_0086', 'ACC_0186', 5300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0086_D', 'ACC_0086', 'JRN_TX_INIT_0086', 'DEBIT', 5300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0086_C', 'ACC_0186', 'JRN_TX_INIT_0086', 'CREDIT', 5300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0087', 'ACC_0087', 'ACC_0187', 5350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0087_D', 'ACC_0087', 'JRN_TX_INIT_0087', 'DEBIT', 5350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0087_C', 'ACC_0187', 'JRN_TX_INIT_0087', 'CREDIT', 5350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0088', 'ACC_0088', 'ACC_0188', 5400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0088_D', 'ACC_0088', 'JRN_TX_INIT_0088', 'DEBIT', 5400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0088_C', 'ACC_0188', 'JRN_TX_INIT_0088', 'CREDIT', 5400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0089', 'ACC_0089', 'ACC_0189', 5450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0089_D', 'ACC_0089', 'JRN_TX_INIT_0089', 'DEBIT', 5450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0089_C', 'ACC_0189', 'JRN_TX_INIT_0089', 'CREDIT', 5450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0090', 'ACC_0090', 'ACC_0190', 5500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0090_D', 'ACC_0090', 'JRN_TX_INIT_0090', 'DEBIT', 5500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0090_C', 'ACC_0190', 'JRN_TX_INIT_0090', 'CREDIT', 5500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0091', 'ACC_0091', 'ACC_0191', 5550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0091_D', 'ACC_0091', 'JRN_TX_INIT_0091', 'DEBIT', 5550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0091_C', 'ACC_0191', 'JRN_TX_INIT_0091', 'CREDIT', 5550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0092', 'ACC_0092', 'ACC_0192', 5600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0092_D', 'ACC_0092', 'JRN_TX_INIT_0092', 'DEBIT', 5600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0092_C', 'ACC_0192', 'JRN_TX_INIT_0092', 'CREDIT', 5600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0093', 'ACC_0093', 'ACC_0193', 5650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0093_D', 'ACC_0093', 'JRN_TX_INIT_0093', 'DEBIT', 5650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0093_C', 'ACC_0193', 'JRN_TX_INIT_0093', 'CREDIT', 5650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0094', 'ACC_0094', 'ACC_0194', 5700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0094_D', 'ACC_0094', 'JRN_TX_INIT_0094', 'DEBIT', 5700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0094_C', 'ACC_0194', 'JRN_TX_INIT_0094', 'CREDIT', 5700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0095', 'ACC_0095', 'ACC_0195', 5750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0095_D', 'ACC_0095', 'JRN_TX_INIT_0095', 'DEBIT', 5750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0095_C', 'ACC_0195', 'JRN_TX_INIT_0095', 'CREDIT', 5750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0096', 'ACC_0096', 'ACC_0196', 5800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0096_D', 'ACC_0096', 'JRN_TX_INIT_0096', 'DEBIT', 5800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0096_C', 'ACC_0196', 'JRN_TX_INIT_0096', 'CREDIT', 5800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0097', 'ACC_0097', 'ACC_0197', 5850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0097_D', 'ACC_0097', 'JRN_TX_INIT_0097', 'DEBIT', 5850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0097_C', 'ACC_0197', 'JRN_TX_INIT_0097', 'CREDIT', 5850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0098', 'ACC_0098', 'ACC_0198', 5900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0098_D', 'ACC_0098', 'JRN_TX_INIT_0098', 'DEBIT', 5900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0098_C', 'ACC_0198', 'JRN_TX_INIT_0098', 'CREDIT', 5900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0099', 'ACC_0099', 'ACC_0199', 5950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0099_D', 'ACC_0099', 'JRN_TX_INIT_0099', 'DEBIT', 5950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0099_C', 'ACC_0199', 'JRN_TX_INIT_0099', 'CREDIT', 5950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0100', 'ACC_0100', 'ACC_0200', 6000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0100_D', 'ACC_0100', 'JRN_TX_INIT_0100', 'DEBIT', 6000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0100_C', 'ACC_0200', 'JRN_TX_INIT_0100', 'CREDIT', 6000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0101', 'ACC_0101', 'ACC_0201', 6050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0101_D', 'ACC_0101', 'JRN_TX_INIT_0101', 'DEBIT', 6050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0101_C', 'ACC_0201', 'JRN_TX_INIT_0101', 'CREDIT', 6050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0102', 'ACC_0102', 'ACC_0202', 6100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0102_D', 'ACC_0102', 'JRN_TX_INIT_0102', 'DEBIT', 6100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0102_C', 'ACC_0202', 'JRN_TX_INIT_0102', 'CREDIT', 6100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0103', 'ACC_0103', 'ACC_0203', 6150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0103_D', 'ACC_0103', 'JRN_TX_INIT_0103', 'DEBIT', 6150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0103_C', 'ACC_0203', 'JRN_TX_INIT_0103', 'CREDIT', 6150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0104', 'ACC_0104', 'ACC_0204', 6200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0104_D', 'ACC_0104', 'JRN_TX_INIT_0104', 'DEBIT', 6200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0104_C', 'ACC_0204', 'JRN_TX_INIT_0104', 'CREDIT', 6200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0105', 'ACC_0105', 'ACC_0205', 6250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0105_D', 'ACC_0105', 'JRN_TX_INIT_0105', 'DEBIT', 6250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0105_C', 'ACC_0205', 'JRN_TX_INIT_0105', 'CREDIT', 6250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0106', 'ACC_0106', 'ACC_0206', 6300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0106_D', 'ACC_0106', 'JRN_TX_INIT_0106', 'DEBIT', 6300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0106_C', 'ACC_0206', 'JRN_TX_INIT_0106', 'CREDIT', 6300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0107', 'ACC_0107', 'ACC_0207', 6350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0107_D', 'ACC_0107', 'JRN_TX_INIT_0107', 'DEBIT', 6350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0107_C', 'ACC_0207', 'JRN_TX_INIT_0107', 'CREDIT', 6350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0108', 'ACC_0108', 'ACC_0208', 6400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0108_D', 'ACC_0108', 'JRN_TX_INIT_0108', 'DEBIT', 6400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0108_C', 'ACC_0208', 'JRN_TX_INIT_0108', 'CREDIT', 6400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0109', 'ACC_0109', 'ACC_0209', 6450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0109_D', 'ACC_0109', 'JRN_TX_INIT_0109', 'DEBIT', 6450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0109_C', 'ACC_0209', 'JRN_TX_INIT_0109', 'CREDIT', 6450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0110', 'ACC_0110', 'ACC_0210', 6500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0110_D', 'ACC_0110', 'JRN_TX_INIT_0110', 'DEBIT', 6500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0110_C', 'ACC_0210', 'JRN_TX_INIT_0110', 'CREDIT', 6500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0111', 'ACC_0111', 'ACC_0211', 6550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0111_D', 'ACC_0111', 'JRN_TX_INIT_0111', 'DEBIT', 6550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0111_C', 'ACC_0211', 'JRN_TX_INIT_0111', 'CREDIT', 6550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0112', 'ACC_0112', 'ACC_0212', 6600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0112_D', 'ACC_0112', 'JRN_TX_INIT_0112', 'DEBIT', 6600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0112_C', 'ACC_0212', 'JRN_TX_INIT_0112', 'CREDIT', 6600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0113', 'ACC_0113', 'ACC_0213', 6650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0113_D', 'ACC_0113', 'JRN_TX_INIT_0113', 'DEBIT', 6650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0113_C', 'ACC_0213', 'JRN_TX_INIT_0113', 'CREDIT', 6650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0114', 'ACC_0114', 'ACC_0214', 6700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0114_D', 'ACC_0114', 'JRN_TX_INIT_0114', 'DEBIT', 6700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0114_C', 'ACC_0214', 'JRN_TX_INIT_0114', 'CREDIT', 6700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0115', 'ACC_0115', 'ACC_0215', 6750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0115_D', 'ACC_0115', 'JRN_TX_INIT_0115', 'DEBIT', 6750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0115_C', 'ACC_0215', 'JRN_TX_INIT_0115', 'CREDIT', 6750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0116', 'ACC_0116', 'ACC_0216', 6800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0116_D', 'ACC_0116', 'JRN_TX_INIT_0116', 'DEBIT', 6800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0116_C', 'ACC_0216', 'JRN_TX_INIT_0116', 'CREDIT', 6800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0117', 'ACC_0117', 'ACC_0217', 6850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0117_D', 'ACC_0117', 'JRN_TX_INIT_0117', 'DEBIT', 6850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0117_C', 'ACC_0217', 'JRN_TX_INIT_0117', 'CREDIT', 6850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0118', 'ACC_0118', 'ACC_0218', 6900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0118_D', 'ACC_0118', 'JRN_TX_INIT_0118', 'DEBIT', 6900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0118_C', 'ACC_0218', 'JRN_TX_INIT_0118', 'CREDIT', 6900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0119', 'ACC_0119', 'ACC_0219', 6950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0119_D', 'ACC_0119', 'JRN_TX_INIT_0119', 'DEBIT', 6950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0119_C', 'ACC_0219', 'JRN_TX_INIT_0119', 'CREDIT', 6950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0120', 'ACC_0120', 'ACC_0220', 7000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0120_D', 'ACC_0120', 'JRN_TX_INIT_0120', 'DEBIT', 7000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0120_C', 'ACC_0220', 'JRN_TX_INIT_0120', 'CREDIT', 7000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0121', 'ACC_0121', 'ACC_0221', 7050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0121_D', 'ACC_0121', 'JRN_TX_INIT_0121', 'DEBIT', 7050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0121_C', 'ACC_0221', 'JRN_TX_INIT_0121', 'CREDIT', 7050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0122', 'ACC_0122', 'ACC_0222', 7100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0122_D', 'ACC_0122', 'JRN_TX_INIT_0122', 'DEBIT', 7100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0122_C', 'ACC_0222', 'JRN_TX_INIT_0122', 'CREDIT', 7100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0123', 'ACC_0123', 'ACC_0223', 7150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0123_D', 'ACC_0123', 'JRN_TX_INIT_0123', 'DEBIT', 7150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0123_C', 'ACC_0223', 'JRN_TX_INIT_0123', 'CREDIT', 7150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0124', 'ACC_0124', 'ACC_0224', 7200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0124_D', 'ACC_0124', 'JRN_TX_INIT_0124', 'DEBIT', 7200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0124_C', 'ACC_0224', 'JRN_TX_INIT_0124', 'CREDIT', 7200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0125', 'ACC_0125', 'ACC_0225', 7250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0125_D', 'ACC_0125', 'JRN_TX_INIT_0125', 'DEBIT', 7250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0125_C', 'ACC_0225', 'JRN_TX_INIT_0125', 'CREDIT', 7250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0126', 'ACC_0126', 'ACC_0226', 7300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0126_D', 'ACC_0126', 'JRN_TX_INIT_0126', 'DEBIT', 7300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0126_C', 'ACC_0226', 'JRN_TX_INIT_0126', 'CREDIT', 7300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0127', 'ACC_0127', 'ACC_0227', 7350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0127_D', 'ACC_0127', 'JRN_TX_INIT_0127', 'DEBIT', 7350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0127_C', 'ACC_0227', 'JRN_TX_INIT_0127', 'CREDIT', 7350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0128', 'ACC_0128', 'ACC_0228', 7400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0128_D', 'ACC_0128', 'JRN_TX_INIT_0128', 'DEBIT', 7400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0128_C', 'ACC_0228', 'JRN_TX_INIT_0128', 'CREDIT', 7400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0129', 'ACC_0129', 'ACC_0229', 7450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0129_D', 'ACC_0129', 'JRN_TX_INIT_0129', 'DEBIT', 7450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0129_C', 'ACC_0229', 'JRN_TX_INIT_0129', 'CREDIT', 7450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0130', 'ACC_0130', 'ACC_0230', 7500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0130_D', 'ACC_0130', 'JRN_TX_INIT_0130', 'DEBIT', 7500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0130_C', 'ACC_0230', 'JRN_TX_INIT_0130', 'CREDIT', 7500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0131', 'ACC_0131', 'ACC_0231', 7550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0131_D', 'ACC_0131', 'JRN_TX_INIT_0131', 'DEBIT', 7550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0131_C', 'ACC_0231', 'JRN_TX_INIT_0131', 'CREDIT', 7550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0132', 'ACC_0132', 'ACC_0232', 7600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0132_D', 'ACC_0132', 'JRN_TX_INIT_0132', 'DEBIT', 7600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0132_C', 'ACC_0232', 'JRN_TX_INIT_0132', 'CREDIT', 7600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0133', 'ACC_0133', 'ACC_0233', 7650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0133_D', 'ACC_0133', 'JRN_TX_INIT_0133', 'DEBIT', 7650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0133_C', 'ACC_0233', 'JRN_TX_INIT_0133', 'CREDIT', 7650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0134', 'ACC_0134', 'ACC_0234', 7700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0134_D', 'ACC_0134', 'JRN_TX_INIT_0134', 'DEBIT', 7700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0134_C', 'ACC_0234', 'JRN_TX_INIT_0134', 'CREDIT', 7700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0135', 'ACC_0135', 'ACC_0235', 7750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0135_D', 'ACC_0135', 'JRN_TX_INIT_0135', 'DEBIT', 7750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0135_C', 'ACC_0235', 'JRN_TX_INIT_0135', 'CREDIT', 7750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0136', 'ACC_0136', 'ACC_0236', 7800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0136_D', 'ACC_0136', 'JRN_TX_INIT_0136', 'DEBIT', 7800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0136_C', 'ACC_0236', 'JRN_TX_INIT_0136', 'CREDIT', 7800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0137', 'ACC_0137', 'ACC_0237', 7850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0137_D', 'ACC_0137', 'JRN_TX_INIT_0137', 'DEBIT', 7850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0137_C', 'ACC_0237', 'JRN_TX_INIT_0137', 'CREDIT', 7850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0138', 'ACC_0138', 'ACC_0238', 7900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0138_D', 'ACC_0138', 'JRN_TX_INIT_0138', 'DEBIT', 7900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0138_C', 'ACC_0238', 'JRN_TX_INIT_0138', 'CREDIT', 7900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0139', 'ACC_0139', 'ACC_0239', 7950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0139_D', 'ACC_0139', 'JRN_TX_INIT_0139', 'DEBIT', 7950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0139_C', 'ACC_0239', 'JRN_TX_INIT_0139', 'CREDIT', 7950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0140', 'ACC_0140', 'ACC_0240', 8000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0140_D', 'ACC_0140', 'JRN_TX_INIT_0140', 'DEBIT', 8000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0140_C', 'ACC_0240', 'JRN_TX_INIT_0140', 'CREDIT', 8000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0141', 'ACC_0141', 'ACC_0241', 8050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0141_D', 'ACC_0141', 'JRN_TX_INIT_0141', 'DEBIT', 8050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0141_C', 'ACC_0241', 'JRN_TX_INIT_0141', 'CREDIT', 8050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0142', 'ACC_0142', 'ACC_0242', 8100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0142_D', 'ACC_0142', 'JRN_TX_INIT_0142', 'DEBIT', 8100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0142_C', 'ACC_0242', 'JRN_TX_INIT_0142', 'CREDIT', 8100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0143', 'ACC_0143', 'ACC_0243', 8150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0143_D', 'ACC_0143', 'JRN_TX_INIT_0143', 'DEBIT', 8150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0143_C', 'ACC_0243', 'JRN_TX_INIT_0143', 'CREDIT', 8150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0144', 'ACC_0144', 'ACC_0244', 8200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0144_D', 'ACC_0144', 'JRN_TX_INIT_0144', 'DEBIT', 8200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0144_C', 'ACC_0244', 'JRN_TX_INIT_0144', 'CREDIT', 8200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0145', 'ACC_0145', 'ACC_0245', 8250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0145_D', 'ACC_0145', 'JRN_TX_INIT_0145', 'DEBIT', 8250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0145_C', 'ACC_0245', 'JRN_TX_INIT_0145', 'CREDIT', 8250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0146', 'ACC_0146', 'ACC_0246', 8300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0146_D', 'ACC_0146', 'JRN_TX_INIT_0146', 'DEBIT', 8300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0146_C', 'ACC_0246', 'JRN_TX_INIT_0146', 'CREDIT', 8300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0147', 'ACC_0147', 'ACC_0247', 8350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0147_D', 'ACC_0147', 'JRN_TX_INIT_0147', 'DEBIT', 8350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0147_C', 'ACC_0247', 'JRN_TX_INIT_0147', 'CREDIT', 8350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0148', 'ACC_0148', 'ACC_0248', 8400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0148_D', 'ACC_0148', 'JRN_TX_INIT_0148', 'DEBIT', 8400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0148_C', 'ACC_0248', 'JRN_TX_INIT_0148', 'CREDIT', 8400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0149', 'ACC_0149', 'ACC_0249', 8450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0149_D', 'ACC_0149', 'JRN_TX_INIT_0149', 'DEBIT', 8450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0149_C', 'ACC_0249', 'JRN_TX_INIT_0149', 'CREDIT', 8450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0150', 'ACC_0150', 'ACC_0250', 8500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0150_D', 'ACC_0150', 'JRN_TX_INIT_0150', 'DEBIT', 8500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0150_C', 'ACC_0250', 'JRN_TX_INIT_0150', 'CREDIT', 8500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0151', 'ACC_0151', 'ACC_0251', 8550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0151_D', 'ACC_0151', 'JRN_TX_INIT_0151', 'DEBIT', 8550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0151_C', 'ACC_0251', 'JRN_TX_INIT_0151', 'CREDIT', 8550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0152', 'ACC_0152', 'ACC_0252', 8600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0152_D', 'ACC_0152', 'JRN_TX_INIT_0152', 'DEBIT', 8600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0152_C', 'ACC_0252', 'JRN_TX_INIT_0152', 'CREDIT', 8600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0153', 'ACC_0153', 'ACC_0253', 8650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0153_D', 'ACC_0153', 'JRN_TX_INIT_0153', 'DEBIT', 8650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0153_C', 'ACC_0253', 'JRN_TX_INIT_0153', 'CREDIT', 8650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0154', 'ACC_0154', 'ACC_0254', 8700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0154_D', 'ACC_0154', 'JRN_TX_INIT_0154', 'DEBIT', 8700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0154_C', 'ACC_0254', 'JRN_TX_INIT_0154', 'CREDIT', 8700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0155', 'ACC_0155', 'ACC_0255', 8750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0155_D', 'ACC_0155', 'JRN_TX_INIT_0155', 'DEBIT', 8750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0155_C', 'ACC_0255', 'JRN_TX_INIT_0155', 'CREDIT', 8750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0156', 'ACC_0156', 'ACC_0256', 8800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0156_D', 'ACC_0156', 'JRN_TX_INIT_0156', 'DEBIT', 8800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0156_C', 'ACC_0256', 'JRN_TX_INIT_0156', 'CREDIT', 8800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0157', 'ACC_0157', 'ACC_0257', 8850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0157_D', 'ACC_0157', 'JRN_TX_INIT_0157', 'DEBIT', 8850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0157_C', 'ACC_0257', 'JRN_TX_INIT_0157', 'CREDIT', 8850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0158', 'ACC_0158', 'ACC_0258', 8900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0158_D', 'ACC_0158', 'JRN_TX_INIT_0158', 'DEBIT', 8900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0158_C', 'ACC_0258', 'JRN_TX_INIT_0158', 'CREDIT', 8900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0159', 'ACC_0159', 'ACC_0259', 8950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0159_D', 'ACC_0159', 'JRN_TX_INIT_0159', 'DEBIT', 8950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0159_C', 'ACC_0259', 'JRN_TX_INIT_0159', 'CREDIT', 8950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0160', 'ACC_0160', 'ACC_0260', 9000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0160_D', 'ACC_0160', 'JRN_TX_INIT_0160', 'DEBIT', 9000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0160_C', 'ACC_0260', 'JRN_TX_INIT_0160', 'CREDIT', 9000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0161', 'ACC_0161', 'ACC_0261', 9050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0161_D', 'ACC_0161', 'JRN_TX_INIT_0161', 'DEBIT', 9050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0161_C', 'ACC_0261', 'JRN_TX_INIT_0161', 'CREDIT', 9050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0162', 'ACC_0162', 'ACC_0262', 9100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0162_D', 'ACC_0162', 'JRN_TX_INIT_0162', 'DEBIT', 9100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0162_C', 'ACC_0262', 'JRN_TX_INIT_0162', 'CREDIT', 9100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0163', 'ACC_0163', 'ACC_0263', 9150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0163_D', 'ACC_0163', 'JRN_TX_INIT_0163', 'DEBIT', 9150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0163_C', 'ACC_0263', 'JRN_TX_INIT_0163', 'CREDIT', 9150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0164', 'ACC_0164', 'ACC_0264', 9200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0164_D', 'ACC_0164', 'JRN_TX_INIT_0164', 'DEBIT', 9200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0164_C', 'ACC_0264', 'JRN_TX_INIT_0164', 'CREDIT', 9200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0165', 'ACC_0165', 'ACC_0265', 9250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0165_D', 'ACC_0165', 'JRN_TX_INIT_0165', 'DEBIT', 9250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0165_C', 'ACC_0265', 'JRN_TX_INIT_0165', 'CREDIT', 9250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0166', 'ACC_0166', 'ACC_0266', 9300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0166_D', 'ACC_0166', 'JRN_TX_INIT_0166', 'DEBIT', 9300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0166_C', 'ACC_0266', 'JRN_TX_INIT_0166', 'CREDIT', 9300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0167', 'ACC_0167', 'ACC_0267', 9350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0167_D', 'ACC_0167', 'JRN_TX_INIT_0167', 'DEBIT', 9350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0167_C', 'ACC_0267', 'JRN_TX_INIT_0167', 'CREDIT', 9350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0168', 'ACC_0168', 'ACC_0268', 9400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0168_D', 'ACC_0168', 'JRN_TX_INIT_0168', 'DEBIT', 9400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0168_C', 'ACC_0268', 'JRN_TX_INIT_0168', 'CREDIT', 9400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0169', 'ACC_0169', 'ACC_0269', 9450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0169_D', 'ACC_0169', 'JRN_TX_INIT_0169', 'DEBIT', 9450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0169_C', 'ACC_0269', 'JRN_TX_INIT_0169', 'CREDIT', 9450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0170', 'ACC_0170', 'ACC_0270', 9500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0170_D', 'ACC_0170', 'JRN_TX_INIT_0170', 'DEBIT', 9500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0170_C', 'ACC_0270', 'JRN_TX_INIT_0170', 'CREDIT', 9500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0171', 'ACC_0171', 'ACC_0271', 9550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0171_D', 'ACC_0171', 'JRN_TX_INIT_0171', 'DEBIT', 9550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0171_C', 'ACC_0271', 'JRN_TX_INIT_0171', 'CREDIT', 9550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0172', 'ACC_0172', 'ACC_0272', 9600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0172_D', 'ACC_0172', 'JRN_TX_INIT_0172', 'DEBIT', 9600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0172_C', 'ACC_0272', 'JRN_TX_INIT_0172', 'CREDIT', 9600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0173', 'ACC_0173', 'ACC_0273', 9650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0173_D', 'ACC_0173', 'JRN_TX_INIT_0173', 'DEBIT', 9650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0173_C', 'ACC_0273', 'JRN_TX_INIT_0173', 'CREDIT', 9650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0174', 'ACC_0174', 'ACC_0274', 9700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0174_D', 'ACC_0174', 'JRN_TX_INIT_0174', 'DEBIT', 9700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0174_C', 'ACC_0274', 'JRN_TX_INIT_0174', 'CREDIT', 9700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0175', 'ACC_0175', 'ACC_0275', 9750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0175_D', 'ACC_0175', 'JRN_TX_INIT_0175', 'DEBIT', 9750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0175_C', 'ACC_0275', 'JRN_TX_INIT_0175', 'CREDIT', 9750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0176', 'ACC_0176', 'ACC_0276', 9800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0176_D', 'ACC_0176', 'JRN_TX_INIT_0176', 'DEBIT', 9800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0176_C', 'ACC_0276', 'JRN_TX_INIT_0176', 'CREDIT', 9800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0177', 'ACC_0177', 'ACC_0277', 9850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0177_D', 'ACC_0177', 'JRN_TX_INIT_0177', 'DEBIT', 9850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0177_C', 'ACC_0277', 'JRN_TX_INIT_0177', 'CREDIT', 9850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0178', 'ACC_0178', 'ACC_0278', 9900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0178_D', 'ACC_0178', 'JRN_TX_INIT_0178', 'DEBIT', 9900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0178_C', 'ACC_0278', 'JRN_TX_INIT_0178', 'CREDIT', 9900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0179', 'ACC_0179', 'ACC_0279', 9950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0179_D', 'ACC_0179', 'JRN_TX_INIT_0179', 'DEBIT', 9950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0179_C', 'ACC_0279', 'JRN_TX_INIT_0179', 'CREDIT', 9950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0180', 'ACC_0180', 'ACC_0280', 10000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0180_D', 'ACC_0180', 'JRN_TX_INIT_0180', 'DEBIT', 10000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0180_C', 'ACC_0280', 'JRN_TX_INIT_0180', 'CREDIT', 10000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0181', 'ACC_0181', 'ACC_0281', 10050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0181_D', 'ACC_0181', 'JRN_TX_INIT_0181', 'DEBIT', 10050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0181_C', 'ACC_0281', 'JRN_TX_INIT_0181', 'CREDIT', 10050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0182', 'ACC_0182', 'ACC_0282', 10100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0182_D', 'ACC_0182', 'JRN_TX_INIT_0182', 'DEBIT', 10100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0182_C', 'ACC_0282', 'JRN_TX_INIT_0182', 'CREDIT', 10100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0183', 'ACC_0183', 'ACC_0283', 10150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0183_D', 'ACC_0183', 'JRN_TX_INIT_0183', 'DEBIT', 10150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0183_C', 'ACC_0283', 'JRN_TX_INIT_0183', 'CREDIT', 10150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0184', 'ACC_0184', 'ACC_0284', 10200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0184_D', 'ACC_0184', 'JRN_TX_INIT_0184', 'DEBIT', 10200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0184_C', 'ACC_0284', 'JRN_TX_INIT_0184', 'CREDIT', 10200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0185', 'ACC_0185', 'ACC_0285', 10250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0185_D', 'ACC_0185', 'JRN_TX_INIT_0185', 'DEBIT', 10250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0185_C', 'ACC_0285', 'JRN_TX_INIT_0185', 'CREDIT', 10250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0186', 'ACC_0186', 'ACC_0286', 10300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0186_D', 'ACC_0186', 'JRN_TX_INIT_0186', 'DEBIT', 10300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0186_C', 'ACC_0286', 'JRN_TX_INIT_0186', 'CREDIT', 10300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0187', 'ACC_0187', 'ACC_0287', 10350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0187_D', 'ACC_0187', 'JRN_TX_INIT_0187', 'DEBIT', 10350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0187_C', 'ACC_0287', 'JRN_TX_INIT_0187', 'CREDIT', 10350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0188', 'ACC_0188', 'ACC_0288', 10400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0188_D', 'ACC_0188', 'JRN_TX_INIT_0188', 'DEBIT', 10400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0188_C', 'ACC_0288', 'JRN_TX_INIT_0188', 'CREDIT', 10400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0189', 'ACC_0189', 'ACC_0289', 10450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0189_D', 'ACC_0189', 'JRN_TX_INIT_0189', 'DEBIT', 10450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0189_C', 'ACC_0289', 'JRN_TX_INIT_0189', 'CREDIT', 10450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0190', 'ACC_0190', 'ACC_0290', 10500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0190_D', 'ACC_0190', 'JRN_TX_INIT_0190', 'DEBIT', 10500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0190_C', 'ACC_0290', 'JRN_TX_INIT_0190', 'CREDIT', 10500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0191', 'ACC_0191', 'ACC_0291', 10550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0191_D', 'ACC_0191', 'JRN_TX_INIT_0191', 'DEBIT', 10550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0191_C', 'ACC_0291', 'JRN_TX_INIT_0191', 'CREDIT', 10550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0192', 'ACC_0192', 'ACC_0292', 10600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0192_D', 'ACC_0192', 'JRN_TX_INIT_0192', 'DEBIT', 10600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0192_C', 'ACC_0292', 'JRN_TX_INIT_0192', 'CREDIT', 10600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0193', 'ACC_0193', 'ACC_0293', 10650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0193_D', 'ACC_0193', 'JRN_TX_INIT_0193', 'DEBIT', 10650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0193_C', 'ACC_0293', 'JRN_TX_INIT_0193', 'CREDIT', 10650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0194', 'ACC_0194', 'ACC_0294', 10700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0194_D', 'ACC_0194', 'JRN_TX_INIT_0194', 'DEBIT', 10700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0194_C', 'ACC_0294', 'JRN_TX_INIT_0194', 'CREDIT', 10700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0195', 'ACC_0195', 'ACC_0295', 10750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0195_D', 'ACC_0195', 'JRN_TX_INIT_0195', 'DEBIT', 10750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0195_C', 'ACC_0295', 'JRN_TX_INIT_0195', 'CREDIT', 10750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0196', 'ACC_0196', 'ACC_0296', 10800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0196_D', 'ACC_0196', 'JRN_TX_INIT_0196', 'DEBIT', 10800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0196_C', 'ACC_0296', 'JRN_TX_INIT_0196', 'CREDIT', 10800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0197', 'ACC_0197', 'ACC_0297', 10850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0197_D', 'ACC_0197', 'JRN_TX_INIT_0197', 'DEBIT', 10850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0197_C', 'ACC_0297', 'JRN_TX_INIT_0197', 'CREDIT', 10850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0198', 'ACC_0198', 'ACC_0298', 10900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0198_D', 'ACC_0198', 'JRN_TX_INIT_0198', 'DEBIT', 10900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0198_C', 'ACC_0298', 'JRN_TX_INIT_0198', 'CREDIT', 10900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0199', 'ACC_0199', 'ACC_0299', 10950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0199_D', 'ACC_0199', 'JRN_TX_INIT_0199', 'DEBIT', 10950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0199_C', 'ACC_0299', 'JRN_TX_INIT_0199', 'CREDIT', 10950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0200', 'ACC_0200', 'ACC_0300', 11000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0200_D', 'ACC_0200', 'JRN_TX_INIT_0200', 'DEBIT', 11000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0200_C', 'ACC_0300', 'JRN_TX_INIT_0200', 'CREDIT', 11000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0201', 'ACC_0201', 'ACC_0301', 11050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0201_D', 'ACC_0201', 'JRN_TX_INIT_0201', 'DEBIT', 11050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0201_C', 'ACC_0301', 'JRN_TX_INIT_0201', 'CREDIT', 11050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0202', 'ACC_0202', 'ACC_0302', 11100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0202_D', 'ACC_0202', 'JRN_TX_INIT_0202', 'DEBIT', 11100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0202_C', 'ACC_0302', 'JRN_TX_INIT_0202', 'CREDIT', 11100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0203', 'ACC_0203', 'ACC_0303', 11150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0203_D', 'ACC_0203', 'JRN_TX_INIT_0203', 'DEBIT', 11150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0203_C', 'ACC_0303', 'JRN_TX_INIT_0203', 'CREDIT', 11150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0204', 'ACC_0204', 'ACC_0304', 11200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0204_D', 'ACC_0204', 'JRN_TX_INIT_0204', 'DEBIT', 11200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0204_C', 'ACC_0304', 'JRN_TX_INIT_0204', 'CREDIT', 11200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0205', 'ACC_0205', 'ACC_0305', 11250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0205_D', 'ACC_0205', 'JRN_TX_INIT_0205', 'DEBIT', 11250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0205_C', 'ACC_0305', 'JRN_TX_INIT_0205', 'CREDIT', 11250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0206', 'ACC_0206', 'ACC_0306', 11300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0206_D', 'ACC_0206', 'JRN_TX_INIT_0206', 'DEBIT', 11300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0206_C', 'ACC_0306', 'JRN_TX_INIT_0206', 'CREDIT', 11300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0207', 'ACC_0207', 'ACC_0307', 11350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0207_D', 'ACC_0207', 'JRN_TX_INIT_0207', 'DEBIT', 11350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0207_C', 'ACC_0307', 'JRN_TX_INIT_0207', 'CREDIT', 11350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0208', 'ACC_0208', 'ACC_0308', 11400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0208_D', 'ACC_0208', 'JRN_TX_INIT_0208', 'DEBIT', 11400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0208_C', 'ACC_0308', 'JRN_TX_INIT_0208', 'CREDIT', 11400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0209', 'ACC_0209', 'ACC_0309', 11450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0209_D', 'ACC_0209', 'JRN_TX_INIT_0209', 'DEBIT', 11450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0209_C', 'ACC_0309', 'JRN_TX_INIT_0209', 'CREDIT', 11450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0210', 'ACC_0210', 'ACC_0310', 11500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0210_D', 'ACC_0210', 'JRN_TX_INIT_0210', 'DEBIT', 11500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0210_C', 'ACC_0310', 'JRN_TX_INIT_0210', 'CREDIT', 11500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0211', 'ACC_0211', 'ACC_0311', 11550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0211_D', 'ACC_0211', 'JRN_TX_INIT_0211', 'DEBIT', 11550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0211_C', 'ACC_0311', 'JRN_TX_INIT_0211', 'CREDIT', 11550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0212', 'ACC_0212', 'ACC_0312', 11600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0212_D', 'ACC_0212', 'JRN_TX_INIT_0212', 'DEBIT', 11600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0212_C', 'ACC_0312', 'JRN_TX_INIT_0212', 'CREDIT', 11600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0213', 'ACC_0213', 'ACC_0313', 11650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0213_D', 'ACC_0213', 'JRN_TX_INIT_0213', 'DEBIT', 11650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0213_C', 'ACC_0313', 'JRN_TX_INIT_0213', 'CREDIT', 11650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0214', 'ACC_0214', 'ACC_0314', 11700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0214_D', 'ACC_0214', 'JRN_TX_INIT_0214', 'DEBIT', 11700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0214_C', 'ACC_0314', 'JRN_TX_INIT_0214', 'CREDIT', 11700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0215', 'ACC_0215', 'ACC_0315', 11750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0215_D', 'ACC_0215', 'JRN_TX_INIT_0215', 'DEBIT', 11750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0215_C', 'ACC_0315', 'JRN_TX_INIT_0215', 'CREDIT', 11750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0216', 'ACC_0216', 'ACC_0316', 11800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0216_D', 'ACC_0216', 'JRN_TX_INIT_0216', 'DEBIT', 11800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0216_C', 'ACC_0316', 'JRN_TX_INIT_0216', 'CREDIT', 11800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0217', 'ACC_0217', 'ACC_0317', 11850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0217_D', 'ACC_0217', 'JRN_TX_INIT_0217', 'DEBIT', 11850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0217_C', 'ACC_0317', 'JRN_TX_INIT_0217', 'CREDIT', 11850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0218', 'ACC_0218', 'ACC_0318', 11900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0218_D', 'ACC_0218', 'JRN_TX_INIT_0218', 'DEBIT', 11900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0218_C', 'ACC_0318', 'JRN_TX_INIT_0218', 'CREDIT', 11900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0219', 'ACC_0219', 'ACC_0319', 11950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0219_D', 'ACC_0219', 'JRN_TX_INIT_0219', 'DEBIT', 11950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0219_C', 'ACC_0319', 'JRN_TX_INIT_0219', 'CREDIT', 11950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0220', 'ACC_0220', 'ACC_0320', 12000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0220_D', 'ACC_0220', 'JRN_TX_INIT_0220', 'DEBIT', 12000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0220_C', 'ACC_0320', 'JRN_TX_INIT_0220', 'CREDIT', 12000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0221', 'ACC_0221', 'ACC_0321', 12050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0221_D', 'ACC_0221', 'JRN_TX_INIT_0221', 'DEBIT', 12050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0221_C', 'ACC_0321', 'JRN_TX_INIT_0221', 'CREDIT', 12050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0222', 'ACC_0222', 'ACC_0322', 12100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0222_D', 'ACC_0222', 'JRN_TX_INIT_0222', 'DEBIT', 12100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0222_C', 'ACC_0322', 'JRN_TX_INIT_0222', 'CREDIT', 12100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0223', 'ACC_0223', 'ACC_0323', 12150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0223_D', 'ACC_0223', 'JRN_TX_INIT_0223', 'DEBIT', 12150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0223_C', 'ACC_0323', 'JRN_TX_INIT_0223', 'CREDIT', 12150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0224', 'ACC_0224', 'ACC_0324', 12200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0224_D', 'ACC_0224', 'JRN_TX_INIT_0224', 'DEBIT', 12200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0224_C', 'ACC_0324', 'JRN_TX_INIT_0224', 'CREDIT', 12200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0225', 'ACC_0225', 'ACC_0325', 12250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0225_D', 'ACC_0225', 'JRN_TX_INIT_0225', 'DEBIT', 12250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0225_C', 'ACC_0325', 'JRN_TX_INIT_0225', 'CREDIT', 12250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0226', 'ACC_0226', 'ACC_0326', 12300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0226_D', 'ACC_0226', 'JRN_TX_INIT_0226', 'DEBIT', 12300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0226_C', 'ACC_0326', 'JRN_TX_INIT_0226', 'CREDIT', 12300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0227', 'ACC_0227', 'ACC_0327', 12350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0227_D', 'ACC_0227', 'JRN_TX_INIT_0227', 'DEBIT', 12350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0227_C', 'ACC_0327', 'JRN_TX_INIT_0227', 'CREDIT', 12350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0228', 'ACC_0228', 'ACC_0328', 12400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0228_D', 'ACC_0228', 'JRN_TX_INIT_0228', 'DEBIT', 12400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0228_C', 'ACC_0328', 'JRN_TX_INIT_0228', 'CREDIT', 12400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0229', 'ACC_0229', 'ACC_0329', 12450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0229_D', 'ACC_0229', 'JRN_TX_INIT_0229', 'DEBIT', 12450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0229_C', 'ACC_0329', 'JRN_TX_INIT_0229', 'CREDIT', 12450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0230', 'ACC_0230', 'ACC_0330', 12500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0230_D', 'ACC_0230', 'JRN_TX_INIT_0230', 'DEBIT', 12500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0230_C', 'ACC_0330', 'JRN_TX_INIT_0230', 'CREDIT', 12500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0231', 'ACC_0231', 'ACC_0331', 12550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0231_D', 'ACC_0231', 'JRN_TX_INIT_0231', 'DEBIT', 12550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0231_C', 'ACC_0331', 'JRN_TX_INIT_0231', 'CREDIT', 12550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0232', 'ACC_0232', 'ACC_0332', 12600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0232_D', 'ACC_0232', 'JRN_TX_INIT_0232', 'DEBIT', 12600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0232_C', 'ACC_0332', 'JRN_TX_INIT_0232', 'CREDIT', 12600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0233', 'ACC_0233', 'ACC_0333', 12650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0233_D', 'ACC_0233', 'JRN_TX_INIT_0233', 'DEBIT', 12650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0233_C', 'ACC_0333', 'JRN_TX_INIT_0233', 'CREDIT', 12650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0234', 'ACC_0234', 'ACC_0334', 12700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0234_D', 'ACC_0234', 'JRN_TX_INIT_0234', 'DEBIT', 12700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0234_C', 'ACC_0334', 'JRN_TX_INIT_0234', 'CREDIT', 12700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0235', 'ACC_0235', 'ACC_0335', 12750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0235_D', 'ACC_0235', 'JRN_TX_INIT_0235', 'DEBIT', 12750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0235_C', 'ACC_0335', 'JRN_TX_INIT_0235', 'CREDIT', 12750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0236', 'ACC_0236', 'ACC_0336', 12800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0236_D', 'ACC_0236', 'JRN_TX_INIT_0236', 'DEBIT', 12800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0236_C', 'ACC_0336', 'JRN_TX_INIT_0236', 'CREDIT', 12800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0237', 'ACC_0237', 'ACC_0337', 12850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0237_D', 'ACC_0237', 'JRN_TX_INIT_0237', 'DEBIT', 12850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0237_C', 'ACC_0337', 'JRN_TX_INIT_0237', 'CREDIT', 12850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0238', 'ACC_0238', 'ACC_0338', 12900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0238_D', 'ACC_0238', 'JRN_TX_INIT_0238', 'DEBIT', 12900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0238_C', 'ACC_0338', 'JRN_TX_INIT_0238', 'CREDIT', 12900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0239', 'ACC_0239', 'ACC_0339', 12950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0239_D', 'ACC_0239', 'JRN_TX_INIT_0239', 'DEBIT', 12950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0239_C', 'ACC_0339', 'JRN_TX_INIT_0239', 'CREDIT', 12950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0240', 'ACC_0240', 'ACC_0340', 13000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0240_D', 'ACC_0240', 'JRN_TX_INIT_0240', 'DEBIT', 13000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0240_C', 'ACC_0340', 'JRN_TX_INIT_0240', 'CREDIT', 13000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0241', 'ACC_0241', 'ACC_0341', 13050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0241_D', 'ACC_0241', 'JRN_TX_INIT_0241', 'DEBIT', 13050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0241_C', 'ACC_0341', 'JRN_TX_INIT_0241', 'CREDIT', 13050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0242', 'ACC_0242', 'ACC_0342', 13100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0242_D', 'ACC_0242', 'JRN_TX_INIT_0242', 'DEBIT', 13100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0242_C', 'ACC_0342', 'JRN_TX_INIT_0242', 'CREDIT', 13100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0243', 'ACC_0243', 'ACC_0343', 13150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0243_D', 'ACC_0243', 'JRN_TX_INIT_0243', 'DEBIT', 13150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0243_C', 'ACC_0343', 'JRN_TX_INIT_0243', 'CREDIT', 13150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0244', 'ACC_0244', 'ACC_0344', 13200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0244_D', 'ACC_0244', 'JRN_TX_INIT_0244', 'DEBIT', 13200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0244_C', 'ACC_0344', 'JRN_TX_INIT_0244', 'CREDIT', 13200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0245', 'ACC_0245', 'ACC_0345', 13250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0245_D', 'ACC_0245', 'JRN_TX_INIT_0245', 'DEBIT', 13250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0245_C', 'ACC_0345', 'JRN_TX_INIT_0245', 'CREDIT', 13250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0246', 'ACC_0246', 'ACC_0346', 13300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0246_D', 'ACC_0246', 'JRN_TX_INIT_0246', 'DEBIT', 13300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0246_C', 'ACC_0346', 'JRN_TX_INIT_0246', 'CREDIT', 13300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0247', 'ACC_0247', 'ACC_0347', 13350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0247_D', 'ACC_0247', 'JRN_TX_INIT_0247', 'DEBIT', 13350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0247_C', 'ACC_0347', 'JRN_TX_INIT_0247', 'CREDIT', 13350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0248', 'ACC_0248', 'ACC_0348', 13400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0248_D', 'ACC_0248', 'JRN_TX_INIT_0248', 'DEBIT', 13400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0248_C', 'ACC_0348', 'JRN_TX_INIT_0248', 'CREDIT', 13400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0249', 'ACC_0249', 'ACC_0349', 13450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0249_D', 'ACC_0249', 'JRN_TX_INIT_0249', 'DEBIT', 13450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0249_C', 'ACC_0349', 'JRN_TX_INIT_0249', 'CREDIT', 13450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0250', 'ACC_0250', 'ACC_0350', 13500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0250_D', 'ACC_0250', 'JRN_TX_INIT_0250', 'DEBIT', 13500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0250_C', 'ACC_0350', 'JRN_TX_INIT_0250', 'CREDIT', 13500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0251', 'ACC_0251', 'ACC_0351', 13550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0251_D', 'ACC_0251', 'JRN_TX_INIT_0251', 'DEBIT', 13550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0251_C', 'ACC_0351', 'JRN_TX_INIT_0251', 'CREDIT', 13550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0252', 'ACC_0252', 'ACC_0352', 13600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0252_D', 'ACC_0252', 'JRN_TX_INIT_0252', 'DEBIT', 13600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0252_C', 'ACC_0352', 'JRN_TX_INIT_0252', 'CREDIT', 13600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0253', 'ACC_0253', 'ACC_0353', 13650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0253_D', 'ACC_0253', 'JRN_TX_INIT_0253', 'DEBIT', 13650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0253_C', 'ACC_0353', 'JRN_TX_INIT_0253', 'CREDIT', 13650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0254', 'ACC_0254', 'ACC_0354', 13700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0254_D', 'ACC_0254', 'JRN_TX_INIT_0254', 'DEBIT', 13700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0254_C', 'ACC_0354', 'JRN_TX_INIT_0254', 'CREDIT', 13700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0255', 'ACC_0255', 'ACC_0355', 13750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0255_D', 'ACC_0255', 'JRN_TX_INIT_0255', 'DEBIT', 13750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0255_C', 'ACC_0355', 'JRN_TX_INIT_0255', 'CREDIT', 13750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0256', 'ACC_0256', 'ACC_0356', 13800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0256_D', 'ACC_0256', 'JRN_TX_INIT_0256', 'DEBIT', 13800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0256_C', 'ACC_0356', 'JRN_TX_INIT_0256', 'CREDIT', 13800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0257', 'ACC_0257', 'ACC_0357', 13850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0257_D', 'ACC_0257', 'JRN_TX_INIT_0257', 'DEBIT', 13850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0257_C', 'ACC_0357', 'JRN_TX_INIT_0257', 'CREDIT', 13850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0258', 'ACC_0258', 'ACC_0358', 13900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0258_D', 'ACC_0258', 'JRN_TX_INIT_0258', 'DEBIT', 13900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0258_C', 'ACC_0358', 'JRN_TX_INIT_0258', 'CREDIT', 13900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0259', 'ACC_0259', 'ACC_0359', 13950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0259_D', 'ACC_0259', 'JRN_TX_INIT_0259', 'DEBIT', 13950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0259_C', 'ACC_0359', 'JRN_TX_INIT_0259', 'CREDIT', 13950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0260', 'ACC_0260', 'ACC_0360', 14000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0260_D', 'ACC_0260', 'JRN_TX_INIT_0260', 'DEBIT', 14000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0260_C', 'ACC_0360', 'JRN_TX_INIT_0260', 'CREDIT', 14000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0261', 'ACC_0261', 'ACC_0361', 14050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0261_D', 'ACC_0261', 'JRN_TX_INIT_0261', 'DEBIT', 14050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0261_C', 'ACC_0361', 'JRN_TX_INIT_0261', 'CREDIT', 14050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0262', 'ACC_0262', 'ACC_0362', 14100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0262_D', 'ACC_0262', 'JRN_TX_INIT_0262', 'DEBIT', 14100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0262_C', 'ACC_0362', 'JRN_TX_INIT_0262', 'CREDIT', 14100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0263', 'ACC_0263', 'ACC_0363', 14150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0263_D', 'ACC_0263', 'JRN_TX_INIT_0263', 'DEBIT', 14150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0263_C', 'ACC_0363', 'JRN_TX_INIT_0263', 'CREDIT', 14150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0264', 'ACC_0264', 'ACC_0364', 14200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0264_D', 'ACC_0264', 'JRN_TX_INIT_0264', 'DEBIT', 14200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0264_C', 'ACC_0364', 'JRN_TX_INIT_0264', 'CREDIT', 14200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0265', 'ACC_0265', 'ACC_0365', 14250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0265_D', 'ACC_0265', 'JRN_TX_INIT_0265', 'DEBIT', 14250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0265_C', 'ACC_0365', 'JRN_TX_INIT_0265', 'CREDIT', 14250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0266', 'ACC_0266', 'ACC_0366', 14300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0266_D', 'ACC_0266', 'JRN_TX_INIT_0266', 'DEBIT', 14300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0266_C', 'ACC_0366', 'JRN_TX_INIT_0266', 'CREDIT', 14300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0267', 'ACC_0267', 'ACC_0367', 14350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0267_D', 'ACC_0267', 'JRN_TX_INIT_0267', 'DEBIT', 14350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0267_C', 'ACC_0367', 'JRN_TX_INIT_0267', 'CREDIT', 14350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0268', 'ACC_0268', 'ACC_0368', 14400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0268_D', 'ACC_0268', 'JRN_TX_INIT_0268', 'DEBIT', 14400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0268_C', 'ACC_0368', 'JRN_TX_INIT_0268', 'CREDIT', 14400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0269', 'ACC_0269', 'ACC_0369', 14450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0269_D', 'ACC_0269', 'JRN_TX_INIT_0269', 'DEBIT', 14450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0269_C', 'ACC_0369', 'JRN_TX_INIT_0269', 'CREDIT', 14450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0270', 'ACC_0270', 'ACC_0370', 14500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0270_D', 'ACC_0270', 'JRN_TX_INIT_0270', 'DEBIT', 14500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0270_C', 'ACC_0370', 'JRN_TX_INIT_0270', 'CREDIT', 14500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0271', 'ACC_0271', 'ACC_0371', 14550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0271_D', 'ACC_0271', 'JRN_TX_INIT_0271', 'DEBIT', 14550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0271_C', 'ACC_0371', 'JRN_TX_INIT_0271', 'CREDIT', 14550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0272', 'ACC_0272', 'ACC_0372', 14600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0272_D', 'ACC_0272', 'JRN_TX_INIT_0272', 'DEBIT', 14600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0272_C', 'ACC_0372', 'JRN_TX_INIT_0272', 'CREDIT', 14600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0273', 'ACC_0273', 'ACC_0373', 14650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0273_D', 'ACC_0273', 'JRN_TX_INIT_0273', 'DEBIT', 14650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0273_C', 'ACC_0373', 'JRN_TX_INIT_0273', 'CREDIT', 14650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0274', 'ACC_0274', 'ACC_0374', 14700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0274_D', 'ACC_0274', 'JRN_TX_INIT_0274', 'DEBIT', 14700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0274_C', 'ACC_0374', 'JRN_TX_INIT_0274', 'CREDIT', 14700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0275', 'ACC_0275', 'ACC_0375', 14750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0275_D', 'ACC_0275', 'JRN_TX_INIT_0275', 'DEBIT', 14750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0275_C', 'ACC_0375', 'JRN_TX_INIT_0275', 'CREDIT', 14750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0276', 'ACC_0276', 'ACC_0376', 14800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0276_D', 'ACC_0276', 'JRN_TX_INIT_0276', 'DEBIT', 14800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0276_C', 'ACC_0376', 'JRN_TX_INIT_0276', 'CREDIT', 14800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0277', 'ACC_0277', 'ACC_0377', 14850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0277_D', 'ACC_0277', 'JRN_TX_INIT_0277', 'DEBIT', 14850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0277_C', 'ACC_0377', 'JRN_TX_INIT_0277', 'CREDIT', 14850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0278', 'ACC_0278', 'ACC_0378', 14900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0278_D', 'ACC_0278', 'JRN_TX_INIT_0278', 'DEBIT', 14900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0278_C', 'ACC_0378', 'JRN_TX_INIT_0278', 'CREDIT', 14900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0279', 'ACC_0279', 'ACC_0379', 14950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0279_D', 'ACC_0279', 'JRN_TX_INIT_0279', 'DEBIT', 14950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0279_C', 'ACC_0379', 'JRN_TX_INIT_0279', 'CREDIT', 14950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0280', 'ACC_0280', 'ACC_0380', 15000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0280_D', 'ACC_0280', 'JRN_TX_INIT_0280', 'DEBIT', 15000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0280_C', 'ACC_0380', 'JRN_TX_INIT_0280', 'CREDIT', 15000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0281', 'ACC_0281', 'ACC_0381', 15050.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0281_D', 'ACC_0281', 'JRN_TX_INIT_0281', 'DEBIT', 15050.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0281_C', 'ACC_0381', 'JRN_TX_INIT_0281', 'CREDIT', 15050.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0282', 'ACC_0282', 'ACC_0382', 15100.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0282_D', 'ACC_0282', 'JRN_TX_INIT_0282', 'DEBIT', 15100.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0282_C', 'ACC_0382', 'JRN_TX_INIT_0282', 'CREDIT', 15100.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0283', 'ACC_0283', 'ACC_0383', 15150.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0283_D', 'ACC_0283', 'JRN_TX_INIT_0283', 'DEBIT', 15150.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0283_C', 'ACC_0383', 'JRN_TX_INIT_0283', 'CREDIT', 15150.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0284', 'ACC_0284', 'ACC_0384', 15200.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0284_D', 'ACC_0284', 'JRN_TX_INIT_0284', 'DEBIT', 15200.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0284_C', 'ACC_0384', 'JRN_TX_INIT_0284', 'CREDIT', 15200.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0285', 'ACC_0285', 'ACC_0385', 15250.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0285_D', 'ACC_0285', 'JRN_TX_INIT_0285', 'DEBIT', 15250.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0285_C', 'ACC_0385', 'JRN_TX_INIT_0285', 'CREDIT', 15250.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0286', 'ACC_0286', 'ACC_0386', 15300.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0286_D', 'ACC_0286', 'JRN_TX_INIT_0286', 'DEBIT', 15300.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0286_C', 'ACC_0386', 'JRN_TX_INIT_0286', 'CREDIT', 15300.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0287', 'ACC_0287', 'ACC_0387', 15350.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0287_D', 'ACC_0287', 'JRN_TX_INIT_0287', 'DEBIT', 15350.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0287_C', 'ACC_0387', 'JRN_TX_INIT_0287', 'CREDIT', 15350.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0288', 'ACC_0288', 'ACC_0388', 15400.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0288_D', 'ACC_0288', 'JRN_TX_INIT_0288', 'DEBIT', 15400.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0288_C', 'ACC_0388', 'JRN_TX_INIT_0288', 'CREDIT', 15400.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0289', 'ACC_0289', 'ACC_0389', 15450.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0289_D', 'ACC_0289', 'JRN_TX_INIT_0289', 'DEBIT', 15450.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0289_C', 'ACC_0389', 'JRN_TX_INIT_0289', 'CREDIT', 15450.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0290', 'ACC_0290', 'ACC_0390', 15500.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0290_D', 'ACC_0290', 'JRN_TX_INIT_0290', 'DEBIT', 15500.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0290_C', 'ACC_0390', 'JRN_TX_INIT_0290', 'CREDIT', 15500.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0291', 'ACC_0291', 'ACC_0391', 15550.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0291_D', 'ACC_0291', 'JRN_TX_INIT_0291', 'DEBIT', 15550.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0291_C', 'ACC_0391', 'JRN_TX_INIT_0291', 'CREDIT', 15550.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0292', 'ACC_0292', 'ACC_0392', 15600.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0292_D', 'ACC_0292', 'JRN_TX_INIT_0292', 'DEBIT', 15600.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0292_C', 'ACC_0392', 'JRN_TX_INIT_0292', 'CREDIT', 15600.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0293', 'ACC_0293', 'ACC_0393', 15650.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0293_D', 'ACC_0293', 'JRN_TX_INIT_0293', 'DEBIT', 15650.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0293_C', 'ACC_0393', 'JRN_TX_INIT_0293', 'CREDIT', 15650.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0294', 'ACC_0294', 'ACC_0394', 15700.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0294_D', 'ACC_0294', 'JRN_TX_INIT_0294', 'DEBIT', 15700.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0294_C', 'ACC_0394', 'JRN_TX_INIT_0294', 'CREDIT', 15700.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0295', 'ACC_0295', 'ACC_0395', 15750.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0295_D', 'ACC_0295', 'JRN_TX_INIT_0295', 'DEBIT', 15750.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0295_C', 'ACC_0395', 'JRN_TX_INIT_0295', 'CREDIT', 15750.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0296', 'ACC_0296', 'ACC_0396', 15800.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0296_D', 'ACC_0296', 'JRN_TX_INIT_0296', 'DEBIT', 15800.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0296_C', 'ACC_0396', 'JRN_TX_INIT_0296', 'CREDIT', 15800.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0297', 'ACC_0297', 'ACC_0397', 15850.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0297_D', 'ACC_0297', 'JRN_TX_INIT_0297', 'DEBIT', 15850.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0297_C', 'ACC_0397', 'JRN_TX_INIT_0297', 'CREDIT', 15850.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0298', 'ACC_0298', 'ACC_0398', 15900.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0298_D', 'ACC_0298', 'JRN_TX_INIT_0298', 'DEBIT', 15900.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0298_C', 'ACC_0398', 'JRN_TX_INIT_0298', 'CREDIT', 15900.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0299', 'ACC_0299', 'ACC_0399', 15950.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0299_D', 'ACC_0299', 'JRN_TX_INIT_0299', 'DEBIT', 15950.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0299_C', 'ACC_0399', 'JRN_TX_INIT_0299', 'CREDIT', 15950.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');
INSERT INTO cbs_settlement_transactions (tx_id, source_account, target_account, amount, currency_code, channel_code, tx_status, settlement_date, completed_at) VALUES ('TX_INIT_0300', 'ACC_0300', 'ACC_0400', 16000.0000, 'CNY', 'ONLINE', 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP);
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0300_D', 'ACC_0300', 'JRN_TX_INIT_0300', 'DEBIT', 16000.0000, 50000.0000, 'CNY', 'Initial Seed Transfer Debit');
INSERT INTO cbs_general_ledger (ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description) VALUES ('GL_TX_INIT_0300_C', 'ACC_0400', 'JRN_TX_INIT_0300', 'CREDIT', 16000.0000, 60000.0000, 'CNY', 'Initial Seed Transfer Credit');

COMMIT;
