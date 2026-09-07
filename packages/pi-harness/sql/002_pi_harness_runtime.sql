-- Complete PostgreSQL runtime tables for the v5.1 kernel. The application
-- binds elmos.tenant_id transaction-locally before every tenant query.

CREATE TABLE IF NOT EXISTS pi_executor_connection (
  environment_id uuid NOT NULL REFERENCES pi_execution_environment(environment_id),
  executor_id text NOT NULL,
  executor_generation bigint NOT NULL CHECK (executor_generation >= 0),
  connection_epoch bigint NOT NULL CHECK (connection_epoch >= 0),
  state text NOT NULL,
  retired integer NOT NULL DEFAULT 0 CHECK (retired IN (0,1)),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(environment_id, executor_id, executor_generation)
);
CREATE INDEX IF NOT EXISTS pi_executor_active_idx ON pi_executor_connection(environment_id, retired, executor_generation);

CREATE TABLE IF NOT EXISTS pi_checkpoint (
  checkpoint_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES pi_tenant(tenant_id),
  task_id uuid NOT NULL REFERENCES pi_task(task_id),
  workspace_id text,
  owner_execution_id uuid NOT NULL,
  state_json jsonb NOT NULL,
  workspace_digest text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pi_tool_call (
  call_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES pi_tenant(tenant_id),
  task_id uuid NOT NULL REFERENCES pi_task(task_id),
  environment_id uuid NOT NULL REFERENCES pi_execution_environment(environment_id),
  authority_snapshot_id uuid NOT NULL REFERENCES pi_authority_snapshot(authority_snapshot_id),
  capability text NOT NULL,
  request_digest text NOT NULL,
  idempotency_key text NOT NULL,
  executor_id text NOT NULL,
  executor_generation bigint NOT NULL CHECK (executor_generation >= 0),
  state text NOT NULL,
  result_json jsonb,
  error_json jsonb,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  UNIQUE(tenant_id, task_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS pi_effect_journal (
  effect_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES pi_tenant(tenant_id),
  task_id uuid NOT NULL REFERENCES pi_task(task_id),
  action_kind text NOT NULL,
  parent_call_id uuid,
  status text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  resolver_id text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pi_artifact (
  artifact_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES pi_tenant(tenant_id),
  task_id uuid NOT NULL REFERENCES pi_task(task_id),
  logical_name text NOT NULL,
  media_type text NOT NULL,
  size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
  sha256 text NOT NULL,
  storage_uri text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id, task_id, sha256)
);

CREATE TABLE IF NOT EXISTS pi_campaign (
  campaign_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES pi_tenant(tenant_id),
  name text NOT NULL,
  mode text NOT NULL,
  definition_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pi_benchmark_run (
  run_id uuid PRIMARY KEY,
  campaign_id uuid NOT NULL REFERENCES pi_campaign(campaign_id),
  tenant_id uuid NOT NULL REFERENCES pi_tenant(tenant_id),
  system text NOT NULL,
  system_version text,
  repo_revision text NOT NULL,
  task_case text NOT NULL,
  repetition integer NOT NULL CHECK (repetition >= 0),
  validated_success integer CHECK (validated_success IS NULL OR validated_success IN (0,1)),
  evidence_level text NOT NULL,
  result_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(campaign_id, system, task_case, repetition)
);

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'pi_checkpoint','pi_tool_call','pi_effect_journal','pi_artifact',
    'pi_campaign','pi_benchmark_run'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS pi_tenant_isolation ON %I', table_name);
    EXECUTE format(
      'CREATE POLICY pi_tenant_isolation ON %I USING (tenant_id = pi_current_tenant()) WITH CHECK (tenant_id = pi_current_tenant())',
      table_name
    );
  END LOOP;
END $$;

-- Executor rows inherit tenant isolation through their environment. They do
-- not duplicate tenant_id, so their policy uses an EXISTS relationship.
ALTER TABLE pi_executor_connection ENABLE ROW LEVEL SECURITY;
ALTER TABLE pi_executor_connection FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pi_executor_tenant_isolation ON pi_executor_connection;
CREATE POLICY pi_executor_tenant_isolation ON pi_executor_connection
USING (EXISTS (
  SELECT 1 FROM pi_execution_environment environment
  WHERE environment.environment_id = pi_executor_connection.environment_id
    AND environment.tenant_id = pi_current_tenant()
))
WITH CHECK (EXISTS (
  SELECT 1 FROM pi_execution_environment environment
  WHERE environment.environment_id = pi_executor_connection.environment_id
    AND environment.tenant_id = pi_current_tenant()
));

-- FORCE RLS closes accidental owner bypass for all v5.1 tenant tables. A
-- separate migration role, never the service role, owns these objects.
ALTER TABLE pi_tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE pi_tenant FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pi_tenant_self_isolation ON pi_tenant;
CREATE POLICY pi_tenant_self_isolation ON pi_tenant
USING (tenant_id = pi_current_tenant())
WITH CHECK (tenant_id = pi_current_tenant());
ALTER TABLE pi_project FORCE ROW LEVEL SECURITY;
ALTER TABLE pi_task FORCE ROW LEVEL SECURITY;
ALTER TABLE pi_task_event FORCE ROW LEVEL SECURITY;
ALTER TABLE pi_idempotency_key FORCE ROW LEVEL SECURITY;
ALTER TABLE pi_execution_environment FORCE ROW LEVEL SECURITY;
ALTER TABLE pi_authority_snapshot FORCE ROW LEVEL SECURITY;
ALTER TABLE pi_workspace_lease FORCE ROW LEVEL SECURITY;
