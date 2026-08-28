BEGIN;

-- event_contracts — production schema contract; exact indexes/partitions must be benchmarked before release.

CREATE TABLE IF NOT EXISTS event_contracts (
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
ALTER TABLE event_contracts ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_event_contracts_tenant_revision ON event_contracts(tenant_id, revision_set_id, created_at);

CREATE TABLE IF NOT EXISTS event_consumers (
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
ALTER TABLE event_consumers ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_event_consumers_tenant_revision ON event_consumers(tenant_id, revision_set_id, created_at);

CREATE TABLE IF NOT EXISTS event_replay_runs (
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
ALTER TABLE event_replay_runs ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_event_replay_runs_tenant_revision ON event_replay_runs(tenant_id, revision_set_id, created_at);

COMMIT;
