-- ELMOS V75: platform administrators and the audited cross-tenant read path.
--
-- Why this migration exists
-- -------------------------
-- Every existing administrator in this system is scoped to one organization.
-- OperationsAuthorization resolves an OIDC principal to a tenant; the fallback
-- credential path is bound to a single configured organization; and the codebase
-- is full of CROSS_TENANT_*_DENIED. That is the right default and this migration
-- does not weaken it.
--
-- It adds one deliberate exception: a small number of named accounts who can see
-- balances and job execution across tenants, because somebody has to answer
-- "did this customer's top-up land" without asking the customer to screen-share.
--
-- What makes the exception affordable
-- -----------------------------------
-- The exception is not a role that bypasses row level security. It is a set of
-- functions, and the tables they read are not readable by the role that calls
-- them. Every function does the same three things before returning anything:
-- check the caller is a live administrator, write an access log row naming the
-- tenant being read, and only then read. Skipping the check is not possible
-- because the data only comes out of the function.
--
-- Why denials return a status instead of raising
-- ----------------------------------------------
-- A RAISE would roll back the transaction, and the access log row written just
-- before it would go with it -- so the one case most worth auditing, a refused
-- access, would be the one case that leaves no trace. Every function here
-- therefore returns a status and writes its audit row on both paths. Callers
-- map DENIED_* to 403; a caller that ignores the status gets no data anyway,
-- because the denial path returns no rows.

-- ---------------------------------------------------------------------------
-- 1. Runtime role
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_platform_admin_runtime') THEN
        CREATE ROLE elmos_platform_admin_runtime NOLOGIN;
    END IF;
END;
$$;

COMMENT ON ROLE elmos_platform_admin_runtime IS
    'Non-login role for the platform administration surface. Granted EXECUTE on the elmos_platform_* functions and SELECT on nothing. It cannot read a wallet, a ledger or a job directly; the functions are the only door and every one of them audits.';

-- ---------------------------------------------------------------------------
-- 2. Who the administrators are
-- ---------------------------------------------------------------------------

CREATE TABLE platform_administrators (
    account_id varchar(96) PRIMARY KEY REFERENCES accounts(account_id),
    platform_role varchar(24) NOT NULL CHECK (platform_role IN (
        'PLATFORM_VIEWER', 'PLATFORM_OPERATOR', 'PLATFORM_APPROVER'
    )),
    granted_by varchar(96) REFERENCES accounts(account_id),
    granted_at timestamptz NOT NULL DEFAULT now(),
    grant_reason varchar(255) NOT NULL,
    revoked_at timestamptz,
    revoked_by varchar(96) REFERENCES accounts(account_id),
    revoke_reason varchar(255),
    state_version bigint NOT NULL DEFAULT 0,
    CONSTRAINT platform_administrators_revoke_shape CHECK (
        revoked_at IS NULL OR (revoked_by IS NOT NULL AND revoke_reason IS NOT NULL)
    )
);

CREATE INDEX platform_administrators_live_idx
    ON platform_administrators (platform_role) WHERE revoked_at IS NULL;

COMMENT ON TABLE platform_administrators IS
    'Accounts that may read across tenants. Deliberately NOT row level security isolated, for the same reason `accounts` is not: a platform administrator does not belong to a tenant. Reachable only through SECURITY DEFINER functions.';
COMMENT ON COLUMN platform_administrators.grant_reason IS
    'Required. Granting cross-tenant read to a person without recording why is how an access list stops being reviewable.';

-- ---------------------------------------------------------------------------
-- 3. What they looked at
-- ---------------------------------------------------------------------------

CREATE TABLE platform_admin_access_log (
    access_id varchar(96) PRIMARY KEY,
    admin_account_id varchar(96) NOT NULL,
    platform_role varchar(24),
    operation varchar(64) NOT NULL,
    target_organization_id varchar(96),
    target_ref varchar(160),
    result varchar(24) NOT NULL CHECK (result IN (
        'ALLOWED', 'DENIED_NOT_ADMIN', 'DENIED_ROLE', 'DENIED_POLICY'
    )),
    detail varchar(255),
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX platform_admin_access_log_admin_idx
    ON platform_admin_access_log (admin_account_id, occurred_at DESC);
CREATE INDEX platform_admin_access_log_target_idx
    ON platform_admin_access_log (target_organization_id, occurred_at DESC)
    WHERE target_organization_id IS NOT NULL;

CREATE TRIGGER platform_admin_access_log_append_only
BEFORE UPDATE OR DELETE ON platform_admin_access_log
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

COMMENT ON TABLE platform_admin_access_log IS
    'Every cross-tenant access attempt, allowed or refused. Append-only. This is the price of the row level security exemption above, and the reason it is defensible.';

-- ---------------------------------------------------------------------------
-- 4. Authorize + audit, as one act
-- ---------------------------------------------------------------------------
-- Deliberately one function rather than an authorize() and a separate audit():
-- two functions can be called separately, and the one that gets forgotten is
-- always the audit.

CREATE OR REPLACE FUNCTION elmos_platform_authorize(
    p_admin_account_id varchar,
    p_required_role varchar,
    p_operation varchar,
    p_target_organization_id varchar DEFAULT NULL,
    p_target_ref varchar DEFAULT NULL
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_role varchar(24);
    v_rank integer;
    v_required integer;
    v_result varchar(24);
BEGIN
    SELECT platform_role INTO v_role FROM platform_administrators
     WHERE account_id = p_admin_account_id AND revoked_at IS NULL;

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

    INSERT INTO platform_admin_access_log (
        access_id, admin_account_id, platform_role, operation,
        target_organization_id, target_ref, result)
    VALUES (
        'pal-' || md5(p_admin_account_id || ':' || p_operation || ':'
                      || coalesce(p_target_organization_id, '-') || ':'
                      || coalesce(p_target_ref, '-') || ':' || clock_timestamp()::text),
        p_admin_account_id, v_role, p_operation,
        p_target_organization_id, p_target_ref, v_result);

    RETURN v_result;
END;
$$;

COMMENT ON FUNCTION elmos_platform_authorize(varchar, varchar, varchar, varchar, varchar) IS
    'Decides and records in one step. Returns ALLOWED or a DENIED_* code; never raises, so that the audit row for a refusal survives rather than being rolled back with the refusal.';

-- ---------------------------------------------------------------------------
-- 4b. Resolving the caller
-- ---------------------------------------------------------------------------
-- The console session carries an actor id, not an account id -- and actor id is
-- sha256(organizationId + ':' + accountId) truncated, so it cannot be reversed.
-- It is also per (organization, account), while a platform administrator is
-- deliberately not scoped to an organization; the same person authenticating
-- through two of their tenants presents two different actor ids for one
-- administrator entry.
--
-- identity_membership_directory (V59) already holds both identifiers side by
-- side and is not tenant isolated, which is exactly the lookup this needs. The
-- alternative -- adding accountId to the sealed session payload -- would touch
-- the session format and invalidate every live session for a read-only feature.

CREATE INDEX IF NOT EXISTS identity_membership_directory_org_actor_idx
    ON identity_membership_directory (organization_id, actor_id)
    WHERE actor_id IS NOT NULL;

CREATE OR REPLACE FUNCTION elmos_platform_resolve_admin_account(
    p_organization_id varchar,
    p_actor_id varchar
) RETURNS varchar
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT d.account_id FROM identity_membership_directory d
     WHERE d.organization_id = p_organization_id
       AND d.actor_id = p_actor_id
       AND d.member_state <> 'REMOVED'
     LIMIT 1;
$$;

COMMENT ON FUNCTION elmos_platform_resolve_admin_account(varchar, varchar) IS
    'Maps a console session (organization + actor) back to the account it belongs to. Returns NULL when there is no live membership, which the caller must treat as "not an administrator" -- the platform administrator check that follows would refuse a NULL anyway, but failing here keeps a bad actor id out of the audit log as a named account.';

-- ---------------------------------------------------------------------------
-- 5. Cross-tenant reads
-- ---------------------------------------------------------------------------
-- Each iterates organizations (that table is not tenant isolated) and binds each
-- tenant in turn. That is slower than a projection table holding every balance
-- in the clear, and it is the point: there is no second copy of anyone's balance
-- sitting outside row level security waiting to be read by the next thing that
-- gets a SELECT grant.

CREATE OR REPLACE FUNCTION elmos_platform_wallet_overview(
    p_admin_account_id varchar,
    p_after_organization_id varchar DEFAULT NULL,
    p_limit integer DEFAULT 50
) RETURNS TABLE (
    organization_id varchar, display_name varchar, currency char,
    balance_minor numeric, reserved_minor numeric, spendable_minor numeric,
    wallet_status varchar, held_reservations bigint, updated_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_previous text;
    v_org record;
BEGIN
    IF elmos_platform_authorize(p_admin_account_id, 'PLATFORM_VIEWER',
                                'WALLET_OVERVIEW') <> 'ALLOWED' THEN
        RETURN;
    END IF;

    v_previous := coalesce(current_setting('app.organization_id', true), '');
    FOR v_org IN
        SELECT o.organization_id, o.display_name FROM organizations o
         WHERE p_after_organization_id IS NULL
            OR o.organization_id > p_after_organization_id
         ORDER BY o.organization_id
         LIMIT greatest(coalesce(p_limit, 50), 1)
    LOOP
        PERFORM set_config('app.organization_id', v_org.organization_id, true);
        RETURN QUERY
        SELECT w.organization_id, v_org.display_name, w.currency,
               w.balance_minor, w.reserved_minor,
               w.balance_minor - w.reserved_minor,
               w.status,
               (SELECT count(*) FROM wallet_reservations r
                 WHERE r.organization_id = w.organization_id AND r.status = 'HELD'),
               w.updated_at
          FROM wallet_accounts w
         WHERE w.organization_id = v_org.organization_id;
    END LOOP;
    PERFORM set_config('app.organization_id', v_previous, true);
END;
$$;

CREATE OR REPLACE FUNCTION elmos_platform_wallet_ledger(
    p_admin_account_id varchar,
    p_organization_id varchar,
    p_limit integer DEFAULT 50,
    p_offset integer DEFAULT 0
) RETURNS TABLE (
    entry_id varchar, seq bigint, direction varchar, amount_minor numeric,
    balance_after_minor numeric, entry_type varchar, source_type varchar,
    source_ref varchar, actor_id varchar, reason varchar, occurred_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_previous text;
BEGIN
    IF elmos_platform_authorize(p_admin_account_id, 'PLATFORM_VIEWER',
                                'WALLET_LEDGER', p_organization_id) <> 'ALLOWED' THEN
        RETURN;
    END IF;

    v_previous := elmos_wallet_bind_tenant(p_organization_id);
    RETURN QUERY
    SELECT l.entry_id, l.seq, l.direction, l.amount_minor, l.balance_after_minor,
           l.entry_type, l.source_type, l.source_ref, l.actor_id, l.reason, l.occurred_at
      FROM wallet_ledger_entries l
     WHERE l.organization_id = p_organization_id
     ORDER BY l.seq DESC
     LIMIT greatest(coalesce(p_limit, 50), 1) OFFSET greatest(coalesce(p_offset, 0), 0);
    PERFORM set_config('app.organization_id', v_previous, true);
END;
$$;

/**
 * Top-up orders across tenants, newest first.
 *
 * The directory projection already exists and is not tenant isolated, which is
 * exactly the shape this needs -- but it carries only the resolution mapping, so
 * the per-order detail still comes from the isolated table under a bound tenant.
 */
CREATE OR REPLACE FUNCTION elmos_platform_topup_orders(
    p_admin_account_id varchar,
    p_status_filter varchar DEFAULT NULL,
    p_limit integer DEFAULT 50
) RETURNS TABLE (
    topup_order_id varchar, organization_id varchar, actor_id varchar,
    amount_minor numeric, provider varchar, out_trade_no varchar,
    status varchar, created_at timestamptz, paid_at timestamptz,
    credited_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_previous text;
    v_row record;
BEGIN
    IF elmos_platform_authorize(p_admin_account_id, 'PLATFORM_VIEWER',
                                'TOPUP_ORDERS', NULL, p_status_filter) <> 'ALLOWED' THEN
        RETURN;
    END IF;

    v_previous := coalesce(current_setting('app.organization_id', true), '');
    FOR v_row IN
        SELECT d.topup_order_id, d.organization_id
          FROM wallet_topup_order_directory d
         WHERE p_status_filter IS NULL OR d.status = p_status_filter
         ORDER BY d.created_at DESC
         LIMIT greatest(coalesce(p_limit, 50), 1)
    LOOP
        PERFORM set_config('app.organization_id', v_row.organization_id, true);
        RETURN QUERY
        SELECT t.topup_order_id, t.organization_id, t.actor_id, t.amount_minor,
               t.provider, t.out_trade_no, t.status, t.created_at, t.paid_at, t.credited_at
          FROM wallet_topup_orders t
         WHERE t.topup_order_id = v_row.topup_order_id;
    END LOOP;
    PERFORM set_config('app.organization_id', v_previous, true);
END;
$$;

/**
 * Job execution across tenants.
 *
 * Driven from execution_job_dispatch where possible -- it is already exempt from
 * isolation and carries no customer content -- but the interesting columns
 * (status, failure code, timing) live on the isolated table, so each row is read
 * under its own bound tenant.
 */
CREATE OR REPLACE FUNCTION elmos_platform_job_overview(
    p_admin_account_id varchar,
    p_status_filter varchar DEFAULT NULL,
    p_organization_filter varchar DEFAULT NULL,
    -- Per organization, not a total. The rows have to be gathered tenant by
    -- tenant, so a global "latest N" would mean reading every tenant's page and
    -- throwing most of it away. Named for what it does rather than for what a
    -- reader might assume.
    p_limit_per_organization integer DEFAULT 50
) RETURNS TABLE (
    job_id varchar, organization_id varchar, business_line varchar, job_kind varchar,
    status varchar, result_status varchar, failure_code varchar,
    created_at timestamptz, started_at timestamptz, finished_at timestamptz,
    settled_amount_minor numeric, hold_status varchar
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_previous text;
    v_org record;
BEGIN
    IF elmos_platform_authorize(p_admin_account_id, 'PLATFORM_VIEWER',
                                'JOB_OVERVIEW', p_organization_filter,
                                p_status_filter) <> 'ALLOWED' THEN
        RETURN;
    END IF;

    v_previous := coalesce(current_setting('app.organization_id', true), '');
    FOR v_org IN
        SELECT o.organization_id FROM organizations o
         WHERE p_organization_filter IS NULL OR o.organization_id = p_organization_filter
         ORDER BY o.organization_id
    LOOP
        PERFORM set_config('app.organization_id', v_org.organization_id, true);
        RETURN QUERY
        SELECT j.job_id, j.organization_id, j.business_line, j.job_kind,
               j.status, j.result_status, j.failure_code,
               j.created_at, j.started_at, j.finished_at,
               r.settled_amount_minor, r.status
          FROM execution_jobs j
          LEFT JOIN wallet_reservations r
                 ON r.organization_id = j.organization_id AND r.job_id = j.job_id
         -- Explicit, not left to row level security.
         --
         -- The first version omitted this and relied on the bound tenant to
         -- scope the read. It does, in production. It does NOT when the owner
         -- bypasses RLS, and the first superuser run returned every job once per
         -- organization -- four copies of each row. A query whose correctness
         -- depends on a policy being enforced is a query that silently changes
         -- meaning with the deployment. RLS is the safety net here, not the
         -- filter.
         WHERE j.organization_id = v_org.organization_id
           AND (p_status_filter IS NULL OR j.status = p_status_filter)
         ORDER BY j.created_at DESC
         LIMIT greatest(coalesce(p_limit_per_organization, 50), 1);
    END LOOP;
    PERFORM set_config('app.organization_id', v_previous, true);
END;
$$;

-- ---------------------------------------------------------------------------
-- 6. The one cross-tenant write
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_platform_wallet_adjust(
    p_admin_account_id varchar,
    p_organization_id varchar,
    p_direction varchar,
    p_amount_minor numeric,
    p_reason varchar,
    p_idempotency_key varchar
) RETURNS TABLE (status varchar, entry_id varchar)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_decision varchar(24);
    v_entry varchar(96);
BEGIN
    -- APPROVER, not OPERATOR. Moving a balance by hand is the most dangerous
    -- thing in this subsystem and the only one with no compensating record
    -- elsewhere -- there is no payment, no job, nothing to reconcile against
    -- except the reason the administrator typed.
    v_decision := elmos_platform_authorize(
        p_admin_account_id, 'PLATFORM_APPROVER', 'WALLET_ADJUST',
        p_organization_id, p_direction || ':' || p_amount_minor::text);
    IF v_decision <> 'ALLOWED' THEN
        RETURN QUERY SELECT v_decision, NULL::varchar;
        RETURN;
    END IF;

    -- The reason recorded on the ledger entry names the administrator, so the
    -- ledger alone answers "who did this and why" without joining the audit log.
    v_entry := elmos_wallet_adjust(
        p_organization_id, p_direction, p_amount_minor,
        'platform:' || p_admin_account_id,
        p_reason || ' [by ' || p_admin_account_id || ']',
        p_idempotency_key);

    RETURN QUERY SELECT 'ALLOWED'::varchar, v_entry;
END;
$$;

-- ---------------------------------------------------------------------------
-- 7. Granting and revoking
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_platform_grant_admin(
    p_admin_account_id varchar,
    p_target_account_id varchar,
    p_platform_role varchar,
    p_reason varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_decision varchar(24);
BEGIN
    IF p_reason IS NULL OR length(btrim(p_reason)) = 0 THEN
        RETURN 'DENIED_POLICY';
    END IF;

    v_decision := elmos_platform_authorize(
        p_admin_account_id, 'PLATFORM_APPROVER', 'GRANT_ADMIN', NULL,
        p_target_account_id || ':' || p_platform_role);
    IF v_decision <> 'ALLOWED' THEN
        RETURN v_decision;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM accounts WHERE account_id = p_target_account_id) THEN
        RETURN 'DENIED_POLICY';
    END IF;

    INSERT INTO platform_administrators (
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

/**
 * Revoking the last live approver is refused.
 *
 * Not paternalism: with no approver left, nobody can grant one, and the only way
 * back is a direct database session -- which is precisely the access this table
 * exists to make unnecessary. Revoking yourself is allowed, as long as you are
 * not the last one.
 */
CREATE OR REPLACE FUNCTION elmos_platform_revoke_admin(
    p_admin_account_id varchar,
    p_target_account_id varchar,
    p_reason varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_decision varchar(24);
    v_target_role varchar(24);
    v_live_approvers integer;
BEGIN
    IF p_reason IS NULL OR length(btrim(p_reason)) = 0 THEN
        RETURN 'DENIED_POLICY';
    END IF;

    v_decision := elmos_platform_authorize(
        p_admin_account_id, 'PLATFORM_APPROVER', 'REVOKE_ADMIN', NULL, p_target_account_id);
    IF v_decision <> 'ALLOWED' THEN
        RETURN v_decision;
    END IF;

    SELECT platform_role INTO v_target_role FROM platform_administrators
     WHERE account_id = p_target_account_id AND revoked_at IS NULL;
    IF NOT FOUND THEN
        RETURN 'DENIED_POLICY';
    END IF;

    IF v_target_role = 'PLATFORM_APPROVER' THEN
        SELECT count(*) INTO v_live_approvers FROM platform_administrators
         WHERE platform_role = 'PLATFORM_APPROVER' AND revoked_at IS NULL;
        IF v_live_approvers <= 1 THEN
            INSERT INTO platform_admin_access_log (
                access_id, admin_account_id, platform_role, operation,
                target_ref, result, detail)
            VALUES (
                'pal-' || md5(p_admin_account_id || ':lastapprover:' || clock_timestamp()::text),
                p_admin_account_id, 'PLATFORM_APPROVER', 'REVOKE_ADMIN',
                p_target_account_id, 'DENIED_POLICY',
                'refused: this is the last live PLATFORM_APPROVER');
            RETURN 'DENIED_LAST_APPROVER';
        END IF;
    END IF;

    UPDATE platform_administrators
       SET revoked_at = now(), revoked_by = p_admin_account_id, revoke_reason = p_reason,
           state_version = state_version + 1
     WHERE account_id = p_target_account_id;
    RETURN 'ALLOWED';
END;
$$;

-- ---------------------------------------------------------------------------
-- 8. Bootstrap
-- ---------------------------------------------------------------------------
-- The first administrator cannot be granted through the functions above, since
-- they all require an existing approver. It is deliberately not seeded here
-- either: a migration that installs a fixed administrator puts the same identity
-- in every environment including every test database.
--
-- The bootstrap path is an operator with a direct database session calling this
-- function, which is the same access level as editing the table by hand -- but
-- leaves an audit row saying so. `elmosctl platform-admin bootstrap` wraps it.

CREATE OR REPLACE FUNCTION elmos_platform_bootstrap_admin(
    p_target_account_id varchar,
    p_reason varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM platform_administrators
                WHERE platform_role = 'PLATFORM_APPROVER' AND revoked_at IS NULL) THEN
        -- Once an approver exists, grants go through the audited path. Leaving
        -- this open would be a permanent unaudited way to mint administrators.
        RETURN 'DENIED_POLICY';
    END IF;
    IF p_reason IS NULL OR length(btrim(p_reason)) = 0
       OR NOT EXISTS (SELECT 1 FROM accounts WHERE account_id = p_target_account_id) THEN
        RETURN 'DENIED_POLICY';
    END IF;

    INSERT INTO platform_administrators (account_id, platform_role, grant_reason)
    VALUES (p_target_account_id, 'PLATFORM_APPROVER', p_reason)
    ON CONFLICT (account_id) DO UPDATE
        SET platform_role = 'PLATFORM_APPROVER', revoked_at = NULL,
            grant_reason = EXCLUDED.grant_reason,
            state_version = platform_administrators.state_version + 1;

    INSERT INTO platform_admin_access_log (
        access_id, admin_account_id, platform_role, operation, target_ref, result, detail)
    VALUES (
        'pal-' || md5('bootstrap:' || p_target_account_id || ':' || clock_timestamp()::text),
        p_target_account_id, 'PLATFORM_APPROVER', 'BOOTSTRAP_ADMIN',
        p_target_account_id, 'ALLOWED', p_reason);
    RETURN 'ALLOWED';
END;
$$;

-- ---------------------------------------------------------------------------
-- 9. Grants
-- ---------------------------------------------------------------------------

DO $$
DECLARE v_function record;
BEGIN
    FOR v_function IN
        SELECT p.oid::regprocedure AS signature
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public' AND p.proname LIKE 'elmos_platform_%'
    LOOP
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', v_function.signature);
    END LOOP;
END;
$$;

REVOKE ALL ON platform_administrators FROM PUBLIC;
REVOKE ALL ON platform_admin_access_log FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_platform_admin_runtime') THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_platform_resolve_admin_account(varchar, varchar) TO elmos_platform_admin_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_platform_wallet_overview(varchar, varchar, integer) TO elmos_platform_admin_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_platform_wallet_ledger(varchar, varchar, integer, integer) TO elmos_platform_admin_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_platform_topup_orders(varchar, varchar, integer) TO elmos_platform_admin_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_platform_job_overview(varchar, varchar, varchar, integer) TO elmos_platform_admin_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_platform_wallet_adjust(varchar, varchar, varchar, numeric, varchar, varchar) TO elmos_platform_admin_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_platform_grant_admin(varchar, varchar, varchar, varchar) TO elmos_platform_admin_runtime';
        EXECUTE 'GRANT EXECUTE ON FUNCTION elmos_platform_revoke_admin(varchar, varchar, varchar) TO elmos_platform_admin_runtime';
        -- Deliberately NOT granted: elmos_platform_bootstrap_admin. It is for a
        -- direct operator session only, never for the application role.
    END IF;
END;
$$;
