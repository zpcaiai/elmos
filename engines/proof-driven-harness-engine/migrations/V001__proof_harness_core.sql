-- PostgreSQL 17 production control-plane schema for the proof-driven harness.
-- This migration is inert repository material until an authorized deployment
-- applies it. The application identity gateway must set app.tenant_id,
-- app.project_id and app.actor_id from authenticated identity, never from
-- request JSON.

CREATE SCHEMA IF NOT EXISTS proof_harness;
REVOKE ALL ON SCHEMA proof_harness FROM PUBLIC;

-- The semantic proof model remains in ``proof_harness``.  The executable
-- durable-store contract lives in a separate schema so its opaque external
-- identity keys are not incorrectly narrowed to UUIDs.  Both schemas are
-- migrated together and both are protected by forced RLS.
CREATE SCHEMA IF NOT EXISTS proof_harness_runtime;
REVOKE ALL ON SCHEMA proof_harness_runtime FROM PUBLIC;

CREATE OR REPLACE FUNCTION proof_harness.current_tenant_id()
RETURNS uuid
LANGUAGE sql
STABLE
SET search_path = pg_catalog
AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION proof_harness.current_actor_id()
RETURNS text
LANGUAGE sql
STABLE
SET search_path = pg_catalog
AS $$
  SELECT NULLIF(current_setting('app.actor_id', true), '')
$$;

CREATE OR REPLACE FUNCTION proof_harness.current_project_id()
RETURNS uuid
LANGUAGE sql
STABLE
SET search_path = pg_catalog
AS $$
  SELECT NULLIF(current_setting('app.project_id', true), '')::uuid
$$;

CREATE TABLE proof_harness.tenant_projects (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  project_revision bigint NOT NULL DEFAULT 1 CHECK (project_revision > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id)
);

CREATE TABLE proof_harness.goal_contracts (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  goal_id uuid NOT NULL,
  contract_digest text NOT NULL CHECK (contract_digest ~ '^sha256:[0-9a-f]{64}$'),
  contract_json jsonb NOT NULL,
  state text NOT NULL CHECK (state IN ('DRAFT', 'FROZEN', 'SUPERSEDED')),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, goal_id),
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES proof_harness.tenant_projects (tenant_id, project_id)
);

CREATE TABLE proof_harness.revision_sets (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  revision_set_id uuid NOT NULL,
  goal_id uuid NOT NULL,
  revision_set_digest text NOT NULL CHECK (revision_set_digest ~ '^sha256:[0-9a-f]{64}$'),
  source_digest text NOT NULL CHECK (source_digest ~ '^sha256:[0-9a-f]{64}$'),
  baseline_digest text NOT NULL CHECK (baseline_digest ~ '^sha256:[0-9a-f]{64}$'),
  requirements_digest text NOT NULL CHECK (requirements_digest ~ '^sha256:[0-9a-f]{64}$'),
  policy_digest text NOT NULL CHECK (policy_digest ~ '^sha256:[0-9a-f]{64}$'),
  workflow_digest text NOT NULL CHECK (workflow_digest ~ '^sha256:[0-9a-f]{64}$'),
  model_route_digest text NOT NULL CHECK (model_route_digest ~ '^sha256:[0-9a-f]{64}$'),
  toolchain_digest text NOT NULL CHECK (toolchain_digest ~ '^sha256:[0-9a-f]{64}$'),
  environment_digest text NOT NULL CHECK (environment_digest ~ '^sha256:[0-9a-f]{64}$'),
  domain_pack_digest text NOT NULL CHECK (domain_pack_digest ~ '^sha256:[0-9a-f]{64}$'),
  frozen_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, revision_set_id),
  UNIQUE (tenant_id, project_id, revision_set_digest),
  FOREIGN KEY (tenant_id, project_id, goal_id)
    REFERENCES proof_harness.goal_contracts (tenant_id, project_id, goal_id)
);

CREATE TABLE proof_harness.environment_authorities (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  authority_id uuid NOT NULL,
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  environment_id text NOT NULL,
  execution_epoch bigint NOT NULL CHECK (execution_epoch > 0),
  fencing_generation bigint NOT NULL CHECK (fencing_generation > 0),
  capabilities_json jsonb NOT NULL,
  read_paths_json jsonb NOT NULL,
  write_paths_json jsonb NOT NULL,
  network_mode text NOT NULL CHECK (network_mode IN ('DENY', 'ALLOWLIST')),
  valid_from timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  issued_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK (valid_from < expires_at),
  PRIMARY KEY (tenant_id, project_id, authority_id),
  UNIQUE (tenant_id, project_id, authority_id, execution_epoch, fencing_generation),
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES proof_harness.tenant_projects (tenant_id, project_id)
);

CREATE TABLE proof_harness.environment_authority_revocations (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  authority_id uuid NOT NULL,
  revocation_id uuid NOT NULL,
  reason text NOT NULL,
  actor_id text NOT NULL,
  revoked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, authority_id, revocation_id),
  FOREIGN KEY (tenant_id, project_id, authority_id)
    REFERENCES proof_harness.environment_authorities (tenant_id, project_id, authority_id)
);

CREATE TABLE proof_harness.runs (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  run_id uuid NOT NULL,
  goal_id uuid NOT NULL,
  revision_set_id uuid NOT NULL,
  authority_id uuid NOT NULL,
  execution_epoch bigint NOT NULL CHECK (execution_epoch > 0),
  fencing_generation bigint NOT NULL CHECK (fencing_generation > 0),
  state text NOT NULL CHECK (state IN (
    'CREATED', 'ADMITTED', 'PLANNING', 'EXECUTING', 'CHECKPOINTED',
    'PAUSED', 'RESUMING', 'AWAITING_REVIEW', 'VERIFYING', 'CERTIFYING',
    'COMPLETED', 'BLOCKED', 'FAILED', 'CANCELLED', 'TIMED_OUT', 'PARTIAL'
  )),
  state_version bigint NOT NULL DEFAULT 1 CHECK (state_version > 0),
  cancellation_requested_at timestamptz,
  deadline_at timestamptz,
  checkpoint_digest text CHECK (checkpoint_digest IS NULL OR checkpoint_digest ~ '^sha256:[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, run_id),
  FOREIGN KEY (tenant_id, project_id, goal_id)
    REFERENCES proof_harness.goal_contracts (tenant_id, project_id, goal_id),
  FOREIGN KEY (tenant_id, project_id, revision_set_id)
    REFERENCES proof_harness.revision_sets (tenant_id, project_id, revision_set_id),
  FOREIGN KEY (tenant_id, project_id, authority_id, execution_epoch, fencing_generation)
    REFERENCES proof_harness.environment_authorities
      (tenant_id, project_id, authority_id, execution_epoch, fencing_generation)
);

CREATE TABLE proof_harness.run_leases (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  run_id uuid NOT NULL,
  lease_id uuid NOT NULL,
  holder_id text NOT NULL,
  execution_epoch bigint NOT NULL CHECK (execution_epoch > 0),
  fencing_generation bigint NOT NULL CHECK (fencing_generation > 0),
  acquired_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  released_at timestamptz,
  PRIMARY KEY (tenant_id, project_id, run_id),
  UNIQUE (tenant_id, project_id, lease_id),
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness.runs (tenant_id, project_id, run_id),
  CHECK (acquired_at < expires_at),
  CHECK (released_at IS NULL OR released_at >= acquired_at)
);

CREATE TABLE proof_harness.run_events (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  run_id uuid NOT NULL,
  sequence_no bigint NOT NULL CHECK (sequence_no > 0),
  execution_epoch bigint NOT NULL CHECK (execution_epoch > 0),
  fencing_generation bigint NOT NULL CHECK (fencing_generation > 0),
  event_type text NOT NULL,
  payload_digest text NOT NULL CHECK (payload_digest ~ '^sha256:[0-9a-f]{64}$'),
  payload_json jsonb NOT NULL,
  actor_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, run_id, sequence_no),
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness.runs (tenant_id, project_id, run_id)
);

CREATE TABLE proof_harness.proof_obligations (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  run_id uuid NOT NULL,
  obligation_id text NOT NULL,
  family text NOT NULL,
  severity text NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
  relation text NOT NULL,
  subject_revision text NOT NULL CHECK (subject_revision ~ '^sha256:[0-9a-f]{64}$'),
  scope_digest text NOT NULL CHECK (scope_digest ~ '^sha256:[0-9a-f]{64}$'),
  minimum_status text NOT NULL,
  accepted_evidence_classes jsonb NOT NULL,
  assumptions_digest text NOT NULL CHECK (assumptions_digest ~ '^sha256:[0-9a-f]{64}$'),
  state text NOT NULL CHECK (state IN ('PENDING', 'READY', 'RUNNING', 'CLOSED', 'REFUTED', 'BLOCKED')),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, run_id, obligation_id),
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness.runs (tenant_id, project_id, run_id)
);

CREATE TABLE proof_harness.proof_obligation_edges (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  run_id uuid NOT NULL,
  obligation_id text NOT NULL,
  dependency_id text NOT NULL,
  PRIMARY KEY (tenant_id, project_id, run_id, obligation_id, dependency_id),
  FOREIGN KEY (tenant_id, project_id, run_id, obligation_id)
    REFERENCES proof_harness.proof_obligations
      (tenant_id, project_id, run_id, obligation_id),
  FOREIGN KEY (tenant_id, project_id, run_id, dependency_id)
    REFERENCES proof_harness.proof_obligations
      (tenant_id, project_id, run_id, obligation_id),
  CHECK (obligation_id <> dependency_id)
);

CREATE TABLE proof_harness.evidence_objects (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  evidence_id uuid NOT NULL,
  subject_revision text NOT NULL CHECK (subject_revision ~ '^sha256:[0-9a-f]{64}$'),
  kind text NOT NULL,
  content_digest text NOT NULL CHECK (content_digest ~ '^sha256:[0-9a-f]{64}$'),
  content_length bigint NOT NULL CHECK (content_length >= 0),
  media_type text NOT NULL,
  inline_content bytea,
  object_store_ref jsonb,
  producer_execution_id text NOT NULL,
  producer_source text NOT NULL CHECK (producer_source IN ('ENGINE', 'RUNNER', 'VERIFIER', 'CERTIFIER', 'CUSTOMER', 'OPERATOR')),
  producer_tool_digest text NOT NULL CHECK (producer_tool_digest ~ '^sha256:[0-9a-f]{64}$'),
  environment_digest text NOT NULL CHECK (environment_digest ~ '^sha256:[0-9a-f]{64}$'),
  lineage_json jsonb NOT NULL,
  classification text NOT NULL CHECK (classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')),
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, evidence_id),
  UNIQUE (tenant_id, project_id, content_digest, producer_execution_id),
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES proof_harness.tenant_projects (tenant_id, project_id),
  CHECK ((inline_content IS NOT NULL)::integer + (object_store_ref IS NOT NULL)::integer = 1),
  CHECK (inline_content IS NULL OR
         (octet_length(inline_content) = content_length AND content_length <= 16777216)),
  CHECK (object_store_ref IS NULL OR
         (object_store_ref ?& ARRAY['provider', 'bucket', 'key', 'versionId'] AND
          jsonb_typeof(object_store_ref) = 'object'))
);

CREATE TABLE proof_harness.evidence_revocations (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  evidence_id uuid NOT NULL,
  revocation_id uuid NOT NULL,
  reason text NOT NULL,
  actor_id text NOT NULL,
  revoked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, evidence_id, revocation_id),
  FOREIGN KEY (tenant_id, project_id, evidence_id)
    REFERENCES proof_harness.evidence_objects (tenant_id, project_id, evidence_id)
);

CREATE TABLE proof_harness.proof_results (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  run_id uuid NOT NULL,
  result_id uuid NOT NULL,
  obligation_id text NOT NULL,
  status text NOT NULL,
  subject_revision text NOT NULL CHECK (subject_revision ~ '^sha256:[0-9a-f]{64}$'),
  scope_digest text NOT NULL CHECK (scope_digest ~ '^sha256:[0-9a-f]{64}$'),
  tool_name text NOT NULL,
  tool_digest text NOT NULL CHECK (tool_digest ~ '^sha256:[0-9a-f]{64}$'),
  tool_version text NOT NULL,
  options_digest text NOT NULL CHECK (options_digest ~ '^sha256:[0-9a-f]{64}$'),
  encoder_digest text NOT NULL CHECK (encoder_digest ~ '^sha256:[0-9a-f]{64}$'),
  environment_digest text NOT NULL CHECK (environment_digest ~ '^sha256:[0-9a-f]{64}$'),
  assumptions_digest text NOT NULL CHECK (assumptions_digest ~ '^sha256:[0-9a-f]{64}$'),
  evidence_classes_json jsonb NOT NULL,
  bounds_json jsonb NOT NULL,
  accepted boolean NOT NULL DEFAULT false,
  rejection_reason text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, run_id, result_id),
  FOREIGN KEY (tenant_id, project_id, run_id, obligation_id)
    REFERENCES proof_harness.proof_obligations
      (tenant_id, project_id, run_id, obligation_id),
  CHECK ((accepted AND rejection_reason IS NULL) OR (NOT accepted AND rejection_reason IS NOT NULL))
);

CREATE TABLE proof_harness.proof_result_evidence (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  run_id uuid NOT NULL,
  result_id uuid NOT NULL,
  evidence_id uuid NOT NULL,
  PRIMARY KEY (tenant_id, project_id, run_id, result_id, evidence_id),
  FOREIGN KEY (tenant_id, project_id, run_id, result_id)
    REFERENCES proof_harness.proof_results (tenant_id, project_id, run_id, result_id),
  FOREIGN KEY (tenant_id, project_id, evidence_id)
    REFERENCES proof_harness.evidence_objects (tenant_id, project_id, evidence_id)
);

CREATE TABLE proof_harness.gate_results (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  run_id uuid NOT NULL,
  evaluation_id uuid NOT NULL,
  gate_name text NOT NULL CHECK (gate_name IN ('P05', 'E0', 'E1', 'E2', 'E3', 'E4', 'E5')),
  decision text NOT NULL CHECK (decision IN ('PASS', 'FAIL', 'BLOCKED', 'NOT_RUN', 'UNKNOWN')),
  subject_revision text NOT NULL CHECK (subject_revision ~ '^sha256:[0-9a-f]{64}$'),
  evidence_root text NOT NULL CHECK (evidence_root ~ '^sha256:[0-9a-f]{64}$'),
  evaluator_identity text NOT NULL,
  evaluator_independent boolean NOT NULL,
  evaluated_at timestamptz NOT NULL,
  expires_at timestamptz,
  PRIMARY KEY (tenant_id, project_id, run_id, gate_name, evaluation_id),
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness.runs (tenant_id, project_id, run_id)
);

CREATE TABLE proof_harness.completion_reviews (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  run_id uuid NOT NULL,
  review_id uuid NOT NULL,
  revision_set_digest text NOT NULL CHECK (revision_set_digest ~ '^sha256:[0-9a-f]{64}$'),
  proof_graph_digest text NOT NULL CHECK (proof_graph_digest ~ '^sha256:[0-9a-f]{64}$'),
  evidence_root text NOT NULL CHECK (evidence_root ~ '^sha256:[0-9a-f]{64}$'),
  decision text NOT NULL CHECK (decision IN ('READY_FOR_EXTERNAL_GATE', 'BLOCKED', 'REJECTED', 'EXTERNALLY_VERIFIED', 'CERTIFIED')),
  independent_verification text NOT NULL CHECK (independent_verification IN ('NOT_RUN', 'PENDING', 'VERIFIED', 'REJECTED', 'REVOKED')),
  reviewer_identity text NOT NULL,
  reviewer_execution_source text NOT NULL,
  payload_digest text NOT NULL CHECK (payload_digest ~ '^sha256:[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, run_id, review_id),
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness.runs (tenant_id, project_id, run_id),
  CHECK (decision NOT IN ('EXTERNALLY_VERIFIED', 'CERTIFIED') OR independent_verification = 'VERIFIED')
);

CREATE TABLE proof_harness.external_signature_receipts (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  run_id uuid NOT NULL,
  review_id uuid NOT NULL,
  receipt_id uuid NOT NULL,
  key_id text NOT NULL,
  algorithm text NOT NULL CHECK (algorithm IN ('Ed25519', 'ECDSA-P256-SHA256', 'RSA-PSS-SHA256', 'X509-REMOTE')),
  payload_digest text NOT NULL CHECK (payload_digest ~ '^sha256:[0-9a-f]{64}$'),
  signature text NOT NULL CHECK (length(signature) >= 32),
  verifier_identity text NOT NULL,
  verifier_trust_root_digest text NOT NULL CHECK (verifier_trust_root_digest ~ '^sha256:[0-9a-f]{64}$'),
  attested_status text NOT NULL CHECK (attested_status IN ('EXTERNALLY_VERIFIED', 'CERTIFIED')),
  certification_authority boolean NOT NULL DEFAULT false,
  issued_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  verified_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, run_id, review_id, receipt_id),
  FOREIGN KEY (tenant_id, project_id, run_id, review_id)
    REFERENCES proof_harness.completion_reviews (tenant_id, project_id, run_id, review_id),
  CHECK (issued_at <= verified_at AND verified_at < expires_at),
  CHECK (attested_status <> 'CERTIFIED' OR certification_authority)
);

CREATE TABLE proof_harness.external_signature_revocations (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  run_id uuid NOT NULL,
  review_id uuid NOT NULL,
  receipt_id uuid NOT NULL,
  revocation_id uuid NOT NULL,
  reason text NOT NULL,
  actor_id text NOT NULL,
  revoked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, run_id, review_id, receipt_id, revocation_id),
  FOREIGN KEY (tenant_id, project_id, run_id, review_id, receipt_id)
    REFERENCES proof_harness.external_signature_receipts
      (tenant_id, project_id, run_id, review_id, receipt_id)
);

CREATE OR REPLACE FUNCTION proof_harness.assert_completion_signature()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness
AS $$
BEGIN
  IF NEW.decision IN ('EXTERNALLY_VERIFIED', 'CERTIFIED') AND NOT EXISTS (
    SELECT 1
      FROM proof_harness.external_signature_receipts AS receipt
     WHERE receipt.tenant_id = NEW.tenant_id
       AND receipt.project_id = NEW.project_id
       AND receipt.run_id = NEW.run_id
       AND receipt.review_id = NEW.review_id
       AND receipt.payload_digest = NEW.payload_digest
       AND receipt.attested_status = NEW.decision
       AND receipt.verifier_identity <> NEW.reviewer_identity
       AND receipt.issued_at <= receipt.verified_at
       AND receipt.verified_at <= clock_timestamp()
       AND clock_timestamp() < receipt.expires_at
       AND (
         NEW.decision <> 'CERTIFIED'
         OR receipt.certification_authority
       )
       AND NOT EXISTS (
         SELECT 1
           FROM proof_harness.external_signature_revocations AS revocation
          WHERE revocation.tenant_id = receipt.tenant_id
            AND revocation.project_id = receipt.project_id
            AND revocation.run_id = receipt.run_id
            AND revocation.review_id = receipt.review_id
            AND revocation.receipt_id = receipt.receipt_id
       )
  ) THEN
    RAISE EXCEPTION 'external completion decision lacks a live bound signature receipt'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE CONSTRAINT TRIGGER completion_review_signature_required
AFTER INSERT ON proof_harness.completion_reviews
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION proof_harness.assert_completion_signature();

CREATE VIEW proof_harness.effective_completion_reviews
WITH (security_barrier = true, security_invoker = true)
AS
SELECT
  review.*,
  CASE
    WHEN review.decision IN ('EXTERNALLY_VERIFIED', 'CERTIFIED')
      AND EXISTS (
        SELECT 1
          FROM proof_harness.external_signature_receipts AS receipt
          JOIN proof_harness.external_signature_revocations AS revocation
            ON revocation.tenant_id = receipt.tenant_id
           AND revocation.project_id = receipt.project_id
           AND revocation.run_id = receipt.run_id
           AND revocation.review_id = receipt.review_id
           AND revocation.receipt_id = receipt.receipt_id
         WHERE receipt.tenant_id = review.tenant_id
           AND receipt.project_id = review.project_id
           AND receipt.run_id = review.run_id
           AND receipt.review_id = review.review_id
           AND receipt.payload_digest = review.payload_digest
           AND receipt.attested_status = review.decision
           AND receipt.verifier_identity <> review.reviewer_identity
           AND (
             review.decision <> 'CERTIFIED'
             OR receipt.certification_authority
           )
      )
    THEN 'REVOKED'
    WHEN review.decision IN ('EXTERNALLY_VERIFIED', 'CERTIFIED')
      AND NOT EXISTS (
        SELECT 1
          FROM proof_harness.external_signature_receipts AS receipt
         WHERE receipt.tenant_id = review.tenant_id
           AND receipt.project_id = review.project_id
           AND receipt.run_id = review.run_id
           AND receipt.review_id = review.review_id
           AND receipt.payload_digest = review.payload_digest
           AND receipt.attested_status = review.decision
           AND receipt.verifier_identity <> review.reviewer_identity
           AND receipt.issued_at <= receipt.verified_at
           AND receipt.verified_at <= clock_timestamp()
           AND receipt.expires_at > clock_timestamp()
           AND (
             review.decision <> 'CERTIFIED'
             OR receipt.certification_authority
           )
           AND NOT EXISTS (
             SELECT 1
               FROM proof_harness.external_signature_revocations AS revocation
              WHERE revocation.tenant_id = receipt.tenant_id
                AND revocation.project_id = receipt.project_id
                AND revocation.run_id = receipt.run_id
                AND revocation.review_id = receipt.review_id
                AND revocation.receipt_id = receipt.receipt_id
           )
      )
    THEN 'EXPIRED'
    ELSE review.decision
  END AS effective_decision
FROM proof_harness.completion_reviews AS review;

CREATE TABLE proof_harness.idempotency_receipts (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  actor_id text NOT NULL,
  operation text NOT NULL,
  idempotency_key text NOT NULL,
  request_digest text NOT NULL CHECK (request_digest ~ '^sha256:[0-9a-f]{64}$'),
  response_digest text NOT NULL CHECK (response_digest ~ '^sha256:[0-9a-f]{64}$'),
  response_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, actor_id, operation, idempotency_key),
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES proof_harness.tenant_projects (tenant_id, project_id)
);

CREATE TABLE proof_harness.audit_log (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  sequence_no bigint GENERATED ALWAYS AS IDENTITY,
  event_id uuid NOT NULL,
  actor_id text NOT NULL,
  action text NOT NULL,
  resource_type text NOT NULL,
  resource_id text NOT NULL,
  outcome text NOT NULL,
  previous_digest text CHECK (previous_digest IS NULL OR previous_digest ~ '^sha256:[0-9a-f]{64}$'),
  record_digest text NOT NULL CHECK (record_digest ~ '^sha256:[0-9a-f]{64}$'),
  detail_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, sequence_no),
  UNIQUE (tenant_id, project_id, event_id),
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES proof_harness.tenant_projects (tenant_id, project_id)
);

CREATE TABLE proof_harness.outbox (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  event_id uuid NOT NULL,
  aggregate_type text NOT NULL,
  aggregate_id text NOT NULL,
  event_type text NOT NULL,
  payload_digest text NOT NULL CHECK (payload_digest ~ '^sha256:[0-9a-f]{64}$'),
  payload_json jsonb NOT NULL,
  state text NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING', 'DELIVERING', 'DELIVERED', 'UNKNOWN', 'DEAD_LETTER')),
  attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  lease_owner text,
  lease_expires_at timestamptz,
  provider_receipt text,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, event_id),
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES proof_harness.tenant_projects (tenant_id, project_id)
);

CREATE TABLE proof_harness.usage_ledger (
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  usage_id uuid NOT NULL,
  run_id uuid,
  meter text NOT NULL,
  quantity numeric(38, 12) NOT NULL CHECK (quantity >= 0),
  unit text NOT NULL,
  currency char(3),
  amount numeric(38, 12),
  rounding_rule text,
  source_digest text NOT NULL CHECK (source_digest ~ '^sha256:[0-9a-f]{64}$'),
  occurred_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, project_id, usage_id),
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES proof_harness.tenant_projects (tenant_id, project_id),
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness.runs (tenant_id, project_id, run_id),
  CHECK ((currency IS NULL AND amount IS NULL AND rounding_rule IS NULL) OR
         (currency IS NOT NULL AND amount IS NOT NULL AND rounding_rule IS NOT NULL))
);

-- -------------------------------------------------------------------------
-- Executable Store Protocol tables.  These names and column order mirror the
-- dependency-free SQLite local-engineering backend, while PostgreSQL provides
-- real transaction isolation and forced RLS.  Evidence and checkpoints are
-- exact inline bytes with a hard 16 MiB bound; no unverified URI is accepted.

CREATE OR REPLACE FUNCTION proof_harness.current_tenant_key()
RETURNS text
LANGUAGE sql
STABLE
SET search_path = pg_catalog
AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')
$$;

CREATE OR REPLACE FUNCTION proof_harness.current_project_key()
RETURNS text
LANGUAGE sql
STABLE
SET search_path = pg_catalog
AS $$
  SELECT NULLIF(current_setting('app.project_id', true), '')
$$;

CREATE TABLE proof_harness_runtime.schema_migrations (
  version integer PRIMARY KEY CHECK (version > 0),
  migration_name text NOT NULL UNIQUE,
  applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO proof_harness_runtime.schema_migrations(version, migration_name)
VALUES (1, 'V001__proof_harness_core.sql');

-- The migration runner records a detached digest of this complete SQL file
-- after application.  Embedding the file digest in this file would be
-- self-referential.  Production readiness requires the ledger value to match
-- the independently packaged runtime constant.
CREATE TABLE proof_harness_runtime.migration_digest_ledger (
  version integer NOT NULL,
  migration_name text NOT NULL,
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  recorded_by text NOT NULL CHECK (length(btrim(recorded_by)) > 0),
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (version, migration_name),
  FOREIGN KEY (version) REFERENCES proof_harness_runtime.schema_migrations(version) ON DELETE RESTRICT,
  UNIQUE (content_sha256)
);

CREATE TABLE proof_harness_runtime.tenants (
  tenant_id text PRIMARY KEY,
  created_at timestamptz NOT NULL
);

CREATE TABLE proof_harness_runtime.projects (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  created_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id),
  FOREIGN KEY (tenant_id) REFERENCES proof_harness_runtime.tenants(tenant_id) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.actors (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  actor_id text NOT NULL,
  created_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, actor_id),
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES proof_harness_runtime.projects(tenant_id, project_id) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.runs (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  run_id text NOT NULL,
  actor_id text NOT NULL,
  revision_set_id text NOT NULL,
  state text NOT NULL CHECK (state IN (
    'CREATED', 'ADMITTED', 'PLANNING', 'EXECUTING', 'CHECKPOINTED',
    'PAUSED', 'RESUMING', 'AWAITING_REVIEW', 'VERIFYING', 'CERTIFYING',
    'COMPLETED', 'BLOCKED', 'FAILED', 'CANCELLED', 'TIMED_OUT', 'PARTIAL'
  )),
  sequence bigint NOT NULL DEFAULT 0 CHECK (sequence >= 0),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  lease_owner text,
  lease_token_sha256 text CHECK (lease_token_sha256 IS NULL OR lease_token_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  lease_expires_at timestamptz,
  deadline_at timestamptz,
  last_checkpoint_id text,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, run_id),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.idempotency_receipts (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  actor_id text NOT NULL,
  operation text NOT NULL,
  idempotency_key text NOT NULL,
  request_sha256 text NOT NULL CHECK (request_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  response_json jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, operation, idempotency_key),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.control_plane_receipts (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  actor_id text NOT NULL,
  operation text NOT NULL,
  idempotency_key text NOT NULL,
  request_sha256 text NOT NULL CHECK (request_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  run_id text NOT NULL,
  request_json jsonb NOT NULL,
  response_json jsonb,
  created_at timestamptz NOT NULL,
  completed_at timestamptz,
  PRIMARY KEY (tenant_id, project_id, operation, idempotency_key),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  CHECK ((response_json IS NULL AND completed_at IS NULL) OR
         (response_json IS NOT NULL AND completed_at IS NOT NULL))
);

-- Global scheduler index.  These two relations deliberately do not expose an
-- RLS-selectable queue: all direct privileges are revoked and the only
-- production access path is ``proof_harness.claim_next_control_plane_job``.
-- That SECURITY DEFINER function returns exactly one complete scope and then
-- switches into that scope before reading the tenant receipt.
CREATE TABLE proof_harness_runtime.scheduler_jobs (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  actor_id text NOT NULL,
  operation text NOT NULL,
  idempotency_key text NOT NULL,
  request_sha256 text NOT NULL CHECK (request_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  run_id text NOT NULL,
  state text NOT NULL CHECK (state IN ('PENDING','CLAIMED','COMPLETED')),
  scheduler_role text,
  worker_instance_id text,
  lease_token_sha256 text CHECK (lease_token_sha256 IS NULL OR lease_token_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  lease_generation bigint NOT NULL DEFAULT 0 CHECK (lease_generation >= 0),
  lease_expires_at timestamptz,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, operation, idempotency_key),
  FOREIGN KEY (tenant_id, project_id, operation, idempotency_key)
    REFERENCES proof_harness_runtime.control_plane_receipts
      (tenant_id, project_id, operation, idempotency_key) ON DELETE RESTRICT,
  CHECK ((state = 'PENDING' AND scheduler_role IS NULL AND worker_instance_id IS NULL
          AND lease_token_sha256 IS NULL AND lease_expires_at IS NULL)
      OR (state = 'CLAIMED' AND scheduler_role IS NOT NULL AND worker_instance_id IS NOT NULL
          AND lease_token_sha256 IS NOT NULL AND lease_expires_at IS NOT NULL)
      OR state = 'COMPLETED')
);

CREATE TABLE proof_harness_runtime.scheduler_claim_events (
  event_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  operation text NOT NULL,
  idempotency_key text NOT NULL,
  scheduler_role text NOT NULL,
  worker_instance_id text NOT NULL,
  lease_generation bigint NOT NULL CHECK (lease_generation >= 1),
  occurred_at timestamptz NOT NULL,
  FOREIGN KEY (tenant_id, project_id, operation, idempotency_key)
    REFERENCES proof_harness_runtime.scheduler_jobs
      (tenant_id, project_id, operation, idempotency_key) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.evidence (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  evidence_id text NOT NULL,
  actor_id text NOT NULL,
  subject_revision text NOT NULL CHECK (subject_revision ~ '^sha256:[0-9a-f]{64}$'),
  evidence_class text NOT NULL,
  scope text NOT NULL,
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  content_bytes bytea NOT NULL CHECK (octet_length(content_bytes) <= 16777216),
  record_json jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  expires_at timestamptz,
  PRIMARY KEY (tenant_id, project_id, evidence_id),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  CHECK (expires_at IS NULL OR expires_at > created_at)
);

CREATE TABLE proof_harness_runtime.evidence_revocations (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  revocation_id text NOT NULL,
  evidence_id text NOT NULL,
  actor_id text NOT NULL,
  reason text NOT NULL CHECK (length(btrim(reason)) > 0),
  created_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, revocation_id),
  UNIQUE (tenant_id, project_id, evidence_id),
  FOREIGN KEY (tenant_id, project_id, evidence_id)
    REFERENCES proof_harness_runtime.evidence(tenant_id, project_id, evidence_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.audit_events (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  event_id text NOT NULL,
  actor_id text NOT NULL,
  event_type text NOT NULL,
  subject_id text NOT NULL,
  payload_json jsonb NOT NULL,
  payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, event_id),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.outbox_events (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  event_id text NOT NULL,
  topic text NOT NULL,
  aggregate_id text NOT NULL,
  payload_json jsonb NOT NULL,
  payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, event_id),
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES proof_harness_runtime.projects(tenant_id, project_id) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.outbox_deliveries (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  delivery_id text NOT NULL,
  event_id text NOT NULL,
  destination text NOT NULL,
  state text NOT NULL CHECK (state IN ('DELIVERED', 'FAILED', 'UNKNOWN')),
  detail_sha256 text CHECK (detail_sha256 IS NULL OR detail_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, delivery_id),
  FOREIGN KEY (tenant_id, project_id, event_id)
    REFERENCES proof_harness_runtime.outbox_events(tenant_id, project_id, event_id) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.run_checkpoints (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  checkpoint_id text NOT NULL,
  run_id text NOT NULL,
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  sequence bigint NOT NULL CHECK (sequence >= 1),
  payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  payload_bytes bytea NOT NULL CHECK (octet_length(payload_bytes) BETWEEN 1 AND 16777216),
  created_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, checkpoint_id),
  UNIQUE (tenant_id, project_id, run_id, sequence),
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.external_effects (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  effect_id text NOT NULL,
  run_id text NOT NULL,
  actor_id text NOT NULL,
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  provider text NOT NULL,
  operation text NOT NULL,
  idempotency_key text NOT NULL,
  request_sha256 text NOT NULL CHECK (request_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  state text NOT NULL CHECK (state IN (
    'STARTED', 'SUCCEEDED', 'FAILED_RETRYABLE', 'FAILED_TERMINAL', 'UNKNOWN_RESULT', 'RECONCILED'
  )),
  external_reference text,
  reconciliation_strategy text NOT NULL,
  version bigint NOT NULL DEFAULT 0 CHECK (version >= 0),
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, effect_id),
  UNIQUE (tenant_id, project_id, provider, operation, idempotency_key),
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.effect_events (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  event_id text NOT NULL,
  effect_id text NOT NULL,
  state text NOT NULL,
  detail_json jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, event_id),
  FOREIGN KEY (tenant_id, project_id, effect_id)
    REFERENCES proof_harness_runtime.external_effects(tenant_id, project_id, effect_id) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.metric_points (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  metric_id text NOT NULL,
  name text NOT NULL,
  value double precision NOT NULL CHECK (value NOT IN ('Infinity'::double precision, '-Infinity'::double precision) AND value <> 'NaN'::double precision),
  labels_json jsonb NOT NULL,
  occurred_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, metric_id),
  FOREIGN KEY (tenant_id, project_id)
    REFERENCES proof_harness_runtime.projects(tenant_id, project_id) ON DELETE RESTRICT
);

-- -------------------------------------------------------------------------
-- Durable certification authority data plane.  IDs are opaque text to match
-- the runtime Store API; no UUID reinterpretation or semantic-schema mapping
-- is performed.  An independent certifier role owns no table and receives
-- append-only grants only.  Exact canonical bytes are retained so digest
-- verification survives process and instance restarts.

CREATE TABLE proof_harness_runtime.certification_assessments (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  assessment_digest text NOT NULL CHECK (assessment_digest ~ '^sha256:[0-9a-f]{64}$'),
  certificate_id text NOT NULL,
  run_id text NOT NULL,
  actor_id text NOT NULL,
  goal_id text NOT NULL,
  revision_set_id text NOT NULL,
  revision_set_digest text NOT NULL CHECK (revision_set_digest ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_json jsonb NOT NULL,
  revision_set_bytes bytea NOT NULL CHECK (octet_length(revision_set_bytes) BETWEEN 2 AND 4194304),
  proof_graph_digest text NOT NULL CHECK (proof_graph_digest ~ '^sha256:[0-9a-f]{64}$'),
  proof_graph_bytes bytea NOT NULL CHECK (octet_length(proof_graph_bytes) BETWEEN 2 AND 4194304),
  evidence_root text NOT NULL CHECK (evidence_root ~ '^sha256:[0-9a-f]{64}$'),
  production_assessment boolean NOT NULL,
  local_status text NOT NULL CHECK (local_status IN ('BLOCKED','FAILED_ASSURANCE','READY_FOR_EXTERNAL_GATE')),
  reviewer_identity text NOT NULL,
  reviewer_independent boolean NOT NULL,
  certified_envelope_json jsonb NOT NULL,
  status_counts_json jsonb NOT NULL,
  unresolved_risks_json jsonb NOT NULL,
  payload_json jsonb NOT NULL,
  payload_bytes bytea NOT NULL CHECK (octet_length(payload_bytes) BETWEEN 2 AND 4194304),
  certificate_json jsonb NOT NULL,
  issued_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, assessment_digest),
  UNIQUE (tenant_id, project_id, certificate_id),
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  CHECK (reviewer_independent OR local_status <> 'READY_FOR_EXTERNAL_GATE'),
  CHECK (local_status <> 'READY_FOR_EXTERNAL_GATE' OR jsonb_array_length(unresolved_risks_json) = 0),
  CHECK (revision_set_json = (convert_from(revision_set_bytes, 'UTF8')::jsonb)->'revisions'),
  CHECK (payload_json = (convert_from(payload_bytes, 'UTF8')::jsonb)),
  CHECK (revision_set_digest = 'sha256:' || encode(sha256(
    convert_to('elmos.proof-harness.v1','UTF8') || decode('00','hex') ||
    convert_to('certification-revision-set','UTF8') || decode('00','hex') || revision_set_bytes
  ), 'hex')),
  CHECK (proof_graph_digest = 'sha256:' || encode(sha256(
    convert_to('elmos.proof-harness.v1','UTF8') || decode('00','hex') ||
    convert_to('proof-obligation-graph-state','UTF8') || decode('00','hex') || proof_graph_bytes
  ), 'hex')),
  CHECK (assessment_digest = 'sha256:' || encode(sha256(
    convert_to('elmos.proof-harness.v1','UTF8') || decode('00','hex') ||
    convert_to('local-certification-assessment','UTF8') || decode('00','hex') || payload_bytes
  ), 'hex'))
);

CREATE TABLE proof_harness_runtime.certification_gate_results (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  assessment_digest text NOT NULL,
  ordinal integer NOT NULL CHECK (ordinal BETWEEN 0 AND 6),
  gate_name text NOT NULL CHECK (gate_name IN ('P05','E0','E1','E2','E3','E4','E5')),
  decision text NOT NULL CHECK (decision IN ('PASS','FAIL','BLOCKED','NOT_RUN','UNKNOWN','NOT_APPLICABLE')),
  evidence_ids_json jsonb NOT NULL,
  reasons_json jsonb NOT NULL,
  result_digest text NOT NULL CHECK (result_digest ~ '^sha256:[0-9a-f]{64}$'),
  PRIMARY KEY (tenant_id, project_id, assessment_digest, gate_name),
  UNIQUE (tenant_id, project_id, assessment_digest, ordinal),
  FOREIGN KEY (tenant_id, project_id, assessment_digest)
    REFERENCES proof_harness_runtime.certification_assessments
      (tenant_id, project_id, assessment_digest) ON DELETE RESTRICT,
  CHECK (jsonb_typeof(evidence_ids_json) = 'array'),
  CHECK (jsonb_typeof(reasons_json) = 'array'),
  CHECK (decision <> 'PASS' OR jsonb_array_length(evidence_ids_json) > 0)
);

CREATE TABLE proof_harness_runtime.certification_evidence_links (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  assessment_digest text NOT NULL,
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  evidence_id text NOT NULL,
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  PRIMARY KEY (tenant_id, project_id, assessment_digest, evidence_id),
  UNIQUE (tenant_id, project_id, assessment_digest, ordinal),
  FOREIGN KEY (tenant_id, project_id, assessment_digest)
    REFERENCES proof_harness_runtime.certification_assessments
      (tenant_id, project_id, assessment_digest) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, evidence_id)
    REFERENCES proof_harness_runtime.evidence(tenant_id, project_id, evidence_id) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.certification_external_receipts (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  assessment_digest text NOT NULL,
  receipt_id text NOT NULL,
  verification_evidence_id text NOT NULL,
  payload_digest text NOT NULL CHECK (payload_digest ~ '^sha256:[0-9a-f]{64}$'),
  certificate_id text NOT NULL,
  provider_id text NOT NULL,
  signer_identity text NOT NULL,
  key_id text NOT NULL,
  algorithm text NOT NULL CHECK (algorithm IN ('Ed25519','ECDSA-P256-SHA256','RSA-PSS-SHA256','X509-REMOTE')),
  signature_bytes bytea NOT NULL CHECK (octet_length(signature_bytes) >= 32),
  signed_payload_bytes bytea NOT NULL CHECK (octet_length(signed_payload_bytes) BETWEEN 2 AND 4194304),
  receipt_json_bytes bytea NOT NULL CHECK (octet_length(receipt_json_bytes) BETWEEN 2 AND 4194304),
  receipt_sha256 text NOT NULL CHECK (receipt_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  trust_anchor_sha256 text NOT NULL CHECK (trust_anchor_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  attested_status text NOT NULL CHECK (attested_status IN ('EXTERNALLY_VERIFIED','CERTIFIED')),
  independent boolean NOT NULL,
  certification_authority boolean NOT NULL,
  cryptographically_verified boolean NOT NULL,
  issued_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  verified_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, receipt_id),
  UNIQUE (tenant_id, project_id, assessment_digest, attested_status),
  FOREIGN KEY (tenant_id, project_id, assessment_digest)
    REFERENCES proof_harness_runtime.certification_assessments
      (tenant_id, project_id, assessment_digest) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, verification_evidence_id)
    REFERENCES proof_harness_runtime.evidence(tenant_id, project_id, evidence_id) ON DELETE RESTRICT,
  CHECK (payload_digest = assessment_digest),
  CHECK (issued_at <= verified_at AND verified_at < expires_at),
  CHECK (attested_status <> 'CERTIFIED' OR certification_authority),
  CHECK (receipt_sha256 = 'sha256:' || encode(sha256(
    convert_to('elmos.proof-harness.v1','UTF8') || decode('00','hex') ||
    convert_to('external-signature-receipt','UTF8') || decode('00','hex') || receipt_json_bytes
  ), 'hex'))
);

CREATE TABLE proof_harness_runtime.certification_external_decisions (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  assessment_digest text NOT NULL,
  decision_id text NOT NULL,
  receipt_id text NOT NULL,
  status text NOT NULL CHECK (status IN ('EXTERNALLY_VERIFIED','CERTIFIED')),
  external_certificate_digest text NOT NULL CHECK (external_certificate_digest ~ '^sha256:[0-9a-f]{64}$'),
  external_certificate_json jsonb NOT NULL,
  external_certificate_bytes bytea NOT NULL CHECK (octet_length(external_certificate_bytes) BETWEEN 2 AND 4194304),
  decided_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, decision_id),
  UNIQUE (tenant_id, project_id, assessment_digest, status),
  FOREIGN KEY (tenant_id, project_id, assessment_digest)
    REFERENCES proof_harness_runtime.certification_assessments
      (tenant_id, project_id, assessment_digest) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, receipt_id)
    REFERENCES proof_harness_runtime.certification_external_receipts
      (tenant_id, project_id, receipt_id) ON DELETE RESTRICT,
  CHECK (external_certificate_json = (convert_from(external_certificate_bytes, 'UTF8')::jsonb)),
  CHECK (external_certificate_digest = 'sha256:' || encode(sha256(
    convert_to('elmos.proof-harness.v1','UTF8') || decode('00','hex') ||
    convert_to('external-completion-certificate','UTF8') || decode('00','hex') || external_certificate_bytes
  ), 'hex'))
);

CREATE TABLE proof_harness_runtime.certification_signature_revocations (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  revocation_id text NOT NULL,
  receipt_id text NOT NULL,
  assessment_digest text NOT NULL,
  actor_id text NOT NULL,
  reason text NOT NULL CHECK (length(btrim(reason)) > 0),
  revoked_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, revocation_id),
  UNIQUE (tenant_id, project_id, receipt_id),
  FOREIGN KEY (tenant_id, project_id, receipt_id)
    REFERENCES proof_harness_runtime.certification_external_receipts
      (tenant_id, project_id, receipt_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.certification_events (
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  event_id text NOT NULL,
  actor_id text NOT NULL,
  event_type text NOT NULL CHECK (event_type IN (
    'LOCAL_ASSESSMENT_RECORDED','EXTERNAL_DECISION_RECORDED','EXTERNAL_SIGNATURE_REVOKED'
  )),
  subject_id text NOT NULL,
  detail_json jsonb NOT NULL,
  detail_sha256 text NOT NULL CHECK (detail_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  occurred_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, project_id, event_id),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION proof_harness.reject_immutable_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness
AS $$
BEGIN
  RAISE EXCEPTION 'immutable relation % cannot be updated or deleted', TG_TABLE_NAME
    USING ERRCODE = '55000';
END
$$;

CREATE OR REPLACE FUNCTION proof_harness.assert_runtime_evidence_integrity()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime, proof_harness
AS $$
BEGIN
  IF NEW.content_sha256 IS DISTINCT FROM 'sha256:' || encode(sha256(
    convert_to('elmos.proof-harness.v1','UTF8') || decode('00','hex') ||
    convert_to('evidence-content','UTF8') || decode('00','hex') || NEW.content_bytes
  ), 'hex') THEN
    RAISE EXCEPTION 'runtime evidence content digest does not match its exact bytes'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION proof_harness.assert_event_fence()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness
AS $$
DECLARE
  current_epoch bigint;
  current_fence bigint;
BEGIN
  SELECT execution_epoch, fencing_generation
    INTO current_epoch, current_fence
    FROM proof_harness.runs
   WHERE tenant_id = NEW.tenant_id
     AND project_id = NEW.project_id
     AND run_id = NEW.run_id
   FOR KEY SHARE;
  IF NOT FOUND OR current_epoch <> NEW.execution_epoch OR current_fence <> NEW.fencing_generation THEN
    RAISE EXCEPTION 'stale or missing execution fence' USING ERRCODE = '40001';
  END IF;
  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION proof_harness.guard_runtime_control_receipt()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
       OR OLD.project_id IS DISTINCT FROM NEW.project_id
       OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
       OR OLD.operation IS DISTINCT FROM NEW.operation
       OR OLD.idempotency_key IS DISTINCT FROM NEW.idempotency_key
       OR OLD.request_sha256 IS DISTINCT FROM NEW.request_sha256
       OR OLD.run_id IS DISTINCT FROM NEW.run_id
       OR OLD.request_json IS DISTINCT FROM NEW.request_json
       OR OLD.created_at IS DISTINCT FROM NEW.created_at
       OR OLD.response_json IS NOT NULL
       OR NEW.response_json IS NULL
       OR NEW.completed_at IS NULL THEN
      RAISE EXCEPTION 'control-plane receipt identity is immutable and may complete once'
        USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.response_json IS NOT NULL
     OR OLD.completed_at IS NOT NULL
     OR OLD.actor_id IS DISTINCT FROM NULLIF(current_setting('app.actor_id', true), '') THEN
    RAISE EXCEPTION 'only the owning actor may remove an incomplete receipt'
      USING ERRCODE = '55000';
  END IF;
  RETURN OLD;
END
$$;

CREATE OR REPLACE FUNCTION proof_harness.enqueue_runtime_scheduler_job()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, proof_harness_runtime
AS $$
BEGIN
  IF NEW.operation = 'invoke' THEN
    INSERT INTO proof_harness_runtime.scheduler_jobs(
      tenant_id,project_id,actor_id,operation,idempotency_key,request_sha256,run_id,
      state,lease_generation,created_at,updated_at
    ) VALUES (
      NEW.tenant_id,NEW.project_id,NEW.actor_id,NEW.operation,NEW.idempotency_key,
      NEW.request_sha256,NEW.run_id,'PENDING',0,NEW.created_at,NEW.created_at
    );
  END IF;
  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION proof_harness.complete_runtime_scheduler_job()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, proof_harness_runtime
AS $$
BEGIN
  IF OLD.response_json IS NULL AND NEW.response_json IS NOT NULL THEN
    UPDATE proof_harness_runtime.scheduler_jobs
       SET state='COMPLETED',lease_token_sha256=NULL,lease_expires_at=NULL,
           updated_at=NEW.completed_at
     WHERE tenant_id=NEW.tenant_id AND project_id=NEW.project_id
       AND operation=NEW.operation AND idempotency_key=NEW.idempotency_key;
  END IF;
  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION proof_harness.claim_next_control_plane_job(
  requested_worker_instance_id text,
  requested_ttl_seconds integer DEFAULT 60
)
RETURNS TABLE(
  tenant_id text,
  project_id text,
  actor_id text,
  operation text,
  idempotency_key text,
  request_sha256 text,
  run_id text,
  request_json jsonb,
  scheduler_role text,
  worker_instance_id text,
  lease_token text,
  lease_generation bigint,
  lease_expires_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, proof_harness_runtime, proof_harness
AS $$
DECLARE
  candidate proof_harness_runtime.scheduler_jobs%ROWTYPE;
  opaque_token text;
  current_time timestamptz := clock_timestamp();
  expires_at timestamptz;
  bound_request jsonb;
BEGIN
  IF NOT pg_has_role(session_user, 'proof_harness_scheduler_authority', 'MEMBER') THEN
    RAISE EXCEPTION 'caller is not a member of the scheduler authority role'
      USING ERRCODE = '42501';
  END IF;
  IF requested_worker_instance_id IS NULL
     OR length(btrim(requested_worker_instance_id)) < 1
     OR length(requested_worker_instance_id) > 256
     OR requested_ttl_seconds < 5
     OR requested_ttl_seconds > 900
  THEN
    RAISE EXCEPTION 'scheduler worker identity or lease ttl is invalid'
      USING ERRCODE = '22023';
  END IF;

  SELECT job.* INTO candidate
    FROM proof_harness_runtime.scheduler_jobs AS job
   WHERE job.state = 'PENDING'
      OR (job.state = 'CLAIMED' AND job.lease_expires_at <= current_time)
   ORDER BY job.created_at,job.tenant_id,job.project_id,job.operation,job.idempotency_key
   FOR UPDATE SKIP LOCKED
   LIMIT 1;
  IF NOT FOUND THEN
    RETURN;
  END IF;

  opaque_token := gen_random_uuid()::text || gen_random_uuid()::text;
  expires_at := current_time + make_interval(secs => requested_ttl_seconds);
  UPDATE proof_harness_runtime.scheduler_jobs AS job
     SET state='CLAIMED',scheduler_role=session_user,
         worker_instance_id=requested_worker_instance_id,
         lease_token_sha256='sha256:' || encode(sha256(
           convert_to('elmos.proof-harness.v1','UTF8') || decode('00','hex') ||
           convert_to('scheduler-lease-token','UTF8') || decode('00','hex') ||
           convert_to(opaque_token,'UTF8')
         ),'hex'),
         lease_generation=job.lease_generation+1,
         lease_expires_at=expires_at,updated_at=current_time
   WHERE job.tenant_id=candidate.tenant_id AND job.project_id=candidate.project_id
     AND job.operation=candidate.operation AND job.idempotency_key=candidate.idempotency_key
   RETURNING job.* INTO candidate;

  PERFORM set_config('app.tenant_id', candidate.tenant_id, true);
  PERFORM set_config('app.project_id', candidate.project_id, true);
  PERFORM set_config('app.actor_id', candidate.actor_id, true);
  SELECT receipt.request_json INTO bound_request
    FROM proof_harness_runtime.control_plane_receipts AS receipt
   WHERE receipt.tenant_id=candidate.tenant_id AND receipt.project_id=candidate.project_id
     AND receipt.operation=candidate.operation AND receipt.idempotency_key=candidate.idempotency_key
     AND receipt.request_sha256=candidate.request_sha256 AND receipt.response_json IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'claimed scheduler job lacks its exact pending tenant receipt'
      USING ERRCODE = '23503';
  END IF;

  INSERT INTO proof_harness_runtime.scheduler_claim_events(
    event_id,tenant_id,project_id,operation,idempotency_key,scheduler_role,
    worker_instance_id,lease_generation,occurred_at
  ) VALUES (
    gen_random_uuid()::text,candidate.tenant_id,candidate.project_id,candidate.operation,
    candidate.idempotency_key,session_user,requested_worker_instance_id,
    candidate.lease_generation,current_time
  );

  RETURN QUERY SELECT
    candidate.tenant_id,candidate.project_id,candidate.actor_id,candidate.operation,
    candidate.idempotency_key,candidate.request_sha256,candidate.run_id,bound_request,
    session_user::text,requested_worker_instance_id,opaque_token,
    candidate.lease_generation,expires_at;
END
$$;

CREATE OR REPLACE FUNCTION proof_harness.canonical_utc_timestamp(value timestamptz)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $$
  SELECT to_char(value AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
$$;

CREATE OR REPLACE FUNCTION proof_harness.assert_runtime_certification_assessment()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime, proof_harness
AS $$
DECLARE
  gate_payload jsonb;
  evidence_payload jsonb;
  expected_payload jsonb;
  revision_payload jsonb;
  graph_payload jsonb;
  observed_gates text[];
  required_gates text[];
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM proof_harness_runtime.runs AS run
     WHERE run.tenant_id = NEW.tenant_id
       AND run.project_id = NEW.project_id
       AND run.run_id = NEW.run_id
       AND run.revision_set_id = NEW.revision_set_id
  ) THEN
    RAISE EXCEPTION 'certification assessment run/revision binding is invalid'
      USING ERRCODE = '23514';
  END IF;

  revision_payload := convert_from(NEW.revision_set_bytes, 'UTF8')::jsonb;
  IF revision_payload <> jsonb_build_object(
       'revision_set_id', NEW.revision_set_id,
       'tenant_id', NEW.tenant_id,
       'project_id', NEW.project_id,
       'goal_id', NEW.goal_id,
       'revisions', NEW.revision_set_json
     )
     OR (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(NEW.revision_set_json) AS key)
        <> ARRAY['baseline_repository','domain_pack','environment','model_route','policy',
                 'requirements','source_repository','toolchain','workflow']::text[]
  THEN
    RAISE EXCEPTION 'certification revision set is not the exact nine-dimensional snapshot'
      USING ERRCODE = '23514';
  END IF;

  graph_payload := convert_from(NEW.proof_graph_bytes, 'UTF8')::jsonb;
  IF graph_payload->>'tenant_id' IS DISTINCT FROM NEW.tenant_id
     OR graph_payload->>'project_id' IS DISTINCT FROM NEW.project_id
     OR graph_payload->>'goal_id' IS DISTINCT FROM NEW.goal_id
     OR graph_payload->'status_counts' IS DISTINCT FROM NEW.status_counts_json
     OR jsonb_typeof(graph_payload->'obligations') <> 'array'
     OR jsonb_typeof(graph_payload->'edges') <> 'array'
     OR jsonb_typeof(graph_payload->'decisions') <> 'array'
  THEN
    RAISE EXCEPTION 'certification proof graph payload binding is invalid'
      USING ERRCODE = '23514';
  END IF;

  SELECT COALESCE(jsonb_agg(jsonb_build_object(
           'gate', gate_name,
           'decision', decision,
           'evidence_ids', evidence_ids_json,
           'reasons', reasons_json
         ) ORDER BY ordinal), '[]'::jsonb),
         array_agg(gate_name ORDER BY gate_name)
    INTO gate_payload, observed_gates
    FROM proof_harness_runtime.certification_gate_results
   WHERE tenant_id = NEW.tenant_id
     AND project_id = NEW.project_id
     AND assessment_digest = NEW.assessment_digest;

  SELECT COALESCE(jsonb_agg(to_jsonb(evidence_id) ORDER BY ordinal), '[]'::jsonb)
    INTO evidence_payload
    FROM proof_harness_runtime.certification_evidence_links
   WHERE tenant_id = NEW.tenant_id
     AND project_id = NEW.project_id
     AND assessment_digest = NEW.assessment_digest;

  IF NEW.local_status = 'READY_FOR_EXTERNAL_GATE' THEN
    required_gates := CASE WHEN NEW.production_assessment
      THEN ARRAY['E0','E1','E2','E3','E4','E5','P05']::text[]
      ELSE ARRAY['E0','E1','E2','E3','E4']::text[]
    END;
    IF observed_gates IS DISTINCT FROM required_gates OR EXISTS (
      SELECT 1 FROM proof_harness_runtime.certification_gate_results
       WHERE tenant_id = NEW.tenant_id
         AND project_id = NEW.project_id
         AND assessment_digest = NEW.assessment_digest
         AND decision <> 'PASS'
    ) THEN
      RAISE EXCEPTION 'ready certification assessment lacks the exact unique passing gate set'
        USING ERRCODE = '23514';
    END IF;
  END IF;

  IF evidence_payload = '[]'::jsonb OR EXISTS (
    SELECT 1
      FROM proof_harness_runtime.certification_evidence_links AS link
      LEFT JOIN proof_harness_runtime.evidence AS evidence
        ON evidence.tenant_id = link.tenant_id
       AND evidence.project_id = link.project_id
       AND evidence.evidence_id = link.evidence_id
     WHERE link.tenant_id = NEW.tenant_id
       AND link.project_id = NEW.project_id
       AND link.assessment_digest = NEW.assessment_digest
       AND (
         evidence.evidence_id IS NULL
         OR evidence.content_sha256 <> link.content_sha256
         OR evidence.content_sha256 IS DISTINCT FROM 'sha256:' || encode(sha256(
           convert_to('elmos.proof-harness.v1','UTF8') || decode('00','hex') ||
           convert_to('evidence-content','UTF8') || decode('00','hex') || evidence.content_bytes
         ), 'hex')
         OR (evidence.expires_at IS NOT NULL AND evidence.expires_at <= clock_timestamp())
         OR EXISTS (
           SELECT 1 FROM proof_harness_runtime.evidence_revocations AS revocation
            WHERE revocation.tenant_id = link.tenant_id
              AND revocation.project_id = link.project_id
              AND revocation.evidence_id = link.evidence_id
         )
       )
  ) OR EXISTS (
    SELECT 1
      FROM proof_harness_runtime.certification_gate_results AS gate
      CROSS JOIN LATERAL jsonb_array_elements_text(gate.evidence_ids_json) AS gate_evidence(evidence_id)
      LEFT JOIN proof_harness_runtime.certification_evidence_links AS link
        ON link.tenant_id = gate.tenant_id
       AND link.project_id = gate.project_id
       AND link.assessment_digest = gate.assessment_digest
       AND link.evidence_id = gate_evidence.evidence_id
     WHERE gate.tenant_id = NEW.tenant_id
       AND gate.project_id = NEW.project_id
       AND gate.assessment_digest = NEW.assessment_digest
       AND link.evidence_id IS NULL
  ) THEN
    RAISE EXCEPTION 'certification evidence set is missing, stale, revoked, or gate-unbound'
      USING ERRCODE = '23514';
  END IF;

  expected_payload := jsonb_build_object(
    'tenant_id', NEW.tenant_id,
    'project_id', NEW.project_id,
    'goal_id', NEW.goal_id,
    'run_id', NEW.run_id,
    'revision_set_id', NEW.revision_set_id,
    'revision_set_digest', NEW.revision_set_digest,
    'revision_set_revisions', NEW.revision_set_json,
    'proof_graph_digest', NEW.proof_graph_digest,
    'certified_envelope', NEW.certified_envelope_json,
    'gate_results', gate_payload,
    'status_counts', NEW.status_counts_json,
    'evidence_ids', evidence_payload,
    'evidence_root', NEW.evidence_root,
    'local_status', NEW.local_status,
    'independent_verifier_identity', NEW.reviewer_identity,
    'issued_at', proof_harness.canonical_utc_timestamp(NEW.issued_at),
    'unresolved_risks', NEW.unresolved_risks_json,
    'production_assessment', NEW.production_assessment
  );
  IF NEW.payload_json <> expected_payload THEN
    RAISE EXCEPTION 'certification payload does not exactly cover gates, evidence, revisions, graph and run'
      USING ERRCODE = '23514';
  END IF;

  IF NEW.certificate_json->>'certificate_id' IS DISTINCT FROM NEW.certificate_id
     OR NEW.certificate_json->>'tenant_id' IS DISTINCT FROM NEW.tenant_id
     OR NEW.certificate_json->>'project_id' IS DISTINCT FROM NEW.project_id
     OR NEW.certificate_json->>'goal_id' IS DISTINCT FROM NEW.goal_id
     OR NEW.certificate_json->>'run_id' IS DISTINCT FROM NEW.run_id
     OR NEW.certificate_json->>'revision_set_id' IS DISTINCT FROM NEW.revision_set_id
     OR NEW.certificate_json->>'revision_set_digest' IS DISTINCT FROM NEW.revision_set_digest
     OR NEW.certificate_json->'revision_set_revisions' IS DISTINCT FROM NEW.revision_set_json
     OR NEW.certificate_json->>'proof_graph_digest' IS DISTINCT FROM NEW.proof_graph_digest
     OR NEW.certificate_json->'certified_envelope' IS DISTINCT FROM NEW.certified_envelope_json
     OR NEW.certificate_json->'gate_results' IS DISTINCT FROM gate_payload
     OR NEW.certificate_json->'status_counts' IS DISTINCT FROM NEW.status_counts_json
     OR NEW.certificate_json->'evidence_ids' IS DISTINCT FROM evidence_payload
     OR NEW.certificate_json->>'evidence_root' IS DISTINCT FROM NEW.evidence_root
     OR NEW.certificate_json->>'payload_digest' IS DISTINCT FROM NEW.assessment_digest
     OR NEW.certificate_json->>'status' IS DISTINCT FROM NEW.local_status
     OR NEW.certificate_json->'production_assessment' IS DISTINCT FROM to_jsonb(NEW.production_assessment)
     OR NEW.certificate_json->'unresolved_risks' IS DISTINCT FROM NEW.unresolved_risks_json
     OR NEW.certificate_json->>'issued_at' IS DISTINCT FROM proof_harness.canonical_utc_timestamp(NEW.issued_at)
     OR NEW.certificate_json->>'signer_identity' IS DISTINCT FROM NEW.reviewer_identity
     OR NEW.certificate_json->'signer_independent' IS DISTINCT FROM to_jsonb(NEW.reviewer_independent)
     OR NEW.certificate_json->'signature_receipt_id' IS DISTINCT FROM 'null'::jsonb
     OR NEW.certificate_json->'signature_receipt_sha256' IS DISTINCT FROM 'null'::jsonb
  THEN
    RAISE EXCEPTION 'typed local certificate does not match its durable assessment'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION proof_harness.assert_runtime_external_decision()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime, proof_harness
AS $$
DECLARE
  assessment record;
  receipt record;
  signed_payload jsonb;
  receipt_payload jsonb;
  gate_payload jsonb;
  evidence_payload jsonb;
BEGIN
  SELECT * INTO assessment
    FROM proof_harness_runtime.certification_assessments
   WHERE tenant_id = NEW.tenant_id
     AND project_id = NEW.project_id
     AND assessment_digest = NEW.assessment_digest;
  SELECT * INTO receipt
    FROM proof_harness_runtime.certification_external_receipts
   WHERE tenant_id = NEW.tenant_id
     AND project_id = NEW.project_id
     AND receipt_id = NEW.receipt_id;
  IF assessment IS NULL OR receipt IS NULL
     OR assessment.local_status <> 'READY_FOR_EXTERNAL_GATE'
     OR assessment.unresolved_risks_json <> '[]'::jsonb
     OR NOT assessment.reviewer_independent
     OR receipt.assessment_digest <> assessment.assessment_digest
     OR receipt.payload_digest <> assessment.assessment_digest
     OR receipt.certificate_id <> assessment.certificate_id
     OR receipt.attested_status <> NEW.status
     OR NOT receipt.independent
     OR NOT receipt.cryptographically_verified
     OR receipt.signer_identity IN (assessment.reviewer_identity, assessment.actor_id)
     OR receipt.issued_at > receipt.verified_at
     OR receipt.verified_at > NEW.decided_at
     OR receipt.expires_at <= NEW.decided_at
     OR (NEW.status = 'CERTIFIED' AND (NOT assessment.production_assessment OR NOT receipt.certification_authority))
     OR EXISTS (
       SELECT 1 FROM proof_harness_runtime.certification_signature_revocations AS revocation
        WHERE revocation.tenant_id = receipt.tenant_id
          AND revocation.project_id = receipt.project_id
          AND revocation.receipt_id = receipt.receipt_id
     )
  THEN
    RAISE EXCEPTION 'external completion decision lacks a live independent bound verifier receipt'
      USING ERRCODE = '23514';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM proof_harness_runtime.evidence AS evidence
     WHERE evidence.tenant_id = receipt.tenant_id
       AND evidence.project_id = receipt.project_id
       AND evidence.evidence_id = receipt.verification_evidence_id
       AND evidence.subject_revision = assessment.assessment_digest
       AND evidence.evidence_class = 'external-signature'
       AND evidence.content_bytes = receipt.receipt_json_bytes
       AND evidence.content_sha256 = 'sha256:' || encode(sha256(
         convert_to('elmos.proof-harness.v1','UTF8') || decode('00','hex') ||
         convert_to('evidence-content','UTF8') || decode('00','hex') || evidence.content_bytes
       ), 'hex')
       AND evidence.record_json->'producer'->>'source' = 'CERTIFIER'
       AND evidence.record_json->'producer'->>'tool_name' = receipt.provider_id
       AND (evidence.record_json->'producer'->>'independent')::boolean
       AND NOT EXISTS (
         SELECT 1 FROM proof_harness_runtime.evidence_revocations AS revocation
          WHERE revocation.tenant_id = evidence.tenant_id
            AND revocation.project_id = evidence.project_id
            AND revocation.evidence_id = evidence.evidence_id
       )
  ) THEN
    RAISE EXCEPTION 'external receipt is not backed by live byte-bound certifier evidence'
      USING ERRCODE = '23514';
  END IF;

  signed_payload := convert_from(receipt.signed_payload_bytes, 'UTF8')::jsonb;
  receipt_payload := convert_from(receipt.receipt_json_bytes, 'UTF8')::jsonb;
  IF signed_payload <> jsonb_build_object(
       'receipt_id', receipt.receipt_id,
       'tenant_id', receipt.tenant_id,
       'project_id', receipt.project_id,
       'payload_sha256', receipt.payload_digest,
       'certificate_id', receipt.certificate_id,
       'signer_identity', receipt.signer_identity,
       'key_id', receipt.key_id,
       'provider_id', receipt.provider_id,
       'algorithm', receipt.algorithm,
       'verification_evidence_id', receipt.verification_evidence_id,
       'issued_at', proof_harness.canonical_utc_timestamp(receipt.issued_at),
       'expires_at', proof_harness.canonical_utc_timestamp(receipt.expires_at),
       'independent', receipt.independent,
       'certification_authority', receipt.certification_authority,
       'attested_status', receipt.attested_status
     )
     OR receipt_payload->>'receipt_id' IS DISTINCT FROM receipt.receipt_id
     OR receipt_payload->>'payload_sha256' IS DISTINCT FROM receipt.payload_digest
     OR receipt_payload->>'verification_evidence_id' IS DISTINCT FROM receipt.verification_evidence_id
     OR receipt_payload->>'attested_status' IS DISTINCT FROM receipt.attested_status
     OR receipt_payload->>'signature_base64' IS DISTINCT FROM replace(encode(receipt.signature_bytes, 'base64'), E'\n', '')
  THEN
    RAISE EXCEPTION 'external signature bytes do not cover the exact receipt claims'
      USING ERRCODE = '23514';
  END IF;

  SELECT jsonb_agg(jsonb_build_object(
           'gate', gate_name, 'decision', decision,
           'evidence_ids', evidence_ids_json, 'reasons', reasons_json
         ) ORDER BY ordinal)
    INTO gate_payload
    FROM proof_harness_runtime.certification_gate_results
   WHERE tenant_id = NEW.tenant_id AND project_id = NEW.project_id
     AND assessment_digest = NEW.assessment_digest;
  SELECT jsonb_agg(to_jsonb(evidence_id) ORDER BY ordinal)
    INTO evidence_payload
    FROM proof_harness_runtime.certification_evidence_links
   WHERE tenant_id = NEW.tenant_id AND project_id = NEW.project_id
     AND assessment_digest = NEW.assessment_digest;

  IF NEW.external_certificate_json->>'certificate_id' IS DISTINCT FROM assessment.certificate_id
     OR NEW.external_certificate_json->>'tenant_id' IS DISTINCT FROM NEW.tenant_id
     OR NEW.external_certificate_json->>'project_id' IS DISTINCT FROM NEW.project_id
     OR NEW.external_certificate_json->>'run_id' IS DISTINCT FROM assessment.run_id
     OR NEW.external_certificate_json->>'revision_set_id' IS DISTINCT FROM assessment.revision_set_id
     OR NEW.external_certificate_json->>'revision_set_digest' IS DISTINCT FROM assessment.revision_set_digest
     OR NEW.external_certificate_json->'revision_set_revisions' IS DISTINCT FROM assessment.revision_set_json
     OR NEW.external_certificate_json->>'proof_graph_digest' IS DISTINCT FROM assessment.proof_graph_digest
     OR NEW.external_certificate_json->'certified_envelope' IS DISTINCT FROM assessment.certified_envelope_json
     OR NEW.external_certificate_json->'gate_results' IS DISTINCT FROM gate_payload
     OR NEW.external_certificate_json->'status_counts' IS DISTINCT FROM assessment.status_counts_json
     OR NEW.external_certificate_json->'evidence_ids' IS DISTINCT FROM evidence_payload
     OR NEW.external_certificate_json->>'evidence_root' IS DISTINCT FROM assessment.evidence_root
     OR NEW.external_certificate_json->>'payload_digest' IS DISTINCT FROM assessment.assessment_digest
     OR NEW.external_certificate_json->>'status' IS DISTINCT FROM NEW.status
     OR NEW.external_certificate_json->>'signer_identity' IS DISTINCT FROM receipt.signer_identity
     OR NEW.external_certificate_json->>'signer_key_id' IS DISTINCT FROM receipt.key_id
     OR NEW.external_certificate_json->>'signature_receipt_id' IS DISTINCT FROM receipt.receipt_id
     OR NEW.external_certificate_json->>'signature_receipt_sha256' IS DISTINCT FROM receipt.receipt_sha256
     OR NEW.external_certificate_json->'signer_independent' IS DISTINCT FROM 'true'::jsonb
     OR NEW.external_certificate_json->'unresolved_risks' IS DISTINCT FROM '[]'::jsonb
     OR NEW.external_certificate_json->'production_assessment' IS DISTINCT FROM to_jsonb(assessment.production_assessment)
     OR NEW.external_certificate_json->>'issued_at' IS DISTINCT FROM proof_harness.canonical_utc_timestamp(NEW.decided_at)
  THEN
    RAISE EXCEPTION 'external certificate does not exactly bind the approved assessment and receipt'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE CONSTRAINT TRIGGER runtime_certification_assessment_complete
AFTER INSERT ON proof_harness_runtime.certification_assessments
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION proof_harness.assert_runtime_certification_assessment();

CREATE CONSTRAINT TRIGGER runtime_certification_external_decision_complete
AFTER INSERT ON proof_harness_runtime.certification_external_decisions
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION proof_harness.assert_runtime_external_decision();

CREATE VIEW proof_harness_runtime.effective_certification_decisions
WITH (security_barrier = true, security_invoker = true)
AS
SELECT
  decision.*,
  CASE
    WHEN EXISTS (
      SELECT 1 FROM proof_harness_runtime.certification_signature_revocations AS revocation
       WHERE revocation.tenant_id = decision.tenant_id
         AND revocation.project_id = decision.project_id
         AND revocation.receipt_id = decision.receipt_id
    ) THEN 'REVOKED'
    WHEN NOT EXISTS (
      SELECT 1 FROM proof_harness_runtime.certification_external_receipts AS receipt
       WHERE receipt.tenant_id = decision.tenant_id
         AND receipt.project_id = decision.project_id
         AND receipt.receipt_id = decision.receipt_id
         AND receipt.assessment_digest = decision.assessment_digest
         AND receipt.attested_status = decision.status
         AND receipt.cryptographically_verified
         AND receipt.independent
         AND receipt.verified_at <= clock_timestamp()
         AND receipt.expires_at > clock_timestamp()
    ) THEN 'EXPIRED'
    ELSE decision.status
  END AS effective_status
FROM proof_harness_runtime.certification_external_decisions AS decision;

CREATE TRIGGER run_events_fence
BEFORE INSERT ON proof_harness.run_events
FOR EACH ROW EXECUTE FUNCTION proof_harness.assert_event_fence();

CREATE TRIGGER runtime_control_receipt_guard
BEFORE UPDATE OR DELETE ON proof_harness_runtime.control_plane_receipts
FOR EACH ROW EXECUTE FUNCTION proof_harness.guard_runtime_control_receipt();
CREATE TRIGGER runtime_control_receipt_enqueue
AFTER INSERT ON proof_harness_runtime.control_plane_receipts
FOR EACH ROW EXECUTE FUNCTION proof_harness.enqueue_runtime_scheduler_job();
CREATE TRIGGER runtime_control_receipt_complete_job
AFTER UPDATE OF response_json ON proof_harness_runtime.control_plane_receipts
FOR EACH ROW EXECUTE FUNCTION proof_harness.complete_runtime_scheduler_job();

CREATE TRIGGER evidence_objects_immutable
BEFORE UPDATE OR DELETE ON proof_harness.evidence_objects
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER environment_authority_revocations_immutable
BEFORE UPDATE OR DELETE ON proof_harness.environment_authority_revocations
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER run_events_immutable
BEFORE UPDATE OR DELETE ON proof_harness.run_events
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER evidence_revocations_immutable
BEFORE UPDATE OR DELETE ON proof_harness.evidence_revocations
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER proof_results_immutable
BEFORE UPDATE OR DELETE ON proof_harness.proof_results
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER proof_result_evidence_immutable
BEFORE UPDATE OR DELETE ON proof_harness.proof_result_evidence
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER gate_results_immutable
BEFORE UPDATE OR DELETE ON proof_harness.gate_results
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER completion_reviews_immutable
BEFORE UPDATE OR DELETE ON proof_harness.completion_reviews
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER external_signature_receipts_immutable
BEFORE UPDATE OR DELETE ON proof_harness.external_signature_receipts
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER external_signature_revocations_immutable
BEFORE UPDATE OR DELETE ON proof_harness.external_signature_revocations
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER audit_log_immutable
BEFORE UPDATE OR DELETE ON proof_harness.audit_log
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER idempotency_receipts_immutable
BEFORE UPDATE OR DELETE ON proof_harness.idempotency_receipts
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER usage_ledger_immutable
BEFORE UPDATE OR DELETE ON proof_harness.usage_ledger
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();

CREATE TRIGGER runtime_evidence_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.evidence
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_evidence_integrity
BEFORE INSERT ON proof_harness_runtime.evidence
FOR EACH ROW EXECUTE FUNCTION proof_harness.assert_runtime_evidence_integrity();
CREATE TRIGGER runtime_evidence_revocations_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.evidence_revocations
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_audit_events_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.audit_events
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_outbox_events_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.outbox_events
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_outbox_deliveries_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.outbox_deliveries
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_checkpoints_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.run_checkpoints
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_effect_events_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.effect_events
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_metric_points_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.metric_points
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_idempotency_receipts_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.idempotency_receipts
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_certification_assessments_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.certification_assessments
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_certification_gate_results_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.certification_gate_results
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_certification_evidence_links_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.certification_evidence_links
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_certification_external_receipts_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.certification_external_receipts
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_certification_external_decisions_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.certification_external_decisions
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_certification_signature_revocations_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.certification_signature_revocations
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_certification_events_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.certification_events
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER runtime_scheduler_claim_events_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.scheduler_claim_events
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();

DO $$
DECLARE
  relation_name text;
BEGIN
  FOREACH relation_name IN ARRAY ARRAY[
    'tenant_projects', 'goal_contracts', 'revision_sets',
    'environment_authorities', 'environment_authority_revocations',
    'runs', 'run_leases', 'run_events',
    'proof_obligations', 'proof_obligation_edges', 'evidence_objects',
    'evidence_revocations', 'proof_results', 'proof_result_evidence',
    'gate_results', 'completion_reviews', 'external_signature_receipts',
    'external_signature_revocations',
    'idempotency_receipts', 'audit_log', 'outbox', 'usage_ledger'
  ] LOOP
    EXECUTE format('ALTER TABLE proof_harness.%I ENABLE ROW LEVEL SECURITY', relation_name);
    EXECUTE format('ALTER TABLE proof_harness.%I FORCE ROW LEVEL SECURITY', relation_name);
    EXECUTE format(
      'CREATE POLICY tenant_project_isolation ON proof_harness.%I USING (tenant_id = proof_harness.current_tenant_id() AND project_id = proof_harness.current_project_id()) WITH CHECK (tenant_id = proof_harness.current_tenant_id() AND project_id = proof_harness.current_project_id())',
      relation_name
    );
  END LOOP;
END
$$;

ALTER TABLE proof_harness_runtime.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE proof_harness_runtime.tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY runtime_tenant_isolation
  ON proof_harness_runtime.tenants
  USING (tenant_id = proof_harness.current_tenant_key())
  WITH CHECK (tenant_id = proof_harness.current_tenant_key());

DO $$
DECLARE
  relation_name text;
BEGIN
  FOREACH relation_name IN ARRAY ARRAY[
    'projects', 'actors', 'runs', 'idempotency_receipts',
    'control_plane_receipts', 'evidence', 'evidence_revocations',
    'audit_events', 'outbox_events', 'outbox_deliveries',
    'run_checkpoints', 'external_effects', 'effect_events', 'metric_points',
    'certification_assessments', 'certification_gate_results',
    'certification_evidence_links', 'certification_external_receipts',
    'certification_external_decisions', 'certification_signature_revocations',
    'certification_events'
  ] LOOP
    EXECUTE format('ALTER TABLE proof_harness_runtime.%I ENABLE ROW LEVEL SECURITY', relation_name);
    EXECUTE format('ALTER TABLE proof_harness_runtime.%I FORCE ROW LEVEL SECURITY', relation_name);
    EXECUTE format(
      'CREATE POLICY runtime_tenant_project_isolation ON proof_harness_runtime.%I USING (tenant_id = proof_harness.current_tenant_key() AND project_id = proof_harness.current_project_key()) WITH CHECK (tenant_id = proof_harness.current_tenant_key() AND project_id = proof_harness.current_project_key())',
      relation_name
    );
  END LOOP;
END
$$;

CREATE INDEX run_state_idx
  ON proof_harness.runs (tenant_id, project_id, state, updated_at);
CREATE INDEX obligation_ready_idx
  ON proof_harness.proof_obligations (tenant_id, project_id, run_id, state, severity);
CREATE INDEX evidence_subject_idx
  ON proof_harness.evidence_objects (tenant_id, project_id, subject_revision, kind);
CREATE INDEX outbox_delivery_idx
  ON proof_harness.outbox (tenant_id, project_id, state, available_at);
CREATE INDEX audit_resource_idx
  ON proof_harness.audit_log (tenant_id, project_id, resource_type, resource_id, sequence_no);

CREATE INDEX runtime_run_state_idx
  ON proof_harness_runtime.runs (tenant_id, project_id, state, updated_at);
CREATE INDEX runtime_evidence_subject_idx
  ON proof_harness_runtime.evidence (tenant_id, project_id, subject_revision, created_at);
CREATE INDEX runtime_outbox_topic_idx
  ON proof_harness_runtime.outbox_events (tenant_id, project_id, topic, created_at);
CREATE INDEX runtime_effect_state_idx
  ON proof_harness_runtime.external_effects (tenant_id, project_id, state);
CREATE INDEX runtime_metric_name_idx
  ON proof_harness_runtime.metric_points (tenant_id, project_id, name, occurred_at);
CREATE INDEX runtime_certification_run_idx
  ON proof_harness_runtime.certification_assessments (tenant_id, project_id, run_id, issued_at);
CREATE INDEX runtime_certification_receipt_expiry_idx
  ON proof_harness_runtime.certification_external_receipts (tenant_id, project_id, expires_at);
CREATE INDEX runtime_scheduler_claim_idx
  ON proof_harness_runtime.scheduler_jobs (state, lease_expires_at, created_at);

REVOKE ALL ON ALL TABLES IN SCHEMA proof_harness FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA proof_harness FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA proof_harness FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA proof_harness_runtime FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA proof_harness_runtime FROM PUBLIC;
