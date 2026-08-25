-- Transactional integration effects, reconciliation, validated learning assets,
-- deployment/Migration health evidence and immutable audit records.

BEGIN;

CREATE TABLE integration.outbox_event (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT extensions.gen_random_uuid(),
  aggregate_type text NOT NULL,
  aggregate_id uuid NOT NULL,
  event_type text NOT NULL CHECK (event_type ~ '^[a-z][a-z0-9_.-]+$'),
  event_version integer NOT NULL DEFAULT 1 CHECK (event_version > 0),
  correlation_id text NOT NULL,
  causation_id uuid,
  payload jsonb NOT NULL,
  payload_sha256 text CHECK (core.sha256_is_valid(payload_sha256)),
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'publishing', 'published', 'failed', 'dead_letter')),
  available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  published_at timestamptz,
  attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  last_error text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, id),
  UNIQUE (tenant_id, aggregate_type, aggregate_id, event_type, correlation_id)
) PARTITION BY HASH (tenant_id);

DO $$
DECLARE i integer;
BEGIN
  FOR i IN 0..15 LOOP
    EXECUTE format(
      'CREATE TABLE integration.outbox_event_p%s PARTITION OF integration.outbox_event FOR VALUES WITH (MODULUS 16, REMAINDER %s)',
      lpad(i::text, 2, '0'), i
    );
  END LOOP;
END $$;

CREATE TABLE integration.inbox_message (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  source_system text NOT NULL,
  source_message_id text NOT NULL,
  message_type text NOT NULL,
  payload_sha256 text NOT NULL CHECK (core.sha256_is_valid(payload_sha256)),
  payload jsonb,
  status text NOT NULL DEFAULT 'received' CHECK (status IN ('received', 'processing', 'processed', 'ignored', 'failed', 'dead_letter')),
  received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  processed_at timestamptz,
  error_detail jsonb,
  UNIQUE (tenant_id, source_system, source_message_id),
  UNIQUE (tenant_id, id)
);

CREATE TABLE integration.side_effect_receipt (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  task_id uuid,
  task_attempt_id uuid,
  tool_invocation_id uuid,
  effect_kind text NOT NULL
    CHECK (effect_kind IN ('git_push', 'pull_request', 'ticket_write', 'deployment', 'database_migration', 'external_api_write', 'notification', 'payment', 'file_publish', 'other')),
  destination text NOT NULL,
  idempotency_key text NOT NULL,
  request_sha256 text NOT NULL CHECK (core.sha256_is_valid(request_sha256)),
  external_operation_id text,
  status text NOT NULL DEFAULT 'reserved'
    CHECK (status IN ('reserved', 'dispatching', 'succeeded', 'failed', 'unknown_result', 'reconciling', 'compensating', 'compensated', 'abandoned')),
  response_sha256 text CHECK (core.sha256_is_valid(response_sha256)),
  response_artifact_id uuid,
  first_dispatched_at timestamptz,
  last_checked_at timestamptz,
  completed_at timestamptz,
  error_code text,
  error_detail jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, destination, idempotency_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id),
  FOREIGN KEY (tenant_id, task_attempt_id) REFERENCES exec.task_attempt(tenant_id, id),
  FOREIGN KEY (tenant_id, tool_invocation_id) REFERENCES metering.tool_invocation(tenant_id, id),
  FOREIGN KEY (tenant_id, response_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TRIGGER side_effect_receipt_touch_updated_at
BEFORE UPDATE ON integration.side_effect_receipt
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE integration.compensation_action (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  side_effect_receipt_id uuid NOT NULL,
  compensation_kind text NOT NULL,
  idempotency_key text NOT NULL,
  status text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'approved', 'running', 'succeeded', 'failed', 'not_possible', 'cancelled')),
  request_sha256 text CHECK (core.sha256_is_valid(request_sha256)),
  external_operation_id text,
  result_artifact_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  started_at timestamptz,
  ended_at timestamptz,
  error_detail jsonb,
  UNIQUE (tenant_id, side_effect_receipt_id, idempotency_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, side_effect_receipt_id) REFERENCES integration.side_effect_receipt(tenant_id, id),
  FOREIGN KEY (tenant_id, result_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE integration.reconciliation_run (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  reconciliation_kind text NOT NULL CHECK (reconciliation_kind IN ('startup', 'periodic', 'run', 'side_effect', 'billing', 'artifact', 'deployment')),
  scope_kind text NOT NULL CHECK (scope_kind IN ('tenant', 'account', 'project', 'job', 'run', 'global')),
  scope_id uuid,
  status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'partial', 'failed')),
  scanned_count bigint NOT NULL DEFAULT 0 CHECK (scanned_count >= 0),
  issue_count bigint NOT NULL DEFAULT 0 CHECK (issue_count >= 0),
  repaired_count bigint NOT NULL DEFAULT 0 CHECK (repaired_count >= 0),
  started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  ended_at timestamptz,
  summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (tenant_id, id)
);

CREATE TABLE integration.reconciliation_issue (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  reconciliation_run_id uuid NOT NULL,
  issue_kind text NOT NULL,
  severity text NOT NULL CHECK (severity IN ('info', 'warning', 'high', 'critical')),
  subject_kind text NOT NULL,
  subject_id uuid,
  expected_state jsonb,
  observed_state jsonb,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'repairing', 'repaired', 'ignored', 'failed', 'manual')),
  recovery_action_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  resolved_at timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, reconciliation_run_id) REFERENCES integration.reconciliation_run(tenant_id, id),
  FOREIGN KEY (tenant_id, recovery_action_id) REFERENCES exec.recovery_action(tenant_id, id)
);

CREATE TABLE learning.data_authorization (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  project_id uuid,
  authorization_scope text NOT NULL CHECK (authorization_scope IN ('none', 'tenant_private', 'cross_project_private', 'anonymized_aggregate', 'global_public')),
  allowed_asset_kinds jsonb NOT NULL DEFAULT '[]'::jsonb,
  prohibited_data_classes jsonb NOT NULL DEFAULT '["restricted"]'::jsonb,
  policy_revision_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'expired', 'superseded')),
  approved_by text NOT NULL,
  approved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  revoked_at timestamptz,
  UNIQUE NULLS NOT DISTINCT (tenant_id, project_id, status),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES core.project(tenant_id, id),
  FOREIGN KEY (tenant_id, policy_revision_id) REFERENCES core.revision_snapshot(tenant_id, id)
);

CREATE TABLE learning.transformation_case (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  target_revision_id uuid NOT NULL,
  gate_evaluation_id uuid NOT NULL,
  data_authorization_id uuid NOT NULL,
  source_stack jsonb NOT NULL,
  target_stack jsonb NOT NULL,
  case_signature_sha256 text NOT NULL CHECK (core.sha256_is_valid(case_signature_sha256)),
  case_artifact_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'eligible' CHECK (status IN ('eligible', 'curated', 'rejected', 'quarantined', 'superseded')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, case_signature_sha256, target_revision_id),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, gate_evaluation_id) REFERENCES verify.gate_evaluation(tenant_id, id),
  FOREIGN KEY (tenant_id, data_authorization_id) REFERENCES learning.data_authorization(tenant_id, id),
  FOREIGN KEY (tenant_id, case_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE learning.repair_trace (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  repair_attempt_id uuid NOT NULL,
  data_authorization_id uuid NOT NULL,
  failure_signature_sha256 text NOT NULL CHECK (core.sha256_is_valid(failure_signature_sha256)),
  before_target_revision_id uuid NOT NULL,
  after_target_revision_id uuid NOT NULL,
  verification_execution_id uuid NOT NULL,
  trace_artifact_id uuid NOT NULL,
  outcome text NOT NULL CHECK (outcome IN ('verified_success', 'verified_failure', 'reverted', 'ambiguous')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, repair_attempt_id),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, repair_attempt_id) REFERENCES verify.repair_attempt(tenant_id, id),
  FOREIGN KEY (tenant_id, data_authorization_id) REFERENCES learning.data_authorization(tenant_id, id),
  FOREIGN KEY (tenant_id, before_target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, after_target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, verification_execution_id) REFERENCES verify.verification_execution(tenant_id, id),
  FOREIGN KEY (tenant_id, trace_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE learning.rule_candidate (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  rule_key text NOT NULL,
  candidate_version integer NOT NULL CHECK (candidate_version > 0),
  rule_kind text NOT NULL CHECK (rule_kind IN ('semantic_mapping', 'framework_mapping', 'project_pattern', 'gap_detection', 'repair', 'verification', 'routing')),
  source_pattern jsonb NOT NULL,
  applicability_contract jsonb NOT NULL,
  transformation_contract jsonb NOT NULL,
  verification_contract jsonb NOT NULL,
  candidate_sha256 text NOT NULL CHECK (core.sha256_is_valid(candidate_sha256)),
  source_case_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  stage text NOT NULL DEFAULT 'experimental' CHECK (stage IN ('experimental', 'candidate', 'validated', 'trusted', 'certified', 'deprecated', 'revoked')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, rule_key, candidate_version),
  UNIQUE (tenant_id, id)
);

CREATE TABLE learning.rule_validation (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  rule_candidate_id uuid NOT NULL,
  validation_kind text NOT NULL CHECK (validation_kind IN ('positive', 'negative', 'boundary', 'cross_project', 'cross_version', 'regression', 'security')),
  benchmark_run_id uuid,
  sample_count integer NOT NULL CHECK (sample_count > 0),
  passed_count integer NOT NULL CHECK (passed_count >= 0),
  failed_count integer NOT NULL CHECK (failed_count >= 0),
  status text NOT NULL CHECK (status IN ('passed', 'failed', 'inconclusive', 'invalid')),
  result_artifact_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, rule_candidate_id) REFERENCES learning.rule_candidate(tenant_id, id),
  FOREIGN KEY (tenant_id, result_artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  CHECK (passed_count + failed_count <= sample_count)
);

CREATE TABLE learning.rule_release (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  rule_candidate_id uuid NOT NULL,
  release_version text NOT NULL,
  release_stage text NOT NULL CHECK (release_stage IN ('validated', 'trusted', 'certified', 'deprecated', 'revoked')),
  compatibility_contract jsonb NOT NULL,
  known_exceptions jsonb NOT NULL DEFAULT '[]'::jsonb,
  release_artifact_id uuid NOT NULL,
  release_sha256 text NOT NULL CHECK (core.sha256_is_valid(release_sha256)),
  approved_by text NOT NULL,
  released_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  revoked_at timestamptz,
  UNIQUE (tenant_id, rule_candidate_id, release_version),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, rule_candidate_id) REFERENCES learning.rule_candidate(tenant_id, id),
  FOREIGN KEY (tenant_id, release_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE learning.benchmark_suite (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  suite_key text NOT NULL,
  version text NOT NULL,
  domain text NOT NULL,
  manifest_artifact_id uuid NOT NULL,
  manifest_sha256 text NOT NULL CHECK (core.sha256_is_valid(manifest_sha256)),
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('draft', 'active', 'deprecated', 'retired')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, suite_key, version),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, manifest_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE learning.benchmark_run (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  benchmark_suite_id uuid NOT NULL,
  subject_kind text NOT NULL CHECK (subject_kind IN ('release', 'model_route', 'harness', 'rule_release', 'ir_version', 'complete_system')),
  subject_reference jsonb NOT NULL,
  environment_revision_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled', 'invalid')),
  started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  ended_at timestamptz,
  result_artifact_id uuid,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, benchmark_suite_id) REFERENCES learning.benchmark_suite(tenant_id, id),
  FOREIGN KEY (tenant_id, environment_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, result_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE learning.benchmark_result (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  benchmark_run_id uuid NOT NULL,
  case_key text NOT NULL,
  metric_name text NOT NULL,
  metric_value numeric(30,9) NOT NULL,
  metric_unit text NOT NULL,
  pass boolean,
  detail_artifact_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, benchmark_run_id, case_key, metric_name),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, benchmark_run_id) REFERENCES learning.benchmark_run(tenant_id, id),
  FOREIGN KEY (tenant_id, detail_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TRIGGER benchmark_result_immutable
BEFORE UPDATE OR DELETE ON learning.benchmark_result
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE ops.release (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  release_key text NOT NULL,
  version text NOT NULL,
  git_sha text NOT NULL,
  image_manifest_artifact_id uuid NOT NULL,
  sbom_artifact_id uuid,
  signature_artifact_id uuid,
  database_schema_version text NOT NULL,
  contract_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'approved', 'deployed', 'rejected', 'superseded', 'revoked')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  approved_at timestamptz,
  UNIQUE (tenant_id, release_key, version),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, image_manifest_artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  FOREIGN KEY (tenant_id, sbom_artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  FOREIGN KEY (tenant_id, signature_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE ops.release_component (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  release_id uuid NOT NULL,
  component_key text NOT NULL,
  component_kind text NOT NULL CHECK (component_kind IN ('service', 'worker', 'migration', 'web', 'job', 'sidecar')),
  image_repository text,
  image_digest text,
  version_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  livez_path text,
  readyz_path text,
  metrics_path text,
  version_path text,
  required boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, release_id, component_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, release_id) REFERENCES ops.release(tenant_id, id),
  CHECK (component_kind = 'migration' OR image_digest IS NOT NULL)
);

CREATE TABLE ops.deployment (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  release_id uuid NOT NULL,
  environment text NOT NULL,
  region text,
  cluster text,
  namespace text,
  deployment_no integer NOT NULL CHECK (deployment_no > 0),
  status text NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'migrating', 'deploying', 'verifying', 'healthy', 'failed', 'rolled_back', 'cancelled')),
  deployment_manifest_artifact_id uuid,
  started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  completed_at timestamptz,
  rollback_of_deployment_id uuid,
  UNIQUE (tenant_id, environment, deployment_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, release_id) REFERENCES ops.release(tenant_id, id),
  FOREIGN KEY (tenant_id, deployment_manifest_artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  FOREIGN KEY (tenant_id, rollback_of_deployment_id) REFERENCES ops.deployment(tenant_id, id)
);

CREATE TABLE ops.migration_run (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  deployment_id uuid NOT NULL,
  migration_tool text NOT NULL,
  from_schema_version text,
  to_schema_version text NOT NULL,
  migration_manifest_sha256 text NOT NULL CHECK (core.sha256_is_valid(migration_manifest_sha256)),
  status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'succeeded', 'failed', 'rolled_back', 'not_required')),
  output_artifact_id uuid,
  started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  ended_at timestamptz,
  UNIQUE (tenant_id, deployment_id, to_schema_version),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, deployment_id) REFERENCES ops.deployment(tenant_id, id),
  FOREIGN KEY (tenant_id, output_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE ops.service_health_snapshot (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  deployment_id uuid NOT NULL,
  release_component_id uuid NOT NULL,
  service_name text NOT NULL,
  image_digest text NOT NULL,
  livez boolean NOT NULL,
  readyz boolean NOT NULL,
  version_payload jsonb NOT NULL,
  metrics_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  replica_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, deployment_id, service_name, observed_at),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, deployment_id) REFERENCES ops.deployment(tenant_id, id),
  FOREIGN KEY (tenant_id, release_component_id) REFERENCES ops.release_component(tenant_id, id)
);

CREATE TRIGGER service_health_snapshot_immutable
BEFORE UPDATE OR DELETE ON ops.service_health_snapshot
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE ops.deployment_check (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  deployment_id uuid NOT NULL,
  check_key text NOT NULL,
  check_kind text NOT NULL CHECK (check_kind IN ('image', 'signature', 'sbom', 'migration', 'health', 'metrics', 'smoke', 'security', 'rollback', 'p05')),
  status text NOT NULL CHECK (status IN ('passed', 'failed', 'warning', 'blocked', 'not_run')),
  evidence_artifact_id uuid,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, deployment_id, check_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, deployment_id) REFERENCES ops.deployment(tenant_id, id),
  FOREIGN KEY (tenant_id, evidence_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE ops.deployment_gate (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  deployment_id uuid NOT NULL,
  gate_policy_revision_id uuid NOT NULL,
  release_id uuid NOT NULL,
  migration_run_id uuid,
  decision text NOT NULL CHECK (decision IN ('pass', 'fail', 'blocked', 'error')),
  required_check_count integer NOT NULL CHECK (required_check_count >= 0),
  passed_check_count integer NOT NULL CHECK (passed_check_count >= 0),
  failed_check_count integer NOT NULL CHECK (failed_check_count >= 0),
  evaluation_summary jsonb NOT NULL,
  evaluator_version text NOT NULL,
  evaluated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, deployment_id, evaluated_at),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, deployment_id) REFERENCES ops.deployment(tenant_id, id),
  FOREIGN KEY (tenant_id, gate_policy_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, release_id) REFERENCES ops.release(tenant_id, id),
  FOREIGN KEY (tenant_id, migration_run_id) REFERENCES ops.migration_run(tenant_id, id),
  CHECK (passed_check_count + failed_check_count <= required_check_count)
);

CREATE TRIGGER deployment_gate_immutable
BEFORE UPDATE OR DELETE ON ops.deployment_gate
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE audit.audit_event (
  tenant_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT extensions.gen_random_uuid(),
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  actor_kind text NOT NULL CHECK (actor_kind IN ('user', 'service', 'agent', 'worker', 'operator', 'integration', 'policy')),
  actor_id text,
  action text NOT NULL,
  subject_kind text NOT NULL,
  subject_id uuid,
  request_id text,
  run_id uuid,
  source_ip inet,
  outcome text NOT NULL CHECK (outcome IN ('success', 'failure', 'denied', 'unknown')),
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  previous_event_hash text,
  event_hash text NOT NULL CHECK (core.sha256_is_valid(event_hash)),
  PRIMARY KEY (tenant_id, id),
  CHECK (previous_event_hash IS NULL OR core.sha256_is_valid(previous_event_hash))
) PARTITION BY HASH (tenant_id);

DO $$
DECLARE i integer;
BEGIN
  FOR i IN 0..15 LOOP
    EXECUTE format(
      'CREATE TABLE audit.audit_event_p%s PARTITION OF audit.audit_event FOR VALUES WITH (MODULUS 16, REMAINDER %s)',
      lpad(i::text, 2, '0'), i
    );
  END LOOP;
END $$;

CREATE TRIGGER audit_event_immutable
BEFORE UPDATE OR DELETE ON audit.audit_event
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE INDEX outbox_dispatch_idx ON integration.outbox_event (tenant_id, status, available_at)
  WHERE status IN ('pending', 'failed');
CREATE INDEX side_effect_unresolved_idx ON integration.side_effect_receipt (tenant_id, run_id, status, updated_at)
  WHERE status IN ('reserved', 'dispatching', 'unknown_result', 'reconciling', 'compensating');
CREATE INDEX reconciliation_issue_open_idx ON integration.reconciliation_issue (tenant_id, status, severity, created_at)
  WHERE status IN ('open', 'repairing', 'failed', 'manual');
CREATE INDEX learning_rule_stage_idx ON learning.rule_candidate (tenant_id, stage, rule_kind, created_at DESC);
CREATE INDEX benchmark_result_metric_idx ON learning.benchmark_result (tenant_id, metric_name, created_at DESC);
CREATE INDEX deployment_status_idx ON ops.deployment (tenant_id, environment, status, started_at DESC);
CREATE INDEX audit_event_subject_idx ON audit.audit_event (tenant_id, subject_kind, subject_id, occurred_at DESC);
CREATE INDEX audit_event_run_idx ON audit.audit_event (tenant_id, run_id, occurred_at DESC) WHERE run_id IS NOT NULL;

COMMIT;
