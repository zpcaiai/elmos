-- Immutable, exact-principal cache SLO rollout event journal.

CREATE TABLE IF NOT EXISTS cache_slo_control_events_v12 (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  controller_id TEXT NOT NULL,
  principal_digest TEXT NOT NULL,
  sequence INTEGER NOT NULL CHECK (sequence > 0),
  previous_event_digest TEXT,
  event_digest TEXT NOT NULL,
  action TEXT NOT NULL,
  proposal_digest TEXT,
  approval_digest TEXT,
  evidence_digest TEXT,
  evidence_state TEXT CHECK (
    evidence_state IS NULL OR evidence_state IN ('LOCAL_ENGINEERING', 'EXTERNAL_VERIFIED')
  ),
  document TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, controller_id, sequence),
  UNIQUE (tenant_id, project_id, controller_id, event_digest),
  CHECK (
    (sequence = 1 AND previous_event_digest IS NULL)
    OR (sequence > 1 AND previous_event_digest IS NOT NULL)
  ),
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES projects (tenant_id, project_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_cache_slo_control_events_scope
  ON cache_slo_control_events_v12 (
    tenant_id, project_id, controller_id, principal_digest, sequence
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_cache_slo_control_events_evidence
  ON cache_slo_control_events_v12 (
    tenant_id, project_id, controller_id, evidence_digest
  )
  WHERE evidence_digest IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_cache_slo_control_events_chain_insert
BEFORE INSERT ON cache_slo_control_events_v12
BEGIN
  SELECT CASE
    WHEN NEW.sequence = 1 AND EXISTS (
      SELECT 1
      FROM cache_slo_control_events_v12 AS existing
      WHERE existing.tenant_id = NEW.tenant_id
        AND existing.project_id = NEW.project_id
        AND existing.controller_id = NEW.controller_id
    )
    THEN RAISE(ABORT, 'cache SLO chain is already initialized')
  END;
  SELECT CASE
    WHEN NEW.sequence > 1 AND NOT EXISTS (
      SELECT 1
      FROM cache_slo_control_events_v12 AS predecessor
      WHERE predecessor.tenant_id = NEW.tenant_id
        AND predecessor.project_id = NEW.project_id
        AND predecessor.controller_id = NEW.controller_id
        AND predecessor.principal_digest = NEW.principal_digest
        AND predecessor.sequence = NEW.sequence - 1
        AND predecessor.event_digest = NEW.previous_event_digest
    )
    THEN RAISE(ABORT, 'cache SLO predecessor is missing or mismatched')
  END;
END;

CREATE TRIGGER IF NOT EXISTS trg_cache_slo_control_events_immutable_update
BEFORE UPDATE ON cache_slo_control_events_v12
BEGIN
  SELECT RAISE(ABORT, 'cache SLO events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_cache_slo_control_events_immutable_delete
BEFORE DELETE ON cache_slo_control_events_v12
BEGIN
  SELECT RAISE(ABORT, 'cache SLO events are immutable');
END;
