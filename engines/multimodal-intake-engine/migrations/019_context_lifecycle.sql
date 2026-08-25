BEGIN IMMEDIATE;

CREATE TABLE context_capability_snapshots (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  model_id TEXT NOT NULL,
  version INTEGER NOT NULL CHECK (version > 0),
  snapshot_json TEXT NOT NULL,
  snapshot_digest TEXT NOT NULL,
  source TEXT NOT NULL,
  trust TEXT NOT NULL,
  observed_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  previous_snapshot_id TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, snapshot_id),
  UNIQUE (tenant_id, project_id, provider, model_id, version),
  CHECK (expires_at > observed_at),
  CHECK (length(snapshot_digest) = 64)
);

CREATE TABLE context_capability_heads (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  model_id TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  version INTEGER NOT NULL CHECK (version > 0),
  updated_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, provider, model_id),
  FOREIGN KEY (tenant_id, project_id, snapshot_id)
    REFERENCES context_capability_snapshots (tenant_id, project_id, snapshot_id)
);

CREATE TABLE context_usage_ledger (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  usage_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  model_snapshot_id TEXT,
  estimator_version TEXT NOT NULL,
  accounting_digest TEXT NOT NULL,
  current_window_input_tokens INTEGER NOT NULL CHECK (current_window_input_tokens >= 0),
  current_window_output_reserved_tokens INTEGER NOT NULL CHECK (current_window_output_reserved_tokens >= 0),
  cumulative_provider_input_tokens INTEGER NOT NULL CHECK (cumulative_provider_input_tokens >= 0),
  cumulative_provider_output_tokens INTEGER NOT NULL CHECK (cumulative_provider_output_tokens >= 0),
  cumulative_cost_minor_units INTEGER NOT NULL CHECK (cumulative_cost_minor_units >= 0),
  currency TEXT NOT NULL,
  estimate_kind TEXT NOT NULL CHECK (estimate_kind IN ('MEASURED_VERIFIED','ESTIMATED_UPPER_BOUND','MIXED_UPPER_BOUND')),
  record_json TEXT NOT NULL,
  record_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, usage_id),
  UNIQUE (tenant_id, project_id, idempotency_key),
  CHECK (length(accounting_digest) = 64),
  CHECK (length(record_digest) = 64)
);

CREATE TABLE context_lifecycle_records (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  record_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('PARITY','BUDGET','PACKING','COMPACTION','REHYDRATION')),
  request_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  parent_record_id TEXT,
  payload_json TEXT NOT NULL,
  payload_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, record_id),
  UNIQUE (tenant_id, project_id, kind, idempotency_key),
  CHECK (length(payload_digest) = 64)
);

CREATE TABLE context_pressure_snapshots (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  pressure_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  previous_pressure_id TEXT,
  previous_state TEXT NOT NULL,
  pressure_state TEXT NOT NULL,
  used_tokens INTEGER NOT NULL CHECK (used_tokens >= 0),
  effective_input_budget INTEGER NOT NULL CHECK (effective_input_budget > 0),
  forecast_tokens INTEGER NOT NULL CHECK (forecast_tokens >= 0),
  forecast_horizon INTEGER NOT NULL CHECK (forecast_horizon >= 0),
  action TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  snapshot_json TEXT NOT NULL,
  snapshot_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, pressure_id),
  UNIQUE (tenant_id, project_id, idempotency_key),
  CHECK (previous_state IN ('NORMAL','ELEVATED','HIGH','CRITICAL')),
  CHECK (pressure_state IN ('NORMAL','ELEVATED','HIGH','CRITICAL')),
  CHECK (length(snapshot_digest) = 64)
);

CREATE TABLE context_integrity_reports (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  report_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  checkpoint_id TEXT,
  passed INTEGER NOT NULL CHECK (passed IN (0,1)),
  side_effect_authorized INTEGER NOT NULL CHECK (side_effect_authorized IN (0,1)),
  report_json TEXT NOT NULL,
  report_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, report_id),
  UNIQUE (tenant_id, project_id, idempotency_key),
  CHECK (side_effect_authorized = passed),
  CHECK (length(report_digest) = 64)
);

CREATE TABLE context_checkpoints (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  checkpoint_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  package_version TEXT NOT NULL,
  model_snapshot_id TEXT,
  raw_history_digest TEXT NOT NULL,
  raw_history_bytes INTEGER NOT NULL CHECK (raw_history_bytes > 0),
  checkpoint_json TEXT NOT NULL,
  checkpoint_digest TEXT NOT NULL,
  integrity_report_id TEXT NOT NULL,
  rollback_checkpoint_id TEXT,
  side_effect_cursor_digest TEXT NOT NULL,
  cost_cursor_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, checkpoint_id),
  UNIQUE (tenant_id, project_id, idempotency_key),
  CHECK (length(raw_history_digest) = 64),
  CHECK (length(checkpoint_digest) = 64),
  CHECK (length(side_effect_cursor_digest) = 64),
  CHECK (length(cost_cursor_digest) = 64),
  FOREIGN KEY (tenant_id, project_id, integrity_report_id)
    REFERENCES context_integrity_reports (tenant_id, project_id, report_id)
);

CREATE TABLE context_recovery_attempts (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL,
  checkpoint_id TEXT NOT NULL,
  restore_request_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  outcome TEXT NOT NULL CHECK (outcome IN ('RESTORED','RECONCILE','BLOCKED')),
  side_effect_cursor_digest TEXT NOT NULL,
  cost_cursor_digest TEXT NOT NULL,
  result_json TEXT NOT NULL,
  result_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, attempt_id),
  UNIQUE (tenant_id, project_id, idempotency_key),
  CHECK (length(side_effect_cursor_digest) = 64),
  CHECK (length(cost_cursor_digest) = 64),
  CHECK (length(result_digest) = 64),
  FOREIGN KEY (tenant_id, project_id, checkpoint_id)
    REFERENCES context_checkpoints (tenant_id, project_id, checkpoint_id)
);

CREATE INDEX context_usage_task_time
  ON context_usage_ledger (tenant_id, project_id, task_id, created_at);
CREATE INDEX context_pressure_task_time
  ON context_pressure_snapshots (tenant_id, project_id, task_id, created_at);
CREATE INDEX context_checkpoint_task_time
  ON context_checkpoints (tenant_id, project_id, task_id, created_at);
CREATE INDEX context_integrity_task_time
  ON context_integrity_reports (tenant_id, project_id, task_id, created_at);

CREATE TRIGGER context_capability_snapshots_no_update BEFORE UPDATE ON context_capability_snapshots
BEGIN SELECT RAISE(ABORT, 'context capability snapshots are immutable'); END;
CREATE TRIGGER context_capability_snapshots_no_delete BEFORE DELETE ON context_capability_snapshots
BEGIN SELECT RAISE(ABORT, 'context capability snapshots are immutable'); END;
CREATE TRIGGER context_usage_ledger_no_update BEFORE UPDATE ON context_usage_ledger
BEGIN SELECT RAISE(ABORT, 'context usage ledger is append only'); END;
CREATE TRIGGER context_usage_ledger_no_delete BEFORE DELETE ON context_usage_ledger
BEGIN SELECT RAISE(ABORT, 'context usage ledger is append only'); END;
CREATE TRIGGER context_lifecycle_records_no_update BEFORE UPDATE ON context_lifecycle_records
BEGIN SELECT RAISE(ABORT, 'context lifecycle records are immutable'); END;
CREATE TRIGGER context_lifecycle_records_no_delete BEFORE DELETE ON context_lifecycle_records
BEGIN SELECT RAISE(ABORT, 'context lifecycle records are immutable'); END;
CREATE TRIGGER context_pressure_snapshots_no_update BEFORE UPDATE ON context_pressure_snapshots
BEGIN SELECT RAISE(ABORT, 'context pressure snapshots are immutable'); END;
CREATE TRIGGER context_pressure_snapshots_no_delete BEFORE DELETE ON context_pressure_snapshots
BEGIN SELECT RAISE(ABORT, 'context pressure snapshots are immutable'); END;
CREATE TRIGGER context_checkpoints_no_update BEFORE UPDATE ON context_checkpoints
BEGIN SELECT RAISE(ABORT, 'context checkpoints are immutable'); END;
CREATE TRIGGER context_checkpoints_no_delete BEFORE DELETE ON context_checkpoints
BEGIN SELECT RAISE(ABORT, 'context checkpoints are immutable'); END;
CREATE TRIGGER context_integrity_reports_no_update BEFORE UPDATE ON context_integrity_reports
BEGIN SELECT RAISE(ABORT, 'context integrity reports are immutable'); END;
CREATE TRIGGER context_integrity_reports_no_delete BEFORE DELETE ON context_integrity_reports
BEGIN SELECT RAISE(ABORT, 'context integrity reports are immutable'); END;
CREATE TRIGGER context_recovery_attempts_no_update BEFORE UPDATE ON context_recovery_attempts
BEGIN SELECT RAISE(ABORT, 'context recovery attempts are immutable'); END;
CREATE TRIGGER context_recovery_attempts_no_delete BEFORE DELETE ON context_recovery_attempts
BEGIN SELECT RAISE(ABORT, 'context recovery attempts are immutable'); END;

PRAGMA user_version = 19;
COMMIT;
