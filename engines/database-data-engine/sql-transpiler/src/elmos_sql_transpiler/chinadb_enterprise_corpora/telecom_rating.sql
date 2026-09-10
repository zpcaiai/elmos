-- ============================================================================
-- Enterprise Telecom Billing & Real-Time CDR Rating Workload
-- Source Dialects: Oracle PL/SQL & SQL Server T-SQL
-- ============================================================================

-- Table: Telecom Subscribers
CREATE TABLE tel_subscribers (
    msisdn VARCHAR2(20) NOT NULL,
    imsi VARCHAR2(20) NOT NULL,
    customer_id VARCHAR2(32) NOT NULL,
    plan_id VARCHAR2(16) NOT NULL,
    account_balance NUMBER(12, 4) DEFAULT 0.0000 NOT NULL,
    voice_bucket_seconds NUMBER(10, 0) DEFAULT 0 NOT NULL,
    data_bucket_mb NUMBER(12, 0) DEFAULT 0 NOT NULL,
    status VARCHAR2(16) DEFAULT 'ACTIVE' NOT NULL,
    activated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_tel_subs PRIMARY KEY (msisdn),
    CONSTRAINT uk_tel_imsi UNIQUE (imsi),
    CONSTRAINT chk_tel_sub_status CHECK (status IN ('ACTIVE', 'SUSPENDED', 'TERMINATED', 'BARRED'))
);

-- Table: Rate Plans & Tariff Tariffs
CREATE TABLE tel_rate_plans (
    plan_id VARCHAR2(16) NOT NULL,
    plan_name VARCHAR2(64) NOT NULL,
    monthly_fee NUMBER(10, 2) NOT NULL,
    included_voice_sec NUMBER(10, 0) NOT NULL,
    included_data_mb NUMBER(12, 0) NOT NULL,
    voice_rate_per_min NUMBER(8, 4) NOT NULL,
    data_rate_per_mb NUMBER(8, 4) NOT NULL,
    sms_rate NUMBER(8, 4) NOT NULL,
    roaming_multiplier NUMBER(4, 2) DEFAULT 1.50 NOT NULL,
    CONSTRAINT pk_tel_plans PRIMARY KEY (plan_id)
);

-- Table: Call Detail Records (CDRs)
CREATE TABLE tel_cdrs (
    cdr_id VARCHAR2(64) NOT NULL,
    caller_msisdn VARCHAR2(20) NOT NULL,
    callee_msisdn VARCHAR2(20),
    service_type VARCHAR2(16) NOT NULL,
    start_time TIMESTAMP NOT NULL,
    duration_seconds NUMBER(8, 0) DEFAULT 0 NOT NULL,
    data_bytes NUMBER(16, 0) DEFAULT 0 NOT NULL,
    roaming_flag NUMBER(1, 0) DEFAULT 0 NOT NULL,
    charged_amount NUMBER(12, 4) DEFAULT 0.0000 NOT NULL,
    rated_status VARCHAR2(16) DEFAULT 'UNRATED' NOT NULL,
    rated_at TIMESTAMP,
    CONSTRAINT pk_tel_cdrs PRIMARY KEY (cdr_id),
    CONSTRAINT fk_tel_cdr_sub FOREIGN KEY (caller_msisdn) REFERENCES tel_subscribers (msisdn),
    CONSTRAINT chk_tel_service CHECK (service_type IN ('VOICE', 'DATA', 'SMS'))
);

-- View: Subscriber Usage Summary
CREATE OR REPLACE VIEW v_tel_monthly_usage AS
SELECT 
    s.msisdn,
    s.plan_id,
    s.account_balance,
    COUNT(c.cdr_id) AS total_sessions,
    NVL(SUM(CASE WHEN c.service_type = 'VOICE' THEN c.duration_seconds ELSE 0 END), 0) AS total_voice_seconds,
    NVL(SUM(CASE WHEN c.service_type = 'DATA' THEN c.data_bytes ELSE 0 END), 0) AS total_data_bytes,
    NVL(SUM(c.charged_amount), 0) AS total_charges
FROM tel_subscribers s
LEFT JOIN tel_cdrs c ON s.msisdn = c.caller_msisdn AND c.rated_status = 'RATED'
GROUP BY s.msisdn, s.plan_id, s.account_balance;

-- Procedure: Real-time CDR Rating and Quota Deduction
CREATE OR REPLACE PROCEDURE sp_tel_rate_cdr (
    p_cdr_id IN VARCHAR2,
    p_final_charge OUT NUMBER,
    p_status OUT VARCHAR2
)
IS
    v_msisdn VARCHAR2(20);
    v_service VARCHAR2(16);
    v_dur NUMBER(8, 0);
    v_bytes NUMBER(16, 0);
    v_roaming NUMBER(1, 0);
    v_plan_id VARCHAR2(16);
    v_balance NUMBER(12, 4);
    v_voice_bkt NUMBER(10, 0);
    v_data_bkt NUMBER(12, 0);
    v_v_rate NUMBER(8, 4);
    v_d_rate NUMBER(8, 4);
    v_roam_mult NUMBER(4, 2);
    v_charge NUMBER(12, 4);
    v_mb NUMBER(12, 0);
BEGIN
    p_final_charge := 0;

    -- Fetch and lock CDR
    SELECT caller_msisdn, service_type, duration_seconds, data_bytes, roaming_flag
    INTO v_msisdn, v_service, v_dur, v_bytes, v_roaming
    FROM tel_cdrs
    WHERE cdr_id = p_cdr_id
    FOR UPDATE;

    -- Lock subscriber balance
    SELECT plan_id, account_balance, voice_bucket_seconds, data_bucket_mb
    INTO v_plan_id, v_balance, v_voice_bkt, v_data_bkt
    FROM tel_subscribers
    WHERE msisdn = v_msisdn
    FOR UPDATE;

    -- Fetch plan rates
    SELECT voice_rate_per_min, data_rate_per_mb, roaming_multiplier
    INTO v_v_rate, v_d_rate, v_roam_mult
    FROM tel_rate_plans
    WHERE plan_id = v_plan_id;

    v_charge := 0.0000;

    IF v_service = 'VOICE' THEN
        -- Check voice bucket first
        IF v_voice_bkt >= v_dur THEN
            -- Deduct from bucket, no monetary charge
            UPDATE tel_subscribers
            SET voice_bucket_seconds = voice_bucket_seconds - v_dur,
                updated_at = SYSTIMESTAMP
            WHERE msisdn = v_msisdn;
            v_charge := 0.0000;
        ELSE
            -- Partial bucket, remainder charged per minute
            v_dur := v_dur - v_voice_bkt;
            UPDATE tel_subscribers
            SET voice_bucket_seconds = 0,
                updated_at = SYSTIMESTAMP
            WHERE msisdn = v_msisdn;

            v_charge := ROUND((v_dur / 60.0) * v_v_rate, 4);
            IF v_roaming = 1 THEN
                v_charge := ROUND(v_charge * v_roam_mult, 4);
            END IF;
        END IF;

    ELSIF v_service = 'DATA' THEN
        v_mb := CEIL(v_bytes / (1024 * 1024));
        IF v_data_bkt >= v_mb THEN
            UPDATE tel_subscribers
            SET data_bucket_mb = data_bucket_mb - v_mb,
                updated_at = SYSTIMESTAMP
            WHERE msisdn = v_msisdn;
            v_charge := 0.0000;
        ELSE
            v_mb := v_mb - v_data_bkt;
            UPDATE tel_subscribers
            SET data_bucket_mb = 0,
                updated_at = SYSTIMESTAMP
            WHERE msisdn = v_msisdn;

            v_charge := ROUND(v_mb * v_d_rate, 4);
            IF v_roaming = 1 THEN
                v_charge := ROUND(v_charge * v_roam_mult, 4);
            END IF;
        END IF;
    END IF;

    -- Apply monetary charge to balance
    IF v_charge > 0 THEN
        UPDATE tel_subscribers
        SET account_balance = account_balance - v_charge,
            updated_at = SYSTIMESTAMP
        WHERE msisdn = v_msisdn;
    END IF;

    -- Update CDR status
    UPDATE tel_cdrs
    SET charged_amount = v_charge,
        rated_status = 'RATED',
        rated_at = SYSTIMESTAMP
    WHERE cdr_id = p_cdr_id;

    p_final_charge := v_charge;
    p_status := 'SUCCESS';
    COMMIT;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        ROLLBACK;
        p_status := 'ERROR_NOT_FOUND';
    WHEN OTHERS THEN
        ROLLBACK;
        p_status := 'ERROR_RATING_FAILED';
END sp_tel_rate_cdr;
/
