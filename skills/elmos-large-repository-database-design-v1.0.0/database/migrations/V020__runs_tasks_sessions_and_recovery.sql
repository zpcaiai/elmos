-- Durable execution state for very large repositories: runs, stages, DAG tasks,
-- attempts, leases/fencing, workspaces, ordered event journals, sessions,
-- workpads, approvals, control requests and recovery actions.

BEGIN;

CREATE TABLE exec.run (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  job_id uuid NOT NULL,
  account_id uuid NOT NULL,
  run_no integer NOT NULL CHECK (run_no > 0),
  run_kind text NOT NULL
    CHECK (run_kind IN ('project_generation', 'repository_conversion', 'analysis', 'verification', 'repair', 'deployment')),
  status text NOT NULL DEFAULT 'created'
    CHECK (status IN (
      'created', 'admitting', 'admission_wait', 'planning', 'ready', 'running', 'pause_requested',
      'paused', 'resume_requested', 'cancel_requested', 'cancelling',
      'verifying', 'repairing', 'human_review', 'releasing', 'completed',
      'failed', 'cancelled', 'blocked', 'archived'
    )),
  execution_epoch integer NOT NULL DEFAULT 1 CHECK (execution_epoch > 0),
  temporal_namespace text,
  temporal_workflow_id text,
  temporal_run_id text,
  current_stage_key text,
  progress_basis_points integer NOT NULL DEFAULT 0 CHECK (progress_basis_points BETWEEN 0 AND 10000),
  source_repository_revision_id uuid,
  baseline_repository_revision_id uuid,
  target_repository_revision_id uuid,
  requirements_revision_id uuid,
  policy_revision_id uuid NOT NULL,
  workflow_revision_id uuid NOT NULL,
  model_route_revision_id uuid NOT NULL,
  toolchain_revision_id uuid NOT NULL,
  environment_revision_id uuid NOT NULL,
  archetype_revision_id uuid,
  input_bundle_sha256 text NOT NULL CHECK (core.sha256_is_valid(input_bundle_sha256)),
  current_target_revision_id uuid,
  completion_gate_evaluation_id uuid,
  slot_no smallint CHECK (slot_no BETWEEN 1 AND 3),
  slot_lease_generation bigint CHECK (slot_lease_generation IS NULL OR slot_lease_generation >= 0),
  cancellation_reason text,
  failure_code text,
  failure_summary text,
  started_at timestamptz,
  last_progress_at timestamptz,
  paused_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, job_id, run_no),
  UNIQUE (tenant_id, id),
  UNIQUE NULLS NOT DISTINCT (tenant_id, temporal_namespace, temporal_workflow_id, temporal_run_id),
  FOREIGN KEY (tenant_id, job_id) REFERENCES core.job(tenant_id, id),
  FOREIGN KEY (tenant_id, account_id) REFERENCES core.account(tenant_id, id),
  FOREIGN KEY (tenant_id, source_repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, baseline_repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, target_repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, requirements_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, policy_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, workflow_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, model_route_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, toolchain_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, environment_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, archetype_revision_id) REFERENCES core.revision_snapshot(tenant_id, id)
);

CREATE TRIGGER run_touch_updated_at
BEFORE UPDATE ON exec.run
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE exec.run_attempt (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  attempt_no integer NOT NULL CHECK (attempt_no > 0),
  trigger_kind text NOT NULL
    CHECK (trigger_kind IN ('initial', 'retry', 'resume', 'reconciliation', 'operator', 'repair')),
  status text NOT NULL DEFAULT 'starting'
    CHECK (status IN ('starting', 'running', 'succeeded', 'failed', 'cancelled', 'interrupted', 'stalled')),
  temporal_run_id text,
  execution_epoch integer NOT NULL CHECK (execution_epoch > 0),
  resume_checkpoint_id uuid,
  failure_code text,
  failure_detail jsonb,
  started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  ended_at timestamptz,
  UNIQUE (tenant_id, run_id, attempt_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id)
);

CREATE TABLE exec.run_stage (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  stage_key text NOT NULL CHECK (stage_key ~ '^[a-z][a-z0-9_.-]+$'),
  stage_type text NOT NULL
    CHECK (stage_type IN (
      'intake', 'discovery', 'analysis', 'ir_build', 'planning', 'generation',
      'transformation', 'build', 'verification', 'repair', 'release', 'learning'
    )),
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'ready', 'running', 'paused', 'succeeded', 'failed', 'cancelled', 'blocked', 'skipped')),
  progress_basis_points integer NOT NULL DEFAULT 0 CHECK (progress_basis_points BETWEEN 0 AND 10000),
  task_count integer NOT NULL DEFAULT 0 CHECK (task_count >= 0),
  completed_task_count integer NOT NULL DEFAULT 0 CHECK (completed_task_count >= 0),
  started_at timestamptz,
  ended_at timestamptz,
  summary jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (core.json_object_or_empty(summary)),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, run_id, stage_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id)
);

CREATE TRIGGER run_stage_touch_updated_at
BEFORE UPDATE ON exec.run_stage
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE exec.task (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  stage_id uuid NOT NULL,
  task_key text NOT NULL CHECK (task_key ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]*$'),
  task_type text NOT NULL,
  title text NOT NULL,
  description text,
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN (
      'pending', 'ready', 'claimed', 'running', 'waiting_async', 'waiting_human',
      'pause_requested', 'paused', 'succeeded', 'failed', 'cancelled',
      'blocked', 'skipped', 'superseded'
    )),
  criticality text NOT NULL DEFAULT 'normal'
    CHECK (criticality IN ('low', 'normal', 'high', 'critical')),
  shard_key text,
  concurrency_group text,
  resource_class text NOT NULL DEFAULT 'standard',
  idempotency_key text NOT NULL,
  input_sha256 text NOT NULL CHECK (core.sha256_is_valid(input_sha256)),
  expected_output_contract jsonb NOT NULL DEFAULT '{}'::jsonb,
  skill_name text,
  preferred_agent_role text,
  preferred_model_route text,
  max_attempts smallint NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 20),
  retry_policy jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (core.json_object_or_empty(retry_policy)),
  timeout_ms bigint CHECK (timeout_ms IS NULL OR timeout_ms > 0),
  not_before timestamptz,
  priority smallint NOT NULL DEFAULT 50 CHECK (priority BETWEEN 0 AND 100),
  current_attempt_id uuid,
  last_checkpoint_id uuid,
  output_manifest_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  started_at timestamptz,
  ended_at timestamptz,
  UNIQUE (tenant_id, run_id, task_key),
  UNIQUE (tenant_id, run_id, idempotency_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, stage_id) REFERENCES exec.run_stage(tenant_id, id)
);

CREATE TRIGGER task_touch_updated_at
BEFORE UPDATE ON exec.task
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE exec.task_dependency (
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL,
  task_id uuid NOT NULL,
  depends_on_task_id uuid NOT NULL,
  dependency_kind text NOT NULL DEFAULT 'success'
    CHECK (dependency_kind IN ('success', 'completion', 'artifact', 'evidence', 'soft')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, task_id, depends_on_task_id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id),
  FOREIGN KEY (tenant_id, depends_on_task_id) REFERENCES exec.task(tenant_id, id),
  CHECK (task_id <> depends_on_task_id)
);

CREATE TRIGGER task_dependency_immutable
BEFORE UPDATE OR DELETE ON exec.task_dependency
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE exec.worker_node (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  worker_pool text NOT NULL,
  node_name text NOT NULL,
  platform text NOT NULL CHECK (platform IN ('linux', 'windows', 'macos')),
  architecture text NOT NULL,
  runtime_class text,
  status text NOT NULL DEFAULT 'registering'
    CHECK (status IN ('registering', 'ready', 'busy', 'draining', 'unhealthy', 'offline')),
  capabilities jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (core.json_object_or_empty(capabilities)),
  capacity jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (core.json_object_or_empty(capacity)),
  current_load jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (core.json_object_or_empty(current_load)),
  agent_version text,
  last_heartbeat_at timestamptz,
  registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, worker_pool, node_name),
  UNIQUE (tenant_id, id)
);

CREATE TRIGGER worker_node_touch_updated_at
BEFORE UPDATE ON exec.worker_node
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE exec.workspace (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  task_id uuid,
  workspace_kind text NOT NULL
    CHECK (workspace_kind IN ('run_root', 'worktree', 'sandbox', 'browser', 'build_cache', 'verification')),
  workspace_key text NOT NULL,
  provider text NOT NULL CHECK (provider IN ('local', 'kubernetes', 'remote', 'e2b', 'microvm', 'macos_runner', 'windows_runner')),
  host_ref text,
  local_path text,
  storage_manifest_id uuid,
  base_repository_revision_id uuid,
  state text NOT NULL DEFAULT 'provisioning'
    CHECK (state IN ('provisioning', 'ready', 'in_use', 'checkpointing', 'released', 'quarantined', 'deleted', 'failed')),
  write_scope text NOT NULL DEFAULT 'workspace'
    CHECK (write_scope IN ('read_only', 'workspace', 'danger_full_access')),
  network_policy text NOT NULL DEFAULT 'deny'
    CHECK (network_policy IN ('deny', 'egress_proxy', 'allowlist', 'full')),
  sandbox_enforcement text CHECK (sandbox_enforcement IS NULL OR sandbox_enforcement IN ('full', 'partial', 'none')),
  lease_generation bigint NOT NULL DEFAULT 0 CHECK (lease_generation >= 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  released_at timestamptz,
  UNIQUE (tenant_id, run_id, workspace_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id),
  FOREIGN KEY (tenant_id, base_repository_revision_id) REFERENCES core.repository_revision(tenant_id, id)
);

CREATE TRIGGER workspace_touch_updated_at
BEFORE UPDATE ON exec.workspace
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE exec.task_attempt (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  task_id uuid NOT NULL,
  attempt_no smallint NOT NULL CHECK (attempt_no > 0),
  run_attempt_id uuid,
  status text NOT NULL DEFAULT 'created'
    CHECK (status IN (
      'created', 'claimed', 'starting', 'running', 'waiting_async', 'waiting_human',
      'succeeded', 'failed', 'timed_out', 'stalled', 'cancelled', 'interrupted', 'lost'
    )),
  worker_node_id uuid,
  workspace_id uuid,
  model_route_revision_id uuid,
  toolchain_revision_id uuid,
  execution_environment_sha256 text CHECK (core.sha256_is_valid(execution_environment_sha256)),
  lease_generation bigint NOT NULL DEFAULT 0 CHECK (lease_generation >= 0),
  fencing_token uuid NOT NULL DEFAULT extensions.gen_random_uuid(),
  input_manifest_id uuid,
  output_manifest_id uuid,
  checkpoint_id uuid,
  exit_code integer,
  failure_class text,
  failure_code text,
  failure_detail jsonb,
  claimed_at timestamptz,
  started_at timestamptz,
  last_heartbeat_at timestamptz,
  ended_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, task_id, attempt_no),
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, fencing_token),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id),
  FOREIGN KEY (tenant_id, run_attempt_id) REFERENCES exec.run_attempt(tenant_id, id),
  FOREIGN KEY (tenant_id, workspace_id) REFERENCES exec.workspace(tenant_id, id),
  FOREIGN KEY (tenant_id, worker_node_id) REFERENCES exec.worker_node(tenant_id, id),
  FOREIGN KEY (tenant_id, model_route_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, toolchain_revision_id) REFERENCES core.revision_snapshot(tenant_id, id)
);

CREATE TABLE exec.execution_lease (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  resource_kind text NOT NULL CHECK (resource_kind IN ('run', 'task', 'workspace', 'side_effect', 'gate')),
  resource_id uuid NOT NULL,
  holder_kind text NOT NULL CHECK (holder_kind IN ('scheduler', 'worker', 'verifier', 'reconciler', 'operator')),
  holder_id text NOT NULL,
  lease_token uuid NOT NULL DEFAULT extensions.gen_random_uuid(),
  lease_generation bigint NOT NULL CHECK (lease_generation > 0),
  acquired_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  renewed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz NOT NULL,
  released_at timestamptz,
  release_reason text,
  UNIQUE (tenant_id, resource_kind, resource_id, lease_generation),
  UNIQUE (tenant_id, lease_token),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  CHECK (expires_at > acquired_at)
);

CREATE TABLE exec.run_event_cursor (
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL,
  next_seq bigint NOT NULL DEFAULT 1 CHECK (next_seq > 0),
  last_event_hash text,
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, run_id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  CHECK (last_event_hash IS NULL OR core.sha256_is_valid(last_event_hash))
);

CREATE TABLE exec.run_event (
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL,
  seq bigint NOT NULL CHECK (seq > 0),
  event_id uuid NOT NULL DEFAULT extensions.gen_random_uuid(),
  event_type text NOT NULL CHECK (event_type ~ '^[a-z][a-z0-9_.-]+$'),
  event_version smallint NOT NULL DEFAULT 1 CHECK (event_version > 0),
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  actor_kind text NOT NULL CHECK (actor_kind IN ('system', 'scheduler', 'worker', 'agent', 'user', 'integration', 'reconciler')),
  actor_id text,
  task_id uuid,
  task_attempt_id uuid,
  correlation_id text,
  causation_event_id uuid,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  previous_event_hash text,
  event_hash text NOT NULL CHECK (core.sha256_is_valid(event_hash)),
  PRIMARY KEY (tenant_id, run_id, seq),
  UNIQUE (tenant_id, event_id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id),
  FOREIGN KEY (tenant_id, task_attempt_id) REFERENCES exec.task_attempt(tenant_id, id),
  CHECK (previous_event_hash IS NULL OR core.sha256_is_valid(previous_event_hash))
) PARTITION BY HASH (run_id);

DO $$
DECLARE i integer;
BEGIN
  FOR i IN 0..15 LOOP
    EXECUTE format(
      'CREATE TABLE exec.run_event_p%s PARTITION OF exec.run_event FOR VALUES WITH (MODULUS 16, REMAINDER %s)',
      lpad(i::text, 2, '0'), i
    );
  END LOOP;
END $$;

CREATE TRIGGER run_event_immutable
BEFORE UPDATE OR DELETE ON exec.run_event
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE exec.run_progress_snapshot (
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL,
  status text NOT NULL,
  current_stage_key text,
  progress_basis_points integer NOT NULL CHECK (progress_basis_points BETWEEN 0 AND 10000),
  total_tasks integer NOT NULL DEFAULT 0 CHECK (total_tasks >= 0),
  pending_tasks integer NOT NULL DEFAULT 0 CHECK (pending_tasks >= 0),
  running_tasks integer NOT NULL DEFAULT 0 CHECK (running_tasks >= 0),
  succeeded_tasks integer NOT NULL DEFAULT 0 CHECK (succeeded_tasks >= 0),
  failed_tasks integer NOT NULL DEFAULT 0 CHECK (failed_tasks >= 0),
  blocked_tasks integer NOT NULL DEFAULT 0 CHECK (blocked_tasks >= 0),
  last_event_seq bigint NOT NULL DEFAULT 0 CHECK (last_event_seq >= 0),
  last_event_type text,
  last_progress_message text,
  estimated_machine_seconds_remaining bigint,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, run_id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id)
);

CREATE TABLE exec.session (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  task_id uuid,
  parent_session_id uuid,
  session_kind text NOT NULL
    CHECK (session_kind IN ('primary', 'subagent', 'reviewer', 'verifier', 'repair', 'auditor', 'human')),
  agent_role text NOT NULL,
  harness_provider text NOT NULL,
  provider_session_id text,
  status text NOT NULL DEFAULT 'created'
    CHECK (status IN ('created', 'active', 'idle', 'waiting', 'compacting', 'completed', 'failed', 'cancelled', 'interrupted')),
  delegation_depth smallint NOT NULL DEFAULT 0 CHECK (delegation_depth BETWEEN 0 AND 16),
  model_route_revision_id uuid NOT NULL,
  toolset_sha256 text NOT NULL CHECK (core.sha256_is_valid(toolset_sha256)),
  system_context_sha256 text CHECK (core.sha256_is_valid(system_context_sha256)),
  current_context_epoch_no integer NOT NULL DEFAULT 1 CHECK (current_context_epoch_no > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  last_activity_at timestamptz,
  ended_at timestamptz,
  UNIQUE NULLS NOT DISTINCT (tenant_id, harness_provider, provider_session_id),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id),
  FOREIGN KEY (tenant_id, parent_session_id) REFERENCES exec.session(tenant_id, id),
  FOREIGN KEY (tenant_id, model_route_revision_id) REFERENCES core.revision_snapshot(tenant_id, id)
);

CREATE TABLE exec.session_event_cursor (
  tenant_id uuid NOT NULL,
  session_id uuid NOT NULL,
  next_seq bigint NOT NULL DEFAULT 1 CHECK (next_seq > 0),
  last_event_hash text,
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, session_id),
  FOREIGN KEY (tenant_id, session_id) REFERENCES exec.session(tenant_id, id),
  CHECK (last_event_hash IS NULL OR core.sha256_is_valid(last_event_hash))
);

CREATE TABLE exec.session_event (
  tenant_id uuid NOT NULL,
  session_id uuid NOT NULL,
  run_id uuid NOT NULL,
  seq bigint NOT NULL CHECK (seq > 0),
  event_id uuid NOT NULL DEFAULT extensions.gen_random_uuid(),
  event_type text NOT NULL CHECK (event_type ~ '^[a-z][a-z0-9_./-]+$'),
  turn_no integer,
  step_no integer,
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  model_visible boolean NOT NULL DEFAULT false,
  ignorable boolean NOT NULL DEFAULT false,
  payload jsonb NOT NULL,
  artifact_id uuid,
  previous_event_hash text,
  event_hash text NOT NULL CHECK (core.sha256_is_valid(event_hash)),
  PRIMARY KEY (tenant_id, session_id, seq),
  UNIQUE (tenant_id, event_id),
  FOREIGN KEY (tenant_id, session_id) REFERENCES exec.session(tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  CHECK (previous_event_hash IS NULL OR core.sha256_is_valid(previous_event_hash))
) PARTITION BY HASH (session_id);

DO $$
DECLARE i integer;
BEGIN
  FOR i IN 0..15 LOOP
    EXECUTE format(
      'CREATE TABLE exec.session_event_p%s PARTITION OF exec.session_event FOR VALUES WITH (MODULUS 16, REMAINDER %s)',
      lpad(i::text, 2, '0'), i
    );
  END LOOP;
END $$;

CREATE TRIGGER session_event_immutable
BEFORE UPDATE OR DELETE ON exec.session_event
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE exec.context_epoch (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  session_id uuid NOT NULL,
  epoch_no integer NOT NULL CHECK (epoch_no > 0),
  baseline_system_context_sha256 text NOT NULL CHECK (core.sha256_is_valid(baseline_system_context_sha256)),
  baseline_artifact_id uuid,
  context_snapshot jsonb NOT NULL,
  tool_schema_sha256 text NOT NULL CHECK (core.sha256_is_valid(tool_schema_sha256)),
  model_route_revision_id uuid NOT NULL,
  reason text NOT NULL CHECK (reason IN ('initial', 'compaction', 'move', 'incompatible_context_change', 'resume')),
  started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  ended_at timestamptz,
  UNIQUE (tenant_id, session_id, epoch_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, session_id) REFERENCES exec.session(tenant_id, id),
  FOREIGN KEY (tenant_id, model_route_revision_id) REFERENCES core.revision_snapshot(tenant_id, id)
);

CREATE TABLE exec.workpad (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  task_id uuid,
  workpad_kind text NOT NULL CHECK (workpad_kind IN ('run', 'stage', 'task', 'review', 'repair', 'release')),
  title text NOT NULL,
  revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'closed')),
  document jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE NULLS NOT DISTINCT (tenant_id, run_id, task_id, workpad_kind, status),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id)
);

CREATE TRIGGER workpad_touch_updated_at
BEFORE UPDATE ON exec.workpad
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE exec.workpad_item (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  workpad_id uuid NOT NULL,
  parent_item_id uuid,
  item_key text NOT NULL,
  item_type text NOT NULL CHECK (item_type IN ('plan', 'acceptance', 'validation', 'risk', 'decision', 'note', 'blocker')),
  content text NOT NULL,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'blocked', 'waived', 'superseded')),
  ordinal integer NOT NULL DEFAULT 0 CHECK (ordinal >= 0),
  evidence_reference jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, workpad_id, item_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, workpad_id) REFERENCES exec.workpad(tenant_id, id),
  FOREIGN KEY (tenant_id, parent_item_id) REFERENCES exec.workpad_item(tenant_id, id)
);

CREATE TRIGGER workpad_item_touch_updated_at
BEFORE UPDATE ON exec.workpad_item
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE exec.approval_request (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  task_id uuid,
  session_id uuid,
  action text NOT NULL,
  resources jsonb NOT NULL,
  risk_level text NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
  reason text,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'allowed_once', 'allowed_policy', 'rejected', 'cancelled', 'expired', 'unavailable')),
  requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz,
  resolved_at timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id),
  FOREIGN KEY (tenant_id, session_id) REFERENCES exec.session(tenant_id, id)
);

CREATE TABLE exec.approval_decision (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  approval_request_id uuid NOT NULL,
  decision text NOT NULL CHECK (decision IN ('allow_once', 'allow_policy', 'reject', 'cancel')),
  decided_by_kind text NOT NULL CHECK (decided_by_kind IN ('user', 'policy', 'operator', 'automation')),
  decided_by text,
  rationale text,
  policy_patch jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, approval_request_id),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, approval_request_id) REFERENCES exec.approval_request(tenant_id, id)
);

CREATE TRIGGER approval_decision_immutable
BEFORE UPDATE OR DELETE ON exec.approval_decision
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE exec.human_gate (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  task_id uuid,
  gate_kind text NOT NULL CHECK (gate_kind IN ('clarification', 'design_review', 'security_review', 'release_review', 'semantic_gap', 'external_access')),
  question text NOT NULL,
  context_artifact_id uuid,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'answered', 'cancelled', 'expired', 'superseded')),
  answer jsonb,
  opened_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  answered_at timestamptz,
  answered_by text,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id)
);

CREATE TABLE exec.run_control_request (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  command text NOT NULL CHECK (command IN ('pause', 'resume', 'cancel', 'retry', 'reconcile', 'archive')),
  idempotency_key text NOT NULL,
  requested_by text NOT NULL,
  reason text,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'applied', 'rejected', 'failed')),
  requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  applied_at timestamptz,
  result jsonb,
  UNIQUE (tenant_id, run_id, idempotency_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id)
);

CREATE TABLE exec.recovery_action (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  task_id uuid,
  action_kind text NOT NULL
    CHECK (action_kind IN ('reclaim_slot', 'expire_lease', 'resume_checkpoint', 'requeue_task', 'mark_lost', 'reconcile_side_effect', 'repair_event_tail', 'operator_override')),
  trigger_kind text NOT NULL CHECK (trigger_kind IN ('startup', 'timer', 'heartbeat', 'operator', 'reconciliation', 'workflow')),
  status text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'running', 'succeeded', 'failed', 'skipped')),
  idempotency_key text NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  started_at timestamptz,
  ended_at timestamptz,
  UNIQUE (tenant_id, run_id, idempotency_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id)
);

-- Initialize the authoritative cursor/progress rows transactionally with each run/session.
CREATE OR REPLACE FUNCTION exec.initialize_run_records()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO exec.run_event_cursor (tenant_id, run_id) VALUES (NEW.tenant_id, NEW.id);
  INSERT INTO exec.run_progress_snapshot (
    tenant_id, run_id, status, current_stage_key, progress_basis_points
  ) VALUES (
    NEW.tenant_id, NEW.id, NEW.status, NEW.current_stage_key, NEW.progress_basis_points
  );
  RETURN NEW;
END;
$$;

CREATE TRIGGER initialize_run_records
AFTER INSERT ON exec.run
FOR EACH ROW EXECUTE FUNCTION exec.initialize_run_records();

CREATE OR REPLACE FUNCTION exec.initialize_session_cursor()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO exec.session_event_cursor (tenant_id, session_id) VALUES (NEW.tenant_id, NEW.id);
  RETURN NEW;
END;
$$;

CREATE TRIGGER initialize_session_cursor
AFTER INSERT ON exec.session
FOR EACH ROW EXECUTE FUNCTION exec.initialize_session_cursor();

CREATE INDEX run_job_history_idx ON exec.run (tenant_id, job_id, run_no DESC);
CREATE INDEX run_status_activity_idx ON exec.run (tenant_id, status, last_progress_at)
  WHERE status NOT IN ('completed', 'failed', 'cancelled', 'archived');
CREATE INDEX stage_run_ordinal_idx ON exec.run_stage (tenant_id, run_id, ordinal);
CREATE INDEX task_ready_queue_idx ON exec.task (tenant_id, status, priority DESC, not_before, created_at)
  WHERE status IN ('pending', 'ready');
CREATE INDEX task_run_stage_idx ON exec.task (tenant_id, run_id, stage_id, status);
CREATE INDEX task_dependency_reverse_idx ON exec.task_dependency (tenant_id, depends_on_task_id);
CREATE INDEX attempt_heartbeat_idx ON exec.task_attempt (tenant_id, status, last_heartbeat_at)
  WHERE status IN ('claimed', 'starting', 'running', 'waiting_async');
CREATE INDEX lease_expiry_idx ON exec.execution_lease (tenant_id, expires_at)
  WHERE released_at IS NULL;
CREATE UNIQUE INDEX execution_lease_one_active_idx
  ON exec.execution_lease (tenant_id, resource_kind, resource_id)
  WHERE released_at IS NULL;
CREATE INDEX workspace_run_state_idx ON exec.workspace (tenant_id, run_id, state);
CREATE INDEX run_event_type_idx ON exec.run_event (tenant_id, run_id, event_type, seq DESC);
CREATE INDEX session_event_run_idx ON exec.session_event (tenant_id, run_id, occurred_at DESC);
CREATE INDEX open_human_gate_idx ON exec.human_gate (tenant_id, run_id, opened_at)
  WHERE status = 'open';

COMMIT;
