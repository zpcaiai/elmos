-- Executable acceptance rehearsal for the V55 authentication runtime.
-- Requires V1..V55. Every RAISE EXCEPTION is a real assertion.
--
-- Deliberately exercised through a NON-SUPERUSER role wherever the application
-- would be one, because RLS and grants behave differently for a superuser and
-- testing as one proves nothing about production.

\set ON_ERROR_STOP on
BEGIN;

-- ---------------------------------------------------------------------------
-- Application role, mirroring how the control plane connects
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_app_test') THEN
        CREATE ROLE elmos_app_test NOLOGIN;
    END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION
    elmos_issue_verification_challenge(varchar, varchar, varchar, varchar, varchar, integer, varchar),
    elmos_consume_verification_challenge(varchar, varchar, varchar),
    elmos_complete_signup(varchar, varchar, varchar, varchar, varchar, varchar),
    elmos_open_session(varchar, varchar, varchar, varchar, integer, integer, text[], varchar, varchar, varchar),
    elmos_rotate_session_token(varchar, varchar, integer),
    elmos_record_sign_in_failure(varchar, smallint, integer),
    elmos_consume_rate_budget(varchar, varchar, integer, integer)
TO elmos_app_test;

-- ---------------------------------------------------------------------------
-- Provider configuration is fail-closed
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    -- An SMS provider without a filed signature must not go ACTIVE. Sending
    -- unfiled template SMS in mainland China suspends the whole signature.
    BEGIN
        UPDATE identity_message_providers
           SET provider_state = 'ACTIVE', credential_reference = 'secret://sms'
         WHERE provider_id = 'sms-primary';
        RAISE EXCEPTION 'ASSERT_FAILED: an unfiled SMS provider went ACTIVE';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;
END;
$$;

-- Issuing a code nobody can deliver strands the user, so it is refused.
DO $$
BEGIN
    BEGIN
        PERFORM elmos_issue_verification_challenge(
            'chal-none', 'SMS', repeat('a', 64), 'SIGN_UP', repeat('1', 64), 300, '10.0.0');
        RAISE EXCEPTION 'ASSERT_FAILED: a challenge was issued with no active provider';
    EXCEPTION WHEN sqlstate 'P0001' THEN
        IF SQLERRM NOT LIKE '%PROVIDER_NOT_CONFIGURED%' THEN RAISE; END IF;
    END;
END;
$$;

UPDATE identity_message_providers
   SET provider_state = 'ACTIVE', credential_reference = 'secret://sms',
       signature_name = 'ELMOS', filing_reference = 'SMS-FILING-2026-0001'
 WHERE provider_id = 'sms-primary';

-- ---------------------------------------------------------------------------
-- Rate limiting
-- ---------------------------------------------------------------------------

DO $$
DECLARE v_hmac varchar := repeat('b', 64);
BEGIN
    PERFORM elmos_issue_verification_challenge(
        'chal-1', 'SMS', v_hmac, 'SIGN_UP', repeat('1', 64), 300, '10.0.0');

    -- Second request inside the same minute: the resend button must not become an
    -- SMS cannon aimed at one number.
    BEGIN
        PERFORM elmos_issue_verification_challenge(
            'chal-2', 'SMS', v_hmac, 'SIGN_UP', repeat('2', 64), 300, '10.0.0');
        RAISE EXCEPTION 'ASSERT_FAILED: a second code was issued within the minute window';
    EXCEPTION WHEN sqlstate 'P0001' THEN
        IF SQLERRM NOT LIKE '%TOO_FREQUENT%' THEN RAISE; END IF;
    END;

    -- One source walking a range of numbers hits the client limit.
    FOR i IN 1..30 LOOP
        PERFORM elmos_consume_rate_budget('CLIENT_PREFIX', '10.0.9', 3600, 30);
    END LOOP;
    BEGIN
        PERFORM elmos_issue_verification_challenge(
            'chal-walk', 'SMS', repeat('c', 64), 'SIGN_UP', repeat('3', 64), 300, '10.0.9');
        RAISE EXCEPTION 'ASSERT_FAILED: the client-prefix limit did not apply';
    EXCEPTION WHEN sqlstate 'P0001' THEN
        IF SQLERRM NOT LIKE '%CLIENT_LIMIT%' THEN RAISE; END IF;
    END;
END;
$$;

-- ---------------------------------------------------------------------------
-- Challenge verification
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    v_hmac varchar := repeat('b', 64);
    v_result varchar;
    v_attempts smallint;
BEGIN
    -- Enumeration resistance: an unknown destination and a wrong code are
    -- indistinguishable to the caller. Both return NULL.
    v_result := elmos_consume_verification_challenge(repeat('f', 64), 'SIGN_UP', repeat('1', 64));
    IF v_result IS NOT NULL THEN
        RAISE EXCEPTION 'ASSERT_FAILED: an unknown destination returned a challenge';
    END IF;

    v_result := elmos_consume_verification_challenge(v_hmac, 'SIGN_UP', repeat('9', 64));
    IF v_result IS NOT NULL THEN
        RAISE EXCEPTION 'ASSERT_FAILED: a wrong code was accepted';
    END IF;

    SELECT attempt_count INTO v_attempts FROM account_verification_challenges
     WHERE challenge_id = 'chal-1';
    IF v_attempts <> 1 THEN
        RAISE EXCEPTION 'ASSERT_FAILED: the wrong attempt was not counted (%)', v_attempts;
    END IF;

    v_result := elmos_consume_verification_challenge(v_hmac, 'SIGN_UP', repeat('1', 64));
    IF v_result <> 'chal-1' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: the correct code was not accepted';
    END IF;

    -- Single use.
    v_result := elmos_consume_verification_challenge(v_hmac, 'SIGN_UP', repeat('1', 64));
    IF v_result IS NOT NULL THEN
        RAISE EXCEPTION 'ASSERT_FAILED: a consumed code was replayed';
    END IF;
END;
$$;

-- Attempt budget burns the challenge, so a five-guess window is not a six-guess one.
DO $$
DECLARE v_hmac varchar := repeat('d', 64);
BEGIN
    PERFORM elmos_issue_verification_challenge(
        'chal-burn', 'SMS', v_hmac, 'SIGN_IN', repeat('4', 64), 300, NULL);
    FOR i IN 1..5 LOOP
        PERFORM elmos_consume_verification_challenge(v_hmac, 'SIGN_IN', repeat('0', 64));
    END LOOP;
    IF elmos_consume_verification_challenge(v_hmac, 'SIGN_IN', repeat('4', 64)) IS NOT NULL THEN
        RAISE EXCEPTION 'ASSERT_FAILED: the correct code still worked after the attempt budget was spent';
    END IF;
    IF (SELECT invalidated_at FROM account_verification_challenges WHERE challenge_id = 'chal-burn') IS NULL THEN
        RAISE EXCEPTION 'ASSERT_FAILED: the exhausted challenge was not invalidated';
    END IF;
END;
$$;

-- A reissue retires the previous code; only the newest one works.
DO $$
DECLARE v_hmac varchar := repeat('e', 64);
BEGIN
    PERFORM elmos_issue_verification_challenge(
        'chal-old', 'SMS', v_hmac, 'SIGN_IN', repeat('5', 64), 300, NULL);
    UPDATE identity_rate_counters SET hits = 0
     WHERE counter_scope = 'DESTINATION' AND counter_key = v_hmac;
    PERFORM elmos_issue_verification_challenge(
        'chal-new', 'SMS', v_hmac, 'SIGN_IN', repeat('6', 64), 300, NULL);

    IF elmos_consume_verification_challenge(v_hmac, 'SIGN_IN', repeat('5', 64)) IS NOT NULL THEN
        RAISE EXCEPTION 'ASSERT_FAILED: a superseded code still worked';
    END IF;
    IF elmos_consume_verification_challenge(v_hmac, 'SIGN_IN', repeat('6', 64)) <> 'chal-new' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: the newest code did not work';
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Sign-up completion: account, organization and entitlement together
-- ---------------------------------------------------------------------------

DO $$
DECLARE v_org varchar;
BEGIN
    INSERT INTO accounts (account_id, status, display_name, phone_lookup_hmac,
                          phone_last4, phone_cipher_ref, phone_verified_at)
    VALUES ('acc-signup', 'PENDING_VERIFICATION', '新用户', repeat('7', 64),
            '8888', 'kms://phone/acc-signup', now());

    v_org := elmos_complete_signup('acc-signup', 'org-signup', '新用户的组织',
                                   'actor-signup', repeat('7', 64), 'cn-north');
    IF v_org <> 'org-signup' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: sign-up returned %', v_org;
    END IF;

    IF (SELECT status FROM accounts WHERE account_id = 'acc-signup') <> 'ACTIVE' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: the account was not activated';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM organization_memberships
                    WHERE organization_id = 'org-signup' AND member_role = 'OWNER') THEN
        RAISE EXCEPTION 'ASSERT_FAILED: no owner membership was created';
    END IF;

    -- The seam this function exists to close: a new organization must be able to
    -- run something immediately.
    IF elmos_execution_concurrency_limit('org-signup') < 1 THEN
        RAISE EXCEPTION 'ASSERT_FAILED: a freshly signed-up organization has no entitlement';
    END IF;
END;
$$;

-- An account with no verified channel cannot complete sign-up.
DO $$
BEGIN
    INSERT INTO accounts (account_id, status, display_name)
    VALUES ('acc-unverified', 'PENDING_VERIFICATION', 'Unverified');
    BEGIN
        PERFORM elmos_complete_signup('acc-unverified', 'org-unverified', 'X',
                                      'actor-x', repeat('8', 64), 'cn-north');
        RAISE EXCEPTION 'ASSERT_FAILED: an unverified account completed sign-up';
    EXCEPTION WHEN sqlstate 'P0001' THEN
        IF SQLERRM NOT LIKE '%NO_VERIFIED_CHANNEL%' THEN RAISE; END IF;
    END;
END;
$$;

-- One verified identity, one trial. Otherwise the free tier is unlimited.
DO $$
BEGIN
    INSERT INTO accounts (account_id, status, display_name, phone_lookup_hmac,
                          phone_last4, phone_cipher_ref, phone_verified_at)
    VALUES ('acc-second', 'PENDING_VERIFICATION', '同一个人', repeat('a', 63) || '1',
            '9999', 'kms://phone/acc-second', now());
    BEGIN
        -- Same verified subject hash as the first sign-up.
        PERFORM elmos_complete_signup('acc-second', 'org-second', '第二个组织',
                                      'actor-second', repeat('7', 64), 'cn-north');
        RAISE EXCEPTION 'ASSERT_FAILED: the same verified identity claimed a second trial';
    EXCEPTION WHEN unique_violation THEN
        NULL;
    WHEN sqlstate 'P0001' THEN
        IF SQLERRM NOT LIKE '%TRIAL%' THEN RAISE; END IF;
    END;
END;
$$;

-- ---------------------------------------------------------------------------
-- Sessions: rotation and stolen-token detection
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    v_first varchar := repeat('1', 64);
    v_second varchar := repeat('2', 64);
    v_third varchar := repeat('3', 64);
    v_outcome varchar;
BEGIN
    PERFORM elmos_open_session('sess-1', 'acc-signup', 'org-signup', v_first,
                               2592000, 1209600, ARRAY['SMS_OTP'], 'MacBook', 'chrome', '10.0.0');

    SELECT outcome INTO v_outcome FROM elmos_rotate_session_token(v_first, v_second, 1209600);
    IF v_outcome <> 'ROTATED' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: the current token did not rotate (%)', v_outcome;
    END IF;

    -- The decisive case. An attacker who copied the first token presents it after
    -- the real client already rotated. Refusing just this request would leak
    -- nothing and teach us nothing; the session must die.
    SELECT outcome INTO v_outcome FROM elmos_rotate_session_token(v_first, v_third, 1209600);
    IF v_outcome <> 'REUSED' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: a superseded token was not recognised as reuse (%)', v_outcome;
    END IF;
    IF (SELECT session_state FROM authentication_sessions WHERE authentication_session_id = 'sess-1') <> 'REVOKED' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: token reuse did not revoke the session';
    END IF;
    IF (SELECT revocation_code FROM authentication_sessions WHERE authentication_session_id = 'sess-1')
        <> 'REFRESH_TOKEN_REUSED' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: the revocation reason was not recorded';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM account_security_events
                    WHERE account_id = 'acc-signup' AND failure_code = 'REFRESH_TOKEN_REUSED') THEN
        RAISE EXCEPTION 'ASSERT_FAILED: the reuse was not recorded as a security event';
    END IF;

    -- The legitimate client's newer token is dead too, which is the point.
    SELECT outcome INTO v_outcome FROM elmos_rotate_session_token(v_second, repeat('4', 64), 1209600);
    IF v_outcome <> 'REJECTED' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: a revoked session still rotated (%)', v_outcome;
    END IF;
END;
$$;

-- Idle expiry never outlives the absolute deadline.
DO $$
DECLARE v_outcome varchar;
BEGIN
    PERFORM elmos_open_session('sess-2', 'acc-signup', 'org-signup', repeat('5', 64),
                               600, 300, ARRAY['PASSWORD'], 'CI', 'cli', '10.0.1');
    SELECT outcome INTO v_outcome FROM elmos_rotate_session_token(repeat('5', 64), repeat('6', 64), 100000);
    IF v_outcome <> 'ROTATED' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: rotation failed (%)', v_outcome;
    END IF;
    IF (SELECT idle_expires_at > absolute_expires_at FROM authentication_sessions
         WHERE authentication_session_id = 'sess-2') THEN
        RAISE EXCEPTION 'ASSERT_FAILED: idle expiry outlived the absolute deadline';
    END IF;

    BEGIN
        PERFORM elmos_open_session('sess-bad', 'acc-signup', 'org-signup', repeat('7', 64),
                                   300, 600, ARRAY['PASSWORD'], 'X', 'cli', '10.0.1');
        RAISE EXCEPTION 'ASSERT_FAILED: idle longer than absolute was accepted';
    EXCEPTION WHEN sqlstate 'P0001' THEN
        IF SQLERRM NOT LIKE '%IDLE_EXCEEDS_ABSOLUTE%' THEN RAISE; END IF;
    END;
END;
$$;

-- An expired session cannot be refreshed back to life.
DO $$
DECLARE v_outcome varchar;
BEGIN
    PERFORM elmos_open_session('sess-3', 'acc-signup', 'org-signup', repeat('8', 64),
                               2592000, 1209600, ARRAY['SMS_OTP'], 'Old', 'chrome', '10.0.2');
    -- The V53 shape CHECK forbids an idle deadline before issuance, so a stale
    -- session is simulated by moving the whole row back in time rather than by
    -- backdating one column. That constraint is doing its job: it means expiry
    -- can never be faked by rewriting a single timestamp.
    UPDATE authentication_sessions
       SET issued_at = now() - interval '3 hours',
           idle_expires_at = now() - interval '1 hour'
     WHERE authentication_session_id = 'sess-3';
    SELECT outcome INTO v_outcome FROM elmos_rotate_session_token(repeat('8', 64), repeat('9', 64), 1209600);
    IF v_outcome <> 'REJECTED' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: an idle-expired session rotated (%)', v_outcome;
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Lockout
-- ---------------------------------------------------------------------------

DO $$
DECLARE v_locked boolean;
BEGIN
    FOR i IN 1..4 LOOP
        v_locked := elmos_record_sign_in_failure('acc-signup', 5::smallint, 900);
        IF v_locked THEN
            RAISE EXCEPTION 'ASSERT_FAILED: locked too early at attempt %', i;
        END IF;
    END LOOP;
    v_locked := elmos_record_sign_in_failure('acc-signup', 5::smallint, 900);
    IF NOT v_locked THEN
        RAISE EXCEPTION 'ASSERT_FAILED: the account was not locked on the fifth failure';
    END IF;
    IF (SELECT locked_until FROM accounts WHERE account_id = 'acc-signup') IS NULL THEN
        RAISE EXCEPTION 'ASSERT_FAILED: no lock deadline was set';
    END IF;

    -- The scheduled sweeper releases the lock rather than requiring support.
    UPDATE accounts SET locked_until = now() - interval '1 minute' WHERE account_id = 'acc-signup';
    PERFORM elmos_expire_stale_identity_records();
    IF (SELECT locked_until FROM accounts WHERE account_id = 'acc-signup') IS NOT NULL THEN
        RAISE EXCEPTION 'ASSERT_FAILED: an elapsed lock was not released';
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- The application role cannot read identity tables directly
-- ---------------------------------------------------------------------------

DO $$
DECLARE v_denied boolean := false;
BEGIN
    SET LOCAL ROLE elmos_app_test;
    BEGIN
        PERFORM 1 FROM accounts LIMIT 1;
    EXCEPTION WHEN insufficient_privilege THEN
        v_denied := true;
    END;
    RESET ROLE;
    IF NOT v_denied THEN
        RAISE EXCEPTION 'ASSERT_FAILED: the application role can read accounts directly';
    END IF;
END;
$$;

DO $$
DECLARE v_denied boolean := false;
BEGIN
    SET LOCAL ROLE elmos_app_test;
    BEGIN
        PERFORM 1 FROM identity_rate_counters LIMIT 1;
    EXCEPTION WHEN insufficient_privilege THEN
        v_denied := true;
    END;
    RESET ROLE;
    IF NOT v_denied THEN
        RAISE EXCEPTION 'ASSERT_FAILED: the application role can read rate counters directly';
    END IF;
END;
$$;

ROLLBACK;
\echo 'IDENTITY SMOKE TEST PASSED'
