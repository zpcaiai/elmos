-- SQLite mirror of the package control-plane metadata. Large payloads belong
-- in the private content-addressed store, not in job rows.
CREATE TABLE IF NOT EXISTS modernization_run (
  tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
  state TEXT NOT NULL, policy_hash TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0,
  owner_environment_id TEXT NOT NULL, current_phase TEXT, created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL, PRIMARY KEY (tenant_id, project_id, job_id)
);
CREATE TABLE IF NOT EXISTS idempotency_record (
  tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
  skill_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, input_hash TEXT NOT NULL,
  response_json TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, job_id, skill_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS control_event (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL, job_id TEXT NOT NULL, event_type TEXT NOT NULL,
  payload_digest TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS artifact_index (
  tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
  artifact_digest TEXT NOT NULL, artifact_type TEXT NOT NULL, schema_version TEXT NOT NULL,
  producer_skill TEXT NOT NULL, uri TEXT NOT NULL, size_bytes INTEGER NOT NULL,
  state TEXT NOT NULL, policy_hash TEXT NOT NULL, environment_id TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY (tenant_id, project_id, job_id, artifact_digest, artifact_type)
);
CREATE TABLE IF NOT EXISTS execution_checkpoint (
  tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
  skill_id TEXT NOT NULL, input_hash TEXT NOT NULL, policy_hash TEXT NOT NULL,
  fencing_token INTEGER NOT NULL, state TEXT NOT NULL, cursor_json TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY (tenant_id, project_id, job_id, skill_id, input_hash, policy_hash)
);
CREATE TABLE IF NOT EXISTS execution_lease (
  tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
  skill_id TEXT NOT NULL, lease_id TEXT NOT NULL, fencing_token INTEGER NOT NULL,
  expires_at TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, job_id, skill_id, fencing_token),
  UNIQUE (tenant_id, project_id, job_id, skill_id, lease_id)
);
CREATE TABLE IF NOT EXISTS change_set (
  tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
  change_set_id TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL,
  fencing_token INTEGER NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, job_id, change_set_id)
);
CREATE INDEX IF NOT EXISTS idx_control_event_scope_time
  ON control_event(tenant_id, project_id, job_id, created_at);
CREATE INDEX IF NOT EXISTS idx_artifact_index_scope_time
  ON artifact_index(tenant_id, project_id, job_id, created_at);
CREATE INDEX IF NOT EXISTS idx_execution_lease_active
  ON execution_lease(tenant_id, project_id, job_id, skill_id, state, expires_at);
