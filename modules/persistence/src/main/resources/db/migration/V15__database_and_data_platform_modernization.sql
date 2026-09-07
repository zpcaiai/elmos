-- ELMOS Batch 15: database and data-platform modernization projections.
-- Tenant, workflow, approval, evidence, billing, audit, SCM, and delivery authorities remain shared.
-- cdc_streams and cdc_offsets are reused from V13 instead of creating competing CDC authorities.

DO $$
DECLARE
    table_name text;
    data_tables text[] := ARRAY[
        'database_estates','database_instances','database_engine_profiles','databases','database_schemas','database_objects',
        'database_tables','database_columns','database_constraints','database_indexes','database_partitions','database_sequences',
        'database_identities','database_views','database_materialized_views','database_synonyms','database_links','database_extensions',
        'database_routines','database_procedures','database_functions','database_packages','database_triggers','database_scheduled_jobs','database_events',
        'sql_statements','sql_fingerprints','sql_workloads','sql_workload_samples','sql_execution_plans','sql_runtime_statistics','sql_dependency_edges',
        'database_target_profiles','database_migration_plans','database_migration_steps','schema_conversions','sql_conversions','procedure_conversions','conversion_findings',
        'bulk_load_plans','bulk_load_runs','bulk_load_chunks','cdc_plans','cdc_lag_samples','replication_conflicts',
        'data_assets','data_owners','data_classifications','data_quality_rules','data_quality_runs','data_quality_results',
        'data_reconciliation_runs','data_reconciliation_results',
        'lakehouse_catalogs','lakehouse_tables','lakehouse_table_versions','lakehouse_snapshots','lakehouse_partition_specs','lakehouse_protocol_profiles',
        'data_products','data_product_contracts','transformation_models','transformation_runs',
        'semantic_models','semantic_entities','semantic_dimensions','semantic_measures','semantic_metrics','metric_versions',
        'bi_artifacts','bi_reports','bi_dashboards','bi_datasets','bi_calculations','bi_dependencies',
        'lineage_jobs','lineage_runs','lineage_datasets','lineage_edges','lineage_events',
        'governance_policies','data_access_policies','data_retention_policies','data_masking_policies','data_deletion_policies'
    ];
BEGIN
    FOREACH table_name IN ARRAY data_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),' ||
            'database_estate_ref varchar(255),' ||
            'data_asset_ref varchar(255),' ||
            'modernization_track varchar(64) NOT NULL DEFAULT ''OLTP_DATABASE'',' ||
            'engine_version varchar(64) NOT NULL DEFAULT ''1.0.0'',' ||
            'schema_version varchar(32) NOT NULL DEFAULT ''1.0'',' ||
            'status varchar(64) NOT NULL DEFAULT ''CREATED'',' ||
            'external_ref varchar(255),' ||
            'idempotency_key varchar(160),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb,' ||
            'content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ ''^[0-9a-f]{64}$''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'updated_at timestamptz NOT NULL DEFAULT now(),' ||
            'CHECK (modernization_track IN (''OLTP_DATABASE'',''ANALYTICS_PLATFORM'',''BI_SEMANTIC'')),' ||
            'UNIQUE (organization_id, idempotency_key))', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id)',
            'idx_' || table_name || '_org', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id, database_estate_ref)',
            'idx_' || table_name || '_estate', table_name);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name);
    END LOOP;
END;
$$;

ALTER TABLE cdc_streams
    ADD COLUMN IF NOT EXISTS database_estate_ref varchar(255),
    ADD COLUMN IF NOT EXISTS cutover_frontier varchar(255),
    ADD COLUMN IF NOT EXISTS database_engine_version varchar(64);
ALTER TABLE cdc_offsets
    ADD COLUMN IF NOT EXISTS database_estate_ref varchar(255),
    ADD COLUMN IF NOT EXISTS source_position varchar(255),
    ADD COLUMN IF NOT EXISTS applied_position varchar(255),
    ADD COLUMN IF NOT EXISTS offset_recoverable boolean NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS idx_cdc_streams_database_estate
    ON cdc_streams (organization_id, database_estate_ref);
CREATE INDEX IF NOT EXISTS idx_cdc_offsets_database_estate
    ON cdc_offsets (organization_id, database_estate_ref);

CREATE TRIGGER database_engine_profiles_append_only BEFORE UPDATE OR DELETE ON database_engine_profiles
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER sql_workload_samples_append_only BEFORE UPDATE OR DELETE ON sql_workload_samples
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER sql_execution_plans_append_only BEFORE UPDATE OR DELETE ON sql_execution_plans
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER sql_runtime_statistics_append_only BEFORE UPDATE OR DELETE ON sql_runtime_statistics
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER schema_conversions_append_only BEFORE UPDATE OR DELETE ON schema_conversions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER sql_conversions_append_only BEFORE UPDATE OR DELETE ON sql_conversions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER procedure_conversions_append_only BEFORE UPDATE OR DELETE ON procedure_conversions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER bulk_load_runs_append_only BEFORE UPDATE OR DELETE ON bulk_load_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER bulk_load_chunks_append_only BEFORE UPDATE OR DELETE ON bulk_load_chunks
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER cdc_lag_samples_append_only BEFORE UPDATE OR DELETE ON cdc_lag_samples
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER replication_conflicts_append_only BEFORE UPDATE OR DELETE ON replication_conflicts
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER data_quality_runs_append_only BEFORE UPDATE OR DELETE ON data_quality_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER data_quality_results_append_only BEFORE UPDATE OR DELETE ON data_quality_results
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER data_reconciliation_results_append_only BEFORE UPDATE OR DELETE ON data_reconciliation_results
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER lakehouse_table_versions_append_only BEFORE UPDATE OR DELETE ON lakehouse_table_versions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER lakehouse_snapshots_append_only BEFORE UPDATE OR DELETE ON lakehouse_snapshots
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER lakehouse_protocol_profiles_append_only BEFORE UPDATE OR DELETE ON lakehouse_protocol_profiles
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER transformation_runs_append_only BEFORE UPDATE OR DELETE ON transformation_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER metric_versions_append_only BEFORE UPDATE OR DELETE ON metric_versions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER lineage_runs_append_only BEFORE UPDATE OR DELETE ON lineage_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER lineage_events_append_only BEFORE UPDATE OR DELETE ON lineage_events
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
