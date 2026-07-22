-- ELMOS cross-language Batch 13: evidence projections for the enterprise commercial loop.
-- V10 remains authoritative for catalog, pricing, quotes, orders, subscriptions, entitlements,
-- delivery projects, support, customer success, marketplace and commercial economics.
-- CRM, CPQ, contract, billing, accounting, payment and partner-settlement execution remain external.

DO $$
DECLARE
    table_name text;
    commercial_loop_tables text[] := ARRAY[
        'commercial_leads','commercial_opportunities','commercial_activities','commercial_discoveries',
        'commercial_solution_assessments','commercial_portfolio_assessments','commercial_pocs',
        'commercial_poc_criteria','commercial_poc_results','commercial_stakeholders',
        'commercial_contract_assumptions','commercial_engagements','commercial_waves',
        'commercial_raid_items','commercial_resource_plans','commercial_time_entries',
        'commercial_cost_entries','commercial_deliverables','commercial_deliverable_versions',
        'commercial_acceptances','commercial_success_qbrs','commercial_customer_references',
        'commercial_partners','commercial_partner_contacts','commercial_partner_levels',
        'commercial_partner_certifications','commercial_partner_deals','commercial_partner_projects',
        'commercial_partner_quality_scores','commercial_partner_settlements',
        'commercial_capacity_forecasts','commercial_product_feedback','commercial_risks',
        'commercial_lifecycle_events','commercial_forecasts','commercial_value_realizations'
    ];
BEGIN
    FOREACH table_name IN ARRAY commercial_loop_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),' ||
            'commercial_account_ref varchar(255),' ||
            'opportunity_ref varchar(255),' ||
            'customer_tenant_ref varchar(255),' ||
            'owner_ref varchar(255) NOT NULL,' ||
            'source_system varchar(96) NOT NULL,' ||
            'source_record_ref varchar(512) NOT NULL,' ||
            'record_version varchar(64) NOT NULL,' ||
            'schema_version varchar(32) NOT NULL DEFAULT ''1.0'',' ||
            'status varchar(64) NOT NULL DEFAULT ''OBSERVED'',' ||
            'idempotency_key varchar(160) NOT NULL,' ||
            'observed_at timestamptz NOT NULL,' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb,' ||
            'content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ ''^[0-9a-f]{64}$''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'updated_at timestamptz NOT NULL DEFAULT now(),' ||
            'UNIQUE (organization_id, source_system, source_record_ref, record_version),' ||
            'UNIQUE (organization_id, idempotency_key))', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id)', 'idx_' || table_name || '_org', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id, commercial_account_ref)', 'idx_' || table_name || '_account', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id, opportunity_ref)', 'idx_' || table_name || '_opportunity', table_name);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name);
    END LOOP;
END;
$$;

ALTER TABLE commercial_leads
    ADD COLUMN qualification_stage varchar(64),
    ADD COLUMN fit_score numeric(6,5),
    ADD CONSTRAINT commercial_leads_fit_score_range CHECK (fit_score IS NULL OR (fit_score >= 0 AND fit_score <= 1));
ALTER TABLE commercial_opportunities
    ADD COLUMN lifecycle_stage varchar(64),
    ADD COLUMN motion varchar(64),
    ADD COLUMN amount numeric(20,4) CHECK (amount IS NULL OR amount >= 0),
    ADD COLUMN currency varchar(3),
    ADD COLUMN expected_close_date date,
    ADD COLUMN entry_criteria_satisfied boolean NOT NULL DEFAULT false,
    ADD COLUMN exit_criteria_satisfied boolean NOT NULL DEFAULT false;
ALTER TABLE commercial_discoveries
    ADD COLUMN discovery_coverage numeric(6,5),
    ADD COLUMN customer_owner_ref varchar(255),
    ADD CONSTRAINT commercial_discoveries_coverage_range CHECK (discovery_coverage IS NULL OR (discovery_coverage >= 0 AND discovery_coverage <= 1));
ALTER TABLE commercial_solution_assessments
    ADD COLUMN architecture_fit varchar(32),
    ADD COLUMN security_review_ref varchar(512),
    ADD COLUMN unsupported_commitments integer NOT NULL DEFAULT 0 CHECK (unsupported_commitments >= 0);
ALTER TABLE commercial_pocs
    ADD COLUMN scope_version varchar(64),
    ADD COLUMN budget_amount numeric(20,4) CHECK (budget_amount IS NULL OR budget_amount >= 0),
    ADD COLUMN criteria_predefined boolean NOT NULL DEFAULT false,
    ADD COLUMN customer_acceptance_ref varchar(512);
ALTER TABLE commercial_poc_criteria
    ADD COLUMN criterion_key varchar(160),
    ADD COLUMN measurement_method varchar(1024),
    ADD COLUMN acceptance_threshold varchar(512),
    ADD COLUMN approved_before_execution boolean NOT NULL DEFAULT false;
ALTER TABLE commercial_poc_results
    ADD COLUMN criterion_ref varchar(255),
    ADD COLUMN result_status varchar(32),
    ADD COLUMN failure_preserved boolean NOT NULL DEFAULT true;
ALTER TABLE commercial_contract_assumptions
    ADD COLUMN contract_ref varchar(255),
    ADD COLUMN assumption_type varchar(64),
    ADD COLUMN due_at timestamptz,
    ADD COLUMN impact varchar(1024);
ALTER TABLE commercial_engagements
    ADD COLUMN contract_ref varchar(255),
    ADD COLUMN delivery_motion varchar(64),
    ADD COLUMN baseline_approved boolean NOT NULL DEFAULT false;
ALTER TABLE commercial_waves
    ADD COLUMN engagement_ref varchar(255),
    ADD COLUMN sequence_number integer CHECK (sequence_number IS NULL OR sequence_number >= 0),
    ADD COLUMN entry_criteria jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN exit_criteria jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE commercial_raid_items
    ADD COLUMN raid_type varchar(16),
    ADD COLUMN severity varchar(32),
    ADD COLUMN due_at timestamptz,
    ADD COLUMN closed_evidence_ref varchar(512);
ALTER TABLE commercial_cost_entries
    ADD COLUMN project_ref varchar(255),
    ADD COLUMN cost_type varchar(64),
    ADD COLUMN amount numeric(20,4) NOT NULL DEFAULT 0 CHECK (amount >= 0),
    ADD COLUMN currency varchar(3);
ALTER TABLE commercial_acceptances
    ADD COLUMN deliverable_ref varchar(255),
    ADD COLUMN milestone_ref varchar(255),
    ADD COLUMN acceptance_authority_ref varchar(255),
    ADD COLUMN accepted_at timestamptz,
    ADD COLUMN billing_authorized boolean NOT NULL DEFAULT false;
ALTER TABLE commercial_partners
    ADD COLUMN partner_type varchar(64),
    ADD COLUMN program_level_ref varchar(255),
    ADD COLUMN due_diligence_status varchar(64);
ALTER TABLE commercial_partner_certifications
    ADD COLUMN certification_type varchar(96),
    ADD COLUMN effective_at timestamptz,
    ADD COLUMN expires_at timestamptz,
    ADD COLUMN authorized_scope jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE commercial_partner_settlements
    ADD COLUMN settlement_period_start date,
    ADD COLUMN settlement_period_end date,
    ADD COLUMN currency varchar(3),
    ADD COLUMN eligible_revenue numeric(20,4) CHECK (eligible_revenue IS NULL OR eligible_revenue >= 0),
    ADD COLUMN settlement_amount numeric(20,4),
    ADD COLUMN reconciliation_status varchar(64);
ALTER TABLE commercial_forecasts
    ADD COLUMN forecast_period_start date,
    ADD COLUMN forecast_period_end date,
    ADD COLUMN forecast_category varchar(64),
    ADD COLUMN forecast_amount numeric(20,4) CHECK (forecast_amount IS NULL OR forecast_amount >= 0),
    ADD COLUMN currency varchar(3),
    ADD COLUMN confidence numeric(6,5),
    ADD CONSTRAINT commercial_forecasts_confidence_range CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1));
ALTER TABLE commercial_capacity_forecasts
    ADD COLUMN skill_key varchar(160),
    ADD COLUMN period_start date,
    ADD COLUMN period_end date,
    ADD COLUMN demand_hours numeric(20,4) CHECK (demand_hours IS NULL OR demand_hours >= 0),
    ADD COLUMN capacity_hours numeric(20,4) CHECK (capacity_hours IS NULL OR capacity_hours >= 0);
ALTER TABLE commercial_value_realizations
    ADD COLUMN baseline_ref varchar(512),
    ADD COLUMN metric_key varchar(160),
    ADD COLUMN baseline_value numeric(24,8),
    ADD COLUMN observed_value numeric(24,8),
    ADD COLUMN customer_acknowledgement_ref varchar(512);

CREATE TRIGGER commercial_lifecycle_events_append_only BEFORE UPDATE OR DELETE ON commercial_lifecycle_events FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER commercial_poc_results_append_only BEFORE UPDATE OR DELETE ON commercial_poc_results FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER commercial_deliverable_versions_append_only BEFORE UPDATE OR DELETE ON commercial_deliverable_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER commercial_acceptances_append_only BEFORE UPDATE OR DELETE ON commercial_acceptances FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER commercial_partner_quality_scores_append_only BEFORE UPDATE OR DELETE ON commercial_partner_quality_scores FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER commercial_partner_settlements_append_only BEFORE UPDATE OR DELETE ON commercial_partner_settlements FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER commercial_forecasts_append_only BEFORE UPDATE OR DELETE ON commercial_forecasts FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER commercial_capacity_forecasts_append_only BEFORE UPDATE OR DELETE ON commercial_capacity_forecasts FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER commercial_value_realizations_append_only BEFORE UPDATE OR DELETE ON commercial_value_realizations FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
