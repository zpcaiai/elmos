-- ELMOS Batch 16: provider-neutral cloud and infrastructure modernization projections.
-- Tenant, workflow, approval, secret, evidence, billing, audit, SCM, and delivery authorities remain shared.
-- Existing service_level_objectives, backup_runs, restore_runs, and disaster_recovery_tests are extended,
-- not duplicated. Provider credentials, private keys, and secret values are forbidden from these projections.

DO $$
DECLARE
    table_name text;
    infrastructure_tables text[] := ARRAY[
        'infrastructure_estates','infrastructure_estate_versions','infrastructure_environments','infrastructure_regions','infrastructure_zones',
        'physical_hosts','hypervisors','virtual_machines','operating_system_profiles','host_processes','system_services','workloads','workload_runtime_profiles',
        'network_zones','network_segments','subnets','firewall_rules','load_balancers','load_balancer_routes','dns_zones','dns_records','certificates',
        'storage_volumes','file_shares','object_stores','backup_repositories','storage_dependencies',
        'middleware_instances','middleware_domains','middleware_applications','message_brokers','middleware_queues','middleware_topics','schedulers','scheduled_jobs','web_servers','application_servers',
        'workload_target_profiles','workload_placement_decisions','workload_modernization_plans','workload_modernization_steps',
        'container_profiles','container_images','container_image_layers','container_build_runs','container_sboms','container_signatures','container_vulnerabilities',
        'kubernetes_clusters','kubernetes_namespaces','kubernetes_workloads','kubernetes_services','kubernetes_gateways','kubernetes_network_policies','kubernetes_security_profiles','kubernetes_autoscaling_profiles',
        'serverless_platforms','serverless_services','serverless_functions','serverless_event_sources','serverless_revisions','serverless_scaling_profiles',
        'infrastructure_modules','infrastructure_resources','infrastructure_state_backends','infrastructure_state_versions','infrastructure_plans','infrastructure_apply_runs','infrastructure_drift_findings',
        'observability_profiles','telemetry_sources','telemetry_pipelines','service_level_indicators','error_budgets','operational_readiness_results',
        'cost_allocations','cost_budgets','cost_forecasts','cost_anomalies','optimization_recommendations','unit_economics_metrics',
        'resilience_profiles','failure_scenarios','chaos_experiments','chaos_experiment_runs','backup_plans','disaster_recovery_plans',
        'cloud_provider_profiles','cloud_service_mappings','portability_profiles','vendor_bindings','cloud_exit_plans',
        'infrastructure_cutover_plans','infrastructure_cutover_steps','infrastructure_rollback_runs','infrastructure_decommission_plans'
    ];
BEGIN
    FOREACH table_name IN ARRAY infrastructure_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),' ||
            'infrastructure_estate_ref varchar(255),' ||
            'workload_ref varchar(255),' ||
            'modernization_track varchar(64) NOT NULL DEFAULT ''CLOUD_GOVERNANCE'',' ||
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
            'CHECK (modernization_track IN (''VM_MODERNIZATION'',''CONTAINER_KUBERNETES'',''SERVERLESS_EVENT_DRIVEN'',''CLOUD_GOVERNANCE'')),' ||
            'UNIQUE (organization_id, idempotency_key))', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id)', 'idx_' || table_name || '_org', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id, infrastructure_estate_ref)',
            'idx_' || table_name || '_estate', table_name);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name);
    END LOOP;
END;
$$;

ALTER TABLE service_level_objectives
    ADD COLUMN IF NOT EXISTS infrastructure_estate_ref varchar(255),
    ADD COLUMN IF NOT EXISTS observability_profile_ref varchar(255),
    ADD COLUMN IF NOT EXISTS evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE backup_runs
    ADD COLUMN IF NOT EXISTS infrastructure_estate_ref varchar(255),
    ADD COLUMN IF NOT EXISTS backup_plan_ref varchar(255),
    ADD COLUMN IF NOT EXISTS evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE restore_runs
    ADD COLUMN IF NOT EXISTS infrastructure_estate_ref varchar(255),
    ADD COLUMN IF NOT EXISTS backup_run_ref varchar(255),
    ADD COLUMN IF NOT EXISTS evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE disaster_recovery_tests
    ADD COLUMN IF NOT EXISTS infrastructure_estate_ref varchar(255),
    ADD COLUMN IF NOT EXISTS disaster_recovery_plan_ref varchar(255),
    ADD COLUMN IF NOT EXISTS evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_service_level_objectives_infra_estate ON service_level_objectives (organization_id, infrastructure_estate_ref);
CREATE INDEX IF NOT EXISTS idx_backup_runs_infra_estate ON backup_runs (organization_id, infrastructure_estate_ref);
CREATE INDEX IF NOT EXISTS idx_restore_runs_infra_estate ON restore_runs (organization_id, infrastructure_estate_ref);
CREATE INDEX IF NOT EXISTS idx_disaster_recovery_tests_infra_estate ON disaster_recovery_tests (organization_id, infrastructure_estate_ref);

CREATE TRIGGER infrastructure_estate_versions_append_only BEFORE UPDATE OR DELETE ON infrastructure_estate_versions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER workload_placement_decisions_append_only BEFORE UPDATE OR DELETE ON workload_placement_decisions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER container_build_runs_append_only BEFORE UPDATE OR DELETE ON container_build_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER container_sboms_append_only BEFORE UPDATE OR DELETE ON container_sboms
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER container_signatures_append_only BEFORE UPDATE OR DELETE ON container_signatures
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER container_vulnerabilities_append_only BEFORE UPDATE OR DELETE ON container_vulnerabilities
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER infrastructure_state_versions_append_only BEFORE UPDATE OR DELETE ON infrastructure_state_versions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER infrastructure_plans_append_only BEFORE UPDATE OR DELETE ON infrastructure_plans
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER infrastructure_apply_runs_append_only BEFORE UPDATE OR DELETE ON infrastructure_apply_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER infrastructure_drift_findings_append_only BEFORE UPDATE OR DELETE ON infrastructure_drift_findings
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER operational_readiness_results_append_only BEFORE UPDATE OR DELETE ON operational_readiness_results
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER cost_allocations_append_only BEFORE UPDATE OR DELETE ON cost_allocations
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER cost_forecasts_append_only BEFORE UPDATE OR DELETE ON cost_forecasts
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER cost_anomalies_append_only BEFORE UPDATE OR DELETE ON cost_anomalies
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER unit_economics_metrics_append_only BEFORE UPDATE OR DELETE ON unit_economics_metrics
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER chaos_experiment_runs_append_only BEFORE UPDATE OR DELETE ON chaos_experiment_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER backup_runs_infrastructure_append_only BEFORE UPDATE OR DELETE ON backup_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER restore_runs_infrastructure_append_only BEFORE UPDATE OR DELETE ON restore_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER disaster_recovery_tests_infrastructure_append_only BEFORE UPDATE OR DELETE ON disaster_recovery_tests
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER portability_profiles_append_only BEFORE UPDATE OR DELETE ON portability_profiles
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER infrastructure_cutover_steps_append_only BEFORE UPDATE OR DELETE ON infrastructure_cutover_steps
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER infrastructure_rollback_runs_append_only BEFORE UPDATE OR DELETE ON infrastructure_rollback_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER infrastructure_decommission_plans_append_only BEFORE UPDATE OR DELETE ON infrastructure_decommission_plans
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
