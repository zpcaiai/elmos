-- ============================================================================
-- Enterprise Core Banking & Double-Entry Settlement Production Workload
-- Source Dialects: Oracle PL/SQL & SQL Server T-SQL
-- ============================================================================

-- Table: Accounts (Customer deposit & credit accounts)
CREATE TABLE cbs_accounts (
    account_no VARCHAR2(32) NOT NULL,
    customer_id VARCHAR2(32) NOT NULL,
    account_type VARCHAR2(16) NOT NULL,
    currency_code VARCHAR2(3) DEFAULT 'CNY' NOT NULL,
    balance NUMBER(18, 4) DEFAULT 0.0000 NOT NULL,
    frozen_balance NUMBER(18, 4) DEFAULT 0.0000 NOT NULL,
    status VARCHAR2(16) DEFAULT 'ACTIVE' NOT NULL,
    interest_rate NUMBER(8, 6) DEFAULT 0.003500 NOT NULL,
    last_interest_date DATE DEFAULT SYSDATE NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_cbs_accounts PRIMARY KEY (account_no),
    CONSTRAINT chk_cbs_acc_status CHECK (status IN ('ACTIVE', 'FROZEN', 'CLOSED', 'DORMANT')),
    CONSTRAINT chk_cbs_acc_balance CHECK (balance >= 0)
);

-- Table: General Ledger Double-Entry Chart of Accounts
CREATE TABLE cbs_general_ledger (
    ledger_id VARCHAR2(32) NOT NULL,
    account_no VARCHAR2(32) NOT NULL,
    journal_id VARCHAR2(64) NOT NULL,
    entry_type VARCHAR2(6) NOT NULL,
    amount NUMBER(18, 4) NOT NULL,
    running_balance NUMBER(18, 4) NOT NULL,
    currency_code VARCHAR2(3) DEFAULT 'CNY' NOT NULL,
    value_date DATE DEFAULT SYSDATE NOT NULL,
    description VARCHAR2(256),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_cbs_gl PRIMARY KEY (ledger_id),
    CONSTRAINT fk_cbs_gl_account FOREIGN KEY (account_no) REFERENCES cbs_accounts (account_no),
    CONSTRAINT chk_cbs_gl_entry CHECK (entry_type IN ('DEBIT', 'CREDIT')),
    CONSTRAINT chk_cbs_gl_amount CHECK (amount > 0)
);

-- Table: Interbank Settlement Transactions
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
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    CONSTRAINT pk_cbs_tx PRIMARY KEY (tx_id),
    CONSTRAINT fk_cbs_tx_src FOREIGN KEY (source_account) REFERENCES cbs_accounts (account_no),
    CONSTRAINT fk_cbs_tx_tgt FOREIGN KEY (target_account) REFERENCES cbs_accounts (account_no),
    CONSTRAINT chk_cbs_tx_status CHECK (tx_status IN ('PENDING', 'COMMITTED', 'REVERSED', 'FAILED'))
);

-- Table: Audit Trail Log (Immutable event sourcing)
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
    CONSTRAINT pk_cbs_audit PRIMARY KEY (log_id)
);

-- Table: Foreign Exchange Currency Rates
CREATE TABLE cbs_fx_rates (
    base_currency VARCHAR2(3) NOT NULL,
    target_currency VARCHAR2(3) NOT NULL,
    buy_rate NUMBER(14, 6) NOT NULL,
    sell_rate NUMBER(14, 6) NOT NULL,
    middle_rate NUMBER(14, 6) NOT NULL,
    effective_date DATE DEFAULT SYSDATE NOT NULL,
    status VARCHAR2(16) DEFAULT 'ACTIVE' NOT NULL,
    CONSTRAINT pk_cbs_fx PRIMARY KEY (base_currency, target_currency, effective_date)
);

-- Sequence: Journal Transaction Sequence
CREATE SEQUENCE cbs_journal_seq
    START WITH 1000001
    INCREMENT BY 1
    NOCACHE
    NOCYCLE;

-- View: Account Daily Summary
CREATE OR REPLACE VIEW v_cbs_daily_account_summary AS
SELECT 
    a.account_no,
    a.customer_id,
    a.account_type,
    a.currency_code,
    a.balance,
    NVL(SUM(CASE WHEN gl.entry_type = 'CREDIT' THEN gl.amount ELSE 0 END), 0) AS total_credits,
    NVL(SUM(CASE WHEN gl.entry_type = 'DEBIT' THEN gl.amount ELSE 0 END), 0) AS total_debits
FROM cbs_accounts a
LEFT JOIN cbs_general_ledger gl ON a.account_no = gl.account_no AND gl.value_date = TRUNC(SYSDATE)
GROUP BY a.account_no, a.customer_id, a.account_type, a.currency_code, a.balance;

-- View: Double-Entry Conservation Check
CREATE OR REPLACE VIEW v_cbs_ledger_conservation AS
SELECT 
    journal_id,
    SUM(CASE WHEN entry_type = 'DEBIT' THEN amount ELSE 0 END) AS total_debit,
    SUM(CASE WHEN entry_type = 'CREDIT' THEN amount ELSE 0 END) AS total_credit,
    SUM(CASE WHEN entry_type = 'DEBIT' THEN amount ELSE -amount END) AS imbalance
FROM cbs_general_ledger
GROUP BY journal_id;

-- PL/SQL Stored Procedure: Execute Atomic Fund Transfer with Double-Entry Ledger
CREATE OR REPLACE PROCEDURE sp_cbs_transfer_funds (
    p_src_account IN VARCHAR2,
    p_tgt_account IN VARCHAR2,
    p_amount IN NUMBER,
    p_fee IN NUMBER,
    p_channel IN VARCHAR2,
    p_tx_id OUT VARCHAR2,
    p_status OUT VARCHAR2
)
IS
    v_src_balance NUMBER(18, 4);
    v_src_status VARCHAR2(16);
    v_tgt_status VARCHAR2(16);
    v_journal_id VARCHAR2(64);
    v_ledger_id_1 VARCHAR2(32);
    v_ledger_id_2 VARCHAR2(32);
BEGIN
    p_tx_id := 'TX_' || TO_CHAR(SYSDATE, 'YYYYMMDDHH24MISS') || '_' || LPAD(cbs_journal_seq.NEXTVAL, 8, '0');
    v_journal_id := 'JRN_' || p_tx_id;

    -- Validate input amount
    IF p_amount <= 0 THEN
        p_status := 'ERROR_INVALID_AMOUNT';
        RETURN;
    END IF;

    -- Lock source account and fetch current balance
    SELECT balance, status INTO v_src_balance, v_src_status
    FROM cbs_accounts
    WHERE account_no = p_src_account
    FOR UPDATE;

    IF v_src_status <> 'ACTIVE' THEN
        p_status := 'ERROR_SRC_ACCOUNT_FROZEN';
        RETURN;
    END IF;

    IF v_src_balance < (p_amount + p_fee) THEN
        p_status := 'ERROR_INSUFFICIENT_FUNDS';
        RETURN;
    END IF;

    -- Lock target account and verify status
    SELECT status INTO v_tgt_status
    FROM cbs_accounts
    WHERE account_no = p_tgt_account
    FOR UPDATE;

    IF v_tgt_status <> 'ACTIVE' THEN
        p_status := 'ERROR_TGT_ACCOUNT_INACTIVE';
        RETURN;
    END IF;

    -- 1. Deduct from source account
    UPDATE cbs_accounts
    SET balance = balance - (p_amount + p_fee),
        updated_at = SYSTIMESTAMP
    WHERE account_no = p_src_account;

    -- 2. Credit to target account
    UPDATE cbs_accounts
    SET balance = balance + p_amount,
        updated_at = SYSTIMESTAMP
    WHERE account_no = p_tgt_account;

    -- 3. Insert Double-Entry Ledger for Source Debit
    v_ledger_id_1 := 'GL_' || p_tx_id || '_D';
    INSERT INTO cbs_general_ledger (
        ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description
    ) VALUES (
        v_ledger_id_1, p_src_account, v_journal_id, 'DEBIT', (p_amount + p_fee), (v_src_balance - p_amount - p_fee), 'CNY', 'Transfer out'
    );

    -- 4. Insert Double-Entry Ledger for Target Credit
    v_ledger_id_2 := 'GL_' || p_tx_id || '_C';
    INSERT INTO cbs_general_ledger (
        ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description
    ) VALUES (
        v_ledger_id_2, p_tgt_account, v_journal_id, 'CREDIT', p_amount, 0, 'CNY', 'Transfer in'
    );

    -- 5. Record Transaction record
    INSERT INTO cbs_settlement_transactions (
        tx_id, source_account, target_account, amount, fee_amount, currency_code, channel_code, tx_status, settlement_date, completed_at
    ) VALUES (
        p_tx_id, p_src_account, p_tgt_account, p_amount, p_fee, 'CNY', p_channel, 'COMMITTED', TRUNC(SYSDATE), SYSTIMESTAMP
    );

    p_status := 'SUCCESS';
    COMMIT;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        ROLLBACK;
        p_status := 'ERROR_ACCOUNT_NOT_FOUND';
    WHEN OTHERS THEN
        ROLLBACK;
        p_status := 'ERROR_SYSTEM_EXCEPTION';
END sp_cbs_transfer_funds;
/

-- PL/SQL Stored Procedure: Accrue Daily Interest across all active deposit accounts
CREATE OR REPLACE PROCEDURE sp_cbs_accrue_daily_interest (
    p_settlement_date IN DATE,
    p_processed_count OUT NUMBER,
    p_total_interest OUT NUMBER
)
IS
    CURSOR cur_accounts IS
        SELECT account_no, balance, interest_rate
        FROM cbs_accounts
        WHERE status = 'ACTIVE' AND balance > 0
        FOR UPDATE OF balance;
        
    v_acc_no VARCHAR2(32);
    v_bal NUMBER(18, 4);
    v_rate NUMBER(8, 6);
    v_daily_interest NUMBER(18, 4);
BEGIN
    p_processed_count := 0;
    p_total_interest := 0;

    OPEN cur_accounts;
    LOOP
        FETCH cur_accounts INTO v_acc_no, v_bal, v_rate;
        EXIT WHEN cur_accounts%NOTFOUND;

        -- Daily interest = balance * (annual_rate / 365)
        v_daily_interest := ROUND(v_bal * (v_rate / 365.0), 4);

        IF v_daily_interest > 0 THEN
            UPDATE cbs_accounts
            SET balance = balance + v_daily_interest,
                last_interest_date = p_settlement_date,
                updated_at = SYSTIMESTAMP
            WHERE account_no = v_acc_no;

            INSERT INTO cbs_general_ledger (
                ledger_id, account_no, journal_id, entry_type, amount, running_balance, currency_code, description
            ) VALUES (
                'INT_' || v_acc_no || '_' || TO_CHAR(p_settlement_date, 'YYYYMMDD'),
                v_acc_no,
                'JRN_INTEREST_' || TO_CHAR(p_settlement_date, 'YYYYMMDD'),
                'CREDIT',
                v_daily_interest,
                (v_bal + v_daily_interest),
                'CNY',
                'Daily interest accrual'
            );

            p_total_interest := p_total_interest + v_daily_interest;
        END IF;

        p_processed_count := p_processed_count + 1;
    END LOOP;
    CLOSE cur_accounts;

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF cur_accounts%ISOPEN THEN
            CLOSE cur_accounts;
        END IF;
        ROLLBACK;
        RAISE;
END sp_cbs_accrue_daily_interest;
/

-- Trigger: Account Audit Trail on Balance Mutation
CREATE OR REPLACE TRIGGER trg_cbs_account_audit
AFTER UPDATE OF balance ON cbs_accounts
FOR EACH ROW
BEGIN
    INSERT INTO cbs_audit_log (
        log_id, entity_name, entity_key, action_type, old_state, new_state, operator_id, checksum
    ) VALUES (
        'AUDIT_' || TO_CHAR(SYSTIMESTAMP, 'YYYYMMDDHH24MISSFF6'),
        'cbs_accounts',
        :NEW.account_no,
        'UPDATE_BALANCE',
        'balance=' || TO_CHAR(:OLD.balance),
        'balance=' || TO_CHAR(:NEW.balance),
        'TRIGGER',
        STANDARD_HASH(:NEW.account_no || TO_CHAR(:NEW.balance), 'SHA256')
    );
END;
/
