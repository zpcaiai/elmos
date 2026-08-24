-- ELMOS V73: repository-owned multi-tenant task control and FinOps runtime.
--
-- This migration is intentionally not derived from the supplied V100-V102
-- reference SQL. It reconciles the requested behavior with the authoritative
-- repository aggregates introduced by V49, V52, V55, V57, V58 and V61:
--
--   * execution_jobs / execution_job_events remain the task truth;
--   * accounts / organization_memberships / user_identities remain identity;
--   * content_objects / job_artifacts remain object and artifact truth;
--   * usage_events remains the immutable usage truth;
--   * one new revenue ledger is introduced because no revenue truth exists.
--
-- Legacy execution rows are never assigned an account by guesswork. A row is
-- backfilled only when its organization + actor maps to one exact active
-- canonical identity. All new MTF submission paths require an exact account.

-- ---------------------------------------------------------------------------
-- 1. Least-privilege role contracts
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_mtf_application') THEN
        CREATE ROLE elmos_mtf_application
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_mtf_workflow') THEN
        CREATE ROLE elmos_mtf_workflow
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_mtf_analytics') THEN
        CREATE ROLE elmos_mtf_analytics
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'elmos_mtf_break_glass') THEN
        CREATE ROLE elmos_mtf_break_glass
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
END;
$$;

COMMENT ON ROLE elmos_mtf_application IS
    'Tenant API capability role. NOLOGIN, NOSUPERUSER and NOBYPASSRLS; deployment grants it only to the separately provisioned runtime login.';
COMMENT ON ROLE elmos_mtf_workflow IS
    'Workflow and scheduler capability role. Cross-tenant access is limited to audited SECURITY DEFINER functions.';
COMMENT ON ROLE elmos_mtf_analytics IS
    'Read-only, RLS-bound task and financial projection capability role.';
COMMENT ON ROLE elmos_mtf_break_glass IS
    'Dormant capability role. It has no login and no BYPASSRLS; activation and expiry are external governed operations.';

-- ---------------------------------------------------------------------------
-- 2. Canonical task/account shape
-- ---------------------------------------------------------------------------

ALTER TABLE execution_jobs
    ADD COLUMN account_id varchar(96) REFERENCES accounts(account_id),
    ADD COLUMN admission_state varchar(24),
    ADD COLUMN control_state varchar(24),
    ADD COLUMN workflow_id varchar(160),
    ADD COLUMN workflow_run_number integer,
    ADD COLUMN workflow_payload_version integer,
    ADD COLUMN workload_class varchar(32),
    ADD COLUMN resource_units integer,
    ADD COLUMN account_slot_number smallint,
    ADD COLUMN account_slot_generation bigint,
    ADD COLUMN progress_sequence bigint NOT NULL DEFAULT 0,
    ADD COLUMN elapsed_millis bigint NOT NULL DEFAULT 0,
    ADD COLUMN eta_p50_millis bigint,
    ADD COLUMN eta_p90_millis bigint,
    ADD COLUMN monetary_budget_minor numeric(30,6),
    ADD COLUMN monetary_budget_currency char(3),
    ADD COLUMN request_id varchar(160),
    ADD CONSTRAINT execution_jobs_account_scope_uq
        UNIQUE (job_id, organization_id, account_id),
    ADD CONSTRAINT execution_jobs_mtf_shape CHECK (
        account_id IS NULL OR (
            admission_state IN ('WAITING_FOR_SLOT', 'ADMITTED', 'RECONCILING', 'RELEASED')
            AND control_state IN (
                'RUNNABLE', 'PAUSE_REQUESTED', 'PAUSED', 'RESUME_REQUESTED',
                'CANCEL_REQUESTED', 'MANUAL_RECOVERY'
            )
            AND workflow_id IS NOT NULL
            AND workflow_run_number >= 1
            AND workflow_payload_version >= 1
            AND workload_class IN (
                'PARSING', 'GENERATION', 'CONVERSION',
                'VALIDATION', 'RENDERING', 'MODEL_GPU'
            )
            AND resource_units BETWEEN 1 AND 64
            AND request_id IS NOT NULL
        )
    ),
    ADD CONSTRAINT execution_jobs_slot_shape CHECK (
        (account_slot_number IS NULL AND account_slot_generation IS NULL)
        OR (
            account_id IS NOT NULL
            AND account_slot_number BETWEEN 1 AND 3
            AND account_slot_generation > 0
        )
    ),
    ADD CONSTRAINT execution_jobs_eta_shape CHECK (
        progress_sequence >= 0
        AND elapsed_millis >= 0
        AND (eta_p50_millis IS NULL OR eta_p50_millis >= 0)
        AND (eta_p90_millis IS NULL OR eta_p90_millis >= coalesce(eta_p50_millis, 0))
    ),
    ADD CONSTRAINT execution_jobs_money_budget_shape CHECK (
        (monetary_budget_minor IS NULL AND monetary_budget_currency IS NULL)
        OR (
            monetary_budget_minor >= 0
            AND monetary_budget_currency ~ '^[A-Z]{3}$'
        )
    );

-- Backfill only an unambiguous canonical actor/account mapping. Rows that used
-- a raw OIDC subject remain NULL and are explicitly legacy-unresolved.
WITH exact_identity AS (
    SELECT organization_id, actor_id, min(account_ref) AS account_id
      FROM user_identities
     WHERE account_ref IS NOT NULL
       AND actor_id IS NOT NULL
       AND deprovisioned_at IS NULL
     GROUP BY organization_id, actor_id
    HAVING count(DISTINCT account_ref) = 1
)
UPDATE execution_jobs job
   SET account_id = identity.account_id
  FROM exact_identity identity
 WHERE job.account_id IS NULL
   AND identity.organization_id = job.organization_id
   AND identity.actor_id = job.actor_id;

ALTER TABLE execution_job_dispatch
    ADD COLUMN account_id varchar(96) REFERENCES accounts(account_id),
    ADD COLUMN workload_class varchar(32),
    ADD COLUMN resource_units integer,
    ADD COLUMN queue_reason varchar(64),
    ADD CONSTRAINT execution_job_dispatch_mtf_shape CHECK (
        account_id IS NULL OR (
            workload_class IN (
                'PARSING', 'GENERATION', 'CONVERSION',
                'VALIDATION', 'RENDERING', 'MODEL_GPU'
            )
            AND resource_units BETWEEN 1 AND 64
        )
    );

UPDATE execution_job_dispatch dispatch
   SET account_id = job.account_id
  FROM execution_jobs job
 WHERE dispatch.job_id = job.job_id
   AND job.account_id IS NOT NULL;

ALTER TABLE execution_job_events
    ADD COLUMN account_id varchar(96) REFERENCES accounts(account_id),
    ADD COLUMN event_key varchar(160),
    ADD COLUMN transition_id varchar(160),
    ADD COLUMN run_number integer,
    ADD COLUMN elapsed_millis bigint,
    ADD COLUMN eta_p50_millis bigint,
    ADD COLUMN eta_p90_millis bigint,
    ADD COLUMN payload_digest char(64),
    ADD CONSTRAINT execution_job_events_scope_fk
        FOREIGN KEY (job_id, organization_id, account_id)
        REFERENCES execution_jobs(job_id, organization_id, account_id),
    ADD CONSTRAINT execution_job_events_mtf_shape CHECK (
        account_id IS NULL OR (
            event_key IS NOT NULL
            AND run_number >= 1
            AND (payload_digest IS NULL OR payload_digest ~ '^[0-9a-f]{64}$')
            AND (elapsed_millis IS NULL OR elapsed_millis >= 0)
            AND (eta_p50_millis IS NULL OR eta_p50_millis >= 0)
            AND (eta_p90_millis IS NULL OR eta_p90_millis >= coalesce(eta_p50_millis, 0))
        )
    );

CREATE UNIQUE INDEX execution_job_events_event_key_uq
    ON execution_job_events(job_id, event_key)
    WHERE event_key IS NOT NULL;
CREATE UNIQUE INDEX execution_job_events_transition_uq
    ON execution_job_events(job_id, transition_id)
    WHERE transition_id IS NOT NULL;
CREATE INDEX execution_jobs_account_admission_idx
    ON execution_jobs(account_id, admission_state, created_at)
    WHERE account_id IS NOT NULL;
CREATE INDEX execution_dispatch_account_ready_idx
    ON execution_job_dispatch(account_id, dispatch_state, priority DESC, enqueued_at)
    WHERE account_id IS NOT NULL;

ALTER TABLE execution_jobs DROP CONSTRAINT execution_jobs_status;
ALTER TABLE execution_jobs ADD CONSTRAINT execution_jobs_status CHECK (
    status IN (
        'QUEUED', 'CLAIMED', 'RUNNING', 'PAUSED',
        'UNKNOWN_RESULT', 'RECONCILING',
        'SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'LOST'
    )
);
ALTER TABLE execution_jobs DROP CONSTRAINT execution_jobs_business_line;
ALTER TABLE execution_jobs ADD CONSTRAINT execution_jobs_business_line CHECK (
    business_line IN (
        'GENERATION', 'TRANSLATION', 'SPRING_UPGRADE',
        'REPOSITORY_WORKSPACE', 'MODERNIZATION_PROOF'
    )
);
ALTER TABLE execution_job_dispatch DROP CONSTRAINT execution_job_dispatch_state;
ALTER TABLE execution_job_dispatch ADD CONSTRAINT execution_job_dispatch_state CHECK (
    dispatch_state IN ('READY', 'LEASED', 'PAUSED', 'RECONCILING', 'DONE', 'DEAD')
);
ALTER TABLE execution_job_events DROP CONSTRAINT execution_job_events_type;
ALTER TABLE execution_job_events ADD CONSTRAINT execution_job_events_type CHECK (
    event_type IN (
        'ENQUEUED', 'SUBMITTED', 'WAITING_FOR_SLOT', 'SLOT_CLAIMED',
        'SLOT_RENEWED', 'SLOT_RELEASED', 'CLAIMED', 'HEARTBEAT',
        'STAGE_CHANGED', 'PROGRESS_RECORDED', 'CHECKPOINT', 'CHECKPOINT_COMMITTED',
        'SIDE_EFFECT_INTENT', 'SIDE_EFFECT_RECEIPT', 'ARTIFACT_PUBLISHED',
        'USAGE_RECORDED', 'REVENUE_RECORDED', 'OUTBOX_PENDING',
        'PAUSE_REQUESTED', 'PAUSED', 'RESUME_REQUESTED', 'RESUMED',
        'CANCEL_REQUESTED', 'CANCELLED', 'LEASE_EXPIRED',
        'UNKNOWN_RESULT', 'RECONCILING', 'MANUAL_RECOVERY',
        'REQUEUED', 'COMPLETED', 'FAILED'
    )
);

-- ---------------------------------------------------------------------------
-- 3. Workload profiles and exact three-slot semaphore
-- ---------------------------------------------------------------------------

CREATE TABLE task_finops_workload_profiles (
    workload_class varchar(32) PRIMARY KEY,
    task_queue varchar(96) NOT NULL UNIQUE,
    resource_units integer NOT NULL CHECK (resource_units BETWEEN 1 AND 64),
    max_worker_concurrency integer NOT NULL CHECK (max_worker_concurrency BETWEEN 1 AND 64),
    autoscale_min_workers integer NOT NULL CHECK (autoscale_min_workers >= 0),
    autoscale_max_workers integer NOT NULL CHECK (autoscale_max_workers >= autoscale_min_workers),
    policy_version varchar(64) NOT NULL,
    status varchar(16) NOT NULL CHECK (status IN ('ACTIVE', 'DISABLED')),
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO task_finops_workload_profiles (
    workload_class, task_queue, resource_units, max_worker_concurrency,
    autoscale_min_workers, autoscale_max_workers, policy_version, status
) VALUES
    ('PARSING', 'mtf.parsing.v1', 1, 16, 0, 32, 'mtf-workload-v1', 'ACTIVE'),
    ('GENERATION', 'mtf.generation.v1', 2, 8, 0, 16, 'mtf-workload-v1', 'ACTIVE'),
    ('CONVERSION', 'mtf.conversion.v1', 3, 6, 0, 12, 'mtf-workload-v1', 'ACTIVE'),
    ('VALIDATION', 'mtf.validation.v1', 2, 8, 0, 16, 'mtf-workload-v1', 'ACTIVE'),
    ('RENDERING', 'mtf.rendering.v1', 4, 4, 0, 8, 'mtf-workload-v1', 'ACTIVE'),
    ('MODEL_GPU', 'mtf.model-gpu.v1', 8, 2, 0, 4, 'mtf-workload-v1', 'ACTIVE');

CREATE TRIGGER task_finops_workload_profiles_append_only
BEFORE UPDATE OR DELETE ON task_finops_workload_profiles
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE execution_account_slots (
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    slot_number smallint NOT NULL CHECK (slot_number BETWEEN 1 AND 3),
    slot_state varchar(24) NOT NULL DEFAULT 'FREE'
        CHECK (slot_state IN ('FREE', 'ACTIVE', 'RECONCILING')),
    organization_id varchar(96) REFERENCES organizations(organization_id),
    active_job_id varchar(96),
    active_lease_ref varchar(96),
    lease_generation bigint NOT NULL DEFAULT 0 CHECK (lease_generation >= 0),
    lease_expires_at timestamptz,
    last_renewed_at timestamptz,
    occupied_at timestamptz,
    released_at timestamptz,
    release_reason varchar(96),
    PRIMARY KEY (account_id, slot_number),
    CONSTRAINT execution_account_slots_job_scope_fk
        FOREIGN KEY (active_job_id, organization_id, account_id)
        REFERENCES execution_jobs(job_id, organization_id, account_id),
    CONSTRAINT execution_account_slots_lease_fk
        FOREIGN KEY (active_lease_ref)
        REFERENCES runner_job_leases(runner_job_lease_id),
    CONSTRAINT execution_account_slots_occupancy CHECK (
        (slot_state = 'FREE'
            AND organization_id IS NULL
            AND active_job_id IS NULL
            AND active_lease_ref IS NULL
            AND lease_expires_at IS NULL)
        OR
        (slot_state IN ('ACTIVE', 'RECONCILING')
            AND organization_id IS NOT NULL
            AND active_job_id IS NOT NULL
            AND active_lease_ref IS NOT NULL
            AND lease_generation > 0
            AND lease_expires_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX execution_account_slots_active_job_uq
    ON execution_account_slots(active_job_id)
    WHERE active_job_id IS NOT NULL;
CREATE UNIQUE INDEX execution_account_slots_active_lease_uq
    ON execution_account_slots(active_lease_ref)
    WHERE active_lease_ref IS NOT NULL;
CREATE INDEX execution_account_slots_expiry_idx
    ON execution_account_slots(lease_expires_at)
    WHERE slot_state IN ('ACTIVE', 'RECONCILING');

-- Existing accounts receive exactly three rows before FORCE RLS is enabled.
INSERT INTO execution_account_slots(account_id, slot_number)
SELECT account_id, slot_number
  FROM accounts
 CROSS JOIN generate_series(1, 3) AS slot_number
ON CONFLICT DO NOTHING;

COMMENT ON TABLE execution_account_slots IS
    'Authoritative platform-global account semaphore. Exactly slots 1..3 exist for each account; tenant plans may lower effective admission but can never raise this hard maximum.';

-- ---------------------------------------------------------------------------
-- 4. Workflow start, checkpoints, receipts, manifests and audit
-- ---------------------------------------------------------------------------

CREATE TABLE task_workflow_start_outbox (
    outbox_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    job_id varchar(96) NOT NULL,
    run_number integer NOT NULL CHECK (run_number >= 1),
    workflow_id varchar(160) NOT NULL,
    payload_version integer NOT NULL CHECK (payload_version >= 1),
    payload_digest char(64) NOT NULL CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
    outbox_state varchar(24) NOT NULL DEFAULT 'PENDING'
        CHECK (outbox_state IN ('PENDING', 'DISPATCHING', 'STARTED', 'UNKNOWN_RESULT', 'FAILED')),
    attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    available_at timestamptz NOT NULL DEFAULT now(),
    claimed_at timestamptz,
    completed_at timestamptz,
    failure_code varchar(96),
    created_at timestamptz NOT NULL DEFAULT now(),
    state_version bigint NOT NULL DEFAULT 0,
    UNIQUE (job_id, run_number),
    UNIQUE (workflow_id),
    CONSTRAINT task_workflow_outbox_scope_fk
        FOREIGN KEY (job_id, organization_id, account_id)
        REFERENCES execution_jobs(job_id, organization_id, account_id)
);

CREATE INDEX task_workflow_start_outbox_pending_idx
    ON task_workflow_start_outbox(available_at, created_at)
    WHERE outbox_state = 'PENDING';

CREATE TABLE task_checkpoint_manifests (
    checkpoint_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    job_id varchar(96) NOT NULL,
    run_number integer NOT NULL CHECK (run_number >= 1),
    event_key varchar(160) NOT NULL,
    checkpoint_sequence bigint NOT NULL CHECK (checkpoint_sequence >= 1),
    input_manifest_digest char(64) NOT NULL CHECK (input_manifest_digest ~ '^[0-9a-f]{64}$'),
    repository_revision varchar(160) NOT NULL,
    state_digest char(64) NOT NULL CHECK (state_digest ~ '^[0-9a-f]{64}$'),
    toolchain_digest char(64) NOT NULL CHECK (toolchain_digest ~ '^[0-9a-f]{64}$'),
    model_digest char(64) CHECK (model_digest IS NULL OR model_digest ~ '^[0-9a-f]{64}$'),
    schema_version varchar(64) NOT NULL,
    next_node varchar(96) NOT NULL,
    manifest jsonb NOT NULL CHECK (jsonb_typeof(manifest) = 'object'),
    compatibility_state varchar(24) NOT NULL
        CHECK (compatibility_state IN ('COMPATIBLE', 'INCOMPATIBLE', 'UNKNOWN')),
    created_by_actor_id varchar(128) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (job_id, run_number, checkpoint_sequence),
    UNIQUE (job_id, event_key),
    CONSTRAINT task_checkpoint_scope_fk
        FOREIGN KEY (job_id, organization_id, account_id)
        REFERENCES execution_jobs(job_id, organization_id, account_id)
);

CREATE TRIGGER task_checkpoint_manifests_append_only
BEFORE UPDATE OR DELETE ON task_checkpoint_manifests
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE task_side_effect_receipts (
    side_effect_receipt_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    job_id varchar(96) NOT NULL,
    run_number integer NOT NULL CHECK (run_number >= 1),
    node_key varchar(96) NOT NULL,
    operation_type varchar(48) NOT NULL
        CHECK (operation_type IN (
            'GIT', 'PAYMENT', 'PROVIDER', 'STORAGE', 'EXTERNAL_API',
            'DATABASE', 'MESSAGE', 'FILE_SYSTEM'
        )),
    idempotency_key varchar(160) NOT NULL,
    intent_digest char(64) NOT NULL CHECK (intent_digest ~ '^[0-9a-f]{64}$'),
    provider_reference varchar(255),
    receipt_digest char(64) NOT NULL CHECK (receipt_digest ~ '^[0-9a-f]{64}$'),
    receipt_state varchar(24) NOT NULL
        CHECK (receipt_state IN ('CONFIRMED', 'FAILED', 'UNKNOWN')),
    occurred_at timestamptz NOT NULL,
    signature_algorithm varchar(64) NOT NULL,
    signing_key_id varchar(255) NOT NULL,
    signature text NOT NULL CHECK (length(signature) BETWEEN 1 AND 4096),
    recorded_by_actor_id varchar(128) NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    UNIQUE (organization_id, account_id, idempotency_key),
    CONSTRAINT task_side_effect_scope_fk
        FOREIGN KEY (job_id, organization_id, account_id)
        REFERENCES execution_jobs(job_id, organization_id, account_id),
    CONSTRAINT task_side_effect_completion_shape CHECK (
        receipt_state <> 'CONFIRMED'
        OR (provider_reference IS NOT NULL AND receipt_digest IS NOT NULL)
    )
);

CREATE TRIGGER task_side_effect_receipts_append_only
BEFORE UPDATE OR DELETE ON task_side_effect_receipts
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE task_io_manifests (
    task_manifest_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    job_id varchar(96) NOT NULL,
    run_number integer NOT NULL CHECK (run_number >= 1),
    manifest_role varchar(24) NOT NULL
        CHECK (manifest_role IN ('INPUT', 'EXECUTION', 'OUTPUT', 'LOG_SEGMENT', 'EVIDENCE')),
    manifest_version integer NOT NULL CHECK (manifest_version >= 1),
    content_object_id varchar(96) REFERENCES content_objects(content_object_id),
    manifest_digest char(64) NOT NULL CHECK (manifest_digest ~ '^[0-9a-f]{64}$'),
    media_type varchar(160) NOT NULL,
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    encryption_key_ref varchar(255) NOT NULL,
    retention_class varchar(32) NOT NULL
        CHECK (retention_class IN ('EPHEMERAL', 'STANDARD', 'EXTENDED', 'LEGAL_HOLD')),
    redaction_state varchar(24) NOT NULL
        CHECK (redaction_state IN ('NOT_REQUIRED', 'REDACTED', 'RESTRICTED', 'PENDING_REVIEW')),
    environment_digest char(64) CHECK (environment_digest IS NULL OR environment_digest ~ '^[0-9a-f]{64}$'),
    dependency_lock_digest char(64) CHECK (dependency_lock_digest IS NULL OR dependency_lock_digest ~ '^[0-9a-f]{64}$'),
    toolchain_digest char(64) CHECK (toolchain_digest IS NULL OR toolchain_digest ~ '^[0-9a-f]{64}$'),
    model_digest char(64) CHECK (model_digest IS NULL OR model_digest ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (job_id, run_number, manifest_role, manifest_version),
    CONSTRAINT task_io_manifest_scope_fk
        FOREIGN KEY (job_id, organization_id, account_id)
        REFERENCES execution_jobs(job_id, organization_id, account_id)
);

CREATE TRIGGER task_io_manifests_append_only
BEFORE UPDATE OR DELETE ON task_io_manifests
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE task_finops_audit_events (
    audit_event_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    job_id varchar(96),
    actor_id varchar(128) NOT NULL,
    request_id varchar(160) NOT NULL,
    action varchar(64) NOT NULL,
    idempotency_key varchar(160) NOT NULL,
    outcome varchar(24) NOT NULL CHECK (outcome IN ('SUCCESS', 'DENIED', 'FAILED', 'UNKNOWN_RESULT')),
    reason_code varchar(96),
    target_digest char(64) CHECK (target_digest IS NULL OR target_digest ~ '^[0-9a-f]{64}$'),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, account_id, action, idempotency_key),
    CONSTRAINT task_finops_audit_job_scope_fk
        FOREIGN KEY (job_id, organization_id, account_id)
        REFERENCES execution_jobs(job_id, organization_id, account_id)
);

CREATE INDEX task_finops_audit_scope_idx
    ON task_finops_audit_events(organization_id, account_id, occurred_at DESC);
CREATE TRIGGER task_finops_audit_events_append_only
BEFORE UPDATE OR DELETE ON task_finops_audit_events
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE task_finops_outbox_events (
    outbox_event_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    job_id varchar(96) NOT NULL,
    event_key varchar(160) NOT NULL,
    event_type varchar(64) NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    payload_digest char(64) NOT NULL CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    publish_state varchar(24) NOT NULL DEFAULT 'PENDING'
        CHECK (publish_state IN ('PENDING', 'PUBLISHED', 'FAILED', 'UNKNOWN_RESULT')),
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    UNIQUE (job_id, event_key),
    CONSTRAINT task_finops_outbox_scope_fk
        FOREIGN KEY (job_id, organization_id, account_id)
        REFERENCES execution_jobs(job_id, organization_id, account_id)
);

-- ---------------------------------------------------------------------------
-- 5. Provider cost, usage, revenue and reconciliation
-- ---------------------------------------------------------------------------

-- PostgreSQL round(numeric, scale) resolves exact ties away from zero, while
-- TaskFinopsPolicy uses HALF_EVEN. Keep one explicit database implementation so
-- signed money, conservation checks and idempotency comparisons cannot diverge.
CREATE OR REPLACE FUNCTION elmos_mtf_round_half_even(
    p_value numeric,
    p_scale integer
) RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
DECLARE
    v_factor numeric;
    v_scaled numeric;
    v_floor numeric;
    v_fraction numeric;
    v_integer numeric;
BEGIN
    IF p_scale < 0 OR p_scale > 18 THEN
        RAISE EXCEPTION 'ELMOS_MTF_HALF_EVEN_SCALE_INVALID';
    END IF;
    IF p_value::text IN ('NaN', 'Infinity', '-Infinity') THEN
        RAISE EXCEPTION 'ELMOS_MTF_FINANCE_NUMERIC_NON_FINITE';
    END IF;
    v_factor := power(10::numeric, p_scale);
    v_scaled := p_value * v_factor;
    v_floor := floor(v_scaled);
    v_fraction := v_scaled - v_floor;
    IF v_fraction < 0.5 THEN
        v_integer := v_floor;
    ELSIF v_fraction > 0.5 THEN
        v_integer := v_floor + 1;
    ELSIF mod(abs(v_floor), 2) = 0 THEN
        v_integer := v_floor;
    ELSE
        v_integer := v_floor + 1;
    END IF;
    RETURN v_integer / v_factor;
END;
$$;

COMMENT ON FUNCTION elmos_mtf_round_half_even(numeric, integer) IS
    'Exact decimal HALF_EVEN rounding shared with TaskFinopsPolicy; handles positive and negative ties symmetrically.';

-- Fail the migration itself if either sign or either parity branch drifts.
DO $elmos_mtf_half_even_self_check$
BEGIN
    IF elmos_mtf_round_half_even(1.2345665, 6) IS DISTINCT FROM 1.234566
       OR elmos_mtf_round_half_even(1.2345675, 6) IS DISTINCT FROM 1.234568
       OR elmos_mtf_round_half_even(-1.2345665, 6) IS DISTINCT FROM -1.234566
       OR elmos_mtf_round_half_even(-1.2345675, 6) IS DISTINCT FROM -1.234568 THEN
        RAISE EXCEPTION 'ELMOS_MTF_HALF_EVEN_SELF_CHECK_FAILED';
    END IF;
END;
$elmos_mtf_half_even_self_check$;

ALTER TABLE price_books
    ADD COLUMN mtf_book_kind varchar(24),
    ADD COLUMN currency char(3),
    ADD COLUMN effective_from timestamptz,
    ADD COLUMN effective_until timestamptz,
    ADD COLUMN published_by_actor_id varchar(128),
    ADD COLUMN published_at timestamptz,
    ADD CONSTRAINT price_books_mtf_shape CHECK (
        mtf_book_kind IS NULL OR (
            mtf_book_kind IN ('PROVIDER_COST', 'INTERNAL_COST')
            AND currency ~ '^[A-Z]{3}$'
            AND effective_from IS NOT NULL
            AND (effective_until IS NULL OR effective_until > effective_from)
            AND status IN ('DRAFT', 'PUBLISHED', 'SUPERSEDED')
        )
    );

ALTER TABLE price_items
    ADD COLUMN price_book_ref varchar(96) REFERENCES price_books(price_book_id),
    ADD COLUMN provider varchar(64),
    ADD COLUMN provider_sku varchar(128),
    ADD COLUMN usage_unit varchar(32),
    ADD COLUMN unit_price_minor numeric(30,9),
    ADD COLUMN cost_class varchar(32),
    ADD COLUMN effective_from timestamptz,
    ADD COLUMN effective_until timestamptz,
    ADD CONSTRAINT price_items_mtf_shape CHECK (
        price_book_ref IS NULL OR (
            provider IS NOT NULL
            AND provider_sku IS NOT NULL
            AND usage_unit IN (
                'TOKEN', 'IMAGE', 'AUDIO_SECOND', 'CPU_SECOND', 'MEMORY_GIB_SECOND',
                'GPU_SECOND', 'SANDBOX_SECOND', 'RUNNER_SECOND', 'STORAGE_BYTE_HOUR',
                'EGRESS_BYTE', 'API_CALL', 'RENDER_SECOND', 'HUMAN_REVIEW_MINUTE'
            )
            AND unit_price_minor >= 0
            AND cost_class IN ('AUTONOMOUS_RUNTIME', 'HUMAN_REVIEW', 'SUPPORT', 'THIRD_PARTY')
            AND effective_from IS NOT NULL
            AND (effective_until IS NULL OR effective_until > effective_from)
        )
    );

CREATE UNIQUE INDEX price_items_mtf_effective_uq
    ON price_items(organization_id, price_book_ref, provider, provider_sku, usage_unit, effective_from)
    WHERE price_book_ref IS NOT NULL;

CREATE TABLE task_finops_fx_snapshots (
    fx_snapshot_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    source_currency char(3) NOT NULL CHECK (source_currency ~ '^[A-Z]{3}$'),
    target_currency char(3) NOT NULL CHECK (target_currency ~ '^[A-Z]{3}$'),
    rate numeric(30,12) NOT NULL CHECK (rate > 0),
    effective_at timestamptz NOT NULL,
    source_ref varchar(255) NOT NULL,
    source_digest char(64) NOT NULL CHECK (source_digest ~ '^[0-9a-f]{64}$'),
    reconciliation_state varchar(24) NOT NULL
        CHECK (reconciliation_state IN ('PENDING', 'RECONCILED', 'REJECTED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, source_currency, target_currency, effective_at, source_ref)
);

CREATE TRIGGER task_finops_fx_snapshots_append_only
BEFORE UPDATE OR DELETE ON task_finops_fx_snapshots
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

ALTER TABLE usage_events
    ALTER COLUMN provider_cost_minor TYPE numeric(30,6),
    ADD COLUMN account_id varchar(96) REFERENCES accounts(account_id),
    ADD COLUMN job_id varchar(96),
    ADD COLUMN run_number integer,
    ADD COLUMN node_key varchar(96),
    ADD COLUMN provider_sku varchar(128),
    ADD COLUMN usage_unit varchar(32),
    ADD COLUMN exact_quantity numeric(30,9),
    ADD COLUMN price_book_ref varchar(96) REFERENCES price_books(price_book_id),
    ADD COLUMN price_book_version varchar(96),
    ADD COLUMN price_effective_at timestamptz,
    ADD COLUMN price_item_ref varchar(96) REFERENCES price_items(price_item_id),
    ADD COLUMN unit_price_minor numeric(30,9),
    ADD COLUMN fx_snapshot_ref varchar(96) REFERENCES task_finops_fx_snapshots(fx_snapshot_id),
    ADD COLUMN fx_rate numeric(30,12),
    ADD COLUMN base_currency char(3),
    ADD COLUMN base_cost_minor numeric(30,6),
    ADD COLUMN cost_state varchar(24),
    ADD COLUMN cost_class varchar(32),
    ADD COLUMN period_start timestamptz,
    ADD COLUMN period_end timestamptz,
    ADD COLUMN correction_reason varchar(96),
    ADD COLUMN correction_approved_by varchar(128),
    ADD COLUMN correction_approved_at timestamptz,
    ADD CONSTRAINT usage_events_task_scope_fk
        FOREIGN KEY (job_id, organization_id, account_id)
        REFERENCES execution_jobs(job_id, organization_id, account_id),
    ADD CONSTRAINT usage_events_mtf_shape CHECK (
        job_id IS NULL OR (
            account_id IS NOT NULL
            AND run_number >= 1
            AND provider IS NOT NULL
            AND provider_sku IS NOT NULL
            AND usage_unit IN (
                'TOKEN', 'IMAGE', 'AUDIO_SECOND', 'CPU_SECOND', 'MEMORY_GIB_SECOND',
                'GPU_SECOND', 'SANDBOX_SECOND', 'RUNNER_SECOND', 'STORAGE_BYTE_HOUR',
                'EGRESS_BYTE', 'API_CALL', 'RENDER_SECOND', 'HUMAN_REVIEW_MINUTE'
            )
            AND exact_quantity > 0
            AND price_book_ref IS NOT NULL
            AND price_book_version IS NOT NULL
            AND price_effective_at IS NOT NULL
            AND price_item_ref IS NOT NULL
            AND unit_price_minor >= 0
            AND fx_rate > 0
            AND base_currency ~ '^[A-Z]{3}$'
            AND base_cost_minor >= 0
            AND cost_state IN (
                'ESTIMATED', 'RESERVED', 'POSTED', 'FINAL',
                'REVERSED', 'DISPUTED', 'UNRECONCILED'
            )
            AND cost_class IN ('AUTONOMOUS_RUNTIME', 'HUMAN_REVIEW', 'SUPPORT', 'THIRD_PARTY')
            AND reconciliation_status IN (
                'PENDING', 'RECONCILED', 'REJECTED', 'UNKNOWN', 'INCONCLUSIVE'
            )
            AND period_start IS NOT NULL
            AND period_end > period_start
            AND occurred_at IS NOT NULL
            AND recorded_at IS NOT NULL
        )
    ),
    ADD CONSTRAINT usage_events_correction_governance CHECK (
        correction_of_event_id IS NULL OR (
            correction_reason IS NOT NULL
            AND correction_approved_by IS NOT NULL
            AND correction_approved_at IS NOT NULL
            AND correction_approved_by IS DISTINCT FROM actor_id
        )
    );

CREATE INDEX usage_events_task_cost_idx
    ON usage_events(organization_id, account_id, job_id, occurred_at)
    WHERE job_id IS NOT NULL;

CREATE UNIQUE INDEX usage_events_mtf_provider_receipt_uq
    ON usage_events(provider, provider_receipt_ref, provider_sku, usage_unit)
    WHERE job_id IS NOT NULL AND provider_receipt_ref IS NOT NULL;

CREATE TABLE task_revenue_ledger_entries (
    revenue_entry_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    project_id varchar(96),
    legal_entity_id varchar(96) NOT NULL,
    job_id varchar(96) NOT NULL,
    run_number integer NOT NULL CHECK (run_number >= 1),
    entry_kind varchar(32) NOT NULL CHECK (entry_kind IN (
        'CHARGE', 'CREDIT', 'REFUND', 'CASH_RECEIPT',
        'REVENUE_RECOGNITION', 'TAX', 'PAYMENT_FEE',
        'CORRECTION', 'REVERSAL'
    )),
    entry_state varchar(24) NOT NULL
        CHECK (entry_state IN (
            'RECORDED', 'POSTED', 'RECOGNIZED', 'COLLECTED',
            'REFUNDED', 'REVERSED', 'DISPUTED', 'UNRECONCILED'
        )),
    amount_minor numeric(30,6) NOT NULL CHECK (amount_minor <> 0),
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    effective_at timestamptz NOT NULL,
    period_start timestamptz NOT NULL,
    period_end timestamptz NOT NULL CHECK (period_end > period_start),
    source_type varchar(96) NOT NULL,
    source_reference varchar(512) NOT NULL,
    idempotency_key varchar(160) NOT NULL,
    correction_of_revenue_entry_id varchar(96)
        REFERENCES task_revenue_ledger_entries(revenue_entry_id),
    reconciliation_status varchar(16) NOT NULL CHECK (reconciliation_status IN (
        'PENDING', 'RECONCILED', 'REJECTED', 'UNKNOWN', 'INCONCLUSIVE'
    )),
    signature_algorithm varchar(64) NOT NULL,
    signing_key_id varchar(255) NOT NULL,
    signed_digest char(64) NOT NULL CHECK (signed_digest ~ '^[0-9a-f]{64}$'),
    signature text NOT NULL CHECK (length(signature) BETWEEN 1 AND 4096),
    submitted_by_actor_id varchar(128) NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, account_id, idempotency_key),
    UNIQUE (revenue_entry_id, organization_id, account_id),
    CONSTRAINT task_revenue_scope_fk
        FOREIGN KEY (job_id, organization_id, account_id)
        REFERENCES execution_jobs(job_id, organization_id, account_id),
    CONSTRAINT task_revenue_sign CHECK (
        (entry_kind IN ('CHARGE', 'CASH_RECEIPT', 'REVENUE_RECOGNITION') AND amount_minor > 0)
        OR (entry_kind IN (
            'CREDIT', 'REFUND', 'TAX', 'PAYMENT_FEE', 'REVERSAL'
        ) AND amount_minor < 0)
        OR (entry_kind = 'CORRECTION' AND correction_of_revenue_entry_id IS NOT NULL)
    ),
    CONSTRAINT task_revenue_kind_state CHECK (
        entry_kind <> 'CASH_RECEIPT' OR entry_state IN ('COLLECTED', 'UNRECONCILED')
    ),
    CONSTRAINT task_revenue_refund_state CHECK (
        entry_kind <> 'REFUND' OR entry_state IN ('REFUNDED', 'UNRECONCILED')
    ),
    CONSTRAINT task_revenue_deduction_state CHECK (
        entry_kind NOT IN ('TAX', 'PAYMENT_FEE')
        OR entry_state IN ('RECORDED', 'POSTED', 'UNRECONCILED')
    )
);

CREATE INDEX task_revenue_job_time_idx
    ON task_revenue_ledger_entries(organization_id, account_id, job_id, effective_at)
    WHERE job_id IS NOT NULL;
CREATE TRIGGER task_revenue_ledger_entries_append_only
BEFORE UPDATE OR DELETE ON task_revenue_ledger_entries
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE task_revenue_allocations (
    revenue_allocation_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    revenue_entry_id varchar(96) NOT NULL,
    project_id varchar(96),
    job_id varchar(96) NOT NULL,
    run_number integer NOT NULL CHECK (run_number >= 1),
    allocation_basis varchar(32) NOT NULL CHECK (allocation_basis IN (
        'DIRECT_TASK', 'DIRECT_PROJECT', 'MILESTONE', 'USAGE',
        'SUBSCRIPTION_POLICY', 'MANUAL_APPROVED'
    )),
    policy_version varchar(64) NOT NULL,
    allocated_amount_minor numeric(30,6) NOT NULL CHECK (allocated_amount_minor <> 0),
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    effective_at timestamptz NOT NULL,
    idempotency_key varchar(160) NOT NULL,
    allocated_by_actor_id varchar(128) NOT NULL,
    signature_algorithm varchar(64) NOT NULL,
    signing_key_id varchar(255) NOT NULL,
    signed_digest char(64) NOT NULL CHECK (signed_digest ~ '^[0-9a-f]{64}$'),
    signature text NOT NULL CHECK (length(signature) BETWEEN 1 AND 4096),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, account_id, idempotency_key),
    CONSTRAINT task_revenue_allocation_source_scope_fk
        FOREIGN KEY (revenue_entry_id, organization_id, account_id)
        REFERENCES task_revenue_ledger_entries(
            revenue_entry_id, organization_id, account_id
        ),
    CONSTRAINT task_revenue_allocation_scope_fk
        FOREIGN KEY (job_id, organization_id, account_id)
        REFERENCES execution_jobs(job_id, organization_id, account_id)
);

CREATE INDEX task_revenue_allocations_source_idx
    ON task_revenue_allocations(revenue_entry_id, created_at);
CREATE TRIGGER task_revenue_allocations_append_only
BEFORE UPDATE OR DELETE ON task_revenue_allocations
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

ALTER TABLE cost_snapshots
    ADD COLUMN account_id varchar(96) REFERENCES accounts(account_id),
    ADD COLUMN job_id varchar(96),
    ADD COLUMN as_of timestamptz,
    ADD COLUMN base_currency char(3),
    ADD COLUMN estimated_cost_minor numeric(30,6),
    ADD COLUMN reserved_cost_minor numeric(30,6),
    ADD COLUMN posted_cost_minor numeric(30,6),
    ADD COLUMN reconciled_cost_minor numeric(30,6),
    ADD COLUMN unreconciled_event_count bigint,
    ADD COLUMN source_checksum char(64),
    ADD CONSTRAINT cost_snapshots_task_scope_fk
        FOREIGN KEY (job_id, organization_id, account_id)
        REFERENCES execution_jobs(job_id, organization_id, account_id),
    ADD CONSTRAINT cost_snapshots_mtf_shape CHECK (
        job_id IS NULL OR (
            account_id IS NOT NULL
            AND as_of IS NOT NULL
            AND base_currency ~ '^[A-Z]{3}$'
            AND estimated_cost_minor >= 0
            AND reserved_cost_minor >= 0
            AND posted_cost_minor >= 0
            AND reconciled_cost_minor >= 0
            AND unreconciled_event_count >= 0
            AND source_checksum ~ '^[0-9a-f]{64}$'
        )
    );

ALTER TABLE invoice_lines
    ADD COLUMN provider varchar(64),
    ADD COLUMN provider_invoice_ref varchar(255),
    ADD COLUMN provider_line_ref varchar(255),
    ADD COLUMN usage_event_ref varchar(96) REFERENCES usage_events(usage_event_id),
    ADD COLUMN billed_amount_minor numeric(30,6),
    ADD COLUMN billed_currency char(3),
    ADD COLUMN reconciliation_state varchar(24),
    ADD COLUMN reconciliation_reason varchar(96),
    ADD CONSTRAINT invoice_lines_mtf_shape CHECK (
        provider_invoice_ref IS NULL OR (
            provider IS NOT NULL
            AND provider_line_ref IS NOT NULL
            AND billed_amount_minor IS NOT NULL
            AND billed_currency ~ '^[A-Z]{3}$'
            AND reconciliation_state IN ('PENDING', 'MATCHED', 'VARIANCE', 'REJECTED')
        )
    );

CREATE UNIQUE INDEX invoice_lines_provider_line_uq
    ON invoice_lines(provider, provider_invoice_ref, provider_line_ref)
    WHERE provider_invoice_ref IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 6. RLS and direct-access boundary
-- ---------------------------------------------------------------------------

ALTER TABLE execution_account_slots ENABLE ROW LEVEL SECURITY;
ALTER TABLE execution_account_slots FORCE ROW LEVEL SECURITY;
CREATE POLICY account_owner_isolation ON execution_account_slots
    USING (account_id = nullif(current_setting('app.account_id', true), ''))
    WITH CHECK (account_id = nullif(current_setting('app.account_id', true), ''));

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'task_workflow_start_outbox',
        'task_checkpoint_manifests',
        'task_side_effect_receipts',
        'task_io_manifests',
        'task_finops_audit_events',
        'task_finops_outbox_events',
        'task_revenue_ledger_entries',
        'task_revenue_allocations'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_account_isolation ON %I ' ||
            'USING (organization_id = nullif(current_setting(''app.organization_id'', true), '''') ' ||
            'AND account_id = nullif(current_setting(''app.account_id'', true), '''')) ' ||
            'WITH CHECK (organization_id = nullif(current_setting(''app.organization_id'', true), '''') ' ||
            'AND account_id = nullif(current_setting(''app.account_id'', true), ''''))',
            table_name
        );
    END LOOP;
END;
$$;

-- FX snapshots are tenant-scoped but intentionally not account-scoped.
ALTER TABLE task_finops_fx_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_finops_fx_snapshots FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON task_finops_fx_snapshots
    USING (organization_id = nullif(current_setting('app.organization_id', true), ''))
    WITH CHECK (organization_id = nullif(current_setting('app.organization_id', true), ''));

REVOKE ALL ON execution_account_slots FROM PUBLIC;
REVOKE ALL ON task_workflow_start_outbox FROM PUBLIC;
REVOKE ALL ON task_checkpoint_manifests FROM PUBLIC;
REVOKE ALL ON task_side_effect_receipts FROM PUBLIC;
REVOKE ALL ON task_io_manifests FROM PUBLIC;
REVOKE ALL ON task_finops_audit_events FROM PUBLIC;
REVOKE ALL ON task_finops_outbox_events FROM PUBLIC;
REVOKE ALL ON task_finops_fx_snapshots FROM PUBLIC;
REVOKE ALL ON task_revenue_ledger_entries FROM PUBLIC;
REVOKE ALL ON task_revenue_allocations FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- 7. Identity binding, authorization and ordered task events
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_mtf_assert_bound_context()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_organization_id varchar(96) := nullif(current_setting('app.organization_id', true), '');
    v_account_id varchar(96) := nullif(current_setting('app.account_id', true), '');
    v_actor_id varchar(128) := nullif(current_setting('app.actor_id', true), '');
    v_request_id varchar(160) := nullif(current_setting('app.request_id', true), '');
    v_matches integer;
BEGIN
    IF v_organization_id IS NULL OR v_account_id IS NULL
       OR v_actor_id IS NULL OR v_request_id IS NULL THEN
        RAISE EXCEPTION 'ELMOS_MTF_IDENTITY_CONTEXT_MISSING';
    END IF;

    SELECT count(*) INTO v_matches
      FROM accounts account
      JOIN organization_memberships membership
        ON membership.organization_id = v_organization_id
       AND membership.account_ref = account.account_id
       AND membership.member_state = 'ACTIVE'
      JOIN user_identities identity
        ON identity.organization_id = membership.organization_id
       AND identity.account_ref = membership.account_ref
       AND identity.actor_id = v_actor_id
       AND identity.deprovisioned_at IS NULL
     WHERE account.account_id = v_account_id
       AND account.status = 'ACTIVE';

    IF v_matches <> 1 THEN
        RAISE EXCEPTION 'ELMOS_MTF_IDENTITY_CONTEXT_INVALID';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_bind_identity(
    p_organization_id varchar,
    p_account_id varchar,
    p_actor_id varchar,
    p_request_id varchar
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
BEGIN
    IF p_organization_id IS NULL OR length(p_organization_id) NOT BETWEEN 1 AND 96
       OR p_account_id IS NULL OR length(p_account_id) NOT BETWEEN 1 AND 96
       OR p_actor_id IS NULL OR length(p_actor_id) NOT BETWEEN 1 AND 128
       OR p_request_id IS NULL OR length(p_request_id) NOT BETWEEN 1 AND 160 THEN
        RAISE EXCEPTION 'ELMOS_MTF_IDENTITY_CONTEXT_INVALID';
    END IF;

    -- Tenant context is bound before querying FORCE-RLS identity projections.
    PERFORM set_config('app.organization_id', p_organization_id, true);
    PERFORM set_config('app.account_id', p_account_id, true);
    PERFORM set_config('app.actor_id', p_actor_id, true);
    PERFORM set_config('app.request_id', p_request_id, true);
    PERFORM elmos_mtf_assert_bound_context();

    INSERT INTO execution_account_slots(account_id, slot_number)
    SELECT p_account_id, slot_number
      FROM generate_series(1, 3) AS slot_number
    ON CONFLICT DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_require_finance_authority()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_authorized boolean;
BEGIN
    PERFORM elmos_mtf_assert_bound_context();
    SELECT EXISTS (
        SELECT 1
          FROM organization_memberships membership
          JOIN user_identities identity
            ON identity.organization_id = membership.organization_id
           AND identity.account_ref = membership.account_ref
           AND identity.deprovisioned_at IS NULL
         WHERE membership.organization_id = current_setting('app.organization_id')
           AND membership.account_ref = current_setting('app.account_id')
           AND membership.member_state = 'ACTIVE'
           AND membership.member_role IN ('OWNER', 'ADMIN', 'BILLING')
           AND identity.actor_id = current_setting('app.actor_id')
    ) INTO v_authorized;
    IF NOT v_authorized THEN
        RAISE EXCEPTION 'ELMOS_MTF_FINANCE_AUTHORITY_REQUIRED';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_append_job_event(
    p_job_id varchar,
    p_event_key varchar,
    p_event_type varchar,
    p_from_status varchar,
    p_to_status varchar,
    p_stage varchar,
    p_progress smallint,
    p_lease_ref varchar,
    p_runner_node_ref varchar,
    p_elapsed_millis bigint,
    p_eta_p50_millis bigint,
    p_eta_p90_millis bigint,
    p_payload_digest varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_job execution_jobs%ROWTYPE;
    v_existing execution_job_events%ROWTYPE;
    v_sequence integer;
    v_event_id varchar(96);
BEGIN
    PERFORM elmos_mtf_assert_bound_context();
    IF p_event_key IS NULL OR length(p_event_key) NOT BETWEEN 1 AND 160 THEN
        RAISE EXCEPTION 'ELMOS_MTF_EVENT_KEY_INVALID';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(p_job_id, 7070));
    SELECT * INTO v_job
      FROM execution_jobs
     WHERE job_id = p_job_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_TASK_UNKNOWN'; END IF;

    SELECT * INTO v_existing
      FROM execution_job_events
     WHERE job_id = p_job_id AND event_key = p_event_key;
    IF FOUND THEN
        IF v_existing.event_type IS DISTINCT FROM p_event_type
           OR v_existing.payload_digest IS DISTINCT FROM p_payload_digest::char(64) THEN
            RAISE EXCEPTION 'ELMOS_MTF_EVENT_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.job_event_id;
    END IF;

    SELECT coalesce(max(sequence_no), 0) + 1 INTO v_sequence
      FROM execution_job_events WHERE job_id = p_job_id;
    v_event_id := 'mtf-jev-' || md5(p_job_id || ':' || p_event_key);

    INSERT INTO execution_job_events (
        job_event_id, organization_id, account_id, job_id, sequence_no,
        event_key, event_type, from_status, to_status, stage, progress,
        runner_node_ref, lease_ref, actor_id, occurred_at, run_number,
        elapsed_millis, eta_p50_millis, eta_p90_millis, payload_digest
    ) VALUES (
        v_event_id, v_job.organization_id, v_job.account_id, v_job.job_id,
        v_sequence, p_event_key, p_event_type, p_from_status, p_to_status,
        p_stage, p_progress, p_runner_node_ref, p_lease_ref,
        current_setting('app.actor_id'), now(), v_job.workflow_run_number,
        p_elapsed_millis, p_eta_p50_millis, p_eta_p90_millis,
        p_payload_digest::char(64)
    );
    RETURN v_event_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_guard_execution_job_transition()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status IN (
        'SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'LOST'
    ) AND NEW.status IS DISTINCT FROM OLD.status THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_JOB_TERMINAL_IMMUTABLE';
    END IF;
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR (OLD.account_id IS NOT NULL AND NEW.account_id IS DISTINCT FROM OLD.account_id)
       OR NEW.actor_id IS DISTINCT FROM OLD.actor_id THEN
        RAISE EXCEPTION 'ELMOS_MTF_IDENTITY_IMMUTABLE';
    END IF;
    IF NEW.request_digest IS DISTINCT FROM OLD.request_digest
       OR (OLD.workflow_id IS NOT NULL AND NEW.workflow_id IS DISTINCT FROM OLD.workflow_id)
       OR (OLD.workflow_payload_version IS NOT NULL
           AND NEW.workflow_payload_version IS DISTINCT FROM OLD.workflow_payload_version) THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_JOB_REQUEST_IMMUTABLE';
    END IF;
    IF NEW.progress < OLD.progress OR NEW.progress_sequence < OLD.progress_sequence
       OR NEW.elapsed_millis < OLD.elapsed_millis THEN
        RAISE EXCEPTION 'ELMOS_MTF_PROGRESS_NOT_MONOTONIC';
    END IF;
    IF NEW.progress = 100 AND NEW.status <> 'SUCCEEDED' THEN
        RAISE EXCEPTION 'ELMOS_MTF_PROGRESS_100_REQUIRES_SUCCESS';
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
        (OLD.status = 'QUEUED' AND NEW.status IN ('CLAIMED', 'PAUSED', 'CANCELLED', 'RECONCILING'))
        OR (OLD.status = 'CLAIMED' AND NEW.status IN (
            'RUNNING', 'QUEUED', 'PAUSED', 'SUCCEEDED', 'PARTIAL',
            'FAILED', 'CANCELLED', 'UNKNOWN_RESULT'
        ))
        OR (OLD.status = 'RUNNING' AND NEW.status IN (
            'QUEUED', 'PAUSED', 'SUCCEEDED', 'PARTIAL',
            'FAILED', 'CANCELLED', 'UNKNOWN_RESULT'
        ))
        OR (OLD.status = 'PAUSED' AND NEW.status IN ('QUEUED', 'CANCELLED', 'RECONCILING'))
        OR (OLD.status = 'UNKNOWN_RESULT' AND NEW.status = 'RECONCILING')
        OR (OLD.status = 'RECONCILING' AND NEW.status IN (
            'QUEUED', 'SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'LOST'
        ))
    ) THEN
        RAISE EXCEPTION 'ELMOS_MTF_ILLEGAL_TASK_TRANSITION_%_TO_%', OLD.status, NEW.status;
    END IF;

    NEW.updated_at := now();
    NEW.state_version := OLD.state_version + 1;
    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- 8. Account-bound enqueue and three-slot claim
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_mtf_enqueue_execution_job(
    p_job_id varchar,
    p_organization_id varchar,
    p_account_id varchar,
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
    p_max_attempts smallint,
    p_request_id varchar,
    p_workload_class varchar,
    p_resource_units integer
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_profile task_finops_workload_profiles%ROWTYPE;
    v_job_id varchar(96);
    v_job execution_jobs%ROWTYPE;
BEGIN
    PERFORM elmos_mtf_bind_identity(
        p_organization_id, p_account_id, p_actor_id, p_request_id);

    SELECT * INTO v_profile
      FROM task_finops_workload_profiles
     WHERE workload_class = p_workload_class AND status = 'ACTIVE';
    IF NOT FOUND OR v_profile.resource_units <> p_resource_units THEN
        RAISE EXCEPTION 'ELMOS_MTF_WORKLOAD_PROFILE_MISMATCH';
    END IF;

    v_job_id := elmos_enqueue_execution_job(
        p_job_id, p_organization_id, p_actor_id, p_business_line, p_job_kind,
        p_idempotency_key, p_request_digest, p_request_payload,
        p_required_capability, p_runner_image, p_priority,
        p_budget_wall_seconds, p_max_attempts);

    SELECT * INTO v_job
      FROM execution_jobs
     WHERE job_id = v_job_id AND organization_id = p_organization_id
     FOR UPDATE;
    IF v_job.actor_id IS DISTINCT FROM p_actor_id
       OR v_job.request_digest IS DISTINCT FROM p_request_digest
       OR (v_job.account_id IS NOT NULL AND v_job.account_id <> p_account_id) THEN
        RAISE EXCEPTION 'ELMOS_MTF_TASK_IDEMPOTENCY_CONFLICT';
    END IF;

    IF v_job.account_id IS NULL THEN
        UPDATE execution_jobs
           SET account_id = p_account_id,
               admission_state = 'WAITING_FOR_SLOT',
               control_state = 'RUNNABLE',
               workflow_id = 'mtf-' || v_job_id,
               workflow_run_number = 1,
               workflow_payload_version = 1,
               workload_class = p_workload_class,
               resource_units = p_resource_units,
               request_id = p_request_id
         WHERE job_id = v_job_id;

        UPDATE execution_job_dispatch
           SET account_id = p_account_id,
               workload_class = p_workload_class,
               resource_units = p_resource_units,
               queue_reason = 'WAITING_FOR_ACCOUNT_SLOT'
         WHERE job_id = v_job_id;

        INSERT INTO task_workflow_start_outbox (
            outbox_id, organization_id, account_id, job_id, run_number,
            workflow_id, payload_version, payload_digest
        ) VALUES (
            'mtf-out-' || md5(v_job_id || ':1'), p_organization_id, p_account_id,
            v_job_id, 1, 'mtf-' || v_job_id, 1, p_request_digest
        ) ON CONFLICT (job_id, run_number) DO NOTHING;

        PERFORM elmos_mtf_append_job_event(
            v_job_id, 'submitted:' || p_idempotency_key, 'SUBMITTED',
            NULL::varchar, 'WAITING_FOR_SLOT', 'queued', 0::smallint,
            NULL::varchar, NULL::varchar, 0::bigint,
            NULL::bigint, NULL::bigint, p_request_digest);
    ELSE
        IF v_job.workload_class IS DISTINCT FROM p_workload_class
           OR v_job.resource_units IS DISTINCT FROM p_resource_units
           OR v_job.request_id IS DISTINCT FROM p_request_id THEN
            RAISE EXCEPTION 'ELMOS_MTF_TASK_IDEMPOTENCY_CONFLICT';
        END IF;
    END IF;

    RETURN v_job_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_claim_execution_jobs(
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

    -- p_capabilities is retained for wire compatibility only. The scheduler
    -- exclusively trusts the independently registered node capability set.
    FOR v_candidate IN
        SELECT d.job_id AS candidate_job_id,
               d.organization_id AS candidate_organization_id,
               d.account_id AS candidate_account_id
          FROM execution_job_dispatch d
          LEFT JOIN execution_dispatch_org_counters counter
            ON counter.organization_id = d.organization_id
         WHERE d.dispatch_state = 'READY'
           AND d.visible_at <= now()
           AND d.account_id IS NOT NULL
           AND d.required_capability = ANY (v_node.capabilities)
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

-- ---------------------------------------------------------------------------
-- 9. Lease generation fencing, progress, pause and completion
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_mtf_heartbeat_execution_lease(
    p_lease_id varchar,
    p_runner_node_id varchar,
    p_token_hash varchar,
    p_stage varchar,
    p_progress smallint,
    p_checkpoint jsonb,
    p_lease_seconds integer
) RETURNS TABLE (
    cancel_requested boolean,
    pause_requested boolean,
    lease_expires_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_dispatch execution_job_dispatch%ROWTYPE;
    v_lease runner_job_leases%ROWTYPE;
    v_job execution_jobs%ROWTYPE;
    v_slot execution_account_slots%ROWTYPE;
    v_expires timestamptz;
    v_progress smallint;
    v_elapsed bigint;
    v_eta50 bigint;
    v_eta90 bigint;
BEGIN
    IF p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 30 AND 600 THEN
        RAISE EXCEPTION 'ELMOS_MTF_HEARTBEAT_LEASE_SECONDS_INVALID';
    END IF;
    IF p_checkpoint IS NOT NULL AND jsonb_typeof(p_checkpoint) <> 'object' THEN
        RAISE EXCEPTION 'ELMOS_MTF_CHECKPOINT_CURSOR_INVALID';
    END IF;

    SELECT * INTO v_dispatch FROM execution_job_dispatch
     WHERE lease_ref = p_lease_id;
    IF NOT FOUND OR v_dispatch.account_id IS NULL THEN
        RAISE EXCEPTION 'ELMOS_MTF_LEASE_UNKNOWN';
    END IF;
    PERFORM set_config('app.organization_id', v_dispatch.organization_id, true);
    PERFORM set_config('app.account_id', v_dispatch.account_id, true);

    SELECT * INTO v_lease FROM runner_job_leases
     WHERE runner_job_lease_id = p_lease_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_LEASE_UNKNOWN'; END IF;
    IF v_lease.runner_node_ref IS DISTINCT FROM p_runner_node_id
       OR v_lease.token_sha256 IS DISTINCT FROM p_token_hash THEN
        RAISE EXCEPTION 'ELMOS_MTF_LEASE_CREDENTIAL_MISMATCH';
    END IF;
    IF v_lease.lease_state NOT IN ('ISSUED', 'ACTIVE')
       OR v_lease.expires_at <= now() THEN
        RAISE EXCEPTION 'ELMOS_MTF_LEASE_EXPIRED_OR_INACTIVE';
    END IF;

    SELECT * INTO v_job FROM execution_jobs
     WHERE job_id = v_lease.job_ref
       AND organization_id = v_dispatch.organization_id
       AND account_id = v_dispatch.account_id
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_LEASE_TASK_SCOPE_DRIFT'; END IF;
    PERFORM elmos_mtf_bind_identity(
        v_job.organization_id, v_job.account_id, v_job.actor_id,
        'runner-heartbeat:' || p_lease_id);

    SELECT * INTO v_slot FROM execution_account_slots
     WHERE execution_account_slots.account_id = v_job.account_id
       AND slot_number = v_job.account_slot_number
       AND active_job_id = v_job.job_id
       AND active_lease_ref = p_lease_id
       AND lease_generation = v_job.account_slot_generation
       AND slot_state = 'ACTIVE'
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_STALE_LEASE_GENERATION'; END IF;

    v_progress := coalesce(p_progress, v_job.progress);
    IF v_progress < v_job.progress OR v_progress >= 100 THEN
        RAISE EXCEPTION 'ELMOS_MTF_PROGRESS_NOT_MONOTONIC';
    END IF;
    v_elapsed := greatest(
        v_job.elapsed_millis,
        floor(extract(epoch FROM (now() - coalesce(v_job.started_at, now()))) * 1000)::bigint
    );
    IF v_progress > 0 THEN
        v_eta50 := greatest(0, ((v_elapsed * 100) / v_progress) - v_elapsed);
        v_eta90 := greatest(v_eta50, round(v_eta50 * 1.5)::bigint);
    ELSE
        v_eta50 := coalesce(v_job.eta_p50_millis, 0);
        v_eta90 := greatest(v_eta50, coalesce(v_job.eta_p90_millis, v_eta50));
    END IF;
    v_expires := now() + make_interval(secs => p_lease_seconds);

    UPDATE runner_job_leases
       SET lease_state = 'ACTIVE', last_heartbeat_at = now(), expires_at = v_expires
     WHERE runner_job_lease_id = p_lease_id;
    UPDATE execution_job_dispatch
       SET lease_expires_at = v_expires
     WHERE execution_job_dispatch.job_id = v_job.job_id;
    UPDATE execution_account_slots
       SET lease_expires_at = v_expires, last_renewed_at = now()
     WHERE execution_account_slots.account_id = v_job.account_id
       AND slot_number = v_job.account_slot_number
       AND lease_generation = v_job.account_slot_generation;
    UPDATE runner_nodes SET last_heartbeat_at = now()
     WHERE runner_node_id = p_runner_node_id;

    UPDATE execution_jobs
       SET status = CASE WHEN status = 'CLAIMED' THEN 'RUNNING' ELSE status END,
           stage = coalesce(p_stage, stage), progress = v_progress,
           progress_sequence = progress_sequence + 1,
           elapsed_millis = v_elapsed,
           eta_p50_millis = v_eta50, eta_p90_millis = v_eta90,
           checkpoint_cursor = coalesce(p_checkpoint, checkpoint_cursor)
     WHERE execution_jobs.job_id = v_job.job_id
       AND status IN ('CLAIMED', 'RUNNING');
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_TASK_NOT_HEARTBEATABLE'; END IF;

    PERFORM elmos_mtf_append_job_event(
        v_job.job_id,
        'heartbeat:' || v_job.account_slot_generation::text || ':' ||
            (v_job.progress_sequence + 1)::text,
        'PROGRESS_RECORDED', v_job.status, 'RUNNING', coalesce(p_stage, v_job.stage),
        v_progress, p_lease_id, p_runner_node_id, v_elapsed, v_eta50, v_eta90, NULL);

    cancel_requested := v_job.cancel_requested_at IS NOT NULL;
    pause_requested := v_job.control_state = 'PAUSE_REQUESTED';
    lease_expires_at := v_expires;
    RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_complete_execution_job(
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
SET row_security = on
AS $$
DECLARE
    v_dispatch execution_job_dispatch%ROWTYPE;
    v_lease runner_job_leases%ROWTYPE;
    v_job execution_jobs%ROWTYPE;
    v_slot execution_account_slots%ROWTYPE;
    v_requeue boolean := false;
    v_keep_reconciling boolean := false;
    v_event_type varchar(48);
    v_target_status varchar(24);
BEGIN
    IF p_status NOT IN (
        'SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'PAUSED', 'UNKNOWN_RESULT'
    ) THEN RAISE EXCEPTION 'ELMOS_MTF_COMPLETION_STATUS_INVALID'; END IF;
    IF NOT (
        (p_status = 'SUCCEEDED' AND p_result_status = 'PASSED')
        OR (p_status = 'PARTIAL' AND p_result_status = 'PARTIAL')
        OR (p_status = 'FAILED' AND p_result_status IN ('FAILED', 'BLOCKED'))
        OR (p_status = 'CANCELLED' AND p_result_status = 'BLOCKED')
        OR (p_status = 'PAUSED' AND p_result_status = 'NOT_RUN')
        OR (p_status = 'UNKNOWN_RESULT' AND p_result_status IN ('NOT_RUN', 'BLOCKED'))
    ) THEN RAISE EXCEPTION 'ELMOS_MTF_COMPLETION_RESULT_MISMATCH'; END IF;
    IF p_status = 'FAILED' AND p_failure_code IS NULL THEN
        RAISE EXCEPTION 'ELMOS_MTF_FAILURE_CODE_REQUIRED';
    END IF;

    SELECT * INTO v_dispatch FROM execution_job_dispatch
     WHERE lease_ref = p_lease_id;
    IF NOT FOUND OR v_dispatch.account_id IS NULL THEN
        RAISE EXCEPTION 'ELMOS_MTF_LEASE_UNKNOWN';
    END IF;
    PERFORM set_config('app.organization_id', v_dispatch.organization_id, true);
    PERFORM set_config('app.account_id', v_dispatch.account_id, true);

    SELECT * INTO v_lease FROM runner_job_leases
     WHERE runner_job_lease_id = p_lease_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_LEASE_UNKNOWN'; END IF;
    IF v_lease.runner_node_ref IS DISTINCT FROM p_runner_node_id
       OR v_lease.token_sha256 IS DISTINCT FROM p_token_hash THEN
        RAISE EXCEPTION 'ELMOS_MTF_LEASE_CREDENTIAL_MISMATCH';
    END IF;

    SELECT * INTO v_job FROM execution_jobs
     WHERE job_id = v_lease.job_ref
       AND organization_id = v_dispatch.organization_id
       AND account_id = v_dispatch.account_id
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_LEASE_TASK_SCOPE_DRIFT'; END IF;
    PERFORM elmos_mtf_bind_identity(
        v_job.organization_id, v_job.account_id, v_job.actor_id,
        'runner-complete:' || p_lease_id);

    IF v_lease.lease_state NOT IN ('ISSUED', 'ACTIVE') THEN
        RETURN false;
    END IF;
    IF v_lease.expires_at <= now() THEN
        RAISE EXCEPTION 'ELMOS_MTF_LEASE_EXPIRED';
    END IF;

    SELECT * INTO v_slot FROM execution_account_slots
     WHERE execution_account_slots.account_id = v_job.account_id
       AND slot_number = v_job.account_slot_number
       AND active_job_id = v_job.job_id
       AND active_lease_ref = p_lease_id
       AND lease_generation = v_job.account_slot_generation
       AND slot_state = 'ACTIVE'
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_STALE_LEASE_GENERATION'; END IF;

    v_requeue := p_status = 'FAILED'
        AND v_job.attempt < v_job.max_attempts
        AND (p_failure_code LIKE 'TRANSIENT\_%' ESCAPE '\'
             OR p_failure_code LIKE 'THROTTLED\_%' ESCAPE '\');
    v_keep_reconciling := p_status = 'UNKNOWN_RESULT';

    UPDATE runner_job_leases
       SET lease_state = 'RELEASED', released_at = now(),
           revocation_code = CASE WHEN v_keep_reconciling THEN 'UNKNOWN_RESULT' ELSE revocation_code END
     WHERE runner_job_lease_id = p_lease_id;

    IF v_requeue THEN
        UPDATE execution_jobs
           SET status = 'QUEUED', stage = 'retry-wait',
               admission_state = 'WAITING_FOR_SLOT', control_state = 'RUNNABLE',
               failure_code = p_failure_code,
               account_slot_number = NULL, account_slot_generation = NULL
         WHERE execution_jobs.job_id = v_job.job_id;
        UPDATE execution_job_dispatch
           SET dispatch_state = 'READY', queue_reason = 'RETRY_BACKOFF',
               visible_at = now() + make_interval(
                   secs => least(900, 30 * power(2, greatest(v_job.attempt - 1, 0))::integer))
         WHERE execution_job_dispatch.job_id = v_job.job_id;
        UPDATE execution_dispatch_org_counters
           SET leased_count = greatest(leased_count - 1, 0),
               queued_count = queued_count + 1, updated_at = now()
         WHERE organization_id = v_job.organization_id;
        v_target_status := 'QUEUED';
        v_event_type := 'REQUEUED';
    ELSIF p_status = 'PAUSED' THEN
        UPDATE execution_jobs
           SET status = 'PAUSED', stage = 'paused', result_status = 'NOT_RUN',
               control_state = 'PAUSED', admission_state = 'RELEASED',
               account_slot_number = NULL, account_slot_generation = NULL
         WHERE execution_jobs.job_id = v_job.job_id;
        UPDATE execution_job_dispatch
           SET dispatch_state = 'PAUSED', queue_reason = 'USER_PAUSED'
         WHERE execution_job_dispatch.job_id = v_job.job_id;
        UPDATE execution_dispatch_org_counters
           SET leased_count = greatest(leased_count - 1, 0), updated_at = now()
         WHERE organization_id = v_job.organization_id;
        v_target_status := 'PAUSED';
        v_event_type := 'PAUSED';
    ELSIF v_keep_reconciling THEN
        UPDATE execution_jobs
           SET status = 'UNKNOWN_RESULT', stage = 'unknown-result',
               result_status = p_result_status, failure_code = p_failure_code,
               control_state = 'MANUAL_RECOVERY', admission_state = 'RECONCILING'
         WHERE execution_jobs.job_id = v_job.job_id;
        UPDATE execution_job_dispatch
           SET dispatch_state = 'RECONCILING', queue_reason = 'UNKNOWN_RESULT'
         WHERE execution_job_dispatch.job_id = v_job.job_id;
        UPDATE execution_account_slots
           SET slot_state = 'RECONCILING', release_reason = 'UNKNOWN_RESULT'
         WHERE execution_account_slots.account_id = v_job.account_id
           AND slot_number = v_job.account_slot_number
           AND lease_generation = v_job.account_slot_generation;
        UPDATE execution_dispatch_org_counters
           SET leased_count = greatest(leased_count - 1, 0), updated_at = now()
         WHERE organization_id = v_job.organization_id;
        v_target_status := 'UNKNOWN_RESULT';
        v_event_type := 'UNKNOWN_RESULT';
    ELSE
        UPDATE execution_jobs
           SET status = p_status, result_status = p_result_status,
               failure_code = p_failure_code,
               progress = CASE WHEN p_status = 'SUCCEEDED' THEN 100 ELSE progress END,
               progress_sequence = progress_sequence + 1,
               admission_state = 'RELEASED', finished_at = now(),
               account_slot_number = NULL, account_slot_generation = NULL
         WHERE execution_jobs.job_id = v_job.job_id;
        UPDATE execution_job_dispatch
           SET dispatch_state = 'DONE', queue_reason = NULL
         WHERE execution_job_dispatch.job_id = v_job.job_id;
        UPDATE execution_dispatch_org_counters
           SET leased_count = greatest(leased_count - 1, 0), updated_at = now()
         WHERE organization_id = v_job.organization_id;
        v_target_status := p_status;
        v_event_type := CASE WHEN p_status = 'FAILED' THEN 'FAILED' ELSE 'COMPLETED' END;
    END IF;

    IF NOT v_keep_reconciling THEN
        UPDATE execution_account_slots
           SET slot_state = 'FREE', organization_id = NULL, active_job_id = NULL,
               active_lease_ref = NULL, lease_expires_at = NULL,
               last_renewed_at = NULL, released_at = now(),
               release_reason = CASE
                   WHEN v_requeue THEN 'RETRY'
                   WHEN p_status = 'PAUSED' THEN 'PAUSED'
                   ELSE p_status
               END
         WHERE execution_account_slots.account_id = v_job.account_id
           AND slot_number = v_job.account_slot_number
           AND lease_generation = v_job.account_slot_generation;
    END IF;

    PERFORM elmos_mtf_append_job_event(
        v_job.job_id, 'complete:' || p_lease_id, v_event_type,
        v_job.status, v_target_status,
        CASE WHEN v_requeue THEN 'retry-wait' ELSE lower(v_target_status) END,
        CASE WHEN p_status = 'SUCCEEDED' THEN 100::smallint ELSE v_job.progress END,
        p_lease_id, p_runner_node_id, v_job.elapsed_millis,
        v_job.eta_p50_millis, v_job.eta_p90_millis, NULL);
    RETURN true;
END;
$$;

-- ---------------------------------------------------------------------------
-- 10. Authenticated control commands and fail-closed lease reconciliation
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_mtf_pause_task(
    p_task_id varchar,
    p_reason_code varchar,
    p_idempotency_key varchar,
    p_request_digest varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_job execution_jobs%ROWTYPE;
    v_audit task_finops_audit_events%ROWTYPE;
    v_return_state varchar(24);
BEGIN
    PERFORM elmos_mtf_assert_bound_context();
    SELECT * INTO v_audit FROM task_finops_audit_events
     WHERE organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
       AND action = 'PAUSE_TASK' AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_audit.target_digest IS DISTINCT FROM p_request_digest::char(64) THEN
            RAISE EXCEPTION 'ELMOS_MTF_CONTROL_IDEMPOTENCY_CONFLICT';
        END IF;
        SELECT CASE
            WHEN status = 'PAUSED' THEN 'PAUSED'
            ELSE control_state
        END INTO v_return_state
          FROM execution_jobs WHERE job_id = p_task_id;
        RETURN v_return_state;
    END IF;

    SELECT * INTO v_job FROM execution_jobs
     WHERE job_id = p_task_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_TASK_UNKNOWN'; END IF;
    IF v_job.status IN ('SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'LOST') THEN
        RAISE EXCEPTION 'ELMOS_MTF_TASK_TERMINAL';
    END IF;

    IF v_job.status = 'QUEUED' THEN
        UPDATE execution_jobs
           SET status = 'PAUSED', stage = 'paused', control_state = 'PAUSED',
               admission_state = 'RELEASED'
         WHERE job_id = p_task_id;
        UPDATE execution_job_dispatch
           SET dispatch_state = 'PAUSED', queue_reason = 'USER_PAUSED'
         WHERE job_id = p_task_id;
        UPDATE execution_dispatch_org_counters
           SET queued_count = greatest(queued_count - 1, 0), updated_at = now()
         WHERE organization_id = v_job.organization_id;
        v_return_state := 'PAUSED';
    ELSIF v_job.status = 'PAUSED' THEN
        v_return_state := 'PAUSED';
    ELSIF v_job.status IN ('CLAIMED', 'RUNNING') THEN
        UPDATE execution_jobs SET control_state = 'PAUSE_REQUESTED'
         WHERE job_id = p_task_id;
        v_return_state := 'PAUSE_REQUESTED';
    ELSE
        RAISE EXCEPTION 'ELMOS_MTF_TASK_NOT_PAUSABLE';
    END IF;

    INSERT INTO task_finops_audit_events (
        audit_event_id, organization_id, account_id, job_id, actor_id,
        request_id, action, idempotency_key, outcome, reason_code, target_digest
    ) VALUES (
        'mtf-aud-' || md5(p_task_id || ':pause:' || p_idempotency_key),
        v_job.organization_id, v_job.account_id, v_job.job_id,
        current_setting('app.actor_id'), current_setting('app.request_id'),
        'PAUSE_TASK', p_idempotency_key, 'SUCCESS', p_reason_code, p_request_digest
    );
    PERFORM elmos_mtf_append_job_event(
        p_task_id, 'pause:' || p_idempotency_key,
        CASE WHEN v_return_state = 'PAUSED' THEN 'PAUSED' ELSE 'PAUSE_REQUESTED' END,
        v_job.status, v_return_state, v_job.stage, v_job.progress,
        NULL, NULL, v_job.elapsed_millis, v_job.eta_p50_millis,
        v_job.eta_p90_millis, p_request_digest);
    RETURN v_return_state;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_resume_task(
    p_task_id varchar,
    p_reason_code varchar,
    p_idempotency_key varchar,
    p_request_digest varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_job execution_jobs%ROWTYPE;
    v_audit task_finops_audit_events%ROWTYPE;
    v_return_state varchar(24);
BEGIN
    PERFORM elmos_mtf_assert_bound_context();
    SELECT * INTO v_audit FROM task_finops_audit_events
     WHERE organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
       AND action = 'RESUME_TASK' AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_audit.target_digest IS DISTINCT FROM p_request_digest::char(64) THEN
            RAISE EXCEPTION 'ELMOS_MTF_CONTROL_IDEMPOTENCY_CONFLICT';
        END IF;
        SELECT CASE
            WHEN status = 'QUEUED' THEN 'WAITING_FOR_SLOT'
            ELSE control_state
        END INTO v_return_state
          FROM execution_jobs WHERE job_id = p_task_id;
        RETURN v_return_state;
    END IF;

    SELECT * INTO v_job FROM execution_jobs
     WHERE job_id = p_task_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_TASK_UNKNOWN'; END IF;

    IF v_job.status = 'PAUSED' THEN
        UPDATE execution_jobs
           SET status = 'QUEUED', stage = 'queued', control_state = 'RUNNABLE',
               admission_state = 'WAITING_FOR_SLOT'
         WHERE job_id = p_task_id;
        UPDATE execution_job_dispatch
           SET dispatch_state = 'READY', lease_ref = NULL, runner_node_ref = NULL,
               lease_expires_at = NULL, visible_at = now(),
               queue_reason = 'RESUMED_WAITING_FOR_SLOT'
         WHERE job_id = p_task_id;
        UPDATE execution_dispatch_org_counters
           SET queued_count = queued_count + 1, updated_at = now()
         WHERE organization_id = v_job.organization_id;
        v_return_state := 'WAITING_FOR_SLOT';
    ELSIF v_job.status IN ('CLAIMED', 'RUNNING')
          AND v_job.control_state = 'PAUSE_REQUESTED' THEN
        UPDATE execution_jobs SET control_state = 'RESUME_REQUESTED'
         WHERE job_id = p_task_id;
        v_return_state := 'RESUME_REQUESTED';
    ELSE
        RAISE EXCEPTION 'ELMOS_MTF_TASK_NOT_RESUMABLE';
    END IF;

    INSERT INTO task_finops_audit_events (
        audit_event_id, organization_id, account_id, job_id, actor_id,
        request_id, action, idempotency_key, outcome, reason_code, target_digest
    ) VALUES (
        'mtf-aud-' || md5(p_task_id || ':resume:' || p_idempotency_key),
        v_job.organization_id, v_job.account_id, v_job.job_id,
        current_setting('app.actor_id'), current_setting('app.request_id'),
        'RESUME_TASK', p_idempotency_key, 'SUCCESS', p_reason_code, p_request_digest
    );
    PERFORM elmos_mtf_append_job_event(
        p_task_id, 'resume:' || p_idempotency_key,
        CASE WHEN v_return_state = 'WAITING_FOR_SLOT' THEN 'RESUMED' ELSE 'RESUME_REQUESTED' END,
        v_job.status, v_return_state, v_job.stage, v_job.progress,
        NULL, NULL, v_job.elapsed_millis, v_job.eta_p50_millis,
        v_job.eta_p90_millis, p_request_digest);
    RETURN v_return_state;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_request_execution_cancel(
    p_organization_id varchar,
    p_account_id varchar,
    p_job_id varchar,
    p_actor_id varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_job execution_jobs%ROWTYPE;
    v_actor_authorized boolean;
    v_result varchar(24);
BEGIN
    PERFORM elmos_mtf_assert_bound_context();
    IF current_setting('app.organization_id') IS DISTINCT FROM p_organization_id
       OR current_setting('app.account_id') IS DISTINCT FROM p_account_id
       OR current_setting('app.actor_id') IS DISTINCT FROM p_actor_id THEN
        RAISE EXCEPTION 'ELMOS_MTF_IDENTITY_CONTEXT_INVALID';
    END IF;
    SELECT * INTO v_job FROM execution_jobs
     WHERE job_id = p_job_id
       AND organization_id = p_organization_id
       AND account_id = p_account_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_MTF_TASK_UNKNOWN';
    END IF;
    SELECT p_actor_id = v_job.actor_id OR EXISTS (
        SELECT 1 FROM organization_memberships membership
         WHERE membership.organization_id = v_job.organization_id
           AND membership.account_ref = v_job.account_id
           AND membership.member_state = 'ACTIVE'
           AND membership.member_role IN ('OWNER', 'ADMIN', 'MAINTAINER')
    ) INTO v_actor_authorized;
    IF NOT v_actor_authorized THEN RAISE EXCEPTION 'ELMOS_MTF_CONTROL_FORBIDDEN'; END IF;
    IF v_job.status IN ('SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'LOST') THEN
        RAISE EXCEPTION 'ELMOS_MTF_TASK_TERMINAL';
    END IF;

    IF v_job.status IN ('QUEUED', 'PAUSED') THEN
        UPDATE execution_jobs
           SET status = 'CANCELLED', result_status = 'BLOCKED',
               control_state = 'CANCEL_REQUESTED', admission_state = 'RELEASED',
               cancel_requested_at = coalesce(cancel_requested_at, now()),
               cancel_requested_by = coalesce(cancel_requested_by, p_actor_id),
               finished_at = now()
         WHERE job_id = p_job_id;
        UPDATE execution_job_dispatch SET dispatch_state = 'DONE', queue_reason = NULL
         WHERE job_id = p_job_id;
        IF v_job.status = 'QUEUED' THEN
            UPDATE execution_dispatch_org_counters
               SET queued_count = greatest(queued_count - 1, 0), updated_at = now()
             WHERE organization_id = v_job.organization_id;
        END IF;
        v_result := 'CANCELLED';
    ELSE
        UPDATE execution_jobs
           SET control_state = 'CANCEL_REQUESTED',
               cancel_requested_at = coalesce(cancel_requested_at, now()),
               cancel_requested_by = coalesce(cancel_requested_by, p_actor_id)
         WHERE job_id = p_job_id;
        v_result := v_job.status;
    END IF;
    PERFORM elmos_mtf_append_job_event(
        p_job_id, 'cancel:' || current_setting('app.request_id'),
        'CANCEL_REQUESTED', v_job.status, v_result, v_job.stage, v_job.progress,
        NULL, NULL, v_job.elapsed_millis, v_job.eta_p50_millis,
        v_job.eta_p90_millis, NULL);
    RETURN v_result;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_append_system_event(
    p_job_id varchar,
    p_organization_id varchar,
    p_account_id varchar,
    p_event_key varchar,
    p_event_type varchar,
    p_from_status varchar,
    p_to_status varchar,
    p_failure_code varchar,
    p_lease_ref varchar,
    p_runner_node_ref varchar
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_sequence integer;
    v_job execution_jobs%ROWTYPE;
BEGIN
    PERFORM set_config('app.organization_id', p_organization_id, true);
    PERFORM set_config('app.account_id', coalesce(p_account_id, ''), true);
    PERFORM pg_advisory_xact_lock(hashtextextended(p_job_id, 7070));
    SELECT * INTO v_job FROM execution_jobs WHERE job_id = p_job_id FOR UPDATE;
    SELECT coalesce(max(sequence_no), 0) + 1 INTO v_sequence
      FROM execution_job_events WHERE job_id = p_job_id;
    INSERT INTO execution_job_events (
        job_event_id, organization_id, account_id, job_id, sequence_no,
        event_key, event_type, from_status, to_status, stage, progress,
        runner_node_ref, lease_ref, actor_id, failure_code, occurred_at,
        run_number, elapsed_millis, eta_p50_millis, eta_p90_millis
    ) VALUES (
        'mtf-sys-' || md5(p_job_id || ':' || p_event_key), p_organization_id,
        p_account_id, p_job_id, v_sequence, p_event_key, p_event_type,
        p_from_status, p_to_status, v_job.stage, v_job.progress,
        p_runner_node_ref, p_lease_ref, 'workload:lease-reaper', p_failure_code,
        now(), v_job.workflow_run_number, v_job.elapsed_millis,
        v_job.eta_p50_millis, v_job.eta_p90_millis
    ) ON CONFLICT (job_id, event_key) DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_reap_execution_leases()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_row record;
    v_job execution_jobs%ROWTYPE;
    v_count integer := 0;
BEGIN
    FOR v_row IN
        SELECT job_id, organization_id, account_id, lease_ref, runner_node_ref
          FROM execution_job_dispatch
         WHERE dispatch_state = 'LEASED' AND lease_expires_at < now()
         FOR UPDATE SKIP LOCKED
    LOOP
        PERFORM set_config('app.organization_id', v_row.organization_id, true);
        PERFORM set_config('app.account_id', coalesce(v_row.account_id, ''), true);
        UPDATE runner_job_leases
           SET lease_state = 'EXPIRED', released_at = now(),
               revocation_code = 'LEASE_EXPIRED'
         WHERE runner_job_lease_id = v_row.lease_ref
           AND lease_state IN ('ISSUED', 'ACTIVE');
        SELECT * INTO v_job FROM execution_jobs
         WHERE job_id = v_row.job_id FOR UPDATE;

        UPDATE execution_jobs
           SET status = 'UNKNOWN_RESULT', result_status = 'BLOCKED',
               failure_code = 'RUNNER_LEASE_LOST', stage = 'unknown-result',
               control_state = CASE WHEN account_id IS NULL THEN control_state ELSE 'MANUAL_RECOVERY' END,
               admission_state = CASE WHEN account_id IS NULL THEN admission_state ELSE 'RECONCILING' END
         WHERE job_id = v_row.job_id AND status IN ('CLAIMED', 'RUNNING');
        PERFORM elmos_mtf_append_system_event(
            v_row.job_id, v_row.organization_id, v_row.account_id,
            'lease-expired:' || v_row.lease_ref, 'LEASE_EXPIRED',
            v_job.status, 'UNKNOWN_RESULT', 'RUNNER_LEASE_LOST',
            v_row.lease_ref, v_row.runner_node_ref);
        UPDATE execution_jobs SET status = 'RECONCILING', stage = 'reconciling'
         WHERE job_id = v_row.job_id AND status = 'UNKNOWN_RESULT';
        UPDATE execution_job_dispatch
           SET dispatch_state = 'RECONCILING', queue_reason = 'LEASE_RESULT_UNKNOWN'
         WHERE job_id = v_row.job_id;
        IF v_row.account_id IS NOT NULL THEN
            UPDATE execution_account_slots
               SET slot_state = 'RECONCILING', release_reason = 'LEASE_EXPIRED'
             WHERE account_id = v_row.account_id
               AND active_job_id = v_row.job_id
               AND active_lease_ref = v_row.lease_ref;
        END IF;
        UPDATE execution_dispatch_org_counters
           SET leased_count = greatest(leased_count - 1, 0), updated_at = now()
         WHERE organization_id = v_row.organization_id;
        PERFORM elmos_mtf_append_system_event(
            v_row.job_id, v_row.organization_id, v_row.account_id,
            'reconciling:' || v_row.lease_ref, 'RECONCILING',
            'UNKNOWN_RESULT', 'RECONCILING', 'RUNNER_LEASE_LOST',
            v_row.lease_ref, v_row.runner_node_ref);
        v_count := v_count + 1;
    END LOOP;
    PERFORM elmos_reconcile_dispatch_counters();
    RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_request_manual_reconciliation(
    p_task_id varchar,
    p_reason_code varchar,
    p_evidence_reference varchar,
    p_idempotency_key varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_job execution_jobs%ROWTYPE;
    v_existing task_finops_audit_events%ROWTYPE;
BEGIN
    PERFORM elmos_mtf_assert_bound_context();
    IF p_task_id IS NULL OR length(p_task_id) NOT BETWEEN 1 AND 96
       OR p_reason_code IS NULL OR length(p_reason_code) NOT BETWEEN 1 AND 96
       OR p_evidence_reference IS NULL
       OR length(p_evidence_reference) NOT BETWEEN 1 AND 512
       OR p_idempotency_key IS NULL
       OR length(p_idempotency_key) NOT BETWEEN 1 AND 160 THEN
        RAISE EXCEPTION 'ELMOS_MTF_RECONCILIATION_REQUEST_INVALID';
    END IF;

    -- Serialize the account-wide idempotency namespace before taking the task
    -- lock. The key is account scoped, so two tasks cannot silently reuse it.
    PERFORM pg_advisory_xact_lock(hashtextextended(
        jsonb_build_array(
            current_setting('app.organization_id'),
            current_setting('app.account_id'),
            'REQUEST_RECONCILIATION',
            p_idempotency_key
        )::text,
        7070
    ));
    SELECT * INTO v_existing
      FROM task_finops_audit_events
     WHERE organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
       AND action = 'REQUEST_RECONCILIATION'
       AND idempotency_key = p_idempotency_key
     FOR UPDATE;
    IF FOUND THEN
        IF v_existing.job_id IS DISTINCT FROM p_task_id
           OR v_existing.actor_id IS DISTINCT FROM current_setting('app.actor_id')
           OR v_existing.reason_code IS DISTINCT FROM p_reason_code
           OR v_existing.metadata IS DISTINCT FROM
                jsonb_build_object('evidence_reference', p_evidence_reference) THEN
            RAISE EXCEPTION 'ELMOS_MTF_RECONCILIATION_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN 'PENDING';
    END IF;

    SELECT * INTO v_job FROM execution_jobs
     WHERE job_id = p_task_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_TASK_UNKNOWN'; END IF;
    IF v_job.status NOT IN ('UNKNOWN_RESULT', 'RECONCILING') THEN
        RAISE EXCEPTION 'ELMOS_MTF_RECONCILIATION_NOT_REQUIRED';
    END IF;
    IF v_job.status = 'UNKNOWN_RESULT' THEN
        UPDATE execution_jobs SET status = 'RECONCILING', stage = 'manual-reconciliation'
         WHERE job_id = p_task_id;
    END IF;
    INSERT INTO task_finops_audit_events (
        audit_event_id, organization_id, account_id, job_id, actor_id,
        request_id, action, idempotency_key, outcome, reason_code, metadata
    ) VALUES (
        'mtf-aud-' || md5(jsonb_build_array(
            v_job.organization_id, v_job.account_id, v_job.job_id,
            'REQUEST_RECONCILIATION', p_idempotency_key
        )::text),
        v_job.organization_id, v_job.account_id, v_job.job_id,
        current_setting('app.actor_id'), current_setting('app.request_id'),
        'REQUEST_RECONCILIATION', p_idempotency_key, 'SUCCESS', p_reason_code,
        jsonb_build_object('evidence_reference', p_evidence_reference)
    );
    RETURN 'PENDING';
END;
$$;

-- ---------------------------------------------------------------------------
-- 11. Checkpoint, side-effect, usage and revenue write boundaries
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_mtf_append_checkpoint(
    p_checkpoint_id varchar,
    p_task_id varchar,
    p_run_id varchar,
    p_node_id varchar,
    p_checkpoint_sequence bigint,
    p_input_manifest_digest varchar,
    p_repository_revision varchar,
    p_toolchain_digest varchar,
    p_model_digest varchar,
    p_schema_version varchar,
    p_object_ref varchar,
    p_content_digest varchar,
    p_content_length bigint,
    p_created_at timestamptz,
    p_idempotency_key varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_job execution_jobs%ROWTYPE;
    v_existing task_checkpoint_manifests%ROWTYPE;
BEGIN
    PERFORM elmos_mtf_assert_bound_context();
    IF length(p_checkpoint_id) NOT BETWEEN 1 AND 96
       OR p_checkpoint_sequence < 1 OR p_content_length < 0
       OR p_created_at > now() + interval '5 minutes'
       OR p_run_id !~ '^[1-9][0-9]*$' THEN
        RAISE EXCEPTION 'ELMOS_MTF_CHECKPOINT_INVALID';
    END IF;
    SELECT * INTO v_job FROM execution_jobs
     WHERE job_id = p_task_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_TASK_UNKNOWN'; END IF;
    IF p_run_id::integer <> v_job.workflow_run_number THEN
        RAISE EXCEPTION 'ELMOS_MTF_CHECKPOINT_RUN_MISMATCH';
    END IF;

    SELECT * INTO v_existing FROM task_checkpoint_manifests
     WHERE job_id = p_task_id AND event_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.checkpoint_id IS DISTINCT FROM p_checkpoint_id
           OR v_existing.organization_id IS DISTINCT FROM v_job.organization_id
           OR v_existing.account_id IS DISTINCT FROM v_job.account_id
           OR v_existing.job_id IS DISTINCT FROM v_job.job_id
           OR v_existing.run_number IS DISTINCT FROM v_job.workflow_run_number
           OR v_existing.event_key IS DISTINCT FROM p_idempotency_key
           OR v_existing.checkpoint_sequence IS DISTINCT FROM p_checkpoint_sequence
           OR v_existing.input_manifest_digest IS DISTINCT FROM
                p_input_manifest_digest::char(64)
           OR v_existing.repository_revision IS DISTINCT FROM p_repository_revision
           OR v_existing.state_digest IS DISTINCT FROM p_content_digest::char(64)
           OR v_existing.toolchain_digest IS DISTINCT FROM p_toolchain_digest::char(64)
           OR v_existing.model_digest IS DISTINCT FROM p_model_digest::char(64)
           OR v_existing.schema_version IS DISTINCT FROM p_schema_version
           OR v_existing.next_node IS DISTINCT FROM p_node_id
           OR v_existing.manifest IS DISTINCT FROM jsonb_build_object(
                'object_ref', p_object_ref,
                'content_digest', p_content_digest,
                'content_length', p_content_length
           )
           OR v_existing.compatibility_state IS DISTINCT FROM 'UNKNOWN'
           OR v_existing.created_by_actor_id IS DISTINCT FROM
                current_setting('app.actor_id')
           OR v_existing.created_at IS DISTINCT FROM p_created_at THEN
            RAISE EXCEPTION 'ELMOS_MTF_CHECKPOINT_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.checkpoint_id;
    END IF;

    INSERT INTO task_checkpoint_manifests (
        checkpoint_id, organization_id, account_id, job_id, run_number,
        event_key, checkpoint_sequence, input_manifest_digest,
        repository_revision, state_digest, toolchain_digest, model_digest,
        schema_version, next_node, manifest, compatibility_state,
        created_by_actor_id, created_at
    ) VALUES (
        p_checkpoint_id, v_job.organization_id, v_job.account_id, v_job.job_id,
        v_job.workflow_run_number, p_idempotency_key, p_checkpoint_sequence,
        p_input_manifest_digest, p_repository_revision, p_content_digest,
        p_toolchain_digest, p_model_digest, p_schema_version, p_node_id,
        jsonb_build_object(
            'object_ref', p_object_ref,
            'content_digest', p_content_digest,
            'content_length', p_content_length
        ),
        -- A writer cannot self-certify replay compatibility. A separately
        -- qualified recovery path must promote this state after verification.
        'UNKNOWN', current_setting('app.actor_id'), p_created_at
    );
    PERFORM elmos_mtf_append_job_event(
        p_task_id, 'checkpoint:' || p_idempotency_key,
        'CHECKPOINT_COMMITTED', v_job.status, v_job.status, p_node_id,
        v_job.progress, NULL, NULL, v_job.elapsed_millis,
        v_job.eta_p50_millis, v_job.eta_p90_millis, p_content_digest);
    RETURN p_checkpoint_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_record_side_effect_receipt(
    p_receipt_id varchar,
    p_task_id varchar,
    p_run_id varchar,
    p_node_id varchar,
    p_effect_type varchar,
    p_idempotency_key varchar,
    p_request_digest varchar,
    p_result_digest varchar,
    p_provider_reference varchar,
    p_result_state varchar,
    p_occurred_at timestamptz,
    p_signature_algorithm varchar,
    p_signing_key_id varchar,
    p_signature varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_job execution_jobs%ROWTYPE;
    v_existing task_side_effect_receipts%ROWTYPE;
BEGIN
    PERFORM elmos_mtf_assert_bound_context();
    IF length(p_receipt_id) NOT BETWEEN 1 AND 96
       OR p_run_id !~ '^[1-9][0-9]*$'
       OR p_result_state NOT IN ('CONFIRMED', 'FAILED', 'UNKNOWN')
       OR p_occurred_at > now() + interval '5 minutes' THEN
        RAISE EXCEPTION 'ELMOS_MTF_SIDE_EFFECT_RECEIPT_INVALID';
    END IF;
    SELECT * INTO v_job FROM execution_jobs
     WHERE job_id = p_task_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_TASK_UNKNOWN'; END IF;
    IF p_run_id::integer <> v_job.workflow_run_number THEN
        RAISE EXCEPTION 'ELMOS_MTF_SIDE_EFFECT_RUN_MISMATCH';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        v_job.organization_id, v_job.account_id,
        'SIDE_EFFECT_RECEIPT', p_idempotency_key
    )::text, 7070));
    SELECT * INTO v_existing FROM task_side_effect_receipts
     WHERE organization_id = v_job.organization_id
       AND account_id = v_job.account_id
       AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.side_effect_receipt_id IS DISTINCT FROM p_receipt_id
           OR v_existing.organization_id IS DISTINCT FROM v_job.organization_id
           OR v_existing.account_id IS DISTINCT FROM v_job.account_id
           OR v_existing.job_id IS DISTINCT FROM v_job.job_id
           OR v_existing.run_number IS DISTINCT FROM v_job.workflow_run_number
           OR v_existing.node_key IS DISTINCT FROM p_node_id
           OR v_existing.operation_type IS DISTINCT FROM p_effect_type
           OR v_existing.idempotency_key IS DISTINCT FROM p_idempotency_key
           OR v_existing.intent_digest IS DISTINCT FROM p_request_digest::char(64)
           OR v_existing.provider_reference IS DISTINCT FROM p_provider_reference
           OR v_existing.receipt_digest IS DISTINCT FROM p_result_digest::char(64)
           OR v_existing.receipt_state IS DISTINCT FROM p_result_state
           OR v_existing.occurred_at IS DISTINCT FROM p_occurred_at
           OR v_existing.signature_algorithm IS DISTINCT FROM p_signature_algorithm
           OR v_existing.signing_key_id IS DISTINCT FROM p_signing_key_id
           OR v_existing.signature IS DISTINCT FROM p_signature
           OR v_existing.recorded_by_actor_id IS DISTINCT FROM
                current_setting('app.actor_id')
           OR v_existing.metadata IS DISTINCT FROM '{}'::jsonb THEN
            RAISE EXCEPTION 'ELMOS_MTF_SIDE_EFFECT_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.side_effect_receipt_id;
    END IF;

    INSERT INTO task_side_effect_receipts (
        side_effect_receipt_id, organization_id, account_id, job_id,
        run_number, node_key, operation_type, idempotency_key, intent_digest,
        provider_reference, receipt_digest, receipt_state, occurred_at,
        signature_algorithm, signing_key_id, signature, recorded_by_actor_id
    ) VALUES (
        p_receipt_id, v_job.organization_id, v_job.account_id, v_job.job_id,
        v_job.workflow_run_number, p_node_id, p_effect_type, p_idempotency_key,
        p_request_digest, p_provider_reference, p_result_digest, p_result_state,
        p_occurred_at, p_signature_algorithm, p_signing_key_id, p_signature,
        current_setting('app.actor_id')
    );
    PERFORM elmos_mtf_append_job_event(
        p_task_id, 'side-effect:' || p_idempotency_key,
        'SIDE_EFFECT_RECEIPT', v_job.status, v_job.status, p_node_id,
        v_job.progress, NULL, NULL, v_job.elapsed_millis,
        v_job.eta_p50_millis, v_job.eta_p90_millis, p_result_digest);
    RETURN p_receipt_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_record_usage(
    p_usage_entry_id varchar,
    p_task_id varchar,
    p_run_id varchar,
    p_provider varchar,
    p_provider_sku varchar,
    p_usage_unit varchar,
    p_quantity numeric,
    p_price_book_id varchar,
    p_price_book_version varchar,
    p_price_effective_at timestamptz,
    p_source_currency varchar,
    p_unit_price_minor numeric,
    p_fx_snapshot_id varchar,
    p_base_currency varchar,
    p_fx_rate numeric,
    p_source_cost_minor numeric,
    p_base_cost_minor numeric,
    p_cost_state varchar,
    p_reconciliation_status varchar,
    p_provider_receipt_ref varchar,
    p_period_start timestamptz,
    p_period_end timestamptz,
    p_occurred_at timestamptz,
    p_idempotency_key varchar,
    p_correction_of_usage_entry_id varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_job execution_jobs%ROWTYPE;
    v_book price_books%ROWTYPE;
    v_item price_items%ROWTYPE;
    v_fx task_finops_fx_snapshots%ROWTYPE;
    v_existing usage_events%ROWTYPE;
    v_source_cost numeric(30,6);
    v_base_cost numeric(30,6);
    v_cost_class varchar(32);
BEGIN
    PERFORM elmos_mtf_assert_bound_context();
    IF length(p_usage_entry_id) NOT BETWEEN 1 AND 96
       OR p_run_id !~ '^[1-9][0-9]*$'
       OR p_quantity <= 0 OR p_unit_price_minor < 0 OR p_fx_rate <= 0
       OR p_period_end <= p_period_start
       OR p_occurred_at < p_period_start OR p_occurred_at > p_period_end
       OR p_correction_of_usage_entry_id IS NOT NULL THEN
        -- Corrections require a separate independently approved command that is
        -- intentionally unavailable while the exact dependency is unresolved.
        RAISE EXCEPTION 'ELMOS_MTF_USAGE_ENTRY_INVALID_OR_CORRECTION_UNAPPROVED';
    END IF;
    IF p_reconciliation_status = 'RECONCILED' AND p_provider_receipt_ref IS NULL THEN
        RAISE EXCEPTION 'ELMOS_MTF_RECONCILED_USAGE_RECEIPT_REQUIRED';
    END IF;

    SELECT * INTO v_job FROM execution_jobs
     WHERE job_id = p_task_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_TASK_UNKNOWN'; END IF;
    IF p_run_id::integer <> v_job.workflow_run_number THEN
        RAISE EXCEPTION 'ELMOS_MTF_USAGE_RUN_MISMATCH';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        v_job.organization_id, 'USAGE', p_idempotency_key
    )::text, 7070));

    SELECT * INTO v_book FROM price_books
     WHERE price_book_id = p_price_book_id
       AND organization_id = v_job.organization_id
       AND schema_version = p_price_book_version
       AND mtf_book_kind = 'PROVIDER_COST'
       AND status = 'PUBLISHED'
       AND currency = p_source_currency
       AND effective_from <= p_price_effective_at
       AND (effective_until IS NULL OR effective_until > p_price_effective_at);
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_PRICE_BOOK_NOT_EFFECTIVE'; END IF;
    SELECT * INTO v_item FROM price_items
     WHERE organization_id = v_job.organization_id
       AND price_book_ref = p_price_book_id
       AND provider = p_provider AND provider_sku = p_provider_sku
       AND usage_unit = p_usage_unit
       AND unit_price_minor = elmos_mtf_round_half_even(p_unit_price_minor, 9)
       AND effective_from <= p_price_effective_at
       AND (effective_until IS NULL OR effective_until > p_price_effective_at);
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_PRICE_ITEM_NOT_EFFECTIVE'; END IF;
    SELECT * INTO v_fx FROM task_finops_fx_snapshots
     WHERE fx_snapshot_id = p_fx_snapshot_id
       AND organization_id = v_job.organization_id
       AND source_currency = p_source_currency
       AND target_currency = p_base_currency
       AND rate = elmos_mtf_round_half_even(p_fx_rate, 12)
       AND effective_at <= p_occurred_at;
    IF NOT FOUND OR (p_cost_state = 'FINAL' AND v_fx.reconciliation_state <> 'RECONCILED') THEN
        RAISE EXCEPTION 'ELMOS_MTF_FX_SNAPSHOT_NOT_QUALIFIED';
    END IF;

    v_source_cost := elmos_mtf_round_half_even(
        elmos_mtf_round_half_even(p_quantity, 9)
            * elmos_mtf_round_half_even(p_unit_price_minor, 9),
        6
    );
    v_base_cost := elmos_mtf_round_half_even(
        v_source_cost * elmos_mtf_round_half_even(p_fx_rate, 12),
        6
    );
    IF v_source_cost IS DISTINCT FROM
            elmos_mtf_round_half_even(p_source_cost_minor, 6)
       OR v_base_cost IS DISTINCT FROM
            elmos_mtf_round_half_even(p_base_cost_minor, 6) THEN
        RAISE EXCEPTION 'ELMOS_MTF_COST_CONSERVATION_FAILED';
    END IF;
    v_cost_class := CASE
        WHEN p_usage_unit = 'HUMAN_REVIEW_MINUTE' THEN 'HUMAN_REVIEW'
        WHEN upper(p_provider) = 'ELMOS' THEN 'AUTONOMOUS_RUNTIME'
        ELSE 'THIRD_PARTY'
    END;

    SELECT * INTO v_existing FROM usage_events
     WHERE organization_id = v_job.organization_id
       AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.usage_event_id IS DISTINCT FROM p_usage_entry_id
           OR v_existing.organization_id IS DISTINCT FROM v_job.organization_id
           OR v_existing.account_id IS DISTINCT FROM v_job.account_id
           OR v_existing.job_id IS DISTINCT FROM v_job.job_id
           OR v_existing.run_number IS DISTINCT FROM v_job.workflow_run_number
           OR v_existing.schema_version IS DISTINCT FROM 'mtf-1.0'
           OR v_existing.status IS DISTINCT FROM 'RECORDED'
           OR v_existing.external_ref IS DISTINCT FROM p_provider_receipt_ref
           OR v_existing.idempotency_key IS DISTINCT FROM p_idempotency_key
           OR v_existing.content_hash IS NOT NULL
           OR v_existing.payload IS DISTINCT FROM '{}'::jsonb
           OR v_existing.subscription_id IS NOT NULL
           OR v_existing.quota_allocation_id IS NOT NULL
           OR v_existing.reservation_id IS NOT NULL
           OR v_existing.plan_id IS NOT NULL
           OR v_existing.meter_id IS NOT NULL
           OR v_existing.token_class IS NOT NULL
           OR v_existing.quantity IS NOT NULL
           OR v_existing.actor_id IS DISTINCT FROM current_setting('app.actor_id')
           OR v_existing.operation_key IS DISTINCT FROM 'task-runtime-cost'
           OR v_existing.occurred_at IS DISTINCT FROM p_occurred_at
           OR v_existing.reconciliation_status IS DISTINCT FROM
                p_reconciliation_status
           OR v_existing.provider IS DISTINCT FROM p_provider
           OR v_existing.provider_receipt_ref IS DISTINCT FROM p_provider_receipt_ref
           OR v_existing.provider_cost_currency IS DISTINCT FROM p_source_currency
           OR v_existing.provider_cost_minor IS DISTINCT FROM v_source_cost
           OR v_existing.provider_sku IS DISTINCT FROM p_provider_sku
           OR v_existing.usage_unit IS DISTINCT FROM p_usage_unit
           OR v_existing.exact_quantity IS DISTINCT FROM
                elmos_mtf_round_half_even(p_quantity, 9)
           OR v_existing.price_book_ref IS DISTINCT FROM p_price_book_id
           OR v_existing.price_book_version IS DISTINCT FROM p_price_book_version
           OR v_existing.price_effective_at IS DISTINCT FROM p_price_effective_at
           OR v_existing.price_item_ref IS DISTINCT FROM v_item.price_item_id
           OR v_existing.unit_price_minor IS DISTINCT FROM
                elmos_mtf_round_half_even(p_unit_price_minor, 9)
           OR v_existing.fx_snapshot_ref IS DISTINCT FROM p_fx_snapshot_id
           OR v_existing.fx_rate IS DISTINCT FROM
                elmos_mtf_round_half_even(p_fx_rate, 12)
           OR v_existing.base_currency IS DISTINCT FROM p_base_currency
           OR v_existing.base_cost_minor IS DISTINCT FROM v_base_cost
           OR v_existing.cost_state IS DISTINCT FROM p_cost_state
           OR v_existing.cost_class IS DISTINCT FROM v_cost_class
           OR v_existing.period_start IS DISTINCT FROM p_period_start
           OR v_existing.period_end IS DISTINCT FROM p_period_end
           OR v_existing.node_key IS NOT NULL
           OR v_existing.correction_of_event_id IS NOT NULL
           OR v_existing.correction_reason IS NOT NULL
           OR v_existing.correction_approved_by IS NOT NULL
           OR v_existing.correction_approved_at IS NOT NULL THEN
            RAISE EXCEPTION 'ELMOS_MTF_USAGE_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.usage_event_id;
    END IF;

    INSERT INTO usage_events (
        usage_event_id, organization_id, schema_version, status, external_ref,
        idempotency_key, payload, actor_id, operation_key, occurred_at,
        recorded_at, reconciliation_status, provider, provider_receipt_ref,
        provider_cost_currency, provider_cost_minor, account_id, job_id,
        run_number, provider_sku, usage_unit, exact_quantity, price_book_ref,
        price_book_version, price_effective_at, price_item_ref,
        unit_price_minor, fx_snapshot_ref, fx_rate, base_currency,
        base_cost_minor, cost_state, cost_class, period_start, period_end
    ) VALUES (
        p_usage_entry_id, v_job.organization_id, 'mtf-1.0', 'RECORDED',
        p_provider_receipt_ref, p_idempotency_key, '{}'::jsonb,
        current_setting('app.actor_id'), 'task-runtime-cost', p_occurred_at,
        now(), p_reconciliation_status, p_provider, p_provider_receipt_ref,
        p_source_currency, v_source_cost, v_job.account_id, v_job.job_id,
        v_job.workflow_run_number, p_provider_sku, p_usage_unit,
        elmos_mtf_round_half_even(p_quantity, 9),
        p_price_book_id, p_price_book_version, p_price_effective_at,
        v_item.price_item_id,
        elmos_mtf_round_half_even(p_unit_price_minor, 9), p_fx_snapshot_id,
        elmos_mtf_round_half_even(p_fx_rate, 12),
        p_base_currency, v_base_cost, p_cost_state, v_cost_class,
        p_period_start, p_period_end
    );
    PERFORM elmos_mtf_append_job_event(
        p_task_id, 'usage:' || p_idempotency_key, 'USAGE_RECORDED',
        v_job.status, v_job.status, v_job.stage, v_job.progress,
        NULL, NULL, v_job.elapsed_millis, v_job.eta_p50_millis,
        v_job.eta_p90_millis, NULL);
    RETURN p_usage_entry_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_record_revenue(
    p_revenue_entry_id varchar,
    p_task_id varchar,
    p_project_id varchar,
    p_legal_entity_id varchar,
    p_entry_kind varchar,
    p_entry_state varchar,
    p_currency varchar,
    p_amount_minor numeric,
    p_effective_at timestamptz,
    p_period_start timestamptz,
    p_period_end timestamptz,
    p_source_type varchar,
    p_source_reference varchar,
    p_correction_of_revenue_entry_id varchar,
    p_reconciliation_status varchar,
    p_signature_algorithm varchar,
    p_signing_key_id varchar,
    p_signed_digest varchar,
    p_signature varchar,
    p_idempotency_key varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_job execution_jobs%ROWTYPE;
    v_existing task_revenue_ledger_entries%ROWTYPE;
BEGIN
    PERFORM elmos_mtf_require_finance_authority();
    IF length(p_revenue_entry_id) NOT BETWEEN 1 AND 96
       OR elmos_mtf_round_half_even(p_amount_minor, 6) = 0
       OR p_period_end <= p_period_start
       OR p_effective_at < p_period_start OR p_effective_at > p_period_end
       OR p_correction_of_revenue_entry_id IS NOT NULL
       OR upper(p_source_type) = 'MANUAL' THEN
        -- Manual and correction entries remain unavailable until an exact,
        -- independent approval/SoD dependency is bound and exercised.
        RAISE EXCEPTION 'ELMOS_MTF_REVENUE_ENTRY_INVALID_OR_APPROVAL_UNRESOLVED';
    END IF;
    SELECT * INTO v_job FROM execution_jobs
     WHERE job_id = p_task_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_TASK_UNKNOWN'; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        v_job.organization_id, v_job.account_id,
        'REVENUE', p_idempotency_key
    )::text, 7070));
    SELECT * INTO v_existing FROM task_revenue_ledger_entries
     WHERE organization_id = v_job.organization_id
       AND account_id = v_job.account_id
       AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.revenue_entry_id IS DISTINCT FROM p_revenue_entry_id
           OR v_existing.organization_id IS DISTINCT FROM v_job.organization_id
           OR v_existing.account_id IS DISTINCT FROM v_job.account_id
           OR v_existing.project_id IS DISTINCT FROM p_project_id
           OR v_existing.legal_entity_id IS DISTINCT FROM p_legal_entity_id
           OR v_existing.job_id IS DISTINCT FROM v_job.job_id
           OR v_existing.run_number IS DISTINCT FROM v_job.workflow_run_number
           OR v_existing.entry_kind IS DISTINCT FROM p_entry_kind
           OR v_existing.entry_state IS DISTINCT FROM p_entry_state
           OR v_existing.amount_minor IS DISTINCT FROM
                elmos_mtf_round_half_even(p_amount_minor, 6)
           OR v_existing.currency IS DISTINCT FROM p_currency
           OR v_existing.effective_at IS DISTINCT FROM p_effective_at
           OR v_existing.period_start IS DISTINCT FROM p_period_start
           OR v_existing.period_end IS DISTINCT FROM p_period_end
           OR v_existing.source_type IS DISTINCT FROM p_source_type
           OR v_existing.source_reference IS DISTINCT FROM p_source_reference
           OR v_existing.idempotency_key IS DISTINCT FROM p_idempotency_key
           OR v_existing.correction_of_revenue_entry_id IS DISTINCT FROM
                p_correction_of_revenue_entry_id
           OR v_existing.reconciliation_status IS DISTINCT FROM
                p_reconciliation_status
           OR v_existing.signature_algorithm IS DISTINCT FROM p_signature_algorithm
           OR v_existing.signing_key_id IS DISTINCT FROM p_signing_key_id
           OR v_existing.signed_digest IS DISTINCT FROM p_signed_digest::char(64)
           OR v_existing.signature IS DISTINCT FROM p_signature
           OR v_existing.submitted_by_actor_id IS DISTINCT FROM
                current_setting('app.actor_id') THEN
            RAISE EXCEPTION 'ELMOS_MTF_REVENUE_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.revenue_entry_id;
    END IF;

    INSERT INTO task_revenue_ledger_entries (
        revenue_entry_id, organization_id, account_id, project_id,
        legal_entity_id, job_id, run_number, entry_kind, entry_state,
        amount_minor, currency, effective_at, period_start, period_end,
        source_type, source_reference, idempotency_key,
        reconciliation_status, signature_algorithm, signing_key_id,
        signed_digest, signature, submitted_by_actor_id
    ) VALUES (
        p_revenue_entry_id, v_job.organization_id, v_job.account_id,
        p_project_id, p_legal_entity_id, v_job.job_id, v_job.workflow_run_number,
        p_entry_kind, p_entry_state,
        elmos_mtf_round_half_even(p_amount_minor, 6), p_currency,
        p_effective_at, p_period_start, p_period_end, p_source_type,
        p_source_reference, p_idempotency_key, p_reconciliation_status,
        p_signature_algorithm, p_signing_key_id, p_signed_digest, p_signature,
        current_setting('app.actor_id')
    );
    PERFORM elmos_mtf_append_job_event(
        p_task_id, 'revenue:' || p_idempotency_key, 'REVENUE_RECORDED',
        v_job.status, v_job.status, v_job.stage, v_job.progress,
        NULL, NULL, v_job.elapsed_millis, v_job.eta_p50_millis,
        v_job.eta_p90_millis, p_signed_digest);
    RETURN p_revenue_entry_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_allocate_revenue(
    p_allocation_id varchar,
    p_revenue_entry_id varchar,
    p_task_id varchar,
    p_project_id varchar,
    p_allocation_basis varchar,
    p_policy_version varchar,
    p_currency varchar,
    p_amount_minor numeric,
    p_effective_at timestamptz,
    p_signature_algorithm varchar,
    p_signing_key_id varchar,
    p_signed_digest varchar,
    p_signature varchar,
    p_idempotency_key varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_job execution_jobs%ROWTYPE;
    v_source task_revenue_ledger_entries%ROWTYPE;
    v_existing task_revenue_allocations%ROWTYPE;
    v_allocated numeric(30,6);
BEGIN
    PERFORM elmos_mtf_require_finance_authority();
    IF length(p_allocation_id) NOT BETWEEN 1 AND 96
       OR elmos_mtf_round_half_even(p_amount_minor, 6) = 0
       OR p_allocation_basis = 'MANUAL_APPROVED' THEN
        RAISE EXCEPTION 'ELMOS_MTF_ALLOCATION_INVALID_OR_APPROVAL_UNRESOLVED';
    END IF;
    SELECT * INTO v_job FROM execution_jobs
     WHERE job_id = p_task_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_TASK_UNKNOWN'; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        v_job.organization_id, v_job.account_id,
        'REVENUE_ALLOCATION', p_idempotency_key
    )::text, 7070));
    SELECT * INTO v_source FROM task_revenue_ledger_entries
     WHERE revenue_entry_id = p_revenue_entry_id
       AND organization_id = v_job.organization_id
       AND account_id = v_job.account_id
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_REVENUE_SOURCE_UNKNOWN'; END IF;
    IF v_source.currency <> p_currency
       OR sign(v_source.amount_minor) <> sign(p_amount_minor) THEN
        RAISE EXCEPTION 'ELMOS_MTF_ALLOCATION_CURRENCY_OR_SIGN_MISMATCH';
    END IF;

    SELECT * INTO v_existing FROM task_revenue_allocations
     WHERE organization_id = v_job.organization_id
       AND account_id = v_job.account_id
       AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.revenue_allocation_id IS DISTINCT FROM p_allocation_id
           OR v_existing.organization_id IS DISTINCT FROM v_job.organization_id
           OR v_existing.account_id IS DISTINCT FROM v_job.account_id
           OR v_existing.revenue_entry_id IS DISTINCT FROM p_revenue_entry_id
           OR v_existing.project_id IS DISTINCT FROM p_project_id
           OR v_existing.job_id IS DISTINCT FROM v_job.job_id
           OR v_existing.run_number IS DISTINCT FROM v_job.workflow_run_number
           OR v_existing.allocation_basis IS DISTINCT FROM p_allocation_basis
           OR v_existing.policy_version IS DISTINCT FROM p_policy_version
           OR v_existing.allocated_amount_minor IS DISTINCT FROM
                elmos_mtf_round_half_even(p_amount_minor, 6)
           OR v_existing.currency IS DISTINCT FROM p_currency
           OR v_existing.effective_at IS DISTINCT FROM p_effective_at
           OR v_existing.idempotency_key IS DISTINCT FROM p_idempotency_key
           OR v_existing.allocated_by_actor_id IS DISTINCT FROM
                current_setting('app.actor_id')
           OR v_existing.signature_algorithm IS DISTINCT FROM p_signature_algorithm
           OR v_existing.signing_key_id IS DISTINCT FROM p_signing_key_id
           OR v_existing.signed_digest IS DISTINCT FROM p_signed_digest::char(64)
           OR v_existing.signature IS DISTINCT FROM p_signature THEN
            RAISE EXCEPTION 'ELMOS_MTF_ALLOCATION_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.revenue_allocation_id;
    END IF;
    SELECT coalesce(sum(allocated_amount_minor), 0) INTO v_allocated
      FROM task_revenue_allocations
     WHERE revenue_entry_id = p_revenue_entry_id
       AND organization_id = v_job.organization_id
       AND account_id = v_job.account_id;
    IF abs(v_allocated + elmos_mtf_round_half_even(p_amount_minor, 6))
            > abs(v_source.amount_minor) THEN
        RAISE EXCEPTION 'ELMOS_MTF_REVENUE_OVER_ALLOCATION';
    END IF;

    INSERT INTO task_revenue_allocations (
        revenue_allocation_id, organization_id, account_id, revenue_entry_id,
        project_id, job_id, run_number, allocation_basis, policy_version,
        allocated_amount_minor, currency, effective_at, idempotency_key,
        allocated_by_actor_id, signature_algorithm, signing_key_id,
        signed_digest, signature
    ) VALUES (
        p_allocation_id, v_job.organization_id, v_job.account_id,
        p_revenue_entry_id, p_project_id, v_job.job_id,
        v_job.workflow_run_number, p_allocation_basis, p_policy_version,
        elmos_mtf_round_half_even(p_amount_minor, 6), p_currency,
        p_effective_at, p_idempotency_key,
        current_setting('app.actor_id'), p_signature_algorithm,
        p_signing_key_id, p_signed_digest, p_signature
    );
    PERFORM elmos_mtf_append_job_event(
        p_task_id, 'revenue-allocation:' || p_idempotency_key,
        'REVENUE_RECORDED', v_job.status, v_job.status, v_job.stage,
        v_job.progress, NULL, NULL, v_job.elapsed_millis,
        v_job.eta_p50_millis, v_job.eta_p90_millis, p_signed_digest);
    RETURN p_allocation_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- 12. Account-safe read projections and metric definitions
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_mtf_queue_position(p_job_id varchar)
RETURNS integer
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_job execution_jobs%ROWTYPE;
    v_dispatch execution_job_dispatch%ROWTYPE;
    v_position integer;
BEGIN
    PERFORM elmos_mtf_assert_bound_context();
    SELECT * INTO v_job FROM execution_jobs
     WHERE job_id = p_job_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id');
    IF NOT FOUND THEN RETURN NULL; END IF;
    SELECT * INTO v_dispatch FROM execution_job_dispatch
     WHERE job_id = p_job_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id');
    IF NOT FOUND OR v_dispatch.dispatch_state <> 'READY'
       OR v_dispatch.account_id IS NULL THEN RETURN NULL; END IF;

    SELECT 1 + count(*) INTO v_position
      FROM execution_job_dispatch candidate
     WHERE candidate.organization_id = v_dispatch.organization_id
       AND candidate.account_id = v_dispatch.account_id
       AND candidate.dispatch_state = 'READY'
       AND candidate.visible_at <= now()
       AND (
            candidate.priority > v_dispatch.priority
            OR (candidate.priority = v_dispatch.priority
                AND candidate.enqueued_at < v_dispatch.enqueued_at)
            OR (candidate.priority = v_dispatch.priority
                AND candidate.enqueued_at = v_dispatch.enqueued_at
                AND candidate.job_id < v_dispatch.job_id)
       );
    RETURN v_position;
END;
$$;

CREATE VIEW mtf_account_concurrency_status AS
SELECT
    current_setting('app.organization_id')::varchar AS organization_id,
    slot.account_id,
    3::integer AS root_task_limit,
    count(*) FILTER (WHERE slot.slot_state IN ('ACTIVE', 'RECONCILING'))::integer
        AS active_root_tasks,
    (SELECT count(*)::integer
       FROM execution_jobs waiting
      WHERE waiting.organization_id = current_setting('app.organization_id')
        AND waiting.account_id = slot.account_id
        AND waiting.status = 'QUEUED'
        AND waiting.admission_state = 'WAITING_FOR_SLOT') AS waiting_root_tasks,
    count(*) FILTER (WHERE slot.slot_state = 'FREE')::integer AS available_root_slots,
    transaction_timestamp() AS as_of,
    CASE WHEN bool_or(slot.slot_state = 'RECONCILING')
         THEN 'UNKNOWN' ELSE 'RECONCILED' END::varchar AS reconciliation_status
FROM execution_account_slots slot
WHERE slot.account_id = nullif(current_setting('app.account_id', true), '')
GROUP BY slot.account_id;

CREATE VIEW mtf_task_events AS
SELECT
    event.organization_id,
    event.account_id,
    event.job_id AS task_id,
    event.job_event_id AS event_id,
    event.sequence_no::bigint AS event_sequence,
    event.event_type,
    CASE
        WHEN event.to_status IN ('WAITING_FOR_SLOT', 'QUEUED') THEN 'WAITING_FOR_SLOT'
        WHEN event.to_status IN ('ADMITTED', 'CLAIMED') THEN 'ADMITTED'
        WHEN event.to_status = 'RUNNING' THEN 'RUNNING'
        WHEN event.to_status = 'PAUSE_REQUESTED' THEN 'PAUSE_REQUESTED'
        WHEN event.to_status = 'PAUSED' THEN 'PAUSED'
        WHEN event.to_status = 'RESUME_REQUESTED' THEN 'RESUME_REQUESTED'
        WHEN event.to_status = 'UNKNOWN_RESULT' THEN 'UNKNOWN_RESULT'
        WHEN event.to_status = 'RECONCILING' THEN 'RECONCILING'
        WHEN event.to_status = 'SUCCEEDED' THEN 'SUCCEEDED'
        WHEN event.to_status IN ('PARTIAL', 'FAILED', 'LOST') THEN 'FAILED'
        WHEN event.to_status = 'CANCELLED' THEN 'CANCELLED'
        ELSE CASE
            WHEN job.status = 'QUEUED' THEN 'WAITING_FOR_SLOT'
            WHEN job.status = 'CLAIMED' THEN 'ADMITTED'
            WHEN job.status IN ('PARTIAL', 'LOST') THEN 'FAILED'
            ELSE job.status
        END
    END::varchar AS task_state,
    coalesce(event.stage, job.stage) AS stage,
    CASE
        WHEN coalesce(event.to_status, job.status) = 'SUCCEEDED' THEN 100
        ELSE least(coalesce(event.progress, job.progress), 99)
    END::smallint AS progress_percent,
    coalesce(event.actor_id, job.actor_id) AS actor_id,
    event.occurred_at,
    event.payload_digest::varchar AS evidence_digest
FROM execution_job_events event
JOIN execution_jobs job ON job.job_id = event.job_id
WHERE event.account_id = nullif(current_setting('app.account_id', true), '')
  AND event.organization_id = nullif(current_setting('app.organization_id', true), '');

CREATE VIEW mtf_task_progress AS
SELECT
    job.organization_id,
    job.account_id,
    job.job_id AS task_id,
    CASE
        WHEN job.status = 'QUEUED' THEN 'WAITING_FOR_SLOT'
        WHEN job.status = 'CLAIMED' THEN 'ADMITTED'
        WHEN job.status IN ('PARTIAL', 'LOST') THEN 'FAILED'
        ELSE job.status
    END::varchar AS task_state,
    job.stage,
    job.progress AS progress_percent,
    job.elapsed_millis,
    coalesce(job.eta_p50_millis, 0) AS eta_p50_millis,
    coalesce(job.eta_p90_millis, coalesce(job.eta_p50_millis, 0)) AS eta_p90_millis,
    coalesce(max(event.sequence_no), 0)::bigint AS last_event_sequence,
    job.updated_at AS as_of,
    CASE
        WHEN job.status IN ('UNKNOWN_RESULT', 'RECONCILING') THEN 'UNKNOWN'
        WHEN job.status IN ('SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'LOST')
            THEN 'RECONCILED'
        ELSE 'PENDING'
    END::varchar AS reconciliation_status
FROM execution_jobs job
LEFT JOIN execution_job_events event ON event.job_id = job.job_id
WHERE job.organization_id = nullif(current_setting('app.organization_id', true), '')
  AND job.account_id = nullif(current_setting('app.account_id', true), '')
GROUP BY job.job_id;

CREATE VIEW mtf_task_financial_summary AS
WITH usage_totals AS (
    SELECT
        organization_id, account_id, job_id, base_currency AS currency,
        coalesce(sum(base_cost_minor) FILTER (WHERE cost_state = 'ESTIMATED'), 0)::numeric(30,6)
            AS estimated_cost_minor,
        coalesce(sum(base_cost_minor) FILTER (WHERE cost_state = 'RESERVED'), 0)::numeric(30,6)
            AS reserved_cost_minor,
        coalesce(sum(base_cost_minor) FILTER (WHERE cost_state = 'POSTED'), 0)::numeric(30,6)
            AS posted_cost_minor,
        (sum(base_cost_minor) FILTER (WHERE cost_state = 'FINAL'))::numeric(30,6)
            AS final_cost_minor,
        count(*)::bigint AS usage_entry_count,
        count(*) FILTER (WHERE reconciliation_status <> 'RECONCILED')::bigint
            AS unreconciled_usage_count,
        max(occurred_at) AS usage_watermark
      FROM usage_events
     WHERE job_id IS NOT NULL
       AND organization_id = nullif(current_setting('app.organization_id', true), '')
       AND account_id = nullif(current_setting('app.account_id', true), '')
     GROUP BY organization_id, account_id, job_id, base_currency
), allocation_totals AS (
    SELECT revenue_entry_id, coalesce(sum(allocated_amount_minor), 0)::numeric(30,6)
        AS allocated_amount_minor
      FROM task_revenue_allocations
     GROUP BY revenue_entry_id
), revenue_totals AS (
    SELECT
        revenue.organization_id, revenue.account_id, revenue.job_id, revenue.currency,
        coalesce(sum(revenue.amount_minor) FILTER (
            WHERE revenue.entry_kind NOT IN ('TAX', 'PAYMENT_FEE')
              AND (revenue.entry_kind = 'REVENUE_RECOGNITION'
                   OR revenue.entry_state = 'RECOGNIZED')), 0)::numeric(30,6)
            AS recognized_revenue_minor,
        coalesce(sum(revenue.amount_minor) FILTER (
            WHERE revenue.entry_kind = 'CASH_RECEIPT'
               OR revenue.entry_state = 'COLLECTED'), 0)::numeric(30,6)
            AS collected_cash_minor,
        coalesce(sum(revenue.amount_minor) FILTER (
            WHERE revenue.entry_kind = 'REFUND'
               OR revenue.entry_state = 'REFUNDED'), 0)::numeric(30,6)
            AS refunds_minor,
        count(*)::bigint AS revenue_entry_count,
        count(*) FILTER (
            WHERE revenue.reconciliation_status <> 'RECONCILED'
               OR abs(coalesce(allocation.allocated_amount_minor, 0))
                    <> abs(revenue.amount_minor)
        )::bigint AS unreconciled_revenue_count,
        max(revenue.effective_at) AS revenue_watermark
      FROM task_revenue_ledger_entries revenue
      LEFT JOIN allocation_totals allocation
        ON allocation.revenue_entry_id = revenue.revenue_entry_id
     WHERE revenue.organization_id = nullif(current_setting('app.organization_id', true), '')
       AND revenue.account_id = nullif(current_setting('app.account_id', true), '')
     GROUP BY revenue.organization_id, revenue.account_id, revenue.job_id, revenue.currency
), currencies AS (
    SELECT organization_id, account_id, job_id, currency FROM usage_totals
    UNION
    SELECT organization_id, account_id, job_id, currency FROM revenue_totals
)
SELECT
    currency_scope.organization_id,
    currency_scope.account_id,
    currency_scope.job_id AS task_id,
    currency_scope.currency,
    coalesce(usage.estimated_cost_minor, 0)::numeric(30,6) AS estimated_cost_minor,
    coalesce(usage.reserved_cost_minor, 0)::numeric(30,6) AS reserved_cost_minor,
    coalesce(usage.posted_cost_minor, 0)::numeric(30,6) AS posted_cost_minor,
    coalesce(usage.final_cost_minor, 0)::numeric(30,6) AS final_cost_minor,
    coalesce(revenue.recognized_revenue_minor, 0)::numeric(30,6)
        AS recognized_revenue_minor,
    coalesce(revenue.collected_cash_minor, 0)::numeric(30,6) AS collected_cash_minor,
    coalesce(revenue.refunds_minor, 0)::numeric(30,6) AS refunds_minor,
    (coalesce(revenue.recognized_revenue_minor, 0)
        - coalesce(usage.final_cost_minor, usage.posted_cost_minor, 0))::numeric(30,6)
        AS gross_profit_minor,
    CASE WHEN coalesce(revenue.recognized_revenue_minor, 0) = 0 THEN NULL
         ELSE elmos_mtf_round_half_even(
             (coalesce(revenue.recognized_revenue_minor, 0)
                - coalesce(usage.final_cost_minor, usage.posted_cost_minor, 0))
             / revenue.recognized_revenue_minor, 18)
    END AS gross_margin_ratio,
    coalesce(usage.usage_entry_count, 0)::bigint AS usage_entry_count,
    coalesce(usage.unreconciled_usage_count, 0)::bigint AS unreconciled_usage_count,
    coalesce(revenue.revenue_entry_count, 0)::bigint AS revenue_entry_count,
    coalesce(revenue.unreconciled_revenue_count, 0)::bigint AS unreconciled_revenue_count,
    greatest(usage.usage_watermark, revenue.revenue_watermark) AS event_watermark,
    greatest(job.updated_at, usage.usage_watermark, revenue.revenue_watermark) AS as_of,
    CASE WHEN coalesce(usage.unreconciled_usage_count, 0) > 0
              OR coalesce(revenue.unreconciled_revenue_count, 0) > 0
         THEN 'UNKNOWN' ELSE 'RECONCILED' END::varchar AS reconciliation_status,
    CASE WHEN coalesce(usage.unreconciled_usage_count, 0) > 0
              OR coalesce(revenue.unreconciled_revenue_count, 0) > 0
         THEN 'UNRECONCILED'
         WHEN usage.job_id IS NULL OR revenue.job_id IS NULL THEN 'PARTIAL'
         ELSE 'CURRENT' END::varchar AS qualification
FROM currencies currency_scope
JOIN execution_jobs job ON job.job_id = currency_scope.job_id
LEFT JOIN usage_totals usage
  ON usage.organization_id = currency_scope.organization_id
 AND usage.account_id = currency_scope.account_id
 AND usage.job_id = currency_scope.job_id
 AND usage.currency = currency_scope.currency
LEFT JOIN revenue_totals revenue
  ON revenue.organization_id = currency_scope.organization_id
 AND revenue.account_id = currency_scope.account_id
 AND revenue.job_id = currency_scope.job_id
 AND revenue.currency = currency_scope.currency;

-- ---------------------------------------------------------------------------
-- 13. Capability grants (deployment logins remain externally provisioned)
-- ---------------------------------------------------------------------------

REVOKE ALL ON task_finops_workload_profiles FROM PUBLIC;
REVOKE ALL ON mtf_account_concurrency_status FROM PUBLIC;
REVOKE ALL ON mtf_task_events FROM PUBLIC;
REVOKE ALL ON mtf_task_progress FROM PUBLIC;
REVOKE ALL ON mtf_task_financial_summary FROM PUBLIC;

DO $$
DECLARE v_function record;
BEGIN
    FOR v_function IN
        SELECT function_record.oid::regprocedure AS signature
          FROM pg_proc function_record
          JOIN pg_namespace namespace_record
            ON namespace_record.oid = function_record.pronamespace
         WHERE namespace_record.nspname = 'public'
           AND function_record.proname LIKE 'elmos_mtf_%'
    LOOP
        EXECUTE format(
            'REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', v_function.signature);
    END LOOP;
END;
$$;

GRANT EXECUTE ON FUNCTION elmos_mtf_bind_identity(varchar, varchar, varchar, varchar)
    TO elmos_mtf_application, elmos_mtf_workflow, elmos_mtf_analytics;
GRANT EXECUTE ON FUNCTION elmos_mtf_enqueue_execution_job(
    varchar, varchar, varchar, varchar, varchar, varchar, varchar, varchar,
    jsonb, varchar, varchar, smallint, integer, smallint, varchar, varchar, integer
) TO elmos_mtf_application;
GRANT EXECUTE ON FUNCTION elmos_mtf_queue_position(varchar)
    TO elmos_mtf_application, elmos_mtf_analytics;
GRANT EXECUTE ON FUNCTION elmos_mtf_round_half_even(numeric, integer)
    TO elmos_mtf_application, elmos_mtf_workflow, elmos_mtf_analytics;
GRANT EXECUTE ON FUNCTION elmos_mtf_pause_task(varchar, varchar, varchar, varchar)
    TO elmos_mtf_application;
GRANT EXECUTE ON FUNCTION elmos_mtf_resume_task(varchar, varchar, varchar, varchar)
    TO elmos_mtf_application;
GRANT EXECUTE ON FUNCTION elmos_mtf_request_execution_cancel(
    varchar, varchar, varchar, varchar)
    TO elmos_mtf_application;

GRANT EXECUTE ON FUNCTION elmos_mtf_claim_execution_jobs(
    varchar, text[], integer, integer, text[], text[]
) TO elmos_mtf_workflow;
GRANT EXECUTE ON FUNCTION elmos_mtf_heartbeat_execution_lease(
    varchar, varchar, varchar, varchar, smallint, jsonb, integer
) TO elmos_mtf_workflow;
GRANT EXECUTE ON FUNCTION elmos_mtf_complete_execution_job(
    varchar, varchar, varchar, varchar, varchar, varchar
) TO elmos_mtf_workflow;
GRANT EXECUTE ON FUNCTION elmos_mtf_reap_execution_leases()
    TO elmos_mtf_workflow;
GRANT EXECUTE ON FUNCTION elmos_mtf_append_checkpoint(
    varchar, varchar, varchar, varchar, bigint, varchar, varchar, varchar,
    varchar, varchar, varchar, varchar, bigint, timestamptz, varchar
) TO elmos_mtf_workflow;
GRANT EXECUTE ON FUNCTION elmos_mtf_record_side_effect_receipt(
    varchar, varchar, varchar, varchar, varchar, varchar, varchar, varchar,
    varchar, varchar, timestamptz, varchar, varchar, varchar
) TO elmos_mtf_workflow;
GRANT EXECUTE ON FUNCTION elmos_mtf_record_usage(
    varchar, varchar, varchar, varchar, varchar, varchar, numeric, varchar,
    varchar, timestamptz, varchar, numeric, varchar, varchar, numeric, numeric,
    numeric, varchar, varchar, varchar, timestamptz, timestamptz, timestamptz,
    varchar, varchar
) TO elmos_mtf_workflow;
GRANT EXECUTE ON FUNCTION elmos_mtf_record_revenue(
    varchar, varchar, varchar, varchar, varchar, varchar, varchar, numeric,
    timestamptz, timestamptz, timestamptz, varchar, varchar, varchar, varchar,
    varchar, varchar, varchar, varchar, varchar
) TO elmos_mtf_workflow;
GRANT EXECUTE ON FUNCTION elmos_mtf_allocate_revenue(
    varchar, varchar, varchar, varchar, varchar, varchar, varchar, numeric,
    timestamptz, varchar, varchar, varchar, varchar, varchar
) TO elmos_mtf_workflow;
GRANT EXECUTE ON FUNCTION elmos_mtf_request_manual_reconciliation(
    varchar, varchar, varchar, varchar
) TO elmos_mtf_workflow;

GRANT SELECT ON task_finops_workload_profiles
    TO elmos_mtf_application, elmos_mtf_workflow, elmos_mtf_analytics;
GRANT SELECT ON mtf_account_concurrency_status, mtf_task_events,
    mtf_task_progress, mtf_task_financial_summary
    TO elmos_mtf_application, elmos_mtf_workflow, elmos_mtf_analytics;

COMMENT ON VIEW mtf_task_financial_summary IS
    'Current repository projection only. UNKNOWN/UNRECONCILED never means certified; provider, invoice, cash and independent-verifier evidence remain separately gated.';
