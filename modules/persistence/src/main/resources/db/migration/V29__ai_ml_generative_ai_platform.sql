-- ELMOS Skill Pack Batch 23. Generated from the authoritative attachment table inventory.
-- A dedicated namespace preserves logical names without stealing authority from earlier batch tables.
-- These tables record tenant-scoped evidence and decisions; they do not execute provider or production actions.

CREATE SCHEMA IF NOT EXISTS ai_platform;

DO $$
DECLARE
    target_schema text := 'ai_platform';
    table_name text;
    batch_tables text[] := ARRAY[
        'ai_estates',
        'ai_use_cases',
        'ai_systems',
        'ai_system_versions',
        'ai_risk_tiers',
        'ai_owners',
        'ai_datasets',
        'ai_dataset_versions',
        'ai_dataset_snapshots',
        'ai_dataset_lineage_edges',
        'ai_label_schemas',
        'ai_labeling_jobs',
        'ai_annotations',
        'ai_ground_truth_records',
        'ai_features',
        'ai_feature_definitions',
        'ai_feature_views',
        'ai_feature_services',
        'ai_feature_materializations',
        'ai_feature_freshness_samples',
        'ai_feature_parity_results',
        'ai_experiments',
        'ai_experiment_runs',
        'ai_training_pipelines',
        'ai_training_pipeline_versions',
        'ai_training_runs',
        'ai_training_components',
        'ai_training_checkpoints',
        'ai_hyperparameters',
        'ai_training_resources',
        'ai_models',
        'ai_model_versions',
        'ai_model_artifacts',
        'ai_model_signatures',
        'ai_model_cards',
        'ai_model_approvals',
        'ai_model_aliases',
        'ai_prompts',
        'ai_prompt_versions',
        'ai_prompt_templates',
        'ai_instruction_bundles',
        'ai_few_shot_datasets',
        'ai_inference_endpoints',
        'ai_inference_runtimes',
        'ai_inference_deployments',
        'ai_inference_routes',
        'ai_inference_profiles',
        'ai_inference_observations',
        'llm_providers',
        'llm_provider_accounts',
        'llm_models',
        'llm_endpoints',
        'llm_route_policies',
        'llm_quotas',
        'llm_usage_records',
        'llm_cache_records',
        'knowledge_sources',
        'knowledge_documents',
        'knowledge_document_versions',
        'knowledge_chunks',
        'knowledge_embeddings',
        'vector_indexes',
        'vector_index_versions',
        'retrievers',
        'rerankers',
        'rag_citations',
        'agent_definitions',
        'agent_versions',
        'agent_tools',
        'agent_tool_permissions',
        'agent_memory_policies',
        'agent_runs',
        'agent_steps',
        'agent_handoffs',
        'agent_human_approvals',
        'ai_evaluation_datasets',
        'ai_evaluation_cases',
        'ai_evaluators',
        'ai_judges',
        'ai_judge_calibrations',
        'ai_evaluation_runs',
        'ai_evaluation_results',
        'ai_human_feedback',
        'ai_guardrails',
        'ai_guardrail_versions',
        'ai_guardrail_decisions',
        'ai_red_team_scenarios',
        'ai_red_team_runs',
        'responsible_ai_profiles',
        'ai_risks',
        'fairness_assessments',
        'explainability_assessments',
        'human_oversight_policies',
        'ai_impact_assessments',
        'ai_traces',
        'ai_trace_spans',
        'ai_quality_observations',
        'ai_drift_observations',
        'ai_incidents',
        'ai_cost_allocations',
        'ai_cost_budgets',
        'ai_unit_economics',
        'ai_capacity_forecasts',
        'ai_release_bundles',
        'ai_release_decisions',
        'ai_rollback_plans',
        'ai_decommission_plans'
    ];
    append_only_tables text[] := ARRAY[
        'ai_system_versions',
        'ai_dataset_versions',
        'ai_ground_truth_records',
        'ai_feature_parity_results',
        'ai_experiment_runs',
        'ai_training_pipeline_versions',
        'ai_training_runs',
        'ai_training_checkpoints',
        'ai_model_versions',
        'ai_model_approvals',
        'ai_prompt_versions',
        'ai_inference_endpoints',
        'ai_inference_observations',
        'llm_endpoints',
        'llm_usage_records',
        'llm_cache_records',
        'knowledge_document_versions',
        'vector_index_versions',
        'agent_versions',
        'agent_runs',
        'agent_handoffs',
        'agent_human_approvals',
        'ai_evaluation_runs',
        'ai_evaluation_results',
        'ai_human_feedback',
        'ai_guardrail_versions',
        'ai_guardrail_decisions',
        'ai_red_team_runs',
        'ai_traces',
        'ai_trace_spans',
        'ai_quality_observations',
        'ai_drift_observations',
        'ai_release_decisions'
    ];
BEGIN
    FOREACH table_name IN ARRAY batch_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I.%I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES public.organizations(organization_id),' ||
            'tenant_id varchar(96) NOT NULL,' ||
            'domain_run_id varchar(160),' ||
            'workspace_ref varchar(512),' ||
            'owner_id varchar(160) NOT NULL,' ||
            'human_owner_id varchar(160) NOT NULL,' ||
            'status varchar(64) NOT NULL DEFAULT ''OBSERVED'',' ||
            'authority_status varchar(64) NOT NULL DEFAULT ''OBSERVED'',' ||
            'confidence numeric(5,4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),' ||
            'source varchar(160) NOT NULL,' ||
            'source_record_ref varchar(512) NOT NULL,' ||
            'idempotency_key varchar(160) NOT NULL,' ||
            'evidence_status varchar(32) NOT NULL DEFAULT ''NOT_RUN'' CHECK (evidence_status IN (''NOT_RUN'',''INCONCLUSIVE'',''PASS'',''FAIL'',''BLOCKED'')),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb CHECK (jsonb_typeof(evidence_refs) = ''array''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb CHECK (jsonb_typeof(payload) = ''object''),' ||
            'external_operation_executed boolean NOT NULL DEFAULT false,' ||
            'actual_execution_evidence_ref varchar(512),' ||
            'production_state_changed boolean NOT NULL DEFAULT false,' ||
            'human_approval_ref varchar(512),' ||
            'observed_at timestamptz NOT NULL,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'updated_at timestamptz NOT NULL DEFAULT now(),' ||
            'CHECK (NOT external_operation_executed OR actual_execution_evidence_ref IS NOT NULL),' ||
            'CHECK (NOT production_state_changed OR human_approval_ref IS NOT NULL),' ||
            'CHECK (status NOT IN (''SUCCEEDED'',''APPROVED'',''PASS'') OR jsonb_array_length(evidence_refs) > 0),' ||
            'UNIQUE (organization_id, idempotency_key),' ||
            'UNIQUE (organization_id, source, source_record_ref))',
            target_schema, table_name);
        EXECUTE format('CREATE INDEX %I ON %I.%I (organization_id)',
                       'idx_' || table_name || '_organization', target_schema, table_name);
        EXECUTE format('CREATE INDEX %I ON %I.%I (organization_id, domain_run_id, status)',
                       'idx_' || table_name || '_domain_run', target_schema, table_name);
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', target_schema, table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', target_schema, table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I.%I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            target_schema, table_name);
        IF table_name = ANY(append_only_tables) THEN
            EXECUTE format(
                'CREATE TRIGGER batch_23_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
                target_schema, table_name);
        END IF;
    END LOOP;
END;
$$;
