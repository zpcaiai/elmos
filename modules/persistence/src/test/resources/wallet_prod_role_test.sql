\set ON_ERROR_STOP on
\pset pager off
-- Runs entirely as elmos_app_prod: a NOSUPERUSER, non-BYPASSRLS application role
-- that holds EXECUTE on the accounting functions and nothing else. The wallet
-- objects are owned by a NOSUPERUSER role, so FORCE ROW LEVEL SECURITY applies
-- inside the SECURITY DEFINER functions too. This is the configuration the
-- earlier superuser run could not have caught anything in.

INSERT INTO organizations (organization_id, display_name, data_region)
VALUES ('org-p1','prod role probe','cn-north') ON CONFLICT DO NOTHING;

\echo '--- P01 open a wallet with NO tenant context bound (the payment callback case)'
SELECT elmos_wallet_open('org-p1');

\echo '--- P02 top-up order, then credit it with NO tenant context bound'
SELECT elmos_wallet_create_topup_order(
    'tp-1','org-p1','actor-1',100000,'ALIPAY','ALI-P1','idem-p1',3600) AS order_created;
SELECT elmos_wallet_create_topup_order(
    'tp-1b','org-p1','actor-1',100000,'ALIPAY','ALI-P1b','idem-p1',3600) AS same_order_replayed;

\echo '--- P02a the callback can resolve the tenant before it has one'
SELECT out_trade_no, organization_id, amount_minor, status FROM wallet_topup_order_directory
 WHERE out_trade_no = 'ALI-P1';

SELECT elmos_wallet_credit_topup('org-p1','tp-1','txn-1','system-callback') AS credited;
SELECT elmos_wallet_credit_topup('org-p1','tp-1','txn-1','system-callback') AS replayed;

\echo '--- P02b directory status follows the order'
SELECT status FROM wallet_topup_order_directory WHERE out_trade_no = 'ALI-P1';

\echo '--- P03 reserve / settle / release with no tenant context bound'
SELECT elmos_wallet_reserve('rp-1','org-p1','pjob-1',30000,'q','actor-1',3600);
SELECT elmos_wallet_settle('org-p1','pjob-1',12000,'settler','SUCCEEDED');
SELECT elmos_wallet_reserve('rp-2','org-p1','pjob-2',7000,'q','actor-1',3600);
SELECT elmos_wallet_release('org-p1','pjob-2','FAILED_PLATFORM');

\echo '--- P04 hold that the sweeper will later collect (backdated by the harness)'
SELECT elmos_wallet_reserve('rp-3','org-p1','pjob-3',9000,'q','actor-1',60);

\echo '--- P05 reconcile: expect 0 drift on both columns'
SELECT projected_balance_minor - ledger_balance_minor AS balance_drift,
       projected_reserved_minor - held_reserved_minor AS reserved_drift
  FROM elmos_wallet_reconcile('org-p1');

\echo '--- P06 the bound tenant must NOT leak out of the function'
SELECT coalesce(nullif(current_setting('app.organization_id', true), ''), '<unset>') AS context_after_calls;

\echo '--- P07 a tenant cannot credit a top-up belonging to another tenant'
INSERT INTO organizations (organization_id, display_name, data_region)
VALUES ('org-p2','other tenant','cn-north') ON CONFLICT DO NOTHING;
DO $$ BEGIN
    PERFORM elmos_wallet_credit_topup('org-p2','tp-1','txn-x','attacker');
    RAISE EXCEPTION 'TEST_FAILED_cross_tenant_credit_allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%TOPUP_UNKNOWN%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- P08 the app role still cannot touch the tables directly'
DO $$ BEGIN
    PERFORM 1 FROM wallet_accounts;
    RAISE EXCEPTION 'TEST_FAILED_app_role_can_read_wallets';
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;
DO $$ BEGIN
    PERFORM 1 FROM wallet_ledger_entries;
    RAISE EXCEPTION 'TEST_FAILED_app_role_can_read_ledger';
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- P09 an empty tenant argument is refused rather than binding nothing'
DO $$ BEGIN
    PERFORM elmos_wallet_open('');
    RAISE EXCEPTION 'TEST_FAILED_empty_tenant_accepted';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%TENANT_REQUIRED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- P10 final balances'
SELECT projected_balance_minor AS balance, projected_reserved_minor AS reserved
  FROM elmos_wallet_reconcile('org-p1');


\echo '--- P11 amount bounds and the daily cap are enforced by the storage layer'
DO $$ BEGIN
    PERFORM elmos_wallet_create_topup_order('tp-lo','org-p1','a',1,'ALIPAY','ALI-LO','idem-lo',3600);
    RAISE EXCEPTION 'TEST_FAILED_below_minimum_accepted';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%BELOW_MINIMUM%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;
DO $$ BEGIN
    PERFORM elmos_wallet_create_topup_order('tp-hi','org-p1','a',9999999,'ALIPAY','ALI-HI','idem-hi',3600);
    RAISE EXCEPTION 'TEST_FAILED_above_maximum_accepted';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%ABOVE_MAXIMUM%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;
DO $$
DECLARE i integer;
BEGIN
    -- Default daily cap is 20,000,000 fen, per-order max 5,000,000, and tp-1
    -- already spent 100,000 of today's allowance. Three maxed orders bring the
    -- day to 15,100,000; a fourth would reach 20,100,000 and must be refused.
    -- The first version of this loop forgot tp-1 and expected the refusal one
    -- order later -- the arithmetic was the test's, not the function's.
    FOR i IN 1..3 LOOP
        PERFORM elmos_wallet_create_topup_order(
            'tp-day-' || i, 'org-p1', 'a', 5000000, 'ALIPAY',
            'ALI-DAY-' || i, 'idem-day-' || i, 3600);
    END LOOP;
    BEGIN
        PERFORM elmos_wallet_create_topup_order(
            'tp-day-4','org-p1','a',5000000,'ALIPAY','ALI-DAY-4','idem-day-4',3600);
        RAISE EXCEPTION 'TEST_FAILED_daily_cap_not_enforced';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM NOT LIKE '%DAILY_LIMIT_EXCEEDED%' THEN RAISE; END IF;
        RAISE NOTICE 'OK refused: %', SQLERRM;
    END;
END $$;

\echo ''
\echo '======== PRODUCTION-ROLE RUN PASSED (NOSUPERUSER owner, RLS enforced) ========'
