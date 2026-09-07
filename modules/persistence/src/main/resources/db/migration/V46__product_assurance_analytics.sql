-- ELMOS Product B37C: exact evidence projection generated from the commercial specification.
-- This migration records readiness and evidence only; external operations remain NOT_RUN.

DO $$
DECLARE
    target record;
BEGIN
    FOR target IN SELECT * FROM (VALUES
        ('analytics', 'semantic_models'),
        ('analytics', 'semantic_model_versions'),
        ('analytics', 'metric_definitions'),
        ('analytics', 'metric_definition_versions'),
        ('analytics', 'metric_measures'),
        ('analytics', 'metric_dimensions'),
        ('analytics', 'metric_denominators'),
        ('analytics', 'metric_applicability_rules'),
        ('analytics', 'metric_time_windows'),
        ('analytics', 'metric_aggregation_rules'),
        ('analytics', 'metric_targets'),
        ('analytics', 'metric_guardrails'),
        ('analytics', 'metric_source_bindings'),
        ('analytics', 'metric_owners'),
        ('analytics', 'metric_snapshots'),
        ('analytics', 'metric_snapshot_dimensions'),
        ('analytics', 'metric_restatements'),
        ('analytics', 'metric_findings'),
        ('analytics', 'data_sources'),
        ('analytics', 'data_source_versions'),
        ('analytics', 'data_source_grains'),
        ('analytics', 'data_source_owners'),
        ('analytics', 'data_quality_profiles'),
        ('analytics', 'data_quality_checks'),
        ('analytics', 'data_quality_runs'),
        ('analytics', 'data_quality_results'),
        ('analytics', 'data_quality_findings'),
        ('analytics', 'data_source_certifications'),
        ('analytics', 'data_lineage_nodes'),
        ('analytics', 'data_lineage_edges'),
        ('analytics', 'source_precedence_rules'),
        ('analytics', 'source_reconciliations'),
        ('analytics', 'metric_source_readiness'),
        ('assurance', 'evidence_requirement_profiles'),
        ('assurance', 'evidence_requirement_profile_versions'),
        ('assurance', 'evidence_requirements'),
        ('assurance', 'evidence_requirement_applicability'),
        ('assurance', 'evidence_requirement_matches'),
        ('assurance', 'evidence_chain_definitions'),
        ('assurance', 'evidence_chain_stages'),
        ('assurance', 'evidence_chain_instances'),
        ('assurance', 'evidence_completeness_runs'),
        ('assurance', 'evidence_completeness_dimensions'),
        ('assurance', 'evidence_gaps'),
        ('assurance', 'project_readiness_snapshots'),
        ('risk', 'supply_chain_risk_profiles'),
        ('risk', 'supply_chain_risk_profile_versions'),
        ('risk', 'risk_subjects'),
        ('risk', 'risk_signals'),
        ('risk', 'risk_dimensions'),
        ('risk', 'component_criticality'),
        ('risk', 'component_reachability'),
        ('risk', 'component_exploitability'),
        ('risk', 'component_exposure_windows'),
        ('risk', 'builder_concentration'),
        ('risk', 'signer_concentration'),
        ('risk', 'provider_concentration'),
        ('risk', 'dependency_concentration'),
        ('risk', 'single_points_of_failure'),
        ('risk', 'blast_radius_runs'),
        ('risk', 'risk_snapshots'),
        ('risk', 'risk_acceptances'),
        ('control', 'control_catalogs'),
        ('control', 'control_catalog_versions'),
        ('control', 'controls'),
        ('control', 'control_versions'),
        ('control', 'control_profiles'),
        ('control', 'control_profile_versions'),
        ('control', 'control_parameters'),
        ('control', 'control_mappings'),
        ('control', 'control_mapping_versions'),
        ('control', 'control_responsibilities'),
        ('control', 'control_implementations'),
        ('control', 'control_implementation_statements'),
        ('control', 'assessment_plans'),
        ('control', 'assessment_plan_objectives'),
        ('control', 'assessment_methods'),
        ('control', 'assessment_objects'),
        ('control', 'assessment_runs'),
        ('control', 'assessment_results'),
        ('control', 'assessment_findings'),
        ('control', 'control_evidence_links'),
        ('control', 'continuous_monitor_rules'),
        ('control', 'continuous_monitor_results'),
        ('control', 'poam_items'),
        ('control', 'oscal_imports'),
        ('control', 'oscal_exports'),
        ('audit', 'audit_engagements'),
        ('audit', 'audit_engagement_versions'),
        ('audit', 'audit_scopes'),
        ('audit', 'audit_periods'),
        ('audit', 'audit_frameworks'),
        ('audit', 'pbc_request_lists'),
        ('audit', 'pbc_request_list_versions'),
        ('audit', 'pbc_requests'),
        ('audit', 'pbc_request_evidence_mappings'),
        ('audit', 'pbc_request_assignments'),
        ('audit', 'pbc_request_responses'),
        ('audit', 'pbc_request_reviews'),
        ('audit', 'evidence_rooms'),
        ('audit', 'evidence_room_items'),
        ('audit', 'examiner_accounts'),
        ('audit', 'examiner_access_grants'),
        ('audit', 'examiner_questions'),
        ('audit', 'examiner_answers'),
        ('audit', 'audit_samples'),
        ('audit', 'audit_sample_items'),
        ('audit', 'audit_readiness_snapshots'),
        ('audit', 'audit_exports'),
        ('assurance', 'freshness_policies'),
        ('assurance', 'freshness_policy_versions'),
        ('assurance', 'evidence_validity_periods'),
        ('assurance', 'evidence_freshness_results'),
        ('assurance', 'evidence_staleness_reasons'),
        ('assurance', 'renewal_profiles'),
        ('assurance', 'renewal_schedules'),
        ('assurance', 'expiry_forecasts'),
        ('assurance', 'freshness_alerts'),
        ('analytics', 'time_series_definitions'),
        ('analytics', 'time_series_points'),
        ('analytics', 'time_series_intervals'),
        ('analytics', 'time_series_gaps'),
        ('analytics', 'metric_baselines'),
        ('analytics', 'baseline_versions'),
        ('analytics', 'seasonality_profiles'),
        ('analytics', 'change_point_runs'),
        ('analytics', 'change_points'),
        ('analytics', 'anomaly_profiles'),
        ('analytics', 'anomaly_runs'),
        ('analytics', 'anomalies'),
        ('analytics', 'anomaly_explanations'),
        ('analytics', 'driver_contributions'),
        ('analytics', 'segment_diagnostics'),
        ('portfolio', 'portfolios'),
        ('portfolio', 'portfolio_versions'),
        ('portfolio', 'portfolio_members'),
        ('portfolio', 'portfolio_member_versions'),
        ('portfolio', 'portfolio_hierarchies'),
        ('portfolio', 'portfolio_segments'),
        ('portfolio', 'portfolio_cohorts'),
        ('portfolio', 'rollup_profiles'),
        ('portfolio', 'rollup_profile_versions'),
        ('portfolio', 'portfolio_metric_snapshots'),
        ('portfolio', 'portfolio_risk_appetites'),
        ('portfolio', 'portfolio_thresholds'),
        ('portfolio', 'portfolio_benchmarks'),
        ('portfolio', 'portfolio_distributions'),
        ('portfolio', 'portfolio_concentrations'),
        ('cockpit', 'executive_cockpit_profiles'),
        ('cockpit', 'executive_cockpit_profile_versions'),
        ('cockpit', 'executive_metric_selections'),
        ('cockpit', 'executive_layouts'),
        ('cockpit', 'executive_sections'),
        ('cockpit', 'executive_narrative_profiles'),
        ('cockpit', 'executive_narratives'),
        ('cockpit', 'executive_snapshot_publications'),
        ('cockpit', 'auditor_cockpit_profiles'),
        ('cockpit', 'auditor_views'),
        ('cockpit', 'control_navigator_states'),
        ('cockpit', 'control_assurance_snapshots'),
        ('cockpit', 'evidence_navigation_sessions'),
        ('cockpit', 'auditor_sample_plans'),
        ('cockpit', 'auditor_sample_runs'),
        ('cockpit', 'auditor_notes'),
        ('cockpit', 'auditor_exports'),
        ('assurance', 'alert_rules'),
        ('assurance', 'alert_rule_versions'),
        ('assurance', 'alerts'),
        ('assurance', 'alert_occurrences'),
        ('assurance', 'alert_dedup_keys'),
        ('assurance', 'alert_suppressions'),
        ('assurance', 'assurance_cases'),
        ('assurance', 'case_owners'),
        ('assurance', 'case_tasks'),
        ('assurance', 'case_slas'),
        ('assurance', 'case_escalations'),
        ('assurance', 'remediation_plans'),
        ('assurance', 'remediation_steps'),
        ('assurance', 'remediation_evidence'),
        ('assurance', 'risk_acceptances'),
        ('assurance', 'reverification_requests'),
        ('assurance', 'reverification_results'),
        ('analytics', 'analytical_models'),
        ('analytics', 'analytical_model_versions'),
        ('analytics', 'fact_definitions'),
        ('analytics', 'dimension_definitions'),
        ('analytics', 'materialized_aggregates'),
        ('analytics', 'aggregate_refresh_runs'),
        ('analytics', 'assurance_cubes'),
        ('analytics', 'assurance_cube_versions'),
        ('analytics', 'query_definitions'),
        ('analytics', 'query_runs'),
        ('analytics', 'query_cache_entries'),
        ('analytics', 'dashboard_datasets'),
        ('analytics', 'dashboard_filter_definitions'),
        ('analytics', 'dashboard_exports'),
        ('analytics', 'dashboard_schedules'),
        ('analytics', 'published_dashboard_snapshots'),
        ('analytics', 'snapshot_signatures'),
        ('forecast', 'forecast_profiles'),
        ('forecast', 'forecast_profile_versions'),
        ('forecast', 'forecast_runs'),
        ('forecast', 'forecast_inputs'),
        ('forecast', 'forecast_assumptions'),
        ('forecast', 'forecast_models'),
        ('forecast', 'forecast_results'),
        ('forecast', 'forecast_intervals'),
        ('forecast', 'scenario_definitions'),
        ('forecast', 'scenario_runs'),
        ('forecast', 'scenario_results'),
        ('forecast', 'stress_tests'),
        ('forecast', 'sensitivity_runs'),
        ('forecast', 'sensitivity_results'),
        ('forecast', 'action_priorities')
    ) AS listed(schema_name, table_name)
    LOOP
        EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', target.schema_name);
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I.%I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES public.organizations(organization_id),' ||
            'domain_run_id varchar(160) NOT NULL,' ||
            'subject_digest varchar(64) NOT NULL CHECK (subject_digest ~ ''^[0-9a-f]{64}$''),' ||
            'context_snapshot_digest varchar(64) NOT NULL CHECK (context_snapshot_digest ~ ''^[0-9a-f]{64}$''),' ||
            'policy_version varchar(96) NOT NULL,' ||
            'status varchar(64) NOT NULL DEFAULT ''NOT_RUN'' CHECK (status IN (''OBSERVED'',''VERIFIED'',''FAILED'',''NOT_RUN'',''INCONCLUSIVE'',''UNKNOWN'',''BLOCKED'',''READY_FOR_EXTERNAL_GATE'',''READY_FOR_HUMAN_DECISION'')),' ||
            'independent_verifier_id varchar(160),' ||
            'critical_open_risks integer NOT NULL DEFAULT 0 CHECK (critical_open_risks >= 0),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb CHECK (jsonb_typeof(evidence_refs) = ''array''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb CHECK (jsonb_typeof(payload) = ''object''),' ||
            'external_operation_executed boolean NOT NULL DEFAULT false CHECK (external_operation_executed = false),' ||
            'human_approval_ref varchar(512),' ||
            'idempotency_key varchar(160) NOT NULL,' ||
            'observed_at timestamptz NOT NULL,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'CHECK (status <> ''READY_FOR_HUMAN_DECISION'' OR (independent_verifier_id IS NOT NULL AND critical_open_risks = 0 AND jsonb_array_length(evidence_refs) > 0)),' ||
            'CHECK (human_approval_ref IS NULL OR jsonb_array_length(evidence_refs) > 0),' ||
            'UNIQUE (organization_id, idempotency_key))',
            target.schema_name, target.table_name);
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON %I.%I (organization_id, domain_run_id, status)',
            'idx_' || left(target.table_name, 32) || '_' || substr(md5(target.schema_name || target.table_name), 1, 8),
            target.schema_name, target.table_name);
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', target.schema_name, target.table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', target.schema_name, target.table_name);
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = target.schema_name AND tablename = target.table_name AND policyname = 'product_b37c_tenant_isolation'
        ) THEN
            EXECUTE format(
                'CREATE POLICY product_b37c_tenant_isolation ON %I.%I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
                target.schema_name, target.table_name);
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger trigger
            JOIN pg_class relation ON relation.oid = trigger.tgrelid
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = target.schema_name AND relation.relname = target.table_name
              AND trigger.tgname = 'product_b37c_append_only' AND NOT trigger.tgisinternal
        ) THEN
            EXECUTE format(
                'CREATE TRIGGER product_b37c_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
                target.schema_name, target.table_name);
        END IF;
    END LOOP;
END;
$$;
