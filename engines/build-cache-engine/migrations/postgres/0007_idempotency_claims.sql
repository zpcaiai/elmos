-- Crash-safe idempotency ownership. Existing rows are complete replay
-- records; new requests must be claimed before a side effect is attempted.

ALTER TABLE idempotency_records
  ADD COLUMN IF NOT EXISTS state text NOT NULL DEFAULT 'COMPLETE'
  CHECK (state IN ('PENDING', 'COMPLETE'));

ALTER TABLE idempotency_records
  ADD COLUMN IF NOT EXISTS owner_token text NOT NULL DEFAULT 'legacy-complete';

ALTER TABLE idempotency_records
  ADD COLUMN IF NOT EXISTS fence bigint NOT NULL DEFAULT 0 CHECK (fence >= 0);

ALTER TABLE idempotency_records
  ADD COLUMN IF NOT EXISTS updated_at double precision NOT NULL DEFAULT 0;

ALTER TABLE idempotency_records
  ADD COLUMN IF NOT EXISTS completed_at double precision;

ALTER TABLE idempotency_records
  ADD COLUMN IF NOT EXISTS reconciled_by text;

CREATE INDEX IF NOT EXISTS idx_idempotency_state
  ON idempotency_records (tenant_id, state, updated_at);
