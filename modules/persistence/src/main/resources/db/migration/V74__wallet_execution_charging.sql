-- ELMOS V74: charge execution jobs against the prepaid wallet.
--
-- Why this migration exists
-- -------------------------
-- V73 built the wallet and left the job queue untouched. This one connects
-- them: money is held when a job is admitted and resolved when it reaches a
-- terminal state. Until now `elmos_enqueue_execution_job` performed no billing
-- of any kind -- it checked the runner image, rejected sensitive payloads and
-- inserted. There was no charge to modify; this opens a new gate.
--
-- Where the gate goes, and why not in the controller
-- --------------------------------------------------
-- Inside `elmos_enqueue_execution_job`, next to the concurrency check that is
-- already there. The controller is one caller; the function is the only way a
-- row reaches `execution_jobs` with its dispatch row and its ENQUEUED event.
-- A gate in the controller is a gate the next caller forgets. A gate here is
-- also automatically in the same transaction as the insert, so "money held but
-- no job" and "job queued but no money held" are both unrepresentable rather
-- than merely unlikely.
--
-- Off by default
-- --------------
-- `wallet_enforcement_settings.enabled` starts false and every code path below
-- short-circuits on it. With the flag off this migration is observably inert:
-- enqueue behaves exactly as it did, no reservation is taken, no outbox row is
-- written. That is the rollback path -- the ledger is append-only, so deleting
-- rows never was one.
--
-- Allowance first, wallet second
-- ------------------------------
-- A tenant with an active V49 subscription and enough remaining credit
-- allowance is not charged. The wallet is the second means of payment, not a
-- replacement, so a subscribed tenant sees no behaviour change when the flag is
-- turned on. Coverage is all-or-nothing per job: either the allowance covers the
-- whole quote or the wallet holds the whole quote. Splitting one job across two
-- funding sources would need a second reservation kind and a settlement that
-- unwinds both; that is a real feature, not a detail, and it is not this one.

-- ---------------------------------------------------------------------------
-- 1. Enforcement switch
-- ---------------------------------------------------------------------------

CREATE TABLE wallet_enforcement_settings (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    enabled boolean NOT NULL DEFAULT false,
    catalog_version varchar(64) NOT NULL,
    reservation_ttl_seconds integer NOT NULL DEFAULT 14400
        CHECK (reservation_ttl_seconds BETWEEN 300 AND 172800),
    updated_by varchar(128) NOT NULL DEFAULT 'migration:V74',
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO wallet_enforcement_settings (singleton, enabled, catalog_version)
VALUES (true, false, '2026-08-25.1');

COMMENT ON TABLE wallet_enforcement_settings IS
    'Single-row switch for wallet charging. Disabled at install: turning it on is a deliberate operational act, and turning it off is the rollback, because an append-only ledger cannot be rolled back by deleting rows.';
COMMENT ON COLUMN wallet_enforcement_settings.reservation_ttl_seconds IS
    'How long a hold survives without resolution. Must outlast the longest job budget (execution_jobs allows 43200s) plus settlement lag, or the sweeper will release money for jobs that are still running and the settle will then find no hold.';

CREATE OR REPLACE FUNCTION elmos_wallet_enforcement_enabled()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT coalesce((SELECT enabled FROM wallet_enforcement_settings WHERE singleton), false);
$$;

-- ---------------------------------------------------------------------------
-- 2. Which failures the user pays for
-- ---------------------------------------------------------------------------
-- Seeded EMPTY, which means: a failed job costs nothing. That is the safe
-- default, and it is a product decision rather than a technical one -- the
-- opposite default (charge unless proven otherwise) bills people for our own
-- outages. The table exists so that adding a genuinely user-caused code later
-- is an INSERT with a reason attached, not a migration that edits a CASE.

CREATE TABLE wallet_chargeable_failure_codes (
    failure_code varchar(96) PRIMARY KEY,
    rationale varchar(255) NOT NULL,
    added_by varchar(128) NOT NULL,
    added_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE wallet_chargeable_failure_codes IS
    'Failure codes the tenant is charged the minimum for. Empty by default: FAILED jobs are free unless someone states, in writing and in this table, why a particular failure is the caller''s doing.';

-- ---------------------------------------------------------------------------
-- 3. Quoting
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_wallet_quote(
    p_business_line varchar,
    p_job_kind varchar,
    p_budget_wall_seconds integer
) RETURNS TABLE (quote_ref varchar, reserve_minor numeric, min_charge_minor numeric,
                 unit varchar, unit_price_minor numeric)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_catalog varchar(64);
    v_row wallet_price_book%ROWTYPE;
BEGIN
    SELECT s.catalog_version INTO v_catalog
      FROM wallet_enforcement_settings s WHERE s.singleton;

    -- Exact job_kind wins over the per-line fallback. Both must be PUBLISHED:
    -- a DRAFT price is a price nobody approved, and charging against one is how
    -- a typo in a review branch becomes a customer's invoice.
    SELECT * INTO v_row FROM wallet_price_book b
     WHERE b.catalog_version = v_catalog
       AND b.business_line = p_business_line
       AND b.job_kind IN (p_job_kind, '*')
       AND b.status = 'PUBLISHED'
       AND b.effective_from <= now()
       AND (b.effective_until IS NULL OR b.effective_until > now())
     ORDER BY CASE WHEN b.job_kind = p_job_kind THEN 0 ELSE 1 END
     LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_WALLET_NO_PUBLISHED_PRICE';
    END IF;

    RETURN QUERY SELECT
        (v_row.catalog_version || '/' || v_row.business_line || '/' || v_row.job_kind)::varchar,
        -- The hold scales with what the caller asked to be allowed to consume.
        -- Quoting a flat reserve would under-hold a 12-hour job and over-hold a
        -- one-minute one, and the second is what users actually complain about.
        greatest(
            v_row.reserve_minor,
            CASE WHEN v_row.unit = 'WALL_SECOND'
                 THEN ceil(v_row.unit_price_minor * coalesce(p_budget_wall_seconds, 3600))
                 ELSE v_row.reserve_minor END),
        v_row.min_charge_minor,
        v_row.unit,
        v_row.unit_price_minor;
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. Remaining subscription allowance
-- ---------------------------------------------------------------------------

-- Binds the tenant, and is therefore VOLATILE rather than STABLE.
--
-- The first version was a STABLE sql function with no binding. quota_allocations
-- and subscriptions are both FORCE RLS, so under an owner without BYPASSRLS it
-- would have returned 0 for everyone -- and 0 does not look like a failure, it
-- looks like "this tenant has no allowance left". The visible symptom would have
-- been subscribed tenants quietly being charged from their wallet for work their
-- plan already covers. Same family as the V62 callback bug: the query returns
-- nothing and nothing raises.
CREATE OR REPLACE FUNCTION elmos_wallet_allowance_remaining(p_organization_id varchar)
RETURNS numeric
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_previous text;
    v_remaining numeric(30,0);
BEGIN
    v_previous := elmos_wallet_bind_tenant(p_organization_id);
    SELECT coalesce(
        (SELECT max(q.credit_limit - q.consumed_credits - q.reserved_credits)
           FROM quota_allocations q
           JOIN subscriptions s ON s.subscription_id = q.subscription_id
          WHERE s.organization_id = p_organization_id
            AND q.subscription_id IS NOT NULL
            AND s.status IN ('ACTIVE', 'TRIALING')
            AND q.period_start <= now() AND q.period_end > now()),
        0) INTO v_remaining;
    PERFORM set_config('app.organization_id', v_previous, true);
    RETURN v_remaining;
END;
$$;

COMMENT ON FUNCTION elmos_wallet_allowance_remaining(varchar) IS
    'Credits still available in the current V49 subscription period, or zero when there is none. Zero is also the honest answer for a wallet-only tenant, which is why the wallet is consulted second rather than instead.';

-- ---------------------------------------------------------------------------
-- 5. Admission: the gate itself
-- ---------------------------------------------------------------------------
-- Returns the reservation id it took, or NULL when nothing was held (the flag
-- is off, or the subscription allowance covers this job).

CREATE OR REPLACE FUNCTION elmos_wallet_admit_job(
    p_organization_id varchar,
    p_job_id varchar,
    p_actor_id varchar,
    p_business_line varchar,
    p_job_kind varchar,
    p_budget_wall_seconds integer
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_quote record;
    v_ttl integer;
    v_reservation varchar(96);
BEGIN
    IF NOT elmos_wallet_enforcement_enabled() THEN
        RETURN NULL;
    END IF;

    SELECT * INTO v_quote FROM elmos_wallet_quote(
        p_business_line, p_job_kind, p_budget_wall_seconds);

    IF elmos_wallet_allowance_remaining(p_organization_id) >= v_quote.reserve_minor THEN
        -- Covered by the subscription. The allowance is consumed by the existing
        -- V49 usage path, not here; double-counting it would charge twice.
        RETURN NULL;
    END IF;

    SELECT s.reservation_ttl_seconds INTO v_ttl
      FROM wallet_enforcement_settings s WHERE s.singleton;

    v_reservation := 'wres-' || md5(p_organization_id || ':' || p_job_id);
    RETURN elmos_wallet_reserve(
        v_reservation, p_organization_id, p_job_id, v_quote.reserve_minor,
        v_quote.quote_ref, p_actor_id, v_ttl);
END;
$$;

COMMENT ON FUNCTION elmos_wallet_admit_job(varchar, varchar, varchar, varchar, varchar, integer) IS
    'The enqueue-time charge. Returns NULL when nothing was held. Raises ELMOS_WALLET_INSUFFICIENT_BALANCE when the tenant cannot cover the quote, which the enqueue path lets propagate so the job is never created.';

-- ---------------------------------------------------------------------------
-- 6. Entitlement: let a funded wallet admit work
-- ---------------------------------------------------------------------------
-- elmos_execution_concurrency_limit returns 0 -- fail closed, nothing is
-- scheduled -- when there is no active CNY subscription. That is correct while
-- a subscription is the only way to pay. Once the wallet is a means of payment,
-- it leaves a prepaid tenant unable to run anything they have already paid for.
--
-- The wallet branch applies ONLY when enforcement is on, so with the flag off
-- this function's behaviour is unchanged, byte for byte.

CREATE OR REPLACE FUNCTION elmos_execution_concurrency_limit(p_organization_id varchar)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_previous text;
    v_plan_limit integer;
    v_spendable numeric(19,0);
BEGIN
    -- V52 read subscriptions with no tenant bound, which works only while the
    -- owner bypasses row level security. Binding here makes the answer the same
    -- either way; it also has to be bound before the new wallet_accounts read.
    -- STABLE is dropped for the same reason: this now sets a GUC.
    v_previous := elmos_wallet_bind_tenant(p_organization_id);
    SELECT coalesce(
        (SELECT p.concurrent_job_limit
           FROM subscriptions s
           JOIN self_service_pricing_plan_versions p
             ON p.catalog_version = s.catalog_version AND p.plan_id = s.plan_id
          WHERE s.organization_id = p_organization_id
            AND s.plan_id IS NOT NULL
            AND s.status IN ('ACTIVE', 'TRIALING')
            AND s.current_period_end > now()
          ORDER BY p.concurrent_job_limit DESC
          LIMIT 1),
        0) INTO v_plan_limit;

    IF v_plan_limit > 0 OR NOT elmos_wallet_enforcement_enabled() THEN
        PERFORM set_config('app.organization_id', v_previous, true);
        RETURN v_plan_limit;
    END IF;

    SELECT coalesce(w.balance_minor - w.reserved_minor, 0) INTO v_spendable
      FROM wallet_accounts w WHERE w.organization_id = p_organization_id;

    -- One at a time for a prepaid tenant. Concurrency is a plan feature; the
    -- wallet buys the right to run, not the right to run in parallel. A tenant
    -- who wants more takes a plan, which is also the only way we can bound the
    -- fleet a single prepaid balance can occupy.
    PERFORM set_config('app.organization_id', v_previous, true);
    RETURN CASE WHEN coalesce(v_spendable, 0) > 0 THEN 1 ELSE 0 END;
END;
$$;

COMMENT ON FUNCTION elmos_execution_concurrency_limit(varchar) IS
    'Effective concurrent job limit. A plan sets it; failing that, a funded wallet earns exactly one slot, and only while wallet enforcement is enabled. Returns 0 - fail closed - otherwise.';

-- ---------------------------------------------------------------------------
-- 7. Enqueue, with the gate wired in
-- ---------------------------------------------------------------------------
-- Replaced whole rather than patched: this is the transaction that must contain
-- both the hold and the insert, and a reader needs to see that in one place.
-- Everything except the marked block is byte-identical to V52.

CREATE OR REPLACE FUNCTION elmos_enqueue_execution_job(
    p_job_id varchar,
    p_organization_id varchar,
    p_actor_id varchar,
    p_business_line varchar,
    p_job_kind varchar,
    p_idempotency_key varchar,
    p_request_digest varchar,
    p_request_payload jsonb,
    p_required_capability varchar,
    p_runner_image varchar,
    p_priority smallint,
    p_budget_wall_seconds integer,
    p_max_attempts smallint
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_existing execution_jobs%ROWTYPE;
    v_queued integer;
    v_limit integer;
BEGIN
    SELECT * INTO v_existing FROM execution_jobs
     WHERE organization_id = p_organization_id AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.request_digest IS DISTINCT FROM p_request_digest THEN
            RAISE EXCEPTION 'ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.job_id;
    END IF;

    v_limit := elmos_execution_concurrency_limit(p_organization_id);
    IF v_limit < 1 THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_NO_ACTIVE_ENTITLEMENT';
    END IF;

    SELECT coalesce(queued_count, 0) INTO v_queued
      FROM execution_dispatch_org_counters WHERE organization_id = p_organization_id;
    IF coalesce(v_queued, 0) >= v_limit * 10 THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_QUEUE_DEPTH_EXCEEDED';
    END IF;

    -- ---- V74: the charge -------------------------------------------------
    -- Deliberately after the idempotency check, so a retried enqueue returns
    -- the existing job without taking a second hold; and before every insert,
    -- so a refusal leaves no job, no dispatch row and no event behind.
    -- Refusals propagate: ELMOS_WALLET_INSUFFICIENT_BALANCE aborts the whole
    -- transaction, which is the intended answer to "run this without paying".
    PERFORM elmos_wallet_admit_job(
        p_organization_id, p_job_id, p_actor_id,
        p_business_line, p_job_kind, p_budget_wall_seconds);
    -- ---- end V74 ---------------------------------------------------------

    INSERT INTO execution_jobs (
        job_id, organization_id, actor_id, business_line, job_kind,
        idempotency_key, request_digest, request_payload, required_capability,
        runner_image, priority, budget_wall_seconds, max_attempts
    ) VALUES (
        p_job_id, p_organization_id, p_actor_id, p_business_line, p_job_kind,
        p_idempotency_key, p_request_digest, coalesce(p_request_payload, '{}'::jsonb),
        p_required_capability, p_runner_image, coalesce(p_priority, 100::smallint),
        coalesce(p_budget_wall_seconds, 3600), coalesce(p_max_attempts, 1::smallint)
    );

    INSERT INTO execution_job_dispatch (
        job_id, organization_id, required_capability, priority
    ) VALUES (
        p_job_id, p_organization_id, p_required_capability, coalesce(p_priority, 100::smallint)
    );

    INSERT INTO execution_dispatch_org_counters (organization_id, queued_count)
    VALUES (p_organization_id, 1)
    ON CONFLICT (organization_id) DO UPDATE
        SET queued_count = execution_dispatch_org_counters.queued_count + 1,
            updated_at = now();

    INSERT INTO execution_job_events (
        job_event_id, organization_id, job_id, sequence_no, event_type,
        to_status, stage, progress, actor_id
    ) VALUES (
        'jev-' || md5(p_job_id || ':0'), p_organization_id, p_job_id, 0, 'ENQUEUED',
        'QUEUED', 'queued', 0, p_actor_id
    );

    RETURN p_job_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- 8. Terminal state -> settlement outbox
-- ---------------------------------------------------------------------------
-- A trigger rather than a call in the worker, because the worker is not the only
-- writer: the lease reaper marks jobs LOST, an operator cancels, a future path
-- we have not written yet will mark something else. Every one of them must
-- resolve the hold, and the only place that is true by construction is here.
--
-- SECURITY DEFINER with a pinned search_path and a schema-qualified target, for
-- the reason V64 had to retrofit onto the V62 directory trigger: the runtime
-- role holds no write permission on the outbox, and granting it one would make
-- the outbox writable from anywhere.

CREATE OR REPLACE FUNCTION elmos_wallet_enqueue_settlement()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_reservation varchar(96);
BEGIN
    IF NEW.status NOT IN ('SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'LOST') THEN
        RETURN NEW;
    END IF;
    IF OLD.status = NEW.status THEN
        RETURN NEW;
    END IF;

    SELECT r.reservation_id INTO v_reservation
      FROM public.wallet_reservations r
     WHERE r.organization_id = NEW.organization_id
       AND r.job_id = NEW.job_id
       AND r.status = 'HELD';
    IF NOT FOUND THEN
        -- No hold: this job was admitted with the flag off, or covered by the
        -- subscription allowance. Nothing to settle, and nothing to complain
        -- about either -- an outbox row with no reservation would be a work item
        -- the settler can never resolve.
        RETURN NEW;
    END IF;

    INSERT INTO public.wallet_settlement_outbox (
        outbox_id, organization_id, job_id, reservation_id, job_status, failure_code)
    VALUES (
        'wsx-' || md5(NEW.job_id), NEW.organization_id, NEW.job_id, v_reservation,
        NEW.status, NEW.failure_code)
    ON CONFLICT (job_id) DO NOTHING;

    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION elmos_wallet_enqueue_settlement() FROM PUBLIC;

CREATE TRIGGER execution_jobs_wallet_settlement
AFTER UPDATE OF status ON execution_jobs
FOR EACH ROW EXECUTE FUNCTION elmos_wallet_enqueue_settlement();

-- ---------------------------------------------------------------------------
-- 9. The settler
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_wallet_claim_settlements(
    p_limit integer DEFAULT 50,
    p_lease_seconds integer DEFAULT 120
) RETURNS TABLE (
    outbox_id varchar, organization_id varchar, job_id varchar,
    reservation_id varchar, job_status varchar, failure_code varchar, attempts smallint
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    UPDATE wallet_settlement_outbox o
       SET claimed_until = now() + make_interval(secs => greatest(coalesce(p_lease_seconds, 120), 30)),
           attempts = least(o.attempts + 1, 20)
     WHERE o.outbox_id IN (
            SELECT c.outbox_id FROM wallet_settlement_outbox c
             WHERE c.resolved_at IS NULL
               AND (c.claimed_until IS NULL OR c.claimed_until < now())
               AND c.attempts < 20
             ORDER BY c.enqueued_at
             LIMIT greatest(coalesce(p_limit, 50), 1)
             FOR UPDATE SKIP LOCKED)
    RETURNING o.outbox_id, o.organization_id, o.job_id, o.reservation_id,
              o.job_status, o.failure_code, o.attempts;
END;
$$;

/**
 * Facts the settler needs to price a finished job.
 *
 * Reads execution_jobs, which is FORCE RLS, so it binds the tenant the outbox
 * row named. The settler itself is cross-tenant and has no context of its own.
 */
CREATE OR REPLACE FUNCTION elmos_wallet_settlement_facts(
    p_organization_id varchar,
    p_job_id varchar
) RETURNS TABLE (
    status varchar, failure_code varchar, business_line varchar, job_kind varchar,
    budget_wall_seconds integer, elapsed_seconds integer, chargeable_failure boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_previous text;
BEGIN
    v_previous := elmos_wallet_bind_tenant(p_organization_id);
    RETURN QUERY
    SELECT j.status, j.failure_code, j.business_line, j.job_kind, j.budget_wall_seconds,
           -- A job that never started took no time, whatever the clock says about
           -- how long it sat in the queue. Queue time is our latency, not theirs.
           CASE WHEN j.started_at IS NULL THEN 0
                ELSE greatest(0, extract(epoch FROM
                        coalesce(j.finished_at, now()) - j.started_at)::integer) END,
           EXISTS (SELECT 1 FROM wallet_chargeable_failure_codes f
                    WHERE f.failure_code = j.failure_code)
      FROM execution_jobs j
     WHERE j.organization_id = p_organization_id AND j.job_id = p_job_id;
    PERFORM set_config('app.organization_id', v_previous, true);
END;
$$;

CREATE OR REPLACE FUNCTION elmos_wallet_resolve_settlement(
    p_outbox_id varchar,
    p_settled_amount_minor numeric,
    p_resolution_code varchar,
    p_actor_id varchar
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_row wallet_settlement_outbox%ROWTYPE;
BEGIN
    SELECT * INTO v_row FROM wallet_settlement_outbox
     WHERE outbox_id = p_outbox_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_WALLET_SETTLEMENT_UNKNOWN';
    END IF;
    IF v_row.resolved_at IS NOT NULL THEN
        RETURN false;
    END IF;

    IF coalesce(p_settled_amount_minor, 0) > 0 THEN
        PERFORM elmos_wallet_settle(
            v_row.organization_id, v_row.job_id, p_settled_amount_minor,
            p_actor_id, p_resolution_code);
    ELSE
        -- Zero is a release, not a zero-value charge. A SETTLED reservation with
        -- settled_amount 0 and a RELEASED one describe the same money but read
        -- very differently to whoever audits this later.
        PERFORM elmos_wallet_release(
            v_row.organization_id, v_row.job_id, p_resolution_code);
    END IF;

    UPDATE wallet_settlement_outbox
       SET resolved_at = now(), claimed_until = NULL, last_error_code = NULL
     WHERE outbox_id = p_outbox_id;
    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_wallet_fail_settlement(
    p_outbox_id varchar,
    p_error_code varchar
) RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
    UPDATE wallet_settlement_outbox
       SET claimed_until = NULL, last_error_code = p_error_code
     WHERE outbox_id = p_outbox_id AND resolved_at IS NULL;
$$;

-- ---------------------------------------------------------------------------
-- 10. Grants
-- ---------------------------------------------------------------------------

DO $$
DECLARE v_function record;
BEGIN
    FOR v_function IN
        SELECT p.oid::regprocedure AS signature
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND p.proname IN (
               'elmos_wallet_enforcement_enabled',
               'elmos_wallet_quote',
               'elmos_wallet_allowance_remaining',
               'elmos_wallet_admit_job',
               'elmos_wallet_enqueue_settlement',
               'elmos_wallet_claim_settlements',
               'elmos_wallet_settlement_facts',
               'elmos_wallet_resolve_settlement',
               'elmos_wallet_fail_settlement'
           )
    LOOP
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', v_function.signature);
    END LOOP;
END;
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_wallet_settler') THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_wallet_claim_settlements(integer, integer) TO elmos_wallet_settler';
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_wallet_settlement_facts(varchar, varchar) TO elmos_wallet_settler';
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_wallet_resolve_settlement(varchar, numeric, varchar, varchar) TO elmos_wallet_settler';
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_wallet_fail_settlement(varchar, varchar) TO elmos_wallet_settler';
    END IF;
END;
$$;

REVOKE ALL ON wallet_enforcement_settings FROM PUBLIC;
REVOKE ALL ON wallet_chargeable_failure_codes FROM PUBLIC;
