-- Immutable, exact-principal cache SLO rollout event journal.
-- RLS is intentionally not enabled: MetadataStore does not establish a
-- trusted transaction-local tenant session. Composite ownership, exact
-- application filtering and immutable chain enforcement fail closed instead.

CREATE TABLE IF NOT EXISTS cache_slo_control_events_v12 (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  controller_id TEXT NOT NULL,
  principal_digest TEXT NOT NULL,
  sequence BIGINT NOT NULL CHECK (sequence > 0),
  previous_event_digest TEXT,
  event_digest TEXT NOT NULL,
  action TEXT NOT NULL,
  proposal_digest TEXT,
  approval_digest TEXT,
  evidence_digest TEXT,
  evidence_state TEXT CHECK (
    evidence_state IS NULL OR evidence_state IN ('LOCAL_ENGINEERING', 'EXTERNAL_VERIFIED')
  ),
  document JSONB NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (tenant_id, project_id, controller_id, sequence),
  UNIQUE (tenant_id, project_id, controller_id, event_digest),
  CHECK (
    (sequence = 1 AND previous_event_digest IS NULL)
    OR (sequence > 1 AND previous_event_digest IS NOT NULL)
  ),
  CONSTRAINT fk_cache_slo_control_events_project_scope
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

CREATE OR REPLACE FUNCTION guard_cache_slo_control_event_v12()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $guard$
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'cache SLO events are immutable' USING ERRCODE = '55000';
  END IF;

  IF NEW.sequence = 1 THEN
    IF EXISTS (
      SELECT 1
      FROM cache_slo_control_events_v12 AS existing
      WHERE existing.tenant_id = NEW.tenant_id
        AND existing.project_id = NEW.project_id
        AND existing.controller_id = NEW.controller_id
    ) THEN
      RAISE EXCEPTION 'cache SLO chain is already initialized'
        USING ERRCODE = '23505';
    END IF;
  ELSE
    PERFORM 1
    FROM cache_slo_control_events_v12 AS predecessor
    WHERE predecessor.tenant_id = NEW.tenant_id
      AND predecessor.project_id = NEW.project_id
      AND predecessor.controller_id = NEW.controller_id
      AND predecessor.principal_digest = NEW.principal_digest
      AND predecessor.sequence = NEW.sequence - 1
      AND predecessor.event_digest = NEW.previous_event_digest;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'cache SLO predecessor is missing or mismatched'
        USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END;
$guard$;

DROP TRIGGER IF EXISTS trg_cache_slo_control_events_guard
  ON cache_slo_control_events_v12;
CREATE TRIGGER trg_cache_slo_control_events_guard
BEFORE INSERT OR UPDATE OR DELETE ON cache_slo_control_events_v12
FOR EACH ROW EXECUTE FUNCTION guard_cache_slo_control_event_v12();
