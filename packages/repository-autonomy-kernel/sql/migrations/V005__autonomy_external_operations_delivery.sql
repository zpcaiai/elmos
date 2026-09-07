-- Authorized external effects, receipts, transactional outbox and secret leases.
-- V001-V004 are immutable released migrations; FORCE RLS hardening therefore
-- begins here instead of rewriting their checksummed bytes.
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

create table if not exists autonomy_external_operations (
  operation_id uuid primary key,
  tenant_id uuid not null,
  account_id uuid not null,
  run_id uuid references autonomy_runs(run_id) on delete set null,
  capability text not null,
  adapter_id text not null,
  adapter_version text not null,
  provider_instance text not null,
  region text not null,
  native_resource_id text not null,
  action text not null,
  state text not null check (state in ('DRY_RUN','AUTHORIZED','EXECUTING','EXECUTED','UNKNOWN','RECONCILING','RECONCILED','COMPENSATING','COMPENSATED','FAILED','DENIED','CANCELLED')),
  side_effects boolean not null,
  idempotency_key text not null,
  request_hash text not null,
  request_metadata jsonb not null default '{}'::jsonb,
  authority_hash text,
  result jsonb,
  error jsonb,
  unknown_outcome boolean not null default false,
  compensation_token text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, capability, adapter_id, idempotency_key)
);
create index if not exists idx_autonomy_external_operations_state
  on autonomy_external_operations (tenant_id, state, updated_at);

create table if not exists autonomy_external_receipts (
  receipt_id uuid primary key,
  tenant_id uuid not null,
  operation_id uuid not null references autonomy_external_operations(operation_id) on delete cascade,
  receipt_type text not null,
  status text not null,
  producer_id text not null,
  verifier_id text,
  evidence_class text not null,
  raw_evidence jsonb not null,
  content_hash text not null,
  created_at timestamptz not null default now()
);
create index if not exists idx_autonomy_external_receipts_operation
  on autonomy_external_receipts (tenant_id, operation_id, created_at);

create table if not exists autonomy_outbox_events (
  event_id uuid primary key,
  tenant_id uuid not null,
  operation_id uuid references autonomy_external_operations(operation_id) on delete set null,
  topic text not null,
  ordering_key text not null,
  event_type text not null,
  payload jsonb not null,
  payload_hash text not null,
  state text not null check (state in ('PENDING','PUBLISHING','PUBLISHED','RETRY','UNKNOWN','DEAD_LETTER')),
  attempts integer not null default 0,
  idempotency_key text not null,
  available_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  published_at timestamptz,
  unique (tenant_id, topic, idempotency_key)
);
create index if not exists idx_autonomy_outbox_publish
  on autonomy_outbox_events (tenant_id, state, available_at, ordering_key);

create table if not exists autonomy_outbox_receipts (
  receipt_id uuid primary key,
  tenant_id uuid not null,
  event_id uuid not null references autonomy_outbox_events(event_id) on delete cascade,
  status text not null,
  producer_id text not null,
  verifier_id text,
  evidence_class text not null,
  raw_evidence jsonb not null,
  content_hash text not null,
  created_at timestamptz not null default now()
);
create index if not exists idx_autonomy_outbox_receipts_event
  on autonomy_outbox_receipts (tenant_id, event_id, created_at);

create table if not exists autonomy_inbox_events (
  tenant_id uuid not null,
  consumer_id text not null,
  event_id uuid not null,
  payload_hash text not null,
  ordering_key text not null,
  state text not null check (state in ('PROCESSING','PROCESSED','RETRY','UNKNOWN','DEAD_LETTER')),
  attempts integer not null default 0,
  side_effects boolean not null,
  result jsonb,
  error jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (tenant_id, consumer_id, event_id)
);
create index if not exists idx_autonomy_inbox_ordering
  on autonomy_inbox_events (tenant_id, consumer_id, ordering_key, created_at);

create table if not exists autonomy_secret_leases (
  lease_id uuid primary key,
  tenant_id uuid not null,
  broker_id text not null,
  secret_ref text not null,
  scope_hash text not null,
  state text not null check (state in ('ACTIVE','REVOKED','REVOKE_UNKNOWN','EXPIRED')),
  native_lease_id text,
  evidence_class text not null,
  expires_at timestamptz not null,
  receipt_hash text not null,
  revoke_receipt_hash text,
  created_at timestamptz not null default now(),
  revoked_at timestamptz
);

alter table autonomy_external_operations enable row level security;
alter table autonomy_external_receipts enable row level security;
alter table autonomy_outbox_events enable row level security;
alter table autonomy_outbox_receipts enable row level security;
alter table autonomy_inbox_events enable row level security;
alter table autonomy_secret_leases enable row level security;
alter table autonomy_external_operations force row level security;
alter table autonomy_external_receipts force row level security;
alter table autonomy_outbox_events force row level security;
alter table autonomy_outbox_receipts force row level security;
alter table autonomy_inbox_events force row level security;
alter table autonomy_secret_leases force row level security;

create policy autonomy_external_operations_tenant_isolation on autonomy_external_operations
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_external_receipts_tenant_isolation on autonomy_external_receipts
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_outbox_events_tenant_isolation on autonomy_outbox_events
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_outbox_receipts_tenant_isolation on autonomy_outbox_receipts
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_inbox_events_tenant_isolation on autonomy_inbox_events
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_secret_leases_tenant_isolation on autonomy_secret_leases
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
