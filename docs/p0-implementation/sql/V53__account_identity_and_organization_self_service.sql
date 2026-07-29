-- ELMOS V53: global account identity and organization self-service.
--
-- Why this migration exists
-- -------------------------
-- Before V53 a tenant existed only if an external IdP put organization_id into
-- the token claims (apps/web-console/app/lib/server/accountSession.ts), and the
-- Spring path additionally trusted a single process-wide organization through
-- ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID. There was no way for a person to
-- sign up, create an organization, or invite a colleague.
--
-- V9 modelled user_identities / organization_memberships / authentication_sessions
-- as generic payload-jsonb placeholders. V53 keeps those authoritative aggregate
-- names and gives them real columns, using the V49 ADD COLUMN + shape CHECK
-- convention so historical rows stay valid.
--
-- The one genuinely new aggregate is `accounts`. A person exists before any
-- organization and may belong to several, so an account cannot be tenant scoped.
-- `accounts` is therefore deliberately NOT row-level-security isolated; it is
-- reachable only through SECURITY DEFINER functions and an application role that
-- never serves tenant queries. Everything org-scoped stays under RLS.
--
-- Deployment target for this milestone: mainland-China self-service SaaS, CNY.
-- Primary sign-in is mobile number OTP, then email, then WeChat. Enterprise
-- OIDC/SAML remains supported but is optional, not a prerequisite.

-- ---------------------------------------------------------------------------
-- 1. Global account
-- ---------------------------------------------------------------------------

CREATE TABLE accounts (
    account_id varchar(96) PRIMARY KEY,
    status varchar(32) NOT NULL DEFAULT 'PENDING_VERIFICATION',
    display_name varchar(128) NOT NULL,
    locale varchar(16) NOT NULL DEFAULT 'zh-CN',
    -- Email is stored in the clear because delivery and invitation matching
    -- require it. It is personal information: it participates in export and
    -- erasure, and it is never written to telemetry or audit metadata.
    primary_email varchar(320),
    email_verified_at timestamptz,
    -- Mobile numbers are personal information under PIPL and are not stored in
    -- the clear. phone_lookup_hmac is a keyed hash (pepper held in KMS) that
    -- supports exact-match sign-in; phone_last4 supports human recognition;
    -- phone_cipher_ref points at the envelope-encrypted value.
    phone_lookup_hmac varchar(64) CHECK (phone_lookup_hmac IS NULL OR phone_lookup_hmac ~ '^[0-9a-f]{64}$'),
    phone_last4 char(4),
    phone_cipher_ref varchar(160),
    phone_verified_at timestamptz,
    password_hash varchar(255),
    password_algorithm varchar(32),
    password_updated_at timestamptz,
    mfa_required boolean NOT NULL DEFAULT false,
    failed_sign_in_count smallint NOT NULL DEFAULT 0,
    locked_until timestamptz,
    last_sign_in_at timestamptz,
    terms_accepted_version varchar(32),
    terms_accepted_at timestamptz,
    deletion_requested_at timestamptz,
    purge_after timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    state_version bigint NOT NULL DEFAULT 0,
    CONSTRAINT accounts_status CHECK (
        status IN ('PENDING_VERIFICATION', 'ACTIVE', 'SUSPENDED', 'DELETION_REQUESTED', 'PURGED')
    ),
    CONSTRAINT accounts_password_shape CHECK (
        password_hash IS NULL OR (password_algorithm = 'ARGON2ID' AND password_updated_at IS NOT NULL)
    ),
    CONSTRAINT accounts_phone_shape CHECK (
        (phone_lookup_hmac IS NULL AND phone_last4 IS NULL AND phone_cipher_ref IS NULL)
        OR (phone_lookup_hmac IS NOT NULL AND phone_last4 IS NOT NULL AND phone_cipher_ref IS NOT NULL)
    ),
    -- An ACTIVE account must have at least one verified reachable identifier.
    CONSTRAINT accounts_active_requires_verified_channel CHECK (
        status <> 'ACTIVE' OR email_verified_at IS NOT NULL OR phone_verified_at IS NOT NULL
    ),
    CONSTRAINT accounts_deletion_shape CHECK (
        deletion_requested_at IS NULL OR purge_after > deletion_requested_at
    ),
    CONSTRAINT accounts_failed_sign_in_range CHECK (failed_sign_in_count BETWEEN 0 AND 100)
);

CREATE UNIQUE INDEX accounts_primary_email_uq
    ON accounts (lower(primary_email))
    WHERE primary_email IS NOT NULL AND status <> 'PURGED';
CREATE UNIQUE INDEX accounts_phone_uq
    ON accounts (phone_lookup_hmac)
    WHERE phone_lookup_hmac IS NOT NULL AND status <> 'PURGED';
CREATE INDEX accounts_purge_due_idx ON accounts (purge_after) WHERE purge_after IS NOT NULL;

COMMENT ON TABLE accounts IS
    'Platform-global person record. Deliberately not tenant isolated: an account exists before any organization and may hold memberships in several. All org-scoped data about a person lives in organization_memberships and user_identities, which are RLS isolated.';
COMMENT ON COLUMN accounts.phone_lookup_hmac IS
    'HMAC-SHA256(pepper, E.164). The pepper lives in KMS and never in the database, so a database copy alone cannot enumerate mobile numbers.';

CREATE TABLE account_credentials (
    credential_id varchar(96) PRIMARY KEY,
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    provider varchar(32) NOT NULL,
    provider_issuer varchar(255) NOT NULL DEFAULT 'elmos',
    provider_subject varchar(255) NOT NULL,
    linked_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT account_credentials_provider CHECK (
        provider IN ('PASSWORD', 'EMAIL_OTP', 'SMS_OTP', 'WECHAT', 'GITHUB', 'GITEE', 'ENTERPRISE_OIDC', 'ENTERPRISE_SAML')
    ),
    CONSTRAINT account_credentials_metadata_object CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE UNIQUE INDEX account_credentials_subject_uq
    ON account_credentials (provider, provider_issuer, provider_subject)
    WHERE revoked_at IS NULL;
CREATE INDEX account_credentials_account_idx ON account_credentials (account_id);

COMMENT ON COLUMN account_credentials.metadata IS
    'Non-sensitive linkage facts only (for example WeChat unionid presence flag). Access tokens, refresh tokens, openid secrets and profile payloads are prohibited.';

CREATE TABLE account_verification_challenges (
    challenge_id varchar(96) PRIMARY KEY,
    account_id varchar(96) REFERENCES accounts(account_id),
    channel varchar(16) NOT NULL,
    -- The destination is stored as a keyed hash so an unclaimed challenge cannot
    -- leak a phone number or address that never completed sign-up.
    destination_hmac varchar(64) NOT NULL CHECK (destination_hmac ~ '^[0-9a-f]{64}$'),
    purpose varchar(32) NOT NULL,
    code_hash varchar(64) NOT NULL CHECK (code_hash ~ '^[0-9a-f]{64}$'),
    attempt_count smallint NOT NULL DEFAULT 0,
    max_attempts smallint NOT NULL DEFAULT 5,
    issued_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    invalidated_at timestamptz,
    CONSTRAINT account_challenges_channel CHECK (channel IN ('EMAIL', 'SMS')),
    CONSTRAINT account_challenges_purpose CHECK (
        purpose IN ('SIGN_UP', 'SIGN_IN', 'ADD_CHANNEL', 'PASSWORD_RESET', 'DELETE_ACCOUNT')
    ),
    CONSTRAINT account_challenges_expiry CHECK (expires_at > issued_at),
    CONSTRAINT account_challenges_attempts CHECK (attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10)
);

CREATE INDEX account_challenges_destination_idx
    ON account_verification_challenges (destination_hmac, issued_at DESC);
CREATE INDEX account_challenges_expiry_idx ON account_verification_challenges (expires_at);

COMMENT ON TABLE account_verification_challenges IS
    'One-time codes for email and SMS. Only the SHA-256 of the code is stored; the code itself exists solely in the delivered message. Rate limiting is enforced by elmos_issue_verification_challenge().';

CREATE TABLE account_security_events (
    security_event_id varchar(96) PRIMARY KEY,
    account_id varchar(96) REFERENCES accounts(account_id),
    event_type varchar(48) NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    -- Privacy-safe context only, matching the V50/V51 telemetry rule: no raw IP,
    -- no raw user agent, no request bodies.
    ip_prefix varchar(64),
    client_family varchar(48),
    outcome varchar(16) NOT NULL,
    failure_code varchar(96),
    CONSTRAINT account_security_event_type CHECK (
        event_type IN (
            'SIGN_UP', 'SIGN_IN', 'SIGN_OUT', 'CHALLENGE_ISSUED', 'CHALLENGE_FAILED',
            'PASSWORD_CHANGED', 'MFA_ENROLLED', 'ACCOUNT_LOCKED', 'ACCOUNT_UNLOCKED',
            'CREDENTIAL_LINKED', 'CREDENTIAL_REVOKED', 'SESSION_REVOKED', 'DELETION_REQUESTED'
        )
    ),
    CONSTRAINT account_security_event_outcome CHECK (outcome IN ('SUCCESS', 'FAILURE', 'BLOCKED'))
);

CREATE INDEX account_security_events_account_idx
    ON account_security_events (account_id, occurred_at DESC);

CREATE TRIGGER account_security_events_append_only
BEFORE UPDATE OR DELETE ON account_security_events
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

-- ---------------------------------------------------------------------------
-- 2. Typed sessions (ALTER of the V9 placeholder)
-- ---------------------------------------------------------------------------

ALTER TABLE authentication_sessions
    ADD COLUMN account_ref varchar(96) REFERENCES accounts(account_id),
    ADD COLUMN session_state varchar(24),
    ADD COLUMN refresh_token_sha256 varchar(64)
        CHECK (refresh_token_sha256 IS NULL OR refresh_token_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN issued_at timestamptz,
    ADD COLUMN absolute_expires_at timestamptz,
    ADD COLUMN idle_expires_at timestamptz,
    ADD COLUMN revoked_at timestamptz,
    ADD COLUMN revocation_code varchar(96),
    ADD COLUMN device_label varchar(96),
    ADD COLUMN client_family varchar(48),
    ADD COLUMN ip_prefix varchar(64),
    ADD COLUMN active_organization_ref varchar(96) REFERENCES organizations(organization_id),
    ADD COLUMN amr text[],
    ADD CONSTRAINT authentication_sessions_shape CHECK (
        session_state IS NULL OR (
            session_state IN ('ACTIVE', 'REVOKED', 'EXPIRED')
            AND account_ref IS NOT NULL
            AND refresh_token_sha256 IS NOT NULL
            AND issued_at IS NOT NULL
            AND absolute_expires_at > issued_at
            AND idle_expires_at > issued_at
        )
    );

CREATE UNIQUE INDEX authentication_sessions_refresh_uq
    ON authentication_sessions (refresh_token_sha256)
    WHERE refresh_token_sha256 IS NOT NULL;
CREATE INDEX authentication_sessions_account_idx
    ON authentication_sessions (account_ref, session_state, idle_expires_at DESC)
    WHERE account_ref IS NOT NULL;

COMMENT ON COLUMN authentication_sessions.amr IS
    'Authentication methods actually used for this session (SMS_OTP, PASSWORD, WECHAT, MFA_TOTP...). Step-up policies read this instead of re-deriving trust from the token.';

-- ---------------------------------------------------------------------------
-- 3. Typed membership (ALTER of the V9 placeholder) - tenant isolated
-- ---------------------------------------------------------------------------

ALTER TABLE organization_memberships
    ADD COLUMN account_ref varchar(96) REFERENCES accounts(account_id),
    ADD COLUMN member_role varchar(24),
    ADD COLUMN member_state varchar(24),
    ADD COLUMN invited_by_account_ref varchar(96) REFERENCES accounts(account_id),
    ADD COLUMN joined_at timestamptz,
    ADD COLUMN suspended_at timestamptz,
    ADD COLUMN removed_at timestamptz,
    ADD COLUMN last_active_at timestamptz,
    ADD CONSTRAINT organization_memberships_shape CHECK (
        member_role IS NULL OR (
            member_role IN ('OWNER', 'ADMIN', 'MAINTAINER', 'MEMBER', 'BILLING', 'VIEWER')
            AND member_state IN ('ACTIVE', 'SUSPENDED', 'REMOVED')
            AND account_ref IS NOT NULL
            AND joined_at IS NOT NULL
        )
    );

CREATE UNIQUE INDEX organization_memberships_account_uq
    ON organization_memberships (organization_id, account_ref)
    WHERE account_ref IS NOT NULL AND member_state <> 'REMOVED';
CREATE INDEX organization_memberships_account_idx
    ON organization_memberships (account_ref)
    WHERE account_ref IS NOT NULL;

-- An organization must never lose its last active OWNER. Enforced in the
-- database because the same transition is reachable from the members UI, the
-- admin console, the API and the deletion flow.
CREATE OR REPLACE FUNCTION elmos_guard_last_owner()
RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_owners integer;
BEGIN
    IF OLD.member_role = 'OWNER'
       AND OLD.member_state = 'ACTIVE'
       AND (NEW.member_role IS DISTINCT FROM 'OWNER' OR NEW.member_state IS DISTINCT FROM 'ACTIVE') THEN
        SELECT count(*) INTO v_owners FROM organization_memberships
         WHERE organization_id = OLD.organization_id
           AND member_role = 'OWNER' AND member_state = 'ACTIVE'
           AND organization_membership_id <> OLD.organization_membership_id;
        IF v_owners = 0 THEN
            RAISE EXCEPTION 'ELMOS_ORGANIZATION_LAST_OWNER_PROTECTED';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER organization_memberships_last_owner_guard
BEFORE UPDATE ON organization_memberships
FOR EACH ROW EXECUTE FUNCTION elmos_guard_last_owner();

-- ---------------------------------------------------------------------------
-- 4. Typed per-organization identity projection (ALTER of the V9 placeholder)
-- ---------------------------------------------------------------------------

ALTER TABLE user_identities
    ADD COLUMN account_ref varchar(96) REFERENCES accounts(account_id),
    ADD COLUMN actor_id varchar(128),
    ADD COLUMN source varchar(24),
    ADD COLUMN external_subject varchar(255),
    ADD COLUMN provisioned_at timestamptz,
    ADD COLUMN deprovisioned_at timestamptz,
    ADD CONSTRAINT user_identities_shape CHECK (
        source IS NULL OR (
            source IN ('SELF_SERVICE', 'INVITATION', 'ENTERPRISE_SSO', 'SCIM')
            AND account_ref IS NOT NULL
            AND actor_id IS NOT NULL
            AND provisioned_at IS NOT NULL
        )
    );

CREATE UNIQUE INDEX user_identities_actor_uq
    ON user_identities (organization_id, actor_id)
    WHERE actor_id IS NOT NULL;

COMMENT ON COLUMN user_identities.actor_id IS
    'Stable per-organization actor identifier used by every existing audit, evidence, approval and job record. It is derived once at provisioning and never reused, so a removed member cannot inherit a predecessor audit trail.';

-- ---------------------------------------------------------------------------
-- 5. Invitations - tenant isolated
-- ---------------------------------------------------------------------------

CREATE TABLE organization_invitations (
    invitation_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    channel varchar(16) NOT NULL,
    destination_hmac varchar(64) NOT NULL CHECK (destination_hmac ~ '^[0-9a-f]{64}$'),
    destination_display varchar(160) NOT NULL,
    member_role varchar(24) NOT NULL,
    token_sha256 varchar(64) NOT NULL CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    invited_by_actor_id varchar(128) NOT NULL,
    invitation_state varchar(24) NOT NULL DEFAULT 'PENDING',
    issued_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    accepted_by_account_ref varchar(96) REFERENCES accounts(account_id),
    revoked_at timestamptz,
    revoked_by_actor_id varchar(128),
    CONSTRAINT organization_invitations_channel CHECK (channel IN ('EMAIL', 'SMS')),
    CONSTRAINT organization_invitations_role CHECK (
        member_role IN ('ADMIN', 'MAINTAINER', 'MEMBER', 'BILLING', 'VIEWER')
    ),
    CONSTRAINT organization_invitations_state CHECK (
        invitation_state IN ('PENDING', 'ACCEPTED', 'REVOKED', 'EXPIRED')
    ),
    CONSTRAINT organization_invitations_expiry CHECK (expires_at > issued_at),
    CONSTRAINT organization_invitations_accept_shape CHECK (
        invitation_state <> 'ACCEPTED' OR (accepted_at IS NOT NULL AND accepted_by_account_ref IS NOT NULL)
    )
);

CREATE UNIQUE INDEX organization_invitations_pending_uq
    ON organization_invitations (organization_id, destination_hmac)
    WHERE invitation_state = 'PENDING';
CREATE INDEX organization_invitations_token_idx ON organization_invitations (token_sha256);
CREATE INDEX organization_invitations_org_idx ON organization_invitations (organization_id, invitation_state);

COMMENT ON COLUMN organization_invitations.member_role IS
    'OWNER is intentionally absent. Ownership is transferred through an explicit two-step transfer that both the current and the receiving owner confirm, never by sending an invitation link.';
COMMENT ON COLUMN organization_invitations.destination_display IS
    'Masked form shown in the members list, for example 138****8888 or a***@example.com. The full destination is only used at delivery time.';

-- ---------------------------------------------------------------------------
-- 6. Organization API keys - tenant isolated
-- ---------------------------------------------------------------------------

CREATE TABLE organization_api_keys (
    api_key_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    key_name varchar(96) NOT NULL,
    key_prefix varchar(16) NOT NULL,
    secret_sha256 varchar(64) NOT NULL CHECK (secret_sha256 ~ '^[0-9a-f]{64}$'),
    scopes text[] NOT NULL,
    bound_actor_id varchar(128) NOT NULL,
    created_by_actor_id varchar(128) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    last_used_at timestamptz,
    last_used_ip_prefix varchar(64),
    revoked_at timestamptz,
    revocation_code varchar(96),
    CONSTRAINT organization_api_keys_scopes CHECK (array_length(scopes, 1) BETWEEN 1 AND 24),
    CONSTRAINT organization_api_keys_expiry CHECK (expires_at > created_at),
    -- No non-expiring keys. The maximum lifetime is one year.
    CONSTRAINT organization_api_keys_max_lifetime CHECK (expires_at <= created_at + interval '366 days')
);

CREATE UNIQUE INDEX organization_api_keys_prefix_uq ON organization_api_keys (key_prefix);
CREATE UNIQUE INDEX organization_api_keys_name_uq
    ON organization_api_keys (organization_id, lower(key_name))
    WHERE revoked_at IS NULL;
CREATE INDEX organization_api_keys_expiry_idx ON organization_api_keys (expires_at) WHERE revoked_at IS NULL;

COMMENT ON TABLE organization_api_keys IS
    'Machine credentials for CI and scripted use. The secret is shown once at creation and only its SHA-256 is stored. Every key is bound to a specific actor_id so job, audit and evidence records keep a single actor vocabulary.';

-- ---------------------------------------------------------------------------
-- 7. Optional enterprise SSO - tenant isolated
-- ---------------------------------------------------------------------------

CREATE TABLE organization_sso_connections (
    sso_connection_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    protocol varchar(16) NOT NULL,
    issuer varchar(255) NOT NULL,
    client_id varchar(255),
    client_secret_ref varchar(160),
    metadata_ref varchar(255),
    jwks_uri varchar(512),
    verified_domain varchar(255),
    domain_verification_token varchar(96),
    domain_verified_at timestamptz,
    jit_provisioning boolean NOT NULL DEFAULT false,
    default_member_role varchar(24) NOT NULL DEFAULT 'MEMBER',
    connection_state varchar(24) NOT NULL DEFAULT 'NOT_CONFIGURED',
    enforced_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT organization_sso_protocol CHECK (protocol IN ('OIDC', 'SAML')),
    CONSTRAINT organization_sso_state CHECK (
        connection_state IN ('NOT_CONFIGURED', 'PENDING_DOMAIN_VERIFICATION', 'ACTIVE', 'DISABLED')
    ),
    CONSTRAINT organization_sso_role CHECK (
        default_member_role IN ('ADMIN', 'MAINTAINER', 'MEMBER', 'BILLING', 'VIEWER')
    ),
    -- A connection cannot go ACTIVE until the domain is proven and the secret is
    -- a reference, never an inline value.
    CONSTRAINT organization_sso_active_shape CHECK (
        connection_state <> 'ACTIVE' OR (
            verified_domain IS NOT NULL
            AND domain_verified_at IS NOT NULL
            AND (protocol = 'SAML' OR (client_id IS NOT NULL AND client_secret_ref IS NOT NULL AND jwks_uri IS NOT NULL))
        )
    )
);

CREATE UNIQUE INDEX organization_sso_domain_uq
    ON organization_sso_connections (lower(verified_domain))
    WHERE verified_domain IS NOT NULL AND connection_state = 'ACTIVE';
CREATE INDEX organization_sso_org_idx ON organization_sso_connections (organization_id);

COMMENT ON COLUMN organization_sso_connections.client_secret_ref IS
    'Secret reference resolved through the V9 secret lease authority. Storing an inline client secret here is prohibited.';

-- ---------------------------------------------------------------------------
-- 8. Organization lifecycle - tenant isolated
-- ---------------------------------------------------------------------------

CREATE TABLE organization_lifecycle_requests (
    lifecycle_request_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    request_type varchar(32) NOT NULL,
    request_state varchar(24) NOT NULL DEFAULT 'PENDING',
    requested_by_actor_id varchar(128) NOT NULL,
    target_account_ref varchar(96) REFERENCES accounts(account_id),
    confirmation_token_sha256 varchar(64) CHECK (confirmation_token_sha256 IS NULL OR confirmation_token_sha256 ~ '^[0-9a-f]{64}$'),
    requested_at timestamptz NOT NULL DEFAULT now(),
    effective_after timestamptz NOT NULL,
    confirmed_at timestamptz,
    confirmed_by_actor_id varchar(128),
    cancelled_at timestamptz,
    completed_at timestamptz,
    CONSTRAINT organization_lifecycle_type CHECK (
        request_type IN ('OWNERSHIP_TRANSFER', 'DELETION', 'DATA_EXPORT', 'SUSPENSION_APPEAL')
    ),
    CONSTRAINT organization_lifecycle_state CHECK (
        request_state IN ('PENDING', 'CONFIRMED', 'CANCELLED', 'COMPLETED', 'EXPIRED')
    ),
    -- Destructive lifecycle actions observe a cooling-off window; deletion can
    -- always be cancelled until effective_after passes.
    CONSTRAINT organization_lifecycle_cooling_off CHECK (effective_after > requested_at)
);

CREATE INDEX organization_lifecycle_due_idx
    ON organization_lifecycle_requests (effective_after)
    WHERE request_state = 'CONFIRMED';

-- ---------------------------------------------------------------------------
-- 9. Sign-up, provisioning and invitation acceptance
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_provision_organization(
    p_organization_id varchar,
    p_display_name varchar,
    p_owner_account_id varchar,
    p_owner_actor_id varchar,
    p_data_region varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_account accounts%ROWTYPE;
BEGIN
    SELECT * INTO v_account FROM accounts WHERE account_id = p_owner_account_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_ACCOUNT_UNKNOWN'; END IF;
    IF v_account.status <> 'ACTIVE' THEN RAISE EXCEPTION 'ELMOS_ACCOUNT_NOT_ACTIVE'; END IF;

    INSERT INTO organizations (
        organization_id, display_name, status, isolation_class, data_region, encryption_context_id
    ) VALUES (
        p_organization_id, p_display_name, 'ACTIVE', 'T1_SHARED_SAAS',
        coalesce(p_data_region, 'cn-north'), 'key-' || p_organization_id
    );

    INSERT INTO organization_memberships (
        organization_membership_id, organization_id, schema_version, status,
        idempotency_key, payload, account_ref, member_role, member_state, joined_at
    ) VALUES (
        'mem-' || md5(p_organization_id || ':' || p_owner_account_id), p_organization_id,
        '2.0', 'ACTIVE', 'owner:' || p_owner_account_id, '{}'::jsonb,
        p_owner_account_id, 'OWNER', 'ACTIVE', now()
    );

    INSERT INTO user_identities (
        user_identity_id, organization_id, schema_version, status,
        idempotency_key, payload, account_ref, actor_id, source, provisioned_at
    ) VALUES (
        'uid-' || md5(p_organization_id || ':' || p_owner_account_id), p_organization_id,
        '2.0', 'ACTIVE', 'identity:' || p_owner_account_id, '{}'::jsonb,
        p_owner_account_id, p_owner_actor_id, 'SELF_SERVICE', now()
    );

    RETURN p_organization_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_accept_organization_invitation(
    p_token_sha256 varchar,
    p_account_id varchar,
    p_actor_id varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_invite organization_invitations%ROWTYPE;
    v_account accounts%ROWTYPE;
BEGIN
    SELECT * INTO v_invite FROM organization_invitations
     WHERE token_sha256 = p_token_sha256 FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_INVITATION_UNKNOWN'; END IF;
    IF v_invite.invitation_state <> 'PENDING' THEN RAISE EXCEPTION 'ELMOS_INVITATION_NOT_PENDING'; END IF;
    IF v_invite.expires_at < now() THEN
        UPDATE organization_invitations SET invitation_state = 'EXPIRED'
         WHERE invitation_id = v_invite.invitation_id;
        RAISE EXCEPTION 'ELMOS_INVITATION_EXPIRED';
    END IF;

    SELECT * INTO v_account FROM accounts WHERE account_id = p_account_id;
    IF NOT FOUND OR v_account.status <> 'ACTIVE' THEN RAISE EXCEPTION 'ELMOS_ACCOUNT_NOT_ACTIVE'; END IF;

    INSERT INTO organization_memberships (
        organization_membership_id, organization_id, schema_version, status,
        idempotency_key, payload, account_ref, member_role, member_state,
        invited_by_account_ref, joined_at
    ) VALUES (
        'mem-' || md5(v_invite.organization_id || ':' || p_account_id), v_invite.organization_id,
        '2.0', 'ACTIVE', 'invite:' || v_invite.invitation_id, '{}'::jsonb,
        p_account_id, v_invite.member_role, 'ACTIVE', NULL, now()
    )
    ON CONFLICT (organization_membership_id) DO UPDATE
        SET member_state = 'ACTIVE', member_role = EXCLUDED.member_role, joined_at = now();

    INSERT INTO user_identities (
        user_identity_id, organization_id, schema_version, status,
        idempotency_key, payload, account_ref, actor_id, source, provisioned_at
    ) VALUES (
        'uid-' || md5(v_invite.organization_id || ':' || p_account_id), v_invite.organization_id,
        '2.0', 'ACTIVE', 'identity:' || p_account_id, '{}'::jsonb,
        p_account_id, p_actor_id, 'INVITATION', now()
    )
    ON CONFLICT (user_identity_id) DO NOTHING;

    UPDATE organization_invitations
       SET invitation_state = 'ACCEPTED', accepted_at = now(), accepted_by_account_ref = p_account_id
     WHERE invitation_id = v_invite.invitation_id;

    RETURN v_invite.organization_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_expire_stale_identity_records()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE v_count integer := 0; v_n integer;
BEGIN
    UPDATE organization_invitations SET invitation_state = 'EXPIRED'
     WHERE invitation_state = 'PENDING' AND expires_at < now();
    GET DIAGNOSTICS v_n = ROW_COUNT; v_count := v_count + v_n;

    UPDATE authentication_sessions SET session_state = 'EXPIRED'
     WHERE session_state = 'ACTIVE' AND (idle_expires_at < now() OR absolute_expires_at < now());
    GET DIAGNOSTICS v_n = ROW_COUNT; v_count := v_count + v_n;

    UPDATE account_verification_challenges SET invalidated_at = now()
     WHERE consumed_at IS NULL AND invalidated_at IS NULL AND expires_at < now();
    GET DIAGNOSTICS v_n = ROW_COUNT; v_count := v_count + v_n;

    UPDATE accounts SET locked_until = NULL, failed_sign_in_count = 0
     WHERE locked_until IS NOT NULL AND locked_until < now();
    GET DIAGNOSTICS v_n = ROW_COUNT; v_count := v_count + v_n;

    RETURN v_count;
END;
$$;

-- ---------------------------------------------------------------------------
-- 10. Row level security and grants
-- ---------------------------------------------------------------------------

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'organization_invitations',
        'organization_api_keys',
        'organization_sso_connections',
        'organization_lifecycle_requests'
    ]
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

REVOKE ALL ON accounts FROM PUBLIC;
REVOKE ALL ON account_credentials FROM PUBLIC;
REVOKE ALL ON account_verification_challenges FROM PUBLIC;
REVOKE ALL ON account_security_events FROM PUBLIC;

COMMENT ON TABLE account_security_events IS
    'Append-only account security trail. Not tenant isolated because sign-in happens before an organization is selected. It carries no organization content and no raw network identifiers.';

DO $$
DECLARE v_function record;
BEGIN
    FOR v_function IN
        SELECT p.oid::regprocedure AS signature
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND p.proname IN (
               'elmos_provision_organization',
               'elmos_accept_organization_invitation',
               'elmos_expire_stale_identity_records',
               'elmos_guard_last_owner'
           )
    LOOP
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', v_function.signature);
    END LOOP;
END;
$$;
