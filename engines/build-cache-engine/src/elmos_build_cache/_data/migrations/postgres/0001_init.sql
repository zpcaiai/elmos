-- ELMOS cache/staging production metadata schema (PostgreSQL 16+ reference)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE tenants (
  tenant_id text PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE projects (
  project_id text PRIMARY KEY,
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE TABLE snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  project_id text NOT NULL REFERENCES projects(project_id),
  root_digest text NOT NULL,
  manifest_digest text NOT NULL,
  policy_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, root_digest, policy_version)
);

CREATE TABLE runs (
  run_id text PRIMARY KEY,
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  project_id text NOT NULL REFERENCES projects(project_id),
  snapshot_id uuid NOT NULL REFERENCES snapshots(snapshot_id),
  pipeline_version text NOT NULL,
  source_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
  target_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL CHECK (status IN (
    'PENDING','RUNNING','PAUSED','SUCCEEDED','FAILED','CANCELED','RECOVERING','STALE'
  )),
  version bigint NOT NULL DEFAULT 0,
  published_tree_digest text,
  evidence_bundle_digest text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE run_nodes (
  run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  node_id text NOT NULL,
  attempt integer NOT NULL DEFAULT 1 CHECK (attempt > 0),
  stage_id text NOT NULL,
  stage_version text NOT NULL,
  action_key text,
  status text NOT NULL CHECK (status IN (
    'PENDING','READY','RUNNING','CHECKPOINTED','SUCCEEDED',
    'FAILED_RETRYABLE','FAILED_FINAL','PAUSED','CANCELED','RECOVERING','STALE'
  )),
  lease_id text,
  lease_epoch bigint NOT NULL DEFAULT 0,
  lease_expires_at timestamptz,
  version bigint NOT NULL DEFAULT 0,
  started_at timestamptz,
  finished_at timestamptz,
  error_code text,
  error_details jsonb,
  PRIMARY KEY (run_id, node_id, attempt)
);

CREATE TABLE artifacts (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  digest text NOT NULL,
  size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
  media_type text NOT NULL,
  artifact_kind text NOT NULL,
  storage_state text NOT NULL CHECK (storage_state IN (
    'LOCAL','REMOTE_PENDING','REMOTE','QUARANTINED','DELETING','DELETED'
  )),
  validation_level text NOT NULL CHECK (validation_level IN (
    'UNVERIFIED','COMPILE_VERIFIED','TEST_VERIFIED',
    'BEHAVIOR_VERIFIED','PRODUCTION_CERTIFIED','QUARANTINED'
  )),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_accessed_at timestamptz,
  PRIMARY KEY (tenant_id, digest)
);

CREATE TABLE artifact_refs (
  tenant_id text NOT NULL,
  source_kind text NOT NULL,
  source_id text NOT NULL,
  target_digest text NOT NULL,
  ref_kind text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, source_kind, source_id, target_digest, ref_kind),
  FOREIGN KEY (tenant_id, target_digest) REFERENCES artifacts(tenant_id, digest)
);

CREATE TABLE action_cache_entries (
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  trust_namespace text NOT NULL,
  action_key text NOT NULL,
  result_manifest_digest text NOT NULL,
  validation_level text NOT NULL CHECK (validation_level IN (
    'UNVERIFIED','COMPILE_VERIFIED','TEST_VERIFIED',
    'BEHAVIOR_VERIFIED','PRODUCTION_CERTIFIED','QUARANTINED'
  )),
  producer_identity text NOT NULL,
  provenance_digest text NOT NULL,
  status text NOT NULL CHECK (status IN ('ACTIVE','QUARANTINED','REVOKED','EXPIRED')),
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_accessed_at timestamptz,
  hit_count bigint NOT NULL DEFAULT 0,
  saved_cpu_ms bigint NOT NULL DEFAULT 0,
  saved_model_tokens bigint NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, trust_namespace, action_key)
);

CREATE TABLE staged_files (
  staged_file_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  project_id text NOT NULL REFERENCES projects(project_id),
  run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  node_id text NOT NULL,
  attempt integer NOT NULL CHECK (attempt > 0),
  logical_path text NOT NULL,
  file_class text NOT NULL CHECK (file_class IN (
    'SCRATCH','STAGED_INTERMEDIATE','SEALED_ARTIFACT','PUBLISH_CANDIDATE','QUARANTINED'
  )),
  status text NOT NULL CHECK (status IN (
    'RESERVED','WRITING','SEALED','CAS_PROMOTED','TREE_INCLUDED',
    'PUBLISHED','ABORTED','QUARANTINED'
  )),
  internal_temp_path text,
  internal_sealed_path text,
  lease_id text,
  lease_epoch bigint NOT NULL DEFAULT 0,
  version bigint NOT NULL DEFAULT 0,
  expected_size bigint CHECK (expected_size IS NULL OR expected_size >= 0),
  actual_size bigint CHECK (actual_size IS NULL OR actual_size >= 0),
  digest text,
  media_type text,
  artifact_kind text,
  action_key text,
  artifact_digest text,
  source_map_digest text,
  validation_level text NOT NULL DEFAULT 'UNVERIFIED',
  secret_scan_status text NOT NULL DEFAULT 'NOT_RUN'
    CHECK (secret_scan_status IN ('NOT_RUN','PASS','FAIL','ERROR')),
  quarantine_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  sealed_at timestamptz,
  promoted_at timestamptz,
  tree_included_at timestamptz,
  published_at timestamptz,
  UNIQUE (run_id, node_id, attempt, logical_path)
);

CREATE TABLE checkpoints (
  checkpoint_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL REFERENCES tenants(tenant_id),
  project_id text NOT NULL REFERENCES projects(project_id),
  run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  node_id text NOT NULL,
  attempt integer NOT NULL,
  sequence integer NOT NULL,
  lease_epoch bigint NOT NULL,
  manifest_digest text NOT NULL,
  journal_sequence bigint NOT NULL,
  status text NOT NULL CHECK (status IN ('ACTIVE','SUPERSEDED','INVALID','QUARANTINED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, node_id, attempt, sequence)
);

CREATE TABLE side_effect_receipts (
  tenant_id text NOT NULL,
  run_id text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  node_id text NOT NULL,
  idempotency_key text NOT NULL,
  effect_type text NOT NULL,
  status text NOT NULL CHECK (status IN ('PENDING','COMMITTED','COMPENSATED','FAILED')),
  external_reference text,
  payload_digest text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, idempotency_key)
);

CREATE TABLE cache_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id text NOT NULL,
  project_id text,
  run_id text,
  node_id text,
  sequence bigint,
  event_type text NOT NULL,
  actor text NOT NULL,
  lease_epoch bigint,
  payload jsonb NOT NULL,
  payload_digest text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, sequence)
);

CREATE TABLE pins (
  tenant_id text NOT NULL,
  pin_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_kind text NOT NULL,
  source_id text NOT NULL,
  reason text NOT NULL,
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE outbox_events (
  outbox_id bigserial PRIMARY KEY,
  topic text NOT NULL,
  event_key text NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz
);

CREATE INDEX idx_runs_project_status
  ON runs (tenant_id, project_id, status, updated_at);

CREATE INDEX idx_nodes_schedulable
  ON run_nodes (status, lease_expires_at)
  WHERE status IN ('READY','RUNNING','RECOVERING');

CREATE INDEX idx_artifacts_gc
  ON artifacts (tenant_id, storage_state, last_accessed_at, size_bytes);

CREATE INDEX idx_action_cache_access
  ON action_cache_entries (tenant_id, trust_namespace, status, last_accessed_at);

CREATE INDEX idx_staged_recovery
  ON staged_files (run_id, status, lease_epoch);

CREATE INDEX idx_events_run_sequence
  ON cache_events (run_id, sequence);

CREATE INDEX idx_outbox_pending
  ON outbox_events (outbox_id)
  WHERE published_at IS NULL;
