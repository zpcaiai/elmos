-- Elmos Knowledge–Skill–Model Foundry core schema (PostgreSQL 16+)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE tenant (
  tenant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  region text NOT NULL,
  status text NOT NULL CHECK (status IN ('active','suspended','offboarding','deleted')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE project (
  project_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(tenant_id),
  name text NOT NULL,
  policy_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE TABLE repository_snapshot (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(tenant_id),
  project_id uuid NOT NULL REFERENCES project(project_id),
  repository_uri text NOT NULL,
  revision text NOT NULL,
  content_hash text NOT NULL,
  toolchain_image_digest text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, repository_uri, revision, content_hash)
);

CREATE TABLE knowledge_source (
  source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(tenant_id),
  source_type text NOT NULL,
  locator text NOT NULL,
  rights_class text NOT NULL,
  training_consent text NOT NULL DEFAULT 'deny',
  residency_region text NOT NULL,
  sync_state text NOT NULL,
  last_synced_at timestamptz,
  UNIQUE (tenant_id, locator)
);

CREATE TABLE knowledge_object (
  object_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(tenant_id),
  source_id uuid NOT NULL REFERENCES knowledge_source(source_id),
  object_type text NOT NULL,
  content_hash text NOT NULL,
  confidentiality text NOT NULL,
  valid_from timestamptz,
  valid_to timestamptz,
  payload_uri text NOT NULL,
  provenance jsonb NOT NULL,
  quality jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, content_hash)
);

CREATE TABLE semantic_entity (
  entity_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(tenant_id),
  snapshot_id uuid REFERENCES repository_snapshot(snapshot_id),
  entity_type text NOT NULL,
  canonical_name text NOT NULL,
  source_location jsonb,
  semantic_hash text NOT NULL,
  confidence numeric(5,4) NOT NULL DEFAULT 1.0
);

CREATE TABLE semantic_relation (
  relation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(tenant_id),
  from_entity_id uuid NOT NULL REFERENCES semantic_entity(entity_id),
  to_entity_id uuid NOT NULL REFERENCES semantic_entity(entity_id),
  relation_type text NOT NULL,
  evidence jsonb NOT NULL,
  confidence numeric(5,4) NOT NULL DEFAULT 1.0
);

CREATE TABLE skill (
  skill_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  skill_name text NOT NULL UNIQUE,
  pack text NOT NULL,
  owner text NOT NULL,
  risk_class text NOT NULL,
  status text NOT NULL CHECK (status IN ('draft','certified','deprecated','revoked'))
);

CREATE TABLE skill_version (
  skill_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  skill_id uuid NOT NULL REFERENCES skill(skill_id),
  version text NOT NULL,
  content_hash text NOT NULL,
  package_uri text NOT NULL,
  compatibility jsonb NOT NULL,
  evidence_contract jsonb NOT NULL,
  signature jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (skill_id, version)
);

CREATE TABLE skill_dependency (
  skill_version_id uuid NOT NULL REFERENCES skill_version(skill_version_id),
  dependency_type text NOT NULL,
  dependency_name text NOT NULL,
  version_constraint text,
  required boolean NOT NULL DEFAULT true,
  PRIMARY KEY (skill_version_id, dependency_type, dependency_name)
);

CREATE TABLE experience_episode (
  episode_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(tenant_id),
  project_id uuid REFERENCES project(project_id),
  snapshot_id uuid REFERENCES repository_snapshot(snapshot_id),
  release_id text NOT NULL,
  task_contract jsonb NOT NULL,
  outcome text NOT NULL,
  evidence_level text NOT NULL,
  training_eligibility text NOT NULL DEFAULT 'deny',
  content_hash text NOT NULL,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  wall_clock_ms bigint,
  cost jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (tenant_id, content_hash)
);

CREATE TABLE trajectory_step (
  step_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id uuid NOT NULL REFERENCES experience_episode(episode_id) ON DELETE CASCADE,
  sequence_no integer NOT NULL,
  step_type text NOT NULL,
  model_release text,
  skill_version_id uuid REFERENCES skill_version(skill_version_id),
  input_hash text,
  output_hash text,
  status text NOT NULL,
  timing jsonb,
  UNIQUE (episode_id, sequence_no)
);

CREATE TABLE tool_event (
  tool_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  step_id uuid NOT NULL REFERENCES trajectory_step(step_id) ON DELETE CASCADE,
  tool_name text NOT NULL,
  environment_id text NOT NULL,
  permission_decision jsonb NOT NULL,
  idempotency_key text,
  request_hash text NOT NULL,
  result_hash text,
  side_effects jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL
);

CREATE TABLE evidence_artifact (
  evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(tenant_id),
  episode_id uuid REFERENCES experience_episode(episode_id),
  subject_type text NOT NULL,
  subject_id text NOT NULL,
  evidence_type text NOT NULL,
  decision text NOT NULL,
  content_hash text NOT NULL,
  artifact_uri text NOT NULL,
  signature jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE dataset (
  dataset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  owner text NOT NULL,
  purpose text NOT NULL
);

CREATE TABLE dataset_version (
  dataset_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id uuid NOT NULL REFERENCES dataset(dataset_id),
  version text NOT NULL,
  tier text NOT NULL CHECK (tier IN ('bronze','silver','gold','quarantine')),
  content_hash text NOT NULL,
  lineage_uri text NOT NULL,
  rights_summary jsonb NOT NULL,
  quality_summary jsonb NOT NULL,
  signature jsonb,
  frozen_at timestamptz,
  UNIQUE (dataset_id, version)
);

CREATE TABLE dataset_item (
  dataset_version_id uuid NOT NULL REFERENCES dataset_version(dataset_version_id),
  item_id text NOT NULL,
  source_episode_id uuid REFERENCES experience_episode(episode_id),
  tenant_scope text NOT NULL,
  content_hash text NOT NULL,
  training_eligible boolean NOT NULL DEFAULT false,
  revocation_state text NOT NULL DEFAULT 'active',
  metadata jsonb NOT NULL,
  PRIMARY KEY (dataset_version_id, item_id)
);

CREATE TABLE training_run (
  training_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_name text NOT NULL,
  code_revision text NOT NULL,
  container_digest text NOT NULL,
  dataset_versions jsonb NOT NULL,
  base_model jsonb NOT NULL,
  hyperparameters jsonb NOT NULL,
  hardware jsonb NOT NULL,
  random_seed bigint NOT NULL,
  status text NOT NULL,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  cost jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE model_artifact (
  model_artifact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  training_run_id uuid REFERENCES training_run(training_run_id),
  artifact_type text NOT NULL CHECK (artifact_type IN ('base','checkpoint','adapter','router','embedder','reranker','verifier')),
  name text NOT NULL,
  version text NOT NULL,
  content_hash text NOT NULL,
  artifact_uri text NOT NULL,
  base_model_ref text,
  tenant_id uuid REFERENCES tenant(tenant_id),
  signature jsonb,
  status text NOT NULL,
  UNIQUE (name, version)
);

CREATE TABLE model_evaluation (
  model_evaluation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_artifact_id uuid NOT NULL REFERENCES model_artifact(model_artifact_id),
  eval_suite text NOT NULL,
  baseline_release text,
  scores jsonb NOT NULL,
  hard_gate_results jsonb NOT NULL,
  evidence_bundle_id uuid REFERENCES evidence_artifact(evidence_id),
  decision text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE release_bundle (
  release_bundle_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  release_name text NOT NULL,
  version text NOT NULL,
  manifest_hash text NOT NULL,
  manifest jsonb NOT NULL,
  rollback_release_id uuid REFERENCES release_bundle(release_bundle_id),
  certification_level text NOT NULL,
  signature jsonb NOT NULL,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (release_name, version)
);

CREATE TABLE deployment (
  deployment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenant(tenant_id),
  release_bundle_id uuid NOT NULL REFERENCES release_bundle(release_bundle_id),
  environment text NOT NULL,
  region text NOT NULL,
  traffic_percent numeric(5,2) NOT NULL DEFAULT 0,
  status text NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  rolled_back_at timestamptz
);

CREATE TABLE usage_ledger (
  usage_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(tenant_id),
  project_id uuid REFERENCES project(project_id),
  episode_id uuid REFERENCES experience_episode(episode_id),
  model_release text,
  skill_name text,
  input_tokens bigint NOT NULL DEFAULT 0,
  output_tokens bigint NOT NULL DEFAULT 0,
  cache_tokens bigint NOT NULL DEFAULT 0,
  gpu_ms bigint NOT NULL DEFAULT 0,
  tool_cost numeric(18,8) NOT NULL DEFAULT 0,
  total_cost numeric(18,8) NOT NULL DEFAULT 0,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  idempotency_key text NOT NULL UNIQUE
);

CREATE TABLE policy_decision (
  decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenant(tenant_id),
  policy_bundle text NOT NULL,
  decision_point text NOT NULL,
  input_hash text NOT NULL,
  decision text NOT NULL,
  reasons jsonb NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_event (
  audit_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenant(tenant_id),
  actor jsonb NOT NULL,
  action text NOT NULL,
  resource jsonb NOT NULL,
  result text NOT NULL,
  trace_id text,
  content_hash text NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

-- Production deployment should add Row-Level Security policies for every tenant-scoped table,
-- separate tenant encryption keys, append-only audit storage, partitioning, retention jobs and backups.

-- v3 business-line and repository execution extension
CREATE TABLE IF NOT EXISTS business_line (
    id text PRIMARY KEY,
    pack_id text NOT NULL,
    owner_team text NOT NULL,
    status text NOT NULL,
    lifecycle_coverage jsonb NOT NULL,
    required_gates jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS capability_pack (
    id text PRIMARY KEY,
    version text NOT NULL,
    business_line_id text REFERENCES business_line(id),
    content_hash text NOT NULL,
    signature_ref text,
    maturity text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS skill_capability_binding (
    skill_id text NOT NULL,
    skill_version text NOT NULL,
    business_line_id text NOT NULL REFERENCES business_line(id),
    priority text NOT NULL,
    risk_class text NOT NULL,
    support_tier text NOT NULL,
    status text NOT NULL,
    PRIMARY KEY (skill_id, skill_version, business_line_id)
);

CREATE TABLE IF NOT EXISTS technology_adapter_profile (
    id uuid PRIMARY KEY,
    tenant_id uuid,
    category text NOT NULL,
    adapter_key text NOT NULL,
    version_range text NOT NULL,
    capabilities jsonb NOT NULL,
    limitations jsonb NOT NULL,
    conformance_level text NOT NULL,
    artifact_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, category, adapter_key, version_range, artifact_hash)
);

CREATE TABLE IF NOT EXISTS repository_execution (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    repository_id uuid NOT NULL,
    task_id uuid NOT NULL,
    source_snapshot_hash text NOT NULL,
    release_bundle_hash text NOT NULL,
    status text NOT NULL,
    critical_path jsonb,
    estimated_wall_clock_ms bigint,
    actual_wall_clock_ms bigint,
    rollback_target_hash text NOT NULL,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workspace_lease (
    id uuid PRIMARY KEY,
    repository_execution_id uuid NOT NULL REFERENCES repository_execution(id),
    workspace_uri text NOT NULL,
    owner_environment_id text NOT NULL,
    fencing_token bigint NOT NULL,
    lease_expires_at timestamptz NOT NULL,
    heartbeat_at timestamptz NOT NULL,
    state text NOT NULL,
    UNIQUE (workspace_uri, fencing_token)
);

CREATE TABLE IF NOT EXISTS execution_shard (
    id uuid PRIMARY KEY,
    repository_execution_id uuid NOT NULL REFERENCES repository_execution(id),
    shard_key text NOT NULL,
    dependency_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
    ownership_scope jsonb NOT NULL,
    assigned_environment_id text,
    state text NOT NULL,
    checkpoint_hash text,
    evidence_bundle_id uuid,
    UNIQUE (repository_execution_id, shard_key)
);

CREATE TABLE IF NOT EXISTS patch_set (
    id uuid PRIMARY KEY,
    repository_execution_id uuid NOT NULL REFERENCES repository_execution(id),
    shard_id uuid REFERENCES execution_shard(id),
    parent_patch_set_id uuid REFERENCES patch_set(id),
    content_hash text NOT NULL,
    affected_symbols jsonb NOT NULL,
    blast_radius jsonb NOT NULL,
    merge_state text NOT NULL,
    signature_ref text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS semantic_symbol_mapping (
    id uuid PRIMARY KEY,
    repository_execution_id uuid NOT NULL REFERENCES repository_execution(id),
    source_symbol_id text NOT NULL,
    semantic_ir_id text NOT NULL,
    target_symbol_id text,
    rule_id text,
    confidence numeric(6,5) NOT NULL,
    status text NOT NULL,
    evidence_refs jsonb NOT NULL,
    UNIQUE (repository_execution_id, source_symbol_id, semantic_ir_id, target_symbol_id)
);

CREATE TABLE IF NOT EXISTS transformation_wave (
    id uuid PRIMARY KEY,
    repository_execution_id uuid NOT NULL REFERENCES repository_execution(id),
    sequence_no integer NOT NULL,
    scope jsonb NOT NULL,
    compatibility_window jsonb NOT NULL,
    cutover_plan jsonb NOT NULL,
    rollback_plan jsonb NOT NULL,
    status text NOT NULL,
    UNIQUE (repository_execution_id, sequence_no)
);

CREATE TABLE IF NOT EXISTS verification_obligation (
    id uuid PRIMARY KEY,
    repository_execution_id uuid NOT NULL REFERENCES repository_execution(id),
    wave_id uuid REFERENCES transformation_wave(id),
    claim text NOT NULL,
    method text NOT NULL,
    hard_gate boolean NOT NULL DEFAULT true,
    status text NOT NULL,
    environment_hash text,
    result_hash text,
    evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    invalidated_at timestamptz
);

CREATE TABLE IF NOT EXISTS golden_route (
    id uuid PRIMARY KEY,
    business_line_id text NOT NULL REFERENCES business_line(id),
    version text NOT NULL,
    supported_matrix jsonb NOT NULL,
    repository_evidence jsonb NOT NULL,
    evidence_level text NOT NULL,
    repeatability_metrics jsonb NOT NULL,
    rollback_evidence jsonb NOT NULL,
    status text NOT NULL,
    certified_at timestamptz,
    expires_at timestamptz,
    UNIQUE (business_line_id, version)
);

CREATE TABLE IF NOT EXISTS customer_acceptance (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    repository_execution_id uuid NOT NULL REFERENCES repository_execution(id),
    scope_hash text NOT NULL,
    requirement_coverage jsonb NOT NULL,
    evidence_bundle_hash text NOT NULL,
    residual_risks jsonb NOT NULL,
    decision text NOT NULL,
    signer_refs jsonb NOT NULL,
    decided_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_repository_execution_tenant_status
    ON repository_execution (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_execution_shard_execution_state
    ON execution_shard (repository_execution_id, state);
CREATE INDEX IF NOT EXISTS idx_verification_obligation_execution_status
    ON verification_obligation (repository_execution_id, status, hard_gate);
CREATE INDEX IF NOT EXISTS idx_semantic_symbol_mapping_source
    ON semantic_symbol_mapping (repository_execution_id, source_symbol_id);
