-- ELMOS Batch 7. Append-only evidence records use JSONB for versioned payloads while stable keys remain queryable.

CREATE TABLE validation_plans (
    validation_plan_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE validation_profiles (
    validation_profile_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE validation_stages (
    validation_stage_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE validation_runs (
    validation_run_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE validation_attempts (
    validation_attempt_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE validation_decisions (
    validation_decision_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE build_baselines (
    build_baseline_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE build_results (
    build_result_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE build_artifacts (
    build_artifact_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE build_environment_snapshots (
    build_environment_snapshot_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE build_dependency_snapshots (
    build_dependency_snapshot_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE test_suites (
    test_suite_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE test_case_identities (
    test_case_identity_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE test_case_results (
    test_case_result_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE test_result_comparisons (
    test_result_comparison_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE test_flakiness_records (
    test_flakiness_record_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE test_coverage_snapshots (
    test_coverage_snapshot_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE test_environment_definitions (
    test_environment_definition_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE test_environment_instances (
    test_environment_instance_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE test_environment_services (
    test_environment_service_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE test_environment_fixtures (
    test_environment_fixture_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE test_data_sets (
    test_data_set_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE http_api_snapshots (
    http_api_snapshot_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE http_api_operations (
    http_api_operation_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE http_api_differences (
    http_api_difference_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE java_api_snapshots (
    java_api_snapshot_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE java_api_elements (
    java_api_element_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE java_api_differences (
    java_api_difference_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE json_contracts (
    json_contract_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE json_golden_samples (
    json_golden_sample_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE json_contract_differences (
    json_contract_difference_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE message_contracts (
    message_contract_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE message_schema_snapshots (
    message_schema_snapshot_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE message_contract_differences (
    message_contract_difference_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE database_schema_snapshots (
    database_schema_snapshot_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE database_schema_objects (
    database_schema_object_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE database_schema_differences (
    database_schema_difference_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE database_migration_runs (
    database_migration_run_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE database_data_checks (
    database_data_check_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE transaction_scenarios (
    transaction_scenario_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE transaction_traces (
    transaction_trace_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE transaction_outcomes (
    transaction_outcome_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE transaction_differences (
    transaction_difference_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE performance_scenarios (
    performance_scenario_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE performance_runs (
    performance_run_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE performance_samples (
    performance_sample_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE performance_comparisons (
    performance_comparison_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE resource_usage_samples (
    resource_usage_sample_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE validation_findings (
    validation_finding_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE validation_exceptions (
    validation_exception_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE validation_suppressions (
    validation_suppression_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX validation_run_environment_unique ON validation_runs (migration_run_id, (payload ->> 'stage'), (payload ->> 'side'), (payload ->> 'attempt'));
CREATE UNIQUE INDEX validation_decision_policy_unique ON validation_decisions (migration_run_id, (payload ->> 'policyVersion'), (payload ->> 'baselineEnvironmentId'), (payload ->> 'migratedEnvironmentId'));
CREATE UNIQUE INDEX validation_environment_workspace_unique ON test_environment_instances ((payload ->> 'environmentId'), (payload ->> 'workspaceId'));
CREATE INDEX validation_findings_severity_idx ON validation_findings (migration_run_id, (payload ->> 'severity'));
CREATE INDEX test_case_result_identity_idx ON test_case_results (migration_run_id, (payload ->> 'testIdentity'));
