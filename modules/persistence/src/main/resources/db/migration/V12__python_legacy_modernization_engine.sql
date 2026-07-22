-- ELMOS Batch 12: Python-specific analysis, environment and behavior evidence.
-- Shared workflow, authorization, Runner leases, billing, audit, SCM and delivery remain authoritative in the control plane.

DO $$
DECLARE
    table_name text;
    python_tables text[] := ARRAY[
        'python_projects','python_project_roots','python_packages','python_modules','python_entry_points',
        'python_interpreter_profiles','python_platform_profiles','python_environment_snapshots','python_environment_variables','python_system_dependencies',
        'python_dependency_declarations','python_resolved_distributions','python_dependency_edges','python_dependency_markers','python_dependency_extras','python_wheels','python_sdists','python_lock_files','python_index_sources',
        'python_native_extensions','python_shared_libraries','python_abi_findings','python_cuda_profiles',
        'python_cst_snapshots','python_ast_nodes','python_symbols','python_symbol_edges','python_import_edges','python_call_edges','python_runtime_imports','python_runtime_calls','python_type_results','python_type_diagnostics',
        'python_target_profiles','python_migration_plans','python_migration_steps','python_codemods','python_transformations',
        'django_applications','django_apps','django_models','django_urls','django_views','django_middleware','django_settings','django_migrations',
        'flask_applications','flask_blueprints','flask_routes','flask_extensions','flask_context_usages',
        'data_pipelines','pipeline_tasks','pipeline_dependencies','pipeline_schedules','pipeline_datasets','pipeline_contracts',
        'notebooks','notebook_cells','notebook_dependencies','notebook_execution_results',
        'ml_framework_profiles','ml_model_artifacts','ml_training_configs','ml_feature_schemas','ml_evaluation_results','ml_inference_results',
        'numerical_baselines','numerical_comparisons','dataset_snapshots','dataset_schema_differences'
    ];
BEGIN
    FOREACH table_name IN ARRAY python_tables LOOP
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

CREATE TRIGGER python_environment_snapshots_append_only BEFORE UPDATE OR DELETE ON python_environment_snapshots
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER python_runtime_calls_append_only BEFORE UPDATE OR DELETE ON python_runtime_calls
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER python_transformations_append_only BEFORE UPDATE OR DELETE ON python_transformations
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER numerical_comparisons_append_only BEFORE UPDATE OR DELETE ON numerical_comparisons
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER ml_evaluation_results_append_only BEFORE UPDATE OR DELETE ON ml_evaluation_results
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

