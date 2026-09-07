-- Destructive development rollback for 0001. Production rollback should use a
-- forward compensation/migration after evidence export. Apply 0002 down first.
BEGIN;

DO $$
BEGIN
  IF to_regclass('public.oh_provider_sessions') IS NOT NULL
     OR to_regclass('public.oh_evidence_packs') IS NOT NULL THEN
    RAISE EXCEPTION 'rollback 0002_openhands_production_runtime before 0001';
  END IF;
END $$;

DROP TABLE IF EXISTS oh_execution_outbox;
DROP TRIGGER IF EXISTS oh_execution_events_immutable ON oh_execution_events;
DROP TABLE IF EXISTS oh_execution_events;
DROP TABLE IF EXISTS oh_execution_runs;
DROP FUNCTION IF EXISTS oh_reject_event_mutation();

COMMIT;
