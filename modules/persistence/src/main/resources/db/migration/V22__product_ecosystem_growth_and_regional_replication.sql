-- ELMOS cross-language Batch 14: evidence projections for the authoritative PEGM contract.
-- V10 remains authoritative for Marketplace and commercial execution. V20 remains authoritative
-- for the Batch 13 commercial loop. This migration stores observations and decisions only.

DO $$
DECLARE
    table_name text;
    batch14_tables text[] := ARRAY[
        'growth_programs','growth_goals','north_star_metrics','metric_definitions',
        'growth_events','identity_links','funnels','journeys','experiments',
        'experiment_variants','experiment_assignments','experiment_results',

        'channels','campaigns','touchpoints','attribution_models','attribution_results',

        'content_pillars','content_topics','content_assets','content_versions',
        'content_reviews','seo_keywords','seo_pages','events','event_attendees',

        'developer_profiles','api_applications','sdk_usage','cli_usage',
        'sample_repositories','sandbox_sessions',

        'community_spaces','community_members','community_posts','community_answers',
        'community_reputation','community_badges','moderation_cases','community_events',

        'marketplace_publishers','marketplace_assets','asset_versions','asset_certifications',
        'asset_installations','asset_usage','asset_reviews','asset_reports',
        'marketplace_orders','publisher_payouts','marketplace_bounties',

        'locales','translation_keys','translations','translation_memories',
        'terminology','localization_projects','regional_requirements',

        'regions','regional_launches','regional_prices','regional_partners',
        'regional_campaigns','regional_metrics',

        'growth_playbooks','growth_learnings','growth_risks','growth_costs','growth_economics'
    ];
BEGIN
    FOREACH table_name IN ARRAY batch14_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),' ||
            'tenant_scope varchar(255) NOT NULL,' ||
            'region varchar(32),' ||
            'locale varchar(64),' ||
            'persona varchar(96),' ||
            'channel varchar(96),' ||
            'campaign varchar(160),' ||
            'source varchar(96) NOT NULL,' ||
            'consent varchar(64) NOT NULL,' ||
            'owner_ref varchar(255) NOT NULL,' ||
            'source_record_ref varchar(512) NOT NULL,' ||
            'schema_version varchar(32) NOT NULL DEFAULT ''1.0'',' ||
            'policy_version varchar(64) NOT NULL,' ||
            'status varchar(64) NOT NULL DEFAULT ''OBSERVED'',' ||
            'idempotency_key varchar(160) NOT NULL,' ||
            'observed_at timestamptz NOT NULL,' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb,' ||
            'content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ ''^[0-9a-f]{64}$''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb,' ||
            'external_operation_executed boolean NOT NULL DEFAULT false CHECK (external_operation_executed = false),' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'UNIQUE (organization_id, source, source_record_ref, schema_version),' ||
            'UNIQUE (organization_id, idempotency_key))', table_name);
        EXECUTE format('CREATE INDEX ON %I (organization_id)', table_name);
        EXECUTE format('CREATE INDEX ON %I (organization_id, region, locale)', table_name);
        EXECUTE format('CREATE INDEX ON %I (organization_id, persona, channel, campaign)', table_name);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name);
    END LOOP;
END;
$$;

ALTER TABLE growth_programs
    ADD COLUMN target_segments jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN target_regions jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN product_motions jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN primary_goals jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE north_star_metrics
    ADD COLUMN metric_id varchar(160),
    ADD COLUMN definition text,
    ADD COLUMN grain varchar(96),
    ADD COLUMN numerator text,
    ADD COLUMN denominator text,
    ADD COLUMN exclusions jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN driver_metric_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN guardrail_metric_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN customer_value_bound boolean NOT NULL DEFAULT false,
    ADD COLUMN quality_gate_required boolean NOT NULL DEFAULT false;

ALTER TABLE growth_events
    ADD COLUMN event_id varchar(160),
    ADD COLUMN actor_id varchar(255),
    ADD COLUMN anonymous_id varchar(255),
    ADD COLUMN event_name varchar(255),
    ADD COLUMN properties jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN occurred_at timestamptz,
    ADD COLUMN event_schema_version integer CHECK (event_schema_version IS NULL OR event_schema_version >= 1);

ALTER TABLE experiments
    ADD COLUMN experiment_id varchar(160),
    ADD COLUMN hypothesis text,
    ADD COLUMN population varchar(160),
    ADD COLUMN primary_metric varchar(160),
    ADD COLUMN guardrails jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN assignment_unit varchar(32);

ALTER TABLE experiment_results
    ADD COLUMN decision varchar(32),
    ADD COLUMN effect_size numeric(24,10),
    ADD COLUMN confidence_or_posterior jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN negative_result_preserved boolean NOT NULL DEFAULT true;

ALTER TABLE content_assets
    ADD COLUMN content_id varchar(160),
    ADD COLUMN content_type varchar(64),
    ADD COLUMN funnel_stage varchar(64),
    ADD COLUMN source_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN technical_reviewer varchar(255),
    ADD COLUMN customer_authorization_ref varchar(512);

ALTER TABLE community_spaces
    ADD COLUMN visibility varchar(32),
    ADD COLUMN data_classification varchar(32),
    ADD COLUMN posting_roles jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN moderation_policy_ref varchar(512);

ALTER TABLE moderation_cases
    ADD COLUMN case_type varchar(64),
    ADD COLUMN moderation_action varchar(64),
    ADD COLUMN appeal_status varchar(32),
    ADD COLUMN decision_authority_ref varchar(255);

ALTER TABLE marketplace_publishers
    ADD COLUMN publisher_id varchar(255),
    ADD COLUMN verification varchar(64),
    ADD COLUMN supported_regions jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN support_contact varchar(255),
    ADD COLUMN payout_account_ref varchar(512);

ALTER TABLE marketplace_assets
    ADD COLUMN asset_id varchar(255),
    ADD COLUMN publisher_id varchar(255),
    ADD COLUMN asset_type varchar(64),
    ADD COLUMN version_range varchar(255),
    ADD COLUMN provenance_ref varchar(512),
    ADD COLUMN license_ref varchar(255),
    ADD COLUMN support_policy_ref varchar(512),
    ADD COLUMN upgrade_policy_ref varchar(512),
    ADD COLUMN rollback_policy_ref varchar(512);

ALTER TABLE asset_certifications
    ADD COLUMN certification_level varchar(64),
    ADD COLUMN parse_status varchar(32),
    ADD COLUMN test_status varchar(32),
    ADD COLUMN security_status varchar(32),
    ADD COLUMN license_status varchar(32),
    ADD COLUMN sandbox_status varchar(32),
    ADD COLUMN documentation_status varchar(32);

ALTER TABLE asset_installations
    ADD COLUMN asset_id varchar(255),
    ADD COLUMN asset_version varchar(64),
    ADD COLUMN dependencies jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN permissions jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN conflicts jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN rollback_plan jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE translations
    ADD COLUMN translation_key varchar(255),
    ADD COLUMN source_version varchar(64),
    ADD COLUMN translation_status varchar(32),
    ADD COLUMN human_reviewed boolean NOT NULL DEFAULT false;

ALTER TABLE terminology
    ADD COLUMN source_term varchar(255),
    ADD COLUMN approved_translation varchar(512),
    ADD COLUMN forbidden_translations jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN term_context varchar(255);

ALTER TABLE regional_requirements
    ADD COLUMN requirement text,
    ADD COLUMN affected_components jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN mandatory boolean NOT NULL DEFAULT true,
    ADD COLUMN approval_evidence jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE regional_prices
    ADD COLUMN sku varchar(160),
    ADD COLUMN currency varchar(3),
    ADD COLUMN amount numeric(20,4) CHECK (amount IS NULL OR amount >= 0),
    ADD COLUMN valid_from timestamptz;

ALTER TABLE regions
    ADD COLUMN opportunity_score numeric(8,5) CHECK (opportunity_score IS NULL OR opportunity_score BETWEEN 0 AND 100),
    ADD COLUMN product_readiness_score numeric(8,5) CHECK (product_readiness_score IS NULL OR product_readiness_score BETWEEN 0 AND 100),
    ADD COLUMN channel_readiness_score numeric(8,5) CHECK (channel_readiness_score IS NULL OR channel_readiness_score BETWEEN 0 AND 100),
    ADD COLUMN compliance_readiness_score numeric(8,5) CHECK (compliance_readiness_score IS NULL OR compliance_readiness_score BETWEEN 0 AND 100),
    ADD COLUMN entry_mode varchar(64);

ALTER TABLE growth_risks
    ADD COLUMN risk_type varchar(96),
    ADD COLUMN critical boolean NOT NULL DEFAULT false,
    ADD COLUMN stop_condition text,
    ADD COLUMN resolved_at timestamptz;

ALTER TABLE growth_economics
    ADD COLUMN cac numeric(20,4) CHECK (cac IS NULL OR cac >= 0),
    ADD COLUMN ltv numeric(20,4) CHECK (ltv IS NULL OR ltv >= 0),
    ADD COLUMN payback_months numeric(12,4) CHECK (payback_months IS NULL OR payback_months >= 0),
    ADD COLUMN contribution_margin numeric(12,8);

CREATE TRIGGER batch14_growth_events_append_only
    BEFORE UPDATE OR DELETE ON growth_events
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_identity_links_append_only
    BEFORE UPDATE OR DELETE ON identity_links
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_experiment_assignments_append_only
    BEFORE UPDATE OR DELETE ON experiment_assignments
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_experiment_results_append_only
    BEFORE UPDATE OR DELETE ON experiment_results
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_attribution_results_append_only
    BEFORE UPDATE OR DELETE ON attribution_results
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_content_reviews_append_only
    BEFORE UPDATE OR DELETE ON content_reviews
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_community_reputation_append_only
    BEFORE UPDATE OR DELETE ON community_reputation
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_moderation_cases_append_only
    BEFORE UPDATE OR DELETE ON moderation_cases
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_asset_certifications_append_only
    BEFORE UPDATE OR DELETE ON asset_certifications
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_asset_usage_append_only
    BEFORE UPDATE OR DELETE ON asset_usage
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_asset_reviews_append_only
    BEFORE UPDATE OR DELETE ON asset_reviews
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_asset_reports_append_only
    BEFORE UPDATE OR DELETE ON asset_reports
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_marketplace_orders_append_only
    BEFORE UPDATE OR DELETE ON marketplace_orders
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_publisher_payouts_append_only
    BEFORE UPDATE OR DELETE ON publisher_payouts
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_translations_append_only
    BEFORE UPDATE OR DELETE ON translations
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_regional_requirements_append_only
    BEFORE UPDATE OR DELETE ON regional_requirements
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_growth_learnings_append_only
    BEFORE UPDATE OR DELETE ON growth_learnings
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER batch14_growth_economics_append_only
    BEFORE UPDATE OR DELETE ON growth_economics
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
