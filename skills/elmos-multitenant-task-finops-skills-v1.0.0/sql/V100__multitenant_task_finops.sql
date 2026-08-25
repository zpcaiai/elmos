-- Elmos Multi-Tenant Task Control & FinOps
-- Reference Flyway migration V100
-- PostgreSQL 15+; target Elmos reference uses PostgreSQL 18.
-- Adapt identity/project foreign keys to the target repository after contract freeze.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS elmos;
SET search_path = elmos, public;

CREATE TYPE task_state AS ENUM (
  'CREATED',
  'WAITING_FOR_SLOT',
  'ADMITTED',
  'STARTING',
  'RUNNING',
  'PAUSE_REQUESTED',
  'PAUSING',
  'PAUSED',
  'RETRY_WAIT',
  'CANCEL_REQUESTED',
  'CANCELLING',
  'UNKNOWN_RESULT',
  'RECONCILING',
  'MANUAL_RECOVERY',
  'SUCCEEDED',
  'FAILED',
  'CANCELLED'
);

CREATE TYPE node_state AS ENUM (
  'PLANNED',
  'BLOCKED',
  'READY',
  'SCHEDULED',
  'LEASED',
  'RUNNING',
  'CHECKPOINTING',
  'PAUSE_REQUESTED',
  'PAUSED',
  'RETRY_WAIT',
  'CANCEL_REQUESTED',
  'UNKNOWN_RESULT',
  'RECONCILING',
  'SUCCEEDED',
  'FAILED',
  'CANCELLED',
  'SKIPPED'
);

CREATE TYPE outbox_state AS ENUM (
  'PENDING',
  'CLAIMED',
  'DELIVERED',
  'RETRY_WAIT',
  'DEAD_LETTER'
);

CREATE TYPE financial_status AS ENUM (
  'ESTIMATED',
  'POSTING',
  'PARTIAL_PROVIDER_DATA',
  'UNRECONCILED',
  'COMPLETE',
  'FINAL',
  'MANUAL_REVIEW'
);

CREATE TABLE tenant_runtime_quota (
  tenant_id uuid PRIMARY KEY,
  max_active_tasks integer NOT NULL CHECK (max_active_tasks >= 0),
  max_queued_tasks integer NOT NULL CHECK (max_queued_tasks >= 0),
  max_concurrency_units numeric(18,6) NOT NULL CHECK (max_concurrency_units >= 0),
  monthly_cost_budget numeric(24,8),
  budget_currency char(3),
  policy_version text NOT NULL,
  effective_from timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_by text NOT NULL
);

CREATE TABLE task (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  account_id uuid NOT NULL,
  project_id uuid,
  task_type text NOT NULL,
  title text NOT NULL,
  request_schema_version text NOT NULL DEFAULT '1.0',
  request_hash text NOT NULL,
  idempotency_key text NOT NULL,
  state task_state NOT NULL DEFAULT 'CREATED',
  priority smallint NOT NULL DEFAULT 50 CHECK (priority BETWEEN 0 AND 100),
  workload_class text NOT NULL,
  estimated_concurrency_units numeric(18,6) NOT NULL DEFAULT 1 CHECK (estimated_concurrency_units > 0),
  admission_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  queue_entered_at timestamptz,
  admitted_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  current_run_id uuid,
  current_node_key text,
  latest_checkpoint_id uuid,
  version bigint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  deleted_at timestamptz,
  CONSTRAINT uq_task_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_task_submit_idempotency UNIQUE (tenant_id, account_id, idempotency_key)
);

CREATE TABLE account_task_slot (
  account_id uuid NOT NULL,
  slot_no smallint NOT NULL CHECK (slot_no BETWEEN 1 AND 3),
  tenant_id uuid,
  task_id uuid,
  lease_generation bigint NOT NULL DEFAULT 0,
  claimed_at timestamptz,
  lease_expires_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (account_id, slot_no),
  CONSTRAINT uq_account_slot_task UNIQUE (task_id),
  CONSTRAINT ck_account_slot_occupancy CHECK (
    (tenant_id IS NULL AND task_id IS NULL AND claimed_at IS NULL AND lease_expires_at IS NULL)
    OR
    (tenant_id IS NOT NULL AND task_id IS NOT NULL AND claimed_at IS NOT NULL AND lease_expires_at IS NOT NULL)
  ),
  CONSTRAINT fk_account_slot_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id)
);

CREATE TABLE task_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  task_id uuid NOT NULL,
  run_no integer NOT NULL CHECK (run_no > 0),
  parent_run_id uuid,
  fork_checkpoint_id uuid,
  workflow_id text NOT NULL,
  workflow_run_id text,
  state task_state NOT NULL,
  next_event_sequence bigint NOT NULL DEFAULT 0,
  queue_time_ms bigint NOT NULL DEFAULT 0,
  execution_time_ms bigint NOT NULL DEFAULT 0,
  model_time_ms bigint NOT NULL DEFAULT 0,
  validation_time_ms bigint NOT NULL DEFAULT 0,
  transfer_time_ms bigint NOT NULL DEFAULT 0,
  recovery_time_ms bigint NOT NULL DEFAULT 0,
  human_wait_time_ms bigint NOT NULL DEFAULT 0,
  recovery_count integer NOT NULL DEFAULT 0,
  retry_count integer NOT NULL DEFAULT 0,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_task_run_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT uq_task_run_number UNIQUE (task_id, run_no),
  CONSTRAINT uq_task_run_workflow UNIQUE (workflow_id),
  CONSTRAINT fk_task_run_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id)
);

CREATE TABLE task_node (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  task_id uuid NOT NULL,
  task_run_id uuid NOT NULL,
  node_key text NOT NULL,
  node_type text NOT NULL,
  state node_state NOT NULL DEFAULT 'PLANNED',
  dependency_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
  weight numeric(18,8) NOT NULL DEFAULT 1 CHECK (weight >= 0),
  progress numeric(9,6) NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 1),
  completed_units numeric(24,8),
  total_units numeric(24,8),
  current_attempt_no integer NOT NULL DEFAULT 0,
  current_attempt_id uuid,
  last_heartbeat_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_task_node UNIQUE (task_run_id, node_key),
  CONSTRAINT uq_task_node_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT fk_task_node_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id),
  CONSTRAINT fk_task_node_run FOREIGN KEY (tenant_id, task_run_id)
    REFERENCES task_run (tenant_id, id)
);

CREATE TABLE task_node_attempt (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  task_id uuid NOT NULL,
  task_run_id uuid NOT NULL,
  task_node_id uuid NOT NULL,
  node_key text NOT NULL,
  attempt_no integer NOT NULL CHECK (attempt_no > 0),
  lease_generation bigint NOT NULL DEFAULT 0,
  state node_state NOT NULL,
  worker_type text,
  worker_id text,
  runner_id text,
  lease_expires_at timestamptz,
  heartbeat_at timestamptz,
  error_class text,
  error_code text,
  error_summary text,
  retryable boolean,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_node_attempt UNIQUE (task_run_id, node_key, attempt_no),
  CONSTRAINT uq_node_attempt_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT fk_attempt_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id),
  CONSTRAINT fk_attempt_run FOREIGN KEY (tenant_id, task_run_id)
    REFERENCES task_run (tenant_id, id),
  CONSTRAINT fk_attempt_node FOREIGN KEY (tenant_id, task_node_id)
    REFERENCES task_node (tenant_id, id)
);

CREATE TABLE task_event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  account_id uuid NOT NULL,
  project_id uuid,
  task_id uuid NOT NULL,
  task_run_id uuid NOT NULL,
  task_node_id uuid,
  node_attempt_id uuid,
  sequence_no bigint NOT NULL CHECK (sequence_no > 0),
  event_type text NOT NULL,
  transition_id text NOT NULL,
  actor_type text NOT NULL,
  actor_id text,
  old_state text,
  new_state text,
  checkpoint_id uuid,
  trace_id text,
  request_id text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_task_event_sequence UNIQUE (task_run_id, sequence_no),
  CONSTRAINT uq_task_event_transition UNIQUE (transition_id),
  CONSTRAINT fk_event_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id),
  CONSTRAINT fk_event_run FOREIGN KEY (tenant_id, task_run_id)
    REFERENCES task_run (tenant_id, id)
);

CREATE TABLE task_progress_snapshot (
  task_run_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  task_id uuid NOT NULL,
  event_sequence_watermark bigint NOT NULL DEFAULT 0,
  state task_state NOT NULL,
  current_node_key text,
  progress numeric(9,6) NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 1),
  elapsed_ms bigint NOT NULL DEFAULT 0,
  eta_p50_ms bigint,
  eta_p90_ms bigint,
  node_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
  retry_count integer NOT NULL DEFAULT 0,
  recovery_count integer NOT NULL DEFAULT 0,
  latest_checkpoint_id uuid,
  weight_model_version text,
  as_of timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT fk_progress_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id),
  CONSTRAINT fk_progress_run FOREIGN KEY (tenant_id, task_run_id)
    REFERENCES task_run (tenant_id, id)
);

CREATE TABLE task_checkpoint (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  task_id uuid NOT NULL,
  task_run_id uuid NOT NULL,
  task_node_id uuid,
  node_attempt_id uuid,
  node_key text,
  checkpoint_no integer NOT NULL CHECK (checkpoint_no > 0),
  schema_version text NOT NULL,
  input_manifest_sha256 text NOT NULL,
  repository_revision text,
  state_sha256 text NOT NULL,
  object_uri text,
  object_sha256 text,
  object_size_bytes bigint CHECK (object_size_bytes IS NULL OR object_size_bytes >= 0),
  encryption_key_ref text,
  completed_side_effect_receipts jsonb NOT NULL DEFAULT '[]'::jsonb,
  cache_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
  tool_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
  model_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
  policy_version text NOT NULL,
  next_node_key text,
  compatibility jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_checkpoint_no UNIQUE (task_run_id, checkpoint_no),
  CONSTRAINT uq_checkpoint_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT fk_checkpoint_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id),
  CONSTRAINT fk_checkpoint_run FOREIGN KEY (tenant_id, task_run_id)
    REFERENCES task_run (tenant_id, id)
);

CREATE TABLE task_side_effect_receipt (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  task_id uuid NOT NULL,
  task_run_id uuid NOT NULL,
  node_key text,
  node_attempt_id uuid,
  operation_type text NOT NULL,
  idempotency_key text NOT NULL,
  intent_sha256 text NOT NULL,
  provider text,
  external_object_id text,
  provider_request_id text,
  request_sha256 text,
  response_sha256 text,
  status text NOT NULL CHECK (status IN ('INTENT_RECORDED','IN_PROGRESS','SUCCEEDED','FAILED','COMPENSATED','UNKNOWN')),
  attempt_no integer,
  lease_generation bigint,
  compensation_receipt_id uuid,
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_side_effect_idempotency UNIQUE (task_run_id, operation_type, idempotency_key),
  CONSTRAINT uq_side_effect_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT fk_receipt_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id),
  CONSTRAINT fk_receipt_run FOREIGN KEY (tenant_id, task_run_id)
    REFERENCES task_run (tenant_id, id)
);

CREATE TABLE task_input (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  task_id uuid NOT NULL,
  input_role text NOT NULL,
  schema_version text NOT NULL,
  inline_json jsonb,
  object_uri text,
  object_sha256 text,
  object_size_bytes bigint CHECK (object_size_bytes IS NULL OR object_size_bytes >= 0),
  media_type text,
  encryption_key_ref text,
  retention_class text NOT NULL,
  redaction_status text NOT NULL DEFAULT 'PENDING',
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT ck_task_input_content CHECK (inline_json IS NOT NULL OR object_uri IS NOT NULL),
  CONSTRAINT fk_input_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id)
);

CREATE TABLE task_artifact (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  task_id uuid NOT NULL,
  task_run_id uuid NOT NULL,
  task_node_id uuid,
  artifact_role text NOT NULL,
  artifact_type text NOT NULL,
  version_no integer NOT NULL CHECK (version_no > 0),
  object_uri text NOT NULL,
  object_sha256 text NOT NULL,
  object_size_bytes bigint NOT NULL CHECK (object_size_bytes >= 0),
  media_type text NOT NULL,
  encryption_key_ref text,
  retention_class text NOT NULL,
  integrity_status text NOT NULL DEFAULT 'PENDING',
  evidence_bindings jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_artifact_version UNIQUE (task_id, artifact_role, version_no),
  CONSTRAINT uq_artifact_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT fk_artifact_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id),
  CONSTRAINT fk_artifact_run FOREIGN KEY (tenant_id, task_run_id)
    REFERENCES task_run (tenant_id, id)
);

CREATE TABLE task_log_segment (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  task_id uuid NOT NULL,
  task_run_id uuid NOT NULL,
  node_key text,
  node_attempt_id uuid,
  segment_no bigint NOT NULL CHECK (segment_no > 0),
  first_observed_at timestamptz NOT NULL,
  last_observed_at timestamptz NOT NULL,
  object_uri text NOT NULL,
  object_sha256 text NOT NULL,
  object_size_bytes bigint NOT NULL CHECK (object_size_bytes >= 0),
  redaction_status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_log_segment UNIQUE (task_run_id, node_key, node_attempt_id, segment_no),
  CONSTRAINT fk_log_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id),
  CONSTRAINT fk_log_run FOREIGN KEY (tenant_id, task_run_id)
    REFERENCES task_run (tenant_id, id)
);

CREATE TABLE outbox_event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  aggregate_type text NOT NULL,
  aggregate_id uuid NOT NULL,
  event_type text NOT NULL,
  schema_version text NOT NULL,
  idempotency_key text NOT NULL,
  payload jsonb NOT NULL,
  payload_sha256 text NOT NULL,
  state outbox_state NOT NULL DEFAULT 'PENDING',
  available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  claimed_by text,
  claim_expires_at timestamptz,
  attempt_count integer NOT NULL DEFAULT 0,
  last_error text,
  delivered_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_outbox_idempotency UNIQUE (idempotency_key)
);

-- Internal consumer deduplication store for at-least-once event delivery.
-- It is not exposed to tenant-facing roles; grant only to approved consumer roles.
CREATE TABLE inbox_event_dedup (
  consumer_name text NOT NULL,
  event_id uuid NOT NULL,
  tenant_id uuid,
  event_type text NOT NULL,
  payload_sha256 text,
  first_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  processed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  result_status text NOT NULL DEFAULT 'PROCESSED',
  PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE price_book_item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  price_book_version text NOT NULL,
  provider text NOT NULL,
  sku text NOT NULL,
  usage_type text NOT NULL,
  unit text NOT NULL,
  region text,
  tier_min numeric(30,10),
  tier_max numeric(30,10),
  unit_price numeric(30,12) NOT NULL CHECK (unit_price >= 0),
  currency char(3) NOT NULL,
  effective_from timestamptz NOT NULL,
  effective_to timestamptz,
  rounding_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_reference text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_price_item UNIQUE (
    price_book_version, provider, sku, usage_type, unit, region, effective_from
  ),
  CONSTRAINT ck_price_effective CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE TABLE usage_event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  account_id uuid NOT NULL,
  project_id uuid,
  task_id uuid NOT NULL,
  task_run_id uuid NOT NULL,
  node_key text,
  node_attempt_id uuid,
  idempotency_key text NOT NULL,
  provider_receipt_id text,
  provider_request_id text,
  provider text NOT NULL,
  sku text NOT NULL,
  usage_type text NOT NULL,
  unit text NOT NULL,
  quantity numeric(30,10) NOT NULL,
  price_book_item_id uuid,
  price_book_version text NOT NULL,
  unit_price numeric(30,12) NOT NULL,
  original_currency char(3) NOT NULL,
  original_cost numeric(30,12) NOT NULL,
  base_currency char(3) NOT NULL,
  fx_rate numeric(30,12) NOT NULL CHECK (fx_rate > 0),
  base_cost numeric(30,12) NOT NULL,
  cost_status text NOT NULL CHECK (cost_status IN ('ESTIMATE','POSTED','FINAL','CORRECTION')),
  calculation_version text NOT NULL,
  occurred_at timestamptz NOT NULL,
  ingested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  trace_id text,
  raw_usage jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT uq_usage_idempotency UNIQUE (idempotency_key),
  CONSTRAINT fk_usage_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id),
  CONSTRAINT fk_usage_run FOREIGN KEY (tenant_id, task_run_id)
    REFERENCES task_run (tenant_id, id),
  CONSTRAINT fk_usage_price FOREIGN KEY (price_book_item_id)
    REFERENCES price_book_item (id)
);

CREATE UNIQUE INDEX uq_usage_provider_receipt
  ON usage_event (provider, provider_receipt_id, usage_type)
  WHERE provider_receipt_id IS NOT NULL;

CREATE TABLE task_cost_summary (
  task_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  estimated_cost numeric(30,12) NOT NULL DEFAULT 0,
  reserved_cost numeric(30,12) NOT NULL DEFAULT 0,
  posted_actual_cost numeric(30,12) NOT NULL DEFAULT 0,
  final_actual_cost numeric(30,12),
  human_review_cost numeric(30,12) NOT NULL DEFAULT 0,
  reporting_currency char(3) NOT NULL,
  status financial_status NOT NULL DEFAULT 'ESTIMATED',
  usage_event_watermark timestamptz,
  as_of timestamptz NOT NULL DEFAULT clock_timestamp(),
  reconciliation_status text NOT NULL DEFAULT 'UNRECONCILED',
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT fk_cost_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id)
);

CREATE TABLE revenue_entry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  account_id uuid,
  project_id uuid,
  task_id uuid,
  task_run_id uuid,
  billing_account_id uuid,
  source_entry_id uuid,
  kind text NOT NULL CHECK (kind IN (
    'QUOTE','CHARGE','CREDIT','REFUND','RECOGNITION','COLLECTION',
    'PAYMENT_FEE','TAX','ADJUSTMENT'
  )),
  billing_mode text NOT NULL,
  idempotency_key text NOT NULL,
  external_object_id text,
  amount numeric(30,12) NOT NULL,
  currency char(3) NOT NULL,
  base_currency char(3) NOT NULL,
  fx_rate numeric(30,12) NOT NULL CHECK (fx_rate > 0),
  base_amount numeric(30,12) NOT NULL,
  recognition_basis text,
  status text NOT NULL,
  policy_version text NOT NULL,
  occurred_at timestamptz NOT NULL,
  posted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT uq_revenue_idempotency UNIQUE (idempotency_key),
  CONSTRAINT uq_revenue_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT fk_revenue_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id)
);

CREATE TABLE revenue_allocation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  source_revenue_entry_id uuid NOT NULL,
  project_id uuid,
  task_id uuid,
  task_run_id uuid,
  allocation_method text NOT NULL CHECK (allocation_method IN (
    'DIRECT','MILESTONE','USAGE_WEIGHTED','MANUAL_APPROVED'
  )),
  allocation_policy_version text NOT NULL,
  weight numeric(30,12),
  allocated_amount numeric(30,12) NOT NULL,
  currency char(3) NOT NULL,
  approved_by text,
  occurred_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_revenue_allocation UNIQUE (
    source_revenue_entry_id, task_id, task_run_id, allocation_policy_version
  ),
  CONSTRAINT fk_allocation_source FOREIGN KEY (tenant_id, source_revenue_entry_id)
    REFERENCES revenue_entry (tenant_id, id),
  CONSTRAINT fk_allocation_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id)
);

CREATE TABLE task_financial_summary (
  task_id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  net_billed_revenue numeric(30,12) NOT NULL DEFAULT 0,
  recognized_revenue numeric(30,12) NOT NULL DEFAULT 0,
  collected_cash numeric(30,12) NOT NULL DEFAULT 0,
  refunds numeric(30,12) NOT NULL DEFAULT 0,
  credits numeric(30,12) NOT NULL DEFAULT 0,
  payment_fees numeric(30,12) NOT NULL DEFAULT 0,
  taxes numeric(30,12) NOT NULL DEFAULT 0,
  posted_actual_cost numeric(30,12) NOT NULL DEFAULT 0,
  final_actual_cost numeric(30,12),
  gross_profit numeric(30,12),
  gross_margin numeric(18,10),
  reporting_currency char(3) NOT NULL,
  status financial_status NOT NULL DEFAULT 'POSTING',
  as_of timestamptz NOT NULL DEFAULT clock_timestamp(),
  reconciliation_status text NOT NULL DEFAULT 'UNRECONCILED',
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT fk_financial_task FOREIGN KEY (tenant_id, task_id)
    REFERENCES task (tenant_id, id)
);

CREATE TABLE tenant_financial_daily (
  tenant_id uuid NOT NULL,
  metric_date date NOT NULL,
  reporting_currency char(3) NOT NULL,
  task_count bigint NOT NULL DEFAULT 0,
  successful_task_count bigint NOT NULL DEFAULT 0,
  posted_actual_cost numeric(30,12) NOT NULL DEFAULT 0,
  recognized_revenue numeric(30,12) NOT NULL DEFAULT 0,
  collected_cash numeric(30,12) NOT NULL DEFAULT 0,
  gross_profit numeric(30,12) NOT NULL DEFAULT 0,
  retry_cost numeric(30,12) NOT NULL DEFAULT 0,
  recovery_cost numeric(30,12) NOT NULL DEFAULT 0,
  model_cost numeric(30,12) NOT NULL DEFAULT 0,
  infrastructure_cost numeric(30,12) NOT NULL DEFAULT 0,
  usage_watermark timestamptz,
  revenue_watermark timestamptz,
  as_of timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, metric_date, reporting_currency)
);

CREATE TABLE audit_event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid,
  account_id uuid,
  actor_type text NOT NULL,
  actor_id text NOT NULL,
  action text NOT NULL,
  resource_type text NOT NULL,
  resource_id text,
  request_id text,
  trace_id text,
  reason text,
  outcome text NOT NULL,
  before_hash text,
  after_hash text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- Hot-path and history indexes.
CREATE INDEX ix_task_account_state_created ON task (account_id, state, created_at);
CREATE INDEX ix_task_tenant_state_created ON task (tenant_id, state, created_at);
CREATE INDEX ix_task_queue ON task (state, priority DESC, queue_entered_at, created_at)
  WHERE state = 'WAITING_FOR_SLOT';
CREATE INDEX ix_task_active ON task (account_id, updated_at)
  WHERE state IN (
    'ADMITTED','STARTING','RUNNING','PAUSE_REQUESTED','PAUSING',
    'CANCEL_REQUESTED','CANCELLING','RECONCILING'
  );
CREATE INDEX ix_slot_expiry ON account_task_slot (lease_expires_at)
  WHERE task_id IS NOT NULL;
CREATE INDEX ix_run_task_created ON task_run (task_id, created_at DESC);
CREATE INDEX ix_node_run_state ON task_node (task_run_id, state, node_key);
CREATE INDEX ix_attempt_lease_expiry ON task_node_attempt (lease_expires_at)
  WHERE state IN ('LEASED','RUNNING','CHECKPOINTING','PAUSE_REQUESTED','CANCEL_REQUESTED');
CREATE INDEX ix_event_task_time ON task_event (task_id, occurred_at);
CREATE INDEX ix_event_run_time ON task_event (task_run_id, occurred_at);
CREATE INDEX ix_checkpoint_run_created ON task_checkpoint (task_run_id, created_at DESC);
CREATE INDEX ix_outbox_claim ON outbox_event (state, available_at, created_at)
  WHERE state IN ('PENDING','RETRY_WAIT');
CREATE INDEX ix_inbox_tenant_processed ON inbox_event_dedup (tenant_id, processed_at);
CREATE INDEX ix_usage_tenant_time ON usage_event (tenant_id, occurred_at);
CREATE INDEX ix_usage_task_time ON usage_event (task_id, occurred_at);
CREATE INDEX ix_usage_provider_time ON usage_event (provider, occurred_at);
CREATE INDEX ix_revenue_tenant_time ON revenue_entry (tenant_id, occurred_at);
CREATE INDEX ix_revenue_task_time ON revenue_entry (task_id, occurred_at);
CREATE INDEX ix_allocation_task_time ON revenue_allocation (task_id, occurred_at);
CREATE INDEX ix_audit_tenant_time ON audit_event (tenant_id, occurred_at);

-- Exactly three account slots, created lazily.
CREATE OR REPLACE FUNCTION ensure_account_task_slots(p_account_id uuid)
RETURNS void
LANGUAGE sql
AS $$
  INSERT INTO account_task_slot (account_id, slot_no)
  SELECT p_account_id, s
  FROM generate_series(1, 3) AS s
  ON CONFLICT (account_id, slot_no) DO NOTHING;
$$;

-- Claim only a genuinely free slot. An expired occupied slot is never overwritten here:
-- the reaper must mark the task UNKNOWN_RESULT, reconcile external effects, and release
-- the slot explicitly with the matching lease generation. The caller must have already
-- authorized p_account_id. The task transition and this call share one transaction.
CREATE OR REPLACE FUNCTION claim_account_task_slot(
  p_account_id uuid,
  p_tenant_id uuid,
  p_task_id uuid,
  p_lease_seconds integer DEFAULT 120
)
RETURNS TABLE(slot_no smallint, lease_generation bigint, lease_expires_at timestamptz)
LANGUAGE plpgsql
AS $$
DECLARE
  v_slot_no smallint;
  v_generation bigint;
  v_expiry timestamptz;
BEGIN
  IF p_lease_seconds < 10 OR p_lease_seconds > 3600 THEN
    RAISE EXCEPTION 'invalid lease duration';
  END IF;

  PERFORM ensure_account_task_slots(p_account_id);

  SELECT s.slot_no
    INTO v_slot_no
  FROM account_task_slot s
  WHERE s.account_id = p_account_id
    AND s.task_id IS NULL
  ORDER BY s.slot_no
  FOR UPDATE SKIP LOCKED
  LIMIT 1;

  IF v_slot_no IS NULL THEN
    RETURN;
  END IF;

  UPDATE account_task_slot s
  SET tenant_id = p_tenant_id,
      task_id = p_task_id,
      lease_generation = s.lease_generation + 1,
      claimed_at = clock_timestamp(),
      lease_expires_at = clock_timestamp() + make_interval(secs => p_lease_seconds),
      updated_at = clock_timestamp()
  WHERE s.account_id = p_account_id
    AND s.slot_no = v_slot_no
  RETURNING s.lease_generation, s.lease_expires_at
    INTO v_generation, v_expiry;

  RETURN QUERY SELECT v_slot_no, v_generation, v_expiry;
END;
$$;

CREATE OR REPLACE FUNCTION renew_account_task_slot(
  p_account_id uuid,
  p_slot_no smallint,
  p_task_id uuid,
  p_expected_generation bigint,
  p_lease_seconds integer DEFAULT 120
)
RETURNS timestamptz
LANGUAGE plpgsql
AS $$
DECLARE
  v_expiry timestamptz;
BEGIN
  UPDATE account_task_slot s
  SET lease_expires_at = clock_timestamp() + make_interval(secs => p_lease_seconds),
      updated_at = clock_timestamp()
  WHERE s.account_id = p_account_id
    AND s.slot_no = p_slot_no
    AND s.task_id = p_task_id
    AND s.lease_generation = p_expected_generation
    AND s.lease_expires_at > clock_timestamp()
  RETURNING s.lease_expires_at INTO v_expiry;

  IF v_expiry IS NULL THEN
    RAISE EXCEPTION 'stale or missing slot lease';
  END IF;
  RETURN v_expiry;
END;
$$;

CREATE OR REPLACE FUNCTION release_account_task_slot(
  p_account_id uuid,
  p_slot_no smallint,
  p_task_id uuid,
  p_expected_generation bigint
)
RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
  v_count integer;
BEGIN
  UPDATE account_task_slot s
  SET tenant_id = NULL,
      task_id = NULL,
      claimed_at = NULL,
      lease_expires_at = NULL,
      updated_at = clock_timestamp()
  WHERE s.account_id = p_account_id
    AND s.slot_no = p_slot_no
    AND s.task_id = p_task_id
    AND s.lease_generation = p_expected_generation;

  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count = 1;
END;
$$;

-- Append a critical task event with a monotonic per-run sequence.
CREATE OR REPLACE FUNCTION append_task_event(
  p_tenant_id uuid,
  p_account_id uuid,
  p_project_id uuid,
  p_task_id uuid,
  p_task_run_id uuid,
  p_event_type text,
  p_transition_id text,
  p_actor_type text,
  p_actor_id text,
  p_payload jsonb DEFAULT '{}'::jsonb,
  p_old_state text DEFAULT NULL,
  p_new_state text DEFAULT NULL,
  p_task_node_id uuid DEFAULT NULL,
  p_node_attempt_id uuid DEFAULT NULL,
  p_checkpoint_id uuid DEFAULT NULL,
  p_trace_id text DEFAULT NULL,
  p_request_id text DEFAULT NULL
)
RETURNS TABLE(event_id uuid, sequence_no bigint)
LANGUAGE plpgsql
AS $$
DECLARE
  v_event_id uuid;
  v_sequence bigint;
BEGIN
  -- Serialize appenders for this run before the idempotency check. This avoids
  -- a check-then-insert race and keeps each committed sequence unique/monotonic.
  PERFORM 1
  FROM task_run r
  WHERE r.id = p_task_run_id
    AND r.tenant_id = p_tenant_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'task run not found or tenant mismatch';
  END IF;

  SELECT e.id, e.sequence_no
    INTO v_event_id, v_sequence
  FROM task_event e
  WHERE e.transition_id = p_transition_id;

  IF v_event_id IS NOT NULL THEN
    RETURN QUERY SELECT v_event_id, v_sequence;
    RETURN;
  END IF;

  UPDATE task_run r
  SET next_event_sequence = r.next_event_sequence + 1,
      updated_at = clock_timestamp()
  WHERE r.id = p_task_run_id
    AND r.tenant_id = p_tenant_id
  RETURNING r.next_event_sequence INTO v_sequence;

  v_event_id := gen_random_uuid();

  INSERT INTO task_event (
    id, tenant_id, account_id, project_id, task_id, task_run_id,
    task_node_id, node_attempt_id, sequence_no, event_type, transition_id,
    actor_type, actor_id, old_state, new_state, checkpoint_id,
    trace_id, request_id, payload
  ) VALUES (
    v_event_id, p_tenant_id, p_account_id, p_project_id, p_task_id, p_task_run_id,
    p_task_node_id, p_node_attempt_id, v_sequence, p_event_type, p_transition_id,
    p_actor_type, p_actor_id, p_old_state, p_new_state, p_checkpoint_id,
    p_trace_id, p_request_id, COALESCE(p_payload, '{}'::jsonb)
  );

  RETURN QUERY SELECT v_event_id, v_sequence;
END;
$$;
