-- ELMOS PDHI v1 PostgreSQL control-plane schema.
-- PostgreSQL 16+; apply only through a separately authorized migrator.
-- This migration never creates login roles or credentials. The cluster owner
-- must pre-create NOLOGIN group role pdhi_runtime and bind exact workload
-- identities to it through the approved IAM/database workflow.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL idle_in_transaction_session_timeout = '60s';

DO $pdhi_role_check$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'pdhi_runtime') THEN
    RAISE EXCEPTION 'required NOLOGIN group role pdhi_runtime is absent';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles
    WHERE rolname = 'pdhi_runtime'
      AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolcanlogin)
  ) THEN
    RAISE EXCEPTION 'pdhi_runtime must be NOLOGIN and must not bypass RLS or own cluster privileges';
  END IF;
END
$pdhi_role_check$;

CREATE SCHEMA IF NOT EXISTS pdhi;
REVOKE ALL ON SCHEMA pdhi FROM PUBLIC;

CREATE TABLE IF NOT EXISTS pdhi.schema_migrations (
  version integer PRIMARY KEY CHECK (version > 0),
  source_sha256 text NOT NULL CHECK (source_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  applied_by text NOT NULL DEFAULT session_user
);
REVOKE ALL ON TABLE pdhi.schema_migrations FROM PUBLIC, pdhi_runtime;

CREATE OR REPLACE FUNCTION pdhi.current_tenant_id()
RETURNS text
LANGUAGE sql
STABLE
PARALLEL SAFE
SET search_path = pg_catalog
AS $$ SELECT NULLIF(current_setting('elmos.tenant_id', true), '') $$;

CREATE OR REPLACE FUNCTION pdhi.current_project_id()
RETURNS text
LANGUAGE sql
STABLE
PARALLEL SAFE
SET search_path = pg_catalog
AS $$ SELECT NULLIF(current_setting('elmos.project_id', true), '') $$;

REVOKE ALL ON FUNCTION pdhi.current_tenant_id() FROM PUBLIC;
REVOKE ALL ON FUNCTION pdhi.current_project_id() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pdhi.current_tenant_id() TO pdhi_runtime;
GRANT EXECUTE ON FUNCTION pdhi.current_project_id() TO pdhi_runtime;

CREATE TABLE IF NOT EXISTS pdhi.scopes (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id),
  CHECK (length(tenant_id) BETWEEN 1 AND 256),
  CHECK (length(project_id) BETWEEN 1 AND 256)
);

CREATE TABLE IF NOT EXISTS pdhi.jobs (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  job_id text NOT NULL,
  actor_id text NOT NULL,
  state text NOT NULL CHECK (state IN (
    'QUEUED','PREFLIGHT','PLANNING','EXECUTING','VERIFYING','CERTIFYING',
    'READY_TO_RELEASE','RELEASED','PAUSED','BLOCKED','RETRYING',
    'ROLLING_BACK','FAILED','CANCELLED','QUARANTINED'
  )),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  input_revision text NOT NULL,
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  environment_revision text NOT NULL CHECK (environment_revision ~ '^sha256:[0-9a-f]{64}$'),
  payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, job_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES pdhi.scopes (tenant_id, project_id)
);

CREATE INDEX IF NOT EXISTS pdhi_jobs_state_idx
  ON pdhi.jobs (tenant_id, project_id, state, updated_at, job_id);

CREATE TABLE IF NOT EXISTS pdhi.idempotency (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  operation text NOT NULL,
  idempotency_key text NOT NULL,
  request_digest text NOT NULL CHECK (request_digest ~ '^sha256:[0-9a-f]{64}$'),
  status text NOT NULL CHECK (status IN ('PENDING','COMPLETED','ABANDONED')),
  response jsonb CHECK (response IS NULL OR jsonb_typeof(response) = 'object'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  completed_at timestamptz,
  PRIMARY KEY (tenant_id, project_id, operation, idempotency_key),
  FOREIGN KEY (tenant_id, project_id) REFERENCES pdhi.scopes (tenant_id, project_id),
  CHECK ((status = 'COMPLETED') = (response IS NOT NULL AND completed_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS pdhi.leases (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  resource_id text NOT NULL,
  owner_id text NOT NULL,
  token_digest text NOT NULL CHECK (token_digest ~ '^sha256:[0-9a-f]{64}$'),
  generation bigint NOT NULL CHECK (generation > 0),
  state text NOT NULL CHECK (state IN ('ACTIVE','REVOKED','EXPIRED')),
  expires_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, resource_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES pdhi.scopes (tenant_id, project_id)
);

CREATE TABLE IF NOT EXISTS pdhi.effects (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  effect_id text NOT NULL,
  job_id text NOT NULL,
  operation text NOT NULL,
  idempotency_key text NOT NULL,
  request_digest text NOT NULL CHECK (request_digest ~ '^sha256:[0-9a-f]{64}$'),
  request jsonb NOT NULL CHECK (jsonb_typeof(request) = 'object'),
  state text NOT NULL CHECK (state IN (
    'PREPARED','STARTED','SUCCEEDED','FAILED','UNKNOWN','CANCELLED',
    'COMPENSATING','COMPENSATED'
  )),
  response jsonb CHECK (response IS NULL OR jsonb_typeof(response) = 'object'),
  external_reference_digest text CHECK (
    external_reference_digest IS NULL OR external_reference_digest ~ '^sha256:[0-9a-f]{64}$'
  ),
  lease_resource text NOT NULL,
  lease_generation bigint NOT NULL CHECK (lease_generation > 0),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, effect_id),
  UNIQUE (tenant_id, project_id, operation, idempotency_key),
  FOREIGN KEY (tenant_id, project_id, job_id)
    REFERENCES pdhi.jobs (tenant_id, project_id, job_id)
);

CREATE INDEX IF NOT EXISTS pdhi_effects_reconciliation_idx
  ON pdhi.effects (tenant_id, project_id, state, updated_at, effect_id)
  WHERE state IN ('PREPARED','STARTED','UNKNOWN','COMPENSATING');

CREATE TABLE IF NOT EXISTS pdhi.outbox (
  event_id bigint GENERATED ALWAYS AS IDENTITY,
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  topic text NOT NULL,
  aggregate_id text NOT NULL,
  payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
  state text NOT NULL CHECK (state IN ('PENDING','CLAIMED','DELIVERED','DEAD_LETTER')),
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  claimed_by text,
  claimed_until timestamptz,
  delivery_token_digest text CHECK (
    delivery_token_digest IS NULL OR delivery_token_digest ~ '^sha256:[0-9a-f]{64}$'
  ),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  delivered_at timestamptz,
  PRIMARY KEY (tenant_id, project_id, event_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES pdhi.scopes (tenant_id, project_id)
);

CREATE INDEX IF NOT EXISTS pdhi_outbox_ready_idx
  ON pdhi.outbox (tenant_id, project_id, available_at, event_id)
  WHERE state = 'PENDING';

CREATE TABLE IF NOT EXISTS pdhi.audit (
  audit_id bigint GENERATED ALWAYS AS IDENTITY,
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  actor_id text NOT NULL,
  operation text NOT NULL,
  aggregate_id text NOT NULL,
  decision text NOT NULL,
  detail jsonb NOT NULL CHECK (jsonb_typeof(detail) = 'object'),
  previous_digest text CHECK (previous_digest IS NULL OR previous_digest ~ '^sha256:[0-9a-f]{64}$'),
  record_digest text NOT NULL CHECK (record_digest ~ '^sha256:[0-9a-f]{64}$'),
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, audit_id),
  UNIQUE (tenant_id, project_id, record_digest),
  FOREIGN KEY (tenant_id, project_id) REFERENCES pdhi.scopes (tenant_id, project_id)
);

CREATE INDEX IF NOT EXISTS pdhi_audit_scope_idx
  ON pdhi.audit (tenant_id, project_id, audit_id);

CREATE TABLE IF NOT EXISTS pdhi.metrics (
  metric_id bigint GENERATED ALWAYS AS IDENTITY,
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  job_id text NOT NULL,
  metric_name text NOT NULL,
  value_decimal numeric(38, 12) NOT NULL,
  unit text NOT NULL,
  currency text CHECK (currency IS NULL OR currency ~ '^[A-Z]{3}$'),
  grain text NOT NULL,
  definition_version text NOT NULL,
  observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, metric_id),
  FOREIGN KEY (tenant_id, project_id, job_id)
    REFERENCES pdhi.jobs (tenant_id, project_id, job_id)
);

CREATE INDEX IF NOT EXISTS pdhi_metrics_rollup_idx
  ON pdhi.metrics (tenant_id, project_id, job_id, metric_name, currency, observed_at);

CREATE TABLE IF NOT EXISTS pdhi.agent_controls (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  job_id text NOT NULL,
  agent_id text NOT NULL,
  state text NOT NULL CHECK (state IN ('RUNNING','PAUSED','KILLED','FAILED','SUCCEEDED')),
  generation bigint NOT NULL CHECK (generation > 0),
  command jsonb NOT NULL CHECK (jsonb_typeof(command) = 'object'),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, job_id, agent_id),
  FOREIGN KEY (tenant_id, project_id, job_id)
    REFERENCES pdhi.jobs (tenant_id, project_id, job_id)
);

CREATE TABLE IF NOT EXISTS pdhi.provider_sessions (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  job_id text NOT NULL,
  session_id text NOT NULL,
  provider_id text NOT NULL,
  state text NOT NULL CHECK (state IN ('ACTIVE','STALE','ROTATED','RESET_REQUIRED','CLOSED')),
  generation bigint NOT NULL CHECK (generation > 0),
  external_ref_digest text CHECK (
    external_ref_digest IS NULL OR external_ref_digest ~ '^sha256:[0-9a-f]{64}$'
  ),
  checkpoint_digest text CHECK (
    checkpoint_digest IS NULL OR checkpoint_digest ~ '^sha256:[0-9a-f]{64}$'
  ),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, job_id, session_id),
  FOREIGN KEY (tenant_id, project_id, job_id)
    REFERENCES pdhi.jobs (tenant_id, project_id, job_id)
);

CREATE TABLE IF NOT EXISTS pdhi.bridge_receipts (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  receipt_id text NOT NULL,
  boundary text NOT NULL CHECK (boundary IN ('EVIDENCE','EXTERNAL_EFFECT','CERTIFICATION')),
  subject_digest text NOT NULL CHECK (subject_digest ~ '^sha256:[0-9a-f]{64}$'),
  receipt_digest text NOT NULL CHECK (receipt_digest ~ '^sha256:[0-9a-f]{64}$'),
  status text NOT NULL CHECK (status IN (
    'NOT_RUN','PREPARED','RECORDED','RECONCILIATION_REQUIRED',
    'EXTERNALLY_VERIFIED','CERTIFIED','REVOKED'
  )),
  provider_id text NOT NULL,
  independent boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz,
  PRIMARY KEY (tenant_id, project_id, receipt_id),
  UNIQUE (tenant_id, project_id, receipt_digest),
  FOREIGN KEY (tenant_id, project_id) REFERENCES pdhi.scopes (tenant_id, project_id),
  CHECK (status <> 'CERTIFIED' OR independent)
);

-- Every tenant-bearing table is protected by both ENABLE and FORCE RLS. A
-- missing transaction-local scope resolves to NULL and matches no rows.
DO $pdhi_rls$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'scopes','jobs','idempotency','leases','effects','outbox','audit',
    'metrics','agent_controls','provider_sessions','bridge_receipts'
  ]
  LOOP
    EXECUTE format('ALTER TABLE pdhi.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE pdhi.%I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS pdhi_exact_scope ON pdhi.%I', table_name);
    EXECUTE format(
      'CREATE POLICY pdhi_exact_scope ON pdhi.%I TO pdhi_runtime '
      'USING (tenant_id = pdhi.current_tenant_id() AND project_id = pdhi.current_project_id()) '
      'WITH CHECK (tenant_id = pdhi.current_tenant_id() AND project_id = pdhi.current_project_id())',
      table_name
    );
  END LOOP;
END
$pdhi_rls$;

REVOKE ALL ON ALL TABLES IN SCHEMA pdhi FROM PUBLIC, pdhi_runtime;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA pdhi FROM PUBLIC, pdhi_runtime;
GRANT USAGE ON SCHEMA pdhi TO pdhi_runtime;
GRANT SELECT ON pdhi.scopes TO pdhi_runtime;
GRANT SELECT, INSERT, UPDATE ON pdhi.jobs, pdhi.idempotency, pdhi.leases,
  pdhi.effects, pdhi.outbox, pdhi.agent_controls, pdhi.provider_sessions TO pdhi_runtime;
GRANT SELECT, INSERT ON pdhi.audit, pdhi.metrics, pdhi.bridge_receipts TO pdhi_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA pdhi TO pdhi_runtime;

-- The migration digest is supplied independently by the release runner after
-- it verifies these exact bytes; a self-referential embedded hash is invalid.
DO $pdhi_migration_ledger$
DECLARE
  supplied_digest text := current_setting('elmos.migration_source_sha256');
  existing_digest text;
BEGIN
  IF supplied_digest !~ '^sha256:[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'elmos.migration_source_sha256 must be an independently computed SHA-256 digest';
  END IF;
  SELECT source_sha256 INTO existing_digest
  FROM pdhi.schema_migrations
  WHERE version = 1
  FOR UPDATE;
  IF existing_digest IS NULL THEN
    INSERT INTO pdhi.schema_migrations (version, source_sha256)
    VALUES (1, supplied_digest);
  ELSIF existing_digest <> supplied_digest THEN
    RAISE EXCEPTION 'migration V001 digest drift: stored %, supplied %', existing_digest, supplied_digest;
  END IF;
END
$pdhi_migration_ledger$;

COMMIT;
