-- ELMOS cache parity v1.2.0 additive migration sketch.
-- Adapt names/types to the production migration framework and tenant RLS policy.

CREATE TABLE IF NOT EXISTS prompt_prefix_manifest (
  manifest_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  provider text NOT NULL,
  model_id text NOT NULL,
  effort_profile text NOT NULL,
  compatibility_group text NOT NULL,
  stable_prefix_digest text NOT NULL,
  tool_schema_digest text NOT NULL,
  manifest jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, provider, model_id, effort_profile, compatibility_group, stable_prefix_digest)
);

CREATE TABLE IF NOT EXISTS context_ledger_event (
  stream_id text NOT NULL,
  sequence_no bigint NOT NULL,
  event_id text NOT NULL UNIQUE,
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  branch_lineage text NOT NULL,
  event_type text NOT NULL,
  repository_snapshot_digest text,
  subject_ref text,
  payload_digest text NOT NULL,
  previous_event_digest text,
  event_digest text NOT NULL,
  event_body jsonb NOT NULL,
  occurred_at timestamptz NOT NULL,
  PRIMARY KEY (stream_id, sequence_no),
  UNIQUE (stream_id, event_digest)
);

CREATE TABLE IF NOT EXISTS environment_snapshot (
  snapshot_key text PRIMARY KEY,
  snapshot_id text NOT NULL UNIQUE,
  trust_namespace text NOT NULL,
  tenant_id text NOT NULL,
  project_id text,
  status text NOT NULL,
  manifest_digest text NOT NULL,
  manifest jsonb NOT NULL,
  size_bytes bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz,
  revoked_at timestamptz
);

CREATE TABLE IF NOT EXISTS cache_outcome_event (
  event_id text PRIMARY KEY,
  request_id text NOT NULL,
  tenant_id text NOT NULL,
  project_id text,
  layer text NOT NULL,
  outcome text NOT NULL,
  reason_code text NOT NULL,
  eligible boolean NOT NULL,
  identity_digest text,
  first_difference jsonb,
  value jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cache_outcome_request ON cache_outcome_event(request_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_cache_outcome_reason ON cache_outcome_event(layer, outcome, reason_code, occurred_at);

CREATE TABLE IF NOT EXISTS cache_affinity_decision (
  decision_id text PRIMARY KEY,
  request_id text NOT NULL,
  affinity_key text NOT NULL,
  selected_target text,
  decision jsonb NOT NULL,
  decided_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS cache_parity_report (
  report_id text PRIMARY KEY,
  subject_digest text NOT NULL,
  mandatory_pass boolean NOT NULL,
  false_hits bigint NOT NULL,
  report jsonb NOT NULL,
  signature text,
  generated_at timestamptz NOT NULL,
  expires_at timestamptz
);

-- Apply production row-level security using tenant_id and service identities before enabling writes.
