BEGIN;

-- formal_zero_trust — production schema contract; exact indexes/partitions must be benchmarked before release.

CREATE TABLE IF NOT EXISTS formal_proof_runs (
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
ALTER TABLE formal_proof_runs ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_formal_proof_runs_tenant_revision ON formal_proof_runs(tenant_id, revision_set_id, created_at);

CREATE TABLE IF NOT EXISTS workload_identities (
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
ALTER TABLE workload_identities ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_workload_identities_tenant_revision ON workload_identities(tenant_id, revision_set_id, created_at);

CREATE TABLE IF NOT EXISTS attestation_results (
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
ALTER TABLE attestation_results ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_attestation_results_tenant_revision ON attestation_results(tenant_id, revision_set_id, created_at);

COMMIT;
