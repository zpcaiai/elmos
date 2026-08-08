-- V64: make the payment order directory trigger compatible with least privilege.
--
-- V62 intentionally grants the billing runtime SELECT-only access to
-- payment_order_directory, but its trigger function originally ran as the
-- calling runtime role. Inserts into payment_checkout_sessions therefore
-- failed inside the trigger with permission denied. Direct directory writes
-- must remain denied, so granting INSERT/UPDATE to the runtime role is not an
-- acceptable fix.
--
-- Replace only the trigger function. The migration owner performs the bounded
-- directory UPSERT through SECURITY DEFINER, with an explicit search path and
-- a schema-qualified target. The application role keeps no direct write or
-- function-execution permission.

CREATE OR REPLACE FUNCTION elmos_sync_payment_order_directory()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    INSERT INTO public.payment_order_directory (
        checkout_session_id, organization_id, plan_id, amount_minor, status)
    VALUES (
        NEW.checkout_session_id, NEW.organization_id, NEW.plan_id,
        NEW.amount_minor, NEW.status)
    ON CONFLICT (checkout_session_id) DO UPDATE
        SET status = EXCLUDED.status,
            updated_at = pg_catalog.now();
    -- Organization, plan and amount remain first-write facts. A later source
    -- mismatch stays visible for reconciliation instead of silently rewriting
    -- the cross-tenant lookup projection.
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION elmos_sync_payment_order_directory() FROM PUBLIC;

COMMENT ON FUNCTION elmos_sync_payment_order_directory() IS
    'Trigger-only, least-privileged synchronization from the FORCE-RLS checkout table to the minimal payment order directory. SECURITY DEFINER is bounded by a fixed search_path and schema-qualified target.';
