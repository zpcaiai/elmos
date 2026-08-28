-- T00-T08 evidence, E1-E5 decisions and independent customer acceptance.
create table if not exists autonomy_certification_evidence (
  evidence_id uuid primary key,
  tenant_id uuid not null,
  case_id text not null,
  capability text not null,
  level text not null check (level in ('E1','E2','E3','E4','E5')),
  status text not null check (status in ('PASS','FAIL','UNKNOWN','BLOCKED','NOT_RUN')),
  evidence_class text not null,
  source_kind text not null,
  producer_id text not null,
  verifier_id text,
  independent boolean not null,
  payload jsonb not null,
  signed_document jsonb not null,
  signature text,
  key_id text,
  content_hash text not null,
  signature_verified boolean not null,
  captured_at timestamptz not null,
  expires_at timestamptz,
  check (not independent or verifier_id is distinct from producer_id)
);
create index if not exists idx_autonomy_certification_evidence_case
  on autonomy_certification_evidence (tenant_id, case_id, captured_at);

create table if not exists autonomy_certification_runs (
  certification_run_id uuid primary key,
  tenant_id uuid not null,
  candidate_digest text not null,
  state text not null,
  level_results jsonb not null,
  matrix_result jsonb not null,
  p05_issued boolean not null default false,
  decision_hash text not null,
  created_at timestamptz not null default now(),
  check (not p05_issued or state = 'P05_DEPLOYMENT_COMPLETE')
);

create table if not exists autonomy_customer_acceptance (
  acceptance_id uuid primary key,
  tenant_id uuid not null,
  repository_binding_hash text not null,
  route_id text not null,
  candidate_digest text not null,
  customer_actor_id text not null,
  executor_id text not null,
  decision text not null check (decision in ('ACCEPTED','REJECTED')),
  evidence_ids jsonb not null,
  signature_verified boolean not null,
  content_hash text not null,
  created_at timestamptz not null default now(),
  unique (tenant_id, repository_binding_hash, route_id, candidate_digest),
  check (customer_actor_id <> executor_id),
  check (decision <> 'ACCEPTED' or signature_verified)
);

alter table autonomy_certification_evidence enable row level security;
alter table autonomy_certification_runs enable row level security;
alter table autonomy_customer_acceptance enable row level security;
alter table autonomy_certification_evidence force row level security;
alter table autonomy_certification_runs force row level security;
alter table autonomy_customer_acceptance force row level security;

create policy autonomy_certification_evidence_tenant_isolation on autonomy_certification_evidence
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_certification_runs_tenant_isolation on autonomy_certification_runs
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy autonomy_customer_acceptance_tenant_isolation on autonomy_customer_acceptance
  using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
  with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
