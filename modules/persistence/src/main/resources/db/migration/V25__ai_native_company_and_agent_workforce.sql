-- ELMOS authoritative company-series Batch 16: AI-native company and Agent Workforce.
-- The dedicated schema preserves canonical logical names without colliding with earlier technical batches.
-- This migration stores tenant-scoped observations and decisions; it executes no external business action.

CREATE SCHEMA IF NOT EXISTS agent_workforce;

DO $$
DECLARE
    target_schema text := 'agent_workforce';
    table_name text;
    batch_tables text[] := ARRAY[
        'ai_strategies',
        'ai_operating_principles',
        'ai_use_cases',
        'ai_assets',
        'ai_risk_profiles',
        'work_processes',
        'work_tasks',
        'work_decisions',
        'automation_assessments',
        'role_decompositions',
        'redesigned_roles',
        'human_agent_matrices',
        'agent_portfolios',
        'agent_teams',
        'agent_definitions',
        'agent_charters',
        'agent_versions',
        'agent_lifecycle_events',
        'agent_owners',
        'agent_authority_envelopes',
        'agent_identities',
        'agent_credentials',
        'agent_jobs',
        'agent_job_leases',
        'agent_plans',
        'agent_steps',
        'agent_actions',
        'agent_observations',
        'agent_exceptions',
        'agent_escalations',
        'agent_handoffs',
        'agent_rollbacks',
        'agent_memories',
        'memory_sources',
        'memory_corrections',
        'knowledge_nodes',
        'knowledge_edges',
        'tool_registry',
        'tool_versions',
        'tool_permissions',
        'action_policies',
        'policy_decisions',
        'agent_evaluations',
        'eval_suites',
        'eval_cases',
        'eval_runs',
        'shadow_runs',
        'red_team_runs',
        'drift_events',
        'agent_incidents',
        'model_registry',
        'model_versions',
        'model_deployments',
        'model_risk_profiles',
        'model_evaluations',
        'model_provider_risks',
        'prompt_assets',
        'prompt_versions',
        'context_manifests',
        'model_calls',
        'output_validations',
        'agent_metrics',
        'agent_scorecards',
        'agent_costs',
        'agent_budgets',
        'agent_value_reviews',
        'workforce_transitions',
        'ai_training_programs',
        'ai_certifications',
        'employee_ai_feedback',
        'ai_appeals',
        'ai_governance_policies',
        'ai_constitution_versions',
        'ai_management_reviews',
        'ai_audits',
        'ai_board_reports'
    ];
    append_only_tables text[] := ARRAY[
        'agent_lifecycle_events',
        'agent_actions',
        'agent_observations',
        'policy_decisions',
        'eval_runs',
        'shadow_runs',
        'red_team_runs',
        'drift_events',
        'agent_incidents',
        'model_calls',
        'output_validations',
        'agent_costs',
        'ai_audits'
    ];
BEGIN
    FOREACH table_name IN ARRAY batch_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I.%I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES public.organizations(organization_id),' ||
            'company_id varchar(96) NOT NULL,' ||
            'tenant_id varchar(96) NOT NULL,' ||
            'program_id varchar(160) NOT NULL,' ||
            'legal_entity_id varchar(160),' ||
            'region varchar(64),' ||
            'jurisdiction varchar(64),' ||
            'fiscal_period varchar(32),' ||
            'wave_id varchar(160),' ||
            'owner_id varchar(160) NOT NULL,' ||
            'human_owner_id varchar(160) NOT NULL,' ||
            'status varchar(64) NOT NULL DEFAULT ''OBSERVED'',' ||
            'version varchar(64) NOT NULL,' ||
            'approved_by varchar(160),' ||
            'confidentiality varchar(64) NOT NULL DEFAULT ''CONFIDENTIAL'',' ||
            'source varchar(160) NOT NULL,' ||
            'source_record_ref varchar(512) NOT NULL,' ||
            'idempotency_key varchar(160) NOT NULL,' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb,' ||
            'content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ ''^[0-9a-f]{64}$''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb,' ||
            'external_operation_executed boolean NOT NULL DEFAULT false CHECK (external_operation_executed = false),' ||
            'observed_at timestamptz NOT NULL,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'updated_at timestamptz NOT NULL DEFAULT now(),' ||
            'UNIQUE (organization_id, idempotency_key),' ||
            'UNIQUE (organization_id, source, source_record_ref, version))',
            target_schema, table_name);
        EXECUTE format('CREATE INDEX %I ON %I.%I (organization_id)',
                       'idx_' || table_name || '_organization', target_schema, table_name);
        EXECUTE format('CREATE INDEX %I ON %I.%I (organization_id, program_id, status)',
                       'idx_' || table_name || '_program', target_schema, table_name);
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', target_schema, table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', target_schema, table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I.%I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            target_schema, table_name);
        IF table_name = ANY(append_only_tables) THEN
            EXECUTE format(
                'CREATE TRIGGER company_series_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
                target_schema, table_name);
        END IF;
    END LOOP;
END;
$$;
