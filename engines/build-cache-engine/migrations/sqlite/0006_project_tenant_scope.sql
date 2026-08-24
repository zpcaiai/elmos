-- Bind every v1.2 context/parity row to the exact tenant that owns its
-- project. SQLite cannot add a composite foreign key without rebuilding the
-- table, so this additive migration uses guarded INSERT/UPDATE triggers.
-- Application authorization and tenant-filtered reads remain separate duties.

CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_tenant_project
  ON projects (tenant_id, project_id);

-- Fail the migration before installing enforcement if a legacy database
-- already contains a cross-tenant or orphaned project reference. The store
-- runs this script and its migration-ledger insert in one transaction.
CREATE TEMP TABLE elmos_project_scope_guard (
  valid INTEGER NOT NULL CHECK (valid = 1)
);

INSERT INTO elmos_project_scope_guard (valid)
SELECT 0
FROM (
  SELECT tenant_id, project_id FROM context_ledger_streams
  UNION ALL
  SELECT tenant_id, project_id FROM context_ledger_events
  UNION ALL
  SELECT tenant_id, project_id FROM context_checkpoints
  UNION ALL
  SELECT tenant_id, project_id FROM prompt_prefix_manifests
  UNION ALL
  SELECT tenant_id, project_id FROM provider_cache_usage
  UNION ALL
  SELECT tenant_id, project_id FROM environment_snapshot_manifests
  UNION ALL
  SELECT tenant_id, project_id FROM environment_snapshot_status_events
  UNION ALL
  SELECT tenant_id, project_id FROM cache_outcome_events_v12
  UNION ALL
  SELECT tenant_id, project_id FROM cache_affinity_decisions_v12
  UNION ALL
  SELECT tenant_id, project_id FROM cache_parity_reports_v12
) AS scoped
LEFT JOIN projects AS owner ON owner.project_id = scoped.project_id
WHERE owner.tenant_id IS NULL OR owner.tenant_id <> scoped.tenant_id
LIMIT 1;

DROP TABLE elmos_project_scope_guard;

CREATE TRIGGER IF NOT EXISTS context_ledger_streams_project_scope_insert
BEFORE INSERT ON context_ledger_streams
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS context_ledger_streams_project_scope_update
BEFORE UPDATE OF tenant_id, project_id ON context_ledger_streams
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS context_ledger_events_project_scope_insert
BEFORE INSERT ON context_ledger_events
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS context_ledger_events_project_scope_update
BEFORE UPDATE OF tenant_id, project_id ON context_ledger_events
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS context_checkpoints_project_scope_insert
BEFORE INSERT ON context_checkpoints
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS context_checkpoints_project_scope_update
BEFORE UPDATE OF tenant_id, project_id ON context_checkpoints
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS prompt_prefix_manifests_project_scope_insert
BEFORE INSERT ON prompt_prefix_manifests
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS prompt_prefix_manifests_project_scope_update
BEFORE UPDATE OF tenant_id, project_id ON prompt_prefix_manifests
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS provider_cache_usage_project_scope_insert
BEFORE INSERT ON provider_cache_usage
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS provider_cache_usage_project_scope_update
BEFORE UPDATE OF tenant_id, project_id ON provider_cache_usage
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS environment_snapshot_manifests_project_scope_insert
BEFORE INSERT ON environment_snapshot_manifests
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS environment_snapshot_manifests_project_scope_update
BEFORE UPDATE OF tenant_id, project_id ON environment_snapshot_manifests
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS environment_snapshot_status_events_project_scope_insert
BEFORE INSERT ON environment_snapshot_status_events
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS environment_snapshot_status_events_project_scope_update
BEFORE UPDATE OF tenant_id, project_id ON environment_snapshot_status_events
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS cache_outcome_events_v12_project_scope_insert
BEFORE INSERT ON cache_outcome_events_v12
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS cache_outcome_events_v12_project_scope_update
BEFORE UPDATE OF tenant_id, project_id ON cache_outcome_events_v12
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS cache_affinity_decisions_v12_project_scope_insert
BEFORE INSERT ON cache_affinity_decisions_v12
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS cache_affinity_decisions_v12_project_scope_update
BEFORE UPDATE OF tenant_id, project_id ON cache_affinity_decisions_v12
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS cache_parity_reports_v12_project_scope_insert
BEFORE INSERT ON cache_parity_reports_v12
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;

CREATE TRIGGER IF NOT EXISTS cache_parity_reports_v12_project_scope_update
BEFORE UPDATE OF tenant_id, project_id ON cache_parity_reports_v12
FOR EACH ROW
WHEN NOT EXISTS (
  SELECT 1 FROM projects
  WHERE project_id = NEW.project_id AND tenant_id = NEW.tenant_id
)
BEGIN
  SELECT RAISE(ABORT, 'PROJECT_TENANT_SCOPE_MISMATCH');
END;
