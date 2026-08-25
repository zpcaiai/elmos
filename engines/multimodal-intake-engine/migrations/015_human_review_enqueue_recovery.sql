PRAGMA foreign_keys = ON;

BEGIN IMMEDIATE;

CREATE TABLE human_review_enqueue_preparations (
    preparation_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    recovery_handle_digest TEXT NOT NULL CHECK(length(recovery_handle_digest) = 64),
    execute_idempotency_key_digest TEXT NOT NULL CHECK(length(execute_idempotency_key_digest) = 64),
    enqueue_input_json TEXT NOT NULL,
    enqueue_input_digest TEXT NOT NULL CHECK(length(enqueue_input_digest) = 64),
    prepare_request_digest TEXT NOT NULL CHECK(length(prepare_request_digest) = 64),
    state TEXT NOT NULL CHECK(state IN ('PREPARED','EXECUTED')),
    expires_at TEXT NOT NULL,
    prepared_at TEXT NOT NULL,
    executed_at TEXT,
    task_id TEXT,
    UNIQUE (tenant_id, project_id, actor_id, preparation_id),
    UNIQUE (tenant_id, project_id, actor_id, recovery_handle_digest),
    FOREIGN KEY (tenant_id, project_id, task_id)
        REFERENCES human_review_tasks(tenant_id, project_id, task_id)
        ON UPDATE NO ACTION ON DELETE NO ACTION,
    CHECK (
        (state = 'PREPARED' AND executed_at IS NULL AND task_id IS NULL)
        OR
        (state = 'EXECUTED' AND executed_at IS NOT NULL AND task_id IS NOT NULL)
    )
);

CREATE INDEX idx_human_review_enqueue_preparations_expiry
    ON human_review_enqueue_preparations(tenant_id, project_id, actor_id, expires_at);

CREATE TRIGGER trg_human_review_enqueue_preparations_no_delete
BEFORE DELETE ON human_review_enqueue_preparations
BEGIN
    SELECT RAISE(ABORT, 'human review enqueue preparation deletion forbidden');
END;

CREATE TRIGGER trg_human_review_enqueue_preparations_immutable_identity
BEFORE UPDATE ON human_review_enqueue_preparations
WHEN NEW.preparation_id <> OLD.preparation_id
  OR NEW.tenant_id <> OLD.tenant_id
  OR NEW.project_id <> OLD.project_id
  OR NEW.actor_id <> OLD.actor_id
  OR NEW.recovery_handle_digest <> OLD.recovery_handle_digest
  OR NEW.execute_idempotency_key_digest <> OLD.execute_idempotency_key_digest
  OR NEW.enqueue_input_json <> OLD.enqueue_input_json
  OR NEW.enqueue_input_digest <> OLD.enqueue_input_digest
  OR NEW.prepare_request_digest <> OLD.prepare_request_digest
  OR NEW.expires_at <> OLD.expires_at
  OR NEW.prepared_at <> OLD.prepared_at
BEGIN
    SELECT RAISE(ABORT, 'human review enqueue preparation identity is immutable');
END;

CREATE TRIGGER trg_human_review_enqueue_preparations_transition_guard
BEFORE UPDATE ON human_review_enqueue_preparations
WHEN OLD.state <> 'PREPARED'
  OR NEW.state <> 'EXECUTED'
  OR NEW.executed_at IS NULL
  OR NEW.task_id IS NULL
BEGIN
    SELECT RAISE(ABORT, 'invalid human review enqueue preparation transition');
END;

PRAGMA user_version = 15;

COMMIT;
