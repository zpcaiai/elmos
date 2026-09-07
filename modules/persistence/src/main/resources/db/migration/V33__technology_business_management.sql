-- ELMOS Product Batch 27: technology business management and investment governance.
-- Records are evidence-bound and append-only. This schema does not execute external actions.

CREATE SCHEMA IF NOT EXISTS technology_business_management;

DO $$
DECLARE
    target_schema text := 'technology_business_management';
    table_name text;
    batch_tables text[] := ARRAY[
        'tbm_estates',
        'financial_periods',
        'currency_profiles',
        'cost_sources',
        'technology_cost_records',
        'technology_usage_records',
        'labor_cost_records',
        'vendor_cost_records',
        'tbm_taxonomies',
        'tbm_taxonomy_versions',
        'tbm_cost_pools',
        'tbm_resource_towers',
        'tbm_resource_subtowers',
        'tbm_solutions',
        'tbm_consumers',
        'tbm_taxonomy_mappings',
        'allocation_models',
        'allocation_model_versions',
        'allocation_rules',
        'allocation_drivers',
        'allocation_runs',
        'allocation_results',
        'shared_cost_pools',
        'unallocated_cost_records',
        'digital_products',
        'digital_product_versions',
        'digital_product_owners',
        'digital_product_customers',
        'digital_product_outcomes',
        'digital_product_lifecycle_events',
        'platform_products',
        'technical_services',
        'business_services',
        'product_service_relationships',
        'funding_envelopes',
        'funding_periods',
        'funding_decisions',
        'funding_allocations',
        'funding_reallocations',
        'funding_conditions',
        'budgets',
        'budget_versions',
        'forecasts',
        'forecast_versions',
        'actual_costs',
        'financial_commitments',
        'budget_variances',
        'financial_scenarios',
        'scenario_results',
        'product_costs',
        'product_tco_snapshots',
        'cost_to_serve_metrics',
        'unit_metric_definitions',
        'unit_metric_observations',
        'unit_economic_results',
        'contribution_metrics',
        'showback_statements',
        'chargeback_rules',
        'chargeback_statements',
        'transfer_allocations',
        'chargeback_disputes',
        'vendors',
        'vendor_products',
        'vendor_contracts',
        'vendor_contract_versions',
        'contract_terms',
        'price_schedules',
        'contract_commitments',
        'vendor_entitlements',
        'license_positions',
        'contract_renewal_decisions',
        'capitalization_policies',
        'capitalization_policy_versions',
        'capitalization_candidates',
        'capitalizable_activities',
        'expense_activities',
        'capitalization_evidence',
        'accounting_reviews',
        'capitalization_adjustments',
        'benefit_hypotheses',
        'benefit_baselines',
        'benefit_targets',
        'benefit_observations',
        'benefit_attributions',
        'benefit_realization_results',
        'benefit_adjustments',
        'technical_debt_items',
        'technical_debt_exposures',
        'technical_debt_cost_ranges',
        'technical_debt_risk_impacts',
        'technical_debt_remediation_options',
        'technical_debt_outcomes',
        'investment_initiatives',
        'investment_options',
        'investment_portfolios',
        'portfolio_constraints',
        'portfolio_decisions',
        'portfolio_capacity_allocations',
        'product_value_scorecards',
        'technology_value_metrics',
        'tbm_controls',
        'tbm_control_results',
        'financial_reconciliations',
        'tbm_audit_events'
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
