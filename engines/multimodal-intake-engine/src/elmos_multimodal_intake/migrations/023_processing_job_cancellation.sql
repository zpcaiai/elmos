PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

ALTER TABLE processing_jobs
    ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0
    CHECK (cancel_requested IN (0, 1));

ALTER TABLE processing_jobs
    ADD COLUMN cancel_requested_by TEXT;

ALTER TABLE processing_jobs
    ADD COLUMN cancel_requested_at TEXT;

ALTER TABLE processing_jobs
    ADD COLUMN cancel_reason TEXT;

CREATE TRIGGER processing_jobs_cancellation_insert_guard
BEFORE INSERT ON processing_jobs
FOR EACH ROW
WHEN
    (NEW.cancel_requested = 0 AND (
        NEW.cancel_requested_by IS NOT NULL
        OR NEW.cancel_requested_at IS NOT NULL
        OR NEW.cancel_reason IS NOT NULL
    ))
    OR
    (NEW.cancel_requested = 1 AND (
        NEW.cancel_requested_by IS NULL
        OR length(NEW.cancel_requested_by) = 0
        OR length(NEW.cancel_requested_by) > 255
        OR NEW.cancel_requested_at IS NULL
        OR length(NEW.cancel_requested_at) = 0
        OR NEW.cancel_reason IS NULL
        OR length(NEW.cancel_reason) = 0
        OR length(NEW.cancel_reason) > 128
    ))
BEGIN
    SELECT RAISE(ABORT, 'processing_job_cancellation_metadata_invalid');
END;

CREATE TRIGGER processing_jobs_cancellation_metadata_guard
BEFORE UPDATE OF cancel_requested, cancel_requested_by, cancel_requested_at, cancel_reason
ON processing_jobs
FOR EACH ROW
WHEN
    (OLD.cancel_requested = 1 AND (
        NEW.cancel_requested <> 1
        OR NEW.cancel_requested_by IS NOT OLD.cancel_requested_by
        OR NEW.cancel_requested_at IS NOT OLD.cancel_requested_at
        OR NEW.cancel_reason IS NOT OLD.cancel_reason
    ))
    OR
    (NEW.cancel_requested = 0 AND (
        NEW.cancel_requested_by IS NOT NULL
        OR NEW.cancel_requested_at IS NOT NULL
        OR NEW.cancel_reason IS NOT NULL
    ))
    OR
    (NEW.cancel_requested = 1 AND (
        NEW.cancel_requested_by IS NULL
        OR length(NEW.cancel_requested_by) = 0
        OR length(NEW.cancel_requested_by) > 255
        OR NEW.cancel_requested_at IS NULL
        OR length(NEW.cancel_requested_at) = 0
        OR NEW.cancel_reason IS NULL
        OR length(NEW.cancel_reason) = 0
        OR length(NEW.cancel_reason) > 128
    ))
BEGIN
    SELECT RAISE(ABORT, 'processing_job_cancellation_metadata_immutable');
END;

CREATE INDEX processing_jobs_cancellation_idx
    ON processing_jobs (tenant_id, project_id, cancel_requested, cancel_requested_at)
    WHERE cancel_requested = 1;

PRAGMA user_version = 23;
COMMIT;
