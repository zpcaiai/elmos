PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

ALTER TABLE skill_execution_receipts
    ADD COLUMN dispatch_started_at TEXT;

-- An older IN_PROGRESS row may already have crossed the effect boundary, but
-- the v1 schema could not say so.  Upgrade it fail-closed: a fresh caller must
-- reconcile rather than assume that lease expiry makes replay safe.
UPDATE skill_execution_receipts
   SET dispatch_started_at = updated_at
 WHERE status = 'IN_PROGRESS';

CREATE INDEX skill_execution_receipts_dispatch_idx
    ON skill_execution_receipts (
        tenant_id, project_id, actor_id, skill, idempotency_key
    )
 WHERE status = 'IN_PROGRESS' AND dispatch_started_at IS NOT NULL;

PRAGMA user_version = 9;
COMMIT;
