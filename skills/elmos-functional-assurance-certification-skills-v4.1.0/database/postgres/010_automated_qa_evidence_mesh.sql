BEGIN;

CREATE TABLE qa_plan (tenant_id uuid NOT NULL, plan_id text NOT NULL, revision_set_id text NOT NULL, proof_graph_id text NOT NULL, validation_dag jsonb NOT NULL, selection_rationale jsonb NOT NULL, content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, plan_id));
CREATE TABLE qa_case (tenant_id uuid NOT NULL, case_id text NOT NULL, plan_id text NOT NULL, class text NOT NULL, risk text NOT NULL, oracle_id text NOT NULL, fixture_ref text, required boolean NOT NULL, content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, case_id));
CREATE TABLE qa_run (tenant_id uuid NOT NULL, run_id uuid NOT NULL, plan_id text NOT NULL, execution_epoch bigint NOT NULL, lease_generation bigint NOT NULL, fencing_token text NOT NULL, status text NOT NULL, started_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz, PRIMARY KEY (tenant_id, run_id));
CREATE TABLE qa_case_result (tenant_id uuid NOT NULL, run_id uuid NOT NULL, case_id text NOT NULL, status text NOT NULL, observation jsonb NOT NULL, evidence_hash text NOT NULL, wall_clock_ms bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, run_id, case_id));
CREATE TABLE oracle_registration (tenant_id uuid NOT NULL, oracle_id text NOT NULL, authority_class text NOT NULL, scope jsonb NOT NULL, version_digest text NOT NULL, independent boolean NOT NULL, status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, oracle_id));
CREATE TABLE verification_counterexample (tenant_id uuid NOT NULL, counterexample_id text NOT NULL, obligation_id text NOT NULL, minimal_input jsonb NOT NULL, observation jsonb NOT NULL, regression_case_id text, status text NOT NULL, content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, counterexample_id));
CREATE TABLE flake_record (tenant_id uuid NOT NULL, case_id text NOT NULL, first_failure_hash text NOT NULL, rate numeric NOT NULL, owner text NOT NULL, expires_at timestamptz NOT NULL, critical boolean NOT NULL, status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, case_id));

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['qa_plan','qa_case','qa_run','qa_case_result','oracle_registration','verification_counterexample','flake_record']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_%I ON %I', t, t);
    EXECUTE format('CREATE POLICY tenant_isolation_%I ON %I USING (tenant_id = nullif(current_setting(''app.tenant_id'', true), )::uuid) WITH CHECK (tenant_id = nullif(current_setting(app.tenant_id, true), )::uuid)', t, t);
  END LOOP;
END $$;

COMMIT;
