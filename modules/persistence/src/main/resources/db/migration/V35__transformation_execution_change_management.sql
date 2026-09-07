-- ELMOS Product Batch 29: enterprise transformation execution and change management.
-- Records are evidence-bound and append-only. This schema does not execute external actions.

CREATE SCHEMA IF NOT EXISTS transformation_execution;

DO $$
DECLARE
    target_schema text := 'transformation_execution';
    table_name text;
    batch_tables text[] := ARRAY[
        'transformation_estates',
        'transformations',
        'transformation_versions',
        'transformation_portfolios',
        'transformation_programmes',
        'transformation_initiatives',
        'strategic_themes',
        'strategic_objectives',
        'strategic_outcomes',
        'outcome_metrics',
        'outcome_initiative_links',
        'transformation_offices',
        'transformation_governance_profiles',
        'governance_forums',
        'governance_cadences',
        'transformation_roles',
        'transformation_role_assignments',
        'portfolio_dependencies',
        'dependency_commitments',
        'dependency_milestones',
        'dependency_observations',
        'critical_paths',
        'portfolio_integration_points',
        'change_portfolios',
        'change_initiatives',
        'impacted_cohorts',
        'change_demands',
        'change_capacities',
        'change_capacity_observations',
        'change_collisions',
        'change_saturation_results',
        'stakeholders',
        'stakeholder_roles',
        'stakeholder_positions',
        'stakeholder_concerns',
        'stakeholder_engagement_plans',
        'stakeholder_engagement_observations',
        'stakeholder_decision_rights',
        'change_impacts',
        'role_impacts',
        'task_impacts',
        'process_impacts',
        'system_impacts',
        'data_impacts',
        'control_impacts',
        'location_impacts',
        'change_impact_versions',
        'communication_plans',
        'communication_audiences',
        'communication_messages',
        'communication_channels',
        'communication_deliveries',
        'communication_effectiveness_results',
        'transformation_feedback',
        'adoption_profiles',
        'readiness_assessments',
        'adoption_observations',
        'utilization_observations',
        'proficiency_assessments',
        'sustainment_observations',
        'adoption_regressions',
        'resistance_records',
        'transformation_concerns',
        'transformation_barriers',
        'resistance_responses',
        'concern_resolutions',
        'sponsors',
        'sponsor_coalitions',
        'sponsor_commitments',
        'sponsor_activities',
        'change_champions',
        'change_networks',
        'change_network_activities',
        'transformation_risks',
        'transformation_issues',
        'transformation_assumptions',
        'transformation_decisions',
        'transformation_decision_options',
        'transformation_escalations',
        'transformation_impediments',
        'transformation_waves',
        'business_readiness_profiles',
        'business_readiness_results',
        'transformation_cutover_plans',
        'transformation_cutover_steps',
        'hypercare_plans',
        'hypercare_issues',
        'hypercare_exit_decisions',
        'transformation_benefits',
        'transformation_benefit_owners',
        'transformation_benefit_baselines',
        'transformation_benefit_targets',
        'transformation_benefit_observations',
        'transformation_benefit_results',
        'transformation_health_profiles',
        'transformation_health_snapshots',
        'transformation_leading_indicators',
        'transformation_lagging_indicators',
        'transformation_forecasts',
        'transformation_learnings',
        'transformation_adaptation_decisions',
        'capability_transfer_plans',
        'transformation_closures',
        'transformation_closure_actions'
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
