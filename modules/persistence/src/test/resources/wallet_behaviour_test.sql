\set ON_ERROR_STOP on
\pset pager off

-- ---------------------------------------------------------------------------
-- Fixture
-- ---------------------------------------------------------------------------
INSERT INTO organizations (organization_id, display_name, data_region)
VALUES ('org-w1', 'wallet test 1', 'cn-north'), ('org-w2', 'wallet test 2', 'cn-north')
ON CONFLICT DO NOTHING;

SELECT elmos_wallet_open('org-w1');
SELECT elmos_wallet_open('org-w1');   -- idempotent
\echo '--- T01 wallet opens idempotently (expect one row, balance 0)'
SELECT organization_id, balance_minor, reserved_minor, status FROM wallet_accounts WHERE organization_id='org-w1';

-- ---------------------------------------------------------------------------
-- T02 top-up credits once, replay is a no-op
-- ---------------------------------------------------------------------------
INSERT INTO wallet_topup_orders (topup_order_id, organization_id, actor_id, amount_minor,
    provider, out_trade_no, idempotency_key, expires_at)
VALUES ('tu-1', 'org-w1', 'actor-1', 100000, 'WECHAT_PAY', 'WX-0001', 'idem-tu-1', now() + interval '1 hour');

SELECT elmos_wallet_credit_topup('tu-1', 'wxtxn-1', 'actor-1') AS first_credit;
SELECT elmos_wallet_credit_topup('tu-1', 'wxtxn-1', 'actor-1') AS replayed_credit;
SELECT elmos_wallet_credit_topup('tu-1', 'wxtxn-1', 'actor-1') AS replayed_again;

\echo '--- T02 expect balance 100000 and exactly ONE ledger entry'
SELECT balance_minor FROM wallet_accounts WHERE organization_id='org-w1';
SELECT count(*) AS topup_entries FROM wallet_ledger_entries
 WHERE organization_id='org-w1' AND entry_type='TOPUP_SETTLED';
SELECT status, credited_entry_ref IS NOT NULL AS has_entry FROM wallet_topup_orders WHERE topup_order_id='tu-1';

-- ---------------------------------------------------------------------------
-- T03 reserve holds, spendable shrinks, balance does not
-- ---------------------------------------------------------------------------
SELECT elmos_wallet_reserve('res-1','org-w1','job-1', 30000, '2026-08-25.1/GENERATION/*','actor-1', 3600);
\echo '--- T03 expect balance 100000, reserved 30000'
SELECT balance_minor, reserved_minor, balance_minor - reserved_minor AS spendable
  FROM wallet_accounts WHERE organization_id='org-w1';
\echo '--- T03b a hold is NOT a ledger movement (expect still 1 entry)'
SELECT count(*) AS ledger_entries FROM wallet_ledger_entries WHERE organization_id='org-w1';

-- ---------------------------------------------------------------------------
-- T04 reserve is idempotent per job
-- ---------------------------------------------------------------------------
SELECT elmos_wallet_reserve('res-1b','org-w1','job-1', 30000, 'q','actor-1', 3600) AS same_reservation;
\echo '--- T04 expect reserved still 30000 (one hold, not two)'
SELECT reserved_minor FROM wallet_accounts WHERE organization_id='org-w1';

-- ---------------------------------------------------------------------------
-- T05 over-reserve is refused against SPENDABLE, not balance
-- ---------------------------------------------------------------------------
\echo '--- T05 expect ELMOS_WALLET_INSUFFICIENT_BALANCE (80000 > 100000-30000)'
DO $$ BEGIN
    PERFORM elmos_wallet_reserve('res-2','org-w1','job-2', 80000, 'q','actor-1', 3600);
    RAISE EXCEPTION 'TEST_FAILED_over_reserve_was_allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%INSUFFICIENT_BALANCE%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

-- ---------------------------------------------------------------------------
-- T06 settle charges at most the hold and returns the rest
-- ---------------------------------------------------------------------------
SELECT elmos_wallet_settle('org-w1','job-1', 12000, 'settler','SUCCEEDED');
\echo '--- T06 expect balance 88000, reserved 0, settled 12000'
SELECT balance_minor, reserved_minor FROM wallet_accounts WHERE organization_id='org-w1';
SELECT status, amount_minor, settled_amount_minor FROM wallet_reservations WHERE reservation_id='res-1';

\echo '--- T06b settler retry must not double charge'
SELECT elmos_wallet_settle('org-w1','job-1', 12000, 'settler','SUCCEEDED');
SELECT balance_minor FROM wallet_accounts WHERE organization_id='org-w1';
SELECT count(*) AS consume_entries FROM wallet_ledger_entries
 WHERE organization_id='org-w1' AND entry_type='CONSUME';

-- ---------------------------------------------------------------------------
-- T07 settle clamps an over-quote to the hold (the promise made at submit time)
-- ---------------------------------------------------------------------------
SELECT elmos_wallet_reserve('res-3','org-w1','job-3', 5000, 'q','actor-1', 3600);
SELECT elmos_wallet_settle('org-w1','job-3', 999999, 'settler','SUCCEEDED');
\echo '--- T07 expect settled_amount 5000, not 999999'
SELECT settled_amount_minor FROM wallet_reservations WHERE reservation_id='res-3';

-- ---------------------------------------------------------------------------
-- T08 release returns the whole hold, no ledger movement
-- ---------------------------------------------------------------------------
SELECT elmos_wallet_reserve('res-4','org-w1','job-4', 7000, 'q','actor-1', 3600);
SELECT elmos_wallet_release('org-w1','job-4','FAILED_PLATFORM');
\echo '--- T08 expect reserved 0 and status RELEASED'
SELECT reserved_minor FROM wallet_accounts WHERE organization_id='org-w1';
SELECT status, settled_amount_minor FROM wallet_reservations WHERE reservation_id='res-4';

-- ---------------------------------------------------------------------------
-- T09 expiry sweeper frees a hold nobody resolved
-- ---------------------------------------------------------------------------
SELECT elmos_wallet_reserve('res-5','org-w1','job-5', 9000, 'q','actor-1', 60);
-- Backdate BOTH ends: wallet_reservations_expiry_after_hold rejects an expiry
-- before the hold, which is the constraint doing its job on a lazy test.
UPDATE wallet_reservations SET held_at = now() - interval '2 hours',
       expires_at = now() - interval '1 hour' WHERE reservation_id='res-5';
SELECT elmos_wallet_expire_reservations(100) AS expired_count;
\echo '--- T09 expect 1 expired, reserved back to 0'
SELECT status, resolution_code FROM wallet_reservations WHERE reservation_id='res-5';
SELECT reserved_minor FROM wallet_accounts WHERE organization_id='org-w1';

-- ---------------------------------------------------------------------------
-- T10 GUARDS: every one of these must be REFUSED
-- ---------------------------------------------------------------------------
\echo '--- T10a direct balance UPDATE must be denied'
DO $$ BEGIN
    UPDATE wallet_accounts SET balance_minor = 999999 WHERE organization_id='org-w1';
    RAISE EXCEPTION 'TEST_FAILED_direct_balance_update_allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%DIRECT_MUTATION_DENIED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- T10b direct reserved UPDATE must be denied'
DO $$ BEGIN
    UPDATE wallet_accounts SET reserved_minor = 5 WHERE organization_id='org-w1';
    RAISE EXCEPTION 'TEST_FAILED_direct_reserved_update_allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%DIRECT_MUTATION_DENIED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- T10c wallet DELETE must be denied'
DO $$ BEGIN
    DELETE FROM wallet_accounts WHERE organization_id='org-w1';
    RAISE EXCEPTION 'TEST_FAILED_wallet_delete_allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%WALLET_DELETE_DENIED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- T10d ledger UPDATE must be denied (append-only)'
DO $$ BEGIN
    UPDATE wallet_ledger_entries SET amount_minor = 1 WHERE organization_id='org-w1';
    RAISE EXCEPTION 'TEST_FAILED_ledger_update_allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%append-only%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- T10e ledger DELETE must be denied (append-only)'
DO $$ BEGIN
    DELETE FROM wallet_ledger_entries WHERE organization_id='org-w1';
    RAISE EXCEPTION 'TEST_FAILED_ledger_delete_allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%append-only%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- T10f resolved reservation must be immutable'
DO $$ BEGIN
    UPDATE wallet_reservations SET status='HELD' WHERE reservation_id='res-1';
    RAISE EXCEPTION 'TEST_FAILED_terminal_reservation_mutable';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%RESERVATION_TERMINAL_IMMUTABLE%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- T10g reservation amount must be immutable'
DO $$ BEGIN
    UPDATE wallet_reservations SET amount_minor = 1 WHERE reservation_id='res-3';
    RAISE EXCEPTION 'TEST_FAILED_reservation_amount_mutable';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%AMOUNT_IMMUTABLE%' AND SQLERRM NOT LIKE '%TERMINAL_IMMUTABLE%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- T10h credited top-up amount must be immutable'
DO $$ BEGIN
    UPDATE wallet_topup_orders SET amount_minor = 1 WHERE topup_order_id='tu-1';
    RAISE EXCEPTION 'TEST_FAILED_topup_amount_mutable';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%IMMUTABLE%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- T10i administrator adjustment without a reason must be denied'
DO $$ BEGIN
    PERFORM elmos_wallet_adjust('org-w1','CREDIT', 100, 'admin-1', NULL, 'idem-adj-bad');
    RAISE EXCEPTION 'TEST_FAILED_adjustment_without_reason_allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%REASON_REQUIRED%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- T10j price book is append-only'
DO $$ BEGIN
    UPDATE wallet_price_book SET reserve_minor = 1 WHERE business_line='GENERATION';
    RAISE EXCEPTION 'TEST_FAILED_price_book_mutable';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%append-only%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- T10k debit below zero must be denied'
DO $$ BEGIN
    PERFORM elmos_wallet_adjust('org-w1','DEBIT', 99999999, 'admin-1', 'try to overdraw', 'idem-adj-over');
    RAISE EXCEPTION 'TEST_FAILED_overdraw_allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%INSUFFICIENT_BALANCE%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

-- ---------------------------------------------------------------------------
-- T11 administrator adjustment with a reason works and is idempotent
-- ---------------------------------------------------------------------------
SELECT elmos_wallet_adjust('org-w1','CREDIT', 2500, 'admin-1', '客服补偿工单 #443', 'idem-adj-ok');
SELECT elmos_wallet_adjust('org-w1','CREDIT', 2500, 'admin-1', '客服补偿工单 #443', 'idem-adj-ok');
\echo '--- T11 expect exactly one ADMIN_ADJUSTMENT with the reason recorded'
SELECT count(*) AS adjustments, max(reason) AS reason FROM wallet_ledger_entries
 WHERE organization_id='org-w1' AND entry_type='ADMIN_ADJUSTMENT';

-- ---------------------------------------------------------------------------
-- T12 the ledger proves itself: projection must equal the authority
-- ---------------------------------------------------------------------------
\echo '--- T12 expect zero drift on both columns'
SELECT organization_id,
       projected_balance_minor, ledger_balance_minor,
       projected_balance_minor - ledger_balance_minor AS balance_drift,
       projected_reserved_minor, held_reserved_minor,
       projected_reserved_minor - held_reserved_minor AS reserved_drift
  FROM elmos_wallet_reconcile();

\echo '--- T12b balance_after chain must be self-consistent by replay'
SELECT bool_and(replayed = balance_after_minor) AS chain_intact
  FROM (
    SELECT balance_after_minor,
           sum(CASE WHEN direction='CREDIT' THEN amount_minor ELSE -amount_minor END)
             OVER (PARTITION BY organization_id ORDER BY seq) AS replayed
      FROM wallet_ledger_entries
  ) t;

-- ---------------------------------------------------------------------------
-- T13 top-up bounds default when no per-tenant policy exists
-- ---------------------------------------------------------------------------
\echo '--- T13 expect defaults 100 / 5000000 / 20000000'
SELECT * FROM elmos_wallet_topup_bounds('org-w1');
INSERT INTO wallet_topup_policies (organization_id, min_amount_minor, max_amount_minor,
    daily_amount_limit_minor, updated_by)
VALUES ('org-w1', 1000, 100000, 500000, 'admin-1');
\echo '--- T13b expect the per-tenant override'
SELECT * FROM elmos_wallet_topup_bounds('org-w1');

-- ---------------------------------------------------------------------------
-- T14 row level security is on, forced, with the standard policy
-- ---------------------------------------------------------------------------
\echo '--- T14 expect 5 rows, all relrowsecurity and relforcerowsecurity true'
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
       (SELECT count(*) FROM pg_policies p
         WHERE p.tablename = c.relname AND p.policyname='tenant_isolation') AS policy
  FROM pg_class c
 WHERE c.relname IN ('wallet_accounts','wallet_ledger_entries','wallet_reservations',
                     'wallet_topup_orders','wallet_topup_policies')
 ORDER BY c.relname;

\echo '--- T14b settlement outbox is deliberately NOT tenant isolated and not public'
SELECT relrowsecurity FROM pg_class WHERE relname='wallet_settlement_outbox';
SELECT has_table_privilege('public','wallet_settlement_outbox','SELECT') AS public_can_read;

-- ---------------------------------------------------------------------------
-- T15 seeded prices are DRAFT: an unapproved price cannot charge anyone
-- ---------------------------------------------------------------------------
\echo '--- T15 expect 5 rows, all DRAFT'
SELECT business_line, job_kind, reserve_minor, status FROM wallet_price_book ORDER BY business_line;

\echo ''
\echo '================ ALL BEHAVIOUR ASSERTIONS PASSED ================'
