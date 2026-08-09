create schema if not exists platform;
create schema if not exists migration;
create schema if not exists workflow;
create schema if not exists runner;
create schema if not exists artifact;
create schema if not exists audit;

create table if not exists platform.projects (
    project_id uuid primary key,
    tenant_id uuid not null,
    name varchar(200) not null,
    created_at timestamptz not null
);
create index if not exists idx_projects_tenant on platform.projects(tenant_id, created_at desc);

create table if not exists migration.migrations (
    migration_id uuid primary key,
    tenant_id uuid not null,
    project_id uuid not null,
    source_repository text not null,
    source_language varchar(50) not null,
    target_language varchar(50) not null,
    target_framework varchar(100) not null,
    status varchar(40) not null,
    current_phase varchar(80),
    risk_tier varchar(20) not null,
    aggregate_version bigint not null default 0,
    created_at timestamptz not null,
    updated_at timestamptz not null
);
create index if not exists idx_migrations_tenant_project
    on migration.migrations(tenant_id, project_id, created_at desc);

create table if not exists runner.runners (
    runner_id uuid primary key,
    tenant_id uuid not null,
    name varchar(200) not null,
    version varchar(100) not null,
    capabilities text not null default '',
    status varchar(40) not null,
    registered_at timestamptz not null,
    last_heartbeat_at timestamptz not null
);
create index if not exists idx_runners_tenant_heartbeat
    on runner.runners(tenant_id, last_heartbeat_at desc);

create table if not exists workflow.tasks (
    task_id uuid primary key,
    tenant_id uuid not null,
    workflow_instance_id uuid not null,
    task_type varchar(100) not null,
    status varchar(40) not null,
    priority integer not null default 0,
    attempt integer not null default 0,
    max_attempts integer not null default 3,
    payload jsonb not null default '{}'::jsonb,
    output_payload jsonb,
    leased_by uuid,
    lease_expires_at timestamptz,
    commit_token varchar(100),
    artifact_path text,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    completed_at timestamptz
);
create index if not exists idx_tasks_claim
    on workflow.tasks(tenant_id, status, priority desc, created_at);

create table if not exists artifact.artifacts (
    artifact_id uuid primary key,
    tenant_id uuid not null,
    artifact_type varchar(80) not null,
    digest varchar(128) not null,
    storage_uri text not null,
    size_bytes bigint not null,
    classification varchar(40) not null,
    schema_version integer not null,
    created_at timestamptz not null,
    unique(tenant_id, digest)
);

create table if not exists platform.outbox_events (
    event_id uuid primary key,
    aggregate_type varchar(100) not null,
    aggregate_id uuid not null,
    aggregate_version bigint not null,
    event_type varchar(150) not null,
    event_version integer not null,
    tenant_id uuid not null,
    payload jsonb not null,
    occurred_at timestamptz not null,
    published_at timestamptz
);
create index if not exists idx_outbox_unpublished
    on platform.outbox_events(occurred_at) where published_at is null;

create table if not exists platform.inbox_messages (
    consumer_name varchar(100) not null,
    event_id uuid not null,
    received_at timestamptz not null,
    processed_at timestamptz,
    status varchar(30) not null,
    primary key(consumer_name, event_id)
);

create table if not exists audit.audit_events (
    event_id uuid primary key,
    tenant_id uuid not null,
    actor_id varchar(200) not null,
    actor_type varchar(40) not null,
    action varchar(200) not null,
    resource_type varchar(100) not null,
    resource_id varchar(200) not null,
    decision varchar(20) not null,
    occurred_at timestamptz not null,
    details jsonb not null default '{}'::jsonb
);
