-- Bind callback lookup rows to the exact payment channel selected at order creation.
-- Also add the missing recovery paths for provider handoff failures and expired Credit holds.

ALTER TABLE payment_order_directory ADD COLUMN provider varchar(32);
ALTER TABLE wallet_topup_order_directory
    ADD COLUMN provider varchar(32),
    ALTER COLUMN status TYPE varchar(24);
ALTER TABLE commercial_order_directory ADD COLUMN provider varchar(32);

-- The source tables are FORCE-RLS tenant tables. Temporarily relaxing FORCE for the
-- migration owner is safe only because Flyway wraps this backfill and restoration in
-- one transaction; ordinary roles remain governed by the existing RLS policies.
ALTER TABLE payment_checkout_sessions NO FORCE ROW LEVEL SECURITY;
ALTER TABLE wallet_topup_orders NO FORCE ROW LEVEL SECURITY;
ALTER TABLE commercial_orders NO FORCE ROW LEVEL SECURITY;

UPDATE payment_order_directory d
 SET provider = s.provider
  FROM payment_checkout_sessions s
 WHERE s.checkout_session_id = d.checkout_session_id
   AND s.organization_id = d.organization_id;
UPDATE wallet_topup_order_directory d
 SET provider = s.provider
  FROM wallet_topup_orders s
 WHERE s.out_trade_no = d.out_trade_no
   AND s.organization_id = d.organization_id;
UPDATE commercial_order_directory d
   SET provider = s.provider
  FROM commercial_orders s
 WHERE s.out_trade_no = d.out_trade_no
   AND s.organization_id = d.organization_id;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM payment_checkout_sessions s
        LEFT JOIN payment_order_directory d
          ON d.checkout_session_id = s.checkout_session_id
         AND d.organization_id = s.organization_id
        WHERE d.checkout_session_id IS NULL OR d.provider IS DISTINCT FROM s.provider
    ) THEN
        RAISE EXCEPTION 'ELMOS_PAYMENT_DIRECTORY_PROVIDER_BACKFILL_INCOMPLETE';
    END IF;
    IF EXISTS (
        SELECT 1 FROM wallet_topup_orders s
        LEFT JOIN wallet_topup_order_directory d
          ON d.out_trade_no = s.out_trade_no
         AND d.organization_id = s.organization_id
        WHERE d.out_trade_no IS NULL OR d.provider IS DISTINCT FROM s.provider
    ) THEN
        RAISE EXCEPTION 'ELMOS_WALLET_DIRECTORY_PROVIDER_BACKFILL_INCOMPLETE';
    END IF;
    IF EXISTS (
        SELECT 1 FROM commercial_orders s
        LEFT JOIN commercial_order_directory d
          ON d.out_trade_no = s.out_trade_no
         AND d.organization_id = s.organization_id
        WHERE d.out_trade_no IS NULL OR d.provider IS DISTINCT FROM s.provider
    ) THEN
        RAISE EXCEPTION 'ELMOS_COMMERCIAL_DIRECTORY_PROVIDER_BACKFILL_INCOMPLETE';
    END IF;
END
$$;

ALTER TABLE payment_checkout_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE wallet_topup_orders FORCE ROW LEVEL SECURITY;
ALTER TABLE commercial_orders FORCE ROW LEVEL SECURITY;

DO $$
DECLARE source_table text;
BEGIN
    FOREACH source_table IN ARRAY ARRAY[
        'payment_checkout_sessions', 'wallet_topup_orders', 'commercial_orders'
    ] LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_class
             WHERE relname = source_table AND relrowsecurity AND relforcerowsecurity
        ) THEN
            RAISE EXCEPTION '% FORCE ROW LEVEL SECURITY was not restored', source_table;
        END IF;
    END LOOP;
END
$$;

ALTER TABLE payment_order_directory
    ALTER COLUMN provider SET NOT NULL,
    ADD CONSTRAINT payment_order_directory_provider_check
        CHECK (provider IN ('STRIPE_CHECKOUT', 'ALIPAY_CHECKOUT', 'WECHAT_PAY_NATIVE'));
ALTER TABLE wallet_topup_order_directory
    ALTER COLUMN provider SET NOT NULL,
    ADD CONSTRAINT wallet_topup_order_directory_provider_check
        CHECK (provider IN ('STRIPE', 'ALIPAY', 'WECHAT_PAY', 'OFFLINE'));
ALTER TABLE commercial_order_directory
    ALTER COLUMN provider SET NOT NULL,
    ADD CONSTRAINT commercial_order_directory_provider_check
        CHECK (provider IN ('ALIPAY_CHECKOUT', 'WECHAT_PAY_NATIVE'));

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
        pg_catalog.encode(public.digest(pg_catalog.convert_to(
            NEW.checkout_session_id, 'UTF8'), 'sha256'), 'hex'),
        NEW.organization_id, NEW.plan_id, NEW.amount_minor, NEW.provider, NEW.status)
    ON CONFLICT (checkout_session_id) DO UPDATE
        SET status = EXCLUDED.status,
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
        pg_catalog.encode(public.digest(pg_catalog.convert_to(
            NEW.out_trade_no, 'UTF8'), 'sha256'), 'hex'),
        NEW.topup_order_id, NEW.organization_id, NEW.amount_minor, NEW.provider, NEW.status)
    ON CONFLICT (out_trade_no) DO UPDATE
        SET status = EXCLUDED.status,
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
        pg_catalog.encode(public.digest(pg_catalog.convert_to(
            NEW.out_trade_no, 'UTF8'), 'sha256'), 'hex'),
        NEW.order_id, NEW.organization_id, NEW.order_type, NEW.amount_minor,
        NEW.provider, NEW.status)
    ON CONFLICT (out_trade_no) DO UPDATE
       SET status = EXCLUDED.status, updated_at = pg_catalog.now();
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION elmos_sync_payment_order_directory() FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_sync_wallet_topup_directory() FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_sync_commercial_order_directory() FROM PUBLIC;

COMMENT ON COLUMN payment_order_directory.provider IS
    'Immutable payment channel copied from the source order for callback binding.';
COMMENT ON COLUMN wallet_topup_order_directory.provider IS
    'Immutable payment channel copied from the source order for callback binding.';
COMMENT ON COLUMN commercial_order_directory.provider IS
    'Immutable payment channel copied from the source order for callback binding.';

-- A provider-contacting handoff can have an unknown result. Keep that state distinct
-- from a known local failure, while still allowing a later signed payment callback to
-- settle the order.
DROP TRIGGER wallet_topup_orders_directory_sync ON wallet_topup_orders;
ALTER TABLE wallet_topup_orders
    ALTER COLUMN status TYPE varchar(24),
    DROP CONSTRAINT wallet_topup_orders_status_check,
    ADD CONSTRAINT wallet_topup_orders_status_check CHECK (status IN (
        'CREATED', 'PENDING_PAYMENT', 'PAID', 'CREDITED', 'FAILED', 'EXPIRED',
        'REFUNDED', 'RECONCILIATION_REQUIRED'));

CREATE TRIGGER wallet_topup_orders_directory_sync
AFTER INSERT OR UPDATE OF status ON wallet_topup_orders
FOR EACH ROW EXECUTE FUNCTION elmos_sync_wallet_topup_directory();

CREATE OR REPLACE FUNCTION elmos_wallet_mark_topup_handoff(
    p_organization_id varchar, p_topup_order_id varchar, p_actor_id varchar
) RETURNS varchar
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_previous text := current_setting('app.organization_id', true);
    v_status varchar;
BEGIN
    PERFORM pg_catalog.set_config('app.organization_id', p_organization_id, true);
    UPDATE public.wallet_topup_orders
       SET status = 'PENDING_PAYMENT', failure_code = NULL
     WHERE organization_id = p_organization_id AND topup_order_id = p_topup_order_id
       AND actor_id = p_actor_id AND status = 'CREATED'
     RETURNING status INTO v_status;
    IF FOUND THEN
        PERFORM pg_catalog.set_config('app.organization_id', coalesce(v_previous, ''), true);
        RETURN v_status;
    END IF;
    SELECT status INTO v_status FROM public.wallet_topup_orders
     WHERE organization_id = p_organization_id AND topup_order_id = p_topup_order_id
       AND actor_id = p_actor_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_UNKNOWN'; END IF;
    PERFORM pg_catalog.set_config('app.organization_id', coalesce(v_previous, ''), true);
    IF v_status IN ('PENDING_PAYMENT', 'PAID', 'CREDITED') THEN RETURN v_status; END IF;
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
    v_previous text := current_setting('app.organization_id', true);
    v_status varchar;
BEGIN
    IF p_failure_code IS NULL OR p_failure_code = '' OR length(p_failure_code) > 96 THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_FAILURE_CODE_INVALID';
    END IF;
    PERFORM pg_catalog.set_config('app.organization_id', p_organization_id, true);
    UPDATE public.wallet_topup_orders
       SET status = CASE WHEN p_outcome_unknown THEN 'RECONCILIATION_REQUIRED' ELSE 'FAILED' END,
           failure_code = p_failure_code
     WHERE organization_id = p_organization_id AND topup_order_id = p_topup_order_id
       AND actor_id = p_actor_id AND status IN ('CREATED', 'PENDING_PAYMENT')
     RETURNING status INTO v_status;
    IF FOUND THEN
        PERFORM pg_catalog.set_config('app.organization_id', coalesce(v_previous, ''), true);
        RETURN v_status;
    END IF;
    SELECT status INTO v_status FROM public.wallet_topup_orders
     WHERE organization_id = p_organization_id AND topup_order_id = p_topup_order_id
       AND actor_id = p_actor_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_UNKNOWN'; END IF;
    PERFORM pg_catalog.set_config('app.organization_id', coalesce(v_previous, ''), true);
    IF v_status = 'CREDITED' THEN RETURN v_status; END IF;
    RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_PREPARE_FAILURE_INVALID';
END;
$$;

CREATE OR REPLACE FUNCTION elmos_wallet_credit_topup(
    p_organization_id varchar, p_topup_order_id varchar,
    p_provider_txn_ref varchar, p_actor_id varchar
) RETURNS varchar
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_previous text;
    v_order public.wallet_topup_orders%ROWTYPE;
    v_entry_id varchar(96);
BEGIN
    v_previous := public.elmos_wallet_bind_tenant(p_organization_id);
    SELECT * INTO v_order FROM public.wallet_topup_orders
     WHERE topup_order_id = p_topup_order_id AND organization_id = p_organization_id
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_UNKNOWN'; END IF;
    IF v_order.status = 'CREDITED' THEN
        PERFORM pg_catalog.set_config('app.organization_id', v_previous, true);
        RETURN v_order.credited_entry_ref;
    END IF;
    IF v_order.status = 'RECONCILIATION_REQUIRED'
       AND v_order.failure_code IS DISTINCT FROM 'CHECKOUT_PREPARE_OUTCOME_UNKNOWN' THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_NOT_CREDITABLE';
    END IF;
    IF v_order.status NOT IN (
        'PAID', 'PENDING_PAYMENT', 'CREATED', 'RECONCILIATION_REQUIRED') THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_NOT_CREDITABLE';
    END IF;
    IF v_order.expires_at <= now()
       AND v_order.status IN ('CREATED', 'PENDING_PAYMENT', 'RECONCILIATION_REQUIRED') THEN
        UPDATE public.wallet_topup_orders
           SET status = 'RECONCILIATION_REQUIRED',
               provider_txn_ref = p_provider_txn_ref,
               paid_at = coalesce(paid_at, now()),
               failure_code = 'PAYMENT_AFTER_LOCAL_EXPIRY'
         WHERE topup_order_id = p_topup_order_id
           AND organization_id = p_organization_id;
        PERFORM pg_catalog.set_config('app.organization_id', v_previous, true);
        RETURN p_topup_order_id;
    END IF;
    v_entry_id := public.elmos_wallet_post_entry(
        v_order.organization_id, 'CREDIT', v_order.amount_minor, 'TOPUP_SETTLED',
        'TOPUP_ORDER', v_order.topup_order_id, p_actor_id,
        'topup:' || v_order.provider || ':' || v_order.out_trade_no, NULL, NULL);
    UPDATE public.wallet_topup_orders
       SET status = 'CREDITED',
           provider_txn_ref = coalesce(p_provider_txn_ref, provider_txn_ref),
           paid_at = coalesce(paid_at, now()), credited_at = now(),
           credited_entry_ref = v_entry_id,
           failure_code = NULL
     WHERE topup_order_id = p_topup_order_id
       AND organization_id = p_organization_id;
    PERFORM pg_catalog.set_config('app.organization_id', v_previous, true);
    RETURN v_entry_id;
END;
$$;

-- A checkout request may reach ELMPay even when ELMOS does not receive the
-- response. A later signed callback is then authoritative for the payment, but
-- only the specific prepare-unknown reconciliation state may auto-fulfil. Late
-- payments and every other reconciliation reason remain held for a human
-- refund-or-fulfil decision.
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
    PERFORM pg_catalog.set_config('app.organization_id', p_organization_id, true);
    SELECT * INTO v_order FROM public.commercial_orders
     WHERE organization_id = p_organization_id AND order_id = p_order_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_NOT_FOUND'; END IF;
    IF v_order.status = 'FULFILLED' THEN
        IF v_order.provider_transaction_ref IS DISTINCT FROM p_provider_transaction_ref THEN
            RAISE EXCEPTION 'ELMOS_COMMERCIAL_FULFILLMENT_IDEMPOTENCY_CONFLICT';
        END IF;
        PERFORM pg_catalog.set_config('app.organization_id', coalesce(v_previous, ''), true);
        RETURN p_order_id;
    END IF;
    IF v_order.status = 'RECONCILIATION_REQUIRED'
       AND v_order.failure_code IS DISTINCT FROM 'CHECKOUT_PREPARE_OUTCOME_UNKNOWN' THEN
        RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_NOT_FULFILLABLE';
    END IF;
    IF v_order.status NOT IN (
        'CREATED', 'PENDING_PAYMENT', 'PAID', 'RECONCILIATION_REQUIRED') THEN
        RAISE EXCEPTION 'ELMOS_COMMERCIAL_ORDER_NOT_FULFILLABLE';
    END IF;
    IF v_order.expires_at <= now()
       AND v_order.status IN ('CREATED', 'PENDING_PAYMENT', 'RECONCILIATION_REQUIRED') THEN
        UPDATE public.commercial_orders
           SET status = 'RECONCILIATION_REQUIRED',
               provider_transaction_ref = p_provider_transaction_ref,
               paid_at = coalesce(paid_at, now()),
               failure_code = 'PAYMENT_AFTER_LOCAL_EXPIRY', updated_at = now()
         WHERE order_id = p_order_id AND organization_id = p_organization_id;
        PERFORM pg_catalog.set_config('app.organization_id', coalesce(v_previous, ''), true);
        RETURN p_order_id;
    END IF;
    SELECT * INTO v_product FROM public.commercial_products WHERE sku = v_order.sku;
    IF v_order.order_type = 'CREDIT_PACK' THEN
        PERFORM pg_catalog.set_config('app.commercial_credit_posting', 'on', true);
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
               'purchase:' || p_order_id,
               now() + pg_catalog.make_interval(days => v_product.expiry_days)
          FROM public.commercial_credit_accounts WHERE organization_id = p_organization_id
        ON CONFLICT (organization_id, idempotency_key) DO NOTHING;
        INSERT INTO public.commercial_credit_lots (
            lot_id, organization_id, source_order_id, granted, available, expires_at)
        VALUES ('credit-lot-' || md5(p_order_id), p_organization_id, p_order_id,
                v_order.credit_quantity, v_order.credit_quantity,
                now() + pg_catalog.make_interval(days => v_product.expiry_days))
        ON CONFLICT (source_order_id) DO NOTHING;
    ELSE
        INSERT INTO public.project_generation_entitlements (
            entitlement_id, organization_id, actor_id, source_order_id,
            project_id, status, expires_at)
        VALUES ('entitlement-' || md5(p_order_id), p_organization_id, v_order.actor_id,
                p_order_id, v_order.project_id, 'AVAILABLE',
                now() + pg_catalog.make_interval(days => v_product.expiry_days))
        ON CONFLICT (source_order_id) DO NOTHING;
    END IF;
    UPDATE public.commercial_orders
       SET status = 'FULFILLED', provider_transaction_ref = p_provider_transaction_ref,
           paid_at = coalesce(paid_at, now()), fulfilled_at = coalesce(fulfilled_at, now()),
           failure_code = NULL, updated_at = now()
     WHERE order_id = p_order_id AND organization_id = p_organization_id;
    PERFORM pg_catalog.set_config('app.commercial_credit_posting', '', true);
    PERFORM pg_catalog.set_config('app.organization_id', coalesce(v_previous, ''), true);
    RETURN p_order_id;
EXCEPTION WHEN OTHERS THEN
    PERFORM pg_catalog.set_config('app.commercial_credit_posting', '', true);
    PERFORM pg_catalog.set_config('app.organization_id', coalesce(v_previous, ''), true);
    RAISE;
END;
$$;

REVOKE ALL ON FUNCTION elmos_wallet_mark_topup_handoff(varchar, varchar, varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_wallet_mark_topup_prepare_failed(
    varchar, varchar, varchar, boolean, varchar) FROM PUBLIC;

-- Reclaim stale generation holds deterministically. Expired lot quantities are not
-- made spendable again; they are consumed from the account balance. Unexpired lot
-- quantities return to availability. One-time entitlements follow their own TTL.
CREATE OR REPLACE FUNCTION elmos_commercial_expire_generation_reservations(
    p_limit integer
) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_org varchar := public.elmos_current_organization_id();
    v_res public.commercial_credit_reservations%ROWTYPE;
    v_allocation public.commercial_credit_reservation_lots%ROWTYPE;
    v_lot public.commercial_credit_lots%ROWTYPE;
    v_allocated numeric;
    v_expired numeric;
    v_count integer := 0;
BEGIN
    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 1000 THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_EXPIRY_LIMIT_INVALID';
    END IF;
    FOR v_res IN
        SELECT * FROM public.commercial_credit_reservations
         WHERE organization_id = v_org AND status = 'HELD' AND expires_at <= now()
         ORDER BY expires_at, reservation_id LIMIT p_limit FOR UPDATE SKIP LOCKED
    LOOP
        IF v_res.funding_source = 'ONE_TIME_ENTITLEMENT' THEN
            UPDATE public.project_generation_entitlements
               SET status = CASE WHEN expires_at > now() THEN 'AVAILABLE' ELSE 'EXPIRED' END,
                   held_by_job_id = NULL, updated_at = now()
             WHERE entitlement_id = v_res.entitlement_id AND status = 'HELD'
               AND held_by_job_id = v_res.job_id;
            IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_CREDIT_ENTITLEMENT_DRIFT'; END IF;
        ELSE
            v_allocated := 0;
            v_expired := 0;
            FOR v_allocation IN
                SELECT * FROM public.commercial_credit_reservation_lots
                 WHERE organization_id = v_org AND reservation_id = v_res.reservation_id
                 ORDER BY lot_id FOR UPDATE
            LOOP
                v_allocated := v_allocated + v_allocation.quantity;
                SELECT * INTO v_lot FROM public.commercial_credit_lots
                 WHERE lot_id = v_allocation.lot_id
                   AND organization_id = v_org
                 FOR UPDATE;
                IF NOT FOUND OR v_lot.reserved < v_allocation.quantity THEN
                    RAISE EXCEPTION 'ELMOS_CREDIT_LOT_DRIFT';
                END IF;
                IF v_lot.expires_at <= now() THEN
                    -- The lot TTL applies to both the held slice and any
                    -- unreserved remainder. Retaining that remainder would
                    -- leave account.balance above the authoritative lot sum.
                    v_expired := v_expired + v_lot.available + v_allocation.quantity;
                    UPDATE public.commercial_credit_lots
                       SET available = 0,
                           reserved = reserved - v_allocation.quantity,
                           consumed = consumed + v_lot.available + v_allocation.quantity,
                           status = CASE WHEN reserved - v_allocation.quantity = 0
                                         THEN 'EXPIRED' ELSE status END,
                           updated_at = now()
                     WHERE lot_id = v_allocation.lot_id AND organization_id = v_org;
                ELSE
                    UPDATE public.commercial_credit_lots
                       SET reserved = reserved - v_allocation.quantity,
                           available = available + v_allocation.quantity,
                           updated_at = now()
                     WHERE lot_id = v_allocation.lot_id AND organization_id = v_org;
                END IF;
            END LOOP;
            IF v_allocated <> v_res.requested_credits THEN
                RAISE EXCEPTION 'ELMOS_CREDIT_LOT_DRIFT';
            END IF;
            PERFORM pg_catalog.set_config('app.commercial_credit_posting', 'on', true);
            UPDATE public.commercial_credit_accounts
               SET balance = balance - v_expired,
                   reserved = reserved - v_res.requested_credits,
                   account_version = account_version + 1, updated_at = now()
             WHERE organization_id = v_org
               AND balance >= v_expired AND reserved >= v_res.requested_credits;
            PERFORM pg_catalog.set_config('app.commercial_credit_posting', '', true);
            IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_CREDIT_ACCOUNT_DRIFT'; END IF;
        END IF;
        UPDATE public.commercial_credit_reservations
           SET status = 'EXPIRED', updated_at = now()
         WHERE reservation_id = v_res.reservation_id AND organization_id = v_org;
        v_count := v_count + 1;
    END LOOP;
    -- Once holds have been resolved, retire every unreserved quantity whose lot
    -- TTL has elapsed. This keeps the materialized account balance equal to the
    -- lot ledger even when no new reservation is attempted after expiry.
    v_expired := 0;
    FOR v_lot IN
        SELECT * FROM public.commercial_credit_lots
         WHERE organization_id = v_org AND status = 'ACTIVE'
           AND expires_at <= now() AND available > 0
         ORDER BY expires_at, lot_id FOR UPDATE
    LOOP
        v_expired := v_expired + v_lot.available;
        UPDATE public.commercial_credit_lots
           SET available = 0, consumed = consumed + v_lot.available,
               status = CASE WHEN reserved = 0 THEN 'EXPIRED' ELSE status END,
               updated_at = now()
         WHERE lot_id = v_lot.lot_id AND organization_id = v_org;
    END LOOP;
    IF v_expired > 0 THEN
        PERFORM pg_catalog.set_config('app.commercial_credit_posting', 'on', true);
        UPDATE public.commercial_credit_accounts
           SET balance = balance - v_expired,
               account_version = account_version + 1, updated_at = now()
         WHERE organization_id = v_org AND balance >= v_expired;
        PERFORM pg_catalog.set_config('app.commercial_credit_posting', '', true);
        IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_CREDIT_ACCOUNT_DRIFT'; END IF;
    END IF;
    RETURN v_count;
EXCEPTION WHEN OTHERS THEN
    PERFORM pg_catalog.set_config('app.commercial_credit_posting', '', true);
    RAISE;
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
END
$$;
