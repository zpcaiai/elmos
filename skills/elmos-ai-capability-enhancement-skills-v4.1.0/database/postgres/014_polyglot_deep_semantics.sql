BEGIN;

-- polyglot_deep_semantics — production schema contract; exact indexes/partitions must be benchmarked before release.

CREATE TABLE IF NOT EXISTS polyglot_semantic_profiles (
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
ALTER TABLE polyglot_semantic_profiles ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_polyglot_semantic_profiles_tenant_revision ON polyglot_semantic_profiles(tenant_id, revision_set_id, created_at);

CREATE TABLE IF NOT EXISTS polyglot_route_overlays (
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
ALTER TABLE polyglot_route_overlays ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_polyglot_route_overlays_tenant_revision ON polyglot_route_overlays(tenant_id, revision_set_id, created_at);

CREATE TABLE IF NOT EXISTS polyglot_conformance_runs (
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
ALTER TABLE polyglot_conformance_runs ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_polyglot_conformance_runs_tenant_revision ON polyglot_conformance_runs(tenant_id, revision_set_id, created_at);

COMMIT;
