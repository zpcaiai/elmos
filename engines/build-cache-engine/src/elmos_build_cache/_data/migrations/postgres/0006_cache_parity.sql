-- Durable v1.2 cache-parity metadata. Documents are canonical, content-free
-- JSON; payload bytes, prompts, source files, and secret values live elsewhere.

CREATE TABLE IF NOT EXISTS prompt_prefix_manifests (
  tenant_id              text NOT NULL REFERENCES tenants(tenant_id),
  project_id             text NOT NULL REFERENCES projects(project_id),
  manifest_id            text NOT NULL,
  manifest_digest        text NOT NULL,
  provider               text,
  provider_namespace     text NOT NULL,
  compatibility_group    text NOT NULL,
  stable_prefix_digest   text NOT NULL,
  document               jsonb NOT NULL,
  recorded_at            double precision NOT NULL,
  PRIMARY KEY (tenant_id, project_id, manifest_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_manifest_digest
  ON prompt_prefix_manifests (tenant_id, project_id, manifest_digest);

CREATE TABLE IF NOT EXISTS provider_cache_usage (
  tenant_id                  text NOT NULL REFERENCES tenants(tenant_id),
  project_id                 text NOT NULL REFERENCES projects(project_id),
  observation_id             text NOT NULL,
  prompt_manifest_digest     text NOT NULL,
  usage_digest               text NOT NULL,
  provider                   text NOT NULL,
  total_input_tokens         bigint NOT NULL CHECK (total_input_tokens >= 0),
  processed_input_tokens     bigint NOT NULL CHECK (processed_input_tokens >= 0),
  output_tokens              bigint NOT NULL CHECK (output_tokens >= 0),
  cache_read_tokens          bigint NOT NULL CHECK (cache_read_tokens >= 0),
  cache_write_tokens         bigint CHECK (cache_write_tokens IS NULL OR cache_write_tokens >= 0),
  accounting                 text NOT NULL CHECK (accounting IN ('INCLUSIVE','ADDITIVE')),
  document                   jsonb NOT NULL,
  observed_at                double precision NOT NULL,
  PRIMARY KEY (tenant_id, project_id, observation_id)
);

CREATE INDEX IF NOT EXISTS idx_provider_usage_manifest
  ON provider_cache_usage (tenant_id, project_id, prompt_manifest_digest, observed_at);

CREATE TABLE IF NOT EXISTS environment_snapshot_manifests (
  tenant_id              text NOT NULL REFERENCES tenants(tenant_id),
  project_id             text NOT NULL REFERENCES projects(project_id),
  snapshot_id            text NOT NULL,
  snapshot_key           text NOT NULL,
  manifest_digest        text NOT NULL,
  trust_namespace        text NOT NULL,
  status                 text NOT NULL,
  document               jsonb NOT NULL,
  recorded_at            double precision NOT NULL,
  PRIMARY KEY (tenant_id, project_id, snapshot_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_environment_snapshot_key
  ON environment_snapshot_manifests (tenant_id, project_id, snapshot_key);

CREATE TABLE IF NOT EXISTS environment_snapshot_status_events (
  tenant_id              text NOT NULL REFERENCES tenants(tenant_id),
  project_id             text NOT NULL REFERENCES projects(project_id),
  snapshot_key           text NOT NULL,
  sequence               bigint NOT NULL CHECK (sequence > 0),
  event_id               text NOT NULL,
  expected_status        text NOT NULL,
  new_status             text NOT NULL CHECK (new_status IN ('QUARANTINED','REVOKED')),
  reason_digest          text NOT NULL,
  previous_event_digest  text,
  event_digest           text NOT NULL,
  document               jsonb NOT NULL,
  recorded_at            double precision NOT NULL,
  PRIMARY KEY (tenant_id, project_id, snapshot_key, sequence),
  UNIQUE (tenant_id, project_id, snapshot_key, event_id),
  UNIQUE (tenant_id, project_id, snapshot_key, event_digest)
);

CREATE OR REPLACE FUNCTION elmos_environment_snapshot_status_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'ENVIRONMENT_SNAPSHOT_STATUS_APPEND_ONLY';
END;
$$;

DROP TRIGGER IF EXISTS environment_snapshot_status_events_no_update
  ON environment_snapshot_status_events;
CREATE TRIGGER environment_snapshot_status_events_no_update
BEFORE UPDATE ON environment_snapshot_status_events
FOR EACH ROW EXECUTE FUNCTION elmos_environment_snapshot_status_immutable();

DROP TRIGGER IF EXISTS environment_snapshot_status_events_no_delete
  ON environment_snapshot_status_events;
CREATE TRIGGER environment_snapshot_status_events_no_delete
BEFORE DELETE ON environment_snapshot_status_events
FOR EACH ROW EXECUTE FUNCTION elmos_environment_snapshot_status_immutable();

CREATE TABLE IF NOT EXISTS cache_outcome_events_v12 (
  tenant_id              text NOT NULL REFERENCES tenants(tenant_id),
  project_id             text NOT NULL REFERENCES projects(project_id),
  event_id               text NOT NULL,
  request_id             text NOT NULL,
  event_digest           text NOT NULL,
  layer                  text NOT NULL,
  outcome                text NOT NULL,
  reason_code            text NOT NULL,
  eligible               boolean NOT NULL,
  document               jsonb NOT NULL,
  recorded_at            double precision NOT NULL,
  PRIMARY KEY (tenant_id, project_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_cache_outcomes_request
  ON cache_outcome_events_v12 (tenant_id, project_id, request_id, recorded_at);

CREATE OR REPLACE FUNCTION elmos_cache_outcome_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'CACHE_OUTCOME_APPEND_ONLY';
END;
$$;

DROP TRIGGER IF EXISTS cache_outcome_events_v12_no_update ON cache_outcome_events_v12;
CREATE TRIGGER cache_outcome_events_v12_no_update
BEFORE UPDATE ON cache_outcome_events_v12
FOR EACH ROW EXECUTE FUNCTION elmos_cache_outcome_immutable();

DROP TRIGGER IF EXISTS cache_outcome_events_v12_no_delete ON cache_outcome_events_v12;
CREATE TRIGGER cache_outcome_events_v12_no_delete
BEFORE DELETE ON cache_outcome_events_v12
FOR EACH ROW EXECUTE FUNCTION elmos_cache_outcome_immutable();

CREATE TABLE IF NOT EXISTS cache_affinity_decisions_v12 (
  tenant_id              text NOT NULL REFERENCES tenants(tenant_id),
  project_id             text NOT NULL REFERENCES projects(project_id),
  decision_id            text NOT NULL,
  request_id             text NOT NULL,
  affinity_key           text NOT NULL,
  decision_digest        text NOT NULL,
  selected_target        text NOT NULL,
  document               jsonb NOT NULL,
  recorded_at            double precision NOT NULL,
  PRIMARY KEY (tenant_id, project_id, decision_id)
);

CREATE INDEX IF NOT EXISTS idx_affinity_request
  ON cache_affinity_decisions_v12 (tenant_id, project_id, request_id, recorded_at);

CREATE TABLE IF NOT EXISTS cache_parity_reports_v12 (
  tenant_id              text NOT NULL REFERENCES tenants(tenant_id),
  project_id             text NOT NULL REFERENCES projects(project_id),
  report_id              text NOT NULL,
  report_digest          text NOT NULL,
  mandatory_pass         boolean NOT NULL,
  document               jsonb NOT NULL,
  recorded_at            double precision NOT NULL,
  PRIMARY KEY (tenant_id, project_id, report_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cache_parity_report_digest
  ON cache_parity_reports_v12 (tenant_id, project_id, report_digest);
