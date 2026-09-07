-- Elmos hybrid billing reference schema (PostgreSQL 15+).
-- Adapt names and migration conventions to the target repository.
-- Money and credits use integer units. Never use floating point for financial state.

CREATE SCHEMA IF NOT EXISTS elmos_billing;
SET search_path = elmos_billing, public;

CREATE TABLE IF NOT EXISTS price_books (
    id                  text PRIMARY KEY,
    logical_key         text NOT NULL,
    version             integer NOT NULL CHECK (version > 0),
    scope               text NOT NULL,
    currency            char(3) NOT NULL,
    status              text NOT NULL CHECK (status IN ('draft','in_review','approved','scheduled','active','retired')),
    valid_from          timestamptz NOT NULL,
    valid_to            timestamptz,
    content_hash        text NOT NULL,
    approved_by         text,
    approved_at         timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (logical_key, version),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE IF NOT EXISTS price_rates (
    id                  text PRIMARY KEY,
    price_book_id       text NOT NULL REFERENCES price_books(id),
    charge_code         text NOT NULL,
    unit                text NOT NULL,
    unit_size           bigint NOT NULL CHECK (unit_size > 0),
    amount_minor        bigint NOT NULL CHECK (amount_minor >= 0),
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (price_book_id, charge_code, unit)
);

CREATE TABLE IF NOT EXISTS vendor_rate_books (
    id                  text PRIMARY KEY,
    provider            text NOT NULL,
    version             integer NOT NULL CHECK (version > 0),
    currency            char(3) NOT NULL,
    valid_from          timestamptz NOT NULL,
    valid_to            timestamptz,
    status              text NOT NULL CHECK (status IN ('draft','approved','active','retired')),
    content_hash        text NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider, version),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE IF NOT EXISTS vendor_rates (
    id                  text PRIMARY KEY,
    rate_book_id        text NOT NULL REFERENCES vendor_rate_books(id),
    resource_code       text NOT NULL,
    unit                text NOT NULL,
    unit_size           bigint NOT NULL CHECK (unit_size > 0),
    amount_minor        bigint NOT NULL CHECK (amount_minor >= 0),
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (rate_book_id, resource_code, unit)
);

CREATE TABLE IF NOT EXISTS billing_accounts (
    id                  text PRIMARY KEY,
    tenant_id           text NOT NULL,
    account_type        text NOT NULL CHECK (account_type IN ('prepaid','postpaid','hybrid')),
    default_currency    char(3) NOT NULL,
    status              text NOT NULL CHECK (status IN ('active','past_due','suspended','closed')),
    credit_limit_minor  bigint NOT NULL DEFAULT 0 CHECK (credit_limit_minor >= 0),
    terms_version       text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS wallets (
    id                  text PRIMARY KEY,
    tenant_id           text NOT NULL,
    billing_account_id  text NOT NULL REFERENCES billing_accounts(id),
    unit_type           text NOT NULL CHECK (unit_type IN ('money','credit')),
    currency_or_unit    text NOT NULL,
    status              text NOT NULL CHECK (status IN ('active','frozen','closed')),
    version             bigint NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, billing_account_id, unit_type, currency_or_unit)
);

CREATE TABLE IF NOT EXISTS ledger_accounts (
    id                  text PRIMARY KEY,
    tenant_id           text,
    wallet_id           text REFERENCES wallets(id),
    account_code        text NOT NULL,
    account_class       text NOT NULL CHECK (account_class IN ('asset','liability','equity','revenue','expense','contra_revenue','suspense')),
    unit_type           text NOT NULL CHECK (unit_type IN ('money','credit')),
    currency_or_unit    text NOT NULL,
    status              text NOT NULL DEFAULT 'active' CHECK (status IN ('active','closed')),
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, account_code, currency_or_unit)
);

CREATE TABLE IF NOT EXISTS ledger_transactions (
    id                  text PRIMARY KEY,
    tenant_id           text NOT NULL,
    operation_type      text NOT NULL,
    idempotency_key     text NOT NULL,
    correlation_id      text NOT NULL,
    causation_id        text,
    reference_type      text,
    reference_id        text,
    status              text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','posted','reversed')),
    policy_version      text,
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by          text NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    posted_at           timestamptz,
    UNIQUE (tenant_id, operation_type, idempotency_key)
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id                  text PRIMARY KEY,
    transaction_id      text NOT NULL REFERENCES ledger_transactions(id),
    account_id          text NOT NULL REFERENCES ledger_accounts(id),
    side                text NOT NULL CHECK (side IN ('debit','credit')),
    amount_units        bigint NOT NULL CHECK (amount_units > 0),
    currency_or_unit    text NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_tx ON ledger_entries(transaction_id);
CREATE INDEX IF NOT EXISTS idx_ledger_tx_tenant_created ON ledger_transactions(tenant_id, created_at);

CREATE OR REPLACE FUNCTION assert_transaction_balanced_on_post() RETURNS trigger AS $$
DECLARE
    debit_total bigint;
    credit_total bigint;
    unit_count integer;
BEGIN
    IF NEW.status = 'posted' AND OLD.status <> 'posted' THEN
        SELECT
            COALESCE(SUM(amount_units) FILTER (WHERE side='debit'), 0),
            COALESCE(SUM(amount_units) FILTER (WHERE side='credit'), 0),
            COUNT(DISTINCT currency_or_unit)
        INTO debit_total, credit_total, unit_count
        FROM ledger_entries
        WHERE transaction_id = NEW.id;

        IF debit_total = 0 OR debit_total <> credit_total OR unit_count <> 1 THEN
            RAISE EXCEPTION 'ledger transaction % is not balanced: debit %, credit %, units %',
                NEW.id, debit_total, credit_total, unit_count;
        END IF;
        NEW.posted_at := COALESCE(NEW.posted_at, now());
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ledger_post_balance ON ledger_transactions;
CREATE TRIGGER trg_ledger_post_balance
BEFORE UPDATE OF status ON ledger_transactions
FOR EACH ROW EXECUTE FUNCTION assert_transaction_balanced_on_post();

CREATE OR REPLACE FUNCTION prevent_posted_ledger_mutation() RETURNS trigger AS $$
DECLARE tx_status text;
BEGIN
    SELECT status INTO tx_status FROM ledger_transactions WHERE id = COALESCE(OLD.transaction_id, NEW.transaction_id);
    IF tx_status = 'posted' THEN
        RAISE EXCEPTION 'posted ledger entries are immutable';
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ledger_entry_immutable ON ledger_entries;
CREATE TRIGGER trg_ledger_entry_immutable
BEFORE UPDATE OR DELETE ON ledger_entries
FOR EACH ROW EXECUTE FUNCTION prevent_posted_ledger_mutation();

CREATE TABLE IF NOT EXISTS wallet_balance_projection (
    wallet_id               text PRIMARY KEY REFERENCES wallets(id),
    tenant_id               text NOT NULL,
    available_units         bigint NOT NULL DEFAULT 0,
    reserved_units          bigint NOT NULL DEFAULT 0,
    paid_units              bigint NOT NULL DEFAULT 0,
    promotional_units       bigint NOT NULL DEFAULT 0,
    consumed_units          bigint NOT NULL DEFAULT 0,
    refunded_units          bigint NOT NULL DEFAULT 0,
    projection_version      bigint NOT NULL DEFAULT 0,
    source_ledger_cursor    text,
    rebuilt_at              timestamptz,
    updated_at              timestamptz NOT NULL DEFAULT now(),
    CHECK (reserved_units >= 0),
    CHECK (paid_units >= 0),
    CHECK (promotional_units >= 0)
);

CREATE TABLE IF NOT EXISTS usage_events (
    id                      text PRIMARY KEY,
    tenant_id               text NOT NULL,
    source_system           text NOT NULL,
    source_event_id         text NOT NULL,
    task_id                 text NOT NULL,
    run_id                  text NOT NULL,
    node_id                 text,
    provider                text,
    model                   text,
    resource_code           text NOT NULL,
    quantity_value          numeric(38, 12) NOT NULL CHECK (quantity_value >= 0),
    quantity_unit           text NOT NULL,
    occurred_at             timestamptz NOT NULL,
    received_at             timestamptz NOT NULL DEFAULT now(),
    raw_payload_hash        text NOT NULL,
    billability             text NOT NULL CHECK (billability IN ('customer','platform','free','failed_retry','byok_excluded','review')),
    vendor_rate_book_id     text REFERENCES vendor_rate_books(id),
    internal_cost_minor     bigint,
    price_book_id           text REFERENCES price_books(id),
    customer_charge_minor   bigint,
    correction_of_event_id  text REFERENCES usage_events(id),
    settlement_status       text NOT NULL DEFAULT 'open' CHECK (settlement_status IN ('open','rated','settled','adjusted','review')),
    metadata                jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (tenant_id, source_system, source_event_id)
);

CREATE INDEX IF NOT EXISTS idx_usage_task_run ON usage_events(tenant_id, task_id, run_id, occurred_at);

CREATE TABLE IF NOT EXISTS task_estimates (
    id                      text PRIMARY KEY,
    tenant_id               text NOT NULL,
    task_id                 text NOT NULL,
    scope_hash              text NOT NULL,
    repository_commit       text,
    estimator_version       text NOT NULL,
    quality_mode            text NOT NULL CHECK (quality_mode IN ('economy','balanced','best_quality')),
    cost_p50_minor          bigint NOT NULL CHECK (cost_p50_minor >= 0),
    cost_p80_minor          bigint NOT NULL CHECK (cost_p80_minor >= cost_p50_minor),
    cost_p90_minor          bigint NOT NULL CHECK (cost_p90_minor >= cost_p80_minor),
    machine_runtime_p50_s   bigint NOT NULL CHECK (machine_runtime_p50_s >= 0),
    machine_runtime_p90_s   bigint NOT NULL CHECK (machine_runtime_p90_s >= machine_runtime_p50_s),
    human_reference_hours   numeric(12,2),
    confidence              numeric(5,4) CHECK (confidence BETWEEN 0 AND 1),
    features                jsonb NOT NULL,
    risk_factors            jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS task_quotes (
    id                      text PRIMARY KEY,
    tenant_id               text NOT NULL,
    task_id                 text NOT NULL,
    estimate_id             text NOT NULL REFERENCES task_estimates(id),
    price_book_id           text NOT NULL REFERENCES price_books(id),
    scope_hash              text NOT NULL,
    status                  text NOT NULL CHECK (status IN ('draft','offered','accepted','expired','canceled','superseded')),
    currency                char(3) NOT NULL,
    estimate_min_minor      bigint NOT NULL CHECK (estimate_min_minor >= 0),
    estimate_max_minor      bigint NOT NULL CHECK (estimate_max_minor >= estimate_min_minor),
    hard_cap_minor          bigint NOT NULL CHECK (hard_cap_minor >= estimate_max_minor),
    accepted_by             text,
    accepted_at             timestamptz,
    expires_at              timestamptz NOT NULL,
    quote_snapshot          jsonb NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS budget_authorizations (
    id                      text PRIMARY KEY,
    tenant_id               text NOT NULL,
    quote_id                text NOT NULL REFERENCES task_quotes(id),
    wallet_id               text REFERENCES wallets(id),
    ledger_reserve_tx_id    text REFERENCES ledger_transactions(id),
    status                  text NOT NULL CHECK (status IN ('requested','active','partially_captured','captured','released','expired','review')),
    authorized_units        bigint NOT NULL CHECK (authorized_units >= 0),
    captured_units          bigint NOT NULL DEFAULT 0 CHECK (captured_units >= 0),
    released_units          bigint NOT NULL DEFAULT 0 CHECK (released_units >= 0),
    version                 bigint NOT NULL DEFAULT 0,
    expires_at              timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now(),
    CHECK (captured_units + released_units <= authorized_units)
);

CREATE TABLE IF NOT EXISTS task_runs (
    id                      text PRIMARY KEY,
    tenant_id               text NOT NULL,
    task_id                 text NOT NULL,
    quote_id                text NOT NULL REFERENCES task_quotes(id),
    authorization_id        text NOT NULL REFERENCES budget_authorizations(id),
    status                  text NOT NULL CHECK (status IN ('authorized','running','paused_budget','completed','failed','canceled','settling','settled','settlement_review')),
    current_node_id         text,
    input_hash              text NOT NULL,
    repository_commit       text,
    execution_state         jsonb NOT NULL DEFAULT '{}'::jsonb,
    estimated_remaining_minor bigint,
    started_at              timestamptz,
    completed_at            timestamptz,
    updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_contracts (
    id                      text PRIMARY KEY,
    tenant_id               text NOT NULL,
    contract_type           text NOT NULL CHECK (contract_type IN ('discovery','capped','fixed')),
    status                  text NOT NULL CHECK (status IN ('draft','proposed','accepted','active','paused','completed','terminated','settled')),
    currency                char(3) NOT NULL,
    price_minor             bigint NOT NULL CHECK (price_minor >= 0),
    cap_minor               bigint CHECK (cap_minor IS NULL OR cap_minor >= price_minor),
    scope_hash              text NOT NULL,
    source_repository_hash  text NOT NULL,
    requirements_version    text NOT NULL,
    acceptance_snapshot     jsonb NOT NULL,
    included_revisions      integer NOT NULL DEFAULT 0 CHECK (included_revisions >= 0),
    exclusions              jsonb NOT NULL DEFAULT '[]'::jsonb,
    price_book_id           text NOT NULL REFERENCES price_books(id),
    contract_version        integer NOT NULL CHECK (contract_version > 0),
    accepted_by             text,
    accepted_at             timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_milestones (
    id                      text PRIMARY KEY,
    tenant_id               text NOT NULL,
    project_contract_id     text NOT NULL REFERENCES project_contracts(id),
    sequence_no             integer NOT NULL CHECK (sequence_no > 0),
    status                  text NOT NULL CHECK (status IN ('planned','in_progress','review','accepted','rejected','waived')),
    amount_minor            bigint NOT NULL CHECK (amount_minor >= 0),
    acceptance_snapshot     jsonb NOT NULL,
    evidence_uri            text,
    accepted_by             text,
    accepted_at             timestamptz,
    UNIQUE (project_contract_id, sequence_no)
);

CREATE TABLE IF NOT EXISTS change_orders (
    id                      text PRIMARY KEY,
    tenant_id               text NOT NULL,
    project_contract_id     text NOT NULL REFERENCES project_contracts(id),
    status                  text NOT NULL CHECK (status IN ('requested','proposed','approved','rejected','canceled','applied')),
    reason                  text NOT NULL,
    old_scope_hash          text NOT NULL,
    new_scope_hash          text NOT NULL,
    price_delta_minor       bigint NOT NULL,
    schedule_delta_seconds  bigint NOT NULL DEFAULT 0,
    requested_by            text NOT NULL,
    approved_by             text,
    approved_at             timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plans (
    id                      text PRIMARY KEY,
    logical_key             text NOT NULL,
    version                 integer NOT NULL CHECK (version > 0),
    status                  text NOT NULL CHECK (status IN ('draft','approved','active','retired')),
    billing_period          text NOT NULL CHECK (billing_period IN ('none','monthly','annual','custom')),
    price_book_id           text NOT NULL REFERENCES price_books(id),
    entitlements            jsonb NOT NULL,
    included_credit_policy  jsonb NOT NULL DEFAULT '{}'::jsonb,
    valid_from              timestamptz NOT NULL,
    valid_to                timestamptz,
    UNIQUE (logical_key, version)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id                      text PRIMARY KEY,
    tenant_id               text NOT NULL,
    billing_account_id      text NOT NULL REFERENCES billing_accounts(id),
    plan_id                 text NOT NULL REFERENCES plans(id),
    status                  text NOT NULL CHECK (status IN ('draft','trialing','active','past_due','suspended','paused','cancel_at_period_end','canceled')),
    seat_count              integer NOT NULL DEFAULT 1 CHECK (seat_count >= 0),
    billing_anchor          timestamptz NOT NULL,
    current_period_start    timestamptz NOT NULL,
    current_period_end      timestamptz NOT NULL,
    cancel_at               timestamptz,
    version                 bigint NOT NULL DEFAULT 0,
    created_at              timestamptz NOT NULL DEFAULT now(),
    CHECK (current_period_end > current_period_start)
);

CREATE TABLE IF NOT EXISTS invoices (
    id                      text PRIMARY KEY,
    tenant_id               text NOT NULL,
    billing_account_id      text NOT NULL REFERENCES billing_accounts(id),
    status                  text NOT NULL CHECK (status IN ('draft','open','partially_paid','paid','void','uncollectible')),
    currency                char(3) NOT NULL,
    subtotal_minor          bigint NOT NULL DEFAULT 0,
    discount_minor          bigint NOT NULL DEFAULT 0 CHECK (discount_minor >= 0),
    tax_minor               bigint NOT NULL DEFAULT 0 CHECK (tax_minor >= 0),
    total_minor             bigint NOT NULL DEFAULT 0,
    amount_paid_minor       bigint NOT NULL DEFAULT 0 CHECK (amount_paid_minor >= 0),
    amount_due_minor        bigint NOT NULL DEFAULT 0,
    price_tax_contract_snapshot jsonb NOT NULL,
    period_start            timestamptz,
    period_end              timestamptz,
    finalized_at            timestamptz,
    due_at                  timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id                      text PRIMARY KEY,
    invoice_id              text NOT NULL REFERENCES invoices(id),
    line_type               text NOT NULL CHECK (line_type IN ('plan','seat','usage','project','discount','tax','adjustment','service_credit')),
    reference_type          text,
    reference_id            text,
    description             text NOT NULL,
    quantity                numeric(38,12) NOT NULL DEFAULT 1,
    unit_amount_minor       bigint NOT NULL,
    amount_minor            bigint NOT NULL,
    calculation_snapshot    jsonb NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payments (
    id                      text PRIMARY KEY,
    tenant_id               text NOT NULL,
    billing_account_id      text NOT NULL REFERENCES billing_accounts(id),
    invoice_id              text REFERENCES invoices(id),
    provider                text NOT NULL,
    provider_payment_id     text,
    provider_event_id       text,
    idempotency_key         text NOT NULL,
    status                  text NOT NULL CHECK (status IN ('created','requires_action','authorized','captured','settled','canceled','partially_refunded','refunded','disputed','failed')),
    currency                char(3) NOT NULL,
    gross_minor             bigint NOT NULL CHECK (gross_minor >= 0),
    fee_minor               bigint NOT NULL DEFAULT 0 CHECK (fee_minor >= 0),
    net_minor               bigint NOT NULL DEFAULT 0,
    exchange_rate_snapshot  jsonb,
    provider_payload_hash   text,
    settled_at              timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, provider, idempotency_key),
    UNIQUE (provider, provider_event_id)
);

CREATE TABLE IF NOT EXISTS refunds (
    id                      text PRIMARY KEY,
    tenant_id               text NOT NULL,
    payment_id              text REFERENCES payments(id),
    ledger_transaction_id   text REFERENCES ledger_transactions(id),
    status                  text NOT NULL CHECK (status IN ('requested','eligibility_review','approved','processing','succeeded','partial','failed_retryable','failed_final','rejected')),
    reason_code             text NOT NULL,
    responsibility          text NOT NULL CHECK (responsibility IN ('platform','model_in_budget','user','third_party','scope_change','acceptance_failure','fraud','other')),
    amount_minor            bigint NOT NULL CHECK (amount_minor >= 0),
    currency                char(3) NOT NULL,
    evidence                jsonb NOT NULL,
    requested_by            text NOT NULL,
    approved_by             text,
    created_at              timestamptz NOT NULL DEFAULT now(),
    completed_at            timestamptz
);

CREATE TABLE IF NOT EXISTS enterprise_contracts (
    id                      text PRIMARY KEY,
    tenant_id               text NOT NULL,
    version                 integer NOT NULL CHECK (version > 0),
    status                  text NOT NULL CHECK (status IN ('draft','approved','active','expired','terminated')),
    valid_from              timestamptz NOT NULL,
    valid_to                timestamptz NOT NULL,
    currency                char(3) NOT NULL,
    annual_platform_fee_minor bigint NOT NULL DEFAULT 0,
    committed_spend_minor   bigint NOT NULL DEFAULT 0,
    credit_limit_minor      bigint NOT NULL DEFAULT 0,
    payment_terms_days      integer NOT NULL DEFAULT 0,
    byok_policy             jsonb NOT NULL DEFAULT '{}'::jsonb,
    private_deployment_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
    sla_policy              jsonb NOT NULL DEFAULT '{}'::jsonb,
    overrides               jsonb NOT NULL DEFAULT '{}'::jsonb,
    content_hash            text NOT NULL,
    approved_by             text,
    approved_at             timestamptz,
    UNIQUE (tenant_id, version),
    CHECK (valid_to > valid_from)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id                      text PRIMARY KEY,
    tenant_id               text,
    actor_id                text NOT NULL,
    actor_type              text NOT NULL,
    action                  text NOT NULL,
    resource_type           text NOT NULL,
    resource_id             text NOT NULL,
    reason                  text,
    correlation_id          text NOT NULL,
    before_hash             text,
    after_hash              text,
    approval_id             text,
    occurred_at             timestamptz NOT NULL DEFAULT now(),
    metadata                jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS outbox_events (
    id                      text PRIMARY KEY,
    tenant_id               text,
    event_type              text NOT NULL,
    aggregate_type          text NOT NULL,
    aggregate_id            text NOT NULL,
    aggregate_version       bigint,
    correlation_id          text NOT NULL,
    causation_id            text,
    payload                 jsonb NOT NULL,
    occurred_at             timestamptz NOT NULL,
    published_at            timestamptz,
    attempt_count           integer NOT NULL DEFAULT 0,
    last_error              text
);

CREATE TABLE IF NOT EXISTS inbox_messages (
    consumer_name           text NOT NULL,
    message_id              text NOT NULL,
    payload_hash            text NOT NULL,
    processed_at            timestamptz NOT NULL DEFAULT now(),
    result_snapshot         jsonb,
    PRIMARY KEY (consumer_name, message_id)
);

-- Example RLS setup. Adapt tenant context mechanism to the target stack.
ALTER TABLE billing_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_quotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS billing_accounts_tenant ON billing_accounts;
CREATE POLICY billing_accounts_tenant ON billing_accounts
USING (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS wallets_tenant ON wallets;
CREATE POLICY wallets_tenant ON wallets
USING (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS usage_events_tenant ON usage_events;
CREATE POLICY usage_events_tenant ON usage_events
USING (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS task_quotes_tenant ON task_quotes;
CREATE POLICY task_quotes_tenant ON task_quotes
USING (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS invoices_tenant ON invoices;
CREATE POLICY invoices_tenant ON invoices
USING (tenant_id = current_setting('app.tenant_id', true));
