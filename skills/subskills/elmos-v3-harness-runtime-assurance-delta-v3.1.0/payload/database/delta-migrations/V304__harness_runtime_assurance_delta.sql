-- Elmos v3.1.0 incremental migration. PostgreSQL 17.
BEGIN;

CREATE TABLE IF NOT EXISTS elmos_tool_result_commits (
  tenant_id text NOT NULL,
  invocation_id text NOT NULL,
  attempt integer NOT NULL,
  execution_epoch bigint NOT NULL,
  call_id text NOT NULL,
  execution_plan_hash text NOT NULL,
  environment_id text NOT NULL,
  authority_snapshot_id text NOT NULL,
  raw_result_ref text NOT NULL,
  effective_result_ref text NOT NULL,
  interceptor_chain jsonb NOT NULL DEFAULT '[]'::jsonb,
  mutation_provenance_ref text,
  state text NOT NULL CHECK (state IN ('RAW_CAPTURED','INTERCEPTING','COMMITTED','PUBLISHED','ABORTED')),
  committed_at timestamptz,
  PRIMARY KEY (tenant_id, invocation_id, attempt, execution_epoch)
);

CREATE TABLE IF NOT EXISTS elmos_step_execution_plans (
  tenant_id text NOT NULL,
  plan_id text NOT NULL,
  step_id text NOT NULL,
  plan_hash text NOT NULL,
  model_snapshot jsonb NOT NULL,
  tool_plan jsonb NOT NULL,
  environment_snapshot_id text NOT NULL,
  authority_snapshot_id text NOT NULL,
  state text NOT NULL CHECK (state IN ('CANDIDATE','FINALIZED','ACTIVE','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, plan_id),
  UNIQUE (tenant_id, plan_hash)
);

CREATE TABLE IF NOT EXISTS elmos_capability_leases (
  tenant_id text NOT NULL,
  lease_id text NOT NULL,
  invocation_id text NOT NULL,
  environment_id text NOT NULL,
  authority_snapshot_id text NOT NULL,
  execution_epoch bigint NOT NULL,
  capability_set jsonb NOT NULL,
  state text NOT NULL CHECK (state IN ('ACTIVE','REVOKED','EXPIRED')),
  issued_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  PRIMARY KEY (tenant_id, lease_id)
);

CREATE TABLE IF NOT EXISTS elmos_executor_generations (
  tenant_id text NOT NULL,
  environment_id text NOT NULL,
  executor_identity text NOT NULL,
  executor_generation bigint NOT NULL,
  connection_epoch bigint NOT NULL,
  state text NOT NULL CHECK (state IN ('CONNECTING','ACTIVE','RETIRED','FAILED')),
  live_probe_evidence_ref text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, environment_id, executor_generation, connection_epoch)
);

CREATE UNIQUE INDEX IF NOT EXISTS elmos_one_active_executor_generation
ON elmos_executor_generations(tenant_id, environment_id)
WHERE state = 'ACTIVE';

CREATE TABLE IF NOT EXISTS elmos_workspace_leases (
  tenant_id text NOT NULL,
  workspace_id text NOT NULL,
  owner_execution_id text NOT NULL,
  generation bigint NOT NULL,
  repository_id text NOT NULL,
  base_revision text NOT NULL,
  write_scopes jsonb NOT NULL DEFAULT '[]'::jsonb,
  state text NOT NULL CHECK (state IN ('ACTIVE','HANDOFF_PENDING','RETIRED','TAKEOVER_PENDING')),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, workspace_id, generation)
);

CREATE UNIQUE INDEX IF NOT EXISTS elmos_one_active_workspace_owner
ON elmos_workspace_leases(tenant_id, workspace_id)
WHERE state = 'ACTIVE';

CREATE TABLE IF NOT EXISTS elmos_durable_event_registrations (
  tenant_id text NOT NULL,
  event_type text NOT NULL,
  owner text NOT NULL,
  schema_version integer NOT NULL,
  semantics text NOT NULL CHECK (semantics IN ('OPTIONAL_OBSERVATION','REQUIRED_STATE')),
  validator_ref text NOT NULL,
  upgrader_ref text NOT NULL,
  projections jsonb NOT NULL,
  registration_hash text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  PRIMARY KEY (tenant_id, event_type, schema_version)
);

ALTER TABLE elmos_tool_result_commits ENABLE ROW LEVEL SECURITY;
ALTER TABLE elmos_step_execution_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE elmos_capability_leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE elmos_executor_generations ENABLE ROW LEVEL SECURITY;
ALTER TABLE elmos_workspace_leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE elmos_durable_event_registrations ENABLE ROW LEVEL SECURITY;

COMMIT;
