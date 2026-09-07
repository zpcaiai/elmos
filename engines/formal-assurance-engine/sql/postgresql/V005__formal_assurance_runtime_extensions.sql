-- Repository-owned PostgreSQL 17 runtime extensions for the pinned v1 package.
-- The immutable source migrations V001-V004 remain unchanged.
CREATE TABLE IF NOT EXISTS formal_assurance.proof_revalidation_queue (
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  project_id text,
  subject_type text NOT NULL,
  subject_id text NOT NULL,
  dependency_kind text NOT NULL,
  dependency_id text NOT NULL,
  old_hash char(64) NOT NULL CHECK (old_hash ~ '^[a-f0-9]{64}$'),
  new_hash char(64) NOT NULL CHECK (new_hash ~ '^[a-f0-9]{64}$'),
  state text NOT NULL CHECK (state IN ('QUEUED','LEASED','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
  owner_id text,
  fencing_token bigint NOT NULL DEFAULT 1 CHECK (fencing_token > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (
    tenant_id, account_id, subject_type, subject_id,
    dependency_kind, dependency_id, new_hash
  )
);

CREATE TABLE IF NOT EXISTS formal_assurance.security_audit_event (
  id bigserial PRIMARY KEY,
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  project_id text,
  actor_id text NOT NULL,
  action text NOT NULL,
  decision text NOT NULL CHECK (decision IN ('ALLOW','DENY')),
  reason text NOT NULL,
  request_digest char(64) NOT NULL CHECK (request_digest ~ '^[a-f0-9]{64}$'),
  authorization_ref text,
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS formal_assurance.event_outbox (
  event_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  project_id text,
  topic text NOT NULL CHECK (topic IN ('proofEvents','driftEvents','gateEvents')),
  aggregate_type text NOT NULL,
  aggregate_id text NOT NULL,
  sequence bigint NOT NULL CHECK (sequence > 0),
  scope_digest char(64) NOT NULL CHECK (scope_digest ~ '^[a-f0-9]{64}$'),
  message jsonb NOT NULL,
  state text NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','PUBLISHED','DEAD')),
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  published_at timestamptz,
  delivery_receipt char(64) CHECK (delivery_receipt IS NULL OR delivery_receipt ~ '^[a-f0-9]{64}$'),
  last_error text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, aggregate_type, aggregate_id, sequence)
);

CREATE INDEX IF NOT EXISTS ix_revalidation_queue_ready
  ON formal_assurance.proof_revalidation_queue (tenant_id, account_id, state, created_at)
  WHERE state = 'QUEUED';
CREATE INDEX IF NOT EXISTS ix_security_audit_tenant_time
  ON formal_assurance.security_audit_event (tenant_id, account_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_event_outbox_ready
  ON formal_assurance.event_outbox (tenant_id, account_id, state, available_at, created_at)
  WHERE state = 'PENDING';

ALTER TABLE formal_assurance.proof_revalidation_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE formal_assurance.security_audit_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE formal_assurance.event_outbox ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON formal_assurance.proof_revalidation_queue;
CREATE POLICY tenant_isolation ON formal_assurance.proof_revalidation_queue
  USING (
    tenant_id = current_setting('elmos.tenant_id', true)
    AND account_id = current_setting('elmos.account_id', true)
  )
  WITH CHECK (
    tenant_id = current_setting('elmos.tenant_id', true)
    AND account_id = current_setting('elmos.account_id', true)
  );

DROP POLICY IF EXISTS tenant_isolation ON formal_assurance.security_audit_event;
CREATE POLICY tenant_isolation ON formal_assurance.security_audit_event
  USING (
    tenant_id = current_setting('elmos.tenant_id', true)
    AND account_id = current_setting('elmos.account_id', true)
  )
  WITH CHECK (
    tenant_id = current_setting('elmos.tenant_id', true)
    AND account_id = current_setting('elmos.account_id', true)
  );

DROP POLICY IF EXISTS tenant_isolation ON formal_assurance.event_outbox;
CREATE POLICY tenant_isolation ON formal_assurance.event_outbox
  USING (
    tenant_id = current_setting('elmos.tenant_id', true)
    AND account_id = current_setting('elmos.account_id', true)
  )
  WITH CHECK (
    tenant_id = current_setting('elmos.tenant_id', true)
    AND account_id = current_setting('elmos.account_id', true)
  );

CREATE OR REPLACE FUNCTION formal_assurance.reject_security_audit_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'security audit events are append-only';
END $$;

DROP TRIGGER IF EXISTS trg_security_audit_immutable
  ON formal_assurance.security_audit_event;
CREATE TRIGGER trg_security_audit_immutable
BEFORE UPDATE OR DELETE ON formal_assurance.security_audit_event
FOR EACH ROW EXECUTE FUNCTION formal_assurance.reject_security_audit_mutation();

CREATE OR REPLACE FUNCTION formal_assurance.enqueue_proof_event()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  selected_topic text;
  selected_message jsonb;
BEGIN
  selected_topic := CASE
    WHEN NEW.aggregate_type = 'proof_drift' THEN 'driftEvents'
    ELSE 'proofEvents'
  END;
  IF selected_topic = 'driftEvents' THEN
    selected_message := jsonb_build_object(
      'dependencyKind', NEW.payload ->> 'dependencyKind',
      'dependencyId', NEW.payload ->> 'dependencyId',
      'oldHash', NEW.payload ->> 'oldHash',
      'newHash', NEW.payload ->> 'newHash'
    );
  ELSE
    selected_message := jsonb_build_object(
      'eventId', NEW.event_id,
      'eventType', NEW.event_type,
      'tenantId', NEW.tenant_id,
      'aggregateId', NEW.aggregate_id,
      'occurredAt', NEW.created_at,
      'payload', NEW.payload
    );
  END IF;
  INSERT INTO formal_assurance.event_outbox (
    event_id, tenant_id, account_id, topic, aggregate_type, aggregate_id,
    sequence, scope_digest, message
  ) VALUES (
    NEW.event_id,
    NEW.tenant_id,
    current_setting('elmos.account_id', false),
    selected_topic,
    NEW.aggregate_type,
    NEW.aggregate_id,
    NEW.id,
    current_setting('elmos.scope_digest', false),
    selected_message
  ) ON CONFLICT (event_id) DO NOTHING;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_proof_event_outbox ON formal_assurance.proof_event;
CREATE TRIGGER trg_proof_event_outbox
AFTER INSERT ON formal_assurance.proof_event
FOR EACH ROW EXECUTE FUNCTION formal_assurance.enqueue_proof_event();

CREATE OR REPLACE FUNCTION formal_assurance.enqueue_gate_event()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO formal_assurance.event_outbox (
    event_id, tenant_id, account_id, topic, aggregate_type, aggregate_id,
    sequence, scope_digest, message
  ) VALUES (
    'gate:' || NEW.id,
    NEW.tenant_id,
    NEW.account_id,
    'gateEvents',
    'gate_decision',
    NEW.id,
    1,
    current_setting('elmos.scope_digest', false),
    jsonb_strip_nulls(jsonb_build_object(
      'id', NEW.id,
      'tenant', jsonb_strip_nulls(jsonb_build_object(
        'tenantId', NEW.tenant_id,
        'accountId', NEW.account_id
      )),
      'subjectId', NEW.subject_id,
      'gate', NEW.gate,
      'decision', NEW.decision,
      'policyRevision', NEW.policy_revision,
      'evaluatedAt', NEW.evaluated_at,
      'blockingReasons', NEW.blocking_reasons,
      'evidenceHash', NEW.evidence_hash,
      'expiresAt', NEW.expires_at
    ))
  ) ON CONFLICT (event_id) DO NOTHING;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_gate_event_outbox
  ON formal_assurance.release_gate_decision;
CREATE TRIGGER trg_gate_event_outbox
AFTER INSERT ON formal_assurance.release_gate_decision
FOR EACH ROW EXECUTE FUNCTION formal_assurance.enqueue_gate_event();
