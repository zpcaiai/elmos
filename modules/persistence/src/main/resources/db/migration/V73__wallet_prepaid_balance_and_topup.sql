-- ELMOS V73: prepaid wallet, ledger, reservations and top-up orders.
--
-- Why this migration exists
-- -------------------------
-- V49 gave the CNY self-service line a subscription model: a plan version, a
-- billing period and a per-period quota allowance. A period allowance cannot
-- express the thing self-service users actually ask for -- money that they put
-- in, that carries across periods, and that they can watch go down. V73 adds
-- that as a second, independent means of payment. It does NOT replace V49:
-- entitlement is resolved allowance-first, wallet-second (wired in a later
-- migration), so a subscribed tenant sees no behaviour change.
--
-- What is deliberately NOT here
-- -----------------------------
-- This migration is purely additive: it creates new tables and functions and
-- touches no existing table, trigger or function. The enqueue-time charge and
-- the terminal-state settlement hook are a separate migration, behind a flag,
-- so that this one can be applied and rolled forward with zero behavioural
-- risk to the running job queue.
--
-- Accounting model
-- ----------------
-- `wallet_ledger_entries` is the sole authority and records ONLY real movements
-- of money: a top-up credits, a settled job debits, a refund credits, an
-- administrator adjustment does either. Reservations are NOT ledger entries.
-- Holding money for a job that has not run yet is not a movement -- writing it
-- as one makes `balance_after_minor` mean two different things on two different
-- rows, which is exactly the ambiguity that makes a ledger unauditable.
-- A hold lives in `wallet_reservations` with its own state machine, and the
-- spendable figure is `balance_minor - reserved_minor`.
--
-- That gives two invariants, each checkable on its own:
--   balance_minor  = SUM(credits) - SUM(debits) over wallet_ledger_entries
--   reserved_minor = SUM(amount_minor) over wallet_reservations WHERE status='HELD'
--
-- Tenancy
-- -------
-- Every tenant-scoped table here is FORCE ROW LEVEL SECURITY under the same
-- app.organization_id policy as V49/V51/V52. `wallet_price_book` is a global
-- catalog with no organization_id (same shape as
-- self_service_pricing_plan_versions). `wallet_settlement_outbox` carries no
-- customer content and is deliberately NOT tenant isolated, for the same reason
-- execution_job_dispatch is not: a cross-tenant settler cannot run under a
-- per-transaction app.organization_id. It is reachable only by a role.

-- ---------------------------------------------------------------------------
-- 1. Settlement role
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_wallet_settler') THEN
        CREATE ROLE elmos_wallet_settler NOLOGIN;
    END IF;
END;
$$;

COMMENT ON ROLE elmos_wallet_settler IS
    'Non-login role owning the cross-tenant settlement outbox. Granted to the control-plane application role only. It can never read wallet balances or ledgers directly; it reaches them through SECURITY DEFINER functions that bind an explicit organization.';

-- ---------------------------------------------------------------------------
-- 2. Wallets
-- ---------------------------------------------------------------------------

CREATE TABLE wallet_accounts (
    organization_id varchar(96) PRIMARY KEY REFERENCES organizations(organization_id),
    currency char(3) NOT NULL DEFAULT 'CNY' CHECK (currency = 'CNY'),
    balance_minor numeric(19,0) NOT NULL DEFAULT 0 CHECK (balance_minor >= 0),
    reserved_minor numeric(19,0) NOT NULL DEFAULT 0 CHECK (reserved_minor >= 0),
    status varchar(16) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'FROZEN', 'CLOSED')),
    last_entry_seq bigint NOT NULL DEFAULT 0 CHECK (last_entry_seq >= 0),
    frozen_reason varchar(255),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    state_version bigint NOT NULL DEFAULT 0,
    -- Reserved money must be money that is actually there. Without this a bug in
    -- the hold path can promise the same balance to two jobs and only be found
    -- when the second one settles into a negative balance.
    CONSTRAINT wallet_accounts_reserved_within_balance CHECK (reserved_minor <= balance_minor),
    CONSTRAINT wallet_accounts_frozen_shape CHECK (status <> 'FROZEN' OR frozen_reason IS NOT NULL)
);

COMMENT ON TABLE wallet_accounts IS
    'Materialized prepaid balance per tenant. NOT the authority: wallet_ledger_entries is. Balance and reservation columns are writable only from the SECURITY DEFINER accounting functions -- a direct UPDATE is rejected by wallet_accounts_balance_guard.';
COMMENT ON COLUMN wallet_accounts.reserved_minor IS
    'Sum of HELD reservations. Spendable balance is balance_minor - reserved_minor.';
COMMENT ON COLUMN wallet_accounts.last_entry_seq IS
    'High water mark of the per-tenant ledger sequence. Advanced under the wallet row lock so two concurrent postings cannot mint the same seq.';

-- ---------------------------------------------------------------------------
-- 3. Ledger (append-only, the authority)
-- ---------------------------------------------------------------------------

CREATE TABLE wallet_ledger_entries (
    entry_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    seq bigint NOT NULL CHECK (seq > 0),
    currency char(3) NOT NULL DEFAULT 'CNY' CHECK (currency = 'CNY'),
    direction varchar(8) NOT NULL CHECK (direction IN ('CREDIT', 'DEBIT')),
    amount_minor numeric(19,0) NOT NULL CHECK (amount_minor > 0),
    balance_after_minor numeric(19,0) NOT NULL CHECK (balance_after_minor >= 0),
    entry_type varchar(24) NOT NULL CHECK (entry_type IN (
        'TOPUP_SETTLED', 'CONSUME', 'REFUND', 'ADMIN_ADJUSTMENT', 'TRIAL_GRANT'
    )),
    source_type varchar(16) NOT NULL CHECK (source_type IN (
        'TOPUP_ORDER', 'JOB', 'ADMIN', 'SYSTEM'
    )),
    source_ref varchar(160) NOT NULL,
    reservation_ref varchar(96),
    actor_id varchar(128) NOT NULL,
    idempotency_key varchar(160) NOT NULL,
    reason varchar(255),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, seq),
    -- The single most load-bearing constraint here. Payment callback replay,
    -- runner retry and a double-clicked administrator all collapse onto this,
    -- rather than onto every caller remembering to check first.
    UNIQUE (organization_id, idempotency_key),
    -- Moving money by hand without saying why is how a ledger stops being
    -- evidence. Required at the storage layer, not in a form validator.
    CONSTRAINT wallet_ledger_entries_adjustment_reason
        CHECK (entry_type <> 'ADMIN_ADJUSTMENT' OR reason IS NOT NULL),
    CONSTRAINT wallet_ledger_entries_direction_shape CHECK (
        (entry_type IN ('TOPUP_SETTLED', 'REFUND', 'TRIAL_GRANT') AND direction = 'CREDIT')
        OR (entry_type = 'CONSUME' AND direction = 'DEBIT')
        OR entry_type = 'ADMIN_ADJUSTMENT'
    ),
    CONSTRAINT wallet_ledger_entries_consume_shape CHECK (
        entry_type <> 'CONSUME' OR (reservation_ref IS NOT NULL AND source_type = 'JOB')
    )
);

CREATE INDEX idx_wallet_ledger_entries_org_time
    ON wallet_ledger_entries (organization_id, occurred_at DESC);
CREATE INDEX idx_wallet_ledger_entries_org_type
    ON wallet_ledger_entries (organization_id, entry_type, occurred_at DESC);
CREATE INDEX idx_wallet_ledger_entries_source
    ON wallet_ledger_entries (source_type, source_ref);

CREATE TRIGGER wallet_ledger_entries_append_only
BEFORE UPDATE OR DELETE ON wallet_ledger_entries
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

COMMENT ON TABLE wallet_ledger_entries IS
    'Authoritative record of every real movement of prepaid money. Append-only. Holds are not movements and are not recorded here; see wallet_reservations.';
COMMENT ON COLUMN wallet_ledger_entries.balance_after_minor IS
    'Balance immediately after this entry. Lets the ledger prove itself by replay without trusting wallet_accounts, which is what the reconciliation check compares against.';

-- ---------------------------------------------------------------------------
-- 4. Reservations (holds against future job cost)
-- ---------------------------------------------------------------------------

CREATE TABLE wallet_reservations (
    reservation_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    job_id varchar(96) NOT NULL,
    amount_minor numeric(19,0) NOT NULL CHECK (amount_minor > 0),
    settled_amount_minor numeric(19,0) CHECK (settled_amount_minor IS NULL OR settled_amount_minor >= 0),
    status varchar(16) NOT NULL DEFAULT 'HELD'
        CHECK (status IN ('HELD', 'SETTLED', 'RELEASED', 'EXPIRED')),
    quote_ref varchar(96) NOT NULL,
    actor_id varchar(128) NOT NULL,
    held_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    resolved_at timestamptz,
    resolution_code varchar(48),
    state_version bigint NOT NULL DEFAULT 0,
    -- One live hold per job. Without this a retried enqueue holds the money twice
    -- and only one of the two is ever settled.
    UNIQUE (organization_id, job_id),
    CONSTRAINT wallet_reservations_expiry_after_hold CHECK (expires_at > held_at),
    CONSTRAINT wallet_reservations_resolved_shape
        CHECK (status = 'HELD' OR resolved_at IS NOT NULL),
    -- A job can never be charged more than was held for it. This is the promise
    -- the user was shown at submit time.
    CONSTRAINT wallet_reservations_settled_shape CHECK (
        status <> 'SETTLED' OR (
            settled_amount_minor IS NOT NULL
            AND settled_amount_minor <= amount_minor
        )
    ),
    CONSTRAINT wallet_reservations_unsettled_shape CHECK (
        status = 'SETTLED' OR settled_amount_minor IS NULL
    )
);

CREATE INDEX idx_wallet_reservations_org_status
    ON wallet_reservations (organization_id, status, held_at DESC);
-- Drives the expiry sweeper. Partial so it stays small: resolved holds are the
-- overwhelming majority and are of no interest to it.
CREATE INDEX idx_wallet_reservations_expiring
    ON wallet_reservations (expires_at) WHERE status = 'HELD';

CREATE OR REPLACE FUNCTION elmos_guard_wallet_reservation_transition()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status <> 'HELD' AND NEW.status IS DISTINCT FROM OLD.status THEN
        RAISE EXCEPTION 'ELMOS_WALLET_RESERVATION_TERMINAL_IMMUTABLE';
    END IF;
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
        RAISE EXCEPTION 'ELMOS_WALLET_RESERVATION_TENANT_IMMUTABLE';
    END IF;
    IF NEW.job_id IS DISTINCT FROM OLD.job_id THEN
        RAISE EXCEPTION 'ELMOS_WALLET_RESERVATION_JOB_IMMUTABLE';
    END IF;
    IF NEW.amount_minor IS DISTINCT FROM OLD.amount_minor THEN
        RAISE EXCEPTION 'ELMOS_WALLET_RESERVATION_AMOUNT_IMMUTABLE';
    END IF;
    NEW.state_version := OLD.state_version + 1;
    RETURN NEW;
END;
$$;

CREATE TRIGGER wallet_reservations_transition_guard
BEFORE UPDATE ON wallet_reservations
FOR EACH ROW EXECUTE FUNCTION elmos_guard_wallet_reservation_transition();

COMMENT ON TABLE wallet_reservations IS
    'Money held against a job that has not finished. Resolved exactly once into SETTLED (charged), RELEASED (given back) or EXPIRED (given back because nothing resolved it in time). Terminal states are immutable.';
COMMENT ON COLUMN wallet_reservations.expires_at IS
    'Leak guard. A runner that dies, or a settler that stops, must not freeze a tenant out of their own balance forever. The sweeper releases past this point, which under-charges rather than over-charges -- the deliberate direction to fail in.';

-- ---------------------------------------------------------------------------
-- 5. Top-up orders
-- ---------------------------------------------------------------------------
-- Deliberately a new table rather than a reuse of payment_checkout_sessions:
-- that table has plan_id NOT NULL and CHECK (provider = 'STRIPE_CHECKOUT').
-- A top-up has no plan and must reach WeChat Pay and Alipay. Relaxing those two
-- constraints would weaken subscription checkout, which is in production use,
-- to accommodate a case it was never meant to carry.

CREATE TABLE wallet_topup_orders (
    topup_order_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    actor_id varchar(128) NOT NULL,
    currency char(3) NOT NULL DEFAULT 'CNY' CHECK (currency = 'CNY'),
    amount_minor numeric(19,0) NOT NULL CHECK (amount_minor > 0),
    provider varchar(16) NOT NULL CHECK (provider IN ('WECHAT_PAY', 'ALIPAY', 'STRIPE', 'OFFLINE')),
    out_trade_no varchar(255) NOT NULL,
    provider_txn_ref varchar(255),
    status varchar(16) NOT NULL DEFAULT 'CREATED' CHECK (status IN (
        'CREATED', 'PENDING_PAYMENT', 'PAID', 'CREDITED', 'FAILED', 'EXPIRED', 'REFUNDED'
    )),
    credited_entry_ref varchar(96),
    failure_code varchar(96),
    idempotency_key varchar(160) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    paid_at timestamptz,
    credited_at timestamptz,
    expires_at timestamptz NOT NULL,
    state_version bigint NOT NULL DEFAULT 0,
    UNIQUE (provider, out_trade_no),
    UNIQUE (organization_id, idempotency_key),
    -- PAID and CREDITED are separate on purpose. "The channel confirmed the money"
    -- and "the money is in the wallet" are two events, and the gap between them
    -- is where money gets lost. Keeping them distinct makes that gap a state you
    -- can query and reconcile instead of an event nobody recorded.
    CONSTRAINT wallet_topup_orders_paid_shape
        CHECK (status NOT IN ('PAID', 'CREDITED', 'REFUNDED') OR paid_at IS NOT NULL),
    CONSTRAINT wallet_topup_orders_credited_shape CHECK (
        status <> 'CREDITED' OR (credited_entry_ref IS NOT NULL AND credited_at IS NOT NULL)
    ),
    CONSTRAINT wallet_topup_orders_failure_shape
        CHECK (status <> 'FAILED' OR failure_code IS NOT NULL),
    CONSTRAINT wallet_topup_orders_expiry CHECK (expires_at > created_at)
);

CREATE INDEX idx_wallet_topup_orders_org_time
    ON wallet_topup_orders (organization_id, created_at DESC);
-- The reconciliation view. This index exists to make "paid but not credited"
-- cheap to ask, because it should be asked constantly and should always be empty.
CREATE INDEX idx_wallet_topup_orders_uncredited
    ON wallet_topup_orders (paid_at) WHERE status = 'PAID';

CREATE OR REPLACE FUNCTION elmos_guard_wallet_topup_transition()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status IN ('CREDITED', 'FAILED', 'EXPIRED')
       AND NEW.status IS DISTINCT FROM OLD.status
       AND NOT (OLD.status = 'CREDITED' AND NEW.status = 'REFUNDED') THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_TERMINAL_IMMUTABLE';
    END IF;
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_TENANT_IMMUTABLE';
    END IF;
    IF NEW.amount_minor IS DISTINCT FROM OLD.amount_minor THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_AMOUNT_IMMUTABLE';
    END IF;
    IF NEW.out_trade_no IS DISTINCT FROM OLD.out_trade_no THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_TRADE_NO_IMMUTABLE';
    END IF;
    NEW.updated_at := now();
    NEW.state_version := OLD.state_version + 1;
    RETURN NEW;
END;
$$;

CREATE TRIGGER wallet_topup_orders_transition_guard
BEFORE UPDATE ON wallet_topup_orders
FOR EACH ROW EXECUTE FUNCTION elmos_guard_wallet_topup_transition();

COMMENT ON TABLE wallet_topup_orders IS
    'Prepaid top-up orders. Settled money reaches the wallet only through elmos_wallet_credit_topup, keyed on out_trade_no, so a replayed payment callback credits once.';

-- ---------------------------------------------------------------------------
-- 6. Per-tenant top-up policy
-- ---------------------------------------------------------------------------

CREATE TABLE wallet_topup_policies (
    organization_id varchar(96) PRIMARY KEY REFERENCES organizations(organization_id),
    min_amount_minor numeric(19,0) NOT NULL CHECK (min_amount_minor > 0),
    max_amount_minor numeric(19,0) NOT NULL CHECK (max_amount_minor > 0),
    daily_amount_limit_minor numeric(19,0) NOT NULL CHECK (daily_amount_limit_minor > 0),
    updated_by varchar(128) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT wallet_topup_policies_range CHECK (max_amount_minor >= min_amount_minor),
    CONSTRAINT wallet_topup_policies_daily CHECK (daily_amount_limit_minor >= max_amount_minor)
);

COMMENT ON TABLE wallet_topup_policies IS
    'Optional per-tenant override of the platform default top-up bounds. Absent means the defaults in elmos_wallet_topup_bounds apply. The upper bound protects the user from a mistyped amount; the daily bound is an anti-abuse control. They are different jobs and are therefore separate numbers.';

-- ---------------------------------------------------------------------------
-- 7. Price book (global catalog, append-only, versioned like V49)
-- ---------------------------------------------------------------------------

CREATE TABLE wallet_price_book (
    catalog_version varchar(64) NOT NULL,
    business_line varchar(32) NOT NULL,
    job_kind varchar(64) NOT NULL,
    currency char(3) NOT NULL DEFAULT 'CNY' CHECK (currency = 'CNY'),
    reserve_minor numeric(19,0) NOT NULL CHECK (reserve_minor > 0),
    unit varchar(16) NOT NULL CHECK (unit IN ('WALL_SECOND', 'TOKEN', 'JOB')),
    unit_price_minor numeric(19,0) NOT NULL CHECK (unit_price_minor >= 0),
    min_charge_minor numeric(19,0) NOT NULL CHECK (min_charge_minor >= 0),
    effective_from timestamptz NOT NULL,
    effective_until timestamptz,
    source_ref varchar(255) NOT NULL,
    status varchar(16) NOT NULL CHECK (status IN ('DRAFT', 'PUBLISHED', 'SUPERSEDED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (catalog_version, business_line, job_kind),
    CONSTRAINT wallet_price_book_window
        CHECK (effective_until IS NULL OR effective_until > effective_from),
    CONSTRAINT wallet_price_book_min_within_reserve CHECK (min_charge_minor <= reserve_minor),
    CONSTRAINT wallet_price_book_business_line CHECK (business_line IN (
        'GENERATION', 'TRANSLATION', 'SPRING_UPGRADE', 'REPOSITORY_WORKSPACE', 'MODERNIZATION_PROOF'
    ))
);

CREATE TRIGGER wallet_price_book_append_only
BEFORE UPDATE OR DELETE ON wallet_price_book
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

-- Seeded DRAFT, exactly as V49 seeds its plan versions: a price that nobody has
-- approved must not be able to charge anyone. Publishing is a separate act.
-- job_kind '*' is the per-line fallback.
INSERT INTO wallet_price_book (
    catalog_version, business_line, job_kind, reserve_minor, unit,
    unit_price_minor, min_charge_minor, effective_from, source_ref, status
) VALUES
    ('2026-08-25.1', 'GENERATION',           '*', 500,  'WALL_SECOND', 1, 50,  '2026-08-25T00:00:00Z', '.ai/DESIGN-2026-08-25-wallet-and-platform-admin.md', 'DRAFT'),
    ('2026-08-25.1', 'TRANSLATION',          '*', 2000, 'WALL_SECOND', 2, 100, '2026-08-25T00:00:00Z', '.ai/DESIGN-2026-08-25-wallet-and-platform-admin.md', 'DRAFT'),
    ('2026-08-25.1', 'SPRING_UPGRADE',       '*', 3000, 'WALL_SECOND', 2, 100, '2026-08-25T00:00:00Z', '.ai/DESIGN-2026-08-25-wallet-and-platform-admin.md', 'DRAFT'),
    ('2026-08-25.1', 'REPOSITORY_WORKSPACE', '*', 200,  'WALL_SECOND', 1, 20,  '2026-08-25T00:00:00Z', '.ai/DESIGN-2026-08-25-wallet-and-platform-admin.md', 'DRAFT'),
    ('2026-08-25.1', 'MODERNIZATION_PROOF',  '*', 1000, 'WALL_SECOND', 2, 50,  '2026-08-25T00:00:00Z', '.ai/DESIGN-2026-08-25-wallet-and-platform-admin.md', 'DRAFT');

COMMENT ON TABLE wallet_price_book IS
    'Versioned job pricing. Same governance shape as self_service_pricing_plan_versions so operations reason about one price lifecycle, not two. A reservation records the quote_ref it was priced against, so republishing prices never retroactively rewrites a settled job.';

-- ---------------------------------------------------------------------------
-- 8. Settlement outbox (cross-tenant, no customer content)
-- ---------------------------------------------------------------------------

CREATE TABLE wallet_settlement_outbox (
    outbox_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL,
    job_id varchar(96) NOT NULL,
    reservation_id varchar(96) NOT NULL,
    job_status varchar(24) NOT NULL,
    failure_code varchar(96),
    enqueued_at timestamptz NOT NULL DEFAULT now(),
    attempts smallint NOT NULL DEFAULT 0 CHECK (attempts >= 0 AND attempts <= 20),
    claimed_until timestamptz,
    resolved_at timestamptz,
    last_error_code varchar(96),
    UNIQUE (job_id)
);

CREATE INDEX idx_wallet_settlement_outbox_pending
    ON wallet_settlement_outbox (enqueued_at) WHERE resolved_at IS NULL;

REVOKE ALL ON wallet_settlement_outbox FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON wallet_settlement_outbox TO elmos_wallet_settler;

COMMENT ON TABLE wallet_settlement_outbox IS
    'Cross-tenant work list for the settler. Carries identifiers and a status only -- no payload, no amounts, no customer content -- which is why it can be exempt from row level security on the same grounds as execution_job_dispatch.';

-- ---------------------------------------------------------------------------
-- 9. Balance write guard
-- ---------------------------------------------------------------------------
-- wallet_accounts is a projection of the ledger. Anything that changes a balance
-- without writing the matching ledger row silently breaks the invariant that the
-- reconciler checks, and the break is discovered later, by an accountant, on a
-- number that has already been shown to a customer. The accounting functions set
-- a transaction-local flag; nothing else can move these columns.

CREATE OR REPLACE FUNCTION elmos_guard_wallet_account_mutation()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.balance_minor IS DISTINCT FROM OLD.balance_minor
        OR NEW.reserved_minor IS DISTINCT FROM OLD.reserved_minor
        OR NEW.last_entry_seq IS DISTINCT FROM OLD.last_entry_seq)
       AND coalesce(current_setting('app.wallet_posting', true), '') <> 'on' THEN
        RAISE EXCEPTION 'ELMOS_WALLET_BALANCE_DIRECT_MUTATION_DENIED';
    END IF;
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TENANT_IMMUTABLE';
    END IF;
    IF NEW.currency IS DISTINCT FROM OLD.currency THEN
        RAISE EXCEPTION 'ELMOS_WALLET_CURRENCY_IMMUTABLE';
    END IF;
    NEW.updated_at := now();
    NEW.state_version := OLD.state_version + 1;
    RETURN NEW;
END;
$$;

CREATE TRIGGER wallet_accounts_balance_guard
BEFORE UPDATE ON wallet_accounts
FOR EACH ROW EXECUTE FUNCTION elmos_guard_wallet_account_mutation();

CREATE OR REPLACE FUNCTION elmos_forbid_wallet_account_delete()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'ELMOS_WALLET_DELETE_DENIED';
END;
$$;

CREATE TRIGGER wallet_accounts_no_delete
BEFORE DELETE ON wallet_accounts
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_wallet_account_delete();

-- ---------------------------------------------------------------------------
-- 10. Accounting functions
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_wallet_open(p_organization_id varchar)
RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO wallet_accounts (organization_id) VALUES (p_organization_id)
    ON CONFLICT (organization_id) DO NOTHING;
    RETURN p_organization_id;
END;
$$;

COMMENT ON FUNCTION elmos_wallet_open(varchar) IS
    'Idempotently opens a wallet. Safe to call on every sign-in and every top-up so a tenant created before V73 is never missing one.';

-- The one place a balance changes. Everything else calls this.
CREATE OR REPLACE FUNCTION elmos_wallet_post_entry(
    p_organization_id varchar,
    p_direction varchar,
    p_amount_minor numeric,
    p_entry_type varchar,
    p_source_type varchar,
    p_source_ref varchar,
    p_actor_id varchar,
    p_idempotency_key varchar,
    p_reservation_ref varchar DEFAULT NULL,
    p_reason varchar DEFAULT NULL
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_wallet wallet_accounts%ROWTYPE;
    v_existing varchar;
    v_seq bigint;
    v_balance numeric(19,0);
    v_entry_id varchar(96);
BEGIN
    IF p_amount_minor IS NULL OR p_amount_minor <= 0 THEN
        RAISE EXCEPTION 'ELMOS_WALLET_AMOUNT_INVALID';
    END IF;

    -- Idempotent replay returns the original entry rather than raising, because
    -- the caller that replays is usually a payment provider retry, and the honest
    -- answer to "credit this again" is "it is already credited, here it is".
    SELECT entry_id INTO v_existing FROM wallet_ledger_entries
     WHERE organization_id = p_organization_id AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        RETURN v_existing;
    END IF;

    PERFORM elmos_wallet_open(p_organization_id);
    SELECT * INTO v_wallet FROM wallet_accounts
     WHERE organization_id = p_organization_id FOR UPDATE;

    IF v_wallet.status = 'CLOSED' THEN
        RAISE EXCEPTION 'ELMOS_WALLET_CLOSED';
    END IF;

    IF p_direction = 'CREDIT' THEN
        v_balance := v_wallet.balance_minor + p_amount_minor;
    ELSIF p_direction = 'DEBIT' THEN
        v_balance := v_wallet.balance_minor - p_amount_minor;
        IF v_balance < 0 THEN
            RAISE EXCEPTION 'ELMOS_WALLET_INSUFFICIENT_BALANCE';
        END IF;
    ELSE
        RAISE EXCEPTION 'ELMOS_WALLET_DIRECTION_INVALID';
    END IF;

    v_seq := v_wallet.last_entry_seq + 1;
    v_entry_id := 'wle-' || md5(p_organization_id || ':' || v_seq::text || ':' || p_idempotency_key);

    INSERT INTO wallet_ledger_entries (
        entry_id, organization_id, seq, direction, amount_minor, balance_after_minor,
        entry_type, source_type, source_ref, reservation_ref, actor_id,
        idempotency_key, reason
    ) VALUES (
        v_entry_id, p_organization_id, v_seq, p_direction, p_amount_minor, v_balance,
        p_entry_type, p_source_type, p_source_ref, p_reservation_ref, p_actor_id,
        p_idempotency_key, p_reason
    );

    PERFORM set_config('app.wallet_posting', 'on', true);
    UPDATE wallet_accounts
       SET balance_minor = v_balance,
           last_entry_seq = v_seq
     WHERE organization_id = p_organization_id;
    PERFORM set_config('app.wallet_posting', 'off', true);

    RETURN v_entry_id;
END;
$$;

COMMENT ON FUNCTION elmos_wallet_post_entry(varchar, varchar, numeric, varchar, varchar, varchar, varchar, varchar, varchar, varchar) IS
    'The only writer of wallet balances. Takes the wallet row lock, so concurrent postings for one tenant serialize and the per-tenant ledger sequence cannot be minted twice.';

CREATE OR REPLACE FUNCTION elmos_wallet_topup_bounds(p_organization_id varchar)
RETURNS TABLE (min_amount_minor numeric, max_amount_minor numeric, daily_amount_limit_minor numeric)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT coalesce(p.min_amount_minor, 100),          -- 1 CNY
           coalesce(p.max_amount_minor, 5000000),      -- 50,000 CNY
           coalesce(p.daily_amount_limit_minor, 20000000)  -- 200,000 CNY
      FROM (SELECT 1) one
      LEFT JOIN wallet_topup_policies p ON p.organization_id = p_organization_id;
$$;

CREATE OR REPLACE FUNCTION elmos_wallet_credit_topup(
    p_topup_order_id varchar,
    p_provider_txn_ref varchar,
    p_actor_id varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_order wallet_topup_orders%ROWTYPE;
    v_entry_id varchar(96);
BEGIN
    SELECT * INTO v_order FROM wallet_topup_orders
     WHERE topup_order_id = p_topup_order_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_UNKNOWN';
    END IF;

    IF v_order.status = 'CREDITED' THEN
        RETURN v_order.credited_entry_ref;
    END IF;
    IF v_order.status NOT IN ('PAID', 'PENDING_PAYMENT', 'CREATED') THEN
        RAISE EXCEPTION 'ELMOS_WALLET_TOPUP_NOT_CREDITABLE';
    END IF;

    -- Keyed on the trade number, not on the order id: the trade number is what the
    -- payment provider replays, and it is what a duplicate callback carries.
    v_entry_id := elmos_wallet_post_entry(
        v_order.organization_id, 'CREDIT', v_order.amount_minor, 'TOPUP_SETTLED',
        'TOPUP_ORDER', v_order.topup_order_id, p_actor_id,
        'topup:' || v_order.provider || ':' || v_order.out_trade_no, NULL, NULL);

    UPDATE wallet_topup_orders
       SET status = 'CREDITED',
           provider_txn_ref = coalesce(p_provider_txn_ref, provider_txn_ref),
           paid_at = coalesce(paid_at, now()),
           credited_at = now(),
           credited_entry_ref = v_entry_id
     WHERE topup_order_id = p_topup_order_id;

    RETURN v_entry_id;
END;
$$;

COMMENT ON FUNCTION elmos_wallet_credit_topup(varchar, varchar, varchar) IS
    'Credits a confirmed top-up exactly once. This is the ONLY wallet function granted to elmos_billing_runtime: the payment service can settle a specific order and can do nothing else to a balance.';

CREATE OR REPLACE FUNCTION elmos_wallet_reserve(
    p_reservation_id varchar,
    p_organization_id varchar,
    p_job_id varchar,
    p_amount_minor numeric,
    p_quote_ref varchar,
    p_actor_id varchar,
    p_ttl_seconds integer
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_wallet wallet_accounts%ROWTYPE;
    v_existing wallet_reservations%ROWTYPE;
    v_available numeric(19,0);
BEGIN
    IF p_amount_minor IS NULL OR p_amount_minor <= 0 THEN
        RAISE EXCEPTION 'ELMOS_WALLET_AMOUNT_INVALID';
    END IF;
    IF p_ttl_seconds IS NULL OR p_ttl_seconds < 60 OR p_ttl_seconds > 172800 THEN
        RAISE EXCEPTION 'ELMOS_WALLET_RESERVATION_TTL_INVALID';
    END IF;

    SELECT * INTO v_existing FROM wallet_reservations
     WHERE organization_id = p_organization_id AND job_id = p_job_id;
    IF FOUND THEN
        IF v_existing.status = 'HELD' THEN
            RETURN v_existing.reservation_id;
        END IF;
        RAISE EXCEPTION 'ELMOS_WALLET_RESERVATION_ALREADY_RESOLVED';
    END IF;

    PERFORM elmos_wallet_open(p_organization_id);
    SELECT * INTO v_wallet FROM wallet_accounts
     WHERE organization_id = p_organization_id FOR UPDATE;

    IF v_wallet.status <> 'ACTIVE' THEN
        RAISE EXCEPTION 'ELMOS_WALLET_NOT_ACTIVE';
    END IF;

    v_available := v_wallet.balance_minor - v_wallet.reserved_minor;
    IF v_available < p_amount_minor THEN
        RAISE EXCEPTION 'ELMOS_WALLET_INSUFFICIENT_BALANCE';
    END IF;

    INSERT INTO wallet_reservations (
        reservation_id, organization_id, job_id, amount_minor, quote_ref,
        actor_id, expires_at
    ) VALUES (
        p_reservation_id, p_organization_id, p_job_id, p_amount_minor, p_quote_ref,
        p_actor_id, now() + make_interval(secs => p_ttl_seconds)
    );

    PERFORM set_config('app.wallet_posting', 'on', true);
    UPDATE wallet_accounts
       SET reserved_minor = reserved_minor + p_amount_minor
     WHERE organization_id = p_organization_id;
    PERFORM set_config('app.wallet_posting', 'off', true);

    RETURN p_reservation_id;
END;
$$;

COMMENT ON FUNCTION elmos_wallet_reserve(varchar, varchar, varchar, numeric, varchar, varchar, integer) IS
    'Holds money for a job under the wallet row lock. Two concurrent reservations that together exceed the balance cannot both succeed; the second sees the first reflected in reserved_minor.';

CREATE OR REPLACE FUNCTION elmos_wallet_settle(
    p_organization_id varchar,
    p_job_id varchar,
    p_settled_amount_minor numeric,
    p_actor_id varchar,
    p_resolution_code varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_reservation wallet_reservations%ROWTYPE;
    v_charge numeric(19,0);
    v_entry_id varchar(96);
BEGIN
    SELECT * INTO v_reservation FROM wallet_reservations
     WHERE organization_id = p_organization_id AND job_id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_WALLET_RESERVATION_UNKNOWN';
    END IF;
    IF v_reservation.status <> 'HELD' THEN
        -- Already resolved. A settler retry must be a no-op, not a second charge.
        RETURN v_reservation.reservation_id;
    END IF;

    v_charge := least(greatest(coalesce(p_settled_amount_minor, 0), 0), v_reservation.amount_minor);

    PERFORM set_config('app.wallet_posting', 'on', true);
    UPDATE wallet_accounts
       SET reserved_minor = reserved_minor - v_reservation.amount_minor
     WHERE organization_id = p_organization_id;
    PERFORM set_config('app.wallet_posting', 'off', true);

    IF v_charge > 0 THEN
        v_entry_id := elmos_wallet_post_entry(
            p_organization_id, 'DEBIT', v_charge, 'CONSUME', 'JOB', p_job_id,
            p_actor_id, 'settle:' || p_job_id, v_reservation.reservation_id, NULL);
    END IF;

    UPDATE wallet_reservations
       SET status = 'SETTLED',
           settled_amount_minor = v_charge,
           resolved_at = now(),
           resolution_code = p_resolution_code
     WHERE reservation_id = v_reservation.reservation_id;

    RETURN v_reservation.reservation_id;
END;
$$;

COMMENT ON FUNCTION elmos_wallet_settle(varchar, varchar, numeric, varchar, varchar) IS
    'Charges at most what was held and releases the remainder. Clamps rather than raising on an over-quote, because the promise made to the user at submit time is the ceiling, and a settler bug must not be able to exceed it.';

CREATE OR REPLACE FUNCTION elmos_wallet_release(
    p_organization_id varchar,
    p_job_id varchar,
    p_resolution_code varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_reservation wallet_reservations%ROWTYPE;
BEGIN
    SELECT * INTO v_reservation FROM wallet_reservations
     WHERE organization_id = p_organization_id AND job_id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_WALLET_RESERVATION_UNKNOWN';
    END IF;
    IF v_reservation.status <> 'HELD' THEN
        RETURN v_reservation.reservation_id;
    END IF;

    PERFORM set_config('app.wallet_posting', 'on', true);
    UPDATE wallet_accounts
       SET reserved_minor = reserved_minor - v_reservation.amount_minor
     WHERE organization_id = p_organization_id;
    PERFORM set_config('app.wallet_posting', 'off', true);

    UPDATE wallet_reservations
       SET status = 'RELEASED', resolved_at = now(), resolution_code = p_resolution_code
     WHERE reservation_id = v_reservation.reservation_id;

    RETURN v_reservation.reservation_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_wallet_expire_reservations(p_limit integer DEFAULT 500)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_row record;
    v_count integer := 0;
BEGIN
    FOR v_row IN
        SELECT reservation_id, organization_id, amount_minor
          FROM wallet_reservations
         WHERE status = 'HELD' AND expires_at <= now()
         ORDER BY expires_at
         LIMIT greatest(coalesce(p_limit, 500), 1)
         FOR UPDATE SKIP LOCKED
    LOOP
        PERFORM set_config('app.wallet_posting', 'on', true);
        UPDATE wallet_accounts
           SET reserved_minor = reserved_minor - v_row.amount_minor
         WHERE organization_id = v_row.organization_id;
        PERFORM set_config('app.wallet_posting', 'off', true);

        UPDATE wallet_reservations
           SET status = 'EXPIRED', resolved_at = now(), resolution_code = 'TTL_EXPIRED'
         WHERE reservation_id = v_row.reservation_id;

        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION elmos_wallet_expire_reservations(integer) IS
    'Sweeps holds whose job never resolved. Under-charges by design: a stuck settler must not be able to lock a tenant out of money they still own.';

CREATE OR REPLACE FUNCTION elmos_wallet_adjust(
    p_organization_id varchar,
    p_direction varchar,
    p_amount_minor numeric,
    p_actor_id varchar,
    p_reason varchar,
    p_idempotency_key varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF p_reason IS NULL OR length(btrim(p_reason)) = 0 THEN
        RAISE EXCEPTION 'ELMOS_WALLET_ADJUSTMENT_REASON_REQUIRED';
    END IF;
    RETURN elmos_wallet_post_entry(
        p_organization_id, p_direction, p_amount_minor, 'ADMIN_ADJUSTMENT',
        'ADMIN', p_actor_id, p_actor_id, p_idempotency_key, NULL, p_reason);
END;
$$;

-- ---------------------------------------------------------------------------
-- 11. Reconciliation
-- ---------------------------------------------------------------------------
-- The projection is only trustworthy if something keeps checking it against the
-- authority. This returns the drift rather than fixing it: a wallet that does
-- not match its own ledger is an incident, and silently repairing it would erase
-- the evidence needed to find out why.

CREATE OR REPLACE FUNCTION elmos_wallet_reconcile(p_organization_id varchar DEFAULT NULL)
RETURNS TABLE (
    organization_id varchar,
    projected_balance_minor numeric,
    ledger_balance_minor numeric,
    projected_reserved_minor numeric,
    held_reserved_minor numeric
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT w.organization_id,
           w.balance_minor,
           coalesce((SELECT sum(CASE WHEN l.direction = 'CREDIT' THEN l.amount_minor
                                     ELSE -l.amount_minor END)
                       FROM wallet_ledger_entries l
                      WHERE l.organization_id = w.organization_id), 0),
           w.reserved_minor,
           coalesce((SELECT sum(r.amount_minor)
                       FROM wallet_reservations r
                      WHERE r.organization_id = w.organization_id AND r.status = 'HELD'), 0)
      FROM wallet_accounts w
     WHERE p_organization_id IS NULL OR w.organization_id = p_organization_id;
$$;

-- ---------------------------------------------------------------------------
-- 12. Row level security
-- ---------------------------------------------------------------------------

DO $$
DECLARE v_table text;
BEGIN
    FOREACH v_table IN ARRAY ARRAY[
        'wallet_accounts',
        'wallet_ledger_entries',
        'wallet_reservations',
        'wallet_topup_orders',
        'wallet_topup_policies'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', v_table);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', v_table);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            v_table
        );
    END LOOP;
END;
$$;

-- ---------------------------------------------------------------------------
-- 13. Grants
-- ---------------------------------------------------------------------------

DO $$
DECLARE v_function record;
BEGIN
    FOR v_function IN
        SELECT p.oid::regprocedure AS signature
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND p.proname IN (
               'elmos_wallet_open',
               'elmos_wallet_post_entry',
               'elmos_wallet_topup_bounds',
               'elmos_wallet_credit_topup',
               'elmos_wallet_reserve',
               'elmos_wallet_settle',
               'elmos_wallet_release',
               'elmos_wallet_expire_reservations',
               'elmos_wallet_adjust',
               'elmos_wallet_reconcile',
               'elmos_guard_wallet_account_mutation',
               'elmos_guard_wallet_reservation_transition',
               'elmos_guard_wallet_topup_transition',
               'elmos_forbid_wallet_account_delete'
           )
    LOOP
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', v_function.signature);
    END LOOP;
END;
$$;

-- The payment service reaches the wallet through exactly one door, and that door
-- settles one named order. It is never granted a table.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_billing_runtime') THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_wallet_credit_topup(varchar, varchar, varchar) TO elmos_billing_runtime';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE ON wallet_topup_orders TO elmos_billing_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_wallet_topup_bounds(varchar) TO elmos_billing_runtime';
    END IF;
END;
$$;
