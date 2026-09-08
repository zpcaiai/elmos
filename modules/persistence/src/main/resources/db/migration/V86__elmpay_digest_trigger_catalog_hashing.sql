-- V86 repairs the V84 ELMPay order-directory triggers without changing the
-- already-released V84 migration checksum. PostgreSQL provides sha256(bytea)
-- and encode(bytea, text) in pg_catalog, so trigger execution must not depend
-- on the schema chosen when the optional pgcrypto extension was installed.

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
        pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
            NEW.out_trade_no, 'UTF8')), 'hex'),
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
        pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
            NEW.out_trade_no, 'UTF8')), 'hex'),
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
