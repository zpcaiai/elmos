CREATE TABLE health_check_runs (
    health_check_run_id varchar(64) PRIMARY KEY,
    organization_id varchar(64) NOT NULL REFERENCES organizations(organization_id),
    snapshot_id varchar(64) NOT NULL REFERENCES repository_snapshots(snapshot_id),
    scanner_version varchar(64) NOT NULL,
    policy_hash varchar(80) NOT NULL,
    status varchar(32) NOT NULL CHECK (status IN ('REQUESTED','RUNNING','PASS','FAIL','INCONCLUSIVE','FAILED')),
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    correlation_id varchar(128) NOT NULL,
    UNIQUE (snapshot_id, scanner_version, policy_hash)
);

CREATE TABLE health_project_modules (
    health_module_id varchar(64) PRIMARY KEY,
    health_check_run_id varchar(64) NOT NULL REFERENCES health_check_runs(health_check_run_id),
    module_path text NOT NULL,
    coordinates text NOT NULL,
    build_system varchar(32) NOT NULL,
    descriptor_hash varchar(80) NOT NULL,
    UNIQUE (health_check_run_id, module_path)
);

CREATE TABLE health_dependencies (
    health_dependency_id varchar(64) PRIMARY KEY,
    health_check_run_id varchar(64) NOT NULL REFERENCES health_check_runs(health_check_run_id),
    module_path text NOT NULL,
    group_id text NOT NULL,
    artifact_id text NOT NULL,
    version text,
    scope varchar(32) NOT NULL,
    direct boolean NOT NULL,
    resolution_status varchar(32) NOT NULL,
    UNIQUE NULLS NOT DISTINCT (health_check_run_id, module_path, group_id, artifact_id, version, scope, direct)
);

CREATE TABLE health_vulnerabilities (
    health_vulnerability_id varchar(64) PRIMARY KEY,
    health_check_run_id varchar(64) NOT NULL REFERENCES health_check_runs(health_check_run_id),
    advisory_id varchar(200) NOT NULL,
    dependency_coordinates text NOT NULL,
    severity varchar(16) NOT NULL,
    fixed_version text,
    advisory_url text NOT NULL,
    observed_at timestamptz NOT NULL,
    provider varchar(64) NOT NULL,
    UNIQUE (health_check_run_id, advisory_id, dependency_coordinates)
);

CREATE TABLE health_findings (
    health_finding_id varchar(64) PRIMARY KEY,
    health_check_run_id varchar(64) NOT NULL REFERENCES health_check_runs(health_check_run_id),
    finding_code varchar(128) NOT NULL,
    category varchar(64) NOT NULL,
    severity varchar(16) NOT NULL,
    evidence_status varchar(32) NOT NULL,
    location text NOT NULL,
    message text NOT NULL,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE health_public_apis (
    health_public_api_id varchar(64) PRIMARY KEY,
    health_check_run_id varchar(64) NOT NULL REFERENCES health_check_runs(health_check_run_id),
    api_kind varchar(32) NOT NULL,
    owner text NOT NULL,
    signature text NOT NULL,
    location text NOT NULL,
    UNIQUE (health_check_run_id, api_kind, owner, signature)
);

CREATE TABLE health_test_readiness (
    health_check_run_id varchar(64) PRIMARY KEY REFERENCES health_check_runs(health_check_run_id),
    production_files integer NOT NULL CHECK (production_files >= 0),
    test_files integer NOT NULL CHECK (test_files >= 0),
    junit_detected boolean NOT NULL,
    integration_tests_detected boolean NOT NULL,
    coverage_plugin_detected boolean NOT NULL,
    test_to_production_ratio numeric(12,6) NOT NULL CHECK (test_to_production_ratio >= 0),
    evidence_status varchar(32) NOT NULL
);

CREATE TABLE health_reports (
    health_report_id varchar(64) PRIMARY KEY,
    health_check_run_id varchar(64) NOT NULL UNIQUE REFERENCES health_check_runs(health_check_run_id),
    snapshot_id varchar(64) NOT NULL REFERENCES repository_snapshots(snapshot_id),
    health_score integer NOT NULL CHECK (health_score BETWEEN 0 AND 100),
    overall_risk varchar(16) NOT NULL,
    evidence_status varchar(32) NOT NULL,
    report_artifact_ref text NOT NULL,
    report_sha256 varchar(64) NOT NULL CHECK (report_sha256 ~ '^[0-9a-f]{64}$'),
    generated_at timestamptz NOT NULL
);

CREATE INDEX health_runs_org_snapshot_idx ON health_check_runs(organization_id, snapshot_id);
CREATE INDEX health_findings_run_severity_idx ON health_findings(health_check_run_id, severity);
CREATE INDEX health_dependencies_coordinates_idx ON health_dependencies(group_id, artifact_id, version);
