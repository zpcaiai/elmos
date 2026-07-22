CREATE TABLE organizations (
    organization_id varchar(64) PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE repositories (
    repository_id varchar(64) PRIMARY KEY,
    organization_id varchar(64) NOT NULL REFERENCES organizations(organization_id),
    scm_provider varchar(32) NOT NULL,
    external_id text NOT NULL,
    default_branch text NOT NULL
);
CREATE INDEX repositories_tenant_idx ON repositories(organization_id);

CREATE TABLE repository_snapshots (
    snapshot_id varchar(64) PRIMARY KEY,
    organization_id varchar(64) NOT NULL REFERENCES organizations(organization_id),
    repository_id varchar(64) NOT NULL REFERENCES repositories(repository_id),
    commit_sha varchar(64) NOT NULL,
    branch text NOT NULL,
    captured_at timestamptz NOT NULL,
    build_files_hash text NOT NULL,
    source_archive_ref text NOT NULL,
    CONSTRAINT repository_snapshots_content_v1_uq UNIQUE (organization_id, repository_id, commit_sha)
);

CREATE TABLE assessment_runs (
    assessment_run_id varchar(64) PRIMARY KEY,
    organization_id varchar(64) NOT NULL REFERENCES organizations(organization_id),
    snapshot_id varchar(64) NOT NULL REFERENCES repository_snapshots(snapshot_id),
    status varchar(32) NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz
);

CREATE TABLE migration_plans (
    migration_plan_id varchar(64) NOT NULL,
    organization_id varchar(64) NOT NULL REFERENCES organizations(organization_id),
    snapshot_id varchar(64) NOT NULL REFERENCES repository_snapshots(snapshot_id),
    plan_version integer NOT NULL CHECK (plan_version > 0),
    status varchar(32) NOT NULL,
    source_profile text NOT NULL,
    target_profile text NOT NULL,
    approved_at timestamptz,
    approved_by text,
    PRIMARY KEY (migration_plan_id, plan_version)
);

CREATE TABLE migration_runs (
    migration_run_id varchar(64) PRIMARY KEY,
    organization_id varchar(64) NOT NULL REFERENCES organizations(organization_id),
    snapshot_id varchar(64) NOT NULL REFERENCES repository_snapshots(snapshot_id),
    migration_plan_id varchar(64) NOT NULL,
    plan_version integer NOT NULL,
    state varchar(64) NOT NULL,
    version bigint NOT NULL DEFAULT 0,
    FOREIGN KEY (migration_plan_id, plan_version) REFERENCES migration_plans(migration_plan_id, plan_version)
);

CREATE TABLE migration_step_runs (
    step_run_id varchar(64) PRIMARY KEY,
    migration_run_id varchar(64) NOT NULL REFERENCES migration_runs(migration_run_id),
    step_id text NOT NULL,
    attempt integer NOT NULL CHECK (attempt > 0),
    executor_type varchar(64) NOT NULL,
    state varchar(64) NOT NULL,
    started_at timestamptz,
    finished_at timestamptz,
    failure_code text,
    UNIQUE (migration_run_id, step_id, attempt)
);

CREATE TABLE evidence (
    evidence_id varchar(64) PRIMARY KEY,
    organization_id varchar(64) NOT NULL REFERENCES organizations(organization_id),
    migration_run_id varchar(64) NOT NULL REFERENCES migration_runs(migration_run_id),
    step_run_id varchar(64) REFERENCES migration_step_runs(step_run_id),
    evidence_type varchar(64) NOT NULL,
    producer_type varchar(64) NOT NULL,
    producer_name text NOT NULL,
    producer_version text NOT NULL,
    source_commit varchar(64) NOT NULL,
    target_commit varchar(64),
    created_at timestamptz NOT NULL,
    status varchar(32) NOT NULL,
    summary text NOT NULL,
    artifact_ref text NOT NULL,
    content_hash varchar(80) NOT NULL,
    schema_version varchar(16) NOT NULL,
    correlation_id varchar(128) NOT NULL
);

CREATE TABLE audit_events (
    audit_id varchar(64) PRIMARY KEY,
    actor_type varchar(32) NOT NULL,
    actor_id text NOT NULL,
    action text NOT NULL,
    resource_type varchar(64) NOT NULL,
    resource_id text NOT NULL,
    before_hash text,
    after_hash text,
    occurred_at timestamptz NOT NULL,
    request_id varchar(128) NOT NULL,
    runner_id text,
    policy_decision varchar(32) NOT NULL,
    result varchar(32) NOT NULL
);

CREATE TABLE outbox_events (
    event_id varchar(64) PRIMARY KEY,
    aggregate_type varchar(64) NOT NULL,
    aggregate_id varchar(64) NOT NULL,
    event_type varchar(128) NOT NULL,
    occurred_at timestamptz NOT NULL,
    attributes text NOT NULL,
    published_at timestamptz
);
CREATE INDEX outbox_unpublished_idx ON outbox_events(occurred_at) WHERE published_at IS NULL;
