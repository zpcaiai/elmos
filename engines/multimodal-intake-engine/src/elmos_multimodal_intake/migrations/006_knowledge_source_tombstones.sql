PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS knowledge_source_tombstones (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    package_version TEXT NOT NULL,
    source_digest TEXT NOT NULL CHECK (length(source_digest) = 64),
    generation INTEGER NOT NULL CHECK (generation >= 1),
    record_count INTEGER NOT NULL CHECK (record_count >= 0),
    record_set_digest TEXT NOT NULL CHECK (length(record_set_digest) = 64),
    deletion_generation_digest TEXT NOT NULL CHECK (length(deletion_generation_digest) = 64),
    event_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, actor_id, branch, package_version, source_digest),
    FOREIGN KEY (tenant_id, project_id, actor_id, event_id)
        REFERENCES knowledge_outbox_events (tenant_id, project_id, actor_id, event_id)
);
CREATE INDEX IF NOT EXISTS knowledge_source_tombstones_generation_idx
    ON knowledge_source_tombstones (
        tenant_id, project_id, actor_id, branch, package_version, generation
    );

CREATE TABLE IF NOT EXISTS knowledge_rebuild_completions (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    rebuild_id TEXT NOT NULL,
    target TEXT NOT NULL CHECK (target IN ('content-index','project-memory')),
    cause_digest TEXT NOT NULL CHECK (length(cause_digest) = 64),
    rebuilt_digest TEXT NOT NULL CHECK (length(rebuilt_digest) = 64),
    record_count INTEGER NOT NULL CHECK (record_count >= 0),
    term_count INTEGER NOT NULL CHECK (term_count >= 0),
    completion_event_id TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, actor_id, rebuild_id),
    FOREIGN KEY (tenant_id, project_id, actor_id, rebuild_id)
        REFERENCES knowledge_rebuild_jobs (tenant_id, project_id, actor_id, rebuild_id),
    FOREIGN KEY (tenant_id, project_id, actor_id, completion_event_id)
        REFERENCES knowledge_outbox_events (tenant_id, project_id, actor_id, event_id)
);
CREATE INDEX IF NOT EXISTS knowledge_rebuild_completions_digest_idx
    ON knowledge_rebuild_completions (
        tenant_id, project_id, actor_id, target, rebuilt_digest
    );

PRAGMA user_version = 6;
COMMIT;
