BEGIN;

CREATE OR REPLACE FUNCTION etgb.current_tenant_id()
RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT nullif(current_setting('app.tenant_id', true), '')::uuid
$$;

DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'benchmark_suite','benchmark_case','benchmark_case_version','corpus_snapshot','release_candidate','run_plan',
    'environment_authority','benchmark_run','run_shard','benchmark_case_run','run_transition','run_checkpoint',
    'oracle_result','evidence_artifact','evidence_seal','budget_reservation','usage_ledger','release_gate_result',
    'waiver','capability_coverage','failure_cluster','regression_link','idempotency_record','outbox_event'
  ] LOOP
    EXECUTE format('ALTER TABLE etgb.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE etgb.%I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON etgb.%I', table_name);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON etgb.%I USING (tenant_id = etgb.current_tenant_id()) WITH CHECK (tenant_id = etgb.current_tenant_id())',
      table_name
    );
  END LOOP;
END;
$$;

COMMIT;
