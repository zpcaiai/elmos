-- ELMOS Batch 11: .NET-specific analysis and execution evidence.
-- Shared jobs, workflow, authorization, billing, audit, SCM and delivery remain in the existing control plane.

DO $$
DECLARE
    table_name text;
    dotnet_tables text[] := ARRAY[
        'dotnet_solutions','dotnet_solution_files','dotnet_projects','dotnet_project_configurations','dotnet_project_references','dotnet_solution_folders',
        'msbuild_evaluations','msbuild_properties','msbuild_items','msbuild_imports','msbuild_targets','msbuild_tasks','msbuild_conditions','msbuild_configurations',
        'dotnet_target_frameworks','dotnet_framework_references','dotnet_assembly_references','dotnet_com_references','dotnet_native_references',
        'nuget_package_references','nuget_packages_config_entries','nuget_dependency_nodes','nuget_dependency_edges','nuget_lock_files','nuget_restore_results',
        'dotnet_fingerprints','dotnet_platform_findings','dotnet_portability_findings',
        'roslyn_solution_snapshots','roslyn_projects','roslyn_documents','roslyn_symbols','roslyn_symbol_edges','roslyn_call_edges','roslyn_diagnostics','roslyn_transformations',
        'dotnet_target_profiles','dotnet_migration_plans','dotnet_migration_steps',
        'aspnet_inventories','aspnet_endpoints','aspnet_modules','aspnet_handlers','aspnet_session_usages','aspnet_auth_usages',
        'wcf_services','wcf_contracts','wcf_endpoints','wcf_bindings','wcf_behaviors','wcf_operations',
        'ef_contexts','ef_models','ef_entities','ef_mappings','ef_queries','ef_migrations','ef_behavior_findings',
        'dotnet_build_runs','dotnet_test_runs','dotnet_compatibility_results'
    ];
BEGIN
    FOREACH table_name IN ARRAY dotnet_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),' ||
            'snapshot_ref varchar(255),' ||
            'engine_version varchar(64) NOT NULL DEFAULT ''1.0.0'',' ||
            'schema_version varchar(32) NOT NULL DEFAULT ''1.0'',' ||
            'status varchar(64) NOT NULL DEFAULT ''CREATED'',' ||
            'external_ref varchar(255),' ||
            'idempotency_key varchar(160),' ||
            'content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ ''^[0-9a-f]{64}$''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'updated_at timestamptz NOT NULL DEFAULT now(),' ||
            'UNIQUE (organization_id, idempotency_key))', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id)', 'idx_' || table_name || '_org', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id, snapshot_ref)', 'idx_' || table_name || '_snapshot', table_name);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name);
    END LOOP;
END;
$$;

CREATE TRIGGER dotnet_build_runs_append_only BEFORE UPDATE OR DELETE ON dotnet_build_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER dotnet_test_runs_append_only BEFORE UPDATE OR DELETE ON dotnet_test_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER dotnet_compatibility_results_append_only BEFORE UPDATE OR DELETE ON dotnet_compatibility_results
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER roslyn_transformations_append_only BEFORE UPDATE OR DELETE ON roslyn_transformations
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
