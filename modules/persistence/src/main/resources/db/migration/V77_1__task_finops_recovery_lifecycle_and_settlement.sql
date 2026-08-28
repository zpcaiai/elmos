-- ELMOS V77.1: fail-closed recovery, tenant lifecycle, rollout and settlement.
--
-- This repository-owned migration implements durable local control-plane
-- boundaries.  It does not call Temporal, object-storage, payment, bank, tax,
-- KMS or production deployment providers.  UNKNOWN outcomes remain non-final,
-- and the supplied package's V100-V102 reference migrations remain NOT_APPLIED.

-- ---------------------------------------------------------------------------
-- 1. Safe feature rollout state
-- ---------------------------------------------------------------------------

CREATE TABLE task_finops_feature_rollouts (
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    environment varchar(24) NOT NULL
        CHECK (environment IN ('DEVELOPMENT', 'STAGING', 'PRODUCTION')),
    feature_key varchar(96) NOT NULL,
    rollout_stage varchar(24) NOT NULL
        CHECK (rollout_stage IN ('OFF', 'SHADOW', 'CANARY', 'ON')),
    exposure_percent smallint NOT NULL CHECK (exposure_percent BETWEEN 0 AND 100),
    state_version bigint NOT NULL CHECK (state_version >= 1),
    changed_by_actor_id varchar(128) NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, account_id, environment, feature_key),
    CONSTRAINT task_finops_feature_exposure_shape CHECK (
        (rollout_stage IN ('OFF', 'SHADOW') AND exposure_percent = 0)
        OR (rollout_stage = 'CANARY' AND exposure_percent BETWEEN 1 AND 99)
        OR (rollout_stage = 'ON' AND exposure_percent = 100)
    )
);

-- ---------------------------------------------------------------------------
-- 2. Independently recorded checkpoint decisions and fork lineage
-- ---------------------------------------------------------------------------

CREATE TABLE task_checkpoint_compatibility_decisions (
    compatibility_decision_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    checkpoint_id varchar(96) NOT NULL REFERENCES task_checkpoint_manifests(checkpoint_id),
    decision_state varchar(24) NOT NULL
        CHECK (decision_state IN ('COMPATIBLE', 'INCOMPATIBLE')),
    fingerprint_digest char(64) NOT NULL CHECK (fingerprint_digest ~ '^[0-9a-f]{64}$'),
    reason_codes text[] NOT NULL,
    evidence_digest char(64) NOT NULL CHECK (evidence_digest ~ '^[0-9a-f]{64}$'),
    signature_algorithm varchar(64) NOT NULL,
    signing_key_id varchar(255) NOT NULL,
    signature text NOT NULL CHECK (length(signature) BETWEEN 1 AND 4096),
    verifier_actor_id varchar(128) NOT NULL,
    decided_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (checkpoint_id, evidence_digest),
    CONSTRAINT task_checkpoint_compatibility_reasons CHECK (
        cardinality(reason_codes) BETWEEN 1 AND 16
    )
);

CREATE TRIGGER task_checkpoint_compatibility_decisions_append_only
BEFORE UPDATE OR DELETE ON task_checkpoint_compatibility_decisions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE task_recovery_forks (
    recovery_fork_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    parent_job_id varchar(96) NOT NULL,
    parent_run_number integer NOT NULL CHECK (parent_run_number >= 1),
    checkpoint_id varchar(96) NOT NULL REFERENCES task_checkpoint_manifests(checkpoint_id),
    compatibility_decision_id varchar(96) NOT NULL
        REFERENCES task_checkpoint_compatibility_decisions(compatibility_decision_id),
    child_job_id varchar(96) NOT NULL UNIQUE,
    child_run_number integer NOT NULL CHECK (child_run_number >= 1),
    request_digest char(64) NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    idempotency_key varchar(160) NOT NULL,
    requested_by_actor_id varchar(128) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, account_id, idempotency_key),
    CONSTRAINT task_recovery_parent_scope_fk
        FOREIGN KEY (parent_job_id, organization_id, account_id)
        REFERENCES execution_jobs(job_id, organization_id, account_id),
    CONSTRAINT task_recovery_child_scope_fk
        FOREIGN KEY (child_job_id, organization_id, account_id)
        REFERENCES execution_jobs(job_id, organization_id, account_id)
);

CREATE TRIGGER task_recovery_forks_append_only
BEFORE UPDATE OR DELETE ON task_recovery_forks
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

-- ---------------------------------------------------------------------------
-- 3. Recoverable tenant export and deletion workflow
-- ---------------------------------------------------------------------------

CREATE TABLE task_tenant_lifecycle_jobs (
    lifecycle_job_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    operation_kind varchar(16) NOT NULL CHECK (operation_kind IN ('EXPORT', 'DELETE')),
    export_format varchar(16) NOT NULL CHECK (export_format IN ('JSON', 'CSV')),
    operation_state varchar(24) NOT NULL CHECK (operation_state IN (
        'REQUESTED', 'EXPORTING', 'TOMBSTONED', 'PURGE_PENDING',
        'RECONCILING', 'COMPLETED', 'BLOCKED', 'UNKNOWN_RESULT', 'FAILED'
    )),
    retention_cutoff timestamptz NOT NULL,
    page_cursor varchar(512),
    manifest_digest char(64) CHECK (manifest_digest IS NULL OR manifest_digest ~ '^[0-9a-f]{64}$'),
    exported_row_count bigint NOT NULL DEFAULT 0 CHECK (exported_row_count >= 0),
    exported_byte_count bigint NOT NULL DEFAULT 0 CHECK (exported_byte_count >= 0),
    provider_result_state varchar(24) NOT NULL DEFAULT 'NOT_RUN'
        CHECK (provider_result_state IN (
            'NOT_RUN', 'PENDING', 'CONFIRMED', 'FAILED', 'UNKNOWN'
        )),
    failure_code varchar(96),
    request_digest char(64) NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    idempotency_key varchar(160) NOT NULL,
    requested_by_actor_id varchar(128) NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    state_version bigint NOT NULL DEFAULT 1 CHECK (state_version >= 1),
    UNIQUE (organization_id, account_id, idempotency_key),
    UNIQUE (lifecycle_job_id, organization_id, account_id),
    CONSTRAINT task_tenant_lifecycle_terminal_shape CHECK (
        (operation_state = 'COMPLETED' AND completed_at IS NOT NULL
            AND provider_result_state = 'CONFIRMED' AND manifest_digest IS NOT NULL)
        OR (operation_state <> 'COMPLETED' AND completed_at IS NULL)
    )
);

-- Once deletion reaches the irreversible local tombstone boundary the account
-- may never acquire another execution job.  The fence is separate from the
-- lifecycle row so a later FAILED/COMPLETED transition cannot accidentally
-- reopen task creation.
CREATE TABLE task_tenant_task_creation_fences (
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    lifecycle_job_id varchar(96) NOT NULL,
    fence_reason varchar(48) NOT NULL DEFAULT 'TENANT_TOMBSTONED'
        CHECK (fence_reason = 'TENANT_TOMBSTONED'),
    fenced_by_actor_id varchar(128) NOT NULL,
    fenced_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, account_id),
    UNIQUE (lifecycle_job_id),
    CONSTRAINT task_tenant_creation_fence_scope_fk
        FOREIGN KEY (lifecycle_job_id, organization_id, account_id)
        REFERENCES task_tenant_lifecycle_jobs(
            lifecycle_job_id, organization_id, account_id)
);

CREATE TRIGGER task_tenant_task_creation_fences_append_only
BEFORE UPDATE OR DELETE ON task_tenant_task_creation_fences
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE task_tenant_export_pages (
    export_page_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    lifecycle_job_id varchar(96) NOT NULL,
    page_number bigint NOT NULL CHECK (page_number >= 1),
    cursor_digest char(64) NOT NULL CHECK (cursor_digest ~ '^[0-9a-f]{64}$'),
    row_count bigint NOT NULL CHECK (row_count >= 0),
    byte_count bigint NOT NULL CHECK (byte_count >= 0),
    cumulative_row_count bigint NOT NULL CHECK (cumulative_row_count >= row_count),
    cumulative_byte_count bigint NOT NULL CHECK (cumulative_byte_count >= byte_count),
    terminal boolean NOT NULL,
    page_digest char(64) NOT NULL CHECK (page_digest ~ '^[0-9a-f]{64}$'),
    checkpoint_chain_digest char(64) NOT NULL
        CHECK (checkpoint_chain_digest ~ '^[0-9a-f]{64}$'),
    manifest_digest char(64)
        CHECK (manifest_digest IS NULL OR manifest_digest ~ '^[0-9a-f]{64}$'),
    expected_state_version bigint NOT NULL CHECK (expected_state_version >= 1),
    request_digest char(64) NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    idempotency_key varchar(160) NOT NULL,
    actor_id varchar(128) NOT NULL,
    checkpointed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (lifecycle_job_id, page_number),
    UNIQUE (organization_id, account_id, idempotency_key),
    CONSTRAINT task_tenant_export_page_scope_fk
        FOREIGN KEY (lifecycle_job_id, organization_id, account_id)
        REFERENCES task_tenant_lifecycle_jobs(
            lifecycle_job_id, organization_id, account_id),
    CONSTRAINT task_tenant_export_page_terminal_shape CHECK (
        (terminal AND manifest_digest IS NOT NULL
            AND manifest_digest = checkpoint_chain_digest)
        OR (NOT terminal AND manifest_digest IS NULL)
    )
);

CREATE TRIGGER task_tenant_export_pages_append_only
BEFORE UPDATE OR DELETE ON task_tenant_export_pages
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE task_tenant_lifecycle_events (
    lifecycle_event_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    lifecycle_job_id varchar(96) NOT NULL REFERENCES task_tenant_lifecycle_jobs(lifecycle_job_id),
    event_sequence bigint NOT NULL CHECK (event_sequence >= 1),
    from_state varchar(24),
    to_state varchar(24) NOT NULL,
    page_cursor varchar(512),
    manifest_digest char(64) CHECK (manifest_digest IS NULL OR manifest_digest ~ '^[0-9a-f]{64}$'),
    exported_row_count bigint NOT NULL CHECK (exported_row_count >= 0),
    exported_byte_count bigint NOT NULL CHECK (exported_byte_count >= 0),
    provider_result_state varchar(24) NOT NULL,
    failure_code varchar(96),
    request_digest char(64) NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    idempotency_key varchar(160) NOT NULL,
    actor_id varchar(128) NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (lifecycle_job_id, event_sequence),
    UNIQUE (organization_id, account_id, idempotency_key)
);

ALTER TABLE execution_jobs
    ADD CONSTRAINT execution_jobs_tenant_lifecycle_fk
    FOREIGN KEY (tenant_lifecycle_job_id)
    REFERENCES task_tenant_lifecycle_jobs(lifecycle_job_id);

CREATE TRIGGER task_tenant_lifecycle_events_append_only
BEFORE UPDATE OR DELETE ON task_tenant_lifecycle_events
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE task_tenant_resource_tombstones (
    lifecycle_job_id varchar(96) NOT NULL REFERENCES task_tenant_lifecycle_jobs(lifecycle_job_id),
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    resource_type varchar(24) NOT NULL
        CHECK (resource_type IN ('EXECUTION_JOB', 'ARTIFACT', 'CONTENT_OBJECT')),
    resource_id varchar(96) NOT NULL,
    resource_digest char(64) CHECK (resource_digest IS NULL OR resource_digest ~ '^[0-9a-f]{64}$'),
    tombstoned_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (lifecycle_job_id, resource_type, resource_id)
);

CREATE TRIGGER task_tenant_resource_tombstones_append_only
BEFORE UPDATE OR DELETE ON task_tenant_resource_tombstones
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE task_tenant_purge_items (
    lifecycle_job_id varchar(96) NOT NULL REFERENCES task_tenant_lifecycle_jobs(lifecycle_job_id),
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    content_object_id varchar(96) NOT NULL REFERENCES content_objects(content_object_id),
    purge_state varchar(24) NOT NULL DEFAULT 'PENDING'
        CHECK (purge_state IN ('PENDING', 'CONFIRMED', 'FAILED', 'UNKNOWN')),
    state_version bigint NOT NULL DEFAULT 1 CHECK (state_version >= 1),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (lifecycle_job_id, content_object_id)
);

CREATE TABLE task_tenant_purge_receipts (
    purge_receipt_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    lifecycle_job_id varchar(96) NOT NULL REFERENCES task_tenant_lifecycle_jobs(lifecycle_job_id),
    content_object_id varchar(96) NOT NULL REFERENCES content_objects(content_object_id),
    provider_result_state varchar(24) NOT NULL
        CHECK (provider_result_state IN ('CONFIRMED_ABSENT', 'FAILED', 'UNKNOWN')),
    provider_reference varchar(255),
    evidence_digest char(64) CHECK (evidence_digest IS NULL OR evidence_digest ~ '^[0-9a-f]{64}$'),
    request_digest char(64) NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    idempotency_key varchar(160) NOT NULL,
    expected_state_version bigint NOT NULL CHECK (expected_state_version >= 1),
    actor_id varchar(128) NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, account_id, idempotency_key),
    CONSTRAINT task_tenant_purge_confirmation_shape CHECK (
        provider_result_state <> 'CONFIRMED_ABSENT'
        OR (provider_reference IS NOT NULL AND evidence_digest IS NOT NULL)
    )
);

CREATE TRIGGER task_tenant_purge_receipts_append_only
BEFORE UPDATE OR DELETE ON task_tenant_purge_receipts
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

-- ---------------------------------------------------------------------------
-- 4. Exact, append-only settlement reconciliation results
-- ---------------------------------------------------------------------------

CREATE TABLE task_settlement_reconciliations (
    settlement_reconciliation_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    provider varchar(64) NOT NULL,
    provider_settlement_reference varchar(255),
    period_start timestamptz NOT NULL,
    period_end timestamptz NOT NULL,
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    provider_reported_minor numeric(30,6),
    ledger_recorded_minor numeric(30,6) NOT NULL,
    difference_minor numeric(30,6),
    provider_result_state varchar(24) NOT NULL
        CHECK (provider_result_state IN ('CONFIRMED', 'FAILED', 'UNKNOWN')),
    reconciliation_state varchar(24) NOT NULL
        CHECK (reconciliation_state IN ('MATCHED', 'UNRECONCILED', 'UNKNOWN')),
    external_evidence_digest char(64)
        CHECK (external_evidence_digest IS NULL OR external_evidence_digest ~ '^[0-9a-f]{64}$'),
    evidence_verifier_actor_id varchar(128),
    request_digest char(64) NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    idempotency_key varchar(160) NOT NULL,
    recorded_by_actor_id varchar(128) NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, account_id, idempotency_key),
    CONSTRAINT task_settlement_period CHECK (period_end > period_start),
    CONSTRAINT task_settlement_matched_shape CHECK (
        reconciliation_state <> 'MATCHED' OR (
            provider_result_state = 'CONFIRMED'
            AND provider_reported_minor IS NOT NULL
            AND difference_minor = 0
            AND provider_settlement_reference IS NOT NULL
            AND external_evidence_digest IS NOT NULL
            AND evidence_verifier_actor_id IS NOT NULL
            AND evidence_verifier_actor_id <> recorded_by_actor_id
        )
    )
);

CREATE TRIGGER task_settlement_reconciliations_append_only
BEFORE UPDATE OR DELETE ON task_settlement_reconciliations
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

-- ---------------------------------------------------------------------------
-- 5. FORCE RLS and role checks
-- ---------------------------------------------------------------------------

DO $$
DECLARE v_table text;
BEGIN
    FOREACH v_table IN ARRAY ARRAY[
        'task_finops_feature_rollouts',
        'task_checkpoint_compatibility_decisions',
        'task_recovery_forks',
        'task_tenant_lifecycle_jobs',
        'task_tenant_task_creation_fences',
        'task_tenant_export_pages',
        'task_tenant_lifecycle_events',
        'task_tenant_resource_tombstones',
        'task_tenant_purge_items',
        'task_tenant_purge_receipts',
        'task_settlement_reconciliations'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', v_table);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', v_table);
        EXECUTE format(
            'CREATE POLICY %I ON %I ' ||
            'USING (elmos_mtf_context_matches(organization_id, account_id)) ' ||
            'WITH CHECK (elmos_mtf_context_matches(organization_id, account_id))',
            v_table || '_scope', v_table);
        EXECUTE format('REVOKE ALL ON %I FROM PUBLIC', v_table);
    END LOOP;
END;
$$;

-- Serialize account binding with the irreversible deletion boundary.  The
-- base enqueue first creates an unbound job and then binds account_id; the two
-- triggers cover both that update and any direct account-bound insert.
CREATE OR REPLACE FUNCTION elmos_mtf_guard_account_task_creation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
BEGIN
    IF NEW.account_id IS NULL THEN
        RETURN NEW;
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        NEW.organization_id, NEW.account_id, 'TENANT_TASK_CREATE_FENCE'
    )::text, 7717));
    IF EXISTS (
        SELECT 1
          FROM task_tenant_task_creation_fences fence
         WHERE fence.organization_id = NEW.organization_id
           AND fence.account_id = NEW.account_id
    ) THEN
        RAISE EXCEPTION 'ELMOS_MTF_ACCOUNT_TASK_CREATION_FENCED';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER execution_jobs_tenant_creation_fence_insert
BEFORE INSERT ON execution_jobs
FOR EACH ROW EXECUTE FUNCTION elmos_mtf_guard_account_task_creation();

CREATE TRIGGER execution_jobs_tenant_creation_fence_account_bind
BEFORE UPDATE OF account_id ON execution_jobs
FOR EACH ROW EXECUTE FUNCTION elmos_mtf_guard_account_task_creation();

CREATE OR REPLACE FUNCTION elmos_mtf_require_member_role(p_roles text[])
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE v_authorized boolean;
BEGIN
    PERFORM elmos_mtf_assert_bound_context();
    IF p_roles IS NULL OR cardinality(p_roles) < 1 THEN
        RAISE EXCEPTION 'ELMOS_MTF_AUTHORITY_POLICY_INVALID';
    END IF;
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
           AND membership.member_role = ANY (p_roles)
           AND identity.actor_id = current_setting('app.actor_id')
    ) INTO v_authorized;
    IF NOT v_authorized THEN
        RAISE EXCEPTION 'ELMOS_MTF_AUTHORITY_REQUIRED';
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- 6. Ordered feature rollout mutation
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_mtf_set_feature_rollout(
    p_environment varchar,
    p_feature_key varchar,
    p_rollout_stage varchar,
    p_exposure_percent smallint,
    p_expected_version bigint,
    p_idempotency_key varchar,
    p_request_digest varchar
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_existing task_finops_audit_events%ROWTYPE;
    v_current task_finops_feature_rollouts%ROWTYPE;
    v_old_rank integer := 0;
    v_new_rank integer;
    v_prerequisite_rank integer := 0;
    v_dependency varchar(96);
    v_version bigint;
BEGIN
    PERFORM elmos_mtf_require_member_role(ARRAY['OWNER', 'ADMIN']);
    IF p_environment NOT IN ('DEVELOPMENT', 'STAGING', 'PRODUCTION')
       OR p_feature_key NOT IN (
           'AUTHENTICATED_ACCOUNT_BINDING', 'ACCOUNT_CONCURRENCY_LIMIT',
           'DURABLE_WORKFLOW_START', 'CHECKPOINT_FORK_RECOVERY',
           'EXACT_USAGE_METERING', 'PAYMENT_SETTLEMENT_RECONCILIATION'
       )
       OR p_rollout_stage NOT IN ('OFF', 'SHADOW', 'CANARY', 'ON')
       OR (p_rollout_stage IN ('OFF', 'SHADOW') AND p_exposure_percent <> 0)
       OR (p_rollout_stage = 'CANARY' AND p_exposure_percent NOT BETWEEN 1 AND 99)
       OR (p_rollout_stage = 'ON' AND p_exposure_percent <> 100)
       OR p_expected_version < 0
       OR length(p_idempotency_key) NOT BETWEEN 1 AND 160
       OR p_request_digest !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'ELMOS_MTF_FEATURE_ROLLOUT_INVALID';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        current_setting('app.organization_id'), current_setting('app.account_id'),
        p_feature_key, p_environment
    )::text, 7711));

    SELECT * INTO v_existing
      FROM task_finops_audit_events
     WHERE organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
       AND action = 'FEATURE_ROLLOUT'
       AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.target_digest IS DISTINCT FROM p_request_digest::char(64) THEN
            RAISE EXCEPTION 'ELMOS_MTF_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN (v_existing.metadata ->> 'state_version')::bigint;
    END IF;

    SELECT * INTO v_current
      FROM task_finops_feature_rollouts
     WHERE organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
       AND environment = p_environment
       AND feature_key = p_feature_key
     FOR UPDATE;
    IF FOUND THEN
        v_old_rank := CASE v_current.rollout_stage
            WHEN 'OFF' THEN 0 WHEN 'SHADOW' THEN 1
            WHEN 'CANARY' THEN 2 ELSE 3 END;
        IF v_current.state_version <> p_expected_version THEN
            RAISE EXCEPTION 'ELMOS_MTF_FEATURE_ROLLOUT_VERSION_CONFLICT';
        END IF;
    ELSIF p_expected_version <> 0 THEN
        RAISE EXCEPTION 'ELMOS_MTF_FEATURE_ROLLOUT_VERSION_CONFLICT';
    END IF;

    v_new_rank := CASE p_rollout_stage
        WHEN 'OFF' THEN 0 WHEN 'SHADOW' THEN 1
        WHEN 'CANARY' THEN 2 ELSE 3 END;
    IF v_new_rank > v_old_rank + 1 THEN
        RAISE EXCEPTION 'ELMOS_MTF_FEATURE_ROLLOUT_STAGE_SKIPPED';
    END IF;
    IF p_environment = 'PRODUCTION' AND p_rollout_stage = 'ON' THEN
        RAISE EXCEPTION 'ELMOS_MTF_EXTERNAL_GATE_REQUIRED';
    END IF;

    v_dependency := CASE p_feature_key
        WHEN 'ACCOUNT_CONCURRENCY_LIMIT' THEN 'AUTHENTICATED_ACCOUNT_BINDING'
        WHEN 'DURABLE_WORKFLOW_START' THEN 'ACCOUNT_CONCURRENCY_LIMIT'
        WHEN 'CHECKPOINT_FORK_RECOVERY' THEN 'DURABLE_WORKFLOW_START'
        WHEN 'EXACT_USAGE_METERING' THEN 'CHECKPOINT_FORK_RECOVERY'
        WHEN 'PAYMENT_SETTLEMENT_RECONCILIATION' THEN 'EXACT_USAGE_METERING'
        ELSE NULL END;
    IF v_new_rank > v_old_rank AND v_dependency IS NOT NULL
       AND NOT EXISTS (
            SELECT 1 FROM task_finops_feature_rollouts dependency
             WHERE dependency.organization_id = current_setting('app.organization_id')
               AND dependency.account_id = current_setting('app.account_id')
               AND dependency.environment = p_environment
               AND dependency.feature_key = v_dependency
               AND dependency.rollout_stage = 'ON'
       ) THEN
        RAISE EXCEPTION 'ELMOS_MTF_FEATURE_ROLLOUT_DEPENDENCY_NOT_READY';
    END IF;
    IF v_new_rank < v_old_rank AND EXISTS (
        SELECT 1 FROM task_finops_feature_rollouts dependent
         WHERE dependent.organization_id = current_setting('app.organization_id')
           AND dependent.account_id = current_setting('app.account_id')
           AND dependent.environment = p_environment
           AND CASE dependent.feature_key
               WHEN 'AUTHENTICATED_ACCOUNT_BINDING' THEN 1
               WHEN 'ACCOUNT_CONCURRENCY_LIMIT' THEN 2
               WHEN 'DURABLE_WORKFLOW_START' THEN 3
               WHEN 'CHECKPOINT_FORK_RECOVERY' THEN 4
               WHEN 'EXACT_USAGE_METERING' THEN 5
               ELSE 6 END
               > CASE p_feature_key
                   WHEN 'AUTHENTICATED_ACCOUNT_BINDING' THEN 1
                   WHEN 'ACCOUNT_CONCURRENCY_LIMIT' THEN 2
                   WHEN 'DURABLE_WORKFLOW_START' THEN 3
                   WHEN 'CHECKPOINT_FORK_RECOVERY' THEN 4
                   WHEN 'EXACT_USAGE_METERING' THEN 5
                   ELSE 6 END
           AND CASE dependent.rollout_stage
               WHEN 'OFF' THEN 0 WHEN 'SHADOW' THEN 1
               WHEN 'CANARY' THEN 2 ELSE 3 END > v_new_rank
    ) THEN
        RAISE EXCEPTION 'ELMOS_MTF_FEATURE_ROLLOUT_DEPENDENT_ACTIVE';
    END IF;
    IF v_new_rank < v_old_rank AND EXISTS (
        SELECT 1 FROM task_finops_feature_rollouts downstream
         WHERE downstream.organization_id = current_setting('app.organization_id')
           AND downstream.account_id = current_setting('app.account_id')
           AND downstream.feature_key = p_feature_key
           AND CASE downstream.environment
               WHEN 'DEVELOPMENT' THEN 1 WHEN 'STAGING' THEN 2 ELSE 3 END
               > CASE p_environment
                   WHEN 'DEVELOPMENT' THEN 1 WHEN 'STAGING' THEN 2 ELSE 3 END
           AND CASE downstream.rollout_stage
               WHEN 'OFF' THEN 0 WHEN 'SHADOW' THEN 1
               WHEN 'CANARY' THEN 2 ELSE 3 END > v_new_rank
    ) THEN
        RAISE EXCEPTION 'ELMOS_MTF_FEATURE_ROLLOUT_DOWNSTREAM_ACTIVE';
    END IF;

    IF p_environment IN ('STAGING', 'PRODUCTION') THEN
        SELECT coalesce(max(CASE rollout_stage
            WHEN 'OFF' THEN 0 WHEN 'SHADOW' THEN 1
            WHEN 'CANARY' THEN 2 ELSE 3 END), 0)
          INTO v_prerequisite_rank
          FROM task_finops_feature_rollouts
         WHERE organization_id = current_setting('app.organization_id')
           AND account_id = current_setting('app.account_id')
           AND feature_key = p_feature_key
           AND environment = CASE p_environment
               WHEN 'STAGING' THEN 'DEVELOPMENT' ELSE 'STAGING' END;
        IF v_new_rank > 0 AND v_prerequisite_rank <> 3 THEN
            RAISE EXCEPTION 'ELMOS_MTF_FEATURE_ROLLOUT_PREREQUISITE_MISSING';
        END IF;
    END IF;

    v_version := coalesce(v_current.state_version, 0) + 1;
    INSERT INTO task_finops_feature_rollouts (
        organization_id, account_id, environment, feature_key, rollout_stage,
        exposure_percent, state_version, changed_by_actor_id
    ) VALUES (
        current_setting('app.organization_id'), current_setting('app.account_id'),
        p_environment, p_feature_key, p_rollout_stage, p_exposure_percent, v_version,
        current_setting('app.actor_id')
    ) ON CONFLICT (organization_id, account_id, environment, feature_key)
      DO UPDATE SET rollout_stage = excluded.rollout_stage,
                    exposure_percent = excluded.exposure_percent,
                    state_version = excluded.state_version,
                    changed_by_actor_id = excluded.changed_by_actor_id,
                    changed_at = now();

    INSERT INTO task_finops_audit_events (
        audit_event_id, organization_id, account_id, actor_id, request_id,
        action, idempotency_key, outcome, target_digest, metadata
    ) VALUES (
        'mtf-aud-' || md5(jsonb_build_array(
            current_setting('app.organization_id'), current_setting('app.account_id'),
            'FEATURE_ROLLOUT', p_idempotency_key
        )::text),
        current_setting('app.organization_id'), current_setting('app.account_id'),
        current_setting('app.actor_id'), current_setting('app.request_id'),
        'FEATURE_ROLLOUT', p_idempotency_key, 'SUCCESS', p_request_digest,
        jsonb_build_object('environment', p_environment, 'feature_key', p_feature_key,
            'rollout_stage', p_rollout_stage,
            'exposure_percent', p_exposure_percent,
            'state_version', v_version)
    );
    RETURN v_version;
END;
$$;

-- ---------------------------------------------------------------------------
-- 7. Compatibility decision and incompatible fork
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_mtf_record_checkpoint_compatibility(
    p_decision_id varchar,
    p_checkpoint_id varchar,
    p_decision_state varchar,
    p_fingerprint_digest varchar,
    p_reason_codes text[],
    p_evidence_digest varchar,
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
    v_checkpoint task_checkpoint_manifests%ROWTYPE;
    v_existing task_checkpoint_compatibility_decisions%ROWTYPE;
    v_expected_fingerprint varchar(64);
BEGIN
    PERFORM elmos_mtf_require_member_role(ARRAY['OWNER', 'ADMIN', 'MAINTAINER']);
    IF length(p_decision_id) NOT BETWEEN 1 AND 96
       OR p_decision_state NOT IN ('COMPATIBLE', 'INCOMPATIBLE')
       OR p_fingerprint_digest !~ '^[0-9a-f]{64}$'
       OR cardinality(p_reason_codes) NOT BETWEEN 1 AND 16
       OR p_evidence_digest !~ '^[0-9a-f]{64}$'
       OR length(p_signature_algorithm) NOT BETWEEN 1 AND 64
       OR length(p_signing_key_id) NOT BETWEEN 1 AND 255
       OR length(p_signature) NOT BETWEEN 1 AND 4096 THEN
        RAISE EXCEPTION 'ELMOS_MTF_CHECKPOINT_DECISION_INVALID';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        current_setting('app.organization_id'), current_setting('app.account_id'),
        'CHECKPOINT_COMPATIBILITY', p_decision_id
    )::text, 7718));
    SELECT * INTO v_existing FROM task_checkpoint_compatibility_decisions
     WHERE compatibility_decision_id = p_decision_id;
    IF FOUND THEN
        IF v_existing.checkpoint_id IS DISTINCT FROM p_checkpoint_id
           OR v_existing.decision_state IS DISTINCT FROM p_decision_state
           OR v_existing.fingerprint_digest IS DISTINCT FROM p_fingerprint_digest::char(64)
           OR v_existing.reason_codes IS DISTINCT FROM p_reason_codes
           OR v_existing.evidence_digest IS DISTINCT FROM p_evidence_digest::char(64) THEN
            RAISE EXCEPTION 'ELMOS_MTF_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.compatibility_decision_id;
    END IF;

    SELECT * INTO v_checkpoint FROM task_checkpoint_manifests
     WHERE checkpoint_id = p_checkpoint_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id');
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_CHECKPOINT_UNKNOWN'; END IF;
    IF v_checkpoint.created_by_actor_id = current_setting('app.actor_id') THEN
        RAISE EXCEPTION 'ELMOS_MTF_INDEPENDENT_VERIFIER_REQUIRED';
    END IF;
    v_expected_fingerprint := encode(sha256(convert_to(jsonb_build_array(
        v_checkpoint.input_manifest_digest::varchar,
        v_checkpoint.repository_revision,
        v_checkpoint.toolchain_digest::varchar,
        v_checkpoint.model_digest::varchar,
        v_checkpoint.schema_version
    )::text, 'UTF8')), 'hex');
    IF v_expected_fingerprint <> p_fingerprint_digest THEN
        RAISE EXCEPTION 'ELMOS_MTF_CHECKPOINT_FINGERPRINT_MISMATCH';
    END IF;

    INSERT INTO task_checkpoint_compatibility_decisions (
        compatibility_decision_id, organization_id, account_id, checkpoint_id,
        decision_state, fingerprint_digest, reason_codes, evidence_digest,
        signature_algorithm, signing_key_id, signature, verifier_actor_id
    ) VALUES (
        p_decision_id, v_checkpoint.organization_id, v_checkpoint.account_id,
        v_checkpoint.checkpoint_id, p_decision_state, p_fingerprint_digest,
        p_reason_codes, p_evidence_digest, p_signature_algorithm,
        p_signing_key_id, p_signature, current_setting('app.actor_id')
    );
    RETURN p_decision_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_fork_incompatible_recovery(
    p_recovery_fork_id varchar,
    p_parent_job_id varchar,
    p_checkpoint_id varchar,
    p_compatibility_decision_id varchar,
    p_child_job_id varchar,
    p_idempotency_key varchar,
    p_request_digest varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_existing task_recovery_forks%ROWTYPE;
    v_parent execution_jobs%ROWTYPE;
    v_decision task_checkpoint_compatibility_decisions%ROWTYPE;
    v_child_payload jsonb;
    v_child_digest varchar(64);
    v_child_id varchar(96);
BEGIN
    PERFORM elmos_mtf_require_member_role(ARRAY['OWNER', 'ADMIN', 'MAINTAINER']);
    IF length(p_recovery_fork_id) NOT BETWEEN 1 AND 96
       OR length(p_child_job_id) NOT BETWEEN 1 AND 96
       OR length(p_idempotency_key) NOT BETWEEN 1 AND 140
       OR p_request_digest !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'ELMOS_MTF_RECOVERY_FORK_INVALID';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        current_setting('app.organization_id'), current_setting('app.account_id'),
        'RECOVERY_FORK_IDEMPOTENCY', p_idempotency_key
    )::text, 7719));
    SELECT * INTO v_existing FROM task_recovery_forks
     WHERE organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
       AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.recovery_fork_id IS DISTINCT FROM p_recovery_fork_id
           OR v_existing.parent_job_id IS DISTINCT FROM p_parent_job_id
           OR v_existing.checkpoint_id IS DISTINCT FROM p_checkpoint_id
           OR v_existing.compatibility_decision_id IS DISTINCT FROM p_compatibility_decision_id
           OR v_existing.child_job_id IS DISTINCT FROM p_child_job_id
           OR v_existing.request_digest IS DISTINCT FROM p_request_digest::char(64) THEN
            RAISE EXCEPTION 'ELMOS_MTF_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.child_job_id;
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        current_setting('app.organization_id'), current_setting('app.account_id'),
        p_parent_job_id, 'RECOVERY_FORK'
    )::text, 7712));
    SELECT * INTO v_parent FROM execution_jobs
     WHERE job_id = p_parent_job_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_TASK_UNKNOWN'; END IF;
    IF v_parent.status NOT IN ('PARTIAL', 'FAILED', 'LOST', 'UNKNOWN_RESULT', 'RECONCILING')
       OR v_parent.workload_class IS NULL OR v_parent.resource_units IS NULL THEN
        RAISE EXCEPTION 'ELMOS_MTF_RECOVERY_FORK_NOT_ALLOWED';
    END IF;
    SELECT * INTO v_decision FROM task_checkpoint_compatibility_decisions
     WHERE compatibility_decision_id = p_compatibility_decision_id
       AND checkpoint_id = p_checkpoint_id
       AND organization_id = v_parent.organization_id
       AND account_id = v_parent.account_id;
    IF NOT FOUND OR v_decision.decision_state <> 'INCOMPATIBLE' THEN
        RAISE EXCEPTION 'ELMOS_MTF_INCOMPATIBLE_DECISION_REQUIRED';
    END IF;
    IF v_decision.verifier_actor_id = current_setting('app.actor_id') THEN
        RAISE EXCEPTION 'ELMOS_MTF_EXECUTOR_VERIFIER_SEPARATION_REQUIRED';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM task_checkpoint_manifests checkpoint
         WHERE checkpoint.checkpoint_id = p_checkpoint_id
           AND checkpoint.job_id = v_parent.job_id
           AND checkpoint.run_number = v_parent.workflow_run_number
    ) THEN
        RAISE EXCEPTION 'ELMOS_MTF_CHECKPOINT_RUN_MISMATCH';
    END IF;

    v_child_payload := v_parent.request_payload || jsonb_build_object(
        'recovery', jsonb_build_object(
            'parent_job_id', v_parent.job_id,
            'parent_run_number', v_parent.workflow_run_number,
            'checkpoint_id', p_checkpoint_id,
            'compatibility_decision_id', p_compatibility_decision_id,
            'mode', 'FORK_INCOMPATIBLE'
        )
    );
    v_child_digest := encode(sha256(convert_to(v_child_payload::text, 'UTF8')), 'hex');
    v_child_id := elmos_mtf_enqueue_execution_job(
        p_child_job_id, v_parent.organization_id, v_parent.account_id,
        current_setting('app.actor_id'), v_parent.business_line, v_parent.job_kind,
        'fork:' || p_idempotency_key, v_child_digest, v_child_payload,
        v_parent.required_capability, v_parent.runner_image, v_parent.priority,
        v_parent.budget_wall_seconds, v_parent.max_attempts,
        current_setting('app.request_id'), v_parent.workload_class,
        v_parent.resource_units
    );

    INSERT INTO task_recovery_forks (
        recovery_fork_id, organization_id, account_id, parent_job_id,
        parent_run_number, checkpoint_id, compatibility_decision_id,
        child_job_id, child_run_number, request_digest, idempotency_key,
        requested_by_actor_id
    ) VALUES (
        p_recovery_fork_id, v_parent.organization_id, v_parent.account_id,
        v_parent.job_id, v_parent.workflow_run_number, p_checkpoint_id,
        p_compatibility_decision_id, v_child_id, 1, p_request_digest,
        p_idempotency_key, current_setting('app.actor_id')
    );
    INSERT INTO task_finops_audit_events (
        audit_event_id, organization_id, account_id, job_id, actor_id, request_id,
        action, idempotency_key, outcome, target_digest, metadata
    ) VALUES (
        'mtf-aud-' || md5(jsonb_build_array(v_parent.organization_id,
            v_parent.account_id, 'FORK_RECOVERY', p_idempotency_key)::text),
        v_parent.organization_id, v_parent.account_id, v_parent.job_id,
        current_setting('app.actor_id'), current_setting('app.request_id'),
        'FORK_RECOVERY', p_idempotency_key, 'SUCCESS', p_request_digest,
        jsonb_build_object('child_job_id', v_child_id,
            'compatibility_decision_id', p_compatibility_decision_id)
    );
    RETURN v_child_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- 8. Tenant lifecycle request, checkpoint and provider receipt
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_mtf_request_tenant_lifecycle(
    p_lifecycle_job_id varchar,
    p_operation_kind varchar,
    p_export_format varchar,
    p_retention_cutoff timestamptz,
    p_idempotency_key varchar,
    p_request_digest varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_existing task_tenant_lifecycle_jobs%ROWTYPE;
    v_state varchar(24) := 'REQUESTED';
    v_failure varchar(96);
BEGIN
    PERFORM elmos_mtf_require_member_role(ARRAY['OWNER', 'ADMIN']);
    IF p_lifecycle_job_id IS NULL
       OR length(p_lifecycle_job_id) NOT BETWEEN 1 AND 96
       OR p_operation_kind IS NULL
       OR p_operation_kind NOT IN ('EXPORT', 'DELETE')
       OR p_export_format IS NULL
       OR p_export_format NOT IN ('JSON', 'CSV')
       OR p_retention_cutoff IS NULL OR p_retention_cutoff > now()
       OR p_idempotency_key IS NULL
       OR length(p_idempotency_key) NOT BETWEEN 1 AND 160
       OR p_request_digest IS NULL
       OR p_request_digest !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'ELMOS_MTF_LIFECYCLE_REQUEST_INVALID';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        current_setting('app.organization_id'), current_setting('app.account_id'),
        'TENANT_LIFECYCLE_REQUEST', p_idempotency_key
    )::text, 7714));
    SELECT * INTO v_existing FROM task_tenant_lifecycle_jobs
     WHERE organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
       AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.lifecycle_job_id IS DISTINCT FROM p_lifecycle_job_id
           OR v_existing.operation_kind IS DISTINCT FROM p_operation_kind
           OR v_existing.export_format IS DISTINCT FROM p_export_format
           OR v_existing.retention_cutoff IS DISTINCT FROM p_retention_cutoff
           OR v_existing.request_digest IS DISTINCT FROM p_request_digest::char(64) THEN
            RAISE EXCEPTION 'ELMOS_MTF_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.lifecycle_job_id;
    END IF;

    IF p_operation_kind = 'DELETE' AND EXISTS (
        SELECT 1
          FROM execution_jobs job
         WHERE job.organization_id = current_setting('app.organization_id')
           AND job.account_id IS NULL
           AND job.tenant_tombstoned_at IS NULL
    ) THEN
        v_state := 'BLOCKED';
        v_failure := 'ELMOS_MTF_RESOURCE_ACCOUNT_BINDING_UNKNOWN';
    ELSIF p_operation_kind = 'DELETE' AND EXISTS (
        SELECT 1
          FROM job_artifacts artifact
          JOIN execution_jobs job ON job.job_id = artifact.job_id
         WHERE artifact.organization_id = current_setting('app.organization_id')
           AND job.organization_id = current_setting('app.organization_id')
           AND job.account_id = current_setting('app.account_id')
           AND artifact.deleted_at IS NULL
           AND (artifact.legal_hold OR artifact.retention_class = 'LEGAL_HOLD')
    ) THEN
        v_state := 'BLOCKED';
        v_failure := 'ELMOS_MTF_LEGAL_HOLD_ACTIVE';
    ELSIF p_operation_kind = 'DELETE' AND EXISTS (
        SELECT 1
          FROM job_artifacts artifact
          JOIN execution_jobs job ON job.job_id = artifact.job_id
         WHERE artifact.organization_id = current_setting('app.organization_id')
           AND job.organization_id = current_setting('app.organization_id')
           AND job.account_id = current_setting('app.account_id')
           AND artifact.deleted_at IS NULL
           AND NOT artifact.legal_hold
           AND artifact.retention_class <> 'LEGAL_HOLD'
           AND (artifact.expires_at IS NULL OR artifact.expires_at > now())
    ) THEN
        v_state := 'BLOCKED';
        v_failure := 'ELMOS_MTF_RETENTION_ACTIVE_OR_UNKNOWN';
    END IF;

    INSERT INTO task_tenant_lifecycle_jobs (
        lifecycle_job_id, organization_id, account_id, operation_kind,
        export_format, operation_state, retention_cutoff, failure_code,
        request_digest, idempotency_key, requested_by_actor_id
    ) VALUES (
        p_lifecycle_job_id, current_setting('app.organization_id'),
        current_setting('app.account_id'), p_operation_kind, p_export_format,
        v_state, p_retention_cutoff, v_failure, p_request_digest,
        p_idempotency_key, current_setting('app.actor_id')
    );
    INSERT INTO task_tenant_lifecycle_events (
        lifecycle_event_id, organization_id, account_id, lifecycle_job_id,
        event_sequence, to_state, exported_row_count, exported_byte_count,
        provider_result_state, failure_code, request_digest, idempotency_key, actor_id
    ) VALUES (
        'mtf-life-' || md5(jsonb_build_array(p_lifecycle_job_id, 1)::text),
        current_setting('app.organization_id'), current_setting('app.account_id'),
        p_lifecycle_job_id, 1, v_state, 0, 0, 'NOT_RUN', v_failure,
        p_request_digest, p_idempotency_key, current_setting('app.actor_id')
    );
    RETURN p_lifecycle_job_id;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_checkpoint_tenant_export_page(
    p_lifecycle_job_id varchar,
    p_page_number bigint,
    p_cursor_digest varchar,
    p_row_count bigint,
    p_byte_count bigint,
    p_cumulative_row_count bigint,
    p_cumulative_byte_count bigint,
    p_terminal boolean,
    p_page_digest varchar,
    p_expected_version bigint,
    p_idempotency_key varchar,
    p_request_digest varchar
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_job task_tenant_lifecycle_jobs%ROWTYPE;
    v_previous task_tenant_export_pages%ROWTYPE;
    v_existing task_tenant_export_pages%ROWTYPE;
    v_has_previous boolean;
    v_chain_digest varchar(64);
    v_manifest_digest varchar(64);
    v_version bigint;
BEGIN
    PERFORM elmos_mtf_require_member_role(ARRAY['OWNER', 'ADMIN']);
    IF p_lifecycle_job_id IS NULL
       OR length(p_lifecycle_job_id) NOT BETWEEN 1 AND 96
       OR p_page_number IS NULL OR p_page_number < 1
       OR p_cursor_digest IS NULL OR p_cursor_digest !~ '^[0-9a-f]{64}$'
       OR p_row_count IS NULL OR p_row_count < 0
       OR p_byte_count IS NULL OR p_byte_count < 0
       OR p_cumulative_row_count IS NULL
       OR p_cumulative_row_count < p_row_count
       OR p_cumulative_byte_count IS NULL
       OR p_cumulative_byte_count < p_byte_count
       OR p_terminal IS NULL
       OR p_page_digest IS NULL OR p_page_digest !~ '^[0-9a-f]{64}$'
       OR p_expected_version IS NULL OR p_expected_version < 1
       OR p_expected_version >= 9223372036854775807
       OR p_idempotency_key IS NULL
       OR length(p_idempotency_key) NOT BETWEEN 1 AND 160
       OR p_request_digest IS NULL
       OR p_request_digest !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'ELMOS_MTF_EXPORT_PAGE_INVALID';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        current_setting('app.organization_id'), current_setting('app.account_id'),
        'TENANT_EXPORT_PAGE', p_idempotency_key
    )::text, 7715));
    SELECT * INTO v_existing
      FROM task_tenant_export_pages
     WHERE organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
       AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.lifecycle_job_id IS DISTINCT FROM p_lifecycle_job_id
           OR v_existing.page_number IS DISTINCT FROM p_page_number
           OR v_existing.cursor_digest IS DISTINCT FROM p_cursor_digest::char(64)
           OR v_existing.row_count IS DISTINCT FROM p_row_count
           OR v_existing.byte_count IS DISTINCT FROM p_byte_count
           OR v_existing.cumulative_row_count IS DISTINCT FROM p_cumulative_row_count
           OR v_existing.cumulative_byte_count IS DISTINCT FROM p_cumulative_byte_count
           OR v_existing.terminal IS DISTINCT FROM p_terminal
           OR v_existing.page_digest IS DISTINCT FROM p_page_digest::char(64)
           OR v_existing.expected_state_version IS DISTINCT FROM p_expected_version
           OR v_existing.request_digest IS DISTINCT FROM p_request_digest::char(64) THEN
            RAISE EXCEPTION 'ELMOS_MTF_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.expected_state_version + 1;
    END IF;

    SELECT * INTO v_job
      FROM task_tenant_lifecycle_jobs
     WHERE lifecycle_job_id = p_lifecycle_job_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_MTF_LIFECYCLE_JOB_UNKNOWN';
    END IF;
    IF v_job.state_version <> p_expected_version THEN
        RAISE EXCEPTION 'ELMOS_MTF_LIFECYCLE_VERSION_CONFLICT';
    END IF;
    IF v_job.operation_state <> 'EXPORTING'
       OR v_job.provider_result_state IN ('FAILED', 'UNKNOWN')
       OR v_job.manifest_digest IS NOT NULL THEN
        RAISE EXCEPTION 'ELMOS_MTF_EXPORT_PAGE_NOT_ALLOWED';
    END IF;

    SELECT * INTO v_previous
      FROM task_tenant_export_pages
     WHERE lifecycle_job_id = v_job.lifecycle_job_id
       AND organization_id = v_job.organization_id
       AND account_id = v_job.account_id
     ORDER BY page_number DESC
     LIMIT 1;
    v_has_previous := FOUND;

    IF NOT v_has_previous THEN
        IF p_page_number <> 1
           OR p_cumulative_row_count <> p_row_count
           OR p_cumulative_byte_count <> p_byte_count THEN
            RAISE EXCEPTION 'ELMOS_MTF_EXPORT_PAGE_SEQUENCE_INVALID';
        END IF;
    ELSE
        IF v_previous.terminal THEN
            RAISE EXCEPTION 'ELMOS_MTF_EXPORT_PAGE_ALREADY_TERMINAL';
        END IF;
        IF p_page_number::numeric <> v_previous.page_number::numeric + 1
           OR p_cumulative_row_count::numeric
                <> v_previous.cumulative_row_count::numeric + p_row_count::numeric
           OR p_cumulative_byte_count::numeric
                <> v_previous.cumulative_byte_count::numeric + p_byte_count::numeric THEN
            RAISE EXCEPTION 'ELMOS_MTF_EXPORT_PAGE_SEQUENCE_INVALID';
        END IF;
        IF NOT p_terminal
           AND p_cursor_digest::char(64) = v_previous.cursor_digest THEN
            RAISE EXCEPTION 'ELMOS_MTF_EXPORT_CURSOR_DID_NOT_ADVANCE';
        END IF;
    END IF;

    v_chain_digest := encode(sha256(convert_to(jsonb_build_array(
        'ELMOS_TENANT_EXPORT_PAGE_V1',
        v_job.organization_id,
        v_job.account_id,
        v_job.lifecycle_job_id,
        p_page_number,
        CASE WHEN v_has_previous
            THEN v_previous.checkpoint_chain_digest::varchar
            ELSE repeat('0', 64) END,
        p_cursor_digest,
        p_row_count,
        p_byte_count,
        p_cumulative_row_count,
        p_cumulative_byte_count,
        p_terminal,
        p_page_digest
    )::text, 'UTF8')), 'hex');
    v_manifest_digest := CASE WHEN p_terminal THEN v_chain_digest ELSE NULL END;
    v_version := v_job.state_version + 1;

    INSERT INTO task_tenant_export_pages (
        export_page_id, organization_id, account_id, lifecycle_job_id,
        page_number, cursor_digest, row_count, byte_count,
        cumulative_row_count, cumulative_byte_count, terminal, page_digest,
        checkpoint_chain_digest, manifest_digest, expected_state_version,
        request_digest, idempotency_key, actor_id
    ) VALUES (
        'mtf-export-page-' || md5(jsonb_build_array(
            v_job.lifecycle_job_id, p_page_number)::text),
        v_job.organization_id, v_job.account_id, v_job.lifecycle_job_id,
        p_page_number, p_cursor_digest, p_row_count, p_byte_count,
        p_cumulative_row_count, p_cumulative_byte_count, p_terminal,
        p_page_digest, v_chain_digest, v_manifest_digest, p_expected_version,
        p_request_digest, p_idempotency_key, current_setting('app.actor_id')
    );

    UPDATE task_tenant_lifecycle_jobs
       SET page_cursor = p_cursor_digest,
           manifest_digest = v_manifest_digest,
           exported_row_count = p_cumulative_row_count,
           exported_byte_count = p_cumulative_byte_count,
           state_version = v_version
     WHERE lifecycle_job_id = v_job.lifecycle_job_id
       AND organization_id = v_job.organization_id
       AND account_id = v_job.account_id
       AND state_version = p_expected_version;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_MTF_LIFECYCLE_VERSION_CONFLICT';
    END IF;

    INSERT INTO task_tenant_lifecycle_events (
        lifecycle_event_id, organization_id, account_id, lifecycle_job_id,
        event_sequence, from_state, to_state, page_cursor, manifest_digest,
        exported_row_count, exported_byte_count, provider_result_state,
        request_digest, idempotency_key, actor_id
    ) VALUES (
        'mtf-life-' || md5(jsonb_build_array(
            v_job.lifecycle_job_id, v_version)::text),
        v_job.organization_id, v_job.account_id, v_job.lifecycle_job_id,
        v_version, 'EXPORTING', 'EXPORTING', p_cursor_digest,
        v_manifest_digest, p_cumulative_row_count, p_cumulative_byte_count,
        v_job.provider_result_state, p_request_digest, p_idempotency_key,
        current_setting('app.actor_id')
    );
    RETURN v_version;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_advance_tenant_lifecycle(
    p_lifecycle_job_id varchar,
    p_expected_version bigint,
    p_next_state varchar,
    p_page_cursor varchar,
    p_manifest_digest varchar,
    p_exported_row_count bigint,
    p_exported_byte_count bigint,
    p_provider_result_state varchar,
    p_failure_code varchar,
    p_idempotency_key varchar,
    p_request_digest varchar
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_job task_tenant_lifecycle_jobs%ROWTYPE;
    v_existing task_tenant_lifecycle_events%ROWTYPE;
    v_terminal_page task_tenant_export_pages%ROWTYPE;
    v_unknown_origin varchar(24);
    v_allowed boolean := false;
    v_version bigint;
BEGIN
    PERFORM elmos_mtf_require_member_role(ARRAY['OWNER', 'ADMIN']);
    IF p_lifecycle_job_id IS NULL
       OR length(p_lifecycle_job_id) NOT BETWEEN 1 AND 96
       OR p_next_state IS NULL
       OR p_next_state NOT IN (
            'REQUESTED', 'EXPORTING', 'TOMBSTONED', 'PURGE_PENDING',
            'RECONCILING', 'COMPLETED', 'UNKNOWN_RESULT', 'FAILED'
       )
       OR p_expected_version IS NULL OR p_expected_version < 1
       OR p_expected_version >= 9223372036854775807
       OR p_exported_row_count IS NULL OR p_exported_row_count < 0
       OR p_exported_byte_count IS NULL OR p_exported_byte_count < 0
       OR p_provider_result_state IS NULL
       OR p_provider_result_state NOT IN (
            'NOT_RUN', 'PENDING', 'CONFIRMED', 'FAILED', 'UNKNOWN'
       )
       OR p_idempotency_key IS NULL
       OR length(p_idempotency_key) NOT BETWEEN 1 AND 160
       OR p_request_digest IS NULL
       OR p_request_digest !~ '^[0-9a-f]{64}$'
       OR (p_page_cursor IS NOT NULL AND p_page_cursor !~ '^[0-9a-f]{64}$')
       OR (p_failure_code IS NOT NULL
           AND length(p_failure_code) NOT BETWEEN 1 AND 96)
       OR (p_manifest_digest IS NOT NULL AND p_manifest_digest !~ '^[0-9a-f]{64}$') THEN
        RAISE EXCEPTION 'ELMOS_MTF_LIFECYCLE_TRANSITION_INVALID';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        current_setting('app.organization_id'), current_setting('app.account_id'),
        'TENANT_LIFECYCLE_ADVANCE', p_idempotency_key
    )::text, 7716));
    IF p_next_state = 'TOMBSTONED' THEN
        PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
            current_setting('app.organization_id'), current_setting('app.account_id'),
            'TENANT_TASK_CREATE_FENCE'
        )::text, 7717));
    END IF;
    SELECT * INTO v_existing FROM task_tenant_lifecycle_events
     WHERE organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
       AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.lifecycle_job_id IS DISTINCT FROM p_lifecycle_job_id
           OR v_existing.event_sequence IS DISTINCT FROM p_expected_version + 1
           OR v_existing.to_state IS DISTINCT FROM p_next_state
           OR v_existing.page_cursor IS DISTINCT FROM p_page_cursor
           OR v_existing.manifest_digest IS DISTINCT FROM p_manifest_digest::char(64)
           OR v_existing.exported_row_count IS DISTINCT FROM p_exported_row_count
           OR v_existing.exported_byte_count IS DISTINCT FROM p_exported_byte_count
           OR v_existing.provider_result_state IS DISTINCT FROM p_provider_result_state
           OR v_existing.failure_code IS DISTINCT FROM p_failure_code
           OR v_existing.request_digest IS DISTINCT FROM p_request_digest::char(64) THEN
            RAISE EXCEPTION 'ELMOS_MTF_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.event_sequence;
    END IF;

    SELECT * INTO v_job FROM task_tenant_lifecycle_jobs
     WHERE lifecycle_job_id = p_lifecycle_job_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_LIFECYCLE_JOB_UNKNOWN'; END IF;
    IF v_job.state_version <> p_expected_version THEN
        RAISE EXCEPTION 'ELMOS_MTF_LIFECYCLE_VERSION_CONFLICT';
    END IF;
    IF v_job.operation_state IN ('COMPLETED', 'FAILED') THEN
        RAISE EXCEPTION 'ELMOS_MTF_LIFECYCLE_TERMINAL';
    END IF;
    IF p_provider_result_state = 'UNKNOWN'
       AND p_next_state NOT IN ('UNKNOWN_RESULT', 'RECONCILING') THEN
        RAISE EXCEPTION 'ELMOS_MTF_PROVIDER_RESULT_UNKNOWN';
    END IF;
    IF p_next_state = 'UNKNOWN_RESULT'
       AND p_provider_result_state <> 'UNKNOWN' THEN
        RAISE EXCEPTION 'ELMOS_MTF_UNKNOWN_RESULT_REQUIRED';
    END IF;
    IF p_provider_result_state = 'FAILED' AND p_next_state <> 'FAILED' THEN
        RAISE EXCEPTION 'ELMOS_MTF_PROVIDER_RESULT_FAILED';
    END IF;
    IF p_next_state IN ('UNKNOWN_RESULT', 'RECONCILING', 'FAILED')
       AND p_failure_code IS NULL THEN
        RAISE EXCEPTION 'ELMOS_MTF_LIFECYCLE_FAILURE_CODE_REQUIRED';
    END IF;
    IF p_next_state NOT IN ('UNKNOWN_RESULT', 'RECONCILING', 'FAILED')
       AND p_failure_code IS NOT NULL THEN
        RAISE EXCEPTION 'ELMOS_MTF_LIFECYCLE_UNEXPECTED_FAILURE_CODE';
    END IF;
    IF p_page_cursor IS DISTINCT FROM v_job.page_cursor
       OR p_manifest_digest::char(64) IS DISTINCT FROM v_job.manifest_digest
       OR p_exported_row_count IS DISTINCT FROM v_job.exported_row_count
       OR p_exported_byte_count IS DISTINCT FROM v_job.exported_byte_count THEN
        RAISE EXCEPTION 'ELMOS_MTF_EXPORT_PROGRESS_NOT_CHECKPOINTED';
    END IF;
    IF v_job.operation_state = 'RECONCILING' THEN
        SELECT event.from_state INTO v_unknown_origin
          FROM task_tenant_lifecycle_events event
         WHERE event.lifecycle_job_id = v_job.lifecycle_job_id
           AND event.organization_id = v_job.organization_id
           AND event.account_id = v_job.account_id
           AND event.to_state = 'UNKNOWN_RESULT'
         ORDER BY event.event_sequence DESC
         LIMIT 1;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'ELMOS_MTF_RECONCILIATION_ORIGIN_UNKNOWN';
        END IF;
    END IF;

    v_allowed := CASE
        WHEN v_job.operation_state = 'REQUESTED' AND p_next_state = 'EXPORTING' THEN true
        WHEN v_job.operation_state = 'BLOCKED'
             AND v_job.operation_kind = 'DELETE'
             AND p_next_state = 'REQUESTED' THEN true
        WHEN v_job.operation_state = 'EXPORTING' AND v_job.operation_kind = 'EXPORT'
             AND p_next_state = 'COMPLETED' THEN true
        WHEN v_job.operation_state = 'EXPORTING' AND v_job.operation_kind = 'DELETE'
             AND p_next_state = 'TOMBSTONED' THEN true
        WHEN v_job.operation_state = 'TOMBSTONED' AND p_next_state = 'PURGE_PENDING' THEN true
        WHEN v_job.operation_state = 'PURGE_PENDING' AND p_next_state = 'COMPLETED' THEN true
        WHEN v_job.operation_state = 'UNKNOWN_RESULT'
             AND p_next_state = 'RECONCILING' THEN true
        WHEN v_job.operation_state = 'RECONCILING'
             AND v_unknown_origin IN ('REQUESTED', 'EXPORTING')
             AND p_next_state = 'EXPORTING' THEN true
        WHEN v_job.operation_state = 'RECONCILING'
             AND v_job.operation_kind = 'DELETE'
             AND v_unknown_origin IN ('TOMBSTONED', 'PURGE_PENDING')
             AND p_next_state = 'PURGE_PENDING' THEN true
        WHEN v_job.operation_state IN ('REQUESTED', 'EXPORTING', 'TOMBSTONED', 'PURGE_PENDING')
             AND p_next_state IN ('UNKNOWN_RESULT', 'FAILED') THEN true
        WHEN v_job.operation_state = 'RECONCILING' AND p_next_state = 'FAILED' THEN true
        ELSE false END;
    IF NOT v_allowed THEN RAISE EXCEPTION 'ELMOS_MTF_ILLEGAL_TRANSITION'; END IF;

    IF v_job.operation_state = 'BLOCKED'
       AND p_next_state = 'REQUESTED'
       AND p_provider_result_state <> 'NOT_RUN' THEN
        RAISE EXCEPTION 'ELMOS_MTF_BLOCKED_RECOVERY_PROVIDER_STATE_INVALID';
    END IF;
    IF v_job.operation_state = 'UNKNOWN_RESULT'
       AND p_next_state = 'RECONCILING'
       AND p_provider_result_state <> 'UNKNOWN' THEN
        RAISE EXCEPTION 'ELMOS_MTF_UNKNOWN_RESULT_UNRESOLVED';
    END IF;
    IF v_job.operation_state = 'RECONCILING'
       AND p_next_state IN ('EXPORTING', 'PURGE_PENDING')
       AND p_provider_result_state <> 'CONFIRMED' THEN
        RAISE EXCEPTION 'ELMOS_MTF_UNKNOWN_RESULT_UNRESOLVED';
    END IF;

    IF p_next_state IN ('TOMBSTONED', 'COMPLETED') THEN
        SELECT * INTO v_terminal_page
          FROM task_tenant_export_pages page
         WHERE page.lifecycle_job_id = v_job.lifecycle_job_id
           AND page.organization_id = v_job.organization_id
           AND page.account_id = v_job.account_id
         ORDER BY page.page_number DESC
         LIMIT 1;
        IF NOT FOUND
           OR NOT v_terminal_page.terminal
           OR v_terminal_page.cursor_digest::varchar
                IS DISTINCT FROM v_job.page_cursor
           OR v_terminal_page.manifest_digest
                IS DISTINCT FROM v_job.manifest_digest
           OR v_terminal_page.manifest_digest
                IS DISTINCT FROM p_manifest_digest::char(64)
           OR v_terminal_page.cumulative_row_count
                IS DISTINCT FROM v_job.exported_row_count
           OR v_terminal_page.cumulative_row_count
                IS DISTINCT FROM p_exported_row_count
           OR v_terminal_page.cumulative_byte_count
                IS DISTINCT FROM v_job.exported_byte_count
           OR v_terminal_page.cumulative_byte_count
                IS DISTINCT FROM p_exported_byte_count
           OR p_provider_result_state <> 'CONFIRMED' THEN
            RAISE EXCEPTION 'ELMOS_MTF_EXPORT_TERMINAL_CHECKPOINT_REQUIRED';
        END IF;
    END IF;
    IF (p_next_state = 'TOMBSTONED'
            OR (v_job.operation_state = 'BLOCKED' AND p_next_state = 'REQUESTED'))
       AND EXISTS (
            SELECT 1 FROM execution_jobs job
             WHERE job.organization_id = v_job.organization_id
               AND job.account_id IS NULL
               AND job.tenant_tombstoned_at IS NULL
       ) THEN
        RAISE EXCEPTION 'ELMOS_MTF_RESOURCE_ACCOUNT_BINDING_UNKNOWN';
    END IF;
    IF (p_next_state = 'TOMBSTONED'
            OR (v_job.operation_state = 'BLOCKED' AND p_next_state = 'REQUESTED'))
       AND EXISTS (
        SELECT 1
          FROM job_artifacts artifact
          JOIN execution_jobs job ON job.job_id = artifact.job_id
         WHERE artifact.organization_id = v_job.organization_id
           AND job.organization_id = v_job.organization_id
           AND job.account_id = v_job.account_id
           AND artifact.deleted_at IS NULL
           AND (artifact.legal_hold OR artifact.retention_class = 'LEGAL_HOLD')
    ) THEN
        RAISE EXCEPTION 'ELMOS_MTF_LEGAL_HOLD_ACTIVE';
    END IF;
    IF (p_next_state = 'TOMBSTONED'
            OR (v_job.operation_state = 'BLOCKED' AND p_next_state = 'REQUESTED'))
       AND EXISTS (
        SELECT 1
          FROM job_artifacts artifact
          JOIN execution_jobs job ON job.job_id = artifact.job_id
         WHERE artifact.organization_id = v_job.organization_id
           AND job.organization_id = v_job.organization_id
           AND job.account_id = v_job.account_id
           AND artifact.deleted_at IS NULL
           AND NOT artifact.legal_hold
           AND artifact.retention_class <> 'LEGAL_HOLD'
           AND (artifact.expires_at IS NULL OR artifact.expires_at > now())
    ) THEN
        RAISE EXCEPTION 'ELMOS_MTF_RETENTION_ACTIVE_OR_UNKNOWN';
    END IF;
    IF (p_next_state = 'TOMBSTONED'
            OR (v_job.operation_state = 'BLOCKED' AND p_next_state = 'REQUESTED'))
       AND EXISTS (
        SELECT 1 FROM execution_jobs job
         WHERE job.organization_id = v_job.organization_id
           AND job.account_id = v_job.account_id
           AND job.tenant_tombstoned_at IS NULL
           AND job.status IN (
                'QUEUED', 'CLAIMED', 'RUNNING', 'PAUSED',
                'UNKNOWN_RESULT', 'RECONCILING'
           )
    ) THEN
        RAISE EXCEPTION 'ELMOS_MTF_ACTIVE_OR_UNKNOWN_TASKS_BLOCK_DELETION';
    END IF;
    IF p_next_state = 'COMPLETED' AND v_job.operation_kind = 'DELETE'
       AND EXISTS (
            SELECT 1 FROM task_tenant_purge_items item
             WHERE item.lifecycle_job_id = v_job.lifecycle_job_id
               AND item.organization_id = v_job.organization_id
               AND item.account_id = v_job.account_id
               AND item.purge_state <> 'CONFIRMED'
       ) THEN
        RAISE EXCEPTION 'ELMOS_MTF_PURGE_RECONCILIATION_REQUIRED';
    END IF;

    v_version := v_job.state_version + 1;
    UPDATE task_tenant_lifecycle_jobs
       SET operation_state = p_next_state,
           page_cursor = p_page_cursor,
           manifest_digest = p_manifest_digest::char(64),
           exported_row_count = p_exported_row_count,
           exported_byte_count = p_exported_byte_count,
           provider_result_state = p_provider_result_state,
           failure_code = p_failure_code,
           completed_at = CASE WHEN p_next_state = 'COMPLETED' THEN now() ELSE NULL END,
           state_version = v_version
     WHERE lifecycle_job_id = v_job.lifecycle_job_id
       AND organization_id = v_job.organization_id
       AND account_id = v_job.account_id
       AND state_version = p_expected_version;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_MTF_LIFECYCLE_VERSION_CONFLICT';
    END IF;

    IF p_next_state = 'TOMBSTONED' THEN
        INSERT INTO task_tenant_task_creation_fences (
            organization_id, account_id, lifecycle_job_id, fenced_by_actor_id
        ) VALUES (
            v_job.organization_id, v_job.account_id, v_job.lifecycle_job_id,
            current_setting('app.actor_id')
        ) ON CONFLICT (organization_id, account_id) DO NOTHING;
        IF NOT EXISTS (
            SELECT 1
              FROM task_tenant_task_creation_fences fence
             WHERE fence.organization_id = v_job.organization_id
               AND fence.account_id = v_job.account_id
               AND fence.lifecycle_job_id = v_job.lifecycle_job_id
        ) THEN
            RAISE EXCEPTION 'ELMOS_MTF_ACCOUNT_TASK_CREATION_FENCED';
        END IF;
        UPDATE execution_job_dispatch dispatch
           SET dispatch_state = 'DONE', queue_reason = 'TENANT_TOMBSTONED'
          FROM execution_jobs job
         WHERE job.job_id = dispatch.job_id
           AND job.organization_id = v_job.organization_id
           AND job.account_id = v_job.account_id
           AND dispatch.dispatch_state = 'READY';
        INSERT INTO task_tenant_resource_tombstones (
            lifecycle_job_id, organization_id, account_id, resource_type, resource_id
        )
        SELECT v_job.lifecycle_job_id, v_job.organization_id, v_job.account_id,
               'EXECUTION_JOB', job.job_id
          FROM execution_jobs job
         WHERE job.organization_id = v_job.organization_id
           AND job.account_id = v_job.account_id
        ON CONFLICT DO NOTHING;
        INSERT INTO task_tenant_resource_tombstones (
            lifecycle_job_id, organization_id, account_id, resource_type,
            resource_id, resource_digest
        )
        SELECT v_job.lifecycle_job_id, v_job.organization_id, v_job.account_id,
               'ARTIFACT', artifact.artifact_id, object.content_sha256
          FROM job_artifacts artifact
          JOIN execution_jobs job ON job.job_id = artifact.job_id
          JOIN content_objects object ON object.content_object_id = artifact.content_object_ref
         WHERE artifact.organization_id = v_job.organization_id
           AND job.account_id = v_job.account_id
        ON CONFLICT DO NOTHING;
        INSERT INTO task_tenant_resource_tombstones (
            lifecycle_job_id, organization_id, account_id, resource_type,
            resource_id, resource_digest
        )
        SELECT DISTINCT v_job.lifecycle_job_id, v_job.organization_id,
               v_job.account_id, 'CONTENT_OBJECT', object.content_object_id,
               object.content_sha256
          FROM job_artifacts artifact
          JOIN execution_jobs job ON job.job_id = artifact.job_id
          JOIN content_objects object ON object.content_object_id = artifact.content_object_ref
         WHERE artifact.organization_id = v_job.organization_id
           AND job.account_id = v_job.account_id
        ON CONFLICT DO NOTHING;
        UPDATE job_artifacts artifact
           SET deleted_at = coalesce(artifact.deleted_at, now()),
               deletion_reason = coalesce(
                   artifact.deletion_reason, 'TENANT_LIFECYCLE_TOMBSTONE')
          FROM execution_jobs job
         WHERE job.job_id = artifact.job_id
           AND artifact.organization_id = v_job.organization_id
           AND job.account_id = v_job.account_id;
        UPDATE execution_jobs job
           SET tenant_tombstoned_at = now(),
               tenant_lifecycle_job_id = v_job.lifecycle_job_id
         WHERE job.organization_id = v_job.organization_id
           AND job.account_id = v_job.account_id
           AND job.tenant_tombstoned_at IS NULL;
    ELSIF p_next_state = 'PURGE_PENDING' THEN
        INSERT INTO task_tenant_purge_items (
            lifecycle_job_id, organization_id, account_id, content_object_id
        )
        SELECT DISTINCT v_job.lifecycle_job_id, v_job.organization_id,
               v_job.account_id, artifact.content_object_ref
          FROM job_artifacts artifact
          JOIN execution_jobs job ON job.job_id = artifact.job_id
         WHERE artifact.organization_id = v_job.organization_id
           AND job.account_id = v_job.account_id
           AND NOT artifact.legal_hold
           AND NOT EXISTS (
                SELECT 1
                  FROM job_artifacts other_artifact
                  JOIN execution_jobs other_job
                    ON other_job.job_id = other_artifact.job_id
                 WHERE other_artifact.content_object_ref = artifact.content_object_ref
                   AND other_artifact.organization_id = v_job.organization_id
                   AND other_artifact.deleted_at IS NULL
                   AND other_job.account_id <> v_job.account_id
           )
        ON CONFLICT DO NOTHING;
    END IF;

    INSERT INTO task_tenant_lifecycle_events (
        lifecycle_event_id, organization_id, account_id, lifecycle_job_id,
        event_sequence, from_state, to_state, page_cursor, manifest_digest,
        exported_row_count, exported_byte_count, provider_result_state,
        failure_code, request_digest, idempotency_key, actor_id
    ) VALUES (
        'mtf-life-' || md5(jsonb_build_array(v_job.lifecycle_job_id, v_version)::text),
        v_job.organization_id, v_job.account_id, v_job.lifecycle_job_id,
        v_version, v_job.operation_state, p_next_state, p_page_cursor,
        p_manifest_digest::char(64),
        p_exported_row_count, p_exported_byte_count, p_provider_result_state,
        p_failure_code, p_request_digest, p_idempotency_key,
        current_setting('app.actor_id')
    );
    RETURN v_version;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_mtf_record_tenant_purge_result(
    p_purge_receipt_id varchar,
    p_lifecycle_job_id varchar,
    p_content_object_id varchar,
    p_provider_result_state varchar,
    p_provider_reference varchar,
    p_evidence_digest varchar,
    p_expected_version bigint,
    p_idempotency_key varchar,
    p_request_digest varchar
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_item task_tenant_purge_items%ROWTYPE;
    v_existing task_tenant_purge_receipts%ROWTYPE;
    v_state varchar(24);
BEGIN
    PERFORM elmos_mtf_require_member_role(ARRAY['OWNER', 'ADMIN']);
    IF p_purge_receipt_id IS NULL
       OR length(p_purge_receipt_id) NOT BETWEEN 1 AND 96
       OR p_lifecycle_job_id IS NULL
       OR length(p_lifecycle_job_id) NOT BETWEEN 1 AND 96
       OR p_content_object_id IS NULL
       OR length(p_content_object_id) NOT BETWEEN 1 AND 96
       OR p_provider_result_state IS NULL
       OR p_provider_result_state NOT IN ('CONFIRMED_ABSENT', 'FAILED', 'UNKNOWN')
       OR (p_provider_reference IS NOT NULL
           AND length(p_provider_reference) NOT BETWEEN 1 AND 255)
       OR p_expected_version IS NULL OR p_expected_version < 1
       OR p_expected_version >= 9223372036854775807
       OR p_idempotency_key IS NULL
       OR length(p_idempotency_key) NOT BETWEEN 1 AND 160
       OR p_request_digest IS NULL OR p_request_digest !~ '^[0-9a-f]{64}$'
       OR (p_evidence_digest IS NOT NULL AND p_evidence_digest !~ '^[0-9a-f]{64}$')
       OR (p_provider_result_state = 'CONFIRMED_ABSENT'
           AND (p_provider_reference IS NULL OR p_evidence_digest IS NULL)) THEN
        RAISE EXCEPTION 'ELMOS_MTF_PURGE_RECEIPT_INVALID';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        current_setting('app.organization_id'), current_setting('app.account_id'),
        'TENANT_PURGE_RESULT', p_idempotency_key
    )::text, 7720));
    SELECT * INTO v_existing FROM task_tenant_purge_receipts
     WHERE organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
       AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.purge_receipt_id IS DISTINCT FROM p_purge_receipt_id
           OR v_existing.lifecycle_job_id IS DISTINCT FROM p_lifecycle_job_id
           OR v_existing.content_object_id IS DISTINCT FROM p_content_object_id
           OR v_existing.provider_result_state IS DISTINCT FROM p_provider_result_state
           OR v_existing.provider_reference IS DISTINCT FROM p_provider_reference
           OR v_existing.evidence_digest IS DISTINCT FROM p_evidence_digest::char(64)
           OR v_existing.expected_state_version IS DISTINCT FROM p_expected_version
           OR v_existing.actor_id IS DISTINCT FROM current_setting('app.actor_id')
           OR v_existing.request_digest IS DISTINCT FROM p_request_digest::char(64) THEN
            RAISE EXCEPTION 'ELMOS_MTF_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.expected_state_version + 1;
    END IF;
    SELECT * INTO v_item FROM task_tenant_purge_items
     WHERE lifecycle_job_id = p_lifecycle_job_id
       AND content_object_id = p_content_object_id
       AND organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_MTF_PURGE_ITEM_UNKNOWN'; END IF;
    IF v_item.state_version <> p_expected_version THEN
        RAISE EXCEPTION 'ELMOS_MTF_PURGE_VERSION_CONFLICT';
    END IF;
    IF v_item.purge_state = 'CONFIRMED' THEN
        RAISE EXCEPTION 'ELMOS_MTF_PURGE_ITEM_TERMINAL';
    END IF;
    v_state := CASE p_provider_result_state
        WHEN 'CONFIRMED_ABSENT' THEN 'CONFIRMED'
        WHEN 'FAILED' THEN 'FAILED' ELSE 'UNKNOWN' END;
    UPDATE task_tenant_purge_items
       SET purge_state = v_state,
           state_version = state_version + 1,
           updated_at = now()
     WHERE lifecycle_job_id = p_lifecycle_job_id
       AND content_object_id = p_content_object_id
       AND organization_id = v_item.organization_id
       AND account_id = v_item.account_id
       AND state_version = p_expected_version;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_MTF_PURGE_VERSION_CONFLICT';
    END IF;
    INSERT INTO task_tenant_purge_receipts (
        purge_receipt_id, organization_id, account_id, lifecycle_job_id,
        content_object_id, provider_result_state, provider_reference,
        evidence_digest, request_digest, idempotency_key,
        expected_state_version, actor_id
    ) VALUES (
        p_purge_receipt_id, v_item.organization_id, v_item.account_id,
        p_lifecycle_job_id, p_content_object_id, p_provider_result_state,
        p_provider_reference, p_evidence_digest, p_request_digest,
        p_idempotency_key, p_expected_version, current_setting('app.actor_id')
    );
    RETURN v_item.state_version + 1;
END;
$$;

-- ---------------------------------------------------------------------------
-- 9. Settlement reconciliation without inferred provider success
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_mtf_record_settlement_reconciliation(
    p_reconciliation_id varchar,
    p_provider varchar,
    p_provider_settlement_reference varchar,
    p_period_start timestamptz,
    p_period_end timestamptz,
    p_currency varchar,
    p_provider_reported_minor numeric,
    p_ledger_recorded_minor numeric,
    p_provider_result_state varchar,
    p_external_evidence_digest varchar,
    p_evidence_verifier_actor_id varchar,
    p_idempotency_key varchar,
    p_request_digest varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_existing task_settlement_reconciliations%ROWTYPE;
    v_difference numeric;
    v_state varchar(24);
BEGIN
    PERFORM elmos_mtf_require_finance_authority();
    IF p_reconciliation_id IS NULL
       OR length(p_reconciliation_id) NOT BETWEEN 1 AND 96
       OR p_provider IS NULL OR length(p_provider) NOT BETWEEN 1 AND 64
       OR (p_provider_settlement_reference IS NOT NULL
           AND length(p_provider_settlement_reference) NOT BETWEEN 1 AND 255)
       OR p_period_start IS NULL OR p_period_end IS NULL
       OR p_period_end <= p_period_start
       OR p_currency IS NULL OR p_currency !~ '^[A-Z]{3}$'
       OR p_ledger_recorded_minor IS NULL
       OR scale(p_ledger_recorded_minor) > 6
       OR abs(p_ledger_recorded_minor)
            >= 1000000000000000000000000::numeric
       OR (p_provider_reported_minor IS NOT NULL
           AND (scale(p_provider_reported_minor) > 6
                OR abs(p_provider_reported_minor)
                    >= 1000000000000000000000000::numeric))
       OR (p_provider_result_state = 'CONFIRMED'
           AND p_provider_reported_minor IS NULL)
       OR p_provider_result_state IS NULL
       OR p_provider_result_state NOT IN ('CONFIRMED', 'FAILED', 'UNKNOWN')
       OR (p_external_evidence_digest IS NOT NULL
           AND p_external_evidence_digest !~ '^[0-9a-f]{64}$')
       OR (p_evidence_verifier_actor_id IS NOT NULL
           AND length(p_evidence_verifier_actor_id) NOT BETWEEN 1 AND 128)
       OR p_idempotency_key IS NULL
       OR length(p_idempotency_key) NOT BETWEEN 1 AND 160
       OR p_request_digest IS NULL
       OR p_request_digest !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'ELMOS_MTF_SETTLEMENT_RECONCILIATION_INVALID';
    END IF;

    v_difference := CASE WHEN p_provider_result_state = 'CONFIRMED'
        THEN elmos_mtf_round_half_even(
            p_provider_reported_minor - p_ledger_recorded_minor, 6)
        ELSE NULL END;
    IF v_difference IS NOT NULL
       AND abs(v_difference) >= 1000000000000000000000000::numeric THEN
        RAISE EXCEPTION 'ELMOS_MTF_SETTLEMENT_RECONCILIATION_INVALID';
    END IF;
    v_state := CASE
        WHEN p_provider_result_state = 'UNKNOWN' THEN 'UNKNOWN'
        WHEN p_provider_result_state = 'FAILED' THEN 'UNRECONCILED'
        WHEN v_difference IS DISTINCT FROM 0 THEN 'UNRECONCILED'
        ELSE 'MATCHED' END;

    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        current_setting('app.organization_id'), current_setting('app.account_id'),
        'SETTLEMENT_RECONCILIATION', p_idempotency_key
    )::text, 7713));
    SELECT * INTO v_existing FROM task_settlement_reconciliations
     WHERE organization_id = current_setting('app.organization_id')
       AND account_id = current_setting('app.account_id')
       AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.settlement_reconciliation_id IS DISTINCT FROM p_reconciliation_id
           OR v_existing.provider IS DISTINCT FROM p_provider
           OR v_existing.provider_settlement_reference
                IS DISTINCT FROM p_provider_settlement_reference
           OR v_existing.period_start IS DISTINCT FROM p_period_start
           OR v_existing.period_end IS DISTINCT FROM p_period_end
           OR v_existing.currency IS DISTINCT FROM p_currency::char(3)
           OR v_existing.provider_reported_minor IS DISTINCT FROM (CASE
                WHEN p_provider_reported_minor IS NULL THEN NULL
                ELSE elmos_mtf_round_half_even(p_provider_reported_minor, 6) END)
           OR v_existing.ledger_recorded_minor IS DISTINCT FROM
                elmos_mtf_round_half_even(p_ledger_recorded_minor, 6)
           OR v_existing.difference_minor IS DISTINCT FROM v_difference
           OR v_existing.provider_result_state IS DISTINCT FROM p_provider_result_state
           OR v_existing.reconciliation_state IS DISTINCT FROM v_state
           OR v_existing.external_evidence_digest
                IS DISTINCT FROM p_external_evidence_digest::char(64)
           OR v_existing.evidence_verifier_actor_id
                IS DISTINCT FROM p_evidence_verifier_actor_id
           OR v_existing.recorded_by_actor_id
                IS DISTINCT FROM current_setting('app.actor_id')
           OR v_existing.request_digest IS DISTINCT FROM p_request_digest::char(64) THEN
            RAISE EXCEPTION 'ELMOS_MTF_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.settlement_reconciliation_id;
    END IF;

    IF v_state = 'MATCHED' THEN
        IF p_provider_settlement_reference IS NULL
           OR p_external_evidence_digest IS NULL
           OR p_external_evidence_digest !~ '^[0-9a-f]{64}$'
           OR p_evidence_verifier_actor_id IS NULL
           OR p_evidence_verifier_actor_id = current_setting('app.actor_id')
           OR NOT EXISTS (
                SELECT 1
                  FROM user_identities identity
                  JOIN organization_memberships membership
                    ON membership.organization_id = identity.organization_id
                   AND membership.account_ref = identity.account_ref
                 WHERE identity.organization_id = current_setting('app.organization_id')
                   AND identity.account_ref <> current_setting('app.account_id')
                   AND identity.actor_id = p_evidence_verifier_actor_id
                   AND identity.deprovisioned_at IS NULL
                   AND membership.member_state = 'ACTIVE'
                   AND membership.member_role IN ('OWNER', 'ADMIN', 'BILLING')
           ) THEN
            RAISE EXCEPTION 'ELMOS_MTF_INDEPENDENT_SETTLEMENT_EVIDENCE_REQUIRED';
        END IF;
    END IF;

    INSERT INTO task_settlement_reconciliations (
        settlement_reconciliation_id, organization_id, account_id, provider,
        provider_settlement_reference, period_start, period_end, currency,
        provider_reported_minor, ledger_recorded_minor, difference_minor,
        provider_result_state, reconciliation_state, external_evidence_digest,
        evidence_verifier_actor_id, request_digest, idempotency_key,
        recorded_by_actor_id
    ) VALUES (
        p_reconciliation_id, current_setting('app.organization_id'),
        current_setting('app.account_id'), p_provider,
        p_provider_settlement_reference, p_period_start, p_period_end,
        p_currency, CASE WHEN p_provider_reported_minor IS NULL THEN NULL
            ELSE elmos_mtf_round_half_even(p_provider_reported_minor, 6) END,
        elmos_mtf_round_half_even(p_ledger_recorded_minor, 6), v_difference,
        p_provider_result_state, v_state, p_external_evidence_digest,
        p_evidence_verifier_actor_id, p_request_digest, p_idempotency_key,
        current_setting('app.actor_id')
    );
    RETURN p_reconciliation_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- 10. Capability grants
-- ---------------------------------------------------------------------------

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
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', v_function.signature);
    END LOOP;
END;
$$;

GRANT EXECUTE ON FUNCTION elmos_mtf_set_feature_rollout(
    varchar, varchar, varchar, smallint, bigint, varchar, varchar
) TO elmos_mtf_application;
GRANT EXECUTE ON FUNCTION elmos_mtf_record_checkpoint_compatibility(
    varchar, varchar, varchar, varchar, text[], varchar, varchar, varchar, varchar
) TO elmos_mtf_workflow;
GRANT EXECUTE ON FUNCTION elmos_mtf_fork_incompatible_recovery(
    varchar, varchar, varchar, varchar, varchar, varchar, varchar
) TO elmos_mtf_application;
GRANT EXECUTE ON FUNCTION elmos_mtf_request_tenant_lifecycle(
    varchar, varchar, varchar, timestamptz, varchar, varchar
) TO elmos_mtf_application;
GRANT EXECUTE ON FUNCTION elmos_mtf_checkpoint_tenant_export_page(
    varchar, bigint, varchar, bigint, bigint, bigint, bigint, boolean,
    varchar, bigint, varchar, varchar
) TO elmos_mtf_workflow;
GRANT EXECUTE ON FUNCTION elmos_mtf_advance_tenant_lifecycle(
    varchar, bigint, varchar, varchar, varchar, bigint, bigint,
    varchar, varchar, varchar, varchar
) TO elmos_mtf_workflow;
GRANT EXECUTE ON FUNCTION elmos_mtf_record_tenant_purge_result(
    varchar, varchar, varchar, varchar, varchar, varchar, bigint, varchar, varchar
) TO elmos_mtf_workflow;
GRANT EXECUTE ON FUNCTION elmos_mtf_record_settlement_reconciliation(
    varchar, varchar, varchar, timestamptz, timestamptz, varchar, numeric,
    numeric, varchar, varchar, varchar, varchar, varchar
) TO elmos_mtf_workflow;

GRANT SELECT ON task_finops_feature_rollouts, task_checkpoint_compatibility_decisions,
    task_recovery_forks, task_tenant_lifecycle_jobs,
    task_tenant_task_creation_fences, task_tenant_export_pages,
    task_tenant_lifecycle_events, task_tenant_resource_tombstones, task_tenant_purge_items,
    task_tenant_purge_receipts, task_settlement_reconciliations
    TO elmos_mtf_application, elmos_mtf_workflow, elmos_mtf_analytics;

COMMENT ON TABLE task_tenant_export_pages IS
    'Append-only local export checkpoints. The terminal chain digest binds ordered page cursors, page digests and cumulative counts; it is not object-storage execution, external verification or production certification evidence.';

COMMENT ON TABLE task_settlement_reconciliations IS
    'Repository reconciliation records only. MATCHED is exact local ledger/evidence agreement; it is not bank, tax, accounting, payment-provider, external-review or production certification.';
