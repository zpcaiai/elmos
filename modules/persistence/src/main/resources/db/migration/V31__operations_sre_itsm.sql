-- ELMOS Skill Pack Batch 25. Generated from the authoritative attachment table inventory.
-- A dedicated namespace preserves logical names without stealing authority from earlier batch tables.
-- These tables record tenant-scoped evidence and decisions; they do not execute provider or production actions.

CREATE SCHEMA IF NOT EXISTS operations_sre;

DO $$
DECLARE
    target_schema text := 'operations_sre';
    table_name text;
    batch_tables text[] := ARRAY[
        'operations_estates',
        'business_services',
        'technical_services',
        'application_services',
        'service_instances',
        'service_offerings',
        'service_owners',
        'configuration_items',
        'configuration_item_versions',
        'assets',
        'configuration_baselines',
        'configuration_relationships',
        'cmdb_reconciliation_rules',
        'cmdb_reconciliation_results',
        'cmdb_staleness_findings',
        'service_topologies',
        'service_topology_versions',
        'service_dependencies',
        'dependency_observations',
        'business_impact_paths',
        'operational_events',
        'normalized_events',
        'event_correlations',
        'event_correlation_members',
        'alerts',
        'alert_policies',
        'alert_policy_versions',
        'alert_routes',
        'alert_suppressions',
        'alert_notifications',
        'incidents',
        'major_incidents',
        'incident_roles',
        'incident_role_assignments',
        'incident_timelines',
        'incident_impacts',
        'incident_actions',
        'incident_communications',
        'incident_handoffs',
        'problems',
        'root_cause_hypotheses',
        'root_cause_evidence',
        'known_errors',
        'known_error_workarounds',
        'postmortems',
        'postmortem_actions',
        'changes',
        'change_types',
        'change_risk_assessments',
        'change_windows',
        'change_approvals',
        'change_executions',
        'change_verifications',
        'change_failures',
        'service_level_indicators',
        'service_level_objectives',
        'slo_measurements',
        'error_budgets',
        'error_budget_policies',
        'error_budget_burns',
        'service_level_agreements',
        'oncall_rotations',
        'oncall_shifts',
        'oncall_participants',
        'escalation_policies',
        'escalation_steps',
        'oncall_handoffs',
        'operational_load_observations',
        'runbooks',
        'runbook_versions',
        'runbook_steps',
        'diagnostic_procedures',
        'runbook_executions',
        'runbook_validation_results',
        'aiops_analyses',
        'aiops_anomalies',
        'event_clusters',
        'causal_hypotheses',
        'similar_incident_matches',
        'aiops_recommendations',
        'remediation_policies',
        'remediation_actions',
        'remediation_runs',
        'remediation_verifications',
        'remediation_rollbacks',
        'capacity_resources',
        'capacity_demand_observations',
        'capacity_forecasts',
        'capacity_thresholds',
        'saturation_risks',
        'capacity_plans',
        'business_impact_analyses',
        'continuity_plans',
        'continuity_strategies',
        'crises',
        'crisis_roles',
        'recovery_exercises',
        'continuity_exercise_results',
        'service_request_offerings',
        'service_requests',
        'service_request_steps',
        'operational_workflows',
        'operations_dashboards',
        'operations_dashboard_views',
        'business_impact_views',
        'operations_metrics',
        'toil_records',
        'improvement_initiatives'
    ];
    append_only_tables text[] := ARRAY[
        'configuration_item_versions',
        'cmdb_reconciliation_results',
        'cmdb_staleness_findings',
        'service_topology_versions',
        'dependency_observations',
        'operational_events',
        'normalized_events',
        'alert_policy_versions',
        'incident_timelines',
        'incident_communications',
        'incident_handoffs',
        'change_approvals',
        'change_executions',
        'slo_measurements',
        'oncall_handoffs',
        'operational_load_observations',
        'runbook_versions',
        'runbook_executions',
        'runbook_validation_results',
        'remediation_runs',
        'capacity_demand_observations',
        'continuity_exercise_results',
        'toil_records'
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
                'CREATE TRIGGER batch_25_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
                target_schema, table_name);
        END IF;
    END LOOP;
END;
$$;
