-- Core durable lifecycle state. Apply in order with V002-V004.
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
