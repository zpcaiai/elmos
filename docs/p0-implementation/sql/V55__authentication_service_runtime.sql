-- ELMOS V55: runtime support for the self-service authentication service.
--
-- V53 defined the identity aggregates. V55 adds the four things the running
-- service needs and V53 deliberately left open:
--
--   1. Refresh-token rotation with theft detection.
--   2. A delivery outbox for SMS and email, so a code that was never delivered is
--      distinguishable from one the user ignored.
--   3. Durable rate-limit counters, because per-process counters do not survive a
--      restart and do not exist at all across replicas.
--   4. One atomic sign-up completion, closing the seam where an account could be
--      activated and an organization provisioned without an entitlement - which
--      leaves a brand-new user unable to run anything and reading
--      ELMOS_EXECUTION_NO_ACTIVE_ENTITLEMENT.

-- ---------------------------------------------------------------------------
-- 1. Password hashing: allow an algorithm the platform can actually compute
-- ---------------------------------------------------------------------------
-- V53 pinned ARGON2ID. There is no Argon2 in the JDK, so a deployment without the
-- optional dependency cannot store a password at all. PBKDF2-HMAC-SHA256 is in the
-- platform and is an acceptable fallback; Argon2id remains preferred.

ALTER TABLE accounts DROP CONSTRAINT accounts_password_shape;
ALTER TABLE accounts
    ADD CONSTRAINT accounts_password_shape CHECK (
        password_hash IS NULL OR (
            password_algorithm IN ('ARGON2ID', 'PBKDF2_SHA256')
            AND password_updated_at IS NOT NULL
        )
    );

COMMENT ON COLUMN accounts.password_algorithm IS
    'ARGON2ID preferred. PBKDF2_SHA256 is the platform fallback so a deployment without the optional Argon2 dependency can still store credentials rather than silently refusing sign-up.';

-- ---------------------------------------------------------------------------
-- 2. Refresh-token rotation and reuse detection
-- ---------------------------------------------------------------------------

ALTER TABLE authentication_sessions
    ADD COLUMN token_generation integer NOT NULL DEFAULT 0,
    ADD COLUMN compromised_at timestamptz,
    ADD CONSTRAINT authentication_sessions_generation_range
        CHECK (token_generation >= 0 AND token_generation <= 100000);

/*
 * Every refresh token ever issued for a session, and when it was superseded.
 *
 * This is what makes stolen-token detection possible. Rotation alone is not
 * enough: if an attacker copies a refresh token and the legitimate client rotates
 * first, the attacker's copy simply fails and nobody learns anything. By keeping
 * superseded hashes, a presentation of an already-rotated token is recognised as
 * proof that two parties hold the same secret - and the whole session is revoked
 * rather than just that request refused.
 */
CREATE TABLE authentication_token_generations (
    token_generation_id varchar(96) PRIMARY KEY,
    authentication_session_id varchar(96) NOT NULL
        REFERENCES authentication_sessions(authentication_session_id),
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    generation integer NOT NULL,
    refresh_token_sha256 varchar(64) NOT NULL CHECK (refresh_token_sha256 ~ '^[0-9a-f]{64}$'),
    issued_at timestamptz NOT NULL DEFAULT now(),
    superseded_at timestamptz,
    UNIQUE (authentication_session_id, generation),
    CONSTRAINT authentication_token_generation_range CHECK (generation >= 0)
);

CREATE UNIQUE INDEX authentication_token_generations_hash_uq
    ON authentication_token_generations (refresh_token_sha256);
CREATE INDEX authentication_token_generations_session_idx
    ON authentication_token_generations (authentication_session_id, generation DESC);

CREATE TRIGGER authentication_token_generations_no_delete
BEFORE DELETE ON authentication_token_generations
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

-- ---------------------------------------------------------------------------
-- 3. Delivery outbox
-- ---------------------------------------------------------------------------

CREATE TABLE identity_message_deliveries (
    delivery_id varchar(96) PRIMARY KEY,
    challenge_id varchar(96) REFERENCES account_verification_challenges(challenge_id),
    channel varchar(16) NOT NULL,
    purpose varchar(32) NOT NULL,
    -- Keyed hash, never the address. An undelivered message must not leave a
    -- readable phone number behind for someone who never completed sign-up.
    destination_hmac varchar(64) NOT NULL CHECK (destination_hmac ~ '^[0-9a-f]{64}$'),
    provider varchar(32) NOT NULL,
    provider_template_id varchar(96),
    provider_message_ref varchar(255),
    delivery_state varchar(24) NOT NULL DEFAULT 'PENDING',
    attempt smallint NOT NULL DEFAULT 0,
    queued_at timestamptz NOT NULL DEFAULT now(),
    sent_at timestamptz,
    settled_at timestamptz,
    failure_code varchar(96),
    CONSTRAINT identity_delivery_channel CHECK (channel IN ('EMAIL', 'SMS')),
    CONSTRAINT identity_delivery_state CHECK (
        delivery_state IN ('PENDING', 'SENT', 'DELIVERED', 'FAILED', 'ABANDONED')
    ),
    CONSTRAINT identity_delivery_attempt CHECK (attempt >= 0 AND attempt <= 5),
    -- A provider that is not configured must not look like a successful send.
    CONSTRAINT identity_delivery_sent_shape CHECK (
        delivery_state NOT IN ('SENT', 'DELIVERED') OR (sent_at IS NOT NULL AND provider_message_ref IS NOT NULL)
    )
);

CREATE INDEX identity_deliveries_pending_idx
    ON identity_message_deliveries (queued_at)
    WHERE delivery_state = 'PENDING';
CREATE INDEX identity_deliveries_destination_idx
    ON identity_message_deliveries (destination_hmac, queued_at DESC);

COMMENT ON TABLE identity_message_deliveries IS
    'Outbox for verification codes. Records that a message was attempted and what the provider said, never the code and never the address. Without it, "the SMS never arrived" is unanswerable.';

CREATE TABLE identity_message_providers (
    provider_id varchar(32) PRIMARY KEY,
    channel varchar(16) NOT NULL,
    provider_state varchar(24) NOT NULL DEFAULT 'NOT_CONFIGURED',
    credential_reference varchar(160),
    -- Mainland-China SMS requires a filed signature and template per purpose.
    signature_name varchar(96),
    filing_reference varchar(96),
    daily_send_cap integer NOT NULL DEFAULT 100000,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT identity_provider_channel CHECK (channel IN ('EMAIL', 'SMS')),
    CONSTRAINT identity_provider_state CHECK (
        provider_state IN ('NOT_CONFIGURED', 'ACTIVE', 'SUSPENDED')
    ),
    CONSTRAINT identity_provider_active_shape CHECK (
        provider_state <> 'ACTIVE' OR (
            credential_reference IS NOT NULL
            AND (channel <> 'SMS' OR (signature_name IS NOT NULL AND filing_reference IS NOT NULL))
        )
    )
);

INSERT INTO identity_message_providers (provider_id, channel, provider_state) VALUES
    ('sms-primary', 'SMS', 'NOT_CONFIGURED'),
    ('email-primary', 'EMAIL', 'NOT_CONFIGURED');

COMMENT ON CONSTRAINT identity_provider_active_shape ON identity_message_providers IS
    'An SMS provider cannot go ACTIVE without a filed signature and filing reference. Sending unfiled template SMS in mainland China gets the whole signature suspended, not just the one message.';

CREATE TABLE identity_message_templates (
    template_id varchar(96) PRIMARY KEY,
    provider_id varchar(32) NOT NULL REFERENCES identity_message_providers(provider_id),
    purpose varchar(32) NOT NULL,
    locale varchar(16) NOT NULL DEFAULT 'zh-CN',
    provider_template_code varchar(96) NOT NULL,
    filing_state varchar(24) NOT NULL DEFAULT 'PENDING',
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider_id, purpose, locale),
    CONSTRAINT identity_template_purpose CHECK (
        purpose IN ('SIGN_UP', 'SIGN_IN', 'ADD_CHANNEL', 'PASSWORD_RESET', 'DELETE_ACCOUNT', 'INVITATION')
    ),
    CONSTRAINT identity_template_filing CHECK (filing_state IN ('PENDING', 'APPROVED', 'REJECTED'))
);

-- ---------------------------------------------------------------------------
-- 4. Durable rate limiting
-- ---------------------------------------------------------------------------

CREATE TABLE identity_rate_counters (
    counter_scope varchar(24) NOT NULL,
    counter_key varchar(64) NOT NULL,
    window_start timestamptz NOT NULL,
    window_seconds integer NOT NULL,
    hits integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (counter_scope, counter_key, window_start, window_seconds),
    CONSTRAINT identity_rate_scope CHECK (
        counter_scope IN ('DESTINATION', 'CLIENT_PREFIX', 'ACCOUNT')
    ),
    CONSTRAINT identity_rate_window CHECK (window_seconds BETWEEN 1 AND 86400),
    CONSTRAINT identity_rate_hits CHECK (hits >= 0)
);

CREATE INDEX identity_rate_counters_expiry
    ON identity_rate_counters (window_start);

COMMENT ON TABLE identity_rate_counters IS
    'Fixed-window counters in the database rather than in process memory: an in-memory limiter resets on deploy and does not exist across replicas, which is precisely when an attacker benefits.';

CREATE OR REPLACE FUNCTION elmos_consume_rate_budget(
    p_scope varchar,
    p_key varchar,
    p_window_seconds integer,
    p_limit integer
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_window timestamptz;
    v_hits integer;
BEGIN
    -- Align to a fixed window so concurrent callers share the same bucket.
    v_window := to_timestamp(floor(extract(epoch from now()) / p_window_seconds) * p_window_seconds);

    INSERT INTO identity_rate_counters (counter_scope, counter_key, window_start, window_seconds, hits)
    VALUES (p_scope, p_key, v_window, p_window_seconds, 1)
    ON CONFLICT (counter_scope, counter_key, window_start, window_seconds) DO UPDATE
        SET hits = identity_rate_counters.hits + 1, updated_at = now()
    RETURNING hits INTO v_hits;

    RETURN v_hits <= p_limit;
END;
$$;

-- ---------------------------------------------------------------------------
-- 5. Challenge issuance and verification
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_issue_verification_challenge(
    p_challenge_id varchar,
    p_channel varchar,
    p_destination_hmac varchar,
    p_purpose varchar,
    p_code_sha256 varchar,
    p_ttl_seconds integer,
    p_client_prefix varchar
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_provider identity_message_providers%ROWTYPE;
BEGIN
    IF p_ttl_seconds < 60 OR p_ttl_seconds > 900 THEN
        RAISE EXCEPTION 'ELMOS_CHALLENGE_TTL_INVALID';
    END IF;

    -- Three independent limits. The per-destination minute window stops the
    -- "resend" button becoming an SMS cannon aimed at one person; the daily window
    -- caps the spend on any single number; the client window stops one source
    -- walking a range of numbers.
    IF NOT elmos_consume_rate_budget('DESTINATION', p_destination_hmac, 60, 1) THEN
        RAISE EXCEPTION 'ELMOS_CHALLENGE_TOO_FREQUENT';
    END IF;
    IF NOT elmos_consume_rate_budget('DESTINATION', p_destination_hmac, 86400, 10) THEN
        RAISE EXCEPTION 'ELMOS_CHALLENGE_DAILY_LIMIT';
    END IF;
    IF p_client_prefix IS NOT NULL
       AND NOT elmos_consume_rate_budget('CLIENT_PREFIX', p_client_prefix, 3600, 30) THEN
        RAISE EXCEPTION 'ELMOS_CHALLENGE_CLIENT_LIMIT';
    END IF;

    SELECT * INTO v_provider FROM identity_message_providers
     WHERE channel = p_channel AND provider_state = 'ACTIVE'
     ORDER BY provider_id LIMIT 1;
    IF NOT FOUND THEN
        -- Fail closed: issuing a code nobody can deliver strands the user on a
        -- screen asking for it.
        RAISE EXCEPTION 'ELMOS_MESSAGE_PROVIDER_NOT_CONFIGURED';
    END IF;

    -- Any earlier live challenge for the same destination and purpose is retired,
    -- so only the newest code works.
    UPDATE account_verification_challenges
       SET invalidated_at = now()
     WHERE destination_hmac = p_destination_hmac
       AND purpose = p_purpose
       AND consumed_at IS NULL
       AND invalidated_at IS NULL;

    INSERT INTO account_verification_challenges (
        challenge_id, channel, destination_hmac, purpose, code_hash, expires_at
    ) VALUES (
        p_challenge_id, p_channel, p_destination_hmac, p_purpose, p_code_sha256,
        now() + make_interval(secs => p_ttl_seconds)
    );

    INSERT INTO identity_message_deliveries (
        delivery_id, challenge_id, channel, purpose, destination_hmac, provider
    ) VALUES (
        'dlv-' || md5(p_challenge_id), p_challenge_id, p_channel, p_purpose,
        p_destination_hmac, v_provider.provider_id
    );

    RETURN true;
END;
$$;

/*
 * Verifies a code.
 *
 * Returns the challenge id on success and NULL on every failure - wrong code,
 * expired, already used, unknown destination. The caller therefore cannot tell
 * "no such account" from "wrong code", which is what keeps the endpoint from
 * being an account-enumeration oracle.
 */
CREATE OR REPLACE FUNCTION elmos_consume_verification_challenge(
    p_destination_hmac varchar,
    p_purpose varchar,
    p_code_sha256 varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_challenge account_verification_challenges%ROWTYPE;
BEGIN
    SELECT * INTO v_challenge FROM account_verification_challenges
     WHERE destination_hmac = p_destination_hmac
       AND purpose = p_purpose
       AND consumed_at IS NULL
       AND invalidated_at IS NULL
     ORDER BY issued_at DESC
     LIMIT 1
     FOR UPDATE;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    IF v_challenge.expires_at < now() THEN
        UPDATE account_verification_challenges SET invalidated_at = now()
         WHERE challenge_id = v_challenge.challenge_id;
        RETURN NULL;
    END IF;

    IF v_challenge.attempt_count >= v_challenge.max_attempts THEN
        UPDATE account_verification_challenges SET invalidated_at = now()
         WHERE challenge_id = v_challenge.challenge_id;
        RETURN NULL;
    END IF;

    IF v_challenge.code_hash <> p_code_sha256 THEN
        -- Count the attempt, then burn the challenge once the budget is gone.
        UPDATE account_verification_challenges
           SET attempt_count = attempt_count + 1,
               invalidated_at = CASE WHEN attempt_count + 1 >= max_attempts THEN now() ELSE NULL END
         WHERE challenge_id = v_challenge.challenge_id;
        RETURN NULL;
    END IF;

    UPDATE account_verification_challenges SET consumed_at = now()
     WHERE challenge_id = v_challenge.challenge_id;
    RETURN v_challenge.challenge_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- 6. Sign-up completion, in one transaction
-- ---------------------------------------------------------------------------

/*
 * Activates the account, creates the organization, provisions the owner identity
 * and grants the trial - atomically.
 *
 * The trial grant is the point. Provisioning an organization without an
 * entitlement produces a user who can log in, see the product, press the button
 * and receive ELMOS_EXECUTION_NO_ACTIVE_ENTITLEMENT, because
 * elmos_execution_concurrency_limit() returns 0 with no active subscription.
 * Keeping the two steps apart is how that ships.
 */
CREATE OR REPLACE FUNCTION elmos_complete_signup(
    p_account_id varchar,
    p_organization_id varchar,
    p_display_name varchar,
    p_owner_actor_id varchar,
    p_verified_subject_hash varchar,
    p_data_region varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_account accounts%ROWTYPE;
BEGIN
    SELECT * INTO v_account FROM accounts WHERE account_id = p_account_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_ACCOUNT_UNKNOWN';
    END IF;
    IF v_account.email_verified_at IS NULL AND v_account.phone_verified_at IS NULL THEN
        RAISE EXCEPTION 'ELMOS_ACCOUNT_NO_VERIFIED_CHANNEL';
    END IF;

    UPDATE accounts SET status = 'ACTIVE', updated_at = now()
     WHERE account_id = p_account_id AND status <> 'ACTIVE';

    PERFORM elmos_provision_organization(
        p_organization_id, p_display_name, p_account_id, p_owner_actor_id, p_data_region);

    -- elmos_grant_trial reads the tenant from the RLS context.
    PERFORM set_config('app.organization_id', p_organization_id, true);
    PERFORM elmos_grant_trial(
        'trial-' || p_organization_id,
        'sub-' || p_organization_id,
        'quota-' || p_organization_id,
        p_owner_actor_id,
        p_verified_subject_hash,
        'signup:' || p_organization_id);

    -- A brand-new organization that cannot run anything is a failed sign-up, so
    -- assert the entitlement actually landed rather than trusting the sequence.
    IF elmos_execution_concurrency_limit(p_organization_id) < 1 THEN
        RAISE EXCEPTION 'ELMOS_SIGNUP_ENTITLEMENT_MISSING';
    END IF;

    RETURN p_organization_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- 7. Session issuance, rotation and reuse detection
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_open_session(
    p_session_id varchar,
    p_account_id varchar,
    p_organization_id varchar,
    p_refresh_token_sha256 varchar,
    p_absolute_seconds integer,
    p_idle_seconds integer,
    p_amr text[],
    p_device_label varchar,
    p_client_family varchar,
    p_ip_prefix varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF p_idle_seconds > p_absolute_seconds THEN
        RAISE EXCEPTION 'ELMOS_SESSION_IDLE_EXCEEDS_ABSOLUTE';
    END IF;

    INSERT INTO authentication_sessions (
        authentication_session_id, organization_id, schema_version, status,
        idempotency_key, payload, account_ref, session_state, refresh_token_sha256,
        issued_at, absolute_expires_at, idle_expires_at, amr, device_label,
        client_family, ip_prefix, active_organization_ref, token_generation
    ) VALUES (
        p_session_id, p_organization_id, '2.0', 'ACTIVE',
        'session:' || p_session_id, '{}'::jsonb, p_account_id, 'ACTIVE',
        p_refresh_token_sha256, now(),
        now() + make_interval(secs => p_absolute_seconds),
        now() + make_interval(secs => p_idle_seconds),
        p_amr, p_device_label, p_client_family, p_ip_prefix, p_organization_id, 0
    );

    INSERT INTO authentication_token_generations (
        token_generation_id, authentication_session_id, organization_id,
        generation, refresh_token_sha256
    ) VALUES (
        p_session_id || ':0', p_session_id, p_organization_id, 0, p_refresh_token_sha256
    );

    RETURN p_session_id;
END;
$$;

/*
 * Rotates a refresh token, or detects that the old one was stolen.
 *
 * Three outcomes:
 *   'ROTATED'    - the current token was presented; a new one is now current.
 *   'REUSED'     - a superseded token was presented. Two parties hold the same
 *                  secret, so the entire session is revoked, not just this call.
 *   'REJECTED'   - unknown, expired or already revoked.
 */
CREATE OR REPLACE FUNCTION elmos_rotate_session_token(
    p_presented_sha256 varchar,
    p_next_sha256 varchar,
    p_idle_seconds integer
) RETURNS TABLE (outcome varchar, session_id varchar, account_id varchar, organization_id varchar)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_generation authentication_token_generations%ROWTYPE;
    v_session authentication_sessions%ROWTYPE;
BEGIN
    SELECT * INTO v_generation FROM authentication_token_generations
     WHERE refresh_token_sha256 = p_presented_sha256;
    IF NOT FOUND THEN
        outcome := 'REJECTED'; RETURN NEXT; RETURN;
    END IF;

    SELECT * INTO v_session FROM authentication_sessions
     WHERE authentication_session_id = v_generation.authentication_session_id FOR UPDATE;

    IF v_generation.superseded_at IS NOT NULL THEN
        -- Replay of a rotated token. The legitimate client and someone else both
        -- have it; end the session for both.
        UPDATE authentication_sessions
           SET session_state = 'REVOKED', revoked_at = now(),
               revocation_code = 'REFRESH_TOKEN_REUSED', compromised_at = now()
         WHERE authentication_session_id = v_session.authentication_session_id
           AND session_state = 'ACTIVE';

        INSERT INTO account_security_events (
            security_event_id, account_id, event_type, outcome, failure_code
        ) VALUES (
            'sec-' || md5(v_session.authentication_session_id || ':reuse:' || p_presented_sha256),
            v_session.account_ref, 'SESSION_REVOKED', 'BLOCKED', 'REFRESH_TOKEN_REUSED'
        ) ON CONFLICT (security_event_id) DO NOTHING;

        outcome := 'REUSED';
        session_id := v_session.authentication_session_id;
        account_id := v_session.account_ref;
        organization_id := v_session.organization_id;
        RETURN NEXT; RETURN;
    END IF;

    IF v_session.session_state <> 'ACTIVE'
       OR v_session.absolute_expires_at < now()
       OR v_session.idle_expires_at < now() THEN
        UPDATE authentication_sessions SET session_state = 'EXPIRED'
         WHERE authentication_session_id = v_session.authentication_session_id
           AND session_state = 'ACTIVE';
        outcome := 'REJECTED'; RETURN NEXT; RETURN;
    END IF;

    UPDATE authentication_token_generations SET superseded_at = now()
     WHERE token_generation_id = v_generation.token_generation_id;

    UPDATE authentication_sessions
       SET refresh_token_sha256 = p_next_sha256,
           token_generation = token_generation + 1,
           idle_expires_at = least(
               now() + make_interval(secs => p_idle_seconds),
               absolute_expires_at)
     WHERE authentication_session_id = v_session.authentication_session_id;

    INSERT INTO authentication_token_generations (
        token_generation_id, authentication_session_id, organization_id,
        generation, refresh_token_sha256
    ) VALUES (
        v_session.authentication_session_id || ':' || (v_session.token_generation + 1),
        v_session.authentication_session_id, v_session.organization_id,
        v_session.token_generation + 1, p_next_sha256
    );

    outcome := 'ROTATED';
    session_id := v_session.authentication_session_id;
    account_id := v_session.account_ref;
    organization_id := v_session.organization_id;
    RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_record_sign_in_failure(
    p_account_id varchar,
    p_max_failures smallint,
    p_lock_seconds integer
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_count smallint;
BEGIN
    UPDATE accounts
       SET failed_sign_in_count = failed_sign_in_count + 1,
           locked_until = CASE
               WHEN failed_sign_in_count + 1 >= p_max_failures
               THEN now() + make_interval(secs => p_lock_seconds)
               ELSE locked_until END
     WHERE account_id = p_account_id
    RETURNING failed_sign_in_count INTO v_count;

    RETURN coalesce(v_count, 0) >= p_max_failures;
END;
$$;

-- ---------------------------------------------------------------------------
-- 8. Row level security and grants
-- ---------------------------------------------------------------------------

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['authentication_token_generations']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name
        );
    END LOOP;
END;
$$;

REVOKE ALL ON identity_message_deliveries FROM PUBLIC;
REVOKE ALL ON identity_message_providers FROM PUBLIC;
REVOKE ALL ON identity_message_templates FROM PUBLIC;
REVOKE ALL ON identity_rate_counters FROM PUBLIC;

COMMENT ON TABLE identity_rate_counters IS
    'Not tenant isolated: rate limiting happens before any organization is known. It holds only keyed hashes and counts.';

DO $$
DECLARE v_function record;
BEGIN
    FOR v_function IN
        SELECT p.oid::regprocedure AS signature
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND p.proname IN (
               'elmos_consume_rate_budget',
               'elmos_issue_verification_challenge',
               'elmos_consume_verification_challenge',
               'elmos_complete_signup',
               'elmos_open_session',
               'elmos_rotate_session_token',
               'elmos_record_sign_in_failure'
           )
    LOOP
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', v_function.signature);
    END LOOP;
END;
$$;
