-- V86 used the optional payment role for new translation grants. Keep existing
-- payment rights unchanged; translation has its own explicitly provisioned role.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='elmos_billing_runtime') THEN
        REVOKE SELECT ON execution_input_bindings FROM elmos_billing_runtime;
        REVOKE EXECUTE ON FUNCTION elmos_prepare_execution_input(varchar,varchar,varchar,varchar,varchar,bigint),
            elmos_attach_execution_input(varchar,varchar,varchar), elmos_translation_billing_guard()
            FROM elmos_billing_runtime;
    END IF;
END $$;
