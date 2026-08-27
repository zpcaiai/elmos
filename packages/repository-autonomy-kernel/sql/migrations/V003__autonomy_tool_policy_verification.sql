-- Typed tools, policy decisions, approvals and independent verification state.
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
