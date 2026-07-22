-- ELMOS authoritative company-series Batch 17: Vertical Solution Factory.
-- The dedicated schema preserves canonical logical names without colliding with earlier technical batches.
-- This migration stores tenant-scoped observations and decisions; it executes no external business action.

CREATE SCHEMA IF NOT EXISTS vertical_solutions;

DO $$
DECLARE
    target_schema text := 'vertical_solutions';
    table_name text;
    batch_tables text[] := ARRAY[
        'vertical_solution_packs',
        'vertical_pack_versions',
        'industry_domain_models',
        'industry_entities',
        'industry_aggregates',
        'industry_workflows',
        'industry_state_machines',
        'industry_invariants',
        'industry_terminology',
        'industry_code_sets',
        'regulatory_controls',
        'jurisdiction_overlays',
        'control_crosswalks',
        'vertical_control_evidence',
        'industry_data_classifications',
        'industry_residency_rules',
        'industry_identity_roles',
        'industry_authorization_rules',
        'industry_events',
        'industry_api_contracts',
        'industry_recipes',
        'industry_recipe_versions',
        'industry_golden_cases',
        'industry_eval_cases',
        'industry_eval_runs',
        'industry_reference_architectures',
        'industry_deployment_profiles',
        'industry_slos',
        'industry_risks',
        'industry_safety_cases',
        'vertical_products',
        'vertical_entitlements',
        'vertical_prices',
        'vertical_poc_packs',
        'vertical_sow_templates',
        'vertical_partners',
        'vertical_certifications',
        'regional_vertical_launches',
        'vertical_marketplace_assets',
        'vertical_conformance_reports'
    ];
    append_only_tables text[] := ARRAY[
        'vertical_control_evidence',
        'industry_recipe_versions',
        'industry_eval_runs',
        'industry_safety_cases',
        'vertical_certifications',
        'vertical_conformance_reports'
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
