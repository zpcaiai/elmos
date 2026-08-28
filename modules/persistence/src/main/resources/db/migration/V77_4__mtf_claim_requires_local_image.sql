-- ELMOS V77.4: bind account-scoped claims to the runner's local image set.
--
-- V74 hardened the legacy claim function, but the account-scoped V77 function
-- introduced a second claim path. The Java port validated available images but
-- did not pass them into PostgreSQL, leaving the authoritative scheduler unable
-- to enforce that the selected immutable image was actually present. Replace
-- the six-argument function; do not leave an overload that can bypass the gate.

REVOKE ALL ON FUNCTION elmos_mtf_claim_execution_jobs(
    varchar, text[], integer, integer, text[], text[])
    FROM PUBLIC, elmos_mtf_workflow;
DROP FUNCTION elmos_mtf_claim_execution_jobs(
    varchar, text[], integer, integer, text[], text[]);

CREATE FUNCTION elmos_mtf_claim_execution_jobs(
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
SET row_security = on
AS $$
DECLARE
    v_runner_organization_id varchar(96);
    v_node runner_nodes%ROWTYPE;
    v_candidate record;
    v_job execution_jobs%ROWTYPE;
    v_slot execution_account_slots%ROWTYPE;
    v_active integer;
    v_claimed integer := 0;
    v_org_limit integer;
    v_org_active integer;
    v_lease_id varchar(96);
    v_expires timestamptz;
BEGIN
    IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 16 THEN
        RAISE EXCEPTION 'ELMOS_MTF_CLAIM_LIMIT_INVALID';
    END IF;
    IF p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 30 AND 3600 THEN
        RAISE EXCEPTION 'ELMOS_MTF_CLAIM_LEASE_SECONDS_INVALID';
    END IF;
    IF coalesce(array_length(p_lease_ids, 1), 0) <> p_limit
       OR coalesce(array_length(p_token_hashes, 1), 0) <> p_limit THEN
        RAISE EXCEPTION 'ELMOS_MTF_CLAIM_CREDENTIAL_COUNT_MISMATCH';
    END IF;
    IF coalesce(array_length(p_available_images, 1), 0) NOT BETWEEN 1 AND 32
       OR cardinality(p_available_images) <> (
           SELECT count(DISTINCT supplied.image)
             FROM unnest(p_available_images) AS supplied(image))
       OR EXISTS (
           SELECT 1
             FROM unnest(p_available_images) AS supplied(image)
            WHERE supplied.image IS NULL
               OR supplied.image !~ '^[a-z0-9][a-z0-9._/-]*(:[0-9]+)?/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$'
       ) THEN
        RAISE EXCEPTION 'ELMOS_RUNNER_AVAILABLE_IMAGES_INVALID';
    END IF;

    SELECT authentication.organization_id INTO v_runner_organization_id
      FROM runner_node_authentication authentication
     WHERE authentication.runner_node_id = p_runner_node_id
       AND authentication.revoked_at IS NULL;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_RUNNER_UNKNOWN'; END IF;
    PERFORM set_config('app.organization_id', v_runner_organization_id, true);

    SELECT * INTO v_node FROM runner_nodes
     WHERE runner_node_id = p_runner_node_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_RUNNER_UNKNOWN'; END IF;
    IF v_node.fleet_status <> 'READY'
       OR v_node.last_heartbeat_at IS NULL
       OR v_node.last_heartbeat_at < now() - interval '90 seconds'
       OR v_node.drain_requested_at IS NOT NULL THEN
        RAISE EXCEPTION 'ELMOS_MTF_RUNNER_NOT_ADMISSIBLE';
    END IF;

    SELECT count(*) INTO v_active FROM execution_job_dispatch
     WHERE runner_node_ref = p_runner_node_id AND dispatch_state = 'LEASED';
    IF v_active >= v_node.max_concurrency THEN RETURN; END IF;

    -- p_capabilities remains wire-compatibility input only. Registered runner
    -- capabilities and the immediate digest-pinned local image set are the two
    -- authoritative placement gates.
    FOR v_candidate IN
        SELECT d.job_id AS candidate_job_id,
               d.organization_id AS candidate_organization_id,
               d.account_id AS candidate_account_id
          FROM execution_job_dispatch d
          LEFT JOIN execution_dispatch_org_counters counter
            ON counter.organization_id = d.organization_id
         WHERE d.dispatch_state = 'READY'
           AND d.visible_at <= now()
           AND d.organization_id = v_runner_organization_id
           AND d.account_id IS NOT NULL
           AND d.required_capability = ANY (v_node.capabilities)
           AND EXISTS (
               SELECT 1
                 FROM execution_jobs candidate_job
                WHERE candidate_job.job_id = d.job_id
                  AND candidate_job.organization_id = d.organization_id
                  AND candidate_job.account_id = d.account_id
                  AND candidate_job.runner_image = ANY (p_available_images))
         ORDER BY coalesce(counter.leased_count, 0) ASC,
                  d.priority DESC, d.enqueued_at ASC, d.job_id ASC
         FOR UPDATE OF d SKIP LOCKED
    LOOP
        EXIT WHEN v_claimed >= p_limit
               OR (v_active + v_claimed) >= v_node.max_concurrency;

        v_org_limit := elmos_execution_concurrency_limit(
            v_candidate.candidate_organization_id);
        SELECT coalesce(counter.leased_count, 0) INTO v_org_active
          FROM execution_dispatch_org_counters counter
         WHERE counter.organization_id = v_candidate.candidate_organization_id;
        CONTINUE WHEN coalesce(v_org_active, 0) >= v_org_limit;

        PERFORM set_config(
            'app.organization_id', v_candidate.candidate_organization_id, true);
        PERFORM set_config(
            'app.account_id', v_candidate.candidate_account_id, true);
        SELECT * INTO v_job FROM execution_jobs
         WHERE execution_jobs.job_id = v_candidate.candidate_job_id
           AND execution_jobs.organization_id = v_candidate.candidate_organization_id
           AND execution_jobs.account_id = v_candidate.candidate_account_id
         FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'ELMOS_MTF_DISPATCH_SCOPE_DRIFT';
        END IF;

        -- Recheck under the tenant/account-bound row lock before minting a
        -- credential. Candidate selection alone is not a sufficient race gate.
        CONTINUE WHEN v_job.runner_image IS NULL
            OR NOT (v_job.runner_image = ANY (p_available_images));

        PERFORM elmos_mtf_bind_identity(
            v_job.organization_id, v_job.account_id, v_job.actor_id,
            'runner-claim:' || p_runner_node_id);

        IF v_job.cancel_requested_at IS NOT NULL THEN
            UPDATE execution_jobs
               SET status = 'CANCELLED', result_status = 'BLOCKED',
                   control_state = 'CANCEL_REQUESTED',
                   admission_state = 'RELEASED', finished_at = now()
             WHERE execution_jobs.job_id = v_job.job_id;
            UPDATE execution_job_dispatch SET dispatch_state = 'DONE'
             WHERE execution_job_dispatch.job_id = v_job.job_id;
            UPDATE execution_dispatch_org_counters
               SET queued_count = greatest(queued_count - 1, 0), updated_at = now()
             WHERE execution_dispatch_org_counters.organization_id = v_job.organization_id;
            PERFORM elmos_mtf_append_job_event(
                v_job.job_id, 'cancel-before-claim:' || v_job.state_version,
                'CANCELLED', 'QUEUED', 'CANCELLED', 'cancelled', v_job.progress,
                NULL, NULL, v_job.elapsed_millis, v_job.eta_p50_millis,
                v_job.eta_p90_millis, NULL);
            CONTINUE;
        END IF;

        SELECT * INTO v_slot
          FROM execution_account_slots
         WHERE execution_account_slots.account_id = v_job.account_id
           AND slot_state = 'FREE'
         ORDER BY slot_number
         FOR UPDATE SKIP LOCKED
         LIMIT 1;
        IF NOT FOUND THEN
            UPDATE execution_jobs
               SET admission_state = 'WAITING_FOR_SLOT'
             WHERE execution_jobs.job_id = v_job.job_id;
            UPDATE execution_job_dispatch
               SET queue_reason = 'ACCOUNT_CONCURRENCY_LIMIT'
             WHERE execution_job_dispatch.job_id = v_job.job_id;
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
            v_lease_id, v_job.organization_id, 'mtf-1.0', 'ISSUED',
            v_lease_id, '{}'::jsonb, v_job.job_id, p_runner_node_id, v_job.actor_id,
            'ISSUED', p_token_hashes[v_claimed], now(), v_expires, now()
        );

        UPDATE execution_account_slots
           SET slot_state = 'ACTIVE', organization_id = v_job.organization_id,
               active_job_id = v_job.job_id, active_lease_ref = v_lease_id,
               lease_generation = lease_generation + 1,
               lease_expires_at = v_expires, last_renewed_at = now(),
               occupied_at = now(), released_at = NULL, release_reason = NULL
         WHERE execution_account_slots.account_id = v_job.account_id
           AND slot_number = v_slot.slot_number;

        UPDATE execution_job_dispatch
           SET dispatch_state = 'LEASED', lease_ref = v_lease_id,
               runner_node_ref = p_runner_node_id, lease_expires_at = v_expires,
               attempt = execution_job_dispatch.attempt + 1, queue_reason = NULL
         WHERE execution_job_dispatch.job_id = v_job.job_id;

        UPDATE execution_jobs
           SET status = 'CLAIMED', stage = 'claimed',
               admission_state = 'ADMITTED',
               account_slot_number = v_slot.slot_number,
               account_slot_generation = v_slot.lease_generation + 1,
               attempt = execution_jobs.attempt + 1,
               started_at = coalesce(execution_jobs.started_at, now())
         WHERE execution_jobs.job_id = v_job.job_id;

        UPDATE execution_dispatch_org_counters
           SET leased_count = leased_count + 1,
               queued_count = greatest(queued_count - 1, 0), updated_at = now()
         WHERE execution_dispatch_org_counters.organization_id = v_job.organization_id;

        PERFORM elmos_mtf_append_job_event(
            v_job.job_id,
            'slot-claimed:' || (v_slot.lease_generation + 1)::text,
            'SLOT_CLAIMED', 'WAITING_FOR_SLOT', 'ADMITTED', 'claimed',
            v_job.progress, v_lease_id, p_runner_node_id, v_job.elapsed_millis,
            v_job.eta_p50_millis, v_job.eta_p90_millis, NULL);

        job_id := v_job.job_id;
        organization_id := v_job.organization_id;
        lease_id := v_lease_id;
        lease_expires_at := v_expires;
        business_line := v_job.business_line;
        job_kind := v_job.job_kind;
        runner_image := v_job.runner_image;
        budget_wall_seconds := v_job.budget_wall_seconds;
        budget_cpu_millis := v_job.budget_cpu_millis;
        budget_memory_mib := v_job.budget_memory_mib;
        attempt := (v_job.attempt + 1)::smallint;
        checkpoint_cursor := v_job.checkpoint_cursor;
        request_payload := v_job.request_payload;
        RETURN NEXT;
    END LOOP;
    RETURN;
END;
$$;

REVOKE ALL ON FUNCTION elmos_mtf_claim_execution_jobs(
    varchar, text[], text[], integer, integer, text[], text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION elmos_mtf_claim_execution_jobs(
    varchar, text[], text[], integer, integer, text[], text[])
    TO elmos_mtf_workflow;

-- A runner may report one final safe-point heartbeat after the account owner
-- requests a pause. V77 recorded that heartbeat as RUNNING even though the
-- durable control state was already PAUSE_REQUESTED. That manufactured an
-- illegal PAUSE_REQUESTED -> RUNNING edge during analytics replay. Normalize
-- historical rows from that exact interval and keep future writes canonical.
WITH paused_progress AS (
    SELECT progress.job_event_id
      FROM execution_job_events progress
     WHERE progress.event_type = 'PROGRESS_RECORDED'
       AND progress.to_status = 'RUNNING'
       AND EXISTS (
           SELECT 1
             FROM execution_job_events pause
            WHERE pause.job_id = progress.job_id
              AND pause.run_number = progress.run_number
              AND pause.sequence_no < progress.sequence_no
              AND pause.to_status = 'PAUSE_REQUESTED'
              AND NOT EXISTS (
                  SELECT 1
                    FROM execution_job_events boundary
                   WHERE boundary.job_id = progress.job_id
                     AND boundary.run_number = progress.run_number
                     AND boundary.sequence_no > pause.sequence_no
                     AND boundary.sequence_no < progress.sequence_no
                     AND boundary.to_status IN (
                         'PAUSED', 'RESUME_REQUESTED', 'WAITING_FOR_SLOT',
                         'QUEUED', 'ADMITTED', 'CLAIMED', 'SUCCEEDED',
                         'PARTIAL', 'FAILED', 'CANCELLED', 'UNKNOWN_RESULT',
                         'RECONCILING', 'LOST'
                     )
              )
       )
)
UPDATE execution_job_events event
   SET from_status = 'PAUSE_REQUESTED',
       to_status = 'PAUSE_REQUESTED'
  FROM paused_progress
 WHERE event.job_event_id = paused_progress.job_event_id;

CREATE FUNCTION elmos_mtf_normalize_paused_progress_event()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    IF NEW.event_type = 'PROGRESS_RECORDED'
       AND NEW.to_status = 'RUNNING'
       AND EXISTS (
           SELECT 1
             FROM execution_jobs job
            WHERE job.job_id = NEW.job_id
              AND job.organization_id = NEW.organization_id
              AND job.account_id = NEW.account_id
              AND job.control_state = 'PAUSE_REQUESTED'
       ) THEN
        NEW.from_status := 'PAUSE_REQUESTED';
        NEW.to_status := 'PAUSE_REQUESTED';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION elmos_mtf_normalize_paused_progress_event() FROM PUBLIC;
CREATE TRIGGER execution_job_events_pause_progress_normalize
BEFORE INSERT ON execution_job_events
FOR EACH ROW EXECUTE FUNCTION elmos_mtf_normalize_paused_progress_event();
