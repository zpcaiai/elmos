-- Durable v1.2 cache-parity metadata. Documents are canonical, content-free
-- JSON; payload bytes, prompts, source files, and secret values live elsewhere.

CREATE TABLE IF NOT EXISTS prompt_prefix_manifests (
  tenant_id              TEXT NOT NULL REFERENCES tenants(tenant_id),
  project_id             TEXT NOT NULL REFERENCES projects(project_id),
  manifest_id            TEXT NOT NULL,
  manifest_digest        TEXT NOT NULL,
  provider               TEXT,
  provider_namespace     TEXT NOT NULL,
  compatibility_group    TEXT NOT NULL,
  stable_prefix_digest   TEXT NOT NULL,
  document               TEXT NOT NULL CHECK (json_valid(document)),
  recorded_at            REAL NOT NULL,
  PRIMARY KEY (tenant_id, project_id, manifest_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_manifest_digest
  ON prompt_prefix_manifests (tenant_id, project_id, manifest_digest);

CREATE TABLE IF NOT EXISTS provider_cache_usage (
  tenant_id                  TEXT NOT NULL REFERENCES tenants(tenant_id),
  project_id                 TEXT NOT NULL REFERENCES projects(project_id),
  observation_id             TEXT NOT NULL,
  prompt_manifest_digest     TEXT NOT NULL,
  usage_digest               TEXT NOT NULL,
  provider                   TEXT NOT NULL,
  total_input_tokens         INTEGER NOT NULL CHECK (total_input_tokens >= 0),
  processed_input_tokens     INTEGER NOT NULL CHECK (processed_input_tokens >= 0),
  output_tokens              INTEGER NOT NULL CHECK (output_tokens >= 0),
  cache_read_tokens          INTEGER NOT NULL CHECK (cache_read_tokens >= 0),
  cache_write_tokens         INTEGER CHECK (cache_write_tokens IS NULL OR cache_write_tokens >= 0),
  accounting                 TEXT NOT NULL CHECK (accounting IN ('INCLUSIVE','ADDITIVE')),
  document                   TEXT NOT NULL CHECK (json_valid(document)),
  observed_at                REAL NOT NULL,
  PRIMARY KEY (tenant_id, project_id, observation_id)
);

CREATE INDEX IF NOT EXISTS idx_provider_usage_manifest
  ON provider_cache_usage (tenant_id, project_id, prompt_manifest_digest, observed_at);

CREATE TABLE IF NOT EXISTS environment_snapshot_manifests (
  tenant_id              TEXT NOT NULL REFERENCES tenants(tenant_id),
  project_id             TEXT NOT NULL REFERENCES projects(project_id),
  snapshot_id            TEXT NOT NULL,
  snapshot_key           TEXT NOT NULL,
  manifest_digest        TEXT NOT NULL,
  trust_namespace        TEXT NOT NULL,
  status                 TEXT NOT NULL,
  document               TEXT NOT NULL CHECK (json_valid(document)),
  recorded_at            REAL NOT NULL,
  PRIMARY KEY (tenant_id, project_id, snapshot_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_environment_snapshot_key
  ON environment_snapshot_manifests (tenant_id, project_id, snapshot_key);

CREATE TABLE IF NOT EXISTS environment_snapshot_status_events (
  tenant_id              TEXT NOT NULL REFERENCES tenants(tenant_id),
  project_id             TEXT NOT NULL REFERENCES projects(project_id),
  snapshot_key           TEXT NOT NULL,
  sequence               INTEGER NOT NULL CHECK (sequence > 0),
  event_id               TEXT NOT NULL,
  expected_status        TEXT NOT NULL,
  new_status             TEXT NOT NULL CHECK (new_status IN ('QUARANTINED','REVOKED')),
  reason_digest          TEXT NOT NULL,
  previous_event_digest  TEXT,
  event_digest           TEXT NOT NULL,
  document               TEXT NOT NULL CHECK (json_valid(document)),
  recorded_at            REAL NOT NULL,
  PRIMARY KEY (tenant_id, project_id, snapshot_key, sequence),
  UNIQUE (tenant_id, project_id, snapshot_key, event_id),
  UNIQUE (tenant_id, project_id, snapshot_key, event_digest)
);

CREATE TRIGGER IF NOT EXISTS environment_snapshot_status_events_no_update
BEFORE UPDATE ON environment_snapshot_status_events
BEGIN
  SELECT RAISE(ABORT, 'ENVIRONMENT_SNAPSHOT_STATUS_APPEND_ONLY');
END;

CREATE TRIGGER IF NOT EXISTS environment_snapshot_status_events_no_delete
BEFORE DELETE ON environment_snapshot_status_events
BEGIN
  SELECT RAISE(ABORT, 'ENVIRONMENT_SNAPSHOT_STATUS_APPEND_ONLY');
END;

CREATE TABLE IF NOT EXISTS cache_outcome_events_v12 (
  tenant_id              TEXT NOT NULL REFERENCES tenants(tenant_id),
  project_id             TEXT NOT NULL REFERENCES projects(project_id),
  event_id               TEXT NOT NULL,
  request_id             TEXT NOT NULL,
  event_digest           TEXT NOT NULL,
  layer                  TEXT NOT NULL,
  outcome                TEXT NOT NULL,
  reason_code            TEXT NOT NULL,
  eligible               INTEGER NOT NULL CHECK (eligible IN (0, 1)),
  document               TEXT NOT NULL CHECK (json_valid(document)),
  recorded_at            REAL NOT NULL,
  PRIMARY KEY (tenant_id, project_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_cache_outcomes_request
  ON cache_outcome_events_v12 (tenant_id, project_id, request_id, recorded_at);

CREATE TRIGGER IF NOT EXISTS cache_outcome_events_v12_no_update
BEFORE UPDATE ON cache_outcome_events_v12
BEGIN
  SELECT RAISE(ABORT, 'CACHE_OUTCOME_APPEND_ONLY');
END;

CREATE TRIGGER IF NOT EXISTS cache_outcome_events_v12_no_delete
BEFORE DELETE ON cache_outcome_events_v12
BEGIN
  SELECT RAISE(ABORT, 'CACHE_OUTCOME_APPEND_ONLY');
END;

CREATE TABLE IF NOT EXISTS cache_affinity_decisions_v12 (
  tenant_id              TEXT NOT NULL REFERENCES tenants(tenant_id),
  project_id             TEXT NOT NULL REFERENCES projects(project_id),
  decision_id            TEXT NOT NULL,
  request_id             TEXT NOT NULL,
  affinity_key           TEXT NOT NULL,
  decision_digest        TEXT NOT NULL,
  selected_target        TEXT NOT NULL,
  document               TEXT NOT NULL CHECK (json_valid(document)),
  recorded_at            REAL NOT NULL,
  PRIMARY KEY (tenant_id, project_id, decision_id)
);

CREATE INDEX IF NOT EXISTS idx_affinity_request
  ON cache_affinity_decisions_v12 (tenant_id, project_id, request_id, recorded_at);

CREATE TABLE IF NOT EXISTS cache_parity_reports_v12 (
  tenant_id              TEXT NOT NULL REFERENCES tenants(tenant_id),
  project_id             TEXT NOT NULL REFERENCES projects(project_id),
  report_id              TEXT NOT NULL,
  report_digest          TEXT NOT NULL,
  mandatory_pass         INTEGER NOT NULL CHECK (mandatory_pass IN (0, 1)),
  document               TEXT NOT NULL CHECK (json_valid(document)),
  recorded_at            REAL NOT NULL,
  PRIMARY KEY (tenant_id, project_id, report_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cache_parity_report_digest
  ON cache_parity_reports_v12 (tenant_id, project_id, report_digest);
