-- ELMOS self-service billing and usage closure.
-- PostgreSQL 17.5 / Flyway-owned schema. Existing V9/V10 aggregates remain authoritative.

CREATE TABLE self_service_pricing_plan_versions (
    catalog_version varchar(64) NOT NULL,
    plan_id varchar(96) NOT NULL,
    currency char(3) NOT NULL CHECK (currency = 'CNY'),
    price_minor numeric(19,0) NOT NULL CHECK (price_minor >= 0),
    billing_period varchar(16) NOT NULL CHECK (billing_period IN ('TRIAL', 'MONTH', 'YEAR')),
    allowance_window varchar(32) NOT NULL CHECK (allowance_window IN ('TRIAL_TERM', 'MONTHLY')),
    token_limit numeric(30,0) NOT NULL CHECK (token_limit >= 0),
    credit_limit numeric(30,0) NOT NULL CHECK (credit_limit >= 0),
    active_project_limit integer NOT NULL CHECK (active_project_limit > 0),
    concurrent_job_limit integer NOT NULL CHECK (concurrent_job_limit > 0),
    artifact_retention_days integer NOT NULL CHECK (artifact_retention_days > 0),
    effective_from timestamptz NOT NULL,
    effective_until timestamptz,
    source_ref varchar(255) NOT NULL,
    status varchar(16) NOT NULL CHECK (status IN ('DRAFT', 'PUBLISHED', 'SUPERSEDED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (catalog_version, plan_id),
    CHECK (effective_until IS NULL OR effective_until > effective_from)
);

INSERT INTO self_service_pricing_plan_versions (
    catalog_version, plan_id, currency, price_minor, billing_period, allowance_window,
    token_limit, credit_limit, active_project_limit, concurrent_job_limit,
    artifact_retention_days, effective_from, source_ref, status
) VALUES
    ('2026-07-28.2', 'elmos-free-trial', 'CNY', 0, 'TRIAL', 'TRIAL_TERM',
     2000000, 60, 1, 1, 7, '2026-07-28T00:00:00Z',
     'contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json', 'DRAFT'),
    ('2026-07-28.2', 'elmos-pro-monthly', 'CNY', 12900, 'MONTH', 'MONTHLY',
     20000000, 600, 10, 3, 30, '2026-07-28T00:00:00Z',
     'contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json', 'DRAFT'),
    ('2026-07-28.2', 'elmos-pro-annual', 'CNY', 129000, 'YEAR', 'MONTHLY',
     25000000, 750, 25, 5, 90, '2026-07-28T00:00:00Z',
     'contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json', 'DRAFT');

CREATE TRIGGER self_service_pricing_plan_versions_append_only
BEFORE UPDATE OR DELETE ON self_service_pricing_plan_versions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

ALTER TABLE subscriptions
    ADD COLUMN catalog_version varchar(64),
    ADD COLUMN plan_id varchar(96),
    ADD COLUMN actor_id varchar(128),
    ADD COLUMN billing_period varchar(16),
    ADD COLUMN currency char(3),
    ADD COLUMN price_minor numeric(19,0),
    ADD COLUMN provider varchar(32),
    ADD COLUMN provider_customer_ref varchar(255),
    ADD COLUMN provider_subscription_ref varchar(255),
    ADD COLUMN current_period_start timestamptz,
    ADD COLUMN current_period_end timestamptz,
    ADD COLUMN cancel_at_period_end boolean NOT NULL DEFAULT false,
    ADD COLUMN state_version bigint NOT NULL DEFAULT 0,
    ADD CONSTRAINT subscriptions_self_service_shape CHECK (
        plan_id IS NULL OR (
            catalog_version IS NOT NULL
            AND actor_id IS NOT NULL
            AND billing_period IN ('TRIAL', 'MONTH', 'YEAR')
            AND currency = 'CNY'
            AND price_minor >= 0
            AND current_period_start IS NOT NULL
            AND current_period_end > current_period_start
        )
    );

CREATE UNIQUE INDEX subscriptions_provider_ref_uq
    ON subscriptions(provider, provider_subscription_ref)
    WHERE provider IS NOT NULL AND provider_subscription_ref IS NOT NULL;
CREATE INDEX subscriptions_active_period_idx
    ON subscriptions(organization_id, status, current_period_end)
    WHERE plan_id IS NOT NULL;

ALTER TABLE subscription_events
    ADD COLUMN subscription_id varchar(96) REFERENCES subscriptions(subscription_id),
    ADD COLUMN actor_id varchar(128),
    ADD COLUMN event_type varchar(48),
    ADD COLUMN effective_at timestamptz,
    ADD COLUMN provider_event_ref varchar(255),
    ADD COLUMN event_version bigint,
    ADD CONSTRAINT subscription_events_self_service_type CHECK (
        event_type IS NULL OR event_type IN (
            'TRIAL_GRANTED', 'CHECKOUT_COMPLETED', 'INVOICE_PAID',
            'PAYMENT_FAILED', 'CANCEL_SCHEDULED', 'CANCELLED',
            'PLAN_CHANGED', 'REFUNDED', 'EXPIRED'
        )
    );

CREATE TRIGGER subscription_events_append_only
BEFORE UPDATE OR DELETE ON subscription_events
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

ALTER TABLE quota_allocations
    ADD COLUMN subscription_id varchar(96) REFERENCES subscriptions(subscription_id),
    ADD COLUMN plan_id varchar(96),
    ADD COLUMN catalog_version varchar(64),
    ADD COLUMN period_start timestamptz,
    ADD COLUMN period_end timestamptz,
    ADD COLUMN token_limit numeric(30,0),
    ADD COLUMN credit_limit numeric(30,0),
    ADD COLUMN consumed_tokens numeric(30,0) NOT NULL DEFAULT 0,
    ADD COLUMN consumed_credits numeric(30,0) NOT NULL DEFAULT 0,
    ADD COLUMN reserved_tokens numeric(30,0) NOT NULL DEFAULT 0,
    ADD COLUMN reserved_credits numeric(30,0) NOT NULL DEFAULT 0,
    ADD COLUMN allocation_version bigint NOT NULL DEFAULT 0,
    ADD CONSTRAINT quota_allocations_self_service_shape CHECK (
        subscription_id IS NULL OR (
            plan_id IS NOT NULL
            AND catalog_version IS NOT NULL
            AND period_start IS NOT NULL
            AND period_end > period_start
            AND token_limit >= 0
            AND credit_limit >= 0
            AND consumed_tokens >= 0
            AND consumed_credits >= 0
            AND reserved_tokens >= 0
            AND reserved_credits >= 0
            AND consumed_tokens + reserved_tokens <= token_limit
            AND consumed_credits + reserved_credits <= credit_limit
        )
    );

CREATE UNIQUE INDEX quota_allocations_subscription_period_uq
    ON quota_allocations(subscription_id, period_start)
    WHERE subscription_id IS NOT NULL;
CREATE INDEX quota_allocations_current_idx
    ON quota_allocations(organization_id, subscription_id, period_start, period_end)
    WHERE subscription_id IS NOT NULL AND status = 'ACTIVE';

ALTER TABLE usage_reservations
    ADD COLUMN subscription_id varchar(96) REFERENCES subscriptions(subscription_id),
    ADD COLUMN quota_allocation_id varchar(96) REFERENCES quota_allocations(quota_allocation_id),
    ADD COLUMN actor_id varchar(128),
    ADD COLUMN operation_key varchar(96),
    ADD COLUMN requested_tokens numeric(30,0),
    ADD COLUMN requested_credits numeric(30,0),
    ADD COLUMN actual_tokens numeric(30,0),
    ADD COLUMN actual_credits numeric(30,0),
    ADD COLUMN expires_at timestamptz,
    ADD COLUMN settled_at timestamptz,
    ADD COLUMN released_at timestamptz,
    ADD COLUMN provider_receipt_ref varchar(255),
    ADD COLUMN reservation_version bigint NOT NULL DEFAULT 0,
    ADD CONSTRAINT usage_reservations_self_service_shape CHECK (
        subscription_id IS NULL OR (
            quota_allocation_id IS NOT NULL
            AND actor_id IS NOT NULL
            AND operation_key IN (
                'repository-discovery', 'migration-or-translation-plan',
                'verified-generation-or-migration', 'isolated-runner-minute',
                'evidence-pack-verification', 'model-inference'
            )
            AND requested_tokens >= 0
            AND requested_credits >= 0
            AND requested_tokens + requested_credits > 0
            AND expires_at IS NOT NULL
            AND status IN ('RESERVED', 'SETTLED', 'RELEASED', 'EXPIRED')
            AND (actual_tokens IS NULL OR actual_tokens >= 0)
            AND (actual_credits IS NULL OR actual_credits >= 0)
        )
    );

CREATE INDEX usage_reservations_expiry_idx
    ON usage_reservations(organization_id, expires_at)
    WHERE status = 'RESERVED' AND subscription_id IS NOT NULL;

ALTER TABLE usage_events
    ADD COLUMN subscription_id varchar(96) REFERENCES subscriptions(subscription_id),
    ADD COLUMN quota_allocation_id varchar(96) REFERENCES quota_allocations(quota_allocation_id),
    ADD COLUMN reservation_id varchar(96) REFERENCES usage_reservations(usage_reservation_id),
    ADD COLUMN actor_id varchar(128),
    ADD COLUMN plan_id varchar(96),
    ADD COLUMN operation_key varchar(96),
    ADD COLUMN meter_id varchar(64),
    ADD COLUMN token_class varchar(16),
    ADD COLUMN quantity numeric(30,0),
    ADD COLUMN occurred_at timestamptz,
    ADD COLUMN recorded_at timestamptz,
    ADD COLUMN reconciliation_status varchar(16),
    ADD COLUMN provider varchar(64),
    ADD COLUMN provider_receipt_ref varchar(255),
    ADD COLUMN provider_cost_currency char(3),
    ADD COLUMN provider_cost_minor numeric(19,6),
    ADD COLUMN correction_of_event_id varchar(96),
    ADD CONSTRAINT usage_events_meter_shape CHECK (
        meter_id IS NULL OR (
            meter_id IN ('model-token-v1', 'platform-credit-v1')
            AND quantity > 0
            AND operation_key IS NOT NULL
            AND occurred_at IS NOT NULL
            AND recorded_at IS NOT NULL
            AND reconciliation_status IN ('PENDING', 'RECONCILED', 'REJECTED')
            AND (
                (meter_id = 'model-token-v1' AND token_class IN (
                    'INPUT', 'OUTPUT', 'CACHE_READ', 'CACHE_WRITE'
                ))
                OR (meter_id = 'platform-credit-v1' AND token_class IS NULL)
            )
            AND (
                provider_cost_minor IS NULL
                OR (provider_cost_minor >= 0 AND provider_cost_currency IS NOT NULL)
            )
        )
    );

CREATE TRIGGER usage_events_self_service_append_only
BEFORE UPDATE OR DELETE ON usage_events
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE INDEX usage_events_period_idx
    ON usage_events(organization_id, subscription_id, occurred_at, reconciliation_status)
    WHERE meter_id IS NOT NULL;
CREATE INDEX usage_events_actor_idx
    ON usage_events(organization_id, actor_id, occurred_at)
    WHERE meter_id IS NOT NULL;
CREATE UNIQUE INDEX usage_events_provider_receipt_uq
    ON usage_events(provider, provider_receipt_ref, meter_id, token_class)
    WHERE provider IS NOT NULL AND provider_receipt_ref IS NOT NULL;

ALTER TABLE usage_ledger_entries
    ADD COLUMN subscription_id varchar(96) REFERENCES subscriptions(subscription_id),
    ADD COLUMN quota_allocation_id varchar(96) REFERENCES quota_allocations(quota_allocation_id),
    ADD COLUMN usage_event_id varchar(96) REFERENCES usage_events(usage_event_id),
    ADD COLUMN actor_id varchar(128),
    ADD COLUMN operation_key varchar(96),
    ADD COLUMN meter_id varchar(64),
    ADD COLUMN direction varchar(8),
    ADD COLUMN quantity numeric(30,0),
    ADD COLUMN correction_of_ledger_entry_id varchar(96),
    ADD COLUMN occurred_at timestamptz,
    ADD COLUMN recorded_at timestamptz,
    ADD CONSTRAINT usage_ledger_entries_meter_shape CHECK (
        meter_id IS NULL OR (
            meter_id IN ('model-token-v1', 'platform-credit-v1')
            AND direction IN ('DEBIT', 'CREDIT')
            AND quantity > 0
            AND operation_key IS NOT NULL
            AND occurred_at IS NOT NULL
            AND recorded_at IS NOT NULL
            AND (
                (direction = 'DEBIT' AND correction_of_ledger_entry_id IS NULL)
                OR (direction = 'CREDIT' AND correction_of_ledger_entry_id IS NOT NULL)
            )
        )
    );

CREATE INDEX usage_ledger_period_idx
    ON usage_ledger_entries(organization_id, subscription_id, occurred_at)
    WHERE meter_id IS NOT NULL;

CREATE TABLE trial_grants (
    trial_grant_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    actor_id varchar(128) NOT NULL,
    verified_subject_hash char(64) NOT NULL CHECK (verified_subject_hash ~ '^[0-9a-f]{64}$'),
    subscription_id varchar(96) NOT NULL REFERENCES subscriptions(subscription_id),
    catalog_version varchar(64) NOT NULL,
    plan_id varchar(96) NOT NULL CHECK (plan_id = 'elmos-free-trial'),
    status varchar(16) NOT NULL CHECK (status IN ('ACTIVE', 'CONVERTED', 'EXPIRED', 'REVOKED')),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    idempotency_key varchar(160) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id),
    UNIQUE (verified_subject_hash),
    UNIQUE (organization_id, idempotency_key),
    CHECK (ends_at > starts_at)
);

CREATE TABLE trial_events (
    trial_event_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    trial_grant_id varchar(96) NOT NULL REFERENCES trial_grants(trial_grant_id),
    actor_id varchar(128) NOT NULL,
    event_type varchar(24) NOT NULL CHECK (event_type IN ('GRANTED', 'CONVERTED', 'EXPIRED', 'REVOKED')),
    reason_code varchar(96) NOT NULL,
    occurred_at timestamptz NOT NULL,
    idempotency_key varchar(160) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TRIGGER trial_events_append_only
BEFORE UPDATE OR DELETE ON trial_events
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE payment_checkout_sessions (
    checkout_session_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    actor_id varchar(128) NOT NULL,
    plan_id varchar(96) NOT NULL,
    catalog_version varchar(64) NOT NULL,
    currency char(3) NOT NULL CHECK (currency = 'CNY'),
    amount_minor numeric(19,0) NOT NULL CHECK (amount_minor > 0),
    provider varchar(32) NOT NULL CHECK (provider = 'STRIPE_CHECKOUT'),
    provider_session_ref varchar(255),
    provider_customer_ref varchar(255),
    status varchar(24) NOT NULL CHECK (
        status IN ('CREATING', 'OPEN', 'COMPLETED', 'EXPIRED', 'FAILED', 'RECONCILIATION_REQUIRED')
    ),
    checkout_url varchar(2048),
    expires_at timestamptz NOT NULL,
    completed_at timestamptz,
    failure_code varchar(96),
    idempotency_key varchar(160) NOT NULL,
    request_hash char(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key),
    UNIQUE (provider, provider_session_ref)
);

CREATE TABLE payment_provider_events (
    payment_provider_event_id varchar(255) NOT NULL,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    provider varchar(32) NOT NULL CHECK (provider = 'STRIPE_CHECKOUT'),
    event_type varchar(64) NOT NULL,
    object_ref varchar(255) NOT NULL,
    subscription_ref varchar(255),
    customer_ref varchar(255),
    invoice_ref varchar(255),
    amount_minor numeric(19,0),
    currency char(3),
    event_created_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    payload_sha256 char(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    signature_verified boolean NOT NULL CHECK (signature_verified),
    processing_status varchar(32) NOT NULL CHECK (
        processing_status IN ('RECEIVED', 'APPLIED', 'DUPLICATE', 'RECONCILIATION_REQUIRED', 'REJECTED')
    ),
    idempotency_key varchar(160) NOT NULL,
    PRIMARY KEY (provider, payment_provider_event_id),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TRIGGER payment_provider_events_append_only
BEFORE UPDATE OR DELETE ON payment_provider_events
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE payment_reconciliation_cases (
    payment_reconciliation_case_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    provider varchar(32) NOT NULL,
    provider_object_ref varchar(255) NOT NULL,
    expected_state varchar(64) NOT NULL,
    observed_state varchar(64) NOT NULL,
    status varchar(24) NOT NULL CHECK (status IN ('OPEN', 'RESOLVED', 'REJECTED')),
    reason_code varchar(96) NOT NULL,
    opened_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    resolver_actor_id varchar(128),
    resolution_ref varchar(255),
    idempotency_key varchar(160) NOT NULL,
    UNIQUE (organization_id, idempotency_key),
    CHECK ((status = 'OPEN' AND resolved_at IS NULL) OR (status <> 'OPEN' AND resolved_at IS NOT NULL))
);

CREATE TABLE payment_reconciliation_case_events (
    payment_reconciliation_case_event_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    payment_reconciliation_case_id varchar(96) NOT NULL
        REFERENCES payment_reconciliation_cases(payment_reconciliation_case_id),
    actor_id varchar(128) NOT NULL,
    event_type varchar(24) NOT NULL CHECK (event_type IN ('RESOLVED', 'REJECTED')),
    resolution_ref varchar(255) NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key varchar(160) NOT NULL,
    UNIQUE (organization_id, idempotency_key)
);

CREATE TRIGGER payment_reconciliation_case_events_append_only
BEFORE UPDATE OR DELETE ON payment_reconciliation_case_events
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE usage_alert_preferences (
    usage_alert_preference_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    actor_id varchar(128) NOT NULL,
    scope varchar(16) NOT NULL CHECK (scope IN ('ORGANIZATION', 'ACTOR')),
    threshold_bps integer[] NOT NULL DEFAULT ARRAY[5000,8000,9500,10000],
    email_enabled boolean NOT NULL DEFAULT false,
    in_app_enabled boolean NOT NULL DEFAULT true,
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, actor_id),
    CHECK (
        cardinality(threshold_bps) BETWEEN 1 AND 8
        AND threshold_bps <@ ARRAY[1000,2500,5000,7500,8000,9000,9500,10000]
    )
);

CREATE TABLE usage_alert_deliveries (
    usage_alert_delivery_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    actor_id varchar(128) NOT NULL,
    subscription_id varchar(96) NOT NULL REFERENCES subscriptions(subscription_id),
    quota_allocation_id varchar(96) NOT NULL REFERENCES quota_allocations(quota_allocation_id),
    meter_id varchar(64) NOT NULL,
    threshold_bps integer NOT NULL CHECK (threshold_bps BETWEEN 1 AND 10000),
    channel varchar(16) NOT NULL CHECK (channel IN ('IN_APP', 'EMAIL')),
    status varchar(16) NOT NULL CHECK (status IN ('PENDING', 'SENT', 'FAILED', 'SUPPRESSED')),
    destination_hash char(64),
    provider_message_ref varchar(255),
    occurred_at timestamptz NOT NULL,
    idempotency_key varchar(160) NOT NULL,
    UNIQUE (organization_id, idempotency_key)
);

CREATE TRIGGER usage_alert_deliveries_append_only
BEFORE UPDATE OR DELETE ON usage_alert_deliveries
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

DO $$
DECLARE tenant_table text;
BEGIN
    FOREACH tenant_table IN ARRAY ARRAY[
        'trial_grants',
        'trial_events',
        'payment_checkout_sessions',
        'payment_provider_events',
        'payment_reconciliation_cases',
        'payment_reconciliation_case_events',
        'usage_alert_preferences',
        'usage_alert_deliveries'
    ]
    LOOP
        EXECUTE format('CREATE INDEX %I ON %I (organization_id)',
                       'idx_' || tenant_table || '_organization', tenant_table);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tenant_table);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', tenant_table);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            tenant_table
        );
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_enqueue_usage_alerts(
    p_subscription_id varchar,
    p_quota_allocation_id varchar,
    p_actor_id varchar,
    p_meter_id varchar,
    p_before_quantity numeric,
    p_after_quantity numeric,
    p_limit numeric
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    v_org varchar := elmos_current_organization_id();
    v_preference usage_alert_preferences%ROWTYPE;
    v_before_bps integer;
    v_after_bps integer;
    v_threshold integer;
    v_seed text;
BEGIN
    IF p_limit <= 0 OR p_before_quantity < 0 OR p_after_quantity < p_before_quantity THEN
        RAISE EXCEPTION 'USAGE_ALERT_QUANTITY_INVALID';
    END IF;
    SELECT * INTO v_preference
      FROM usage_alert_preferences
     WHERE organization_id = v_org AND actor_id = p_actor_id;
    IF NOT FOUND THEN
        v_preference.threshold_bps := ARRAY[5000,8000,9500,10000];
        v_preference.email_enabled := false;
        v_preference.in_app_enabled := true;
    END IF;
    v_before_bps := least(10000, floor(p_before_quantity * 10000 / p_limit)::integer);
    v_after_bps := least(10000, floor(p_after_quantity * 10000 / p_limit)::integer);
    FOREACH v_threshold IN ARRAY v_preference.threshold_bps LOOP
        IF v_before_bps < v_threshold AND v_after_bps >= v_threshold THEN
            IF v_preference.in_app_enabled THEN
                v_seed := p_quota_allocation_id || ':' || p_meter_id || ':'
                    || v_threshold || ':IN_APP';
                INSERT INTO usage_alert_deliveries (
                    usage_alert_delivery_id, organization_id, actor_id, subscription_id,
                    quota_allocation_id, meter_id, threshold_bps, channel, status,
                    occurred_at, idempotency_key
                ) VALUES (
                    'usage-alert-' || md5(v_seed), v_org, p_actor_id, p_subscription_id,
                    p_quota_allocation_id, p_meter_id, v_threshold, 'IN_APP', 'SENT',
                    now(), v_seed
                ) ON CONFLICT (organization_id, idempotency_key) DO NOTHING;
            END IF;
            IF v_preference.email_enabled THEN
                v_seed := p_quota_allocation_id || ':' || p_meter_id || ':'
                    || v_threshold || ':EMAIL';
                INSERT INTO usage_alert_deliveries (
                    usage_alert_delivery_id, organization_id, actor_id, subscription_id,
                    quota_allocation_id, meter_id, threshold_bps, channel, status,
                    occurred_at, idempotency_key
                ) VALUES (
                    'usage-alert-' || md5(v_seed), v_org, p_actor_id, p_subscription_id,
                    p_quota_allocation_id, p_meter_id, v_threshold, 'EMAIL', 'PENDING',
                    now(), v_seed
                ) ON CONFLICT (organization_id, idempotency_key) DO NOTHING;
            END IF;
        END IF;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_current_organization_id() RETURNS varchar
LANGUAGE plpgsql STABLE AS $$
DECLARE value varchar;
BEGIN
    value := current_setting('app.organization_id', true);
    IF value IS NULL OR value = '' THEN
        RAISE EXCEPTION 'TENANT_CONTEXT_REQUIRED';
    END IF;
    RETURN value;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_reserve_usage(
    p_reservation_id varchar,
    p_subscription_id varchar,
    p_actor_id varchar,
    p_idempotency_key varchar,
    p_operation_key varchar,
    p_requested_tokens numeric,
    p_requested_credits numeric,
    p_expires_at timestamptz
) RETURNS TABLE (
    reservation_id varchar,
    decision varchar,
    remaining_tokens numeric,
    remaining_credits numeric
) LANGUAGE plpgsql AS $$
DECLARE
    v_org varchar := elmos_current_organization_id();
    v_allocation quota_allocations%ROWTYPE;
    v_existing usage_reservations%ROWTYPE;
BEGIN
    IF p_operation_key NOT IN (
        'repository-discovery', 'migration-or-translation-plan',
        'verified-generation-or-migration', 'isolated-runner-minute',
        'evidence-pack-verification', 'model-inference'
    ) THEN
        RAISE EXCEPTION 'USAGE_OPERATION_KEY_INVALID';
    END IF;
    IF p_requested_tokens < 0 OR p_requested_credits < 0
       OR p_requested_tokens <> trunc(p_requested_tokens)
       OR p_requested_credits <> trunc(p_requested_credits)
       OR p_requested_tokens + p_requested_credits <= 0 THEN
        RAISE EXCEPTION 'USAGE_RESERVATION_QUANTITY_INVALID';
    END IF;
    IF p_expires_at <= now() OR p_expires_at > now() + interval '24 hours' THEN
        RAISE EXCEPTION 'USAGE_RESERVATION_EXPIRY_INVALID';
    END IF;

    SELECT * INTO v_existing
      FROM usage_reservations
     WHERE organization_id = v_org AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.subscription_id <> p_subscription_id
           OR v_existing.actor_id <> p_actor_id
           OR v_existing.operation_key <> p_operation_key
           OR v_existing.requested_tokens <> p_requested_tokens
           OR v_existing.requested_credits <> p_requested_credits THEN
            RAISE EXCEPTION 'USAGE_RESERVATION_IDEMPOTENCY_CONFLICT';
        END IF;
        SELECT * INTO v_allocation
          FROM quota_allocations
         WHERE quota_allocation_id = v_existing.quota_allocation_id;
        RETURN QUERY SELECT
            v_existing.usage_reservation_id,
            v_existing.status,
            v_allocation.token_limit - v_allocation.consumed_tokens - v_allocation.reserved_tokens,
            v_allocation.credit_limit - v_allocation.consumed_credits - v_allocation.reserved_credits;
        RETURN;
    END IF;

    SELECT * INTO v_allocation
      FROM quota_allocations
     WHERE organization_id = v_org
       AND subscription_id = p_subscription_id
       AND status = 'ACTIVE'
       AND period_start <= now()
       AND period_end > now()
     ORDER BY period_start DESC
     LIMIT 1
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ACTIVE_ALLOWANCE_NOT_FOUND'; END IF;

    IF v_allocation.consumed_tokens + v_allocation.reserved_tokens + p_requested_tokens
       > v_allocation.token_limit THEN
        RETURN QUERY SELECT
            p_reservation_id, 'DENY_TOKEN_LIMIT'::varchar,
            v_allocation.token_limit - v_allocation.consumed_tokens - v_allocation.reserved_tokens,
            v_allocation.credit_limit - v_allocation.consumed_credits - v_allocation.reserved_credits;
        RETURN;
    END IF;
    IF v_allocation.consumed_credits + v_allocation.reserved_credits + p_requested_credits
       > v_allocation.credit_limit THEN
        RETURN QUERY SELECT
            p_reservation_id, 'DENY_CREDIT_LIMIT'::varchar,
            v_allocation.token_limit - v_allocation.consumed_tokens - v_allocation.reserved_tokens,
            v_allocation.credit_limit - v_allocation.consumed_credits - v_allocation.reserved_credits;
        RETURN;
    END IF;

    INSERT INTO usage_reservations (
        usage_reservation_id, organization_id, schema_version, status,
        idempotency_key, subscription_id, quota_allocation_id, actor_id,
        operation_key, requested_tokens, requested_credits, expires_at, payload
    ) VALUES (
        p_reservation_id, v_org, '2.0', 'RESERVED',
        p_idempotency_key, p_subscription_id, v_allocation.quota_allocation_id, p_actor_id,
        p_operation_key, p_requested_tokens, p_requested_credits, p_expires_at, '{}'::jsonb
    );
    UPDATE quota_allocations
       SET reserved_tokens = reserved_tokens + p_requested_tokens,
           reserved_credits = reserved_credits + p_requested_credits,
           allocation_version = allocation_version + 1,
           updated_at = now()
     WHERE quota_allocation_id = v_allocation.quota_allocation_id;

    RETURN QUERY SELECT
        p_reservation_id, 'RESERVED'::varchar,
        v_allocation.token_limit - v_allocation.consumed_tokens
            - v_allocation.reserved_tokens - p_requested_tokens,
        v_allocation.credit_limit - v_allocation.consumed_credits
            - v_allocation.reserved_credits - p_requested_credits;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_settle_usage(
    p_reservation_id varchar,
    p_event_prefix varchar,
    p_actual_tokens numeric,
    p_actual_credits numeric,
    p_token_class varchar,
    p_provider varchar,
    p_provider_receipt_ref varchar,
    p_provider_cost_currency char(3),
    p_provider_cost_minor numeric,
    p_occurred_at timestamptz
) RETURNS TABLE (
    reservation_id varchar,
    status varchar,
    consumed_tokens numeric,
    consumed_credits numeric,
    remaining_tokens numeric,
    remaining_credits numeric
) LANGUAGE plpgsql AS $$
DECLARE
    v_org varchar := elmos_current_organization_id();
    v_reservation usage_reservations%ROWTYPE;
    v_allocation quota_allocations%ROWTYPE;
    v_token_event_id varchar := p_event_prefix || ':token';
    v_credit_event_id varchar := p_event_prefix || ':credit';
BEGIN
    IF p_actual_tokens < 0 OR p_actual_credits < 0
       OR p_actual_tokens <> trunc(p_actual_tokens)
       OR p_actual_credits <> trunc(p_actual_credits) THEN
        RAISE EXCEPTION 'USAGE_SETTLEMENT_QUANTITY_INVALID';
    END IF;
    SELECT * INTO v_reservation
      FROM usage_reservations
     WHERE organization_id = v_org AND usage_reservation_id = p_reservation_id
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'USAGE_RESERVATION_NOT_FOUND'; END IF;
    IF v_reservation.status = 'SETTLED' THEN
        IF v_reservation.actual_tokens <> p_actual_tokens
           OR v_reservation.actual_credits <> p_actual_credits
           OR v_reservation.provider_receipt_ref <> p_provider_receipt_ref THEN
            RAISE EXCEPTION 'USAGE_SETTLEMENT_IDEMPOTENCY_CONFLICT';
        END IF;
    ELSIF v_reservation.status <> 'RESERVED' THEN
        RAISE EXCEPTION 'USAGE_RESERVATION_NOT_SETTLEABLE';
    ELSE
        IF v_reservation.expires_at <= now() THEN
            RAISE EXCEPTION 'USAGE_RESERVATION_EXPIRED';
        END IF;
        IF p_actual_tokens > v_reservation.requested_tokens
           OR p_actual_credits > v_reservation.requested_credits THEN
            RAISE EXCEPTION 'USAGE_ACTUAL_EXCEEDS_RESERVATION';
        END IF;
        IF p_actual_tokens > 0 AND (
            p_token_class IS NULL
            OR p_token_class NOT IN ('INPUT', 'OUTPUT', 'CACHE_READ', 'CACHE_WRITE')
            OR p_provider IS NULL OR p_provider = ''
            OR p_provider_receipt_ref IS NULL OR p_provider_receipt_ref = ''
        ) THEN
            RAISE EXCEPTION 'TOKEN_PROVIDER_RECEIPT_REQUIRED';
        END IF;

        SELECT * INTO v_allocation
          FROM quota_allocations
         WHERE quota_allocation_id = v_reservation.quota_allocation_id
         FOR UPDATE;

        UPDATE quota_allocations AS allowance
           SET reserved_tokens = allowance.reserved_tokens - v_reservation.requested_tokens,
               reserved_credits = allowance.reserved_credits - v_reservation.requested_credits,
               consumed_tokens = allowance.consumed_tokens + p_actual_tokens,
               consumed_credits = allowance.consumed_credits + p_actual_credits,
               allocation_version = allowance.allocation_version + 1,
               updated_at = now()
         WHERE quota_allocation_id = v_allocation.quota_allocation_id;

        UPDATE usage_reservations
           SET status = 'SETTLED',
               actual_tokens = p_actual_tokens,
               actual_credits = p_actual_credits,
               provider_receipt_ref = p_provider_receipt_ref,
               settled_at = now(),
               reservation_version = reservation_version + 1,
               updated_at = now()
         WHERE usage_reservation_id = p_reservation_id;

        IF p_actual_tokens > 0 THEN
            PERFORM elmos_enqueue_usage_alerts(
                v_reservation.subscription_id, v_reservation.quota_allocation_id,
                v_reservation.actor_id, 'model-token-v1',
                v_allocation.consumed_tokens,
                v_allocation.consumed_tokens + p_actual_tokens,
                v_allocation.token_limit
            );
            INSERT INTO usage_events (
                usage_event_id, organization_id, schema_version, status, idempotency_key,
                subscription_id, quota_allocation_id, reservation_id, actor_id, plan_id,
                operation_key, meter_id, token_class, quantity, occurred_at, recorded_at,
                reconciliation_status, provider, provider_receipt_ref,
                provider_cost_currency, provider_cost_minor, payload
            ) VALUES (
                v_token_event_id, v_org, '2.0', 'RECONCILED', v_token_event_id,
                v_reservation.subscription_id, v_reservation.quota_allocation_id,
                p_reservation_id, v_reservation.actor_id, v_allocation.plan_id,
                v_reservation.operation_key, 'model-token-v1', p_token_class,
                p_actual_tokens, p_occurred_at, now(),
                'RECONCILED', p_provider, p_provider_receipt_ref,
                p_provider_cost_currency, p_provider_cost_minor, '{}'::jsonb
            );
            INSERT INTO usage_ledger_entries (
                usage_ledger_entry_id, organization_id, schema_version, status, idempotency_key,
                subscription_id, quota_allocation_id, usage_event_id, actor_id,
                operation_key, meter_id, direction, quantity, occurred_at, recorded_at, payload
            ) VALUES (
                p_event_prefix || ':token:debit', v_org, '2.0', 'POSTED',
                p_event_prefix || ':token:debit', v_reservation.subscription_id,
                v_reservation.quota_allocation_id, v_token_event_id, v_reservation.actor_id,
                v_reservation.operation_key, 'model-token-v1', 'DEBIT',
                p_actual_tokens, p_occurred_at, now(), '{}'::jsonb
            );
        END IF;

        IF p_actual_credits > 0 THEN
            PERFORM elmos_enqueue_usage_alerts(
                v_reservation.subscription_id, v_reservation.quota_allocation_id,
                v_reservation.actor_id, 'platform-credit-v1',
                v_allocation.consumed_credits,
                v_allocation.consumed_credits + p_actual_credits,
                v_allocation.credit_limit
            );
            INSERT INTO usage_events (
                usage_event_id, organization_id, schema_version, status, idempotency_key,
                subscription_id, quota_allocation_id, reservation_id, actor_id, plan_id,
                operation_key, meter_id, quantity, occurred_at, recorded_at, reconciliation_status,
                provider, provider_receipt_ref, payload
            ) VALUES (
                v_credit_event_id, v_org, '2.0', 'RECONCILED', v_credit_event_id,
                v_reservation.subscription_id, v_reservation.quota_allocation_id,
                p_reservation_id, v_reservation.actor_id, v_allocation.plan_id,
                v_reservation.operation_key, 'platform-credit-v1',
                p_actual_credits, p_occurred_at, now(), 'RECONCILED',
                'ELMOS', p_event_prefix || ':internal-credit', '{}'::jsonb
            );
            INSERT INTO usage_ledger_entries (
                usage_ledger_entry_id, organization_id, schema_version, status, idempotency_key,
                subscription_id, quota_allocation_id, usage_event_id, actor_id,
                operation_key, meter_id, direction, quantity, occurred_at, recorded_at, payload
            ) VALUES (
                p_event_prefix || ':credit:debit', v_org, '2.0', 'POSTED',
                p_event_prefix || ':credit:debit', v_reservation.subscription_id,
                v_reservation.quota_allocation_id, v_credit_event_id, v_reservation.actor_id,
                v_reservation.operation_key, 'platform-credit-v1', 'DEBIT',
                p_actual_credits, p_occurred_at, now(), '{}'::jsonb
            );
        END IF;
    END IF;

    SELECT * INTO v_allocation
      FROM quota_allocations
     WHERE quota_allocation_id = v_reservation.quota_allocation_id;
    RETURN QUERY SELECT
        p_reservation_id, 'SETTLED'::varchar,
        v_allocation.consumed_tokens, v_allocation.consumed_credits,
        v_allocation.token_limit - v_allocation.consumed_tokens - v_allocation.reserved_tokens,
        v_allocation.credit_limit - v_allocation.consumed_credits - v_allocation.reserved_credits;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_release_usage(
    p_reservation_id varchar,
    p_reason_code varchar
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    v_org varchar := elmos_current_organization_id();
    v_reservation usage_reservations%ROWTYPE;
BEGIN
    SELECT * INTO v_reservation
      FROM usage_reservations
     WHERE organization_id = v_org AND usage_reservation_id = p_reservation_id
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'USAGE_RESERVATION_NOT_FOUND'; END IF;
    IF v_reservation.status IN ('RELEASED', 'EXPIRED') THEN
        IF v_reservation.payload->>'reasonCode' IS DISTINCT FROM p_reason_code THEN
            RAISE EXCEPTION 'USAGE_RELEASE_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN;
    END IF;
    IF v_reservation.status <> 'RESERVED' THEN
        RAISE EXCEPTION 'USAGE_RESERVATION_NOT_RELEASABLE';
    END IF;
    PERFORM 1 FROM quota_allocations
     WHERE quota_allocation_id = v_reservation.quota_allocation_id FOR UPDATE;
    UPDATE quota_allocations
       SET reserved_tokens = reserved_tokens - v_reservation.requested_tokens,
           reserved_credits = reserved_credits - v_reservation.requested_credits,
           allocation_version = allocation_version + 1,
           updated_at = now()
     WHERE quota_allocation_id = v_reservation.quota_allocation_id;
    UPDATE usage_reservations
       SET status = CASE WHEN expires_at <= now() THEN 'EXPIRED' ELSE 'RELEASED' END,
           released_at = now(),
           reservation_version = reservation_version + 1,
           updated_at = now(),
           payload = jsonb_build_object('reasonCode', p_reason_code)
     WHERE usage_reservation_id = p_reservation_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_correct_usage(
    p_ledger_entry_id varchar,
    p_original_ledger_entry_id varchar,
    p_actor_id varchar,
    p_quantity numeric,
    p_reason_code varchar,
    p_idempotency_key varchar
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    v_org varchar := elmos_current_organization_id();
    v_original usage_ledger_entries%ROWTYPE;
    v_allocation quota_allocations%ROWTYPE;
    v_prior numeric;
BEGIN
    IF p_quantity <= 0 OR p_quantity <> trunc(p_quantity) THEN
        RAISE EXCEPTION 'USAGE_CORRECTION_QUANTITY_INVALID';
    END IF;
    IF EXISTS (
        SELECT 1 FROM usage_ledger_entries
         WHERE organization_id = v_org AND idempotency_key = p_idempotency_key
    ) THEN RETURN; END IF;
    SELECT * INTO v_original
      FROM usage_ledger_entries
     WHERE organization_id = v_org
       AND usage_ledger_entry_id = p_original_ledger_entry_id
       AND direction = 'DEBIT';
    IF NOT FOUND THEN RAISE EXCEPTION 'USAGE_ORIGINAL_DEBIT_NOT_FOUND'; END IF;
    SELECT COALESCE(sum(quantity), 0) INTO v_prior
      FROM usage_ledger_entries
     WHERE organization_id = v_org
       AND correction_of_ledger_entry_id = p_original_ledger_entry_id
       AND direction = 'CREDIT';
    IF v_prior + p_quantity > v_original.quantity THEN
        RAISE EXCEPTION 'USAGE_CORRECTION_EXCEEDS_ORIGINAL';
    END IF;
    SELECT * INTO v_allocation
      FROM quota_allocations
     WHERE quota_allocation_id = v_original.quota_allocation_id
     FOR UPDATE;
    IF v_original.meter_id = 'model-token-v1' THEN
        IF v_allocation.consumed_tokens < p_quantity THEN
            RAISE EXCEPTION 'USAGE_CORRECTION_NEGATIVE_BALANCE';
        END IF;
        UPDATE quota_allocations
           SET consumed_tokens = consumed_tokens - p_quantity,
               allocation_version = allocation_version + 1,
               updated_at = now()
         WHERE quota_allocation_id = v_allocation.quota_allocation_id;
    ELSE
        IF v_allocation.consumed_credits < p_quantity THEN
            RAISE EXCEPTION 'USAGE_CORRECTION_NEGATIVE_BALANCE';
        END IF;
        UPDATE quota_allocations
           SET consumed_credits = consumed_credits - p_quantity,
               allocation_version = allocation_version + 1,
               updated_at = now()
         WHERE quota_allocation_id = v_allocation.quota_allocation_id;
    END IF;
    INSERT INTO usage_ledger_entries (
        usage_ledger_entry_id, organization_id, schema_version, status, idempotency_key,
        subscription_id, quota_allocation_id, actor_id, meter_id, direction, quantity,
        operation_key, correction_of_ledger_entry_id, occurred_at, recorded_at, payload
    ) VALUES (
        p_ledger_entry_id, v_org, '2.0', 'POSTED', p_idempotency_key,
        v_original.subscription_id, v_original.quota_allocation_id, p_actor_id,
        v_original.meter_id, 'CREDIT', p_quantity, v_original.operation_key,
        p_original_ledger_entry_id,
        now(), now(), jsonb_build_object('reasonCode', p_reason_code)
    );
END;
$$;

CREATE OR REPLACE FUNCTION elmos_activate_subscription_period(
    p_subscription_id varchar,
    p_quota_allocation_id varchar,
    p_actor_id varchar,
    p_plan_id varchar,
    p_provider varchar,
    p_provider_customer_ref varchar,
    p_provider_subscription_ref varchar,
    p_period_start timestamptz,
    p_period_end timestamptz,
    p_provider_event_ref varchar,
    p_idempotency_key varchar
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    v_org varchar := elmos_current_organization_id();
    v_plan self_service_pricing_plan_versions%ROWTYPE;
BEGIN
    IF p_period_end <= p_period_start THEN RAISE EXCEPTION 'BILLING_PERIOD_INVALID'; END IF;
    SELECT * INTO v_plan
      FROM self_service_pricing_plan_versions
     WHERE catalog_version = '2026-07-28.2' AND plan_id = p_plan_id;
    IF NOT FOUND OR v_plan.billing_period = 'TRIAL' THEN
        RAISE EXCEPTION 'PAID_PLAN_INVALID';
    END IF;
    INSERT INTO subscriptions (
        subscription_id, organization_id, schema_version, status, external_ref,
        idempotency_key, payload, catalog_version, plan_id, actor_id, billing_period,
        currency, price_minor, provider, provider_customer_ref, provider_subscription_ref,
        current_period_start, current_period_end, state_version
    ) VALUES (
        p_subscription_id, v_org, '2.0', 'ACTIVE', p_provider_subscription_ref,
        p_idempotency_key, '{}'::jsonb, v_plan.catalog_version, v_plan.plan_id,
        p_actor_id, v_plan.billing_period, v_plan.currency, v_plan.price_minor,
        p_provider, p_provider_customer_ref, p_provider_subscription_ref,
        p_period_start, p_period_end, 1
    )
    ON CONFLICT (subscription_id) DO UPDATE SET
        status = 'ACTIVE',
        provider_customer_ref = EXCLUDED.provider_customer_ref,
        provider_subscription_ref = EXCLUDED.provider_subscription_ref,
        current_period_start = EXCLUDED.current_period_start,
        current_period_end = EXCLUDED.current_period_end,
        state_version = subscriptions.state_version + 1,
        updated_at = now()
    WHERE subscriptions.organization_id = v_org;

    INSERT INTO quota_allocations (
        quota_allocation_id, organization_id, schema_version, status, external_ref,
        idempotency_key, payload, subscription_id, plan_id, catalog_version,
        period_start, period_end, token_limit, credit_limit
    ) VALUES (
        p_quota_allocation_id, v_org, '2.0', 'ACTIVE', p_provider_event_ref,
        p_idempotency_key || ':allowance', '{}'::jsonb, p_subscription_id, v_plan.plan_id,
        v_plan.catalog_version, p_period_start, p_period_end, v_plan.token_limit, v_plan.credit_limit
    )
    ON CONFLICT (subscription_id, period_start) WHERE subscription_id IS NOT NULL
    DO NOTHING;

    INSERT INTO subscription_events (
        subscription_event_id, organization_id, schema_version, status, external_ref,
        idempotency_key, payload, subscription_id, actor_id, event_type,
        effective_at, provider_event_ref, event_version
    ) VALUES (
        p_provider_event_ref || ':subscription', v_org, '2.0', 'APPLIED',
        p_provider_event_ref, p_idempotency_key || ':subscription-event', '{}'::jsonb,
        p_subscription_id, p_actor_id, 'INVOICE_PAID', p_period_start,
        p_provider_event_ref, 1
    ) ON CONFLICT (organization_id, idempotency_key) DO NOTHING;

    UPDATE trial_grants
       SET status = 'CONVERTED', updated_at = now()
     WHERE organization_id = v_org AND status = 'ACTIVE';
    INSERT INTO trial_events (
        trial_event_id, organization_id, trial_grant_id, actor_id,
        event_type, reason_code, occurred_at, idempotency_key
    )
    SELECT
        'trial-event-' || md5(trial_grant_id || ':converted'),
        organization_id, trial_grant_id, p_actor_id,
        'CONVERTED', 'PAID_SUBSCRIPTION_ACTIVATED', now(),
        trial_grant_id || ':converted'
      FROM trial_grants
     WHERE organization_id = v_org AND status = 'CONVERTED'
    ON CONFLICT (organization_id, idempotency_key) DO NOTHING;
    UPDATE subscriptions
       SET status = 'CONVERTED', state_version = state_version + 1, updated_at = now()
     WHERE organization_id = v_org AND billing_period = 'TRIAL' AND status = 'TRIALING';
    UPDATE quota_allocations
       SET status = 'CLOSED', allocation_version = allocation_version + 1, updated_at = now()
     WHERE organization_id = v_org AND plan_id = 'elmos-free-trial' AND status = 'ACTIVE';
END;
$$;

CREATE OR REPLACE FUNCTION elmos_grant_trial(
    p_trial_grant_id varchar,
    p_subscription_id varchar,
    p_quota_allocation_id varchar,
    p_actor_id varchar,
    p_verified_subject_hash char(64),
    p_idempotency_key varchar
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    v_org varchar := elmos_current_organization_id();
    v_plan self_service_pricing_plan_versions%ROWTYPE;
    v_start timestamptz := now();
    v_end timestamptz := now() + interval '14 days';
BEGIN
    IF p_verified_subject_hash !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'TRIAL_VERIFIED_SUBJECT_INVALID';
    END IF;
    SELECT * INTO v_plan
      FROM self_service_pricing_plan_versions
     WHERE catalog_version = '2026-07-28.2' AND plan_id = 'elmos-free-trial';
    IF EXISTS (SELECT 1 FROM trial_grants WHERE organization_id = v_org) THEN
        IF EXISTS (
            SELECT 1 FROM trial_grants
             WHERE organization_id = v_org AND idempotency_key = p_idempotency_key
        ) THEN RETURN; END IF;
        RAISE EXCEPTION 'TRIAL_ALREADY_USED';
    END IF;

    INSERT INTO subscriptions (
        subscription_id, organization_id, schema_version, status, external_ref,
        idempotency_key, payload, catalog_version, plan_id, actor_id, billing_period,
        currency, price_minor, current_period_start, current_period_end, state_version
    ) VALUES (
        p_subscription_id, v_org, '2.0', 'TRIALING', p_trial_grant_id,
        p_idempotency_key || ':subscription', '{}'::jsonb, v_plan.catalog_version,
        v_plan.plan_id, p_actor_id, v_plan.billing_period, v_plan.currency,
        v_plan.price_minor, v_start, v_end, 1
    );
    INSERT INTO quota_allocations (
        quota_allocation_id, organization_id, schema_version, status, external_ref,
        idempotency_key, payload, subscription_id, plan_id, catalog_version,
        period_start, period_end, token_limit, credit_limit
    ) VALUES (
        p_quota_allocation_id, v_org, '2.0', 'ACTIVE', p_trial_grant_id,
        p_idempotency_key || ':allowance', '{}'::jsonb, p_subscription_id,
        v_plan.plan_id, v_plan.catalog_version, v_start, v_end,
        v_plan.token_limit, v_plan.credit_limit
    );
    INSERT INTO trial_grants (
        trial_grant_id, organization_id, actor_id, verified_subject_hash,
        subscription_id, catalog_version, plan_id, status, starts_at, ends_at,
        idempotency_key
    ) VALUES (
        p_trial_grant_id, v_org, p_actor_id, p_verified_subject_hash,
        p_subscription_id, v_plan.catalog_version, v_plan.plan_id, 'ACTIVE',
        v_start, v_end, p_idempotency_key
    );
    INSERT INTO trial_events (
        trial_event_id, organization_id, trial_grant_id, actor_id, event_type,
        reason_code, occurred_at, idempotency_key
    ) VALUES (
        p_trial_grant_id || ':granted', v_org, p_trial_grant_id, p_actor_id,
        'GRANTED', 'VERIFIED_ORGANIZATION_ELIGIBLE', v_start,
        p_idempotency_key || ':trial-event'
    );
END;
$$;

CREATE OR REPLACE FUNCTION elmos_resolve_payment_reconciliation(
    p_case_id varchar,
    p_actor_id varchar,
    p_resolution_status varchar,
    p_resolution_ref varchar,
    p_idempotency_key varchar
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    v_org varchar := elmos_current_organization_id();
    v_case payment_reconciliation_cases%ROWTYPE;
    v_existing payment_reconciliation_case_events%ROWTYPE;
BEGIN
    IF p_resolution_status NOT IN ('RESOLVED', 'REJECTED') THEN
        RAISE EXCEPTION 'PAYMENT_RECONCILIATION_RESOLUTION_INVALID';
    END IF;
    IF p_resolution_ref IS NULL OR length(trim(p_resolution_ref)) < 8 THEN
        RAISE EXCEPTION 'PAYMENT_RECONCILIATION_REFERENCE_INVALID';
    END IF;

    SELECT * INTO v_existing
      FROM payment_reconciliation_case_events
     WHERE organization_id = v_org AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.payment_reconciliation_case_id <> p_case_id
           OR v_existing.event_type <> p_resolution_status
           OR v_existing.resolution_ref <> p_resolution_ref THEN
            RAISE EXCEPTION 'PAYMENT_RECONCILIATION_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN;
    END IF;

    SELECT * INTO v_case
      FROM payment_reconciliation_cases
     WHERE organization_id = v_org
       AND payment_reconciliation_case_id = p_case_id
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'PAYMENT_RECONCILIATION_CASE_NOT_FOUND'; END IF;
    IF v_case.status <> 'OPEN' THEN
        RAISE EXCEPTION 'PAYMENT_RECONCILIATION_CASE_ALREADY_CLOSED';
    END IF;

    UPDATE payment_reconciliation_cases
       SET status = p_resolution_status,
           resolved_at = now(),
           resolver_actor_id = p_actor_id,
           resolution_ref = p_resolution_ref
     WHERE payment_reconciliation_case_id = p_case_id;
    INSERT INTO payment_reconciliation_case_events (
        payment_reconciliation_case_event_id, organization_id,
        payment_reconciliation_case_id, actor_id, event_type,
        resolution_ref, occurred_at, idempotency_key
    ) VALUES (
        'recon-event-' || md5(p_case_id || ':' || p_idempotency_key),
        v_org, p_case_id, p_actor_id, p_resolution_status,
        p_resolution_ref, now(), p_idempotency_key
    );
END;
$$;

CREATE OR REPLACE FUNCTION elmos_expire_current_trial()
RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE
    v_org varchar := elmos_current_organization_id();
    v_grant trial_grants%ROWTYPE;
BEGIN
    SELECT * INTO v_grant
      FROM trial_grants
     WHERE organization_id = v_org AND status = 'ACTIVE' AND ends_at <= now()
     FOR UPDATE;
    IF NOT FOUND THEN RETURN false; END IF;

    UPDATE trial_grants
       SET status = 'EXPIRED', updated_at = now()
     WHERE trial_grant_id = v_grant.trial_grant_id;
    UPDATE subscriptions
       SET status = 'EXPIRED', state_version = state_version + 1, updated_at = now()
     WHERE organization_id = v_org AND subscription_id = v_grant.subscription_id
       AND status = 'TRIALING';
    UPDATE quota_allocations
       SET status = 'EXPIRED', allocation_version = allocation_version + 1, updated_at = now()
     WHERE organization_id = v_org AND subscription_id = v_grant.subscription_id
       AND status = 'ACTIVE';
    INSERT INTO trial_events (
        trial_event_id, organization_id, trial_grant_id, actor_id,
        event_type, reason_code, occurred_at, idempotency_key
    ) VALUES (
        'trial-event-' || md5(v_grant.trial_grant_id || ':expired'),
        v_org, v_grant.trial_grant_id, v_grant.actor_id,
        'EXPIRED', 'TRIAL_TERM_ENDED', now(), v_grant.trial_grant_id || ':expired'
    ) ON CONFLICT (organization_id, idempotency_key) DO NOTHING;
    INSERT INTO subscription_events (
        subscription_event_id, organization_id, schema_version, status,
        idempotency_key, payload, subscription_id, actor_id, event_type,
        effective_at, event_version
    ) VALUES (
        'sub-event-' || md5(v_grant.subscription_id || ':expired'),
        v_org, '2.0', 'APPLIED', v_grant.subscription_id || ':expired',
        '{}'::jsonb, v_grant.subscription_id, v_grant.actor_id,
        'EXPIRED', now(), 1
    ) ON CONFLICT (organization_id, idempotency_key) DO NOTHING;
    RETURN true;
END;
$$;

DO $$
DECLARE
    v_function record;
BEGIN
    FOR v_function IN
        SELECT p.oid::regprocedure AS signature
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND p.proname IN (
               'elmos_enqueue_usage_alerts',
               'elmos_current_organization_id',
               'elmos_reserve_usage',
               'elmos_settle_usage',
               'elmos_release_usage',
               'elmos_correct_usage',
               'elmos_activate_subscription_period',
               'elmos_grant_trial',
               'elmos_resolve_payment_reconciliation',
               'elmos_expire_current_trial'
           )
    LOOP
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', v_function.signature);
    END LOOP;
END;
$$;
