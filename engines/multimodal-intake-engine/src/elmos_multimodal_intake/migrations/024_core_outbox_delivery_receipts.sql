PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE core_outbox_delivery_receipts (
    event_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL CHECK (
        typeof(actor_id) = 'text'
        AND length(actor_id) BETWEEN 1 AND 200
    ),
    payload_digest TEXT NOT NULL CHECK (
        length(payload_digest) = 64
        AND payload_digest NOT GLOB '*[^0-9a-f]*'
    ),
    transport TEXT NOT NULL,
    delivery_id TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    receipt_digest TEXT NOT NULL CHECK (
        length(receipt_digest) = 64
        AND receipt_digest NOT GLOB '*[^0-9a-f]*'
    ),
    verified_response_digest TEXT NOT NULL CHECK (
        length(verified_response_digest) = 64
        AND verified_response_digest NOT GLOB '*[^0-9a-f]*'
    ),
    delivered_at TEXT NOT NULL,
    publisher_capability_id TEXT NOT NULL,
    response_verifier_capability_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, transport, delivery_id),
    FOREIGN KEY (tenant_id, project_id, event_id)
        REFERENCES outbox_events (tenant_id, project_id, event_id)
);
CREATE INDEX core_outbox_delivery_scope_idx
    ON core_outbox_delivery_receipts (tenant_id, project_id, delivered_at, event_id);

CREATE TRIGGER core_outbox_delivery_receipts_no_update
BEFORE UPDATE ON core_outbox_delivery_receipts
BEGIN
    SELECT RAISE(ABORT, 'core outbox delivery receipt immutable');
END;

CREATE TRIGGER core_outbox_delivery_receipts_no_delete
BEFORE DELETE ON core_outbox_delivery_receipts
BEGIN
    SELECT RAISE(ABORT, 'core outbox delivery receipt immutable');
END;

PRAGMA user_version = 24;
COMMIT;
