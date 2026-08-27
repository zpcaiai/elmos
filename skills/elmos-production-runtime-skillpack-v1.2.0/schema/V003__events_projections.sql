CREATE TABLE observability.outbox_events (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    trace_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    publish_attempts integer NOT NULL DEFAULT 0,
    last_error text
);

CREATE TABLE observability.project_events (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    project_id uuid NOT NULL REFERENCES project.projects(id),
    job_id uuid REFERENCES orchestration.jobs(id),
    work_item_id uuid REFERENCES orchestration.work_items(id),
    attempt_id uuid REFERENCES runtime.execution_attempts(id),
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    trace_id text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE observability.progress_snapshots (
    job_id uuid PRIMARY KEY REFERENCES orchestration.jobs(id),
    project_id uuid NOT NULL REFERENCES project.projects(id),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    total_work_items bigint NOT NULL DEFAULT 0,
    ready_work_items bigint NOT NULL DEFAULT 0,
    running_work_items bigint NOT NULL DEFAULT 0,
    completed_work_items bigint NOT NULL DEFAULT 0,
    failed_work_items bigint NOT NULL DEFAULT 0,
    progress numeric(5,2) NOT NULL DEFAULT 0,
    tokens_consumed bigint NOT NULL DEFAULT 0,
    credits_consumed numeric(38,12) NOT NULL DEFAULT 0,
    metered_credits numeric(38,12) NOT NULL DEFAULT 0,
    estimated_remaining_credits numeric(38,12) NOT NULL DEFAULT 0,
    estimated_remaining_wall_clock_ms bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_outbox_unpublished
ON observability.outbox_events(id)
WHERE published_at IS NULL;
