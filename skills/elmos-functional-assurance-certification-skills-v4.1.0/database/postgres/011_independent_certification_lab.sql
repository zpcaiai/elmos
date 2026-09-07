BEGIN;

CREATE TABLE certification_scope (tenant_id uuid NOT NULL, scope_id text NOT NULL, revision_set_id text NOT NULL, subject jsonb NOT NULL, assumptions jsonb NOT NULL, excluded_claims jsonb NOT NULL, assurance_level text NOT NULL, content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, scope_id));
CREATE TABLE clean_room_build (tenant_id uuid NOT NULL, build_id uuid NOT NULL, scope_id text NOT NULL, builder_identity text NOT NULL, source_digest text NOT NULL, environment_digest text NOT NULL, artifact_digests jsonb NOT NULL, reproducible boolean NOT NULL, attestation_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, build_id));
CREATE TABLE native_conformance_run (tenant_id uuid NOT NULL, run_id uuid NOT NULL, scope_id text NOT NULL, target text NOT NULL, exact_version text NOT NULL, runner_identity text NOT NULL, results jsonb NOT NULL, decision text NOT NULL, evidence_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, run_id));
CREATE TABLE customer_holdout_run (tenant_id uuid NOT NULL, run_id uuid NOT NULL, scope_id text NOT NULL, holdout_digest text NOT NULL, contamination_report jsonb NOT NULL, results jsonb NOT NULL, customer_decision text NOT NULL, evidence_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, run_id));
CREATE TABLE evidence_chain_entry (tenant_id uuid NOT NULL, chain_id text NOT NULL, sequence bigint NOT NULL, previous_hash text, artifact_hash text NOT NULL, entry_hash text NOT NULL, signer text, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, chain_id, sequence));
CREATE TABLE certification_waiver (tenant_id uuid NOT NULL, waiver_id text NOT NULL, scope_id text NOT NULL, claim text NOT NULL, justification text NOT NULL, owner text NOT NULL, approver text NOT NULL, expires_at timestamptz NOT NULL, status text NOT NULL, evidence_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, waiver_id));
CREATE TABLE certificate_revocation (tenant_id uuid NOT NULL, revocation_id text NOT NULL, certificate_id text NOT NULL, trigger text NOT NULL, effective_at timestamptz NOT NULL, scope_impact jsonb NOT NULL, recertification_required boolean NOT NULL, evidence_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, revocation_id));

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['certification_scope','clean_room_build','native_conformance_run','customer_holdout_run','evidence_chain_entry','certification_waiver','certificate_revocation']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_%I ON %I', t, t);
    EXECUTE format('CREATE POLICY tenant_isolation_%I ON %I USING (tenant_id = nullif(current_setting(''app.tenant_id'', true), )::uuid) WITH CHECK (tenant_id = nullif(current_setting(app.tenant_id, true), )::uuid)', t, t);
  END LOOP;
END $$;

COMMIT;
