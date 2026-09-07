-- Coordinate snapshot artifact reads with archive/GC and make reconciliation globally schedulable.
-- All externally callable operations are exact, fenced SECURITY DEFINER functions; the runtime
-- role receives no direct access to the global queue or fencing counter.

CREATE TABLE snapshot_materialization_fences (
    organization_id varchar(64) NOT NULL,
    repository_id varchar(64) NOT NULL,
    snapshot_id varchar(64) NOT NULL,
    fencing_token bigint NOT NULL CHECK (fencing_token > 0),
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (organization_id, repository_id, snapshot_id),
    FOREIGN KEY (organization_id, repository_id, snapshot_id)
        REFERENCES repository_snapshots(organization_id, repository_id, snapshot_id)
);

CREATE TABLE snapshot_materialization_leases (
    organization_id varchar(64) NOT NULL,
    repository_id varchar(64) NOT NULL,
    snapshot_id varchar(64) NOT NULL,
    lease_id varchar(64) NOT NULL
        CHECK (lease_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'),
    holder_id varchar(128) NOT NULL
        CHECK (holder_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    fencing_token bigint NOT NULL CHECK (fencing_token > 0),
    acquired_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    released_at timestamptz,
    release_reason varchar(32)
        CHECK (release_reason IN ('CLIENT_RELEASE', 'EXPIRED_RELEASE', 'EXPIRED_RECLAIM')),
    PRIMARY KEY (organization_id, lease_id),
    UNIQUE (organization_id, repository_id, snapshot_id, fencing_token),
    FOREIGN KEY (organization_id, repository_id, snapshot_id)
        REFERENCES repository_snapshots(organization_id, repository_id, snapshot_id),
    CONSTRAINT snapshot_materialization_lease_time_ck CHECK (
        expires_at > acquired_at
        AND updated_at >= acquired_at
        AND (released_at IS NULL OR released_at >= acquired_at)
    ),
    CONSTRAINT snapshot_materialization_lease_release_ck CHECK (
        (released_at IS NULL) = (release_reason IS NULL)
    )
);

CREATE INDEX snapshot_materialization_active_idx
    ON snapshot_materialization_leases (
        organization_id, repository_id, snapshot_id, expires_at)
    WHERE released_at IS NULL;

REVOKE ALL ON TABLE snapshot_materialization_fences FROM PUBLIC;
REVOKE ALL ON TABLE snapshot_materialization_leases FROM PUBLIC;

CREATE FUNCTION public.elmos_enforce_snapshot_materialization_lease_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.released_at IS NOT NULL
           OR NEW.release_reason IS NOT NULL
           OR NEW.updated_at IS DISTINCT FROM NEW.acquired_at THEN
            RAISE EXCEPTION 'snapshot materialization lease must start active';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'snapshot materialization lease history is append-preserving';
    END IF;
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.repository_id IS DISTINCT FROM OLD.repository_id
       OR NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id
       OR NEW.lease_id IS DISTINCT FROM OLD.lease_id
       OR NEW.holder_id IS DISTINCT FROM OLD.holder_id
       OR NEW.fencing_token IS DISTINCT FROM OLD.fencing_token
       OR NEW.acquired_at IS DISTINCT FROM OLD.acquired_at THEN
        RAISE EXCEPTION 'snapshot materialization lease identity is immutable';
    END IF;
    IF OLD.released_at IS NOT NULL AND NEW IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'released snapshot materialization lease is immutable';
    END IF;
    IF NEW.expires_at < OLD.expires_at OR NEW.updated_at < OLD.updated_at THEN
        RAISE EXCEPTION 'snapshot materialization lease time moved backwards';
    END IF;
    IF OLD.released_at IS NULL AND NEW.released_at IS NOT NULL
       AND NEW.release_reason IS NULL THEN
        RAISE EXCEPTION 'snapshot materialization lease release reason is required';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER snapshot_materialization_lease_transition
BEFORE INSERT OR UPDATE OR DELETE ON snapshot_materialization_leases
FOR EACH ROW EXECUTE FUNCTION
    public.elmos_enforce_snapshot_materialization_lease_transition();

ALTER TABLE snapshot_materialization_leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE snapshot_materialization_leases FORCE ROW LEVEL SECURITY;
CREATE POLICY snapshot_materialization_lease_tenant_isolation
ON snapshot_materialization_leases
USING (organization_id = current_setting('app.organization_id', true))
WITH CHECK (organization_id = current_setting('app.organization_id', true));

CREATE FUNCTION public.elmos_acquire_snapshot_materialization_lease(
    requested_organization_id varchar,
    requested_repository_id varchar,
    requested_snapshot_id varchar,
    requested_lease_id varchar,
    requested_holder_id varchar,
    requested_duration_seconds integer
)
RETURNS TABLE (
    lease_organization_id varchar,
    lease_repository_id varchar,
    lease_snapshot_id varchar,
    lease_identifier varchar,
    lease_holder_id varchar,
    lease_fencing_token bigint,
    lease_acquired_at timestamptz,
    lease_expires_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    database_now timestamptz := clock_timestamp();
    trusted_organization_id varchar := current_setting('app.organization_id', true);
    snapshot_status varchar;
    existing snapshot_materialization_leases%ROWTYPE;
    next_fence bigint;
BEGIN
    IF requested_organization_id IS NULL
       OR requested_organization_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'
       OR requested_repository_id IS NULL
       OR requested_repository_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'
       OR requested_snapshot_id IS NULL
       OR requested_snapshot_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'
       OR requested_lease_id IS NULL
       OR requested_lease_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'
       OR requested_holder_id IS NULL
       OR requested_holder_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
       OR requested_duration_seconds IS NULL
       OR requested_duration_seconds < 15
       OR requested_duration_seconds > 3600 THEN
        RAISE EXCEPTION 'snapshot materialization lease request is invalid';
    END IF;
    IF trusted_organization_id IS NULL
       OR trusted_organization_id IS DISTINCT FROM requested_organization_id THEN
        RAISE EXCEPTION 'snapshot materialization tenant context is missing or conflicting';
    END IF;
    PERFORM set_config('app.organization_id', requested_organization_id, true);

    SELECT snapshot.status
      INTO snapshot_status
      FROM public.repository_snapshots snapshot
     WHERE snapshot.organization_id = requested_organization_id
       AND snapshot.repository_id = requested_repository_id
       AND snapshot.snapshot_id = requested_snapshot_id
     FOR UPDATE;
    IF NOT FOUND OR snapshot_status <> 'AVAILABLE' THEN
        RAISE EXCEPTION 'snapshot is unavailable for materialization';
    END IF;

    SELECT lease.*
      INTO existing
      FROM public.snapshot_materialization_leases lease
     WHERE lease.organization_id = requested_organization_id
       AND lease.lease_id = requested_lease_id
     FOR UPDATE;
    IF FOUND THEN
        IF existing.repository_id IS DISTINCT FROM requested_repository_id
           OR existing.snapshot_id IS DISTINCT FROM requested_snapshot_id
           OR existing.holder_id IS DISTINCT FROM requested_holder_id THEN
            RAISE EXCEPTION 'materialization lease id is bound to another resource';
        END IF;
        IF existing.released_at IS NULL AND existing.expires_at > database_now THEN
            RETURN QUERY SELECT existing.organization_id, existing.repository_id,
                existing.snapshot_id, existing.lease_id, existing.holder_id,
                existing.fencing_token, existing.acquired_at, existing.expires_at;
            RETURN;
        END IF;
        RAISE EXCEPTION 'materialization lease id has already completed';
    END IF;

    UPDATE public.snapshot_materialization_leases lease
       SET released_at = database_now,
           release_reason = 'EXPIRED_RECLAIM',
           updated_at = database_now
     WHERE lease.organization_id = requested_organization_id
       AND lease.repository_id = requested_repository_id
       AND lease.snapshot_id = requested_snapshot_id
       AND lease.released_at IS NULL
       AND lease.expires_at <= database_now;

    IF EXISTS (
        SELECT 1
          FROM public.snapshot_materialization_leases lease
         WHERE lease.organization_id = requested_organization_id
           AND lease.repository_id = requested_repository_id
           AND lease.snapshot_id = requested_snapshot_id
           AND lease.released_at IS NULL
           AND lease.expires_at > database_now
    ) THEN
        RAISE EXCEPTION 'snapshot already has an active materialization lease';
    END IF;

    INSERT INTO public.snapshot_materialization_fences(
        organization_id, repository_id, snapshot_id, fencing_token, updated_at)
    VALUES (requested_organization_id, requested_repository_id,
            requested_snapshot_id, 1, database_now)
    ON CONFLICT (organization_id, repository_id, snapshot_id) DO UPDATE
       SET fencing_token = snapshot_materialization_fences.fencing_token + 1,
           updated_at = excluded.updated_at
    RETURNING fencing_token INTO next_fence;

    INSERT INTO public.snapshot_materialization_leases(
        organization_id, repository_id, snapshot_id, lease_id, holder_id,
        fencing_token, acquired_at, expires_at, updated_at)
    VALUES (requested_organization_id, requested_repository_id,
            requested_snapshot_id, requested_lease_id, requested_holder_id,
            next_fence, database_now,
            database_now + make_interval(secs => requested_duration_seconds), database_now);

    RETURN QUERY SELECT requested_organization_id, requested_repository_id,
        requested_snapshot_id, requested_lease_id, requested_holder_id,
        next_fence, database_now,
        database_now + make_interval(secs => requested_duration_seconds);
END;
$$;

CREATE FUNCTION public.elmos_renew_snapshot_materialization_lease(
    requested_organization_id varchar,
    requested_repository_id varchar,
    requested_snapshot_id varchar,
    requested_lease_id varchar,
    requested_holder_id varchar,
    requested_fencing_token bigint,
    requested_duration_seconds integer
)
RETURNS TABLE (
    lease_organization_id varchar,
    lease_repository_id varchar,
    lease_snapshot_id varchar,
    lease_identifier varchar,
    lease_holder_id varchar,
    lease_fencing_token bigint,
    lease_acquired_at timestamptz,
    lease_expires_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    database_now timestamptz := clock_timestamp();
    trusted_organization_id varchar := current_setting('app.organization_id', true);
    snapshot_status varchar;
    current_lease snapshot_materialization_leases%ROWTYPE;
BEGIN
    IF requested_duration_seconds IS NULL
       OR requested_duration_seconds < 15
       OR requested_duration_seconds > 3600
       OR requested_fencing_token IS NULL
       OR requested_fencing_token < 1 THEN
        RAISE EXCEPTION 'snapshot materialization renewal is invalid';
    END IF;
    IF trusted_organization_id IS NULL
       OR trusted_organization_id IS DISTINCT FROM requested_organization_id THEN
        RAISE EXCEPTION 'snapshot materialization tenant context is missing or conflicting';
    END IF;
    PERFORM set_config('app.organization_id', requested_organization_id, true);
    SELECT snapshot.status INTO snapshot_status
      FROM public.repository_snapshots snapshot
     WHERE snapshot.organization_id = requested_organization_id
       AND snapshot.repository_id = requested_repository_id
       AND snapshot.snapshot_id = requested_snapshot_id
     FOR UPDATE;
    IF NOT FOUND OR snapshot_status <> 'AVAILABLE' THEN
        RAISE EXCEPTION 'snapshot is unavailable for lease renewal';
    END IF;
    SELECT lease.* INTO current_lease
      FROM public.snapshot_materialization_leases lease
     WHERE lease.organization_id = requested_organization_id
       AND lease.lease_id = requested_lease_id
     FOR UPDATE;
    IF NOT FOUND
       OR current_lease.repository_id IS DISTINCT FROM requested_repository_id
       OR current_lease.snapshot_id IS DISTINCT FROM requested_snapshot_id
       OR current_lease.holder_id IS DISTINCT FROM requested_holder_id
       OR current_lease.fencing_token IS DISTINCT FROM requested_fencing_token
       OR current_lease.released_at IS NOT NULL
       OR current_lease.expires_at <= database_now THEN
        RAISE EXCEPTION 'snapshot materialization lease is stale';
    END IF;
    UPDATE public.snapshot_materialization_leases lease
       SET expires_at = database_now + make_interval(secs => requested_duration_seconds),
           updated_at = database_now
     WHERE lease.organization_id = requested_organization_id
       AND lease.lease_id = requested_lease_id;
    RETURN QUERY SELECT current_lease.organization_id, current_lease.repository_id,
        current_lease.snapshot_id, current_lease.lease_id, current_lease.holder_id,
        current_lease.fencing_token, current_lease.acquired_at,
        database_now + make_interval(secs => requested_duration_seconds);
END;
$$;

CREATE FUNCTION public.elmos_require_active_snapshot_materialization_lease(
    requested_organization_id varchar,
    requested_repository_id varchar,
    requested_snapshot_id varchar,
    requested_lease_id varchar,
    requested_holder_id varchar,
    requested_fencing_token bigint
)
RETURNS TABLE (
    lease_organization_id varchar,
    lease_repository_id varchar,
    lease_snapshot_id varchar,
    lease_identifier varchar,
    lease_holder_id varchar,
    lease_fencing_token bigint,
    lease_acquired_at timestamptz,
    lease_expires_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    database_now timestamptz := clock_timestamp();
    trusted_organization_id varchar := current_setting('app.organization_id', true);
    snapshot_status varchar;
    current_lease snapshot_materialization_leases%ROWTYPE;
BEGIN
    IF trusted_organization_id IS NULL
       OR trusted_organization_id IS DISTINCT FROM requested_organization_id THEN
        RAISE EXCEPTION 'snapshot materialization tenant context is missing or conflicting';
    END IF;
    PERFORM set_config('app.organization_id', requested_organization_id, true);
    SELECT snapshot.status INTO snapshot_status
      FROM public.repository_snapshots snapshot
     WHERE snapshot.organization_id = requested_organization_id
       AND snapshot.repository_id = requested_repository_id
       AND snapshot.snapshot_id = requested_snapshot_id
     FOR SHARE;
    SELECT lease.* INTO current_lease
      FROM public.snapshot_materialization_leases lease
     WHERE lease.organization_id = requested_organization_id
       AND lease.lease_id = requested_lease_id
     FOR SHARE;
    IF snapshot_status IS DISTINCT FROM 'AVAILABLE'
       OR NOT FOUND
       OR current_lease.repository_id IS DISTINCT FROM requested_repository_id
       OR current_lease.snapshot_id IS DISTINCT FROM requested_snapshot_id
       OR current_lease.holder_id IS DISTINCT FROM requested_holder_id
       OR current_lease.fencing_token IS DISTINCT FROM requested_fencing_token
       OR current_lease.released_at IS NOT NULL
       OR current_lease.expires_at <= database_now THEN
        RAISE EXCEPTION 'snapshot materialization lease is not active';
    END IF;
    RETURN QUERY SELECT current_lease.organization_id, current_lease.repository_id,
        current_lease.snapshot_id, current_lease.lease_id, current_lease.holder_id,
        current_lease.fencing_token, current_lease.acquired_at, current_lease.expires_at;
END;
$$;

CREATE FUNCTION public.elmos_release_snapshot_materialization_lease(
    requested_organization_id varchar,
    requested_repository_id varchar,
    requested_snapshot_id varchar,
    requested_lease_id varchar,
    requested_holder_id varchar,
    requested_fencing_token bigint
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    database_now timestamptz := clock_timestamp();
    trusted_organization_id varchar := current_setting('app.organization_id', true);
    current_lease snapshot_materialization_leases%ROWTYPE;
BEGIN
    IF trusted_organization_id IS NULL
       OR trusted_organization_id IS DISTINCT FROM requested_organization_id THEN
        RAISE EXCEPTION 'snapshot materialization tenant context is missing or conflicting';
    END IF;
    PERFORM set_config('app.organization_id', requested_organization_id, true);
    SELECT lease.* INTO current_lease
      FROM public.snapshot_materialization_leases lease
     WHERE lease.organization_id = requested_organization_id
       AND lease.lease_id = requested_lease_id
     FOR UPDATE;
    IF NOT FOUND
       OR current_lease.repository_id IS DISTINCT FROM requested_repository_id
       OR current_lease.snapshot_id IS DISTINCT FROM requested_snapshot_id
       OR current_lease.holder_id IS DISTINCT FROM requested_holder_id
       OR current_lease.fencing_token IS DISTINCT FROM requested_fencing_token THEN
        RAISE EXCEPTION 'snapshot materialization release has a stale fence';
    END IF;
    IF current_lease.released_at IS NOT NULL THEN
        RETURN true;
    END IF;
    UPDATE public.snapshot_materialization_leases lease
       SET released_at = database_now,
           release_reason = CASE WHEN current_lease.expires_at <= database_now
               THEN 'EXPIRED_RELEASE' ELSE 'CLIENT_RELEASE' END,
           updated_at = database_now
     WHERE lease.organization_id = requested_organization_id
       AND lease.lease_id = requested_lease_id;
    RETURN true;
END;
$$;

REVOKE ALL ON FUNCTION public.elmos_acquire_snapshot_materialization_lease(
    varchar, varchar, varchar, varchar, varchar, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.elmos_renew_snapshot_materialization_lease(
    varchar, varchar, varchar, varchar, varchar, bigint, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.elmos_require_active_snapshot_materialization_lease(
    varchar, varchar, varchar, varchar, varchar, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.elmos_release_snapshot_materialization_lease(
    varchar, varchar, varchar, varchar, varchar, bigint) FROM PUBLIC;

-- The snapshot row is the common serialization point: acquisition locks it before inserting a
-- lease, and AVAILABLE -> ARCHIVED locks it before this trigger checks active leases.
CREATE OR REPLACE FUNCTION public.enforce_repository_snapshot_lifecycle()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'AVAILABLE' THEN
            RAISE EXCEPTION 'repository snapshot must start available';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'repository snapshots are append-preserving';
    END IF;
    IF (to_jsonb(NEW) - 'status') IS DISTINCT FROM
       (to_jsonb(OLD) - 'status') THEN
        RAISE EXCEPTION 'repository snapshot identity and content are immutable';
    END IF;
    IF NEW.status = OLD.status THEN
        RETURN NEW;
    END IF;
    IF OLD.status <> 'AVAILABLE' OR NEW.status <> 'ARCHIVED' THEN
        RAISE EXCEPTION 'invalid repository snapshot lifecycle transition';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM public.snapshot_materialization_leases lease
         WHERE lease.organization_id = OLD.organization_id
           AND lease.repository_id = OLD.repository_id
           AND lease.snapshot_id = OLD.snapshot_id
           AND lease.released_at IS NULL
           AND lease.expires_at > clock_timestamp()
    ) THEN
        RAISE EXCEPTION 'snapshot has an active materialization lease'
            USING ERRCODE = '55006';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.enforce_repository_snapshot_lifecycle() FROM PUBLIC;

-- Private, cross-tenant work index. Tenant IDs originate only from the journal's constrained
-- organization_id; application callers can claim/complete leases only through the exact API.
CREATE TABLE snapshot_reconciliation_tenant_work (
    organization_id varchar(64) PRIMARY KEY REFERENCES organizations(organization_id),
    work_pending boolean NOT NULL,
    next_attempt_at timestamptz NOT NULL,
    lease_owner varchar(128)
        CHECK (lease_owner ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    lease_until timestamptz,
    fencing_token bigint NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
    last_completed_fencing_token bigint,
    last_completed_by varchar(128)
        CHECK (last_completed_by ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    consecutive_failures integer NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    updated_at timestamptz NOT NULL,
    CONSTRAINT snapshot_reconciliation_work_lease_shape CHECK (
        (lease_owner IS NULL) = (lease_until IS NULL)
        AND (last_completed_by IS NULL) = (last_completed_fencing_token IS NULL)
        AND (last_completed_fencing_token IS NULL
             OR last_completed_fencing_token <= fencing_token)
    )
);

CREATE INDEX snapshot_reconciliation_tenant_work_due_idx
    ON snapshot_reconciliation_tenant_work(next_attempt_at, organization_id)
    WHERE work_pending;

REVOKE ALL ON TABLE snapshot_reconciliation_tenant_work FROM PUBLIC;

INSERT INTO snapshot_reconciliation_tenant_work(
    organization_id, work_pending, next_attempt_at, updated_at)
SELECT organization_id, true, min(recorded_at), clock_timestamp()
  FROM snapshot_root_reconciliations
 WHERE phase <> 'RESOLVED'
 GROUP BY organization_id;

CREATE FUNCTION public.elmos_schedule_snapshot_reconciliation_work()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    database_now timestamptz := clock_timestamp();
BEGIN
    INSERT INTO public.snapshot_reconciliation_tenant_work(
        organization_id, work_pending, next_attempt_at, updated_at)
    VALUES (NEW.organization_id, true, database_now, database_now)
    ON CONFLICT (organization_id) DO UPDATE
       SET work_pending = true,
           next_attempt_at = least(
               snapshot_reconciliation_tenant_work.next_attempt_at,
               excluded.next_attempt_at),
           updated_at = excluded.updated_at;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.elmos_schedule_snapshot_reconciliation_work() FROM PUBLIC;

CREATE TRIGGER snapshot_reconciliation_global_work_sync
AFTER INSERT OR UPDATE OF phase ON snapshot_root_reconciliations
FOR EACH ROW EXECUTE FUNCTION public.elmos_schedule_snapshot_reconciliation_work();

CREATE FUNCTION public.elmos_claim_snapshot_reconciliation_work(
    requested_worker_id varchar,
    requested_limit integer,
    requested_lease_seconds integer
)
RETURNS TABLE (
    work_organization_id varchar,
    work_worker_id varchar,
    work_fencing_token bigint,
    work_expires_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    database_now timestamptz := clock_timestamp();
BEGIN
    IF requested_worker_id IS NULL
       OR requested_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
       OR requested_limit IS NULL OR requested_limit < 1 OR requested_limit > 64
       OR requested_lease_seconds IS NULL
       OR requested_lease_seconds < 15 OR requested_lease_seconds > 900 THEN
        RAISE EXCEPTION 'snapshot reconciliation work claim is invalid';
    END IF;
    RETURN QUERY
    WITH candidates AS (
        SELECT work.organization_id
          FROM public.snapshot_reconciliation_tenant_work work
         WHERE work.work_pending
           AND work.next_attempt_at <= database_now
           AND (work.lease_until IS NULL OR work.lease_until <= database_now)
         ORDER BY work.next_attempt_at, work.organization_id
         FOR UPDATE SKIP LOCKED
         LIMIT requested_limit
    ), claimed AS (
        UPDATE public.snapshot_reconciliation_tenant_work work
           SET lease_owner = requested_worker_id,
               lease_until = database_now
                   + make_interval(secs => requested_lease_seconds),
               fencing_token = work.fencing_token + 1,
               updated_at = database_now
          FROM candidates
         WHERE work.organization_id = candidates.organization_id
        RETURNING work.organization_id, work.fencing_token, work.lease_until
    )
    SELECT claimed.organization_id, requested_worker_id,
           claimed.fencing_token, claimed.lease_until
      FROM claimed
     ORDER BY claimed.organization_id;
END;
$$;

CREATE FUNCTION public.elmos_complete_snapshot_reconciliation_work(
    requested_organization_id varchar,
    requested_worker_id varchar,
    requested_fencing_token bigint,
    requested_successful boolean,
    requested_retry_seconds integer
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    database_now timestamptz := clock_timestamp();
    current_work snapshot_reconciliation_tenant_work%ROWTYPE;
    unresolved boolean;
BEGIN
    IF requested_organization_id IS NULL
       OR requested_organization_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'
       OR requested_worker_id IS NULL
       OR requested_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
       OR requested_fencing_token IS NULL OR requested_fencing_token < 1
       OR requested_successful IS NULL
       OR requested_retry_seconds IS NULL
       OR requested_retry_seconds < 0 OR requested_retry_seconds > 86400 THEN
        RAISE EXCEPTION 'snapshot reconciliation work completion is invalid';
    END IF;
    SELECT work.* INTO current_work
      FROM public.snapshot_reconciliation_tenant_work work
     WHERE work.organization_id = requested_organization_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'snapshot reconciliation work lease is missing';
    END IF;
    IF current_work.lease_owner IS NULL
       AND current_work.last_completed_fencing_token = requested_fencing_token
       AND current_work.last_completed_by IS NOT DISTINCT FROM requested_worker_id THEN
        RETURN current_work.work_pending;
    END IF;
    IF current_work.lease_owner IS DISTINCT FROM requested_worker_id
       OR current_work.fencing_token IS DISTINCT FROM requested_fencing_token
       OR current_work.lease_until IS NULL
       OR current_work.lease_until <= database_now THEN
        RAISE EXCEPTION 'snapshot reconciliation work lease is stale';
    END IF;
    PERFORM set_config('app.organization_id', requested_organization_id, true);
    SELECT EXISTS (
        SELECT 1
          FROM public.snapshot_root_reconciliations reconciliation
         WHERE reconciliation.organization_id = requested_organization_id
           AND reconciliation.phase <> 'RESOLVED'
    ) INTO unresolved;
    UPDATE public.snapshot_reconciliation_tenant_work work
       SET work_pending = unresolved,
           next_attempt_at = CASE WHEN unresolved
               THEN database_now + make_interval(secs => requested_retry_seconds)
               ELSE database_now END,
           lease_owner = NULL,
           lease_until = NULL,
           last_completed_fencing_token = requested_fencing_token,
           last_completed_by = requested_worker_id,
           consecutive_failures = CASE
               WHEN NOT unresolved OR requested_successful THEN 0
               ELSE work.consecutive_failures + 1 END,
           updated_at = database_now
     WHERE work.organization_id = requested_organization_id;
    RETURN unresolved;
END;
$$;

REVOKE ALL ON FUNCTION public.elmos_claim_snapshot_reconciliation_work(
    varchar, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.elmos_complete_snapshot_reconciliation_work(
    varchar, varchar, bigint, boolean, integer) FROM PUBLIC;
