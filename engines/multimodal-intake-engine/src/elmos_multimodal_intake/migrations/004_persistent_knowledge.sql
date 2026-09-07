PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS knowledge_documents (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    package_version TEXT NOT NULL,
    document_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    status TEXT NOT NULL CHECK (status IN ('CURRENT','SUPERSEDED','DELETED')),
    text_content TEXT NOT NULL,
    content_digest TEXT NOT NULL CHECK (length(content_digest) = 64),
    source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
    source_anchor_json TEXT NOT NULL,
    source_anchor_digest TEXT NOT NULL CHECK (length(source_anchor_digest) = 64),
    required_permissions_json TEXT NOT NULL,
    required_permissions_digest TEXT NOT NULL CHECK (length(required_permissions_digest) = 64),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (
        tenant_id, project_id, actor_id, branch, package_version, document_id, version
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS knowledge_documents_current_idx
    ON knowledge_documents (
        tenant_id, project_id, actor_id, branch, package_version, document_id
    ) WHERE status = 'CURRENT';
CREATE INDEX IF NOT EXISTS knowledge_documents_source_idx
    ON knowledge_documents (
        tenant_id, project_id, actor_id, branch, package_version, source_digest, status
    );

CREATE TABLE IF NOT EXISTS knowledge_document_terms (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    package_version TEXT NOT NULL,
    document_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    term TEXT NOT NULL CHECK (length(term) BETWEEN 2 AND 128),
    PRIMARY KEY (
        tenant_id, project_id, actor_id, branch, package_version, document_id, version, term
    ),
    FOREIGN KEY (
        tenant_id, project_id, actor_id, branch, package_version, document_id, version
    ) REFERENCES knowledge_documents (
        tenant_id, project_id, actor_id, branch, package_version, document_id, version
    ) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS knowledge_document_terms_lookup_idx
    ON knowledge_document_terms (
        tenant_id, project_id, actor_id, branch, package_version, term
    );

CREATE TABLE IF NOT EXISTS project_memory_records (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    package_version TEXT NOT NULL,
    memory_key TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    status TEXT NOT NULL CHECK (status IN ('CURRENT','SUPERSEDED','DELETED')),
    memory_kind TEXT NOT NULL CHECK (memory_kind IN (
        'FACT','DECISION','REQUIREMENT','PREFERENCE','TASK_STATE','TEST_EVIDENCE'
    )),
    semantic_state TEXT NOT NULL CHECK (semantic_state IN (
        'ACTIVE','REJECTED','EXPIRED','CONFLICTING'
    )),
    value_json TEXT NOT NULL,
    value_digest TEXT NOT NULL CHECK (length(value_digest) = 64),
    source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
    source_anchor_json TEXT NOT NULL,
    source_anchor_digest TEXT NOT NULL CHECK (length(source_anchor_digest) = 64),
    required_permissions_json TEXT NOT NULL,
    required_permissions_digest TEXT NOT NULL CHECK (length(required_permissions_digest) = 64),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (
        tenant_id, project_id, actor_id, branch, package_version, memory_key, version
    ),
    UNIQUE (tenant_id, project_id, actor_id, branch, package_version, memory_id, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS project_memory_current_idx
    ON project_memory_records (
        tenant_id, project_id, actor_id, branch, package_version, memory_key
    ) WHERE status = 'CURRENT';
CREATE INDEX IF NOT EXISTS project_memory_source_idx
    ON project_memory_records (
        tenant_id, project_id, actor_id, branch, package_version, source_digest, status
    );

CREATE TABLE IF NOT EXISTS project_memory_terms (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    package_version TEXT NOT NULL,
    memory_key TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    term TEXT NOT NULL CHECK (length(term) BETWEEN 2 AND 128),
    PRIMARY KEY (
        tenant_id, project_id, actor_id, branch, package_version, memory_key, version, term
    ),
    FOREIGN KEY (
        tenant_id, project_id, actor_id, branch, package_version, memory_key, version
    ) REFERENCES project_memory_records (
        tenant_id, project_id, actor_id, branch, package_version, memory_key, version
    ) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS project_memory_terms_lookup_idx
    ON project_memory_terms (
        tenant_id, project_id, actor_id, branch, package_version, term
    );

CREATE TABLE IF NOT EXISTS knowledge_operation_receipts (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    response_json TEXT NOT NULL,
    response_digest TEXT NOT NULL CHECK (length(response_digest) = 64),
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, actor_id, operation, idempotency_key)
);

CREATE TABLE IF NOT EXISTS knowledge_rebuild_jobs (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    package_version TEXT NOT NULL,
    rebuild_id TEXT NOT NULL,
    target TEXT NOT NULL CHECK (target IN ('content-index','project-memory')),
    cause_digest TEXT NOT NULL CHECK (length(cause_digest) = 64),
    status TEXT NOT NULL CHECK (status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')),
    attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    failure_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, actor_id, rebuild_id),
    UNIQUE (tenant_id, project_id, actor_id, branch, package_version, target, cause_digest)
);
CREATE INDEX IF NOT EXISTS knowledge_rebuild_pending_idx
    ON knowledge_rebuild_jobs (
        tenant_id, project_id, actor_id, branch, package_version, status, created_at
    );

CREATE TABLE IF NOT EXISTS knowledge_outbox_events (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_digest TEXT NOT NULL CHECK (length(payload_digest) = 64),
    idempotency_key TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    published_at TEXT,
    PRIMARY KEY (tenant_id, project_id, actor_id, event_id),
    UNIQUE (tenant_id, project_id, actor_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS knowledge_outbox_unpublished_idx
    ON knowledge_outbox_events (tenant_id, project_id, actor_id, occurred_at)
    WHERE published_at IS NULL;

PRAGMA user_version = 4;
COMMIT;
