BEGIN;

-- platform_productization — production schema contract; exact indexes/partitions must be benchmarked before release.

CREATE TABLE IF NOT EXISTS platform_templates (
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
ALTER TABLE platform_templates ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_platform_templates_tenant_revision ON platform_templates(tenant_id, revision_set_id, created_at);

CREATE TABLE IF NOT EXISTS gitops_promotions (
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
ALTER TABLE gitops_promotions ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_gitops_promotions_tenant_revision ON gitops_promotions(tenant_id, revision_set_id, created_at);

CREATE TABLE IF NOT EXISTS multi_region_drills (
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
ALTER TABLE multi_region_drills ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_multi_region_drills_tenant_revision ON multi_region_drills(tenant_id, revision_set_id, created_at);

COMMIT;
