PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE downstream_agent_contexts (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    context_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    package_version INTEGER NOT NULL CHECK (package_version >= 1),
    actor_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    policy_version TEXT NOT NULL,
    source_set_digest TEXT NOT NULL CHECK (length(source_set_digest) = 64),
    context_json TEXT NOT NULL,
    context_digest TEXT NOT NULL CHECK (length(context_digest) = 64),
    state TEXT NOT NULL CHECK (state IN ('ACTIVE','REVOKED')),
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    PRIMARY KEY (tenant_id, project_id, context_id),
    UNIQUE (tenant_id, project_id, actor_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id, package_version)
        REFERENCES project_package_versions (tenant_id, project_id, package_version)
) WITHOUT ROWID;

CREATE TABLE downstream_context_sources (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    context_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    source_receipt_id TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('CONTENT_BLOCK','REQUIREMENT','REPOSITORY_MAP')),
    source_id TEXT NOT NULL,
    source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
    receipt_digest TEXT NOT NULL CHECK (length(receipt_digest) = 64),
    normalized_json TEXT NOT NULL,
    normalized_digest TEXT NOT NULL CHECK (length(normalized_digest) = 64),
    raw_asset_included INTEGER NOT NULL CHECK (raw_asset_included = 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, context_id, ordinal),
    UNIQUE (tenant_id, project_id, context_id, source_receipt_id),
    FOREIGN KEY (tenant_id, project_id, context_id)
        REFERENCES downstream_agent_contexts (tenant_id, project_id, context_id)
) WITHOUT ROWID;

CREATE TABLE downstream_tool_grants (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    context_id TEXT NOT NULL,
    grant_id TEXT NOT NULL,
    tool_receipt_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    capability_version TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    input_digest TEXT NOT NULL CHECK (length(input_digest) = 64),
    scope_digest TEXT NOT NULL CHECK (length(scope_digest) = 64),
    receipt_digest TEXT NOT NULL CHECK (length(receipt_digest) = 64),
    policy_version TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('ISSUED','CLAIMED','VERIFIED','LINKED','REVOKED','EXPIRED','UNKNOWN','BLOCKED')),
    expires_at TEXT NOT NULL,
    single_use INTEGER NOT NULL CHECK (single_use = 1),
    claim_fence INTEGER NOT NULL DEFAULT 0 CHECK (claim_fence >= 0),
    claim_token_digest TEXT CHECK (claim_token_digest IS NULL OR length(claim_token_digest) = 64),
    claimed_by TEXT,
    execution_receipt_id TEXT,
    issued_at TEXT NOT NULL,
    claimed_at TEXT,
    terminal_at TEXT,
    revocation_reason TEXT,
    PRIMARY KEY (tenant_id, project_id, grant_id),
    UNIQUE (tenant_id, project_id, context_id, grant_id),
    UNIQUE (tenant_id, project_id, context_id, tool_receipt_id),
    FOREIGN KEY (tenant_id, project_id, context_id)
        REFERENCES downstream_agent_contexts (tenant_id, project_id, context_id)
) WITHOUT ROWID;

CREATE TABLE downstream_tool_executions (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    context_id TEXT NOT NULL,
    grant_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    executor_id TEXT NOT NULL,
    claim_fence INTEGER NOT NULL CHECK (claim_fence >= 1),
    state TEXT NOT NULL CHECK (state IN ('IN_PROGRESS','VERIFIED','UNKNOWN','BLOCKED')),
    result_receipt_id TEXT,
    result_receipt_json TEXT,
    result_receipt_digest TEXT CHECK (result_receipt_digest IS NULL OR length(result_receipt_digest) = 64),
    response_json TEXT,
    response_digest TEXT CHECK (response_digest IS NULL OR length(response_digest) = 64),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (tenant_id, project_id, execution_id),
    UNIQUE (tenant_id, project_id, context_id, grant_id, execution_id),
    UNIQUE (tenant_id, project_id, grant_id, idempotency_key),
    UNIQUE (tenant_id, project_id, result_receipt_id),
    FOREIGN KEY (tenant_id, project_id, context_id, grant_id)
        REFERENCES downstream_tool_grants (tenant_id, project_id, context_id, grant_id)
) WITHOUT ROWID;

CREATE TABLE downstream_agent_result_links (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    link_id TEXT NOT NULL,
    context_id TEXT NOT NULL,
    grant_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    result_receipt_id TEXT NOT NULL,
    result_digest TEXT NOT NULL CHECK (length(result_digest) = 64),
    result_byte_count INTEGER NOT NULL CHECK (result_byte_count >= 0),
    result_locator TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    verifier_id TEXT NOT NULL CHECK (verifier_id <> executor_id),
    verification_method TEXT NOT NULL CHECK (verification_method IN ('HOST_VERIFIED','SIGNATURE_VERIFIED')),
    receipt_digest TEXT NOT NULL CHECK (length(receipt_digest) = 64),
    link_json TEXT NOT NULL,
    link_digest TEXT NOT NULL CHECK (length(link_digest) = 64),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, link_id),
    UNIQUE (tenant_id, project_id, grant_id),
    UNIQUE (tenant_id, project_id, result_receipt_id),
    FOREIGN KEY (tenant_id, project_id, context_id)
        REFERENCES downstream_agent_contexts (tenant_id, project_id, context_id),
    FOREIGN KEY (tenant_id, project_id, context_id, grant_id)
        REFERENCES downstream_tool_grants (tenant_id, project_id, context_id, grant_id),
    FOREIGN KEY (tenant_id, project_id, context_id, grant_id, execution_id)
        REFERENCES downstream_tool_executions
        (tenant_id, project_id, context_id, grant_id, execution_id)
) WITHOUT ROWID;

CREATE TABLE downstream_agent_operation_receipts (
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
) WITHOUT ROWID;

CREATE TABLE downstream_agent_outbox (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_digest TEXT NOT NULL CHECK (length(payload_digest) = 64),
    delivery_state TEXT NOT NULL CHECK (delivery_state IN ('PENDING','PUBLISHED','DEAD')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    claim_token_digest TEXT CHECK (claim_token_digest IS NULL OR length(claim_token_digest) = 64),
    claim_expires_at TEXT,
    created_at TEXT NOT NULL,
    published_at TEXT,
    PRIMARY KEY (tenant_id, project_id, event_id),
    UNIQUE (tenant_id, project_id, idempotency_key)
) WITHOUT ROWID;

CREATE INDEX downstream_context_subject_idx
    ON downstream_agent_contexts (tenant_id, project_id, subject_id, package_version, created_at);
CREATE INDEX downstream_grant_state_expiry_idx
    ON downstream_tool_grants (tenant_id, project_id, state, expires_at);
CREATE INDEX downstream_outbox_delivery_idx
    ON downstream_agent_outbox (tenant_id, project_id, delivery_state, created_at);

CREATE TRIGGER downstream_context_update_guard
BEFORE UPDATE ON downstream_agent_contexts
WHEN NEW.tenant_id <> OLD.tenant_id
  OR NEW.project_id <> OLD.project_id
  OR NEW.context_id <> OLD.context_id
  OR NEW.task_id <> OLD.task_id
  OR NEW.subject_id <> OLD.subject_id
  OR NEW.package_version <> OLD.package_version
  OR NEW.actor_id <> OLD.actor_id
  OR NEW.idempotency_key <> OLD.idempotency_key
  OR NEW.request_digest <> OLD.request_digest
  OR NEW.policy_version <> OLD.policy_version
  OR NEW.source_set_digest <> OLD.source_set_digest
  OR NEW.context_json <> OLD.context_json
  OR NEW.context_digest <> OLD.context_digest
  OR NEW.created_at <> OLD.created_at
  OR OLD.state <> 'ACTIVE'
  OR NEW.state <> 'REVOKED'
  OR NEW.revoked_at IS NULL
BEGIN
    SELECT RAISE(ABORT, 'downstream context transition invalid');
END;

CREATE TRIGGER downstream_context_delete_forbidden
BEFORE DELETE ON downstream_agent_contexts
BEGIN
    SELECT RAISE(ABORT, 'downstream context deletion forbidden');
END;

CREATE TRIGGER downstream_source_update_forbidden
BEFORE UPDATE ON downstream_context_sources
BEGIN
    SELECT RAISE(ABORT, 'downstream context source immutable');
END;
CREATE TRIGGER downstream_source_delete_forbidden
BEFORE DELETE ON downstream_context_sources
BEGIN
    SELECT RAISE(ABORT, 'downstream context source deletion forbidden');
END;

CREATE TRIGGER downstream_grant_update_guard
BEFORE UPDATE ON downstream_tool_grants
WHEN NEW.tenant_id <> OLD.tenant_id
  OR NEW.project_id <> OLD.project_id
  OR NEW.context_id <> OLD.context_id
  OR NEW.grant_id <> OLD.grant_id
  OR NEW.tool_receipt_id <> OLD.tool_receipt_id
  OR NEW.tool_id <> OLD.tool_id
  OR NEW.capability_version <> OLD.capability_version
  OR NEW.subject_id <> OLD.subject_id
  OR NEW.input_digest <> OLD.input_digest
  OR NEW.scope_digest <> OLD.scope_digest
  OR NEW.receipt_digest <> OLD.receipt_digest
  OR NEW.policy_version <> OLD.policy_version
  OR NEW.expires_at <> OLD.expires_at
  OR NEW.single_use <> OLD.single_use
  OR NEW.issued_at <> OLD.issued_at
  OR NEW.claim_fence < OLD.claim_fence
  OR (
      OLD.state = 'ISSUED' AND NEW.state IN ('CLAIMED','EXPIRED','BLOCKED')
      AND NEW.claim_fence <> OLD.claim_fence + 1
  )
  OR (
      NOT (OLD.state = 'ISSUED' AND NEW.state IN ('CLAIMED','EXPIRED','BLOCKED'))
      AND NEW.claim_fence <> OLD.claim_fence
  )
  OR (
      NEW.state = 'CLAIMED'
      AND (NEW.claim_token_digest IS NULL OR NEW.claimed_by IS NULL OR NEW.claimed_at IS NULL)
  )
  OR (
      NEW.state = 'VERIFIED'
      AND (NEW.execution_receipt_id IS NULL OR NEW.terminal_at IS NULL)
  )
  OR (NEW.state IN ('REVOKED','EXPIRED','UNKNOWN','BLOCKED') AND NEW.terminal_at IS NULL)
  OR NOT (
      (OLD.state = 'ISSUED' AND NEW.state IN ('CLAIMED','REVOKED','EXPIRED','BLOCKED'))
      OR (OLD.state = 'CLAIMED' AND NEW.state IN ('VERIFIED','UNKNOWN','REVOKED'))
      OR (OLD.state = 'UNKNOWN' AND NEW.state IN ('VERIFIED','REVOKED'))
      OR (OLD.state = 'VERIFIED' AND NEW.state = 'LINKED')
  )
BEGIN
    SELECT RAISE(ABORT, 'downstream grant transition invalid');
END;

CREATE TRIGGER downstream_grant_delete_forbidden
BEFORE DELETE ON downstream_tool_grants
BEGIN
    SELECT RAISE(ABORT, 'downstream grant deletion forbidden');
END;

CREATE TRIGGER downstream_execution_update_guard
BEFORE UPDATE ON downstream_tool_executions
WHEN NEW.tenant_id <> OLD.tenant_id
  OR NEW.project_id <> OLD.project_id
  OR NEW.execution_id <> OLD.execution_id
  OR NEW.context_id <> OLD.context_id
  OR NEW.grant_id <> OLD.grant_id
  OR NEW.idempotency_key <> OLD.idempotency_key
  OR NEW.request_digest <> OLD.request_digest
  OR NEW.executor_id <> OLD.executor_id
  OR NEW.claim_fence <> OLD.claim_fence
  OR NEW.started_at <> OLD.started_at
  OR (NEW.state = 'VERIFIED' AND (
      NEW.result_receipt_id IS NULL OR NEW.result_receipt_json IS NULL
      OR NEW.result_receipt_digest IS NULL OR NEW.response_json IS NULL
      OR NEW.response_digest IS NULL OR NEW.completed_at IS NULL
  ))
  OR (NEW.state IN ('UNKNOWN','BLOCKED') AND (
      NEW.response_json IS NULL OR NEW.response_digest IS NULL OR NEW.completed_at IS NULL
  ))
  OR NOT (
      (OLD.state = 'IN_PROGRESS' AND NEW.state IN ('VERIFIED','UNKNOWN','BLOCKED'))
      OR (OLD.state = 'UNKNOWN' AND NEW.state = 'VERIFIED')
  )
BEGIN
    SELECT RAISE(ABORT, 'downstream execution transition invalid');
END;

CREATE TRIGGER downstream_execution_delete_forbidden
BEFORE DELETE ON downstream_tool_executions
BEGIN
    SELECT RAISE(ABORT, 'downstream execution deletion forbidden');
END;

CREATE TRIGGER downstream_result_link_update_forbidden
BEFORE UPDATE ON downstream_agent_result_links
BEGIN
    SELECT RAISE(ABORT, 'downstream result link immutable');
END;
CREATE TRIGGER downstream_result_link_delete_forbidden
BEFORE DELETE ON downstream_agent_result_links
BEGIN
    SELECT RAISE(ABORT, 'downstream result link deletion forbidden');
END;
CREATE TRIGGER downstream_operation_receipt_update_forbidden
BEFORE UPDATE ON downstream_agent_operation_receipts
BEGIN
    SELECT RAISE(ABORT, 'downstream operation receipt immutable');
END;
CREATE TRIGGER downstream_operation_receipt_delete_forbidden
BEFORE DELETE ON downstream_agent_operation_receipts
BEGIN
    SELECT RAISE(ABORT, 'downstream operation receipt deletion forbidden');
END;

CREATE TRIGGER downstream_outbox_update_guard
BEFORE UPDATE ON downstream_agent_outbox
WHEN NEW.tenant_id <> OLD.tenant_id
  OR NEW.project_id <> OLD.project_id
  OR NEW.event_id <> OLD.event_id
  OR NEW.aggregate_type <> OLD.aggregate_type
  OR NEW.aggregate_id <> OLD.aggregate_id
  OR NEW.event_type <> OLD.event_type
  OR NEW.idempotency_key <> OLD.idempotency_key
  OR NEW.payload_json <> OLD.payload_json
  OR NEW.payload_digest <> OLD.payload_digest
  OR NEW.created_at <> OLD.created_at
  OR NEW.attempt_count < OLD.attempt_count
BEGIN
    SELECT RAISE(ABORT, 'downstream outbox transition invalid');
END;
CREATE TRIGGER downstream_outbox_delete_forbidden
BEFORE DELETE ON downstream_agent_outbox
BEGIN
    SELECT RAISE(ABORT, 'downstream outbox deletion forbidden');
END;

PRAGMA user_version = 22;
COMMIT;
