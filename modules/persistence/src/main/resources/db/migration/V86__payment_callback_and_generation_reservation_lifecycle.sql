-- Complete all callback directory projections. Callback routing must choose
-- the stored provider before tenant RLS context exists, so each non-RLS
-- directory owns that minimum fact as well.

ALTER TABLE payment_order_directory
    ADD COLUMN provider varchar(32);
ALTER TABLE wallet_topup_order_directory
    ADD COLUMN provider varchar(16);

ALTER TABLE commercial_order_directory
    ADD COLUMN provider varchar(32);

-- The source tables use FORCE RLS, including against their owner. Flyway's
-- migration role therefore cannot backfill all tenants unless FORCE is
-- removed briefly. These changes share the migration transaction: any later
-- failure rolls the entire sequence back and cannot leave FORCE disabled.
ALTER TABLE payment_checkout_sessions NO FORCE ROW LEVEL SECURITY;
ALTER TABLE wallet_topup_orders NO FORCE ROW LEVEL SECURITY;
ALTER TABLE commercial_orders NO FORCE ROW LEVEL SECURITY;

UPDATE payment_order_directory d
   SET provider = o.provider
  FROM payment_checkout_sessions o
 WHERE o.checkout_session_id = d.checkout_session_id
   AND o.organization_id = d.organization_id;

UPDATE wallet_topup_order_directory d
   SET provider = o.provider
  FROM wallet_topup_orders o
 WHERE o.topup_order_id = d.topup_order_id
   AND o.organization_id = d.organization_id;

UPDATE commercial_order_directory d
   SET provider = o.provider
  FROM commercial_orders o
 WHERE o.order_id = d.order_id
   AND o.organization_id = d.organization_id;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM payment_checkout_sessions o
        LEFT JOIN payment_order_directory d
          ON d.checkout_session_id = o.checkout_session_id
         AND d.organization_id = o.organization_id
        WHERE d.checkout_session_id IS NULL OR d.provider IS DISTINCT FROM o.provider
    ) THEN
        RAISE EXCEPTION 'ELMOS_PAYMENT_DIRECTORY_PROVIDER_BACKFILL_INCOMPLETE';
    END IF;
    IF EXISTS (
        SELECT 1 FROM wallet_topup_orders o
        LEFT JOIN wallet_topup_order_directory d
          ON d.topup_order_id = o.topup_order_id
         AND d.organization_id = o.organization_id
        WHERE d.topup_order_id IS NULL OR d.provider IS DISTINCT FROM o.provider
    ) THEN
        RAISE EXCEPTION 'ELMOS_WALLET_DIRECTORY_PROVIDER_BACKFILL_INCOMPLETE';
    END IF;
    IF EXISTS (
        SELECT 1 FROM commercial_orders o
        LEFT JOIN commercial_order_directory d
          ON d.order_id = o.order_id
         AND d.organization_id = o.organization_id
        WHERE d.order_id IS NULL OR d.provider IS DISTINCT FROM o.provider
    ) THEN
        RAISE EXCEPTION 'ELMOS_COMMERCIAL_DIRECTORY_PROVIDER_BACKFILL_INCOMPLETE';
    END IF;
END;
$$;

ALTER TABLE payment_checkout_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE wallet_topup_orders FORCE ROW LEVEL SECURITY;
ALTER TABLE commercial_orders FORCE ROW LEVEL SECURITY;

ALTER TABLE payment_order_directory
    ALTER COLUMN provider SET NOT NULL;
ALTER TABLE wallet_topup_order_directory
    ALTER COLUMN provider SET NOT NULL;
ALTER TABLE commercial_order_directory
    ALTER COLUMN provider SET NOT NULL;

CREATE OR REPLACE FUNCTION elmos_sync_payment_order_directory()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    INSERT INTO public.payment_order_directory (
        checkout_session_id, business_order_sha256, organization_id, plan_id,
        amount_minor, provider, status)
    VALUES (
        NEW.checkout_session_id,
        pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
            NEW.checkout_session_id, 'UTF8')), 'hex'),
        NEW.organization_id, NEW.plan_id, NEW.amount_minor, NEW.provider, NEW.status)
    ON CONFLICT (checkout_session_id) DO UPDATE
        SET provider = EXCLUDED.provider,
            status = EXCLUDED.status,
            updated_at = pg_catalog.now();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_sync_wallet_topup_directory()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    INSERT INTO public.wallet_topup_order_directory (
        out_trade_no, business_order_sha256, topup_order_id, organization_id,
        amount_minor, provider, status)
    VALUES (
        NEW.out_trade_no,
        pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
            NEW.out_trade_no, 'UTF8')), 'hex'),
        NEW.topup_order_id, NEW.organization_id, NEW.amount_minor,
        NEW.provider, NEW.status)
    ON CONFLICT (out_trade_no) DO UPDATE
        SET provider = EXCLUDED.provider,
            status = EXCLUDED.status,
            updated_at = pg_catalog.now();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_sync_commercial_order_directory()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    INSERT INTO public.commercial_order_directory (
        out_trade_no, business_order_sha256, order_id, organization_id, order_type,
        amount_minor, provider, status)
    VALUES (
        NEW.out_trade_no,
        pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
            NEW.out_trade_no, 'UTF8')), 'hex'),
        NEW.order_id, NEW.organization_id, NEW.order_type, NEW.amount_minor,
        NEW.provider, NEW.status)
    ON CONFLICT (out_trade_no) DO UPDATE
       SET provider = EXCLUDED.provider,
           status = EXCLUDED.status,
           updated_at = pg_catalog.now();
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION elmos_sync_payment_order_directory() FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_sync_wallet_topup_directory() FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_sync_commercial_order_directory() FROM PUBLIC;

DROP TRIGGER wallet_topup_orders_directory_sync ON wallet_topup_orders;

ALTER TABLE wallet_topup_orders
    ALTER COLUMN status TYPE varchar(24),
    DROP CONSTRAINT wallet_topup_orders_status_check,
    ADD CONSTRAINT wallet_topup_orders_status_check CHECK (status IN (
        'CREATED', 'PENDING_PAYMENT', 'PAID', 'CREDITED', 'FAILED', 'EXPIRED',
        'REFUNDED', 'RECONCILIATION_REQUIRED'
    ));

ALTER TABLE wallet_topup_order_directory
    ALTER COLUMN status TYPE varchar(24);

CREATE TRIGGER wallet_topup_orders_directory_sync
AFTER INSERT OR UPDATE OF status ON wallet_topup_orders
FOR EACH ROW EXECUTE FUNCTION elmos_sync_wallet_topup_directory();

CREATE OR REPLACE FUNCTION elmos_wallet_mark_topup_handoff(
    p_organization_id varchar, p_topup_order_id varchar, p_actor_id varchar
) RETURNS varchar
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_previous text;
    v_status varchar;
BEGIN
    v_previous := public.elmos_wallet_bind_tenant(p_organization_id);
    UPDATE public.wallet_topup_orders
       SET status = 'PENDING_PAYMENT', failure_code = NULL, updated_at = now()
     WHERE organization_id = p_organization_id
       AND topup_order_id = p_topup_order_id
       AND actor_id = p_actor_id
       AND status = 'CREATED'
     RETURNING status INTO v_status;
    IF FOUND THEN
        PERFORM set_config('app.organization_id', v_previous, true);
        RETURN v_status;
    END IF;
    SELECT status INTO v_status FROM public.wallet_topup_orders
     WHERE organization_id = p_organization_id
       AND topup_order_id = p_topup_order_id
       AND actor_id = p_actor_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_UNKNOWN'; END IF;
    IF v_status IN ('PENDING_PAYMENT', 'PAID', 'CREDITED') THEN
        PERFORM set_config('app.organization_id', v_previous, true);
        RETURN v_status;
    END IF;
    RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_HANDOFF_INVALID';
END;
$$;

CREATE OR REPLACE FUNCTION elmos_wallet_mark_topup_prepare_failed(
    p_organization_id varchar, p_topup_order_id varchar, p_actor_id varchar,
    p_outcome_unknown boolean, p_failure_code varchar
) RETURNS varchar
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_previous text;
    v_status varchar;
BEGIN
    IF p_failure_code IS NULL OR p_failure_code = '' OR length(p_failure_code) > 96 THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_FAILURE_CODE_INVALID';
    END IF;
    v_previous := public.elmos_wallet_bind_tenant(p_organization_id);
    UPDATE public.wallet_topup_orders
       SET status = CASE WHEN p_outcome_unknown
                         THEN 'RECONCILIATION_REQUIRED' ELSE 'FAILED' END,
           failure_code = p_failure_code,
           updated_at = now()
     WHERE organization_id = p_organization_id
       AND topup_order_id = p_topup_order_id
       AND actor_id = p_actor_id
       AND status IN ('CREATED', 'PENDING_PAYMENT')
     RETURNING status INTO v_status;
    IF FOUND THEN
        PERFORM set_config('app.organization_id', v_previous, true);
        RETURN v_status;
    END IF;
    SELECT status INTO v_status FROM public.wallet_topup_orders
     WHERE organization_id = p_organization_id
       AND topup_order_id = p_topup_order_id
       AND actor_id = p_actor_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_UNKNOWN'; END IF;
    IF v_status = 'CREDITED' THEN
        PERFORM set_config('app.organization_id', v_previous, true);
        RETURN v_status;
    END IF;
    RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_PREPARE_FAILURE_INVALID';
END;
$$;

CREATE OR REPLACE FUNCTION elmos_wallet_credit_topup(
    p_organization_id varchar,
    p_topup_order_id varchar,
    p_provider_txn_ref varchar,
    p_actor_id varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_previous text;
    v_order public.wallet_topup_orders%ROWTYPE;
    v_entry_id varchar(96);
BEGIN
    v_previous := public.elmos_wallet_bind_tenant(p_organization_id);
    SELECT * INTO v_order FROM public.wallet_topup_orders
     WHERE topup_order_id = p_topup_order_id
       AND organization_id = p_organization_id
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_UNKNOWN'; END IF;
    IF v_order.status = 'CREDITED' THEN
        PERFORM set_config('app.organization_id', v_previous, true);
        RETURN v_order.credited_entry_ref;
    END IF;
    IF v_order.status NOT IN ('PAID', 'PENDING_PAYMENT', 'CREATED')
       AND NOT (v_order.status = 'RECONCILIATION_REQUIRED'
                AND v_order.failure_code = 'CHECKOUT_PREPARE_OUTCOME_UNKNOWN') THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_NOT_CREDITABLE';
    END IF;
    IF v_order.expires_at <= now() AND v_order.status <> 'PAID' THEN
        UPDATE public.wallet_topup_orders
           SET status = 'RECONCILIATION_REQUIRED',
               provider_txn_ref = p_provider_txn_ref,
               paid_at = coalesce(paid_at, now()),
               failure_code = 'PAYMENT_AFTER_LOCAL_EXPIRY',
               updated_at = now()
         WHERE topup_order_id = p_topup_order_id
           AND organization_id = p_organization_id;
        PERFORM set_config('app.organization_id', v_previous, true);
        RETURN p_topup_order_id;
    END IF;
    v_entry_id := public.elmos_wallet_post_entry(
        v_order.organization_id, 'CREDIT', v_order.amount_minor, 'TOPUP_SETTLED',
        'TOPUP_ORDER', v_order.topup_order_id, p_actor_id,
        'topup:' || v_order.provider || ':' || v_order.out_trade_no, NULL, NULL);
    UPDATE public.wallet_topup_orders
       SET status = 'CREDITED',
           provider_txn_ref = coalesce(p_provider_txn_ref, provider_txn_ref),
           paid_at = coalesce(paid_at, now()),
           credited_at = now(),
           credited_entry_ref = v_entry_id,
           failure_code = NULL
     WHERE topup_order_id = p_topup_order_id
       AND organization_id = p_organization_id;
    PERFORM set_config('app.organization_id', v_previous, true);
    RETURN v_entry_id;
END;
$$;

REVOKE ALL ON FUNCTION elmos_wallet_mark_topup_handoff(varchar, varchar, varchar)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_wallet_mark_topup_prepare_failed(
    varchar, varchar, varchar, boolean, varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_wallet_credit_topup(varchar, varchar, varchar, varchar)
    FROM PUBLIC;

-- A checkout prepare call can time out after the provider accepted it. A
-- verified callback is then allowed to recover only that exact unknown-outcome
-- state. Other reconciliation states, failed orders, and late callbacks stay
-- fail-closed and cannot mint credits or an entitlement.

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
    IF v_order.status NOT IN ('CREATED', 'PENDING_PAYMENT', 'PAID')
       AND NOT (v_order.status = 'RECONCILIATION_REQUIRED'
                AND v_order.failure_code = 'CHECKOUT_PREPARE_OUTCOME_UNKNOWN') THEN
        RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_NOT_FULFILLABLE';
    END IF;
    IF v_order.expires_at <= now() AND v_order.status <> 'PAID' THEN
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
           failure_code = NULL, updated_at = now()
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

REVOKE ALL ON FUNCTION elmos_commercial_fulfill_order(varchar, varchar, varchar, varchar)
    FROM PUBLIC;

-- Reclaim expired project-generation reservations through a bounded,
-- tenant-scoped function. Runtime callers retain read-only table grants and
-- receive only this narrow mutation boundary.

CREATE OR REPLACE FUNCTION elmos_commercial_expire_generation_reservations(
    p_limit integer
) RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_org varchar := elmos_current_organization_id();
    v_reservation commercial_credit_reservations%ROWTYPE;
    v_allocation commercial_credit_reservation_lots%ROWTYPE;
    v_lot commercial_credit_lots%ROWTYPE;
    v_account commercial_credit_accounts%ROWTYPE;
    v_allocated numeric(19,0);
    v_expired numeric(19,0);
    v_processed integer := 0;
BEGIN
    IF p_limit < 1 OR p_limit > 1000 THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_RESERVATION_EXPIRY_LIMIT_INVALID';
    END IF;

    FOR v_reservation IN
        SELECT *
          FROM commercial_credit_reservations
         WHERE organization_id = v_org
           AND status = 'HELD'
           AND expires_at <= now()
         ORDER BY expires_at, reservation_id
         LIMIT p_limit
         FOR UPDATE SKIP LOCKED
    LOOP
        IF v_reservation.funding_source = 'ONE_TIME_ENTITLEMENT' THEN
            UPDATE project_generation_entitlements
               SET status = CASE WHEN expires_at > now() THEN 'AVAILABLE' ELSE 'EXPIRED' END,
                   held_by_job_id = NULL,
                   updated_at = now()
             WHERE organization_id = v_org
               AND entitlement_id = v_reservation.entitlement_id
               AND status = 'HELD'
               AND held_by_job_id = v_reservation.job_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'ELMOS_CREDIT_ENTITLEMENT_DRIFT';
            END IF;
        ELSE
            v_allocated := 0;
            v_expired := 0;
            FOR v_allocation IN
                SELECT *
                  FROM commercial_credit_reservation_lots
                 WHERE organization_id = v_org
                   AND reservation_id = v_reservation.reservation_id
                 ORDER BY lot_id
            LOOP
                SELECT * INTO v_lot
                  FROM commercial_credit_lots
                 WHERE organization_id = v_org
                   AND lot_id = v_allocation.lot_id
                 FOR UPDATE;
                IF NOT FOUND OR v_lot.reserved < v_allocation.quantity THEN
                    RAISE EXCEPTION 'ELMOS_CREDIT_LOT_DRIFT';
                END IF;

                v_allocated := v_allocated + v_allocation.quantity;
                IF v_lot.expires_at <= now() THEN
                    v_expired := v_expired + v_lot.available + v_allocation.quantity;
                    UPDATE commercial_credit_lots
                       SET available = 0,
                           reserved = reserved - v_allocation.quantity,
                           consumed = consumed + v_lot.available + v_allocation.quantity,
                           status = CASE
                               WHEN reserved - v_allocation.quantity = 0 THEN 'EXPIRED'
                               ELSE status
                           END,
                           updated_at = now()
                     WHERE organization_id = v_org
                       AND lot_id = v_allocation.lot_id;
                ELSE
                    UPDATE commercial_credit_lots
                       SET available = available + v_allocation.quantity,
                           reserved = reserved - v_allocation.quantity,
                           updated_at = now()
                     WHERE organization_id = v_org
                       AND lot_id = v_allocation.lot_id;
                END IF;
            END LOOP;
            IF v_allocated <> v_reservation.requested_credits THEN
                RAISE EXCEPTION 'ELMOS_CREDIT_LOT_DRIFT';
            END IF;

            -- Match settle/release lock order: reservation, allocation lots,
            -- then account. A sweeper must not introduce an inverse lock edge.
            SELECT * INTO v_account
              FROM commercial_credit_accounts
             WHERE organization_id = v_org
               AND status = 'ACTIVE'
             FOR UPDATE;
            IF NOT FOUND OR v_account.reserved < v_reservation.requested_credits THEN
                RAISE EXCEPTION 'ELMOS_CREDIT_ACCOUNT_DRIFT';
            END IF;

            PERFORM set_config('app.commercial_credit_posting', 'on', true);
            UPDATE commercial_credit_accounts
               SET balance = balance - v_expired,
                   reserved = reserved - v_reservation.requested_credits,
                   account_version = account_version + 1,
                   updated_at = now()
             WHERE organization_id = v_org
               AND balance >= v_expired
               AND reserved >= v_reservation.requested_credits;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'ELMOS_CREDIT_ACCOUNT_DRIFT';
            END IF;
            PERFORM set_config('app.commercial_credit_posting', '', true);
        END IF;

        UPDATE commercial_credit_reservations
           SET status = 'EXPIRED',
               updated_at = now()
         WHERE organization_id = v_org
           AND reservation_id = v_reservation.reservation_id
           AND status = 'HELD';
        IF NOT FOUND THEN
            RAISE EXCEPTION 'ELMOS_CREDIT_RESERVATION_DRIFT';
        END IF;
        v_processed := v_processed + 1;
    END LOOP;

    RETURN v_processed;
END;
$$;

REVOKE ALL ON FUNCTION elmos_commercial_expire_generation_reservations(integer) FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_billing_runtime') THEN
        GRANT EXECUTE ON FUNCTION elmos_wallet_mark_topup_handoff(
            varchar, varchar, varchar) TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_wallet_mark_topup_prepare_failed(
            varchar, varchar, varchar, boolean, varchar) TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_commercial_expire_generation_reservations(integer)
            TO elmos_billing_runtime;
    END IF;
END;
$$;
