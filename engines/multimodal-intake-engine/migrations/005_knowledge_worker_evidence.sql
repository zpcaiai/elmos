PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS knowledge_outbox_publications (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    delivery_receipt_json TEXT NOT NULL,
    delivery_receipt_digest TEXT NOT NULL CHECK (length(delivery_receipt_digest) = 64),
    published_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, actor_id, event_id),
    FOREIGN KEY (tenant_id, project_id, actor_id, event_id)
        REFERENCES knowledge_outbox_events (tenant_id, project_id, actor_id, event_id)
        ON DELETE CASCADE
);

PRAGMA user_version = 5;
COMMIT;
