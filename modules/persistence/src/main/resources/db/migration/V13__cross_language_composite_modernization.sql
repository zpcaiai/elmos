-- ELMOS Batch 13: cross-language composite modernization control and evidence.
-- The Java, .NET and Python engines remain the only source transformation engines.

DO $$
DECLARE
    table_name text;
    composite_tables text[] := ARRAY[
        'system_landscapes','system_landscape_versions','business_domains','business_capabilities','business_journeys','business_journey_steps',
        'system_nodes','repository_nodes','deployable_units','runtime_services','batch_jobs','model_endpoints','external_systems',
        'system_dependency_edges','dependency_edge_evidence','dependency_confidence_records','dependency_observations','dependency_unknowns',
        'api_contracts','api_contract_versions','api_operations','message_contracts','message_contract_versions','message_channels','message_operations','data_contracts','data_contract_versions','file_contracts','model_contracts',
        'contract_producers','contract_consumers','contract_consumer_matrix','contract_compatibility_results','unknown_consumers',
        'composite_migration_plans','composite_migration_waves','composite_wave_members','composite_step_dependencies',
        'compatibility_windows','compatibility_window_versions','compatibility_runtime_components','compatibility_runtime_routes','compatibility_runtime_transformations',
        'data_ownership_records','data_ownership_transitions','data_migration_plans','cdc_streams','cdc_offsets','backfill_runs','backfill_chunks','reconciliation_runs','reconciliation_results',
        'shadow_experiments','shadow_traffic_sources','shadow_requests','shadow_responses','shadow_differential_results',
        'traffic_shift_plans','traffic_shift_stages','traffic_shift_observations','canary_cohorts','traffic_shift_decisions',
        'system_validation_plans','business_journey_runs','system_consistency_results','system_slo_results',
        'system_cutover_plans','system_cutover_steps','cutover_decisions','rollback_points','rollback_executions','stability_hold_periods',
        'decommission_plans','decommission_checks','decommission_decisions','legacy_access_records'
    ];
BEGIN
    FOREACH table_name IN ARRAY composite_tables LOOP
        -- Batch 7 already owns message contract validation and Batch 9 owns the model endpoint
        -- catalog. Reuse those tenant-scoped authorities and add only the composite projection.
        IF table_name IN ('message_contracts', 'model_endpoints') THEN
            EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS landscape_version_ref varchar(255)', table_name);
            EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS engine_version varchar(64) NOT NULL DEFAULT ''1.0.0''', table_name);
            EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (organization_id, landscape_version_ref)',
                'idx_' || table_name || '_landscape', table_name);
            CONTINUE;
        END IF;
        EXECUTE format(
            'CREATE TABLE %I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),' ||
            'landscape_version_ref varchar(255),' ||
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
        EXECUTE format('CREATE INDEX %I ON %I (organization_id, landscape_version_ref)', 'idx_' || table_name || '_landscape', table_name);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name);
    END LOOP;
END;
$$;

CREATE TRIGGER system_landscape_versions_append_only BEFORE UPDATE OR DELETE ON system_landscape_versions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER dependency_edge_evidence_append_only BEFORE UPDATE OR DELETE ON dependency_edge_evidence
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER dependency_observations_append_only BEFORE UPDATE OR DELETE ON dependency_observations
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER contract_compatibility_results_append_only BEFORE UPDATE OR DELETE ON contract_compatibility_results
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER compatibility_window_versions_append_only BEFORE UPDATE OR DELETE ON compatibility_window_versions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER data_ownership_transitions_append_only BEFORE UPDATE OR DELETE ON data_ownership_transitions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER cdc_offsets_append_only BEFORE UPDATE OR DELETE ON cdc_offsets
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER reconciliation_results_append_only BEFORE UPDATE OR DELETE ON reconciliation_results
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER shadow_requests_append_only BEFORE UPDATE OR DELETE ON shadow_requests
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER shadow_responses_append_only BEFORE UPDATE OR DELETE ON shadow_responses
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER shadow_differential_results_append_only BEFORE UPDATE OR DELETE ON shadow_differential_results
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER traffic_shift_observations_append_only BEFORE UPDATE OR DELETE ON traffic_shift_observations
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER traffic_shift_decisions_append_only BEFORE UPDATE OR DELETE ON traffic_shift_decisions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER business_journey_runs_append_only BEFORE UPDATE OR DELETE ON business_journey_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER cutover_decisions_append_only BEFORE UPDATE OR DELETE ON cutover_decisions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER rollback_executions_append_only BEFORE UPDATE OR DELETE ON rollback_executions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER decommission_decisions_append_only BEFORE UPDATE OR DELETE ON decommission_decisions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER legacy_access_records_append_only BEFORE UPDATE OR DELETE ON legacy_access_records
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
