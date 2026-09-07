-- Meter every model/tool/resource round, keep immutable financial ledgers,
-- report autonomous machine ETA separately from human-equivalent effort,
-- and persist deterministic cache/checkpoint reuse evidence.

BEGIN;

CREATE TABLE metering.price_snapshot (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  provider text NOT NULL,
  model text,
  meter_kind text NOT NULL
    CHECK (meter_kind IN ('input_token', 'output_token', 'cached_token', 'reasoning_token', 'request', 'tool', 'cpu_second', 'gpu_second', 'memory_gb_second', 'storage_gb_month', 'network_gb')),
  unit_price_microunits bigint NOT NULL CHECK (unit_price_microunits >= 0),
  unit_scale bigint NOT NULL DEFAULT 1 CHECK (unit_scale > 0),
  currency char(3) NOT NULL DEFAULT 'USD',
  effective_from timestamptz NOT NULL,
  effective_to timestamptz,
  source_artifact_id uuid,
  source_sha256 text CHECK (core.sha256_is_valid(source_sha256)),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE NULLS NOT DISTINCT (tenant_id, provider, model, meter_kind, effective_from),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, source_artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE TRIGGER price_snapshot_immutable
BEFORE UPDATE OR DELETE ON metering.price_snapshot
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE metering.budget_reservation (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  account_id uuid NOT NULL,
  run_id uuid NOT NULL,
  reservation_kind text NOT NULL CHECK (reservation_kind IN ('run', 'stage', 'task', 'model_call', 'deployment')),
  reserved_microunits bigint NOT NULL CHECK (reserved_microunits >= 0),
  consumed_microunits bigint NOT NULL DEFAULT 0 CHECK (consumed_microunits >= 0),
  currency char(3) NOT NULL DEFAULT 'USD',
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'consumed', 'released', 'expired', 'exceeded')),
  idempotency_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz,
  released_at timestamptz,
  UNIQUE (tenant_id, account_id, idempotency_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, account_id) REFERENCES core.account(tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  CHECK (consumed_microunits <= reserved_microunits OR status = 'exceeded')
);

CREATE TABLE metering.model_invocation (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  task_id uuid,
  task_attempt_id uuid,
  session_id uuid,
  invocation_no bigint NOT NULL CHECK (invocation_no > 0),
  turn_no integer,
  round_kind text NOT NULL CHECK (round_kind IN ('initial', 'tool_followup', 'continuation', 'review', 'repair', 'compaction', 'final_response', 'advisor', 'audit')),
  agent_role text NOT NULL,
  provider text NOT NULL,
  provider_endpoint text,
  model text NOT NULL,
  model_route_revision_id uuid NOT NULL,
  request_sha256 text NOT NULL CHECK (core.sha256_is_valid(request_sha256)),
  response_sha256 text CHECK (core.sha256_is_valid(response_sha256)),
  request_artifact_id uuid,
  response_artifact_id uuid,
  status text NOT NULL CHECK (status IN ('started', 'completed', 'failed', 'timed_out', 'cancelled', 'rate_limited')),
  finish_reason text,
  input_tokens bigint NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
  output_tokens bigint NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
  cached_input_tokens bigint NOT NULL DEFAULT 0 CHECK (cached_input_tokens >= 0),
  reasoning_tokens bigint NOT NULL DEFAULT 0 CHECK (reasoning_tokens >= 0),
  context_window_tokens bigint,
  first_token_latency_ms bigint,
  duration_ms bigint,
  reported_cost_microunits bigint CHECK (reported_cost_microunits IS NULL OR reported_cost_microunits >= 0),
  calculated_cost_microunits bigint CHECK (calculated_cost_microunits IS NULL OR calculated_cost_microunits >= 0),
  price_snapshot_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  retry_of_invocation_id uuid,
  started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  ended_at timestamptz,
  UNIQUE (tenant_id, run_id, invocation_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id),
  FOREIGN KEY (tenant_id, task_attempt_id) REFERENCES exec.task_attempt(tenant_id, id),
  FOREIGN KEY (tenant_id, session_id) REFERENCES exec.session(tenant_id, id),
  FOREIGN KEY (tenant_id, model_route_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  FOREIGN KEY (tenant_id, request_artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  FOREIGN KEY (tenant_id, response_artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  FOREIGN KEY (tenant_id, retry_of_invocation_id) REFERENCES metering.model_invocation(tenant_id, id)
);

CREATE TABLE metering.tool_invocation (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  task_id uuid,
  task_attempt_id uuid,
  session_id uuid,
  model_invocation_id uuid,
  call_id text NOT NULL,
  root_call_id text NOT NULL,
  parent_tool_invocation_id uuid,
  tool_name text NOT NULL,
  tool_version text,
  lifecycle text NOT NULL DEFAULT 'sync' CHECK (lifecycle IN ('sync', 'background', 'deferred', 'manual', 'subagent')),
  execution_mode text NOT NULL DEFAULT 'exclusive' CHECK (execution_mode IN ('exclusive', 'parallel')),
  arguments_sha256 text NOT NULL CHECK (core.sha256_is_valid(arguments_sha256)),
  result_sha256 text CHECK (core.sha256_is_valid(result_sha256)),
  arguments_artifact_id uuid,
  result_artifact_id uuid,
  status text NOT NULL CHECK (status IN ('requested', 'approved', 'running', 'pending', 'completed', 'failed', 'blocked', 'rejected', 'timed_out', 'cancelled', 'unknown_result')),
  approval_request_id uuid,
  task_external_id text,
  timeout_ms bigint,
  duration_ms bigint,
  error_code text,
  error_message text,
  started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  ended_at timestamptz,
  UNIQUE (tenant_id, session_id, call_id),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id),
  FOREIGN KEY (tenant_id, task_attempt_id) REFERENCES exec.task_attempt(tenant_id, id),
  FOREIGN KEY (tenant_id, session_id) REFERENCES exec.session(tenant_id, id),
  FOREIGN KEY (tenant_id, model_invocation_id) REFERENCES metering.model_invocation(tenant_id, id),
  FOREIGN KEY (tenant_id, parent_tool_invocation_id) REFERENCES metering.tool_invocation(tenant_id, id),
  FOREIGN KEY (tenant_id, arguments_artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  FOREIGN KEY (tenant_id, result_artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  FOREIGN KEY (tenant_id, approval_request_id) REFERENCES exec.approval_request(tenant_id, id)
);

CREATE TABLE metering.resource_usage_aggregate (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  task_attempt_id uuid,
  worker_node_id uuid,
  usage_window_start timestamptz NOT NULL,
  usage_window_end timestamptz NOT NULL,
  cpu_milliseconds bigint NOT NULL DEFAULT 0 CHECK (cpu_milliseconds >= 0),
  memory_gb_milliseconds numeric(24,6) NOT NULL DEFAULT 0 CHECK (memory_gb_milliseconds >= 0),
  gpu_milliseconds bigint NOT NULL DEFAULT 0 CHECK (gpu_milliseconds >= 0),
  storage_read_bytes bigint NOT NULL DEFAULT 0 CHECK (storage_read_bytes >= 0),
  storage_write_bytes bigint NOT NULL DEFAULT 0 CHECK (storage_write_bytes >= 0),
  network_ingress_bytes bigint NOT NULL DEFAULT 0 CHECK (network_ingress_bytes >= 0),
  network_egress_bytes bigint NOT NULL DEFAULT 0 CHECK (network_egress_bytes >= 0),
  build_cache_read_bytes bigint NOT NULL DEFAULT 0 CHECK (build_cache_read_bytes >= 0),
  build_cache_write_bytes bigint NOT NULL DEFAULT 0 CHECK (build_cache_write_bytes >= 0),
  sample_count integer NOT NULL DEFAULT 1 CHECK (sample_count > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE NULLS NOT DISTINCT (tenant_id, run_id, task_attempt_id, usage_window_start, usage_window_end),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_attempt_id) REFERENCES exec.task_attempt(tenant_id, id),
  FOREIGN KEY (tenant_id, worker_node_id) REFERENCES exec.worker_node(tenant_id, id),
  CHECK (usage_window_end > usage_window_start)
);

CREATE TABLE metering.usage_ledger (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  account_id uuid NOT NULL,
  meter_kind text NOT NULL,
  quantity numeric(30,9) NOT NULL CHECK (quantity >= 0),
  unit text NOT NULL,
  source_kind text NOT NULL CHECK (source_kind IN ('model_invocation', 'tool_invocation', 'resource_usage', 'storage', 'network', 'manual_adjustment')),
  source_id uuid,
  idempotency_key text NOT NULL,
  occurred_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, idempotency_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, account_id) REFERENCES core.account(tenant_id, id)
);

CREATE TRIGGER usage_ledger_immutable
BEFORE UPDATE OR DELETE ON metering.usage_ledger
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE metering.cost_ledger (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  account_id uuid NOT NULL,
  usage_ledger_id uuid,
  cost_category text NOT NULL CHECK (cost_category IN ('model', 'tool', 'compute', 'storage', 'network', 'third_party', 'credit', 'adjustment')),
  amount_microunits bigint NOT NULL,
  currency char(3) NOT NULL DEFAULT 'USD',
  price_snapshot_id uuid,
  idempotency_key text NOT NULL,
  occurred_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, idempotency_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, account_id) REFERENCES core.account(tenant_id, id),
  FOREIGN KEY (tenant_id, usage_ledger_id) REFERENCES metering.usage_ledger(tenant_id, id),
  FOREIGN KEY (tenant_id, price_snapshot_id) REFERENCES metering.price_snapshot(tenant_id, id)
);

CREATE TRIGGER cost_ledger_immutable
BEFORE UPDATE OR DELETE ON metering.cost_ledger
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE metering.revenue_ledger (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid,
  account_id uuid NOT NULL,
  revenue_category text NOT NULL CHECK (revenue_category IN ('project_fee', 'token_markup', 'subscription_allocation', 'support', 'credit', 'refund', 'adjustment')),
  amount_microunits bigint NOT NULL,
  currency char(3) NOT NULL DEFAULT 'USD',
  allocation_method text,
  external_reference text,
  idempotency_key text NOT NULL,
  occurred_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, idempotency_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, account_id) REFERENCES core.account(tenant_id, id)
);

CREATE TRIGGER revenue_ledger_immutable
BEFORE UPDATE OR DELETE ON metering.revenue_ledger
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE metering.eta_forecast (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  task_id uuid,
  forecast_no bigint NOT NULL CHECK (forecast_no > 0),
  forecast_kind text NOT NULL CHECK (forecast_kind IN ('initial', 'progress', 'recovery', 'replan', 'human_gate', 'completion')),
  machine_wall_clock_p50_seconds bigint CHECK (machine_wall_clock_p50_seconds IS NULL OR machine_wall_clock_p50_seconds >= 0),
  machine_wall_clock_p90_seconds bigint CHECK (machine_wall_clock_p90_seconds IS NULL OR machine_wall_clock_p90_seconds >= 0),
  machine_wall_clock_remaining_p50_seconds bigint CHECK (machine_wall_clock_remaining_p50_seconds IS NULL OR machine_wall_clock_remaining_p50_seconds >= 0),
  machine_wall_clock_remaining_p90_seconds bigint CHECK (machine_wall_clock_remaining_p90_seconds IS NULL OR machine_wall_clock_remaining_p90_seconds >= 0),
  human_equivalent_p50_hours numeric(12,3) CHECK (human_equivalent_p50_hours IS NULL OR human_equivalent_p50_hours >= 0),
  human_equivalent_p90_hours numeric(12,3) CHECK (human_equivalent_p90_hours IS NULL OR human_equivalent_p90_hours >= 0),
  expected_hitl_wait_seconds bigint NOT NULL DEFAULT 0 CHECK (expected_hitl_wait_seconds >= 0),
  estimated_cost_p50_microunits bigint CHECK (estimated_cost_p50_microunits IS NULL OR estimated_cost_p50_microunits >= 0),
  estimated_cost_p90_microunits bigint CHECK (estimated_cost_p90_microunits IS NULL OR estimated_cost_p90_microunits >= 0),
  model_version text NOT NULL,
  feature_snapshot jsonb NOT NULL,
  confidence numeric(5,4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  generated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE NULLS NOT DISTINCT (tenant_id, run_id, task_id, forecast_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id)
);

CREATE TRIGGER eta_forecast_immutable
BEFORE UPDATE OR DELETE ON metering.eta_forecast
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE exec.context_compaction (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  session_id uuid NOT NULL,
  context_epoch_no integer NOT NULL CHECK (context_epoch_no > 0),
  trigger_kind text NOT NULL CHECK (trigger_kind IN ('auto', 'manual', 'reactive', 'provider_limit')),
  compaction_kind text NOT NULL CHECK (compaction_kind IN ('micro', 'full', 'session_memory', 'tool_result_prune')),
  before_tokens bigint NOT NULL CHECK (before_tokens >= 0),
  after_tokens bigint NOT NULL CHECK (after_tokens >= 0),
  preserved_task_state_sha256 text NOT NULL CHECK (core.sha256_is_valid(preserved_task_state_sha256)),
  summary_artifact_id uuid,
  status text NOT NULL CHECK (status IN ('completed', 'failed', 'partial')),
  started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  ended_at timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, session_id) REFERENCES exec.session(tenant_id, id),
  FOREIGN KEY (tenant_id, summary_artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  CHECK (after_tokens <= before_tokens OR status <> 'completed')
);

CREATE TABLE cache.cache_entry (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  cache_namespace text NOT NULL,
  cache_key text NOT NULL,
  cache_kind text NOT NULL CHECK (cache_kind IN ('model_prefix', 'model_response', 'repository_scan', 'ast', 'symbol_index', 'graph', 'semantic_ir', 'transformation', 'build', 'test', 'checkpoint', 'artifact')),
  scope_kind text NOT NULL CHECK (scope_kind IN ('tenant', 'project', 'repository', 'revision', 'run', 'task', 'global_public')),
  scope_id uuid,
  input_fingerprint_sha256 text NOT NULL CHECK (core.sha256_is_valid(input_fingerprint_sha256)),
  policy_fingerprint_sha256 text NOT NULL CHECK (core.sha256_is_valid(policy_fingerprint_sha256)),
  toolchain_fingerprint_sha256 text NOT NULL CHECK (core.sha256_is_valid(toolchain_fingerprint_sha256)),
  environment_fingerprint_sha256 text NOT NULL CHECK (core.sha256_is_valid(environment_fingerprint_sha256)),
  artifact_id uuid NOT NULL,
  value_sha256 text NOT NULL CHECK (core.sha256_is_valid(value_sha256)),
  status text NOT NULL DEFAULT 'available' CHECK (status IN ('writing', 'available', 'stale', 'invalidated', 'quarantined', 'deleted')),
  size_bytes bigint NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
  hit_count bigint NOT NULL DEFAULT 0 CHECK (hit_count >= 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  last_accessed_at timestamptz,
  expires_at timestamptz,
  UNIQUE (tenant_id, cache_namespace, cache_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE cache.cache_dependency (
  tenant_id uuid NOT NULL,
  cache_entry_id uuid NOT NULL,
  dependency_kind text NOT NULL CHECK (dependency_kind IN ('artifact', 'repository_revision', 'policy_revision', 'workflow_revision', 'model_route_revision', 'toolchain_revision', 'environment_revision', 'rule_release')),
  dependency_id uuid,
  dependency_sha256 text NOT NULL CHECK (core.sha256_is_valid(dependency_sha256)),
  PRIMARY KEY (tenant_id, cache_entry_id, dependency_kind, dependency_sha256),
  FOREIGN KEY (tenant_id, cache_entry_id) REFERENCES cache.cache_entry(tenant_id, id)
);

CREATE TRIGGER cache_dependency_immutable
BEFORE UPDATE OR DELETE ON cache.cache_dependency
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE cache.cache_access (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  cache_entry_id uuid NOT NULL,
  run_id uuid,
  task_id uuid,
  access_kind text NOT NULL CHECK (access_kind IN ('lookup_hit', 'lookup_miss', 'read', 'write', 'refresh', 'bypass')),
  avoided_input_tokens bigint NOT NULL DEFAULT 0 CHECK (avoided_input_tokens >= 0),
  avoided_compute_ms bigint NOT NULL DEFAULT 0 CHECK (avoided_compute_ms >= 0),
  avoided_cost_microunits bigint NOT NULL DEFAULT 0 CHECK (avoided_cost_microunits >= 0),
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, cache_entry_id) REFERENCES cache.cache_entry(tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id)
);

CREATE TRIGGER cache_access_immutable
BEFORE UPDATE OR DELETE ON cache.cache_access
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE cache.cache_invalidation (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  cache_entry_id uuid NOT NULL,
  reason_kind text NOT NULL CHECK (reason_kind IN ('dependency_changed', 'policy_changed', 'toolchain_changed', 'environment_changed', 'rule_revoked', 'manual', 'corruption', 'expiry')),
  reason text,
  source_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, cache_entry_id),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, cache_entry_id) REFERENCES cache.cache_entry(tenant_id, id)
);

CREATE TRIGGER cache_invalidation_immutable
BEFORE UPDATE OR DELETE ON cache.cache_invalidation
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE INDEX model_invocation_run_idx ON metering.model_invocation (tenant_id, run_id, invocation_no);
CREATE INDEX model_invocation_provider_idx ON metering.model_invocation (tenant_id, provider, model, started_at DESC);
CREATE INDEX tool_invocation_pending_idx ON metering.tool_invocation (tenant_id, run_id, status, started_at)
  WHERE status IN ('requested', 'approved', 'running', 'pending', 'unknown_result');
CREATE INDEX usage_ledger_run_idx ON metering.usage_ledger (tenant_id, run_id, occurred_at);
CREATE INDEX cost_ledger_run_idx ON metering.cost_ledger (tenant_id, run_id, occurred_at);
CREATE INDEX eta_run_latest_idx ON metering.eta_forecast (tenant_id, run_id, generated_at DESC);
CREATE INDEX cache_lookup_idx ON cache.cache_entry (tenant_id, cache_namespace, cache_key)
  WHERE status = 'available';
CREATE INDEX cache_expiry_idx ON cache.cache_entry (tenant_id, expires_at)
  WHERE status = 'available' AND expires_at IS NOT NULL;

COMMIT;
