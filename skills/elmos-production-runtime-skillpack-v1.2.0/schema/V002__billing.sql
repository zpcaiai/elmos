CREATE TABLE billing.billing_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    account_id uuid NOT NULL REFERENCES identity.accounts(id),
    billing_type text NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE',
    UNIQUE(tenant_id, account_id)
);

CREATE TABLE billing.wallets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    billing_account_id uuid NOT NULL REFERENCES billing.billing_accounts(id),
    currency text NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE',
    UNIQUE(billing_account_id, currency)
);

CREATE TABLE billing.wallet_balances (
    wallet_id uuid PRIMARY KEY REFERENCES billing.wallets(id),
    available_balance numeric(38,12) NOT NULL DEFAULT 0 CHECK(available_balance >= 0),
    reserved_balance numeric(38,12) NOT NULL DEFAULT 0 CHECK(reserved_balance >= 0),
    version bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE billing.idempotency_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    operation_type text NOT NULL,
    idempotency_key text NOT NULL,
    request_hash text NOT NULL,
    state text NOT NULL DEFAULT 'IN_PROGRESS',
    resource_id uuid,
    response_json jsonb,
    last_error text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    expires_at timestamptz,
    UNIQUE(tenant_id, operation_type, idempotency_key)
);

CREATE TABLE billing.topups (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    wallet_id uuid NOT NULL REFERENCES billing.wallets(id),
    provider text NOT NULL,
    provider_payment_id text NOT NULL,
    amount numeric(38,12) NOT NULL CHECK(amount > 0),
    status text NOT NULL DEFAULT 'PENDING',
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE(provider, provider_payment_id)
);

CREATE TABLE billing.provider_pricing_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    effective_from timestamptz NOT NULL,
    effective_to timestamptz
);

CREATE TABLE billing.provider_model_prices (
    pricing_version_id uuid NOT NULL REFERENCES billing.provider_pricing_versions(id),
    provider text NOT NULL,
    model text NOT NULL,
    currency text NOT NULL DEFAULT 'USD',
    input_per_million numeric(38,12) NOT NULL DEFAULT 0,
    cached_input_per_million numeric(38,12) NOT NULL DEFAULT 0,
    output_per_million numeric(38,12) NOT NULL DEFAULT 0,
    reasoning_per_million numeric(38,12) NOT NULL DEFAULT 0,
    PRIMARY KEY(pricing_version_id, provider, model)
);

CREATE TABLE billing.commercial_pricing_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    effective_from timestamptz NOT NULL,
    effective_to timestamptz
);

CREATE TABLE billing.commercial_model_prices (
    pricing_version_id uuid NOT NULL REFERENCES billing.commercial_pricing_versions(id),
    provider text NOT NULL,
    model text NOT NULL,
    credit_per_input_million numeric(38,12) NOT NULL DEFAULT 0,
    credit_per_cached_million numeric(38,12) NOT NULL DEFAULT 0,
    credit_per_output_million numeric(38,12) NOT NULL DEFAULT 0,
    credit_per_reasoning_million numeric(38,12) NOT NULL DEFAULT 0,
    PRIMARY KEY(pricing_version_id, provider, model)
);

CREATE TABLE billing.credit_reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    wallet_id uuid NOT NULL REFERENCES billing.wallets(id),
    project_id uuid NOT NULL REFERENCES project.projects(id),
    job_id uuid REFERENCES orchestration.jobs(id),
    work_item_id uuid REFERENCES orchestration.work_items(id),
    model_call_id uuid,
    reserved_amount numeric(38,12) NOT NULL CHECK(reserved_amount > 0),
    consumed_amount numeric(38,12) NOT NULL DEFAULT 0 CHECK(consumed_amount >= 0),
    status text NOT NULL DEFAULT 'ACTIVE',
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    settled_at timestamptz,
    CHECK(consumed_amount <= reserved_amount)
);

CREATE TABLE ai_usage.model_calls (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    account_id uuid NOT NULL REFERENCES identity.accounts(id),
    project_id uuid NOT NULL REFERENCES project.projects(id),
    job_id uuid REFERENCES orchestration.jobs(id),
    stage_id uuid REFERENCES orchestration.job_stages(id),
    work_item_id uuid REFERENCES orchestration.work_items(id),
    attempt_id uuid REFERENCES runtime.execution_attempts(id),
    provider text NOT NULL,
    model text NOT NULL,
    idempotency_key text NOT NULL,
    provider_request_id text,
    status text NOT NULL DEFAULT 'CREATED',
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE(tenant_id, idempotency_key)
);

CREATE TABLE ai_usage.model_call_receipts (
    model_call_id uuid PRIMARY KEY REFERENCES ai_usage.model_calls(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    request_hash text NOT NULL,
    receipt_state text NOT NULL,
    provider_request_id text,
    response_artifact_id uuid,
    last_provider_status text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE billing.credit_reservations
ADD CONSTRAINT fk_reservation_model_call
FOREIGN KEY(model_call_id) REFERENCES ai_usage.model_calls(id);

CREATE TABLE billing.usage_meter_events (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    reservation_id uuid NOT NULL REFERENCES billing.credit_reservations(id),
    model_call_id uuid NOT NULL REFERENCES ai_usage.model_calls(id),
    sequence_no bigint NOT NULL,
    cumulative_input_tokens bigint NOT NULL DEFAULT 0,
    cumulative_cached_input_tokens bigint NOT NULL DEFAULT 0,
    cumulative_output_tokens bigint NOT NULL DEFAULT 0,
    cumulative_reasoning_tokens bigint NOT NULL DEFAULT 0,
    metered_provider_cost numeric(38,12) NOT NULL DEFAULT 0,
    metered_credit_cost numeric(38,12) NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(model_call_id, sequence_no)
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
    input_tokens bigint NOT NULL DEFAULT 0,
    cached_input_tokens bigint NOT NULL DEFAULT 0,
    output_tokens bigint NOT NULL DEFAULT 0,
    reasoning_tokens bigint NOT NULL DEFAULT 0,
    provider_total_cost numeric(38,12) NOT NULL DEFAULT 0,
    customer_credit_cost numeric(38,12) NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(provider, provider_usage_id)
);

CREATE TABLE billing.ledger_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    wallet_id uuid NOT NULL REFERENCES billing.wallets(id),
    entry_type text NOT NULL,
    reference_type text NOT NULL,
    reference_id uuid,
    amount numeric(38,12) NOT NULL,
    idempotency_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, idempotency_key)
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
    UNIQUE(tenant_id, idempotency_key)
);

CREATE TABLE billing.billing_journal_lines (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    journal_id uuid NOT NULL REFERENCES billing.billing_journals(id) ON DELETE CASCADE,
    account_code text NOT NULL,
    currency text NOT NULL,
    debit numeric(38,12) NOT NULL DEFAULT 0 CHECK(debit >= 0),
    credit numeric(38,12) NOT NULL DEFAULT 0 CHECK(credit >= 0),
    wallet_id uuid REFERENCES billing.wallets(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK((debit = 0 AND credit > 0) OR (credit = 0 AND debit > 0))
);

CREATE INDEX idx_active_reservations
ON billing.credit_reservations(wallet_id, expires_at)
WHERE status = 'ACTIVE';

CREATE INDEX idx_meter_call_seq
ON billing.usage_meter_events(model_call_id, sequence_no DESC);
