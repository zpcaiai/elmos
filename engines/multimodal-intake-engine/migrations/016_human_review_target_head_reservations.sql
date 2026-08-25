PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE human_review_target_head_reservations (
    reservation_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    asset_version INTEGER NOT NULL CHECK (asset_version >= 1),
    asset_content_digest TEXT NOT NULL CHECK (length(asset_content_digest) = 64),
    asset_sha256 TEXT NOT NULL CHECK (length(asset_sha256) = 64),
    target_kind TEXT NOT NULL CHECK (target_kind IN (
        'TEXT','SPEAKER','TIME_RANGE','BBOX','TABLE','REQUIREMENT','CONFLICT'
    )),
    target_digest TEXT NOT NULL CHECK (length(target_digest) = 64),
    snapshot_id TEXT NOT NULL,
    snapshot_digest TEXT NOT NULL CHECK (length(snapshot_digest) = 64),
    reserved_head_version INTEGER NOT NULL CHECK (reserved_head_version >= 1),
    reserved_head_value_digest TEXT NOT NULL
        CHECK (length(reserved_head_value_digest) = 64),
    task_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    decision_action TEXT NOT NULL CHECK (decision_action IN ('APPROVE','REVERT')),
    correction_version INTEGER NOT NULL CHECK (correction_version >= 1),
    correction_digest TEXT NOT NULL CHECK (length(correction_digest) = 64),
    source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
    source_ref_digest TEXT NOT NULL CHECK (length(source_ref_digest) = 64),
    parent_reservation_id TEXT,
    reservation_fence INTEGER NOT NULL CHECK (reservation_fence >= 1),
    binding_digest TEXT NOT NULL CHECK (length(binding_digest) = 64),
    state TEXT NOT NULL CHECK (state IN (
        'PROPAGATING','UNKNOWN','FAILED','APPLIED','REVERTED'
    )),
    state_version INTEGER NOT NULL DEFAULT 1 CHECK (state_version >= 1),
    materialized_head_version INTEGER
        CHECK (materialized_head_version IS NULL OR materialized_head_version >= 2),
    failure_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (tenant_id, project_id, reservation_id),
    UNIQUE (
        tenant_id, project_id, asset_id, asset_version, target_kind,
        target_digest, reserved_head_version
    ),
    UNIQUE (tenant_id, project_id, decision_id),
    UNIQUE (tenant_id, project_id, parent_reservation_id),
    FOREIGN KEY (tenant_id, project_id, task_id)
        REFERENCES human_review_tasks (tenant_id, project_id, task_id),
    FOREIGN KEY (tenant_id, project_id, task_id, correction_version)
        REFERENCES human_review_correction_versions (
            tenant_id, project_id, task_id, correction_version
        ),
    FOREIGN KEY (tenant_id, project_id, decision_id)
        REFERENCES human_review_decisions (tenant_id, project_id, decision_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (tenant_id, project_id, snapshot_id)
        REFERENCES human_review_source_snapshots (
            tenant_id, project_id, snapshot_id
        ),
    FOREIGN KEY (
        tenant_id, project_id, asset_id, asset_version, target_kind, target_digest
    ) REFERENCES human_review_target_heads (
        tenant_id, project_id, asset_id, asset_version, target_kind, target_digest
    ),
    FOREIGN KEY (tenant_id, project_id, parent_reservation_id)
        REFERENCES human_review_target_head_reservations (
            tenant_id, project_id, reservation_id
        ),
    CHECK (reservation_fence = reserved_head_version),
    CHECK (
        (decision_action = 'APPROVE' AND parent_reservation_id IS NULL)
        OR (decision_action = 'REVERT' AND parent_reservation_id IS NOT NULL)
    ),
    CHECK (
        (state IN ('PROPAGATING','UNKNOWN')
            AND materialized_head_version IS NULL
            AND failure_code IS NULL
            AND completed_at IS NULL)
        OR (state = 'FAILED'
            AND materialized_head_version IS NULL
            AND failure_code IS NOT NULL
            AND completed_at IS NOT NULL)
        OR (state = 'APPLIED'
            AND decision_action = 'APPROVE'
            AND materialized_head_version = reserved_head_version + 1
            AND failure_code IS NULL
            AND completed_at IS NOT NULL)
        OR (state = 'REVERTED'
            AND decision_action = 'REVERT'
            AND materialized_head_version = reserved_head_version + 1
            AND failure_code IS NULL
            AND completed_at IS NOT NULL)
    )
);

CREATE INDEX human_review_target_head_reservations_task_idx
    ON human_review_target_head_reservations (
        tenant_id, project_id, task_id, created_at, reservation_id
    );
CREATE INDEX human_review_target_head_reservations_state_idx
    ON human_review_target_head_reservations (
        tenant_id, project_id, state, updated_at, reservation_id
    ) WHERE state IN ('PROPAGATING','UNKNOWN','FAILED');

CREATE TRIGGER human_review_target_head_reservations_insert_guard
BEFORE INSERT ON human_review_target_head_reservations
WHEN NOT (
    NEW.state = 'PROPAGATING'
    AND NEW.state_version = 1
    AND NEW.materialized_head_version IS NULL
    AND NEW.failure_code IS NULL
    AND NEW.completed_at IS NULL
    AND NEW.reservation_fence = NEW.reserved_head_version
    AND EXISTS (
        SELECT 1 FROM input_assets AS asset
         WHERE asset.tenant_id = NEW.tenant_id
           AND asset.project_id = NEW.project_id
           AND asset.asset_id = NEW.asset_id
           AND asset.version = NEW.asset_version
           AND asset.sha256 = NEW.asset_sha256
           AND asset.cas_digest = NEW.asset_sha256
    )
    AND EXISTS (
        SELECT 1 FROM human_review_tasks AS task
         WHERE task.tenant_id = NEW.tenant_id
           AND task.project_id = NEW.project_id
           AND task.task_id = NEW.task_id
           AND task.asset_id = NEW.asset_id
           AND task.target_kind = NEW.target_kind
           AND task.target_digest = NEW.target_digest
           AND task.source_ref_digest = NEW.source_ref_digest
           AND json_extract(task.source_ref_json, '$.content_id') = NEW.asset_id
           AND json_extract(task.source_ref_json, '$.content_version') = NEW.asset_version
           AND json_extract(task.source_ref_json, '$.content_digest') = 'sha256:' || NEW.asset_content_digest
           AND json_extract(task.source_ref_json, '$.asset_sha256') = 'sha256:' || NEW.asset_sha256
           AND json_extract(task.source_ref_json, '$.target_kind') = NEW.target_kind
           AND json_extract(task.source_ref_json, '$.target_digest') = 'sha256:' || NEW.target_digest
    )
    AND EXISTS (
        SELECT 1 FROM human_review_correction_versions AS correction
         WHERE correction.tenant_id = NEW.tenant_id
           AND correction.project_id = NEW.project_id
           AND correction.task_id = NEW.task_id
           AND correction.correction_version = NEW.correction_version
           AND correction.correction_digest = NEW.correction_digest
           AND correction.source_digest = NEW.source_digest
           AND correction.target_kind = NEW.target_kind
    )
    AND EXISTS (
        SELECT 1 FROM human_review_source_snapshots AS snapshot
         WHERE snapshot.tenant_id = NEW.tenant_id
           AND snapshot.project_id = NEW.project_id
           AND snapshot.snapshot_id = NEW.snapshot_id
           AND snapshot.snapshot_digest = NEW.snapshot_digest
           AND snapshot.asset_id = NEW.asset_id
           AND snapshot.asset_version = NEW.asset_version
           AND snapshot.target_kind = NEW.target_kind
           AND snapshot.target_digest = NEW.target_digest
    )
    AND EXISTS (
        SELECT 1 FROM human_review_target_heads AS head
         WHERE head.tenant_id = NEW.tenant_id
           AND head.project_id = NEW.project_id
           AND head.asset_id = NEW.asset_id
           AND head.asset_version = NEW.asset_version
           AND head.target_kind = NEW.target_kind
           AND head.target_digest = NEW.target_digest
           AND head.base_snapshot_id = NEW.snapshot_id
           AND head.version = NEW.reserved_head_version
           AND head.current_value_digest = NEW.reserved_head_value_digest
    )
    AND (
        (NEW.decision_action = 'APPROVE'
            AND NEW.parent_reservation_id IS NULL
            AND EXISTS (
                SELECT 1 FROM human_review_tasks AS task
                 WHERE task.tenant_id = NEW.tenant_id
                   AND task.project_id = NEW.project_id
                   AND task.task_id = NEW.task_id
                   AND json_extract(task.source_ref_json, '$.snapshot_id') = NEW.snapshot_id
                   AND json_extract(task.source_ref_json, '$.snapshot_digest') = 'sha256:' || NEW.snapshot_digest
                   AND json_extract(task.source_ref_json, '$.head_version') = NEW.reserved_head_version
                   AND json_extract(task.source_ref_json, '$.head_value_digest') = 'sha256:' || NEW.reserved_head_value_digest
            ))
        OR (NEW.decision_action = 'REVERT'
            AND NEW.parent_reservation_id IS NOT NULL
            AND EXISTS (
                SELECT 1
                  FROM human_review_target_head_reservations AS parent
                  JOIN human_review_target_heads AS head
                    ON head.tenant_id = parent.tenant_id
                   AND head.project_id = parent.project_id
                   AND head.asset_id = parent.asset_id
                   AND head.asset_version = parent.asset_version
                   AND head.target_kind = parent.target_kind
                   AND head.target_digest = parent.target_digest
                 WHERE parent.tenant_id = NEW.tenant_id
                   AND parent.project_id = NEW.project_id
                   AND parent.reservation_id = NEW.parent_reservation_id
                   AND parent.decision_action = 'APPROVE'
                   AND parent.state = 'APPLIED'
                   AND parent.task_id = NEW.task_id
                   AND parent.correction_version = NEW.correction_version
                   AND parent.correction_digest = NEW.correction_digest
                   AND parent.materialized_head_version = NEW.reserved_head_version
                   AND head.source_decision_id = parent.decision_id
                   AND head.direction = 'APPLY'
            ))
    )
)
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_TARGET_HEAD_RESERVATION_BINDING_INVALID');
END;

CREATE TRIGGER human_review_target_head_reservations_identity_no_update
BEFORE UPDATE ON human_review_target_head_reservations
WHEN NEW.reservation_id IS NOT OLD.reservation_id
  OR NEW.tenant_id IS NOT OLD.tenant_id
  OR NEW.project_id IS NOT OLD.project_id
  OR NEW.asset_id IS NOT OLD.asset_id
  OR NEW.asset_version IS NOT OLD.asset_version
  OR NEW.asset_content_digest IS NOT OLD.asset_content_digest
  OR NEW.asset_sha256 IS NOT OLD.asset_sha256
  OR NEW.target_kind IS NOT OLD.target_kind
  OR NEW.target_digest IS NOT OLD.target_digest
  OR NEW.snapshot_id IS NOT OLD.snapshot_id
  OR NEW.snapshot_digest IS NOT OLD.snapshot_digest
  OR NEW.reserved_head_version IS NOT OLD.reserved_head_version
  OR NEW.reserved_head_value_digest IS NOT OLD.reserved_head_value_digest
  OR NEW.task_id IS NOT OLD.task_id
  OR NEW.decision_id IS NOT OLD.decision_id
  OR NEW.decision_action IS NOT OLD.decision_action
  OR NEW.correction_version IS NOT OLD.correction_version
  OR NEW.correction_digest IS NOT OLD.correction_digest
  OR NEW.source_digest IS NOT OLD.source_digest
  OR NEW.source_ref_digest IS NOT OLD.source_ref_digest
  OR NEW.parent_reservation_id IS NOT OLD.parent_reservation_id
  OR NEW.reservation_fence IS NOT OLD.reservation_fence
  OR NEW.binding_digest IS NOT OLD.binding_digest
  OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_TARGET_HEAD_RESERVATION_IMMUTABLE');
END;

CREATE TRIGGER human_review_target_head_reservations_state_transition
BEFORE UPDATE OF state,state_version,materialized_head_version,failure_code,updated_at,completed_at
ON human_review_target_head_reservations
WHEN NOT (
    NEW.state_version = OLD.state_version + 1
    AND (
        (OLD.state = 'PROPAGATING'
            AND NEW.state IN ('UNKNOWN','FAILED','APPLIED','REVERTED'))
        OR (OLD.state = 'UNKNOWN'
            AND NEW.state IN ('PROPAGATING','FAILED'))
    )
    AND (
        (NEW.state IN ('PROPAGATING','UNKNOWN')
            AND NEW.materialized_head_version IS NULL
            AND NEW.failure_code IS NULL
            AND NEW.completed_at IS NULL)
        OR (NEW.state = 'FAILED'
            AND NEW.materialized_head_version IS NULL
            AND NEW.failure_code IS NOT NULL
            AND NEW.completed_at IS NOT NULL)
        OR (NEW.state = 'APPLIED'
            AND NEW.decision_action = 'APPROVE'
            AND NEW.materialized_head_version = NEW.reserved_head_version + 1
            AND NEW.failure_code IS NULL
            AND NEW.completed_at IS NOT NULL)
        OR (NEW.state = 'REVERTED'
            AND NEW.decision_action = 'REVERT'
            AND NEW.materialized_head_version = NEW.reserved_head_version + 1
            AND NEW.failure_code IS NULL
            AND NEW.completed_at IS NOT NULL)
    )
    AND (
        (NEW.state = 'UNKNOWN' AND EXISTS (
            SELECT 1 FROM human_review_propagation_tasks AS propagation
             WHERE propagation.tenant_id = NEW.tenant_id
               AND propagation.project_id = NEW.project_id
               AND propagation.decision_id = NEW.decision_id
               AND propagation.state = 'UNKNOWN'
               AND propagation.reconciliation_required = 1
        ))
        OR (NEW.state = 'PROPAGATING' AND NOT EXISTS (
            SELECT 1 FROM human_review_propagation_tasks AS propagation
             WHERE propagation.tenant_id = NEW.tenant_id
               AND propagation.project_id = NEW.project_id
               AND propagation.decision_id = NEW.decision_id
               AND propagation.state IN ('UNKNOWN','FAILED')
        ))
        OR (NEW.state = 'FAILED' AND EXISTS (
            SELECT 1 FROM human_review_propagation_tasks AS propagation
             WHERE propagation.tenant_id = NEW.tenant_id
               AND propagation.project_id = NEW.project_id
               AND propagation.decision_id = NEW.decision_id
               AND propagation.state = 'FAILED'
               AND propagation.failure_code = NEW.failure_code
        ))
        OR (NEW.state IN ('APPLIED','REVERTED')
            AND EXISTS (
                SELECT 1 FROM human_review_target_heads AS head
                 WHERE head.tenant_id = NEW.tenant_id
                   AND head.project_id = NEW.project_id
                   AND head.asset_id = NEW.asset_id
                   AND head.asset_version = NEW.asset_version
                   AND head.target_kind = NEW.target_kind
                   AND head.target_digest = NEW.target_digest
                   AND head.version = NEW.materialized_head_version
                   AND head.source_decision_id = NEW.decision_id
                   AND head.direction = CASE NEW.state
                       WHEN 'APPLIED' THEN 'APPLY' ELSE 'REVERT' END
            )
            AND (
                SELECT count(*)
                  FROM human_review_propagation_tasks AS propagation
                 WHERE propagation.tenant_id = NEW.tenant_id
                   AND propagation.project_id = NEW.project_id
                   AND propagation.decision_id = NEW.decision_id
                   AND propagation.state = 'SUCCEEDED'
            ) = 4
            AND (
                SELECT count(*)
                  FROM human_review_effective_projections AS projection
                 WHERE projection.tenant_id = NEW.tenant_id
                   AND projection.project_id = NEW.project_id
                   AND projection.task_id = NEW.task_id
                   AND projection.source_decision_id = NEW.decision_id
                   AND projection.direction = CASE NEW.state
                       WHEN 'APPLIED' THEN 'APPLY' ELSE 'REVERT' END
            ) = 4)
    )
)
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_TARGET_HEAD_RESERVATION_STATE_INVALID');
END;

CREATE TRIGGER human_review_target_head_reservations_no_delete
BEFORE DELETE ON human_review_target_head_reservations
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_TARGET_HEAD_RESERVATION_IMMUTABLE');
END;

CREATE TRIGGER human_review_decisions_require_target_head_reservation
BEFORE INSERT ON human_review_decisions
WHEN NEW.decision IN ('APPROVE','REVERT') AND NOT EXISTS (
    SELECT 1 FROM human_review_target_head_reservations AS reservation
     WHERE reservation.tenant_id = NEW.tenant_id
       AND reservation.project_id = NEW.project_id
       AND reservation.task_id = NEW.task_id
       AND reservation.decision_id = NEW.decision_id
       AND reservation.decision_action = NEW.decision
       AND reservation.correction_version = NEW.correction_version
       AND reservation.correction_digest = NEW.correction_digest
       AND reservation.source_digest = NEW.source_digest
       AND reservation.state = 'PROPAGATING'
)
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_DECISION_RESERVATION_REQUIRED');
END;

CREATE TRIGGER human_review_propagations_require_target_head_reservation
BEFORE INSERT ON human_review_propagation_tasks
WHEN NOT EXISTS (
    SELECT 1 FROM human_review_target_head_reservations AS reservation
     WHERE reservation.tenant_id = NEW.tenant_id
       AND reservation.project_id = NEW.project_id
       AND reservation.task_id = NEW.task_id
       AND reservation.decision_id = NEW.decision_id
       AND reservation.correction_version = NEW.correction_version
       AND reservation.state = 'PROPAGATING'
       AND json_extract(NEW.payload_json, '$.schema_version') = 'human-review-propagation-v2'
       AND json_extract(NEW.payload_json, '$.tenant_id') = NEW.tenant_id
       AND json_extract(NEW.payload_json, '$.project_id') = NEW.project_id
       AND json_extract(NEW.payload_json, '$.task_id') = NEW.task_id
       AND json_extract(NEW.payload_json, '$.decision_id') = NEW.decision_id
       AND json_extract(NEW.payload_json, '$.correction_version') = NEW.correction_version
       AND json_extract(NEW.payload_json, '$.correction_digest') = 'sha256:' || reservation.correction_digest
       AND json_extract(NEW.payload_json, '$.source_digest') = 'sha256:' || reservation.source_digest
       AND json_extract(NEW.payload_json, '$.channel') = NEW.channel
       AND json_extract(NEW.payload_json, '$.direction') = NEW.direction
       AND json_extract(NEW.payload_json, '$.reservation_id') = reservation.reservation_id
       AND json_extract(NEW.payload_json, '$.reservation_fence') = reservation.reservation_fence
       AND json_extract(NEW.payload_json, '$.reservation_binding_digest') = 'sha256:' || reservation.binding_digest
)
BEGIN
    SELECT RAISE(ABORT, 'HUMAN_REVIEW_PROPAGATION_RESERVATION_REQUIRED');
END;

PRAGMA user_version = 16;
COMMIT;
