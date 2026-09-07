BEGIN;

-- model_serving_edge — production schema contract; exact indexes/partitions must be benchmarked before release.

CREATE TABLE IF NOT EXISTS model_serving_profiles (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  goal_id uuid NOT NULL,
  revision_set_id uuid NOT NULL,
  execution_epoch bigint NOT NULL DEFAULT 0,
  lease_generation bigint,
  fencing_token text,
  idempotency_key text,
  status text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  content_hash text NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, idempotency_key)
);
ALTER TABLE model_serving_profiles ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_model_serving_profiles_tenant_revision ON model_serving_profiles(tenant_id, revision_set_id, created_at);

CREATE TABLE IF NOT EXISTS model_deployments (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  goal_id uuid NOT NULL,
  revision_set_id uuid NOT NULL,
  execution_epoch bigint NOT NULL DEFAULT 0,
  lease_generation bigint,
  fencing_token text,
  idempotency_key text,
  status text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  content_hash text NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, idempotency_key)
);
ALTER TABLE model_deployments ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_model_deployments_tenant_revision ON model_deployments(tenant_id, revision_set_id, created_at);

CREATE TABLE IF NOT EXISTS model_canary_runs (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  goal_id uuid NOT NULL,
  revision_set_id uuid NOT NULL,
  execution_epoch bigint NOT NULL DEFAULT 0,
  lease_generation bigint,
  fencing_token text,
  idempotency_key text,
  status text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  content_hash text NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, idempotency_key)
);
ALTER TABLE model_canary_runs ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_model_canary_runs_tenant_revision ON model_canary_runs(tenant_id, revision_set_id, created_at);

COMMIT;
