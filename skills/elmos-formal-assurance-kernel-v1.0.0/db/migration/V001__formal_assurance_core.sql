-- Elmos Formal Assurance Kernel V1: core state
CREATE SCHEMA IF NOT EXISTS formal_assurance;

DO $$ BEGIN
  CREATE TYPE formal_assurance.proof_status AS ENUM (
    'PROVED_CERTIFIED','PROVED_INDUCTIVE','PROVED_SOLVER_TRUSTED',
    'PROVED_FOR_SUPPORTED_FRAGMENT','BOUNDED_NO_COUNTEREXAMPLE',
    'REFUTED_WITH_COUNTEREXAMPLE','UNKNOWN_TIMEOUT','UNKNOWN_RESOURCE_LIMIT',
    'UNSUPPORTED','ASSUMPTION_REQUIRED','RUNTIME_MONITORED','WAIVED_BY_APPROVER'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE formal_assurance.proof_run_state AS ENUM (
    'QUEUED','LEASED','RUNNING','PAUSED','CANCEL_REQUESTED',
    'SUCCEEDED','FAILED','CANCELLED','TIMED_OUT'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS formal_assurance.formal_spec (
  id text PRIMARY KEY,
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  project_id text,
  business_line text NOT NULL CHECK (business_line IN (
    'core','spring-modernization','cross-language','project-generation','sql-conversion','platform'
  )),
  spec_kind text NOT NULL,
  version text NOT NULL,
  source_uri text,
  source_hash char(64) NOT NULL CHECK (source_hash ~ '^[a-f0-9]{64}$'),
  semantic_profile_id text NOT NULL,
  semantic_model_hash char(64) NOT NULL CHECK (semantic_model_hash ~ '^[a-f0-9]{64}$'),
  body jsonb NOT NULL,
  source_map jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL CHECK (status IN ('DRAFT','FROZEN','SUPERSEDED','REJECTED')),
  provenance jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, id, version)
);

CREATE TABLE IF NOT EXISTS formal_assurance.proof_assumption (
  id text PRIMARY KEY,
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  statement text NOT NULL,
  formal_expression text,
  risk_level text NOT NULL CHECK (risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  owner_id text NOT NULL,
  status text NOT NULL CHECK (status IN ('PROPOSED','ACTIVE','VIOLATED','EXPIRED','REVOKED')),
  assumption_hash char(64) NOT NULL CHECK (assumption_hash ~ '^[a-f0-9]{64}$'),
  monitor_id text,
  evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
  valid_from timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, assumption_hash)
);

CREATE TABLE IF NOT EXISTS formal_assurance.proof_obligation (
  id text PRIMARY KEY,
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  project_id text,
  formal_spec_id text NOT NULL REFERENCES formal_assurance.formal_spec(id) ON DELETE RESTRICT,
  subject_uri text,
  property_kind text NOT NULL,
  criticality text NOT NULL CHECK (criticality IN ('P0','P1','P2','P3')),
  formula text NOT NULL,
  formula_hash char(64) NOT NULL CHECK (formula_hash ~ '^[a-f0-9]{64}$'),
  required_assurance text NOT NULL CHECK (required_assurance IN (
    'NONE','A0_TESTED','A1_BOUNDED','A2_SOLVER_PROVED','A3_CERTIFIED','A4_COMPOSED','TRUSTED'
  )),
  allow_bounded boolean NOT NULL DEFAULT false,
  assumption_ids text[] NOT NULL DEFAULT '{}',
  dependency_ids text[] NOT NULL DEFAULT '{}',
  source_map jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL CHECK (status IN ('PLANNED','READY','RUNNING','BLOCKED','TERMINAL')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, formula_hash, formal_spec_id)
);

CREATE TABLE IF NOT EXISTS formal_assurance.proof_plan (
  id text PRIMARY KEY,
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  project_id text,
  business_line text NOT NULL,
  model_version text NOT NULL,
  policy_revision text NOT NULL,
  budget jsonb NOT NULL,
  estimated_wall_clock_seconds bigint CHECK (estimated_wall_clock_seconds >= 0),
  plan_hash char(64) NOT NULL CHECK (plan_hash ~ '^[a-f0-9]{64}$'),
  state text NOT NULL CHECK (state IN ('DRAFT','READY','RUNNING','PAUSED','SUCCEEDED','FAILED','CANCELLED')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, plan_hash)
);

CREATE TABLE IF NOT EXISTS formal_assurance.proof_plan_obligation (
  plan_id text NOT NULL REFERENCES formal_assurance.proof_plan(id) ON DELETE CASCADE,
  obligation_id text NOT NULL REFERENCES formal_assurance.proof_obligation(id) ON DELETE RESTRICT,
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  required boolean NOT NULL DEFAULT true,
  PRIMARY KEY (plan_id, obligation_id)
);

CREATE TABLE IF NOT EXISTS formal_assurance.proof_plan_edge (
  plan_id text NOT NULL REFERENCES formal_assurance.proof_plan(id) ON DELETE CASCADE,
  from_obligation_id text NOT NULL REFERENCES formal_assurance.proof_obligation(id) ON DELETE RESTRICT,
  to_obligation_id text NOT NULL REFERENCES formal_assurance.proof_obligation(id) ON DELETE RESTRICT,
  PRIMARY KEY (plan_id, from_obligation_id, to_obligation_id),
  CHECK (from_obligation_id <> to_obligation_id)
);

CREATE TABLE IF NOT EXISTS formal_assurance.proof_run (
  id text PRIMARY KEY,
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  project_id text,
  obligation_id text NOT NULL REFERENCES formal_assurance.proof_obligation(id) ON DELETE RESTRICT,
  engine text NOT NULL,
  engine_version text NOT NULL,
  engine_digest char(64) CHECK (engine_digest IS NULL OR engine_digest ~ '^[a-f0-9]{64}$'),
  mode text NOT NULL CHECK (mode IN ('CERTIFIED','INDUCTIVE','SMT','BOUNDED','RUNTIME')),
  bound jsonb,
  options jsonb NOT NULL DEFAULT '{}'::jsonb,
  state formal_assurance.proof_run_state NOT NULL DEFAULT 'QUEUED',
  result_status formal_assurance.proof_status,
  assurance_level text,
  assumption_hash char(64) CHECK (assumption_hash IS NULL OR assumption_hash ~ '^[a-f0-9]{64}$'),
  tcb_hash char(64) CHECK (tcb_hash IS NULL OR tcb_hash ~ '^[a-f0-9]{64}$'),
  formula_hash char(64) NOT NULL CHECK (formula_hash ~ '^[a-f0-9]{64}$'),
  owner_id text,
  fencing_token bigint NOT NULL DEFAULT 1 CHECK (fencing_token > 0),
  lease_expires_at timestamptz,
  trace_id text,
  checkpoint_uri text,
  wall_clock_ms bigint CHECK (wall_clock_ms IS NULL OR wall_clock_ms >= 0),
  started_at timestamptz,
  completed_at timestamptz,
  stale boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS ix_formal_spec_tenant_project
  ON formal_assurance.formal_spec (tenant_id, project_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_obligation_ready
  ON formal_assurance.proof_obligation (tenant_id, criticality, status, updated_at);
CREATE INDEX IF NOT EXISTS ix_proof_run_queue
  ON formal_assurance.proof_run (tenant_id, state, created_at)
  WHERE state IN ('QUEUED','LEASED','RUNNING','PAUSED');
CREATE UNIQUE INDEX IF NOT EXISTS ux_proof_run_active_owner
  ON formal_assurance.proof_run (obligation_id)
  WHERE state IN ('LEASED','RUNNING');
