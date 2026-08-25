-- ELMOS cache/staging local-profile metadata schema (SQLite, WAL).
-- Mirrors migrations/postgres/0001_init.sql: UUID -> TEXT, JSONB -> TEXT
-- holding canonical JSON, timestamptz -> TEXT holding RFC3339 UTC.
-- Artifact bytes never live here; only metadata, states and reference edges.

CREATE TABLE IF NOT EXISTS tenants (
  tenant_id  TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY,
  tenant_id  TEXT NOT NULL REFERENCES tenants(tenant_id),
  name       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS snapshots (
  snapshot_id     TEXT PRIMARY KEY,
  tenant_id       TEXT NOT NULL REFERENCES tenants(tenant_id),
  project_id      TEXT NOT NULL REFERENCES projects(project_id),
  root_digest     TEXT NOT NULL,
  manifest_digest TEXT NOT NULL,
  policy_version  TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  UNIQUE (tenant_id, project_id, root_digest, policy_version)
);

CREATE TABLE IF NOT EXISTS runs (
  run_id                TEXT PRIMARY KEY,
  tenant_id             TEXT NOT NULL REFERENCES tenants(tenant_id),
  project_id            TEXT NOT NULL REFERENCES projects(project_id),
  snapshot_id           TEXT NOT NULL REFERENCES snapshots(snapshot_id),
  pipeline_version      TEXT NOT NULL,
  source_profile        TEXT NOT NULL DEFAULT '{}',
  target_profile        TEXT NOT NULL DEFAULT '{}',
  trust_namespace       TEXT NOT NULL DEFAULT 'branch',
  status                TEXT NOT NULL CHECK (status IN (
                          'PENDING','RUNNING','PAUSED','SUCCEEDED','FAILED',
                          'CANCELED','RECOVERING','STALE')),
  version               INTEGER NOT NULL DEFAULT 0,
  journal_sequence      INTEGER NOT NULL DEFAULT 0,
  published_tree_digest TEXT,
  evidence_bundle_digest TEXT,
  created_at            TEXT NOT NULL,
  updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_nodes (
  run_id           TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  node_id          TEXT NOT NULL,
  attempt          INTEGER NOT NULL DEFAULT 1 CHECK (attempt > 0),
  stage_id         TEXT NOT NULL,
  stage_version    TEXT NOT NULL,
  action_key       TEXT,
  status           TEXT NOT NULL CHECK (status IN (
                     'PENDING','READY','RUNNING','CHECKPOINTED','SUCCEEDED',
                     'FAILED_RETRYABLE','FAILED_FINAL','PAUSED','CANCELED',
                     'RECOVERING','STALE')),
  lease_id         TEXT,
  lease_epoch      INTEGER NOT NULL DEFAULT 0,
  lease_expires_at REAL,
  heartbeat_at     REAL,
  retries          INTEGER NOT NULL DEFAULT 0,
  retry_budget     INTEGER NOT NULL DEFAULT 3,
  version          INTEGER NOT NULL DEFAULT 0,
  outcome          TEXT,
  started_at       TEXT,
  finished_at      TEXT,
  error_code       TEXT,
  error_details    TEXT,
  PRIMARY KEY (run_id, node_id, attempt)
);

CREATE TABLE IF NOT EXISTS artifacts (
  tenant_id        TEXT NOT NULL REFERENCES tenants(tenant_id),
  digest           TEXT NOT NULL,
  size_bytes       INTEGER NOT NULL CHECK (size_bytes >= 0),
  media_type       TEXT NOT NULL,
  artifact_kind    TEXT NOT NULL,
  storage_state    TEXT NOT NULL CHECK (storage_state IN (
                     'LOCAL','REMOTE_PENDING','REMOTE','QUARANTINED','DELETING','DELETED')),
  validation_level TEXT NOT NULL CHECK (validation_level IN (
                     'UNVERIFIED','COMPILE_VERIFIED','TEST_VERIFIED',
                     'BEHAVIOR_VERIFIED','PRODUCTION_CERTIFIED','QUARANTINED')),
  metadata         TEXT NOT NULL DEFAULT '{}',
  created_at       TEXT NOT NULL,
  last_accessed_at TEXT,
  PRIMARY KEY (tenant_id, digest)
);

CREATE TABLE IF NOT EXISTS artifact_refs (
  tenant_id     TEXT NOT NULL,
  source_kind   TEXT NOT NULL,
  source_id     TEXT NOT NULL,
  target_digest TEXT NOT NULL,
  ref_kind      TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  PRIMARY KEY (tenant_id, source_kind, source_id, target_digest, ref_kind),
  FOREIGN KEY (tenant_id, target_digest) REFERENCES artifacts(tenant_id, digest)
);

CREATE TABLE IF NOT EXISTS action_cache_entries (
  tenant_id              TEXT NOT NULL REFERENCES tenants(tenant_id),
  trust_namespace        TEXT NOT NULL,
  action_key             TEXT NOT NULL,
  result_manifest_digest TEXT NOT NULL,
  validation_level       TEXT NOT NULL CHECK (validation_level IN (
                           'UNVERIFIED','COMPILE_VERIFIED','TEST_VERIFIED',
                           'BEHAVIOR_VERIFIED','PRODUCTION_CERTIFIED','QUARANTINED')),
  producer_identity      TEXT NOT NULL,
  provenance_digest      TEXT NOT NULL,
  status                 TEXT NOT NULL CHECK (status IN ('ACTIVE','QUARANTINED','REVOKED','EXPIRED')),
  entry_kind             TEXT NOT NULL DEFAULT 'POSITIVE' CHECK (entry_kind IN ('POSITIVE','NEGATIVE')),
  failure_code           TEXT,
  expires_at             REAL,
  created_at             TEXT NOT NULL,
  last_accessed_at       TEXT,
  hit_count              INTEGER NOT NULL DEFAULT 0,
  saved_cpu_ms           INTEGER NOT NULL DEFAULT 0,
  saved_wall_ms          INTEGER NOT NULL DEFAULT 0,
  saved_model_tokens     INTEGER NOT NULL DEFAULT 0,
  quarantine_reason      TEXT,
  PRIMARY KEY (tenant_id, trust_namespace, action_key)
);

CREATE TABLE IF NOT EXISTS staged_files (
  staged_file_id      TEXT PRIMARY KEY,
  tenant_id           TEXT NOT NULL REFERENCES tenants(tenant_id),
  project_id          TEXT NOT NULL REFERENCES projects(project_id),
  run_id              TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  node_id             TEXT NOT NULL,
  attempt             INTEGER NOT NULL CHECK (attempt > 0),
  logical_path        TEXT NOT NULL,
  file_class          TEXT NOT NULL CHECK (file_class IN (
                        'SCRATCH','STAGED_INTERMEDIATE','SEALED_ARTIFACT','PUBLISH_CANDIDATE','QUARANTINED')),
  status              TEXT NOT NULL CHECK (status IN (
                        'RESERVED','WRITING','SEALED','CAS_PROMOTED','TREE_INCLUDED',
                        'PUBLISHED','ABORTED','QUARANTINED')),
  overwrite_policy    TEXT NOT NULL DEFAULT 'reject'
                        CHECK (overwrite_policy IN ('reject','replace','merge')),
  ownership           TEXT NOT NULL DEFAULT 'GENERATED',
  internal_temp_path  TEXT,
  internal_sealed_path TEXT,
  lease_id            TEXT,
  lease_epoch         INTEGER NOT NULL DEFAULT 0,
  version             INTEGER NOT NULL DEFAULT 0,
  expected_size       INTEGER CHECK (expected_size IS NULL OR expected_size >= 0),
  actual_size         INTEGER CHECK (actual_size IS NULL OR actual_size >= 0),
  digest              TEXT,
  media_type          TEXT,
  artifact_kind       TEXT,
  action_key          TEXT,
  artifact_digest     TEXT,
  source_map_digest   TEXT,
  mode                INTEGER NOT NULL DEFAULT 420,
  validation_level    TEXT NOT NULL DEFAULT 'UNVERIFIED',
  secret_scan_status  TEXT NOT NULL DEFAULT 'NOT_RUN'
                        CHECK (secret_scan_status IN ('NOT_RUN','PASS','FAIL','ERROR')),
  quarantine_reason   TEXT,
  created_at          TEXT NOT NULL,
  sealed_at           TEXT,
  promoted_at         TEXT,
  tree_included_at    TEXT,
  published_at        TEXT,
  UNIQUE (run_id, node_id, attempt, logical_path)
);

-- One live logical path per run: reservations from other nodes/attempts that
-- are still in flight must not silently race for the same output.
CREATE UNIQUE INDEX IF NOT EXISTS uq_staged_live_path
  ON staged_files (run_id, logical_path)
  WHERE status IN ('RESERVED','WRITING','SEALED','CAS_PROMOTED','TREE_INCLUDED','PUBLISHED');

CREATE TABLE IF NOT EXISTS file_trees (
  tenant_id        TEXT NOT NULL,
  tree_digest      TEXT NOT NULL,
  run_id           TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  manifest_digest  TEXT NOT NULL,
  entry_count      INTEGER NOT NULL,
  total_bytes      INTEGER NOT NULL,
  validation_level TEXT NOT NULL,
  evidence_digest  TEXT,
  previous_tree    TEXT,
  status           TEXT NOT NULL CHECK (status IN ('CANDIDATE','PUBLISHED','SUPERSEDED','ROLLED_BACK')),
  created_at       TEXT NOT NULL,
  published_at     TEXT,
  PRIMARY KEY (tenant_id, tree_digest)
);

CREATE TABLE IF NOT EXISTS checkpoints (
  checkpoint_id    TEXT PRIMARY KEY,
  tenant_id        TEXT NOT NULL REFERENCES tenants(tenant_id),
  project_id       TEXT NOT NULL REFERENCES projects(project_id),
  run_id           TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  node_id          TEXT NOT NULL,
  attempt          INTEGER NOT NULL,
  sequence         INTEGER NOT NULL,
  lease_epoch      INTEGER NOT NULL,
  manifest_digest  TEXT NOT NULL,
  journal_sequence INTEGER NOT NULL,
  status           TEXT NOT NULL CHECK (status IN ('ACTIVE','SUPERSEDED','INVALID','QUARANTINED')),
  created_at       TEXT NOT NULL,
  UNIQUE (run_id, node_id, attempt, sequence)
);

CREATE TABLE IF NOT EXISTS side_effect_receipts (
  tenant_id          TEXT NOT NULL,
  run_id             TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  node_id            TEXT NOT NULL,
  idempotency_key    TEXT NOT NULL,
  effect_type        TEXT NOT NULL,
  status             TEXT NOT NULL CHECK (status IN ('PENDING','COMMITTED','COMPENSATED','FAILED')),
  external_reference TEXT,
  payload_digest     TEXT NOT NULL,
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL,
  PRIMARY KEY (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS cache_events (
  event_id       TEXT PRIMARY KEY,
  tenant_id      TEXT NOT NULL,
  project_id     TEXT,
  run_id         TEXT,
  node_id        TEXT,
  sequence       INTEGER,
  event_type     TEXT NOT NULL,
  actor          TEXT NOT NULL,
  lease_epoch    INTEGER,
  payload        TEXT NOT NULL,
  payload_digest TEXT NOT NULL,
  created_at     TEXT NOT NULL,
  UNIQUE (run_id, sequence)
);

CREATE TABLE IF NOT EXISTS pins (
  pin_id      TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_id   TEXT NOT NULL,
  reason      TEXT NOT NULL,
  expires_at  REAL,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS certificates (
  certificate_id   TEXT PRIMARY KEY,
  tenant_id        TEXT NOT NULL,
  scope_digest     TEXT NOT NULL,
  tree_digest      TEXT NOT NULL,
  evidence_digest  TEXT NOT NULL,
  validation_level TEXT NOT NULL,
  signature        TEXT NOT NULL,
  issuer           TEXT NOT NULL,
  status           TEXT NOT NULL CHECK (status IN ('VALID','REVOKED','EXPIRED')),
  issued_at        REAL NOT NULL,
  expires_at       REAL NOT NULL,
  limitations      TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS revocations (
  revocation_id TEXT PRIMARY KEY,
  tenant_id     TEXT NOT NULL,
  subject_kind  TEXT NOT NULL,
  subject_id    TEXT NOT NULL,
  reason        TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  UNIQUE (tenant_id, subject_kind, subject_id)
);

CREATE TABLE IF NOT EXISTS gc_plans (
  plan_id     TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  status      TEXT NOT NULL CHECK (status IN ('DRY_RUN','APPROVED','APPLIED','ABANDONED')),
  payload     TEXT NOT NULL,
  created_at  REAL NOT NULL,
  applied_at  REAL
);

CREATE TABLE IF NOT EXISTS gc_receipts (
  plan_id    TEXT NOT NULL REFERENCES gc_plans(plan_id) ON DELETE CASCADE,
  digest     TEXT NOT NULL,
  outcome    TEXT NOT NULL CHECK (outcome IN ('DELETED','ALREADY_ABSENT','PROTECTED','FAILED')),
  detail     TEXT,
  created_at REAL NOT NULL,
  PRIMARY KEY (plan_id, digest)
);

CREATE TABLE IF NOT EXISTS idempotency_records (
  tenant_id       TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  operation       TEXT NOT NULL,
  request_digest  TEXT NOT NULL,
  response        TEXT NOT NULL,
  created_at      REAL NOT NULL,
  PRIMARY KEY (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS outbox_events (
  outbox_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id    TEXT NOT NULL,
  topic        TEXT NOT NULL,
  event_key    TEXT NOT NULL,
  payload      TEXT NOT NULL,
  attempts     INTEGER NOT NULL DEFAULT 0,
  created_at   REAL NOT NULL,
  published_at REAL
);

CREATE INDEX IF NOT EXISTS idx_runs_project_status ON runs (tenant_id, project_id, status, updated_at);
CREATE INDEX IF NOT EXISTS idx_nodes_schedulable   ON run_nodes (status, lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_artifacts_gc        ON artifacts (tenant_id, storage_state, last_accessed_at, size_bytes);
CREATE INDEX IF NOT EXISTS idx_artifact_refs_target ON artifact_refs (tenant_id, target_digest);
CREATE INDEX IF NOT EXISTS idx_action_cache_access ON action_cache_entries (tenant_id, trust_namespace, status, last_accessed_at);
CREATE INDEX IF NOT EXISTS idx_action_cache_result ON action_cache_entries (tenant_id, result_manifest_digest);
CREATE INDEX IF NOT EXISTS idx_staged_recovery     ON staged_files (run_id, status, lease_epoch);
CREATE INDEX IF NOT EXISTS idx_staged_path         ON staged_files (run_id, logical_path);
CREATE INDEX IF NOT EXISTS idx_events_run_sequence ON cache_events (run_id, sequence);
CREATE INDEX IF NOT EXISTS idx_pins_source         ON pins (tenant_id, source_kind, source_id);
CREATE INDEX IF NOT EXISTS idx_outbox_pending      ON outbox_events (outbox_id, published_at);
CREATE INDEX IF NOT EXISTS idx_checkpoints_node    ON checkpoints (run_id, node_id, attempt, sequence);
