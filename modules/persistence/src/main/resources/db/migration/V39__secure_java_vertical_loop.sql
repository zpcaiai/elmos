-- ELMOS Product Batch 33: secure Java modernization paid vertical loop.
-- Records are evidence-bound and append-only. This schema does not execute external actions.

CREATE SCHEMA IF NOT EXISTS secure_java_vertical;

DO $$
DECLARE
    target_schema text := 'secure_java_vertical';
    table_name text;
    batch_tables text[] := ARRAY[
        'identity_contexts',
        'runner_enrollments',
        'runner_leases',
        'sandbox_executions',
        'repository_snapshots',
        'maven_baselines',
        'java_health_reports',
        'migration_plans',
        'rewrite_runs',
        'compatibility_runs',
        'agent_repair_runs',
        'temporal_workflows',
        'pull_request_deliveries',
        'evidence_packs',
        'release_gates',
        'commercial_readiness_reviews'
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
