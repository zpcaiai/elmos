PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE multimodal_telemetry_subjects (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    subject_kind TEXT NOT NULL CHECK (subject_kind IN ('TASK','JOB','SESSION','ASSET','REQUEST')),
    subject_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    latest_estimate_sequence INTEGER NOT NULL DEFAULT 0 CHECK (latest_estimate_sequence >= 0),
    latest_trace_sequence INTEGER NOT NULL DEFAULT 0 CHECK (latest_trace_sequence >= 0),
    actuals_state TEXT NOT NULL CHECK (actuals_state IN ('NOT_RUN','PENDING','RECONCILED','UNKNOWN','BLOCKED')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, subject_kind, subject_id)
) WITHOUT ROWID;

CREATE TABLE multimodal_cost_estimates (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    subject_kind TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    estimate_sequence INTEGER NOT NULL CHECK (estimate_sequence >= 1),
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    estimate_json TEXT NOT NULL,
    estimate_digest TEXT NOT NULL CHECK (length(estimate_digest) = 64),
    result_state TEXT NOT NULL CHECK (result_state IN ('SUCCEEDED','PARTIAL','BLOCKED','FAILED')),
    result_code TEXT NOT NULL,
    calibration_version TEXT,
    estimated_cost TEXT,
    currency TEXT CHECK (currency IS NULL OR (length(currency) = 3 AND currency = upper(currency))),
    actuals_state TEXT NOT NULL CHECK (actuals_state IN ('NOT_RUN','PENDING','RECONCILED','UNKNOWN','BLOCKED')),
    provider_actuals_digest TEXT CHECK (provider_actuals_digest IS NULL OR length(provider_actuals_digest) = 64),
    provider_actuals_byte_count INTEGER CHECK (provider_actuals_byte_count IS NULL OR provider_actuals_byte_count >= 0),
    trace_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, subject_kind, subject_id, estimate_sequence),
    UNIQUE (tenant_id, project_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id, subject_kind, subject_id)
        REFERENCES multimodal_telemetry_subjects (tenant_id, project_id, subject_kind, subject_id)
) WITHOUT ROWID;

CREATE TABLE multimodal_cost_line_items (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    subject_kind TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    estimate_sequence INTEGER NOT NULL,
    stage_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    asset_id TEXT,
    provider TEXT NOT NULL,
    file_type TEXT NOT NULL,
    quantity TEXT NOT NULL,
    unit TEXT NOT NULL,
    unit_price TEXT NOT NULL,
    estimated_cost TEXT NOT NULL,
    actual_quantity TEXT,
    actual_cost TEXT,
    currency TEXT NOT NULL CHECK (length(currency) = 3 AND currency = upper(currency)),
    actual_evidence_digest TEXT CHECK (actual_evidence_digest IS NULL OR length(actual_evidence_digest) = 64),
    actual_evidence_byte_count INTEGER CHECK (actual_evidence_byte_count IS NULL OR actual_evidence_byte_count >= 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, subject_kind, subject_id, estimate_sequence, stage_id),
    FOREIGN KEY (tenant_id, project_id, subject_kind, subject_id, estimate_sequence)
        REFERENCES multimodal_cost_estimates
        (tenant_id, project_id, subject_kind, subject_id, estimate_sequence)
) WITHOUT ROWID;

CREATE TABLE multimodal_telemetry_traces (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    subject_kind TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    trace_sequence INTEGER NOT NULL CHECK (trace_sequence >= 1),
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    trace_id TEXT NOT NULL,
    trace_json TEXT NOT NULL,
    trace_digest TEXT NOT NULL CHECK (length(trace_digest) = 64),
    result_state TEXT NOT NULL CHECK (result_state IN ('SUCCEEDED','PARTIAL','BLOCKED','FAILED')),
    result_code TEXT NOT NULL,
    policy_version TEXT,
    missing_stage_count INTEGER NOT NULL CHECK (missing_stage_count >= 0),
    event_count INTEGER NOT NULL CHECK (event_count >= 0),
    actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, subject_kind, subject_id, trace_sequence),
    UNIQUE (tenant_id, project_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id, subject_kind, subject_id)
        REFERENCES multimodal_telemetry_subjects (tenant_id, project_id, subject_kind, subject_id)
) WITHOUT ROWID;

CREATE TABLE multimodal_telemetry_events (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    subject_kind TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    trace_sequence INTEGER NOT NULL,
    event_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    parent_event_id TEXT,
    event_type TEXT NOT NULL,
    stage TEXT,
    provider TEXT,
    file_type TEXT,
    status TEXT,
    error_code TEXT,
    event_json TEXT NOT NULL,
    event_digest TEXT NOT NULL CHECK (length(event_digest) = 64),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, trace_id, event_id),
    FOREIGN KEY (tenant_id, project_id, subject_kind, subject_id, trace_sequence)
        REFERENCES multimodal_telemetry_traces
        (tenant_id, project_id, subject_kind, subject_id, trace_sequence)
) WITHOUT ROWID;

CREATE INDEX multimodal_cost_subject_created_idx
    ON multimodal_cost_estimates
    (tenant_id, project_id, subject_kind, subject_id, created_at);
CREATE INDEX multimodal_telemetry_stage_status_idx
    ON multimodal_telemetry_events
    (tenant_id, project_id, stage, status, created_at);
CREATE INDEX multimodal_telemetry_provider_type_idx
    ON multimodal_telemetry_events
    (tenant_id, project_id, provider, file_type, created_at);

CREATE TRIGGER multimodal_telemetry_subject_delete_forbidden
BEFORE DELETE ON multimodal_telemetry_subjects
BEGIN
    SELECT RAISE(ABORT, 'telemetry subject deletion forbidden');
END;

CREATE TRIGGER multimodal_telemetry_subject_update_guard
BEFORE UPDATE ON multimodal_telemetry_subjects
WHEN NEW.tenant_id <> OLD.tenant_id
  OR NEW.project_id <> OLD.project_id
  OR NEW.subject_kind <> OLD.subject_kind
  OR NEW.subject_id <> OLD.subject_id
  OR NEW.version <> OLD.version + 1
  OR NEW.latest_estimate_sequence < OLD.latest_estimate_sequence
  OR NEW.latest_trace_sequence < OLD.latest_trace_sequence
BEGIN
    SELECT RAISE(ABORT, 'telemetry subject transition invalid');
END;

CREATE TRIGGER multimodal_cost_estimate_update_forbidden
BEFORE UPDATE ON multimodal_cost_estimates
BEGIN
    SELECT RAISE(ABORT, 'cost estimate immutable');
END;
CREATE TRIGGER multimodal_cost_estimate_delete_forbidden
BEFORE DELETE ON multimodal_cost_estimates
BEGIN
    SELECT RAISE(ABORT, 'cost estimate deletion forbidden');
END;
CREATE TRIGGER multimodal_cost_line_update_forbidden
BEFORE UPDATE ON multimodal_cost_line_items
BEGIN
    SELECT RAISE(ABORT, 'cost line immutable');
END;
CREATE TRIGGER multimodal_cost_line_delete_forbidden
BEFORE DELETE ON multimodal_cost_line_items
BEGIN
    SELECT RAISE(ABORT, 'cost line deletion forbidden');
END;
CREATE TRIGGER multimodal_trace_update_forbidden
BEFORE UPDATE ON multimodal_telemetry_traces
BEGIN
    SELECT RAISE(ABORT, 'telemetry trace immutable');
END;
CREATE TRIGGER multimodal_trace_delete_forbidden
BEFORE DELETE ON multimodal_telemetry_traces
BEGIN
    SELECT RAISE(ABORT, 'telemetry trace deletion forbidden');
END;
CREATE TRIGGER multimodal_event_update_forbidden
BEFORE UPDATE ON multimodal_telemetry_events
BEGIN
    SELECT RAISE(ABORT, 'telemetry event immutable');
END;
CREATE TRIGGER multimodal_event_delete_forbidden
BEFORE DELETE ON multimodal_telemetry_events
BEGIN
    SELECT RAISE(ABORT, 'telemetry event deletion forbidden');
END;

PRAGMA user_version = 21;
COMMIT;
