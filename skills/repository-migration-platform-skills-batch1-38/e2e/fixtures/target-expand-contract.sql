BEGIN;

CREATE TABLE IF NOT EXISTS rmp_schema_migrations (
    version text PRIMARY KEY,
    checksum text NOT NULL,
    applied_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $migration_guard$
DECLARE
    observed text;
BEGIN
    SELECT checksum INTO observed
      FROM rmp_schema_migrations
     WHERE version = '002-provider-reference';
    IF observed IS NOT NULL AND observed <> '__CHECKSUM__' THEN
        RAISE EXCEPTION 'migration checksum drift: %', observed;
    END IF;
END;
$migration_guard$;

ALTER TABLE ledger_entries
    ADD COLUMN IF NOT EXISTS provider_reference text;

CREATE UNIQUE INDEX IF NOT EXISTS ledger_entries_provider_reference_uq
    ON ledger_entries(provider_reference)
    WHERE provider_reference IS NOT NULL;

INSERT INTO rmp_schema_migrations(version, checksum)
VALUES ('002-provider-reference', '__CHECKSUM__')
ON CONFLICT (version) DO NOTHING;

COMMIT;
