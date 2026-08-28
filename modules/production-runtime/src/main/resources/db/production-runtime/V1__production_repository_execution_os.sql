-- ELMOS isolated production-runtime Flyway V1, runtime contract v1.2.0
-- PostgreSQL is authoritative. Redis/cache providers are intentionally absent
-- from this migration because losing them must not lose work or money.

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
    name text NOT NULL CHECK (length(trim(name)) > 0),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'SUSPENDED', 'DELETED')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE identity.accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    external_subject text,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'SUSPENDED', 'DELETED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, external_subject)
);

CREATE TABLE project.projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    account_id uuid NOT NULL,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    project_type text NOT NULL,
    status text NOT NULL DEFAULT 'CREATED' CHECK (status IN ('CREATED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    progress numeric(5,2) NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    estimated_total_tokens bigint NOT NULL DEFAULT 0 CHECK (estimated_total_tokens >= 0),
    consumed_total_tokens bigint NOT NULL DEFAULT 0 CHECK (consumed_total_tokens >= 0),
    estimated_total_credits numeric(38,12) NOT NULL DEFAULT 0 CHECK (estimated_total_credits >= 0),
    consumed_total_credits numeric(38,12) NOT NULL DEFAULT 0 CHECK (consumed_total_credits >= 0),
    estimated_wall_clock_ms bigint NOT NULL DEFAULT 0 CHECK (estimated_wall_clock_ms >= 0),
    elapsed_wall_clock_ms bigint NOT NULL DEFAULT 0 CHECK (elapsed_wall_clock_ms >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, account_id) REFERENCES identity.accounts(tenant_id, id)
);

CREATE TABLE project.repository_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    project_id uuid NOT NULL REFERENCES project.projects(id) ON DELETE CASCADE,
    git_commit_sha text,
    snapshot_hash text NOT NULL CHECK (length(snapshot_hash) >= 32),
    object_uri text NOT NULL,
    total_files bigint NOT NULL DEFAULT 0 CHECK (total_files >= 0),
    total_loc bigint NOT NULL DEFAULT 0 CHECK (total_loc >= 0),
    total_bytes bigint NOT NULL DEFAULT 0 CHECK (total_bytes >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, snapshot_hash)
);

CREATE TABLE orchestration.jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    account_id uuid NOT NULL,
    project_id uuid NOT NULL REFERENCES project.projects(id) ON DELETE CASCADE,
    job_type text NOT NULL,
    status text NOT NULL DEFAULT 'CREATED' CHECK (status IN ('CREATED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    priority integer NOT NULL DEFAULT 100 CHECK (priority BETWEEN 0 AND 1000),
    max_parallelism integer NOT NULL DEFAULT 1 CHECK (max_parallelism > 0),
    input_snapshot_id uuid REFERENCES project.repository_snapshots(id),
    output_snapshot_id uuid REFERENCES project.repository_snapshots(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, account_id) REFERENCES identity.accounts(tenant_id, id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES project.projects(tenant_id, id)
);

CREATE TABLE orchestration.job_stages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    job_id uuid NOT NULL REFERENCES orchestration.jobs(id) ON DELETE CASCADE,
    stage_type text NOT NULL,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'BLOCKED' CHECK (status IN ('BLOCKED', 'READY', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    sequence_no integer NOT NULL DEFAULT 0 CHECK (sequence_no >= 0),
    max_parallelism integer NOT NULL DEFAULT 1 CHECK (max_parallelism > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (job_id, sequence_no),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, job_id) REFERENCES orchestration.jobs(tenant_id, id)
);

CREATE TABLE orchestration.work_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    job_id uuid NOT NULL REFERENCES orchestration.jobs(id) ON DELETE CASCADE,
    stage_id uuid NOT NULL REFERENCES orchestration.job_stages(id) ON DELETE CASCADE,
    work_type text NOT NULL,
    resource_key text NOT NULL,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'READY', 'RESERVING', 'WAITING_FOR_CREDIT', 'RESERVED', 'DISPATCHING', 'RUNNING', 'SUCCEEDED', 'RETRY_WAIT', 'FAILED', 'CANCELLED')),
    priority integer NOT NULL DEFAULT 100 CHECK (priority BETWEEN 0 AND 1000),
    estimated_tokens bigint NOT NULL DEFAULT 0 CHECK (estimated_tokens >= 0),
    consumed_tokens bigint NOT NULL DEFAULT 0 CHECK (consumed_tokens >= 0),
    estimated_cost numeric(38,12) NOT NULL DEFAULT 0 CHECK (estimated_cost >= 0),
    actual_cost numeric(38,12) NOT NULL DEFAULT 0 CHECK (actual_cost >= 0),
    retry_count integer NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    max_retries integer NOT NULL DEFAULT 3 CHECK (max_retries >= 0),
    idempotency_key text NOT NULL,
    ready_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, idempotency_key),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, job_id) REFERENCES orchestration.jobs(tenant_id, id),
    FOREIGN KEY (tenant_id, stage_id) REFERENCES orchestration.job_stages(tenant_id, id)
);

CREATE TABLE orchestration.work_item_dependencies (
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    work_item_id uuid NOT NULL,
    depends_on_work_item_id uuid NOT NULL,
    dependency_type text NOT NULL DEFAULT 'SUCCESS' CHECK (dependency_type IN ('SUCCESS', 'COMPLETION')),
    PRIMARY KEY (work_item_id, depends_on_work_item_id),
    CHECK (work_item_id <> depends_on_work_item_id),
    FOREIGN KEY (tenant_id, work_item_id) REFERENCES orchestration.work_items(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, depends_on_work_item_id) REFERENCES orchestration.work_items(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE runtime.dispatch_intents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    project_id uuid NOT NULL,
    job_id uuid NOT NULL,
    work_item_id uuid NOT NULL REFERENCES orchestration.work_items(id) ON DELETE CASCADE,
    wallet_id uuid NOT NULL,
    estimated_credits numeric(38,12) NOT NULL CHECK (estimated_credits > 0),
    reservation_expires_at timestamptz NOT NULL,
    dispatch_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    state text NOT NULL CHECK (state IN ('CREATED', 'RESERVING', 'RESERVED', 'ATTEMPT_CREATED', 'DISPATCHING', 'ACKED', 'COMPLETED', 'ABORTED')),
    reservation_id uuid,
    worker_id uuid,
    attempt_id uuid,
    fencing_token bigint CHECK (fencing_token IS NULL OR fencing_token > 0),
    reservation_idempotency_key text NOT NULL,
    dispatch_idempotency_key text NOT NULL,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, work_item_id, dispatch_idempotency_key),
    FOREIGN KEY (tenant_id, project_id) REFERENCES project.projects(tenant_id, id),
    FOREIGN KEY (tenant_id, job_id) REFERENCES orchestration.jobs(tenant_id, id),
    FOREIGN KEY (tenant_id, work_item_id) REFERENCES orchestration.work_items(tenant_id, id),
    CHECK (reservation_expires_at > created_at)
);

CREATE TABLE runtime.work_item_fence_counters (
    work_item_id uuid PRIMARY KEY REFERENCES orchestration.work_items(id) ON DELETE CASCADE,
    next_token bigint NOT NULL CHECK (next_token > 0)
);

CREATE TABLE runtime.workers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_name text NOT NULL UNIQUE,
    worker_type text NOT NULL,
    endpoint_uri text NOT NULL CHECK (length(endpoint_uri) > 1),
    region text,
    zone text,
    capabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DRAINING', 'DISABLED')),
    last_heartbeat_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE runtime.execution_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    work_item_id uuid NOT NULL REFERENCES orchestration.work_items(id) ON DELETE CASCADE,
    attempt_no integer NOT NULL CHECK (attempt_no > 0),
    worker_id uuid NOT NULL REFERENCES runtime.workers(id),
    status text NOT NULL DEFAULT 'CREATED' CHECK (status IN ('CREATED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'TIMED_OUT', 'LOST', 'CANCELLED')),
    fencing_token bigint NOT NULL CHECK (fencing_token > 0),
    started_at timestamptz,
    heartbeat_at timestamptz,
    completed_at timestamptz,
    error_code text,
    error_message text,
    UNIQUE (work_item_id, attempt_no),
    UNIQUE (work_item_id, fencing_token),
    FOREIGN KEY (tenant_id, work_item_id) REFERENCES orchestration.work_items(tenant_id, id)
);

CREATE TABLE runtime.worker_leases (
    work_item_id uuid PRIMARY KEY REFERENCES orchestration.work_items(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    worker_id uuid NOT NULL REFERENCES runtime.workers(id),
    attempt_id uuid NOT NULL REFERENCES runtime.execution_attempts(id) ON DELETE CASCADE,
    fencing_token bigint NOT NULL CHECK (fencing_token > 0),
    leased_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    heartbeat_at timestamptz NOT NULL,
    CHECK (expires_at > leased_at)
);

CREATE TABLE runtime.checkpoints (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    job_id uuid NOT NULL REFERENCES orchestration.jobs(id),
    work_item_id uuid REFERENCES orchestration.work_items(id),
    attempt_id uuid REFERENCES runtime.execution_attempts(id),
    checkpoint_type text NOT NULL,
    sequence_no bigint NOT NULL CHECK (sequence_no > 0),
    state_object_uri text NOT NULL,
    state_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (attempt_id, sequence_no)
);

-- Durable cross-context handoff. Runtime records the final usage before the
-- coordinator calls Billing, so a process crash cannot lose the settlement
-- request between the two local transactions.
CREATE TABLE runtime.settlement_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    work_item_id uuid NOT NULL,
    reservation_id uuid NOT NULL,
    model_call_id uuid NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    provider_usage_id text NOT NULL,
    provider_pricing_version_id uuid NOT NULL,
    commercial_pricing_version_id uuid NOT NULL,
    input_tokens bigint NOT NULL CHECK (input_tokens >= 0),
    cached_input_tokens bigint NOT NULL CHECK (cached_input_tokens >= 0),
    output_tokens bigint NOT NULL CHECK (output_tokens >= 0),
    reasoning_tokens bigint NOT NULL CHECK (reasoning_tokens >= 0),
    provider_total_cost numeric(38,12) NOT NULL CHECK (provider_total_cost >= 0),
    customer_credit_cost numeric(38,12) NOT NULL CHECK (customer_credit_cost >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    settled_at timestamptz,
    UNIQUE (tenant_id, work_item_id),
    UNIQUE (tenant_id, model_call_id)
);

CREATE TABLE artifact.artifacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    project_id uuid NOT NULL REFERENCES project.projects(id),
    job_id uuid REFERENCES orchestration.jobs(id),
    work_item_id uuid REFERENCES orchestration.work_items(id),
    artifact_type text NOT NULL,
    object_uri text NOT NULL,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE validation.validation_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    job_id uuid NOT NULL REFERENCES orchestration.jobs(id),
    validation_type text NOT NULL,
    status text NOT NULL DEFAULT 'CREATED',
    passed bigint NOT NULL DEFAULT 0 CHECK (passed >= 0),
    failed bigint NOT NULL DEFAULT 0 CHECK (failed >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE billing.billing_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    account_id uuid NOT NULL,
    billing_type text NOT NULL CHECK (billing_type IN ('PREPAID', 'POSTPAID')),
    status text NOT NULL DEFAULT 'ACTIVE',
    UNIQUE (tenant_id, account_id),
    FOREIGN KEY (tenant_id, account_id) REFERENCES identity.accounts(tenant_id, id)
);

CREATE TABLE billing.wallets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    billing_account_id uuid NOT NULL REFERENCES billing.billing_accounts(id),
    currency char(3) NOT NULL CHECK (currency = upper(currency)),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'FROZEN', 'CLOSED')),
    UNIQUE (billing_account_id, currency)
);

CREATE TABLE billing.wallet_balances (
    wallet_id uuid PRIMARY KEY REFERENCES billing.wallets(id),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    available_balance numeric(38,12) NOT NULL DEFAULT 0 CHECK (available_balance >= 0),
    reserved_balance numeric(38,12) NOT NULL DEFAULT 0 CHECK (reserved_balance >= 0),
    version bigint NOT NULL DEFAULT 0 CHECK (version >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE runtime.dispatch_intents
    ADD CONSTRAINT dispatch_intents_wallet_fk FOREIGN KEY (wallet_id) REFERENCES billing.wallets(id);

CREATE TABLE billing.idempotency_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    operation_type text NOT NULL,
    idempotency_key text NOT NULL,
    request_hash text NOT NULL,
    state text NOT NULL DEFAULT 'IN_PROGRESS' CHECK (state IN ('IN_PROGRESS', 'SUCCEEDED', 'FAILED')),
    resource_id uuid,
    response_json jsonb,
    last_error text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    expires_at timestamptz,
    UNIQUE (tenant_id, operation_type, idempotency_key)
);

CREATE TABLE billing.topups (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    wallet_id uuid NOT NULL REFERENCES billing.wallets(id),
    provider text NOT NULL,
    provider_payment_id text NOT NULL,
    amount numeric(38,12) NOT NULL CHECK (amount > 0),
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'COMPLETED', 'REJECTED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (provider, provider_payment_id)
);

CREATE TABLE billing.provider_pricing_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    effective_from timestamptz NOT NULL,
    effective_to timestamptz,
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE TABLE billing.provider_model_prices (
    pricing_version_id uuid NOT NULL REFERENCES billing.provider_pricing_versions(id),
    provider text NOT NULL,
    model text NOT NULL,
    currency char(3) NOT NULL DEFAULT 'USD',
    input_per_million numeric(38,12) NOT NULL DEFAULT 0 CHECK (input_per_million >= 0),
    cached_input_per_million numeric(38,12) NOT NULL DEFAULT 0 CHECK (cached_input_per_million >= 0),
    output_per_million numeric(38,12) NOT NULL DEFAULT 0 CHECK (output_per_million >= 0),
    reasoning_per_million numeric(38,12) NOT NULL DEFAULT 0 CHECK (reasoning_per_million >= 0),
    PRIMARY KEY (pricing_version_id, provider, model)
);

CREATE TABLE billing.commercial_pricing_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    effective_from timestamptz NOT NULL,
    effective_to timestamptz,
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE TABLE billing.commercial_model_prices (
    pricing_version_id uuid NOT NULL REFERENCES billing.commercial_pricing_versions(id),
    provider text NOT NULL,
    model text NOT NULL,
    credit_per_input_million numeric(38,12) NOT NULL DEFAULT 0 CHECK (credit_per_input_million >= 0),
    credit_per_cached_million numeric(38,12) NOT NULL DEFAULT 0 CHECK (credit_per_cached_million >= 0),
    credit_per_output_million numeric(38,12) NOT NULL DEFAULT 0 CHECK (credit_per_output_million >= 0),
    credit_per_reasoning_million numeric(38,12) NOT NULL DEFAULT 0 CHECK (credit_per_reasoning_million >= 0),
    PRIMARY KEY (pricing_version_id, provider, model)
);

CREATE TABLE ai_usage.model_calls (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    account_id uuid NOT NULL,
    project_id uuid NOT NULL REFERENCES project.projects(id),
    job_id uuid REFERENCES orchestration.jobs(id),
    stage_id uuid REFERENCES orchestration.job_stages(id),
    work_item_id uuid REFERENCES orchestration.work_items(id),
    attempt_id uuid REFERENCES runtime.execution_attempts(id),
    provider text NOT NULL,
    model text NOT NULL,
    idempotency_key text NOT NULL,
    provider_request_id text,
    status text NOT NULL DEFAULT 'CREATED' CHECK (status IN ('CREATED', 'PROVIDER_ACCEPTED', 'RUNNING', 'COMPLETE', 'FAILED', 'UNKNOWN')),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, account_id) REFERENCES identity.accounts(tenant_id, id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES project.projects(tenant_id, id)
);

CREATE TABLE ai_usage.model_call_receipts (
    model_call_id uuid PRIMARY KEY REFERENCES ai_usage.model_calls(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    request_hash text NOT NULL,
    receipt_state text NOT NULL CHECK (receipt_state IN ('CREATED', 'PROVIDER_ACCEPTED', 'COMPLETE', 'FAILED', 'UNKNOWN')),
    provider_request_id text,
    response_artifact_id uuid,
    last_provider_status text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai_usage.tool_calls (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    account_id uuid NOT NULL,
    project_id uuid NOT NULL REFERENCES project.projects(id),
    job_id uuid NOT NULL REFERENCES orchestration.jobs(id),
    stage_id uuid NOT NULL REFERENCES orchestration.job_stages(id),
    work_item_id uuid NOT NULL REFERENCES orchestration.work_items(id),
    attempt_id uuid NOT NULL REFERENCES runtime.execution_attempts(id),
    tool text NOT NULL,
    idempotency_key text NOT NULL,
    provider_request_id text,
    status text NOT NULL DEFAULT 'CREATED' CHECK (status IN ('CREATED', 'PROVIDER_ACCEPTED', 'COMPLETE', 'FAILED', 'UNKNOWN')),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (tenant_id, idempotency_key),
    UNIQUE (tenant_id, provider_request_id),
    FOREIGN KEY (tenant_id, account_id) REFERENCES identity.accounts(tenant_id, id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES project.projects(tenant_id, id),
    FOREIGN KEY (tenant_id, job_id) REFERENCES orchestration.jobs(tenant_id, id),
    FOREIGN KEY (tenant_id, stage_id) REFERENCES orchestration.job_stages(tenant_id, id),
    FOREIGN KEY (tenant_id, work_item_id) REFERENCES orchestration.work_items(tenant_id, id)
);

CREATE TABLE ai_usage.tool_call_receipts (
    tool_call_id uuid PRIMARY KEY REFERENCES ai_usage.tool_calls(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    request_hash text NOT NULL,
    receipt_state text NOT NULL CHECK (receipt_state IN ('CREATED', 'PROVIDER_ACCEPTED', 'COMPLETE', 'FAILED', 'UNKNOWN')),
    provider_request_id text,
    response_artifact_id uuid,
    last_provider_status text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE billing.credit_reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    wallet_id uuid NOT NULL REFERENCES billing.wallets(id),
    project_id uuid NOT NULL REFERENCES project.projects(id),
    job_id uuid REFERENCES orchestration.jobs(id),
    work_item_id uuid REFERENCES orchestration.work_items(id),
    model_call_id uuid REFERENCES ai_usage.model_calls(id),
    reservation_idempotency_key text NOT NULL,
    reserved_amount numeric(38,12) NOT NULL CHECK (reserved_amount > 0),
    consumed_amount numeric(38,12) NOT NULL DEFAULT 0 CHECK (consumed_amount >= 0),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'SETTLED', 'RELEASED', 'EXPIRED')),
    expires_at timestamptz,
    last_transition_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    settled_at timestamptz,
    CHECK (consumed_amount <= reserved_amount),
    UNIQUE (tenant_id, reservation_idempotency_key)
);

CREATE TABLE billing.usage_meter_events (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    reservation_id uuid NOT NULL REFERENCES billing.credit_reservations(id),
    model_call_id uuid NOT NULL REFERENCES ai_usage.model_calls(id),
    sequence_no bigint NOT NULL CHECK (sequence_no > 0),
    cumulative_input_tokens bigint NOT NULL DEFAULT 0 CHECK (cumulative_input_tokens >= 0),
    cumulative_cached_input_tokens bigint NOT NULL DEFAULT 0 CHECK (cumulative_cached_input_tokens >= 0),
    cumulative_output_tokens bigint NOT NULL DEFAULT 0 CHECK (cumulative_output_tokens >= 0),
    cumulative_reasoning_tokens bigint NOT NULL DEFAULT 0 CHECK (cumulative_reasoning_tokens >= 0),
    metered_provider_cost numeric(38,12) NOT NULL DEFAULT 0 CHECK (metered_provider_cost >= 0),
    metered_credit_cost numeric(38,12) NOT NULL DEFAULT 0 CHECK (metered_credit_cost >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (model_call_id, sequence_no)
);

CREATE TABLE billing.token_usage_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    model_call_id uuid NOT NULL REFERENCES ai_usage.model_calls(id),
    reservation_id uuid REFERENCES billing.credit_reservations(id),
    provider text NOT NULL,
    model text NOT NULL,
    provider_usage_id text,
    provider_pricing_version_id uuid NOT NULL REFERENCES billing.provider_pricing_versions(id),
    commercial_pricing_version_id uuid NOT NULL REFERENCES billing.commercial_pricing_versions(id),
    input_tokens bigint NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    cached_input_tokens bigint NOT NULL DEFAULT 0 CHECK (cached_input_tokens >= 0),
    output_tokens bigint NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    reasoning_tokens bigint NOT NULL DEFAULT 0 CHECK (reasoning_tokens >= 0),
    provider_total_cost numeric(38,12) NOT NULL DEFAULT 0 CHECK (provider_total_cost >= 0),
    customer_credit_cost numeric(38,12) NOT NULL DEFAULT 0 CHECK (customer_credit_cost >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (model_call_id),
    UNIQUE (provider, provider_usage_id)
);

CREATE TABLE billing.ledger_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    wallet_id uuid NOT NULL REFERENCES billing.wallets(id),
    entry_type text NOT NULL CHECK (entry_type IN ('TOPUP', 'USAGE', 'REFUND', 'BONUS', 'ADJUSTMENT')),
    reference_type text NOT NULL,
    reference_id uuid,
    amount numeric(38,12) NOT NULL CHECK (amount <> 0),
    idempotency_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE billing.billing_journals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    journal_type text NOT NULL,
    reference_type text NOT NULL,
    reference_id uuid,
    idempotency_key text NOT NULL,
    memo text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE billing.billing_journal_lines (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    journal_id uuid NOT NULL REFERENCES billing.billing_journals(id) ON DELETE CASCADE,
    account_code text NOT NULL,
    currency char(3) NOT NULL,
    debit numeric(38,12) NOT NULL DEFAULT 0 CHECK (debit >= 0),
    credit numeric(38,12) NOT NULL DEFAULT 0 CHECK (credit >= 0),
    wallet_id uuid REFERENCES billing.wallets(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((debit = 0 AND credit > 0) OR (credit = 0 AND debit > 0))
);

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
    publish_attempts integer NOT NULL DEFAULT 0 CHECK (publish_attempts >= 0),
    last_error text,
    claim_token uuid,
    claimed_until timestamptz
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
    progress numeric(5,2) NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    tokens_consumed bigint NOT NULL DEFAULT 0,
    credits_consumed numeric(38,12) NOT NULL DEFAULT 0,
    metered_credits numeric(38,12) NOT NULL DEFAULT 0,
    estimated_remaining_credits numeric(38,12) NOT NULL DEFAULT 0,
    estimated_remaining_wall_clock_ms bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_work_ready ON orchestration.work_items(tenant_id, status, priority, ready_at, created_at)
WHERE status IN ('READY', 'RETRY_WAIT');
CREATE INDEX idx_dispatch_state ON runtime.dispatch_intents(state, updated_at);
CREATE INDEX idx_lease_expiry ON runtime.worker_leases(expires_at);
CREATE INDEX idx_active_reservations ON billing.credit_reservations(wallet_id, expires_at) WHERE status = 'ACTIVE';
CREATE INDEX idx_meter_call_seq ON billing.usage_meter_events(model_call_id, sequence_no DESC);
CREATE INDEX idx_outbox_unpublished ON observability.outbox_events(id) WHERE published_at IS NULL;
CREATE INDEX idx_outbox_claim_expiry ON observability.outbox_events(claimed_until) WHERE published_at IS NULL;

CREATE OR REPLACE FUNCTION public.current_tenant_id() RETURNS uuid
LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$;

CREATE OR REPLACE FUNCTION runtime.allocate_fence(p_work_item_id uuid) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = runtime, orchestration, public AS $$
DECLARE v_token bigint;
BEGIN
    IF public.current_tenant_id() IS NULL OR NOT EXISTS (
        SELECT 1 FROM orchestration.work_items wi
         WHERE wi.id = p_work_item_id AND wi.tenant_id = public.current_tenant_id()
    ) THEN
        RAISE EXCEPTION 'FENCE_TENANT_CONTEXT_REQUIRED';
    END IF;
    INSERT INTO runtime.work_item_fence_counters(work_item_id, next_token)
    VALUES (p_work_item_id, 1)
    ON CONFLICT (work_item_id)
    DO UPDATE SET next_token = runtime.work_item_fence_counters.next_token + 1
    RETURNING next_token INTO v_token;
    RETURN v_token;
END;
$$;

CREATE OR REPLACE FUNCTION runtime.recovery_candidates(p_limit integer)
RETURNS SETOF runtime.dispatch_intents
LANGUAGE sql SECURITY DEFINER SET search_path = runtime, public AS $$
    SELECT di.* FROM runtime.dispatch_intents di
     WHERE di.state NOT IN ('COMPLETED', 'ABORTED')
     ORDER BY di.updated_at, di.id
     LIMIT LEAST(GREATEST(coalesce(p_limit, 1), 1), 500)
$$;

CREATE OR REPLACE FUNCTION runtime.select_fair_ready_work_items(p_limit integer)
RETURNS TABLE (
    tenant_id uuid,
    project_id uuid,
    job_id uuid,
    work_item_id uuid,
    work_type text,
    priority integer,
    estimated_credits numeric,
    ready_at timestamptz,
    created_at timestamptz
)
LANGUAGE sql SECURITY DEFINER SET search_path = runtime, orchestration, public AS $$
    WITH candidates AS (
        SELECT wi.tenant_id, j.project_id, wi.job_id, wi.id AS work_item_id,
               wi.work_type, j.priority, wi.estimated_cost AS estimated_credits,
               wi.ready_at, wi.created_at,
               row_number() OVER (
                   PARTITION BY wi.tenant_id
                   ORDER BY j.priority DESC, wi.ready_at NULLS LAST, wi.created_at, wi.id
               ) AS tenant_rank
          FROM orchestration.work_items wi
          JOIN orchestration.jobs j
            ON j.tenant_id = wi.tenant_id AND j.id = wi.job_id
         WHERE wi.status IN ('READY', 'RETRY_WAIT')
           AND NOT EXISTS (
               SELECT 1
                 FROM orchestration.work_item_dependencies dep
                 JOIN orchestration.work_items blocker
                   ON blocker.tenant_id = dep.tenant_id AND blocker.id = dep.depends_on_work_item_id
                WHERE dep.tenant_id = wi.tenant_id
                  AND dep.work_item_id = wi.id
                  AND blocker.status <> 'SUCCEEDED'
           )
    )
    SELECT tenant_id, project_id, job_id, work_item_id, work_type, priority,
           estimated_credits, ready_at, created_at
      FROM candidates
     ORDER BY tenant_rank, priority DESC, ready_at NULLS LAST, created_at, work_item_id
     LIMIT LEAST(GREATEST(coalesce(p_limit, 1), 1), 1000)
$$;

CREATE OR REPLACE FUNCTION observability.claim_outbox(p_limit integer, p_claim_token uuid, p_claim_seconds integer)
RETURNS TABLE (id bigint, tenant_id uuid, aggregate_type text, aggregate_id uuid, event_type text, payload_json text, claim_token uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = observability, public AS $$
BEGIN
    IF p_claim_token IS NULL OR p_claim_seconds < 1 OR p_claim_seconds > 3600 THEN
        RAISE EXCEPTION 'OUTBOX_CLAIM_ARGUMENT_INVALID';
    END IF;
    WITH candidates AS (
        SELECT e.id FROM observability.outbox_events e
         WHERE e.published_at IS NULL AND (e.claimed_until IS NULL OR e.claimed_until < now())
         ORDER BY e.id LIMIT LEAST(GREATEST(coalesce(p_limit, 1), 1), 1000) FOR UPDATE SKIP LOCKED
    )
    UPDATE observability.outbox_events e
       SET claim_token = p_claim_token, claimed_until = now() + make_interval(secs => p_claim_seconds),
           publish_attempts = e.publish_attempts + 1, last_error = NULL
     WHERE e.id IN (SELECT c.id FROM candidates c);
    RETURN QUERY SELECT e.id, e.tenant_id, e.aggregate_type, e.aggregate_id, e.event_type,
                        e.payload::text, e.claim_token
                   FROM observability.outbox_events e
                  WHERE e.claim_token = p_claim_token AND e.published_at IS NULL
                  ORDER BY e.id;
END;
$$;

CREATE OR REPLACE FUNCTION observability.mark_outbox_published(p_claim_token uuid, p_event_id bigint)
RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path = observability, public AS $$
    UPDATE observability.outbox_events
       SET published_at = now(), claimed_until = NULL, claim_token = NULL
     WHERE id = p_event_id AND claim_token = p_claim_token AND published_at IS NULL
    RETURNING TRUE
$$;

CREATE OR REPLACE FUNCTION observability.mark_outbox_failed(p_claim_token uuid, p_event_id bigint, p_error text)
RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path = observability, public AS $$
    UPDATE observability.outbox_events
       SET last_error = left(coalesce(p_error, 'UNSPECIFIED'), 1000), claimed_until = NULL, claim_token = NULL
     WHERE id = p_event_id AND claim_token = p_claim_token AND published_at IS NULL
    RETURNING TRUE
$$;

-- The service roles are installed by deploy/production/postgres/production_runtime_roles.sql.
-- Until an operator explicitly grants these functions to the correct role, no
-- ordinary database session can use an all-tenant security-definer path.
REVOKE ALL ON FUNCTION runtime.allocate_fence(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION runtime.recovery_candidates(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION runtime.select_fair_ready_work_items(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION observability.claim_outbox(integer, uuid, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION observability.mark_outbox_published(uuid, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION observability.mark_outbox_failed(uuid, bigint, text) FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.forbid_append_only_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'APPEND_ONLY_MUTATION_FORBIDDEN'; END;
$$;

CREATE TRIGGER billing_ledger_append_only BEFORE UPDATE OR DELETE ON billing.ledger_entries FOR EACH ROW EXECUTE FUNCTION public.forbid_append_only_mutation();
CREATE TRIGGER billing_journal_append_only BEFORE UPDATE OR DELETE ON billing.billing_journals FOR EACH ROW EXECUTE FUNCTION public.forbid_append_only_mutation();
CREATE TRIGGER billing_journal_lines_append_only BEFORE UPDATE OR DELETE ON billing.billing_journal_lines FOR EACH ROW EXECUTE FUNCTION public.forbid_append_only_mutation();
CREATE TRIGGER usage_meter_append_only BEFORE UPDATE OR DELETE ON billing.usage_meter_events FOR EACH ROW EXECUTE FUNCTION public.forbid_append_only_mutation();
CREATE TRIGGER token_usage_append_only BEFORE UPDATE OR DELETE ON billing.token_usage_events FOR EACH ROW EXECUTE FUNCTION public.forbid_append_only_mutation();

-- Request-scoped RLS. Background functions are intentionally narrow and
-- SECURITY DEFINER; no application role receives a blanket bypass.
ALTER TABLE identity.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity.accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE project.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE project.repository_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.job_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.work_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE orchestration.work_item_dependencies ENABLE ROW LEVEL SECURITY;
ALTER TABLE runtime.dispatch_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE runtime.execution_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE runtime.worker_leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE runtime.checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE runtime.settlement_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifact.artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE validation.validation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing.billing_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing.wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing.wallet_balances ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing.idempotency_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing.topups ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing.credit_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing.usage_meter_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing.token_usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing.ledger_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing.billing_journals ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing.billing_journal_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_usage.model_calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_usage.model_call_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_usage.tool_calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_usage.tool_call_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE observability.outbox_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE observability.project_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE observability.progress_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON identity.tenants USING (id = public.current_tenant_id()) WITH CHECK (id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON identity.accounts USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON project.projects USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON project.repository_snapshots USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON orchestration.jobs USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON orchestration.job_stages USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON orchestration.work_items USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON orchestration.work_item_dependencies USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON runtime.dispatch_intents USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON runtime.execution_attempts USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON runtime.worker_leases USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON runtime.checkpoints USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON runtime.settlement_requests USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON artifact.artifacts USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON validation.validation_runs USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON billing.billing_accounts USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON billing.wallets USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON billing.wallet_balances USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON billing.idempotency_records USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON billing.topups USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON billing.credit_reservations USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON billing.usage_meter_events USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON billing.token_usage_events USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON billing.ledger_entries USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON billing.billing_journals USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON billing.billing_journal_lines USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON ai_usage.model_calls USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON ai_usage.model_call_receipts USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON ai_usage.tool_calls USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON ai_usage.tool_call_receipts USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON observability.outbox_events USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON observability.project_events USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
CREATE POLICY tenant_isolation ON observability.progress_snapshots USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());

CREATE OR REPLACE VIEW billing.v_wallet_reconciliation AS
WITH ledger_agg AS (
    SELECT wallet_id, SUM(amount) AS posted_effect
      FROM billing.ledger_entries GROUP BY wallet_id
), reservation_agg AS (
    SELECT wallet_id, COALESCE(SUM(reserved_amount - consumed_amount) FILTER (WHERE status = 'ACTIVE'), 0) AS active_reserved
      FROM billing.credit_reservations GROUP BY wallet_id
)
SELECT w.id AS wallet_id, w.tenant_id, wb.available_balance, wb.reserved_balance,
       COALESCE(la.posted_effect, 0) AS posted_effect, COALESCE(ra.active_reserved, 0) AS active_reserved
  FROM billing.wallets w JOIN billing.wallet_balances wb ON wb.wallet_id = w.id
  LEFT JOIN ledger_agg la ON la.wallet_id = w.id
  LEFT JOIN reservation_agg ra ON ra.wallet_id = w.id;

CREATE OR REPLACE VIEW billing.v_model_margin AS
SELECT model_call_id, provider, model, provider_total_cost, customer_credit_cost,
       customer_credit_cost - provider_total_cost AS nominal_margin_value
  FROM billing.token_usage_events;
