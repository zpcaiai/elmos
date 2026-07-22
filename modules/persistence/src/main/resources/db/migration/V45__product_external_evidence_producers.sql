-- ELMOS Product B37B: exact evidence projection generated from the commercial specification.
-- This migration records readiness and evidence only; external operations remain NOT_RUN.

DO $$
DECLARE
    target record;
BEGIN
    FOR target IN SELECT * FROM (VALUES
        ('evidence', 'external_producer_connections'),
        ('evidence', 'external_producer_connection_versions'),
        ('evidence', 'external_producer_capabilities'),
        ('evidence', 'external_producer_credentials'),
        ('evidence', 'external_producer_projects'),
        ('evidence', 'external_producer_events'),
        ('evidence', 'external_producer_health'),
        ('evidence', 'external_runs'),
        ('evidence', 'external_run_attempts'),
        ('evidence', 'external_jobs'),
        ('evidence', 'external_job_attempts'),
        ('evidence', 'external_steps'),
        ('evidence', 'external_native_evidence'),
        ('evidence', 'external_native_evidence_versions'),
        ('evidence', 'external_artifact_descriptors'),
        ('evidence', 'external_report_descriptors'),
        ('evidence', 'external_ingestion_receipts'),
        ('evidence', 'producer_webhook_deliveries'),
        ('evidence', 'producer_webhook_payloads'),
        ('evidence', 'producer_polling_cursors'),
        ('evidence', 'producer_watermarks'),
        ('evidence', 'producer_backfill_runs'),
        ('evidence', 'producer_backfill_pages'),
        ('evidence', 'producer_dedup_records'),
        ('evidence', 'producer_reconciliation_runs'),
        ('evidence', 'producer_reconciliation_findings'),
        ('evidence', 'producer_dead_letters'),
        ('evidence', 'jenkins_controllers'),
        ('evidence', 'jenkins_plugin_snapshots'),
        ('evidence', 'jenkins_jobs'),
        ('evidence', 'jenkins_builds'),
        ('evidence', 'jenkins_fingerprints'),
        ('evidence', 'github_action_workflows'),
        ('evidence', 'github_action_runs'),
        ('evidence', 'github_action_run_attempts'),
        ('evidence', 'github_action_jobs'),
        ('evidence', 'github_action_artifacts'),
        ('evidence', 'github_action_attestations'),
        ('evidence', 'gitlab_pipelines'),
        ('evidence', 'gitlab_pipeline_bridges'),
        ('evidence', 'gitlab_jobs'),
        ('evidence', 'gitlab_job_artifacts'),
        ('evidence', 'gitlab_report_artifacts'),
        ('evidence', 'azure_pipeline_builds'),
        ('evidence', 'azure_pipeline_timelines'),
        ('evidence', 'azure_pipeline_timeline_records'),
        ('evidence', 'azure_pipeline_artifacts'),
        ('evidence', 'azure_test_runs'),
        ('evidence', 'azure_test_results'),
        ('evidence', 'sonarqube_instances'),
        ('evidence', 'sonarqube_projects'),
        ('evidence', 'sonarqube_analyses'),
        ('evidence', 'sonarqube_quality_gates'),
        ('evidence', 'sonarqube_gate_conditions'),
        ('evidence', 'sonarqube_measures'),
        ('evidence', 'sonarqube_issues'),
        ('evidence', 'sonarqube_profiles'),
        ('security', 'scanner_products'),
        ('security', 'scanner_versions'),
        ('security', 'scan_runs'),
        ('security', 'scan_targets'),
        ('security', 'native_security_reports'),
        ('security', 'normalized_findings'),
        ('security', 'finding_versions'),
        ('security', 'finding_locations'),
        ('security', 'finding_fingerprints'),
        ('security', 'finding_taxonomies'),
        ('security', 'finding_severities'),
        ('security', 'vulnerabilities'),
        ('security', 'vulnerability_aliases'),
        ('security', 'affected_components'),
        ('security', 'finding_suppressions'),
        ('security', 'risk_acceptances'),
        ('security', 'finding_conflicts'),
        ('security', 'scan_completeness'),
        ('test', 'test_runs'),
        ('test', 'test_run_attempts'),
        ('test', 'test_suites'),
        ('test', 'test_cases'),
        ('test', 'test_case_versions'),
        ('test', 'test_invocations'),
        ('test', 'test_results'),
        ('test', 'test_attachments'),
        ('test', 'test_discovery_inventories'),
        ('test', 'coverage_runs'),
        ('test', 'coverage_scopes'),
        ('test', 'coverage_metrics'),
        ('test', 'mutation_runs'),
        ('test', 'mutation_results'),
        ('test', 'flaky_observations'),
        ('test', 'flaky_classifications'),
        ('test', 'test_baseline_comparisons'),
        ('test', 'test_completeness'),
        ('performance', 'performance_runs'),
        ('performance', 'performance_run_attempts'),
        ('performance', 'performance_scenarios'),
        ('performance', 'load_models'),
        ('performance', 'environment_manifests'),
        ('performance', 'datasets'),
        ('performance', 'metric_definitions'),
        ('performance', 'metric_series'),
        ('performance', 'metric_summaries'),
        ('performance', 'percentiles'),
        ('performance', 'thresholds'),
        ('performance', 'threshold_results'),
        ('performance', 'baselines'),
        ('performance', 'comparisons'),
        ('performance', 'regressions'),
        ('performance', 'resource_saturation'),
        ('performance', 'performance_completeness'),
        ('audit', 'external_assessors'),
        ('audit', 'external_assessor_versions'),
        ('audit', 'assessor_signing_identities'),
        ('audit', 'external_assessments'),
        ('audit', 'external_assessment_versions'),
        ('audit', 'assessment_scopes'),
        ('audit', 'assessment_periods'),
        ('audit', 'assessment_methodologies'),
        ('audit', 'assessment_claims'),
        ('audit', 'assessment_findings'),
        ('audit', 'assessment_evidence_references'),
        ('audit', 'assessment_signatures'),
        ('audit', 'assessment_reviews'),
        ('audit', 'assessment_revisions'),
        ('audit', 'assessment_withdrawals'),
        ('audit', 'assessment_trust_decisions'),
        ('evidence', 'external_correlations'),
        ('evidence', 'external_correlation_versions'),
        ('evidence', 'correlation_candidates'),
        ('evidence', 'correlation_rules'),
        ('evidence', 'correlation_conflicts'),
        ('evidence', 'correlation_confidence'),
        ('evidence', 'correlation_reviews'),
        ('evidence', 'external_lineage_edges'),
        ('evidence', 'quality_profiles'),
        ('evidence', 'quality_profile_versions'),
        ('evidence', 'quality_assessments'),
        ('evidence', 'quality_dimensions'),
        ('evidence', 'freshness_policies'),
        ('evidence', 'completeness_profiles'),
        ('evidence', 'completeness_results'),
        ('evidence', 'conflicts'),
        ('evidence', 'conflict_resolutions'),
        ('evidence', 'confidence_results'),
        ('evidence', 'external_evidence_gates'),
        ('evidence', 'external_evidence_gate_results')
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
            WHERE schemaname = target.schema_name AND tablename = target.table_name AND policyname = 'product_b37b_tenant_isolation'
        ) THEN
            EXECUTE format(
                'CREATE POLICY product_b37b_tenant_isolation ON %I.%I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
                target.schema_name, target.table_name);
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger trigger
            JOIN pg_class relation ON relation.oid = trigger.tgrelid
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = target.schema_name AND relation.relname = target.table_name
              AND trigger.tgname = 'product_b37b_append_only' AND NOT trigger.tgisinternal
        ) THEN
            EXECUTE format(
                'CREATE TRIGGER product_b37b_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
                target.schema_name, target.table_name);
        END IF;
    END LOOP;
END;
$$;
