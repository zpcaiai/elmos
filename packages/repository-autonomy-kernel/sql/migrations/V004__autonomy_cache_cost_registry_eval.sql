-- Cache, cost, package, adapter and evaluation state plus database isolation.
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

-- RLS is enabled only after all tenant-bearing tables exist. The application
-- must set app.tenant_id from authenticated identity in the same transaction.
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

create policy autonomy_runs_tenant_isolation on autonomy_runs using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_artifacts_tenant_isolation on autonomy_artifacts using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_evidence_tenant_isolation on autonomy_evidence using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_repository_snapshots_tenant_isolation on autonomy_repository_snapshots using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_semantic_indices_tenant_isolation on autonomy_semantic_indices using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_change_nodes_tenant_isolation on autonomy_change_nodes using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_tool_calls_tenant_isolation on autonomy_tool_calls using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_policy_decisions_tenant_isolation on autonomy_policy_decisions using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_approvals_tenant_isolation on autonomy_approvals using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_validations_tenant_isolation on autonomy_validations using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_findings_tenant_isolation on autonomy_findings using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_acceptance_tenant_isolation on autonomy_acceptance_decisions using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_cache_entries_tenant_isolation on autonomy_cache_entries using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_cost_events_tenant_isolation on autonomy_cost_events using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_eval_runs_tenant_isolation on autonomy_eval_runs using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_elo_ratings_tenant_isolation on autonomy_elo_ratings using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
