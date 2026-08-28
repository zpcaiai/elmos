BEGIN;

CREATE TABLE database_dialect_profile (tenant_id uuid NOT NULL, profile_id text NOT NULL, engine text NOT NULL, engine_version text NOT NULL, compatibility_mode text NOT NULL, charset text NOT NULL, collation text NOT NULL, driver_digest text NOT NULL, semantics jsonb NOT NULL, content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, profile_id));
CREATE TABLE sql_ir_artifact (tenant_id uuid NOT NULL, artifact_id text NOT NULL, ir_kind text NOT NULL, source_profile_id text NOT NULL, schema_version text NOT NULL, payload jsonb NOT NULL, content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, artifact_id));
CREATE TABLE database_migration_plan (tenant_id uuid NOT NULL, plan_id text NOT NULL, revision_set_id text NOT NULL, source_profile_id text NOT NULL, target_profile_id text NOT NULL, snapshot_plan jsonb NOT NULL, cdc_plan jsonb NOT NULL, cutover_plan jsonb NOT NULL, rollback_plan jsonb NOT NULL, status text NOT NULL, content_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, plan_id));
CREATE TABLE dual_execution_run (tenant_id uuid NOT NULL, run_id uuid NOT NULL, plan_id text NOT NULL, execution_epoch bigint NOT NULL, lease_generation bigint NOT NULL, fencing_token text NOT NULL, source_observation jsonb NOT NULL, target_observation jsonb NOT NULL, differences jsonb NOT NULL, status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, run_id));
CREATE TABLE transaction_equivalence_result (tenant_id uuid NOT NULL, result_id text NOT NULL, run_id uuid NOT NULL, scenario text NOT NULL, source_trace jsonb NOT NULL, target_trace jsonb NOT NULL, equivalent boolean NOT NULL, evidence_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, result_id));

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['database_dialect_profile','sql_ir_artifact','database_migration_plan','dual_execution_run','transaction_equivalence_result']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_%I ON %I', t, t);
    EXECUTE format('CREATE POLICY tenant_isolation_%I ON %I USING (tenant_id = nullif(current_setting(''app.tenant_id'', true), )::uuid) WITH CHECK (tenant_id = nullif(current_setting(app.tenant_id, true), )::uuid)', t, t);
  END LOOP;
END $$;

COMMIT;
