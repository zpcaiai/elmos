-- P05 reliability plane. Completion is evidence-based and bound to exact source,
-- target, policy, workflow, route, toolchain and environment revisions.

BEGIN;

CREATE TABLE verify.requirement (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  requirement_key text NOT NULL,
  requirement_type text NOT NULL
    CHECK (requirement_type IN ('functional', 'nonfunctional', 'security', 'performance', 'operability', 'compliance', 'migration', 'acceptance')),
  title text NOT NULL,
  description text NOT NULL,
  source_kind text NOT NULL CHECK (source_kind IN ('user', 'document', 'archetype', 'discovered', 'policy', 'review', 'derived')),
  source_reference jsonb NOT NULL DEFAULT '{}'::jsonb,
  criticality text NOT NULL DEFAULT 'medium' CHECK (criticality IN ('low', 'medium', 'high', 'critical')),
  status text NOT NULL DEFAULT 'discovered'
    CHECK (status IN ('discovered', 'confirmed', 'implemented', 'verified', 'blocked', 'waived', 'rejected', 'superseded')),
  semantic_sha256 text NOT NULL CHECK (core.sha256_is_valid(semantic_sha256)),
  generation_requirement_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, run_id, requirement_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, generation_requirement_id) REFERENCES generation.requirement_node(tenant_id, id)
);

CREATE TRIGGER verify_requirement_touch_updated_at
BEFORE UPDATE ON verify.requirement
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE verify.requirement_coverage (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  target_revision_id uuid NOT NULL,
  requirement_id uuid NOT NULL,
  coverage_status text NOT NULL
    CHECK (coverage_status IN ('unmapped', 'mapped', 'implemented', 'tested', 'verified', 'failed', 'blocked', 'waived')),
  implementation_reference jsonb,
  verification_case_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_item_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  coverage_score numeric(6,3) NOT NULL DEFAULT 0 CHECK (coverage_score BETWEEN 0 AND 100),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, target_revision_id, requirement_id),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, requirement_id) REFERENCES verify.requirement(tenant_id, id)
);

CREATE TRIGGER requirement_coverage_touch_updated_at
BEFORE UPDATE ON verify.requirement_coverage
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE verify.capability_coverage (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  target_revision_id uuid NOT NULL,
  source_capability_id uuid NOT NULL,
  target_capability_reference jsonb,
  coverage_status text NOT NULL
    CHECK (coverage_status IN ('discovered', 'mapped', 'generated', 'compiled', 'tested', 'verified', 'failed', 'unsupported', 'semantic_gap', 'waived')),
  equivalence_score numeric(6,3) CHECK (equivalence_score IS NULL OR equivalence_score BETWEEN 0 AND 100),
  evidence_item_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, target_revision_id, source_capability_id),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, source_capability_id) REFERENCES analysis.capability(tenant_id, id)
);

CREATE TRIGGER capability_coverage_touch_updated_at
BEFORE UPDATE ON verify.capability_coverage
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE verify.invariant (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  invariant_key text NOT NULL,
  invariant_kind text NOT NULL CHECK (invariant_kind IN ('business', 'transaction', 'authorization', 'data', 'message', 'concurrency', 'performance', 'security', 'operability')),
  description text NOT NULL,
  source_reference jsonb NOT NULL,
  executable_contract jsonb,
  criticality text NOT NULL DEFAULT 'high' CHECK (criticality IN ('low', 'medium', 'high', 'critical')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, run_id, invariant_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id)
);

CREATE TABLE verify.verification_plan (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  target_revision_id uuid NOT NULL,
  plan_no integer NOT NULL CHECK (plan_no > 0),
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'validated', 'active', 'completed', 'failed', 'superseded')),
  verification_matrix jsonb NOT NULL,
  risk_model jsonb NOT NULL DEFAULT '{}'::jsonb,
  plan_sha256 text NOT NULL CHECK (core.sha256_is_valid(plan_sha256)),
  artifact_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  activated_at timestamptz,
  completed_at timestamptz,
  UNIQUE (tenant_id, run_id, target_revision_id, plan_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE verify.verification_suite (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  verification_plan_id uuid NOT NULL,
  suite_key text NOT NULL,
  suite_type text NOT NULL
    CHECK (suite_type IN ('compile', 'static', 'unit', 'integration', 'contract', 'differential', 'property', 'metamorphic', 'e2e', 'ui', 'performance', 'stress', 'security', 'supply_chain', 'deployment')),
  criticality text NOT NULL DEFAULT 'medium' CHECK (criticality IN ('low', 'medium', 'high', 'critical')),
  required boolean NOT NULL DEFAULT true,
  execution_order integer NOT NULL DEFAULT 0,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, verification_plan_id, suite_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, verification_plan_id) REFERENCES verify.verification_plan(tenant_id, id)
);

CREATE TABLE verify.verification_case (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  suite_id uuid NOT NULL,
  case_key text NOT NULL,
  title text NOT NULL,
  case_kind text NOT NULL,
  requirement_id uuid,
  source_capability_id uuid,
  invariant_id uuid,
  test_artifact_id uuid,
  input_contract jsonb NOT NULL DEFAULT '{}'::jsonb,
  expected_contract jsonb NOT NULL DEFAULT '{}'::jsonb,
  deterministic boolean NOT NULL DEFAULT true,
  timeout_ms bigint CHECK (timeout_ms IS NULL OR timeout_ms > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, suite_id, case_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, suite_id) REFERENCES verify.verification_suite(tenant_id, id),
  FOREIGN KEY (tenant_id, requirement_id) REFERENCES verify.requirement(tenant_id, id),
  FOREIGN KEY (tenant_id, source_capability_id) REFERENCES analysis.capability(tenant_id, id),
  FOREIGN KEY (tenant_id, invariant_id) REFERENCES verify.invariant(tenant_id, id),
  FOREIGN KEY (tenant_id, test_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE verify.verification_execution (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  target_revision_id uuid NOT NULL,
  verification_plan_id uuid NOT NULL,
  suite_id uuid NOT NULL,
  execution_no integer NOT NULL CHECK (execution_no > 0),
  task_attempt_id uuid,
  environment_revision_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'created'
    CHECK (status IN ('created', 'running', 'passed', 'failed', 'error', 'timed_out', 'cancelled', 'invalidated')),
  started_at timestamptz,
  ended_at timestamptz,
  total_cases integer NOT NULL DEFAULT 0 CHECK (total_cases >= 0),
  passed_cases integer NOT NULL DEFAULT 0 CHECK (passed_cases >= 0),
  failed_cases integer NOT NULL DEFAULT 0 CHECK (failed_cases >= 0),
  skipped_cases integer NOT NULL DEFAULT 0 CHECK (skipped_cases >= 0),
  output_artifact_id uuid,
  trace_artifact_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, suite_id, target_revision_id, execution_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, verification_plan_id) REFERENCES verify.verification_plan(tenant_id, id),
  FOREIGN KEY (tenant_id, suite_id) REFERENCES verify.verification_suite(tenant_id, id),
  FOREIGN KEY (tenant_id, task_attempt_id) REFERENCES exec.task_attempt(tenant_id, id),
  FOREIGN KEY (tenant_id, environment_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, output_artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  FOREIGN KEY (tenant_id, trace_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE verify.verification_result (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  verification_execution_id uuid NOT NULL,
  verification_case_id uuid NOT NULL,
  status text NOT NULL CHECK (status IN ('passed', 'failed', 'error', 'skipped', 'not_run')),
  duration_ms bigint CHECK (duration_ms IS NULL OR duration_ms >= 0),
  observed_value jsonb,
  expected_value jsonb,
  failure_code text,
  failure_message text,
  output_artifact_id uuid,
  result_sha256 text NOT NULL CHECK (core.sha256_is_valid(result_sha256)),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, verification_execution_id, verification_case_id),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, verification_execution_id) REFERENCES verify.verification_execution(tenant_id, id),
  FOREIGN KEY (tenant_id, verification_case_id) REFERENCES verify.verification_case(tenant_id, id),
  FOREIGN KEY (tenant_id, output_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TRIGGER verification_result_immutable
BEFORE UPDATE OR DELETE ON verify.verification_result
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE verify.invariant_result (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  target_revision_id uuid NOT NULL,
  invariant_id uuid NOT NULL,
  verification_execution_id uuid,
  status text NOT NULL CHECK (status IN ('passed', 'failed', 'unknown', 'blocked', 'waived')),
  observation jsonb,
  evidence_artifact_id uuid,
  result_sha256 text NOT NULL CHECK (core.sha256_is_valid(result_sha256)),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, target_revision_id, invariant_id, verification_execution_id),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, invariant_id) REFERENCES verify.invariant(tenant_id, id),
  FOREIGN KEY (tenant_id, verification_execution_id) REFERENCES verify.verification_execution(tenant_id, id),
  FOREIGN KEY (tenant_id, evidence_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TRIGGER invariant_result_immutable
BEFORE UPDATE OR DELETE ON verify.invariant_result
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE verify.behavior_observation (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  verification_execution_id uuid NOT NULL,
  observation_key text NOT NULL,
  system_side text NOT NULL CHECK (system_side IN ('source', 'target', 'oracle')),
  input_sha256 text NOT NULL CHECK (core.sha256_is_valid(input_sha256)),
  response_sha256 text CHECK (core.sha256_is_valid(response_sha256)),
  database_state_sha256 text CHECK (core.sha256_is_valid(database_state_sha256)),
  cache_state_sha256 text CHECK (core.sha256_is_valid(cache_state_sha256)),
  message_state_sha256 text CHECK (core.sha256_is_valid(message_state_sha256)),
  filesystem_state_sha256 text CHECK (core.sha256_is_valid(filesystem_state_sha256)),
  authorization_outcome text,
  exception_contract jsonb,
  timing_summary jsonb,
  observation_artifact_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, verification_execution_id, observation_key, system_side),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, verification_execution_id) REFERENCES verify.verification_execution(tenant_id, id),
  FOREIGN KEY (tenant_id, observation_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TRIGGER behavior_observation_immutable
BEFORE UPDATE OR DELETE ON verify.behavior_observation
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE verify.differential_mismatch (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  verification_execution_id uuid NOT NULL,
  source_observation_id uuid NOT NULL,
  target_observation_id uuid NOT NULL,
  mismatch_kind text NOT NULL CHECK (mismatch_kind IN ('response', 'database', 'cache', 'message', 'filesystem', 'transaction', 'authorization', 'exception', 'timing', 'unknown')),
  severity text NOT NULL CHECK (severity IN ('info', 'low', 'medium', 'high', 'critical')),
  diff_summary jsonb NOT NULL,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'triaged', 'repairing', 'resolved', 'waived', 'false_positive')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  resolved_at timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, verification_execution_id) REFERENCES verify.verification_execution(tenant_id, id),
  FOREIGN KEY (tenant_id, source_observation_id) REFERENCES verify.behavior_observation(tenant_id, id),
  FOREIGN KEY (tenant_id, target_observation_id) REFERENCES verify.behavior_observation(tenant_id, id)
);

CREATE TABLE verify.semantic_gap (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  target_revision_id uuid NOT NULL,
  source_capability_id uuid,
  requirement_id uuid,
  gap_key text NOT NULL,
  gap_kind text NOT NULL CHECK (gap_kind IN ('unknown', 'unsupported', 'ambiguous', 'behavior_mismatch', 'missing_implementation', 'missing_test', 'policy_conflict')),
  severity text NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  description text NOT NULL,
  source_reference jsonb NOT NULL DEFAULT '{}'::jsonb,
  target_reference jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'triaged', 'repairing', 'resolved', 'waived', 'blocked', 'superseded')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, run_id, target_revision_id, gap_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, source_capability_id) REFERENCES analysis.capability(tenant_id, id),
  FOREIGN KEY (tenant_id, requirement_id) REFERENCES verify.requirement(tenant_id, id)
);

CREATE TRIGGER semantic_gap_touch_updated_at
BEFORE UPDATE ON verify.semantic_gap
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE verify.evidence_item (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  target_revision_id uuid NOT NULL,
  evidence_kind text NOT NULL
    CHECK (evidence_kind IN ('build', 'static_analysis', 'test', 'differential', 'property', 'e2e', 'ui', 'performance', 'security', 'supply_chain', 'coverage', 'review', 'deployment', 'manual')),
  subject_kind text NOT NULL CHECK (subject_kind IN ('run', 'requirement', 'capability', 'invariant', 'suite', 'case', 'gap', 'deployment')),
  subject_id uuid,
  producer_kind text NOT NULL CHECK (producer_kind IN ('verifier', 'tool', 'agent', 'ci', 'human', 'external_system')),
  producer_id text,
  task_attempt_id uuid,
  source_event_seq bigint NOT NULL CHECK (source_event_seq >= 0),
  artifact_id uuid NOT NULL,
  evidence_sha256 text NOT NULL CHECK (core.sha256_is_valid(evidence_sha256)),
  status text NOT NULL CHECK (status IN ('passed', 'failed', 'warning', 'informational', 'blocked')),
  freshness_deadline timestamptz,
  environment_revision_id uuid NOT NULL,
  toolchain_revision_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, run_id, target_revision_id, evidence_sha256),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, task_attempt_id) REFERENCES exec.task_attempt(tenant_id, id),
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  FOREIGN KEY (tenant_id, environment_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, toolchain_revision_id) REFERENCES core.revision_snapshot(tenant_id, id)
);

CREATE OR REPLACE FUNCTION verify.validate_evidence_item()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM artifact.artifact a
    WHERE a.tenant_id = NEW.tenant_id AND a.id = NEW.artifact_id AND a.state = 'available'
  ) THEN RAISE EXCEPTION 'evidence requires an available artifact'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM transform.target_revision t
    WHERE t.tenant_id = NEW.tenant_id AND t.id = NEW.target_revision_id AND t.run_id = NEW.run_id
  ) THEN RAISE EXCEPTION 'evidence target revision does not belong to run'; END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER validate_evidence_item
BEFORE INSERT ON verify.evidence_item
FOR EACH ROW EXECUTE FUNCTION verify.validate_evidence_item();

CREATE TRIGGER evidence_item_immutable
BEFORE UPDATE OR DELETE ON verify.evidence_item
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE verify.evidence_revocation (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  evidence_item_id uuid NOT NULL,
  reason_code text NOT NULL,
  reason text NOT NULL,
  revoked_by text NOT NULL,
  revoked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, evidence_item_id),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, evidence_item_id) REFERENCES verify.evidence_item(tenant_id, id)
);

CREATE TRIGGER evidence_revocation_immutable
BEFORE UPDATE OR DELETE ON verify.evidence_revocation
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE verify.evidence_bundle (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  target_revision_id uuid NOT NULL,
  bundle_no integer NOT NULL CHECK (bundle_no > 0),
  status text NOT NULL DEFAULT 'building' CHECK (status IN ('building', 'sealed', 'invalidated', 'superseded')),
  bundle_manifest_id uuid NOT NULL,
  bundle_sha256 text NOT NULL CHECK (core.sha256_is_valid(bundle_sha256)),
  evidence_count integer NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  sealed_at timestamptz,
  UNIQUE (tenant_id, run_id, target_revision_id, bundle_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, bundle_manifest_id) REFERENCES artifact.manifest(tenant_id, id),
  CHECK ((status = 'sealed' AND sealed_at IS NOT NULL) OR status <> 'sealed')
);

CREATE TABLE verify.evidence_bundle_item (
  tenant_id uuid NOT NULL,
  evidence_bundle_id uuid NOT NULL,
  evidence_item_id uuid NOT NULL,
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  PRIMARY KEY (tenant_id, evidence_bundle_id, evidence_item_id),
  UNIQUE (tenant_id, evidence_bundle_id, ordinal),
  FOREIGN KEY (tenant_id, evidence_bundle_id) REFERENCES verify.evidence_bundle(tenant_id, id),
  FOREIGN KEY (tenant_id, evidence_item_id) REFERENCES verify.evidence_item(tenant_id, id)
);

CREATE TRIGGER evidence_bundle_item_immutable
BEFORE UPDATE OR DELETE ON verify.evidence_bundle_item
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE verify.waiver (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  subject_kind text NOT NULL CHECK (subject_kind IN ('requirement', 'capability', 'invariant', 'gap', 'gate_finding', 'verification_case')),
  subject_id uuid NOT NULL,
  scope_sha256 text NOT NULL CHECK (core.sha256_is_valid(scope_sha256)),
  rationale text NOT NULL,
  risk_acceptance text NOT NULL,
  approved_by text NOT NULL,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'revoked', 'superseded')),
  approved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz,
  revoked_at timestamptz,
  UNIQUE (tenant_id, run_id, subject_kind, subject_id, scope_sha256),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id)
);

CREATE TABLE verify.gate_evaluation (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  gate_kind text NOT NULL CHECK (gate_kind IN ('generation_complete', 'conversion_complete', 'release_candidate', 'deployment_complete', 'certification')),
  gate_policy_revision_id uuid NOT NULL,
  source_repository_revision_id uuid,
  target_revision_id uuid NOT NULL,
  requirements_revision_id uuid,
  policy_revision_id uuid NOT NULL,
  workflow_revision_id uuid NOT NULL,
  model_route_revision_id uuid NOT NULL,
  toolchain_revision_id uuid NOT NULL,
  environment_revision_id uuid NOT NULL,
  evidence_bundle_id uuid NOT NULL,
  decision text NOT NULL CHECK (decision IN ('pass', 'fail', 'blocked', 'error')),
  requirement_coverage numeric(6,3) NOT NULL CHECK (requirement_coverage BETWEEN 0 AND 100),
  capability_coverage numeric(6,3) NOT NULL CHECK (capability_coverage BETWEEN 0 AND 100),
  behavioral_equivalence numeric(6,3) CHECK (behavioral_equivalence IS NULL OR behavioral_equivalence BETWEEN 0 AND 100),
  unknown_gap_count integer NOT NULL DEFAULT 0 CHECK (unknown_gap_count >= 0),
  critical_failure_count integer NOT NULL DEFAULT 0 CHECK (critical_failure_count >= 0),
  unresolved_side_effect_count integer NOT NULL DEFAULT 0 CHECK (unresolved_side_effect_count >= 0),
  unfinished_task_count integer NOT NULL DEFAULT 0 CHECK (unfinished_task_count >= 0),
  evaluation_summary jsonb NOT NULL,
  evaluator_version text NOT NULL,
  evaluated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, run_id, gate_kind, target_revision_id, evidence_bundle_id),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, gate_policy_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, source_repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, requirements_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, policy_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, workflow_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, model_route_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, toolchain_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, environment_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, evidence_bundle_id) REFERENCES verify.evidence_bundle(tenant_id, id)
);

CREATE OR REPLACE FUNCTION verify.validate_gate_evaluation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM verify.evidence_bundle b
    WHERE b.tenant_id = NEW.tenant_id AND b.id = NEW.evidence_bundle_id
      AND b.run_id = NEW.run_id AND b.target_revision_id = NEW.target_revision_id
      AND b.status = 'sealed'
  ) THEN RAISE EXCEPTION 'gate requires a sealed evidence bundle for the same run and target revision'; END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER validate_gate_evaluation
BEFORE INSERT ON verify.gate_evaluation
FOR EACH ROW EXECUTE FUNCTION verify.validate_gate_evaluation();

CREATE TRIGGER gate_evaluation_immutable
BEFORE UPDATE OR DELETE ON verify.gate_evaluation
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE verify.gate_finding (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  gate_evaluation_id uuid NOT NULL,
  finding_code text NOT NULL,
  severity text NOT NULL CHECK (severity IN ('info', 'warning', 'high', 'critical')),
  subject_kind text,
  subject_id uuid,
  message text NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  waiver_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, gate_evaluation_id) REFERENCES verify.gate_evaluation(tenant_id, id),
  FOREIGN KEY (tenant_id, waiver_id) REFERENCES verify.waiver(tenant_id, id)
);

CREATE TRIGGER gate_finding_immutable
BEFORE UPDATE OR DELETE ON verify.gate_finding
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE verify.failure_cluster (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  cluster_key text NOT NULL,
  failure_kind text NOT NULL,
  normalized_signature text NOT NULL,
  signature_sha256 text NOT NULL CHECK (core.sha256_is_valid(signature_sha256)),
  occurrence_count integer NOT NULL DEFAULT 1 CHECK (occurrence_count > 0),
  severity text NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'triaged', 'repairing', 'resolved', 'waived', 'superseded')),
  representative_artifact_id uuid,
  first_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  last_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, run_id, signature_sha256),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, representative_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE verify.repair_attempt (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  failure_cluster_id uuid,
  semantic_gap_id uuid,
  repair_no integer NOT NULL CHECK (repair_no > 0),
  task_attempt_id uuid,
  before_target_revision_id uuid NOT NULL,
  after_target_revision_id uuid,
  repair_strategy text NOT NULL,
  repair_rule_key text,
  status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'succeeded', 'failed', 'reverted', 'cancelled')),
  verification_execution_id uuid,
  started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  ended_at timestamptz,
  UNIQUE NULLS NOT DISTINCT (tenant_id, run_id, failure_cluster_id, semantic_gap_id, repair_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, failure_cluster_id) REFERENCES verify.failure_cluster(tenant_id, id),
  FOREIGN KEY (tenant_id, semantic_gap_id) REFERENCES verify.semantic_gap(tenant_id, id),
  FOREIGN KEY (tenant_id, task_attempt_id) REFERENCES exec.task_attempt(tenant_id, id),
  FOREIGN KEY (tenant_id, before_target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, after_target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, verification_execution_id) REFERENCES verify.verification_execution(tenant_id, id),
  CHECK (failure_cluster_id IS NOT NULL OR semantic_gap_id IS NOT NULL)
);

CREATE TABLE verify.certification (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  target_revision_id uuid NOT NULL,
  certification_level text NOT NULL CHECK (certification_level IN ('E1', 'E2', 'E3', 'E4', 'E5')),
  gate_evaluation_id uuid NOT NULL,
  certificate_artifact_id uuid NOT NULL,
  certificate_sha256 text NOT NULL CHECK (core.sha256_is_valid(certificate_sha256)),
  issued_by text NOT NULL,
  issued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz,
  revoked_at timestamptz,
  revocation_reason text,
  UNIQUE (tenant_id, target_revision_id, certification_level, issued_at),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, gate_evaluation_id) REFERENCES verify.gate_evaluation(tenant_id, id),
  FOREIGN KEY (tenant_id, certificate_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE INDEX requirement_coverage_open_idx ON verify.requirement_coverage (tenant_id, run_id, coverage_status)
  WHERE coverage_status NOT IN ('verified', 'waived');
CREATE INDEX capability_coverage_open_idx ON verify.capability_coverage (tenant_id, run_id, coverage_status)
  WHERE coverage_status NOT IN ('verified', 'waived');
CREATE INDEX verification_execution_status_idx ON verify.verification_execution (tenant_id, run_id, status, started_at);
CREATE INDEX verification_result_failed_idx ON verify.verification_result (tenant_id, run_id, verification_execution_id)
  WHERE status IN ('failed', 'error');
CREATE INDEX differential_open_idx ON verify.differential_mismatch (tenant_id, run_id, severity, created_at)
  WHERE status IN ('open', 'triaged', 'repairing');
CREATE INDEX semantic_gap_open_idx ON verify.semantic_gap (tenant_id, run_id, severity, created_at)
  WHERE status IN ('open', 'triaged', 'repairing', 'blocked');
CREATE INDEX evidence_subject_idx ON verify.evidence_item (tenant_id, run_id, subject_kind, subject_id, created_at DESC);
CREATE INDEX evidence_freshness_idx ON verify.evidence_item (tenant_id, freshness_deadline)
  WHERE freshness_deadline IS NOT NULL;
CREATE INDEX gate_run_latest_idx ON verify.gate_evaluation (tenant_id, run_id, evaluated_at DESC);

COMMIT;
