BEGIN;

CREATE TABLE release_attestation (tenant_id uuid NOT NULL, attestation_id text NOT NULL, revision_set_id text NOT NULL, predicate_type text NOT NULL, subject_digests jsonb NOT NULL, builder_identity text NOT NULL, signature_bundle jsonb NOT NULL, verified boolean NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, attestation_id));
CREATE TABLE runtime_attestation_result (tenant_id uuid NOT NULL, result_id text NOT NULL, workload_id text NOT NULL, nonce text NOT NULL, evidence jsonb NOT NULL, appraisal_policy_digest text NOT NULL, decision text NOT NULL, expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, result_id));
CREATE TABLE transparency_log_checkpoint (tenant_id uuid NOT NULL, log_id text NOT NULL, tree_size bigint NOT NULL, root_hash text NOT NULL, consistency_proof jsonb NOT NULL, notary_signatures jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, log_id, tree_size));
CREATE TABLE psirt_case (tenant_id uuid NOT NULL, case_id text NOT NULL, product_scope jsonb NOT NULL, severity text NOT NULL, embargo_until timestamptz, affected_versions jsonb NOT NULL, remediation jsonb NOT NULL, disclosure_status text NOT NULL, evidence_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, case_id));
CREATE TABLE incident_recertification_decision (tenant_id uuid NOT NULL, decision_id text NOT NULL, incident_id text NOT NULL, affected_certificates jsonb NOT NULL, causal_claims jsonb NOT NULL, corrective_actions jsonb NOT NULL, decision text NOT NULL, evidence_root text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, decision_id));

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['release_attestation','runtime_attestation_result','transparency_log_checkpoint','psirt_case','incident_recertification_decision']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_%I ON %I', t, t);
    EXECUTE format('CREATE POLICY tenant_isolation_%I ON %I USING (tenant_id = nullif(current_setting(''app.tenant_id'', true), )::uuid) WITH CHECK (tenant_id = nullif(current_setting(app.tenant_id, true), )::uuid)', t, t);
  END LOOP;
END $$;

COMMIT;
