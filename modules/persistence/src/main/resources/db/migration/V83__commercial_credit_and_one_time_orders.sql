-- Commercial purchase closure: purchasable Credit packs, one-project generation
-- entitlements, append-only credit history, and atomic generation funding.
--
-- This migration is forward-only.  All customer-scoped tables use FORCE RLS;
-- the only cross-tenant table is the minimal callback directory.

ALTER TABLE usage_reservations
    ADD COLUMN project_id varchar(128),
    ADD COLUMN job_id varchar(128),
    ADD COLUMN model varchar(160);
ALTER TABLE usage_events
    ADD COLUMN project_id varchar(128),
    ADD COLUMN job_id varchar(128),
    ADD COLUMN model varchar(160);
ALTER TABLE usage_ledger_entries
    ADD COLUMN project_id varchar(128),
    ADD COLUMN job_id varchar(128),
    ADD COLUMN model varchar(160);

-- V54 claimed an event before executing its customer-visible effect. A crash
-- after that insert made all provider retries look like completed duplicates.
ALTER TABLE payment_callback_receipts
    ADD COLUMN processing_status varchar(16) NOT NULL DEFAULT 'COMPLETED'
        CHECK (processing_status IN ('PROCESSING', 'COMPLETED', 'FAILED')),
    ADD COLUMN attempt_count integer NOT NULL DEFAULT 1 CHECK (attempt_count > 0),
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();

-- Production runtime records reasoning tokens as an independent provider fact.
-- Keep the self-service vocabulary lossless instead of folding them into OUTPUT.
ALTER TABLE usage_events DROP CONSTRAINT usage_events_meter_shape;
ALTER TABLE usage_events ADD CONSTRAINT usage_events_meter_shape CHECK (
    meter_id IS NULL OR (
        meter_id IN ('model-token-v1', 'platform-credit-v1')
        AND quantity > 0
        AND operation_key IS NOT NULL
        AND occurred_at IS NOT NULL
        AND recorded_at IS NOT NULL
        AND reconciliation_status IN ('PENDING', 'RECONCILED', 'REJECTED')
        AND (
            (meter_id = 'model-token-v1' AND token_class IN (
                'INPUT', 'OUTPUT', 'CACHE_READ', 'CACHE_WRITE', 'REASONING'
            ))
            OR (meter_id = 'platform-credit-v1' AND token_class IS NULL)
        )
        AND (
            provider_cost_minor IS NULL
            OR (provider_cost_minor >= 0 AND provider_cost_currency IS NOT NULL)
        )
    )
);

CREATE OR REPLACE FUNCTION elmos_reserve_usage_v2(
    p_reservation_id varchar, p_subscription_id varchar, p_actor_id varchar,
    p_idempotency_key varchar, p_operation_key varchar, p_requested_tokens numeric,
    p_requested_credits numeric, p_expires_at timestamptz, p_project_id varchar,
    p_job_id varchar, p_model varchar
) RETURNS TABLE (reservation_id varchar, decision varchar,
                 remaining_tokens numeric, remaining_credits numeric)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_result record;
    v_org varchar := elmos_current_organization_id();
    v_preexisting boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM usage_reservations
         WHERE organization_id = v_org AND idempotency_key = p_idempotency_key
    ) INTO v_preexisting;
    SELECT * INTO v_result FROM elmos_reserve_usage(
        p_reservation_id, p_subscription_id, p_actor_id, p_idempotency_key,
        p_operation_key, p_requested_tokens, p_requested_credits, p_expires_at);
    IF v_result.decision = 'RESERVED' THEN
        IF v_preexisting THEN
            PERFORM 1 FROM usage_reservations
             WHERE organization_id = v_org
               AND usage_reservation_id = v_result.reservation_id
               AND project_id IS NOT DISTINCT FROM p_project_id
               AND job_id IS NOT DISTINCT FROM p_job_id
               AND model IS NOT DISTINCT FROM p_model;
        ELSE
            UPDATE usage_reservations
               SET project_id = p_project_id, job_id = p_job_id, model = p_model
             WHERE organization_id = v_org
               AND usage_reservation_id = v_result.reservation_id;
        END IF;
        IF NOT FOUND THEN RAISE EXCEPTION 'USAGE_RESERVATION_DIMENSION_CONFLICT'; END IF;
    END IF;
    RETURN QUERY SELECT v_result.reservation_id, v_result.decision,
        v_result.remaining_tokens, v_result.remaining_credits;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_settle_usage_v2(
    p_actor_id varchar, p_reservation_id varchar, p_event_prefix varchar,
    p_actual_tokens numeric, p_actual_credits numeric, p_token_class varchar,
    p_provider varchar, p_provider_receipt_ref varchar,
    p_provider_cost_currency char(3), p_provider_cost_minor numeric,
    p_occurred_at timestamptz
) RETURNS TABLE (reservation_id varchar, status varchar, consumed_tokens numeric,
                 consumed_credits numeric, remaining_tokens numeric,
                 remaining_credits numeric)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE v_org varchar := elmos_current_organization_id();
BEGIN
    PERFORM 1 FROM usage_reservations
     WHERE organization_id = v_org AND usage_reservation_id = p_reservation_id
       AND actor_id = p_actor_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'USAGE_RESERVATION_NOT_FOUND'; END IF;
    RETURN QUERY SELECT * FROM elmos_settle_usage(
        p_reservation_id, p_event_prefix, p_actual_tokens, p_actual_credits,
        p_token_class, p_provider, p_provider_receipt_ref,
        p_provider_cost_currency, p_provider_cost_minor, p_occurred_at);
END;
$$;

CREATE OR REPLACE FUNCTION elmos_release_usage_v2(
    p_actor_id varchar, p_reservation_id varchar, p_reason_code varchar
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE v_org varchar := elmos_current_organization_id();
BEGIN
    PERFORM 1 FROM usage_reservations
     WHERE organization_id = v_org AND usage_reservation_id = p_reservation_id
       AND actor_id = p_actor_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'USAGE_RESERVATION_NOT_FOUND'; END IF;
    PERFORM elmos_release_usage(p_reservation_id, p_reason_code);
END;
$$;

CREATE OR REPLACE FUNCTION elmos_usage_event_dimensions()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.reservation_id IS NOT NULL THEN
        SELECT project_id, job_id, model INTO NEW.project_id, NEW.job_id, NEW.model
          FROM usage_reservations WHERE usage_reservation_id = NEW.reservation_id;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER usage_events_dimensions
BEFORE INSERT ON usage_events
FOR EACH ROW EXECUTE FUNCTION elmos_usage_event_dimensions();

CREATE OR REPLACE FUNCTION elmos_usage_ledger_dimensions()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.usage_event_id IS NOT NULL THEN
        SELECT project_id, job_id, model INTO NEW.project_id, NEW.job_id, NEW.model
          FROM usage_events WHERE usage_event_id = NEW.usage_event_id;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER usage_ledger_dimensions
BEFORE INSERT ON usage_ledger_entries
FOR EACH ROW EXECUTE FUNCTION elmos_usage_ledger_dimensions();

CREATE TABLE commercial_products (
    sku varchar(96) PRIMARY KEY,
    product_type varchar(32) NOT NULL CHECK (product_type IN ('CREDIT_PACK', 'PROJECT_GENERATION_ONCE')),
    catalog_version varchar(64) NOT NULL,
    display_name varchar(160) NOT NULL,
    currency char(3) NOT NULL CHECK (currency = 'CNY'),
    amount_minor numeric(19,0) NOT NULL CHECK (amount_minor > 0 AND amount_minor = trunc(amount_minor)),
    credit_quantity numeric(19,0) NOT NULL DEFAULT 0 CHECK (credit_quantity >= 0 AND credit_quantity = trunc(credit_quantity)),
    generation_runs integer NOT NULL DEFAULT 0 CHECK (generation_runs >= 0),
    expiry_days integer NOT NULL CHECK (expiry_days BETWEEN 1 AND 3650),
    status varchar(16) NOT NULL CHECK (status IN ('DRAFT', 'ACTIVE', 'RETIRED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((product_type = 'CREDIT_PACK' AND credit_quantity > 0 AND generation_runs = 0)
        OR (product_type = 'PROJECT_GENERATION_ONCE' AND credit_quantity = 0 AND generation_runs = 1))
);

INSERT INTO commercial_products (
    sku, product_type, catalog_version, display_name, currency, amount_minor,
    credit_quantity, generation_runs, expiry_days, status
) VALUES
    ('elmos-credit-500', 'CREDIT_PACK', '2026-09-08.1', '500 Credits', 'CNY', 9900, 500, 0, 365, 'DRAFT'),
    ('elmos-project-generation-once', 'PROJECT_GENERATION_ONCE', '2026-09-08.1',
     '单项目生成一次', 'CNY', 3900, 0, 1, 30, 'DRAFT');

CREATE OR REPLACE FUNCTION elmos_commercial_products_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'ELMOS_COMMERCIAL_PRODUCT_IMMUTABLE';
END;
$$;

CREATE TRIGGER commercial_products_immutable
BEFORE UPDATE OR DELETE ON commercial_products
FOR EACH ROW EXECUTE FUNCTION elmos_commercial_products_immutable();

CREATE TABLE commercial_orders (
    order_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    actor_id varchar(128) NOT NULL,
    order_type varchar(32) NOT NULL CHECK (order_type IN ('CREDIT_PACK', 'PROJECT_GENERATION_ONCE')),
    sku varchar(96) NOT NULL REFERENCES commercial_products(sku),
    catalog_version varchar(64) NOT NULL,
    project_id varchar(128),
    currency char(3) NOT NULL CHECK (currency = 'CNY'),
    amount_minor numeric(19,0) NOT NULL CHECK (amount_minor > 0 AND amount_minor = trunc(amount_minor)),
    credit_quantity numeric(19,0) NOT NULL DEFAULT 0 CHECK (credit_quantity >= 0 AND credit_quantity = trunc(credit_quantity)),
    provider varchar(32) NOT NULL CHECK (provider IN ('ALIPAY_CHECKOUT', 'WECHAT_PAY_NATIVE')),
    out_trade_no varchar(96) NOT NULL,
    provider_transaction_ref varchar(255),
    failure_code varchar(96),
    status varchar(24) NOT NULL CHECK (status IN (
        'CREATED', 'PENDING_PAYMENT', 'PAID', 'FULFILLED', 'EXPIRED', 'FAILED', 'RECONCILIATION_REQUIRED')),
    idempotency_key varchar(160) NOT NULL,
    request_hash char(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    paid_at timestamptz,
    fulfilled_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key),
    UNIQUE (provider, out_trade_no),
    CHECK ((order_type = 'CREDIT_PACK' AND project_id IS NULL AND credit_quantity > 0)
        OR (order_type = 'PROJECT_GENERATION_ONCE' AND project_id IS NOT NULL AND credit_quantity = 0)),
    CHECK (expires_at > created_at)
);

CREATE TABLE commercial_order_directory (
    out_trade_no varchar(96) PRIMARY KEY,
    order_id varchar(96) NOT NULL UNIQUE,
    organization_id varchar(96) NOT NULL,
    order_type varchar(32) NOT NULL,
    amount_minor numeric(19,0) NOT NULL,
    status varchar(24) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION elmos_sync_commercial_order_directory()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    INSERT INTO public.commercial_order_directory (
        out_trade_no, order_id, organization_id, order_type, amount_minor, status)
    VALUES (NEW.out_trade_no, NEW.order_id, NEW.organization_id,
            NEW.order_type, NEW.amount_minor, NEW.status)
    ON CONFLICT (out_trade_no) DO UPDATE
       SET status = EXCLUDED.status, updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER commercial_orders_directory_sync
AFTER INSERT OR UPDATE OF status ON commercial_orders
FOR EACH ROW EXECUTE FUNCTION elmos_sync_commercial_order_directory();

CREATE TABLE commercial_credit_accounts (
    organization_id varchar(96) PRIMARY KEY REFERENCES organizations(organization_id),
    balance numeric(19,0) NOT NULL DEFAULT 0 CHECK (balance >= 0 AND balance = trunc(balance)),
    reserved numeric(19,0) NOT NULL DEFAULT 0 CHECK (reserved >= 0 AND reserved = trunc(reserved)),
    status varchar(16) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'FROZEN', 'CLOSED')),
    account_version bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (reserved <= balance)
);

CREATE TABLE commercial_credit_lots (
    lot_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    source_order_id varchar(96) NOT NULL UNIQUE,
    granted numeric(19,0) NOT NULL CHECK (granted > 0),
    available numeric(19,0) NOT NULL CHECK (available >= 0),
    reserved numeric(19,0) NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    consumed numeric(19,0) NOT NULL DEFAULT 0 CHECK (consumed >= 0),
    expires_at timestamptz NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DEPLETED', 'EXPIRED', 'REVOKED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (available + reserved + consumed = granted)
);

CREATE TABLE commercial_credit_ledger_entries (
    ledger_entry_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    actor_id varchar(128) NOT NULL,
    direction varchar(8) NOT NULL CHECK (direction IN ('CREDIT', 'DEBIT')),
    quantity numeric(19,0) NOT NULL CHECK (quantity > 0 AND quantity = trunc(quantity)),
    balance_after numeric(19,0) NOT NULL CHECK (balance_after >= 0),
    entry_type varchar(32) NOT NULL CHECK (entry_type IN ('PURCHASE', 'GENERATION', 'REFUND', 'CORRECTION')),
    source_order_id varchar(96),
    project_id varchar(128),
    job_id varchar(128),
    idempotency_key varchar(160) NOT NULL,
    expires_at timestamptz,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (organization_id, idempotency_key)
);

CREATE OR REPLACE FUNCTION elmos_commercial_credit_ledger_append_only()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'ELMOS_CREDIT_LEDGER_APPEND_ONLY';
END;
$$;

CREATE TRIGGER commercial_credit_ledger_append_only
BEFORE UPDATE OR DELETE ON commercial_credit_ledger_entries
FOR EACH ROW EXECUTE FUNCTION elmos_commercial_credit_ledger_append_only();

CREATE TABLE project_generation_entitlements (
    entitlement_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    actor_id varchar(128) NOT NULL,
    source_order_id varchar(96) NOT NULL UNIQUE,
    project_id varchar(128) NOT NULL,
    status varchar(16) NOT NULL CHECK (status IN ('AVAILABLE', 'HELD', 'CONSUMED', 'EXPIRED', 'REVOKED')),
    held_by_job_id varchar(128),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((status = 'HELD' AND held_by_job_id IS NOT NULL)
        OR status <> 'HELD')
);

CREATE TABLE commercial_credit_reservations (
    reservation_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    actor_id varchar(128) NOT NULL,
    project_id varchar(128) NOT NULL,
    job_id varchar(128) NOT NULL,
    requested_credits numeric(19,0) NOT NULL CHECK (requested_credits > 0 AND requested_credits = trunc(requested_credits)),
    settled_credits numeric(19,0) CHECK (settled_credits >= 0 AND settled_credits = trunc(settled_credits)),
    funding_source varchar(24) NOT NULL CHECK (funding_source IN ('CREDIT_ACCOUNT', 'ONE_TIME_ENTITLEMENT')),
    entitlement_id varchar(96),
    status varchar(16) NOT NULL CHECK (status IN ('HELD', 'SETTLED', 'RELEASED', 'EXPIRED')),
    idempotency_key varchar(160) NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    settled_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key),
    UNIQUE (organization_id, job_id),
    CHECK ((funding_source = 'ONE_TIME_ENTITLEMENT' AND entitlement_id IS NOT NULL)
        OR (funding_source = 'CREDIT_ACCOUNT' AND entitlement_id IS NULL))
);

CREATE TABLE commercial_credit_reservation_lots (
    reservation_id varchar(96) NOT NULL REFERENCES commercial_credit_reservations(reservation_id),
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    lot_id varchar(96) NOT NULL REFERENCES commercial_credit_lots(lot_id),
    quantity numeric(19,0) NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (reservation_id, lot_id)
);

CREATE OR REPLACE FUNCTION elmos_commercial_credit_balance_guard()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('app.commercial_credit_posting', true) <> 'on' THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_BALANCE_DIRECT_MUTATION_DENIED';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER commercial_credit_balance_guard
BEFORE INSERT OR UPDATE OR DELETE ON commercial_credit_accounts
FOR EACH ROW EXECUTE FUNCTION elmos_commercial_credit_balance_guard();

CREATE OR REPLACE FUNCTION elmos_commercial_create_order(
    p_order_id varchar, p_actor_id varchar, p_sku varchar, p_project_id varchar,
    p_provider varchar, p_out_trade_no varchar, p_idempotency_key varchar,
    p_request_hash char(64), p_ttl_seconds integer
) RETURNS varchar LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_org varchar := elmos_current_organization_id();
    v_product commercial_products%ROWTYPE;
    v_existing commercial_orders%ROWTYPE;
BEGIN
    IF p_ttl_seconds < 300 OR p_ttl_seconds > 3600 THEN
        RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_TTL_INVALID';
    END IF;
    SELECT * INTO v_existing FROM commercial_orders
     WHERE organization_id = v_org AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.actor_id <> p_actor_id OR v_existing.sku <> p_sku
           OR v_existing.project_id IS DISTINCT FROM p_project_id
           OR v_existing.request_hash <> p_request_hash THEN
            RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.order_id;
    END IF;
    SELECT * INTO v_product FROM commercial_products WHERE sku = p_sku;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_COMMERCIAL_PRODUCT_UNKNOWN'; END IF;
    -- DRAFT products can be exercised by database qualification, but the HTTP
    -- controller independently requires the catalog publication gate.
    IF v_product.product_type = 'PROJECT_GENERATION_ONCE'
       AND (p_project_id IS NULL OR p_project_id = '') THEN
        RAISE EXCEPTION 'ELMOS_COMMERCIAL_PROJECT_REQUIRED';
    END IF;
    INSERT INTO commercial_orders (
        order_id, organization_id, actor_id, order_type, sku, catalog_version,
        project_id, currency, amount_minor, credit_quantity, provider,
        out_trade_no, status, idempotency_key, request_hash, expires_at
    ) VALUES (
        p_order_id, v_org, p_actor_id, v_product.product_type, v_product.sku,
        v_product.catalog_version, nullif(p_project_id, ''), v_product.currency,
        v_product.amount_minor, v_product.credit_quantity, p_provider,
        p_out_trade_no, 'CREATED', p_idempotency_key, p_request_hash,
        now() + make_interval(secs => p_ttl_seconds));
    RETURN p_order_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_commercial_fulfill_order(
    p_organization_id varchar, p_order_id varchar, p_provider_transaction_ref varchar,
    p_actor_id varchar
) RETURNS varchar
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_previous text := current_setting('app.organization_id', true);
    v_order public.commercial_orders%ROWTYPE;
    v_product public.commercial_products%ROWTYPE;
    v_entry_id varchar;
BEGIN
    IF p_organization_id IS NULL OR p_organization_id = '' THEN
        RAISE EXCEPTION 'ELMOS_COMMERCIAL_TENANT_REQUIRED';
    END IF;
    PERFORM set_config('app.organization_id', p_organization_id, true);
    SELECT * INTO v_order FROM public.commercial_orders
     WHERE organization_id = p_organization_id AND order_id = p_order_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_NOT_FOUND'; END IF;
    IF v_order.status = 'FULFILLED' THEN
        IF v_order.provider_transaction_ref IS DISTINCT FROM p_provider_transaction_ref THEN
            RAISE EXCEPTION 'ELMOS_COMMERCIAL_FULFILLMENT_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN p_order_id;
    END IF;
    IF v_order.status NOT IN ('CREATED', 'PENDING_PAYMENT', 'PAID') THEN
        RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_NOT_FULFILLABLE';
    END IF;
    -- A provider may confirm after our checkout TTL. Acknowledge and retain the
    -- money fact, but do not mint Credits/an entitlement automatically: this
    -- requires an explicit refund-or-fulfill reconciliation decision.
    IF v_order.expires_at <= now() AND v_order.status IN ('CREATED', 'PENDING_PAYMENT') THEN
        UPDATE public.commercial_orders
           SET status = 'RECONCILIATION_REQUIRED',
               provider_transaction_ref = p_provider_transaction_ref,
               paid_at = coalesce(paid_at, now()),
               failure_code = 'PAYMENT_AFTER_LOCAL_EXPIRY', updated_at = now()
         WHERE order_id = p_order_id AND organization_id = p_organization_id;
        IF v_previous IS NOT NULL THEN
            PERFORM set_config('app.organization_id', v_previous, true);
        END IF;
        RETURN p_order_id;
    END IF;
    SELECT * INTO v_product FROM public.commercial_products WHERE sku = v_order.sku;
    IF v_order.order_type = 'CREDIT_PACK' THEN
        PERFORM set_config('app.commercial_credit_posting', 'on', true);
        INSERT INTO public.commercial_credit_accounts (organization_id, balance)
        VALUES (p_organization_id, v_order.credit_quantity)
        ON CONFLICT (organization_id) DO UPDATE
           SET balance = public.commercial_credit_accounts.balance + EXCLUDED.balance,
               account_version = public.commercial_credit_accounts.account_version + 1,
               updated_at = now();
        v_entry_id := 'credit-purchase-' || md5(p_order_id);
        INSERT INTO public.commercial_credit_ledger_entries (
            ledger_entry_id, organization_id, actor_id, direction, quantity,
            balance_after, entry_type, source_order_id, idempotency_key, expires_at)
        SELECT v_entry_id, p_organization_id, v_order.actor_id, 'CREDIT',
               v_order.credit_quantity, balance, 'PURCHASE', p_order_id,
               'purchase:' || p_order_id, now() + make_interval(days => v_product.expiry_days)
          FROM public.commercial_credit_accounts WHERE organization_id = p_organization_id
        ON CONFLICT (organization_id, idempotency_key) DO NOTHING;
        INSERT INTO public.commercial_credit_lots (
            lot_id, organization_id, source_order_id, granted, available, expires_at)
        VALUES ('credit-lot-' || md5(p_order_id), p_organization_id, p_order_id,
                v_order.credit_quantity, v_order.credit_quantity,
                now() + make_interval(days => v_product.expiry_days))
        ON CONFLICT (source_order_id) DO NOTHING;
    ELSE
        INSERT INTO public.project_generation_entitlements (
            entitlement_id, organization_id, actor_id, source_order_id,
            project_id, status, expires_at)
        VALUES ('entitlement-' || md5(p_order_id), p_organization_id, v_order.actor_id,
                p_order_id, v_order.project_id, 'AVAILABLE',
                now() + make_interval(days => v_product.expiry_days))
        ON CONFLICT (source_order_id) DO NOTHING;
    END IF;
    UPDATE public.commercial_orders
       SET status = 'FULFILLED', provider_transaction_ref = p_provider_transaction_ref,
           paid_at = coalesce(paid_at, now()), fulfilled_at = coalesce(fulfilled_at, now()),
           updated_at = now()
     WHERE order_id = p_order_id AND organization_id = p_organization_id;
    PERFORM set_config('app.commercial_credit_posting', '', true);
    IF v_previous IS NOT NULL THEN PERFORM set_config('app.organization_id', v_previous, true); END IF;
    RETURN p_order_id;
EXCEPTION WHEN OTHERS THEN
    PERFORM set_config('app.commercial_credit_posting', '', true);
    IF v_previous IS NOT NULL THEN PERFORM set_config('app.organization_id', v_previous, true); END IF;
    RAISE;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_commercial_mark_order_handoff(
    p_order_id varchar, p_actor_id varchar
) RETURNS varchar LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE v_org varchar := elmos_current_organization_id(); v_status varchar;
BEGIN
    UPDATE commercial_orders
       SET status = 'PENDING_PAYMENT', failure_code = NULL, updated_at = now()
     WHERE organization_id = v_org AND order_id = p_order_id
       AND actor_id = p_actor_id AND status = 'CREATED'
     RETURNING status INTO v_status;
    IF FOUND THEN RETURN v_status; END IF;
    SELECT status INTO v_status FROM commercial_orders
     WHERE organization_id = v_org AND order_id = p_order_id AND actor_id = p_actor_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_NOT_FOUND'; END IF;
    IF v_status IN ('PENDING_PAYMENT', 'FULFILLED') THEN RETURN v_status; END IF;
    RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_HANDOFF_INVALID';
END;
$$;

CREATE OR REPLACE FUNCTION elmos_commercial_mark_order_prepare_failed(
    p_order_id varchar, p_actor_id varchar, p_outcome_unknown boolean,
    p_failure_code varchar
) RETURNS varchar LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE v_org varchar := elmos_current_organization_id(); v_status varchar;
BEGIN
    IF p_failure_code IS NULL OR p_failure_code = '' OR length(p_failure_code) > 96 THEN
        RAISE EXCEPTION 'ELMOS_COMMERCIAL_FAILURE_CODE_INVALID';
    END IF;
    UPDATE commercial_orders
       SET status = CASE WHEN p_outcome_unknown THEN 'RECONCILIATION_REQUIRED' ELSE 'FAILED' END,
           failure_code = p_failure_code, updated_at = now()
     WHERE organization_id = v_org AND order_id = p_order_id
       AND actor_id = p_actor_id AND status IN ('CREATED', 'PENDING_PAYMENT')
     RETURNING status INTO v_status;
    IF FOUND THEN RETURN v_status; END IF;
    SELECT status INTO v_status FROM commercial_orders
     WHERE organization_id = v_org AND order_id = p_order_id AND actor_id = p_actor_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_NOT_FOUND'; END IF;
    IF v_status = 'FULFILLED' THEN RETURN v_status; END IF;
    RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_PREPARE_FAILURE_INVALID';
END;
$$;

CREATE OR REPLACE FUNCTION elmos_commercial_reserve_generation(
    p_reservation_id varchar, p_actor_id varchar, p_project_id varchar, p_job_id varchar,
    p_requested_credits numeric, p_idempotency_key varchar, p_ttl_seconds integer
) RETURNS TABLE (reservation_id varchar, decision varchar, funding_source varchar, remaining_credits numeric)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_org varchar := elmos_current_organization_id();
    v_existing commercial_credit_reservations%ROWTYPE;
    v_entitlement project_generation_entitlements%ROWTYPE;
    v_account commercial_credit_accounts%ROWTYPE;
    v_lot commercial_credit_lots%ROWTYPE;
    v_expired numeric := 0;
    v_needed numeric;
    v_take numeric;
BEGIN
    IF p_requested_credits <= 0 OR p_requested_credits <> trunc(p_requested_credits)
       OR p_ttl_seconds < 30 OR p_ttl_seconds > 3600 THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_RESERVATION_INVALID';
    END IF;
    SELECT * INTO v_existing FROM commercial_credit_reservations
     WHERE organization_id = v_org AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.actor_id <> p_actor_id OR v_existing.project_id <> p_project_id
           OR v_existing.job_id <> p_job_id OR v_existing.requested_credits <> p_requested_credits THEN
            RAISE EXCEPTION 'ELMOS_CREDIT_RESERVATION_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN QUERY SELECT v_existing.reservation_id, v_existing.status,
            v_existing.funding_source,
            coalesce((SELECT balance - reserved FROM commercial_credit_accounts
                       WHERE organization_id = v_org), 0);
        RETURN;
    END IF;
    SELECT * INTO v_entitlement FROM project_generation_entitlements
     WHERE organization_id = v_org AND actor_id = p_actor_id AND project_id = p_project_id
       AND status = 'AVAILABLE' AND expires_at > now()
     ORDER BY expires_at, created_at LIMIT 1 FOR UPDATE SKIP LOCKED;
    IF FOUND THEN
        UPDATE project_generation_entitlements
           SET status = 'HELD', held_by_job_id = p_job_id, updated_at = now()
         WHERE entitlement_id = v_entitlement.entitlement_id;
        INSERT INTO commercial_credit_reservations (
            reservation_id, organization_id, actor_id, project_id, job_id,
            requested_credits, funding_source, entitlement_id, status,
            idempotency_key, expires_at)
        VALUES (p_reservation_id, v_org, p_actor_id, p_project_id, p_job_id,
                p_requested_credits, 'ONE_TIME_ENTITLEMENT', v_entitlement.entitlement_id,
                'HELD', p_idempotency_key, now() + make_interval(secs => p_ttl_seconds));
        RETURN QUERY SELECT p_reservation_id, 'RESERVED'::varchar,
            'ONE_TIME_ENTITLEMENT'::varchar, 0::numeric;
        RETURN;
    END IF;
    -- Expire only unreserved quantities. A held reservation keeps its exact lot
    -- until it is settled or released, so expiry cannot change a decision after admission.
    FOR v_lot IN SELECT * FROM commercial_credit_lots
        WHERE organization_id = v_org AND status = 'ACTIVE'
          AND expires_at <= now() FOR UPDATE
    LOOP
        v_expired := v_expired + v_lot.available;
        UPDATE commercial_credit_lots
           SET available = 0,
               consumed = consumed + v_lot.available,
               status = CASE WHEN v_lot.reserved = 0 THEN 'EXPIRED' ELSE status END,
               updated_at = now()
         WHERE lot_id = v_lot.lot_id;
    END LOOP;
    IF v_expired > 0 THEN
        PERFORM set_config('app.commercial_credit_posting', 'on', true);
        UPDATE commercial_credit_accounts SET balance = balance - v_expired,
            account_version = account_version + 1, updated_at = now()
         WHERE organization_id = v_org;
        PERFORM set_config('app.commercial_credit_posting', '', true);
    END IF;
    SELECT * INTO v_account FROM commercial_credit_accounts
     WHERE organization_id = v_org AND status = 'ACTIVE' FOR UPDATE;
    IF NOT FOUND OR v_account.balance - v_account.reserved < p_requested_credits THEN
        RETURN QUERY SELECT p_reservation_id, 'DENY_CREDIT_LIMIT'::varchar,
            'CREDIT_ACCOUNT'::varchar,
            greatest(coalesce(v_account.balance - v_account.reserved, 0), 0);
        RETURN;
    END IF;
    PERFORM set_config('app.commercial_credit_posting', 'on', true);
    UPDATE commercial_credit_accounts
       SET reserved = reserved + p_requested_credits,
           account_version = account_version + 1, updated_at = now()
     WHERE organization_id = v_org;
    PERFORM set_config('app.commercial_credit_posting', '', true);
    INSERT INTO commercial_credit_reservations (
        reservation_id, organization_id, actor_id, project_id, job_id,
        requested_credits, funding_source, status, idempotency_key, expires_at)
    VALUES (p_reservation_id, v_org, p_actor_id, p_project_id, p_job_id,
            p_requested_credits, 'CREDIT_ACCOUNT', 'HELD', p_idempotency_key,
            now() + make_interval(secs => p_ttl_seconds));
    v_needed := p_requested_credits;
    FOR v_lot IN SELECT * FROM commercial_credit_lots
        WHERE organization_id = v_org AND status = 'ACTIVE'
          AND expires_at > now() AND available > 0
        ORDER BY expires_at, created_at FOR UPDATE
    LOOP
        EXIT WHEN v_needed = 0;
        v_take := least(v_needed, v_lot.available);
        UPDATE commercial_credit_lots
           SET available = available - v_take, reserved = reserved + v_take,
               updated_at = now() WHERE lot_id = v_lot.lot_id;
        INSERT INTO commercial_credit_reservation_lots (
            reservation_id, organization_id, lot_id, quantity)
        VALUES (p_reservation_id, v_org, v_lot.lot_id, v_take);
        v_needed := v_needed - v_take;
    END LOOP;
    IF v_needed <> 0 THEN RAISE EXCEPTION 'ELMOS_CREDIT_LOT_DRIFT'; END IF;
    RETURN QUERY SELECT p_reservation_id, 'RESERVED'::varchar, 'CREDIT_ACCOUNT'::varchar,
        v_account.balance - v_account.reserved - p_requested_credits;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_commercial_settle_generation(
    p_reservation_id varchar, p_actor_id varchar, p_actual_credits numeric
) RETURNS varchar LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_org varchar := elmos_current_organization_id();
    v_res commercial_credit_reservations%ROWTYPE;
    v_balance numeric;
    v_allocation commercial_credit_reservation_lots%ROWTYPE;
    v_remaining numeric := p_actual_credits;
    v_consume numeric;
BEGIN
    SELECT * INTO v_res FROM commercial_credit_reservations
     WHERE organization_id = v_org AND reservation_id = p_reservation_id
       AND actor_id = p_actor_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_CREDIT_RESERVATION_NOT_FOUND'; END IF;
    IF v_res.status = 'SETTLED' THEN
        IF v_res.settled_credits <> p_actual_credits THEN
            RAISE EXCEPTION 'ELMOS_CREDIT_SETTLEMENT_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_res.status;
    END IF;
    IF v_res.status <> 'HELD' OR v_res.expires_at <= now() OR p_actual_credits < 0
       OR p_actual_credits > v_res.requested_credits OR p_actual_credits <> trunc(p_actual_credits) THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_RESERVATION_NOT_SETTLEABLE';
    END IF;
    IF v_res.funding_source = 'ONE_TIME_ENTITLEMENT' THEN
        UPDATE project_generation_entitlements
           SET status = 'CONSUMED', consumed_at = now(), updated_at = now()
         WHERE entitlement_id = v_res.entitlement_id AND status = 'HELD'
           AND held_by_job_id = v_res.job_id;
    ELSE
        FOR v_allocation IN SELECT * FROM commercial_credit_reservation_lots
            WHERE organization_id = v_org AND reservation_id = p_reservation_id
            ORDER BY lot_id FOR UPDATE
        LOOP
            v_consume := least(v_remaining, v_allocation.quantity);
            UPDATE commercial_credit_lots
               SET reserved = reserved - v_allocation.quantity,
                   available = available + (v_allocation.quantity - v_consume),
                   consumed = consumed + v_consume,
                   status = CASE
                       WHEN available + (v_allocation.quantity - v_consume) = 0
                            AND reserved - v_allocation.quantity = 0 THEN 'DEPLETED'
                       ELSE status END,
                   updated_at = now()
             WHERE lot_id = v_allocation.lot_id;
            v_remaining := v_remaining - v_consume;
        END LOOP;
        IF v_remaining <> 0 THEN RAISE EXCEPTION 'ELMOS_CREDIT_LOT_DRIFT'; END IF;
        PERFORM set_config('app.commercial_credit_posting', 'on', true);
        UPDATE commercial_credit_accounts
           SET balance = balance - p_actual_credits,
               reserved = reserved - v_res.requested_credits,
               account_version = account_version + 1, updated_at = now()
         WHERE organization_id = v_org RETURNING balance INTO v_balance;
        PERFORM set_config('app.commercial_credit_posting', '', true);
        IF p_actual_credits > 0 THEN
            INSERT INTO commercial_credit_ledger_entries (
                ledger_entry_id, organization_id, actor_id, direction, quantity,
                balance_after, entry_type, project_id, job_id, idempotency_key)
            VALUES ('credit-generation-' || md5(p_reservation_id), v_org, v_res.actor_id,
                    'DEBIT', p_actual_credits, v_balance, 'GENERATION',
                    v_res.project_id, v_res.job_id, 'generation:' || p_reservation_id);
        END IF;
    END IF;
    UPDATE commercial_credit_reservations
       SET status = 'SETTLED', settled_credits = p_actual_credits,
           settled_at = now(), updated_at = now()
     WHERE reservation_id = p_reservation_id;
    RETURN 'SETTLED';
END;
$$;

CREATE OR REPLACE FUNCTION elmos_commercial_release_generation(
    p_reservation_id varchar, p_actor_id varchar
) RETURNS varchar LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_org varchar := elmos_current_organization_id();
    v_res commercial_credit_reservations%ROWTYPE;
    v_allocation commercial_credit_reservation_lots%ROWTYPE;
BEGIN
    SELECT * INTO v_res FROM commercial_credit_reservations
     WHERE organization_id = v_org AND reservation_id = p_reservation_id
       AND actor_id = p_actor_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_CREDIT_RESERVATION_NOT_FOUND'; END IF;
    IF v_res.status = 'RELEASED' THEN RETURN v_res.status; END IF;
    IF v_res.status <> 'HELD' THEN RAISE EXCEPTION 'ELMOS_CREDIT_RESERVATION_NOT_RELEASABLE'; END IF;
    IF v_res.funding_source = 'ONE_TIME_ENTITLEMENT' THEN
        UPDATE project_generation_entitlements
           SET status = CASE WHEN expires_at > now() THEN 'AVAILABLE' ELSE 'EXPIRED' END,
               held_by_job_id = NULL, updated_at = now()
         WHERE entitlement_id = v_res.entitlement_id AND held_by_job_id = v_res.job_id;
    ELSE
        FOR v_allocation IN SELECT * FROM commercial_credit_reservation_lots
            WHERE organization_id = v_org AND reservation_id = p_reservation_id
            ORDER BY lot_id FOR UPDATE
        LOOP
            UPDATE commercial_credit_lots
               SET reserved = reserved - v_allocation.quantity,
                   available = available + v_allocation.quantity,
                   updated_at = now()
             WHERE lot_id = v_allocation.lot_id;
        END LOOP;
        PERFORM set_config('app.commercial_credit_posting', 'on', true);
        UPDATE commercial_credit_accounts
           SET reserved = reserved - v_res.requested_credits,
               account_version = account_version + 1, updated_at = now()
         WHERE organization_id = v_org;
        PERFORM set_config('app.commercial_credit_posting', '', true);
    END IF;
    UPDATE commercial_credit_reservations SET status = 'RELEASED', updated_at = now()
     WHERE reservation_id = p_reservation_id;
    RETURN 'RELEASED';
END;
$$;

DO $$
DECLARE name text;
BEGIN
    FOREACH name IN ARRAY ARRAY[
        'commercial_orders', 'commercial_credit_accounts',
        'commercial_credit_lots', 'commercial_credit_ledger_entries',
        'project_generation_entitlements', 'commercial_credit_reservations',
        'commercial_credit_reservation_lots'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', name);
        EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))', name);
    END LOOP;
END;
$$;

REVOKE ALL ON commercial_products, commercial_orders, commercial_order_directory,
    commercial_credit_accounts, commercial_credit_ledger_entries,
    commercial_credit_lots, project_generation_entitlements,
    commercial_credit_reservations, commercial_credit_reservation_lots FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_sync_commercial_order_directory() FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_reserve_usage_v2(varchar, varchar, varchar, varchar, varchar, numeric, numeric, timestamptz, varchar, varchar, varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_settle_usage_v2(varchar, varchar, varchar, numeric, numeric, varchar, varchar, varchar, char, numeric, timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_release_usage_v2(varchar, varchar, varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_commercial_create_order(varchar, varchar, varchar, varchar, varchar, varchar, varchar, char, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_commercial_fulfill_order(varchar, varchar, varchar, varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_commercial_mark_order_handoff(varchar, varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_commercial_mark_order_prepare_failed(varchar, varchar, boolean, varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_commercial_reserve_generation(varchar, varchar, varchar, varchar, numeric, varchar, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_commercial_settle_generation(varchar, varchar, numeric) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_commercial_release_generation(varchar, varchar) FROM PUBLIC;

-- The billing read path expires an elapsed trial before returning balances.
-- Keep the runtime role on a narrow function boundary instead of granting it
-- writes to subscription, quota and trial tables.  A fixed search_path prevents
-- caller-controlled name resolution inside this SECURITY DEFINER function.
ALTER FUNCTION elmos_expire_current_trial() SECURITY DEFINER;
ALTER FUNCTION elmos_expire_current_trial() SET search_path = pg_catalog, public;
REVOKE ALL ON FUNCTION elmos_expire_current_trial() FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_billing_runtime') THEN
        GRANT USAGE ON SCHEMA identity, ai_usage, billing TO elmos_billing_runtime;
        GRANT SELECT ON commercial_products TO elmos_billing_runtime;
        GRANT SELECT ON identity.accounts, ai_usage.model_calls,
            billing.token_usage_events TO elmos_billing_runtime;
        GRANT SELECT ON commercial_order_directory TO elmos_billing_runtime;
        GRANT UPDATE (processing_status, attempt_count, updated_at)
            ON payment_callback_receipts TO elmos_billing_runtime;
        GRANT SELECT ON commercial_orders, commercial_credit_accounts,
            commercial_credit_lots, commercial_credit_ledger_entries,
            project_generation_entitlements, commercial_credit_reservations,
            commercial_credit_reservation_lots TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_commercial_create_order(varchar, varchar, varchar, varchar, varchar, varchar, varchar, char, integer) TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_reserve_usage_v2(varchar, varchar, varchar, varchar, varchar, numeric, numeric, timestamptz, varchar, varchar, varchar) TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_settle_usage_v2(varchar, varchar, varchar, numeric, numeric, varchar, varchar, varchar, char, numeric, timestamptz) TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_release_usage_v2(varchar, varchar, varchar) TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_commercial_fulfill_order(varchar, varchar, varchar, varchar) TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_commercial_mark_order_handoff(varchar, varchar) TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_commercial_mark_order_prepare_failed(varchar, varchar, boolean, varchar) TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_commercial_reserve_generation(varchar, varchar, varchar, varchar, numeric, varchar, integer) TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_commercial_settle_generation(varchar, varchar, numeric) TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_commercial_release_generation(varchar, varchar) TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_expire_current_trial() TO elmos_billing_runtime;
    END IF;
END;
$$;
