\set ON_ERROR_STOP on
\pset pager off

-- The only eligible administrator plus deliberately ineligible identities.
INSERT INTO accounts (account_id, display_name, primary_email, email_verified_at, status)
VALUES ('acct-root','designated operator','zpchoney@gmail.com', now(), 'ACTIVE'),
       ('acct-two','second approver','two@example.com', now(), 'ACTIVE'),
       ('acct-view','alias is not administrator','zpchoney+alias@gmail.com', now(), 'ACTIVE'),
       ('acct-nobody','not an admin','nobody@example.com', now(), 'ACTIVE')
ON CONFLICT DO NOTHING;

-- ===========================================================================
-- A  Nothing works before there is an administrator
-- ===========================================================================
\echo '--- A1 a non-administrator sees nothing, and the refusal is recorded'
SELECT count(*) AS rows_returned FROM elmos_platform_wallet_overview('acct-nobody');
SELECT result, operation FROM platform_admin_access_log
 WHERE admin_account_id='acct-nobody' ORDER BY occurred_at DESC LIMIT 1;

\echo '--- A2 an unknown account is refused the same way'
SELECT count(*) AS rows_returned FROM elmos_platform_wallet_ledger('acct-ghost','org-pre');
SELECT result FROM platform_admin_access_log WHERE admin_account_id='acct-ghost';

-- ===========================================================================
-- B  Bootstrap, then normal grants
-- ===========================================================================
\echo '--- B1 bootstrap the first approver'
SELECT elmos_platform_bootstrap_admin('acct-root','initial platform operator, ticket OPS-1') AS bootstrap;

\echo '--- B2 bootstrap is closed once an approver exists'
SELECT elmos_platform_bootstrap_admin('acct-nobody','trying to sneak in') AS second_bootstrap;
SELECT count(*) AS admins_after_second_bootstrap FROM platform_administrators WHERE revoked_at IS NULL;

\echo '--- B3 even the approver cannot grant another email'
SELECT elmos_platform_grant_admin('acct-root','acct-view','PLATFORM_VIEWER','support rota') AS grant_viewer;
\echo '--- B3a a grant with no reason is refused'
SELECT elmos_platform_grant_admin('acct-root','acct-two','PLATFORM_APPROVER','') AS grant_without_reason;
\echo '--- B3b a viewer cannot grant anyone'
SELECT elmos_platform_grant_admin('acct-view','acct-two','PLATFORM_APPROVER','trying') AS viewer_grants;

-- ===========================================================================
-- C  Reads see across tenants, and every read is logged
-- ===========================================================================
\echo '--- C1 the designated administrator sees every tenant wallet'
SELECT organization_id, balance_minor, reserved_minor, spendable_minor, held_reservations
  FROM elmos_platform_wallet_overview('acct-root') ORDER BY organization_id;

\echo '--- C2 the read named the operation; a per-tenant read names the tenant'
SELECT count(*) AS ledger_rows FROM elmos_platform_wallet_ledger('acct-root','org-pre');
SELECT operation, target_organization_id, result FROM platform_admin_access_log
 WHERE admin_account_id='acct-root' ORDER BY occurred_at;

\echo '--- C3 jobs across tenants, with the money attached'
SELECT organization_id, job_id, status, settled_amount_minor, hold_status
  FROM elmos_platform_job_overview('acct-root') ORDER BY organization_id, job_id;

\echo '--- C4 top-up orders across tenants'
SELECT organization_id, provider, amount_minor, status
  FROM elmos_platform_topup_orders('acct-root') ORDER BY organization_id;

\echo '--- C5 the bound tenant does not leak out'
SELECT coalesce(nullif(current_setting('app.organization_id', true),''),'<unset>') AS context_after_reads;

-- ===========================================================================
-- D  The one cross-tenant write
-- ===========================================================================
\echo '--- D1 a viewer cannot adjust a balance'
SELECT status, entry_id FROM elmos_platform_wallet_adjust(
    'acct-view','org-pre','CREDIT',1000,'trying it on','idem-v1');

\echo '--- D2 the approver can, and the ledger names them'
SELECT status FROM elmos_platform_wallet_adjust(
    'acct-root','org-pre','CREDIT',1000,'客服补偿 OPS-7','idem-r1');
SELECT entry_type, amount_minor, actor_id, reason FROM wallet_ledger_entries
 WHERE organization_id='org-pre' AND entry_type='ADMIN_ADJUSTMENT';

\echo '--- D3 the same idempotency key does not double-credit'
SELECT status FROM elmos_platform_wallet_adjust(
    'acct-root','org-pre','CREDIT',1000,'客服补偿 OPS-7','idem-r1');
SELECT count(*) AS adjustments FROM wallet_ledger_entries
 WHERE organization_id='org-pre' AND entry_type='ADMIN_ADJUSTMENT';

-- ===========================================================================
-- E  Revocation, and the guard on the last approver
-- ===========================================================================
\echo '--- E1 the only approver cannot revoke themselves'
SELECT elmos_platform_revoke_admin('acct-root','acct-root','stepping down') AS revoke_last_approver;
SELECT platform_role, revoked_at IS NULL AS still_live FROM platform_administrators
 WHERE account_id='acct-root';

\echo '--- E2 a second approver cannot be created and cannot revoke the designated admin'
SELECT elmos_platform_grant_admin('acct-root','acct-two','PLATFORM_APPROVER','handover') AS grant_second;
SELECT elmos_platform_revoke_admin('acct-two','acct-root','handover complete') AS revoke_now_allowed;
SELECT account_id, platform_role, revoked_at IS NULL AS live FROM platform_administrators
 ORDER BY account_id;

\echo '--- E3 losing verified email automatically revokes without blocking the account update'
UPDATE accounts
   SET email_verified_at = NULL, phone_verified_at = now()
 WHERE account_id = 'acct-root';
SELECT count(*) AS rows_for_revoked FROM elmos_platform_wallet_overview('acct-root');
SELECT operation, result FROM platform_admin_access_log
 WHERE admin_account_id='acct-root' ORDER BY occurred_at DESC LIMIT 1;

\echo '--- E4 re-verification does not silently restore privilege; bootstrap is explicit'
UPDATE accounts SET email_verified_at = now() WHERE account_id = 'acct-root';
SELECT elmos_platform_authorize(
    'acct-root','PLATFORM_VIEWER','NOT_AUTO_REGRANTED') AS before_restore;
SELECT elmos_platform_bootstrap_admin(
    'acct-root','explicit restore after re-verification') AS restore;

\echo '--- E5 direct writes cannot bypass the exact-email guard'
DO $$ BEGIN
    INSERT INTO platform_administrators (account_id, platform_role, grant_reason)
    VALUES ('acct-view','PLATFORM_VIEWER','attempted direct bypass');
    RAISE EXCEPTION 'TEST_FAILED_direct_admin_write_allowed';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%ELMOS_PLATFORM_ADMIN_VERIFIED_EMAIL_REQUIRED%'
       THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- E6 the audit log is append-only'
DO $$ BEGIN
    UPDATE platform_admin_access_log SET result='ALLOWED' WHERE result LIKE 'DENIED%';
    RAISE EXCEPTION 'TEST_FAILED_audit_log_rewritable';
EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%append-only%' THEN RAISE; END IF;
    RAISE NOTICE 'OK refused: %', SQLERRM;
END $$;

\echo '--- E7 every attempt in this run left a row, allowed and denied alike'
SELECT result, count(*) FROM platform_admin_access_log GROUP BY result ORDER BY result;

\echo ''
\echo '================ PLATFORM ADMIN SUITE PASSED ================'
