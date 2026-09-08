-- ELMPay business webhooks deliberately expose only SHA-256(business_order_no), not the raw
-- merchant order number. Add an indexed, trigger-maintained projection for each callback order
-- directory so lookup remains bounded without weakening the existing FORCE-RLS source tables.

ALTER TABLE payment_order_directory
    ADD COLUMN business_order_sha256 char(64);
ALTER TABLE wallet_topup_order_directory
    ADD COLUMN business_order_sha256 char(64);
ALTER TABLE commercial_order_directory
    ADD COLUMN business_order_sha256 char(64);

UPDATE payment_order_directory
   SET business_order_sha256 = pg_catalog.encode(pg_catalog.sha256(
       pg_catalog.convert_to(checkout_session_id, 'UTF8')), 'hex');
UPDATE wallet_topup_order_directory
   SET business_order_sha256 = pg_catalog.encode(pg_catalog.sha256(
       pg_catalog.convert_to(out_trade_no, 'UTF8')), 'hex');
UPDATE commercial_order_directory
   SET business_order_sha256 = pg_catalog.encode(pg_catalog.sha256(
       pg_catalog.convert_to(out_trade_no, 'UTF8')), 'hex');

ALTER TABLE payment_order_directory
    ALTER COLUMN business_order_sha256 SET NOT NULL,
    ADD CONSTRAINT payment_order_directory_sha256_format
        CHECK (business_order_sha256 ~ '^[0-9a-f]{64}$');
ALTER TABLE wallet_topup_order_directory
    ALTER COLUMN business_order_sha256 SET NOT NULL,
    ADD CONSTRAINT wallet_topup_order_directory_sha256_format
        CHECK (business_order_sha256 ~ '^[0-9a-f]{64}$');
ALTER TABLE commercial_order_directory
    ALTER COLUMN business_order_sha256 SET NOT NULL,
    ADD CONSTRAINT commercial_order_directory_sha256_format
        CHECK (business_order_sha256 ~ '^[0-9a-f]{64}$');

CREATE UNIQUE INDEX payment_order_directory_business_order_sha256_idx
    ON payment_order_directory (business_order_sha256);
CREATE UNIQUE INDEX wallet_topup_order_directory_business_order_sha256_idx
    ON wallet_topup_order_directory (business_order_sha256);
CREATE UNIQUE INDEX commercial_order_directory_business_order_sha256_idx
    ON commercial_order_directory (business_order_sha256);

CREATE OR REPLACE FUNCTION elmos_sync_payment_order_directory()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    INSERT INTO public.payment_order_directory (
        checkout_session_id, business_order_sha256, organization_id, plan_id,
        amount_minor, status)
    VALUES (
        NEW.checkout_session_id,
        pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
            NEW.checkout_session_id, 'UTF8')), 'hex'),
        NEW.organization_id, NEW.plan_id, NEW.amount_minor, NEW.status)
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
        amount_minor, status)
    VALUES (
        NEW.out_trade_no,
        pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
            NEW.out_trade_no, 'UTF8')), 'hex'),
        NEW.topup_order_id, NEW.organization_id, NEW.amount_minor, NEW.status)
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
        amount_minor, status)
    VALUES (
        NEW.out_trade_no,
        pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
            NEW.out_trade_no, 'UTF8')), 'hex'),
        NEW.order_id, NEW.organization_id, NEW.order_type, NEW.amount_minor, NEW.status)
    ON CONFLICT (out_trade_no) DO UPDATE
       SET status = EXCLUDED.status, updated_at = pg_catalog.now();
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION elmos_sync_payment_order_directory() FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_sync_wallet_topup_directory() FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_sync_commercial_order_directory() FROM PUBLIC;

COMMENT ON COLUMN payment_order_directory.business_order_sha256 IS
    'ELMPay callback lookup key: lowercase SHA-256 of checkout_session_id.';
COMMENT ON COLUMN wallet_topup_order_directory.business_order_sha256 IS
    'ELMPay callback lookup key: lowercase SHA-256 of out_trade_no.';
COMMENT ON COLUMN commercial_order_directory.business_order_sha256 IS
    'ELMPay callback lookup key: lowercase SHA-256 of out_trade_no.';
