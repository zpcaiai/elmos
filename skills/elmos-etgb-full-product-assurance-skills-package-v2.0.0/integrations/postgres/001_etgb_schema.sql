BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS etgb;

CREATE OR REPLACE FUNCTION etgb.set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS etgb.benchmark_suite (
  suite_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  suite_key text NOT NULL,
  version text NOT NULL,
  capability_model_uri text NOT NULL,
  manifest_digest text NOT NULL CHECK (manifest_digest ~ '^sha256:[0-9a-f]{64}$'),
  status text NOT NULL CHECK (status IN ('DRAFT','ACTIVE','RETIRED')),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, suite_key, version)
);

CREATE TABLE IF NOT EXISTS etgb.benchmark_case (
  case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  case_key text NOT NULL,
  business_line text NOT NULL CHECK (business_line IN ('spring-modernization','cross-language','project-generation','sql-conversion','cross-cutting','identity-access-tenant','platform-control-plane','repository-ingestion-context','multimodal-document-processing','ai-runtime-model-routing','agent-protocol-tooling','rag-memory-knowledge','project-intelligence','online-ide-debug','artifact-document-diagram','collaboration-integrations','billing-entitlements','payment-finance','api-sdk-webhook','storage-search-cache','deployment-operations','security-privacy-compliance','ui-accessibility-localization','analytics-admin-support','notifications-scheduler','ai-solution-factory','data-bigdata-solution','commercial-delivery-certification','product-journey','standards-assurance')),
  family text NOT NULL,
  priority text NOT NULL CHECK (priority IN ('P0','P1','P2')),
  level text NOT NULL CHECK (level IN ('L0','L1','L2','L3','L4')),
  capability_id text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, case_key)
);

CREATE TABLE IF NOT EXISTS etgb.benchmark_case_version (
  case_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  case_id uuid NOT NULL REFERENCES etgb.benchmark_case(case_id),
  version integer NOT NULL CHECK (version > 0),
  case_document jsonb NOT NULL,
  case_digest text NOT NULL CHECK (case_digest ~ '^sha256:[0-9a-f]{64}$'),
  oracle_version text NOT NULL,
  normalization_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('DRAFT','ACTIVE','RETIRED','QUARANTINED')),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (case_id, version),
  UNIQUE (tenant_id, case_digest)
);

CREATE TABLE IF NOT EXISTS etgb.corpus_snapshot (
  corpus_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  corpus_key text NOT NULL,
  repository_url text,
  commit_sha text CHECK (commit_sha IS NULL OR commit_sha ~ '^[0-9a-f]{40}$'),
  artifact_digest text CHECK (artifact_digest IS NULL OR artifact_digest ~ '^sha256:[0-9a-f]{64}$'),
  license_id text,
  license_review text NOT NULL CHECK (license_review IN ('REQUIRED','APPROVED','BLOCKED','METADATA_ONLY')),
  security_review text NOT NULL CHECK (security_review IN ('REQUIRED','APPROVED','BLOCKED')),
  temporal_cutoff timestamptz,
  hidden_partition text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, corpus_key, commit_sha, artifact_digest)
);

CREATE TABLE IF NOT EXISTS etgb.release_candidate (
  release_candidate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  candidate_key text NOT NULL,
  source_commit text NOT NULL CHECK (source_commit ~ '^[0-9a-f]{40}$'),
  candidate_digest text NOT NULL CHECK (candidate_digest ~ '^sha256:[0-9a-f]{64}$'),
  model_spec jsonb NOT NULL,
  prompt_digest text NOT NULL,
  skill_manifest_digest text NOT NULL,
  rule_bundle_digest text NOT NULL,
  toolchain_image_digest text NOT NULL,
  oracle_version text NOT NULL,
  normalization_version text NOT NULL,
  frozen_at timestamptz NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, candidate_digest)
);

CREATE TABLE IF NOT EXISTS etgb.run_plan (
  run_plan_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  release_candidate_id uuid NOT NULL REFERENCES etgb.release_candidate(release_candidate_id),
  suite_id uuid NOT NULL REFERENCES etgb.benchmark_suite(suite_id),
  plan_digest text NOT NULL CHECK (plan_digest ~ '^sha256:[0-9a-f]{64}$'),
  selection_policy text NOT NULL,
  profile text NOT NULL CHECK (profile IN ('smoke','pr','nightly','weekly','release','golden','exhaustive')),
  case_count integer NOT NULL CHECK (case_count >= 0),
  shard_count integer NOT NULL CHECK (shard_count > 0),
  case_ids jsonb NOT NULL,
  shards jsonb NOT NULL,
  budget jsonb NOT NULL,
  immutable_at timestamptz NOT NULL DEFAULT now(),
  created_by text NOT NULL,
  UNIQUE (tenant_id, plan_digest)
);

CREATE TABLE IF NOT EXISTS etgb.environment_authority (
  environment_authority_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  authority_id text NOT NULL,
  environment_id text NOT NULL,
  owner_type text NOT NULL CHECK (owner_type IN ('environment','attachment')),
  owner_id text NOT NULL,
  role text NOT NULL,
  authority_document jsonb NOT NULL,
  authority_digest text NOT NULL CHECK (authority_digest ~ '^sha256:[0-9a-f]{64}$'),
  fencing_token bigint NOT NULL CHECK (fencing_token > 0),
  expires_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, authority_id, fencing_token)
);

CREATE TABLE IF NOT EXISTS etgb.benchmark_run (
  run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid,
  task_id uuid,
  account_id uuid,
  release_candidate_id uuid NOT NULL REFERENCES etgb.release_candidate(release_candidate_id),
  run_plan_id uuid NOT NULL REFERENCES etgb.run_plan(run_plan_id),
  environment_authority_id uuid REFERENCES etgb.environment_authority(environment_authority_id),
  status text NOT NULL CHECK (status IN (
    'PLANNED','PREPARING','BASELINING','TRANSFORMING','GENERATING','BUILDING','VALIDATING','SCORING','PUBLISHING',
    'PAUSING','PAUSED','RESUMING','CANCELLING','COMPENSATING','COMPLETED','CANCELLED','FAILED','BLOCKED'
  )),
  revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0),
  owner_id text,
  fencing_token bigint NOT NULL DEFAULT 1 CHECK (fencing_token > 0),
  lease_expires_at timestamptz,
  resume_state text,
  checkpoint_digest text,
  claimed_success boolean NOT NULL DEFAULT false,
  cancel_requested_at timestamptz,
  pause_requested_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  wall_clock_ms bigint NOT NULL DEFAULT 0 CHECK (wall_clock_ms >= 0),
  input_tokens bigint NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
  output_tokens bigint NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
  credit_usd numeric(20,8) NOT NULL DEFAULT 0 CHECK (credit_usd >= 0),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS etgb.run_shard (
  run_shard_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL REFERENCES etgb.benchmark_run(run_id) ON DELETE CASCADE,
  shard_index integer NOT NULL CHECK (shard_index >= 0),
  shard_digest text NOT NULL,
  case_ids jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('PENDING','LEASED','RUNNING','PAUSED','COMPLETED','FAILED','CANCELLED')),
  owner_id text,
  fencing_token bigint NOT NULL DEFAULT 1,
  lease_expires_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  UNIQUE (run_id, shard_index)
);

CREATE TABLE IF NOT EXISTS etgb.benchmark_case_run (
  case_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL REFERENCES etgb.benchmark_run(run_id) ON DELETE CASCADE,
  run_shard_id uuid REFERENCES etgb.run_shard(run_shard_id),
  case_version_id uuid NOT NULL REFERENCES etgb.benchmark_case_version(case_version_id),
  seed bigint,
  attempt integer NOT NULL DEFAULT 1 CHECK (attempt > 0),
  status text NOT NULL CHECK (status IN ('PLANNED','RUNNING','PASSED','FAILED','ERROR','SKIPPED','UNAVAILABLE','CANCELLED','QUARANTINED')),
  failure_class text,
  silent_semantic_error boolean NOT NULL DEFAULT false,
  manual_intervention_required boolean NOT NULL DEFAULT false,
  source_baseline_digest text,
  target_artifact_digest text,
  environment_digest text,
  started_at timestamptz,
  finished_at timestamptz,
  duration_ms bigint NOT NULL DEFAULT 0 CHECK (duration_ms >= 0),
  input_tokens bigint NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
  output_tokens bigint NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
  credit_usd numeric(20,8) NOT NULL DEFAULT 0 CHECK (credit_usd >= 0),
  result_document jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, case_version_id, seed, attempt)
);

CREATE TABLE IF NOT EXISTS etgb.run_transition (
  transition_id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL REFERENCES etgb.benchmark_run(run_id) ON DELETE CASCADE,
  revision bigint NOT NULL,
  from_state text,
  to_state text NOT NULL,
  owner_id text NOT NULL,
  fencing_token bigint NOT NULL,
  reason text NOT NULL,
  checkpoint_digest text,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, revision)
);

CREATE TABLE IF NOT EXISTS etgb.run_checkpoint (
  checkpoint_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL REFERENCES etgb.benchmark_run(run_id) ON DELETE CASCADE,
  case_run_id uuid REFERENCES etgb.benchmark_case_run(case_run_id) ON DELETE CASCADE,
  phase text NOT NULL,
  revision bigint NOT NULL CHECK (revision >= 0),
  candidate_digest text NOT NULL,
  plan_digest text NOT NULL,
  environment_digest text NOT NULL,
  workspace_digest text,
  fencing_token bigint NOT NULL,
  previous_checkpoint_digest text,
  checkpoint_digest text NOT NULL CHECK (checkpoint_digest ~ '^sha256:[0-9a-f]{64}$'),
  artifact_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  side_effect_receipts jsonb NOT NULL DEFAULT '[]'::jsonb,
  resume_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, revision),
  UNIQUE (tenant_id, checkpoint_digest)
);

CREATE TABLE IF NOT EXISTS etgb.oracle_result (
  oracle_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  case_run_id uuid NOT NULL REFERENCES etgb.benchmark_case_run(case_run_id) ON DELETE CASCADE,
  oracle_type text NOT NULL,
  oracle_version text NOT NULL,
  normalization_version text NOT NULL,
  critical boolean NOT NULL,
  passed boolean,
  status text NOT NULL CHECK (status IN ('PASS','FAIL','ERROR','BLOCKED','QUARANTINED')),
  first_difference jsonb,
  tolerance jsonb,
  classification text,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS etgb.evidence_artifact (
  evidence_artifact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL REFERENCES etgb.benchmark_run(run_id) ON DELETE CASCADE,
  case_run_id uuid REFERENCES etgb.benchmark_case_run(case_run_id) ON DELETE CASCADE,
  logical_name text NOT NULL,
  media_type text NOT NULL,
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
  object_uri text NOT NULL,
  producer_environment text NOT NULL,
  redaction_status text NOT NULL CHECK (redaction_status IN ('NOT_CHECKED','CHECKED_CLEAN','REDACTED','QUARANTINED')),
  encryption_key_ref text,
  access_policy text NOT NULL,
  retention_class text NOT NULL,
  expires_at timestamptz,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, run_id, logical_name),
  UNIQUE (tenant_id, sha256, object_uri)
);

CREATE TABLE IF NOT EXISTS etgb.evidence_seal (
  evidence_seal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL REFERENCES etgb.benchmark_run(run_id) ON DELETE CASCADE,
  manifest_digest text NOT NULL CHECK (manifest_digest ~ '^sha256:[0-9a-f]{64}$'),
  signature_algorithm text NOT NULL,
  signature text,
  signer_key_ref text,
  event_chain_head text,
  sealed_at timestamptz NOT NULL DEFAULT now(),
  verified_at timestamptz,
  verification_status text NOT NULL CHECK (verification_status IN ('UNVERIFIED','VALID','INVALID','REVOKED')),
  UNIQUE (run_id)
);

CREATE TABLE IF NOT EXISTS etgb.budget_reservation (
  budget_reservation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL REFERENCES etgb.benchmark_run(run_id) ON DELETE CASCADE,
  state text NOT NULL CHECK (state IN ('RESERVED','ACTIVE','EXHAUSTED','CLOSED','CANCELLED')),
  max_input_tokens bigint NOT NULL CHECK (max_input_tokens >= 0),
  max_output_tokens bigint NOT NULL CHECK (max_output_tokens >= 0),
  max_credit_usd numeric(20,8) NOT NULL CHECK (max_credit_usd >= 0),
  max_wall_clock_ms bigint NOT NULL CHECK (max_wall_clock_ms >= 0),
  used_input_tokens bigint NOT NULL DEFAULT 0 CHECK (used_input_tokens >= 0),
  used_output_tokens bigint NOT NULL DEFAULT 0 CHECK (used_output_tokens >= 0),
  used_credit_usd numeric(20,8) NOT NULL DEFAULT 0 CHECK (used_credit_usd >= 0),
  used_wall_clock_ms bigint NOT NULL DEFAULT 0 CHECK (used_wall_clock_ms >= 0),
  reserved_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id)
);

CREATE TABLE IF NOT EXISTS etgb.usage_ledger (
  usage_ledger_id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL REFERENCES etgb.benchmark_run(run_id) ON DELETE CASCADE,
  case_run_id uuid REFERENCES etgb.benchmark_case_run(case_run_id) ON DELETE CASCADE,
  idempotency_key text NOT NULL,
  phase text NOT NULL,
  input_tokens bigint NOT NULL DEFAULT 0,
  output_tokens bigint NOT NULL DEFAULT 0,
  credit_usd numeric(20,8) NOT NULL DEFAULT 0,
  wall_clock_ms bigint NOT NULL DEFAULT 0,
  provider_usage jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS etgb.release_gate_result (
  release_gate_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL REFERENCES etgb.benchmark_run(run_id) ON DELETE CASCADE,
  gate_id text NOT NULL,
  metric text NOT NULL,
  actual jsonb,
  operator text NOT NULL,
  threshold jsonb NOT NULL,
  state text NOT NULL CHECK (state IN ('PASS','FAIL','BLOCKED','WAIVED','ERROR')),
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  evaluated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, gate_id)
);

CREATE TABLE IF NOT EXISTS etgb.waiver (
  waiver_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL REFERENCES etgb.benchmark_run(run_id) ON DELETE CASCADE,
  gate_ids text[] NOT NULL,
  reason text NOT NULL,
  customer_impact text NOT NULL,
  compensating_control text NOT NULL,
  approved_by text NOT NULL,
  approved_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  regression_ref text,
  CHECK (expires_at > approved_at)
);

CREATE TABLE IF NOT EXISTS etgb.capability_coverage (
  capability_coverage_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  suite_id uuid NOT NULL REFERENCES etgb.benchmark_suite(suite_id) ON DELETE CASCADE,
  capability_id text NOT NULL,
  required_cells integer NOT NULL CHECK (required_cells >= 0),
  materialized_cells integer NOT NULL CHECK (materialized_cells >= 0),
  executable_cells integer NOT NULL CHECK (executable_cells >= 0),
  passed_cells integer NOT NULL CHECK (passed_cells >= 0),
  coverage_document jsonb NOT NULL,
  measured_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (suite_id, capability_id, measured_at)
);

CREATE TABLE IF NOT EXISTS etgb.failure_cluster (
  failure_cluster_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  signature text NOT NULL,
  failure_class text NOT NULL,
  title text,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  occurrence_count bigint NOT NULL DEFAULT 1,
  status text NOT NULL CHECK (status IN ('OPEN','INVESTIGATING','FIXED','ORACLE_DEFECT','ACCEPTED')),
  root_cause jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (tenant_id, signature)
);

CREATE TABLE IF NOT EXISTS etgb.regression_link (
  regression_link_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  failure_cluster_id uuid NOT NULL REFERENCES etgb.failure_cluster(failure_cluster_id) ON DELETE CASCADE,
  case_id uuid REFERENCES etgb.benchmark_case(case_id),
  incident_ref text,
  fixed_candidate_digest text,
  hidden_variant_ref text,
  mutant_ref text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS etgb.idempotency_record (
  idempotency_record_id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL,
  scope text NOT NULL,
  idempotency_key text NOT NULL,
  request_digest text NOT NULL,
  response_document jsonb,
  status text NOT NULL CHECK (status IN ('STARTED','COMPLETED','FAILED','COMPENSATED')),
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, scope, idempotency_key)
);

CREATE TABLE IF NOT EXISTS etgb.outbox_event (
  outbox_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  aggregate_type text NOT NULL,
  aggregate_id uuid NOT NULL,
  event_type text NOT NULL,
  event_version text NOT NULL,
  idempotency_key text NOT NULL,
  payload jsonb NOT NULL,
  headers jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz,
  publish_attempts integer NOT NULL DEFAULT 0,
  last_error text,
  UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_case_capability ON etgb.benchmark_case (tenant_id, capability_id, active);
CREATE INDEX IF NOT EXISTS idx_run_status ON etgb.benchmark_run (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_account_active ON etgb.benchmark_run (tenant_id, account_id, status) WHERE status NOT IN ('COMPLETED','CANCELLED','FAILED','BLOCKED');
CREATE INDEX IF NOT EXISTS idx_case_run_status ON etgb.benchmark_case_run (tenant_id, run_id, status);
CREATE INDEX IF NOT EXISTS idx_case_run_failure ON etgb.benchmark_case_run (tenant_id, failure_class) WHERE status IN ('FAILED','ERROR');
CREATE INDEX IF NOT EXISTS idx_oracle_failed ON etgb.oracle_result (tenant_id, oracle_type, critical) WHERE status IN ('FAIL','ERROR','BLOCKED');
CREATE INDEX IF NOT EXISTS idx_evidence_run ON etgb.evidence_artifact (tenant_id, run_id, case_run_id);
CREATE INDEX IF NOT EXISTS idx_checkpoint_latest ON etgb.run_checkpoint (run_id, revision DESC);
CREATE INDEX IF NOT EXISTS idx_outbox_unpublished ON etgb.outbox_event (created_at) WHERE published_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_usage_run ON etgb.usage_ledger (tenant_id, run_id, occurred_at);

DROP TRIGGER IF EXISTS trg_suite_updated_at ON etgb.benchmark_suite;
CREATE TRIGGER trg_suite_updated_at BEFORE UPDATE ON etgb.benchmark_suite FOR EACH ROW EXECUTE FUNCTION etgb.set_updated_at();
DROP TRIGGER IF EXISTS trg_case_updated_at ON etgb.benchmark_case;
CREATE TRIGGER trg_case_updated_at BEFORE UPDATE ON etgb.benchmark_case FOR EACH ROW EXECUTE FUNCTION etgb.set_updated_at();
DROP TRIGGER IF EXISTS trg_run_updated_at ON etgb.benchmark_run;
CREATE TRIGGER trg_run_updated_at BEFORE UPDATE ON etgb.benchmark_run FOR EACH ROW EXECUTE FUNCTION etgb.set_updated_at();
DROP TRIGGER IF EXISTS trg_budget_updated_at ON etgb.budget_reservation;
CREATE TRIGGER trg_budget_updated_at BEFORE UPDATE ON etgb.budget_reservation FOR EACH ROW EXECUTE FUNCTION etgb.set_updated_at();
DROP TRIGGER IF EXISTS trg_idempotency_updated_at ON etgb.idempotency_record;
CREATE TRIGGER trg_idempotency_updated_at BEFORE UPDATE ON etgb.idempotency_record FOR EACH ROW EXECUTE FUNCTION etgb.set_updated_at();

COMMIT;
