-- PostgreSQL reference migration for the durable P0/P1 runtime.
-- Large payloads stay in an object store; this schema stores only immutable
-- metadata and tenant-scoped references.
CREATE TABLE IF NOT EXISTS oh_execution_runs (
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL,
  project_id uuid NOT NULL,
  task_id uuid NOT NULL,
  node_id text NOT NULL,
  status text NOT NULL CHECK (status IN ('queued','ready','running','waiting','blocked','succeeded','failed','cancelled')),
  manifest_hash text NOT NULL CHECK (manifest_hash LIKE 'sha256:%'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, run_id, node_id)
);

CREATE TABLE IF NOT EXISTS oh_execution_events (
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL,
  seq bigint NOT NULL CHECK (seq >= 0),
  event_id uuid NOT NULL,
  event_type text NOT NULL,
  node_id text,
  agent_id text,
  idempotency_key text,
  payload jsonb NOT NULL,
  artifact_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  policy_decision jsonb,
  usage jsonb,
  cost jsonb,
  previous_digest text,
  digest text NOT NULL CHECK (digest LIKE 'sha256:%'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, run_id, seq),
  UNIQUE (tenant_id, event_id),
  UNIQUE (tenant_id, run_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS oh_execution_outbox (
  outbox_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL,
  seq bigint NOT NULL,
  event_json jsonb NOT NULL,
  published_at timestamptz
);

ALTER TABLE oh_execution_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS oh_execution_events_tenant_isolation ON oh_execution_events;
CREATE POLICY oh_execution_events_tenant_isolation ON oh_execution_events
  USING (tenant_id = current_setting('elmos.tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true)::uuid);

CREATE OR REPLACE FUNCTION oh_reject_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'oh_execution_events is append-only; use a correction event';
END;
$$;
DROP TRIGGER IF EXISTS oh_execution_events_immutable ON oh_execution_events;
CREATE TRIGGER oh_execution_events_immutable
  BEFORE UPDATE OR DELETE ON oh_execution_events
  FOR EACH ROW EXECUTE FUNCTION oh_reject_event_mutation();
