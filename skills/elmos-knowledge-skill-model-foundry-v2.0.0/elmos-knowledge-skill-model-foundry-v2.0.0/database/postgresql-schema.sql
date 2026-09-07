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
