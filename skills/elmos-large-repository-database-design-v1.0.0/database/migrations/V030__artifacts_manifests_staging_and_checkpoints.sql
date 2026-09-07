-- Large payloads live in tenant-isolated object storage. PostgreSQL stores
-- content-addressed identities, manifests, publish state and checkpoint facts.

BEGIN;

CREATE TABLE artifact.object_blob (
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  sha256 text NOT NULL CHECK (core.sha256_is_valid(sha256)),
  storage_backend text NOT NULL CHECK (storage_backend IN ('s3', 'minio', 'filesystem', 'azure_blob', 'gcs')),
  bucket_name text NOT NULL,
  object_key text NOT NULL,
  version_id text,
  media_type text,
  compression text CHECK (compression IS NULL OR compression IN ('none', 'gzip', 'zstd', 'zip', 'tar_zstd')),
  size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
  encryption_key_ref text,
  encryption_context jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (core.json_object_or_empty(encryption_context)),
  object_state text NOT NULL DEFAULT 'writing'
    CHECK (object_state IN ('writing', 'available', 'quarantined', 'missing', 'deleting', 'deleted')),
  verified_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  deleted_at timestamptz,
  PRIMARY KEY (tenant_id, sha256),
  UNIQUE NULLS NOT DISTINCT (tenant_id, bucket_name, object_key, version_id)
);

CREATE TABLE artifact.artifact (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  artifact_kind text NOT NULL
    CHECK (artifact_kind IN (
      'input_archive', 'source_manifest', 'file_catalog', 'repository_graph',
      'semantic_ir', 'graph_shard', 'ir_shard', 'requirement_document',
      'architecture_document', 'generated_tree', 'patch_set', 'build_output',
      'test_output', 'trace', 'log', 'checkpoint', 'evidence', 'report',
      'screenshot', 'video', 'sbom', 'signature', 'deployment_manifest', 'other'
    )),
  logical_name text NOT NULL,
  sha256 text NOT NULL,
  media_type text,
  size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
  state text NOT NULL DEFAULT 'available'
    CHECK (state IN ('reserved', 'writing', 'available', 'quarantined', 'superseded', 'deleted')),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (core.json_object_or_empty(metadata)),
  created_by_run_id uuid,
  created_by_task_attempt_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  superseded_by_artifact_id uuid,
  UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, artifact_kind, logical_name, sha256),
  FOREIGN KEY (tenant_id, sha256) REFERENCES artifact.object_blob(tenant_id, sha256),
  FOREIGN KEY (tenant_id, created_by_run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, created_by_task_attempt_id) REFERENCES exec.task_attempt(tenant_id, id),
  FOREIGN KEY (tenant_id, superseded_by_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE OR REPLACE FUNCTION artifact.validate_available_artifact()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.state = 'available' AND NOT EXISTS (
    SELECT 1 FROM artifact.object_blob b
    WHERE b.tenant_id = NEW.tenant_id AND b.sha256 = NEW.sha256 AND b.object_state = 'available'
  ) THEN
    RAISE EXCEPTION 'available artifact requires an available object blob';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER validate_available_artifact
BEFORE INSERT OR UPDATE OF state, sha256 ON artifact.artifact
FOR EACH ROW EXECUTE FUNCTION artifact.validate_available_artifact();

CREATE TABLE artifact.artifact_link (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  artifact_id uuid NOT NULL,
  owner_kind text NOT NULL
    CHECK (owner_kind IN ('job', 'run', 'stage', 'task', 'attempt', 'session', 'checkpoint', 'scan', 'generation', 'verification', 'evidence', 'deployment')),
  owner_id uuid NOT NULL,
  link_role text NOT NULL,
  ordinal integer NOT NULL DEFAULT 0 CHECK (ordinal >= 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, owner_kind, owner_id, link_role, ordinal),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TRIGGER artifact_link_immutable
BEFORE UPDATE OR DELETE ON artifact.artifact_link
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE artifact.manifest (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  manifest_kind text NOT NULL
    CHECK (manifest_kind IN ('input', 'workspace', 'checkpoint', 'output', 'repository_tree', 'evidence_bundle', 'deployment')),
  root_sha256 text NOT NULL CHECK (core.sha256_is_valid(root_sha256)),
  manifest_artifact_id uuid NOT NULL,
  entry_count bigint NOT NULL DEFAULT 0 CHECK (entry_count >= 0),
  total_bytes bigint NOT NULL DEFAULT 0 CHECK (total_bytes >= 0),
  schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version > 0),
  sealed boolean NOT NULL DEFAULT false,
  sealed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, manifest_kind, root_sha256),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, manifest_artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  CHECK ((sealed AND sealed_at IS NOT NULL) OR (NOT sealed))
);

CREATE OR REPLACE FUNCTION artifact.validate_manifest_seal()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.sealed AND NOT EXISTS (
    SELECT 1 FROM artifact.artifact a
    WHERE a.tenant_id = NEW.tenant_id AND a.id = NEW.manifest_artifact_id AND a.state = 'available'
  ) THEN
    RAISE EXCEPTION 'sealed manifest requires an available manifest artifact';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER validate_manifest_seal
BEFORE INSERT OR UPDATE OF sealed, manifest_artifact_id ON artifact.manifest
FOR EACH ROW EXECUTE FUNCTION artifact.validate_manifest_seal();

CREATE TABLE artifact.manifest_entry (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  manifest_id uuid NOT NULL,
  entry_path text NOT NULL,
  entry_kind text NOT NULL CHECK (entry_kind IN ('file', 'directory', 'symlink', 'artifact', 'metadata')),
  artifact_id uuid,
  sha256 text CHECK (core.sha256_is_valid(sha256)),
  size_bytes bigint CHECK (size_bytes IS NULL OR size_bytes >= 0),
  file_mode integer,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (tenant_id, manifest_id, entry_path),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, manifest_id) REFERENCES artifact.manifest(tenant_id, id),
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE OR REPLACE FUNCTION artifact.reject_sealed_manifest_entry_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE v_tenant uuid; v_manifest uuid;
BEGIN
  v_tenant := COALESCE(NEW.tenant_id, OLD.tenant_id);
  v_manifest := COALESCE(NEW.manifest_id, OLD.manifest_id);
  IF EXISTS (SELECT 1 FROM artifact.manifest m WHERE m.tenant_id = v_tenant AND m.id = v_manifest AND m.sealed) THEN
    RAISE EXCEPTION 'sealed manifest entries are immutable';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER manifest_entry_seal_guard
BEFORE INSERT OR UPDATE OR DELETE ON artifact.manifest_entry
FOR EACH ROW EXECUTE FUNCTION artifact.reject_sealed_manifest_entry_change();

CREATE TABLE artifact.staged_object (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  task_id uuid,
  task_attempt_id uuid,
  workspace_id uuid,
  logical_path text NOT NULL,
  staging_key text NOT NULL,
  state text NOT NULL DEFAULT 'reserved'
    CHECK (state IN (
      'reserved', 'writing', 'sealed', 'cas_promoted', 'tree_included',
      'published', 'quarantined', 'aborted'
    )),
  expected_sha256 text CHECK (core.sha256_is_valid(expected_sha256)),
  actual_sha256 text CHECK (core.sha256_is_valid(actual_sha256)),
  size_bytes bigint CHECK (size_bytes IS NULL OR size_bytes >= 0),
  artifact_id uuid,
  output_manifest_id uuid,
  writer_fencing_token uuid,
  reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  sealed_at timestamptz,
  promoted_at timestamptz,
  published_at timestamptz,
  last_error text,
  UNIQUE (tenant_id, run_id, staging_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id),
  FOREIGN KEY (tenant_id, task_attempt_id) REFERENCES exec.task_attempt(tenant_id, id),
  FOREIGN KEY (tenant_id, workspace_id) REFERENCES exec.workspace(tenant_id, id),
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  FOREIGN KEY (tenant_id, output_manifest_id) REFERENCES artifact.manifest(tenant_id, id)
);

CREATE TABLE artifact.run_archive (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  archive_kind text NOT NULL CHECK (archive_kind IN ('complete', 'events', 'sessions', 'workspaces', 'evidence', 'logs')),
  artifact_id uuid NOT NULL,
  source_event_seq bigint,
  status text NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'verified', 'restored', 'invalid')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  verified_at timestamptz,
  UNIQUE (tenant_id, run_id, archive_kind, source_event_seq),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE exec.checkpoint (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  stage_id uuid,
  task_id uuid,
  task_attempt_id uuid,
  checkpoint_no bigint NOT NULL CHECK (checkpoint_no > 0),
  checkpoint_kind text NOT NULL
    CHECK (checkpoint_kind IN ('run', 'stage', 'task', 'session', 'workspace', 'verification', 'publish')),
  status text NOT NULL DEFAULT 'preparing'
    CHECK (status IN ('preparing', 'sealed', 'invalid', 'superseded', 'restored')),
  manifest_id uuid NOT NULL,
  resume_class text NOT NULL DEFAULT 'same_environment'
    CHECK (resume_class IN ('same_process', 'same_worker', 'same_environment', 'portable', 'manual_only')),
  source_event_seq bigint NOT NULL CHECK (source_event_seq >= 0),
  execution_epoch integer NOT NULL CHECK (execution_epoch > 0),
  state_sha256 text NOT NULL CHECK (core.sha256_is_valid(state_sha256)),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  sealed_at timestamptz,
  restored_at timestamptz,
  UNIQUE (tenant_id, run_id, checkpoint_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, stage_id) REFERENCES exec.run_stage(tenant_id, id),
  FOREIGN KEY (tenant_id, task_id) REFERENCES exec.task(tenant_id, id),
  FOREIGN KEY (tenant_id, task_attempt_id) REFERENCES exec.task_attempt(tenant_id, id),
  FOREIGN KEY (tenant_id, manifest_id) REFERENCES artifact.manifest(tenant_id, id),
  CHECK ((status = 'sealed' AND sealed_at IS NOT NULL) OR status <> 'sealed')
);

CREATE TABLE exec.checkpoint_component (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  checkpoint_id uuid NOT NULL,
  component_key text NOT NULL,
  component_version integer NOT NULL DEFAULT 1 CHECK (component_version > 0),
  artifact_id uuid NOT NULL,
  component_sha256 text NOT NULL CHECK (core.sha256_is_valid(component_sha256)),
  required_for_resume boolean NOT NULL DEFAULT true,
  restore_order integer NOT NULL DEFAULT 0,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (tenant_id, checkpoint_id, component_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, checkpoint_id) REFERENCES exec.checkpoint(tenant_id, id),
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TRIGGER checkpoint_component_immutable
BEFORE UPDATE OR DELETE ON exec.checkpoint_component
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE INDEX artifact_kind_created_idx ON artifact.artifact (tenant_id, artifact_kind, created_at DESC);
CREATE INDEX artifact_link_owner_idx ON artifact.artifact_link (tenant_id, owner_kind, owner_id);
CREATE INDEX staged_object_resume_idx ON artifact.staged_object (tenant_id, run_id, state, reserved_at)
  WHERE state NOT IN ('published', 'aborted');
CREATE INDEX checkpoint_run_latest_idx ON exec.checkpoint (tenant_id, run_id, checkpoint_no DESC)
  WHERE status = 'sealed';
CREATE INDEX checkpoint_task_latest_idx ON exec.checkpoint (tenant_id, task_id, checkpoint_no DESC)
  WHERE task_id IS NOT NULL AND status = 'sealed';

COMMIT;
