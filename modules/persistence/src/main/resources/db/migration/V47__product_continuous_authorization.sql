-- ELMOS Product B38A: exact evidence projection generated from the commercial specification.
-- This migration records readiness and evidence only; external operations remain NOT_RUN.

DO $$
DECLARE
    target record;
BEGIN
    FOR target IN SELECT * FROM (VALUES
        ('policy', 'policy_domains'),
        ('policy', 'policy_sets'),
        ('policy', 'policy_set_versions'),
        ('policy', 'policies'),
        ('policy', 'policy_versions'),
        ('policy', 'policy_kinds'),
        ('policy', 'policy_languages'),
        ('policy', 'policy_language_versions'),
        ('policy', 'policy_schemas'),
        ('policy', 'policy_engine_profiles'),
        ('policy', 'policy_engine_versions'),
        ('policy', 'policy_entrypoints'),
        ('policy', 'policy_dependencies'),
        ('policy', 'policy_conflict_rules'),
        ('policy', 'policy_obligation_types'),
        ('policy', 'policy_advice_types'),
        ('policy', 'policy_lifecycle_events'),
        ('policy', 'policy_repositories'),
        ('policy', 'policy_repository_versions'),
        ('policy', 'policy_source_files'),
        ('policy', 'policy_source_commits'),
        ('policy', 'policy_change_requests'),
        ('policy', 'policy_reviews'),
        ('policy', 'policy_approvals'),
        ('policy', 'policy_bundle_builds'),
        ('policy', 'policy_bundles'),
        ('policy', 'policy_bundle_versions'),
        ('policy', 'policy_bundle_manifests'),
        ('policy', 'policy_bundle_signatures'),
        ('policy', 'policy_bundle_distributions'),
        ('policy', 'policy_bundle_activations'),
        ('policy', 'policy_bundle_status_reports'),
        ('policy', 'policy_bundle_revocations'),
        ('policy', 'policy_bundle_rollbacks'),
        ('policy', 'policy_offline_caches'),
        ('control', 'control_automation_profiles'),
        ('control', 'control_automation_profile_versions'),
        ('control', 'control_objectives'),
        ('control', 'control_objective_versions'),
        ('control', 'control_applicability_rules'),
        ('control', 'control_evidence_requirements'),
        ('control', 'control_policy_bindings'),
        ('control', 'control_monitor_bindings'),
        ('control', 'control_gate_bindings'),
        ('control', 'control_remediation_bindings'),
        ('control', 'control_assessment_bindings'),
        ('control', 'control_automation_runs'),
        ('control', 'control_automation_results'),
        ('control', 'control_effectiveness_snapshots'),
        ('policy', 'fact_types'),
        ('policy', 'fact_type_versions'),
        ('policy', 'fact_sources'),
        ('policy', 'fact_source_versions'),
        ('policy', 'fact_records'),
        ('policy', 'fact_versions'),
        ('policy', 'fact_trust_levels'),
        ('policy', 'fact_freshness_policies'),
        ('policy', 'fact_conflicts'),
        ('policy', 'fact_precedence_rules'),
        ('policy', 'context_resolvers'),
        ('policy', 'context_resolution_runs'),
        ('policy', 'context_snapshots'),
        ('policy', 'context_snapshot_items'),
        ('policy', 'external_data_providers'),
        ('policy', 'external_data_requests'),
        ('policy', 'external_data_responses'),
        ('authorization', 'decision_requests'),
        ('authorization', 'decision_request_versions'),
        ('authorization', 'decisions'),
        ('authorization', 'decision_versions'),
        ('authorization', 'decision_obligations'),
        ('authorization', 'decision_advice'),
        ('authorization', 'decision_errors'),
        ('authorization', 'decision_caches'),
        ('authorization', 'decision_cache_invalidations'),
        ('authorization', 'authorization_versions'),
        ('authorization', 'enforcement_points'),
        ('authorization', 'enforcement_point_capabilities'),
        ('authorization', 'enforcement_requests'),
        ('authorization', 'enforcement_receipts'),
        ('authorization', 'authorization_renewals'),
        ('authorization', 'signal_transmitters'),
        ('authorization', 'signal_transmitter_versions'),
        ('authorization', 'signal_streams'),
        ('authorization', 'signal_stream_configs'),
        ('authorization', 'security_event_tokens'),
        ('authorization', 'security_event_token_receipts'),
        ('authorization', 'signal_subjects'),
        ('authorization', 'normalized_security_signals'),
        ('authorization', 'signal_replay_records'),
        ('authorization', 'signal_context_updates'),
        ('authorization', 'signal_reevaluation_jobs'),
        ('authorization', 'signal_actions'),
        ('policy', 'exception_types'),
        ('policy', 'policy_exceptions'),
        ('policy', 'policy_exception_versions'),
        ('policy', 'exception_scopes'),
        ('policy', 'exception_risk_assessments'),
        ('policy', 'exception_approvals'),
        ('policy', 'exception_compensating_controls'),
        ('policy', 'exception_usage_events'),
        ('policy', 'exception_renewals'),
        ('policy', 'exception_revocations'),
        ('policy', 'control_waivers'),
        ('policy', 'control_waiver_versions'),
        ('risk', 'risk_acceptances'),
        ('risk', 'risk_acceptance_versions'),
        ('policy', 'non_waivable_policies'),
        ('deployment', 'gate_profiles'),
        ('deployment', 'gate_profile_versions'),
        ('deployment', 'gate_requirements'),
        ('deployment', 'gate_requests'),
        ('deployment', 'gate_subjects'),
        ('deployment', 'gate_contexts'),
        ('deployment', 'gate_evidence_inputs'),
        ('deployment', 'gate_policy_decisions'),
        ('deployment', 'gate_reservations'),
        ('deployment', 'gate_expirations'),
        ('deployment', 'gate_invalidations'),
        ('deployment', 'deployment_attempts'),
        ('deployment', 'post_deploy_verifications'),
        ('deployment', 'rollback_decisions'),
        ('runtime', 'runtime_gate_profiles'),
        ('runtime', 'runtime_gate_profile_versions'),
        ('runtime', 'runtime_enforcement_points'),
        ('runtime', 'runtime_actions'),
        ('runtime', 'runtime_resource_types'),
        ('runtime', 'runtime_gate_requests'),
        ('runtime', 'runtime_gate_decisions'),
        ('runtime', 'runtime_obligations'),
        ('runtime', 'runtime_authorization_renewals'),
        ('runtime', 'runtime_gate_receipts'),
        ('runtime', 'runtime_gate_failures'),
        ('admission', 'cluster_profiles'),
        ('admission', 'cluster_capabilities'),
        ('admission', 'policy_bindings'),
        ('admission', 'native_cel_policies'),
        ('admission', 'gatekeeper_templates'),
        ('admission', 'gatekeeper_constraints'),
        ('admission', 'gatekeeper_mutators'),
        ('admission', 'kyverno_policy_refs'),
        ('admission', 'image_verification_profiles'),
        ('admission', 'admission_decisions'),
        ('admission', 'admission_audit_results'),
        ('admission', 'admission_rollouts'),
        ('remediation', 'action_types'),
        ('remediation', 'action_type_versions'),
        ('remediation', 'action_providers'),
        ('remediation', 'remediation_profiles'),
        ('remediation', 'remediation_plans'),
        ('remediation', 'remediation_plan_versions'),
        ('remediation', 'remediation_steps'),
        ('remediation', 'remediation_dependencies'),
        ('remediation', 'remediation_simulations'),
        ('remediation', 'remediation_approvals'),
        ('remediation', 'remediation_executions'),
        ('remediation', 'remediation_step_receipts'),
        ('remediation', 'compensation_plans'),
        ('remediation', 'compensation_runs'),
        ('remediation', 'reverification_runs'),
        ('policy_decision', 'decision_logs'),
        ('policy_decision', 'decision_log_segments'),
        ('policy_decision', 'decision_inputs'),
        ('policy_decision', 'decision_input_snapshots'),
        ('policy_decision', 'decision_outputs'),
        ('policy_decision', 'decision_explanations'),
        ('policy_decision', 'decision_traces'),
        ('policy_decision', 'decision_replay_runs'),
        ('policy_decision', 'decision_replay_results'),
        ('policy_decision', 'decision_attestations'),
        ('policy_decision', 'enforcement_evidence'),
        ('policy_rollout', 'policy_changes'),
        ('policy_rollout', 'policy_change_diffs'),
        ('policy_rollout', 'policy_impact_runs'),
        ('policy_rollout', 'policy_impact_subjects'),
        ('policy_rollout', 'shadow_profiles'),
        ('policy_rollout', 'shadow_decisions'),
        ('policy_rollout', 'shadow_comparisons'),
        ('policy_rollout', 'rollout_plans'),
        ('policy_rollout', 'rollout_waves'),
        ('policy_rollout', 'rollout_targets'),
        ('policy_rollout', 'rollout_results'),
        ('policy_rollout', 'kill_switches'),
        ('policy_rollout', 'rollback_plans'),
        ('policy_rollout', 'rollback_runs')
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
            WHERE schemaname = target.schema_name AND tablename = target.table_name AND policyname = 'product_b38a_tenant_isolation'
        ) THEN
            EXECUTE format(
                'CREATE POLICY product_b38a_tenant_isolation ON %I.%I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
                target.schema_name, target.table_name);
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger trigger
            JOIN pg_class relation ON relation.oid = trigger.tgrelid
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = target.schema_name AND relation.relname = target.table_name
              AND trigger.tgname = 'product_b38a_append_only' AND NOT trigger.tgisinternal
        ) THEN
            EXECUTE format(
                'CREATE TRIGGER product_b38a_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
                target.schema_name, target.table_name);
        END IF;
    END LOOP;
END;
$$;
