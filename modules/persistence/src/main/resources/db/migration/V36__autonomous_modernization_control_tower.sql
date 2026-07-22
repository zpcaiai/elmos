-- ELMOS Product Batch 30: autonomous modernization control tower.
-- Records are evidence-bound and append-only. This schema does not execute external actions.

CREATE SCHEMA IF NOT EXISTS autonomous_control_tower;

DO $$
DECLARE
    target_schema text := 'autonomous_control_tower';
    table_name text;
    batch_tables text[] := ARRAY[
        'enterprise_entities',
        'enterprise_entity_versions',
        'entity_identities',
        'entity_aliases',
        'identity_resolution_candidates',
        'identity_resolution_decisions',
        'enterprise_relationships',
        'enterprise_relationship_versions',
        'claims',
        'claim_versions',
        'claim_conflicts',
        'evidence_records',
        'evidence_artifacts',
        'evidence_sources',
        'provenance_activities',
        'provenance_agents',
        'provenance_relations',
        'temporal_facts',
        'graph_snapshots',
        'graph_snapshot_members',
        'knowledge_graph_partitions',
        'graph_reconciliation_runs',
        'enterprise_twins',
        'enterprise_twin_versions',
        'twin_snapshots',
        'twin_states',
        'twin_state_authorities',
        'twin_drifts',
        'twin_conflicts',
        'enterprise_goals',
        'enterprise_objectives',
        'planning_constraints',
        'planning_resources',
        'planning_resource_allocations',
        'autonomous_plans',
        'autonomous_plan_versions',
        'plan_alternatives',
        'plan_steps',
        'plan_dependencies',
        'plan_assumptions',
        'plan_risks',
        'plan_decisions',
        'scenarios',
        'scenario_versions',
        'simulation_models',
        'simulation_model_versions',
        'simulation_runs',
        'simulation_parameters',
        'simulation_results',
        'counterfactuals',
        'workflow_definitions',
        'workflow_versions',
        'workflow_instances',
        'workflow_steps',
        'workflow_step_runs',
        'workflow_leases',
        'workflow_checkpoints',
        'workflow_signals',
        'workflow_timers',
        'sagas',
        'saga_steps',
        'saga_compensations',
        'execution_receipts',
        'execution_reconciliations',
        'manual_recovery_tasks',
        'agents',
        'agent_versions',
        'agent_cards',
        'agent_capabilities',
        'agent_endpoints',
        'agent_runtimes',
        'agent_tasks',
        'agent_task_runs',
        'tools',
        'tool_versions',
        'tool_contracts',
        'tool_permissions',
        'tool_invocations',
        'tool_invocation_results',
        'delegations',
        'delegated_authorities',
        'agent_budgets',
        'agent_budget_usage',
        'agent_kill_switches',
        'agent_kill_events',
        'policies',
        'policy_versions',
        'policy_bundles',
        'policy_decisions',
        'policy_inputs',
        'policy_exceptions',
        'policy_conflicts',
        'policy_simulation_runs',
        'human_decisions',
        'decision_packages',
        'approvals',
        'approval_conditions',
        'approval_expirations',
        'escalations',
        'decision_overrides',
        'enterprise_outcomes',
        'enterprise_benefits',
        'enterprise_cost_observations',
        'enterprise_risk_observations',
        'value_hypotheses',
        'value_observations',
        'value_realization_results',
        'control_tower_views',
        'control_tower_actions',
        'control_tower_incidents',
        'platform_health_snapshots',
        'data_freshness_results',
        'unified_traces',
        'unified_spans',
        'agent_traces',
        'workflow_traces',
        'execution_traces',
        'audit_events',
        'audit_anchors',
        'tenants',
        'trust_domains',
        'workload_identities',
        'encryption_domains',
        'residency_policies',
        'tenant_isolation_results',
        'platform_releases',
        'platform_component_versions',
        'platform_compatibility_matrices',
        'disaster_recovery_plans',
        'disaster_recovery_runs',
        'chaos_experiments',
        'platform_upgrade_runs'
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
