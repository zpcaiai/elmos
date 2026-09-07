-- ELMOS Batch 8. Append-only evidence records use JSONB for versioned payloads while stable keys remain queryable.

CREATE TABLE delivery_runs (
    delivery_run_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE delivery_snapshots (
    delivery_snapshot_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE delivery_read_models (
    delivery_read_model_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE delivery_model_sections (
    delivery_model_section_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE report_definitions (
    report_definition_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE generated_reports (
    generated_report_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE report_artifacts (
    report_artifact_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE report_rendering_runs (
    report_rendering_run_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE risk_registers (
    risk_register_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE risk_items (
    risk_item_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE risk_item_links (
    risk_item_link_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE risk_exceptions (
    risk_exception_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE risk_acceptances (
    risk_acceptance_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE risk_compensating_controls (
    risk_compensating_control_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE risk_review_events (
    risk_review_event_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE scm_deliveries (
    scm_delivery_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE scm_branches (
    scm_branch_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE scm_commits (
    scm_commit_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE pull_request_deliveries (
    pull_request_delivery_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE merge_request_deliveries (
    merge_request_delivery_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE scm_review_requests (
    scm_review_request_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE scm_comments (
    scm_comment_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE check_definitions (
    check_definition_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE check_publications (
    check_publication_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE check_results (
    check_result_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE check_annotations (
    check_annotation_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE check_retry_requests (
    check_retry_request_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE evidence_packages (
    evidence_package_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE evidence_package_entries (
    evidence_package_entry_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE evidence_manifests (
    evidence_manifest_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE evidence_signatures (
    evidence_signature_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE artifact_provenance_records (
    artifact_provenance_record_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE artifact_attestations (
    artifact_attestation_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rollback_plans (
    rollback_plan_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rollback_steps (
    rollback_step_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rollback_preconditions (
    rollback_precondition_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rollback_commands (
    rollback_command_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rollback_validations (
    rollback_validation_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rollback_drills (
    rollback_drill_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE acceptance_packages (
    acceptance_package_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE acceptance_criteria (
    acceptance_criteria_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE acceptance_decisions (
    acceptance_decision_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE acceptance_signoffs (
    acceptance_signoff_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE delivery_closures (
    delivery_closure_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE delivery_retention_policies (
    delivery_retention_policy_id varchar(96) PRIMARY KEY,
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE delivery_snapshots ADD COLUMN delivery_snapshot_version integer NOT NULL DEFAULT 1 CHECK (delivery_snapshot_version > 0);
ALTER TABLE delivery_snapshots ADD CONSTRAINT delivery_snapshot_version_unique UNIQUE (migration_run_id, delivery_snapshot_version);
ALTER TABLE check_publications ADD COLUMN scm_provider varchar(16);
ALTER TABLE check_publications ADD COLUMN repository_id text;
ALTER TABLE check_publications ADD COLUMN head_commit_sha text;
ALTER TABLE check_publications ADD COLUMN check_definition_ref varchar(96);
ALTER TABLE check_publications ADD CONSTRAINT check_publication_head_unique UNIQUE (scm_provider, repository_id, head_commit_sha, check_definition_ref);
ALTER TABLE evidence_packages ADD COLUMN evidence_package_version integer NOT NULL DEFAULT 1 CHECK (evidence_package_version > 0);
ALTER TABLE evidence_packages ADD CONSTRAINT evidence_package_version_unique UNIQUE (migration_run_id, evidence_package_version);
ALTER TABLE rollback_plans ADD COLUMN rollback_plan_version integer NOT NULL DEFAULT 1 CHECK (rollback_plan_version > 0);
ALTER TABLE rollback_plans ADD CONSTRAINT rollback_plan_version_unique UNIQUE (migration_run_id, rollback_plan_version);
CREATE INDEX delivery_snapshot_status_idx ON delivery_snapshots (migration_run_id, status);
CREATE INDEX risk_item_severity_status_idx ON risk_items (migration_run_id, (payload ->> 'severity'), status);
CREATE INDEX acceptance_package_status_idx ON acceptance_packages (migration_run_id, status);
