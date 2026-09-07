BEGIN;
CREATE TABLE IF NOT EXISTS ai_factory_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  goal_id uuid NOT NULL,
  revision_set_id uuid NOT NULL REFERENCES ai_solution_revision(id),
  execution_epoch bigint NOT NULL DEFAULT 1,
  status text NOT NULL CHECK (status IN ('QUEUED','RUNNING','PAUSED','CANCELLING','CANCELLED','BLOCKED','FAILED','COMPLETED')),
  machine_eta_seconds bigint,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_factory_step (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL REFERENCES ai_factory_run(id) ON DELETE CASCADE,
  step_key text NOT NULL,
  attempt integer NOT NULL DEFAULT 1,
  lease_generation bigint NOT NULL DEFAULT 0,
  fencing_token uuid NOT NULL DEFAULT gen_random_uuid(),
  idempotency_key text NOT NULL,
  status text NOT NULL,
  checkpoint_uri text,
  started_at timestamptz,
  completed_at timestamptz,
  UNIQUE (run_id, step_key, attempt),
  UNIQUE (run_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS side_effect_ledger (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL REFERENCES ai_factory_run(id) ON DELETE CASCADE,
  step_id uuid NOT NULL REFERENCES ai_factory_step(id) ON DELETE CASCADE,
  idempotency_key text NOT NULL,
  effect_type text NOT NULL,
  target_ref text NOT NULL,
  state text NOT NULL CHECK (state IN ('PROPOSED','APPROVED','EXECUTING','APPLIED','RECONCILED','COMPENSATED','UNKNOWN','BLOCKED')),
  request_hash text NOT NULL,
  result_hash text,
  reconciliation_evidence uuid REFERENCES evidence_artifact(id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS usage_ledger (
  id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL REFERENCES ai_factory_run(id) ON DELETE CASCADE,
  step_id uuid REFERENCES ai_factory_step(id) ON DELETE CASCADE,
  provider text,
  model text,
  input_tokens bigint NOT NULL DEFAULT 0,
  output_tokens bigint NOT NULL DEFAULT 0,
  cached_tokens bigint NOT NULL DEFAULT 0,
  compute_seconds numeric(18,6) NOT NULL DEFAULT 0,
  storage_bytes bigint NOT NULL DEFAULT 0,
  network_bytes bigint NOT NULL DEFAULT 0,
  amount_usd numeric(18,8) NOT NULL DEFAULT 0,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE ai_solution ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_solution_revision ENABLE ROW LEVEL SECURITY;
ALTER TABLE target_portfolio ENABLE ROW LEVEL SECURITY;
ALTER TABLE generated_project ENABLE ROW LEVEL SECURITY;
ALTER TABLE unsupported_feature ENABLE ROW LEVEL SECURITY;
ALTER TABLE normalized_trace ENABLE ROW LEVEL SECURITY;
ALTER TABLE proof_obligation ENABLE ROW LEVEL SECURITY;
ALTER TABLE proof_result ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_artifact ENABLE ROW LEVEL SECURITY;
ALTER TABLE completion_certificate ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_factory_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_factory_step ENABLE ROW LEVEL SECURITY;
ALTER TABLE side_effect_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_ledger ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_ai_solution ON ai_solution;
CREATE POLICY tenant_isolation_ai_solution ON ai_solution USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
DROP POLICY IF EXISTS tenant_isolation_ai_solution_revision ON ai_solution_revision;
CREATE POLICY tenant_isolation_ai_solution_revision ON ai_solution_revision USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
DROP POLICY IF EXISTS tenant_isolation_target_portfolio ON target_portfolio;
CREATE POLICY tenant_isolation_target_portfolio ON target_portfolio USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
DROP POLICY IF EXISTS tenant_isolation_generated_project ON generated_project;
CREATE POLICY tenant_isolation_generated_project ON generated_project USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
DROP POLICY IF EXISTS tenant_isolation_unsupported_feature ON unsupported_feature;
CREATE POLICY tenant_isolation_unsupported_feature ON unsupported_feature USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
DROP POLICY IF EXISTS tenant_isolation_normalized_trace ON normalized_trace;
CREATE POLICY tenant_isolation_normalized_trace ON normalized_trace USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
DROP POLICY IF EXISTS tenant_isolation_proof_obligation ON proof_obligation;
CREATE POLICY tenant_isolation_proof_obligation ON proof_obligation USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
DROP POLICY IF EXISTS tenant_isolation_proof_result ON proof_result;
CREATE POLICY tenant_isolation_proof_result ON proof_result USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
DROP POLICY IF EXISTS tenant_isolation_evidence_artifact ON evidence_artifact;
CREATE POLICY tenant_isolation_evidence_artifact ON evidence_artifact USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
DROP POLICY IF EXISTS tenant_isolation_completion_certificate ON completion_certificate;
CREATE POLICY tenant_isolation_completion_certificate ON completion_certificate USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
DROP POLICY IF EXISTS tenant_isolation_ai_factory_run ON ai_factory_run;
CREATE POLICY tenant_isolation_ai_factory_run ON ai_factory_run USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
DROP POLICY IF EXISTS tenant_isolation_ai_factory_step ON ai_factory_step;
CREATE POLICY tenant_isolation_ai_factory_step ON ai_factory_step USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
DROP POLICY IF EXISTS tenant_isolation_side_effect_ledger ON side_effect_ledger;
CREATE POLICY tenant_isolation_side_effect_ledger ON side_effect_ledger USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
DROP POLICY IF EXISTS tenant_isolation_usage_ledger ON usage_ledger;
CREATE POLICY tenant_isolation_usage_ledger ON usage_ledger USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
COMMIT;
