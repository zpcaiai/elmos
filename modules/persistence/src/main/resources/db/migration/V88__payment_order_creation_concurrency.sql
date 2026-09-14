-- ELMOS V88: serialize payment-order creation and bind idempotent replays.
--
-- V73 checked the wallet daily cap before it opened/locked the wallet row, so two
-- concurrent requests could both observe the same total and exceed the cap. It also
-- returned an existing idempotency key without proving actor, amount and provider.
-- V83 had the equivalent select-before-insert race for commercial orders. These
-- replacements retain the public signatures while closing both races.

CREATE OR REPLACE FUNCTION elmos_wallet_create_topup_order(
    p_topup_order_id varchar,
    p_organization_id varchar,
    p_actor_id varchar,
    p_amount_minor numeric,
    p_provider varchar,
    p_out_trade_no varchar,
    p_idempotency_key varchar,
    p_ttl_seconds integer DEFAULT 3600
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_previous text;
    v_existing wallet_topup_orders%ROWTYPE;
    v_bounds record;
    v_today numeric(19,0);
BEGIN
    IF p_ttl_seconds IS NULL OR p_ttl_seconds < 60 OR p_ttl_seconds > 86400 THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_TTL_INVALID';
    END IF;
    IF p_idempotency_key IS NULL OR length(p_idempotency_key) < 8
       OR length(p_idempotency_key) > 160 THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_IDEMPOTENCY_INVALID';
    END IF;

    v_previous := elmos_wallet_bind_tenant(p_organization_id);
    PERFORM elmos_wallet_open(p_organization_id);

    -- The wallet row is the per-tenant creation mutex. The daily-cap read and the
    -- insert now occur under one lock, so another creator must observe this order.
    PERFORM 1 FROM wallet_accounts
     WHERE organization_id = p_organization_id FOR UPDATE;

    SELECT * INTO v_existing FROM wallet_topup_orders
     WHERE organization_id = p_organization_id AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.actor_id IS DISTINCT FROM p_actor_id
           OR v_existing.amount_minor IS DISTINCT FROM p_amount_minor
           OR v_existing.provider IS DISTINCT FROM p_provider THEN
            RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_IDEMPOTENCY_CONFLICT';
        END IF;
        PERFORM set_config('app.organization_id', v_previous, true);
        RETURN v_existing.topup_order_id;
    END IF;

    SELECT * INTO v_bounds FROM elmos_wallet_topup_bounds(p_organization_id);
    IF p_amount_minor IS NULL OR p_amount_minor < v_bounds.min_amount_minor THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_BELOW_MINIMUM';
    END IF;
    IF p_amount_minor > v_bounds.max_amount_minor THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_ABOVE_MAXIMUM';
    END IF;

    SELECT coalesce(sum(amount_minor), 0) INTO v_today
      FROM wallet_topup_orders
     WHERE organization_id = p_organization_id
       AND created_at >= date_trunc('day', now())
       AND status NOT IN ('FAILED', 'EXPIRED')
       -- CREATED/PENDING_PAYMENT orders stop consuming today's cap once their
       -- local checkout TTL ends. Keep the stored status unchanged: a late
       -- provider success must still enter the existing reconciliation path.
       AND (status NOT IN ('CREATED', 'PENDING_PAYMENT') OR expires_at > now());
    IF v_today + p_amount_minor > v_bounds.daily_amount_limit_minor THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_DAILY_LIMIT_EXCEEDED';
    END IF;

    INSERT INTO wallet_topup_orders (
        topup_order_id, organization_id, actor_id, amount_minor, provider,
        out_trade_no, idempotency_key, expires_at
    ) VALUES (
        p_topup_order_id, p_organization_id, p_actor_id, p_amount_minor, p_provider,
        p_out_trade_no, p_idempotency_key, now() + make_interval(secs => p_ttl_seconds)
    );

    PERFORM set_config('app.organization_id', v_previous, true);
    RETURN p_topup_order_id;
END;
$$;

COMMENT ON FUNCTION elmos_wallet_create_topup_order(
    varchar, varchar, varchar, numeric, varchar, varchar, varchar, integer) IS
    'Creates a top-up under the per-tenant wallet lock; expired unpaid checkouts no longer consume the daily cap, exact idempotent replays return the original order, and conflicting actor, amount or provider facts fail closed.';

CREATE OR REPLACE FUNCTION elmos_commercial_create_order(
    p_order_id varchar, p_actor_id varchar, p_sku varchar, p_project_id varchar,
    p_provider varchar, p_out_trade_no varchar, p_idempotency_key varchar,
    p_request_hash char(64), p_ttl_seconds integer
) RETURNS varchar LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_org varchar := public.elmos_current_organization_id();
    v_product public.commercial_products%ROWTYPE;
    v_existing public.commercial_orders%ROWTYPE;
BEGIN
    IF p_ttl_seconds < 300 OR p_ttl_seconds > 3600 THEN
        RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_TTL_INVALID';
    END IF;
    IF p_idempotency_key IS NULL OR length(p_idempotency_key) < 8
       OR length(p_idempotency_key) > 160 THEN
        RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_IDEMPOTENCY_INVALID';
    END IF;

    -- Only creators for the same tenant/key serialize; unrelated checkout traffic
    -- remains concurrent. The lock closes V83's SELECT then INSERT unique-key race.
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(v_org || chr(31) || p_idempotency_key, 0));
    SELECT * INTO v_existing FROM public.commercial_orders
     WHERE organization_id = v_org AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.actor_id IS DISTINCT FROM p_actor_id
           OR v_existing.sku IS DISTINCT FROM p_sku
           OR v_existing.project_id IS DISTINCT FROM p_project_id
           OR v_existing.request_hash IS DISTINCT FROM p_request_hash THEN
            RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.order_id;
    END IF;

    SELECT * INTO v_product FROM public.commercial_products WHERE sku = p_sku;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_COMMERCIAL_PRODUCT_UNKNOWN'; END IF;
    IF v_product.product_type = 'PROJECT_GENERATION_ONCE'
       AND (p_project_id IS NULL OR p_project_id = '') THEN
        RAISE EXCEPTION 'ELMOS_COMMERCIAL_PROJECT_REQUIRED';
    END IF;
    INSERT INTO public.commercial_orders (
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

COMMENT ON FUNCTION elmos_commercial_create_order(
    varchar, varchar, varchar, varchar, varchar, varchar, varchar, char, integer) IS
    'Creates a commercial order after serializing the tenant/idempotency identity; exact concurrent replays converge on one order and changed facts fail closed.';

REVOKE ALL ON FUNCTION elmos_wallet_create_topup_order(
    varchar, varchar, varchar, numeric, varchar, varchar, varchar, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_commercial_create_order(
    varchar, varchar, varchar, varchar, varchar, varchar, varchar, char, integer) FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_billing_runtime') THEN
        GRANT EXECUTE ON FUNCTION elmos_wallet_create_topup_order(
            varchar, varchar, varchar, numeric, varchar, varchar, varchar, integer)
            TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_commercial_create_order(
            varchar, varchar, varchar, varchar, varchar, varchar, varchar, char, integer)
            TO elmos_billing_runtime;
    END IF;
END;
$$;
