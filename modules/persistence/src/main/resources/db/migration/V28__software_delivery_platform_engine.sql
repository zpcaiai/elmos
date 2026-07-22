-- ELMOS Skill Pack Batch 22. Generated from the authoritative attachment table inventory.
-- A dedicated namespace preserves logical names without stealing authority from earlier batch tables.
-- These tables record tenant-scoped evidence and decisions; they do not execute provider or production actions.

CREATE SCHEMA IF NOT EXISTS software_delivery;

DO $$
DECLARE
    target_schema text := 'software_delivery';
    table_name text;
    batch_tables text[] := ARRAY[
        'software_delivery_estates',
        'scm_systems',
        'scm_repositories',
        'repository_histories',
        'repository_identity_mappings',
        'repository_branches',
        'repository_tags',
        'repository_migration_runs',
        'delivery_value_streams',
        'delivery_stages',
        'delivery_activities',
        'delivery_wait_states',
        'delivery_handoffs',
        'delivery_approvals',
        'delivery_rework_records',
        'pipeline_definitions',
        'pipeline_versions',
        'pipeline_runs',
        'pipeline_stages',
        'pipeline_jobs',
        'pipeline_components',
        'pipeline_component_versions',
        'pipeline_dependencies',
        'pipeline_templates',
        'artifacts',
        'artifact_versions',
        'artifact_digests',
        'artifact_relationships',
        'artifact_promotions',
        'artifact_retention_policies',
        'artifact_quarantines',
        'artifact_download_observations',
        'environments',
        'environment_types',
        'environment_templates',
        'environment_leases',
        'environment_deployments',
        'environment_drift_findings',
        'environment_cleanup_runs',
        'platform_capabilities',
        'platform_capability_versions',
        'platform_products',
        'platform_service_levels',
        'platform_incidents',
        'software_catalog_entities',
        'software_catalog_relations',
        'software_catalog_owners',
        'software_catalog_scores',
        'software_catalog_annotations',
        'golden_paths',
        'golden_path_versions',
        'golden_path_variants',
        'golden_path_capabilities',
        'golden_path_adoptions',
        'golden_path_exceptions',
        'golden_path_deprecations',
        'self_service_offerings',
        'self_service_requests',
        'self_service_operations',
        'self_service_approvals',
        'resource_leases',
        'resource_quota_allocations',
        'developer_journeys',
        'developer_journey_steps',
        'developer_experience_signals',
        'developer_friction_points',
        'cognitive_load_findings',
        'developer_satisfaction_surveys',
        'dora_metric_definitions',
        'dora_metric_observations',
        'flow_metric_observations',
        'platform_outcomes',
        'platform_scorecards',
        'metric_coverage_results',
        'metric_quality_findings',
        'platform_adoption_plans',
        'platform_cohorts',
        'platform_onboarding_runs',
        'platform_support_cases',
        'platform_feedback',
        'platform_roadmap_items'
    ];
    append_only_tables text[] := ARRAY[
        'repository_histories',
        'repository_migration_runs',
        'delivery_handoffs',
        'delivery_approvals',
        'delivery_rework_records',
        'pipeline_versions',
        'pipeline_runs',
        'pipeline_component_versions',
        'artifact_versions',
        'artifact_download_observations',
        'environment_drift_findings',
        'environment_cleanup_runs',
        'platform_capability_versions',
        'golden_path_versions',
        'self_service_approvals',
        'developer_friction_points',
        'cognitive_load_findings',
        'dora_metric_observations',
        'flow_metric_observations',
        'metric_coverage_results',
        'metric_quality_findings',
        'platform_onboarding_runs',
        'platform_feedback'
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
                'CREATE TRIGGER batch_22_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
                target_schema, table_name);
        END IF;
    END LOOP;
END;
$$;
