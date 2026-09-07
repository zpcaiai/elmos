-- Bind every v1.2 context/parity row to the exact tenant that owns its
-- project. MetadataStore does not establish a trusted transaction-local
-- tenant session, so this migration intentionally does not enable RLS.
-- Composite ownership constraints protect project identity; application
-- authorization and tenant-filtered reads remain required.

ALTER TABLE projects
  ADD CONSTRAINT projects_tenant_project_key
  UNIQUE (tenant_id, project_id);

ALTER TABLE context_ledger_streams
  ADD CONSTRAINT fk_context_ledger_streams_project_scope
  FOREIGN KEY (tenant_id, project_id)
  REFERENCES projects (tenant_id, project_id)
  ON UPDATE RESTRICT ON DELETE RESTRICT
  NOT VALID;
ALTER TABLE context_ledger_streams
  VALIDATE CONSTRAINT fk_context_ledger_streams_project_scope;

ALTER TABLE context_ledger_events
  ADD CONSTRAINT fk_context_ledger_events_project_scope
  FOREIGN KEY (tenant_id, project_id)
  REFERENCES projects (tenant_id, project_id)
  ON UPDATE RESTRICT ON DELETE RESTRICT
  NOT VALID;
ALTER TABLE context_ledger_events
  VALIDATE CONSTRAINT fk_context_ledger_events_project_scope;

ALTER TABLE context_checkpoints
  ADD CONSTRAINT fk_context_checkpoints_project_scope
  FOREIGN KEY (tenant_id, project_id)
  REFERENCES projects (tenant_id, project_id)
  ON UPDATE RESTRICT ON DELETE RESTRICT
  NOT VALID;
ALTER TABLE context_checkpoints
  VALIDATE CONSTRAINT fk_context_checkpoints_project_scope;

ALTER TABLE prompt_prefix_manifests
  ADD CONSTRAINT fk_prompt_prefix_manifests_project_scope
  FOREIGN KEY (tenant_id, project_id)
  REFERENCES projects (tenant_id, project_id)
  ON UPDATE RESTRICT ON DELETE RESTRICT
  NOT VALID;
ALTER TABLE prompt_prefix_manifests
  VALIDATE CONSTRAINT fk_prompt_prefix_manifests_project_scope;

ALTER TABLE provider_cache_usage
  ADD CONSTRAINT fk_provider_cache_usage_project_scope
  FOREIGN KEY (tenant_id, project_id)
  REFERENCES projects (tenant_id, project_id)
  ON UPDATE RESTRICT ON DELETE RESTRICT
  NOT VALID;
ALTER TABLE provider_cache_usage
  VALIDATE CONSTRAINT fk_provider_cache_usage_project_scope;

ALTER TABLE environment_snapshot_manifests
  ADD CONSTRAINT fk_environment_snapshot_manifests_project_scope
  FOREIGN KEY (tenant_id, project_id)
  REFERENCES projects (tenant_id, project_id)
  ON UPDATE RESTRICT ON DELETE RESTRICT
  NOT VALID;
ALTER TABLE environment_snapshot_manifests
  VALIDATE CONSTRAINT fk_environment_snapshot_manifests_project_scope;

ALTER TABLE environment_snapshot_status_events
  ADD CONSTRAINT fk_environment_snapshot_status_events_project_scope
  FOREIGN KEY (tenant_id, project_id)
  REFERENCES projects (tenant_id, project_id)
  ON UPDATE RESTRICT ON DELETE RESTRICT
  NOT VALID;
ALTER TABLE environment_snapshot_status_events
  VALIDATE CONSTRAINT fk_environment_snapshot_status_events_project_scope;

ALTER TABLE cache_outcome_events_v12
  ADD CONSTRAINT fk_cache_outcome_events_v12_project_scope
  FOREIGN KEY (tenant_id, project_id)
  REFERENCES projects (tenant_id, project_id)
  ON UPDATE RESTRICT ON DELETE RESTRICT
  NOT VALID;
ALTER TABLE cache_outcome_events_v12
  VALIDATE CONSTRAINT fk_cache_outcome_events_v12_project_scope;

ALTER TABLE cache_affinity_decisions_v12
  ADD CONSTRAINT fk_cache_affinity_decisions_v12_project_scope
  FOREIGN KEY (tenant_id, project_id)
  REFERENCES projects (tenant_id, project_id)
  ON UPDATE RESTRICT ON DELETE RESTRICT
  NOT VALID;
ALTER TABLE cache_affinity_decisions_v12
  VALIDATE CONSTRAINT fk_cache_affinity_decisions_v12_project_scope;

ALTER TABLE cache_parity_reports_v12
  ADD CONSTRAINT fk_cache_parity_reports_v12_project_scope
  FOREIGN KEY (tenant_id, project_id)
  REFERENCES projects (tenant_id, project_id)
  ON UPDATE RESTRICT ON DELETE RESTRICT
  NOT VALID;
ALTER TABLE cache_parity_reports_v12
  VALIDATE CONSTRAINT fk_cache_parity_reports_v12_project_scope;
