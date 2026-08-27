-- Elmos Formal Assurance Kernel V3: cache, dependencies, monitors and tenant isolation
CREATE TABLE IF NOT EXISTS formal_assurance.proof_cache (
  cache_key char(64) PRIMARY KEY CHECK (cache_key ~ '^[a-f0-9]{64}$'),
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  obligation_id text NOT NULL REFERENCES formal_assurance.proof_obligation(id) ON DELETE CASCADE,
  result_run_id text NOT NULL REFERENCES formal_assurance.proof_run(id) ON DELETE RESTRICT,
  formula_hash char(64) NOT NULL,
  semantic_profile_hash char(64) NOT NULL,
  semantic_model_hash char(64) NOT NULL,
  assumption_hash char(64) NOT NULL,
  tcb_hash char(64) NOT NULL,
  engine_options_hash char(64) NOT NULL,
  bound_hash char(64) NOT NULL,
  source_hash char(64) NOT NULL,
  target_hash char(64) NOT NULL,
  status formal_assurance.proof_status NOT NULL,
  stale boolean NOT NULL DEFAULT false,
  reusable_across_tenants boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS formal_assurance.proof_dependency (
  proof_run_id text NOT NULL REFERENCES formal_assurance.proof_run(id) ON DELETE CASCADE,
  dependency_kind text NOT NULL CHECK (dependency_kind IN (
    'SOURCE','TARGET','FORMULA','SEMANTIC_PROFILE','SEMANTIC_MODEL','ASSUMPTION','TCB','POLICY','EXTERNAL_CONTRACT'
  )),
  dependency_id text NOT NULL,
  dependency_hash char(64) NOT NULL CHECK (dependency_hash ~ '^[a-f0-9]{64}$'),
  PRIMARY KEY (proof_run_id, dependency_kind, dependency_id)
);

CREATE TABLE IF NOT EXISTS formal_assurance.trace_mapping (
  id bigserial PRIMARY KEY,
  tenant_id text NOT NULL,
  subject_id text NOT NULL,
  source_location text NOT NULL,
  formal_node_id text NOT NULL,
  target_location text,
  mapping_kind text NOT NULL,
  mapping_hash char(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, subject_id, source_location, formal_node_id, target_location)
);

CREATE TABLE IF NOT EXISTS formal_assurance.runtime_monitor (
  id text PRIMARY KEY,
  tenant_id text NOT NULL,
  account_id text NOT NULL,
  assumption_id text REFERENCES formal_assurance.proof_assumption(id) ON DELETE RESTRICT,
  obligation_id text REFERENCES formal_assurance.proof_obligation(id) ON DELETE RESTRICT,
  monitor_kind text NOT NULL,
  config jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('ACTIVE','PAUSED','VIOLATED','RETIRED')),
  last_observed_at timestamptz,
  last_violation_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK (assumption_id IS NOT NULL OR obligation_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_cache_lookup
  ON formal_assurance.proof_cache (tenant_id, formula_hash, semantic_model_hash, assumption_hash, tcb_hash, stale, expires_at);
CREATE INDEX IF NOT EXISTS ix_dependency_hash
  ON formal_assurance.proof_dependency (dependency_kind, dependency_id, dependency_hash);
CREATE INDEX IF NOT EXISTS ix_monitor_active
  ON formal_assurance.runtime_monitor (tenant_id, status, last_observed_at);

ALTER TABLE formal_assurance.formal_spec ENABLE ROW LEVEL SECURITY;
ALTER TABLE formal_assurance.proof_assumption ENABLE ROW LEVEL SECURITY;
ALTER TABLE formal_assurance.proof_obligation ENABLE ROW LEVEL SECURITY;
ALTER TABLE formal_assurance.proof_plan ENABLE ROW LEVEL SECURITY;
ALTER TABLE formal_assurance.proof_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE formal_assurance.proof_artifact ENABLE ROW LEVEL SECURITY;
ALTER TABLE formal_assurance.proof_counterexample ENABLE ROW LEVEL SECURITY;
ALTER TABLE formal_assurance.proof_waiver ENABLE ROW LEVEL SECURITY;
ALTER TABLE formal_assurance.proof_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE formal_assurance.runtime_monitor ENABLE ROW LEVEL SECURITY;

DO $$ DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'formal_spec','proof_assumption','proof_obligation','proof_plan','proof_run',
    'proof_artifact','proof_counterexample','proof_waiver','proof_cache','runtime_monitor'
  ]
  LOOP
    EXECUTE format(
      'DROP POLICY IF EXISTS tenant_isolation ON formal_assurance.%I; ' ||
      'CREATE POLICY tenant_isolation ON formal_assurance.%I USING ' ||
      '(tenant_id = current_setting(''elmos.tenant_id'', true)) WITH CHECK ' ||
      '(tenant_id = current_setting(''elmos.tenant_id'', true))',
      t, t
    );
  END LOOP;
END $$;
