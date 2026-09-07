PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

ALTER TABLE skill_execution_receipts
    ADD COLUMN response_digest TEXT
    CHECK (
        response_digest IS NULL
        OR (
            typeof(response_digest) = 'text'
            AND length(response_digest) = 64
            AND response_digest NOT GLOB '*[^0-9a-f]*'
        )
    );

-- Existing COMPLETED rows deliberately remain NULL.  Their bytes were never
-- digest-bound, so replay must enter explicit reconciliation instead of
-- manufacturing trust by backfilling a digest during migration.

PRAGMA user_version = 12;
COMMIT;
