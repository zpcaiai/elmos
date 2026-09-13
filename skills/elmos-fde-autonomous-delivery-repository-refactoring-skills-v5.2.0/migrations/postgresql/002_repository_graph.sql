create table if not exists elmos_fde.repository_snapshot (
  tenant_id text not null, repository_id text not null, revision_set_id text not null,
  content_hash text not null, payload jsonb not null, created_at timestamptz not null default now(),
  primary key (tenant_id, repository_id, revision_set_id)
);
create table if not exists elmos_fde.system_graph_node (
  tenant_id text not null, graph_id text not null, node_id text not null, kind text not null, payload jsonb not null,
  primary key (tenant_id, graph_id, node_id)
);
create table if not exists elmos_fde.system_graph_edge (
  tenant_id text not null, graph_id text not null, edge_id text not null, from_node text not null, to_node text not null,
  kind text not null, confidence numeric not null check (confidence >= 0 and confidence <= 1), payload jsonb not null,
  primary key (tenant_id, graph_id, edge_id)
);
