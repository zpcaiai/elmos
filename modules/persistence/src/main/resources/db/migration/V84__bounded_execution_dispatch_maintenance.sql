-- Bounded scheduling maintenance; preserves V57 signatures and V80 billing authority.
-- New scheduling timestamps carry no customer payload and are owner-only.
ALTER TABLE execution_dispatch_org_counters
    ADD COLUMN last_claim_probe_at timestamptz NOT NULL DEFAULT '-infinity',
    ADD COLUMN last_reconciled_at timestamptz NOT NULL DEFAULT '-infinity';
ALTER TABLE execution_job_dispatch
    ADD COLUMN last_reap_probe_at timestamptz NOT NULL DEFAULT '-infinity';
ALTER TABLE runner_node_authentication
    ADD COLUMN last_reaped_at timestamptz NOT NULL DEFAULT '-infinity';

CREATE INDEX execution_counter_claim_window_idx
    ON execution_dispatch_org_counters (last_claim_probe_at, leased_count, organization_id)
    WHERE queued_count > 0;
CREATE INDEX execution_counter_reconcile_window_idx
    ON execution_dispatch_org_counters (last_reconciled_at, organization_id);
CREATE INDEX execution_dispatch_tenant_ready_idx
    ON execution_job_dispatch (organization_id, required_capability, priority DESC, enqueued_at, job_id)
    WHERE dispatch_state = 'READY';
CREATE INDEX execution_dispatch_active_counter_idx
    ON execution_job_dispatch (organization_id, dispatch_state)
    WHERE dispatch_state IN ('READY', 'LEASED');
CREATE INDEX execution_dispatch_runner_active_idx
    ON execution_job_dispatch (runner_node_ref) WHERE dispatch_state = 'LEASED';
CREATE INDEX execution_dispatch_reap_window_idx
    ON execution_job_dispatch (last_reap_probe_at, lease_expires_at, job_id)
    WHERE dispatch_state = 'LEASED';
CREATE INDEX runner_auth_reap_window_idx
    ON runner_node_authentication (last_reaped_at, runner_node_id) WHERE revoked_at IS NULL;

COMMENT ON TABLE execution_dispatch_org_counters IS
    'Owner-only cross-tenant scheduling projection. Atomic dispatch counters with rotating bounded scheduled reconciliation; explicit full reconciliation remains available to authorized administrators.';

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
    v_org varchar(96);
    v_probed integer := 0;
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

    SELECT a.organization_id INTO v_runner_organization_id
      FROM runner_node_authentication a
     WHERE a.runner_node_id = p_runner_node_id AND a.revoked_at IS NULL;
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

    -- Rotate a bounded tenant window, including saturated tenants. This avoids
    -- scanning every READY job or allowing a full tenant to pin the same window.
    FOR v_org IN
        SELECT c.organization_id FROM execution_dispatch_org_counters c
         WHERE c.queued_count > 0 AND EXISTS (
             SELECT 1 FROM execution_job_dispatch d
              WHERE d.organization_id = c.organization_id
                AND d.dispatch_state = 'READY' AND d.visible_at <= now()
                AND d.required_capability = ANY (p_capabilities))
         ORDER BY c.last_claim_probe_at, c.leased_count, c.organization_id
         LIMIT 32 FOR UPDATE OF c SKIP LOCKED
    LOOP
        EXIT WHEN v_claimed >= p_limit OR v_probed >= 128
               OR v_active + v_claimed >= v_node.max_concurrency;
        UPDATE execution_dispatch_org_counters c
           SET last_claim_probe_at = clock_timestamp() WHERE c.organization_id = v_org;
        v_org_limit := elmos_execution_concurrency_limit(v_org);
        SELECT c.leased_count INTO v_org_active
          FROM execution_dispatch_org_counters c WHERE c.organization_id = v_org;
        CONTINUE WHEN v_org_active >= v_org_limit;

        -- Counter -> dispatch uses SKIP LOCKED: completion/reaper may hold
        -- dispatch before counter, but claim never waits on that reverse edge.
        FOR v_candidate IN
            SELECT d.job_id AS d_job_id, d.organization_id AS d_org, d.attempt AS d_attempt
              FROM execution_job_dispatch d
             WHERE d.organization_id = v_org AND d.dispatch_state = 'READY'
               AND d.visible_at <= now() AND d.required_capability = ANY (p_capabilities)
             ORDER BY d.priority DESC, d.enqueued_at, d.job_id
             LIMIT (128 - v_probed) FOR UPDATE OF d SKIP LOCKED
        LOOP
        EXIT WHEN v_claimed >= p_limit OR v_org_active >= v_org_limit
               OR v_active + v_claimed >= v_node.max_concurrency;
        v_probed := v_probed + 1;

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
        v_org_active := v_org_active + 1;
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
    END LOOP;

    RETURN;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_reconcile_dispatch_counters_batch(p_limit integer)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_org varchar(96);
    v_leased integer;
    v_queued integer;
    v_fixed integer := 0;
    v_changed integer;
BEGIN
    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 128 THEN
        RAISE EXCEPTION 'ELMOS_RECONCILE_LIMIT_INVALID';
    END IF;
    FOR v_org IN
        SELECT c.organization_id FROM execution_dispatch_org_counters c
        ORDER BY c.last_reconciled_at, c.organization_id LIMIT p_limit FOR UPDATE SKIP LOCKED
    LOOP
        -- Separate statement: READ COMMITTED snapshot after taking this tenant's lock.
        SELECT count(*) FILTER (WHERE d.dispatch_state = 'LEASED'),
               count(*) FILTER (WHERE d.dispatch_state = 'READY')
          INTO v_leased, v_queued FROM execution_job_dispatch d
         WHERE d.organization_id = v_org AND d.dispatch_state IN ('READY', 'LEASED');
        UPDATE execution_dispatch_org_counters c
           SET leased_count = v_leased, queued_count = v_queued, updated_at = now()
         WHERE c.organization_id = v_org
           AND (c.leased_count <> v_leased OR c.queued_count <> v_queued);
        GET DIAGNOSTICS v_changed = ROW_COUNT;
        v_fixed := v_fixed + v_changed;
        UPDATE execution_dispatch_org_counters c SET last_reconciled_at = clock_timestamp()
         WHERE c.organization_id = v_org;
    END LOOP;
    RETURN v_fixed;
END;
$$;

REVOKE ALL ON FUNCTION elmos_reconcile_dispatch_counters_batch(integer) FROM PUBLIC;

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
         ORDER BY d.last_reap_probe_at, d.lease_expires_at, d.job_id
         LIMIT 128 FOR UPDATE SKIP LOCKED
    LOOP
        UPDATE execution_job_dispatch SET last_reap_probe_at = clock_timestamp()
         WHERE job_id = v_row.job_id;
        PERFORM 1 FROM execution_dispatch_org_counters c
         WHERE c.organization_id = v_row.organization_id FOR UPDATE SKIP LOCKED;
        CONTINUE WHEN NOT FOUND;
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
         ORDER BY last_reaped_at, runner_node_id
         LIMIT 64 FOR UPDATE SKIP LOCKED
    LOOP
        UPDATE runner_node_authentication SET last_reaped_at = clock_timestamp()
         WHERE runner_node_id = v_node.runner_node_id;
        PERFORM set_config('app.organization_id', v_node.organization_id, true);
        PERFORM 1 FROM runner_nodes n WHERE n.runner_node_id = v_node.runner_node_id
         FOR UPDATE SKIP LOCKED;
        CONTINUE WHEN NOT FOUND;
        UPDATE runner_nodes
           SET fleet_status = 'LOST'
         WHERE runner_node_id = v_node.runner_node_id
           AND fleet_status IN ('READY', 'DRAINING')
           AND (last_heartbeat_at IS NULL
                OR last_heartbeat_at < now() - interval '120 seconds');
    END LOOP;

    PERFORM elmos_reconcile_dispatch_counters_batch(32);
    RETURN v_count;
END;
$$;



-- Explicit administrator full repair retains its public ABI and full-scan semantics.
CREATE OR REPLACE FUNCTION elmos_reconcile_dispatch_counters()
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    v_org varchar(96);
    v_leased integer;
    v_queued integer;
    v_fixed integer := 0;
    v_changed integer;
BEGIN
    FOR v_org IN
        SELECT c.organization_id FROM execution_dispatch_org_counters c
        ORDER BY c.organization_id FOR UPDATE SKIP LOCKED
    LOOP
        -- Separate statement: READ COMMITTED snapshot after taking this tenant's lock.
        SELECT count(*) FILTER (WHERE d.dispatch_state = 'LEASED'),
               count(*) FILTER (WHERE d.dispatch_state = 'READY')
          INTO v_leased, v_queued FROM execution_job_dispatch d
         WHERE d.organization_id = v_org AND d.dispatch_state IN ('READY', 'LEASED');
        UPDATE execution_dispatch_org_counters c
           SET leased_count = v_leased, queued_count = v_queued, updated_at = now()
         WHERE c.organization_id = v_org
           AND (c.leased_count <> v_leased OR c.queued_count <> v_queued);
        GET DIAGNOSTICS v_changed = ROW_COUNT;
        v_fixed := v_fixed + v_changed;
    END LOOP;
    RETURN v_fixed;
END;
$$;

