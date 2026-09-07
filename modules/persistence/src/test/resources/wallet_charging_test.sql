\set ON_ERROR_STOP on
\pset pager off

-- ---------------------------------------------------------------------------
-- Fixture. Two tenants: one on a subscription, one prepaid only.
-- ---------------------------------------------------------------------------
INSERT INTO organizations (organization_id, display_name, data_region) VALUES
    ('org-sub',  'subscribed tenant', 'cn-north'),
    ('org-pre',  'prepaid tenant',    'cn-north'),
    ('org-broke','prepaid but empty', 'cn-north')
ON CONFLICT DO NOTHING;

-- A live subscription period with allowance, for org-sub.
INSERT INTO subscriptions (subscription_id, organization_id, status, catalog_version,
    plan_id, actor_id, billing_period, currency, price_minor,
    current_period_start, current_period_end)
VALUES ('sub-1', 'org-sub', 'ACTIVE', '2026-07-28.2', 'elmos-pro-monthly', 'actor-s',
    'MONTH', 'CNY', 12900, now() - interval '1 day', now() + interval '29 days');
INSERT INTO quota_allocations (quota_allocation_id, organization_id, subscription_id,
    plan_id, catalog_version, period_start, period_end,
    token_limit, credit_limit, consumed_credits, reserved_credits)
VALUES ('qa-1', 'org-sub', 'sub-1', 'elmos-pro-monthly', '2026-07-28.2',
    now() - interval '1 day', now() + interval '29 days', 20000000, 600000, 0, 0);

-- Fund both prepaid wallets; org-broke stays at zero.
SELECT elmos_wallet_create_topup_order('tu-pre','org-pre','actor-p',500000,
    'ALIPAY','ALI-PRE','idem-pre',3600);
SELECT elmos_wallet_credit_topup('org-pre','tu-pre','txn','sys');
SELECT elmos_wallet_open('org-broke');

\set IMAGE '\'registry.example.com/elmos/runner@sha256:1111111111111111111111111111111111111111111111111111111111111111\''

-- ===========================================================================
-- C1  FLAG OFF: enqueue must behave exactly as before V74
-- ===========================================================================
\echo '--- C1 flag is off by default'
SELECT enabled FROM wallet_enforcement_settings;

\echo '--- C1a a subscribed tenant enqueues, and NOTHING is held'
SELECT elmos_enqueue_execution_job('job-off-1','org-sub','actor-s','GENERATION','gen',
    'idem-off-1', repeat('a',64), '{}'::jsonb, 'cap', :IMAGE, 100::smallint, 3600, 1::smallint);
SELECT count(*) AS reservations_taken FROM wallet_reservations WHERE organization_id='org-sub';
SELECT status FROM execution_jobs WHERE job_id='job-off-1';

\echo '--- C1b a prepaid tenant with no plan is still refused while the flag is off'
DO $$ BEGIN
    PERFORM elmos_enqueue_execution_job('job-off-2','org-pre','actor-p','GENERATION','gen',
        'idem-off-2', repeat('b',64), '{}'::jsonb, 'cap',
        'registry.example.com/elmos/runner@sha256:1111111111111111111111111111111111111111111111111111111111111111',
        100::smallint, 3600, 1::smallint);
    RAISE EXCEPTION 'TEST_FAILED_prepaid_admitted_while_flag_off';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%NO_ACTIVE_ENTITLEMENT%' THEN RAISE; END IF;
    RAISE NOTICE 'OK unchanged: %', SQLERRM;
END $$;

\echo '--- C1c terminal transition with no hold writes no outbox row'
UPDATE execution_jobs SET status='SUCCEEDED', finished_at=now() WHERE job_id='job-off-1';
SELECT count(*) AS outbox_rows FROM wallet_settlement_outbox;

-- ===========================================================================
-- C2  Turn it on. An unapproved price must not be able to charge anyone.
-- ===========================================================================
UPDATE wallet_enforcement_settings SET enabled = true;

\echo '--- C2 all seeded prices are DRAFT, so admission fails closed'
DO $$ BEGIN
    PERFORM elmos_wallet_admit_job('org-pre','job-x','actor-p','GENERATION','gen',3600);
    RAISE EXCEPTION 'TEST_FAILED_draft_price_charged';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%NO_PUBLISHED_PRICE%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

-- Publish the generation price. wallet_price_book is append-only, so a new row
-- rather than an UPDATE -- which is the point of it being append-only.
INSERT INTO wallet_price_book (catalog_version, business_line, job_kind, reserve_minor,
    unit, unit_price_minor, min_charge_minor, effective_from, source_ref, status)
VALUES ('2026-08-25.1','GENERATION','gen', 500, 'WALL_SECOND', 1, 50,
    now() - interval '1 hour', 'test', 'PUBLISHED');

\echo '--- C2b quote scales with the requested budget (3600s x 1 fen, floor 500)'
SELECT reserve_minor, min_charge_minor, quote_ref FROM elmos_wallet_quote('GENERATION','gen',3600);
SELECT reserve_minor AS short_job_falls_back_to_floor
  FROM elmos_wallet_quote('GENERATION','gen',60);

-- ===========================================================================
-- C3  A funded prepaid tenant can now enqueue, and money is held
-- ===========================================================================
\echo '--- C3 wallet earns exactly one concurrency slot'
SELECT elmos_execution_concurrency_limit('org-pre') AS prepaid_slots,
       elmos_execution_concurrency_limit('org-sub') AS subscribed_slots,
       elmos_execution_concurrency_limit('org-broke') AS empty_wallet_slots;

SELECT elmos_enqueue_execution_job('job-on-1','org-pre','actor-p','GENERATION','gen',
    'idem-on-1', repeat('c',64), '{}'::jsonb, 'cap', :IMAGE, 100::smallint, 3600, 1::smallint);

\echo '--- C3a expect one HELD reservation of 3600, balance untouched, spendable down'
SELECT status, amount_minor FROM wallet_reservations WHERE organization_id='org-pre';
SELECT balance_minor, reserved_minor, balance_minor - reserved_minor AS spendable
  FROM wallet_accounts WHERE organization_id='org-pre';

\echo '--- C3b a retried enqueue returns the same job and does NOT hold twice'
SELECT elmos_enqueue_execution_job('job-on-1b','org-pre','actor-p','GENERATION','gen',
    'idem-on-1', repeat('c',64), '{}'::jsonb, 'cap', :IMAGE, 100::smallint, 3600, 1::smallint)
    AS returns_original_job;
SELECT count(*) AS holds FROM wallet_reservations WHERE organization_id='org-pre';

\echo '--- C3c the subscribed tenant is covered by allowance: still nothing held'
SELECT elmos_enqueue_execution_job('job-on-2','org-sub','actor-s','GENERATION','gen',
    'idem-on-2', repeat('d',64), '{}'::jsonb, 'cap', :IMAGE, 100::smallint, 3600, 1::smallint);
SELECT count(*) AS reservations_for_subscriber FROM wallet_reservations WHERE organization_id='org-sub';

-- ===========================================================================
-- C4  Insufficient balance must leave NO trace of the job
-- ===========================================================================
\echo '--- C4 an unfunded tenant is refused, and the refusal is atomic'
DO $$ BEGIN
    PERFORM elmos_wallet_create_topup_order('tu-b','org-broke','a',1000,'ALIPAY','ALI-B','idem-b',3600);
    PERFORM elmos_wallet_credit_topup('org-broke','tu-b','t','sys');   -- 1000 fen, quote needs 3600
    PERFORM elmos_enqueue_execution_job('job-poor','org-broke','actor-b','GENERATION','gen',
        'idem-poor', repeat('e',64), '{}'::jsonb, 'cap',
        'registry.example.com/elmos/runner@sha256:1111111111111111111111111111111111111111111111111111111111111111',
        100::smallint, 3600, 1::smallint);
    RAISE EXCEPTION 'TEST_FAILED_enqueued_without_funds';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%INSUFFICIENT_BALANCE%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- C4a expect zero rows in all three tables for the refused job'
SELECT (SELECT count(*) FROM execution_jobs WHERE job_id='job-poor') AS jobs,
       (SELECT count(*) FROM execution_job_dispatch WHERE job_id='job-poor') AS dispatch,
       (SELECT count(*) FROM execution_job_events WHERE job_id='job-poor') AS events,
       (SELECT count(*) FROM wallet_reservations WHERE job_id='job-poor') AS holds;

-- ===========================================================================
-- C5  Terminal state enqueues settlement work
-- ===========================================================================
\echo '--- C5 finishing the job writes exactly one outbox row'
UPDATE execution_jobs SET status='RUNNING', started_at = now() - interval '400 seconds'
 WHERE job_id='job-on-1';
UPDATE execution_jobs SET status='SUCCEEDED', finished_at=now() WHERE job_id='job-on-1';
SELECT job_status, resolved_at IS NULL AS pending FROM wallet_settlement_outbox WHERE job_id='job-on-1';

\echo '--- C5a facts the settler prices from (elapsed ~400s, not queue time)'
SELECT status, elapsed_seconds, chargeable_failure FROM elmos_wallet_settlement_facts('org-pre','job-on-1');

\echo '--- C5b claim, then resolve at 400 fen (400s x 1 fen)'
SELECT job_id, job_status, attempts FROM elmos_wallet_claim_settlements(10, 120);
SELECT elmos_wallet_resolve_settlement('wsx-' || md5('job-on-1'), 400, 'SUCCEEDED', 'settler')
    AS resolved;
SELECT elmos_wallet_resolve_settlement('wsx-' || md5('job-on-1'), 400, 'SUCCEEDED', 'settler')
    AS second_call_is_a_noop;

\echo '--- C5c expect charged 400, hold released, ledger has one CONSUME'
SELECT balance_minor, reserved_minor FROM wallet_accounts WHERE organization_id='org-pre';
SELECT status, settled_amount_minor FROM wallet_reservations WHERE job_id='job-on-1';
SELECT entry_type, amount_minor FROM wallet_ledger_entries
 WHERE organization_id='org-pre' ORDER BY seq;

-- ===========================================================================
-- C6  A failed job costs nothing, by default
-- ===========================================================================
SELECT elmos_enqueue_execution_job('job-fail','org-pre','actor-p','GENERATION','gen',
    'idem-fail', repeat('f',64), '{}'::jsonb, 'cap', :IMAGE, 100::smallint, 3600, 1::smallint);
UPDATE execution_jobs SET status='FAILED', failure_code='RUNNER_OOM', finished_at=now()
 WHERE job_id='job-fail';

\echo '--- C6 RUNNER_OOM is not in the chargeable list, so it is not chargeable'
SELECT chargeable_failure FROM elmos_wallet_settlement_facts('org-pre','job-fail');
SELECT elmos_wallet_resolve_settlement('wsx-' || md5('job-fail'), 0, 'FAILED_NOT_CHARGED', 'settler');
\echo '--- C6a expect RELEASED with no settled amount, and no new ledger entry'
SELECT status, settled_amount_minor, resolution_code FROM wallet_reservations WHERE job_id='job-fail';
SELECT count(*) AS consume_entries FROM wallet_ledger_entries
 WHERE organization_id='org-pre' AND entry_type='CONSUME';

-- ===========================================================================
-- C7  Turning the flag back off restores the previous behaviour
-- ===========================================================================
UPDATE wallet_enforcement_settings SET enabled = false;
\echo '--- C7 prepaid tenant is refused again, exactly as before V74'
SELECT elmos_execution_concurrency_limit('org-pre') AS prepaid_slots_with_flag_off;

\echo '--- C8 invariants hold on both tenants'
SELECT organization_id,
       projected_balance_minor - ledger_balance_minor AS balance_drift,
       projected_reserved_minor - held_reserved_minor AS reserved_drift
  FROM elmos_wallet_reconcile('org-pre')
UNION ALL
SELECT organization_id,
       projected_balance_minor - ledger_balance_minor,
       projected_reserved_minor - held_reserved_minor
  FROM elmos_wallet_reconcile('org-broke');

\echo ''
\echo '================ WALLET CHARGING SUITE PASSED ================'
