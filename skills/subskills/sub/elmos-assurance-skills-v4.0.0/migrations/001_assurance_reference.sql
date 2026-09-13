-- REFERENCE MIGRATION; PostgreSQL candidate; native execution status NOT_RUN.
-- Adapt to existing Elmos schemas/IDs through the bootstrap ADR. Never auto-run.
-- No CREATE ROLE / GRANT / production secrets. A reviewed deployment assigns least privilege.
BEGIN;
CREATE SCHEMA assurance_v4;
CREATE DOMAIN assurance_v4.digest256 AS text CHECK (VALUE ~ '^[0-9a-f]{64}$');
CREATE TABLE assurance_v4.runs (
  tenant_id uuid NOT NULL, run_id uuid NOT NULL, project_id uuid NOT NULL,
  approved_request_digest assurance_v4.digest256 NOT NULL,
  profile_id text NOT NULL, target_level text NOT NULL CHECK (target_level IN ('E0','E1','E2','E3','E4','E5')),
  state text NOT NULL CHECK (state IN ('PLANNED','RUNNING','BLOCKED','CANCELLED','COMPLETED')),
  current_epoch bigint NOT NULL DEFAULT 1 CHECK (current_epoch > 0),
  lease_expires_at timestamptz, inventory_sealed_at timestamptz,
  evidence_inventory_digest assurance_v4.digest256,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  row_version bigint NOT NULL DEFAULT 1 CHECK (row_version > 0),
  PRIMARY KEY (tenant_id,run_id),
  CHECK ((inventory_sealed_at IS NULL) = (evidence_inventory_digest IS NULL))
);
CREATE TABLE assurance_v4.obligations (
  tenant_id uuid NOT NULL, run_id uuid NOT NULL, obligation_id text NOT NULL,
  kind text NOT NULL, critical boolean NOT NULL, definition_digest assurance_v4.digest256 NOT NULL,
  case_manifest_digest assurance_v4.digest256 NOT NULL,
  case_count integer NOT NULL CHECK (case_count > 0),
  PRIMARY KEY (tenant_id,run_id,obligation_id),
  FOREIGN KEY (tenant_id,run_id) REFERENCES assurance_v4.runs(tenant_id,run_id)
);
CREATE TABLE assurance_v4.result_commits (
  tenant_id uuid NOT NULL, run_id uuid NOT NULL, step_id text NOT NULL,
  attempt_id uuid NOT NULL, executor_epoch bigint NOT NULL,
  idempotency_key text NOT NULL, payload_digest assurance_v4.digest256 NOT NULL,
  event_id uuid NOT NULL, committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id,run_id,step_id),
  UNIQUE (tenant_id,run_id,idempotency_key),
  UNIQUE (tenant_id,event_id),
  FOREIGN KEY (tenant_id,run_id) REFERENCES assurance_v4.runs(tenant_id,run_id)
);
CREATE TABLE assurance_v4.evidence (
  tenant_id uuid NOT NULL, run_id uuid NOT NULL, evidence_id uuid NOT NULL,
  obligation_id text NOT NULL, attempt_id uuid NOT NULL,
  execution_status text NOT NULL CHECK (execution_status IN ('PASS','FAIL','UNKNOWN','NOT_RUN','TIMED_OUT','CANCELLED')),
  request_digest assurance_v4.digest256 NOT NULL, payload_digest assurance_v4.digest256 NOT NULL,
  report_digest assurance_v4.digest256 NOT NULL,
  signer_identity_ref text NOT NULL, signature_envelope_ref text NOT NULL,
  issued_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id,run_id,evidence_id),
  FOREIGN KEY (tenant_id,run_id,obligation_id) REFERENCES assurance_v4.obligations(tenant_id,run_id,obligation_id),
  CHECK (expires_at > issued_at)
);
CREATE TABLE assurance_v4.audit_decisions (
  tenant_id uuid NOT NULL, run_id uuid NOT NULL, audit_id uuid NOT NULL,
  auditor_identity_ref text NOT NULL, auditor_control_domain text NOT NULL,
  reviewed_bundle_digest assurance_v4.digest256 NOT NULL,
  decision text NOT NULL CHECK (decision IN ('APPROVE','REJECT','NEEDS_EVIDENCE')),
  signature_envelope_ref text NOT NULL, nonce_digest assurance_v4.digest256 NOT NULL,
  issued_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id,audit_id),
  UNIQUE (tenant_id,nonce_digest),
  FOREIGN KEY (tenant_id,run_id) REFERENCES assurance_v4.runs(tenant_id,run_id),
  CHECK (expires_at > issued_at)
);
CREATE TABLE assurance_v4.gate_decisions (
  tenant_id uuid NOT NULL, run_id uuid NOT NULL, decision_id uuid NOT NULL,
  request_digest assurance_v4.digest256 NOT NULL, bundle_digest assurance_v4.digest256 NOT NULL,
  verdict text NOT NULL CHECK (verdict IN ('PASS','FAIL','INCONCLUSIVE')),
  reason_manifest_digest assurance_v4.digest256 NOT NULL,
  profile_digest assurance_v4.digest256 NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id,decision_id),
  FOREIGN KEY (tenant_id,run_id) REFERENCES assurance_v4.runs(tenant_id,run_id)
);
CREATE TABLE assurance_v4.attestations (
  tenant_id uuid NOT NULL, certificate_id uuid NOT NULL, decision_id uuid NOT NULL,
  subject_artifact_digest assurance_v4.digest256 NOT NULL,
  signed_envelope_digest assurance_v4.digest256 NOT NULL,
  signer_identity_ref text NOT NULL, issued_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id,certificate_id),
  FOREIGN KEY (tenant_id,decision_id) REFERENCES assurance_v4.gate_decisions(tenant_id,decision_id),
  CHECK (expires_at > issued_at)
);
CREATE TABLE assurance_v4.revocations (
  tenant_id uuid NOT NULL, revocation_id uuid NOT NULL, certificate_id uuid NOT NULL,
  reason_digest assurance_v4.digest256 NOT NULL, signed_envelope_digest assurance_v4.digest256 NOT NULL,
  revoked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id,revocation_id),
  FOREIGN KEY (tenant_id,certificate_id) REFERENCES assurance_v4.attestations(tenant_id,certificate_id)
);
CREATE TABLE assurance_v4.outbox (
  tenant_id uuid NOT NULL, event_id uuid NOT NULL, run_id uuid NOT NULL,
  event_type text NOT NULL, payload_digest assurance_v4.digest256 NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(), published_at timestamptz,
  publish_attempts integer NOT NULL DEFAULT 0 CHECK (publish_attempts >= 0),
  PRIMARY KEY (tenant_id,event_id),
  FOREIGN KEY (tenant_id,run_id) REFERENCES assurance_v4.runs(tenant_id,run_id)
);
CREATE TABLE assurance_v4.inbox (
  tenant_id uuid NOT NULL, consumer_name text NOT NULL, event_id uuid NOT NULL,
  payload_digest assurance_v4.digest256 NOT NULL, processed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id,consumer_name,event_id)
);
CREATE TABLE assurance_v4.budget_accounts (
  tenant_id uuid NOT NULL, account_id uuid NOT NULL,
  approved_units bigint NOT NULL CHECK (approved_units >= 0),
  settled_units bigint NOT NULL DEFAULT 0 CHECK (settled_units >= 0),
  reserved_units bigint NOT NULL DEFAULT 0 CHECK (reserved_units >= 0),
  running_count integer NOT NULL DEFAULT 0 CHECK (running_count BETWEEN 0 AND 3),
  admission_blocked boolean NOT NULL DEFAULT false, row_version bigint NOT NULL DEFAULT 1,
  PRIMARY KEY (tenant_id,account_id)
);
CREATE TABLE assurance_v4.budget_reservations (
  tenant_id uuid NOT NULL, reservation_id uuid NOT NULL, account_id uuid NOT NULL, run_id uuid NOT NULL,
  reserved_units bigint NOT NULL CHECK (reserved_units >= 0), actual_units bigint CHECK (actual_units >= 0),
  status text NOT NULL CHECK (status IN ('RESERVED','RUNNING','RECONCILE_REQUIRED','SETTLED','CANCELLED')),
  idempotency_key text NOT NULL,
  PRIMARY KEY (tenant_id,reservation_id), UNIQUE (tenant_id,account_id,idempotency_key),
  FOREIGN KEY (tenant_id,account_id) REFERENCES assurance_v4.budget_accounts(tenant_id,account_id),
  FOREIGN KEY (tenant_id,run_id) REFERENCES assurance_v4.runs(tenant_id,run_id)
);
CREATE INDEX evidence_lookup ON assurance_v4.evidence(tenant_id,run_id,obligation_id);
CREATE INDEX revocation_lookup ON assurance_v4.revocations(tenant_id,certificate_id);
CREATE INDEX outbox_pending ON assurance_v4.outbox(tenant_id,created_at) WHERE published_at IS NULL;

-- All scoped reads/writes require a trusted server SET LOCAL app.tenant_id after authentication.
-- FORCE RLS does NOT restrict superusers/BYPASSRLS; untrusted direct SQL must never use this account.
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['runs','obligations','result_commits','evidence','audit_decisions',
      'gate_decisions','attestations','revocations','outbox','inbox','budget_accounts','budget_reservations'] LOOP
    EXECUTE format('ALTER TABLE assurance_v4.%I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('ALTER TABLE assurance_v4.%I FORCE ROW LEVEL SECURITY',t);
    EXECUTE format('CREATE POLICY tenant_scope ON assurance_v4.%I USING (tenant_id = nullif(current_setting(''app.tenant_id'',true),)::uuid) WITH CHECK (tenant_id = nullif(current_setting(app.tenant_id,true),)::uuid)',t);
  END LOOP;
END $$;

CREATE FUNCTION assurance_v4.deny_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'APPEND_ONLY_RECORD' USING ERRCODE='42501'; END $$;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['obligations','result_commits','evidence','audit_decisions','gate_decisions','attestations','revocations','inbox'] LOOP
    EXECUTE format('CREATE TRIGGER reject_mutation BEFORE UPDATE OR DELETE ON assurance_v4.%I FOR EACH ROW EXECUTE FUNCTION assurance_v4.deny_mutation()',t);
  END LOOP;
END $$;

-- Serializes successful commit with cancellation/executor replacement. This is not external exactly-once.
CREATE FUNCTION assurance_v4.fence_result_commit() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r assurance_v4.runs%ROWTYPE;
BEGIN
  SELECT * INTO r FROM assurance_v4.runs WHERE tenant_id=NEW.tenant_id AND run_id=NEW.run_id FOR UPDATE;
  IF NOT FOUND OR r.state <> 'RUNNING' OR r.current_epoch <> NEW.executor_epoch
     OR r.lease_expires_at IS NULL OR r.lease_expires_at <= clock_timestamp()
     OR r.inventory_sealed_at IS NOT NULL THEN
    RAISE EXCEPTION 'STALE_OR_UNAUTHORIZED_COMMIT' USING ERRCODE='42501';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER check_commit BEFORE INSERT ON assurance_v4.result_commits
 FOR EACH ROW EXECUTE FUNCTION assurance_v4.fence_result_commit();

-- Evidence statements must use the approved run subject and cannot be appended after seal.
CREATE FUNCTION assurance_v4.check_evidence_subject() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r assurance_v4.runs%ROWTYPE;
BEGIN
  SELECT * INTO r FROM assurance_v4.runs WHERE tenant_id=NEW.tenant_id AND run_id=NEW.run_id FOR UPDATE;
  IF NOT FOUND OR r.approved_request_digest <> NEW.request_digest OR r.inventory_sealed_at IS NOT NULL THEN
    RAISE EXCEPTION 'UNAPPROVED_OR_SEALED_EVIDENCE_SUBJECT' USING ERRCODE='42501';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER check_evidence BEFORE INSERT ON assurance_v4.evidence
 FOR EACH ROW EXECUTE FUNCTION assurance_v4.check_evidence_subject();
COMMIT;
