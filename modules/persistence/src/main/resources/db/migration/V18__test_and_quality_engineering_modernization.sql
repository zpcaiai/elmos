-- ELMOS Batch 18: test and quality engineering modernization projections.
-- Tenant, workflow, risk, approval, evidence, audit, billing and delivery remain shared authorities.
-- test_suites and test_case_identities are extended from Batch 7 rather than duplicated.
-- Production secrets, unrestricted production data and mutable quality-gate definitions are forbidden.

DO $$
DECLARE
    table_name text;
    quality_tables text[] := ARRAY[
        'test_estates','test_framework_profiles','test_cases','test_case_tags','test_case_dependencies',
        'test_executions','test_attempts','test_results','test_failures','test_failure_fingerprints','test_skips','test_discovery_snapshots',
        'quality_requirements','quality_requirement_versions','quality_risks','quality_risk_factors','quality_coverage_records','quality_coverage_gaps',
        'test_portfolios','test_portfolio_versions','test_layers','test_modernization_plans','test_modernization_steps',
        'characterization_scenarios','behavior_observations','golden_masters','golden_master_versions','snapshot_artifacts','snapshot_approvals',
        'contract_tests','contract_interactions','contract_artifacts','provider_verifications','contract_compatibility_matrices',
        'property_definitions','property_tests','property_test_runs','generated_examples','minimal_failing_examples','state_machine_models','state_machine_runs',
        'mutation_runs','mutation_operators','mutants','mutation_results','mutation_score_snapshots','equivalent_mutant_reviews',
        'test_data_assets','test_data_profiles','synthetic_data_plans','masked_datasets','test_fixtures','test_fixture_versions','test_data_leases',
        'virtual_services','virtual_service_scenarios','test_environment_templates','test_environments','test_environment_leases','test_dependency_instances',
        'ai_test_candidates','ai_test_generation_runs','ai_test_reviews','ai_test_promotion_decisions',
        'flaky_test_profiles','flaky_observations','nondeterminism_causes','test_quarantines','flaky_remediation_tasks',
        'test_impact_graphs','test_impact_edges','test_selections','test_execution_plans','test_shards','test_execution_statistics',
        'quality_gates','quality_gate_rules','quality_gate_results','quality_decisions','release_confidence_snapshots',
        'continuous_validation_plans','continuous_validation_triggers','continuous_validation_runs',
        'production_defects','defect_test_links','quality_learning_actions'
    ];
BEGIN
    FOREACH table_name IN ARRAY quality_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),' ||
            'test_estate_ref varchar(255),' ||
            'repository_snapshot_ref varchar(255),' ||
            'source_commit varchar(128),' ||
            'artifact_digest varchar(255),' ||
            'environment_ref varchar(255),' ||
            'quality_profile varchar(64) NOT NULL DEFAULT ''STANDARD'',' ||
            'engine_version varchar(64) NOT NULL DEFAULT ''1.0.0'',' ||
            'schema_version varchar(32) NOT NULL DEFAULT ''1.0'',' ||
            'status varchar(64) NOT NULL DEFAULT ''CREATED'',' ||
            'external_ref varchar(255),' ||
            'idempotency_key varchar(160),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb,' ||
            'content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ ''^[0-9a-f]{64}$''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'updated_at timestamptz NOT NULL DEFAULT now(),' ||
            'CHECK (quality_profile IN (''STANDARD'',''HIGH_ASSURANCE'',''REGULATED'',''CRITICAL_SYSTEM'')),' ||
            'UNIQUE (organization_id, idempotency_key))', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id)', 'idx_' || table_name || '_org', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id, test_estate_ref)', 'idx_' || table_name || '_estate', table_name);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name);
    END LOOP;
END;
$$;

ALTER TABLE test_suites
    ADD COLUMN IF NOT EXISTS test_estate_ref varchar(255),
    ADD COLUMN IF NOT EXISTS repository_snapshot_ref varchar(255),
    ADD COLUMN IF NOT EXISTS framework_profile_ref varchar(255),
    ADD COLUMN IF NOT EXISTS environment_profile varchar(255),
    ADD COLUMN IF NOT EXISTS quality_evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE test_case_identities
    ADD COLUMN IF NOT EXISTS test_estate_ref varchar(255),
    ADD COLUMN IF NOT EXISTS repository_snapshot_ref varchar(255),
    ADD COLUMN IF NOT EXISTS repository_ref varchar(255),
    ADD COLUMN IF NOT EXISTS module_name varchar(255),
    ADD COLUMN IF NOT EXISTS framework_name varchar(255),
    ADD COLUMN IF NOT EXISTS suite_name varchar(255),
    ADD COLUMN IF NOT EXISTS class_or_file varchar(1024),
    ADD COLUMN IF NOT EXISTS logical_name varchar(1024),
    ADD COLUMN IF NOT EXISTS parameter_signature varchar(1024),
    ADD COLUMN IF NOT EXISTS environment_profile varchar(255),
    ADD COLUMN IF NOT EXISTS stable_identity_hash varchar(64),
    ADD COLUMN IF NOT EXISTS quality_evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD CONSTRAINT test_case_identities_stable_hash_format CHECK (stable_identity_hash IS NULL OR stable_identity_hash ~ '^[0-9a-f]{64}$');

CREATE INDEX IF NOT EXISTS idx_test_suites_quality_estate ON test_suites (organization_id, test_estate_ref);
CREATE INDEX IF NOT EXISTS idx_test_case_identities_quality_estate ON test_case_identities (organization_id, test_estate_ref);
CREATE UNIQUE INDEX IF NOT EXISTS uq_test_case_identities_stable_hash
    ON test_case_identities (organization_id, stable_identity_hash) WHERE stable_identity_hash IS NOT NULL;

CREATE TRIGGER test_case_identities_quality_append_only BEFORE UPDATE OR DELETE ON test_case_identities FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER test_attempts_append_only BEFORE UPDATE OR DELETE ON test_attempts FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER test_results_append_only BEFORE UPDATE OR DELETE ON test_results FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER test_failures_append_only BEFORE UPDATE OR DELETE ON test_failures FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER test_discovery_snapshots_append_only BEFORE UPDATE OR DELETE ON test_discovery_snapshots FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER quality_requirement_versions_append_only BEFORE UPDATE OR DELETE ON quality_requirement_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER quality_coverage_records_append_only BEFORE UPDATE OR DELETE ON quality_coverage_records FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER test_portfolio_versions_append_only BEFORE UPDATE OR DELETE ON test_portfolio_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER behavior_observations_append_only BEFORE UPDATE OR DELETE ON behavior_observations FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER golden_master_versions_append_only BEFORE UPDATE OR DELETE ON golden_master_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER snapshot_artifacts_quality_append_only BEFORE UPDATE OR DELETE ON snapshot_artifacts FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER snapshot_approvals_append_only BEFORE UPDATE OR DELETE ON snapshot_approvals FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER contract_artifacts_append_only BEFORE UPDATE OR DELETE ON contract_artifacts FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER provider_verifications_append_only BEFORE UPDATE OR DELETE ON provider_verifications FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER property_test_runs_append_only BEFORE UPDATE OR DELETE ON property_test_runs FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER minimal_failing_examples_append_only BEFORE UPDATE OR DELETE ON minimal_failing_examples FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER state_machine_runs_append_only BEFORE UPDATE OR DELETE ON state_machine_runs FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER mutation_results_append_only BEFORE UPDATE OR DELETE ON mutation_results FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER mutation_score_snapshots_append_only BEFORE UPDATE OR DELETE ON mutation_score_snapshots FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER equivalent_mutant_reviews_append_only BEFORE UPDATE OR DELETE ON equivalent_mutant_reviews FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER test_fixture_versions_append_only BEFORE UPDATE OR DELETE ON test_fixture_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER test_data_leases_append_only BEFORE UPDATE OR DELETE ON test_data_leases FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER test_environment_leases_append_only BEFORE UPDATE OR DELETE ON test_environment_leases FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER ai_test_generation_runs_append_only BEFORE UPDATE OR DELETE ON ai_test_generation_runs FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER ai_test_reviews_append_only BEFORE UPDATE OR DELETE ON ai_test_reviews FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER ai_test_promotion_decisions_append_only BEFORE UPDATE OR DELETE ON ai_test_promotion_decisions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER flaky_observations_append_only BEFORE UPDATE OR DELETE ON flaky_observations FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER test_execution_statistics_append_only BEFORE UPDATE OR DELETE ON test_execution_statistics FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER quality_gate_results_append_only BEFORE UPDATE OR DELETE ON quality_gate_results FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER quality_decisions_append_only BEFORE UPDATE OR DELETE ON quality_decisions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER release_confidence_snapshots_append_only BEFORE UPDATE OR DELETE ON release_confidence_snapshots FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER continuous_validation_runs_append_only BEFORE UPDATE OR DELETE ON continuous_validation_runs FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER production_defects_append_only BEFORE UPDATE OR DELETE ON production_defects FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER quality_learning_actions_append_only BEFORE UPDATE OR DELETE ON quality_learning_actions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
