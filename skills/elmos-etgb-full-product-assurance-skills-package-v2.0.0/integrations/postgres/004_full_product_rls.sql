BEGIN;

DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'product_feature','feature_test_binding','product_journey','assurance_control','adapter_conformance','coverage_gap'
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
