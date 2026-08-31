-- ELMOS V79: bind every effective platform-administrator privilege to the
-- one verified, active account whose normalized email is zpchoney@gmail.com.
--
-- V75 deliberately kept the browser principal and the database authorization
-- list separate.  That was a useful defence-in-depth boundary, but it also
-- meant a direct bootstrap or a stale platform_administrators row could name a
-- different account.  This forward-only migration closes that gap without
-- rewriting V75 or trusting a caller-supplied email:
--   * eligibility is derived from the authoritative accounts row;
--   * every authorization decision re-evaluates that row;
--   * grants, bootstrap and direct table writes fail closed;
--   * losing the verified email or ACTIVE state automatically revokes a live
--     row instead of blocking the safety update; and
--   * pre-existing ineligible live rows are revoked and audit recorded.

-- ---------------------------------------------------------------------------
-- 1. One database-owned eligibility predicate
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_platform_admin_identity_eligible(
    p_account_id varchar
) RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT EXISTS (
        SELECT 1
          FROM public.accounts account
         WHERE account.account_id = p_account_id
           AND account.status = 'ACTIVE'
           AND account.email_verified_at IS NOT NULL
           AND account.primary_email IS NOT NULL
           -- Whitespace is not part of a valid canonical email. Reject it
           -- rather than letting two differently stored strings normalize to
           -- the designated identity.
           AND account.primary_email = btrim(account.primary_email)
           AND lower(account.primary_email) = 'zpchoney@gmail.com'
    );
$$;

COMMENT ON FUNCTION elmos_platform_admin_identity_eligible(varchar) IS
    'Returns true only for the active account with a verified canonical email exactly equal to zpchoney@gmail.com after case normalization. The account row, never a request parameter, is authoritative.';

REVOKE ALL ON FUNCTION elmos_platform_admin_identity_eligible(varchar) FROM PUBLIC;

-- Prevent an old V75 grant or account update from committing between the
-- convergence scan and installation of the new triggers/functions. Flyway
-- applies PostgreSQL migrations transactionally, so these locks are held only
-- until V79 commits and the new boundary becomes visible atomically.
LOCK TABLE public.accounts IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.platform_administrators IN SHARE ROW EXCLUSIVE MODE;

-- ---------------------------------------------------------------------------
-- 2. Safely converge installations upgraded from V75
-- ---------------------------------------------------------------------------

WITH revoked AS (
    UPDATE public.platform_administrators administrator
       SET revoked_at = clock_timestamp(),
           -- revoked_by is a required FK to accounts.  For a database-owned
           -- safety transition there is no human actor, so the affected
           -- account is used only to satisfy that legacy shape; revoke_reason
           -- and the access-log detail explicitly identify the system action.
           revoked_by = administrator.account_id,
           revoke_reason = 'SYSTEM_SECURITY_MIGRATION_V79_IDENTITY_INELIGIBLE',
           state_version = administrator.state_version + 1
     WHERE administrator.revoked_at IS NULL
       AND NOT public.elmos_platform_admin_identity_eligible(administrator.account_id)
    RETURNING administrator.account_id, administrator.platform_role,
              administrator.revoked_at
)
INSERT INTO public.platform_admin_access_log (
    access_id, admin_account_id, platform_role, operation,
    target_ref, result, detail, occurred_at
)
SELECT 'pal-' || md5(
           revoked.account_id || ':v79-identity-revoke:' || revoked.revoked_at::text),
       revoked.account_id,
       revoked.platform_role,
       'MIGRATION_REVOKE_IDENTITY',
       revoked.account_id,
       'ALLOWED',
       'system migration revoked an ineligible platform administrator; no email value logged',
       revoked.revoked_at
  FROM revoked;

-- ---------------------------------------------------------------------------
-- 3. Guard direct writes and revoke on account-identity loss
-- ---------------------------------------------------------------------------

-- The two row triggers below touch accounts and platform_administrators in
-- opposite directions. Serialize their statement entry before either executor
-- can take a row lock, so every supported INSERT/UPDATE/DELETE path has one
-- global order and cannot form an accounts-row <-> administrator-row cycle.
-- This advisory lock is transaction scoped and intentionally covers only this
-- low-volume security boundary; it is not a general application mutex.
CREATE OR REPLACE FUNCTION elmos_platform_admin_identity_write_lock()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    PERFORM pg_catalog.pg_advisory_xact_lock(1162628425, 79);
    RETURN NULL;
END;
$$;

CREATE TRIGGER "00_platform_administrators_identity_write_lock"
BEFORE INSERT OR UPDATE OR DELETE ON public.platform_administrators
FOR EACH STATEMENT EXECUTE FUNCTION elmos_platform_admin_identity_write_lock();

CREATE TRIGGER "00_accounts_platform_admin_identity_update_lock"
BEFORE UPDATE OF primary_email, email_verified_at, status ON public.accounts
FOR EACH STATEMENT EXECUTE FUNCTION elmos_platform_admin_identity_write_lock();

CREATE TRIGGER "00_accounts_platform_admin_identity_delete_lock"
BEFORE DELETE ON public.accounts
FOR EACH STATEMENT EXECUTE FUNCTION elmos_platform_admin_identity_write_lock();

CREATE OR REPLACE FUNCTION elmos_platform_admin_identity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_status varchar(32);
    v_primary_email varchar(320);
    v_email_verified_at timestamptz;
BEGIN
    IF NEW.revoked_at IS NOT NULL THEN
        RETURN NEW;
    END IF;

    -- FOR SHARE serializes a direct grant with an email/status update. If the
    -- grant wins, the later account update sees and auto-revokes it; if the
    -- account update wins, this trigger rechecks the updated row and refuses
    -- the grant. That closes the otherwise possible stale-live-row race.
    SELECT account.status, account.primary_email, account.email_verified_at
      INTO v_status, v_primary_email, v_email_verified_at
      FROM public.accounts account
     WHERE account.account_id = NEW.account_id
     FOR SHARE;

    IF NOT FOUND
       OR v_status <> 'ACTIVE'
       OR v_email_verified_at IS NULL
       OR v_primary_email IS NULL
       OR v_primary_email <> btrim(v_primary_email)
       OR lower(v_primary_email) <> 'zpchoney@gmail.com' THEN
        RAISE EXCEPTION 'ELMOS_PLATFORM_ADMIN_VERIFIED_EMAIL_REQUIRED';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER platform_administrators_identity_guard
BEFORE INSERT OR UPDATE OF account_id, revoked_at
ON public.platform_administrators
FOR EACH ROW EXECUTE FUNCTION elmos_platform_admin_identity_guard();

CREATE OR REPLACE FUNCTION elmos_platform_admin_revoke_on_identity_loss()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_role varchar(24);
    v_revoked_at timestamptz;
BEGIN
    IF NEW.status = 'ACTIVE'
       AND NEW.email_verified_at IS NOT NULL
       AND NEW.primary_email IS NOT NULL
       AND NEW.primary_email = btrim(NEW.primary_email)
       AND lower(NEW.primary_email) = 'zpchoney@gmail.com' THEN
        RETURN NEW;
    END IF;

    v_revoked_at := clock_timestamp();
    UPDATE public.platform_administrators administrator
       SET revoked_at = v_revoked_at,
           -- See the V79 convergence comment above: this denotes a system
           -- transition, not a claim that the person revoked themselves.
           revoked_by = NEW.account_id,
           revoke_reason = 'SYSTEM_IDENTITY_ELIGIBILITY_LOST_V79',
           state_version = administrator.state_version + 1
     WHERE administrator.account_id = NEW.account_id
       AND administrator.revoked_at IS NULL
    RETURNING administrator.platform_role INTO v_role;

    IF FOUND THEN
        INSERT INTO public.platform_admin_access_log (
            access_id, admin_account_id, platform_role, operation,
            target_ref, result, detail, occurred_at
        ) VALUES (
            'pal-' || md5(NEW.account_id || ':identity-loss:' || v_revoked_at::text),
            NEW.account_id, v_role, 'AUTO_REVOKE_IDENTITY',
            NEW.account_id, 'ALLOWED',
            'automatic revocation: account is no longer active with the verified designated administrator email',
            v_revoked_at
        );
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER accounts_platform_admin_identity_loss
AFTER UPDATE OF primary_email, email_verified_at, status
ON public.accounts
FOR EACH ROW EXECUTE FUNCTION elmos_platform_admin_revoke_on_identity_loss();

REVOKE ALL ON FUNCTION elmos_platform_admin_identity_guard() FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_platform_admin_revoke_on_identity_loss() FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_platform_admin_identity_write_lock() FROM PUBLIC;
REVOKE ALL ON TABLE public.accounts, public.platform_administrators FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- 4. Re-evaluate identity on every effective use
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_platform_authorize(
    p_admin_account_id varchar,
    p_required_role varchar,
    p_operation varchar,
    p_target_organization_id varchar DEFAULT NULL,
    p_target_ref varchar DEFAULT NULL
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_role varchar(24);
    v_rank integer;
    v_required integer;
    v_result varchar(24);
BEGIN
    SELECT administrator.platform_role INTO v_role
      FROM public.platform_administrators administrator
     WHERE administrator.account_id = p_admin_account_id
       AND administrator.revoked_at IS NULL
       AND public.elmos_platform_admin_identity_eligible(administrator.account_id);

    v_rank := CASE v_role
        WHEN 'PLATFORM_APPROVER' THEN 3
        WHEN 'PLATFORM_OPERATOR' THEN 2
        WHEN 'PLATFORM_VIEWER' THEN 1
        ELSE 0 END;
    v_required := CASE p_required_role
        WHEN 'PLATFORM_APPROVER' THEN 3
        WHEN 'PLATFORM_OPERATOR' THEN 2
        ELSE 1 END;

    v_result := CASE
        WHEN v_role IS NULL THEN 'DENIED_NOT_ADMIN'
        WHEN v_rank < v_required THEN 'DENIED_ROLE'
        ELSE 'ALLOWED' END;

    INSERT INTO public.platform_admin_access_log (
        access_id, admin_account_id, platform_role, operation,
        target_organization_id, target_ref, result)
    VALUES (
        'pal-' || md5(coalesce(p_admin_account_id, '<null>') || ':'
                      || coalesce(p_operation, '<null>') || ':'
                      || coalesce(p_target_organization_id, '-') || ':'
                      || coalesce(p_target_ref, '-') || ':' || clock_timestamp()::text),
        coalesce(p_admin_account_id, '<unknown>'), v_role,
        coalesce(p_operation, 'UNKNOWN'),
        p_target_organization_id, p_target_ref, v_result);

    RETURN v_result;
END;
$$;

COMMENT ON FUNCTION elmos_platform_authorize(varchar, varchar, varchar, varchar, varchar) IS
    'Re-evaluates the live administrator row and authoritative verified-email identity for every use, then records ALLOWED or DENIED_* without logging the email value.';

CREATE OR REPLACE FUNCTION elmos_platform_resolve_admin_account(
    p_organization_id varchar,
    p_actor_id varchar
) RETURNS varchar
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT directory.account_id
      FROM public.identity_membership_directory directory
      JOIN public.platform_administrators administrator
        ON administrator.account_id = directory.account_id
       AND administrator.revoked_at IS NULL
     WHERE directory.organization_id = p_organization_id
       AND directory.actor_id = p_actor_id
       AND directory.member_state <> 'REMOVED'
       AND public.elmos_platform_admin_identity_eligible(directory.account_id)
     LIMIT 1;
$$;

COMMENT ON FUNCTION elmos_platform_resolve_admin_account(varchar, varchar) IS
    'Maps an organization-bound actor only when it is the live, active and verified designated administrator account; all other identities resolve to NULL.';

-- ---------------------------------------------------------------------------
-- 5. Make both audited grant paths enforce the same exact target
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_platform_grant_admin(
    p_admin_account_id varchar,
    p_target_account_id varchar,
    p_platform_role varchar,
    p_reason varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_decision varchar(24);
BEGIN
    IF p_reason IS NULL OR length(btrim(p_reason)) = 0
       OR p_platform_role IS NULL
       OR p_platform_role NOT IN (
           'PLATFORM_VIEWER', 'PLATFORM_OPERATOR', 'PLATFORM_APPROVER') THEN
        RETURN 'DENIED_POLICY';
    END IF;

    v_decision := public.elmos_platform_authorize(
        p_admin_account_id, 'PLATFORM_APPROVER', 'GRANT_ADMIN', NULL,
        coalesce(p_target_account_id, '<null>') || ':' || coalesce(p_platform_role, '<null>'));
    IF v_decision <> 'ALLOWED' THEN
        RETURN v_decision;
    END IF;

    IF NOT public.elmos_platform_admin_identity_eligible(p_target_account_id) THEN
        RETURN 'DENIED_POLICY';
    END IF;

    INSERT INTO public.platform_administrators (
        account_id, platform_role, granted_by, grant_reason)
    VALUES (p_target_account_id, p_platform_role, p_admin_account_id, p_reason)
    ON CONFLICT (account_id) DO UPDATE
        SET platform_role = EXCLUDED.platform_role,
            granted_by = EXCLUDED.granted_by,
            granted_at = now(),
            grant_reason = EXCLUDED.grant_reason,
            revoked_at = NULL,
            revoked_by = NULL,
            revoke_reason = NULL,
            state_version = platform_administrators.state_version + 1;
    RETURN 'ALLOWED';
END;
$$;

CREATE OR REPLACE FUNCTION elmos_platform_bootstrap_admin(
    p_target_account_id varchar,
    p_reason varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.platform_administrators administrator
         WHERE administrator.platform_role = 'PLATFORM_APPROVER'
           AND administrator.revoked_at IS NULL
           AND public.elmos_platform_admin_identity_eligible(administrator.account_id)
    ) THEN
        RETURN 'DENIED_POLICY';
    END IF;
    IF p_reason IS NULL OR length(btrim(p_reason)) = 0
       OR NOT public.elmos_platform_admin_identity_eligible(p_target_account_id) THEN
        RETURN 'DENIED_POLICY';
    END IF;

    INSERT INTO public.platform_administrators (
        account_id, platform_role, grant_reason)
    VALUES (p_target_account_id, 'PLATFORM_APPROVER', p_reason)
    ON CONFLICT (account_id) DO UPDATE
        SET platform_role = 'PLATFORM_APPROVER',
            revoked_at = NULL,
            revoked_by = NULL,
            revoke_reason = NULL,
            granted_at = now(),
            grant_reason = EXCLUDED.grant_reason,
            state_version = platform_administrators.state_version + 1;

    INSERT INTO public.platform_admin_access_log (
        access_id, admin_account_id, platform_role, operation,
        target_ref, result, detail)
    VALUES (
        'pal-' || md5('bootstrap:' || p_target_account_id || ':' || clock_timestamp()::text),
        p_target_account_id, 'PLATFORM_APPROVER', 'BOOTSTRAP_ADMIN',
        p_target_account_id, 'ALLOWED', p_reason);
    RETURN 'ALLOWED';
END;
$$;

-- CREATE OR REPLACE retains function ACLs, but explicitly preserving the V75
-- PUBLIC denial makes that boundary visible and guards a misconfigured upgrade.
REVOKE ALL ON FUNCTION elmos_platform_authorize(varchar, varchar, varchar, varchar, varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_platform_resolve_admin_account(varchar, varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_platform_grant_admin(varchar, varchar, varchar, varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_platform_bootstrap_admin(varchar, varchar) FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_platform_admin_runtime') THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_platform_authorize(varchar, varchar, varchar, varchar, varchar) TO elmos_platform_admin_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_platform_resolve_admin_account(varchar, varchar) TO elmos_platform_admin_runtime';
    END IF;
END;
$$;
