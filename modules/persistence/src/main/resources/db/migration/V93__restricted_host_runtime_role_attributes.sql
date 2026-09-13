-- Migration-time, read-only assertion. Do not auto-repair a preexisting role:
-- changing its memberships/privileges requires an accountable operator decision.
-- This creates no runtime execution authority and grants no memberships.
CREATE FUNCTION elmos_assert_restricted_host_role(p_role name) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE v_role record;
BEGIN
    SELECT * INTO v_role FROM pg_catalog.pg_roles WHERE rolname=p_role;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_RUNTIME_ROLE_UNKNOWN: %',p_role; END IF;
    IF v_role.rolcanlogin OR v_role.rolsuper OR v_role.rolbypassrls OR v_role.rolinherit
      OR v_role.rolcreaterole OR v_role.rolcreatedb OR v_role.rolreplication
      OR EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=v_role.oid) THEN
        RAISE EXCEPTION 'ELMOS_RUNTIME_ROLE_UNSAFE: %',p_role;
    END IF;
END $$;
REVOKE ALL ON FUNCTION elmos_assert_restricted_host_role(name) FROM PUBLIC;

DO $$ DECLARE v_role name; BEGIN
    FOREACH v_role IN ARRAY ARRAY['elmos_object_gc_host','elmos_translation_input_runtime']::name[] LOOP
        IF EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname=v_role) THEN
            PERFORM public.elmos_assert_restricted_host_role(v_role);
        END IF;
    END LOOP;
END $$;
