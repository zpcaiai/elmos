create schema if not exists elmos_fde;
create table if not exists elmos_fde.engagement_case (
  tenant_id text not null, engagement_id text not null, phase text not null,
  payload jsonb not null, version bigint not null default 1, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  primary key (tenant_id, engagement_id)
);
create table if not exists elmos_fde.engagement_action (
  tenant_id text not null, engagement_id text not null, action_id text not null, owner text not null,
  status text not null, due_at timestamptz, payload jsonb not null, primary key (tenant_id, engagement_id, action_id)
);
