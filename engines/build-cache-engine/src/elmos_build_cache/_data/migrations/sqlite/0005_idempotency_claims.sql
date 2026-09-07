-- Crash-safe idempotency ownership. Existing v1.1/v1.2 rows are complete
-- replay records; new requests first claim PENDING and only the fenced owner
-- may publish the COMPLETE response.

ALTER TABLE idempotency_records
  ADD COLUMN state TEXT NOT NULL DEFAULT 'COMPLETE'
  CHECK (state IN ('PENDING', 'COMPLETE'));

ALTER TABLE idempotency_records
  ADD COLUMN owner_token TEXT NOT NULL DEFAULT 'legacy-complete';

ALTER TABLE idempotency_records
  ADD COLUMN fence INTEGER NOT NULL DEFAULT 0 CHECK (fence >= 0);

ALTER TABLE idempotency_records
  ADD COLUMN updated_at REAL NOT NULL DEFAULT 0;

ALTER TABLE idempotency_records
  ADD COLUMN completed_at REAL;

ALTER TABLE idempotency_records
  ADD COLUMN reconciled_by TEXT;

CREATE INDEX IF NOT EXISTS idx_idempotency_state
  ON idempotency_records (tenant_id, state, updated_at);
