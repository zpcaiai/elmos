-- PostgreSQL 17 target schema for the Repository Autonomy Kernel v2.
--
-- This migration is intentionally provider-neutral. It persists immutable
-- control-plane state and evidence; provider calls, deployment and release
-- certification remain outside the migration and require explicit adapters.
-- The service must set app.tenant_id from authenticated identity before each
-- transaction. No prompt, model or repository payload is an authority source.

create table if not exists autonomy_runs (
  run_id uuid primary key,
  tenant_id uuid not null,
  account_id uuid not null,
  task_spec_id text not null,
  task_spec_version text not null,
  task_spec_hash text not null,
  workflow_id text not null,
  workflow_version text not null,
  repo_snapshot_sha text,
  state text not null,
  budget jsonb not null default '{}'::jsonb,
  payload jsonb not null default '{}'::jsonb,
  current_step_id text,
  acceptance_decision_id uuid,
  idempotency_key text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, idempotency_key)
);
create index if not exists idx_autonomy_runs_tenant_state on autonomy_runs (tenant_id, state, updated_at desc);

create table if not exists autonomy_steps (
  run_id uuid not null references autonomy_runs(run_id) on delete cascade,
  step_id text not null,
  step_type text not null,
  step_version text not null,
  state text not null,
  attempt_no integer not null default 0,
  workspace_id uuid,
  environment_id uuid,
  permission_profile_id text,
  policy_snapshot_hash text,
  fencing_token bigint,
  input_artifact_hashes jsonb not null default '[]'::jsonb,
  output_artifact_hashes jsonb not null default '[]'::jsonb,
  error jsonb,
  started_at timestamptz,
  finished_at timestamptz,
  wall_clock_ms bigint,
  primary key (run_id, step_id)
);

create table if not exists autonomy_events (
  run_id uuid not null references autonomy_runs(run_id) on delete cascade,
  sequence_no bigint not null,
  event_id uuid not null unique,
  step_id text,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  causation_id uuid,
  correlation_id uuid,
  occurred_at timestamptz not null default now(),
  primary key (run_id, sequence_no)
);

create table if not exists autonomy_checkpoints (
  checkpoint_id uuid primary key,
  run_id uuid not null references autonomy_runs(run_id) on delete cascade,
  step_id text,
  repo_snapshot_sha text,
  workspace_hash text,
  state_snapshot jsonb not null,
  side_effect_cursor bigint not null default 0,
  artifact_id uuid,
  created_at timestamptz not null default now()
);

create table if not exists autonomy_leases (
  lease_id uuid primary key,
  resource_type text not null,
  resource_id text not null,
  owner_id text not null,
  fencing_token bigint not null,
  state text not null,
  acquired_at timestamptz not null default now(),
  heartbeat_at timestamptz,
  expires_at timestamptz not null,
  released_at timestamptz,
  unique (resource_type, resource_id, fencing_token)
);
create index if not exists idx_autonomy_leases_current on autonomy_leases (resource_type, resource_id, fencing_token desc);

create table if not exists autonomy_artifacts (
  artifact_id uuid primary key,
  tenant_id uuid not null,
  run_id uuid references autonomy_runs(run_id) on delete cascade,
  step_id text,
  kind text not null,
  content_hash text not null,
  storage_uri text not null,
  media_type text,
  size_bytes bigint,
  repo_snapshot_sha text,
  producer jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (tenant_id, content_hash, kind)
);

create table if not exists autonomy_evidence (
  evidence_id uuid primary key,
  tenant_id uuid not null,
  run_id uuid references autonomy_runs(run_id) on delete cascade,
  claim text not null,
  evidence_type text not null,
  source jsonb not null,
  confidence numeric(5,4),
  repo_snapshot_sha text,
  captured_at timestamptz not null default now(),
  expires_at timestamptz
);

create table if not exists autonomy_repository_snapshots (
  snapshot_id uuid primary key,
  tenant_id uuid not null,
  repo_uri text not null,
  base_commit_sha text not null,
  content_hash text not null,
  profile jsonb not null,
  captured_at timestamptz not null default now(),
  unique (tenant_id, repo_uri, base_commit_sha)
);

create table if not exists autonomy_semantic_indices (
  index_id uuid primary key,
  tenant_id uuid not null,
  snapshot_id uuid not null references autonomy_repository_snapshots(snapshot_id),
  version text not null,
  artifact_id uuid references autonomy_artifacts(artifact_id),
  quality jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists autonomy_change_nodes (
  change_node_id uuid primary key,
  tenant_id uuid not null,
  run_id uuid not null references autonomy_runs(run_id),
  node_type text not null,
  payload jsonb not null,
  status text not null,
  created_at timestamptz not null default now()
);

create table if not exists autonomy_change_edges (
  from_node_id uuid not null references autonomy_change_nodes(change_node_id) on delete cascade,
  to_node_id uuid not null references autonomy_change_nodes(change_node_id) on delete cascade,
  edge_type text not null,
  primary key (from_node_id, to_node_id, edge_type)
);

create table if not exists autonomy_tool_calls (
  tool_call_id uuid primary key,
  tenant_id uuid not null,
  run_id uuid references autonomy_runs(run_id) on delete cascade,
  step_id text not null,
  tool_id text not null,
  tool_version text not null,
  state text not null,
  input jsonb not null default '{}'::jsonb,
  input_hash text not null,
  idempotency_key text,
  workspace_id uuid,
  environment_id uuid,
  permission_profile_id text,
  policy_snapshot_hash text,
  fencing_token bigint,
  result_artifact_id uuid references autonomy_artifacts(artifact_id),
  structured_error jsonb,
  requested_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  unique (tenant_id, tool_id, idempotency_key)
);

create table if not exists autonomy_policy_decisions (
  decision_id uuid primary key,
  tenant_id uuid not null,
  run_id uuid references autonomy_runs(run_id) on delete cascade,
  step_id text,
  event_type text not null,
  decision text not null,
  reason text,
  policy_ids jsonb not null default '[]'::jsonb,
  policy_snapshot_hash text not null,
  evidence_ids jsonb not null default '[]'::jsonb,
  payload jsonb not null default '{}'::jsonb,
  decided_at timestamptz not null default now()
);

create table if not exists autonomy_approvals (
  approval_request_id uuid primary key,
  tenant_id uuid not null,
  run_id uuid references autonomy_runs(run_id) on delete cascade,
  step_id text,
  scope jsonb not null,
  risk_level text not null,
  state text not null,
  expires_at timestamptz,
  decision_by text,
  decision_reason text,
  created_at timestamptz not null default now(),
  decided_at timestamptz
);

create table if not exists autonomy_validations (
  validation_id uuid primary key,
  tenant_id uuid not null,
  run_id uuid references autonomy_runs(run_id) on delete cascade,
  validator_id text not null,
  validator_version text not null,
  status text not null,
  metrics jsonb not null default '{}'::jsonb,
  started_at timestamptz not null,
  finished_at timestamptz
);

create table if not exists autonomy_findings (
  finding_id uuid primary key,
  tenant_id uuid not null,
  run_id uuid references autonomy_runs(run_id) on delete cascade,
  category text not null,
  severity text not null,
  confidence numeric(5,4) not null,
  description text not null,
  location jsonb,
  evidence_ids jsonb not null default '[]'::jsonb,
  reproducer text,
  status text not null,
  validated_by jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists autonomy_acceptance_decisions (
  acceptance_decision_id uuid primary key,
  tenant_id uuid not null,
  run_id uuid not null references autonomy_runs(run_id) on delete cascade,
  decision text not null,
  gate_results jsonb not null,
  release_artifact_ids jsonb not null default '[]'::jsonb,
  rollback_artifact_ids jsonb not null default '[]'::jsonb,
  deployment_complete boolean not null default false,
  decided_by text not null,
  decided_at timestamptz not null default now()
);

create table if not exists autonomy_cache_entries (
  cache_entry_id uuid primary key,
  tenant_id uuid not null,
  cache_layer text not null,
  key_hash text not null,
  content_hash text not null,
  storage_uri text,
  provenance jsonb not null,
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  unique (tenant_id, cache_layer, key_hash)
);

create table if not exists autonomy_cost_events (
  cost_event_id uuid primary key,
  tenant_id uuid not null,
  account_id uuid not null,
  run_id uuid references autonomy_runs(run_id) on delete cascade,
  step_id text,
  category text not null,
  provider text,
  model_id text,
  quantity numeric(24,8) not null,
  unit text not null,
  unit_price numeric(24,12),
  total_cost numeric(24,12),
  pricing_profile_version text,
  occurred_at timestamptz not null default now()
);

create table if not exists autonomy_capability_packages (
  package_id uuid primary key,
  name text not null,
  version text not null,
  content_hash text not null,
  manifest jsonb not null,
  signature jsonb,
  state text not null,
  created_at timestamptz not null default now(),
  unique (name, version)
);

create table if not exists autonomy_adapter_conformance (
  adapter_id text not null,
  adapter_version text not null,
  suite_version text not null,
  status text not null,
  report_artifact_id uuid references autonomy_artifacts(artifact_id),
  tested_at timestamptz not null default now(),
  primary key (adapter_id, adapter_version, suite_version)
);

create table if not exists autonomy_eval_runs (
  eval_run_id uuid primary key,
  tenant_id uuid not null,
  suite_id text not null,
  candidate_id text not null,
  task_segment text not null,
  result jsonb not null,
  cost numeric(24,12),
  wall_clock_ms bigint,
  created_at timestamptz not null default now()
);

create table if not exists autonomy_elo_ratings (
  tenant_id uuid not null,
  candidate_id text not null,
  task_segment text not null,
  rating numeric(12,4) not null,
  uncertainty numeric(12,4) not null,
  sample_count bigint not null,
  updated_at timestamptz not null default now(),
  primary key (tenant_id, candidate_id, task_segment)
);

-- Tenant-scoped tables fail closed when app.tenant_id is absent. Child tables
-- without a tenant column inherit isolation through their run or artifact.
alter table autonomy_runs enable row level security;
alter table autonomy_artifacts enable row level security;
alter table autonomy_evidence enable row level security;
alter table autonomy_repository_snapshots enable row level security;
alter table autonomy_semantic_indices enable row level security;
alter table autonomy_change_nodes enable row level security;
alter table autonomy_tool_calls enable row level security;
alter table autonomy_policy_decisions enable row level security;
alter table autonomy_approvals enable row level security;
alter table autonomy_validations enable row level security;
alter table autonomy_findings enable row level security;
alter table autonomy_acceptance_decisions enable row level security;
alter table autonomy_cache_entries enable row level security;
alter table autonomy_cost_events enable row level security;
alter table autonomy_eval_runs enable row level security;
alter table autonomy_elo_ratings enable row level security;
alter table autonomy_runs force row level security;
alter table autonomy_artifacts force row level security;
alter table autonomy_evidence force row level security;
alter table autonomy_repository_snapshots force row level security;
alter table autonomy_semantic_indices force row level security;
alter table autonomy_change_nodes force row level security;
alter table autonomy_tool_calls force row level security;
alter table autonomy_policy_decisions force row level security;
alter table autonomy_approvals force row level security;
alter table autonomy_validations force row level security;
alter table autonomy_findings force row level security;
alter table autonomy_acceptance_decisions force row level security;
alter table autonomy_cache_entries force row level security;
alter table autonomy_cost_events force row level security;
alter table autonomy_eval_runs force row level security;
alter table autonomy_elo_ratings force row level security;

create policy autonomy_runs_tenant_isolation on autonomy_runs
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_artifacts_tenant_isolation on autonomy_artifacts
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_evidence_tenant_isolation on autonomy_evidence
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_repository_snapshots_tenant_isolation on autonomy_repository_snapshots
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_semantic_indices_tenant_isolation on autonomy_semantic_indices
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_change_nodes_tenant_isolation on autonomy_change_nodes
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_tool_calls_tenant_isolation on autonomy_tool_calls
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_policy_decisions_tenant_isolation on autonomy_policy_decisions
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_approvals_tenant_isolation on autonomy_approvals
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_validations_tenant_isolation on autonomy_validations
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_findings_tenant_isolation on autonomy_findings
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_acceptance_tenant_isolation on autonomy_acceptance_decisions
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_cache_entries_tenant_isolation on autonomy_cache_entries
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_cost_events_tenant_isolation on autonomy_cost_events
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_eval_runs_tenant_isolation on autonomy_eval_runs
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_elo_ratings_tenant_isolation on autonomy_elo_ratings
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);

-- Authorized external effects and independently verified release evidence.
create table if not exists autonomy_external_operations (
  operation_id uuid primary key, tenant_id uuid not null, account_id uuid not null,
  run_id uuid references autonomy_runs(run_id) on delete set null,
  capability text not null, adapter_id text not null, adapter_version text not null,
  provider_instance text not null, region text not null, native_resource_id text not null,
  action text not null, state text not null, side_effects boolean not null,
  idempotency_key text not null, request_hash text not null,
  request_metadata jsonb not null default '{}'::jsonb, authority_hash text,
  result jsonb, error jsonb, unknown_outcome boolean not null default false,
  compensation_token text, created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, capability, adapter_id, idempotency_key)
);
create table if not exists autonomy_external_receipts (
  receipt_id uuid primary key, tenant_id uuid not null,
  operation_id uuid not null references autonomy_external_operations(operation_id) on delete cascade,
  receipt_type text not null, status text not null, producer_id text not null,
  verifier_id text, evidence_class text not null, raw_evidence jsonb not null,
  content_hash text not null, created_at timestamptz not null default now()
);
create table if not exists autonomy_outbox_events (
  event_id uuid primary key, tenant_id uuid not null,
  operation_id uuid references autonomy_external_operations(operation_id) on delete set null,
  topic text not null, ordering_key text not null, event_type text not null,
  payload jsonb not null, payload_hash text not null, state text not null,
  attempts integer not null default 0, idempotency_key text not null,
  available_at timestamptz not null default now(), created_at timestamptz not null default now(),
  published_at timestamptz, unique (tenant_id, topic, idempotency_key)
);
create table if not exists autonomy_outbox_receipts (
  receipt_id uuid primary key, tenant_id uuid not null,
  event_id uuid not null references autonomy_outbox_events(event_id) on delete cascade,
  status text not null, producer_id text not null, verifier_id text,
  evidence_class text not null, raw_evidence jsonb not null,
  content_hash text not null, created_at timestamptz not null default now()
);
create table if not exists autonomy_inbox_events (
  tenant_id uuid not null, consumer_id text not null, event_id uuid not null,
  payload_hash text not null, ordering_key text not null, state text not null,
  attempts integer not null default 0, side_effects boolean not null,
  result jsonb, error jsonb, created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (tenant_id, consumer_id, event_id)
);
create table if not exists autonomy_secret_leases (
  lease_id uuid primary key, tenant_id uuid not null, broker_id text not null,
  secret_ref text not null, scope_hash text not null, state text not null,
  native_lease_id text, evidence_class text not null,
  expires_at timestamptz not null, receipt_hash text not null, revoke_receipt_hash text,
  created_at timestamptz not null default now(), revoked_at timestamptz
);
create table if not exists autonomy_certification_evidence (
  evidence_id uuid primary key, tenant_id uuid not null, case_id text not null,
  capability text not null, level text not null check (level in ('E1','E2','E3','E4','E5')),
  status text not null check (status in ('PASS','FAIL','UNKNOWN','BLOCKED','NOT_RUN')),
  evidence_class text not null, source_kind text not null, producer_id text not null,
  verifier_id text, independent boolean not null, payload jsonb not null,
  signed_document jsonb not null, signature text, key_id text,
  content_hash text not null, signature_verified boolean not null,
  captured_at timestamptz not null, expires_at timestamptz,
  check (not independent or verifier_id is distinct from producer_id)
);
create table if not exists autonomy_certification_runs (
  certification_run_id uuid primary key, tenant_id uuid not null,
  candidate_digest text not null, state text not null, level_results jsonb not null,
  matrix_result jsonb not null, p05_issued boolean not null default false,
  decision_hash text not null, created_at timestamptz not null default now(),
  check (not p05_issued or state = 'P05_DEPLOYMENT_COMPLETE')
);
create table if not exists autonomy_customer_acceptance (
  acceptance_id uuid primary key, tenant_id uuid not null,
  repository_binding_hash text not null, route_id text not null,
  candidate_digest text not null, customer_actor_id text not null,
  executor_id text not null, decision text not null check (decision in ('ACCEPTED','REJECTED')),
  evidence_ids jsonb not null,
  signature_verified boolean not null, content_hash text not null,
  created_at timestamptz not null default now(),
  unique (tenant_id, repository_binding_hash, route_id, candidate_digest),
  check (customer_actor_id <> executor_id),
  check (decision <> 'ACCEPTED' or signature_verified)
);

alter table autonomy_external_operations enable row level security;
alter table autonomy_external_receipts enable row level security;
alter table autonomy_outbox_events enable row level security;
alter table autonomy_outbox_receipts enable row level security;
alter table autonomy_inbox_events enable row level security;
alter table autonomy_secret_leases enable row level security;
alter table autonomy_certification_evidence enable row level security;
alter table autonomy_certification_runs enable row level security;
alter table autonomy_customer_acceptance enable row level security;
alter table autonomy_external_operations force row level security;
alter table autonomy_external_receipts force row level security;
alter table autonomy_outbox_events force row level security;
alter table autonomy_outbox_receipts force row level security;
alter table autonomy_inbox_events force row level security;
alter table autonomy_secret_leases force row level security;
alter table autonomy_certification_evidence force row level security;
alter table autonomy_certification_runs force row level security;
alter table autonomy_customer_acceptance force row level security;

create policy autonomy_external_operations_tenant_isolation on autonomy_external_operations using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_external_receipts_tenant_isolation on autonomy_external_receipts using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_outbox_events_tenant_isolation on autonomy_outbox_events using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_outbox_receipts_tenant_isolation on autonomy_outbox_receipts using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_inbox_events_tenant_isolation on autonomy_inbox_events using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_secret_leases_tenant_isolation on autonomy_secret_leases using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_certification_evidence_tenant_isolation on autonomy_certification_evidence using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_certification_runs_tenant_isolation on autonomy_certification_runs using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_customer_acceptance_tenant_isolation on autonomy_customer_acceptance using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
