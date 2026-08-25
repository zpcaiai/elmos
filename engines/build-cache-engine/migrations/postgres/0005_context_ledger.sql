-- Durable v1.2 repository-context ledger and cache-preserving checkpoints.

CREATE TABLE IF NOT EXISTS context_ledger_streams (
  tenant_id                  text NOT NULL REFERENCES tenants(tenant_id),
  project_id                 text NOT NULL REFERENCES projects(project_id),
  stream_id                  text NOT NULL,
  branch_lineage             text NOT NULL,
  repository_snapshot_digest text NOT NULL,
  current_sequence           bigint NOT NULL DEFAULT 0 CHECK (current_sequence >= 0),
  head_event_digest          text,
  active_checkpoint_id       text,
  created_at                 double precision NOT NULL,
  updated_at                 double precision NOT NULL,
  PRIMARY KEY (tenant_id, project_id, stream_id),
  CHECK ((current_sequence = 0 AND head_event_digest IS NULL)
      OR (current_sequence > 0 AND head_event_digest IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS context_ledger_events (
  tenant_id                  text NOT NULL,
  project_id                 text NOT NULL,
  stream_id                  text NOT NULL,
  sequence                   bigint NOT NULL CHECK (sequence > 0),
  event_id                   text NOT NULL,
  idempotency_key            text NOT NULL,
  event_type                 text NOT NULL CHECK (event_type IN (
    'SNAPSHOT_BOUND','FILE_READ','SYMBOL_READ','SUMMARY_WRITTEN',
    'CONTENT_CHANGED','CONTEXT_STALE','CONTENT_REREAD','TOOL_OBSERVED',
    'VALIDATION_OBSERVED','CONTEXT_CHECKPOINT','COMPACTION_COMPLETED',
    'COMPACTION_ROLLBACK')),
  branch_lineage             text NOT NULL,
  repository_snapshot_digest text NOT NULL,
  subject_ref                text,
  payload                    jsonb NOT NULL,
  payload_digest             text NOT NULL,
  previous_event_digest      text,
  event_digest               text NOT NULL,
  supersedes_event_id        text,
  occurred_at                double precision NOT NULL,
  PRIMARY KEY (tenant_id, project_id, stream_id, sequence),
  UNIQUE (tenant_id, project_id, stream_id, event_id),
  UNIQUE (tenant_id, project_id, stream_id, idempotency_key),
  UNIQUE (tenant_id, project_id, stream_id, event_digest),
  FOREIGN KEY (tenant_id, project_id, stream_id)
    REFERENCES context_ledger_streams(tenant_id, project_id, stream_id)
    ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION elmos_context_ledger_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'CONTEXT_LEDGER_APPEND_ONLY';
END;
$$;

DROP TRIGGER IF EXISTS context_ledger_events_no_update ON context_ledger_events;
CREATE TRIGGER context_ledger_events_no_update
BEFORE UPDATE ON context_ledger_events
FOR EACH ROW EXECUTE FUNCTION elmos_context_ledger_immutable();

DROP TRIGGER IF EXISTS context_ledger_events_no_delete ON context_ledger_events;
CREATE TRIGGER context_ledger_events_no_delete
BEFORE DELETE ON context_ledger_events
FOR EACH ROW EXECUTE FUNCTION elmos_context_ledger_immutable();

CREATE TABLE IF NOT EXISTS context_checkpoints (
  tenant_id                  text NOT NULL,
  project_id                 text NOT NULL,
  stream_id                  text NOT NULL,
  checkpoint_id              text NOT NULL,
  ledger_sequence            bigint NOT NULL CHECK (ledger_sequence >= 0),
  ledger_head_digest         text,
  repository_snapshot_digest text NOT NULL,
  compatibility_group        text NOT NULL,
  source_sequence_start      bigint NOT NULL CHECK (source_sequence_start >= 0),
  source_sequence_end        bigint NOT NULL CHECK (source_sequence_end >= source_sequence_start),
  sections                   jsonb NOT NULL,
  external_artifact_refs     jsonb NOT NULL,
  checkpoint_digest          text NOT NULL,
  previous_checkpoint_id     text,
  status                     text NOT NULL CHECK (status IN (
    'PREPARED','WARMED','ACTIVE','SUPERSEDED','ROLLED_BACK')),
  warm_evidence_digest       text,
  created_at                 double precision NOT NULL,
  warmed_at                  double precision,
  adopted_at                 double precision,
  rolled_back_at             double precision,
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
