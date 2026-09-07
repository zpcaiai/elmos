-- Column types the ELMOS implementation actually stores.
--
-- Two corrections to the package's reference schema (0001_init.sql), kept in
-- their own migration so that file stays byte-identical to the shipped package:
--
-- 1. Identifiers are human-readable prefixed strings (``sf_``, ``cp_``,
--    ``snap_``, ``evt_``, ``pin_``) rather than bare UUIDs, so an operator
--    reading a log or a journal line can tell what kind of thing an id refers
--    to. That is worth more than the 16 bytes a ``uuid`` column saves.
-- 2. Lease expiry, heartbeats and TTLs are stored as epoch seconds
--    (``double precision``) so they are comparable against the injectable
--    clock without a timezone round-trip. Wall-clock timestamps used purely
--    for display stay ``timestamptz``.

-- The referencing column has to move with the referenced one, so the foreign
-- key is dropped and re-created around the type change.
ALTER TABLE runs      DROP CONSTRAINT IF EXISTS runs_snapshot_id_fkey;
ALTER TABLE snapshots ALTER COLUMN snapshot_id TYPE text USING snapshot_id::text;
ALTER TABLE snapshots ALTER COLUMN snapshot_id DROP DEFAULT;
ALTER TABLE runs      ALTER COLUMN snapshot_id TYPE text USING snapshot_id::text;
ALTER TABLE runs
  ADD CONSTRAINT runs_snapshot_id_fkey
  FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id);

ALTER TABLE staged_files ALTER COLUMN staged_file_id TYPE text USING staged_file_id::text;
ALTER TABLE staged_files ALTER COLUMN staged_file_id DROP DEFAULT;

ALTER TABLE checkpoints  ALTER COLUMN checkpoint_id  TYPE text USING checkpoint_id::text;
ALTER TABLE checkpoints  ALTER COLUMN checkpoint_id  DROP DEFAULT;

ALTER TABLE cache_events ALTER COLUMN event_id       TYPE text USING event_id::text;
ALTER TABLE cache_events ALTER COLUMN event_id       DROP DEFAULT;

ALTER TABLE pins         ALTER COLUMN pin_id         TYPE text USING pin_id::text;
ALTER TABLE pins         ALTER COLUMN pin_id         DROP DEFAULT;

-- Epoch-second columns.
ALTER TABLE run_nodes
  ALTER COLUMN lease_expires_at TYPE double precision
  USING EXTRACT(EPOCH FROM lease_expires_at);
ALTER TABLE run_nodes
  ALTER COLUMN heartbeat_at TYPE double precision
  USING EXTRACT(EPOCH FROM heartbeat_at);
ALTER TABLE action_cache_entries
  ALTER COLUMN expires_at TYPE double precision
  USING EXTRACT(EPOCH FROM expires_at);
ALTER TABLE pins
  ALTER COLUMN expires_at TYPE double precision
  USING EXTRACT(EPOCH FROM expires_at);
ALTER TABLE outbox_events
  ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE outbox_events
  ALTER COLUMN created_at TYPE double precision
  USING EXTRACT(EPOCH FROM created_at);
ALTER TABLE outbox_events
  ALTER COLUMN published_at TYPE double precision
  USING EXTRACT(EPOCH FROM published_at);

-- ``artifacts.metadata`` is read back through the same JSON path as SQLite.
ALTER TABLE artifacts ALTER COLUMN metadata SET DEFAULT '{}'::jsonb;
