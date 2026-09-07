-- ELMOS Batch 19: mainframe and core legacy platform modernization projections.
-- All external z/OS actions remain leased, allowlisted and independently approved.

DO $$
DECLARE
    table_name text;
    mainframe_tables text[] := ARRAY[
        'mainframe_estates','mainframe_applications','mainframe_application_versions','mainframe_subsystems','mainframe_environments',
        'mainframe_source_datasets','mainframe_source_members','mainframe_copy_libraries','mainframe_copybooks','mainframe_copybook_versions',
        'mainframe_load_modules','mainframe_compiler_listings','mainframe_binder_maps',
        'cobol_programs','cobol_sections','cobol_paragraphs','cobol_data_items','cobol_statements','cobol_calls','cobol_files',
        'cobol_sql_statements','cobol_cics_commands','cobol_ims_calls',
        'jcl_jobs','jcl_job_versions','jcl_steps','jcl_procedures','jcl_procedure_versions','jcl_dd_statements','jcl_conditions',
        'jcl_dataset_flows','jcl_symbolic_parameters','scheduler_jobs','scheduler_calendars','scheduler_dependencies','scheduler_run_histories',
        'cics_regions','cics_transactions','cics_programs','cics_resources','cics_program_links','cics_commareas','cics_channels','cics_containers','cics_bms_maps',
        'ims_systems','ims_transactions','ims_programs','ims_messages','ims_dbds','ims_psbs','ims_pcbs','ims_segments','ims_mfs_maps',
        'db2_subsystems','db2_plans','db2_packages','db2_tables','db2_statements','db2_bind_options',
        'vsam_datasets','vsam_record_layouts','vsam_alternate_indexes',
        'mainframe_business_rules','mainframe_rule_conditions','mainframe_rule_inputs','mainframe_rule_outputs','mainframe_rule_side_effects','mainframe_rule_evidence',
        'business_capability_slices','capability_slice_members','capability_slice_dependencies',
        'mainframe_target_profiles','mainframe_migration_plans','mainframe_migration_steps','mainframe_transformations',
        'mainframe_test_baselines','mainframe_test_runs','semantic_equivalence_runs','parallel_run_results','mainframe_cutover_plans','mainframe_decommission_plans'
    ];
BEGIN
    FOREACH table_name IN ARRAY mainframe_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),' ||
            'mainframe_estate_ref varchar(255),' ||
            'mainframe_application_ref varchar(255),' ||
            'environment_ref varchar(255),' ||
            'repository_snapshot_ref varchar(255),' ||
            'source_artifact_ref varchar(512),' ||
            'runtime_artifact_ref varchar(512),' ||
            'artifact_digest varchar(255),' ||
            'engine_version varchar(64) NOT NULL DEFAULT ''1.0.0'',' ||
            'schema_version varchar(32) NOT NULL DEFAULT ''1.0'',' ||
            'status varchar(64) NOT NULL DEFAULT ''DISCOVERED'',' ||
            'external_ref varchar(512),' ||
            'idempotency_key varchar(160),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb,' ||
            'content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ ''^[0-9a-f]{64}$''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'updated_at timestamptz NOT NULL DEFAULT now(),' ||
            'UNIQUE (organization_id, idempotency_key))', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id)', 'idx_' || table_name || '_org', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id, mainframe_estate_ref)', 'idx_' || table_name || '_estate', table_name);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name);
    END LOOP;
END;
$$;

ALTER TABLE mainframe_source_members
    ADD COLUMN dataset_name varchar(512), ADD COLUMN member_name varchar(96), ADD COLUMN source_language varchar(32),
    ADD COLUMN compile_unit_ref varchar(255), ADD COLUMN load_module_ref varchar(255);
ALTER TABLE mainframe_copybook_versions
    ADD COLUMN copybook_name varchar(96), ADD COLUMN version_ref varchar(255), ADD COLUMN copylib_search_order integer,
    ADD COLUMN resolution_status varchar(32) CHECK (resolution_status IS NULL OR resolution_status IN ('RESOLVED','AMBIGUOUS','MISSING','CONDITIONAL'));
ALTER TABLE mainframe_load_modules
    ADD COLUMN module_name varchar(96), ADD COLUMN compiler_version varchar(96), ADD COLUMN compiler_options jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN binder_options jsonb NOT NULL DEFAULT '[]'::jsonb, ADD COLUMN last_observed_at timestamptz;
ALTER TABLE cobol_data_items
    ADD COLUMN level_number integer, ADD COLUMN picture varchar(255), ADD COLUMN usage_type varchar(64),
    ADD COLUMN storage_offset integer, ADD COLUMN byte_length integer, ADD COLUMN ccsid varchar(32),
    ADD COLUMN redefines_ref varchar(255), ADD COLUMN occurs_maximum integer;
ALTER TABLE cobol_calls
    ADD COLUMN call_type varchar(64), ADD COLUMN target_name varchar(255), ADD COLUMN confidence numeric(5,4),
    ADD CONSTRAINT cobol_calls_confidence_range CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1));
ALTER TABLE jcl_steps
    ADD COLUMN sequence_number integer, ADD COLUMN execution_target varchar(255), ADD COLUMN return_code_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN restart_capability varchar(64);
ALTER TABLE cics_transactions
    ADD COLUMN transaction_id varchar(16), ADD COLUMN initial_program_ref varchar(255), ADD COLUMN security_context_ref varchar(255);
ALTER TABLE cics_commareas
    ADD COLUMN contract_version varchar(64), ADD COLUMN byte_length integer, ADD COLUMN copybook_version_ref varchar(255);
ALTER TABLE ims_segments
    ADD COLUMN segment_name varchar(96), ADD COLUMN parent_segment_ref varchar(255), ADD COLUMN occurrence_ordered boolean NOT NULL DEFAULT true;
ALTER TABLE db2_bind_options
    ADD COLUMN isolation_level varchar(32), ADD COLUMN release_mode varchar(32), ADD COLUMN validate_mode varchar(32), ADD COLUMN qualifier varchar(255);
ALTER TABLE vsam_datasets
    ADD COLUMN vsam_type varchar(16), ADD COLUMN record_layout_ref varchar(255), ADD COLUMN primary_key_ref varchar(255);
ALTER TABLE mainframe_business_rules
    ADD COLUMN rule_type varchar(64), ADD COLUMN confidence numeric(5,4),
    ADD COLUMN authority varchar(32) NOT NULL DEFAULT 'CANDIDATE', ADD COLUMN business_owner_ref varchar(255),
    ADD CONSTRAINT mainframe_rule_authority CHECK (authority IN ('CANDIDATE','BUSINESS_APPROVED','REJECTED')),
    ADD CONSTRAINT mainframe_rule_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1));
ALTER TABLE mainframe_target_profiles
    ADD COLUMN target_profile varchar(64), ADD COLUMN blocked_reason varchar(1024),
    ADD CONSTRAINT mainframe_target_profile_value CHECK (target_profile IS NULL OR target_profile IN
        ('KEEP_AND_OPTIMIZE','API_ENABLE','MODULARIZE_COBOL','HYBRID_EXTRACT','COBOL_TO_JAVA','REPLATFORM_RUNTIME','DATA_ONLY_MODERNIZATION','PACKAGE_REPLACEMENT','RETIRE'));
ALTER TABLE semantic_equivalence_runs
    ADD COLUMN source_input_snapshot_ref varchar(255), ADD COLUMN source_data_snapshot_ref varchar(255),
    ADD COLUMN equivalence_status varchar(32) NOT NULL DEFAULT 'INCONCLUSIVE',
    ADD CONSTRAINT semantic_equivalence_status CHECK (equivalence_status IN ('EXACT','BUSINESS_EQUIVALENT','EXPECTED_DIFFERENCE','REGRESSION','INCONCLUSIVE'));
ALTER TABLE parallel_run_results
    ADD COLUMN parallel_mode varchar(64), ADD COLUMN side_effect_policy varchar(64),
    ADD COLUMN source_output_ref varchar(255), ADD COLUMN target_output_ref varchar(255), ADD COLUMN difference_count integer;
ALTER TABLE mainframe_cutover_plans
    ADD COLUMN online_cutover_status varchar(64), ADD COLUMN batch_cutover_status varchar(64),
    ADD COLUMN data_authority varchar(64), ADD COLUMN rollback_feasibility varchar(64);
ALTER TABLE mainframe_decommission_plans
    ADD COLUMN transaction_usage_zero boolean NOT NULL DEFAULT false, ADD COLUMN job_usage_zero boolean NOT NULL DEFAULT false,
    ADD COLUMN dataset_consumers_zero boolean NOT NULL DEFAULT false, ADD COLUMN external_consumers_zero boolean NOT NULL DEFAULT false,
    ADD COLUMN security_access_revoked boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX uq_mainframe_source_member_identity ON mainframe_source_members
    (organization_id, mainframe_estate_ref, dataset_name, member_name) WHERE dataset_name IS NOT NULL AND member_name IS NOT NULL;
CREATE UNIQUE INDEX uq_mainframe_copybook_version_identity ON mainframe_copybook_versions
    (organization_id, mainframe_estate_ref, copybook_name, version_ref) WHERE copybook_name IS NOT NULL AND version_ref IS NOT NULL;
CREATE UNIQUE INDEX uq_mainframe_load_module_identity ON mainframe_load_modules
    (organization_id, environment_ref, module_name, artifact_digest) WHERE module_name IS NOT NULL AND artifact_digest IS NOT NULL;

CREATE TRIGGER mainframe_application_versions_append_only BEFORE UPDATE OR DELETE ON mainframe_application_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER mainframe_copybook_versions_append_only BEFORE UPDATE OR DELETE ON mainframe_copybook_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER mainframe_compiler_listings_append_only BEFORE UPDATE OR DELETE ON mainframe_compiler_listings FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER mainframe_binder_maps_append_only BEFORE UPDATE OR DELETE ON mainframe_binder_maps FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER jcl_job_versions_append_only BEFORE UPDATE OR DELETE ON jcl_job_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER jcl_procedure_versions_append_only BEFORE UPDATE OR DELETE ON jcl_procedure_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER scheduler_run_histories_append_only BEFORE UPDATE OR DELETE ON scheduler_run_histories FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER mainframe_rule_evidence_append_only BEFORE UPDATE OR DELETE ON mainframe_rule_evidence FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER mainframe_transformations_append_only BEFORE UPDATE OR DELETE ON mainframe_transformations FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER mainframe_test_baselines_append_only BEFORE UPDATE OR DELETE ON mainframe_test_baselines FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER mainframe_test_runs_append_only BEFORE UPDATE OR DELETE ON mainframe_test_runs FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER semantic_equivalence_runs_append_only BEFORE UPDATE OR DELETE ON semantic_equivalence_runs FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER parallel_run_results_append_only BEFORE UPDATE OR DELETE ON parallel_run_results FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER mainframe_cutover_plans_append_only BEFORE UPDATE OR DELETE ON mainframe_cutover_plans FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER mainframe_decommission_plans_append_only BEFORE UPDATE OR DELETE ON mainframe_decommission_plans FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
