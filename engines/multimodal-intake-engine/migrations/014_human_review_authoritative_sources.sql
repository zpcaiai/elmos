PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE human_review_source_producer_capabilities (
    capability_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    producer_id TEXT NOT NULL,
    token_digest TEXT NOT NULL CHECK (length(token_digest) = 64),
    source_kinds_json TEXT NOT NULL,
    source_kinds_digest TEXT NOT NULL CHECK (length(source_kinds_digest) = 64),
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (
        (revoked_at IS NULL AND version = 1)
        OR (revoked_at IS NOT NULL AND version = 2)
    ),
    UNIQUE (tenant_id, project_id, capability_id),
    UNIQUE (tenant_id, project_id, producer_id, token_digest)
);
CREATE INDEX human_review_source_producer_capability_lookup_idx
    ON human_review_source_producer_capabilities (
        tenant_id, project_id, producer_id, capability_id, expires_at
    ) WHERE revoked_at IS NULL;

CREATE TABLE human_review_source_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    asset_version INTEGER NOT NULL CHECK (asset_version >= 1),
    target_kind TEXT NOT NULL CHECK (target_kind IN (
        'TEXT','SPEAKER','TIME_RANGE','BBOX','TABLE','REQUIREMENT','CONFLICT'
    )),
    target_json TEXT NOT NULL,
    target_digest TEXT NOT NULL CHECK (length(target_digest) = 64),
    original_value_json TEXT NOT NULL,
    original_value_digest TEXT NOT NULL CHECK (length(original_value_digest) = 64),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    asset_sha256 TEXT NOT NULL CHECK (length(asset_sha256) = 64),
    source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
    provenance_json TEXT NOT NULL,
    provenance_digest TEXT NOT NULL CHECK (length(provenance_digest) = 64),
    producer_capability_id TEXT NOT NULL,
    producer_actor_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    snapshot_digest TEXT NOT NULL CHECK (length(snapshot_digest) = 64),
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, snapshot_id),
    UNIQUE (
        tenant_id, project_id, asset_id, asset_version, target_kind, target_digest
    ),
    UNIQUE (tenant_id, project_id, producer_actor_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id, asset_id)
        REFERENCES input_assets (tenant_id, project_id, asset_id),
    FOREIGN KEY (tenant_id, project_id, producer_capability_id)
        REFERENCES human_review_source_producer_capabilities (
            tenant_id, project_id, capability_id
        )
);
CREATE INDEX human_review_source_snapshots_lookup_idx
    ON human_review_source_snapshots (
        tenant_id, project_id, asset_id, asset_version,
        target_kind, target_digest, created_at
    );

CREATE TABLE human_review_source_collection_generations (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    asset_version INTEGER NOT NULL CHECK (asset_version >= 1),
    generation INTEGER NOT NULL CHECK (generation >= 1),
    PRIMARY KEY (tenant_id, project_id, asset_id, asset_version),
    FOREIGN KEY (tenant_id, project_id, asset_id)
        REFERENCES input_assets (tenant_id, project_id, asset_id)
);

CREATE TABLE human_review_target_heads (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    asset_version INTEGER NOT NULL CHECK (asset_version >= 1),
    target_kind TEXT NOT NULL CHECK (target_kind IN (
        'TEXT','SPEAKER','TIME_RANGE','BBOX','TABLE','REQUIREMENT','CONFLICT'
    )),
    target_json TEXT NOT NULL,
    target_digest TEXT NOT NULL CHECK (length(target_digest) = 64),
    base_snapshot_id TEXT NOT NULL,
    current_value_json TEXT NOT NULL,
    current_value_digest TEXT NOT NULL CHECK (length(current_value_digest) = 64),
    source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
    provenance_digest TEXT NOT NULL CHECK (length(provenance_digest) = 64),
    source_decision_id TEXT,
    correction_version INTEGER NOT NULL DEFAULT 0 CHECK (correction_version >= 0),
    direction TEXT NOT NULL CHECK (direction IN ('SNAPSHOT','APPLY','REVERT')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    updated_at TEXT NOT NULL,
    CHECK (
        (direction = 'SNAPSHOT' AND source_decision_id IS NULL AND correction_version = 0)
        OR (direction = 'APPLY' AND source_decision_id IS NOT NULL AND correction_version >= 1)
        OR (direction = 'REVERT' AND source_decision_id IS NOT NULL)
    ),
    PRIMARY KEY (
        tenant_id, project_id, asset_id, asset_version, target_kind, target_digest
    ),
    FOREIGN KEY (tenant_id, project_id, asset_id)
        REFERENCES input_assets (tenant_id, project_id, asset_id),
    FOREIGN KEY (tenant_id, project_id, base_snapshot_id)
        REFERENCES human_review_source_snapshots (
            tenant_id, project_id, snapshot_id
        ),
    FOREIGN KEY (tenant_id, project_id, source_decision_id)
        REFERENCES human_review_decisions (tenant_id, project_id, decision_id)
);
CREATE INDEX human_review_target_heads_decision_idx
    ON human_review_target_heads (
        tenant_id, project_id, source_decision_id, updated_at
    ) WHERE source_decision_id IS NOT NULL;

CREATE TRIGGER human_review_source_snapshots_no_update
BEFORE UPDATE ON human_review_source_snapshots
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_SOURCE_SNAPSHOT_IMMUTABLE');
END;
CREATE TRIGGER human_review_source_producer_capabilities_no_delete
BEFORE DELETE ON human_review_source_producer_capabilities
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_SOURCE_PRODUCER_HISTORY_IMMUTABLE');
END;
CREATE TRIGGER human_review_source_producer_capabilities_identity_no_update
BEFORE UPDATE ON human_review_source_producer_capabilities
WHEN NEW.capability_id IS NOT OLD.capability_id
  OR NEW.tenant_id IS NOT OLD.tenant_id
  OR NEW.project_id IS NOT OLD.project_id
  OR NEW.producer_id IS NOT OLD.producer_id
  OR NEW.token_digest IS NOT OLD.token_digest
  OR NEW.source_kinds_json IS NOT OLD.source_kinds_json
  OR NEW.source_kinds_digest IS NOT OLD.source_kinds_digest
  OR NEW.expires_at IS NOT OLD.expires_at
  OR NEW.created_by IS NOT OLD.created_by
  OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_SOURCE_PRODUCER_IDENTITY_IMMUTABLE');
END;
CREATE TRIGGER human_review_source_producer_capabilities_state_transition
BEFORE UPDATE ON human_review_source_producer_capabilities
WHEN NOT (
    OLD.revoked_at IS NULL
    AND NEW.revoked_at IS NOT NULL
    AND NEW.version = OLD.version + 1
)
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_SOURCE_PRODUCER_STATE_INVALID');
END;
CREATE TRIGGER human_review_source_snapshots_no_delete
BEFORE DELETE ON human_review_source_snapshots
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_SOURCE_SNAPSHOT_IMMUTABLE');
END;
CREATE TRIGGER human_review_target_heads_identity_no_update
BEFORE UPDATE ON human_review_target_heads
WHEN NEW.tenant_id IS NOT OLD.tenant_id
  OR NEW.project_id IS NOT OLD.project_id
  OR NEW.asset_id IS NOT OLD.asset_id
  OR NEW.asset_version IS NOT OLD.asset_version
  OR NEW.target_kind IS NOT OLD.target_kind
  OR NEW.target_json IS NOT OLD.target_json
  OR NEW.target_digest IS NOT OLD.target_digest
  OR NEW.base_snapshot_id IS NOT OLD.base_snapshot_id
  OR NEW.source_digest IS NOT OLD.source_digest
  OR NEW.provenance_digest IS NOT OLD.provenance_digest
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_TARGET_HEAD_IDENTITY_IMMUTABLE');
END;
CREATE TRIGGER human_review_target_heads_state_transition
BEFORE UPDATE ON human_review_target_heads
WHEN NOT (
    NEW.version = OLD.version + 1
    AND NEW.direction IN ('APPLY','REVERT')
    AND NEW.source_decision_id IS NOT NULL
    AND NEW.source_decision_id IS NOT OLD.source_decision_id
)
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_TARGET_HEAD_STATE_INVALID');
END;
CREATE TRIGGER human_review_target_heads_lineage_guard
BEFORE UPDATE ON human_review_target_heads
WHEN NEW.direction IN ('APPLY','REVERT') AND NOT (
    EXISTS (
        SELECT 1
          FROM human_review_decisions AS d
          JOIN human_review_tasks AS t
            ON t.tenant_id = d.tenant_id
           AND t.project_id = d.project_id
           AND t.task_id = d.task_id
          JOIN human_review_correction_versions AS c
            ON c.tenant_id = d.tenant_id
           AND c.project_id = d.project_id
           AND c.task_id = d.task_id
           AND c.correction_version = d.correction_version
         WHERE d.tenant_id = NEW.tenant_id
           AND d.project_id = NEW.project_id
           AND d.decision_id = NEW.source_decision_id
           AND d.decision = CASE NEW.direction
               WHEN 'APPLY' THEN 'APPROVE' ELSE 'REVERT' END
           AND t.asset_id = NEW.asset_id
           AND t.target_kind = NEW.target_kind
           AND t.target_json = NEW.target_json
           AND t.target_digest = NEW.target_digest
           AND t.source_digest = d.source_digest
           AND c.target_kind = NEW.target_kind
           AND c.target_json = NEW.target_json
           AND c.correction_digest = d.correction_digest
           AND c.source_digest = d.source_digest
           AND (
               (NEW.direction = 'APPLY'
                AND NEW.correction_version = d.correction_version
                AND NEW.current_value_json = c.corrected_value_json
                AND NEW.current_value_digest = c.corrected_value_digest)
               OR
               (NEW.direction = 'REVERT'
                AND NEW.correction_version < d.correction_version)
           )
    )
    AND (
        SELECT count(*)
          FROM human_review_effective_projections AS p
          JOIN human_review_decisions AS d
            ON d.tenant_id = p.tenant_id
           AND d.project_id = p.project_id
           AND d.task_id = p.task_id
           AND d.decision_id = p.source_decision_id
         WHERE p.tenant_id = NEW.tenant_id
           AND p.project_id = NEW.project_id
           AND p.source_decision_id = NEW.source_decision_id
           AND p.correction_version = d.correction_version
           AND p.direction = NEW.direction
           AND p.target_kind = NEW.target_kind
           AND p.target_json = NEW.target_json
           AND p.effective_value_json = NEW.current_value_json
           AND p.effective_value_digest = NEW.current_value_digest
           AND p.source_digest = d.source_digest
    ) = 4
)
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_TARGET_HEAD_LINEAGE_INVALID');
END;
CREATE TRIGGER human_review_source_collection_generation_monotonic
BEFORE UPDATE ON human_review_source_collection_generations
WHEN NEW.tenant_id IS NOT OLD.tenant_id
  OR NEW.project_id IS NOT OLD.project_id
  OR NEW.asset_id IS NOT OLD.asset_id
  OR NEW.asset_version IS NOT OLD.asset_version
  OR NEW.generation != OLD.generation + 1
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_SOURCE_GENERATION_INVALID');
END;
CREATE TRIGGER human_review_source_collection_generation_no_delete
BEFORE DELETE ON human_review_source_collection_generations
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_SOURCE_GENERATION_IMMUTABLE');
END;
CREATE TRIGGER human_review_source_generation_head_insert
AFTER INSERT ON human_review_target_heads
BEGIN
    INSERT INTO human_review_source_collection_generations (
        tenant_id,project_id,asset_id,asset_version,generation
    ) VALUES (NEW.tenant_id,NEW.project_id,NEW.asset_id,NEW.asset_version,1)
    ON CONFLICT(tenant_id,project_id,asset_id,asset_version) DO UPDATE SET
        generation=human_review_source_collection_generations.generation+1;
END;
CREATE TRIGGER human_review_source_generation_snapshot_update
AFTER UPDATE ON human_review_source_snapshots
BEGIN
    UPDATE human_review_source_collection_generations
       SET generation=generation+1
     WHERE tenant_id=NEW.tenant_id AND project_id=NEW.project_id
       AND asset_id=NEW.asset_id AND asset_version=NEW.asset_version;
END;
CREATE TRIGGER human_review_source_generation_head_update
AFTER UPDATE ON human_review_target_heads
BEGIN
    UPDATE human_review_source_collection_generations
       SET generation=generation+1
     WHERE tenant_id=NEW.tenant_id AND project_id=NEW.project_id
       AND asset_id=NEW.asset_id AND asset_version=NEW.asset_version;
END;
CREATE TRIGGER human_review_source_generation_projection_insert
AFTER INSERT ON human_review_effective_projections
BEGIN
    UPDATE human_review_source_collection_generations
       SET generation=generation+1
     WHERE tenant_id=NEW.tenant_id AND project_id=NEW.project_id
       AND asset_id=(SELECT asset_id FROM human_review_tasks
                      WHERE tenant_id=NEW.tenant_id AND project_id=NEW.project_id
                        AND task_id=NEW.task_id);
END;
CREATE TRIGGER human_review_source_generation_projection_update
AFTER UPDATE ON human_review_effective_projections
BEGIN
    UPDATE human_review_source_collection_generations
       SET generation=generation+1
     WHERE tenant_id=NEW.tenant_id AND project_id=NEW.project_id
       AND asset_id=(SELECT asset_id FROM human_review_tasks
                      WHERE tenant_id=NEW.tenant_id AND project_id=NEW.project_id
                        AND task_id=NEW.task_id);
END;
CREATE TRIGGER human_review_source_generation_propagation_update
AFTER UPDATE ON human_review_propagation_tasks
WHEN EXISTS (
    SELECT 1 FROM human_review_target_heads
     WHERE tenant_id=OLD.tenant_id AND project_id=OLD.project_id
       AND source_decision_id=OLD.decision_id
)
BEGIN
    UPDATE human_review_source_collection_generations
       SET generation=generation+1
     WHERE tenant_id=OLD.tenant_id AND project_id=OLD.project_id
       AND asset_id=(SELECT asset_id FROM human_review_tasks
                      WHERE tenant_id=OLD.tenant_id AND project_id=OLD.project_id
                        AND task_id=OLD.task_id);
END;
CREATE TRIGGER human_review_source_generation_task_effective_update
AFTER UPDATE OF effective_version,effective_digest ON human_review_tasks
WHEN NEW.effective_version IS NOT OLD.effective_version
  OR NEW.effective_digest IS NOT OLD.effective_digest
BEGIN
    UPDATE human_review_source_collection_generations
       SET generation=generation+1
     WHERE tenant_id=NEW.tenant_id AND project_id=NEW.project_id
       AND asset_id=NEW.asset_id;
END;
CREATE TRIGGER human_review_target_heads_no_delete
BEFORE DELETE ON human_review_target_heads
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_TARGET_HEAD_IMMUTABLE');
END;

PRAGMA user_version = 14;
COMMIT;
