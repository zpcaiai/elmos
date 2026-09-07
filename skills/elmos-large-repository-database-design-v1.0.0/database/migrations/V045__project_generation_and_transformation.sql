-- Complete-project generation and repository/language/framework transformation.
-- Plans and decisions are versioned; generated source bodies remain in CAS/workspaces.

BEGIN;

CREATE TABLE generation.requirement_set (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  requirements_revision_id uuid NOT NULL,
  set_version integer NOT NULL CHECK (set_version > 0),
  status text NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'expanded', 'confirmed', 'frozen', 'superseded', 'invalid')),
  source_kind text NOT NULL CHECK (source_kind IN ('user', 'documents', 'archetype', 'repository', 'merged')),
  root_sha256 text NOT NULL CHECK (core.sha256_is_valid(root_sha256)),
  requirement_count integer NOT NULL DEFAULT 0 CHECK (requirement_count >= 0),
  acceptance_count integer NOT NULL DEFAULT 0 CHECK (acceptance_count >= 0),
  artifact_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  frozen_at timestamptz,
  UNIQUE (tenant_id, run_id, set_version),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, requirements_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE generation.requirement_node (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  requirement_set_id uuid NOT NULL,
  requirement_key text NOT NULL,
  parent_requirement_id uuid,
  requirement_type text NOT NULL
    CHECK (requirement_type IN ('functional', 'nonfunctional', 'security', 'performance', 'operability', 'compliance', 'deployment', 'migration', 'acceptance')),
  title text NOT NULL,
  description text NOT NULL,
  source_kind text NOT NULL CHECK (source_kind IN ('explicit', 'archetype', 'derived', 'discovered', 'policy', 'human')),
  criticality text NOT NULL DEFAULT 'medium' CHECK (criticality IN ('low', 'medium', 'high', 'critical')),
  status text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'confirmed', 'rejected', 'implemented', 'verified', 'blocked', 'waived', 'superseded')),
  source_reference jsonb NOT NULL DEFAULT '{}'::jsonb,
  semantic_sha256 text NOT NULL CHECK (core.sha256_is_valid(semantic_sha256)),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, requirement_set_id, requirement_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, requirement_set_id) REFERENCES generation.requirement_set(tenant_id, id),
  FOREIGN KEY (tenant_id, parent_requirement_id) REFERENCES generation.requirement_node(tenant_id, id)
);

CREATE TRIGGER requirement_node_touch_updated_at
BEFORE UPDATE ON generation.requirement_node
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE generation.requirement_edge (
  tenant_id uuid NOT NULL,
  requirement_set_id uuid NOT NULL,
  from_requirement_id uuid NOT NULL,
  to_requirement_id uuid NOT NULL,
  edge_kind text NOT NULL CHECK (edge_kind IN ('depends_on', 'conflicts', 'refines', 'implements', 'verifies', 'blocks', 'duplicates')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, from_requirement_id, to_requirement_id, edge_kind),
  FOREIGN KEY (tenant_id, requirement_set_id) REFERENCES generation.requirement_set(tenant_id, id),
  FOREIGN KEY (tenant_id, from_requirement_id) REFERENCES generation.requirement_node(tenant_id, id),
  FOREIGN KEY (tenant_id, to_requirement_id) REFERENCES generation.requirement_node(tenant_id, id),
  CHECK (from_requirement_id <> to_requirement_id)
);

CREATE TABLE generation.acceptance_criterion (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  requirement_set_id uuid NOT NULL,
  requirement_id uuid NOT NULL,
  criterion_key text NOT NULL,
  criterion_type text NOT NULL CHECK (criterion_type IN ('example', 'contract', 'property', 'scenario', 'threshold', 'manual_review')),
  description text NOT NULL,
  executable_spec jsonb,
  expected_evidence_kind text,
  criticality text NOT NULL DEFAULT 'medium' CHECK (criticality IN ('low', 'medium', 'high', 'critical')),
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'implemented', 'verified', 'failed', 'blocked', 'waived', 'superseded')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, requirement_set_id, criterion_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, requirement_set_id) REFERENCES generation.requirement_set(tenant_id, id),
  FOREIGN KEY (tenant_id, requirement_id) REFERENCES generation.requirement_node(tenant_id, id)
);

CREATE TRIGGER acceptance_criterion_touch_updated_at
BEFORE UPDATE ON generation.acceptance_criterion
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE generation.archetype_selection (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  archetype_key text NOT NULL,
  archetype_version text NOT NULL,
  confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  selection_kind text NOT NULL CHECK (selection_kind IN ('primary', 'secondary', 'excluded')),
  rationale text,
  capability_baseline jsonb NOT NULL DEFAULT '{}'::jsonb,
  rule_revision_id uuid,
  selected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, run_id, archetype_key, archetype_version),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, rule_revision_id) REFERENCES core.revision_snapshot(tenant_id, id)
);

CREATE TABLE generation.architecture_revision (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  architecture_no integer NOT NULL CHECK (architecture_no > 0),
  status text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'reviewed', 'approved', 'rejected', 'superseded')),
  architecture_style text,
  technology_matrix jsonb NOT NULL DEFAULT '{}'::jsonb,
  component_model jsonb NOT NULL DEFAULT '{}'::jsonb,
  deployment_model jsonb NOT NULL DEFAULT '{}'::jsonb,
  quality_attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  decision_log_artifact_id uuid,
  architecture_artifact_id uuid NOT NULL,
  architecture_sha256 text NOT NULL CHECK (core.sha256_is_valid(architecture_sha256)),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  approved_at timestamptz,
  UNIQUE (tenant_id, run_id, architecture_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, decision_log_artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  FOREIGN KEY (tenant_id, architecture_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE generation.project_generation_plan (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  requirement_set_id uuid NOT NULL,
  architecture_revision_id uuid NOT NULL,
  plan_no integer NOT NULL CHECK (plan_no > 0),
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'validated', 'active', 'completed', 'failed', 'superseded')),
  plan_sha256 text NOT NULL CHECK (core.sha256_is_valid(plan_sha256)),
  task_dag_artifact_id uuid,
  unit_count integer NOT NULL DEFAULT 0 CHECK (unit_count >= 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  activated_at timestamptz,
  completed_at timestamptz,
  UNIQUE (tenant_id, run_id, plan_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, requirement_set_id) REFERENCES generation.requirement_set(tenant_id, id),
  FOREIGN KEY (tenant_id, architecture_revision_id) REFERENCES generation.architecture_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, task_dag_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE generation.generation_unit (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  plan_id uuid NOT NULL,
  unit_key text NOT NULL,
  unit_kind text NOT NULL CHECK (unit_kind IN ('module', 'service', 'library', 'api', 'database', 'ui', 'test', 'infrastructure', 'documentation', 'integration')),
  target_path text,
  status text NOT NULL DEFAULT 'planned'
    CHECK (status IN ('planned', 'ready', 'generating', 'generated', 'building', 'verified', 'failed', 'blocked', 'superseded')),
  requirement_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
  capability_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
  input_contract jsonb NOT NULL DEFAULT '{}'::jsonb,
  output_contract jsonb NOT NULL DEFAULT '{}'::jsonb,
  current_iteration_no integer NOT NULL DEFAULT 0 CHECK (current_iteration_no >= 0),
  task_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, plan_id, unit_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, plan_id) REFERENCES generation.project_generation_plan(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id)
);

CREATE TRIGGER generation_unit_touch_updated_at
BEFORE UPDATE ON generation.generation_unit
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE generation.capability_mapping (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  generation_unit_id uuid NOT NULL,
  source_capability_id uuid,
  requirement_id uuid,
  target_capability_key text NOT NULL,
  mapping_kind text NOT NULL CHECK (mapping_kind IN ('generated', 'adapted', 'reused', 'delegated', 'unsupported', 'waived')),
  status text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'implemented', 'verified', 'failed', 'blocked', 'superseded')),
  mapping_contract jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence numeric(5,4) NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE NULLS NOT DISTINCT (tenant_id, generation_unit_id, source_capability_id, requirement_id, target_capability_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, generation_unit_id) REFERENCES generation.generation_unit(tenant_id, id),
  FOREIGN KEY (tenant_id, source_capability_id) REFERENCES analysis.capability(tenant_id, id),
  FOREIGN KEY (tenant_id, requirement_id) REFERENCES generation.requirement_node(tenant_id, id),
  CHECK (source_capability_id IS NOT NULL OR requirement_id IS NOT NULL)
);

CREATE TRIGGER capability_mapping_touch_updated_at
BEFORE UPDATE ON generation.capability_mapping
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE generation.generation_iteration (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  generation_unit_id uuid NOT NULL,
  iteration_no integer NOT NULL CHECK (iteration_no > 0),
  task_attempt_id uuid,
  trigger_kind text NOT NULL CHECK (trigger_kind IN ('initial', 'feedback', 'compile_repair', 'test_repair', 'review_repair', 'gap_repair')),
  status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'generated', 'accepted', 'rejected', 'failed', 'cancelled')),
  input_sha256 text NOT NULL CHECK (core.sha256_is_valid(input_sha256)),
  output_manifest_id uuid,
  target_revision_id uuid,
  summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  ended_at timestamptz,
  UNIQUE (tenant_id, generation_unit_id, iteration_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, generation_unit_id) REFERENCES generation.generation_unit(tenant_id, id),
  FOREIGN KEY (tenant_id, task_attempt_id) REFERENCES exec.task_attempt(tenant_id, id),
  FOREIGN KEY (tenant_id, output_manifest_id) REFERENCES artifact.manifest(tenant_id, id)
);

CREATE TABLE generation.generated_file (
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL,
  file_id uuid NOT NULL DEFAULT extensions.gen_random_uuid(),
  generation_unit_id uuid NOT NULL,
  generation_iteration_id uuid NOT NULL,
  normalized_path text NOT NULL,
  file_kind text NOT NULL CHECK (file_kind IN ('source', 'test', 'config', 'schema', 'migration', 'infrastructure', 'documentation', 'asset')),
  language text,
  content_sha256 text NOT NULL CHECK (core.sha256_is_valid(content_sha256)),
  artifact_id uuid NOT NULL,
  origin text NOT NULL CHECK (origin IN ('generated', 'copied', 'transformed', 'template', 'repaired', 'human')),
  state text NOT NULL DEFAULT 'generated' CHECK (state IN ('generated', 'staged', 'published', 'superseded', 'deleted', 'quarantined')),
  line_count integer CHECK (line_count IS NULL OR line_count >= 0),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, run_id, file_id),
  UNIQUE (tenant_id, run_id, generation_iteration_id, normalized_path),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, generation_unit_id) REFERENCES generation.generation_unit(tenant_id, id),
  FOREIGN KEY (tenant_id, generation_iteration_id) REFERENCES generation.generation_iteration(tenant_id, id),
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id)
) PARTITION BY HASH (run_id);

DO $$
DECLARE i integer;
BEGIN
  FOR i IN 0..15 LOOP
    EXECUTE format(
      'CREATE TABLE generation.generated_file_p%s PARTITION OF generation.generated_file FOR VALUES WITH (MODULUS 16, REMAINDER %s)',
      lpad(i::text, 2, '0'), i
    );
  END LOOP;
END $$;

CREATE TABLE generation.generation_decision (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  decision_key text NOT NULL,
  decision_kind text NOT NULL CHECK (decision_kind IN ('architecture', 'technology', 'database', 'framework', 'library', 'pattern', 'security', 'operability', 'tradeoff')),
  status text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'accepted', 'rejected', 'superseded')),
  options jsonb NOT NULL,
  selected_option jsonb,
  rationale text,
  decided_by_kind text CHECK (decided_by_kind IS NULL OR decided_by_kind IN ('rule', 'model', 'human', 'policy')),
  evidence_reference jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  decided_at timestamptz,
  UNIQUE (tenant_id, run_id, decision_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id)
);

CREATE TABLE transform.transformation_plan (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  source_analysis_snapshot_id uuid NOT NULL,
  source_ir_revision_id uuid,
  plan_no integer NOT NULL CHECK (plan_no > 0),
  source_stack jsonb NOT NULL,
  target_stack jsonb NOT NULL,
  strategy text NOT NULL CHECK (strategy IN ('full_rewrite', 'incremental', 'strangler', 'shadow', 'adapter', 'hybrid')),
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'validated', 'active', 'completed', 'failed', 'superseded')),
  plan_sha256 text NOT NULL CHECK (core.sha256_is_valid(plan_sha256)),
  plan_artifact_id uuid,
  unit_count integer NOT NULL DEFAULT 0 CHECK (unit_count >= 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  activated_at timestamptz,
  completed_at timestamptz,
  UNIQUE (tenant_id, run_id, plan_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, source_analysis_snapshot_id) REFERENCES analysis.analysis_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, source_ir_revision_id) REFERENCES analysis.semantic_ir_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, plan_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE transform.transformation_unit (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  plan_id uuid NOT NULL,
  unit_key text NOT NULL,
  unit_kind text NOT NULL CHECK (unit_kind IN ('module', 'symbol_group', 'api', 'data', 'message', 'schedule', 'security', 'ui', 'infrastructure', 'test')),
  source_reference jsonb NOT NULL,
  target_reference jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'ready', 'transforming', 'transformed', 'verified', 'failed', 'blocked', 'superseded')),
  task_id uuid,
  source_semantic_sha256 text NOT NULL CHECK (core.sha256_is_valid(source_semantic_sha256)),
  target_semantic_sha256 text CHECK (core.sha256_is_valid(target_semantic_sha256)),
  risk_score numeric(6,3) NOT NULL DEFAULT 0 CHECK (risk_score BETWEEN 0 AND 100),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, plan_id, unit_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, plan_id) REFERENCES transform.transformation_plan(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id)
);

CREATE TRIGGER transformation_unit_touch_updated_at
BEFORE UPDATE ON transform.transformation_unit
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE transform.mapping_decision (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  transformation_unit_id uuid NOT NULL,
  mapping_kind text NOT NULL CHECK (mapping_kind IN ('type', 'api', 'framework', 'transaction', 'concurrency', 'exception', 'database', 'message', 'security', 'ui', 'configuration')),
  source_semantics jsonb NOT NULL,
  target_semantics jsonb NOT NULL,
  invariants jsonb NOT NULL DEFAULT '[]'::jsonb,
  decision_source text NOT NULL CHECK (decision_source IN ('certified_rule', 'trusted_rule', 'model', 'human', 'fallback')),
  rule_release_id uuid,
  confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  status text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'accepted', 'rejected', 'verified', 'failed', 'superseded')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  verified_at timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, transformation_unit_id) REFERENCES transform.transformation_unit(tenant_id, id)
);

CREATE TABLE transform.rule_application (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  transformation_unit_id uuid NOT NULL,
  mapping_decision_id uuid,
  rule_key text NOT NULL,
  rule_version text NOT NULL,
  rule_stage text NOT NULL CHECK (rule_stage IN ('experimental', 'candidate', 'validated', 'trusted', 'certified')),
  applicability_result text NOT NULL CHECK (applicability_result IN ('matched', 'not_matched', 'ambiguous', 'blocked')),
  input_sha256 text NOT NULL CHECK (core.sha256_is_valid(input_sha256)),
  output_sha256 text CHECK (core.sha256_is_valid(output_sha256)),
  status text NOT NULL CHECK (status IN ('planned', 'applied', 'verified', 'failed', 'rolled_back')),
  diagnostic jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, transformation_unit_id) REFERENCES transform.transformation_unit(tenant_id, id),
  FOREIGN KEY (tenant_id, mapping_decision_id) REFERENCES transform.mapping_decision(tenant_id, id)
);

CREATE TABLE transform.target_revision (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  sequence_no integer NOT NULL CHECK (sequence_no > 0),
  parent_target_revision_id uuid,
  repository_revision_id uuid,
  tree_manifest_id uuid NOT NULL,
  tree_sha256 text NOT NULL CHECK (core.sha256_is_valid(tree_sha256)),
  revision_kind text NOT NULL CHECK (revision_kind IN ('generated', 'transformed', 'repaired', 'merged', 'release_candidate', 'released')),
  status text NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'building', 'verified', 'failed', 'superseded', 'released')),
  source_event_seq bigint NOT NULL CHECK (source_event_seq >= 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  verified_at timestamptz,
  UNIQUE (tenant_id, run_id, sequence_no),
  UNIQUE (tenant_id, run_id, tree_sha256),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, parent_target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, tree_manifest_id) REFERENCES artifact.manifest(tenant_id, id)
);

CREATE TABLE transform.patch_set (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  transformation_unit_id uuid,
  from_target_revision_id uuid,
  to_target_revision_id uuid NOT NULL,
  patch_artifact_id uuid NOT NULL,
  patch_sha256 text NOT NULL CHECK (core.sha256_is_valid(patch_sha256)),
  file_count integer NOT NULL DEFAULT 0 CHECK (file_count >= 0),
  additions bigint NOT NULL DEFAULT 0 CHECK (additions >= 0),
  deletions bigint NOT NULL DEFAULT 0 CHECK (deletions >= 0),
  status text NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'applied', 'verified', 'rejected', 'superseded')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, transformation_unit_id) REFERENCES transform.transformation_unit(tenant_id, id),
  FOREIGN KEY (tenant_id, from_target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, to_target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, patch_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE transform.cutover_plan (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  plan_version integer NOT NULL CHECK (plan_version > 0),
  strategy text NOT NULL CHECK (strategy IN ('big_bang', 'strangler', 'shadow', 'dual_run', 'feature_flag', 'manual')),
  stages jsonb NOT NULL,
  rollback_contract jsonb NOT NULL,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'executing', 'completed', 'rolled_back', 'failed', 'superseded')),
  artifact_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  approved_at timestamptz,
  UNIQUE (tenant_id, run_id, plan_version),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE INDEX requirement_node_status_idx ON generation.requirement_node (tenant_id, requirement_set_id, status, criticality);
CREATE INDEX acceptance_pending_idx ON generation.acceptance_criterion (tenant_id, requirement_set_id, status)
  WHERE status NOT IN ('verified', 'waived', 'superseded');
CREATE INDEX generation_unit_status_idx ON generation.generation_unit (tenant_id, run_id, status);
CREATE INDEX generated_file_path_trgm_idx ON generation.generated_file USING gin (normalized_path extensions.gin_trgm_ops);
CREATE INDEX transformation_unit_status_idx ON transform.transformation_unit (tenant_id, run_id, status, risk_score DESC);
CREATE INDEX mapping_decision_status_idx ON transform.mapping_decision (tenant_id, run_id, status, confidence);
CREATE INDEX target_revision_latest_idx ON transform.target_revision (tenant_id, run_id, sequence_no DESC);

COMMIT;
