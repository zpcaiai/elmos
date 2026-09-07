-- ELMOS V57: runner enrollment and tenant-safe execution function upgrade.
--
-- V52 is an immutable, applied migration that created the durable execution
-- queue, dispatch projection, typed Runner fleet, row-level-security policies,
-- and initial SECURITY DEFINER functions. V57 was introduced later and must be
-- a strict forward-only delta: replaying the V52 DDL here would fail on every
-- database whose Flyway history correctly contains V52.
--
-- This migration adds only the short-lived Runner enrollment/authentication
-- projection and replaces the execution functions whose bodies must bind the
-- tenant context before touching FORCE ROW LEVEL SECURITY tables. Missing
-- enrollment still fails closed. No provider role is created here; deployment
-- provisioning owns database roles on managed PostgreSQL.


-- Enrollment credentials are short-lived, revocable, pool-bound and stored only
-- as SHA-256. The node authentication projection carries no customer payload; it
-- exists so a runner can be authenticated before any tenant RLS context exists.
CREATE TABLE runner_enrollment_credentials (
    enrollment_credential_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    runner_pool_id varchar(96) NOT NULL,
    token_sha256 varchar(64) NOT NULL UNIQUE
        CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    credential_state varchar(16) NOT NULL DEFAULT 'ACTIVE'
        CHECK (credential_state IN ('ACTIVE', 'REVOKED', 'EXPIRED')),
    not_before timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    issued_by_actor_id varchar(128) NOT NULL,
    revoked_at timestamptz,
    revoked_by_actor_id varchar(128),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at > not_before),
    CHECK (
        credential_state <> 'REVOKED'
        OR (revoked_at IS NOT NULL AND revoked_by_actor_id IS NOT NULL)
    )
);

CREATE INDEX runner_enrollment_credentials_pool_active
    ON runner_enrollment_credentials (runner_pool_id, expires_at)
    WHERE credential_state = 'ACTIVE';

CREATE TABLE runner_node_authentication (
    runner_node_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    runner_pool_id varchar(96) NOT NULL,
    enrollment_credential_id varchar(96) NOT NULL
        REFERENCES runner_enrollment_credentials(enrollment_credential_id),
    bound_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);

REVOKE ALL ON runner_enrollment_credentials FROM PUBLIC;
REVOKE ALL ON runner_node_authentication FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- 5. Effective concurrency limit, derived from the CNY self-service catalog
-- ---------------------------------------------------------------------------
-- V49 already stores concurrent_job_limit per plan version. The scheduler must
-- reuse that number rather than inventing a second quota source of truth.

CREATE OR REPLACE FUNCTION elmos_execution_concurrency_limit(p_organization_id varchar)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    PERFORM set_config('app.organization_id', p_organization_id, true);
    RETURN (
    SELECT coalesce(
        (SELECT p.concurrent_job_limit
           FROM subscriptions s
           JOIN self_service_pricing_plan_versions p
             ON p.catalog_version = s.catalog_version AND p.plan_id = s.plan_id
          WHERE s.organization_id = p_organization_id
            AND s.plan_id IS NOT NULL
            AND s.status IN ('ACTIVE', 'TRIALING')
            AND s.current_period_end > now()
          ORDER BY p.concurrent_job_limit DESC
          LIMIT 1),
        0));
END;
$$;

COMMENT ON FUNCTION elmos_execution_concurrency_limit(varchar) IS
    'Effective concurrent job limit for a tenant. Returns 0 - fail closed, nothing is scheduled - when there is no active or trialing CNY subscription period.';

-- ---------------------------------------------------------------------------
-- 6. Enqueue
-- ---------------------------------------------------------------------------

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
SET search_path = public
AS $$
DECLARE
    v_existing execution_jobs%ROWTYPE;
    v_queued integer;
    v_limit integer;
BEGIN
    PERFORM set_config('app.organization_id', p_organization_id, true);
    SELECT * INTO v_existing FROM execution_jobs
     WHERE organization_id = p_organization_id AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.request_digest IS DISTINCT FROM p_request_digest THEN
            RAISE EXCEPTION 'ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.job_id;
    END IF;

    v_limit := elmos_execution_concurrency_limit(p_organization_id);
    IF v_limit < 1 THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_NO_ACTIVE_ENTITLEMENT';
    END IF;

    SELECT coalesce(queued_count, 0) INTO v_queued
      FROM execution_dispatch_org_counters WHERE organization_id = p_organization_id;
    IF coalesce(v_queued, 0) >= v_limit * 10 THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_QUEUE_DEPTH_EXCEEDED';
    END IF;

    INSERT INTO execution_jobs (
        job_id, organization_id, actor_id, business_line, job_kind,
        idempotency_key, request_digest, request_payload, required_capability,
        runner_image, priority, budget_wall_seconds, max_attempts
    ) VALUES (
        p_job_id, p_organization_id, p_actor_id, p_business_line, p_job_kind,
        p_idempotency_key, p_request_digest, coalesce(p_request_payload, '{}'::jsonb),
        p_required_capability, p_runner_image, coalesce(p_priority, 100::smallint),
        coalesce(p_budget_wall_seconds, 3600), coalesce(p_max_attempts, 1::smallint)
    );

    INSERT INTO execution_job_dispatch (
        job_id, organization_id, required_capability, priority
    ) VALUES (
        p_job_id, p_organization_id, p_required_capability, coalesce(p_priority, 100::smallint)
    );

    INSERT INTO execution_dispatch_org_counters (organization_id, queued_count)
    VALUES (p_organization_id, 1)
    ON CONFLICT (organization_id) DO UPDATE
        SET queued_count = execution_dispatch_org_counters.queued_count + 1,
            updated_at = now();

    INSERT INTO execution_job_events (
        job_event_id, organization_id, job_id, sequence_no, event_type,
        to_status, stage, progress, actor_id
    ) VALUES (
        'jev-' || md5(p_job_id || ':0'), p_organization_id, p_job_id, 0, 'ENQUEUED',
        'QUEUED', 'queued', 0, p_actor_id
    );

    RETURN p_job_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- 7. Claim (the SKIP LOCKED core)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_claim_execution_jobs(
    p_runner_node_id varchar,
    p_capabilities text[],
    p_limit integer,
    p_lease_seconds integer,
    p_lease_ids text[],
    p_token_hashes text[]
) RETURNS TABLE (
    job_id varchar,
    organization_id varchar,
    lease_id varchar,
    lease_expires_at timestamptz,
    business_line varchar,
    job_kind varchar,
    runner_image varchar,
    budget_wall_seconds integer,
    budget_cpu_millis integer,
    budget_memory_mib integer,
    attempt smallint,
    checkpoint_cursor jsonb,
    request_payload jsonb
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_node runner_nodes%ROWTYPE;
    v_runner_organization_id varchar(96);
    v_candidate record;
    v_job execution_jobs%ROWTYPE;
    v_active integer;
    v_claimed integer := 0;
    v_org_limit integer;
    v_org_active integer;
    v_lease_id varchar(96);
    v_expires timestamptz;
    v_seq integer;
BEGIN
    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 16 THEN
        RAISE EXCEPTION 'ELMOS_CLAIM_LIMIT_INVALID';
    END IF;
    IF p_lease_seconds IS NULL OR p_lease_seconds < 30 OR p_lease_seconds > 3600 THEN
        RAISE EXCEPTION 'ELMOS_CLAIM_LEASE_SECONDS_INVALID';
    END IF;
    IF coalesce(array_length(p_lease_ids, 1), 0) <> p_limit
       OR coalesce(array_length(p_token_hashes, 1), 0) <> p_limit THEN
        RAISE EXCEPTION 'ELMOS_CLAIM_CREDENTIAL_COUNT_MISMATCH';
    END IF;

    SELECT organization_id INTO v_runner_organization_id
      FROM runner_node_authentication
     WHERE runner_node_id = p_runner_node_id AND revoked_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_RUNNER_UNKNOWN';
    END IF;
    PERFORM set_config(
        'app.organization_id', v_runner_organization_id, true);

    SELECT * INTO v_node FROM runner_nodes
     WHERE runner_node_id = p_runner_node_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_RUNNER_UNKNOWN';
    END IF;
    IF v_node.fleet_status IS DISTINCT FROM 'READY' THEN
        RAISE EXCEPTION 'ELMOS_RUNNER_NOT_READY';
    END IF;
    IF v_node.last_heartbeat_at IS NULL OR v_node.last_heartbeat_at < now() - interval '90 seconds' THEN
        RAISE EXCEPTION 'ELMOS_RUNNER_HEARTBEAT_STALE';
    END IF;
    IF v_node.drain_requested_at IS NOT NULL THEN
        RETURN;
    END IF;

    SELECT count(*) INTO v_active FROM execution_job_dispatch
     WHERE runner_node_ref = p_runner_node_id AND dispatch_state = 'LEASED';
    IF v_active >= v_node.max_concurrency THEN
        RETURN;
    END IF;

    FOR v_candidate IN
        SELECT d.job_id AS d_job_id, d.organization_id AS d_org, d.attempt AS d_attempt
          FROM execution_job_dispatch d
          LEFT JOIN execution_dispatch_org_counters c ON c.organization_id = d.organization_id
         WHERE d.dispatch_state = 'READY'
           AND d.visible_at <= now()
           AND d.required_capability = ANY (p_capabilities)
         ORDER BY coalesce(c.leased_count, 0) ASC, d.priority DESC, d.enqueued_at ASC
         FOR UPDATE OF d SKIP LOCKED
    LOOP
        EXIT WHEN v_claimed >= p_limit OR (v_active + v_claimed) >= v_node.max_concurrency;

        v_org_limit := elmos_execution_concurrency_limit(v_candidate.d_org);
        SELECT coalesce(c.leased_count, 0) INTO v_org_active
          FROM execution_dispatch_org_counters c
         WHERE c.organization_id = v_candidate.d_org;
        CONTINUE WHEN coalesce(v_org_active, 0) >= v_org_limit;

        PERFORM set_config(
            'app.organization_id', v_candidate.d_org, true);
        SELECT * INTO v_job FROM execution_jobs
         WHERE execution_jobs.job_id = v_candidate.d_job_id FOR UPDATE;

        -- A cancel that arrived while the job was still queued never reaches a runner.
        IF v_job.cancel_requested_at IS NOT NULL THEN
            UPDATE execution_jobs
               SET status = 'CANCELLED', result_status = 'BLOCKED', finished_at = now()
             WHERE execution_jobs.job_id = v_job.job_id;
            UPDATE execution_job_dispatch SET dispatch_state = 'DONE'
             WHERE execution_job_dispatch.job_id = v_job.job_id;
            UPDATE execution_dispatch_org_counters c
               SET queued_count = greatest(c.queued_count - 1, 0), updated_at = now()
             WHERE c.organization_id = v_candidate.d_org;
            CONTINUE;
        END IF;

        v_claimed := v_claimed + 1;
        v_lease_id := p_lease_ids[v_claimed];
        v_expires := now() + make_interval(secs => p_lease_seconds);

        INSERT INTO runner_job_leases (
            runner_job_lease_id, organization_id, schema_version, status,
            idempotency_key, payload, job_ref, runner_node_ref, actor_id,
            lease_state, token_sha256, issued_at, expires_at, last_heartbeat_at
        ) VALUES (
            v_lease_id, v_candidate.d_org, '2.0', 'ISSUED',
            v_lease_id, '{}'::jsonb, v_job.job_id, p_runner_node_id, v_job.actor_id,
            'ISSUED', p_token_hashes[v_claimed], now(), v_expires, now()
        );

        UPDATE execution_job_dispatch
           SET dispatch_state = 'LEASED',
               lease_ref = v_lease_id,
               runner_node_ref = p_runner_node_id,
               lease_expires_at = v_expires,
               attempt = execution_job_dispatch.attempt + 1
         WHERE execution_job_dispatch.job_id = v_job.job_id;

        UPDATE execution_jobs
           SET status = 'CLAIMED',
               stage = 'claimed',
               attempt = execution_jobs.attempt + 1,
               started_at = coalesce(execution_jobs.started_at, now())
         WHERE execution_jobs.job_id = v_job.job_id;

        UPDATE execution_dispatch_org_counters c
           SET leased_count = c.leased_count + 1,
               queued_count = greatest(c.queued_count - 1, 0),
               updated_at = now()
         WHERE c.organization_id = v_candidate.d_org;

        SELECT coalesce(max(sequence_no), 0) + 1 INTO v_seq
          FROM execution_job_events e WHERE e.job_id = v_job.job_id;
        INSERT INTO execution_job_events (
            job_event_id, organization_id, job_id, sequence_no, event_type,
            from_status, to_status, stage, runner_node_ref, lease_ref
        ) VALUES (
            'jev-' || md5(v_job.job_id || ':' || v_seq), v_candidate.d_org, v_job.job_id,
            v_seq, 'CLAIMED', 'QUEUED', 'CLAIMED', 'claimed', p_runner_node_id, v_lease_id
        );

        job_id := v_job.job_id;
        organization_id := v_candidate.d_org;
        lease_id := v_lease_id;
        lease_expires_at := v_expires;
        business_line := v_job.business_line;
        job_kind := v_job.job_kind;
        runner_image := v_job.runner_image;
        budget_wall_seconds := v_job.budget_wall_seconds;
        budget_cpu_millis := v_job.budget_cpu_millis;
        budget_memory_mib := v_job.budget_memory_mib;
        attempt := v_job.attempt + 1;
        checkpoint_cursor := v_job.checkpoint_cursor;
        request_payload := v_job.request_payload;
        RETURN NEXT;
    END LOOP;

    RETURN;
END;
$$;

-- ---------------------------------------------------------------------------
-- 8. Heartbeat, checkpoint, completion
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_heartbeat_execution_lease(
    p_lease_id varchar,
    p_runner_node_id varchar,
    p_token_hash varchar,
    p_stage varchar,
    p_progress smallint,
    p_checkpoint jsonb,
    p_lease_seconds integer
) RETURNS TABLE (cancel_requested boolean, lease_expires_at timestamptz)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_lease runner_job_leases%ROWTYPE;
    v_organization_id varchar(96);
    v_expires timestamptz;
    v_cancelled boolean;
BEGIN
    SELECT organization_id INTO v_organization_id
      FROM execution_job_dispatch WHERE lease_ref = p_lease_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_LEASE_UNKNOWN'; END IF;
    PERFORM set_config('app.organization_id', v_organization_id, true);

    SELECT * INTO v_lease FROM runner_job_leases
     WHERE runner_job_lease_id = p_lease_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_LEASE_UNKNOWN'; END IF;
    IF v_lease.runner_node_ref IS DISTINCT FROM p_runner_node_id
       OR v_lease.token_sha256 IS DISTINCT FROM p_token_hash THEN
        RAISE EXCEPTION 'ELMOS_LEASE_CREDENTIAL_MISMATCH';
    END IF;
    IF v_lease.lease_state NOT IN ('ISSUED', 'ACTIVE') THEN
        RAISE EXCEPTION 'ELMOS_LEASE_NOT_ACTIVE';
    END IF;
    IF v_lease.expires_at < now() THEN
        RAISE EXCEPTION 'ELMOS_LEASE_EXPIRED';
    END IF;

    v_expires := now() + make_interval(secs => coalesce(p_lease_seconds, 120));

    UPDATE runner_job_leases
       SET lease_state = 'ACTIVE', last_heartbeat_at = now(), expires_at = v_expires
     WHERE runner_job_lease_id = p_lease_id;
    UPDATE execution_job_dispatch
       SET lease_expires_at = v_expires
     WHERE execution_job_dispatch.job_id = v_lease.job_ref;
    UPDATE runner_nodes SET last_heartbeat_at = now()
     WHERE runner_node_id = p_runner_node_id;

    UPDATE execution_jobs
       SET status = CASE WHEN status = 'CLAIMED' THEN 'RUNNING' ELSE status END,
           stage = coalesce(p_stage, stage),
           progress = coalesce(p_progress, progress),
           checkpoint_cursor = coalesce(p_checkpoint, checkpoint_cursor)
     WHERE execution_jobs.job_id = v_lease.job_ref
       AND status IN ('CLAIMED', 'RUNNING')
    RETURNING cancel_requested_at IS NOT NULL INTO v_cancelled;

    cancel_requested := coalesce(v_cancelled, false);
    lease_expires_at := v_expires;
    RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_complete_execution_job(
    p_lease_id varchar,
    p_runner_node_id varchar,
    p_token_hash varchar,
    p_status varchar,
    p_result_status varchar,
    p_failure_code varchar
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_lease runner_job_leases%ROWTYPE;
    v_organization_id varchar(96);
    v_job execution_jobs%ROWTYPE;
    v_seq integer;
    v_requeue boolean := false;
BEGIN
    IF p_status NOT IN ('SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED') THEN
        RAISE EXCEPTION 'ELMOS_COMPLETION_STATUS_INVALID';
    END IF;

    SELECT organization_id INTO v_organization_id
      FROM execution_job_dispatch WHERE lease_ref = p_lease_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_LEASE_UNKNOWN'; END IF;
    PERFORM set_config('app.organization_id', v_organization_id, true);

    SELECT * INTO v_lease FROM runner_job_leases
     WHERE runner_job_lease_id = p_lease_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_LEASE_UNKNOWN'; END IF;
    IF v_lease.runner_node_ref IS DISTINCT FROM p_runner_node_id
       OR v_lease.token_sha256 IS DISTINCT FROM p_token_hash THEN
        RAISE EXCEPTION 'ELMOS_LEASE_CREDENTIAL_MISMATCH';
    END IF;
    IF v_lease.lease_state NOT IN ('ISSUED', 'ACTIVE') THEN
        -- Completion is idempotent: a retried report for an already released
        -- lease is accepted without changing the terminal record.
        RETURN false;
    END IF;

    SELECT * INTO v_job FROM execution_jobs
     WHERE execution_jobs.job_id = v_lease.job_ref FOR UPDATE;

    IF v_job.status IN ('SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'LOST') THEN
        UPDATE runner_job_leases SET lease_state = 'RELEASED', released_at = now()
         WHERE runner_job_lease_id = p_lease_id;
        RETURN false;
    END IF;

    v_requeue := (p_status = 'FAILED' AND v_job.attempt < v_job.max_attempts);

    UPDATE runner_job_leases
       SET lease_state = 'RELEASED', released_at = now()
     WHERE runner_job_lease_id = p_lease_id;

    IF v_requeue THEN
        UPDATE execution_jobs
           SET status = 'QUEUED', stage = 'requeued', failure_code = p_failure_code
         WHERE execution_jobs.job_id = v_job.job_id;
        UPDATE execution_job_dispatch
           SET dispatch_state = 'READY', lease_ref = NULL, runner_node_ref = NULL,
               lease_expires_at = NULL,
               visible_at = now() + make_interval(secs => 30 * power(2, v_job.attempt)::integer)
         WHERE execution_job_dispatch.job_id = v_job.job_id;
        UPDATE execution_dispatch_org_counters
           SET leased_count = greatest(leased_count - 1, 0),
               queued_count = queued_count + 1, updated_at = now()
         WHERE organization_id = v_job.organization_id;
    ELSE
        UPDATE execution_jobs
           SET status = p_status,
               result_status = coalesce(p_result_status, 'NOT_RUN'),
               failure_code = p_failure_code,
               progress = CASE WHEN p_status = 'SUCCEEDED' THEN 100 ELSE progress END,
               finished_at = now()
         WHERE execution_jobs.job_id = v_job.job_id;
        UPDATE execution_job_dispatch SET dispatch_state = 'DONE'
         WHERE execution_job_dispatch.job_id = v_job.job_id;
        UPDATE execution_dispatch_org_counters
           SET leased_count = greatest(leased_count - 1, 0), updated_at = now()
         WHERE organization_id = v_job.organization_id;
    END IF;

    SELECT coalesce(max(sequence_no), 0) + 1 INTO v_seq
      FROM execution_job_events e WHERE e.job_id = v_job.job_id;
    INSERT INTO execution_job_events (
        job_event_id, organization_id, job_id, sequence_no, event_type,
        from_status, to_status, lease_ref, runner_node_ref, failure_code
    ) VALUES (
        'jev-' || md5(v_job.job_id || ':' || v_seq), v_job.organization_id, v_job.job_id,
        v_seq, CASE WHEN v_requeue THEN 'REQUEUED' WHEN p_status = 'FAILED' THEN 'FAILED' ELSE 'COMPLETED' END,
        v_job.status, CASE WHEN v_requeue THEN 'QUEUED' ELSE p_status END,
        p_lease_id, p_runner_node_id, p_failure_code
    );

    RETURN true;
END;
$$;

-- ---------------------------------------------------------------------------
-- 9. Cancellation and lease reaping
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_request_execution_cancel(
    p_organization_id varchar,
    p_job_id varchar,
    p_actor_id varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_job execution_jobs%ROWTYPE;
    v_seq integer;
BEGIN
    PERFORM set_config('app.organization_id', p_organization_id, true);
    SELECT * INTO v_job FROM execution_jobs
     WHERE job_id = p_job_id AND organization_id = p_organization_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_EXECUTION_JOB_UNKNOWN'; END IF;
    IF v_job.status IN ('SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'LOST') THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_JOB_TERMINAL';
    END IF;

    UPDATE execution_jobs
       SET cancel_requested_at = coalesce(cancel_requested_at, now()),
           cancel_requested_by = coalesce(cancel_requested_by, p_actor_id)
     WHERE job_id = p_job_id;

    SELECT coalesce(max(sequence_no), 0) + 1 INTO v_seq
      FROM execution_job_events e WHERE e.job_id = p_job_id;
    INSERT INTO execution_job_events (
        job_event_id, organization_id, job_id, sequence_no, event_type, actor_id
    ) VALUES (
        'jev-' || md5(p_job_id || ':' || v_seq), p_organization_id, p_job_id,
        v_seq, 'CANCEL_REQUESTED', p_actor_id
    );

    RETURN v_job.status;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_reap_execution_leases()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_row record;
    v_node record;
    v_job execution_jobs%ROWTYPE;
    v_seq integer;
    v_count integer := 0;
BEGIN
    FOR v_row IN
        SELECT d.job_id, d.organization_id, d.lease_ref, d.runner_node_ref
          FROM execution_job_dispatch d
         WHERE d.dispatch_state = 'LEASED' AND d.lease_expires_at < now()
         FOR UPDATE SKIP LOCKED
    LOOP
        PERFORM set_config('app.organization_id', v_row.organization_id, true);
        UPDATE runner_job_leases
           SET lease_state = 'EXPIRED', released_at = now(), revocation_code = 'LEASE_EXPIRED'
         WHERE runner_job_lease_id = v_row.lease_ref;

        SELECT * INTO v_job FROM execution_jobs WHERE job_id = v_row.job_id FOR UPDATE;

        IF v_job.attempt < v_job.max_attempts AND v_job.cancel_requested_at IS NULL THEN
            UPDATE execution_jobs SET status = 'QUEUED', stage = 'requeued'
             WHERE job_id = v_row.job_id;
            UPDATE execution_job_dispatch
               SET dispatch_state = 'READY', lease_ref = NULL, runner_node_ref = NULL,
                   lease_expires_at = NULL, visible_at = now() + interval '15 seconds'
             WHERE job_id = v_row.job_id;
            UPDATE execution_dispatch_org_counters
               SET leased_count = greatest(leased_count - 1, 0),
                   queued_count = queued_count + 1, updated_at = now()
             WHERE organization_id = v_row.organization_id;
        ELSE
            UPDATE execution_jobs
               SET status = 'LOST', result_status = 'BLOCKED',
                   failure_code = 'RUNNER_LEASE_LOST', finished_at = now()
             WHERE job_id = v_row.job_id;
            UPDATE execution_job_dispatch SET dispatch_state = 'DEAD' WHERE job_id = v_row.job_id;
            UPDATE execution_dispatch_org_counters
               SET leased_count = greatest(leased_count - 1, 0), updated_at = now()
             WHERE organization_id = v_row.organization_id;
        END IF;

        SELECT coalesce(max(sequence_no), 0) + 1 INTO v_seq
          FROM execution_job_events e WHERE e.job_id = v_row.job_id;
        INSERT INTO execution_job_events (
            job_event_id, organization_id, job_id, sequence_no, event_type,
            lease_ref, runner_node_ref, failure_code
        ) VALUES (
            'jev-' || md5(v_row.job_id || ':' || v_seq), v_row.organization_id, v_row.job_id,
            v_seq, 'LEASE_EXPIRED', v_row.lease_ref, v_row.runner_node_ref, 'RUNNER_LEASE_LOST'
        );

        v_count := v_count + 1;
    END LOOP;

    FOR v_node IN
        SELECT runner_node_id, organization_id
          FROM runner_node_authentication
         WHERE revoked_at IS NULL
    LOOP
        PERFORM set_config('app.organization_id', v_node.organization_id, true);
        UPDATE runner_nodes
           SET fleet_status = 'LOST'
         WHERE runner_node_id = v_node.runner_node_id
           AND fleet_status IN ('READY', 'DRAINING')
           AND (last_heartbeat_at IS NULL
                OR last_heartbeat_at < now() - interval '120 seconds');
    END LOOP;

    PERFORM elmos_reconcile_dispatch_counters();
    RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_reconcile_dispatch_counters()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_fixed integer;
BEGIN
    WITH truth AS (
        SELECT organization_id,
               count(*) FILTER (WHERE dispatch_state = 'LEASED') AS leased,
               count(*) FILTER (WHERE dispatch_state = 'READY') AS queued
          FROM execution_job_dispatch
         GROUP BY organization_id
    ), corrected AS (
        UPDATE execution_dispatch_org_counters c
           SET leased_count = t.leased, queued_count = t.queued, updated_at = now()
          FROM truth t
         WHERE c.organization_id = t.organization_id
           AND (c.leased_count <> t.leased OR c.queued_count <> t.queued)
        RETURNING 1
    )
    SELECT count(*) INTO v_fixed FROM corrected;
    RETURN v_fixed;
END;
$$;

-- ---------------------------------------------------------------------------

REVOKE ALL ON execution_job_dispatch FROM PUBLIC;
REVOKE ALL ON execution_dispatch_org_counters FROM PUBLIC;

DO $$
DECLARE v_function record;
BEGIN
    FOR v_function IN
        SELECT p.oid::regprocedure AS signature
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND p.proname IN (
               'elmos_execution_concurrency_limit',
               'elmos_enqueue_execution_job',
               'elmos_claim_execution_jobs',
               'elmos_heartbeat_execution_lease',
               'elmos_complete_execution_job',
               'elmos_request_execution_cancel',
               'elmos_reap_execution_leases',
               'elmos_reconcile_dispatch_counters',
               'elmos_guard_execution_job_transition'
           )
    LOOP
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', v_function.signature);
    END LOOP;
END;
$$;
