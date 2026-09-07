-- Extensions the ELMOS implementation requires on top of the package's
-- reference schema (0001_init.sql). Kept as a separate migration so the
-- reference file stays byte-identical to the skills package.

ALTER TABLE runs ADD COLUMN IF NOT EXISTS trust_namespace text NOT NULL DEFAULT 'branch';
ALTER TABLE runs ADD COLUMN IF NOT EXISTS journal_sequence bigint NOT NULL DEFAULT 0;

ALTER TABLE run_nodes ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz;
ALTER TABLE run_nodes ADD COLUMN IF NOT EXISTS retries integer NOT NULL DEFAULT 0;
ALTER TABLE run_nodes ADD COLUMN IF NOT EXISTS retry_budget integer NOT NULL DEFAULT 3;
ALTER TABLE run_nodes ADD COLUMN IF NOT EXISTS outcome text;

ALTER TABLE action_cache_entries ADD COLUMN IF NOT EXISTS entry_kind text NOT NULL DEFAULT 'POSITIVE';
ALTER TABLE action_cache_entries ADD COLUMN IF NOT EXISTS failure_code text;
ALTER TABLE action_cache_entries ADD COLUMN IF NOT EXISTS saved_wall_ms bigint NOT NULL DEFAULT 0;
ALTER TABLE action_cache_entries ADD COLUMN IF NOT EXISTS quarantine_reason text;
ALTER TABLE action_cache_entries
  DROP CONSTRAINT IF EXISTS action_cache_entries_entry_kind_check;
ALTER TABLE action_cache_entries
  ADD CONSTRAINT action_cache_entries_entry_kind_check CHECK (entry_kind IN ('POSITIVE','NEGATIVE'));

ALTER TABLE staged_files ADD COLUMN IF NOT EXISTS overwrite_policy text NOT NULL DEFAULT 'reject';
ALTER TABLE staged_files ADD COLUMN IF NOT EXISTS ownership text NOT NULL DEFAULT 'GENERATED';
ALTER TABLE staged_files ADD COLUMN IF NOT EXISTS mode integer NOT NULL DEFAULT 420;

CREATE UNIQUE INDEX IF NOT EXISTS uq_staged_live_path
  ON staged_files (run_id, logical_path)
  WHERE status IN ('RESERVED','WRITING','SEALED','CAS_PROMOTED','TREE_INCLUDED','PUBLISHED');

CREATE TABLE IF NOT EXISTS file_trees (
  tenant_id        text NOT NULL,
  tree_digest      text NOT NULL,
  run_id           text NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  manifest_digest  text NOT NULL,
  entry_count      integer NOT NULL,
  total_bytes      bigint NOT NULL,
  validation_level text NOT NULL,
  evidence_digest  text,
  previous_tree    text,
  status           text NOT NULL CHECK (status IN ('CANDIDATE','PUBLISHED','SUPERSEDED','ROLLED_BACK')),
  created_at       timestamptz NOT NULL DEFAULT now(),
  published_at     timestamptz,
  PRIMARY KEY (tenant_id, tree_digest)
);

CREATE TABLE IF NOT EXISTS certificates (
  certificate_id   text PRIMARY KEY,
  tenant_id        text NOT NULL,
  scope_digest     text NOT NULL,
  tree_digest      text NOT NULL,
  evidence_digest  text NOT NULL,
  validation_level text NOT NULL,
  signature        text NOT NULL,
  issuer           text NOT NULL,
  status           text NOT NULL CHECK (status IN ('VALID','REVOKED','EXPIRED')),
  issued_at        double precision NOT NULL,
  expires_at       double precision NOT NULL,
  limitations      jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS revocations (
  revocation_id text PRIMARY KEY,
  tenant_id     text NOT NULL,
  subject_kind  text NOT NULL,
  subject_id    text NOT NULL,
  reason        text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, subject_kind, subject_id)
);

CREATE TABLE IF NOT EXISTS gc_plans (
  plan_id    text PRIMARY KEY,
  tenant_id  text NOT NULL,
  status     text NOT NULL CHECK (status IN ('DRY_RUN','APPROVED','APPLIED','ABANDONED')),
  payload    jsonb NOT NULL,
  created_at double precision NOT NULL,
  applied_at double precision
);

CREATE TABLE IF NOT EXISTS gc_receipts (
  plan_id    text NOT NULL REFERENCES gc_plans(plan_id) ON DELETE CASCADE,
  digest     text NOT NULL,
  outcome    text NOT NULL CHECK (outcome IN ('DELETED','ALREADY_ABSENT','PROTECTED','FAILED')),
  detail     text,
  created_at double precision NOT NULL,
  PRIMARY KEY (plan_id, digest)
);

CREATE TABLE IF NOT EXISTS idempotency_records (
  tenant_id       text NOT NULL,
  idempotency_key text NOT NULL,
  operation       text NOT NULL,
  request_digest  text NOT NULL,
  response        jsonb NOT NULL,
  created_at      double precision NOT NULL,
  PRIMARY KEY (tenant_id, idempotency_key)
);

ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS tenant_id text NOT NULL DEFAULT '';
ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_artifact_refs_target ON artifact_refs (tenant_id, target_digest);
CREATE INDEX IF NOT EXISTS idx_action_cache_result ON action_cache_entries (tenant_id, result_manifest_digest);
CREATE INDEX IF NOT EXISTS idx_staged_path ON staged_files (run_id, logical_path);
CREATE INDEX IF NOT EXISTS idx_pins_source ON pins (tenant_id, source_kind, source_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_node ON checkpoints (run_id, node_id, attempt, sequence);
