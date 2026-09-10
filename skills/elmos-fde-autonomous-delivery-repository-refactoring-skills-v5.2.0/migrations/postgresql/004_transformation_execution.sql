create table if not exists elmos_fde.transformation_plan (
  tenant_id text not null, plan_id text not null, revision_set_id text not null, status text not null, payload jsonb not null,
  primary key (tenant_id, plan_id)
);
create table if not exists elmos_fde.execution_checkpoint (
  tenant_id text not null, execution_id text not null, checkpoint_id text not null, generation bigint not null,
  state_hash text not null, authority_hash text not null, payload jsonb not null, created_at timestamptz not null default now(),
  primary key (tenant_id, execution_id, checkpoint_id)
);
create table if not exists elmos_fde.idempotency_record (
  tenant_id text not null, idempotency_key text not null, request_hash text not null, result_hash text,
  status text not null, expires_at timestamptz, primary key (tenant_id, idempotency_key)
);
