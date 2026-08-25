-- Durable v1.2 repository-context ledger and cache-preserving checkpoints.

CREATE TABLE IF NOT EXISTS context_ledger_streams (
  tenant_id                  TEXT NOT NULL REFERENCES tenants(tenant_id),
  project_id                 TEXT NOT NULL REFERENCES projects(project_id),
  stream_id                  TEXT NOT NULL,
  branch_lineage             TEXT NOT NULL,
  repository_snapshot_digest TEXT NOT NULL,
  current_sequence           INTEGER NOT NULL DEFAULT 0 CHECK (current_sequence >= 0),
  head_event_digest          TEXT,
  active_checkpoint_id       TEXT,
  created_at                 REAL NOT NULL,
  updated_at                 REAL NOT NULL,
  PRIMARY KEY (tenant_id, project_id, stream_id),
  CHECK ((current_sequence = 0 AND head_event_digest IS NULL)
      OR (current_sequence > 0 AND head_event_digest IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS context_ledger_events (
  tenant_id                  TEXT NOT NULL,
  project_id                 TEXT NOT NULL,
  stream_id                  TEXT NOT NULL,
  sequence                   INTEGER NOT NULL CHECK (sequence > 0),
  event_id                   TEXT NOT NULL,
  idempotency_key            TEXT NOT NULL,
  event_type                 TEXT NOT NULL CHECK (event_type IN (
    'SNAPSHOT_BOUND','FILE_READ','SYMBOL_READ','SUMMARY_WRITTEN',
    'CONTENT_CHANGED','CONTEXT_STALE','CONTENT_REREAD','TOOL_OBSERVED',
    'VALIDATION_OBSERVED','CONTEXT_CHECKPOINT','COMPACTION_COMPLETED',
    'COMPACTION_ROLLBACK')),
  branch_lineage             TEXT NOT NULL,
  repository_snapshot_digest TEXT NOT NULL,
  subject_ref                TEXT,
  payload                    TEXT NOT NULL CHECK (json_valid(payload)),
  payload_digest             TEXT NOT NULL,
  previous_event_digest      TEXT,
  event_digest               TEXT NOT NULL,
  supersedes_event_id        TEXT,
  occurred_at                REAL NOT NULL,
  PRIMARY KEY (tenant_id, project_id, stream_id, sequence),
  UNIQUE (tenant_id, project_id, stream_id, event_id),
  UNIQUE (tenant_id, project_id, stream_id, idempotency_key),
  UNIQUE (tenant_id, project_id, stream_id, event_digest),
  FOREIGN KEY (tenant_id, project_id, stream_id)
    REFERENCES context_ledger_streams(tenant_id, project_id, stream_id)
    ON DELETE RESTRICT
);

CREATE TRIGGER IF NOT EXISTS context_ledger_events_no_update
BEFORE UPDATE ON context_ledger_events
BEGIN
  SELECT RAISE(ABORT, 'CONTEXT_LEDGER_APPEND_ONLY');
END;

CREATE TRIGGER IF NOT EXISTS context_ledger_events_no_delete
BEFORE DELETE ON context_ledger_events
BEGIN
  SELECT RAISE(ABORT, 'CONTEXT_LEDGER_APPEND_ONLY');
END;

CREATE TABLE IF NOT EXISTS context_checkpoints (
  tenant_id                  TEXT NOT NULL,
  project_id                 TEXT NOT NULL,
  stream_id                  TEXT NOT NULL,
  checkpoint_id              TEXT NOT NULL,
  ledger_sequence            INTEGER NOT NULL CHECK (ledger_sequence >= 0),
  ledger_head_digest         TEXT,
  repository_snapshot_digest TEXT NOT NULL,
  compatibility_group        TEXT NOT NULL,
  source_sequence_start      INTEGER NOT NULL CHECK (source_sequence_start >= 0),
  source_sequence_end        INTEGER NOT NULL CHECK (source_sequence_end >= source_sequence_start),
  sections                   TEXT NOT NULL CHECK (json_valid(sections)),
  external_artifact_refs     TEXT NOT NULL CHECK (json_valid(external_artifact_refs)),
  checkpoint_digest          TEXT NOT NULL,
  previous_checkpoint_id     TEXT,
  status                     TEXT NOT NULL CHECK (status IN (
    'PREPARED','WARMED','ACTIVE','SUPERSEDED','ROLLED_BACK')),
  warm_evidence_digest       TEXT,
  created_at                 REAL NOT NULL,
  warmed_at                  REAL,
  adopted_at                 REAL,
  rolled_back_at             REAL,
  PRIMARY KEY (tenant_id, project_id, stream_id, checkpoint_id),
  UNIQUE (tenant_id, project_id, stream_id, checkpoint_digest),
  FOREIGN KEY (tenant_id, project_id, stream_id)
    REFERENCES context_ledger_streams(tenant_id, project_id, stream_id)
    ON DELETE RESTRICT,
  CHECK ((ledger_sequence = 0 AND ledger_head_digest IS NULL)
      OR (ledger_sequence > 0 AND ledger_head_digest IS NOT NULL)),
  CHECK (status = 'PREPARED' OR warm_evidence_digest IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_context_events_subject
  ON context_ledger_events (tenant_id, project_id, stream_id, subject_ref, sequence);
CREATE INDEX IF NOT EXISTS idx_context_checkpoints_status
  ON context_checkpoints (tenant_id, project_id, stream_id, status, created_at);
