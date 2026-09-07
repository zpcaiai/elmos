-- PostgreSQL target schema for the PI Harness.  This migration is data only;
-- it is never executed by the source-package validator.
CREATE TABLE IF NOT EXISTS pi_tenant (
  tenant_id uuid PRIMARY KEY,
  display_name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pi_project (
  project_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES pi_tenant(tenant_id),
  name text NOT NULL,
  repository_uri text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pi_task (
  task_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES pi_tenant(tenant_id),
  project_id uuid NOT NULL REFERENCES pi_project(project_id),
  parent_task_id uuid REFERENCES pi_task(task_id),
  objective text NOT NULL,
  state text NOT NULL,
  request_json jsonb NOT NULL,
  required_verifications integer NOT NULL DEFAULT 0 CHECK (required_verifications >= 0),
  passed_verifications integer NOT NULL DEFAULT 0 CHECK (passed_verifications >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pi_task_tenant_state_idx ON pi_task(tenant_id, state);
CREATE TABLE IF NOT EXISTS pi_task_event (
  sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id uuid NOT NULL UNIQUE,
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  task_id uuid NOT NULL REFERENCES pi_task(task_id),
  task_sequence bigint NOT NULL,
  event_type text NOT NULL,
  actor_id text NOT NULL,
  correlation_id uuid,
  causation_id uuid,
  payload_version integer NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(task_id, task_sequence)
);
CREATE TABLE IF NOT EXISTS pi_idempotency_key (
  tenant_id uuid NOT NULL,
  scope text NOT NULL,
  idempotency_key text NOT NULL,
  request_digest text NOT NULL,
  response_json jsonb,
  state text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  PRIMARY KEY(tenant_id, scope, idempotency_key)
);
CREATE TABLE IF NOT EXISTS pi_execution_environment (
  environment_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES pi_tenant(tenant_id),
  execution_id uuid NOT NULL,
  owner_execution_id uuid NOT NULL,
  generation bigint NOT NULL DEFAULT 0,
  environment_type text NOT NULL,
  config jsonb NOT NULL,
  sandbox_overrides jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pi_authority_snapshot (
  authority_snapshot_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES pi_tenant(tenant_id),
  authority_owner_id uuid NOT NULL,
  environment_id uuid NOT NULL REFERENCES pi_execution_environment(environment_id),
  permission_profile_version text NOT NULL,
  allowed_capabilities jsonb NOT NULL,
  denied_capabilities jsonb NOT NULL,
  sandbox_overrides jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pi_workspace_lease (
  workspace_id text PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES pi_tenant(tenant_id),
  owner_execution_id uuid NOT NULL,
  generation bigint NOT NULL,
  repository_id text NOT NULL,
  base_revision text NOT NULL,
  lifecycle_state text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  heartbeat_at timestamptz NOT NULL,
  lease_expires_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- The service sets this transaction-local value from its authenticated
-- identity.  A missing value yields no rows and no writable policy match.
CREATE OR REPLACE FUNCTION pi_current_tenant() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('elmos.tenant_id', true), '')::uuid
$$;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['pi_project','pi_task','pi_task_event','pi_idempotency_key','pi_execution_environment','pi_authority_snapshot','pi_workspace_lease'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS pi_tenant_isolation ON %I', table_name);
    EXECUTE format('CREATE POLICY pi_tenant_isolation ON %I USING (tenant_id = pi_current_tenant()) WITH CHECK (tenant_id = pi_current_tenant())', table_name);
  END LOOP;
END $$;
