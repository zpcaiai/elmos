CREATE TABLE migration_target_profiles (
    migration_plan_id varchar(64) NOT NULL,
    plan_version integer NOT NULL,
    java_version integer NOT NULL CHECK (java_version IN (17,21,25)),
    spring_boot_line text,
    jakarta_namespace varchar(32) NOT NULL,
    build_tool_strategy varchar(64) NOT NULL,
    evidence_status varchar(32) NOT NULL,
    assumptions jsonb NOT NULL DEFAULT '[]'::jsonb,
    PRIMARY KEY (migration_plan_id, plan_version),
    FOREIGN KEY (migration_plan_id, plan_version) REFERENCES migration_plans(migration_plan_id, plan_version)
);

CREATE TABLE migration_plan_revisions (
    migration_plan_id varchar(64) NOT NULL,
    plan_version integer NOT NULL,
    health_report_id varchar(64) NOT NULL REFERENCES health_reports(health_report_id),
    compatibility_matrix_version varchar(64) NOT NULL,
    status varchar(32) NOT NULL CHECK (status IN ('READY','NEEDS_APPROVAL','BLOCKED')),
    plan_artifact_ref text NOT NULL,
    plan_sha256 varchar(64) NOT NULL CHECK (plan_sha256 ~ '^[0-9a-f]{64}$'),
    generated_at timestamptz NOT NULL,
    PRIMARY KEY (migration_plan_id, plan_version),
    FOREIGN KEY (migration_plan_id, plan_version) REFERENCES migration_plans(migration_plan_id, plan_version)
);

CREATE TABLE compatibility_decisions (
    compatibility_decision_id varchar(64) PRIMARY KEY,
    migration_plan_id varchar(64) NOT NULL,
    plan_version integer NOT NULL,
    component varchar(64) NOT NULL,
    source_version text,
    target_version text,
    compatible boolean NOT NULL,
    migration_required boolean NOT NULL,
    evidence_status varchar(32) NOT NULL,
    rationale text NOT NULL,
    matrix_version varchar(64) NOT NULL,
    FOREIGN KEY (migration_plan_id, plan_version) REFERENCES migration_plan_revisions(migration_plan_id, plan_version),
    UNIQUE (migration_plan_id, plan_version, component)
);

CREATE TABLE migration_plan_steps (
    migration_plan_id varchar(64) NOT NULL,
    plan_version integer NOT NULL,
    step_id varchar(32) NOT NULL,
    step_type varchar(64) NOT NULL,
    objective text NOT NULL,
    risk varchar(16) NOT NULL,
    automation_score integer NOT NULL CHECK (automation_score BETWEEN 0 AND 100),
    approval_required boolean NOT NULL,
    required_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    PRIMARY KEY (migration_plan_id, plan_version, step_id),
    FOREIGN KEY (migration_plan_id, plan_version) REFERENCES migration_plan_revisions(migration_plan_id, plan_version)
);

CREATE TABLE migration_step_dependencies (
    migration_plan_id varchar(64) NOT NULL,
    plan_version integer NOT NULL,
    step_id varchar(32) NOT NULL,
    depends_on_step_id varchar(32) NOT NULL,
    PRIMARY KEY (migration_plan_id, plan_version, step_id, depends_on_step_id),
    FOREIGN KEY (migration_plan_id, plan_version, step_id) REFERENCES migration_plan_steps(migration_plan_id, plan_version, step_id),
    FOREIGN KEY (migration_plan_id, plan_version, depends_on_step_id) REFERENCES migration_plan_steps(migration_plan_id, plan_version, step_id),
    CHECK (step_id <> depends_on_step_id)
);

CREATE TABLE migration_risk_scores (
    migration_plan_id varchar(64) NOT NULL,
    plan_version integer NOT NULL,
    score_type varchar(32) NOT NULL CHECK (score_type IN ('MIGRATION_RISK','AUTOMATION')),
    score integer NOT NULL CHECK (score BETWEEN 0 AND 100),
    factors jsonb NOT NULL,
    rationale jsonb NOT NULL,
    PRIMARY KEY (migration_plan_id, plan_version, score_type),
    FOREIGN KEY (migration_plan_id, plan_version) REFERENCES migration_plan_revisions(migration_plan_id, plan_version)
);

CREATE TABLE migration_effort_estimates (
    migration_plan_id varchar(64) NOT NULL,
    plan_version integer NOT NULL,
    step_id varchar(32),
    minimum_person_days integer NOT NULL CHECK (minimum_person_days >= 0),
    likely_person_days integer NOT NULL CHECK (likely_person_days >= minimum_person_days),
    maximum_person_days integer NOT NULL CHECK (maximum_person_days >= likely_person_days),
    confidence varchar(16) NOT NULL,
    assumptions jsonb NOT NULL,
    estimate_key varchar(64) NOT NULL,
    PRIMARY KEY (migration_plan_id, plan_version, estimate_key),
    FOREIGN KEY (migration_plan_id, plan_version) REFERENCES migration_plan_revisions(migration_plan_id, plan_version)
);

CREATE TABLE migration_waves (
    migration_plan_id varchar(64) NOT NULL,
    plan_version integer NOT NULL,
    wave_number integer NOT NULL CHECK (wave_number > 0),
    exit_criterion text NOT NULL,
    PRIMARY KEY (migration_plan_id, plan_version, wave_number),
    FOREIGN KEY (migration_plan_id, plan_version) REFERENCES migration_plan_revisions(migration_plan_id, plan_version)
);

CREATE TABLE migration_wave_steps (
    migration_plan_id varchar(64) NOT NULL,
    plan_version integer NOT NULL,
    wave_number integer NOT NULL,
    step_id varchar(32) NOT NULL,
    PRIMARY KEY (migration_plan_id, plan_version, wave_number, step_id),
    FOREIGN KEY (migration_plan_id, plan_version, wave_number) REFERENCES migration_waves(migration_plan_id, plan_version, wave_number),
    FOREIGN KEY (migration_plan_id, plan_version, step_id) REFERENCES migration_plan_steps(migration_plan_id, plan_version, step_id)
);

CREATE TABLE migration_approval_gates (
    approval_gate_id varchar(64) PRIMARY KEY,
    migration_plan_id varchar(64) NOT NULL,
    plan_version integer NOT NULL,
    gate_type varchar(32) NOT NULL,
    before_step_id varchar(32) NOT NULL,
    reason text NOT NULL,
    required_evidence jsonb NOT NULL,
    blocking boolean NOT NULL,
    decision varchar(32) NOT NULL DEFAULT 'PENDING',
    decided_by text,
    decided_at timestamptz,
    FOREIGN KEY (migration_plan_id, plan_version) REFERENCES migration_plan_revisions(migration_plan_id, plan_version),
    FOREIGN KEY (migration_plan_id, plan_version, before_step_id) REFERENCES migration_plan_steps(migration_plan_id, plan_version, step_id)
);

CREATE INDEX migration_plan_revision_health_idx ON migration_plan_revisions(health_report_id);
CREATE INDEX migration_approval_pending_idx ON migration_approval_gates(migration_plan_id, plan_version, decision);

