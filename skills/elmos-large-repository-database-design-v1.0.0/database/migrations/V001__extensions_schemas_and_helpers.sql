-- Elmos large-repository generation / repository-conversion data plane.
-- PostgreSQL 16+. Application-generated UUIDv7 is recommended; extensions.gen_random_uuid()
-- is retained as a compatible database-side fallback.

BEGIN;

CREATE SCHEMA IF NOT EXISTS extensions;
REVOKE CREATE ON SCHEMA extensions FROM PUBLIC;

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;

-- A database may already have these relocatable extensions in public. Move
-- them into the locked extension schema before any qualified type/function use.
DO $$
DECLARE
  v_extension text;
BEGIN
  FOREACH v_extension IN ARRAY ARRAY['pgcrypto', 'citext', 'pg_trgm']
  LOOP
    IF EXISTS (
      SELECT 1
      FROM pg_catalog.pg_extension e
      JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace
      WHERE e.extname = v_extension AND n.nspname <> 'extensions'
    ) THEN
      EXECUTE format('ALTER EXTENSION %I SET SCHEMA extensions', v_extension);
    END IF;
  END LOOP;
END;
$$;

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS exec;
CREATE SCHEMA IF NOT EXISTS artifact;
CREATE SCHEMA IF NOT EXISTS analysis;
CREATE SCHEMA IF NOT EXISTS generation;
CREATE SCHEMA IF NOT EXISTS transform;
CREATE SCHEMA IF NOT EXISTS verify;
CREATE SCHEMA IF NOT EXISTS metering;
CREATE SCHEMA IF NOT EXISTS cache;
CREATE SCHEMA IF NOT EXISTS integration;
CREATE SCHEMA IF NOT EXISTS learning;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE OR REPLACE FUNCTION core.current_tenant_id()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION core.current_actor_id()
RETURNS text
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.actor_id', true), '')
$$;

CREATE OR REPLACE FUNCTION core.current_request_id()
RETURNS text
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.request_id', true), '')
$$;

CREATE OR REPLACE FUNCTION core.touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION core.reject_update_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION '% is append-only; % is forbidden', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, TG_OP
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION core.reject_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION '% cannot be deleted', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION core.sha256_is_valid(value text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
RETURNS NULL ON NULL INPUT
AS $$
  SELECT value ~ '^[0-9a-f]{64}$'
$$;

CREATE OR REPLACE FUNCTION core.nonblank(value text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
RETURNS NULL ON NULL INPUT
AS $$
  SELECT length(btrim(value)) > 0
$$;

CREATE OR REPLACE FUNCTION core.json_object_or_empty(value jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT jsonb_typeof(COALESCE(value, '{}'::jsonb)) = 'object'
$$;

COMMENT ON FUNCTION core.current_tenant_id() IS
  'RLS tenant context. The application transaction must SET LOCAL app.tenant_id before tenant-scoped reads or writes.';
COMMENT ON FUNCTION core.reject_update_delete() IS
  'Trigger for immutable ledger/event/evidence facts; corrections are new rows, never mutation.';

COMMIT;
