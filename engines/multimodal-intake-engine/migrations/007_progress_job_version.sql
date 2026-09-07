PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

ALTER TABLE processing_jobs
    ADD COLUMN version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1);

PRAGMA user_version = 7;
COMMIT;
