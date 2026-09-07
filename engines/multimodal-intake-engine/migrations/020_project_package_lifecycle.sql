BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS project_package_sessions (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('OPEN','PARTIAL','FINALIZED','ABORTED')),
    expected_entry_count INTEGER NOT NULL CHECK (expected_entry_count BETWEEN 0 AND 100000),
    accepted_entry_count INTEGER NOT NULL DEFAULT 0 CHECK (accepted_entry_count BETWEEN 0 AND 100000),
    next_chunk_index INTEGER NOT NULL DEFAULT 0 CHECK (next_chunk_index >= 0),
    generation INTEGER NOT NULL DEFAULT 1 CHECK (generation >= 1),
    manifest_version INTEGER,
    manifest_digest TEXT,
    merkle_root TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, session_id)
);

CREATE TABLE IF NOT EXISTS project_package_chunks (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    entry_count INTEGER NOT NULL CHECK (entry_count BETWEEN 1 AND 1000),
    chunk_digest TEXT NOT NULL CHECK (length(chunk_digest) = 64),
    entries_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, session_id, chunk_index),
    FOREIGN KEY (tenant_id, project_id, session_id)
      REFERENCES project_package_sessions(tenant_id, project_id, session_id)
);

CREATE TABLE IF NOT EXISTS project_package_versions (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    package_version INTEGER NOT NULL CHECK (package_version >= 1),
    parent_version INTEGER,
    state TEXT NOT NULL CHECK (state IN ('ACTIVE','SUPERSEDED','ROLLED_BACK')),
    entry_count INTEGER NOT NULL CHECK (entry_count BETWEEN 0 AND 100000),
    manifest_digest TEXT NOT NULL CHECK (length(manifest_digest) = 64),
    merkle_root TEXT NOT NULL CHECK (length(merkle_root) = 64),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, package_version),
    UNIQUE (tenant_id, project_id, manifest_digest)
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_project_package_version
ON project_package_versions(tenant_id, project_id) WHERE state = 'ACTIVE';

CREATE TABLE IF NOT EXISTS project_package_entries (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    package_version INTEGER NOT NULL,
    path TEXT NOT NULL,
    entry_digest TEXT NOT NULL CHECK (length(entry_digest) = 64),
    content_digest TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    kind TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('PRIMARY','REFERENCE','IGNORE')),
    model_read_allowed INTEGER NOT NULL CHECK (model_read_allowed IN (0,1)),
    security_state TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    override_version INTEGER NOT NULL DEFAULT 0 CHECK (override_version >= 0),
    PRIMARY KEY (tenant_id, project_id, package_version, path),
    FOREIGN KEY (tenant_id, project_id, package_version)
      REFERENCES project_package_versions(tenant_id, project_id, package_version)
);

CREATE TABLE IF NOT EXISTS project_package_override_audit (
    audit_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    package_version INTEGER NOT NULL,
    path TEXT NOT NULL,
    audit_kind TEXT NOT NULL CHECK (audit_kind IN ('OVERRIDE','UNDO')),
    prior_role TEXT NOT NULL,
    prior_model_read_allowed INTEGER NOT NULL,
    new_role TEXT NOT NULL,
    new_model_read_allowed INTEGER NOT NULL,
    prior_override_version INTEGER NOT NULL,
    new_override_version INTEGER NOT NULL,
    reason TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    undone_audit_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id, project_id, package_version, path)
      REFERENCES project_package_entries(tenant_id, project_id, package_version, path)
);

CREATE TABLE IF NOT EXISTS project_package_upload_files (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    path TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    content_digest TEXT NOT NULL,
    part_size INTEGER NOT NULL CHECK (part_size BETWEEN 65536 AND 16777216),
    total_parts INTEGER NOT NULL CHECK (total_parts >= 0),
    confirmed_parts INTEGER NOT NULL DEFAULT 0 CHECK (confirmed_parts >= 0),
    state TEXT NOT NULL CHECK (state IN ('NEGOTIATED','PARTIAL','COMPLETE')),
    PRIMARY KEY (tenant_id, project_id, session_id, path),
    FOREIGN KEY (tenant_id, project_id, session_id)
      REFERENCES project_package_sessions(tenant_id, project_id, session_id)
);

CREATE TABLE IF NOT EXISTS project_package_upload_parts (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    path TEXT NOT NULL,
    part_number INTEGER NOT NULL CHECK (part_number >= 0),
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    part_digest TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, session_id, path, part_number),
    FOREIGN KEY (tenant_id, project_id, session_id, path)
      REFERENCES project_package_upload_files(tenant_id, project_id, session_id, path)
);

CREATE TABLE IF NOT EXISTS project_package_artifacts (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    package_version INTEGER NOT NULL,
    artifact_kind TEXT NOT NULL,
    artifact_version INTEGER NOT NULL CHECK (artifact_version >= 1),
    state TEXT NOT NULL CHECK (state IN ('ACTIVE','SUPERSEDED','ROLLED_BACK')),
    result_state TEXT NOT NULL CHECK (result_state IN ('ACTIVE','PARTIAL')),
    input_digest TEXT NOT NULL,
    artifact_digest TEXT NOT NULL,
    artifact_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, package_version, artifact_kind, artifact_version),
    FOREIGN KEY (tenant_id, project_id, package_version)
      REFERENCES project_package_versions(tenant_id, project_id, package_version)
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_project_package_artifact
ON project_package_artifacts(tenant_id, project_id, package_version, artifact_kind)
WHERE state = 'ACTIVE';

PRAGMA user_version = 20;
COMMIT;
