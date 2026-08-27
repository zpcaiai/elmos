-- A runner may claim only jobs whose immutable image it has just proved exists
-- in its local container store. The six-argument function could not express that
-- constraint, so remove it before exposing the fail-closed seven-argument form.

DROP FUNCTION IF EXISTS elmos_claim_execution_jobs(
    varchar, text[], integer, integer, text[], text[]);

CREATE FUNCTION elmos_claim_execution_jobs(
    p_runner_node_id varchar,
    p_capabilities text[],
    p_available_images text[],
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
    IF coalesce(array_length(p_available_images, 1), 0) < 1
       OR coalesce(array_length(p_available_images, 1), 0) > 32
       OR cardinality(p_available_images) <> (
           SELECT count(DISTINCT image)
             FROM unnest(p_available_images) AS supplied(image))
       OR EXISTS (
           SELECT 1
             FROM unnest(p_available_images) AS supplied(image)
            WHERE image IS NULL
               OR image !~ '^[a-z0-9][a-z0-9._/-]*(:[0-9]+)?/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$'
       ) THEN
        RAISE EXCEPTION 'ELMOS_RUNNER_AVAILABLE_IMAGES_INVALID';
    END IF;

    SELECT auth.organization_id INTO v_runner_organization_id
      FROM runner_node_authentication auth
     WHERE auth.runner_node_id = p_runner_node_id
       AND auth.revoked_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_RUNNER_UNKNOWN';
    END IF;
    PERFORM set_config('app.organization_id', v_runner_organization_id, true);

    SELECT * INTO v_node FROM runner_nodes
     WHERE runner_node_id = p_runner_node_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_RUNNER_UNKNOWN';
    END IF;
    IF v_node.fleet_status IS DISTINCT FROM 'READY' THEN
        RAISE EXCEPTION 'ELMOS_RUNNER_NOT_READY';
    END IF;
    IF v_node.last_heartbeat_at IS NULL
       OR v_node.last_heartbeat_at < now() - interval '90 seconds' THEN
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
          LEFT JOIN execution_dispatch_org_counters c
            ON c.organization_id = d.organization_id
         WHERE d.dispatch_state = 'READY'
           AND d.visible_at <= now()
           AND d.required_capability = ANY (p_capabilities)
           AND EXISTS (
               SELECT 1
                 FROM execution_jobs candidate_job
                WHERE candidate_job.job_id = d.job_id
                  AND candidate_job.organization_id = d.organization_id
                  AND candidate_job.runner_image = ANY (p_available_images))
         ORDER BY coalesce(c.leased_count, 0) ASC, d.priority DESC, d.enqueued_at ASC
         FOR UPDATE OF d SKIP LOCKED
    LOOP
        EXIT WHEN v_claimed >= p_limit
            OR (v_active + v_claimed) >= v_node.max_concurrency;

        v_org_limit := elmos_execution_concurrency_limit(v_candidate.d_org);
        SELECT coalesce(c.leased_count, 0) INTO v_org_active
          FROM execution_dispatch_org_counters c
         WHERE c.organization_id = v_candidate.d_org;
        CONTINUE WHEN coalesce(v_org_active, 0) >= v_org_limit;

        PERFORM set_config('app.organization_id', v_candidate.d_org, true);
        SELECT * INTO v_job FROM execution_jobs
         WHERE execution_jobs.job_id = v_candidate.d_job_id FOR UPDATE;

        -- Recheck under the tenant-bound row lock before minting any lease. This
        -- closes both candidate/claim races and future query-plan regressions.
        CONTINUE WHEN v_job.runner_image IS NULL
            OR NOT (v_job.runner_image = ANY (p_available_images));

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
