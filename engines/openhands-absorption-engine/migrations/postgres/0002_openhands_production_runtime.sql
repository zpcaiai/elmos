-- Production runtime schema for OpenHands absorption P0/P1.
-- Apply after 0001. Application connections must set elmos.tenant_id in every
-- transaction. Infrastructure outbox dispatchers require a separately granted
-- PostgreSQL role with BYPASSRLS; this migration does not grant that role.

ALTER TABLE oh_execution_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE oh_execution_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS oh_execution_runs_tenant_isolation ON oh_execution_runs;
CREATE POLICY oh_execution_runs_tenant_isolation ON oh_execution_runs
  USING (tenant_id = current_setting('elmos.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true));

ALTER TABLE oh_execution_events
  ADD COLUMN IF NOT EXISTS causation_event_id text,
  ADD COLUMN IF NOT EXISTS correlation_id text,
  ADD COLUMN IF NOT EXISTS schema_version text NOT NULL DEFAULT '1.0',
  ADD COLUMN IF NOT EXISTS event_timestamp timestamptz NOT NULL DEFAULT now();
ALTER TABLE oh_execution_events FORCE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS oh_events_tenant_run_type_seq_idx
  ON oh_execution_events(tenant_id, run_id, event_type, seq);
CREATE INDEX IF NOT EXISTS oh_events_tenant_created_idx
  ON oh_execution_events(tenant_id, event_timestamp);
CREATE INDEX IF NOT EXISTS oh_outbox_unpublished_idx
  ON oh_execution_outbox(outbox_id) WHERE published_at IS NULL;

ALTER TABLE oh_execution_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE oh_execution_outbox FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS oh_execution_outbox_tenant_isolation ON oh_execution_outbox;
CREATE POLICY oh_execution_outbox_tenant_isolation ON oh_execution_outbox
  USING (tenant_id = current_setting('elmos.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true));

CREATE TABLE IF NOT EXISTS oh_run_leases (
  tenant_id text NOT NULL,
  run_id text NOT NULL,
  node_id text NOT NULL,
  owner text NOT NULL,
  fencing_token text NOT NULL,
  expires_epoch double precision NOT NULL,
  PRIMARY KEY (tenant_id, run_id, node_id)
);

CREATE TABLE IF NOT EXISTS oh_checkpoints (
  checkpoint_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  run_id text NOT NULL,
  node_id text NOT NULL,
  event_seq bigint NOT NULL CHECK (event_seq >= -1),
  manifest_hash text NOT NULL CHECK (manifest_hash LIKE 'sha256:%'),
  state_json jsonb NOT NULL,
  workspace_ref text,
  context_fingerprint text,
  digest text NOT NULL CHECK (digest LIKE 'sha256:%'),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, run_id, node_id, event_seq, digest)
);

CREATE TABLE IF NOT EXISTS oh_projections (
  tenant_id text NOT NULL,
  run_id text NOT NULL,
  projection_name text NOT NULL,
  projection_json jsonb NOT NULL,
  event_seq bigint NOT NULL,
  head_digest text NOT NULL,
  rebuilt_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, run_id, projection_name)
);

CREATE TABLE IF NOT EXISTS oh_workspace_leases (
  workspace_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  run_id text NOT NULL,
  node_id text NOT NULL,
  provider text NOT NULL,
  region text NOT NULL,
  isolation_class text NOT NULL CHECK (isolation_class IN ('L0','L1','L2','L3','L4')),
  state text NOT NULL CHECK (state IN ('allocated','active','suspended','released','destroyed')),
  fencing_token text NOT NULL,
  cpu_limit numeric NOT NULL CHECK (cpu_limit > 0),
  memory_mb bigint NOT NULL CHECK (memory_mb > 0),
  disk_mb bigint NOT NULL CHECK (disk_mb > 0),
  pid_limit integer NOT NULL CHECK (pid_limit > 0),
  network_policy jsonb NOT NULL,
  image_digest text,
  endpoint_ref text,
  snapshot_ref text,
  lease_expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oh_worker_leases (
  worker_id text PRIMARY KEY,
  tenant_id text,
  region text NOT NULL,
  residency_labels text[] NOT NULL DEFAULT '{}',
  capabilities text[] NOT NULL DEFAULT '{}',
  capacity jsonb NOT NULL,
  in_use jsonb NOT NULL,
  fencing_token text NOT NULL,
  draining boolean NOT NULL DEFAULT false,
  expires_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oh_tenant_quotas (
  tenant_id text PRIMARY KEY,
  concurrency_limit integer NOT NULL CHECK (concurrency_limit >= 0),
  token_limit bigint NOT NULL CHECK (token_limit >= 0),
  cpu_minute_limit numeric NOT NULL CHECK (cpu_minute_limit >= 0),
  storage_byte_limit bigint NOT NULL CHECK (storage_byte_limit >= 0),
  cost_micros_limit bigint NOT NULL CHECK (cost_micros_limit >= 0),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oh_tenant_usage (
  tenant_id text NOT NULL,
  window_key text NOT NULL,
  active_runs integer NOT NULL DEFAULT 0 CHECK (active_runs >= 0),
  tokens bigint NOT NULL DEFAULT 0 CHECK (tokens >= 0),
  cpu_minutes numeric NOT NULL DEFAULT 0 CHECK (cpu_minutes >= 0),
  storage_bytes bigint NOT NULL DEFAULT 0 CHECK (storage_bytes >= 0),
  cost_micros bigint NOT NULL DEFAULT 0 CHECK (cost_micros >= 0),
  version bigint NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, window_key)
);

CREATE TABLE IF NOT EXISTS oh_provider_sessions (
  session_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  task_id text NOT NULL,
  run_id text NOT NULL,
  node_id text NOT NULL,
  agent_id text,
  provider text NOT NULL,
  model text NOT NULL,
  region text NOT NULL,
  state text NOT NULL,
  remote_session_id text NOT NULL,
  capabilities_digest text NOT NULL,
  last_sequence bigint NOT NULL DEFAULT -1,
  checkpoint_json jsonb,
  usage_json jsonb NOT NULL DEFAULT '{}',
  fencing_token text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oh_approvals (
  approval_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  run_id text NOT NULL,
  action_digest text NOT NULL,
  risk_level text NOT NULL,
  state text NOT NULL CHECK (state IN ('pending','approved','denied','expired','revoked')),
  requested_by text NOT NULL,
  decided_by text,
  reason text,
  expires_at timestamptz NOT NULL,
  version bigint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oh_approval_decisions (
  approval_id text NOT NULL,
  tenant_id text NOT NULL,
  actor_id text NOT NULL,
  decision text NOT NULL CHECK (decision IN ('approve','deny','revoke')),
  reason text NOT NULL,
  decided_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (approval_id, actor_id)
);

CREATE TABLE IF NOT EXISTS oh_capability_packages (
  tenant_scope text NOT NULL,
  package_name text NOT NULL,
  version text NOT NULL,
  publisher text NOT NULL,
  digest text NOT NULL,
  signature text NOT NULL,
  signing_algorithm text NOT NULL,
  manifest jsonb NOT NULL,
  sbom jsonb NOT NULL,
  dependency_lock jsonb NOT NULL,
  provenance jsonb NOT NULL,
  trust_level text NOT NULL,
  state text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_scope, package_name, version)
);

ALTER TABLE oh_capability_packages ENABLE ROW LEVEL SECURITY;
ALTER TABLE oh_capability_packages FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS oh_capability_packages_tenant_isolation ON oh_capability_packages;
CREATE POLICY oh_capability_packages_tenant_isolation ON oh_capability_packages
  USING (tenant_scope IN (current_setting('elmos.tenant_id', true), 'public'))
  WITH CHECK (tenant_scope = current_setting('elmos.tenant_id', true));

CREATE TABLE IF NOT EXISTS oh_run_package_pins (
  tenant_id text NOT NULL,
  run_id text NOT NULL,
  package_name text NOT NULL,
  version text NOT NULL,
  digest text NOT NULL,
  pinned_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, run_id, package_name)
);

CREATE TABLE IF NOT EXISTS oh_package_bundles (
  tenant_id text NOT NULL,
  package_name text NOT NULL,
  version text NOT NULL,
  bundle_digest text NOT NULL CHECK (bundle_digest LIKE 'sha256:%'),
  bundle_ref text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, package_name, version)
);

CREATE TABLE IF NOT EXISTS oh_package_lifecycle_events (
  event_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  package_name text NOT NULL,
  version text NOT NULL,
  event_type text NOT NULL,
  actor_id text NOT NULL,
  reason text NOT NULL,
  body jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oh_agent_nodes (
  tenant_id text NOT NULL,
  run_id text NOT NULL,
  node_id text NOT NULL,
  plan_version bigint NOT NULL,
  dependencies text[] NOT NULL DEFAULT '{}',
  status text NOT NULL,
  provider text,
  workspace_strategy text NOT NULL,
  budget_json jsonb NOT NULL,
  compensation_json jsonb,
  owner text,
  fencing_token text,
  attempt integer NOT NULL DEFAULT 0,
  result_ref text,
  version bigint NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, run_id, node_id)
);

CREATE TABLE IF NOT EXISTS oh_evidence_packs (
  pack_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  project_id text NOT NULL,
  run_id text NOT NULL,
  manifest_digest text NOT NULL,
  evidence_digest text NOT NULL,
  body jsonb NOT NULL,
  signature text NOT NULL,
  signer_id text NOT NULL,
  state text NOT NULL CHECK (state IN ('engineering','ready_for_independent_review','verified','rejected')),
  independent_verifier_id text,
  independent_verification jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oh_evidence_verifications (
  verification_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  pack_id text NOT NULL,
  pack_digest text NOT NULL,
  verifier_id text NOT NULL,
  decision text NOT NULL CHECK (decision IN ('VERIFIED','REJECTED','INCONCLUSIVE')),
  findings jsonb NOT NULL,
  signature text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oh_qualification_runs (
  qualification_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  run_id text NOT NULL,
  campaign_type text NOT NULL,
  target_digest text NOT NULL,
  environment_digest text NOT NULL,
  status text NOT NULL CHECK (status IN ('NOT_RUN','RUNNING','PASS','FAIL','BLOCKED')),
  evidence_refs jsonb NOT NULL DEFAULT '[]',
  executor_id text,
  independent_verifier_id text,
  authorization_ref text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'oh_run_leases','oh_checkpoints','oh_projections','oh_workspace_leases',
    'oh_tenant_quotas','oh_tenant_usage','oh_provider_sessions','oh_approvals',
    'oh_approval_decisions','oh_run_package_pins','oh_package_bundles',
    'oh_package_lifecycle_events','oh_agent_nodes','oh_evidence_packs',
    'oh_evidence_verifications','oh_qualification_runs'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', table_name || '_tenant_isolation', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (tenant_id = current_setting(''elmos.tenant_id'', true)) WITH CHECK (tenant_id = current_setting(''elmos.tenant_id'', true))',
      table_name || '_tenant_isolation', table_name
    );
  END LOOP;
END $$;

CREATE OR REPLACE FUNCTION oh_reject_immutable_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is immutable; append a correction or verification record', TG_TABLE_NAME;
END;
$$;

DROP TRIGGER IF EXISTS oh_checkpoints_immutable ON oh_checkpoints;
CREATE TRIGGER oh_checkpoints_immutable BEFORE UPDATE OR DELETE ON oh_checkpoints
  FOR EACH ROW EXECUTE FUNCTION oh_reject_immutable_mutation();
DROP TRIGGER IF EXISTS oh_evidence_packs_immutable ON oh_evidence_packs;
CREATE TRIGGER oh_evidence_packs_immutable BEFORE UPDATE OR DELETE ON oh_evidence_packs
  FOR EACH ROW EXECUTE FUNCTION oh_reject_immutable_mutation();
DROP TRIGGER IF EXISTS oh_evidence_verifications_immutable ON oh_evidence_verifications;
CREATE TRIGGER oh_evidence_verifications_immutable BEFORE UPDATE OR DELETE ON oh_evidence_verifications
  FOR EACH ROW EXECUTE FUNCTION oh_reject_immutable_mutation();
DROP TRIGGER IF EXISTS oh_package_lifecycle_events_immutable ON oh_package_lifecycle_events;
CREATE TRIGGER oh_package_lifecycle_events_immutable BEFORE UPDATE OR DELETE ON oh_package_lifecycle_events
  FOR EACH ROW EXECUTE FUNCTION oh_reject_immutable_mutation();

CREATE TABLE IF NOT EXISTS oh_retention_policies (
  tenant_id text NOT NULL,
  policy_id text NOT NULL,
  version bigint NOT NULL,
  record_class text NOT NULL,
  retention_seconds bigint NOT NULL CHECK (retention_seconds >= 0),
  export_before_delete boolean NOT NULL,
  deletion_mode text NOT NULL,
  body_digest text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, policy_id, version)
);

CREATE TABLE IF NOT EXISTS oh_governed_objects (
  object_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  record_class text NOT NULL,
  reference jsonb NOT NULL,
  reference_digest text NOT NULL,
  policy_id text NOT NULL,
  policy_version bigint NOT NULL,
  created_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  state text NOT NULL,
  legal_hold boolean NOT NULL DEFAULT false,
  hold_reason text,
  hold_actor text,
  export_digest text,
  version bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS oh_retention_actions (
  action_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  object_id text NOT NULL,
  action text NOT NULL,
  status text NOT NULL,
  actor_id text NOT NULL,
  independent_verifier_id text NOT NULL,
  approval_ref text NOT NULL,
  provider_receipt text NOT NULL,
  body_digest text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['oh_retention_policies','oh_governed_objects','oh_retention_actions'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', table_name || '_tenant_isolation', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON %I USING (tenant_id = current_setting(''elmos.tenant_id'', true)) WITH CHECK (tenant_id = current_setting(''elmos.tenant_id'', true))',
      table_name || '_tenant_isolation', table_name
    );
  END LOOP;
END $$;

DROP TRIGGER IF EXISTS oh_retention_actions_immutable ON oh_retention_actions;
CREATE TRIGGER oh_retention_actions_immutable BEFORE UPDATE OR DELETE ON oh_retention_actions
  FOR EACH ROW EXECUTE FUNCTION oh_reject_immutable_mutation();

CREATE TABLE IF NOT EXISTS oh_execution_event_archive (
  tenant_id text NOT NULL,
  run_id text NOT NULL,
  seq bigint NOT NULL,
  event_timestamp timestamptz NOT NULL,
  event_json jsonb NOT NULL,
  digest text NOT NULL,
  archived_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, run_id, seq, event_timestamp)
) PARTITION BY RANGE (event_timestamp);

CREATE TABLE IF NOT EXISTS oh_execution_event_archive_default
  PARTITION OF oh_execution_event_archive DEFAULT;

ALTER TABLE oh_execution_event_archive ENABLE ROW LEVEL SECURITY;
ALTER TABLE oh_execution_event_archive FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS oh_execution_event_archive_tenant_isolation ON oh_execution_event_archive;
CREATE POLICY oh_execution_event_archive_tenant_isolation ON oh_execution_event_archive
  USING (tenant_id = current_setting('elmos.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true));

DROP TRIGGER IF EXISTS oh_execution_event_archive_immutable ON oh_execution_event_archive;
CREATE TRIGGER oh_execution_event_archive_immutable BEFORE UPDATE OR DELETE ON oh_execution_event_archive
  FOR EACH ROW EXECUTE FUNCTION oh_reject_immutable_mutation();

CREATE TABLE IF NOT EXISTS oh_retention_partitions (
  partition_name text PRIMARY KEY,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  state text NOT NULL CHECK (state IN ('active','sealed','exported','deleted')),
  archive_digest text,
  CHECK (ends_at > starts_at)
);
