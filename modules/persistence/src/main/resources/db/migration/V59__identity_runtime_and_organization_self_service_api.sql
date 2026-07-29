-- ELMOS V59: production identity runtime and organization self-service API.
--
-- V55/V56 introduced the account aggregates and authentication state. This
-- migration closes two production gaps:
--   * global authentication lookups no longer depend on bypassing tenant RLS;
--   * every operation used by the HTTP identity/org surface has one exact,
--     SECURITY DEFINER entry point with PUBLIC execution revoked.

-- Minimal, non-content authentication projections. These tables intentionally
-- have no RLS: they contain only routing facts needed before a tenant can be
-- bound. They are never granted directly to an application role.
CREATE TABLE identity_membership_directory (
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    organization_membership_id varchar(96) NOT NULL,
    actor_id varchar(128),
    member_role varchar(24) NOT NULL,
    member_state varchar(24) NOT NULL,
    display_name varchar(255) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, organization_id)
);

CREATE TABLE identity_invitation_directory (
    token_sha256 varchar(64) PRIMARY KEY CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    invitation_id varchar(96) NOT NULL UNIQUE,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    invitation_state varchar(24) NOT NULL,
    expires_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE identity_session_token_directory (
    refresh_token_sha256 varchar(64) PRIMARY KEY CHECK (refresh_token_sha256 ~ '^[0-9a-f]{64}$'),
    authentication_session_id varchar(96) NOT NULL,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    generation integer NOT NULL,
    superseded_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

REVOKE ALL ON identity_membership_directory FROM PUBLIC;
REVOKE ALL ON identity_invitation_directory FROM PUBLIC;
REVOKE ALL ON identity_session_token_directory FROM PUBLIC;

CREATE OR REPLACE FUNCTION elmos_sync_membership_directory()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        DELETE FROM identity_membership_directory
         WHERE account_id = OLD.account_ref
           AND organization_id = OLD.organization_id;
        RETURN OLD;
    END IF;
    IF NEW.account_ref IS NULL OR NEW.member_role IS NULL THEN
        RETURN NEW;
    END IF;
    INSERT INTO identity_membership_directory (
        account_id, organization_id, organization_membership_id, actor_id,
        member_role, member_state, display_name, updated_at
    )
    SELECT NEW.account_ref, NEW.organization_id, NEW.organization_membership_id,
           identity.actor_id, NEW.member_role, NEW.member_state,
           organization.display_name, now()
      FROM organizations organization
      LEFT JOIN user_identities identity
        ON identity.organization_id = NEW.organization_id
       AND identity.account_ref = NEW.account_ref
       AND identity.deprovisioned_at IS NULL
     WHERE organization.organization_id = NEW.organization_id
    ON CONFLICT (account_id, organization_id) DO UPDATE
        SET organization_membership_id = EXCLUDED.organization_membership_id,
            actor_id = coalesce(EXCLUDED.actor_id, identity_membership_directory.actor_id),
            member_role = EXCLUDED.member_role,
            member_state = EXCLUDED.member_state,
            display_name = EXCLUDED.display_name,
            updated_at = now();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_sync_identity_directory()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF NEW.account_ref IS NOT NULL THEN
        UPDATE identity_membership_directory
           SET actor_id = CASE WHEN NEW.deprovisioned_at IS NULL THEN NEW.actor_id ELSE NULL END,
               updated_at = now()
         WHERE account_id = NEW.account_ref
           AND organization_id = NEW.organization_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_sync_invitation_directory()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        DELETE FROM identity_invitation_directory WHERE token_sha256 = OLD.token_sha256;
        RETURN OLD;
    END IF;
    INSERT INTO identity_invitation_directory (
        token_sha256, invitation_id, organization_id, invitation_state, expires_at, updated_at
    ) VALUES (
        NEW.token_sha256, NEW.invitation_id, NEW.organization_id,
        NEW.invitation_state, NEW.expires_at, now()
    )
    ON CONFLICT (token_sha256) DO UPDATE
        SET invitation_state = EXCLUDED.invitation_state,
            expires_at = EXCLUDED.expires_at,
            updated_at = now();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_sync_session_token_directory()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE v_account_id varchar(96);
BEGIN
    PERFORM set_config('app.organization_id', NEW.organization_id, true);
    SELECT account_ref INTO v_account_id
      FROM authentication_sessions
     WHERE authentication_session_id = NEW.authentication_session_id;
    IF v_account_id IS NULL THEN
        RAISE EXCEPTION 'ELMOS_SESSION_ACCOUNT_MISSING';
    END IF;
    INSERT INTO identity_session_token_directory (
        refresh_token_sha256, authentication_session_id, organization_id,
        account_id, generation, superseded_at, updated_at
    ) VALUES (
        NEW.refresh_token_sha256, NEW.authentication_session_id,
        NEW.organization_id, v_account_id, NEW.generation, NEW.superseded_at, now()
    )
    ON CONFLICT (refresh_token_sha256) DO UPDATE
        SET superseded_at = EXCLUDED.superseded_at,
            updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER organization_memberships_auth_directory
AFTER INSERT OR UPDATE OR DELETE ON organization_memberships
FOR EACH ROW EXECUTE FUNCTION elmos_sync_membership_directory();

CREATE TRIGGER user_identities_auth_directory
AFTER INSERT OR UPDATE ON user_identities
FOR EACH ROW EXECUTE FUNCTION elmos_sync_identity_directory();

CREATE TRIGGER organization_invitations_auth_directory
AFTER INSERT OR UPDATE OR DELETE ON organization_invitations
FOR EACH ROW EXECUTE FUNCTION elmos_sync_invitation_directory();

CREATE TRIGGER authentication_tokens_auth_directory
AFTER INSERT OR UPDATE ON authentication_token_generations
FOR EACH ROW EXECUTE FUNCTION elmos_sync_session_token_directory();

INSERT INTO identity_membership_directory (
    account_id, organization_id, organization_membership_id, actor_id,
    member_role, member_state, display_name
)
SELECT membership.account_ref, membership.organization_id,
       membership.organization_membership_id, identity.actor_id,
       membership.member_role, membership.member_state, organization.display_name
  FROM organization_memberships membership
  JOIN organizations organization
    ON organization.organization_id = membership.organization_id
  LEFT JOIN user_identities identity
    ON identity.organization_id = membership.organization_id
   AND identity.account_ref = membership.account_ref
   AND identity.deprovisioned_at IS NULL
 WHERE membership.account_ref IS NOT NULL
   AND membership.member_role IS NOT NULL
ON CONFLICT (account_id, organization_id) DO NOTHING;

INSERT INTO identity_invitation_directory (
    token_sha256, invitation_id, organization_id, invitation_state, expires_at
)
SELECT token_sha256, invitation_id, organization_id, invitation_state, expires_at
  FROM organization_invitations
ON CONFLICT (token_sha256) DO NOTHING;

INSERT INTO identity_session_token_directory (
    refresh_token_sha256, authentication_session_id, organization_id,
    account_id, generation, superseded_at
)
SELECT token.refresh_token_sha256, token.authentication_session_id,
       token.organization_id, session.account_ref, token.generation, token.superseded_at
  FROM authentication_token_generations token
  JOIN authentication_sessions session
    ON session.authentication_session_id = token.authentication_session_id
 WHERE session.account_ref IS NOT NULL
ON CONFLICT (refresh_token_sha256) DO NOTHING;

-- Account lookup functions used by JdbcIdentityStore.
CREATE OR REPLACE FUNCTION elmos_account_row(p_account_id varchar)
RETURNS TABLE (
    account_id varchar, status varchar, display_name varchar,
    phone_verified boolean, email_verified boolean,
    failed_sign_in_count smallint, locked boolean
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT account.account_id, account.status, account.display_name,
           account.phone_verified_at IS NOT NULL,
           account.email_verified_at IS NOT NULL,
           account.failed_sign_in_count,
           account.locked_until IS NOT NULL AND account.locked_until > now()
      FROM accounts account
     WHERE account.account_id = p_account_id
       AND account.status <> 'PURGED'
$$;

CREATE OR REPLACE FUNCTION elmos_find_account(p_account_id varchar)
RETURNS TABLE (
    account_id varchar, status varchar, display_name varchar,
    phone_verified boolean, email_verified boolean,
    failed_sign_in_count smallint, locked boolean
)
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$ SELECT * FROM elmos_account_row(p_account_id) $$;

CREATE OR REPLACE FUNCTION elmos_find_account_by_phone(p_phone_lookup_hmac varchar)
RETURNS TABLE (
    account_id varchar, status varchar, display_name varchar,
    phone_verified boolean, email_verified boolean,
    failed_sign_in_count smallint, locked boolean
)
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
    SELECT row.* FROM accounts account
    CROSS JOIN LATERAL elmos_account_row(account.account_id) row
    WHERE account.phone_lookup_hmac = p_phone_lookup_hmac
$$;

CREATE OR REPLACE FUNCTION elmos_find_account_by_email(p_email varchar)
RETURNS TABLE (
    account_id varchar, status varchar, display_name varchar,
    phone_verified boolean, email_verified boolean,
    failed_sign_in_count smallint, locked boolean
)
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
    SELECT row.* FROM accounts account
    CROSS JOIN LATERAL elmos_account_row(account.account_id) row
    WHERE lower(account.primary_email) = lower(p_email)
$$;

CREATE OR REPLACE FUNCTION elmos_create_phone_account(
    p_account_id varchar, p_display_name varchar, p_phone_lookup_hmac varchar,
    p_phone_last4 varchar, p_phone_cipher_ref varchar
) RETURNS varchar
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
    INSERT INTO accounts (
        account_id, status, display_name, phone_lookup_hmac, phone_last4,
        phone_cipher_ref, phone_verified_at
    ) VALUES (
        p_account_id, 'PENDING_VERIFICATION', p_display_name, p_phone_lookup_hmac,
        p_phone_last4, p_phone_cipher_ref, now()
    );
    RETURN p_account_id;
EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION 'ELMOS_IDENTITY_CONFLICT';
END;
$$;

CREATE OR REPLACE FUNCTION elmos_create_email_account(
    p_account_id varchar, p_display_name varchar, p_email varchar
) RETURNS varchar
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
    INSERT INTO accounts (
        account_id, status, display_name, primary_email, email_verified_at
    ) VALUES (
        p_account_id, 'PENDING_VERIFICATION', p_display_name, lower(p_email), now()
    );
    RETURN p_account_id;
EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION 'ELMOS_IDENTITY_CONFLICT';
END;
$$;

CREATE OR REPLACE FUNCTION elmos_clear_sign_in_failures(p_account_id varchar)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
    UPDATE accounts
       SET failed_sign_in_count = 0, locked_until = NULL,
           last_sign_in_at = now(), updated_at = now()
     WHERE account_id = p_account_id
$$;

CREATE OR REPLACE FUNCTION elmos_memberships_of_account(p_account_id varchar)
RETURNS TABLE (
    organization_id varchar, display_name varchar,
    member_role varchar, actor_id varchar
)
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
    SELECT directory.organization_id, directory.display_name,
           directory.member_role, directory.actor_id
      FROM identity_membership_directory directory
     WHERE directory.account_id = p_account_id
       AND directory.member_state = 'ACTIVE'
       AND directory.actor_id IS NOT NULL
     ORDER BY directory.updated_at, directory.organization_id
$$;

-- OIDC is the production browser authentication authority. A verified email is
-- required for first linkage; automatic cross-provider email linking is refused.
CREATE OR REPLACE FUNCTION elmos_resolve_oidc_account(
    p_account_id varchar,
    p_issuer varchar,
    p_subject varchar,
    p_email varchar,
    p_email_verified boolean,
    p_display_name varchar
) RETURNS varchar
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE v_account_id varchar(96);
BEGIN
    SELECT credential.account_id INTO v_account_id
      FROM account_credentials credential
     WHERE credential.provider = 'ENTERPRISE_OIDC'
       AND credential.provider_issuer = p_issuer
       AND credential.provider_subject = p_subject
       AND credential.revoked_at IS NULL;
    IF v_account_id IS NOT NULL THEN
        UPDATE account_credentials SET last_used_at = now()
         WHERE provider = 'ENTERPRISE_OIDC'
           AND provider_issuer = p_issuer
           AND provider_subject = p_subject
           AND revoked_at IS NULL;
        RETURN v_account_id;
    END IF;
    IF NOT coalesce(p_email_verified, false) OR p_email IS NULL OR btrim(p_email) = '' THEN
        RAISE EXCEPTION 'ELMOS_OIDC_VERIFIED_EMAIL_REQUIRED';
    END IF;
    IF EXISTS (
        SELECT 1 FROM accounts
         WHERE lower(primary_email) = lower(p_email) AND status <> 'PURGED'
    ) THEN
        RAISE EXCEPTION 'ELMOS_IDENTITY_LINK_REQUIRED';
    END IF;
    INSERT INTO accounts (
        account_id, status, display_name, primary_email, email_verified_at
    ) VALUES (
        p_account_id, 'ACTIVE', left(p_display_name, 128), lower(p_email), now()
    );
    INSERT INTO account_credentials (
        credential_id, account_id, provider, provider_issuer,
        provider_subject, last_used_at
    ) VALUES (
        'cred-' || md5(p_issuer || ':' || p_subject), p_account_id,
        'ENTERPRISE_OIDC', p_issuer, p_subject, now()
    );
    RETURN p_account_id;
EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION 'ELMOS_IDENTITY_CONFLICT';
END;
$$;

-- Replace organization provisioning so FORCE RLS works for non-superuser
-- runtime roles. Tenant context is bound before the first org-scoped write.
CREATE OR REPLACE FUNCTION elmos_provision_organization(
    p_organization_id varchar,
    p_display_name varchar,
    p_owner_account_id varchar,
    p_owner_actor_id varchar,
    p_data_region varchar
) RETURNS varchar
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE v_account accounts%ROWTYPE;
BEGIN
    SELECT * INTO v_account FROM accounts
     WHERE account_id = p_owner_account_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_ACCOUNT_UNKNOWN'; END IF;
    IF v_account.status <> 'ACTIVE' THEN RAISE EXCEPTION 'ELMOS_ACCOUNT_NOT_ACTIVE'; END IF;

    INSERT INTO organizations (
        organization_id, display_name, status, isolation_class,
        data_region, encryption_context_id
    ) VALUES (
        p_organization_id, p_display_name, 'ACTIVE', 'T1_SHARED_SAAS',
        coalesce(p_data_region, 'cn-north'), 'key-' || p_organization_id
    );
    PERFORM set_config('app.organization_id', p_organization_id, true);
    INSERT INTO organization_memberships (
        organization_membership_id, organization_id, schema_version, status,
        idempotency_key, payload, account_ref, member_role, member_state, joined_at
    ) VALUES (
        'mem-' || md5(p_organization_id || ':' || p_owner_account_id),
        p_organization_id, '2.0', 'ACTIVE', 'owner:' || p_owner_account_id,
        '{}'::jsonb, p_owner_account_id, 'OWNER', 'ACTIVE', now()
    );
    INSERT INTO user_identities (
        user_identity_id, organization_id, schema_version, status,
        idempotency_key, payload, account_ref, actor_id, source, provisioned_at
    ) VALUES (
        'uid-' || md5(p_organization_id || ':' || p_owner_account_id),
        p_organization_id, '2.0', 'ACTIVE', 'identity:' || p_owner_account_id,
        '{}'::jsonb, p_owner_account_id, p_owner_actor_id, 'SELF_SERVICE', now()
    );
    RETURN p_organization_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_create_self_service_organization(
    p_account_id varchar,
    p_organization_id varchar,
    p_display_name varchar,
    p_owner_actor_id varchar,
    p_data_region varchar,
    p_verified_subject_hash varchar
) RETURNS varchar
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE v_has_membership boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM identity_membership_directory
         WHERE account_id = p_account_id AND member_state = 'ACTIVE'
    ) INTO v_has_membership;
    IF v_has_membership THEN
        RETURN elmos_provision_organization(
            p_organization_id, p_display_name, p_account_id,
            p_owner_actor_id, p_data_region);
    END IF;
    RETURN elmos_complete_signup(
        p_account_id, p_organization_id, p_display_name, p_owner_actor_id,
        p_verified_subject_hash, p_data_region);
END;
$$;

CREATE OR REPLACE FUNCTION elmos_create_organization_invitation(
    p_invitation_id varchar,
    p_organization_id varchar,
    p_inviter_account_id varchar,
    p_inviter_actor_id varchar,
    p_destination_hmac varchar,
    p_destination_display varchar,
    p_member_role varchar,
    p_token_sha256 varchar,
    p_ttl_seconds integer
) RETURNS varchar
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
    IF p_ttl_seconds < 300 OR p_ttl_seconds > 604800 THEN
        RAISE EXCEPTION 'ELMOS_INVITATION_TTL_INVALID';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM identity_membership_directory
         WHERE account_id = p_inviter_account_id
           AND organization_id = p_organization_id
           AND actor_id = p_inviter_actor_id
           AND member_state = 'ACTIVE'
           AND member_role IN ('OWNER', 'ADMIN')
    ) THEN
        RAISE EXCEPTION 'ELMOS_ORGANIZATION_ADMIN_REQUIRED';
    END IF;
    PERFORM set_config('app.organization_id', p_organization_id, true);
    INSERT INTO organization_invitations (
        invitation_id, organization_id, channel, destination_hmac,
        destination_display, member_role, token_sha256, invited_by_actor_id,
        expires_at
    ) VALUES (
        p_invitation_id, p_organization_id, 'EMAIL', p_destination_hmac,
        p_destination_display, p_member_role, p_token_sha256, p_inviter_actor_id,
        now() + make_interval(secs => p_ttl_seconds)
    );
    RETURN p_invitation_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_accept_organization_invitation(
    p_token_sha256 varchar,
    p_destination_hmac varchar,
    p_account_id varchar,
    p_actor_id varchar
) RETURNS varchar
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
    v_directory identity_invitation_directory%ROWTYPE;
    v_invite organization_invitations%ROWTYPE;
    v_account accounts%ROWTYPE;
BEGIN
    SELECT * INTO v_directory FROM identity_invitation_directory
     WHERE token_sha256 = p_token_sha256;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_INVITATION_UNKNOWN'; END IF;
    PERFORM set_config('app.organization_id', v_directory.organization_id, true);
    SELECT * INTO v_invite FROM organization_invitations
     WHERE invitation_id = v_directory.invitation_id FOR UPDATE;
    IF NOT FOUND OR v_invite.destination_hmac <> p_destination_hmac THEN
        RAISE EXCEPTION 'ELMOS_INVITATION_DESTINATION_MISMATCH';
    END IF;
    IF v_invite.invitation_state <> 'PENDING' THEN
        RAISE EXCEPTION 'ELMOS_INVITATION_NOT_PENDING';
    END IF;
    IF v_invite.expires_at < now() THEN
        UPDATE organization_invitations SET invitation_state = 'EXPIRED'
         WHERE invitation_id = v_invite.invitation_id;
        RAISE EXCEPTION 'ELMOS_INVITATION_EXPIRED';
    END IF;
    SELECT * INTO v_account FROM accounts WHERE account_id = p_account_id;
    IF NOT FOUND OR v_account.status <> 'ACTIVE' THEN
        RAISE EXCEPTION 'ELMOS_ACCOUNT_NOT_ACTIVE';
    END IF;
    INSERT INTO organization_memberships (
        organization_membership_id, organization_id, schema_version, status,
        idempotency_key, payload, account_ref, member_role, member_state,
        joined_at
    ) VALUES (
        'mem-' || md5(v_invite.organization_id || ':' || p_account_id),
        v_invite.organization_id, '2.0', 'ACTIVE',
        'invite:' || v_invite.invitation_id, '{}'::jsonb,
        p_account_id, v_invite.member_role, 'ACTIVE', now()
    )
    ON CONFLICT (organization_membership_id) DO UPDATE
        SET member_state = 'ACTIVE', member_role = EXCLUDED.member_role,
            joined_at = now(), removed_at = NULL;
    INSERT INTO user_identities (
        user_identity_id, organization_id, schema_version, status,
        idempotency_key, payload, account_ref, actor_id, source, provisioned_at
    ) VALUES (
        'uid-' || md5(v_invite.organization_id || ':' || p_account_id),
        v_invite.organization_id, '2.0', 'ACTIVE',
        'identity:' || p_account_id, '{}'::jsonb, p_account_id,
        p_actor_id, 'INVITATION', now()
    )
    ON CONFLICT (user_identity_id) DO UPDATE
        SET actor_id = EXCLUDED.actor_id, deprovisioned_at = NULL, status = 'ACTIVE';
    UPDATE organization_invitations
       SET invitation_state = 'ACCEPTED', accepted_at = now(),
           accepted_by_account_ref = p_account_id
     WHERE invitation_id = v_invite.invitation_id;
    RETURN v_invite.organization_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_accept_organization_invitation(
    p_token_sha256 varchar, p_account_id varchar, p_actor_id varchar
) RETURNS varchar
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
    RAISE EXCEPTION 'ELMOS_INVITATION_DESTINATION_PROOF_REQUIRED';
END;
$$;

CREATE OR REPLACE FUNCTION elmos_list_organization_members(
    p_organization_id varchar, p_requester_account_id varchar
) RETURNS TABLE (
    account_id varchar, actor_id varchar, display_name varchar,
    member_role varchar, member_state varchar, joined_at timestamptz
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
#variable_conflict use_column
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM identity_membership_directory AS directory
         WHERE directory.account_id = p_requester_account_id
           AND directory.organization_id = p_organization_id
           AND directory.member_state = 'ACTIVE'
           AND directory.member_role IN ('OWNER', 'ADMIN')
    ) THEN RAISE EXCEPTION 'ELMOS_ORGANIZATION_ADMIN_REQUIRED'; END IF;
    PERFORM set_config('app.organization_id', p_organization_id, true);
    RETURN QUERY
    SELECT membership.account_ref, identity.actor_id, account.display_name,
           membership.member_role, membership.member_state, membership.joined_at
      FROM organization_memberships membership
      JOIN accounts account ON account.account_id = membership.account_ref
      LEFT JOIN user_identities identity
        ON identity.organization_id = membership.organization_id
       AND identity.account_ref = membership.account_ref
     WHERE membership.organization_id = p_organization_id
       AND membership.member_role IS NOT NULL
     ORDER BY membership.joined_at, membership.organization_membership_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_update_organization_member(
    p_organization_id varchar,
    p_requester_account_id varchar,
    p_target_account_id varchar,
    p_member_role varchar,
    p_remove boolean
) RETURNS varchar
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE v_membership_id varchar(96);
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM identity_membership_directory
         WHERE account_id = p_requester_account_id
           AND organization_id = p_organization_id
           AND member_state = 'ACTIVE'
           AND member_role IN ('OWNER', 'ADMIN')
    ) THEN RAISE EXCEPTION 'ELMOS_ORGANIZATION_ADMIN_REQUIRED'; END IF;
    IF NOT p_remove AND p_member_role NOT IN (
        'OWNER', 'ADMIN', 'MAINTAINER', 'MEMBER', 'BILLING', 'VIEWER'
    ) THEN RAISE EXCEPTION 'ELMOS_ORGANIZATION_ROLE_INVALID'; END IF;
    PERFORM set_config('app.organization_id', p_organization_id, true);
    SELECT organization_membership_id INTO v_membership_id
      FROM organization_memberships
     WHERE organization_id = p_organization_id
       AND account_ref = p_target_account_id
       AND member_state <> 'REMOVED'
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_ORGANIZATION_MEMBER_UNKNOWN'; END IF;
    UPDATE organization_memberships
       SET member_role = CASE WHEN p_remove THEN member_role ELSE p_member_role END,
           member_state = CASE WHEN p_remove THEN 'REMOVED' ELSE 'ACTIVE' END,
           removed_at = CASE WHEN p_remove THEN now() ELSE NULL END,
           updated_at = now()
     WHERE organization_membership_id = v_membership_id;
    IF p_remove THEN
        UPDATE user_identities
           SET deprovisioned_at = now(), status = 'DEPROVISIONED', updated_at = now()
         WHERE organization_id = p_organization_id
           AND account_ref = p_target_account_id
           AND deprovisioned_at IS NULL;
    END IF;
    RETURN v_membership_id;
END;
$$;

-- Session functions must discover the physical tenant before touching a
-- FORCE-RLS table. The directory contains routing facts only; membership and
-- session state are still read and mutated inside the bound tenant.
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
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
    IF p_idle_seconds <= 0 OR p_absolute_seconds <= 0
       OR p_idle_seconds > p_absolute_seconds THEN
        RAISE EXCEPTION 'ELMOS_SESSION_LIFETIME_INVALID';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM identity_membership_directory
         WHERE account_id = p_account_id
           AND organization_id = p_organization_id
           AND member_state = 'ACTIVE'
           AND actor_id IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'ELMOS_SESSION_MEMBERSHIP_REQUIRED';
    END IF;

    PERFORM set_config('app.organization_id', p_organization_id, true);
    INSERT INTO authentication_sessions (
        authentication_session_id, organization_id, schema_version, status,
        idempotency_key, payload, account_ref, session_state,
        refresh_token_sha256, issued_at, absolute_expires_at, idle_expires_at,
        amr, device_label, client_family, ip_prefix,
        active_organization_ref, token_generation
    ) VALUES (
        p_session_id, p_organization_id, '2.0', 'ACTIVE',
        'session:' || p_session_id, '{}'::jsonb, p_account_id, 'ACTIVE',
        p_refresh_token_sha256, now(),
        now() + make_interval(secs => p_absolute_seconds),
        now() + make_interval(secs => p_idle_seconds),
        p_amr, p_device_label, p_client_family, p_ip_prefix,
        p_organization_id, 0
    );
    INSERT INTO authentication_token_generations (
        token_generation_id, authentication_session_id, organization_id,
        generation, refresh_token_sha256
    ) VALUES (
        p_session_id || ':0', p_session_id, p_organization_id,
        0, p_refresh_token_sha256
    );
    RETURN p_session_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_rotate_session_token(
    p_presented_sha256 varchar,
    p_next_sha256 varchar,
    p_idle_seconds integer
) RETURNS TABLE (
    outcome varchar, session_id varchar, account_id varchar, organization_id varchar
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
#variable_conflict use_column
DECLARE
    v_directory identity_session_token_directory%ROWTYPE;
    v_generation authentication_token_generations%ROWTYPE;
    v_session authentication_sessions%ROWTYPE;
BEGIN
    SELECT * INTO v_directory
      FROM identity_session_token_directory
     WHERE refresh_token_sha256 = p_presented_sha256;
    IF NOT FOUND THEN outcome := 'REJECTED'; RETURN NEXT; RETURN; END IF;

    PERFORM set_config('app.organization_id', v_directory.organization_id, true);
    SELECT * INTO v_generation
      FROM authentication_token_generations
     WHERE refresh_token_sha256 = p_presented_sha256;
    SELECT * INTO v_session
      FROM authentication_sessions
     WHERE authentication_session_id = v_directory.authentication_session_id
     FOR UPDATE;
    IF NOT FOUND OR v_generation.authentication_session_id IS NULL THEN
        outcome := 'REJECTED'; RETURN NEXT; RETURN;
    END IF;

    IF v_generation.superseded_at IS NOT NULL THEN
        UPDATE authentication_sessions
           SET session_state = 'REVOKED', revoked_at = now(),
               revocation_code = 'REFRESH_TOKEN_REUSED',
               compromised_at = now(), updated_at = now()
         WHERE authentication_session_id = v_session.authentication_session_id
           AND session_state = 'ACTIVE';
        INSERT INTO account_security_events (
            security_event_id, account_id, event_type, outcome, failure_code
        ) VALUES (
            'sec-' || md5(v_session.authentication_session_id || ':reuse:' || p_presented_sha256),
            v_session.account_ref, 'SESSION_REVOKED', 'BLOCKED',
            'REFRESH_TOKEN_REUSED'
        ) ON CONFLICT (security_event_id) DO NOTHING;
        outcome := 'REUSED';
        session_id := v_session.authentication_session_id;
        account_id := v_session.account_ref;
        organization_id := coalesce(
                v_session.active_organization_ref, v_session.organization_id);
        RETURN NEXT; RETURN;
    END IF;

    IF v_session.session_state <> 'ACTIVE'
       OR v_session.absolute_expires_at < now()
       OR v_session.idle_expires_at < now()
       OR p_idle_seconds <= 0 THEN
        UPDATE authentication_sessions
           SET session_state = 'EXPIRED', updated_at = now()
         WHERE authentication_session_id = v_session.authentication_session_id
           AND session_state = 'ACTIVE';
        outcome := 'REJECTED'; RETURN NEXT; RETURN;
    END IF;

    UPDATE authentication_token_generations
       SET superseded_at = now()
     WHERE token_generation_id = v_generation.token_generation_id;
    UPDATE authentication_sessions
       SET refresh_token_sha256 = p_next_sha256,
           token_generation = token_generation + 1,
           idle_expires_at = least(
               now() + make_interval(secs => p_idle_seconds),
               absolute_expires_at),
           updated_at = now()
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
    organization_id := coalesce(
            v_session.active_organization_ref, v_session.organization_id);
    RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_switch_session_organization(
    p_session_id varchar,
    p_account_id varchar,
    p_organization_id varchar
) RETURNS TABLE (
    organization_id varchar, display_name varchar,
    member_role varchar, actor_id varchar
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
#variable_conflict use_column
DECLARE
    v_membership identity_membership_directory%ROWTYPE;
    v_session_organization_id varchar(96);
BEGIN
    SELECT * INTO v_membership
      FROM identity_membership_directory directory
     WHERE directory.account_id = p_account_id
       AND directory.organization_id = p_organization_id
       AND directory.member_state = 'ACTIVE'
       AND directory.actor_id IS NOT NULL;
    IF NOT FOUND THEN RETURN; END IF;

    SELECT directory.organization_id INTO v_session_organization_id
      FROM identity_session_token_directory directory
     WHERE directory.authentication_session_id = p_session_id
       AND directory.account_id = p_account_id
     LIMIT 1;
    IF v_session_organization_id IS NULL THEN RETURN; END IF;

    PERFORM set_config('app.organization_id', v_session_organization_id, true);
    UPDATE authentication_sessions
       SET active_organization_ref = p_organization_id, updated_at = now()
     WHERE authentication_session_id = p_session_id
       AND account_ref = p_account_id
       AND session_state = 'ACTIVE'
       AND absolute_expires_at > now()
       AND idle_expires_at > now();
    IF NOT FOUND THEN RETURN; END IF;

    organization_id := v_membership.organization_id;
    display_name := v_membership.display_name;
    member_role := v_membership.member_role;
    actor_id := v_membership.actor_id;
    RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_find_session_by_token(p_refresh_token_sha256 varchar)
RETURNS TABLE (
    session_id varchar, account_id varchar, organization_id varchar,
    absolute_expires_at timestamptz, idle_expires_at timestamptz
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE v_directory identity_session_token_directory%ROWTYPE;
BEGIN
    SELECT * INTO v_directory FROM identity_session_token_directory
     WHERE refresh_token_sha256 = p_refresh_token_sha256;
    IF NOT FOUND THEN RETURN; END IF;
    PERFORM set_config('app.organization_id', v_directory.organization_id, true);
    RETURN QUERY
    SELECT session.authentication_session_id, session.account_ref,
           coalesce(session.active_organization_ref, session.organization_id),
           session.absolute_expires_at, session.idle_expires_at
      FROM authentication_sessions session
     WHERE session.authentication_session_id = v_directory.authentication_session_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_revoke_session(
    p_session_id varchar, p_reason_code varchar
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE v_organization_id varchar(96);
BEGIN
    SELECT organization_id INTO v_organization_id
      FROM identity_session_token_directory
     WHERE authentication_session_id = p_session_id
     LIMIT 1;
    IF v_organization_id IS NULL THEN RETURN; END IF;
    PERFORM set_config('app.organization_id', v_organization_id, true);
    UPDATE authentication_sessions
       SET session_state = 'REVOKED', revoked_at = now(),
           revocation_code = p_reason_code, updated_at = now()
     WHERE authentication_session_id = p_session_id
       AND session_state = 'ACTIVE';
END;
$$;

CREATE OR REPLACE FUNCTION elmos_record_security_event(
    p_event_id varchar, p_account_id varchar, p_event_type varchar,
    p_outcome varchar, p_failure_code varchar, p_ip_prefix varchar,
    p_client_family varchar
) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
    INSERT INTO account_security_events (
        security_event_id, account_id, event_type, outcome,
        failure_code, ip_prefix, client_family
    ) VALUES (
        p_event_id, p_account_id, p_event_type, p_outcome,
        p_failure_code, p_ip_prefix, p_client_family
    ) ON CONFLICT (security_event_id) DO NOTHING
$$;

CREATE OR REPLACE FUNCTION elmos_invitation_organization(p_token_sha256 varchar)
RETURNS varchar
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
    SELECT organization_id
      FROM identity_invitation_directory
     WHERE token_sha256 = p_token_sha256
       AND invitation_state = 'PENDING'
       AND expires_at > now()
$$;

-- Public cannot execute the auth projections, trigger helpers, or APIs. A
-- deployment grant script gives only exact functions to exact runtime roles.
DO $$
DECLARE v_function record;
BEGIN
    FOR v_function IN
        SELECT procedure.oid::regprocedure AS signature
          FROM pg_proc procedure
          JOIN pg_namespace namespace ON namespace.oid = procedure.pronamespace
         WHERE namespace.nspname = 'public'
           AND (
               procedure.proname LIKE 'elmos_%identity%directory%'
               OR procedure.proname IN (
                   'elmos_account_row',
                   'elmos_find_account',
                   'elmos_find_account_by_phone',
                   'elmos_find_account_by_email',
                   'elmos_create_phone_account',
                   'elmos_create_email_account',
                   'elmos_clear_sign_in_failures',
                   'elmos_memberships_of_account',
                   'elmos_resolve_oidc_account',
                   'elmos_provision_organization',
                   'elmos_create_self_service_organization',
                   'elmos_create_organization_invitation',
                   'elmos_accept_organization_invitation',
                   'elmos_list_organization_members',
                   'elmos_update_organization_member',
                   'elmos_invitation_organization',
                   'elmos_open_session',
                   'elmos_rotate_session_token',
                   'elmos_switch_session_organization',
                   'elmos_find_session_by_token',
                   'elmos_revoke_session',
                   'elmos_record_security_event',
                   'elmos_sync_membership_directory',
                   'elmos_sync_identity_directory',
                   'elmos_sync_invitation_directory',
                   'elmos_sync_session_token_directory'
               )
           )
    LOOP
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', v_function.signature);
    END LOOP;
END;
$$;
