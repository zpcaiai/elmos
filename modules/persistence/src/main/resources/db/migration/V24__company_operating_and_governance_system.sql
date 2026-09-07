-- ELMOS authoritative company-series Batch 15: Company Operating and Governance System.
-- The dedicated schema preserves canonical logical names without colliding with earlier technical batches.
-- This migration stores tenant-scoped observations and decisions; it executes no external business action.

CREATE SCHEMA IF NOT EXISTS company_ops;

DO $$
DECLARE
    target_schema text := 'company_ops';
    table_name text;
    batch_tables text[] := ARRAY[
        'company_profiles',
        'missions',
        'visions',
        'operating_principles',
        'strategic_diagnoses',
        'strategic_issues',
        'strategic_scenarios',
        'strategic_plans',
        'strategic_choices',
        'annual_priorities',
        'strategic_initiatives',
        'portfolio_items',
        'investment_proposals',
        'objectives',
        'key_results',
        'okr_alignments',
        'okr_updates',
        'quarterly_plans',
        'operating_reviews',
        'decision_logs',
        'action_items',
        'organization_units',
        'teams',
        'team_charters',
        'roles',
        'role_charters',
        'decision_rights',
        'headcount_plans',
        'job_families',
        'job_levels',
        'competencies',
        'requisitions',
        'candidates',
        'interviews',
        'hiring_scorecards',
        'offers',
        'employees',
        'onboarding_plans',
        'performance_reviews',
        'promotion_cases',
        'compensation_records',
        'equity_grants',
        'succession_plans',
        'engagement_surveys',
        'financial_assumptions',
        'financial_model_versions',
        'revenue_plans',
        'expense_plans',
        'cash_forecasts',
        'budgets',
        'forecasts',
        'actuals',
        'variance_analyses',
        'unit_economics',
        'capital_allocations',
        'fundraising_plans',
        'investors',
        'investor_interactions',
        'fundraising_rounds',
        'data_room_documents',
        'due_diligence_questions',
        'funding_scenarios',
        'cap_table_entries',
        'equity_events',
        'term_sheets',
        'closings',
        'investor_updates',
        'governance_documents',
        'authority_rules',
        'policies',
        'controls',
        'control_evidence',
        'enterprise_risks',
        'risk_treatments',
        'crisis_plans',
        'continuity_tests',
        'board_members',
        'board_committees',
        'board_calendars',
        'board_meetings',
        'board_materials',
        'board_resolutions',
        'board_minutes',
        'board_actions',
        'company_metrics',
        'executive_dashboards',
        'operating_cycles',
        'operating_playbooks'
    ];
    append_only_tables text[] := ARRAY[
        'decision_logs',
        'okr_updates',
        'operating_reviews',
        'actuals',
        'variance_analyses',
        'investor_interactions',
        'equity_events',
        'control_evidence',
        'board_resolutions',
        'board_minutes',
        'board_actions'
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
