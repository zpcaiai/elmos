-- Complete deferred cross-links, enforce high-value same-run relationships,
-- enable FORCE RLS on tenant data, and expose operator/read-model views.

BEGIN;

-- Deferred artifact / execution / verification links.
ALTER TABLE core.revision_snapshot
  ADD CONSTRAINT revision_snapshot_artifact_fk
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id);
ALTER TABLE core.repository_revision
  ADD CONSTRAINT repository_revision_manifest_artifact_fk
  FOREIGN KEY (tenant_id, manifest_artifact_id) REFERENCES artifact.artifact(tenant_id, id);
ALTER TABLE core.job
  ADD CONSTRAINT job_current_run_fk
  FOREIGN KEY (tenant_id, current_run_id) REFERENCES exec.run(tenant_id, id),
  ADD CONSTRAINT job_latest_successful_run_fk
  FOREIGN KEY (tenant_id, latest_successful_run_id) REFERENCES exec.run(tenant_id, id);
ALTER TABLE core.account_task_slot
  ADD CONSTRAINT account_task_slot_run_fk
  FOREIGN KEY (tenant_id, claimed_by_run_id) REFERENCES exec.run(tenant_id, id);
ALTER TABLE exec.run
  ADD CONSTRAINT run_current_target_revision_fk
  FOREIGN KEY (tenant_id, current_target_revision_id) REFERENCES transform.target_revision(tenant_id, id),
  ADD CONSTRAINT run_completion_gate_fk
  FOREIGN KEY (tenant_id, completion_gate_evaluation_id) REFERENCES verify.gate_evaluation(tenant_id, id),
  ADD CONSTRAINT run_slot_fk
  FOREIGN KEY (tenant_id, account_id, slot_no) REFERENCES core.account_task_slot(tenant_id, account_id, slot_no);
ALTER TABLE exec.run_attempt
  ADD CONSTRAINT run_attempt_resume_checkpoint_fk
  FOREIGN KEY (tenant_id, resume_checkpoint_id) REFERENCES exec.checkpoint(tenant_id, id);
ALTER TABLE exec.task
  ADD CONSTRAINT task_current_attempt_fk
  FOREIGN KEY (tenant_id, current_attempt_id) REFERENCES exec.task_attempt(tenant_id, id),
  ADD CONSTRAINT task_last_checkpoint_fk
  FOREIGN KEY (tenant_id, last_checkpoint_id) REFERENCES exec.checkpoint(tenant_id, id),
  ADD CONSTRAINT task_output_manifest_fk
  FOREIGN KEY (tenant_id, output_manifest_id) REFERENCES artifact.manifest(tenant_id, id);
ALTER TABLE exec.workspace
  ADD CONSTRAINT workspace_storage_manifest_fk
  FOREIGN KEY (tenant_id, storage_manifest_id) REFERENCES artifact.manifest(tenant_id, id);
ALTER TABLE exec.task_attempt
  ADD CONSTRAINT task_attempt_input_manifest_fk
  FOREIGN KEY (tenant_id, input_manifest_id) REFERENCES artifact.manifest(tenant_id, id),
  ADD CONSTRAINT task_attempt_output_manifest_fk
  FOREIGN KEY (tenant_id, output_manifest_id) REFERENCES artifact.manifest(tenant_id, id),
  ADD CONSTRAINT task_attempt_checkpoint_fk
  FOREIGN KEY (tenant_id, checkpoint_id) REFERENCES exec.checkpoint(tenant_id, id);
ALTER TABLE exec.session_event
  ADD CONSTRAINT session_event_artifact_fk
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id);
ALTER TABLE exec.context_epoch
  ADD CONSTRAINT context_epoch_baseline_artifact_fk
  FOREIGN KEY (tenant_id, baseline_artifact_id) REFERENCES artifact.artifact(tenant_id, id);
ALTER TABLE exec.human_gate
  ADD CONSTRAINT human_gate_context_artifact_fk
  FOREIGN KEY (tenant_id, context_artifact_id) REFERENCES artifact.artifact(tenant_id, id);
ALTER TABLE generation.generation_iteration
  ADD CONSTRAINT generation_iteration_target_revision_fk
  FOREIGN KEY (tenant_id, target_revision_id) REFERENCES transform.target_revision(tenant_id, id);
ALTER TABLE transform.mapping_decision
  ADD CONSTRAINT mapping_decision_rule_release_fk
  FOREIGN KEY (tenant_id, rule_release_id) REFERENCES learning.rule_release(tenant_id, id);

ALTER TABLE learning.rule_validation
  ADD CONSTRAINT rule_validation_benchmark_run_fk
  FOREIGN KEY (tenant_id, benchmark_run_id) REFERENCES learning.benchmark_run(tenant_id, id);
ALTER TABLE integration.outbox_event
  ADD CONSTRAINT outbox_event_tenant_fk
  FOREIGN KEY (tenant_id) REFERENCES core.tenant(id);
ALTER TABLE audit.audit_event
  ADD CONSTRAINT audit_event_tenant_fk
  FOREIGN KEY (tenant_id) REFERENCES core.tenant(id);

-- Same-run guards for the scheduler's highest-risk relations.
ALTER TABLE exec.run_stage ADD CONSTRAINT run_stage_run_id_id_uq UNIQUE (tenant_id, run_id, id);
ALTER TABLE exec.task ADD CONSTRAINT task_run_id_id_uq UNIQUE (tenant_id, run_id, id);
ALTER TABLE exec.task_attempt ADD CONSTRAINT task_attempt_run_id_id_uq UNIQUE (tenant_id, run_id, id);
ALTER TABLE exec.workspace ADD CONSTRAINT workspace_run_id_id_uq UNIQUE (tenant_id, run_id, id);

ALTER TABLE exec.task
  ADD CONSTRAINT task_stage_same_run_fk
  FOREIGN KEY (tenant_id, run_id, stage_id) REFERENCES exec.run_stage(tenant_id, run_id, id);
ALTER TABLE exec.task_dependency
  ADD CONSTRAINT task_dependency_task_same_run_fk
  FOREIGN KEY (tenant_id, run_id, task_id) REFERENCES exec.task(tenant_id, run_id, id),
  ADD CONSTRAINT task_dependency_depends_same_run_fk
  FOREIGN KEY (tenant_id, run_id, depends_on_task_id) REFERENCES exec.task(tenant_id, run_id, id);
ALTER TABLE exec.task_attempt
  ADD CONSTRAINT task_attempt_task_same_run_fk
  FOREIGN KEY (tenant_id, run_id, task_id) REFERENCES exec.task(tenant_id, run_id, id),
  ADD CONSTRAINT task_attempt_workspace_same_run_fk
  FOREIGN KEY (tenant_id, run_id, workspace_id) REFERENCES exec.workspace(tenant_id, run_id, id);
ALTER TABLE exec.workspace
  ADD CONSTRAINT workspace_task_same_run_fk
  FOREIGN KEY (tenant_id, run_id, task_id) REFERENCES exec.task(tenant_id, run_id, id);

-- Row-level security. Application roles MUST NOT own these tables and MUST NOT
-- have BYPASSRLS. Migration/reconciliation roles are separate audited principals.
ALTER TABLE core.tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.tenant FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_self_isolation ON core.tenant
  USING (id = core.current_tenant_id())
  WITH CHECK (id = core.current_tenant_id());

DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT DISTINCT c.table_schema, c.table_name
    FROM information_schema.columns c
    JOIN information_schema.tables t
      ON t.table_schema = c.table_schema
     AND t.table_name = c.table_name
    WHERE c.column_name = 'tenant_id'
      AND c.table_schema IN (
        'core', 'exec', 'artifact', 'analysis', 'generation', 'transform',
        'verify', 'metering', 'cache', 'integration', 'learning', 'ops', 'audit'
      )
      AND NOT (c.table_schema = 'core' AND c.table_name = 'tenant')
      AND t.table_type = 'BASE TABLE'
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', r.table_schema, r.table_name);
    EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', r.table_schema, r.table_name);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I.%I USING (tenant_id = core.current_tenant_id()) WITH CHECK (tenant_id = core.current_tenant_id())',
      r.table_schema, r.table_name
    );
  END LOOP;
END $$;

-- Read models are security-invoker views so RLS remains authoritative.
CREATE VIEW core.v_account_slot_usage
WITH (security_invoker = true, security_barrier = true)
AS
SELECT
  a.tenant_id,
  a.id AS account_id,
  a.concurrency_limit,
  count(*) FILTER (
    WHERE s.claimed_by_run_id IS NOT NULL
      AND s.lease_expires_at > clock_timestamp()
  )::integer AS active_slots,
  greatest(
    a.concurrency_limit - count(*) FILTER (
      WHERE s.claimed_by_run_id IS NOT NULL
        AND s.lease_expires_at > clock_timestamp()
    )::integer,
    0
  ) AS available_slots
FROM core.account a
JOIN core.account_task_slot s
  ON s.tenant_id = a.tenant_id AND s.account_id = a.id
GROUP BY a.tenant_id, a.id, a.concurrency_limit;

CREATE VIEW exec.v_run_dashboard
WITH (security_invoker = true, security_barrier = true)
AS
SELECT
  r.tenant_id,
  r.id AS run_id,
  r.job_id,
  r.run_kind,
  r.status,
  r.current_stage_key,
  p.progress_basis_points,
  p.total_tasks,
  p.pending_tasks,
  p.running_tasks,
  p.succeeded_tasks,
  p.failed_tasks,
  p.blocked_tasks,
  p.last_event_seq,
  p.last_event_type,
  p.last_progress_message,
  p.estimated_machine_seconds_remaining,
  r.started_at,
  r.last_progress_at,
  r.completed_at,
  r.current_target_revision_id,
  r.completion_gate_evaluation_id
FROM exec.run r
JOIN exec.run_progress_snapshot p
  ON p.tenant_id = r.tenant_id AND p.run_id = r.id;

CREATE VIEW exec.v_stalled_task_attempts
WITH (security_invoker = true, security_barrier = true)
AS
SELECT
  a.tenant_id,
  a.run_id,
  a.task_id,
  a.id AS task_attempt_id,
  a.status,
  a.worker_node_id,
  a.last_heartbeat_at,
  l.expires_at AS lease_expires_at,
  l.lease_generation,
  a.fencing_token
FROM exec.task_attempt a
LEFT JOIN LATERAL (
  SELECT x.expires_at, x.lease_generation
  FROM exec.execution_lease x
  WHERE x.tenant_id = a.tenant_id
    AND x.resource_kind = 'task'
    AND x.resource_id = a.task_id
    AND x.released_at IS NULL
  ORDER BY x.lease_generation DESC
  LIMIT 1
) l ON true
WHERE a.status IN ('claimed', 'starting', 'running', 'waiting_async')
  AND (
    a.last_heartbeat_at IS NULL
    OR a.last_heartbeat_at < clock_timestamp() - interval '5 minutes'
    OR l.expires_at <= clock_timestamp()
  );

CREATE VIEW analysis.v_repository_inventory
WITH (security_invoker = true, security_barrier = true)
AS
SELECT
  f.tenant_id,
  f.repository_revision_id,
  count(*) AS file_count,
  count(*) FILTER (WHERE f.file_kind = 'source') AS source_file_count,
  count(*) FILTER (WHERE f.is_test) AS test_file_count,
  count(*) FILTER (WHERE f.is_generated) AS generated_file_count,
  count(*) FILTER (WHERE f.is_vendor) AS vendor_file_count,
  sum(f.size_bytes) AS total_bytes,
  count(*) FILTER (WHERE f.parse_status IN ('failed', 'unsupported', 'partial')) AS parse_gap_count
FROM analysis.repository_file f
GROUP BY f.tenant_id, f.repository_revision_id;

CREATE VIEW verify.v_completion_readiness
WITH (security_invoker = true, security_barrier = true)
AS
WITH task_counts AS (
  SELECT tenant_id, run_id,
         count(*) FILTER (WHERE status NOT IN ('succeeded', 'skipped', 'superseded')) AS unfinished_task_count
  FROM exec.task
  GROUP BY tenant_id, run_id
), gap_counts AS (
  SELECT tenant_id, run_id,
         count(*) FILTER (WHERE status IN ('open', 'triaged', 'repairing', 'blocked')) AS open_semantic_gap_count,
         count(*) FILTER (WHERE status IN ('open', 'triaged', 'repairing', 'blocked') AND severity = 'critical') AS critical_gap_count
  FROM verify.semantic_gap
  GROUP BY tenant_id, run_id
), effect_counts AS (
  SELECT tenant_id, run_id,
         count(*) FILTER (WHERE status IN ('reserved', 'dispatching', 'unknown_result', 'reconciling', 'compensating')) AS unresolved_side_effect_count
  FROM integration.side_effect_receipt
  GROUP BY tenant_id, run_id
), latest_gate AS (
  SELECT DISTINCT ON (tenant_id, run_id)
         tenant_id, run_id, id AS latest_passing_gate_id, evaluated_at AS latest_passing_gate_at
  FROM verify.gate_evaluation
  WHERE decision = 'pass'
  ORDER BY tenant_id, run_id, evaluated_at DESC, id DESC
)
SELECT
  r.tenant_id,
  r.id AS run_id,
  r.status AS run_status,
  r.current_target_revision_id,
  COALESCE(t.unfinished_task_count, 0) AS unfinished_task_count,
  COALESCE(g.open_semantic_gap_count, 0) AS open_semantic_gap_count,
  COALESCE(g.critical_gap_count, 0) AS critical_gap_count,
  COALESCE(e.unresolved_side_effect_count, 0) AS unresolved_side_effect_count,
  lg.latest_passing_gate_at,
  lg.latest_passing_gate_id
FROM exec.run r
LEFT JOIN task_counts t ON t.tenant_id = r.tenant_id AND t.run_id = r.id
LEFT JOIN gap_counts g ON g.tenant_id = r.tenant_id AND g.run_id = r.id
LEFT JOIN effect_counts e ON e.tenant_id = r.tenant_id AND e.run_id = r.id
LEFT JOIN latest_gate lg ON lg.tenant_id = r.tenant_id AND lg.run_id = r.id;

CREATE VIEW metering.v_run_financials
WITH (security_invoker = true, security_barrier = true)
AS
SELECT
  r.tenant_id,
  r.id AS run_id,
  COALESCE(c.total_cost_microunits, 0) AS total_cost_microunits,
  COALESCE(v.total_revenue_microunits, 0) AS total_revenue_microunits,
  COALESCE(v.total_revenue_microunits, 0) - COALESCE(c.total_cost_microunits, 0) AS gross_margin_microunits,
  COALESCE(m.model_calls, 0) AS model_calls,
  COALESCE(m.total_tokens, 0) AS total_tokens,
  COALESCE(m.cached_tokens, 0) AS cached_tokens
FROM exec.run r
LEFT JOIN (
  SELECT tenant_id, run_id, sum(amount_microunits) AS total_cost_microunits
  FROM metering.cost_ledger GROUP BY tenant_id, run_id
) c ON c.tenant_id = r.tenant_id AND c.run_id = r.id
LEFT JOIN (
  SELECT tenant_id, run_id, sum(amount_microunits) AS total_revenue_microunits
  FROM metering.revenue_ledger WHERE run_id IS NOT NULL GROUP BY tenant_id, run_id
) v ON v.tenant_id = r.tenant_id AND v.run_id = r.id
LEFT JOIN (
  SELECT tenant_id, run_id, count(*) AS model_calls,
         sum(input_tokens + output_tokens + reasoning_tokens) AS total_tokens,
         sum(cached_input_tokens) AS cached_tokens
  FROM metering.model_invocation GROUP BY tenant_id, run_id
) m ON m.tenant_id = r.tenant_id AND m.run_id = r.id;

CREATE VIEW cache.v_run_cache_effectiveness
WITH (security_invoker = true, security_barrier = true)
AS
SELECT
  a.tenant_id,
  a.run_id,
  count(*) FILTER (WHERE a.access_kind = 'lookup_hit') AS hit_count,
  count(*) FILTER (WHERE a.access_kind = 'lookup_miss') AS miss_count,
  sum(a.avoided_input_tokens) AS avoided_input_tokens,
  sum(a.avoided_compute_ms) AS avoided_compute_ms,
  sum(a.avoided_cost_microunits) AS avoided_cost_microunits,
  CASE WHEN count(*) FILTER (WHERE a.access_kind IN ('lookup_hit', 'lookup_miss')) = 0 THEN 0
       ELSE round(
         100.0 * count(*) FILTER (WHERE a.access_kind = 'lookup_hit')
         / count(*) FILTER (WHERE a.access_kind IN ('lookup_hit', 'lookup_miss')),
         3
       )
  END AS hit_rate_percent
FROM cache.cache_access a
WHERE a.run_id IS NOT NULL
GROUP BY a.tenant_id, a.run_id;

CREATE VIEW ops.v_deployment_readiness
WITH (security_invoker = true, security_barrier = true)
AS
WITH check_counts AS (
  SELECT tenant_id, deployment_id,
         count(*) AS check_count,
         count(*) FILTER (WHERE status = 'passed') AS passed_check_count,
         count(*) FILTER (WHERE status = 'failed') AS failed_check_count,
         count(*) FILTER (WHERE status = 'blocked') AS blocked_check_count
  FROM ops.deployment_check
  GROUP BY tenant_id, deployment_id
), latest_health AS (
  SELECT DISTINCT ON (h.tenant_id, h.deployment_id, h.release_component_id)
         h.tenant_id, h.deployment_id, h.release_component_id, h.livez, h.readyz,
         h.image_digest, h.observed_at
  FROM ops.service_health_snapshot h
  ORDER BY h.tenant_id, h.deployment_id, h.release_component_id, h.observed_at DESC
), health_summary AS (
  SELECT d.tenant_id, d.id AS deployment_id,
         count(rc.id) FILTER (WHERE rc.required AND rc.component_kind <> 'migration') AS required_component_count,
         count(lh.release_component_id) FILTER (
           WHERE rc.required AND rc.component_kind <> 'migration'
             AND lh.livez AND lh.readyz AND lh.image_digest = rc.image_digest
         ) AS healthy_required_component_count,
         bool_and(
           CASE WHEN rc.required AND rc.component_kind <> 'migration'
                THEN COALESCE(lh.livez AND lh.readyz AND lh.image_digest = rc.image_digest, false)
                ELSE true END
         ) AS all_required_components_healthy
  FROM ops.deployment d
  JOIN ops.release_component rc
    ON rc.tenant_id = d.tenant_id AND rc.release_id = d.release_id
  LEFT JOIN latest_health lh
    ON lh.tenant_id = d.tenant_id AND lh.deployment_id = d.id AND lh.release_component_id = rc.id
  GROUP BY d.tenant_id, d.id
), latest_gate AS (
  SELECT DISTINCT ON (tenant_id, deployment_id)
         tenant_id, deployment_id, decision, evaluated_at
  FROM ops.deployment_gate
  ORDER BY tenant_id, deployment_id, evaluated_at DESC, id DESC
)
SELECT
  d.tenant_id,
  d.id AS deployment_id,
  d.environment,
  d.status,
  COALESCE(c.check_count, 0) AS check_count,
  COALESCE(c.passed_check_count, 0) AS passed_check_count,
  COALESCE(c.failed_check_count, 0) AS failed_check_count,
  COALESCE(c.blocked_check_count, 0) AS blocked_check_count,
  COALESCE(h.required_component_count, 0) AS required_component_count,
  COALESCE(h.healthy_required_component_count, 0) AS healthy_required_component_count,
  COALESCE(h.all_required_components_healthy, false) AS all_required_components_healthy,
  g.decision AS latest_gate_decision,
  g.evaluated_at AS latest_gate_at
FROM ops.deployment d
LEFT JOIN check_counts c ON c.tenant_id = d.tenant_id AND c.deployment_id = d.id
LEFT JOIN health_summary h ON h.tenant_id = d.tenant_id AND h.deployment_id = d.id
LEFT JOIN latest_gate g ON g.tenant_id = d.tenant_id AND g.deployment_id = d.id;

COMMIT;
