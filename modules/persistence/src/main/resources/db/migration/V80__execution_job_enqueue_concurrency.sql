-- ELMOS V80: serialize tenant execution-job admission.
--
-- V52 introduced the hosted queue, V57 made its SECURITY DEFINER functions
-- tenant-aware, and V74 added wallet admission. Those migrations are immutable.
-- The V74 enqueue body still performed its idempotency lookup and queue-depth
-- check before acquiring a lock. Concurrent callers could therefore all observe
-- a missing idempotency row and the same spare queue slot before any of them
-- incremented the tenant counter.
--
-- This forward-only replacement keeps the V74 wallet gate and the V57 tenant
-- binding. It adds two complementary locks:
--
-- * a transaction advisory lock keyed by organization serializes the
--   missing-row idempotency decision, even before a counter row exists; and
-- * a row lock on execution_dispatch_org_counters serializes the queue-depth
--   decision with counter changes made by claim/reap/cancel transactions.
--
-- Hash collisions can only over-serialize unrelated tenants. They cannot let a
-- tenant exceed its limit or expose another tenant's rows.

CREATE OR REPLACE FUNCTION elmos_enqueue_execution_job(
    p_job_id varchar,
    p_organization_id varchar,
    p_actor_id varchar,
    p_business_line varchar,
    p_job_kind varchar,
    p_idempotency_key varchar,
    p_request_digest varchar,
    p_request_payload jsonb,
    p_required_capability varchar,
    p_runner_image varchar,
    p_priority smallint,
    p_budget_wall_seconds integer,
    p_max_attempts smallint
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $function$
DECLARE
    v_bound_organization_id text;
    v_existing public.execution_jobs%ROWTYPE;
    v_counter_created integer;
    v_leased integer;
    v_queued integer;
    v_limit integer;
BEGIN
    -- A transaction that is already tenant-bound may not use this definer
    -- function to switch to another tenant. An unbound trusted control-plane
    -- caller is still supported, and the function binds it before any RLS table
    -- is read.
    v_bound_organization_id := nullif(
        pg_catalog.btrim(pg_catalog.current_setting('app.organization_id', true)), '');
    IF v_bound_organization_id IS NOT NULL
       AND v_bound_organization_id IS DISTINCT FROM p_organization_id THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_TENANT_CONTEXT_MISMATCH';
    END IF;
    PERFORM pg_catalog.set_config('app.organization_id', p_organization_id, true);

    -- A row that does not exist cannot be SELECT ... FOR UPDATE. The advisory
    -- lock closes that gap for the (organization, idempotency key) first insert.
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(p_organization_id, 1162758739));

    SELECT * INTO v_existing
      FROM public.execution_jobs j
     WHERE j.organization_id = p_organization_id
       AND j.idempotency_key = p_idempotency_key
     FOR UPDATE;
    IF FOUND THEN
        IF v_existing.request_digest IS DISTINCT FROM p_request_digest THEN
            RAISE EXCEPTION 'ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.job_id;
    END IF;

    v_limit := public.elmos_execution_concurrency_limit(p_organization_id);
    IF v_limit < 1 THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_NO_ACTIVE_ENTITLEMENT';
    END IF;

    -- Repair a missing counter from the projection instead of assuming zero.
    -- ON CONFLICT may wait for a concurrent creator; the following row lock then
    -- makes the capacity check and increment one atomic critical section.
    INSERT INTO public.execution_dispatch_org_counters (
        organization_id, leased_count, queued_count)
    VALUES (p_organization_id, 0, 0)
    ON CONFLICT (organization_id) DO NOTHING;
    GET DIAGNOSTICS v_counter_created = ROW_COUNT;

    -- The normal path above is O(1). Only a newly recreated counter needs one
    -- bounded repair scan so an operationally removed counter cannot turn an
    -- existing queue into apparent free capacity.
    IF v_counter_created = 1 THEN
        SELECT count(*) FILTER (WHERE d.dispatch_state = 'LEASED')::integer,
               count(*) FILTER (WHERE d.dispatch_state = 'READY')::integer
          INTO v_leased, v_queued
          FROM public.execution_job_dispatch d
         WHERE d.organization_id = p_organization_id;
        UPDATE public.execution_dispatch_org_counters c
           SET leased_count = v_leased,
               queued_count = v_queued,
               updated_at = pg_catalog.now()
         WHERE c.organization_id = p_organization_id;
    END IF;

    SELECT c.queued_count INTO STRICT v_queued
      FROM public.execution_dispatch_org_counters c
     WHERE c.organization_id = p_organization_id
     FOR UPDATE;
    IF v_queued >= v_limit * 10 THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_QUEUE_DEPTH_EXCEEDED';
    END IF;

    BEGIN
        -- Keep V74 wallet admission inside the same transaction and after the
        -- idempotency/capacity decisions. A failure rolls back every row and any
        -- reservation, so neither double charging nor partial admission exists.
        PERFORM public.elmos_wallet_admit_job(
            p_organization_id, p_job_id, p_actor_id,
            p_business_line, p_job_kind, p_budget_wall_seconds);

        INSERT INTO public.execution_jobs (
            job_id, organization_id, actor_id, business_line, job_kind,
            idempotency_key, request_digest, request_payload, required_capability,
            runner_image, priority, budget_wall_seconds, max_attempts
        ) VALUES (
            p_job_id, p_organization_id, p_actor_id, p_business_line, p_job_kind,
            p_idempotency_key, p_request_digest,
            coalesce(p_request_payload, '{}'::jsonb),
            p_required_capability, p_runner_image,
            coalesce(p_priority, 100::smallint),
            coalesce(p_budget_wall_seconds, 3600),
            coalesce(p_max_attempts, 1::smallint)
        );

        INSERT INTO public.execution_job_dispatch (
            job_id, organization_id, required_capability, priority
        ) VALUES (
            p_job_id, p_organization_id, p_required_capability,
            coalesce(p_priority, 100::smallint)
        );

        INSERT INTO public.execution_job_events (
            job_event_id, organization_id, job_id, sequence_no, event_type,
            to_status, stage, progress, actor_id
        ) VALUES (
            'jev-' || pg_catalog.md5(p_job_id || ':0'),
            p_organization_id, p_job_id, 0, 'ENQUEUED',
            'QUEUED', 'queued', 0, p_actor_id
        );

        UPDATE public.execution_dispatch_org_counters c
           SET queued_count = c.queued_count + 1,
               updated_at = pg_catalog.now()
         WHERE c.organization_id = p_organization_id;
    EXCEPTION
        WHEN unique_violation THEN
            -- Never expose a constraint/table name through the public adapter.
            -- Same-key races cannot reach this branch because they are
            -- serialized above; this is an unrelated storage identity collision.
            RAISE EXCEPTION 'ELMOS_EXECUTION_STORAGE_CONFLICT'
                USING ERRCODE = '23505';
    END;

    RETURN p_job_id;
END;
$function$;

COMMENT ON FUNCTION elmos_enqueue_execution_job(
    varchar, varchar, varchar, varchar, varchar, varchar, varchar, jsonb,
    varchar, varchar, smallint, integer, smallint
) IS
    'Atomically admits one tenant execution job. Same idempotency key and digest returns the original job; digest drift fails; tenant queue capacity and counter changes are serialized; V74 wallet admission remains in the same transaction.';

REVOKE EXECUTE ON FUNCTION elmos_enqueue_execution_job(
    varchar, varchar, varchar, varchar, varchar, varchar, varchar, jsonb,
    varchar, varchar, smallint, integer, smallint
) FROM PUBLIC;
