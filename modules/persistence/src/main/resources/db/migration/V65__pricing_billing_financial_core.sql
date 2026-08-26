-- Durable financial source-fact contract for Pricing/Billing EB04, EB05, EB09 and EB13.
-- This migration provides engineering controls only. It does not certify accounting,
-- tax, banking, payment processing, management reporting or production operations.

CREATE OR REPLACE FUNCTION pricing_billing_reject_immutable_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'pricing/billing source facts are append-only; append a correction instead'
        USING ERRCODE = '55000';
END;
$$;

CREATE TABLE pricing_billing_wallet (
    tenant_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    wallet_id uuid NOT NULL,
    unit text NOT NULL CHECK (unit ~ '^[A-Z][A-Z0-9_.-]{0,31}$'),
    current_version bigint NOT NULL DEFAULT 0 CHECK (current_version >= 0),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, legal_entity_id, wallet_id)
);

CREATE TABLE pricing_billing_wallet_lot (
    tenant_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    wallet_id uuid NOT NULL,
    lot_id uuid NOT NULL,
    credit_kind text NOT NULL CHECK (credit_kind IN ('PAID', 'PROMOTIONAL')),
    original_quantity numeric(38, 12) NOT NULL CHECK (original_quantity > 0),
    unit text NOT NULL CHECK (unit ~ '^[A-Z][A-Z0-9_.-]{0,31}$'),
    effective_at timestamptz NOT NULL,
    expires_at timestamptz,
    source_ref text NOT NULL CHECK (length(btrim(source_ref)) > 0),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, legal_entity_id, wallet_id, lot_id),
    FOREIGN KEY (tenant_id, legal_entity_id, wallet_id)
        REFERENCES pricing_billing_wallet (tenant_id, legal_entity_id, wallet_id),
    CHECK (expires_at IS NULL OR expires_at > effective_at)
);

CREATE TABLE pricing_billing_wallet_entry (
    tenant_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    wallet_id uuid NOT NULL,
    entry_id uuid NOT NULL,
    aggregate_version bigint NOT NULL CHECK (aggregate_version > 0),
    entry_type text NOT NULL CHECK (entry_type IN ('GRANT', 'RESERVE', 'COMMIT', 'RELEASE', 'EXPIRE', 'ADJUSTMENT')),
    lot_id uuid NOT NULL,
    reservation_id uuid,
    debit_account text NOT NULL CHECK (length(btrim(debit_account)) > 0),
    credit_account text NOT NULL CHECK (length(btrim(credit_account)) > 0),
    quantity numeric(38, 12) NOT NULL CHECK (quantity > 0),
    unit text NOT NULL CHECK (unit ~ '^[A-Z][A-Z0-9_.-]{0,31}$'),
    command_id text NOT NULL CHECK (length(btrim(command_id)) > 0),
    command_fingerprint char(64) NOT NULL CHECK (command_fingerprint ~ '^[0-9a-f]{64}$'),
    reason_code text NOT NULL CHECK (length(btrim(reason_code)) > 0),
    effective_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, legal_entity_id, wallet_id, entry_id),
    UNIQUE (tenant_id, legal_entity_id, wallet_id, aggregate_version),
    FOREIGN KEY (tenant_id, legal_entity_id, wallet_id, lot_id)
        REFERENCES pricing_billing_wallet_lot (tenant_id, legal_entity_id, wallet_id, lot_id),
    CHECK (debit_account <> credit_account),
    CHECK ((entry_type IN ('RESERVE', 'COMMIT', 'RELEASE')) = (reservation_id IS NOT NULL))
);

CREATE TABLE pricing_billing_wallet_command (
    tenant_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    wallet_id uuid NOT NULL,
    command_id text NOT NULL,
    command_fingerprint char(64) NOT NULL CHECK (command_fingerprint ~ '^[0-9a-f]{64}$'),
    result_version bigint NOT NULL CHECK (result_version > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, legal_entity_id, wallet_id, command_id),
    FOREIGN KEY (tenant_id, legal_entity_id, wallet_id)
        REFERENCES pricing_billing_wallet (tenant_id, legal_entity_id, wallet_id)
);

CREATE TABLE pricing_billing_usage_source_fact (
    tenant_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    usage_fact_id uuid NOT NULL,
    source_system text NOT NULL CHECK (length(btrim(source_system)) > 0),
    source_event_id text NOT NULL CHECK (length(btrim(source_event_id)) > 0),
    ingest_command_id text NOT NULL CHECK (length(btrim(ingest_command_id)) > 0),
    source_payload_digest char(64) NOT NULL CHECK (source_payload_digest ~ '^[0-9a-f]{64}$'),
    source_payload jsonb NOT NULL,
    event_time timestamptz NOT NULL,
    received_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, legal_entity_id, usage_fact_id),
    UNIQUE (tenant_id, legal_entity_id, source_system, source_event_id),
    UNIQUE (tenant_id, legal_entity_id, ingest_command_id),
    CHECK (jsonb_typeof(source_payload) = 'object')
);

CREATE TABLE pricing_billing_usage_normalized_fact (
    tenant_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    normalized_fact_id uuid NOT NULL,
    usage_fact_id uuid NOT NULL,
    fact_type text NOT NULL CHECK (fact_type IN ('ORIGINAL', 'CORRECTION')),
    correction_of uuid,
    correction_reason text,
    meter_key text NOT NULL CHECK (length(btrim(meter_key)) > 0),
    quantity numeric(38, 12) NOT NULL CHECK (quantity <> 0),
    unit text NOT NULL CHECK (unit ~ '^[A-Z][A-Z0-9_.-]{0,31}$'),
    dimensions jsonb NOT NULL DEFAULT '{}'::jsonb,
    normalization_version text NOT NULL CHECK (length(btrim(normalization_version)) > 0),
    billing_window_start timestamptz NOT NULL,
    billing_window_end timestamptz NOT NULL,
    allowed_lateness interval NOT NULL CHECK (allowed_lateness >= interval '0 seconds'),
    usage_decision text NOT NULL CHECK (usage_decision IN ('ACCEPTED', 'LATE_REVIEW')),
    billable boolean NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, legal_entity_id, normalized_fact_id),
    FOREIGN KEY (tenant_id, legal_entity_id, usage_fact_id)
        REFERENCES pricing_billing_usage_source_fact (tenant_id, legal_entity_id, usage_fact_id),
    FOREIGN KEY (tenant_id, legal_entity_id, correction_of)
        REFERENCES pricing_billing_usage_normalized_fact (tenant_id, legal_entity_id, normalized_fact_id),
    CHECK (billing_window_end > billing_window_start),
    CHECK ((fact_type = 'CORRECTION') = (correction_of IS NOT NULL)),
    CHECK ((fact_type = 'CORRECTION') = (correction_reason IS NOT NULL AND length(btrim(correction_reason)) > 0)),
    CHECK (fact_type = 'CORRECTION' OR quantity > 0),
    CHECK ((usage_decision = 'ACCEPTED') = billable),
    CHECK (jsonb_typeof(dimensions) = 'object')
);

CREATE TABLE pricing_billing_invoice (
    tenant_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    invoice_id uuid NOT NULL,
    invoice_number text,
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    state text NOT NULL CHECK (state IN ('DRAFT', 'REVIEW_REQUIRED', 'FINALIZED', 'ISSUED', 'PARTIALLY_PAID', 'PAID', 'CREDITED', 'VOID')),
    aggregate_version bigint NOT NULL CHECK (aggregate_version > 0),
    maker_actor_id text NOT NULL CHECK (length(btrim(maker_actor_id)) > 0),
    checker_actor_id text,
    tax_state text NOT NULL CHECK (tax_state IN ('CALCULATED', 'EXEMPT', 'UNKNOWN')),
    tax_policy_version text NOT NULL CHECK (length(btrim(tax_policy_version)) > 0),
    tax_evidence_ref text,
    subtotal numeric(38, 12) NOT NULL CHECK (subtotal >= 0),
    tax_total numeric(38, 12) NOT NULL CHECK (tax_total >= 0),
    invoice_total numeric(38, 12) NOT NULL CHECK (invoice_total = subtotal + tax_total),
    paid_total numeric(38, 12) NOT NULL DEFAULT 0 CHECK (paid_total >= 0),
    credited_total numeric(38, 12) NOT NULL DEFAULT 0 CHECK (credited_total >= 0 AND credited_total <= invoice_total),
    service_period_start timestamptz NOT NULL,
    service_period_end timestamptz NOT NULL,
    finalized_at timestamptz,
    issued_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, legal_entity_id, invoice_id),
    UNIQUE (tenant_id, legal_entity_id, invoice_number),
    UNIQUE (tenant_id, legal_entity_id, invoice_id, currency),
    CHECK (service_period_end > service_period_start),
    CHECK (paid_total <= invoice_total),
    CHECK (state IN ('DRAFT', 'REVIEW_REQUIRED') OR (tax_state <> 'UNKNOWN' AND tax_evidence_ref IS NOT NULL)),
    CHECK (state IN ('DRAFT', 'REVIEW_REQUIRED') OR (checker_actor_id IS NOT NULL AND checker_actor_id <> maker_actor_id)),
    CHECK ((state IN ('FINALIZED', 'ISSUED', 'PARTIALLY_PAID', 'PAID', 'CREDITED')) = (finalized_at IS NOT NULL)),
    CHECK ((state IN ('ISSUED', 'PARTIALLY_PAID', 'PAID', 'CREDITED')) = (issued_at IS NOT NULL))
);

CREATE TABLE pricing_billing_invoice_line (
    tenant_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    invoice_id uuid NOT NULL,
    line_id uuid NOT NULL,
    description text NOT NULL CHECK (length(btrim(description)) > 0),
    quantity numeric(38, 12) NOT NULL CHECK (quantity > 0),
    unit_price numeric(38, 12) NOT NULL CHECK (unit_price >= 0),
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    net_amount numeric(38, 12) NOT NULL CHECK (net_amount = quantity * unit_price),
    tax_amount numeric(38, 12) NOT NULL CHECK (tax_amount >= 0),
    tax_state text NOT NULL CHECK (tax_state IN ('CALCULATED', 'EXEMPT', 'UNKNOWN')),
    pricing_version text NOT NULL CHECK (length(btrim(pricing_version)) > 0),
    service_period_start timestamptz NOT NULL,
    service_period_end timestamptz NOT NULL,
    source_fact_refs jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, legal_entity_id, invoice_id, line_id),
    FOREIGN KEY (tenant_id, legal_entity_id, invoice_id, currency)
        REFERENCES pricing_billing_invoice (tenant_id, legal_entity_id, invoice_id, currency),
    CHECK (service_period_end > service_period_start),
    CHECK (jsonb_typeof(source_fact_refs) = 'array' AND jsonb_array_length(source_fact_refs) > 0)
);

CREATE TABLE pricing_billing_invoice_event (
    tenant_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    invoice_id uuid NOT NULL,
    event_id uuid NOT NULL,
    aggregate_version bigint NOT NULL CHECK (aggregate_version > 0),
    event_type text NOT NULL CHECK (event_type IN ('CREATED', 'SUBMITTED_FOR_REVIEW', 'FINALIZED', 'ISSUED', 'PAYMENT_RECONCILED', 'CREDIT_NOTE_ISSUED', 'VOIDED')),
    command_id text NOT NULL CHECK (length(btrim(command_id)) > 0),
    command_fingerprint char(64) NOT NULL CHECK (command_fingerprint ~ '^[0-9a-f]{64}$'),
    actor_id text NOT NULL CHECK (length(btrim(actor_id)) > 0),
    amount numeric(38, 12),
    currency char(3),
    external_ref text,
    provider_evidence_ref text,
    bank_evidence_ref text,
    provider_state text CHECK (provider_state IN ('RECONCILED', 'FINAL', 'UNKNOWN', 'DISPUTED')),
    bank_state text CHECK (bank_state IN ('RECONCILED', 'FINAL', 'UNKNOWN', 'DISPUTED')),
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, legal_entity_id, invoice_id, event_id),
    UNIQUE (tenant_id, legal_entity_id, invoice_id, event_id, currency),
    UNIQUE (tenant_id, legal_entity_id, invoice_id, aggregate_version),
    UNIQUE (tenant_id, legal_entity_id, invoice_id, command_id),
    FOREIGN KEY (tenant_id, legal_entity_id, invoice_id)
        REFERENCES pricing_billing_invoice (tenant_id, legal_entity_id, invoice_id),
    CHECK ((amount IS NULL) = (currency IS NULL)),
    CHECK (amount IS NULL OR amount > 0),
    CHECK (event_type <> 'PAYMENT_RECONCILED' OR
        (external_ref IS NOT NULL AND amount IS NOT NULL
         AND provider_state = 'RECONCILED' AND bank_state = 'RECONCILED'
         AND provider_evidence_ref IS NOT NULL AND bank_evidence_ref IS NOT NULL))
);

CREATE TABLE pricing_billing_credit_note (
    tenant_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    credit_note_id uuid NOT NULL,
    invoice_id uuid NOT NULL,
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    amount numeric(38, 12) NOT NULL CHECK (amount > 0),
    reason_code text NOT NULL CHECK (length(btrim(reason_code)) > 0),
    source_event_id uuid NOT NULL,
    maker_actor_id text NOT NULL,
    checker_actor_id text NOT NULL,
    issued_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, legal_entity_id, credit_note_id),
    UNIQUE (tenant_id, legal_entity_id, invoice_id, source_event_id),
    FOREIGN KEY (tenant_id, legal_entity_id, invoice_id, source_event_id, currency)
        REFERENCES pricing_billing_invoice_event
        (tenant_id, legal_entity_id, invoice_id, event_id, currency),
    CHECK (length(btrim(maker_actor_id)) > 0),
    CHECK (length(btrim(checker_actor_id)) > 0),
    CHECK (maker_actor_id <> checker_actor_id)
);

CREATE TABLE pricing_billing_fx_rate_fact (
    tenant_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    fx_rate_id uuid NOT NULL,
    from_currency char(3) NOT NULL CHECK (from_currency ~ '^[A-Z]{3}$'),
    to_currency char(3) NOT NULL CHECK (to_currency ~ '^[A-Z]{3}$'),
    rate numeric(38, 18) NOT NULL CHECK (rate > 0),
    effective_from timestamptz NOT NULL,
    effective_until timestamptz NOT NULL,
    source_ref text NOT NULL CHECK (length(btrim(source_ref)) > 0),
    evidence_state text NOT NULL CHECK (evidence_state IN ('RECONCILED', 'FINAL', 'UNKNOWN', 'DISPUTED')),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, legal_entity_id, fx_rate_id),
    CHECK (from_currency <> to_currency),
    CHECK (effective_until > effective_from)
);

CREATE TABLE pricing_billing_financial_fact (
    tenant_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    financial_fact_id uuid NOT NULL,
    fact_kind text NOT NULL CHECK (fact_kind IN ('REVENUE', 'PROVIDER', 'RUNNER', 'STORAGE', 'EGRESS', 'HUMAN_REVIEW', 'SUPPORT', 'OTHER_COGS')),
    amount numeric(38, 12) NOT NULL,
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    period_start timestamptz NOT NULL,
    period_end timestamptz NOT NULL,
    effective_at timestamptz NOT NULL,
    allocation_coverage numeric(20, 18) NOT NULL CHECK (allocation_coverage >= 0 AND allocation_coverage <= 1),
    source_ref text NOT NULL CHECK (length(btrim(source_ref)) > 0),
    evidence_state text NOT NULL CHECK (evidence_state IN ('RECONCILED', 'FINAL', 'UNKNOWN', 'DISPUTED')),
    correction_of uuid,
    correction_reason text,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, legal_entity_id, financial_fact_id),
    FOREIGN KEY (tenant_id, legal_entity_id, correction_of)
        REFERENCES pricing_billing_financial_fact (tenant_id, legal_entity_id, financial_fact_id),
    CHECK (period_end > period_start),
    CHECK ((correction_of IS NULL) = (correction_reason IS NULL)),
    CHECK (correction_reason IS NULL OR length(btrim(correction_reason)) > 0)
);

CREATE TABLE pricing_billing_metric_definition (
    metric_id text NOT NULL,
    definition_version text NOT NULL,
    grain text NOT NULL CHECK (length(btrim(grain)) > 0),
    denominator_name text NOT NULL CHECK (length(btrim(denominator_name)) > 0),
    output_scale integer NOT NULL CHECK (output_scale BETWEEN 0 AND 18),
    rounding_mode text NOT NULL CHECK (rounding_mode IN ('HALF_EVEN', 'HALF_UP', 'DOWN', 'UP')),
    definition_digest char(64) NOT NULL CHECK (definition_digest ~ '^[0-9a-f]{64}$'),
    effective_from timestamptz NOT NULL,
    effective_until timestamptz,
    PRIMARY KEY (metric_id, definition_version),
    CHECK (effective_until IS NULL OR effective_until > effective_from)
);

CREATE TABLE pricing_billing_metric_observation (
    tenant_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    observation_id uuid NOT NULL,
    metric_id text NOT NULL,
    definition_version text NOT NULL,
    grain_key text NOT NULL CHECK (length(btrim(grain_key)) > 0),
    denominator numeric(38, 12) NOT NULL,
    reporting_currency char(3) NOT NULL CHECK (reporting_currency ~ '^[A-Z]{3}$'),
    metric_state text NOT NULL CHECK (metric_state IN ('AVAILABLE', 'UNKNOWN')),
    metric_value numeric(38, 18),
    reason_code text NOT NULL CHECK (length(btrim(reason_code)) > 0),
    source_fact_refs jsonb NOT NULL,
    as_of timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, legal_entity_id, observation_id),
    FOREIGN KEY (metric_id, definition_version)
        REFERENCES pricing_billing_metric_definition (metric_id, definition_version),
    CHECK ((metric_state = 'AVAILABLE') = (metric_value IS NOT NULL)),
    CHECK (metric_state <> 'AVAILABLE' OR denominator > 0),
    CHECK (jsonb_typeof(source_fact_refs) = 'array'),
    CHECK (metric_state <> 'AVAILABLE' OR jsonb_array_length(source_fact_refs) > 0)
);

CREATE TABLE pricing_billing_outbox (
    outbox_id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    aggregate_type text NOT NULL CHECK (length(btrim(aggregate_type)) > 0),
    aggregate_id uuid NOT NULL,
    aggregate_version bigint NOT NULL CHECK (aggregate_version > 0),
    event_type text NOT NULL CHECK (length(btrim(event_type)) > 0),
    source_fact_table text NOT NULL CHECK (length(btrim(source_fact_table)) > 0),
    source_fact_id uuid NOT NULL,
    payload jsonb NOT NULL,
    occurred_at timestamptz NOT NULL,
    published_at timestamptz,
    publish_attempts integer NOT NULL DEFAULT 0 CHECK (publish_attempts >= 0),
    last_error_code text,
    UNIQUE (tenant_id, legal_entity_id, aggregate_type, aggregate_id, aggregate_version, event_type),
    CHECK (jsonb_typeof(payload) = 'object')
);

CREATE OR REPLACE FUNCTION pricing_billing_advance_wallet_version()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    prior_version bigint;
BEGIN
    SELECT current_version
      INTO prior_version
      FROM pricing_billing_wallet
     WHERE tenant_id = NEW.tenant_id
       AND legal_entity_id = NEW.legal_entity_id
       AND wallet_id = NEW.wallet_id
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'wallet aggregate not found in scope' USING ERRCODE = '23503';
    END IF;
    IF NEW.aggregate_version <> prior_version + 1 THEN
        RAISE EXCEPTION 'wallet optimistic version mismatch: expected %, received %',
            prior_version + 1, NEW.aggregate_version USING ERRCODE = '40001';
    END IF;
    UPDATE pricing_billing_wallet
       SET current_version = NEW.aggregate_version
     WHERE tenant_id = NEW.tenant_id
       AND legal_entity_id = NEW.legal_entity_id
       AND wallet_id = NEW.wallet_id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER pricing_billing_wallet_version_guard
    BEFORE INSERT ON pricing_billing_wallet_entry
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_advance_wallet_version();

CREATE OR REPLACE FUNCTION pricing_billing_validate_invoice_projection()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    transition_allowed boolean;
    line_subtotal numeric(38, 12);
    line_tax_total numeric(38, 12);
    reconciled_payment_total numeric(38, 12);
    issued_credit_total numeric(38, 12);
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'DRAFT' OR NEW.aggregate_version <> 1 THEN
            RAISE EXCEPTION 'invoice projection must begin at DRAFT version 1' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    IF (NEW.tenant_id, NEW.legal_entity_id, NEW.invoice_id, NEW.currency, NEW.maker_actor_id)
        IS DISTINCT FROM
       (OLD.tenant_id, OLD.legal_entity_id, OLD.invoice_id, OLD.currency, OLD.maker_actor_id) THEN
        RAISE EXCEPTION 'invoice scope, identity, currency and maker are immutable'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.aggregate_version <> OLD.aggregate_version + 1 THEN
        RAISE EXCEPTION 'invoice optimistic version mismatch' USING ERRCODE = '40001';
    END IF;
    IF NEW.paid_total < OLD.paid_total OR NEW.credited_total < OLD.credited_total THEN
        RAISE EXCEPTION 'invoice cash and credit projections cannot decrease; append a correction fact'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.state NOT IN ('DRAFT', 'REVIEW_REQUIRED') AND
       (NEW.subtotal, NEW.tax_total, NEW.invoice_total, NEW.tax_state,
        NEW.tax_policy_version, NEW.tax_evidence_ref, NEW.service_period_start,
        NEW.service_period_end)
       IS DISTINCT FROM
       (OLD.subtotal, OLD.tax_total, OLD.invoice_total, OLD.tax_state,
        OLD.tax_policy_version, OLD.tax_evidence_ref, OLD.service_period_start,
        OLD.service_period_end) THEN
        RAISE EXCEPTION 'finalized invoice financial inputs are immutable'
            USING ERRCODE = '55000';
    END IF;

    transition_allowed :=
        (OLD.state = NEW.state AND OLD.state IN ('DRAFT', 'REVIEW_REQUIRED', 'FINALIZED', 'ISSUED', 'PARTIALLY_PAID', 'CREDITED')) OR
        (OLD.state = 'DRAFT' AND NEW.state = 'REVIEW_REQUIRED') OR
        (OLD.state = 'REVIEW_REQUIRED' AND NEW.state = 'FINALIZED') OR
        (OLD.state = 'FINALIZED' AND NEW.state IN ('ISSUED', 'VOID', 'CREDITED')) OR
        (OLD.state = 'ISSUED' AND NEW.state IN ('PARTIALLY_PAID', 'PAID', 'CREDITED')) OR
        (OLD.state = 'PARTIALLY_PAID' AND NEW.state IN ('PAID', 'CREDITED')) OR
        (OLD.state = 'PAID' AND NEW.state = 'CREDITED');
    IF NOT transition_allowed THEN
        RAISE EXCEPTION 'invalid invoice transition % -> %', OLD.state, NEW.state
            USING ERRCODE = '23514';
    END IF;

    IF NEW.state IN ('FINALIZED', 'ISSUED', 'PARTIALLY_PAID', 'PAID', 'CREDITED') AND
       (NOT EXISTS (
            SELECT 1 FROM pricing_billing_invoice_line line
             WHERE line.tenant_id = NEW.tenant_id
               AND line.legal_entity_id = NEW.legal_entity_id
               AND line.invoice_id = NEW.invoice_id
        ) OR EXISTS (
            SELECT 1 FROM pricing_billing_invoice_line line
             WHERE line.tenant_id = NEW.tenant_id
               AND line.legal_entity_id = NEW.legal_entity_id
               AND line.invoice_id = NEW.invoice_id
               AND line.tax_state = 'UNKNOWN'
        )) THEN
        RAISE EXCEPTION 'missing lines or unknown line tax blocks invoice finalization'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.state IN ('FINALIZED', 'ISSUED', 'PARTIALLY_PAID', 'PAID', 'CREDITED') THEN
        SELECT COALESCE(sum(line.net_amount), 0), COALESCE(sum(line.tax_amount), 0)
          INTO line_subtotal, line_tax_total
          FROM pricing_billing_invoice_line line
         WHERE line.tenant_id = NEW.tenant_id
           AND line.legal_entity_id = NEW.legal_entity_id
           AND line.invoice_id = NEW.invoice_id;
        IF NEW.subtotal <> line_subtotal OR NEW.tax_total <> line_tax_total THEN
            RAISE EXCEPTION 'invoice totals must equal immutable line totals'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    SELECT COALESCE(sum(event.amount), 0)
      INTO reconciled_payment_total
      FROM pricing_billing_invoice_event event
     WHERE event.tenant_id = NEW.tenant_id
       AND event.legal_entity_id = NEW.legal_entity_id
       AND event.invoice_id = NEW.invoice_id
       AND event.event_type = 'PAYMENT_RECONCILED';
    SELECT COALESCE(sum(note.amount), 0)
      INTO issued_credit_total
      FROM pricing_billing_credit_note note
     WHERE note.tenant_id = NEW.tenant_id
       AND note.legal_entity_id = NEW.legal_entity_id
       AND note.invoice_id = NEW.invoice_id;
    IF NEW.paid_total <> reconciled_payment_total THEN
        RAISE EXCEPTION 'invoice paid total must equal reconciled payment events'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.credited_total <> issued_credit_total THEN
        RAISE EXCEPTION 'invoice credited total must equal immutable credit notes'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER pricing_billing_invoice_projection_guard
    BEFORE INSERT OR UPDATE ON pricing_billing_invoice
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_validate_invoice_projection();

CREATE OR REPLACE FUNCTION pricing_billing_validate_credit_note()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    invoice_currency char(3);
    invoice_total numeric(38, 12);
    prior_credit_total numeric(38, 12);
    source_event_type text;
    source_event_amount numeric(38, 12);
    source_event_currency char(3);
BEGIN
    SELECT invoice.currency, invoice.invoice_total
      INTO invoice_currency, invoice_total
      FROM pricing_billing_invoice invoice
     WHERE invoice.tenant_id = NEW.tenant_id
       AND invoice.legal_entity_id = NEW.legal_entity_id
       AND invoice.invoice_id = NEW.invoice_id
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'credit note invoice not found in scope' USING ERRCODE = '23503';
    END IF;
    SELECT event.event_type, event.amount, event.currency
      INTO source_event_type, source_event_amount, source_event_currency
      FROM pricing_billing_invoice_event event
     WHERE event.tenant_id = NEW.tenant_id
       AND event.legal_entity_id = NEW.legal_entity_id
       AND event.invoice_id = NEW.invoice_id
       AND event.event_id = NEW.source_event_id;
    IF NOT FOUND OR source_event_type <> 'CREDIT_NOTE_ISSUED'
       OR source_event_amount IS DISTINCT FROM NEW.amount
       OR source_event_currency IS DISTINCT FROM NEW.currency THEN
        RAISE EXCEPTION 'credit note must bind one matching CREDIT_NOTE_ISSUED event'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.currency <> invoice_currency THEN
        RAISE EXCEPTION 'credit note currency must equal invoice currency'
            USING ERRCODE = '23514';
    END IF;
    SELECT COALESCE(sum(note.amount), 0)
      INTO prior_credit_total
      FROM pricing_billing_credit_note note
     WHERE note.tenant_id = NEW.tenant_id
       AND note.legal_entity_id = NEW.legal_entity_id
       AND note.invoice_id = NEW.invoice_id;
    IF prior_credit_total + NEW.amount > invoice_total THEN
        RAISE EXCEPTION 'cumulative credit notes exceed invoice total'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER pricing_billing_credit_note_guard
    BEFORE INSERT ON pricing_billing_credit_note
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_validate_credit_note();

CREATE OR REPLACE FUNCTION pricing_billing_emit_wallet_outbox()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO pricing_billing_outbox (
        tenant_id, legal_entity_id, aggregate_type, aggregate_id, aggregate_version,
        event_type, source_fact_table, source_fact_id, payload, occurred_at
    ) VALUES (
        NEW.tenant_id, NEW.legal_entity_id, 'CREDIT_WALLET', NEW.wallet_id,
        NEW.aggregate_version, NEW.entry_type, 'pricing_billing_wallet_entry', NEW.entry_id,
        jsonb_build_object(
            'entryId', NEW.entry_id,
            'lotId', NEW.lot_id,
            'reservationId', NEW.reservation_id,
            'quantity', NEW.quantity::text,
            'unit', NEW.unit,
            'commandId', NEW.command_id
        ), NEW.effective_at
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER pricing_billing_wallet_outbox
    AFTER INSERT ON pricing_billing_wallet_entry
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_emit_wallet_outbox();

CREATE OR REPLACE FUNCTION pricing_billing_emit_usage_outbox()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO pricing_billing_outbox (
        tenant_id, legal_entity_id, aggregate_type, aggregate_id, aggregate_version,
        event_type, source_fact_table, source_fact_id, payload, occurred_at
    ) VALUES (
        NEW.tenant_id, NEW.legal_entity_id, 'USAGE_FACT', NEW.normalized_fact_id, 1,
        'USAGE_' || NEW.usage_decision, 'pricing_billing_usage_normalized_fact',
        NEW.normalized_fact_id,
        jsonb_build_object(
            'usageFactId', NEW.usage_fact_id,
            'factType', NEW.fact_type,
            'meterKey', NEW.meter_key,
            'quantity', NEW.quantity::text,
            'unit', NEW.unit,
            'billable', NEW.billable,
            'normalizationVersion', NEW.normalization_version
        ), NEW.recorded_at
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER pricing_billing_usage_outbox
    AFTER INSERT ON pricing_billing_usage_normalized_fact
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_emit_usage_outbox();

CREATE OR REPLACE FUNCTION pricing_billing_emit_invoice_outbox()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO pricing_billing_outbox (
        tenant_id, legal_entity_id, aggregate_type, aggregate_id, aggregate_version,
        event_type, source_fact_table, source_fact_id, payload, occurred_at
    ) VALUES (
        NEW.tenant_id, NEW.legal_entity_id, 'INVOICE', NEW.invoice_id,
        NEW.aggregate_version, NEW.event_type, 'pricing_billing_invoice_event', NEW.event_id,
        jsonb_build_object(
            'eventId', NEW.event_id,
            'commandId', NEW.command_id,
            'externalRef', NEW.external_ref,
            'amount', CASE WHEN NEW.amount IS NULL THEN NULL ELSE NEW.amount::text END,
            'currency', NEW.currency
        ), NEW.occurred_at
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER pricing_billing_invoice_outbox
    AFTER INSERT ON pricing_billing_invoice_event
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_emit_invoice_outbox();

CREATE OR REPLACE FUNCTION pricing_billing_guard_outbox_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'outbox delivery facts cannot be deleted' USING ERRCODE = '55000';
    END IF;
    IF (NEW.outbox_id, NEW.tenant_id, NEW.legal_entity_id, NEW.aggregate_type,
        NEW.aggregate_id, NEW.aggregate_version, NEW.event_type, NEW.source_fact_table,
        NEW.source_fact_id, NEW.payload, NEW.occurred_at)
       IS DISTINCT FROM
       (OLD.outbox_id, OLD.tenant_id, OLD.legal_entity_id, OLD.aggregate_type,
        OLD.aggregate_id, OLD.aggregate_version, OLD.event_type, OLD.source_fact_table,
        OLD.source_fact_id, OLD.payload, OLD.occurred_at) THEN
        RAISE EXCEPTION 'outbox source identity and payload are immutable'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER pricing_billing_outbox_guard
    BEFORE UPDATE OR DELETE ON pricing_billing_outbox
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_guard_outbox_change();

CREATE INDEX pricing_billing_wallet_entry_reservation_idx
    ON pricing_billing_wallet_entry (tenant_id, legal_entity_id, wallet_id, reservation_id)
    WHERE reservation_id IS NOT NULL;
CREATE INDEX pricing_billing_usage_window_idx
    ON pricing_billing_usage_normalized_fact
    (tenant_id, legal_entity_id, meter_key, billing_window_start, billing_window_end)
    WHERE billable;
CREATE INDEX pricing_billing_invoice_state_idx
    ON pricing_billing_invoice (tenant_id, legal_entity_id, state, issued_at);
CREATE UNIQUE INDEX pricing_billing_payment_external_ref_uq
    ON pricing_billing_invoice_event (tenant_id, legal_entity_id, external_ref)
    WHERE event_type = 'PAYMENT_RECONCILED';
CREATE UNIQUE INDEX pricing_billing_credit_note_external_ref_uq
    ON pricing_billing_invoice_event (tenant_id, legal_entity_id, invoice_id, external_ref)
    WHERE event_type = 'CREDIT_NOTE_ISSUED';
CREATE INDEX pricing_billing_outbox_unpublished_idx
    ON pricing_billing_outbox (outbox_id) WHERE published_at IS NULL;
CREATE INDEX pricing_billing_financial_period_idx
    ON pricing_billing_financial_fact (tenant_id, legal_entity_id, period_start, period_end, fact_kind);

-- Immutable facts are never edited or removed. Corrections have their own rows.
CREATE TRIGGER pricing_billing_wallet_lot_immutable
    BEFORE UPDATE OR DELETE ON pricing_billing_wallet_lot
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_reject_immutable_change();
CREATE TRIGGER pricing_billing_wallet_entry_immutable
    BEFORE UPDATE OR DELETE ON pricing_billing_wallet_entry
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_reject_immutable_change();
CREATE TRIGGER pricing_billing_wallet_command_immutable
    BEFORE UPDATE OR DELETE ON pricing_billing_wallet_command
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_reject_immutable_change();
CREATE TRIGGER pricing_billing_usage_source_immutable
    BEFORE UPDATE OR DELETE ON pricing_billing_usage_source_fact
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_reject_immutable_change();
CREATE TRIGGER pricing_billing_usage_normalized_immutable
    BEFORE UPDATE OR DELETE ON pricing_billing_usage_normalized_fact
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_reject_immutable_change();
CREATE TRIGGER pricing_billing_invoice_line_immutable
    BEFORE UPDATE OR DELETE ON pricing_billing_invoice_line
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_reject_immutable_change();
CREATE TRIGGER pricing_billing_invoice_event_immutable
    BEFORE UPDATE OR DELETE ON pricing_billing_invoice_event
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_reject_immutable_change();
CREATE TRIGGER pricing_billing_credit_note_immutable
    BEFORE UPDATE OR DELETE ON pricing_billing_credit_note
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_reject_immutable_change();
CREATE TRIGGER pricing_billing_fx_rate_immutable
    BEFORE UPDATE OR DELETE ON pricing_billing_fx_rate_fact
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_reject_immutable_change();
CREATE TRIGGER pricing_billing_financial_fact_immutable
    BEFORE UPDATE OR DELETE ON pricing_billing_financial_fact
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_reject_immutable_change();
CREATE TRIGGER pricing_billing_metric_definition_immutable
    BEFORE UPDATE OR DELETE ON pricing_billing_metric_definition
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_reject_immutable_change();
CREATE TRIGGER pricing_billing_metric_observation_immutable
    BEFORE UPDATE OR DELETE ON pricing_billing_metric_observation
    FOR EACH ROW EXECUTE FUNCTION pricing_billing_reject_immutable_change();

-- RLS requires both authenticated tenant and trusted legal-entity transaction context.
-- The API/store layer must set both values locally inside the same transaction.
ALTER TABLE pricing_billing_wallet ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_wallet_lot ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_wallet_entry ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_wallet_command ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_usage_source_fact ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_usage_normalized_fact ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_invoice ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_invoice_line ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_invoice_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_credit_note ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_fx_rate_fact ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_financial_fact ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_metric_observation ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_outbox ENABLE ROW LEVEL SECURITY;

ALTER TABLE pricing_billing_wallet FORCE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_wallet_lot FORCE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_wallet_entry FORCE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_wallet_command FORCE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_usage_source_fact FORCE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_usage_normalized_fact FORCE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_invoice FORCE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_invoice_line FORCE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_invoice_event FORCE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_credit_note FORCE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_fx_rate_fact FORCE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_financial_fact FORCE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_metric_observation FORCE ROW LEVEL SECURITY;
ALTER TABLE pricing_billing_outbox FORCE ROW LEVEL SECURITY;

CREATE POLICY pricing_billing_wallet_scope ON pricing_billing_wallet
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid
       AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid
       AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid);
CREATE POLICY pricing_billing_wallet_lot_scope ON pricing_billing_wallet_lot
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid);
CREATE POLICY pricing_billing_wallet_entry_scope ON pricing_billing_wallet_entry
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid);
CREATE POLICY pricing_billing_wallet_command_scope ON pricing_billing_wallet_command
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid);
CREATE POLICY pricing_billing_usage_source_scope ON pricing_billing_usage_source_fact
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid);
CREATE POLICY pricing_billing_usage_normalized_scope ON pricing_billing_usage_normalized_fact
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid);
CREATE POLICY pricing_billing_invoice_scope ON pricing_billing_invoice
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid);
CREATE POLICY pricing_billing_invoice_line_scope ON pricing_billing_invoice_line
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid);
CREATE POLICY pricing_billing_invoice_event_scope ON pricing_billing_invoice_event
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid);
CREATE POLICY pricing_billing_credit_note_scope ON pricing_billing_credit_note
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid);
CREATE POLICY pricing_billing_fx_rate_scope ON pricing_billing_fx_rate_fact
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid);
CREATE POLICY pricing_billing_financial_fact_scope ON pricing_billing_financial_fact
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid);
CREATE POLICY pricing_billing_metric_observation_scope ON pricing_billing_metric_observation
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid);
CREATE POLICY pricing_billing_outbox_scope ON pricing_billing_outbox
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid)
    WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid AND legal_entity_id = nullif(current_setting('app.current_legal_entity_id', true), '')::uuid);

COMMENT ON TABLE pricing_billing_wallet_entry IS
    'Append-only balanced credit journal. Local engineering control; not accounting certification.';
COMMENT ON TABLE pricing_billing_usage_source_fact IS
    'Immutable native usage source facts; normalized facts and corrections are separate rows.';
COMMENT ON TABLE pricing_billing_invoice_event IS
    'Append-only invoice lifecycle, payment reconciliation and credit-note event stream.';
COMMENT ON TABLE pricing_billing_metric_observation IS
    'Versioned metric observation with explicit grain, denominator and UNKNOWN state.';
