PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

-- Existing payloads predate a trustworthy digest.  NULL is therefore an
-- explicit fail-closed legacy marker; it must never be backfilled from the
-- same mutable bytes it is supposed to authenticate.
ALTER TABLE outbox_events
    ADD COLUMN payload_digest TEXT
        CHECK (
            payload_digest IS NULL
            OR (
                typeof(payload_digest) = 'text'
                AND length(payload_digest) = 64
                AND payload_digest NOT GLOB '*[^0-9a-f]*'
            )
        );

PRAGMA user_version = 13;
COMMIT;
