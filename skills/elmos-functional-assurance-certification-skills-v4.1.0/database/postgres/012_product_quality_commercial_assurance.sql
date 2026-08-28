BEGIN;

CREATE TABLE product_quality_model (tenant_id uuid NOT NULL, model_id text NOT NULL, revision_set_id text NOT NULL, characteristics jsonb NOT NULL, measures jsonb NOT NULL, thresholds jsonb NOT NULL, content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, model_id));
CREATE TABLE quality_evaluation_run (tenant_id uuid NOT NULL, run_id uuid NOT NULL, model_id text NOT NULL, results jsonb NOT NULL, critical_failures integer NOT NULL, decision text NOT NULL, evidence_root text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, run_id));
CREATE TABLE accessibility_review (tenant_id uuid NOT NULL, review_id text NOT NULL, revision_set_id text NOT NULL, target text NOT NULL, conformance_level text NOT NULL, automated_results jsonb NOT NULL, manual_results jsonb NOT NULL, exceptions jsonb NOT NULL, decision text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, review_id));
CREATE TABLE privacy_impact_assessment (tenant_id uuid NOT NULL, assessment_id text NOT NULL, revision_set_id text NOT NULL, purposes jsonb NOT NULL, data_flows jsonb NOT NULL, consent_controls jsonb NOT NULL, residual_risks jsonb NOT NULL, decision text NOT NULL, content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, assessment_id));
CREATE TABLE service_slo_window (tenant_id uuid NOT NULL, service_id text NOT NULL, window_start timestamptz NOT NULL, window_end timestamptz NOT NULL, sli_results jsonb NOT NULL, budget_remaining numeric NOT NULL, release_decision text NOT NULL, evidence_hash text NOT NULL, PRIMARY KEY (tenant_id, service_id, window_start));
CREATE TABLE enterprise_assurance_dossier (tenant_id uuid NOT NULL, dossier_id text NOT NULL, customer_scope text NOT NULL, revision_set_id text NOT NULL, sections jsonb NOT NULL, evidence_map jsonb NOT NULL, gaps jsonb NOT NULL, content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, dossier_id));

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['product_quality_model','quality_evaluation_run','accessibility_review','privacy_impact_assessment','service_slo_window','enterprise_assurance_dossier']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_%I ON %I', t, t);
    EXECUTE format('CREATE POLICY tenant_isolation_%I ON %I USING (tenant_id = nullif(current_setting(''app.tenant_id'', true), )::uuid) WITH CHECK (tenant_id = nullif(current_setting(app.tenant_id, true), )::uuid)', t, t);
  END LOOP;
END $$;

COMMIT;
