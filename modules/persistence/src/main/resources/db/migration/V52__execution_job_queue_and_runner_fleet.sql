-- ELMOS V52: durable execution job queue and typed runner fleet.
--
-- Why this migration exists
-- -------------------------
-- Before V52 the generation and translation business lines executed inside the
-- Next.js BFF process. Concurrency was an in-memory Set, tenancy came from
-- ELMOS_LOCAL_RUNNER_TENANT_ID, and a process restart lost every running job.
-- V52 makes the job the authoritative durable record and turns the V9 runner
-- placeholder tables into a typed fleet.
--
-- Boundary preserved from V9/B36: the control plane schedules, it does not
-- execute. A runner may only be leased work after it has attested rootless,
-- read-only root, dropped capabilities and default-deny network. Missing
-- attestation fails closed; it is never inferred.
--
-- Tenancy model
-- -------------
-- execution_jobs / execution_job_events carry customer content and are tenant
-- isolated with FORCE ROW LEVEL SECURITY, exactly like V49/V51.
-- execution_job_dispatch and execution_dispatch_org_counters carry NO customer
-- content (identifiers, capability, priority, lease timing only). They are
-- deliberately NOT tenant isolated because cross-tenant fair scheduling is
-- impossible under a per-transaction app.organization_id. Access is restricted
-- to the elmos_scheduler role and the SECURITY DEFINER functions below.

-- ---------------------------------------------------------------------------
-- 1. Scheduler role
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_scheduler') THEN
        CREATE ROLE elmos_scheduler NOLOGIN;
    END IF;
END;
$$;

COMMENT ON ROLE elmos_scheduler IS
    'Non-login role owning cross-tenant dispatch. Granted to the control-plane application role only. It can never read execution_jobs payloads directly; it reaches them through SECURITY DEFINER functions that bind an explicit organization.';

-- ---------------------------------------------------------------------------
-- 2. Typed runner fleet (ALTER of the V9 placeholder tables)
-- ---------------------------------------------------------------------------
-- V9 created runner_nodes/runner_job_leases as generic payload-jsonb rows.
-- The V49 convention for turning a placeholder into a typed table is
-- ADD COLUMN + a shape CHECK that only applies once the discriminator is set,
-- so historical rows stay valid. The same convention is used here.

ALTER TABLE runner_nodes
    ADD COLUMN runner_pool_ref varchar(96) REFERENCES runner_pools(runner_pool_id),
    ADD COLUMN agent_version varchar(64),
    ADD COLUMN fleet_status varchar(24),
    ADD COLUMN capabilities text[],
    ADD COLUMN max_concurrency smallint,
    ADD COLUMN rootless_attested boolean NOT NULL DEFAULT false,
    ADD COLUMN readonly_root_attested boolean NOT NULL DEFAULT false,
    ADD COLUMN capability_drop_attested boolean NOT NULL DEFAULT false,
    ADD COLUMN network_default_deny_attested boolean NOT NULL DEFAULT false,
    ADD COLUMN attestation_verified_at timestamptz,
    ADD COLUMN attestation_verifier_actor_id varchar(128),
    ADD COLUMN image_allowlist_version varchar(64),
    ADD COLUMN last_heartbeat_at timestamptz,
    ADD COLUMN drain_requested_at timestamptz,
    ADD COLUMN quarantined_at timestamptz,
    ADD COLUMN quarantine_code varchar(96),
    ADD CONSTRAINT runner_nodes_fleet_shape CHECK (
        fleet_status IS NULL OR (
            fleet_status IN ('REGISTERED', 'READY', 'DRAINING', 'QUARANTINED', 'LOST', 'RETIRED')
            AND agent_version IS NOT NULL
            AND capabilities IS NOT NULL
            AND array_length(capabilities, 1) BETWEEN 1 AND 32
            AND max_concurrency BETWEEN 1 AND 16
            AND runner_pool_ref IS NOT NULL
        )
    ),
    ADD CONSTRAINT runner_nodes_ready_requires_attestation CHECK (
        fleet_status IS DISTINCT FROM 'READY' OR (
            rootless_attested
            AND readonly_root_attested
            AND capability_drop_attested
            AND network_default_deny_attested
            AND attestation_verified_at IS NOT NULL
            AND attestation_verifier_actor_id IS NOT NULL
            AND image_allowlist_version IS NOT NULL
        )
    );

CREATE INDEX idx_runner_nodes_fleet_status
    ON runner_nodes (fleet_status, last_heartbeat_at DESC)
    WHERE fleet_status IS NOT NULL;

COMMENT ON CONSTRAINT runner_nodes_ready_requires_attestation ON runner_nodes IS
    'A node cannot reach READY without four independently verified sandbox attestations and a named verifier. The scheduler refuses to lease work to anything else.';

ALTER TABLE runner_job_leases
    ADD COLUMN job_ref varchar(96),
    ADD COLUMN runner_node_ref varchar(96) REFERENCES runner_nodes(runner_node_id),
    ADD COLUMN actor_id varchar(128),
    ADD COLUMN lease_state varchar(24),
    ADD COLUMN token_sha256 varchar(64) CHECK (token_sha256 IS NULL OR token_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN issued_at timestamptz,
    ADD COLUMN expires_at timestamptz,
    ADD COLUMN last_heartbeat_at timestamptz,
    ADD COLUMN released_at timestamptz,
    ADD COLUMN revocation_code varchar(96),
    ADD CONSTRAINT runner_job_leases_shape CHECK (
        lease_state IS NULL OR (
            lease_state IN ('ISSUED', 'ACTIVE', 'RELEASED', 'EXPIRED', 'REVOKED')
            AND job_ref IS NOT NULL
            AND runner_node_ref IS NOT NULL
            AND actor_id IS NOT NULL
            AND token_sha256 IS NOT NULL
            AND issued_at IS NOT NULL
            AND expires_at > issued_at
        )
    );

CREATE INDEX idx_runner_job_leases_job ON runner_job_leases (job_ref) WHERE job_ref IS NOT NULL;
CREATE INDEX idx_runner_job_leases_expiry
    ON runner_job_leases (expires_at)
    WHERE lease_state IN ('ISSUED', 'ACTIVE');

COMMENT ON COLUMN runner_job_leases.token_sha256 IS
    'SHA-256 of the one-time execution credential. The credential itself is returned once at claim time and is never stored, logged or recoverable.';

-- ---------------------------------------------------------------------------
-- 3. Authoritative job record (tenant isolated)
-- ---------------------------------------------------------------------------

CREATE TABLE execution_jobs (
    job_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    actor_id varchar(128) NOT NULL,
    business_line varchar(32) NOT NULL,
    job_kind varchar(64) NOT NULL,
    idempotency_key varchar(160) NOT NULL,
    request_digest varchar(64) NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    request_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    required_capability varchar(96) NOT NULL,
    runner_image varchar(255),
    priority smallint NOT NULL DEFAULT 100,
    status varchar(24) NOT NULL DEFAULT 'QUEUED',
    stage varchar(64) NOT NULL DEFAULT 'queued',
    progress smallint NOT NULL DEFAULT 0,
    result_status varchar(24) NOT NULL DEFAULT 'NOT_RUN',
    failure_code varchar(96),
    attempt smallint NOT NULL DEFAULT 0,
    max_attempts smallint NOT NULL DEFAULT 1,
    budget_wall_seconds integer NOT NULL DEFAULT 3600,
    budget_cpu_millis integer NOT NULL DEFAULT 4000,
    budget_memory_mib integer NOT NULL DEFAULT 8192,
    checkpoint_cursor jsonb NOT NULL DEFAULT '{}'::jsonb,
    cancel_requested_at timestamptz,
    cancel_requested_by varchar(128),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    state_version bigint NOT NULL DEFAULT 0,
    UNIQUE (organization_id, idempotency_key),
    CONSTRAINT execution_jobs_business_line CHECK (
        business_line IN ('GENERATION', 'TRANSLATION', 'SPRING_UPGRADE', 'REPOSITORY_WORKSPACE')
    ),
    CONSTRAINT execution_jobs_status CHECK (
        status IN ('QUEUED', 'CLAIMED', 'RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'LOST')
    ),
    CONSTRAINT execution_jobs_result_status CHECK (
        result_status IN ('NOT_RUN', 'PASSED', 'PARTIAL', 'FAILED', 'BLOCKED')
    ),
    CONSTRAINT execution_jobs_progress_range CHECK (progress BETWEEN 0 AND 100),
    CONSTRAINT execution_jobs_priority_range CHECK (priority BETWEEN 1 AND 1000),
    CONSTRAINT execution_jobs_attempt_range CHECK (attempt >= 0 AND attempt <= max_attempts AND max_attempts BETWEEN 1 AND 5),
    CONSTRAINT execution_jobs_budget_range CHECK (
        budget_wall_seconds BETWEEN 60 AND 43200
        AND budget_cpu_millis BETWEEN 500 AND 32000
        AND budget_memory_mib BETWEEN 512 AND 65536
    ),
    CONSTRAINT execution_jobs_payload_object CHECK (jsonb_typeof(request_payload) = 'object'),
    CONSTRAINT execution_jobs_checkpoint_object CHECK (jsonb_typeof(checkpoint_cursor) = 'object'),
    CONSTRAINT execution_jobs_terminal_shape CHECK (
        status NOT IN ('SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'LOST') OR finished_at IS NOT NULL
    ),
    CONSTRAINT execution_jobs_failure_shape CHECK (
        status <> 'FAILED' OR failure_code IS NOT NULL
    ),
    -- Production runner images must be immutable digests. A mutable tag is a
    -- supply-chain hole and is rejected at the storage layer, not only in code.
    CONSTRAINT execution_jobs_runner_image_digest CHECK (
        runner_image IS NULL OR runner_image ~ '^[a-z0-9][a-z0-9._/-]*(:[0-9]+)?/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$'
    )
);

CREATE INDEX idx_execution_jobs_org_created ON execution_jobs (organization_id, created_at DESC);
CREATE INDEX idx_execution_jobs_org_status ON execution_jobs (organization_id, status, created_at DESC);
CREATE INDEX idx_execution_jobs_org_line ON execution_jobs (organization_id, business_line, created_at DESC);

COMMENT ON TABLE execution_jobs IS
    'Authoritative durable record for every long-running business-line job. Replaces the in-memory job table that the web BFF and the language workers previously kept (capability EPHEMERAL_PROCESS_LOCAL).';
COMMENT ON COLUMN execution_jobs.request_payload IS
    'Approved, validated request intent only. Credentials, tokens, raw source code and provider secrets are prohibited; use secret references and content-addressed inputs.';
COMMENT ON COLUMN execution_jobs.failure_code IS
    'Stable machine-readable code. Raw exception text, stack traces and provider messages are prohibited here and belong in evidence artifacts.';

CREATE TABLE execution_job_events (
    job_event_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    job_id varchar(96) NOT NULL REFERENCES execution_jobs(job_id),
    sequence_no integer NOT NULL,
    event_type varchar(48) NOT NULL,
    from_status varchar(24),
    to_status varchar(24),
    stage varchar(64),
    progress smallint,
    runner_node_ref varchar(96),
    lease_ref varchar(96),
    actor_id varchar(128),
    failure_code varchar(96),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (job_id, sequence_no),
    CONSTRAINT execution_job_events_type CHECK (
        event_type IN (
            'ENQUEUED', 'CLAIMED', 'HEARTBEAT', 'STAGE_CHANGED', 'CHECKPOINT',
            'COMPLETED', 'FAILED', 'CANCEL_REQUESTED', 'CANCELLED',
            'LEASE_EXPIRED', 'REQUEUED', 'ARTIFACT_PUBLISHED'
        )
    ),
    CONSTRAINT execution_job_events_progress_range CHECK (progress IS NULL OR progress BETWEEN 0 AND 100),
    CONSTRAINT execution_job_events_metadata_object CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX idx_execution_job_events_job ON execution_job_events (job_id, sequence_no);
CREATE INDEX idx_execution_job_events_org_time ON execution_job_events (organization_id, occurred_at DESC);

CREATE TRIGGER execution_job_events_append_only
BEFORE UPDATE OR DELETE ON execution_job_events
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

-- Terminal states are immutable. This mirrors the invariant the Java and .NET
-- workers already enforce in memory ("终态统一不可改写"), but puts it where it
-- cannot be bypassed by a new caller.
CREATE OR REPLACE FUNCTION elmos_guard_execution_job_transition()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status IN ('SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'LOST')
       AND NEW.status IS DISTINCT FROM OLD.status THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_JOB_TERMINAL_IMMUTABLE';
    END IF;
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_JOB_TENANT_IMMUTABLE';
    END IF;
    IF NEW.request_digest IS DISTINCT FROM OLD.request_digest THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_JOB_REQUEST_IMMUTABLE';
    END IF;
    NEW.updated_at := now();
    NEW.state_version := OLD.state_version + 1;
    RETURN NEW;
END;
$$;

CREATE TRIGGER execution_jobs_transition_guard
BEFORE UPDATE ON execution_jobs
FOR EACH ROW EXECUTE FUNCTION elmos_guard_execution_job_transition();

-- ---------------------------------------------------------------------------
-- 4. Cross-tenant dispatch projection (NOT tenant isolated, by design)
-- ---------------------------------------------------------------------------

CREATE TABLE execution_job_dispatch (
    job_id varchar(96) PRIMARY KEY REFERENCES execution_jobs(job_id),
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    required_capability varchar(96) NOT NULL,
    priority smallint NOT NULL DEFAULT 100,
    dispatch_state varchar(16) NOT NULL DEFAULT 'READY',
    attempt smallint NOT NULL DEFAULT 0,
    enqueued_at timestamptz NOT NULL DEFAULT now(),
    visible_at timestamptz NOT NULL DEFAULT now(),
    lease_ref varchar(96),
    runner_node_ref varchar(96),
    lease_expires_at timestamptz,
    CONSTRAINT execution_job_dispatch_state CHECK (
        dispatch_state IN ('READY', 'LEASED', 'DONE', 'DEAD')
    ),
    CONSTRAINT execution_job_dispatch_lease_shape CHECK (
        dispatch_state <> 'LEASED' OR (lease_ref IS NOT NULL AND runner_node_ref IS NOT NULL AND lease_expires_at IS NOT NULL)
    )
);

-- The single index the claim query rides on.
CREATE INDEX idx_execution_job_dispatch_ready
    ON execution_job_dispatch (required_capability, priority DESC, enqueued_at)
    WHERE dispatch_state = 'READY';
CREATE INDEX idx_execution_job_dispatch_lease_expiry
    ON execution_job_dispatch (lease_expires_at)
    WHERE dispatch_state = 'LEASED';
CREATE INDEX idx_execution_job_dispatch_org ON execution_job_dispatch (organization_id, dispatch_state);

COMMENT ON TABLE execution_job_dispatch IS
    'Cross-tenant scheduling projection. Intentionally NOT row-level-security isolated: fair scheduling must see every tenant at once, which a per-transaction app.organization_id forbids. It therefore carries no customer content - only identifiers, capability, priority and lease timing. Direct access is revoked from PUBLIC and granted to elmos_scheduler.';

CREATE TABLE execution_dispatch_org_counters (
    organization_id varchar(96) PRIMARY KEY REFERENCES organizations(organization_id),
    leased_count integer NOT NULL DEFAULT 0,
    queued_count integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT execution_dispatch_counters_non_negative CHECK (leased_count >= 0 AND queued_count >= 0)
);

COMMENT ON TABLE execution_dispatch_org_counters IS
    'O(1) fairness and concurrency counters maintained by the dispatch functions. Reconciled by elmos_reconcile_dispatch_counters() on every reaper pass so drift can never silently starve or over-admit a tenant.';

-- ---------------------------------------------------------------------------
-- 5. Effective concurrency limit, derived from the CNY self-service catalog
-- ---------------------------------------------------------------------------
-- V49 already stores concurrent_job_limit per plan version. The scheduler must
-- reuse that number rather than inventing a second quota source of truth.

CREATE OR REPLACE FUNCTION elmos_execution_concurrency_limit(p_organization_id varchar)
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
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
        0);
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

        SELECT * INTO v_job FROM execution_jobs WHERE execution_jobs.job_id = v_candidate.d_job_id FOR UPDATE;

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
    v_expires timestamptz;
    v_cancelled boolean;
BEGIN
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
    v_job execution_jobs%ROWTYPE;
    v_seq integer;
    v_requeue boolean := false;
BEGIN
    IF p_status NOT IN ('SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED') THEN
        RAISE EXCEPTION 'ELMOS_COMPLETION_STATUS_INVALID';
    END IF;

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

    UPDATE runner_nodes
       SET fleet_status = 'LOST'
     WHERE fleet_status IN ('READY', 'DRAINING')
       AND (last_heartbeat_at IS NULL OR last_heartbeat_at < now() - interval '120 seconds');

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
-- 10. Row level security and grants
-- ---------------------------------------------------------------------------

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'execution_jobs',
        'execution_job_events'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name
        );
    END LOOP;
END;
$$;

REVOKE ALL ON execution_job_dispatch FROM PUBLIC;
REVOKE ALL ON execution_dispatch_org_counters FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON execution_job_dispatch TO elmos_scheduler;
GRANT SELECT, INSERT, UPDATE ON execution_dispatch_org_counters TO elmos_scheduler;

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
