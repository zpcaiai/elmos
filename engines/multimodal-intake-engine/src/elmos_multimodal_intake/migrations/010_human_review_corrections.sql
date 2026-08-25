PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE human_review_corrections (
    correction_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    source_version INTEGER NOT NULL CHECK (source_version >= 1),
    version INTEGER NOT NULL CHECK (version = source_version + 1),
    source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
    source_json TEXT NOT NULL,
    correction_digest TEXT NOT NULL CHECK (length(correction_digest) = 64),
    correction_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    policy_version TEXT NOT NULL,
    review_state_version TEXT NOT NULL,
    approval_state TEXT NOT NULL CHECK (approval_state = 'NOT_RUN'),
    rebuild_state TEXT NOT NULL CHECK (rebuild_state = 'NOT_RUN'),
    result_json TEXT NOT NULL,
    result_digest TEXT NOT NULL CHECK (length(result_digest) = 64),
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, correction_id),
    UNIQUE (tenant_id, project_id, asset_id, version),
    UNIQUE (tenant_id, project_id, actor_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id, asset_id)
        REFERENCES input_assets (tenant_id, project_id, asset_id)
);

CREATE INDEX human_review_corrections_latest_idx
    ON human_review_corrections (
        tenant_id, project_id, asset_id, version DESC, correction_id
    );

-- A correction is an immutable content version and an exact idempotency
-- receipt.  New knowledge/rebuild results append separately; neither may
-- rewrite or erase the reviewed source version.
CREATE TRIGGER human_review_corrections_no_update
BEFORE UPDATE ON human_review_corrections
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_CORRECTION_IMMUTABLE');
END;

CREATE TRIGGER human_review_corrections_no_delete
BEFORE DELETE ON human_review_corrections
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_CORRECTION_IMMUTABLE');
END;

PRAGMA user_version = 10;
COMMIT;
