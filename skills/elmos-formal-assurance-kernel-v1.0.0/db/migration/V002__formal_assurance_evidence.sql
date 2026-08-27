-- Elmos Formal Assurance Kernel V2: evidence, governance and audit
CREATE TABLE IF NOT EXISTS formal_assurance.proof_artifact (
  id text PRIMARY KEY,
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  run_id text NOT NULL REFERENCES formal_assurance.proof_run(id) ON DELETE RESTRICT,
  artifact_type text NOT NULL,
  storage_uri text NOT NULL,
  sha256 char(64) NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
  media_type text NOT NULL,
  size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
  encryption_key_ref text,
  independently_checkable boolean NOT NULL DEFAULT false,
  immutable boolean NOT NULL DEFAULT true CHECK (immutable),
  redacted boolean NOT NULL DEFAULT false,
  retention_class text NOT NULL CHECK (retention_class IN ('EPHEMERAL','STANDARD','AUDIT','LEGAL_HOLD')),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, sha256, artifact_type)
);

CREATE TABLE IF NOT EXISTS formal_assurance.proof_counterexample (
  id text PRIMARY KEY,
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  run_id text NOT NULL REFERENCES formal_assurance.proof_run(id) ON DELETE RESTRICT,
  obligation_id text NOT NULL REFERENCES formal_assurance.proof_obligation(id) ON DELETE RESTRICT,
  kind text NOT NULL CHECK (kind IN ('INPUT','STATE','SCHEDULE','DATABASE','TRACE','MODEL_INSTANCE')),
  violated_property text,
  witness jsonb NOT NULL,
  minimized boolean NOT NULL DEFAULT false,
  replay_command text NOT NULL,
  replay_environment jsonb NOT NULL DEFAULT '{}'::jsonb,
  generated_test_uris text[] NOT NULL DEFAULT '{}',
  contains_sensitive_data boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS formal_assurance.trusted_component (
  id text PRIMARY KEY,
  component_name text NOT NULL,
  component_type text NOT NULL,
  version text NOT NULL,
  digest char(64) NOT NULL CHECK (digest ~ '^[a-f0-9]{64}$'),
  signature_uri text,
  sbom_uri text,
  trust_reason text NOT NULL,
  status text NOT NULL CHECK (status IN ('PROPOSED','PINNED','REVOKED','VULNERABLE','UNKNOWN')),
  first_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (component_name, version, digest)
);

CREATE TABLE IF NOT EXISTS formal_assurance.proof_run_tcb (
  run_id text NOT NULL REFERENCES formal_assurance.proof_run(id) ON DELETE CASCADE,
  trusted_component_id text NOT NULL REFERENCES formal_assurance.trusted_component(id) ON DELETE RESTRICT,
  PRIMARY KEY (run_id, trusted_component_id)
);

CREATE TABLE IF NOT EXISTS formal_assurance.proof_waiver (
  id text PRIMARY KEY,
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  obligation_id text NOT NULL REFERENCES formal_assurance.proof_obligation(id) ON DELETE RESTRICT,
  reason text NOT NULL CHECK (length(reason) >= 20),
  risk text NOT NULL CHECK (risk IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  owner_id text NOT NULL,
  compensating_controls jsonb NOT NULL,
  approvals jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('PROPOSED','APPROVED','REJECTED','EXPIRED','REVOKED')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  CHECK (expires_at > created_at)
);

CREATE TABLE IF NOT EXISTS formal_assurance.proof_coverage_snapshot (
  id bigserial PRIMARY KEY,
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  subject_id text NOT NULL,
  critical_total integer NOT NULL CHECK (critical_total >= 0),
  by_status jsonb NOT NULL,
  by_assurance jsonb NOT NULL,
  weighted_coverage numeric(6,5) CHECK (weighted_coverage BETWEEN 0 AND 1),
  uncovered_entrypoints jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_hash char(64) NOT NULL CHECK (evidence_hash ~ '^[a-f0-9]{64}$'),
  generated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS formal_assurance.release_gate_decision (
  id text PRIMARY KEY,
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  subject_id text NOT NULL,
  gate text NOT NULL,
  decision text NOT NULL CHECK (decision IN ('ALLOW','DENY','ADVISORY')),
  policy_revision text NOT NULL,
  blocking_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_hash char(64) NOT NULL CHECK (evidence_hash ~ '^[a-f0-9]{64}$'),
  evaluator_identity text NOT NULL,
  evaluated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz
);

CREATE TABLE IF NOT EXISTS formal_assurance.proof_event (
  id bigserial PRIMARY KEY,
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  aggregate_type text NOT NULL,
  aggregate_id text NOT NULL,
  event_type text NOT NULL,
  event_id text NOT NULL,
  payload jsonb NOT NULL,
  trace_id text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, event_id)
);

CREATE INDEX IF NOT EXISTS ix_artifact_run ON formal_assurance.proof_artifact (run_id, created_at);
CREATE INDEX IF NOT EXISTS ix_counterexample_obligation ON formal_assurance.proof_counterexample (obligation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_waiver_expiry ON formal_assurance.proof_waiver (tenant_id, status, expires_at);
CREATE INDEX IF NOT EXISTS ix_gate_subject ON formal_assurance.release_gate_decision (tenant_id, subject_id, evaluated_at DESC);
CREATE INDEX IF NOT EXISTS ix_event_aggregate ON formal_assurance.proof_event (tenant_id, aggregate_type, aggregate_id, id);
