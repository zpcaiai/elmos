BEGIN;

CREATE TABLE language_semantic_profile (tenant_id uuid NOT NULL, profile_id text NOT NULL, language text NOT NULL, runtime_version text NOT NULL, compiler_digest text NOT NULL, semantics jsonb NOT NULL, status text NOT NULL, content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, profile_id));
CREATE TABLE framework_runtime_bridge (tenant_id uuid NOT NULL, bridge_id text NOT NULL, source_profile_id text NOT NULL, target_profile_id text NOT NULL, mappings jsonb NOT NULL, obligations jsonb NOT NULL, content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, bridge_id));
CREATE TABLE polyglot_route_profile (tenant_id uuid NOT NULL, route_id text NOT NULL, source_profile_id text NOT NULL, target_profile_id text NOT NULL, exact_envelope jsonb NOT NULL, maturity text NOT NULL, evidence_root text, content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, route_id));
CREATE TABLE semantic_gap_obligation (tenant_id uuid NOT NULL, obligation_id text NOT NULL, route_id text NOT NULL, dimension text NOT NULL, classification text NOT NULL, severity text NOT NULL, status text NOT NULL, evidence_refs jsonb NOT NULL DEFAULT '[]', content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, obligation_id));
CREATE TABLE polyglot_differential_run (tenant_id uuid NOT NULL, run_id uuid NOT NULL, route_id text NOT NULL, revision_set_id text NOT NULL, execution_epoch bigint NOT NULL, lease_generation bigint NOT NULL, fencing_token text NOT NULL, results jsonb NOT NULL, status text NOT NULL, evidence_root text, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, run_id));

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['language_semantic_profile','framework_runtime_bridge','polyglot_route_profile','semantic_gap_obligation','polyglot_differential_run']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_%I ON %I', t, t);
    EXECUTE format('CREATE POLICY tenant_isolation_%I ON %I USING (tenant_id = nullif(current_setting(''app.tenant_id'', true), )::uuid) WITH CHECK (tenant_id = nullif(current_setting(app.tenant_id, true), )::uuid)', t, t);
  END LOOP;
END $$;

COMMIT;
