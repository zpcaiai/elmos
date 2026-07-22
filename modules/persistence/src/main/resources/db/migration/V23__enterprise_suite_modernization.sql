-- ELMOS Batch 21: ERP, CRM and Enterprise Application Suite Modernization Engine.
-- Physical V23 is used because V22 already belongs to product ecosystem growth.
-- Existing identity, workflow, evidence, data, integration, security, audit, billing and
-- delivery tables remain authoritative. Batch 13 remains authoritative for business_capabilities;
-- this migration extends it and adds the other 62 tenant-isolated suite projections.

DO $$
DECLARE
    table_name text;
    suite_tables text[] := ARRAY[
        'enterprise_suite_estates','suite_instances','suite_products','suite_releases','suite_environments','suite_modules',
        'suite_configurations','configuration_items','configuration_versions','suite_customizations','suite_extensions','suite_extension_points','suite_custom_code_objects','suite_usage_observations',
        'business_capabilities','business_processes','business_process_versions','business_process_variants','business_process_steps','business_process_actors','business_process_decisions','business_manual_steps','business_process_controls',
        'enterprise_business_objects','master_data_objects','transaction_objects','reference_data_objects','historical_data_objects','business_object_relationships',
        'master_data_records','golden_records','master_data_source_records','master_data_crosswalks','master_data_match_rules','master_data_survivorship_rules','master_data_quality_results',
        'suite_target_profiles','suite_transformation_plans','suite_transformation_waves','suite_transformation_steps',
        'suite_integrations','suite_apis','suite_events','suite_file_interfaces','suite_batch_interfaces',
        'suite_roles','suite_permissions','suite_business_roles','suite_duties','suite_role_mappings','suite_sod_rules','suite_sod_conflicts',
        'suite_test_scenarios','suite_test_runs','process_equivalence_results','financial_reconciliations','inventory_reconciliations',
        'suite_parallel_runs','suite_cutover_plans','suite_cutover_steps','suite_rollback_plans','suite_archive_plans','suite_decommission_plans'
    ];
BEGIN
    FOREACH table_name IN ARRAY suite_tables LOOP
        IF table_name = 'business_capabilities' THEN
            EXECUTE 'ALTER TABLE business_capabilities ADD COLUMN IF NOT EXISTS suite_estate_ref varchar(255)';
            EXECUTE 'ALTER TABLE business_capabilities ADD COLUMN IF NOT EXISTS suite_instance_ref varchar(255)';
            EXECUTE 'ALTER TABLE business_capabilities ADD COLUMN IF NOT EXISTS suite_environment_ref varchar(255)';
            EXECUTE 'ALTER TABLE business_capabilities ADD COLUMN IF NOT EXISTS suite_module_ref varchar(255)';
            EXECUTE 'ALTER TABLE business_capabilities ADD COLUMN IF NOT EXISTS business_process_ref varchar(255)';
            EXECUTE 'ALTER TABLE business_capabilities ADD COLUMN IF NOT EXISTS business_object_ref varchar(255)';
            EXECUTE 'ALTER TABLE business_capabilities ADD COLUMN IF NOT EXISTS master_data_ref varchar(255)';
            EXECUTE 'ALTER TABLE business_capabilities ADD COLUMN IF NOT EXISTS suite_integration_ref varchar(255)';
            EXECUTE 'ALTER TABLE business_capabilities ADD COLUMN IF NOT EXISTS suite_role_ref varchar(255)';
            EXECUTE 'ALTER TABLE business_capabilities ADD COLUMN IF NOT EXISTS repository_snapshot_ref varchar(255)';
            EXECUTE 'ALTER TABLE business_capabilities ADD COLUMN IF NOT EXISTS source_artifact_ref varchar(512)';
            EXECUTE 'ALTER TABLE business_capabilities ADD COLUMN IF NOT EXISTS runtime_artifact_ref varchar(512)';
            EXECUTE 'ALTER TABLE business_capabilities ADD COLUMN IF NOT EXISTS owner_ref varchar(255)';
            EXECUTE 'ALTER TABLE business_capabilities ADD COLUMN IF NOT EXISTS evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb';
            EXECUTE 'CREATE INDEX IF NOT EXISTS idx_business_capabilities_estate ON business_capabilities (organization_id, suite_estate_ref)';
            CONTINUE;
        END IF;
        EXECUTE format(
            'CREATE TABLE %I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),' ||
            'suite_estate_ref varchar(255),' ||
            'suite_instance_ref varchar(255),' ||
            'suite_environment_ref varchar(255),' ||
            'suite_module_ref varchar(255),' ||
            'business_process_ref varchar(255),' ||
            'business_object_ref varchar(255),' ||
            'master_data_ref varchar(255),' ||
            'suite_integration_ref varchar(255),' ||
            'suite_role_ref varchar(255),' ||
            'repository_snapshot_ref varchar(255),' ||
            'source_artifact_ref varchar(512),' ||
            'runtime_artifact_ref varchar(512),' ||
            'engine_version varchar(64) NOT NULL DEFAULT ''1.0.0'',' ||
            'schema_version varchar(32) NOT NULL DEFAULT ''1.0'',' ||
            'status varchar(64) NOT NULL DEFAULT ''DISCOVERED'',' ||
            'owner_ref varchar(255),' ||
            'external_ref varchar(512),' ||
            'idempotency_key varchar(160),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb,' ||
            'content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ ''^[0-9a-f]{64}$''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'updated_at timestamptz NOT NULL DEFAULT now(),' ||
            'UNIQUE (organization_id, idempotency_key))', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id)', 'idx_' || table_name || '_org', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id, suite_estate_ref)', 'idx_' || table_name || '_estate', table_name);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name);
    END LOOP;
END;
$$;

ALTER TABLE enterprise_suite_estates
    ADD COLUMN estate_key varchar(255), ADD COLUMN estate_version varchar(64),
    ADD COLUMN observation_window_start timestamptz, ADD COLUMN observation_window_end timestamptz,
    ADD COLUMN business_owner_approved boolean NOT NULL DEFAULT false;
ALTER TABLE suite_instances
    ADD COLUMN instance_key varchar(255), ADD COLUMN platform varchar(64), ADD COLUMN product_ref varchar(255),
    ADD COLUMN release_ref varchar(255), ADD COLUMN environment_kind varchar(32), ADD COLUMN source_of_truth_status varchar(64);
ALTER TABLE suite_customizations
    ADD COLUMN customization_key varchar(255), ADD COLUMN customization_type varchar(64),
    ADD COLUMN business_value varchar(64), ADD COLUMN clean_core_status varchar(64),
    ADD COLUMN usage_status varchar(32) NOT NULL DEFAULT 'UNKNOWN', ADD COLUMN target_placement varchar(64),
    ADD COLUMN direct_database_access boolean NOT NULL DEFAULT false,
    ADD CONSTRAINT suite_customization_usage CHECK (usage_status IN ('ACTIVE','SEASONAL','DORMANT','HISTORICAL','UNKNOWN'));
ALTER TABLE business_processes
    ADD COLUMN process_key varchar(255), ADD COLUMN value_stream varchar(255), ADD COLUMN capability_ref varchar(255),
    ADD COLUMN process_state varchar(64) NOT NULL DEFAULT 'UNKNOWN', ADD COLUMN business_owner_approved boolean NOT NULL DEFAULT false;
ALTER TABLE business_process_versions
    ADD COLUMN process_key varchar(255), ADD COLUMN process_version varchar(64), ADD COLUMN valid_from timestamptz, ADD COLUMN valid_until timestamptz;
ALTER TABLE business_process_steps
    ADD COLUMN sequence_number integer, ADD COLUMN step_type varchar(64), ADD COLUMN manual_step boolean NOT NULL DEFAULT false,
    ADD COLUMN suite_object_refs jsonb NOT NULL DEFAULT '[]'::jsonb, ADD COLUMN control_refs jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE enterprise_business_objects
    ADD COLUMN object_key varchar(255), ADD COLUMN object_category varchar(64), ADD COLUMN definition text,
    ADD COLUMN authority_status varchar(64) NOT NULL DEFAULT 'UNKNOWN_AUTHORITY', ADD COLUMN unit_ref varchar(64),
    ADD COLUMN currency_ref varchar(16), ADD COLUMN timezone_ref varchar(64), ADD COLUMN code_set_ref varchar(255);
ALTER TABLE master_data_crosswalks
    ADD COLUMN enterprise_object_id varchar(255), ADD COLUMN source_system varchar(64), ADD COLUMN source_id varchar(255),
    ADD COLUMN target_system varchar(64), ADD COLUMN target_id varchar(255), ADD COLUMN valid_from timestamptz,
    ADD COLUMN valid_until timestamptz, ADD COLUMN lifecycle_action varchar(32) NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE master_data_quality_results
    ADD COLUMN domain varchar(64), ADD COLUMN match_status varchar(32), ADD COLUMN possible_match_count integer NOT NULL DEFAULT 0,
    ADD COLUMN auto_merge_permitted boolean NOT NULL DEFAULT false, ADD COLUMN hard_gate_passed boolean NOT NULL DEFAULT false;
ALTER TABLE suite_target_profiles
    ADD COLUMN target_profile_key varchar(255), ADD COLUMN target_type varchar(64), ADD COLUMN wave_dimensions jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN organization_change_capacity varchar(64), ADD COLUMN feasible boolean NOT NULL DEFAULT false;
ALTER TABLE suite_sod_conflicts
    ADD COLUMN conflict_key varchar(255), ADD COLUMN severity varchar(32), ADD COLUMN duty_a varchar(255), ADD COLUMN duty_b varchar(255),
    ADD COLUMN compensating_control_ref varchar(255), ADD COLUMN accepted_exception boolean NOT NULL DEFAULT false,
    ADD COLUMN user_activation_blocked boolean NOT NULL DEFAULT true;
ALTER TABLE process_equivalence_results
    ADD COLUMN scenario_ref varchar(255), ADD COLUMN equivalence_status varchar(32) NOT NULL DEFAULT 'INCONCLUSIVE',
    ADD COLUMN standardized_difference_approval_ref varchar(255),
    ADD CONSTRAINT suite_process_equivalence_status CHECK (equivalence_status IN ('EXACT','BUSINESS_EQUIVALENT','STANDARDIZED_APPROVED','EXPECTED_DIFFERENCE','REGRESSION','INCONCLUSIVE'));
ALTER TABLE financial_reconciliations
    ADD COLUMN company_ref varchar(255), ADD COLUMN ledger_ref varchar(255), ADD COLUMN trial_balance_equal boolean NOT NULL DEFAULT false,
    ADD COLUMN source_amount numeric(38,10), ADD COLUMN target_amount numeric(38,10), ADD COLUMN hard_gate_passed boolean NOT NULL DEFAULT false;
ALTER TABLE inventory_reconciliations
    ADD COLUMN plant_ref varchar(255), ADD COLUMN quantity_equal boolean NOT NULL DEFAULT false,
    ADD COLUMN valuation_equal boolean NOT NULL DEFAULT false, ADD COLUMN hard_gate_passed boolean NOT NULL DEFAULT false;
ALTER TABLE suite_cutover_plans
    ADD COLUMN cutover_key varchar(255), ADD COLUMN wave_dimension varchar(64), ADD COLUMN wave_value varchar(255),
    ADD COLUMN shared_master_authority_ready boolean NOT NULL DEFAULT false,
    ADD COLUMN rollback_feasible boolean NOT NULL DEFAULT false,
    ADD COLUMN point_of_no_return_approved boolean NOT NULL DEFAULT false,
    ADD COLUMN business_owner_approved boolean NOT NULL DEFAULT false;
ALTER TABLE suite_decommission_plans
    ADD COLUMN users_zero boolean NOT NULL DEFAULT false, ADD COLUMN interfaces_zero boolean NOT NULL DEFAULT false,
    ADD COLUMN batch_zero boolean NOT NULL DEFAULT false, ADD COLUMN reports_migrated boolean NOT NULL DEFAULT false,
    ADD COLUMN open_transactions_zero boolean NOT NULL DEFAULT false, ADD COLUMN audit_history_accessible boolean NOT NULL DEFAULT false,
    ADD COLUMN archive_complete boolean NOT NULL DEFAULT false, ADD COLUMN identities_revoked boolean NOT NULL DEFAULT false,
    ADD COLUMN credentials_revoked boolean NOT NULL DEFAULT false, ADD COLUMN license_handled boolean NOT NULL DEFAULT false,
    ADD COLUMN legal_hold_checked boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX uq_suite_estate_identity ON enterprise_suite_estates
    (organization_id, estate_key, estate_version) WHERE estate_key IS NOT NULL AND estate_version IS NOT NULL;
CREATE UNIQUE INDEX uq_suite_instance_identity ON suite_instances
    (organization_id, suite_estate_ref, instance_key, environment_kind) WHERE instance_key IS NOT NULL AND environment_kind IS NOT NULL;
CREATE UNIQUE INDEX uq_suite_customization_identity ON suite_customizations
    (organization_id, suite_instance_ref, customization_key) WHERE customization_key IS NOT NULL;
CREATE UNIQUE INDEX uq_business_process_version_identity ON business_process_versions
    (organization_id, suite_estate_ref, process_key, process_version) WHERE process_key IS NOT NULL AND process_version IS NOT NULL;
CREATE UNIQUE INDEX uq_enterprise_business_object_identity ON enterprise_business_objects
    (organization_id, suite_estate_ref, object_key) WHERE object_key IS NOT NULL;
CREATE UNIQUE INDEX uq_master_data_crosswalk_identity ON master_data_crosswalks
    (organization_id, enterprise_object_id, source_system, source_id, target_system) WHERE enterprise_object_id IS NOT NULL AND source_id IS NOT NULL;
CREATE UNIQUE INDEX uq_suite_cutover_wave_identity ON suite_cutover_plans
    (organization_id, suite_estate_ref, cutover_key, wave_dimension, wave_value) WHERE cutover_key IS NOT NULL;

CREATE TRIGGER suite_usage_observations_append_only BEFORE UPDATE OR DELETE ON suite_usage_observations FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER configuration_versions_append_only BEFORE UPDATE OR DELETE ON configuration_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER master_data_quality_results_append_only BEFORE UPDATE OR DELETE ON master_data_quality_results FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER suite_transformation_steps_append_only BEFORE UPDATE OR DELETE ON suite_transformation_steps FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER suite_test_runs_append_only BEFORE UPDATE OR DELETE ON suite_test_runs FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER process_equivalence_results_append_only BEFORE UPDATE OR DELETE ON process_equivalence_results FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER financial_reconciliations_append_only BEFORE UPDATE OR DELETE ON financial_reconciliations FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER inventory_reconciliations_append_only BEFORE UPDATE OR DELETE ON inventory_reconciliations FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER suite_parallel_runs_append_only BEFORE UPDATE OR DELETE ON suite_parallel_runs FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER suite_cutover_steps_append_only BEFORE UPDATE OR DELETE ON suite_cutover_steps FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER suite_sod_conflicts_append_only BEFORE UPDATE OR DELETE ON suite_sod_conflicts FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER master_data_crosswalks_append_only BEFORE UPDATE OR DELETE ON master_data_crosswalks FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER suite_archive_plans_append_only BEFORE UPDATE OR DELETE ON suite_archive_plans FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER suite_decommission_plans_append_only BEFORE UPDATE OR DELETE ON suite_decommission_plans FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER suite_rollback_plans_append_only BEFORE UPDATE OR DELETE ON suite_rollback_plans FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
