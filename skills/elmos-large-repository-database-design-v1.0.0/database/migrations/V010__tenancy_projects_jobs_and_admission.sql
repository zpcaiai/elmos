-- Tenancy, projects, repositories, immutable input revisions, jobs,
-- idempotent submissions, and authoritative three-slot account admission.

BEGIN;

CREATE TABLE core.tenant (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  slug extensions.citext NOT NULL UNIQUE CHECK (core.nonblank(slug::text)),
  display_name text NOT NULL CHECK (core.nonblank(display_name)),
  status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'suspended', 'closing', 'closed')),
  default_data_classification text NOT NULL DEFAULT 'internal'
    CHECK (default_data_classification IN ('public', 'internal', 'confidential', 'restricted')),
  encryption_key_ref text,
  retention_policy jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (core.json_object_or_empty(retention_policy)),
  settings jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (core.json_object_or_empty(settings)),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  closed_at timestamptz
);

CREATE TRIGGER tenant_touch_updated_at
BEFORE UPDATE ON core.tenant
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE core.account (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  external_subject text,
  email extensions.citext,
  display_name text,
  status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'disabled', 'locked', 'closed')),
  concurrency_limit smallint NOT NULL DEFAULT 3
    CHECK (concurrency_limit BETWEEN 0 AND 3),
  monthly_budget_microunits bigint CHECK (monthly_budget_microunits IS NULL OR monthly_budget_microunits >= 0),
  preferences jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (core.json_object_or_empty(preferences)),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE NULLS NOT DISTINCT (tenant_id, external_subject),
  UNIQUE NULLS NOT DISTINCT (tenant_id, email),
  UNIQUE (tenant_id, id)
);

CREATE TRIGGER account_touch_updated_at
BEFORE UPDATE ON core.account
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE core.project (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  project_key extensions.citext NOT NULL,
  name text NOT NULL CHECK (core.nonblank(name)),
  description text,
  status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'paused', 'archived', 'deleted')),
  default_branch text,
  data_classification text NOT NULL DEFAULT 'internal'
    CHECK (data_classification IN ('public', 'internal', 'confidential', 'restricted')),
  settings jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (core.json_object_or_empty(settings)),
  created_by_account_id uuid REFERENCES core.account(id),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  archived_at timestamptz,
  UNIQUE (tenant_id, project_key),
  UNIQUE (tenant_id, id)
);

CREATE TRIGGER project_touch_updated_at
BEFORE UPDATE ON core.project
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE core.repository (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  project_id uuid NOT NULL,
  repository_key extensions.citext NOT NULL,
  display_name text NOT NULL,
  repository_kind text NOT NULL DEFAULT 'git'
    CHECK (repository_kind IN ('git', 'archive', 'folder', 'generated', 'mirror')),
  canonical_uri text,
  provider text,
  default_branch text,
  visibility text NOT NULL DEFAULT 'private'
    CHECK (visibility IN ('public', 'internal', 'private', 'restricted')),
  credential_ref text,
  settings jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (core.json_object_or_empty(settings)),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, project_id, repository_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES core.project(tenant_id, id)
);

CREATE TRIGGER repository_touch_updated_at
BEFORE UPDATE ON core.repository
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE core.revision_snapshot (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  revision_kind text NOT NULL
    CHECK (revision_kind IN (
      'requirements', 'policy', 'workflow', 'model_route', 'toolchain',
      'environment', 'project_archetype', 'deployment_policy', 'pricing'
    )),
  logical_key text NOT NULL,
  version_label text,
  content_sha256 text NOT NULL CHECK (core.sha256_is_valid(content_sha256)),
  inline_document jsonb,
  artifact_id uuid,
  supersedes_revision_id uuid,
  created_by_account_id uuid REFERENCES core.account(id),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, revision_kind, logical_key, content_sha256),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, supersedes_revision_id) REFERENCES core.revision_snapshot(tenant_id, id),
  CHECK (inline_document IS NOT NULL OR artifact_id IS NOT NULL)
);

CREATE TRIGGER revision_snapshot_immutable
BEFORE UPDATE OR DELETE ON core.revision_snapshot
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE core.repository_revision (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  repository_id uuid NOT NULL,
  revision_kind text NOT NULL
    CHECK (revision_kind IN ('git_commit', 'git_tree', 'archive', 'workspace', 'generated', 'imported')),
  revision_ref text NOT NULL,
  commit_sha text,
  tree_sha256 text NOT NULL CHECK (core.sha256_is_valid(tree_sha256)),
  manifest_artifact_id uuid,
  parent_revision_id uuid,
  source_fetched_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, repository_id, revision_kind, revision_ref, tree_sha256),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, repository_id) REFERENCES core.repository(tenant_id, id),
  FOREIGN KEY (tenant_id, parent_revision_id) REFERENCES core.repository_revision(tenant_id, id)
);

CREATE TRIGGER repository_revision_immutable
BEFORE UPDATE OR DELETE ON core.repository_revision
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE core.job (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  project_id uuid NOT NULL,
  account_id uuid NOT NULL,
  job_type text NOT NULL
    CHECK (job_type IN (
      'project_generation', 'repository_conversion', 'language_conversion',
      'framework_modernization', 'repository_analysis', 'verification_only',
      'repair_only', 'deployment'
    )),
  title text NOT NULL CHECK (core.nonblank(title)),
  status text NOT NULL DEFAULT 'submitted'
    CHECK (status IN (
      'submitted', 'admission_wait', 'admitted', 'running', 'paused',
      'cancel_requested', 'verifying', 'human_review', 'completed',
      'failed', 'cancelled', 'blocked', 'archived'
    )),
  priority smallint NOT NULL DEFAULT 50 CHECK (priority BETWEEN 0 AND 100),
  requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  admitted_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  current_run_id uuid,
  latest_successful_run_id uuid,
  request_summary jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (core.json_object_or_empty(request_summary)),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES core.project(tenant_id, id),
  FOREIGN KEY (tenant_id, account_id) REFERENCES core.account(tenant_id, id)
);

CREATE TRIGGER job_touch_updated_at
BEFORE UPDATE ON core.job
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE core.job_submission (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  account_id uuid NOT NULL,
  project_id uuid NOT NULL,
  idempotency_key text NOT NULL CHECK (core.nonblank(idempotency_key)),
  request_sha256 text NOT NULL CHECK (core.sha256_is_valid(request_sha256)),
  job_id uuid NOT NULL,
  response_snapshot jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  expires_at timestamptz,
  UNIQUE (tenant_id, account_id, idempotency_key),
  FOREIGN KEY (tenant_id, account_id) REFERENCES core.account(tenant_id, id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES core.project(tenant_id, id),
  FOREIGN KEY (tenant_id, job_id) REFERENCES core.job(tenant_id, id)
);

CREATE TRIGGER job_submission_immutable
BEFORE UPDATE OR DELETE ON core.job_submission
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE core.job_input_revision (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  job_id uuid NOT NULL,
  input_role text NOT NULL
    CHECK (input_role IN (
      'source_repository', 'baseline_repository', 'target_repository',
      'requirements', 'policy', 'workflow', 'model_route', 'toolchain',
      'environment', 'project_archetype', 'deployment_policy', 'pricing'
    )),
  repository_revision_id uuid,
  revision_snapshot_id uuid,
  ordinal smallint NOT NULL DEFAULT 0 CHECK (ordinal >= 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, job_id, input_role, ordinal),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, job_id) REFERENCES core.job(tenant_id, id),
  FOREIGN KEY (tenant_id, repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, revision_snapshot_id) REFERENCES core.revision_snapshot(tenant_id, id),
  CHECK ((repository_revision_id IS NOT NULL)::integer + (revision_snapshot_id IS NOT NULL)::integer = 1)
);

CREATE TRIGGER job_input_revision_immutable
BEFORE UPDATE OR DELETE ON core.job_input_revision
FOR EACH ROW EXECUTE FUNCTION core.reject_update_delete();

CREATE TABLE core.account_task_slot (
  tenant_id uuid NOT NULL,
  account_id uuid NOT NULL,
  slot_no smallint NOT NULL CHECK (slot_no BETWEEN 1 AND 3),
  claimed_by_run_id uuid,
  claim_token uuid,
  lease_generation bigint NOT NULL DEFAULT 0 CHECK (lease_generation >= 0),
  claimed_at timestamptz,
  renewed_at timestamptz,
  lease_expires_at timestamptz,
  PRIMARY KEY (tenant_id, account_id, slot_no),
  UNIQUE NULLS NOT DISTINCT (tenant_id, claimed_by_run_id),
  FOREIGN KEY (tenant_id, account_id) REFERENCES core.account(tenant_id, id),
  CHECK (
    (claimed_by_run_id IS NULL AND claim_token IS NULL AND lease_expires_at IS NULL)
    OR
    (claimed_by_run_id IS NOT NULL AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL)
  )
);

CREATE OR REPLACE FUNCTION core.provision_account_task_slots()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO core.account_task_slot (tenant_id, account_id, slot_no)
  VALUES (NEW.tenant_id, NEW.id, 1), (NEW.tenant_id, NEW.id, 2), (NEW.tenant_id, NEW.id, 3);
  RETURN NEW;
END;
$$;

CREATE TRIGGER provision_account_task_slots
AFTER INSERT ON core.account
FOR EACH ROW EXECUTE FUNCTION core.provision_account_task_slots();

CREATE TRIGGER account_task_slot_no_delete
BEFORE DELETE ON core.account_task_slot
FOR EACH ROW EXECUTE FUNCTION core.reject_delete();

CREATE INDEX job_dispatch_idx
  ON core.job (tenant_id, status, priority DESC, requested_at)
  WHERE status IN ('submitted', 'admission_wait', 'admitted');
CREATE INDEX job_project_history_idx
  ON core.job (tenant_id, project_id, requested_at DESC);
CREATE INDEX repository_revision_lookup_idx
  ON core.repository_revision (tenant_id, repository_id, created_at DESC);
CREATE INDEX account_slot_expiry_idx
  ON core.account_task_slot (tenant_id, lease_expires_at)
  WHERE claimed_by_run_id IS NOT NULL;

COMMIT;
