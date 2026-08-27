-- Content-addressed artifact and repository-intelligence state.
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
