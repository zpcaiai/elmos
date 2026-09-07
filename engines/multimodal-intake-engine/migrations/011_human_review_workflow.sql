PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE human_review_tasks (
    task_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    target_kind TEXT NOT NULL CHECK (target_kind IN (
        'TEXT','SPEAKER','TIME_RANGE','BBOX','TABLE','REQUIREMENT','CONFLICT'
    )),
    target_json TEXT NOT NULL,
    target_digest TEXT NOT NULL CHECK (length(target_digest) = 64),
    original_value_json TEXT NOT NULL,
    original_value_digest TEXT NOT NULL CHECK (length(original_value_digest) = 64),
    source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
    source_ref_json TEXT NOT NULL,
    source_ref_digest TEXT NOT NULL CHECK (length(source_ref_digest) = 64),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    reason TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'QUEUED','CLAIMED','EDITED','APPROVED','REJECTED','REOPENED',
        'REVERTING','REVERTED'
    )),
    current_correction_version INTEGER NOT NULL DEFAULT 0
        CHECK (current_correction_version >= 0),
    current_correction_digest TEXT
        CHECK (current_correction_digest IS NULL OR length(current_correction_digest) = 64),
    effective_version INTEGER NOT NULL DEFAULT 0 CHECK (effective_version >= 0),
    effective_digest TEXT
        CHECK (effective_digest IS NULL OR length(effective_digest) = 64),
    claim_actor_id TEXT,
    claim_token_digest TEXT
        CHECK (claim_token_digest IS NULL OR length(claim_token_digest) = 64),
    claim_fence INTEGER NOT NULL DEFAULT 0 CHECK (claim_fence >= 0),
    claim_expires_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    UNIQUE (tenant_id, project_id, task_id),
    FOREIGN KEY (tenant_id, project_id, asset_id)
        REFERENCES input_assets (tenant_id, project_id, asset_id),
    CHECK (
        (claim_actor_id IS NULL AND claim_token_digest IS NULL AND claim_expires_at IS NULL)
        OR
        (claim_actor_id IS NOT NULL AND claim_token_digest IS NOT NULL AND claim_expires_at IS NOT NULL)
    )
);
CREATE INDEX human_review_tasks_queue_idx
    ON human_review_tasks (
        tenant_id, project_id, state, confidence, created_at, task_id
    );
CREATE INDEX human_review_tasks_asset_idx
    ON human_review_tasks (
        tenant_id, project_id, asset_id, target_kind, state, created_at
    );

CREATE TABLE human_review_correction_versions (
    correction_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    correction_version INTEGER NOT NULL CHECK (correction_version >= 1),
    parent_correction_version INTEGER NOT NULL CHECK (parent_correction_version >= 0),
    target_kind TEXT NOT NULL CHECK (target_kind IN (
        'TEXT','SPEAKER','TIME_RANGE','BBOX','TABLE','REQUIREMENT','CONFLICT'
    )),
    target_json TEXT NOT NULL,
    original_value_json TEXT NOT NULL,
    original_value_digest TEXT NOT NULL CHECK (length(original_value_digest) = 64),
    corrected_value_json TEXT NOT NULL,
    corrected_value_digest TEXT NOT NULL CHECK (length(corrected_value_digest) = 64),
    source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
    correction_digest TEXT NOT NULL CHECK (length(correction_digest) = 64),
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, correction_id),
    UNIQUE (tenant_id, project_id, task_id, correction_version),
    FOREIGN KEY (tenant_id, project_id, task_id)
        REFERENCES human_review_tasks (tenant_id, project_id, task_id),
    CHECK (correction_version = parent_correction_version + 1)
);
CREATE INDEX human_review_correction_versions_task_idx
    ON human_review_correction_versions (
        tenant_id, project_id, task_id, correction_version DESC
    );

CREATE TABLE human_review_decisions (
    decision_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    decision_version INTEGER NOT NULL CHECK (decision_version >= 2),
    decision TEXT NOT NULL CHECK (decision IN ('APPROVE','REJECT','REOPEN','REVERT')),
    prior_state TEXT NOT NULL,
    next_state TEXT NOT NULL,
    correction_version INTEGER CHECK (correction_version IS NULL OR correction_version >= 1),
    correction_digest TEXT
        CHECK (correction_digest IS NULL OR length(correction_digest) = 64),
    source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, decision_id),
    UNIQUE (tenant_id, project_id, task_id, decision_version),
    FOREIGN KEY (tenant_id, project_id, task_id)
        REFERENCES human_review_tasks (tenant_id, project_id, task_id)
);
CREATE INDEX human_review_decisions_task_idx
    ON human_review_decisions (
        tenant_id, project_id, task_id, decision_version DESC
    );

CREATE TABLE human_review_audit_log (
    audit_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    prior_state TEXT,
    next_state TEXT,
    task_version INTEGER NOT NULL CHECK (task_version >= 1),
    details_json TEXT NOT NULL,
    details_digest TEXT NOT NULL CHECK (length(details_digest) = 64),
    occurred_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, audit_id),
    FOREIGN KEY (tenant_id, project_id, task_id)
        REFERENCES human_review_tasks (tenant_id, project_id, task_id)
);
CREATE INDEX human_review_audit_task_idx
    ON human_review_audit_log (
        tenant_id, project_id, task_id, occurred_at, audit_id
    );

CREATE TABLE human_review_operation_receipts (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    response_json TEXT NOT NULL,
    response_digest TEXT NOT NULL CHECK (length(response_digest) = 64),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, actor_id, operation, idempotency_key)
);

CREATE TABLE human_review_worker_capabilities (
    capability_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    token_digest TEXT NOT NULL CHECK (length(token_digest) = 64),
    actions_json TEXT NOT NULL,
    actions_digest TEXT NOT NULL CHECK (length(actions_digest) = 64),
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, capability_id),
    UNIQUE (tenant_id, project_id, worker_id, token_digest)
);
CREATE INDEX human_review_worker_capability_lookup_idx
    ON human_review_worker_capabilities (
        tenant_id, project_id, worker_id, capability_id, expires_at
    ) WHERE revoked_at IS NULL;

CREATE TABLE human_review_propagation_tasks (
    propagation_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    correction_version INTEGER NOT NULL CHECK (correction_version >= 1),
    channel TEXT NOT NULL CHECK (channel IN (
        'content-index','requirements','project-memory','downstream'
    )),
    direction TEXT NOT NULL CHECK (direction IN ('APPLY','REVERT')),
    payload_json TEXT NOT NULL,
    payload_digest TEXT NOT NULL CHECK (length(payload_digest) = 64),
    state TEXT NOT NULL CHECK (state IN (
        'PENDING','CLAIMED','SUCCEEDED','FAILED','UNKNOWN'
    )),
    claim_capability_id TEXT,
    claim_owner_digest TEXT
        CHECK (claim_owner_digest IS NULL OR length(claim_owner_digest) = 64),
    claim_fence INTEGER NOT NULL DEFAULT 0 CHECK (claim_fence >= 0),
    claim_expires_at TEXT,
    dispatch_started_at TEXT,
    result_json TEXT,
    result_digest TEXT CHECK (result_digest IS NULL OR length(result_digest) = 64),
    failure_code TEXT,
    reconciliation_required INTEGER NOT NULL DEFAULT 0
        CHECK (reconciliation_required IN (0,1)),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    reconciled_at TEXT,
    UNIQUE (tenant_id, project_id, propagation_id),
    UNIQUE (tenant_id, project_id, decision_id, channel),
    FOREIGN KEY (tenant_id, project_id, task_id)
        REFERENCES human_review_tasks (tenant_id, project_id, task_id),
    FOREIGN KEY (tenant_id, project_id, decision_id)
        REFERENCES human_review_decisions (tenant_id, project_id, decision_id),
    FOREIGN KEY (tenant_id, project_id, claim_capability_id)
        REFERENCES human_review_worker_capabilities (tenant_id, project_id, capability_id),
    CHECK (
        (claim_capability_id IS NULL AND claim_owner_digest IS NULL AND claim_expires_at IS NULL)
        OR
        (claim_capability_id IS NOT NULL AND claim_owner_digest IS NOT NULL AND claim_expires_at IS NOT NULL)
    )
);
CREATE INDEX human_review_propagation_pending_idx
    ON human_review_propagation_tasks (
        tenant_id, project_id, state, created_at, propagation_id
    );
CREATE INDEX human_review_propagation_task_idx
    ON human_review_propagation_tasks (
        tenant_id, project_id, task_id, decision_id, channel
    );

CREATE TABLE human_review_effective_projections (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN (
        'content-index','requirements','project-memory','downstream'
    )),
    source_decision_id TEXT NOT NULL,
    correction_version INTEGER NOT NULL CHECK (correction_version >= 1),
    direction TEXT NOT NULL CHECK (direction IN ('APPLY','REVERT')),
    target_kind TEXT NOT NULL,
    target_json TEXT NOT NULL,
    effective_value_json TEXT NOT NULL,
    effective_value_digest TEXT NOT NULL CHECK (length(effective_value_digest) = 64),
    source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
    version INTEGER NOT NULL CHECK (version >= 1),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, task_id, channel),
    FOREIGN KEY (tenant_id, project_id, task_id)
        REFERENCES human_review_tasks (tenant_id, project_id, task_id),
    FOREIGN KEY (tenant_id, project_id, source_decision_id)
        REFERENCES human_review_decisions (tenant_id, project_id, decision_id)
);

CREATE TRIGGER human_review_tasks_no_delete
BEFORE DELETE ON human_review_tasks
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;
CREATE TRIGGER human_review_tasks_source_no_update
BEFORE UPDATE ON human_review_tasks
WHEN NEW.task_id IS NOT OLD.task_id
  OR NEW.tenant_id IS NOT OLD.tenant_id
  OR NEW.project_id IS NOT OLD.project_id
  OR NEW.asset_id IS NOT OLD.asset_id
  OR NEW.target_kind IS NOT OLD.target_kind
  OR NEW.target_json IS NOT OLD.target_json
  OR NEW.target_digest IS NOT OLD.target_digest
  OR NEW.original_value_json IS NOT OLD.original_value_json
  OR NEW.original_value_digest IS NOT OLD.original_value_digest
  OR NEW.source_digest IS NOT OLD.source_digest
  OR NEW.source_ref_json IS NOT OLD.source_ref_json
  OR NEW.source_ref_digest IS NOT OLD.source_ref_digest
  OR NEW.confidence IS NOT OLD.confidence
  OR NEW.reason IS NOT OLD.reason
  OR NEW.created_by IS NOT OLD.created_by
  OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;

CREATE TRIGGER human_review_correction_versions_no_update
BEFORE UPDATE ON human_review_correction_versions
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;
CREATE TRIGGER human_review_correction_versions_no_delete
BEFORE DELETE ON human_review_correction_versions
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;

CREATE TRIGGER human_review_decisions_no_update
BEFORE UPDATE ON human_review_decisions
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;
CREATE TRIGGER human_review_decisions_no_delete
BEFORE DELETE ON human_review_decisions
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;

CREATE TRIGGER human_review_audit_log_no_update
BEFORE UPDATE ON human_review_audit_log
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;
CREATE TRIGGER human_review_audit_log_no_delete
BEFORE DELETE ON human_review_audit_log
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;

CREATE TRIGGER human_review_operation_receipts_no_update
BEFORE UPDATE ON human_review_operation_receipts
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;
CREATE TRIGGER human_review_operation_receipts_no_delete
BEFORE DELETE ON human_review_operation_receipts
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;

CREATE TRIGGER human_review_worker_capabilities_no_delete
BEFORE DELETE ON human_review_worker_capabilities
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;
CREATE TRIGGER human_review_worker_capabilities_identity_no_update
BEFORE UPDATE ON human_review_worker_capabilities
WHEN NEW.capability_id IS NOT OLD.capability_id
  OR NEW.tenant_id IS NOT OLD.tenant_id
  OR NEW.project_id IS NOT OLD.project_id
  OR NEW.worker_id IS NOT OLD.worker_id
  OR NEW.token_digest IS NOT OLD.token_digest
  OR NEW.actions_json IS NOT OLD.actions_json
  OR NEW.actions_digest IS NOT OLD.actions_digest
  OR NEW.expires_at IS NOT OLD.expires_at
  OR NEW.created_by IS NOT OLD.created_by
  OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;
CREATE TRIGGER human_review_propagation_tasks_no_delete
BEFORE DELETE ON human_review_propagation_tasks
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;
CREATE TRIGGER human_review_propagation_tasks_identity_no_update
BEFORE UPDATE ON human_review_propagation_tasks
WHEN NEW.propagation_id IS NOT OLD.propagation_id
  OR NEW.tenant_id IS NOT OLD.tenant_id
  OR NEW.project_id IS NOT OLD.project_id
  OR NEW.task_id IS NOT OLD.task_id
  OR NEW.decision_id IS NOT OLD.decision_id
  OR NEW.correction_version IS NOT OLD.correction_version
  OR NEW.channel IS NOT OLD.channel
  OR NEW.direction IS NOT OLD.direction
  OR NEW.payload_json IS NOT OLD.payload_json
  OR NEW.payload_digest IS NOT OLD.payload_digest
  OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;
CREATE TRIGGER human_review_effective_projections_no_delete
BEFORE DELETE ON human_review_effective_projections
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_HISTORY_IMMUTABLE');
END;

PRAGMA user_version = 11;
COMMIT;
