PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE governance_deletion_jobs (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    policy_version TEXT NOT NULL,
    inventory_version TEXT NOT NULL,
    inventory_digest TEXT NOT NULL CHECK (length(inventory_digest) = 64),
    state TEXT NOT NULL CHECK (state IN ('PENDING','RUNNING','UNKNOWN','BLOCKED','COMPLETED')),
    backup_delete_not_before TEXT NOT NULL,
    legal_hold_count INTEGER NOT NULL CHECK (legal_hold_count >= 0),
    command_count INTEGER NOT NULL CHECK (command_count >= 1),
    proof_json TEXT,
    proof_digest TEXT CHECK (proof_digest IS NULL OR length(proof_digest) = 64),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (tenant_id, project_id, job_id),
    UNIQUE (tenant_id, project_id, actor_id, idempotency_key),
    CHECK (
      (state = 'COMPLETED' AND proof_json IS NOT NULL AND proof_digest IS NOT NULL AND completed_at IS NOT NULL)
      OR
      (state <> 'COMPLETED' AND proof_json IS NULL AND proof_digest IS NULL AND completed_at IS NULL)
    )
) WITHOUT ROWID;

CREATE TABLE governance_deletion_commands (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    store_kind TEXT NOT NULL,
    object_id TEXT NOT NULL,
    object_version TEXT NOT NULL,
    object_digest TEXT NOT NULL CHECK (length(object_digest) = 64),
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    command_digest TEXT NOT NULL CHECK (length(command_digest) = 64),
    state TEXT NOT NULL CHECK (state IN ('PENDING','CLAIMED','UNKNOWN','VERIFIED','BLOCKED')),
    attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0 AND attempt <= 100),
    claim_token_digest TEXT CHECK (claim_token_digest IS NULL OR length(claim_token_digest) = 64),
    execution_receipt_digest TEXT CHECK (execution_receipt_digest IS NULL OR length(execution_receipt_digest) = 64),
    verification_receipt_digest TEXT CHECK (verification_receipt_digest IS NULL OR length(verification_receipt_digest) = 64),
    failure_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, command_id),
    UNIQUE (tenant_id, project_id, job_id, store_kind, object_id, object_version),
    FOREIGN KEY (tenant_id, project_id, job_id)
      REFERENCES governance_deletion_jobs (tenant_id, project_id, job_id)
) WITHOUT ROWID;

CREATE TABLE governance_deletion_execution_receipts (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    receipt_digest TEXT NOT NULL CHECK (length(receipt_digest) = 64),
    executor_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, command_id),
    FOREIGN KEY (tenant_id, project_id, command_id)
      REFERENCES governance_deletion_commands (tenant_id, project_id, command_id)
) WITHOUT ROWID;

CREATE TABLE governance_deletion_verification_receipts (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    receipt_digest TEXT NOT NULL CHECK (length(receipt_digest) = 64),
    verifier_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, command_id),
    FOREIGN KEY (tenant_id, project_id, command_id)
      REFERENCES governance_deletion_commands (tenant_id, project_id, command_id)
) WITHOUT ROWID;

CREATE TABLE governance_deletion_audit (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    audit_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    command_id TEXT,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    event_digest TEXT NOT NULL CHECK (length(event_digest) = 64),
    occurred_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, audit_id),
    FOREIGN KEY (tenant_id, project_id, job_id)
      REFERENCES governance_deletion_jobs (tenant_id, project_id, job_id)
) WITHOUT ROWID;

CREATE INDEX governance_deletion_command_queue
    ON governance_deletion_commands (tenant_id, project_id, state, created_at, command_id);
CREATE UNIQUE INDEX governance_deletion_claim_identity
    ON governance_deletion_commands (tenant_id, project_id, claim_token_digest)
    WHERE claim_token_digest IS NOT NULL;
CREATE INDEX governance_deletion_audit_job
    ON governance_deletion_audit (tenant_id, project_id, job_id, occurred_at, audit_id);

CREATE TRIGGER governance_deletion_jobs_scope_immutable
BEFORE UPDATE ON governance_deletion_jobs
WHEN NEW.tenant_id IS NOT OLD.tenant_id
  OR NEW.project_id IS NOT OLD.project_id
  OR NEW.job_id IS NOT OLD.job_id
  OR NEW.actor_id IS NOT OLD.actor_id
  OR NEW.idempotency_key IS NOT OLD.idempotency_key
  OR NEW.request_digest IS NOT OLD.request_digest
  OR NEW.policy_version IS NOT OLD.policy_version
  OR NEW.inventory_version IS NOT OLD.inventory_version
  OR NEW.inventory_digest IS NOT OLD.inventory_digest
  OR NEW.backup_delete_not_before IS NOT OLD.backup_delete_not_before
  OR NEW.legal_hold_count IS NOT OLD.legal_hold_count
  OR NEW.command_count IS NOT OLD.command_count
  OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT, 'GOVERNANCE_DELETION_JOB_BINDING_IMMUTABLE'); END;

CREATE TRIGGER governance_deletion_jobs_state_guard
BEFORE UPDATE ON governance_deletion_jobs
WHEN NOT (
    (NEW.state = OLD.state
      AND NEW.proof_json IS OLD.proof_json
      AND NEW.proof_digest IS OLD.proof_digest
      AND NEW.completed_at IS OLD.completed_at)
 OR (OLD.state = 'PENDING' AND NEW.state = 'RUNNING'
      AND NEW.proof_json IS NULL AND NEW.proof_digest IS NULL AND NEW.completed_at IS NULL)
 OR (OLD.state IN ('PENDING','RUNNING','UNKNOWN') AND NEW.state = 'UNKNOWN'
      AND NEW.proof_json IS NULL AND NEW.proof_digest IS NULL AND NEW.completed_at IS NULL)
 OR (OLD.state IN ('RUNNING','UNKNOWN') AND NEW.state = 'BLOCKED'
      AND NEW.proof_json IS NULL AND NEW.proof_digest IS NULL AND NEW.completed_at IS NULL)
 OR (OLD.state IN ('RUNNING','UNKNOWN') AND NEW.state = 'COMPLETED'
      AND NEW.proof_json IS NOT NULL AND NEW.proof_digest IS NOT NULL AND NEW.completed_at IS NOT NULL)
)
BEGIN SELECT RAISE(ABORT, 'GOVERNANCE_DELETION_JOB_TRANSITION_INVALID'); END;

CREATE TRIGGER governance_deletion_commands_binding_immutable
BEFORE UPDATE ON governance_deletion_commands
WHEN NEW.tenant_id IS NOT OLD.tenant_id
  OR NEW.project_id IS NOT OLD.project_id
  OR NEW.command_id IS NOT OLD.command_id
  OR NEW.job_id IS NOT OLD.job_id
  OR NEW.store_kind IS NOT OLD.store_kind
  OR NEW.object_id IS NOT OLD.object_id
  OR NEW.object_version IS NOT OLD.object_version
  OR NEW.object_digest IS NOT OLD.object_digest
  OR NEW.byte_count IS NOT OLD.byte_count
  OR NEW.command_digest IS NOT OLD.command_digest
  OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT, 'GOVERNANCE_DELETION_COMMAND_BINDING_IMMUTABLE'); END;

CREATE TRIGGER governance_deletion_commands_state_guard
BEFORE UPDATE ON governance_deletion_commands
WHEN NOT (
    (OLD.state = 'PENDING' AND NEW.state = 'CLAIMED'
      AND NEW.attempt = OLD.attempt + 1
      AND NEW.claim_token_digest IS NOT NULL
      AND NEW.execution_receipt_digest IS NULL
      AND NEW.verification_receipt_digest IS NULL)
 OR (OLD.state = 'CLAIMED' AND NEW.state = 'UNKNOWN'
      AND NEW.attempt = OLD.attempt
      AND NEW.claim_token_digest IS OLD.claim_token_digest
      AND NEW.execution_receipt_digest IS NOT NULL
      AND NEW.verification_receipt_digest IS NULL)
 OR (OLD.state = 'UNKNOWN' AND NEW.state = 'VERIFIED'
      AND NEW.attempt = OLD.attempt
      AND NEW.claim_token_digest IS OLD.claim_token_digest
      AND NEW.execution_receipt_digest IS OLD.execution_receipt_digest
      AND NEW.verification_receipt_digest IS NOT NULL)
 OR (OLD.state = 'UNKNOWN' AND NEW.state = 'BLOCKED'
      AND NEW.attempt = OLD.attempt
      AND NEW.claim_token_digest IS OLD.claim_token_digest
      AND NEW.execution_receipt_digest IS OLD.execution_receipt_digest
      AND NEW.verification_receipt_digest IS NOT NULL)
)
BEGIN SELECT RAISE(ABORT, 'GOVERNANCE_DELETION_COMMAND_TRANSITION_INVALID'); END;

CREATE TRIGGER governance_deletion_jobs_no_delete BEFORE DELETE ON governance_deletion_jobs BEGIN SELECT RAISE(ABORT, 'GOVERNANCE_DELETION_JOB_IMMUTABLE'); END;
CREATE TRIGGER governance_deletion_commands_no_delete BEFORE DELETE ON governance_deletion_commands BEGIN SELECT RAISE(ABORT, 'GOVERNANCE_DELETION_COMMAND_IMMUTABLE'); END;
CREATE TRIGGER governance_deletion_execution_receipts_no_update BEFORE UPDATE ON governance_deletion_execution_receipts BEGIN SELECT RAISE(ABORT, 'GOVERNANCE_DELETION_RECEIPT_IMMUTABLE'); END;
CREATE TRIGGER governance_deletion_execution_receipts_no_delete BEFORE DELETE ON governance_deletion_execution_receipts BEGIN SELECT RAISE(ABORT, 'GOVERNANCE_DELETION_RECEIPT_IMMUTABLE'); END;
CREATE TRIGGER governance_deletion_verification_receipts_no_update BEFORE UPDATE ON governance_deletion_verification_receipts BEGIN SELECT RAISE(ABORT, 'GOVERNANCE_DELETION_VERIFICATION_IMMUTABLE'); END;
CREATE TRIGGER governance_deletion_verification_receipts_no_delete BEFORE DELETE ON governance_deletion_verification_receipts BEGIN SELECT RAISE(ABORT, 'GOVERNANCE_DELETION_VERIFICATION_IMMUTABLE'); END;
CREATE TRIGGER governance_deletion_audit_no_update BEFORE UPDATE ON governance_deletion_audit BEGIN SELECT RAISE(ABORT, 'GOVERNANCE_DELETION_AUDIT_IMMUTABLE'); END;
CREATE TRIGGER governance_deletion_audit_no_delete BEFORE DELETE ON governance_deletion_audit BEGIN SELECT RAISE(ABORT, 'GOVERNANCE_DELETION_AUDIT_IMMUTABLE'); END;

PRAGMA user_version = 18;
COMMIT;
