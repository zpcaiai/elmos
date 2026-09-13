create table if not exists elmos_fde.adoption_event (
  tenant_id text not null, engagement_id text not null, event_id text not null, event_type text not null,
  occurred_at timestamptz not null, payload jsonb not null, primary key (tenant_id, event_id)
);
create table if not exists elmos_fde.product_feedback (
  tenant_id text not null, feedback_id text not null, engagement_id text, problem_fingerprint text not null,
  status text not null, payload jsonb not null, created_at timestamptz not null default now(), primary key (tenant_id, feedback_id)
);
