-- ============================================================================
-- Enterprise Insurance & Actuarial Claims Production Workload
-- Source Dialects: Oracle PL/SQL & SQL Server T-SQL
-- ============================================================================

-- Table: Insurance Policyholders
CREATE TABLE ins_policyholders (
    holder_id VARCHAR2(32) NOT NULL,
    id_card_no VARCHAR2(18) NOT NULL,
    full_name VARCHAR2(64) NOT NULL,
    phone_number VARCHAR2(20) NOT NULL,
    credit_rating VARCHAR2(8) DEFAULT 'AAA' NOT NULL,
    risk_level NUMBER(3, 0) DEFAULT 1 NOT NULL,
    status VARCHAR2(16) DEFAULT 'ACTIVE' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_ins_holders PRIMARY KEY (holder_id),
    CONSTRAINT uk_ins_idcard UNIQUE (id_card_no)
);

-- Table: Insurance Policies
CREATE TABLE ins_policies (
    policy_no VARCHAR2(32) NOT NULL,
    holder_id VARCHAR2(32) NOT NULL,
    product_type VARCHAR2(32) NOT NULL,
    sum_insured NUMBER(18, 4) NOT NULL,
    deductible NUMBER(18, 4) DEFAULT 0.0000 NOT NULL,
    premium NUMBER(18, 4) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    policy_status VARCHAR2(16) DEFAULT 'IN_FORCE' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_ins_policies PRIMARY KEY (policy_no),
    CONSTRAINT fk_ins_pol_holder FOREIGN KEY (holder_id) REFERENCES ins_policyholders (holder_id),
    CONSTRAINT chk_ins_pol_status CHECK (policy_status IN ('IN_FORCE', 'EXPIRED', 'CANCELLED', 'SUSPENDED'))
);

-- Table: Claims Submissions
CREATE TABLE ins_claims (
    claim_id VARCHAR2(64) NOT NULL,
    policy_no VARCHAR2(32) NOT NULL,
    incident_date DATE NOT NULL,
    report_date DATE DEFAULT SYSDATE NOT NULL,
    claimed_amount NUMBER(18, 4) NOT NULL,
    approved_amount NUMBER(18, 4) DEFAULT 0.0000 NOT NULL,
    deductible_applied NUMBER(18, 4) DEFAULT 0.0000 NOT NULL,
    fraud_risk_score NUMBER(5, 2) DEFAULT 0.00 NOT NULL,
    claim_status VARCHAR2(16) DEFAULT 'SUBMITTED' NOT NULL,
    adjudicator_id VARCHAR2(32),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_ins_claims PRIMARY KEY (claim_id),
    CONSTRAINT fk_ins_claim_policy FOREIGN KEY (policy_no) REFERENCES ins_policies (policy_no),
    CONSTRAINT chk_ins_claim_status CHECK (claim_status IN ('SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'SETTLED'))
);

-- Table: Actuarial Reserves Ledger
CREATE TABLE ins_actuarial_reserves (
    reserve_id VARCHAR2(64) NOT NULL,
    policy_no VARCHAR2(32) NOT NULL,
    claim_id VARCHAR2(64),
    reserve_type VARCHAR2(16) NOT NULL,
    amount NUMBER(18, 4) NOT NULL,
    effective_date DATE DEFAULT SYSDATE NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_ins_reserves PRIMARY KEY (reserve_id),
    CONSTRAINT fk_ins_res_policy FOREIGN KEY (policy_no) REFERENCES ins_policies (policy_no),
    CONSTRAINT chk_ins_res_type CHECK (reserve_type IN ('UNEARNED_PREMIUM', 'OUTSTANDING_CLAIMS', 'IBNR'))
);

-- View: Policy Loss Ratio Summary
CREATE OR REPLACE VIEW v_ins_loss_ratio AS
SELECT 
    p.product_type,
    COUNT(DISTINCT p.policy_no) AS active_policy_count,
    SUM(p.premium) AS total_earned_premiums,
    NVL(SUM(c.approved_amount), 0) AS total_claims_paid,
    ROUND(CASE 
        WHEN SUM(p.premium) > 0 THEN (NVL(SUM(c.approved_amount), 0) / SUM(p.premium)) * 100.0 
        ELSE 0.0 
    END, 2) AS loss_ratio_pct
FROM ins_policies p
LEFT JOIN ins_claims c ON p.policy_no = c.policy_no AND c.claim_status = 'SETTLED'
WHERE p.policy_status = 'IN_FORCE'
GROUP BY p.product_type;

-- Stored Procedure: Adjudicate Claim with Fraud Scoring and Coverage Deductible
CREATE OR REPLACE PROCEDURE sp_ins_adjudicate_claim (
    p_claim_id IN VARCHAR2,
    p_adjudicator_id IN VARCHAR2,
    p_override_fraud IN NUMBER,
    p_final_decision OUT VARCHAR2,
    p_payout_amount OUT NUMBER
)
IS
    v_policy_no VARCHAR2(32);
    v_claimed NUMBER(18, 4);
    v_status VARCHAR2(16);
    v_fraud_score NUMBER(5, 2);
    v_sum_insured NUMBER(18, 4);
    v_deductible NUMBER(18, 4);
    v_net_approved NUMBER(18, 4);
BEGIN
    p_payout_amount := 0;

    -- Lock and retrieve claim details
    SELECT policy_no, claimed_amount, claim_status, fraud_risk_score
    INTO v_policy_no, v_claimed, v_status, v_fraud_score
    FROM ins_claims
    WHERE claim_id = p_claim_id
    FOR UPDATE;

    IF v_status NOT IN ('SUBMITTED', 'UNDER_REVIEW') THEN
        p_final_decision := 'ERROR_INVALID_CLAIM_STATUS';
        RETURN;
    END IF;

    -- High fraud risk check (> 75.0 requires special override)
    IF v_fraud_score > 75.0 AND p_override_fraud = 0 THEN
        UPDATE ins_claims
        SET claim_status = 'UNDER_REVIEW',
            adjudicator_id = p_adjudicator_id,
            updated_at = SYSTIMESTAMP
        WHERE claim_id = p_claim_id;

        p_final_decision := 'FLAGGED_FOR_FRAUD_INVESTIGATION';
        COMMIT;
        RETURN;
    END IF;

    -- Lock and check policy coverage
    SELECT sum_insured, deductible
    INTO v_sum_insured, v_deductible
    FROM ins_policies
    WHERE policy_no = v_policy_no;

    -- Calculate payout after deductible
    IF v_claimed <= v_deductible THEN
        v_net_approved := 0;
        p_final_decision := 'REJECTED_BELOW_DEDUCTIBLE';
    ELSE
        v_net_approved := v_claimed - v_deductible;
        IF v_net_approved > v_sum_insured THEN
            v_net_approved := v_sum_insured;
        END IF;
        p_final_decision := 'APPROVED';
    END IF;

    p_payout_amount := v_net_approved;

    -- Update claim record
    UPDATE ins_claims
    SET approved_amount = v_net_approved,
        deductible_applied = v_deductible,
        claim_status = CASE WHEN v_net_approved > 0 THEN 'APPROVED' ELSE 'REJECTED' END,
        adjudicator_id = p_adjudicator_id,
        updated_at = SYSTIMESTAMP
    WHERE claim_id = p_claim_id;

    -- Create actuarial outstanding claim reserve
    IF v_net_approved > 0 THEN
        INSERT INTO ins_actuarial_reserves (
            reserve_id, policy_no, claim_id, reserve_type, amount, effective_date
        ) VALUES (
            'RES_' || p_claim_id,
            v_policy_no,
            p_claim_id,
            'OUTSTANDING_CLAIMS',
            v_net_approved,
            TRUNC(SYSDATE)
        );
    END IF;

    COMMIT;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        ROLLBACK;
        p_final_decision := 'ERROR_CLAIM_NOT_FOUND';
    WHEN OTHERS THEN
        ROLLBACK;
        p_final_decision := 'ERROR_SYSTEM_EXCEPTION';
END sp_ins_adjudicate_claim;
/
