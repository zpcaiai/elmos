-- ELMOS authoritative company-series Batch 18: Group Integration Factory.
-- The dedicated schema preserves canonical logical names without colliding with earlier technical batches.
-- This migration stores tenant-scoped observations and decisions; it executes no external business action.

CREATE SCHEMA IF NOT EXISTS group_integration;

DO $$
DECLARE
    target_schema text := 'group_integration';
    table_name text;
    batch_tables text[] := ARRAY[
        'integration_programs',
        'deal_theses',
        'integration_archetypes',
        'clean_team_memberships',
        'clean_team_access_logs',
        'day_one_services',
        'day_one_rehearsals',
        'day_hundred_outcomes',
        'imo_workstreams',
        'group_applications',
        'group_repositories',
        'group_databases',
        'group_interfaces',
        'group_dependency_edges',
        'duplicate_system_candidates',
        'application_dispositions',
        'group_business_capabilities',
        'group_legal_entities',
        'transition_services',
        'integration_risks',
        'target_enterprise_architectures',
        'technology_standards',
        'technology_exceptions',
        'integration_waves',
        'migration_factory_capacity',
        'identity_estates',
        'person_account_matches',
        'identity_federations',
        'identity_cutovers',
        'group_data_domains',
        'group_canonical_models',
        'master_data_matches',
        'group_data_quality_results',
        'group_data_migrations',
        'group_data_reconciliations',
        'group_integration_interfaces',
        'integration_flow_observations',
        'tsa_exit_plans',
        'carve_out_perimeters',
        'standalone_validations',
        'synergy_baselines',
        'synergy_initiatives',
        'one_time_costs',
        'stranded_costs',
        'synergy_acceptances',
        'integration_raid_items',
        'integration_incidents',
        'business_readiness_acceptances',
        'legacy_retirement_plans',
        'legacy_retirement_evidence',
        'group_integration_reports'
    ];
    append_only_tables text[] := ARRAY[
        'clean_team_access_logs',
        'day_one_rehearsals',
        'person_account_matches',
        'group_data_quality_results',
        'group_data_reconciliations',
        'integration_flow_observations',
        'standalone_validations',
        'synergy_acceptances',
        'integration_incidents',
        'business_readiness_acceptances',
        'legacy_retirement_evidence',
        'group_integration_reports'
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
