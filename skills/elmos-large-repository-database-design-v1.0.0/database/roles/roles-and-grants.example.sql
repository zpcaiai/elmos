-- Run as a PostgreSQL administrator after Flyway V090.
-- Adapt role names to the enterprise naming policy before production use.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_schema_owner') THEN
    CREATE ROLE elmos_schema_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_runtime_definer') THEN
    CREATE ROLE elmos_runtime_definer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_control_api') THEN
    CREATE ROLE elmos_control_api NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_scheduler') THEN
    CREATE ROLE elmos_scheduler NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_runtime_gateway') THEN
    CREATE ROLE elmos_runtime_gateway NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_verifier') THEN
    CREATE ROLE elmos_verifier NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_deployment_gate') THEN
    CREATE ROLE elmos_deployment_gate NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOBYPASSRLS;
  END IF;
END;
$$;

REVOKE ALL ON SCHEMA extensions, core, exec, artifact, analysis, generation,
  transform, verify, metering, cache, integration, learning, ops, audit FROM PUBLIC;

-- Transfer business schemas and persistent relations away from the Flyway login.
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT nspname
    FROM pg_namespace
    WHERE nspname IN ('core','exec','artifact','analysis','generation','transform',
      'verify','metering','cache','integration','learning','ops','audit')
  LOOP
    EXECUTE format('ALTER SCHEMA %I OWNER TO elmos_schema_owner', r.nspname);
  END LOOP;

  FOR r IN
    SELECT n.nspname, c.relname, c.relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('core','exec','artifact','analysis','generation','transform',
      'verify','metering','cache','integration','learning','ops','audit')
      AND c.relkind IN ('r','p','S','v','m')
  LOOP
    EXECUTE CASE r.relkind
      WHEN 'S' THEN format('ALTER SEQUENCE %I.%I OWNER TO elmos_schema_owner', r.nspname, r.relname)
      WHEN 'v' THEN format('ALTER VIEW %I.%I OWNER TO elmos_schema_owner', r.nspname, r.relname)
      WHEN 'm' THEN format('ALTER MATERIALIZED VIEW %I.%I OWNER TO elmos_schema_owner', r.nspname, r.relname)
      ELSE format('ALTER TABLE %I.%I OWNER TO elmos_schema_owner', r.nspname, r.relname)
    END;
  END LOOP;

  FOR r IN
    SELECT p.oid, n.nspname, p.proname,
           pg_get_function_identity_arguments(p.oid) AS identity_arguments
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE NOT p.prosecdef
      AND n.nspname IN ('core','exec','artifact','analysis','generation','transform',
        'verify','metering','cache','integration','learning','ops','audit')
  LOOP
    EXECUTE format(
      'ALTER FUNCTION %I.%I(%s) OWNER TO elmos_schema_owner',
      r.nspname, r.proname, r.identity_arguments
    );
  END LOOP;
END;
$$;
GRANT USAGE ON SCHEMA extensions, core, exec, artifact, analysis, generation,
  transform, verify, metering, cache, integration, learning, ops, audit TO elmos_runtime_definer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core, exec, artifact,
  analysis, generation, transform, verify, metering, cache, integration, learning, ops, audit
  TO elmos_runtime_definer;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA core, exec, artifact,
  analysis, generation, transform, verify, metering, cache, integration, learning, ops, audit
  TO elmos_runtime_definer;
GRANT EXECUTE ON FUNCTION extensions.digest(bytea, text) TO elmos_runtime_definer;
GRANT EXECUTE ON FUNCTION extensions.digest(text, text) TO elmos_runtime_definer;
GRANT EXECUTE ON FUNCTION extensions.gen_random_uuid() TO elmos_runtime_definer;

-- Transfer only SECURITY DEFINER functions in the approved Elmos schemas.
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid, n.nspname, p.proname,
           pg_get_function_identity_arguments(p.oid) AS identity_arguments
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE p.prosecdef
      AND n.nspname IN ('core','exec','integration','verify','ops')
  LOOP
    EXECUTE format(
      'ALTER FUNCTION %I.%I(%s) OWNER TO elmos_runtime_definer',
      r.nspname, r.proname, r.identity_arguments
    );
    EXECUTE format(
      'REVOKE ALL ON FUNCTION %I.%I(%s) FROM PUBLIC',
      r.nspname, r.proname, r.identity_arguments
    );
  END LOOP;
END;
$$;

GRANT USAGE ON SCHEMA core, exec TO elmos_control_api, elmos_scheduler, elmos_runtime_gateway;
GRANT USAGE ON SCHEMA integration TO elmos_runtime_gateway;
GRANT USAGE ON SCHEMA verify TO elmos_verifier;
GRANT USAGE ON SCHEMA ops TO elmos_deployment_gate;

GRANT EXECUTE ON FUNCTION exec.create_run(uuid, uuid, text, text, uuid, uuid, uuid, uuid, uuid, uuid, uuid, uuid, uuid, uuid)
  TO elmos_control_api;
GRANT EXECUTE ON FUNCTION core.claim_account_slot(uuid, uuid, uuid, interval),
  core.renew_account_slot(uuid, uuid, uuid, smallint, bigint, uuid, interval),
  core.release_account_slot(uuid, uuid, uuid, bigint),
  exec.claim_ready_task(uuid, uuid, uuid, interval),
  exec.renew_task_lease(uuid, uuid, uuid, bigint, uuid, interval),
  exec.finish_task_attempt(uuid, uuid, uuid, bigint, uuid, text, boolean, uuid, uuid, text, jsonb),
  exec.refresh_run_progress(uuid, uuid)
  TO elmos_scheduler;
GRANT EXECUTE ON FUNCTION exec.append_run_event(uuid, uuid, text, jsonb, text, text, uuid, uuid, text, uuid),
  exec.append_session_event(uuid, uuid, text, jsonb, integer, integer, boolean, boolean, uuid),
  exec.seal_checkpoint(uuid, uuid),
  integration.reserve_side_effect(uuid, uuid, uuid, uuid, uuid, text, text, text, text)
  TO elmos_runtime_gateway;
GRANT EXECUTE ON FUNCTION verify.complete_run_with_gate(uuid, uuid, uuid)
  TO elmos_verifier;
GRANT EXECUTE ON FUNCTION ops.complete_deployment_with_gate(uuid, uuid, uuid)
  TO elmos_deployment_gate;

-- Existing Login Roles are granted membership outside this file, for example:
-- GRANT elmos_scheduler TO elmos_scheduler_login;
-- Never grant elmos_runtime_definer to a login role.
