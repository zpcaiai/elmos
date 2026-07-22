-- ELMOS Batch 5. Append-only evidence records use JSONB for versioned payloads while stable keys remain queryable.

CREATE TABLE recipe_definitions (
    recipe_definition_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_versions (
    recipe_version_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_descriptors (
    recipe_descriptor_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_options (
    recipe_option_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_artifacts (
    recipe_artifact_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_artifact_hashes (
    recipe_artifact_hash_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_dependencies (
    recipe_dependency_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_compositions (
    recipe_composition_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_capabilities (
    recipe_capability_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_license_facts (
    recipe_license_fact_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_license_sources (
    recipe_license_source_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_license_policies (
    recipe_license_policy_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_license_decisions (
    recipe_license_decision_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_commercial_grants (
    recipe_commercial_grant_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_selections (
    recipe_selection_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_selection_candidates (
    recipe_selection_candidate_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_selection_rejections (
    recipe_selection_rejection_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_execution_manifests (
    recipe_execution_manifest_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_runs (
    recipe_run_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_cycle_runs (
    recipe_cycle_run_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_file_results (
    recipe_file_result_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_file_errors (
    recipe_file_error_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_run_statistics (
    recipe_run_statistic_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_data_tables (
    recipe_data_table_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_idempotence_runs (
    recipe_idempotence_run_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_fixpoint_results (
    recipe_fixpoint_result_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE custom_recipe_projects (
    custom_recipe_project_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE custom_recipe_versions (
    custom_recipe_version_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE custom_recipe_fixtures (
    custom_recipe_fixture_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE custom_recipe_generation_runs (
    custom_recipe_generation_run_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE patch_sets (
    patch_set_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE patch_segments (
    patch_segment_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE patch_file_changes (
    patch_file_change_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE change_attributions (
    change_attribution_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE patch_policy_results (
    patch_policy_result_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_test_suites (
    recipe_test_suite_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_test_cases (
    recipe_test_case_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_test_runs (
    recipe_test_run_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_regression_results (
    recipe_regression_result_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_promotions (
    recipe_promotion_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recipe_deprecations (
    recipe_deprecation_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX recipe_definitions_name_unique ON recipe_definitions ((payload ->> 'recipeName'));
ALTER TABLE recipe_execution_manifests ADD CONSTRAINT recipe_manifest_hash_unique UNIQUE (content_hash);
CREATE UNIQUE INDEX recipe_run_manifest_attempt_unique ON recipe_runs (migration_run_id, (payload ->> 'manifestId'), (payload ->> 'attempt'));
CREATE INDEX recipe_license_decision_context_idx ON recipe_license_decisions ((payload ->> 'executionContext'), status);
CREATE INDEX recipe_run_migration_status_idx ON recipe_runs (migration_run_id, status);
