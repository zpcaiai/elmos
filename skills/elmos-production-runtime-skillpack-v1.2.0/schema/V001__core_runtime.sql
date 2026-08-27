CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS identity;
CREATE SCHEMA IF NOT EXISTS project;
CREATE SCHEMA IF NOT EXISTS semantic;
CREATE SCHEMA IF NOT EXISTS orchestration;
CREATE SCHEMA IF NOT EXISTS runtime;
CREATE SCHEMA IF NOT EXISTS artifact;
CREATE SCHEMA IF NOT EXISTS validation;
CREATE SCHEMA IF NOT EXISTS ai_usage;
CREATE SCHEMA IF NOT EXISTS billing;
CREATE SCHEMA IF NOT EXISTS observability;

CREATE TABLE identity.tenants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE identity.accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    external_subject text,
    status text NOT NULL DEFAULT 'ACTIVE',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, external_subject)
);

CREATE TABLE project.projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    account_id uuid NOT NULL REFERENCES identity.accounts(id),
    name text NOT NULL,
    project_type text NOT NULL,
    status text NOT NULL DEFAULT 'CREATED',
    progress numeric(5,2) NOT NULL DEFAULT 0,
    estimated_total_tokens bigint NOT NULL DEFAULT 0,
    consumed_total_tokens bigint NOT NULL DEFAULT 0,
    estimated_total_credits numeric(38,12) NOT NULL DEFAULT 0,
    consumed_total_credits numeric(38,12) NOT NULL DEFAULT 0,
    estimated_wall_clock_ms bigint NOT NULL DEFAULT 0,
    elapsed_wall_clock_ms bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE project.repository_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    project_id uuid NOT NULL REFERENCES project.projects(id) ON DELETE CASCADE,
    git_commit_sha text,
    snapshot_hash text NOT NULL,
    object_uri text NOT NULL,
    total_files bigint NOT NULL DEFAULT 0,
    total_loc bigint NOT NULL DEFAULT 0,
    total_bytes bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, snapshot_hash)
);

CREATE TABLE orchestration.jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    account_id uuid NOT NULL REFERENCES identity.accounts(id),
    project_id uuid NOT NULL REFERENCES project.projects(id) ON DELETE CASCADE,
    job_type text NOT NULL,
    status text NOT NULL DEFAULT 'CREATED',
    priority integer NOT NULL DEFAULT 100,
    max_parallelism integer NOT NULL DEFAULT 1,
    input_snapshot_id uuid REFERENCES project.repository_snapshots(id),
    output_snapshot_id uuid REFERENCES project.repository_snapshots(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE orchestration.job_stages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    job_id uuid NOT NULL REFERENCES orchestration.jobs(id) ON DELETE CASCADE,
    stage_type text NOT NULL,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'BLOCKED',
    sequence_no integer NOT NULL DEFAULT 0,
    max_parallelism integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE orchestration.work_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    job_id uuid NOT NULL REFERENCES orchestration.jobs(id) ON DELETE CASCADE,
    stage_id uuid NOT NULL REFERENCES orchestration.job_stages(id) ON DELETE CASCADE,
    work_type text NOT NULL,
    resource_key text NOT NULL,
    status text NOT NULL DEFAULT 'PENDING',
    priority integer NOT NULL DEFAULT 100,
    estimated_tokens bigint NOT NULL DEFAULT 0,
    consumed_tokens bigint NOT NULL DEFAULT 0,
    estimated_cost numeric(38,12) NOT NULL DEFAULT 0,
    actual_cost numeric(38,12) NOT NULL DEFAULT 0,
    retry_count integer NOT NULL DEFAULT 0,
    max_retries integer NOT NULL DEFAULT 3,
    idempotency_key text NOT NULL,
    ready_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, idempotency_key)
);

CREATE TABLE orchestration.work_item_dependencies (
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    work_item_id uuid NOT NULL REFERENCES orchestration.work_items(id) ON DELETE CASCADE,
    depends_on_work_item_id uuid NOT NULL REFERENCES orchestration.work_items(id) ON DELETE CASCADE,
    dependency_type text NOT NULL DEFAULT 'SUCCESS',
    PRIMARY KEY(work_item_id, depends_on_work_item_id),
    CHECK(work_item_id <> depends_on_work_item_id)
);

CREATE TABLE runtime.dispatch_intents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    work_item_id uuid NOT NULL REFERENCES orchestration.work_items(id) ON DELETE CASCADE,
    state text NOT NULL,
    reservation_id uuid,
    worker_id uuid,
    attempt_id uuid,
    fencing_token bigint,
    reservation_idempotency_key text NOT NULL,
    dispatch_idempotency_key text NOT NULL,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(work_item_id, dispatch_idempotency_key)
);

CREATE TABLE runtime.work_item_fence_counters (
    work_item_id uuid PRIMARY KEY REFERENCES orchestration.work_items(id) ON DELETE CASCADE,
    next_token bigint NOT NULL CHECK(next_token > 0)
);

CREATE TABLE runtime.workers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_name text NOT NULL,
    worker_type text NOT NULL,
    endpoint_uri text NOT NULL,
    region text,
    zone text,
    capabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'ACTIVE',
    last_heartbeat_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(worker_name)
);

CREATE TABLE runtime.execution_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    work_item_id uuid NOT NULL REFERENCES orchestration.work_items(id) ON DELETE CASCADE,
    attempt_no integer NOT NULL,
    worker_id uuid REFERENCES runtime.workers(id),
    status text NOT NULL DEFAULT 'CREATED',
    fencing_token bigint NOT NULL,
    started_at timestamptz,
    heartbeat_at timestamptz,
    completed_at timestamptz,
    error_code text,
    error_message text,
    UNIQUE(work_item_id, attempt_no),
    UNIQUE(work_item_id, fencing_token)
);

CREATE TABLE runtime.worker_leases (
    work_item_id uuid PRIMARY KEY REFERENCES orchestration.work_items(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    worker_id uuid NOT NULL REFERENCES runtime.workers(id),
    attempt_id uuid NOT NULL REFERENCES runtime.execution_attempts(id) ON DELETE CASCADE,
    fencing_token bigint NOT NULL,
    leased_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    heartbeat_at timestamptz NOT NULL
);

CREATE TABLE runtime.checkpoints (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    job_id uuid NOT NULL REFERENCES orchestration.jobs(id),
    work_item_id uuid REFERENCES orchestration.work_items(id),
    attempt_id uuid REFERENCES runtime.execution_attempts(id),
    checkpoint_type text NOT NULL,
    sequence_no bigint NOT NULL,
    state_object_uri text NOT NULL,
    state_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(attempt_id, sequence_no)
);

CREATE TABLE artifact.artifacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    project_id uuid NOT NULL REFERENCES project.projects(id),
    job_id uuid REFERENCES orchestration.jobs(id),
    work_item_id uuid REFERENCES orchestration.work_items(id),
    artifact_type text NOT NULL,
    object_uri text NOT NULL,
    sha256 text NOT NULL,
    size_bytes bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE validation.validation_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    job_id uuid NOT NULL REFERENCES orchestration.jobs(id),
    validation_type text NOT NULL,
    status text NOT NULL DEFAULT 'CREATED',
    passed bigint NOT NULL DEFAULT 0,
    failed bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE INDEX idx_work_ready ON orchestration.work_items(tenant_id,status,priority,ready_at,created_at)
WHERE status IN ('READY','RETRY_WAIT');

CREATE INDEX idx_dispatch_state ON runtime.dispatch_intents(state,updated_at);
CREATE INDEX idx_lease_expiry ON runtime.worker_leases(expires_at);
