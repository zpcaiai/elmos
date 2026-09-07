-- Destructive rollback for migration 0002. Run only through an approved change
-- workflow after exporting immutable evidence and event data.
DROP TABLE IF EXISTS oh_retention_partitions;
DROP TABLE IF EXISTS oh_execution_event_archive CASCADE;
DROP TABLE IF EXISTS oh_retention_actions;
DROP TABLE IF EXISTS oh_governed_objects;
DROP TABLE IF EXISTS oh_retention_policies;
DROP TABLE IF EXISTS oh_qualification_runs;
DROP TABLE IF EXISTS oh_evidence_verifications;
DROP TABLE IF EXISTS oh_evidence_packs;
DROP TABLE IF EXISTS oh_agent_nodes;
DROP TABLE IF EXISTS oh_package_lifecycle_events;
DROP TABLE IF EXISTS oh_package_bundles;
DROP TABLE IF EXISTS oh_run_package_pins;
DROP TABLE IF EXISTS oh_capability_packages;
DROP TABLE IF EXISTS oh_approval_decisions;
DROP TABLE IF EXISTS oh_approvals;
DROP TABLE IF EXISTS oh_provider_sessions;
DROP TABLE IF EXISTS oh_tenant_usage;
DROP TABLE IF EXISTS oh_tenant_quotas;
DROP TABLE IF EXISTS oh_worker_leases;
DROP TABLE IF EXISTS oh_workspace_leases;
DROP TABLE IF EXISTS oh_projections;
DROP TABLE IF EXISTS oh_checkpoints;
DROP TABLE IF EXISTS oh_run_leases;
ALTER TABLE oh_execution_events
  DROP COLUMN IF EXISTS causation_event_id,
  DROP COLUMN IF EXISTS correlation_id,
  DROP COLUMN IF EXISTS schema_version,
  DROP COLUMN IF EXISTS event_timestamp;
DROP INDEX IF EXISTS oh_events_tenant_run_type_seq_idx;
DROP INDEX IF EXISTS oh_events_tenant_created_idx;
DROP INDEX IF EXISTS oh_outbox_unpublished_idx;
DROP POLICY IF EXISTS oh_execution_outbox_tenant_isolation ON oh_execution_outbox;
ALTER TABLE oh_execution_outbox NO FORCE ROW LEVEL SECURITY;
ALTER TABLE oh_execution_outbox DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS oh_execution_runs_tenant_isolation ON oh_execution_runs;
ALTER TABLE oh_execution_runs NO FORCE ROW LEVEL SECURITY;
ALTER TABLE oh_execution_runs DISABLE ROW LEVEL SECURITY;
ALTER TABLE oh_execution_events NO FORCE ROW LEVEL SECURITY;
DROP FUNCTION IF EXISTS oh_reject_immutable_mutation();
