-- Forward-only readiness repair for catalog 2026-09-08.1.
--
-- The catalog artifact gained commercial one-time products without changing
-- the three subscription plans. Append the current catalog snapshot so the
-- database health gate, checkout rows, grants, and renewals all bind the same
-- immutable version; never rewrite the V49 or V83 migration history.

INSERT INTO self_service_pricing_plan_versions (
    catalog_version, plan_id, currency, price_minor, billing_period, allowance_window,
    token_limit, credit_limit, active_project_limit, concurrent_job_limit,
    artifact_retention_days, effective_from, source_ref, status
) VALUES
    ('2026-09-08.1', 'elmos-free-trial', 'CNY', 0, 'TRIAL', 'TRIAL_TERM',
     2000000, 60, 1, 1, 7, '2026-07-28T00:00:00Z',
     'contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json', 'DRAFT'),
    ('2026-09-08.1', 'elmos-pro-monthly', 'CNY', 12900, 'MONTH', 'MONTHLY',
     20000000, 600, 10, 3, 30, '2026-07-28T00:00:00Z',
     'contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json', 'DRAFT'),
    ('2026-09-08.1', 'elmos-pro-annual', 'CNY', 129000, 'YEAR', 'MONTHLY',
     25000000, 750, 25, 5, 90, '2026-07-28T00:00:00Z',
     'contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json', 'DRAFT');

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
     WHERE catalog_version = '2026-09-08.1' AND plan_id = p_plan_id;
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
     WHERE catalog_version = '2026-09-08.1' AND plan_id = 'elmos-free-trial';
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
