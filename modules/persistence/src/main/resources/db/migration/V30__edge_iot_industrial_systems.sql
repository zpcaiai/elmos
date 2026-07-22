-- ELMOS Skill Pack Batch 24. Generated from the authoritative attachment table inventory.
-- A dedicated namespace preserves logical names without stealing authority from earlier batch tables.
-- These tables record tenant-scoped evidence and decisions; they do not execute provider or production actions.

CREATE SCHEMA IF NOT EXISTS edge_industrial;

DO $$
DECLARE
    target_schema text := 'edge_industrial';
    table_name text;
    batch_tables text[] := ARRAY[
        'industrial_estates',
        'industrial_sites',
        'industrial_areas',
        'industrial_lines',
        'industrial_cells',
        'physical_assets',
        'asset_classes',
        'asset_relationships',
        'industrial_devices',
        'device_models',
        'device_instances',
        'device_capabilities',
        'device_firmware_versions',
        'device_configuration_versions',
        'plcs',
        'plc_projects',
        'plc_project_versions',
        'plc_programs',
        'plc_tasks',
        'plc_variables',
        'plc_blocks',
        'safety_controllers',
        'industrial_interlocks',
        'scada_systems',
        'scada_tags',
        'hmi_screens',
        'alarm_definitions',
        'historian_sources',
        'industrial_protocols',
        'protocol_endpoints',
        'protocol_addresses',
        'protocol_mappings',
        'protocol_gateways',
        'industrial_tags',
        'industrial_tag_versions',
        'tag_contracts',
        'engineering_units',
        'tag_quality_profiles',
        'tag_write_policies',
        'tag_sampling_policies',
        'opcua_servers',
        'opcua_clients',
        'opcua_nodes',
        'opcua_node_types',
        'opcua_events',
        'opcua_methods',
        'opcua_pubsub_connections',
        'opcua_security_profiles',
        'mqtt_brokers',
        'mqtt_clients',
        'mqtt_topics',
        'mqtt_sessions',
        'mqtt_delivery_profiles',
        'sparkplug_edge_nodes',
        'sparkplug_devices',
        'sparkplug_metrics',
        'edge_nodes',
        'edge_runtime_profiles',
        'edge_workloads',
        'edge_applications',
        'edge_offline_policies',
        'edge_resource_observations',
        'device_identities',
        'device_certificates',
        'device_credentials',
        'device_enrollment_records',
        'device_attestation_results',
        'ota_artifacts',
        'ota_releases',
        'ota_release_dependencies',
        'ota_campaigns',
        'ota_campaign_rings',
        'ota_device_results',
        'ota_rollback_runs',
        'digital_twins',
        'digital_twin_versions',
        'twin_features',
        'twin_reported_states',
        'twin_desired_states',
        'twin_commands',
        'twin_command_results',
        'twin_relationships',
        'time_series_signals',
        'time_series_points',
        'historian_tags',
        'historian_mappings',
        'time_series_quality_profiles',
        'industrial_events',
        'industrial_event_contexts',
        'edge_ai_models',
        'edge_ai_model_versions',
        'edge_ai_deployments',
        'edge_ai_inferences',
        'edge_ai_drift_results',
        'cloud_edge_sync_profiles',
        'edge_buffers',
        'edge_buffer_checkpoints',
        'command_deliveries',
        'command_acknowledgements',
        'consistency_policies',
        'industrial_safety_profiles',
        'industrial_zones',
        'industrial_conduits',
        'ot_security_controls',
        'ot_security_assessments',
        'simulation_models',
        'sil_runs',
        'hil_runs',
        'shadow_runs',
        'site_cutover_plans',
        'site_cutover_steps',
        'industrial_decommission_plans'
    ];
    append_only_tables text[] := ARRAY[
        'device_firmware_versions',
        'device_configuration_versions',
        'plc_project_versions',
        'protocol_endpoints',
        'industrial_tag_versions',
        'opcua_events',
        'edge_resource_observations',
        'device_enrollment_records',
        'device_attestation_results',
        'ota_device_results',
        'ota_rollback_runs',
        'digital_twin_versions',
        'twin_command_results',
        'time_series_points',
        'industrial_events',
        'edge_ai_model_versions',
        'edge_ai_inferences',
        'edge_ai_drift_results',
        'edge_buffer_checkpoints',
        'sil_runs',
        'hil_runs',
        'shadow_runs'
    ];
BEGIN
    FOREACH table_name IN ARRAY batch_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I.%I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES public.organizations(organization_id),' ||
            'tenant_id varchar(96) NOT NULL,' ||
            'domain_run_id varchar(160),' ||
            'workspace_ref varchar(512),' ||
            'owner_id varchar(160) NOT NULL,' ||
            'human_owner_id varchar(160) NOT NULL,' ||
            'status varchar(64) NOT NULL DEFAULT ''OBSERVED'',' ||
            'authority_status varchar(64) NOT NULL DEFAULT ''OBSERVED'',' ||
            'confidence numeric(5,4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),' ||
            'source varchar(160) NOT NULL,' ||
            'source_record_ref varchar(512) NOT NULL,' ||
            'idempotency_key varchar(160) NOT NULL,' ||
            'evidence_status varchar(32) NOT NULL DEFAULT ''NOT_RUN'' CHECK (evidence_status IN (''NOT_RUN'',''INCONCLUSIVE'',''PASS'',''FAIL'',''BLOCKED'')),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb CHECK (jsonb_typeof(evidence_refs) = ''array''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb CHECK (jsonb_typeof(payload) = ''object''),' ||
            'external_operation_executed boolean NOT NULL DEFAULT false,' ||
            'actual_execution_evidence_ref varchar(512),' ||
            'production_state_changed boolean NOT NULL DEFAULT false,' ||
            'human_approval_ref varchar(512),' ||
            'observed_at timestamptz NOT NULL,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'updated_at timestamptz NOT NULL DEFAULT now(),' ||
            'CHECK (NOT external_operation_executed OR actual_execution_evidence_ref IS NOT NULL),' ||
            'CHECK (NOT production_state_changed OR human_approval_ref IS NOT NULL),' ||
            'CHECK (status NOT IN (''SUCCEEDED'',''APPROVED'',''PASS'') OR jsonb_array_length(evidence_refs) > 0),' ||
            'UNIQUE (organization_id, idempotency_key),' ||
            'UNIQUE (organization_id, source, source_record_ref))',
            target_schema, table_name);
        EXECUTE format('CREATE INDEX %I ON %I.%I (organization_id)',
                       'idx_' || table_name || '_organization', target_schema, table_name);
        EXECUTE format('CREATE INDEX %I ON %I.%I (organization_id, domain_run_id, status)',
                       'idx_' || table_name || '_domain_run', target_schema, table_name);
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', target_schema, table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', target_schema, table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I.%I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            target_schema, table_name);
        IF table_name = ANY(append_only_tables) THEN
            EXECUTE format(
                'CREATE TRIGGER batch_24_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
                target_schema, table_name);
        END IF;
    END LOOP;
END;
$$;
