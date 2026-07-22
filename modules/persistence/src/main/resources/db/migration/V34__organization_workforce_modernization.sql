-- ELMOS Product Batch 28: organization capability and workforce modernization.
-- Records are evidence-bound and append-only. This schema does not execute external actions.

CREATE SCHEMA IF NOT EXISTS organization_workforce;

DO $$
DECLARE
    target_schema text := 'organization_workforce';
    table_name text;
    batch_tables text[] := ARRAY[
        'organization_estates',
        'organization_units',
        'organization_unit_versions',
        'organization_relationships',
        'organization_cost_centers',
        'organization_locations',
        'workforce_segments',
        'digital_product_organizations',
        'product_operating_models',
        'product_operating_model_versions',
        'value_stream_teams',
        'teams',
        'team_versions',
        'team_missions',
        'team_types',
        'team_interactions',
        'team_apis',
        'work_definitions',
        'work_definition_versions',
        'work_tasks',
        'work_task_versions',
        'work_responsibilities',
        'work_accountabilities',
        'decision_rights',
        'skill_ontologies',
        'skill_ontology_versions',
        'skills',
        'skill_versions',
        'skill_categories',
        'skill_relationships',
        'skill_proficiency_models',
        'skill_proficiency_levels',
        'skill_claims',
        'skill_evidence',
        'skill_assessments',
        'skill_requirements',
        'team_skill_coverage',
        'skill_evidence_consents',
        'job_families',
        'job_family_versions',
        'job_roles',
        'job_role_versions',
        'work_roles',
        'positions',
        'role_profiles',
        'role_assignments',
        'career_frameworks',
        'career_tracks',
        'career_levels',
        'career_level_expectations',
        'promotion_evidence',
        'career_transitions',
        'career_equivalencies',
        'workforce_demands',
        'workforce_demand_versions',
        'workforce_supplies',
        'capacity_allocations',
        'workforce_scenarios',
        'skill_gaps',
        'workforce_actions',
        'ai_augmented_roles',
        'ai_task_allocations',
        'human_oversight_policies',
        'ai_literacy_profiles',
        'ai_work_risk_assessments',
        'learning_paths',
        'learning_path_versions',
        'learning_modules',
        'practice_assignments',
        'learning_assessments',
        'learning_results',
        'capability_development_plans',
        'credentials',
        'credential_issuers',
        'credential_verifications',
        'credential_endorsements',
        'credential_revocations',
        'credential_expirations',
        'talent_profiles',
        'internal_opportunities',
        'talent_matches',
        'hiring_plans',
        'mobility_plans',
        'succession_plans',
        'succession_candidates',
        'key_person_risks',
        'knowledge_assets',
        'knowledge_asset_owners',
        'knowledge_coverage',
        'knowledge_transfer_runs',
        'continuity_exercises',
        'vendor_workforces',
        'vendor_roles',
        'vendor_skills',
        'vendor_resource_assignments',
        'vendor_continuity_plans',
        'knowledge_transfer_plans',
        'vendor_offboarding_runs',
        'team_health_profiles',
        'team_health_observations',
        'leadership_capabilities',
        'change_readiness_profiles',
        'change_cohorts',
        'workforce_transitions',
        'workforce_transition_appeals',
        'organization_outcomes',
        'organization_effectiveness_metrics',
        'transformation_hypotheses',
        'transformation_results',
        'organization_change_scorecards'
    ];
BEGIN
    FOREACH table_name IN ARRAY batch_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I.%I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES public.organizations(organization_id),' ||
            'domain_run_id varchar(160) NOT NULL,' ||
            'snapshot_digest varchar(64) NOT NULL CHECK (snapshot_digest ~ ''^[0-9a-f]{64}$''),' ||
            'policy_version varchar(96) NOT NULL,' ||
            'human_owner_id varchar(160) NOT NULL,' ||
            'status varchar(64) NOT NULL DEFAULT ''NOT_RUN'' CHECK (status IN (''OBSERVED'',''NOT_RUN'',''INCONCLUSIVE'',''BLOCKED'',''READY_FOR_HUMAN_DECISION'')),' ||
            'independent_judge boolean NOT NULL DEFAULT false,' ||
            'critical_open_risks integer NOT NULL DEFAULT 0 CHECK (critical_open_risks >= 0),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb CHECK (jsonb_typeof(evidence_refs) = ''array''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb CHECK (jsonb_typeof(payload) = ''object''),' ||
            'external_operation_executed boolean NOT NULL DEFAULT false CHECK (external_operation_executed = false),' ||
            'human_approval_ref varchar(512),' ||
            'idempotency_key varchar(160) NOT NULL,' ||
            'observed_at timestamptz NOT NULL,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'CHECK (status <> ''READY_FOR_HUMAN_DECISION'' OR (independent_judge AND critical_open_risks = 0 AND jsonb_array_length(evidence_refs) > 0)),' ||
            'CHECK (human_approval_ref IS NULL OR jsonb_array_length(evidence_refs) > 0),' ||
            'UNIQUE (organization_id, idempotency_key))',
            target_schema, table_name);
        EXECUTE format('CREATE INDEX %I ON %I.%I (organization_id, domain_run_id, status)',
                       'idx_' || left(table_name, 38) || '_roadmap_run', target_schema, table_name);
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', target_schema, table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', target_schema, table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I.%I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            target_schema, table_name);
        EXECUTE format(
            'CREATE TRIGGER product_governance_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
            target_schema, table_name);
    END LOOP;
END;
$$;
