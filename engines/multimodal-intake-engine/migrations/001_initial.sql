PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS project_acl (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    permission TEXT NOT NULL,
    granted_by TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, principal_id, permission)
);

CREATE TABLE IF NOT EXISTS skill_execution_receipts (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    skill TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    status TEXT NOT NULL CHECK (status IN ('IN_PROGRESS','COMPLETED')),
    owner_token TEXT,
    lease_expires_at TEXT,
    response_json TEXT,
    http_status INTEGER CHECK (http_status IS NULL OR http_status BETWEEN 200 AND 599),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, actor_id, skill, idempotency_key),
    CHECK (
        (status = 'IN_PROGRESS' AND owner_token IS NOT NULL AND lease_expires_at IS NOT NULL
            AND response_json IS NULL AND http_status IS NULL)
        OR
        (status = 'COMPLETED' AND owner_token IS NULL AND lease_expires_at IS NULL
            AND response_json IS NOT NULL AND http_status IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS skill_execution_receipts_created_idx
    ON skill_execution_receipts (tenant_id, project_id, created_at);
CREATE INDEX IF NOT EXISTS skill_execution_receipts_lease_idx
    ON skill_execution_receipts (status, lease_expires_at) WHERE status = 'IN_PROGRESS';

CREATE TABLE IF NOT EXISTS input_sessions (
    session_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    requested_role TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'DRAFT','UPLOADING','PROCESSING','READY','PARTIAL_READY',
        'NEEDS_REVIEW','QUARANTINED','FAILED','CANCELLED')),
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    trace_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, session_id),
    UNIQUE (tenant_id, project_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS input_sessions_scope_idx
    ON input_sessions (tenant_id, project_id, status, updated_at);

CREATE TABLE IF NOT EXISTS input_assets (
    asset_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    declared_media_type TEXT NOT NULL,
    detected_media_type TEXT,
    kind TEXT NOT NULL CHECK (kind IN (
        'TEXT','MARKDOWN','LOG','DOCX','PDF','IMAGE','AUDIO','ARCHIVE','UNKNOWN')),
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    sha256 TEXT CHECK (sha256 IS NULL OR length(sha256) = 64),
    cas_digest TEXT CHECK (cas_digest IS NULL OR length(cas_digest) = 64),
    status TEXT NOT NULL CHECK (status IN (
        'CREATED','UPLOADING','UPLOADED','PROCESSING','READY',
        'NEEDS_REVIEW','QUARANTINED','FAILED','DELETED')),
    security_decision TEXT CHECK (
        security_decision IS NULL OR security_decision IN ('ALLOW','NEEDS_REVIEW','QUARANTINE')),
    failure_code TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, asset_id),
    UNIQUE (tenant_id, project_id, session_id, asset_id),
    FOREIGN KEY (tenant_id, project_id, session_id)
        REFERENCES input_sessions (tenant_id, project_id, session_id)
);
CREATE INDEX IF NOT EXISTS input_assets_session_idx
    ON input_assets (tenant_id, project_id, session_id, status, created_at);

CREATE TABLE IF NOT EXISTS upload_sessions (
    upload_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    expected_size INTEGER NOT NULL CHECK (expected_size >= 0),
    expected_sha256 TEXT NOT NULL CHECK (length(expected_sha256) = 64),
    part_size INTEGER NOT NULL CHECK (part_size > 0),
    status TEXT NOT NULL CHECK (status IN ('OPEN','COMPLETED','ABORTED','EXPIRED','QUARANTINED')),
    received_bytes INTEGER NOT NULL DEFAULT 0 CHECK (received_bytes >= 0),
    commit_idempotency_key TEXT,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, upload_id),
    UNIQUE (tenant_id, project_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id, asset_id)
        REFERENCES input_assets (tenant_id, project_id, asset_id)
);
CREATE INDEX IF NOT EXISTS upload_sessions_expiry_idx
    ON upload_sessions (status, expires_at) WHERE status = 'OPEN';

CREATE TABLE IF NOT EXISTS upload_parts (
    upload_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    part_number INTEGER NOT NULL CHECK (part_number >= 0),
    idempotency_key TEXT NOT NULL,
    byte_offset INTEGER NOT NULL CHECK (byte_offset >= 0),
    byte_size INTEGER NOT NULL CHECK (byte_size > 0),
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    cas_digest TEXT NOT NULL CHECK (length(cas_digest) = 64),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, upload_id, part_number),
    UNIQUE (tenant_id, project_id, upload_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id, upload_id)
        REFERENCES upload_sessions (tenant_id, project_id, upload_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS security_findings (
    finding_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('ALLOW','NEEDS_REVIEW','QUARANTINE')),
    code TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id, project_id, asset_id)
        REFERENCES input_assets (tenant_id, project_id, asset_id)
);
CREATE INDEX IF NOT EXISTS security_findings_asset_idx
    ON security_findings (tenant_id, project_id, asset_id, created_at);

CREATE TABLE IF NOT EXISTS processing_jobs (
    job_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    status TEXT NOT NULL CHECK (status IN (
        'QUEUED','RUNNING','COMPLETED','PARTIAL','NEEDS_REVIEW',
        'BLOCKED','FAILED','CANCELLED')),
    stage TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 20),
    result_status TEXT NOT NULL CHECK (result_status IN (
        'PASSED','PARTIAL','NEEDS_REVIEW','NOT_RUN','BLOCKED','FAILED')),
    failure_code TEXT,
    lease_owner TEXT,
    lease_expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, job_id),
    UNIQUE (tenant_id, project_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id, session_id)
        REFERENCES input_sessions (tenant_id, project_id, session_id),
    CHECK (
        (status = 'RUNNING' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR
        (status <> 'RUNNING' AND lease_owner IS NULL AND lease_expires_at IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS processing_jobs_session_idx
    ON processing_jobs (tenant_id, project_id, session_id, status, updated_at);
CREATE INDEX IF NOT EXISTS processing_jobs_lease_idx
    ON processing_jobs (status, lease_expires_at) WHERE status = 'RUNNING';

CREATE TABLE IF NOT EXISTS processing_checkpoints (
    job_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    stage_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, job_id, stage_key),
    FOREIGN KEY (tenant_id, project_id, job_id)
        REFERENCES processing_jobs (tenant_id, project_id, job_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS content_blocks (
    block_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    asset_version INTEGER NOT NULL CHECK (asset_version >= 1),
    schema_version TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    kind TEXT NOT NULL CHECK (kind IN (
        'TEXT','HEADING','CODE','LOG','TABLE','IMAGE','AUDIO_SEGMENT','PAGE','REVIEW_NOTE')),
    text_content TEXT,
    payload_json TEXT NOT NULL,
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, block_id, asset_id),
    UNIQUE (tenant_id, project_id, asset_id, asset_version, ordinal),
    FOREIGN KEY (tenant_id, project_id, asset_id)
        REFERENCES input_assets (tenant_id, project_id, asset_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS source_anchors (
    anchor_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    block_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    locator_type TEXT NOT NULL,
    page_number INTEGER CHECK (page_number IS NULL OR page_number >= 1),
    paragraph_index INTEGER CHECK (paragraph_index IS NULL OR paragraph_index >= 0),
    line_start INTEGER CHECK (line_start IS NULL OR line_start >= 1),
    line_end INTEGER CHECK (line_end IS NULL OR line_end >= line_start),
    time_start_ms INTEGER CHECK (time_start_ms IS NULL OR time_start_ms >= 0),
    time_end_ms INTEGER CHECK (time_end_ms IS NULL OR time_end_ms >= time_start_ms),
    bbox_json TEXT,
    symbol TEXT,
    excerpt_sha256 TEXT CHECK (excerpt_sha256 IS NULL OR length(excerpt_sha256) = 64),
    created_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id, project_id, block_id, asset_id)
        REFERENCES content_blocks (tenant_id, project_id, block_id, asset_id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_id, asset_id)
        REFERENCES input_assets (tenant_id, project_id, asset_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS source_anchors_asset_idx
    ON source_anchors (tenant_id, project_id, asset_id, locator_type);

CREATE TABLE IF NOT EXISTS asset_parse_reports (
    report_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    asset_version INTEGER NOT NULL CHECK (asset_version >= 1),
    report_json TEXT NOT NULL,
    report_sha256 TEXT NOT NULL CHECK (length(report_sha256) = 64),
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, job_id, asset_id, source_sha256),
    FOREIGN KEY (tenant_id, project_id, job_id)
        REFERENCES processing_jobs (tenant_id, project_id, job_id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_id, asset_id)
        REFERENCES input_assets (tenant_id, project_id, asset_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS asset_parse_reports_latest_idx
    ON asset_parse_reports (tenant_id, project_id, asset_id, created_at DESC);

CREATE TABLE IF NOT EXISTS outbox_events (
    event_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE (tenant_id, project_id, event_id),
    UNIQUE (tenant_id, project_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS durable_transitions (
    transition_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 1),
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    from_state TEXT NOT NULL CHECK (from_state IN (
        'PENDING','RUNNING','PAUSED','FAILED_RETRYABLE','SUCCEEDED','FAILED_FINAL','CANCELLED')),
    target_state TEXT NOT NULL CHECK (target_state IN (
        'PENDING','RUNNING','PAUSED','FAILED_RETRYABLE','SUCCEEDED','FAILED_FINAL','CANCELLED')),
    event_json TEXT NOT NULL,
    event_sha256 TEXT NOT NULL CHECK (length(event_sha256) = 64),
    outbox_event_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, task_id, sequence_number),
    UNIQUE (tenant_id, project_id, task_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id, outbox_event_id)
        REFERENCES outbox_events (tenant_id, project_id, event_id)
);
CREATE INDEX IF NOT EXISTS durable_transitions_task_idx
    ON durable_transitions (tenant_id, project_id, task_id, sequence_number DESC);

PRAGMA user_version = 1;
COMMIT;
