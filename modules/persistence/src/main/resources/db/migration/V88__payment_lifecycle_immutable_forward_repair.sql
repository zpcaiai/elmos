-- Forward-only repair for payment lifecycle hardening that was previously
-- (incorrectly) edited into already-applied V84-V86 migrations. Those migration
-- files are immutable again; all live database changes belong to this version.

-- Reconcile provider bindings using the tenant key and fail closed on drift.
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

-- Preserve only the prepare-outcome-unknown recovery path and hold late payments
-- for explicit reconciliation.
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

-- Expire both held and unreserved quantities without minting spendable Credit.
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
