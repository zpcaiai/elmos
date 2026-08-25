-- Elmos post-migration and post-deployment database invariants.
-- Run as an audited migrator/platform test role on a non-production copy or
-- during deployment verification. This script is read-only except for SET.
\set ON_ERROR_STOP on

DO $$
DECLARE
  bad_count bigint;
BEGIN
  -- 1. Every account has exactly three physical slots.
  SELECT count(*) INTO bad_count
  FROM (
    SELECT a.tenant_id, a.id
    FROM core.account a
    LEFT JOIN core.account_task_slot s
      ON s.tenant_id = a.tenant_id AND s.account_id = a.id
    GROUP BY a.tenant_id, a.id
    HAVING count(s.slot_no) <> 3
       OR min(s.slot_no) <> 1
       OR max(s.slot_no) <> 3
  ) x;
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % accounts do not have exactly three slots', bad_count;
  END IF;

  -- 2. Active claims never exceed the account limit.
  SELECT count(*) INTO bad_count
  FROM core.v_account_slot_usage
  WHERE active_slots > concurrency_limit;
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % accounts exceed concurrency limit', bad_count;
  END IF;

  -- 3. Slot shape is all-null or fully claimed.
  SELECT count(*) INTO bad_count
  FROM core.account_task_slot
  WHERE NOT (
    (claimed_by_run_id IS NULL AND claim_token IS NULL AND lease_expires_at IS NULL)
    OR
    (claimed_by_run_id IS NOT NULL AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL)
  );
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % malformed slot claims', bad_count;
  END IF;

  -- 4. At most one unreleased lease per resource.
  SELECT count(*) INTO bad_count
  FROM (
    SELECT tenant_id, resource_kind, resource_id
    FROM exec.execution_lease
    WHERE released_at IS NULL
    GROUP BY tenant_id, resource_kind, resource_id
    HAVING count(*) > 1
  ) x;
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % resources have duplicate active leases', bad_count;
  END IF;

  -- 5. Run event sequences are contiguous.
  SELECT count(*) INTO bad_count
  FROM (
    SELECT tenant_id, run_id, seq,
           lag(seq) OVER (PARTITION BY tenant_id, run_id ORDER BY seq) AS prev_seq
    FROM exec.run_event
  ) e
  WHERE prev_seq IS NOT NULL AND seq <> prev_seq + 1;
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % run event sequence gaps', bad_count;
  END IF;

  -- 6. Run event hash-chain previous pointers match.
  SELECT count(*) INTO bad_count
  FROM (
    SELECT tenant_id, run_id, seq, previous_event_hash,
           lag(event_hash) OVER (PARTITION BY tenant_id, run_id ORDER BY seq) AS expected_previous
    FROM exec.run_event
  ) e
  WHERE (seq = 1 AND previous_event_hash IS NOT NULL)
     OR (seq > 1 AND previous_event_hash IS DISTINCT FROM expected_previous);
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % broken run event hash links', bad_count;
  END IF;

  -- 7. Run cursor points to max(sequence)+1.
  SELECT count(*) INTO bad_count
  FROM exec.run_event_cursor c
  LEFT JOIN (
    SELECT tenant_id, run_id, COALESCE(max(seq), 0) AS max_seq
    FROM exec.run_event GROUP BY tenant_id, run_id
  ) e ON e.tenant_id = c.tenant_id AND e.run_id = c.run_id
  WHERE c.next_seq <> COALESCE(e.max_seq, 0) + 1;
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % run event cursors drifted', bad_count;
  END IF;

  -- 8. Session event sequences and hash chains are contiguous.
  SELECT count(*) INTO bad_count
  FROM (
    SELECT tenant_id, session_id, seq, previous_event_hash,
           lag(seq) OVER (PARTITION BY tenant_id, session_id ORDER BY seq) AS prev_seq,
           lag(event_hash) OVER (PARTITION BY tenant_id, session_id ORDER BY seq) AS expected_previous
    FROM exec.session_event
  ) e
  WHERE (prev_seq IS NOT NULL AND seq <> prev_seq + 1)
     OR (seq = 1 AND previous_event_hash IS NOT NULL)
     OR (seq > 1 AND previous_event_hash IS DISTINCT FROM expected_previous);
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % broken session event sequences/hash links', bad_count;
  END IF;

  -- 9. Session cursor points to max(sequence)+1.
  SELECT count(*) INTO bad_count
  FROM exec.session_event_cursor c
  LEFT JOIN (
    SELECT tenant_id, session_id, COALESCE(max(seq), 0) AS max_seq
    FROM exec.session_event GROUP BY tenant_id, session_id
  ) e ON e.tenant_id = c.tenant_id AND e.session_id = c.session_id
  WHERE c.next_seq <> COALESCE(e.max_seq, 0) + 1;
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % session event cursors drifted', bad_count;
  END IF;

  -- 10. Available artifacts have available object blobs.
  SELECT count(*) INTO bad_count
  FROM artifact.artifact a
  LEFT JOIN artifact.object_blob b
    ON b.tenant_id = a.tenant_id AND b.sha256 = a.sha256
  WHERE a.state = 'available'
    AND (b.sha256 IS NULL OR b.object_state <> 'available');
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % available artifacts lack available blobs', bad_count;
  END IF;

  -- 11. Sealed manifests contain only available artifacts.
  SELECT count(*) INTO bad_count
  FROM artifact.manifest m
  JOIN artifact.manifest_entry me
    ON me.tenant_id = m.tenant_id AND me.manifest_id = m.id
  JOIN artifact.artifact a
    ON a.tenant_id = me.tenant_id AND a.id = me.artifact_id
  WHERE m.sealed AND a.state <> 'available';
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % sealed manifest entries are unavailable', bad_count;
  END IF;

  -- 12. Sealed checkpoints have at least one component and a sealed manifest.
  SELECT count(*) INTO bad_count
  FROM exec.checkpoint c
  LEFT JOIN artifact.manifest m
    ON m.tenant_id = c.tenant_id AND m.id = c.manifest_id
  LEFT JOIN LATERAL (
    SELECT count(*) AS component_count
    FROM exec.checkpoint_component cc
    WHERE cc.tenant_id = c.tenant_id AND cc.checkpoint_id = c.id
  ) cc ON true
  WHERE c.status = 'sealed'
    AND (m.id IS NULL OR NOT m.sealed OR cc.component_count = 0);
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % sealed checkpoints are incomplete', bad_count;
  END IF;

  -- 13. Evidence item is tied to an available artifact and same run target revision.
  SELECT count(*) INTO bad_count
  FROM verify.evidence_item e
  LEFT JOIN artifact.artifact a
    ON a.tenant_id = e.tenant_id AND a.id = e.artifact_id
  LEFT JOIN transform.target_revision tr
    ON tr.tenant_id = e.tenant_id AND tr.id = e.target_revision_id
  WHERE a.id IS NULL OR a.state <> 'available'
     OR tr.id IS NULL OR tr.run_id <> e.run_id;
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % evidence items have invalid artifact/revision binding', bad_count;
  END IF;

  -- 14. Sealed evidence bundles contain at least one item.
  SELECT count(*) INTO bad_count
  FROM verify.evidence_bundle b
  LEFT JOIN LATERAL (
    SELECT count(*) AS item_count
    FROM verify.evidence_bundle_item bi
    WHERE bi.tenant_id = b.tenant_id AND bi.evidence_bundle_id = b.id
  ) i ON true
  WHERE b.status = 'sealed' AND i.item_count = 0;
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % sealed evidence bundles are empty', bad_count;
  END IF;

  -- 15. Passing gates are tied to sealed evidence bundles for the same run/target.
  SELECT count(*) INTO bad_count
  FROM verify.gate_evaluation g
  LEFT JOIN verify.evidence_bundle b
    ON b.tenant_id = g.tenant_id AND b.id = g.evidence_bundle_id
  WHERE g.decision = 'pass'
    AND (b.id IS NULL OR b.status <> 'sealed'
         OR b.run_id <> g.run_id OR b.target_revision_id <> g.target_revision_id);
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % passing gates have invalid bundles', bad_count;
  END IF;

  -- 16. Completed runs must have a passing gate and no mechanical blockers.
  SELECT count(*) INTO bad_count
  FROM exec.run r
  LEFT JOIN verify.gate_evaluation g
    ON g.tenant_id = r.tenant_id AND g.id = r.completion_gate_evaluation_id
  LEFT JOIN verify.v_completion_readiness cr
    ON cr.tenant_id = r.tenant_id AND cr.run_id = r.id
  WHERE r.status = 'completed'
    AND (
      g.id IS NULL OR g.decision <> 'pass'
      OR g.target_revision_id <> r.current_target_revision_id
      OR cr.unfinished_task_count <> 0
      OR cr.critical_gap_count <> 0
      OR cr.unresolved_side_effect_count <> 0
    );
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % completed runs do not satisfy P05 mechanical facts', bad_count;
  END IF;

  -- 17. Unknown side effects may not exist on completed runs.
  SELECT count(*) INTO bad_count
  FROM integration.side_effect_receipt s
  JOIN exec.run r ON r.tenant_id = s.tenant_id AND r.id = s.run_id
  WHERE r.status = 'completed'
    AND s.status IN ('reserved','dispatching','unknown_result','reconciling','compensating');
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % unresolved side effects belong to completed runs', bad_count;
  END IF;

  -- 18. Ledger idempotency keys must be nonblank. Negative adjustment/credit
  -- amounts are allowed and are therefore not treated as corruption.
  SELECT count(*) INTO bad_count
  FROM metering.cost_ledger
  WHERE btrim(idempotency_key) = '';
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % cost ledger entries have blank idempotency keys', bad_count;
  END IF;

  -- 19. Learning cases require active authorization.
  SELECT count(*) INTO bad_count
  FROM learning.transformation_case c
  LEFT JOIN learning.data_authorization a
    ON a.tenant_id = c.tenant_id AND a.id = c.data_authorization_id
  WHERE c.status IN ('eligible','curated')
    AND (a.id IS NULL OR a.status <> 'active' OR a.revoked_at IS NOT NULL);
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % learning cases lack active authorization', bad_count;
  END IF;

  -- 20. Healthy deployments must have a passing deployment gate.
  SELECT count(*) INTO bad_count
  FROM ops.deployment d
  LEFT JOIN LATERAL (
    SELECT g.decision
    FROM ops.deployment_gate g
    WHERE g.tenant_id = d.tenant_id AND g.deployment_id = d.id
    ORDER BY g.evaluated_at DESC, g.id DESC
    LIMIT 1
  ) g ON true
  WHERE d.status = 'healthy' AND COALESCE(g.decision, '') <> 'pass';
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % healthy deployments lack passing gate', bad_count;
  END IF;
END $$;

-- 21. All tenant-scoped parent/partitioned tables must have RLS + FORCE RLS.
DO $$
DECLARE
  bad_count bigint;
BEGIN
  SELECT count(*) INTO bad_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE c.relkind IN ('r','p')
    AND n.nspname IN (
      'core','exec','artifact','analysis','generation','transform',
      'verify','metering','cache','integration','learning','ops','audit'
    )
    AND NOT (n.nspname = 'core' AND c.relname = 'tenant')
    AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity);
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % tenant tables do not force RLS', bad_count;
  END IF;
END $$;

-- 22. High-value transaction functions must not be executable by PUBLIC.
DO $$
DECLARE
  bad_count bigint;
BEGIN
  SELECT count(*) INTO bad_count
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE (n.nspname, p.proname) IN (
    ('core','claim_account_slot'),
    ('core','renew_account_slot'),
    ('core','release_account_slot'),
    ('exec','create_run'),
    ('exec','append_run_event'),
    ('exec','append_session_event'),
    ('exec','claim_ready_task'),
    ('exec','renew_task_lease'),
    ('exec','finish_task_attempt'),
    ('exec','seal_checkpoint'),
    ('integration','reserve_side_effect'),
    ('verify','complete_run_with_gate'),
    ('ops','complete_deployment_with_gate')
  )
  AND has_function_privilege('public', p.oid, 'EXECUTE');
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % high-value functions executable by PUBLIC', bad_count;
  END IF;
END $$;

-- 23. Prohibited large-body columns must not appear in commercial schemas.
DO $$
DECLARE
  bad_count bigint;
BEGIN
  SELECT count(*) INTO bad_count
  FROM information_schema.columns
  WHERE table_schema IN (
    'core','exec','artifact','analysis','generation','transform',
    'verify','metering','cache','integration','learning','ops','audit'
  )
  AND column_name IN ('source_code','full_ast','raw_model_output','complete_stdout');
  IF bad_count <> 0 THEN
    RAISE EXCEPTION 'invariant failed: % prohibited large-body columns found', bad_count;
  END IF;
END $$;

SELECT 'ELMOS DATABASE INVARIANTS PASSED' AS result;
