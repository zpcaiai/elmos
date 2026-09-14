-- ELMOS V88: double-entry Credit journal, transactional outbox and projection rebuild.
--
-- V83/V85 keep the customer-facing lot and balance projections. This migration
-- makes every subsequent mutation of that projection produce an immutable,
-- balanced accounting transaction in the same PostgreSQL transaction. Existing
-- balances are introduced as one auditable opening transaction per organization.

CREATE TABLE commercial_credit_journal_transactions (
    transaction_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    projection_version bigint NOT NULL CHECK (projection_version >= 0),
    operation_type varchar(32) NOT NULL CHECK (operation_type IN (
        'OPENING_BALANCE', 'PURCHASE', 'RESERVE', 'CAPTURE', 'RELEASE',
        'EXPIRY', 'REFUND', 'ADJUSTMENT'
    )),
    actor_id varchar(128) NOT NULL,
    correlation_id varchar(160) NOT NULL,
    causation_id varchar(160) NOT NULL,
    idempotency_key varchar(160) NOT NULL,
    source_type varchar(32) NOT NULL,
    source_ref varchar(160) NOT NULL,
    balance_before numeric(19,0) NOT NULL CHECK (balance_before >= 0),
    reserved_before numeric(19,0) NOT NULL CHECK (reserved_before >= 0),
    balance_after numeric(19,0) NOT NULL CHECK (balance_after >= 0),
    reserved_after numeric(19,0) NOT NULL CHECK (reserved_after >= 0),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, projection_version),
    UNIQUE (transaction_id, organization_id),
    UNIQUE (organization_id, idempotency_key),
    CHECK (reserved_before <= balance_before),
    CHECK (reserved_after <= balance_after)
);

CREATE TABLE commercial_credit_journal_entries (
    posting_id varchar(128) PRIMARY KEY,
    transaction_id varchar(96) NOT NULL,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_code varchar(32) NOT NULL CHECK (account_code IN (
        'CUSTOMER_AVAILABLE', 'CUSTOMER_RESERVED', 'PLATFORM_CLEARING'
    )),
    side varchar(6) NOT NULL CHECK (side IN ('DEBIT', 'CREDIT')),
    quantity numeric(19,0) NOT NULL CHECK (quantity > 0 AND quantity = trunc(quantity)),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (transaction_id, posting_id),
    FOREIGN KEY (transaction_id, organization_id)
        REFERENCES commercial_credit_journal_transactions(transaction_id, organization_id)
);

CREATE INDEX idx_commercial_credit_journal_org_time
    ON commercial_credit_journal_transactions (organization_id, occurred_at DESC);
CREATE INDEX idx_commercial_credit_postings_transaction
    ON commercial_credit_journal_entries (transaction_id, side);

CREATE OR REPLACE FUNCTION elmos_commercial_credit_journal_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'ELMOS_CREDIT_JOURNAL_APPEND_ONLY';
END;
$$;

CREATE TRIGGER commercial_credit_journal_transactions_append_only
BEFORE UPDATE OR DELETE ON commercial_credit_journal_transactions
FOR EACH ROW EXECUTE FUNCTION elmos_commercial_credit_journal_immutable();

CREATE TRIGGER commercial_credit_journal_entries_append_only
BEFORE UPDATE OR DELETE ON commercial_credit_journal_entries
FOR EACH ROW EXECUTE FUNCTION elmos_commercial_credit_journal_immutable();

CREATE OR REPLACE FUNCTION elmos_assert_commercial_credit_transaction_balanced()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_transaction_id varchar := coalesce(NEW.transaction_id, OLD.transaction_id);
    v_debits numeric;
    v_credits numeric;
    v_postings integer;
BEGIN
    SELECT coalesce(sum(quantity) FILTER (WHERE side = 'DEBIT'), 0),
           coalesce(sum(quantity) FILTER (WHERE side = 'CREDIT'), 0),
           count(*)
      INTO v_debits, v_credits, v_postings
      FROM public.commercial_credit_journal_entries
     WHERE transaction_id = v_transaction_id;
    IF v_postings < 2 OR v_debits <> v_credits THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_JOURNAL_UNBALANCED';
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER commercial_credit_transaction_balance_from_header
AFTER INSERT ON commercial_credit_journal_transactions
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION elmos_assert_commercial_credit_transaction_balanced();

CREATE CONSTRAINT TRIGGER commercial_credit_transaction_balance_from_posting
AFTER INSERT OR UPDATE OR DELETE ON commercial_credit_journal_entries
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION elmos_assert_commercial_credit_transaction_balanced();

CREATE TABLE commercial_credit_outbox_events (
    event_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    transaction_id varchar(96) NOT NULL UNIQUE,
    event_type varchar(48) NOT NULL DEFAULT 'COMMERCIAL_CREDIT_BALANCE_CHANGED',
    schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version = 1),
    payload jsonb NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_owner varchar(128),
    lease_expires_at timestamptz,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    published_at timestamptz,
    last_error varchar(255),
    CHECK ((lease_owner IS NULL) = (lease_expires_at IS NULL)),
    CHECK (published_at IS NULL OR lease_owner IS NULL),
    UNIQUE (event_id, organization_id),
    FOREIGN KEY (transaction_id, organization_id)
        REFERENCES commercial_credit_journal_transactions(transaction_id, organization_id)
);

CREATE INDEX idx_commercial_credit_outbox_pending
    ON commercial_credit_outbox_events (available_at, occurred_at)
    WHERE published_at IS NULL;

CREATE OR REPLACE FUNCTION elmos_guard_commercial_credit_outbox_event()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.event_id IS DISTINCT FROM OLD.event_id
       OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.transaction_id IS DISTINCT FROM OLD.transaction_id
       OR NEW.event_type IS DISTINCT FROM OLD.event_type
       OR NEW.schema_version IS DISTINCT FROM OLD.schema_version
       OR NEW.payload IS DISTINCT FROM OLD.payload
       OR NEW.occurred_at IS DISTINCT FROM OLD.occurred_at THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_OUTBOX_EVENT_IMMUTABLE';
    END IF;
    IF NEW.attempt_count < OLD.attempt_count OR OLD.published_at IS NOT NULL THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_OUTBOX_DELIVERY_IMMUTABLE';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER commercial_credit_outbox_event_guard
BEFORE UPDATE ON commercial_credit_outbox_events
FOR EACH ROW EXECUTE FUNCTION elmos_guard_commercial_credit_outbox_event();

CREATE TRIGGER commercial_credit_outbox_no_delete
BEFORE DELETE ON commercial_credit_outbox_events
FOR EACH ROW EXECUTE FUNCTION elmos_commercial_credit_journal_immutable();

CREATE TABLE commercial_credit_outbox_delivery_attempts (
    event_id varchar(96) NOT NULL,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    attempt_number integer NOT NULL CHECK (attempt_number > 0),
    worker_id varchar(128) NOT NULL,
    outcome varchar(20) NOT NULL CHECK (outcome IN ('PUBLISHED', 'RETRY_SCHEDULED')),
    error_message varchar(255),
    completed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, attempt_number),
    FOREIGN KEY (event_id, organization_id)
        REFERENCES commercial_credit_outbox_events(event_id, organization_id),
    CHECK ((outcome = 'PUBLISHED' AND error_message IS NULL)
        OR (outcome = 'RETRY_SCHEDULED' AND error_message IS NOT NULL))
);

CREATE TRIGGER commercial_credit_outbox_delivery_attempts_append_only
BEFORE UPDATE OR DELETE ON commercial_credit_outbox_delivery_attempts
FOR EACH ROW EXECUTE FUNCTION elmos_commercial_credit_journal_immutable();

CREATE TABLE commercial_credit_projection_rebuilds (
    rebuild_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    actor_id varchar(128) NOT NULL,
    reason varchar(255) NOT NULL CHECK (length(trim(reason)) >= 8),
    idempotency_key varchar(160) NOT NULL,
    balance_before numeric(19,0) NOT NULL,
    reserved_before numeric(19,0) NOT NULL,
    balance_after numeric(19,0) NOT NULL,
    reserved_after numeric(19,0) NOT NULL,
    projection_version bigint NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TRIGGER commercial_credit_projection_rebuilds_append_only
BEFORE UPDATE OR DELETE ON commercial_credit_projection_rebuilds
FOR EACH ROW EXECUTE FUNCTION elmos_commercial_credit_journal_immutable();

-- A one-time opening transaction preserves pre-V87 balances without pretending
-- that this migration can recreate provider or actor facts that were not stored.
INSERT INTO commercial_credit_journal_transactions (
    transaction_id, organization_id, projection_version, operation_type,
    actor_id, correlation_id, causation_id, idempotency_key, source_type, source_ref,
    balance_before, reserved_before, balance_after, reserved_after, occurred_at)
SELECT 'credit-opening-' || md5(organization_id), organization_id, account_version,
       'OPENING_BALANCE', 'system:v87-migration',
       'v87-opening:' || organization_id, 'v87-opening:' || organization_id,
       'v87-opening:' || organization_id, 'MIGRATION', 'V87',
       0, 0, balance, reserved, updated_at
  FROM commercial_credit_accounts
 WHERE balance > 0 OR reserved > 0;

INSERT INTO commercial_credit_journal_entries (
    posting_id, transaction_id, organization_id, account_code, side, quantity, occurred_at)
SELECT 'credit-opening-' || md5(organization_id) || ':01',
       'credit-opening-' || md5(organization_id), organization_id,
       'PLATFORM_CLEARING', 'DEBIT', balance - reserved, updated_at
  FROM commercial_credit_accounts WHERE balance - reserved > 0
UNION ALL
SELECT 'credit-opening-' || md5(organization_id) || ':02',
       'credit-opening-' || md5(organization_id), organization_id,
       'CUSTOMER_AVAILABLE', 'CREDIT', balance - reserved, updated_at
  FROM commercial_credit_accounts WHERE balance - reserved > 0
UNION ALL
SELECT 'credit-opening-' || md5(organization_id) || ':03',
       'credit-opening-' || md5(organization_id), organization_id,
       'PLATFORM_CLEARING', 'DEBIT', reserved, updated_at
  FROM commercial_credit_accounts WHERE reserved > 0
UNION ALL
SELECT 'credit-opening-' || md5(organization_id) || ':04',
       'credit-opening-' || md5(organization_id), organization_id,
       'CUSTOMER_RESERVED', 'CREDIT', reserved, updated_at
  FROM commercial_credit_accounts WHERE reserved > 0;

-- Fire the deferred balance assertions before the migration changes RLS on the
-- journal tables; PostgreSQL refuses ALTER TABLE while trigger events are pending.
SET CONSTRAINTS commercial_credit_transaction_balance_from_header,
    commercial_credit_transaction_balance_from_posting IMMEDIATE;

CREATE OR REPLACE FUNCTION elmos_post_commercial_credit_account_change()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_before_balance numeric := CASE WHEN TG_OP = 'INSERT' THEN 0 ELSE OLD.balance END;
    v_before_reserved numeric := CASE WHEN TG_OP = 'INSERT' THEN 0 ELSE OLD.reserved END;
    v_available_delta numeric;
    v_reserved_delta numeric;
    v_operation varchar;
    v_actor varchar;
    v_correlation varchar;
    v_causation varchar;
    v_idempotency varchar;
    v_source_type varchar;
    v_source_ref varchar;
    v_transaction_id varchar;
    v_posting integer := 0;
BEGIN
    IF current_setting('app.commercial_credit_rebuild', true) = 'on' THEN
        RETURN NEW;
    END IF;
    v_available_delta := (NEW.balance - NEW.reserved)
        - (v_before_balance - v_before_reserved);
    v_reserved_delta := NEW.reserved - v_before_reserved;
    IF v_available_delta = 0 AND v_reserved_delta = 0 THEN RETURN NEW; END IF;

    v_operation := nullif(current_setting('app.commercial_credit_operation', true), '');
    IF v_operation IS NULL OR v_operation NOT IN (
        'PURCHASE', 'RESERVE', 'CAPTURE', 'RELEASE', 'EXPIRY', 'REFUND', 'ADJUSTMENT') THEN
        v_operation := CASE
            WHEN NEW.balance > v_before_balance AND NEW.reserved = v_before_reserved THEN 'PURCHASE'
            WHEN NEW.balance = v_before_balance AND NEW.reserved > v_before_reserved THEN 'RESERVE'
            WHEN NEW.balance < v_before_balance AND NEW.reserved < v_before_reserved THEN 'CAPTURE'
            WHEN NEW.balance = v_before_balance AND NEW.reserved < v_before_reserved THEN 'RELEASE'
            WHEN NEW.balance < v_before_balance THEN 'EXPIRY'
            ELSE 'ADJUSTMENT' END;
    END IF;
    v_transaction_id := 'credit-journal-' || md5(NEW.organization_id || ':' || NEW.account_version);
    v_actor := coalesce(nullif(current_setting('app.commercial_credit_actor', true), ''),
                        'system:commercial-credit');
    v_correlation := coalesce(nullif(current_setting('app.commercial_credit_correlation', true), ''),
                              v_transaction_id);
    v_causation := coalesce(nullif(current_setting('app.commercial_credit_causation', true), ''),
                            v_correlation);
    v_idempotency := left(coalesce(
        nullif(current_setting('app.commercial_credit_idempotency', true), ''),
        'account-projection'), 128) || ':version:' || NEW.account_version;
    v_source_type := coalesce(nullif(current_setting('app.commercial_credit_source_type', true), ''),
                              'ACCOUNT_PROJECTION');
    v_source_ref := coalesce(nullif(current_setting('app.commercial_credit_source_ref', true), ''),
                             NEW.organization_id || ':' || NEW.account_version);

    INSERT INTO commercial_credit_journal_transactions (
        transaction_id, organization_id, projection_version, operation_type, actor_id,
        correlation_id, causation_id, idempotency_key, source_type, source_ref,
        balance_before, reserved_before, balance_after, reserved_after)
    VALUES (v_transaction_id, NEW.organization_id, NEW.account_version, v_operation, left(v_actor, 128),
            left(v_correlation, 160), left(v_causation, 160), v_idempotency,
            left(v_source_type, 32), left(v_source_ref, 160),
            v_before_balance, v_before_reserved, NEW.balance, NEW.reserved);

    IF v_available_delta <> 0 THEN
        v_posting := v_posting + 1;
        INSERT INTO commercial_credit_journal_entries VALUES (
            v_transaction_id || ':' || lpad(v_posting::text, 2, '0'), v_transaction_id,
            NEW.organization_id,
            CASE WHEN v_available_delta > 0 THEN 'PLATFORM_CLEARING' ELSE 'CUSTOMER_AVAILABLE' END,
            'DEBIT', abs(v_available_delta), now());
        v_posting := v_posting + 1;
        INSERT INTO commercial_credit_journal_entries VALUES (
            v_transaction_id || ':' || lpad(v_posting::text, 2, '0'), v_transaction_id,
            NEW.organization_id,
            CASE WHEN v_available_delta > 0 THEN 'CUSTOMER_AVAILABLE' ELSE 'PLATFORM_CLEARING' END,
            'CREDIT', abs(v_available_delta), now());
    END IF;
    IF v_reserved_delta <> 0 THEN
        v_posting := v_posting + 1;
        INSERT INTO commercial_credit_journal_entries VALUES (
            v_transaction_id || ':' || lpad(v_posting::text, 2, '0'), v_transaction_id,
            NEW.organization_id,
            CASE WHEN v_reserved_delta > 0 THEN 'PLATFORM_CLEARING' ELSE 'CUSTOMER_RESERVED' END,
            'DEBIT', abs(v_reserved_delta), now());
        v_posting := v_posting + 1;
        INSERT INTO commercial_credit_journal_entries VALUES (
            v_transaction_id || ':' || lpad(v_posting::text, 2, '0'), v_transaction_id,
            NEW.organization_id,
            CASE WHEN v_reserved_delta > 0 THEN 'CUSTOMER_RESERVED' ELSE 'PLATFORM_CLEARING' END,
            'CREDIT', abs(v_reserved_delta), now());
    END IF;

    INSERT INTO commercial_credit_outbox_events (
        event_id, organization_id, transaction_id, payload)
    VALUES ('credit-outbox-' || md5(v_transaction_id), NEW.organization_id, v_transaction_id,
            jsonb_build_object(
                'transactionId', v_transaction_id,
                'organizationId', NEW.organization_id,
                'operationType', v_operation,
                'projectionVersion', NEW.account_version,
                'balance', NEW.balance,
                'reserved', NEW.reserved,
                'spendable', NEW.balance - NEW.reserved));
    RETURN NEW;
END;
$$;

CREATE TRIGGER commercial_credit_account_double_entry
AFTER INSERT OR UPDATE OF balance, reserved ON commercial_credit_accounts
FOR EACH ROW EXECUTE FUNCTION elmos_post_commercial_credit_account_change();

CREATE OR REPLACE FUNCTION elmos_commercial_credit_reconcile()
RETURNS TABLE (
    organization_id varchar, projected_balance numeric, journal_balance numeric,
    projected_reserved numeric, journal_reserved numeric,
    balance_drift numeric, reserved_drift numeric, unbalanced_transactions bigint)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
WITH journal AS (
    SELECT coalesce(sum(CASE WHEN account_code = 'CUSTOMER_AVAILABLE'
                                  THEN CASE side WHEN 'CREDIT' THEN quantity ELSE -quantity END
                             ELSE 0 END), 0) AS available,
           coalesce(sum(CASE WHEN account_code = 'CUSTOMER_RESERVED'
                                  THEN CASE side WHEN 'CREDIT' THEN quantity ELSE -quantity END
                             ELSE 0 END), 0) AS reserved
      FROM public.commercial_credit_journal_entries
     WHERE organization_id = public.elmos_current_organization_id()
), unbalanced AS (
    SELECT count(*) AS count
      FROM (
        SELECT transaction_id
          FROM public.commercial_credit_journal_entries
         WHERE organization_id = public.elmos_current_organization_id()
         GROUP BY transaction_id
        HAVING sum(quantity) FILTER (WHERE side = 'DEBIT')
             <> sum(quantity) FILTER (WHERE side = 'CREDIT')
      ) drift
)
SELECT a.organization_id, a.balance, journal.available + journal.reserved,
       a.reserved, journal.reserved,
       a.balance - (journal.available + journal.reserved),
       a.reserved - journal.reserved, unbalanced.count
  FROM public.commercial_credit_accounts a CROSS JOIN journal CROSS JOIN unbalanced
 WHERE a.organization_id = public.elmos_current_organization_id();
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_credit_reconciler') THEN
        CREATE ROLE elmos_credit_reconciler NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_credit_outbox_publisher') THEN
        CREATE ROLE elmos_credit_outbox_publisher NOLOGIN;
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION elmos_commercial_rebuild_credit_projection(
    p_actor_id varchar, p_reason varchar, p_idempotency_key varchar
) RETURNS varchar LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_org varchar := public.elmos_current_organization_id();
    v_account public.commercial_credit_accounts%ROWTYPE;
    v_existing public.commercial_credit_projection_rebuilds%ROWTYPE;
    v_balance numeric;
    v_reserved numeric;
    v_rebuild_id varchar;
BEGIN
    IF NOT pg_catalog.pg_has_role(session_user, 'elmos_credit_reconciler', 'USAGE') THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_REBUILD_FORBIDDEN';
    END IF;
    IF v_org IS NULL OR p_actor_id IS NULL OR length(trim(p_actor_id)) = 0
       OR length(p_actor_id) > 128
       OR p_reason IS NULL OR length(trim(p_reason)) < 8
       OR length(p_reason) > 255
       OR p_idempotency_key IS NULL OR length(trim(p_idempotency_key)) < 8
       OR length(p_idempotency_key) > 160 THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_REBUILD_INPUT_INVALID';
    END IF;
    SELECT * INTO v_existing FROM public.commercial_credit_projection_rebuilds
     WHERE organization_id = v_org AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.actor_id <> p_actor_id OR v_existing.reason <> p_reason THEN
            RAISE EXCEPTION 'ELMOS_CREDIT_REBUILD_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.rebuild_id;
    END IF;
    SELECT * INTO v_account FROM public.commercial_credit_accounts
     WHERE organization_id = v_org FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_CREDIT_ACCOUNT_NOT_FOUND'; END IF;
    SELECT coalesce(sum(CASE WHEN account_code IN ('CUSTOMER_AVAILABLE', 'CUSTOMER_RESERVED')
                                  THEN CASE side WHEN 'CREDIT' THEN quantity ELSE -quantity END
                             ELSE 0 END), 0),
           coalesce(sum(CASE WHEN account_code = 'CUSTOMER_RESERVED'
                                  THEN CASE side WHEN 'CREDIT' THEN quantity ELSE -quantity END
                             ELSE 0 END), 0)
      INTO v_balance, v_reserved
      FROM public.commercial_credit_journal_entries WHERE organization_id = v_org;
    IF v_balance < 0 OR v_reserved < 0 OR v_reserved > v_balance THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_REBUILD_JOURNAL_INVALID';
    END IF;
    PERFORM set_config('app.commercial_credit_rebuild', 'on', true);
    PERFORM set_config('app.commercial_credit_posting', 'on', true);
    UPDATE public.commercial_credit_accounts
       SET balance = v_balance, reserved = v_reserved,
           account_version = account_version + 1, updated_at = now()
     WHERE organization_id = v_org;
    PERFORM set_config('app.commercial_credit_posting', '', true);
    PERFORM set_config('app.commercial_credit_rebuild', '', true);
    v_rebuild_id := 'credit-rebuild-' || md5(v_org || ':' || p_idempotency_key);
    INSERT INTO public.commercial_credit_projection_rebuilds (
        rebuild_id, organization_id, actor_id, reason, idempotency_key,
        balance_before, reserved_before, balance_after, reserved_after, projection_version)
    VALUES (v_rebuild_id, v_org, p_actor_id, p_reason, p_idempotency_key,
            v_account.balance, v_account.reserved, v_balance, v_reserved,
            v_account.account_version + 1);
    RETURN v_rebuild_id;
EXCEPTION WHEN OTHERS THEN
    PERFORM set_config('app.commercial_credit_posting', '', true);
    PERFORM set_config('app.commercial_credit_rebuild', '', true);
    RAISE;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_claim_commercial_credit_outbox(
    p_worker_id varchar, p_limit integer, p_lease_seconds integer
) RETURNS TABLE (
    event_id varchar, organization_id varchar, transaction_id varchar,
    event_type varchar, schema_version integer, payload jsonb, occurred_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    IF NOT pg_catalog.pg_has_role(session_user, 'elmos_credit_outbox_publisher', 'USAGE') THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_OUTBOX_CLAIM_FORBIDDEN';
    END IF;
    IF p_worker_id IS NULL OR length(trim(p_worker_id)) < 3 OR length(p_worker_id) > 128
       OR p_limit IS NULL OR p_limit < 1 OR p_limit > 1000
       OR p_lease_seconds IS NULL OR p_lease_seconds < 10 OR p_lease_seconds > 600 THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_OUTBOX_CLAIM_INVALID';
    END IF;
    RETURN QUERY
    WITH candidates AS (
        SELECT o.event_id FROM public.commercial_credit_outbox_events o
         WHERE o.published_at IS NULL AND o.available_at <= now()
           AND (o.lease_expires_at IS NULL OR o.lease_expires_at <= now())
         ORDER BY o.available_at, o.occurred_at, o.event_id
         LIMIT p_limit FOR UPDATE SKIP LOCKED
    )
    UPDATE public.commercial_credit_outbox_events o
       SET lease_owner = p_worker_id,
           lease_expires_at = now() + make_interval(secs => p_lease_seconds),
           attempt_count = o.attempt_count + 1,
           last_error = NULL
      FROM candidates c WHERE o.event_id = c.event_id
    RETURNING o.event_id, o.organization_id, o.transaction_id,
              o.event_type, o.schema_version, o.payload, o.occurred_at;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_complete_commercial_credit_outbox(
    p_event_id varchar, p_worker_id varchar, p_published boolean, p_error varchar
) RETURNS varchar LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    v_status varchar;
    v_organization_id varchar;
    v_attempt_number integer;
BEGIN
    IF NOT pg_catalog.pg_has_role(session_user, 'elmos_credit_outbox_publisher', 'USAGE') THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_OUTBOX_COMPLETE_FORBIDDEN';
    END IF;
    IF p_event_id IS NULL OR length(trim(p_event_id)) = 0 OR length(p_event_id) > 96
       OR p_worker_id IS NULL OR length(trim(p_worker_id)) < 3 OR length(p_worker_id) > 128
       OR p_published IS NULL
       OR (NOT p_published AND (p_error IS NULL OR length(trim(p_error)) = 0)) THEN
        RAISE EXCEPTION 'ELMOS_CREDIT_OUTBOX_COMPLETE_INVALID';
    END IF;
    UPDATE public.commercial_credit_outbox_events
       SET published_at = CASE WHEN p_published THEN now() ELSE NULL END,
           available_at = CASE WHEN p_published THEN available_at
                               ELSE now() + interval '1 minute' END,
           lease_owner = NULL, lease_expires_at = NULL,
           last_error = CASE WHEN p_published THEN NULL ELSE left(p_error, 255) END
     WHERE event_id = p_event_id AND lease_owner = p_worker_id
       AND published_at IS NULL AND lease_expires_at > now()
     RETURNING organization_id, attempt_count,
               CASE WHEN published_at IS NULL THEN 'RETRY_SCHEDULED' ELSE 'PUBLISHED' END
      INTO v_organization_id, v_attempt_number, v_status;
    IF FOUND THEN
        INSERT INTO public.commercial_credit_outbox_delivery_attempts (
            event_id, organization_id, attempt_number, worker_id, outcome, error_message)
        VALUES (p_event_id, v_organization_id, v_attempt_number, p_worker_id, v_status,
                CASE WHEN p_published THEN NULL ELSE left(p_error, 255) END);
        RETURN v_status;
    END IF;
    SELECT CASE WHEN published_at IS NULL THEN 'NOT_CLAIMED' ELSE 'PUBLISHED' END
      INTO v_status FROM public.commercial_credit_outbox_events WHERE event_id = p_event_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_CREDIT_OUTBOX_EVENT_NOT_FOUND'; END IF;
    RETURN v_status;
END;
$$;

-- Journal/audit data stays tenant scoped. The cross-tenant outbox carries only
-- accounting identifiers and totals and is reachable exclusively via leased
-- SECURITY DEFINER functions granted to a non-login publisher role.
DO $$
DECLARE v_table text;
BEGIN
    FOREACH v_table IN ARRAY ARRAY[
        'commercial_credit_journal_transactions',
        'commercial_credit_journal_entries',
        'commercial_credit_projection_rebuilds'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', v_table);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', v_table);
        EXECUTE format(
            'CREATE POLICY %I ON %I USING '
            || '(organization_id = elmos_current_organization_id()) WITH CHECK '
            || '(organization_id = elmos_current_organization_id())',
            v_table || '_tenant_policy', v_table);
    END LOOP;
END
$$;

REVOKE ALL ON commercial_credit_journal_transactions,
    commercial_credit_journal_entries, commercial_credit_projection_rebuilds,
    commercial_credit_outbox_events, commercial_credit_outbox_delivery_attempts FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_commercial_credit_reconcile() FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_commercial_rebuild_credit_projection(varchar, varchar, varchar)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_claim_commercial_credit_outbox(varchar, integer, integer)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_complete_commercial_credit_outbox(varchar, varchar, boolean, varchar)
    FROM PUBLIC;

GRANT EXECUTE ON FUNCTION elmos_commercial_rebuild_credit_projection(varchar, varchar, varchar)
    TO elmos_credit_reconciler;
GRANT EXECUTE ON FUNCTION elmos_claim_commercial_credit_outbox(varchar, integer, integer)
    TO elmos_credit_outbox_publisher;
GRANT EXECUTE ON FUNCTION elmos_complete_commercial_credit_outbox(varchar, varchar, boolean, varchar)
    TO elmos_credit_outbox_publisher;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_billing_runtime') THEN
        GRANT SELECT ON commercial_credit_journal_transactions,
            commercial_credit_journal_entries, commercial_credit_projection_rebuilds
            TO elmos_billing_runtime;
        GRANT EXECUTE ON FUNCTION elmos_commercial_credit_reconcile()
            TO elmos_billing_runtime;
    END IF;
END
$$;
