PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE knowledge_outbox_delivery_states (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload_digest TEXT NOT NULL CHECK (length(payload_digest) = 64),
    phase TEXT NOT NULL CHECK (phase IN (
        'PENDING','CLAIMED','DISPATCHING','UNKNOWN','PUBLISHED','BLOCKED'
    )),
    attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt BETWEEN 0 AND 10),
    claim_token_digest TEXT CHECK (
        claim_token_digest IS NULL OR length(claim_token_digest) = 64
    ),
    executor_id TEXT,
    lease_expires_at TEXT,
    last_claim_token_digest TEXT CHECK (
        last_claim_token_digest IS NULL OR length(last_claim_token_digest) = 64
    ),
    last_executor_id TEXT,
    last_error_code TEXT,
    transport_receipt_json TEXT,
    transport_receipt_digest TEXT CHECK (
        transport_receipt_digest IS NULL OR length(transport_receipt_digest) = 64
    ),
    reconciliation_receipt_json TEXT,
    reconciliation_receipt_digest TEXT CHECK (
        reconciliation_receipt_digest IS NULL OR length(reconciliation_receipt_digest) = 64
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, actor_id, event_id),
    FOREIGN KEY (tenant_id, project_id, actor_id, event_id)
        REFERENCES knowledge_outbox_events (tenant_id, project_id, actor_id, event_id)
        ON DELETE CASCADE,
    CHECK (
        (phase IN ('CLAIMED','DISPATCHING')
            AND claim_token_digest IS NOT NULL
            AND executor_id IS NOT NULL
            AND lease_expires_at IS NOT NULL)
        OR
        (phase NOT IN ('CLAIMED','DISPATCHING')
            AND claim_token_digest IS NULL
            AND executor_id IS NULL
            AND lease_expires_at IS NULL)
    ),
    CHECK (
        (transport_receipt_json IS NULL AND transport_receipt_digest IS NULL)
        OR
        (transport_receipt_json IS NOT NULL AND transport_receipt_digest IS NOT NULL)
    ),
    CHECK (
        (reconciliation_receipt_json IS NULL AND reconciliation_receipt_digest IS NULL)
        OR
        (reconciliation_receipt_json IS NOT NULL
            AND reconciliation_receipt_digest IS NOT NULL)
    )
);
CREATE INDEX knowledge_outbox_delivery_phase_idx
    ON knowledge_outbox_delivery_states (
        tenant_id, project_id, actor_id, phase, updated_at, event_id
    );

INSERT INTO knowledge_outbox_delivery_states (
    tenant_id,project_id,actor_id,event_id,event_type,aggregate_id,payload_digest,
    phase,attempt,claim_token_digest,executor_id,lease_expires_at,
    last_claim_token_digest,last_executor_id,last_error_code,
    transport_receipt_json,transport_receipt_digest,
    reconciliation_receipt_json,reconciliation_receipt_digest,created_at,updated_at
)
SELECT tenant_id,project_id,actor_id,event_id,event_type,aggregate_id,payload_digest,
       CASE WHEN published_at IS NULL THEN 'PENDING' ELSE 'PUBLISHED' END,
       0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,occurred_at,
       COALESCE(published_at,occurred_at)
  FROM knowledge_outbox_events;

PRAGMA user_version = 8;
COMMIT;
