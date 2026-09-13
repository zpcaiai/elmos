-- The new hosted translation kind preserves preflight-before-metering.
-- Earlier job kinds retain their established settlement facts and policy.
ALTER TABLE execution_jobs ADD COLUMN metering_started_at timestamptz;
ALTER TABLE execution_jobs ADD CONSTRAINT translation_pipeline_metering_contract CHECK (
    job_kind <> 'translate-pipeline-v1' OR (
        business_line = 'TRANSLATION' AND max_attempts = 1
        AND (status NOT IN ('SUCCEEDED', 'PARTIAL') OR metering_started_at IS NOT NULL)
        AND (metering_started_at IS NULL
             OR (started_at IS NOT NULL AND metering_started_at >= started_at))
    )
);
COMMENT ON COLUMN execution_jobs.metering_started_at IS
    'Database clock, written once by a valid fenced pipeline heartbeat after trusted preflight. Not a caller timestamp. New translate-pipeline-v1 only; legacy kinds keep started_at semantics.';

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
      FROM execution_job_dispatch WHERE lease_ref = p_lease_id FOR UPDATE;
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
    IF v_lease.expires_at <= clock_timestamp() THEN
        RAISE EXCEPTION 'ELMOS_LEASE_EXPIRED';
    END IF;

    IF p_lease_seconds IS NULL OR p_lease_seconds < 30 OR p_lease_seconds > 3600 THEN
        RAISE EXCEPTION 'ELMOS_CLAIM_LEASE_SECONDS_INVALID';
    END IF;

    -- These writes can wait behind another transaction. Obtain their locks in
    -- the established dispatch -> lease -> runner -> job order BEFORE the final
    -- authorization clock check or renewal. Waiting is not a lease extension.
    PERFORM 1 FROM runner_nodes WHERE runner_node_id = p_runner_node_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_RUNNER_UNKNOWN'; END IF;
    PERFORM 1 FROM execution_jobs WHERE job_id = v_lease.job_ref FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_EXECUTION_JOB_UNKNOWN'; END IF;
    IF v_lease.expires_at <= clock_timestamp() THEN
        RAISE EXCEPTION 'ELMOS_LEASE_EXPIRED';
    END IF;
    v_expires := clock_timestamp() + make_interval(secs => p_lease_seconds);

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
           metering_started_at = CASE
               WHEN business_line = 'TRANSLATION' AND job_kind = 'translate-pipeline-v1'
                    AND p_stage = 'pipeline' AND cancel_requested_at IS NULL
               THEN coalesce(metering_started_at, clock_timestamp())
               ELSE metering_started_at END,
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


CREATE OR REPLACE FUNCTION elmos_wallet_settlement_facts(
    p_organization_id varchar,
    p_job_id varchar
) RETURNS TABLE (
    status varchar, failure_code varchar, business_line varchar, job_kind varchar,
    budget_wall_seconds integer, elapsed_seconds integer, chargeable_failure boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_previous text;
BEGIN
    v_previous := elmos_wallet_bind_tenant(p_organization_id);
    RETURN QUERY
    SELECT j.status, j.failure_code, j.business_line, j.job_kind, j.budget_wall_seconds,
           -- A job that never started took no time, whatever the clock says about
           -- how long it sat in the queue. Queue time is our latency, not theirs.
           CASE WHEN j.business_line = 'TRANSLATION' AND j.job_kind = 'translate-pipeline-v1'
                THEN CASE WHEN j.metering_started_at IS NULL THEN 0
                          ELSE greatest(0, extract(epoch FROM
                              coalesce(j.finished_at, now()) - j.metering_started_at)::integer) END
                WHEN j.started_at IS NULL THEN 0
                ELSE greatest(0, extract(epoch FROM
                        coalesce(j.finished_at, now()) - j.started_at)::integer) END,
           EXISTS (SELECT 1 FROM wallet_chargeable_failure_codes f
                    WHERE f.failure_code = j.failure_code)
      FROM execution_jobs j
     WHERE j.organization_id = p_organization_id AND j.job_id = p_job_id;
    PERFORM set_config('app.organization_id', v_previous, true);
END;
$$;
