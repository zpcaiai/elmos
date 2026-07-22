-- ELMOS Skill Pack Batch 26. Generated from the authoritative attachment table inventory.
-- A dedicated namespace preserves logical names without stealing authority from earlier batch tables.
-- These tables record tenant-scoped evidence and decisions; they do not execute provider or production actions.

CREATE SCHEMA IF NOT EXISTS enterprise_architecture;

DO $$
DECLARE
    target_schema text := 'enterprise_architecture';
    table_name text;
    batch_tables text[] := ARRAY[
        'enterprise_contexts',
        'enterprise_strategies',
        'strategic_outcomes',
        'strategic_objectives',
        'enterprise_stakeholders',
        'stakeholder_concerns',
        'enterprise_constraints',
        'business_capabilities',
        'business_capability_versions',
        'business_capability_hierarchies',
        'business_capability_owners',
        'business_capability_assessments',
        'business_capability_heatmaps',
        'value_streams',
        'value_stream_versions',
        'value_stages',
        'customer_journeys',
        'operating_models',
        'organization_units',
        'business_roles',
        'architecture_repositories',
        'architecture_elements',
        'architecture_element_versions',
        'architecture_relationships',
        'architecture_relationship_versions',
        'architecture_snapshots',
        'architecture_baselines',
        'architecture_evidence_links',
        'architecture_frameworks',
        'architecture_languages',
        'architecture_viewpoints',
        'architecture_views',
        'architecture_model_kinds',
        'architecture_models',
        'portfolio_applications',
        'application_versions',
        'application_services',
        'application_instances',
        'application_owners',
        'application_usage_observations',
        'application_cost_observations',
        'application_portfolio_assessments',
        'application_lifecycle_decisions',
        'technologies',
        'technology_products',
        'technology_versions',
        'technology_categories',
        'technology_usage_observations',
        'technology_radar_entries',
        'technology_radar_movements',
        'technology_standards',
        'technology_lifecycle_decisions',
        'architecture_principles',
        'architecture_patterns',
        'reference_architectures',
        'architecture_standards',
        'architecture_standard_versions',
        'architecture_standard_scopes',
        'architecture_exceptions',
        'architecture_exception_reviews',
        'architecture_exception_controls',
        'architecture_exception_remediations',
        'architecture_dependencies',
        'dependency_clusters',
        'technology_concentration_risks',
        'vendor_concentration_risks',
        'skill_concentration_risks',
        'obsolescence_risks',
        'systemic_architecture_risks',
        'current_architectures',
        'transition_architectures',
        'target_architectures',
        'architecture_gaps',
        'architecture_building_blocks',
        'architecture_options',
        'architecture_evaluation_scenarios',
        'quality_attributes',
        'architecture_tradeoffs',
        'architecture_evaluation_results',
        'investment_initiatives',
        'investment_options',
        'business_cases',
        'benefit_hypotheses',
        'benefit_observations',
        'portfolio_decisions',
        'funding_envelopes',
        'architecture_roadmaps',
        'architecture_roadmap_versions',
        'roadmap_waves',
        'roadmap_milestones',
        'roadmap_dependencies',
        'roadmap_decision_gates',
        'architecture_decisions',
        'architecture_decision_options',
        'architecture_decision_criteria',
        'architecture_decision_consequences',
        'architecture_reviews',
        'architecture_review_findings',
        'architecture_conformance_profiles',
        'architecture_conformance_runs',
        'architecture_drift_findings',
        'architecture_remediation_plans',
        'architecture_operating_models',
        'architecture_roles',
        'architecture_role_assignments',
        'architecture_communities',
        'architecture_value_metrics',
        'architecture_value_observations'
    ];
    append_only_tables text[] := ARRAY[
        'business_capability_versions',
        'value_stream_versions',
        'architecture_element_versions',
        'architecture_relationship_versions',
        'architecture_viewpoints',
        'application_versions',
        'application_usage_observations',
        'application_cost_observations',
        'application_lifecycle_decisions',
        'technology_versions',
        'technology_usage_observations',
        'technology_lifecycle_decisions',
        'architecture_standard_versions',
        'architecture_exception_reviews',
        'architecture_evaluation_results',
        'benefit_observations',
        'portfolio_decisions',
        'architecture_roadmap_versions',
        'architecture_decisions',
        'architecture_reviews',
        'architecture_review_findings',
        'architecture_conformance_runs',
        'architecture_drift_findings',
        'architecture_value_observations'
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
                'CREATE TRIGGER batch_26_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
                target_schema, table_name);
        END IF;
    END LOOP;
END;
$$;
