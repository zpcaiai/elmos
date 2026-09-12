create table if not exists elmos_fde.finding (
  tenant_id text not null, finding_id text not null, revision_set_id text not null, domain text not null,
  severity text not null, status text not null, payload jsonb not null, updated_at timestamptz not null default now(),
  primary key (tenant_id, finding_id)
);
create table if not exists elmos_fde.ledger_event (
  tenant_id text not null, ledger text not null, sequence bigint not null, event_id text not null,
  previous_hash text not null, event_hash text not null, payload jsonb not null, created_at timestamptz not null default now(),
  primary key (tenant_id, ledger, sequence), unique (tenant_id, ledger, event_id)
);
