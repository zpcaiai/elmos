-- Elmos large-repository run operator queries.
-- Run inside an explicit tenant transaction unless the operator uses an audited
-- platform role whose scope is intentionally broader.
--
-- BEGIN;
-- SET LOCAL app.tenant_id = '<tenant-uuid>';
-- SET LOCAL app.actor_id = '<operator-uuid>';
-- SET LOCAL app.request_id = '<request-uuid>';

-- Q01. Account slot usage and leaked/expired claims.
SELECT
  u.account_id,
  u.concurrency_limit,
  u.active_slots,
  u.available_slots,
  count(*) FILTER (
    WHERE s.claimed_by_run_id IS NOT NULL
      AND (s.lease_expires_at IS NULL OR s.lease_expires_at <= clock_timestamp())
  ) AS expired_or_invalid_claims
FROM core.v_account_slot_usage u
JOIN core.account_task_slot s
  ON s.tenant_id = u.tenant_id AND s.account_id = u.account_id
GROUP BY u.account_id, u.concurrency_limit, u.active_slots, u.available_slots
ORDER BY u.account_id;

-- Q02. Active run dashboard.
SELECT *
FROM exec.v_run_dashboard
WHERE status NOT IN ('completed', 'failed', 'cancelled', 'archived')
ORDER BY COALESCE(last_progress_at, started_at) NULLS FIRST;

-- Q03. Runs with no recent progress.
SELECT
  run_id, job_id, status, current_stage_key,
  last_progress_at, last_event_seq, last_event_type,
  pending_tasks, running_tasks, failed_tasks, blocked_tasks
FROM exec.v_run_dashboard
WHERE status IN ('running', 'verifying', 'repairing', 'releasing')
  AND COALESCE(last_progress_at, started_at) < clock_timestamp() - interval '10 minutes'
ORDER BY last_progress_at NULLS FIRST;

-- Q04. Stalled attempts or expired leases.
SELECT *
FROM exec.v_stalled_task_attempts
ORDER BY lease_expires_at NULLS FIRST, last_heartbeat_at NULLS FIRST;

-- Q05. Ready tasks not yet claimed.
SELECT
  t.run_id, t.stage_id, t.id AS task_id, t.task_key, t.task_type,
  t.priority, t.resource_class, t.max_attempts, t.not_before, t.created_at
FROM exec.task t
WHERE t.status = 'ready'
  AND (t.not_before IS NULL OR t.not_before <= clock_timestamp())
ORDER BY t.priority DESC, t.created_at;

-- Q06. Task dependency blockers.
SELECT
  t.run_id,
  t.task_key,
  d.dependency_kind,
  blocker.task_key AS blocker_task_key,
  blocker.status AS blocker_status
FROM exec.task t
JOIN exec.task_dependency d
  ON d.tenant_id = t.tenant_id AND d.task_id = t.id
JOIN exec.task blocker
  ON blocker.tenant_id = d.tenant_id AND blocker.id = d.depends_on_task_id
WHERE t.status IN ('pending', 'ready', 'blocked')
  AND (
    (d.dependency_kind = 'success' AND blocker.status <> 'succeeded') OR
    (d.dependency_kind = 'completion' AND blocker.status NOT IN ('succeeded','failed','cancelled','skipped','superseded')) OR
    (d.dependency_kind IN ('artifact','evidence') AND blocker.status <> 'succeeded')
  )
ORDER BY t.run_id, t.task_key, blocker.task_key;

-- Q07. Run event continuity. Any returned row is an invariant violation.
WITH numbered AS (
  SELECT
    tenant_id, run_id, seq,
    lag(seq) OVER (PARTITION BY tenant_id, run_id ORDER BY seq) AS previous_sequence
  FROM exec.run_event
)
SELECT *
FROM numbered
WHERE previous_sequence IS NOT NULL
  AND seq <> previous_sequence + 1
ORDER BY run_id, seq;

-- Q08. Run event cursor drift. Any returned row requires reconciliation.
WITH actual AS (
  SELECT tenant_id, run_id, COALESCE(max(seq), 0) AS max_sequence
  FROM exec.run_event
  GROUP BY tenant_id, run_id
)
SELECT c.tenant_id, c.run_id, c.next_seq, COALESCE(a.max_sequence, 0) AS max_sequence
FROM exec.run_event_cursor c
LEFT JOIN actual a ON a.tenant_id = c.tenant_id AND a.run_id = c.run_id
WHERE c.next_seq <> COALESCE(a.max_sequence, 0) + 1;

-- Q09. Session event continuity.
WITH numbered AS (
  SELECT
    tenant_id, session_id, seq,
    lag(seq) OVER (PARTITION BY tenant_id, session_id ORDER BY seq) AS previous_sequence
  FROM exec.session_event
)
SELECT *
FROM numbered
WHERE previous_sequence IS NOT NULL
  AND seq <> previous_sequence + 1
ORDER BY session_id, seq;

-- Q10. Latest sealed checkpoint per run.
SELECT DISTINCT ON (tenant_id, run_id)
  tenant_id, run_id, id AS checkpoint_id, checkpoint_no,
  status, manifest_id, created_at, sealed_at
FROM exec.checkpoint
WHERE status = 'sealed'
ORDER BY tenant_id, run_id, checkpoint_no DESC, created_at DESC;

-- Q11. Checkpoint components whose artifact is unavailable.
SELECT
  cp.run_id, c.checkpoint_id, c.component_key,
  c.artifact_id, a.state AS artifact_status
FROM exec.checkpoint_component c
JOIN exec.checkpoint cp
  ON cp.tenant_id = c.tenant_id AND cp.id = c.checkpoint_id
LEFT JOIN artifact.artifact a
  ON a.tenant_id = c.tenant_id AND a.id = c.artifact_id
WHERE a.id IS NULL OR a.state <> 'available'
ORDER BY cp.run_id, c.checkpoint_id, c.component_key;

-- Q12. Staged objects older than one hour, candidates for upload reconciliation/GC.
SELECT
  id, run_id, task_id, task_attempt_id, state,
  staging_key, logical_path, expected_sha256, actual_sha256, size_bytes,
  reserved_at, sealed_at, promoted_at
FROM artifact.staged_object
WHERE state IN ('reserved', 'writing', 'sealed')
  AND reserved_at < clock_timestamp() - interval '1 hour'
ORDER BY reserved_at;

-- Q13. Repository inventory and parse gaps.
SELECT *
FROM analysis.v_repository_inventory
ORDER BY parse_gap_count DESC, file_count DESC;

-- Q14. Repository files with failed/partial/unsupported parsing.
SELECT
  repository_revision_id, normalized_path, language, file_kind,
  parse_status, size_bytes, content_sha256
FROM analysis.repository_file
WHERE parse_status IN ('failed', 'partial', 'unsupported')
ORDER BY repository_revision_id, normalized_path;

-- Q15. Open semantic gaps that block completion.
SELECT
  run_id, id AS semantic_gap_id, gap_kind, severity, status,
  source_capability_id, requirement_id, description, created_at, updated_at
FROM verify.semantic_gap
WHERE status IN ('open', 'triaged', 'repairing', 'blocked')
  AND severity IN ('high', 'critical')
ORDER BY severity DESC, updated_at;

-- Q16. Completion readiness facts. A run is mechanically ready only when all
-- counts are zero and latest_passing_gate_id is not null; the authoritative
-- final decision still belongs to verify.complete_run_with_gate().
SELECT
  run_id, run_status, current_target_revision_id,
  unfinished_task_count,
  open_semantic_gap_count,
  critical_gap_count,
  unresolved_side_effect_count,
  latest_passing_gate_id,
  latest_passing_gate_at,
  (
    unfinished_task_count = 0
    AND critical_gap_count = 0
    AND unresolved_side_effect_count = 0
    AND latest_passing_gate_id IS NOT NULL
  ) AS mechanically_ready
FROM verify.v_completion_readiness
ORDER BY mechanically_ready, run_id;

-- Q17. Unknown/unresolved external side effects.
SELECT
  run_id, task_id, task_attempt_id, effect_kind, destination,
  idempotency_key, external_operation_id, status,
  first_dispatched_at, last_checked_at, error_code, updated_at
FROM integration.side_effect_receipt
WHERE status IN ('reserved', 'dispatching', 'unknown_result', 'reconciling', 'compensating')
ORDER BY updated_at;

-- Q18. Outbox backlog.
SELECT
  event_type,
  count(*) AS pending_count,
  min(created_at) AS oldest_created_at,
  max(attempt_count) AS max_attempt_count
FROM integration.outbox_event
WHERE published_at IS NULL
  AND status IN ('pending', 'publishing', 'failed')
GROUP BY event_type
ORDER BY oldest_created_at;

-- Q19. Failed/blocked reconciliation issues.
SELECT
  reconciliation_run_id, severity, issue_kind, subject_kind, subject_id,
  status, created_at, resolved_at
FROM integration.reconciliation_issue
WHERE status IN ('open', 'repairing', 'failed', 'manual')
ORDER BY severity DESC, created_at;

-- Q20. Model/token/cost/revenue summary per run.
SELECT *
FROM metering.v_run_financials
ORDER BY total_cost_microunits DESC;

-- Q21. Expired or exhausted budget reservations.
SELECT
  id AS reservation_id, account_id, run_id, reservation_kind, status,
  reserved_microunits, consumed_microunits,
  expires_at, released_at, created_at
FROM metering.budget_reservation
WHERE status = 'active'
  AND (
    (expires_at IS NOT NULL AND expires_at <= clock_timestamp())
    OR consumed_microunits >= reserved_microunits
  )
ORDER BY created_at;

-- Q22. Latest ETA with machine/HITL/human values kept separate.
SELECT DISTINCT ON (tenant_id, run_id)
  run_id, generated_at, confidence,
  machine_wall_clock_remaining_p50_seconds,
  machine_wall_clock_remaining_p90_seconds,
  expected_hitl_wait_seconds,
  human_equivalent_p50_hours,
  human_equivalent_p90_hours,
  forecast_kind, model_version, feature_snapshot
FROM metering.eta_forecast
ORDER BY tenant_id, run_id, generated_at DESC;

-- Q23. Cache effectiveness.
SELECT *
FROM cache.v_run_cache_effectiveness
ORDER BY avoided_cost_microunits DESC NULLS LAST;

-- Q24. Evidence that has been revoked after a gate was evaluated.
SELECT
  g.run_id,
  g.id AS gate_evaluation_id,
  g.evaluated_at,
  e.id AS evidence_item_id,
  r.revoked_at,
  r.reason
FROM verify.gate_evaluation g
JOIN verify.evidence_bundle_item bi
  ON bi.tenant_id = g.tenant_id AND bi.evidence_bundle_id = g.evidence_bundle_id
JOIN verify.evidence_item e
  ON e.tenant_id = bi.tenant_id AND e.id = bi.evidence_item_id
JOIN verify.evidence_revocation r
  ON r.tenant_id = e.tenant_id AND r.evidence_item_id = e.id
WHERE r.revoked_at >= g.evaluated_at
ORDER BY r.revoked_at DESC;

-- Q25. Deployment readiness.
SELECT *
FROM ops.v_deployment_readiness
ORDER BY environment, deployment_id;

-- Q26. Failed or incomplete migration runs.
SELECT
  m.deployment_id, d.release_id, m.migration_tool,
  m.from_schema_version, m.to_schema_version,
  m.status, m.started_at, m.ended_at, m.output_artifact_id
FROM ops.migration_run m
JOIN ops.deployment d
  ON d.tenant_id = m.tenant_id AND d.id = m.deployment_id
WHERE m.status NOT IN ('succeeded', 'not_required')
ORDER BY m.started_at DESC;

-- Q27. Required release components without a matching latest healthy image.
WITH latest AS (
  SELECT DISTINCT ON (tenant_id, deployment_id, release_component_id)
    tenant_id, deployment_id, release_component_id,
    livez, readyz, image_digest, observed_at
  FROM ops.service_health_snapshot
  ORDER BY tenant_id, deployment_id, release_component_id, observed_at DESC
)
SELECT
  d.id AS deployment_id,
  rc.component_key,
  rc.component_kind,
  rc.image_digest AS expected_image_digest,
  l.image_digest AS observed_image_digest,
  l.livez,
  l.readyz,
  l.observed_at
FROM ops.deployment d
JOIN ops.release_component rc
  ON rc.tenant_id = d.tenant_id AND rc.release_id = d.release_id
LEFT JOIN latest l
  ON l.tenant_id = d.tenant_id
 AND l.deployment_id = d.id
 AND l.release_component_id = rc.id
WHERE rc.required
  AND rc.component_kind <> 'migration'
  AND NOT COALESCE(l.livez AND l.readyz AND l.image_digest = rc.image_digest, false)
ORDER BY d.id, rc.component_key;

-- Q28. Learning assets whose authorization is missing or revoked.
SELECT
  c.id AS transformation_case_id,
  c.run_id,
  a.id AS authorization_id,
  a.status AS authorization_status,
  a.revoked_at
FROM learning.transformation_case c
LEFT JOIN learning.data_authorization a
  ON a.tenant_id = c.tenant_id AND a.id = c.data_authorization_id
WHERE a.id IS NULL OR a.status <> 'active' OR a.revoked_at IS NOT NULL
ORDER BY c.created_at;

-- Q29. High write-volume table sizes.
SELECT
  n.nspname AS schema_name,
  c.relname AS relation_name,
  pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
  pg_total_relation_size(c.oid) AS total_bytes,
  s.n_live_tup,
  s.n_dead_tup,
  s.last_autovacuum,
  s.last_autoanalyze
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
WHERE n.nspname IN (
  'core','exec','artifact','analysis','generation','transform',
  'verify','metering','cache','integration','learning','ops','audit'
)
  AND c.relkind IN ('r','p')
ORDER BY total_bytes DESC;

-- Q30. RLS coverage. Must return zero rows for tenant-scoped parent tables.
SELECT n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p')
  AND n.nspname IN (
    'core','exec','artifact','analysis','generation','transform',
    'verify','metering','cache','integration','learning','ops','audit'
  )
  AND NOT (n.nspname = 'core' AND c.relname = 'tenant')
  AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)
ORDER BY 1,2;

-- COMMIT or ROLLBACK after the operator session.
