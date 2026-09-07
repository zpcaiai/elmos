-- Reference stored procedures for race-free admission, ordered events,
-- task leasing/fencing, checkpoints, idempotent side effects and completion gates.
-- Revoke EXECUTE from PUBLIC in deployment and grant only to dedicated service roles.

BEGIN;

CREATE OR REPLACE FUNCTION core.claim_account_slot(
  p_tenant_id uuid,
  p_account_id uuid,
  p_run_id uuid,
  p_ttl interval DEFAULT interval '2 minutes'
)
RETURNS TABLE(claimed_slot_no smallint, claimed_generation bigint, claimed_token uuid, claimed_until timestamptz)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, core, exec
AS $$
DECLARE
  v_limit smallint;
  v_slot core.account_task_slot%ROWTYPE;
BEGIN
  IF p_ttl <= interval '0 seconds' THEN
    RAISE EXCEPTION 'slot TTL must be positive';
  END IF;

  SELECT concurrency_limit INTO v_limit
  FROM core.account
  WHERE tenant_id = p_tenant_id AND id = p_account_id AND status = 'active'
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'active account not found';
  END IF;
  IF v_limit = 0 THEN
    RETURN;
  END IF;

  PERFORM 1
  FROM exec.run
  WHERE tenant_id = p_tenant_id AND id = p_run_id AND account_id = p_account_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'run/account mismatch';
  END IF;

  SELECT * INTO v_slot
  FROM core.account_task_slot
  WHERE tenant_id = p_tenant_id
    AND account_id = p_account_id
    AND slot_no <= v_limit
    AND claimed_by_run_id = p_run_id
  FOR UPDATE;

  IF FOUND THEN
    UPDATE core.account_task_slot
    SET renewed_at = clock_timestamp(),
        lease_expires_at = clock_timestamp() + p_ttl
    WHERE tenant_id = p_tenant_id AND account_id = p_account_id AND slot_no = v_slot.slot_no
    RETURNING slot_no, lease_generation, claim_token, lease_expires_at
      INTO claimed_slot_no, claimed_generation, claimed_token, claimed_until;
    RETURN NEXT;
    RETURN;
  END IF;

  SELECT * INTO v_slot
  FROM core.account_task_slot
  WHERE tenant_id = p_tenant_id
    AND account_id = p_account_id
    AND slot_no <= v_limit
    AND (claimed_by_run_id IS NULL OR lease_expires_at <= clock_timestamp())
  ORDER BY slot_no
  FOR UPDATE SKIP LOCKED
  LIMIT 1;

  IF NOT FOUND THEN
    RETURN;
  END IF;

  UPDATE core.account_task_slot
  SET claimed_by_run_id = p_run_id,
      claim_token = extensions.gen_random_uuid(),
      lease_generation = lease_generation + 1,
      claimed_at = clock_timestamp(),
      renewed_at = clock_timestamp(),
      lease_expires_at = clock_timestamp() + p_ttl
  WHERE tenant_id = p_tenant_id AND account_id = p_account_id AND slot_no = v_slot.slot_no
  RETURNING slot_no, lease_generation, claim_token, lease_expires_at
    INTO claimed_slot_no, claimed_generation, claimed_token, claimed_until;

  UPDATE exec.run
  SET slot_no = claimed_slot_no,
      slot_lease_generation = claimed_generation,
      status = CASE WHEN status IN ('created', 'admitting', 'admission_wait') THEN 'planning' ELSE status END,
      updated_at = clock_timestamp()
  WHERE tenant_id = p_tenant_id AND id = p_run_id;

  RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION core.renew_account_slot(
  p_tenant_id uuid,
  p_account_id uuid,
  p_run_id uuid,
  p_slot_no smallint,
  p_generation bigint,
  p_claim_token uuid,
  p_ttl interval DEFAULT interval '2 minutes'
)
RETURNS timestamptz
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, core
AS $$
DECLARE v_until timestamptz;
BEGIN
  UPDATE core.account_task_slot
  SET renewed_at = clock_timestamp(), lease_expires_at = clock_timestamp() + p_ttl
  WHERE tenant_id = p_tenant_id
    AND account_id = p_account_id
    AND slot_no = p_slot_no
    AND claimed_by_run_id = p_run_id
    AND lease_generation = p_generation
    AND claim_token = p_claim_token
    AND lease_expires_at > clock_timestamp()
  RETURNING lease_expires_at INTO v_until;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'stale or expired account slot lease' USING ERRCODE = '40001';
  END IF;
  RETURN v_until;
END;
$$;

CREATE OR REPLACE FUNCTION core.release_account_slot(
  p_tenant_id uuid,
  p_account_id uuid,
  p_run_id uuid,
  p_generation bigint
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, core
AS $$
BEGIN
  UPDATE core.account_task_slot
  SET claimed_by_run_id = NULL,
      claim_token = NULL,
      claimed_at = NULL,
      renewed_at = NULL,
      lease_expires_at = NULL
  WHERE tenant_id = p_tenant_id
    AND account_id = p_account_id
    AND claimed_by_run_id = p_run_id
    AND lease_generation = p_generation;
  RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION exec.create_run(
  p_tenant_id uuid,
  p_job_id uuid,
  p_run_kind text,
  p_input_bundle_sha256 text,
  p_source_repository_revision_id uuid,
  p_baseline_repository_revision_id uuid,
  p_target_repository_revision_id uuid,
  p_requirements_revision_id uuid,
  p_policy_revision_id uuid,
  p_workflow_revision_id uuid,
  p_model_route_revision_id uuid,
  p_toolchain_revision_id uuid,
  p_environment_revision_id uuid,
  p_archetype_revision_id uuid DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, core, exec
AS $$
DECLARE
  v_job core.job%ROWTYPE;
  v_run_id uuid;
  v_run_no integer;
  v_slot record;
BEGIN
  IF NOT core.sha256_is_valid(p_input_bundle_sha256) THEN
    RAISE EXCEPTION 'invalid input bundle sha256';
  END IF;

  SELECT * INTO v_job
  FROM core.job
  WHERE tenant_id = p_tenant_id AND id = p_job_id
  FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'job not found'; END IF;
  IF v_job.status IN ('completed', 'cancelled', 'archived') THEN
    RAISE EXCEPTION 'job is terminal';
  END IF;

  SELECT COALESCE(max(run_no), 0) + 1 INTO v_run_no
  FROM exec.run
  WHERE tenant_id = p_tenant_id AND job_id = p_job_id;

  INSERT INTO exec.run (
    tenant_id, job_id, account_id, run_no, run_kind, status,
    source_repository_revision_id, baseline_repository_revision_id,
    target_repository_revision_id, requirements_revision_id,
    policy_revision_id, workflow_revision_id, model_route_revision_id,
    toolchain_revision_id, environment_revision_id, archetype_revision_id,
    input_bundle_sha256
  ) VALUES (
    p_tenant_id, p_job_id, v_job.account_id, v_run_no, p_run_kind, 'admitting',
    p_source_repository_revision_id, p_baseline_repository_revision_id,
    p_target_repository_revision_id, p_requirements_revision_id,
    p_policy_revision_id, p_workflow_revision_id, p_model_route_revision_id,
    p_toolchain_revision_id, p_environment_revision_id, p_archetype_revision_id,
    p_input_bundle_sha256
  ) RETURNING id INTO v_run_id;

  UPDATE core.job
  SET current_run_id = v_run_id,
      status = 'admission_wait',
      updated_at = clock_timestamp()
  WHERE tenant_id = p_tenant_id AND id = p_job_id;

  SELECT * INTO v_slot
  FROM core.claim_account_slot(p_tenant_id, v_job.account_id, v_run_id);

  IF v_slot.claimed_slot_no IS NULL THEN
    UPDATE exec.run SET status = 'admission_wait' WHERE tenant_id = p_tenant_id AND id = v_run_id;
  ELSE
    UPDATE core.job
    SET status = 'admitted', admitted_at = COALESCE(admitted_at, clock_timestamp())
    WHERE tenant_id = p_tenant_id AND id = p_job_id;
  END IF;

  RETURN v_run_id;
END;
$$;

CREATE OR REPLACE FUNCTION exec.append_run_event(
  p_tenant_id uuid,
  p_run_id uuid,
  p_event_type text,
  p_payload jsonb,
  p_actor_kind text DEFAULT 'system',
  p_actor_id text DEFAULT NULL,
  p_task_id uuid DEFAULT NULL,
  p_task_attempt_id uuid DEFAULT NULL,
  p_correlation_id text DEFAULT NULL,
  p_causation_event_id uuid DEFAULT NULL
)
RETURNS TABLE(event_seq bigint, event_id uuid, event_hash text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, exec
AS $$
DECLARE
  v_next bigint;
  v_prev text;
  v_id uuid := extensions.gen_random_uuid();
  v_hash text;
BEGIN
  SELECT next_seq, last_event_hash INTO v_next, v_prev
  FROM exec.run_event_cursor
  WHERE tenant_id = p_tenant_id AND run_id = p_run_id
  FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'run event cursor not found'; END IF;

  v_hash := encode(extensions.digest(
    concat_ws('|', p_run_id::text, v_next::text, p_event_type, COALESCE(p_payload, '{}'::jsonb)::text, COALESCE(v_prev, '')),
    'sha256'
  ), 'hex');

  INSERT INTO exec.run_event (
    tenant_id, run_id, seq, event_id, event_type, actor_kind, actor_id,
    task_id, task_attempt_id, correlation_id, causation_event_id,
    payload, previous_event_hash, event_hash
  ) VALUES (
    p_tenant_id, p_run_id, v_next, v_id, p_event_type, p_actor_kind, p_actor_id,
    p_task_id, p_task_attempt_id, p_correlation_id, p_causation_event_id,
    COALESCE(p_payload, '{}'::jsonb), v_prev, v_hash
  );

  UPDATE exec.run_event_cursor
  SET next_seq = v_next + 1, last_event_hash = v_hash, updated_at = clock_timestamp()
  WHERE tenant_id = p_tenant_id AND run_id = p_run_id;

  event_seq := v_next; event_id := v_id; event_hash := v_hash;
  RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION exec.append_session_event(
  p_tenant_id uuid,
  p_session_id uuid,
  p_event_type text,
  p_payload jsonb,
  p_turn_no integer DEFAULT NULL,
  p_step_no integer DEFAULT NULL,
  p_model_visible boolean DEFAULT false,
  p_ignorable boolean DEFAULT false,
  p_artifact_id uuid DEFAULT NULL
)
RETURNS TABLE(event_seq bigint, event_id uuid, event_hash text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, exec
AS $$
DECLARE
  v_next bigint;
  v_prev text;
  v_run_id uuid;
  v_id uuid := extensions.gen_random_uuid();
  v_hash text;
BEGIN
  SELECT run_id INTO v_run_id
  FROM exec.session WHERE tenant_id = p_tenant_id AND id = p_session_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'session not found'; END IF;

  SELECT next_seq, last_event_hash INTO v_next, v_prev
  FROM exec.session_event_cursor
  WHERE tenant_id = p_tenant_id AND session_id = p_session_id
  FOR UPDATE;

  v_hash := encode(extensions.digest(
    concat_ws('|', p_session_id::text, v_next::text, p_event_type, p_payload::text, COALESCE(v_prev, '')),
    'sha256'
  ), 'hex');

  INSERT INTO exec.session_event (
    tenant_id, session_id, run_id, seq, event_id, event_type, turn_no, step_no,
    model_visible, ignorable, payload, artifact_id, previous_event_hash, event_hash
  ) VALUES (
    p_tenant_id, p_session_id, v_run_id, v_next, v_id, p_event_type, p_turn_no, p_step_no,
    p_model_visible, p_ignorable, p_payload, p_artifact_id, v_prev, v_hash
  );

  UPDATE exec.session_event_cursor
  SET next_seq = v_next + 1, last_event_hash = v_hash, updated_at = clock_timestamp()
  WHERE tenant_id = p_tenant_id AND session_id = p_session_id;

  UPDATE exec.session SET last_activity_at = clock_timestamp() WHERE tenant_id = p_tenant_id AND id = p_session_id;

  event_seq := v_next; event_id := v_id; event_hash := v_hash;
  RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION exec.refresh_run_progress(p_tenant_id uuid, p_run_id uuid)
RETURNS exec.run_progress_snapshot
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, exec
AS $$
DECLARE
  v_total integer;
  v_pending integer;
  v_running integer;
  v_succeeded integer;
  v_failed integer;
  v_blocked integer;
  v_progress integer;
  v_row exec.run_progress_snapshot%ROWTYPE;
BEGIN
  SELECT
    count(*)::integer,
    count(*) FILTER (WHERE status IN ('pending', 'ready', 'claimed'))::integer,
    count(*) FILTER (WHERE status IN ('running', 'waiting_async', 'waiting_human', 'pause_requested', 'paused'))::integer,
    count(*) FILTER (WHERE status IN ('succeeded', 'skipped', 'superseded'))::integer,
    count(*) FILTER (WHERE status IN ('failed', 'cancelled'))::integer,
    count(*) FILTER (WHERE status = 'blocked')::integer
  INTO v_total, v_pending, v_running, v_succeeded, v_failed, v_blocked
  FROM exec.task WHERE tenant_id = p_tenant_id AND run_id = p_run_id;

  v_progress := CASE WHEN v_total = 0 THEN 0 ELSE floor(10000.0 * v_succeeded / v_total)::integer END;

  UPDATE exec.run r
  SET progress_basis_points = v_progress,
      last_progress_at = clock_timestamp(),
      updated_at = clock_timestamp()
  WHERE r.tenant_id = p_tenant_id AND r.id = p_run_id;

  UPDATE exec.run_progress_snapshot p
  SET status = r.status,
      current_stage_key = r.current_stage_key,
      progress_basis_points = v_progress,
      total_tasks = v_total,
      pending_tasks = v_pending,
      running_tasks = v_running,
      succeeded_tasks = v_succeeded,
      failed_tasks = v_failed,
      blocked_tasks = v_blocked,
      version = p.version + 1,
      updated_at = clock_timestamp()
  FROM exec.run r
  WHERE p.tenant_id = p_tenant_id AND p.run_id = p_run_id
    AND r.tenant_id = p.tenant_id AND r.id = p.run_id
  RETURNING p.* INTO v_row;

  RETURN v_row;
END;
$$;

CREATE OR REPLACE FUNCTION exec.claim_ready_task(
  p_tenant_id uuid,
  p_run_id uuid,
  p_worker_node_id uuid,
  p_lease_ttl interval DEFAULT interval '5 minutes'
)
RETURNS TABLE(task_id uuid, task_attempt_id uuid, attempt_no smallint, lease_generation bigint, lease_token uuid, fencing_token uuid)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, exec
AS $$
DECLARE
  v_task exec.task%ROWTYPE;
  v_attempt_no smallint;
  v_attempt_id uuid;
  v_fence uuid;
  v_generation bigint;
  v_lease_token uuid;
  v_run_attempt_id uuid;
BEGIN
  PERFORM 1 FROM exec.run
  WHERE tenant_id = p_tenant_id AND id = p_run_id
    AND status IN ('planning', 'ready', 'running', 'verifying', 'repairing')
  FOR UPDATE;
  IF NOT FOUND THEN RETURN; END IF;

  SELECT t.* INTO v_task
  FROM exec.task t
  WHERE t.tenant_id = p_tenant_id
    AND t.run_id = p_run_id
    AND t.status IN ('pending', 'ready')
    AND (t.not_before IS NULL OR t.not_before <= clock_timestamp())
    AND NOT EXISTS (
      SELECT 1
      FROM exec.task_dependency d
      JOIN exec.task upstream
        ON upstream.tenant_id = d.tenant_id AND upstream.id = d.depends_on_task_id
      WHERE d.tenant_id = t.tenant_id AND d.task_id = t.id
        AND (
          (d.dependency_kind IN ('success', 'artifact', 'evidence') AND upstream.status NOT IN ('succeeded', 'skipped', 'superseded'))
          OR (d.dependency_kind = 'completion' AND upstream.status NOT IN ('succeeded', 'failed', 'cancelled', 'blocked', 'skipped', 'superseded'))
        )
    )
    AND (SELECT count(*) FROM exec.task_attempt a WHERE a.tenant_id = t.tenant_id AND a.task_id = t.id) < t.max_attempts
  ORDER BY t.priority DESC, t.created_at, t.id
  FOR UPDATE SKIP LOCKED
  LIMIT 1;

  IF NOT FOUND THEN RETURN; END IF;

  SELECT COALESCE(max(a.attempt_no), 0) + 1 INTO v_attempt_no
  FROM exec.task_attempt a WHERE a.tenant_id = p_tenant_id AND a.task_id = v_task.id;

  SELECT id INTO v_run_attempt_id
  FROM exec.run_attempt
  WHERE tenant_id = p_tenant_id AND run_id = p_run_id AND status IN ('starting', 'running')
  ORDER BY attempt_no DESC LIMIT 1;

  v_attempt_id := extensions.gen_random_uuid();
  v_fence := extensions.gen_random_uuid();

  INSERT INTO exec.task_attempt (
    id, tenant_id, run_id, task_id, attempt_no, run_attempt_id, status,
    worker_node_id, lease_generation, fencing_token, claimed_at, last_heartbeat_at
  ) VALUES (
    v_attempt_id, p_tenant_id, p_run_id, v_task.id, v_attempt_no, v_run_attempt_id, 'claimed',
    p_worker_node_id, 1, v_fence, clock_timestamp(), clock_timestamp()
  );

  UPDATE exec.execution_lease
  SET released_at = clock_timestamp(), release_reason = 'expired_reclaimed'
  WHERE tenant_id = p_tenant_id AND resource_kind = 'task' AND resource_id = v_task.id
    AND released_at IS NULL AND expires_at <= clock_timestamp();

  SELECT COALESCE(max(l.lease_generation), 0) + 1 INTO v_generation
  FROM exec.execution_lease l
  WHERE l.tenant_id = p_tenant_id AND l.resource_kind = 'task' AND l.resource_id = v_task.id;
  v_lease_token := extensions.gen_random_uuid();

  INSERT INTO exec.execution_lease (
    tenant_id, run_id, resource_kind, resource_id, holder_kind, holder_id,
    lease_token, lease_generation, expires_at
  ) VALUES (
    p_tenant_id, p_run_id, 'task', v_task.id, 'worker', p_worker_node_id::text,
    v_lease_token, v_generation, clock_timestamp() + p_lease_ttl
  );

  UPDATE exec.task_attempt SET lease_generation = v_generation WHERE tenant_id = p_tenant_id AND id = v_attempt_id;
  UPDATE exec.task
  SET status = 'claimed', current_attempt_id = v_attempt_id, started_at = COALESCE(started_at, clock_timestamp())
  WHERE tenant_id = p_tenant_id AND id = v_task.id;

  task_id := v_task.id; task_attempt_id := v_attempt_id; attempt_no := v_attempt_no;
  lease_generation := v_generation; lease_token := v_lease_token; fencing_token := v_fence;
  RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION exec.renew_task_lease(
  p_tenant_id uuid,
  p_task_attempt_id uuid,
  p_lease_token uuid,
  p_generation bigint,
  p_fencing_token uuid,
  p_ttl interval DEFAULT interval '5 minutes'
)
RETURNS timestamptz
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, exec
AS $$
DECLARE v_until timestamptz; v_task_id uuid;
BEGIN
  SELECT task_id INTO v_task_id
  FROM exec.task_attempt
  WHERE tenant_id = p_tenant_id AND id = p_task_attempt_id AND fencing_token = p_fencing_token
  FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'stale task attempt fencing token' USING ERRCODE = '40001'; END IF;

  UPDATE exec.execution_lease
  SET renewed_at = clock_timestamp(), expires_at = clock_timestamp() + p_ttl
  WHERE tenant_id = p_tenant_id
    AND resource_kind = 'task'
    AND resource_id = v_task_id
    AND lease_token = p_lease_token
    AND lease_generation = p_generation
    AND released_at IS NULL
    AND expires_at > clock_timestamp()
  RETURNING expires_at INTO v_until;
  IF NOT FOUND THEN RAISE EXCEPTION 'stale or expired task lease' USING ERRCODE = '40001'; END IF;

  UPDATE exec.task_attempt SET last_heartbeat_at = clock_timestamp(), status = CASE WHEN status = 'claimed' THEN 'running' ELSE status END
  WHERE tenant_id = p_tenant_id AND id = p_task_attempt_id;
  UPDATE exec.task SET status = CASE WHEN status = 'claimed' THEN 'running' ELSE status END
  WHERE tenant_id = p_tenant_id AND id = v_task_id;
  RETURN v_until;
END;
$$;

CREATE OR REPLACE FUNCTION exec.finish_task_attempt(
  p_tenant_id uuid,
  p_task_attempt_id uuid,
  p_lease_token uuid,
  p_generation bigint,
  p_fencing_token uuid,
  p_outcome text,
  p_retryable boolean DEFAULT false,
  p_output_manifest_id uuid DEFAULT NULL,
  p_checkpoint_id uuid DEFAULT NULL,
  p_failure_code text DEFAULT NULL,
  p_failure_detail jsonb DEFAULT NULL
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, exec
AS $$
DECLARE
  v_attempt exec.task_attempt%ROWTYPE;
  v_task exec.task%ROWTYPE;
  v_task_status text;
BEGIN
  IF p_outcome NOT IN ('succeeded', 'failed', 'timed_out', 'cancelled', 'interrupted') THEN
    RAISE EXCEPTION 'invalid task attempt outcome';
  END IF;

  SELECT * INTO v_attempt FROM exec.task_attempt
  WHERE tenant_id = p_tenant_id AND id = p_task_attempt_id AND fencing_token = p_fencing_token
  FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'stale task attempt' USING ERRCODE = '40001'; END IF;

  PERFORM 1 FROM exec.execution_lease
  WHERE tenant_id = p_tenant_id AND resource_kind = 'task' AND resource_id = v_attempt.task_id
    AND lease_token = p_lease_token AND lease_generation = p_generation
    AND released_at IS NULL AND expires_at > clock_timestamp()
  FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'stale or expired lease; result rejected' USING ERRCODE = '40001'; END IF;

  SELECT * INTO v_task FROM exec.task
  WHERE tenant_id = p_tenant_id AND id = v_attempt.task_id FOR UPDATE;

  UPDATE exec.task_attempt
  SET status = p_outcome,
      output_manifest_id = p_output_manifest_id,
      checkpoint_id = p_checkpoint_id,
      failure_code = p_failure_code,
      failure_detail = p_failure_detail,
      ended_at = clock_timestamp(),
      last_heartbeat_at = clock_timestamp()
  WHERE tenant_id = p_tenant_id AND id = p_task_attempt_id;

  IF p_outcome = 'succeeded' THEN
    v_task_status := 'succeeded';
  ELSIF p_retryable AND v_attempt.attempt_no < v_task.max_attempts THEN
    v_task_status := 'ready';
  ELSIF p_outcome = 'cancelled' THEN
    v_task_status := 'cancelled';
  ELSE
    v_task_status := 'failed';
  END IF;

  UPDATE exec.task
  SET status = v_task_status,
      output_manifest_id = COALESCE(p_output_manifest_id, output_manifest_id),
      last_checkpoint_id = COALESCE(p_checkpoint_id, last_checkpoint_id),
      ended_at = CASE WHEN v_task_status IN ('succeeded', 'failed', 'cancelled') THEN clock_timestamp() ELSE NULL END
  WHERE tenant_id = p_tenant_id AND id = v_attempt.task_id;

  UPDATE exec.execution_lease
  SET released_at = clock_timestamp(), release_reason = p_outcome
  WHERE tenant_id = p_tenant_id AND resource_kind = 'task' AND resource_id = v_attempt.task_id
    AND lease_token = p_lease_token AND lease_generation = p_generation;

  PERFORM exec.append_run_event(
    p_tenant_id, v_attempt.run_id, 'task.attempt_finished',
    jsonb_build_object('task_id', v_attempt.task_id, 'task_attempt_id', p_task_attempt_id, 'outcome', p_outcome, 'task_status', v_task_status),
    'worker', v_attempt.worker_node_id::text, v_attempt.task_id, p_task_attempt_id
  );
  PERFORM exec.refresh_run_progress(p_tenant_id, v_attempt.run_id);
  RETURN v_task_status;
END;
$$;

CREATE OR REPLACE FUNCTION exec.seal_checkpoint(p_tenant_id uuid, p_checkpoint_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, exec, artifact
AS $$
DECLARE v_manifest_id uuid;
BEGIN
  SELECT manifest_id INTO v_manifest_id
  FROM exec.checkpoint
  WHERE tenant_id = p_tenant_id AND id = p_checkpoint_id AND status = 'preparing'
  FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'preparing checkpoint not found'; END IF;

  IF NOT EXISTS (
    SELECT 1 FROM artifact.manifest
    WHERE tenant_id = p_tenant_id AND id = v_manifest_id AND sealed = true
  ) THEN RAISE EXCEPTION 'checkpoint manifest is not sealed'; END IF;

  IF EXISTS (
    SELECT 1
    FROM exec.checkpoint_component c
    LEFT JOIN artifact.artifact a ON a.tenant_id = c.tenant_id AND a.id = c.artifact_id
    WHERE c.tenant_id = p_tenant_id AND c.checkpoint_id = p_checkpoint_id
      AND c.required_for_resume
      AND (a.id IS NULL OR a.state <> 'available')
  ) THEN RAISE EXCEPTION 'required checkpoint component unavailable'; END IF;

  UPDATE exec.checkpoint SET status = 'sealed', sealed_at = clock_timestamp()
  WHERE tenant_id = p_tenant_id AND id = p_checkpoint_id;
  RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION integration.reserve_side_effect(
  p_tenant_id uuid,
  p_run_id uuid,
  p_task_id uuid,
  p_task_attempt_id uuid,
  p_tool_invocation_id uuid,
  p_effect_kind text,
  p_destination text,
  p_idempotency_key text,
  p_request_sha256 text
)
RETURNS integration.side_effect_receipt
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, integration
AS $$
DECLARE v_row integration.side_effect_receipt%ROWTYPE;
BEGIN
  INSERT INTO integration.side_effect_receipt (
    tenant_id, run_id, task_id, task_attempt_id, tool_invocation_id,
    effect_kind, destination, idempotency_key, request_sha256
  ) VALUES (
    p_tenant_id, p_run_id, p_task_id, p_task_attempt_id, p_tool_invocation_id,
    p_effect_kind, p_destination, p_idempotency_key, p_request_sha256
  )
  ON CONFLICT (tenant_id, destination, idempotency_key) DO NOTHING;

  SELECT * INTO v_row FROM integration.side_effect_receipt
  WHERE tenant_id = p_tenant_id AND destination = p_destination AND idempotency_key = p_idempotency_key
  FOR UPDATE;

  IF v_row.request_sha256 <> p_request_sha256 THEN
    RAISE EXCEPTION 'idempotency key reused with different request' USING ERRCODE = '23505';
  END IF;
  RETURN v_row;
END;
$$;

CREATE OR REPLACE FUNCTION verify.complete_run_with_gate(
  p_tenant_id uuid,
  p_run_id uuid,
  p_gate_evaluation_id uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, core, exec, verify, integration
AS $$
DECLARE
  v_run exec.run%ROWTYPE;
  v_gate verify.gate_evaluation%ROWTYPE;
  v_bundle verify.evidence_bundle%ROWTYPE;
  v_unfinished bigint;
  v_open_gaps bigint;
  v_side_effects bigint;
  v_bundle_count bigint;
  v_req_total bigint;
  v_req_ok bigint;
  v_cap_total bigint;
  v_cap_ok bigint;
  v_req_pct numeric(6,3);
  v_cap_pct numeric(6,3);
  v_missing_required_suites bigint;
BEGIN
  SELECT * INTO v_run FROM exec.run
  WHERE tenant_id = p_tenant_id AND id = p_run_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'run not found'; END IF;
  IF v_run.status IN ('completed', 'cancelled', 'archived') THEN RETURN v_run.status = 'completed'; END IF;

  SELECT * INTO v_gate FROM verify.gate_evaluation
  WHERE tenant_id = p_tenant_id AND id = p_gate_evaluation_id AND run_id = p_run_id;
  IF NOT FOUND OR v_gate.decision <> 'pass' THEN RAISE EXCEPTION 'passing gate not found'; END IF;

  IF v_gate.target_revision_id IS DISTINCT FROM v_run.current_target_revision_id
     OR v_gate.source_repository_revision_id IS DISTINCT FROM v_run.source_repository_revision_id
     OR v_gate.requirements_revision_id IS DISTINCT FROM v_run.requirements_revision_id
     OR v_gate.policy_revision_id <> v_run.policy_revision_id
     OR v_gate.workflow_revision_id <> v_run.workflow_revision_id
     OR v_gate.model_route_revision_id <> v_run.model_route_revision_id
     OR v_gate.toolchain_revision_id <> v_run.toolchain_revision_id
     OR v_gate.environment_revision_id <> v_run.environment_revision_id THEN
    RAISE EXCEPTION 'gate revision binding does not match run';
  END IF;

  SELECT * INTO v_bundle FROM verify.evidence_bundle
  WHERE tenant_id = p_tenant_id AND id = v_gate.evidence_bundle_id
    AND run_id = p_run_id AND target_revision_id = v_run.current_target_revision_id;
  IF NOT FOUND OR v_bundle.status <> 'sealed' THEN RAISE EXCEPTION 'evidence bundle is not sealed'; END IF;

  SELECT count(*) INTO v_bundle_count
  FROM verify.evidence_bundle_item
  WHERE tenant_id = p_tenant_id AND evidence_bundle_id = v_bundle.id;
  IF v_bundle_count = 0 OR v_bundle_count <> v_bundle.evidence_count THEN
    RAISE EXCEPTION 'evidence bundle count mismatch';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM verify.evidence_bundle_item bi
    JOIN verify.evidence_item ei ON ei.tenant_id = bi.tenant_id AND ei.id = bi.evidence_item_id
    LEFT JOIN verify.evidence_revocation er ON er.tenant_id = ei.tenant_id AND er.evidence_item_id = ei.id
    WHERE bi.tenant_id = p_tenant_id AND bi.evidence_bundle_id = v_bundle.id
      AND (er.id IS NOT NULL
           OR ei.run_id <> p_run_id
           OR ei.target_revision_id <> v_run.current_target_revision_id
           OR ei.environment_revision_id <> v_run.environment_revision_id
           OR ei.toolchain_revision_id <> v_run.toolchain_revision_id
           OR (ei.freshness_deadline IS NOT NULL AND ei.freshness_deadline <= clock_timestamp()))
  ) THEN RAISE EXCEPTION 'evidence bundle contains foreign, revoked or stale evidence'; END IF;

  SELECT count(*), count(*) FILTER (WHERE coverage_status IN ('verified', 'waived'))
  INTO v_req_total, v_req_ok
  FROM verify.requirement_coverage
  WHERE tenant_id = p_tenant_id AND run_id = p_run_id
    AND target_revision_id = v_run.current_target_revision_id;
  v_req_pct := CASE WHEN v_req_total = 0 THEN 100.000 ELSE round(100.0 * v_req_ok / v_req_total, 3) END;

  SELECT count(*), count(*) FILTER (WHERE coverage_status IN ('verified', 'waived'))
  INTO v_cap_total, v_cap_ok
  FROM verify.capability_coverage
  WHERE tenant_id = p_tenant_id AND run_id = p_run_id
    AND target_revision_id = v_run.current_target_revision_id;
  v_cap_pct := CASE WHEN v_cap_total = 0 THEN 100.000 ELSE round(100.0 * v_cap_ok / v_cap_total, 3) END;

  -- Project generation and repository conversion must never obtain a vacuous
  -- 100% score from empty ledgers.
  IF v_run.run_kind IN ('project_generation', 'repository_conversion')
     AND (v_req_total = 0 OR v_cap_total = 0) THEN
    RAISE EXCEPTION 'generation/conversion completion requires non-empty requirement and capability ledgers';
  END IF;

  IF abs(v_req_pct - v_gate.requirement_coverage) > 0.001
     OR abs(v_cap_pct - v_gate.capability_coverage) > 0.001 THEN
    RAISE EXCEPTION 'gate coverage summary does not match authoritative coverage ledgers';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM verify.requirement req
    LEFT JOIN verify.requirement_coverage cov
      ON cov.tenant_id = req.tenant_id AND cov.requirement_id = req.id
      AND cov.target_revision_id = v_run.current_target_revision_id
    WHERE req.tenant_id = p_tenant_id AND req.run_id = p_run_id
      AND req.criticality = 'critical'
      AND COALESCE(cov.coverage_status, 'unmapped') NOT IN ('verified', 'waived')
  ) THEN RAISE EXCEPTION 'critical requirement is not verified or waived'; END IF;

  SELECT count(*) INTO v_missing_required_suites
  FROM verify.verification_suite s
  JOIN verify.verification_plan p ON p.tenant_id = s.tenant_id AND p.id = s.verification_plan_id
  WHERE s.tenant_id = p_tenant_id AND s.run_id = p_run_id AND s.required
    AND p.target_revision_id = v_run.current_target_revision_id
    AND NOT EXISTS (
      SELECT 1 FROM verify.verification_execution x
      WHERE x.tenant_id = s.tenant_id AND x.suite_id = s.id
        AND x.target_revision_id = v_run.current_target_revision_id AND x.status = 'passed'
    );
  IF v_missing_required_suites <> 0 THEN RAISE EXCEPTION 'required verification suite has no passing execution'; END IF;

  SELECT count(*) INTO v_unfinished FROM exec.task
  WHERE tenant_id = p_tenant_id AND run_id = p_run_id
    AND status NOT IN ('succeeded', 'skipped', 'superseded');
  SELECT count(*) INTO v_open_gaps FROM verify.semantic_gap
  WHERE tenant_id = p_tenant_id AND run_id = p_run_id
    AND status IN ('open', 'triaged', 'repairing', 'blocked')
    AND (gap_kind = 'unknown' OR severity IN ('high', 'critical'));
  SELECT count(*) INTO v_side_effects FROM integration.side_effect_receipt
  WHERE tenant_id = p_tenant_id AND run_id = p_run_id
    AND status IN ('reserved', 'dispatching', 'unknown_result', 'reconciling', 'compensating');

  IF v_unfinished <> 0 OR v_open_gaps <> 0 OR v_side_effects <> 0
     OR v_gate.unfinished_task_count <> 0 OR v_gate.unknown_gap_count <> 0
     OR v_gate.critical_failure_count <> 0 OR v_gate.unresolved_side_effect_count <> 0 THEN
    RAISE EXCEPTION 'completion invariants failed: unfinished=%, gaps=%, side_effects=%', v_unfinished, v_open_gaps, v_side_effects;
  END IF;

  UPDATE exec.run
  SET status = 'completed', completion_gate_evaluation_id = v_gate.id,
      progress_basis_points = 10000, completed_at = clock_timestamp(), updated_at = clock_timestamp()
  WHERE tenant_id = p_tenant_id AND id = p_run_id;

  -- A superseded/older Run may finish after the Job has already moved to a
  -- newer current_run_id. Record it as a successful Run, but only close the Job
  -- when this Run is still the authoritative current Run.
  UPDATE core.job
  SET latest_successful_run_id = p_run_id,
      status = CASE WHEN current_run_id = p_run_id THEN 'completed' ELSE status END,
      completed_at = CASE WHEN current_run_id = p_run_id THEN clock_timestamp() ELSE completed_at END,
      updated_at = clock_timestamp()
  WHERE tenant_id = p_tenant_id AND id = v_run.job_id;

  PERFORM exec.append_run_event(
    p_tenant_id, p_run_id, 'run.completed',
    jsonb_build_object('gate_evaluation_id', v_gate.id, 'target_revision_id', v_gate.target_revision_id, 'evidence_bundle_id', v_bundle.id),
    'system', 'p05-completion-gate'
  );

  INSERT INTO integration.outbox_event (
    tenant_id, aggregate_type, aggregate_id, event_type, correlation_id, payload, payload_sha256
  ) VALUES (
    p_tenant_id, 'run', p_run_id, 'run.completed', p_run_id::text,
    jsonb_build_object('run_id', p_run_id, 'job_id', v_run.job_id, 'gate_evaluation_id', v_gate.id),
    encode(extensions.digest(jsonb_build_object('run_id', p_run_id, 'job_id', v_run.job_id, 'gate_evaluation_id', v_gate.id)::text, 'sha256'), 'hex')
  ) ON CONFLICT DO NOTHING;

  IF v_run.slot_no IS NOT NULL AND v_run.slot_lease_generation IS NOT NULL THEN
    PERFORM core.release_account_slot(p_tenant_id, v_run.account_id, p_run_id, v_run.slot_lease_generation);
  END IF;
  PERFORM exec.refresh_run_progress(p_tenant_id, p_run_id);
  RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION ops.complete_deployment_with_gate(
  p_tenant_id uuid,
  p_deployment_id uuid,
  p_gate_id uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, ops, integration
AS $$
DECLARE v_dep ops.deployment%ROWTYPE; v_gate ops.deployment_gate%ROWTYPE;
BEGIN
  SELECT * INTO v_dep FROM ops.deployment
  WHERE tenant_id = p_tenant_id AND id = p_deployment_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'deployment not found'; END IF;

  SELECT * INTO v_gate FROM ops.deployment_gate
  WHERE tenant_id = p_tenant_id AND id = p_gate_id AND deployment_id = p_deployment_id;
  IF NOT FOUND OR v_gate.decision <> 'pass' THEN RAISE EXCEPTION 'passing deployment gate not found'; END IF;
  IF v_gate.release_id <> v_dep.release_id THEN RAISE EXCEPTION 'deployment gate release mismatch'; END IF;

  IF EXISTS (
    SELECT 1 FROM ops.deployment_check
    WHERE tenant_id = p_tenant_id AND deployment_id = p_deployment_id
      AND status IN ('failed', 'blocked', 'not_run')
  ) THEN RAISE EXCEPTION 'deployment has unresolved checks'; END IF;

  IF EXISTS (
    SELECT 1
    FROM ops.release_component rc
    LEFT JOIN LATERAL (
      SELECT h.livez, h.readyz, h.image_digest
      FROM ops.service_health_snapshot h
      WHERE h.tenant_id = rc.tenant_id
        AND h.deployment_id = p_deployment_id
        AND h.release_component_id = rc.id
      ORDER BY h.observed_at DESC
      LIMIT 1
    ) latest ON true
    WHERE rc.tenant_id = p_tenant_id
      AND rc.release_id = v_dep.release_id
      AND rc.required
      AND rc.component_kind <> 'migration'
      AND (latest.livez IS DISTINCT FROM true
           OR latest.readyz IS DISTINCT FROM true
           OR latest.image_digest IS DISTINCT FROM rc.image_digest)
  ) THEN RAISE EXCEPTION 'one or more required release components are unhealthy or have the wrong image digest'; END IF;

  IF EXISTS (
    SELECT 1 FROM ops.release_component rc
    WHERE rc.tenant_id = p_tenant_id AND rc.release_id = v_dep.release_id
      AND rc.required AND rc.component_kind = 'migration'
  ) AND NOT EXISTS (
    SELECT 1 FROM ops.migration_run mr
    WHERE mr.tenant_id = p_tenant_id AND mr.deployment_id = p_deployment_id
      AND mr.status IN ('succeeded', 'not_required')
  ) THEN RAISE EXCEPTION 'required database migration has not succeeded'; END IF;

  UPDATE ops.deployment SET status = 'healthy', completed_at = clock_timestamp()
  WHERE tenant_id = p_tenant_id AND id = p_deployment_id;
  UPDATE ops.release SET status = 'deployed'
  WHERE tenant_id = p_tenant_id AND id = v_dep.release_id;

  INSERT INTO integration.outbox_event (
    tenant_id, aggregate_type, aggregate_id, event_type, correlation_id, payload
  ) VALUES (
    p_tenant_id, 'deployment', p_deployment_id, 'deployment.completed', p_deployment_id::text,
    jsonb_build_object('deployment_id', p_deployment_id, 'release_id', v_dep.release_id, 'gate_id', p_gate_id)
  ) ON CONFLICT DO NOTHING;
  RETURN true;
END;
$$;

REVOKE ALL ON FUNCTION core.claim_account_slot(uuid, uuid, uuid, interval) FROM PUBLIC;
REVOKE ALL ON FUNCTION core.renew_account_slot(uuid, uuid, uuid, smallint, bigint, uuid, interval) FROM PUBLIC;
REVOKE ALL ON FUNCTION core.release_account_slot(uuid, uuid, uuid, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION exec.create_run(uuid, uuid, text, text, uuid, uuid, uuid, uuid, uuid, uuid, uuid, uuid, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION exec.append_run_event(uuid, uuid, text, jsonb, text, text, uuid, uuid, text, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION exec.append_session_event(uuid, uuid, text, jsonb, integer, integer, boolean, boolean, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION exec.refresh_run_progress(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION exec.claim_ready_task(uuid, uuid, uuid, interval) FROM PUBLIC;
REVOKE ALL ON FUNCTION exec.renew_task_lease(uuid, uuid, uuid, bigint, uuid, interval) FROM PUBLIC;
REVOKE ALL ON FUNCTION exec.finish_task_attempt(uuid, uuid, uuid, bigint, uuid, text, boolean, uuid, uuid, text, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION exec.seal_checkpoint(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION integration.reserve_side_effect(uuid, uuid, uuid, uuid, uuid, text, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION verify.complete_run_with_gate(uuid, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION ops.complete_deployment_with_gate(uuid, uuid, uuid) FROM PUBLIC;

COMMIT;
