-- The caller MUST wrap this fixture in a transaction and ROLLBACK, including on
-- error. Only UUID-like disposable names are touched, never deployed role names.
DO $$
DECLARE v_role name:='role_guard_fixture_'||md5(clock_timestamp()::text||random()::text);
    v_parent name:='role_guard_parent_'||md5(clock_timestamp()::text||random()::text);
    v_flag text;
BEGIN
    EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEROLE NOCREATEDB NOREPLICATION',v_role);
    PERFORM public.elmos_assert_restricted_host_role(v_role);
    FOREACH v_flag IN ARRAY ARRAY['CREATEROLE','CREATEDB','REPLICATION','LOGIN','SUPERUSER','BYPASSRLS','INHERIT'] LOOP
        EXECUTE format('ALTER ROLE %I %s',v_role,v_flag);
        BEGIN
            PERFORM public.elmos_assert_restricted_host_role(v_role);
            RAISE EXCEPTION 'TEST_EXPECTED_UNSAFE_ROLE_REJECTION: %',v_flag;
        EXCEPTION WHEN OTHERS THEN
            IF SQLERRM NOT LIKE 'ELMOS_RUNTIME_ROLE_UNSAFE:%' THEN RAISE; END IF;
        END;
        IF NOT (SELECT CASE v_flag WHEN 'CREATEROLE' THEN rolcreaterole WHEN 'CREATEDB' THEN rolcreatedb
            WHEN 'REPLICATION' THEN rolreplication WHEN 'LOGIN' THEN rolcanlogin WHEN 'SUPERUSER' THEN rolsuper
            WHEN 'BYPASSRLS' THEN rolbypassrls WHEN 'INHERIT' THEN rolinherit END
            FROM pg_catalog.pg_roles WHERE rolname=v_role) THEN
            RAISE EXCEPTION 'TEST_GUARD_MUST_NOT_AUTO_REPAIR_ROLE';
        END IF;
        EXECUTE format('ALTER ROLE %I NO%s',v_role,v_flag);
        PERFORM public.elmos_assert_restricted_host_role(v_role);
    END LOOP;
    EXECUTE format('CREATE ROLE %I NOLOGIN NOINHERIT',v_parent);
    EXECUTE format('GRANT %I TO %I',v_parent,v_role);
    BEGIN
        PERFORM public.elmos_assert_restricted_host_role(v_role);
        RAISE EXCEPTION 'TEST_EXPECTED_ROLE_MEMBERSHIP_REJECTION';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM NOT LIKE 'ELMOS_RUNTIME_ROLE_UNSAFE:%' THEN RAISE; END IF;
    END;
    IF EXISTS(SELECT 1 FROM pg_catalog.pg_proc p
        CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
        WHERE p.oid='public.elmos_assert_restricted_host_role(name)'::regprocedure
          AND a.grantee=0 AND a.privilege_type='EXECUTE') THEN
        RAISE EXCEPTION 'TEST_ASSERTION_MUST_NOT_GRANT_PUBLIC_RUNTIME_AUTHORITY';
    END IF;
END $$;
