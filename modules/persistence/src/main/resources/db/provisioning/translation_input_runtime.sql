-- Explicit, operator-owned PUBLIC-schema hosted translation capability bundle.
-- Apply after V88 with the approved migration administrator. This is NOT an
-- application startup action and grants no LOGIN, password or membership.
-- The operator separately grants this exact role to the configured control-plane
-- database login; it supplements, never replaces, that service's existing grants.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='elmos_translation_input_runtime') THEN
        CREATE ROLE elmos_translation_input_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS
            NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles r WHERE r.rolname='elmos_translation_input_runtime'
        AND (r.rolsuper OR r.rolbypassrls OR r.rolcanlogin OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication
             OR EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member=r.oid))) THEN
        RAISE EXCEPTION 'ELMOS_TRANSLATION_RUNTIME_ROLE_UNSAFE';
    END IF;
END $$;
GRANT USAGE ON SCHEMA public TO elmos_translation_input_runtime;
GRANT SELECT ON public.execution_input_bindings TO elmos_translation_input_runtime;
GRANT EXECUTE ON FUNCTION public.elmos_prepare_execution_input(varchar,varchar,varchar,varchar,varchar,bigint),
    public.elmos_attach_execution_input(varchar,varchar,varchar), public.elmos_translation_billing_guard()
    TO elmos_translation_input_runtime;
-- No access to private counters, no tenant-policy changes, no wallet writes.
