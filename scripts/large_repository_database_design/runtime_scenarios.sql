-- Bounded engineering evidence for the imported large-repository database design.
-- This is not certification or production evidence. Run only after all package
-- migrations and roles have been installed in a disposable PostgreSQL database.
-- The fixture is transaction-scoped, performs no external I/O, and rolls back.
\set ON_ERROR_STOP on

BEGIN;

-- Fixed identities make assertion failures reproducible. The surrounding
-- transaction is the cleanup boundary; a failure under ON_ERROR_STOP also
-- leaves no committed fixture data.
INSERT INTO core.tenant (id, slug, display_name)
VALUES
  ('00000000-0000-4000-8000-00000000a001', 'db-runtime-a', 'DB runtime tenant A'),
  ('00000000-0000-4000-8000-00000000b001', 'db-runtime-b', 'DB runtime tenant B');

INSERT INTO core.account (
  id, tenant_id, external_subject, display_name, concurrency_limit
)
VALUES
  (
    '00000000-0000-4000-8000-00000000a002',
    '00000000-0000-4000-8000-00000000a001',
    'db-runtime-account-a',
    'DB runtime account A',
    3
  ),
  (
    '00000000-0000-4000-8000-00000000b002',
    '00000000-0000-4000-8000-00000000b001',
    'db-runtime-account-b',
    'DB runtime account B',
    3
  );

INSERT INTO core.project (
  id, tenant_id, project_key, name, created_by_account_id
)
VALUES (
  '00000000-0000-4000-8000-00000000a003',
  '00000000-0000-4000-8000-00000000a001',
  'db-runtime-project',
  'DB runtime project',
  '00000000-0000-4000-8000-00000000a002'
);

INSERT INTO core.revision_snapshot (
  id, tenant_id, revision_kind, logical_key, content_sha256, inline_document
)
VALUES
  (
    '00000000-0000-4000-8000-00000000a031',
    '00000000-0000-4000-8000-00000000a001',
    'policy', 'db-runtime-policy', repeat('1', 64), '{}'::jsonb
  ),
  (
    '00000000-0000-4000-8000-00000000a032',
    '00000000-0000-4000-8000-00000000a001',
    'workflow', 'db-runtime-workflow', repeat('2', 64), '{}'::jsonb
  ),
  (
    '00000000-0000-4000-8000-00000000a033',
    '00000000-0000-4000-8000-00000000a001',
    'model_route', 'db-runtime-model-route', repeat('3', 64), '{}'::jsonb
  ),
  (
    '00000000-0000-4000-8000-00000000a034',
    '00000000-0000-4000-8000-00000000a001',
    'toolchain', 'db-runtime-toolchain', repeat('4', 64), '{}'::jsonb
  ),
  (
    '00000000-0000-4000-8000-00000000a035',
    '00000000-0000-4000-8000-00000000a001',
    'environment', 'db-runtime-environment', repeat('5', 64), '{}'::jsonb
  );

INSERT INTO core.job (
  id, tenant_id, project_id, account_id, job_type, title, status
)
VALUES
  (
    '00000000-0000-4000-8000-00000000a011',
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a003',
    '00000000-0000-4000-8000-00000000a002',
    'repository_analysis', 'DB runtime job 1', 'admitted'
  ),
  (
    '00000000-0000-4000-8000-00000000a012',
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a003',
    '00000000-0000-4000-8000-00000000a002',
    'repository_analysis', 'DB runtime job 2', 'admitted'
  ),
  (
    '00000000-0000-4000-8000-00000000a013',
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a003',
    '00000000-0000-4000-8000-00000000a002',
    'repository_analysis', 'DB runtime job 3', 'admitted'
  ),
  (
    '00000000-0000-4000-8000-00000000a014',
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a003',
    '00000000-0000-4000-8000-00000000a002',
    'repository_analysis', 'DB runtime job 4', 'admitted'
  );

INSERT INTO exec.run (
  id, tenant_id, job_id, account_id, run_no, run_kind, status,
  policy_revision_id, workflow_revision_id, model_route_revision_id,
  toolchain_revision_id, environment_revision_id, input_bundle_sha256
)
SELECT
  v.run_id,
  '00000000-0000-4000-8000-00000000a001'::uuid,
  v.job_id,
  '00000000-0000-4000-8000-00000000a002'::uuid,
  1,
  'analysis',
  'planning',
  '00000000-0000-4000-8000-00000000a031'::uuid,
  '00000000-0000-4000-8000-00000000a032'::uuid,
  '00000000-0000-4000-8000-00000000a033'::uuid,
  '00000000-0000-4000-8000-00000000a034'::uuid,
  '00000000-0000-4000-8000-00000000a035'::uuid,
  repeat('e', 64)
FROM (
  VALUES
    (
      '00000000-0000-4000-8000-00000000a021'::uuid,
      '00000000-0000-4000-8000-00000000a011'::uuid
    ),
    (
      '00000000-0000-4000-8000-00000000a022'::uuid,
      '00000000-0000-4000-8000-00000000a012'::uuid
    ),
    (
      '00000000-0000-4000-8000-00000000a023'::uuid,
      '00000000-0000-4000-8000-00000000a013'::uuid
    ),
    (
      '00000000-0000-4000-8000-00000000a024'::uuid,
      '00000000-0000-4000-8000-00000000a014'::uuid
    )
) AS v(run_id, job_id);

-- Admission is authoritative in three physical rows. The first three Runs
-- claim slots 1..3, the fourth receives no row, and a valid release permits
-- the fourth Run to acquire the released slot with a higher generation.
DO $scenario$
DECLARE
  v_slot_1 smallint;
  v_slot_2 smallint;
  v_slot_3 smallint;
  v_slot_4 smallint;
  v_generation_1 bigint;
  v_generation_4 bigint;
  v_token_1 uuid;
  v_claimed_count integer;
  v_released boolean;
  v_stale_rejected boolean := false;
BEGIN
  SELECT claimed_slot_no, claimed_generation, claimed_token
  INTO v_slot_1, v_generation_1, v_token_1
  FROM core.claim_account_slot(
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a002',
    '00000000-0000-4000-8000-00000000a021',
    interval '10 minutes'
  );

  SELECT claimed_slot_no INTO v_slot_2
  FROM core.claim_account_slot(
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a002',
    '00000000-0000-4000-8000-00000000a022',
    interval '10 minutes'
  );

  SELECT claimed_slot_no INTO v_slot_3
  FROM core.claim_account_slot(
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a002',
    '00000000-0000-4000-8000-00000000a023',
    interval '10 minutes'
  );

  SELECT claimed_slot_no INTO v_slot_4
  FROM core.claim_account_slot(
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a002',
    '00000000-0000-4000-8000-00000000a024',
    interval '10 minutes'
  );

  SELECT count(*) INTO v_claimed_count
  FROM core.account_task_slot
  WHERE tenant_id = '00000000-0000-4000-8000-00000000a001'
    AND account_id = '00000000-0000-4000-8000-00000000a002'
    AND claimed_by_run_id IS NOT NULL;

  IF ARRAY[v_slot_1, v_slot_2, v_slot_3] <> ARRAY[1, 2, 3]::smallint[]
     OR v_slot_4 IS NOT NULL
     OR v_claimed_count <> 3 THEN
    RAISE EXCEPTION
      'three-slot admission invariant failed: slots=%,%,%, fourth=%, claimed=%',
      v_slot_1, v_slot_2, v_slot_3, v_slot_4, v_claimed_count;
  END IF;

  SELECT core.release_account_slot(
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a002',
    '00000000-0000-4000-8000-00000000a021',
    v_generation_1
  ) INTO v_released;
  IF NOT v_released THEN
    RAISE EXCEPTION 'valid account-slot release was rejected';
  END IF;

  SELECT claimed_slot_no, claimed_generation
  INTO v_slot_4, v_generation_4
  FROM core.claim_account_slot(
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a002',
    '00000000-0000-4000-8000-00000000a024',
    interval '10 minutes'
  );

  IF v_slot_4 <> v_slot_1 OR v_generation_4 <= v_generation_1 THEN
    RAISE EXCEPTION
      'released slot was not fenced on reuse: old=(%,%), new=(%,%)',
      v_slot_1, v_generation_1, v_slot_4, v_generation_4;
  END IF;

  BEGIN
    PERFORM core.renew_account_slot(
      '00000000-0000-4000-8000-00000000a001',
      '00000000-0000-4000-8000-00000000a002',
      '00000000-0000-4000-8000-00000000a021',
      v_slot_1,
      v_generation_1,
      v_token_1,
      interval '10 minutes'
    );
  EXCEPTION
    WHEN SQLSTATE '40001' THEN
      v_stale_rejected := true;
  END;

  IF NOT v_stale_rejected THEN
    RAISE EXCEPTION 'stale account-slot generation/token was accepted';
  END IF;
END;
$scenario$;

-- Appends are serialized through the cursor and the journal is immutable.
DO $scenario$
DECLARE
  v_seq_1 bigint;
  v_seq_2 bigint;
  v_hash_1 text;
  v_hash_2 text;
  v_previous text;
  v_immutable boolean := false;
BEGIN
  SELECT event_seq, event_hash INTO v_seq_1, v_hash_1
  FROM exec.append_run_event(
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a022',
    'runtime.first',
    '{"ordinal": 1}'::jsonb
  );

  SELECT event_seq, event_hash INTO v_seq_2, v_hash_2
  FROM exec.append_run_event(
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a022',
    'runtime.second',
    '{"ordinal": 2}'::jsonb
  );

  SELECT previous_event_hash INTO v_previous
  FROM exec.run_event
  WHERE tenant_id = '00000000-0000-4000-8000-00000000a001'
    AND run_id = '00000000-0000-4000-8000-00000000a022'
    AND seq = 2;

  IF v_seq_1 <> 1 OR v_seq_2 <> 2 OR v_previous IS DISTINCT FROM v_hash_1
     OR v_hash_2 IS NULL THEN
    RAISE EXCEPTION
      'run-event ordering/hash invariant failed: seqs=%,%, previous=%',
      v_seq_1, v_seq_2, v_previous;
  END IF;

  BEGIN
    UPDATE exec.run_event
    SET payload = '{"tampered": true}'::jsonb
    WHERE tenant_id = '00000000-0000-4000-8000-00000000a001'
      AND run_id = '00000000-0000-4000-8000-00000000a022'
      AND seq = 1;
  EXCEPTION
    WHEN SQLSTATE '55000' THEN
      v_immutable := true;
  END;

  IF NOT v_immutable THEN
    RAISE EXCEPTION 'append-only run event accepted an UPDATE';
  END IF;
END;
$scenario$;

-- A real task claim supplies both a lease generation and a fencing token.
-- Wrong generation renewal and wrong-fence completion must be rejected without
-- changing the claimed Attempt or Task.
INSERT INTO exec.run_stage (
  id, tenant_id, run_id, stage_key, stage_type, ordinal, status
)
VALUES (
  '00000000-0000-4000-8000-00000000a041',
  '00000000-0000-4000-8000-00000000a001',
  '00000000-0000-4000-8000-00000000a023',
  'runtime', 'verification', 0, 'running'
);

INSERT INTO exec.task (
  id, tenant_id, run_id, stage_id, task_key, task_type, title, status,
  idempotency_key, input_sha256
)
VALUES (
  '00000000-0000-4000-8000-00000000a042',
  '00000000-0000-4000-8000-00000000a001',
  '00000000-0000-4000-8000-00000000a023',
  '00000000-0000-4000-8000-00000000a041',
  'runtime-fence', 'runtime_fixture', 'Runtime fencing fixture', 'ready',
  'runtime-fence-attempt', repeat('f', 64)
);

INSERT INTO exec.worker_node (
  id, tenant_id, worker_pool, node_name, platform, architecture, status
)
VALUES (
  '00000000-0000-4000-8000-00000000a043',
  '00000000-0000-4000-8000-00000000a001',
  'runtime-fixture', 'runtime-fixture-1', 'linux', 'x86_64', 'ready'
);

DO $scenario$
DECLARE
  v_attempt_id uuid;
  v_generation bigint;
  v_lease_token uuid;
  v_fencing_token uuid;
  v_generation_rejected boolean := false;
  v_fence_rejected boolean := false;
  v_attempt_status text;
  v_task_status text;
BEGIN
  SELECT task_attempt_id, lease_generation, lease_token, fencing_token
  INTO v_attempt_id, v_generation, v_lease_token, v_fencing_token
  FROM exec.claim_ready_task(
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a023',
    '00000000-0000-4000-8000-00000000a043',
    interval '10 minutes'
  );

  IF v_attempt_id IS NULL THEN
    RAISE EXCEPTION 'ready task was not claimed';
  END IF;

  BEGIN
    PERFORM exec.renew_task_lease(
      '00000000-0000-4000-8000-00000000a001',
      v_attempt_id,
      v_lease_token,
      v_generation + 1,
      v_fencing_token,
      interval '10 minutes'
    );
  EXCEPTION
    WHEN SQLSTATE '40001' THEN
      v_generation_rejected := true;
  END;

  BEGIN
    PERFORM exec.finish_task_attempt(
      '00000000-0000-4000-8000-00000000a001',
      v_attempt_id,
      v_lease_token,
      v_generation,
      '00000000-0000-4000-8000-00000000ffff',
      'succeeded'
    );
  EXCEPTION
    WHEN SQLSTATE '40001' THEN
      v_fence_rejected := true;
  END;

  SELECT status INTO v_attempt_status
  FROM exec.task_attempt
  WHERE tenant_id = '00000000-0000-4000-8000-00000000a001'
    AND id = v_attempt_id;
  SELECT status INTO v_task_status
  FROM exec.task
  WHERE tenant_id = '00000000-0000-4000-8000-00000000a001'
    AND id = '00000000-0000-4000-8000-00000000a042';

  IF NOT v_generation_rejected OR NOT v_fence_rejected
     OR v_attempt_status <> 'claimed' OR v_task_status <> 'claimed' THEN
    RAISE EXCEPTION
      'stale task writer invariant failed: generation=%, fence=%, attempt=%, task=%',
      v_generation_rejected, v_fence_rejected, v_attempt_status, v_task_status;
  END IF;
END;
$scenario$;

-- Build a minimal, internally bound analysis Run gate. Its passing summary is
-- deliberately stale: an external write timed out to unknown_result after the
-- evaluation. P05 must re-read authoritative receipts and reject completion.
INSERT INTO artifact.object_blob (
  tenant_id, sha256, storage_backend, bucket_name, object_key, size_bytes,
  object_state, verified_at
)
VALUES
  (
    '00000000-0000-4000-8000-00000000a001', repeat('6', 64),
    'filesystem', 'elmos-disposable', 'runtime/tree', 1, 'available', clock_timestamp()
  ),
  (
    '00000000-0000-4000-8000-00000000a001', repeat('7', 64),
    'filesystem', 'elmos-disposable', 'runtime/evidence', 1, 'available', clock_timestamp()
  );

INSERT INTO artifact.artifact (
  id, tenant_id, artifact_kind, logical_name, sha256, size_bytes, state,
  created_by_run_id
)
VALUES
  (
    '00000000-0000-4000-8000-00000000a051',
    '00000000-0000-4000-8000-00000000a001',
    'generated_tree', 'runtime-tree', repeat('6', 64), 1, 'available',
    '00000000-0000-4000-8000-00000000a024'
  ),
  (
    '00000000-0000-4000-8000-00000000a053',
    '00000000-0000-4000-8000-00000000a001',
    'evidence', 'runtime-evidence', repeat('7', 64), 1, 'available',
    '00000000-0000-4000-8000-00000000a024'
  );

INSERT INTO artifact.manifest (
  id, tenant_id, manifest_kind, root_sha256, manifest_artifact_id,
  entry_count, total_bytes
)
VALUES
  (
    '00000000-0000-4000-8000-00000000a052',
    '00000000-0000-4000-8000-00000000a001',
    'repository_tree', repeat('8', 64),
    '00000000-0000-4000-8000-00000000a051', 1, 1
  ),
  (
    '00000000-0000-4000-8000-00000000a054',
    '00000000-0000-4000-8000-00000000a001',
    'evidence_bundle', repeat('9', 64),
    '00000000-0000-4000-8000-00000000a053', 1, 1
  );

INSERT INTO artifact.manifest_entry (
  tenant_id, manifest_id, entry_path, entry_kind, artifact_id, sha256, size_bytes
)
VALUES
  (
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a052',
    'tree', 'artifact', '00000000-0000-4000-8000-00000000a051',
    repeat('6', 64), 1
  ),
  (
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a054',
    'evidence', 'artifact', '00000000-0000-4000-8000-00000000a053',
    repeat('7', 64), 1
  );

UPDATE artifact.manifest
SET sealed = true, sealed_at = clock_timestamp()
WHERE tenant_id = '00000000-0000-4000-8000-00000000a001'
  AND id IN (
    '00000000-0000-4000-8000-00000000a052',
    '00000000-0000-4000-8000-00000000a054'
  );

INSERT INTO transform.target_revision (
  id, tenant_id, run_id, sequence_no, tree_manifest_id, tree_sha256,
  revision_kind, status, source_event_seq
)
VALUES (
  '00000000-0000-4000-8000-00000000a055',
  '00000000-0000-4000-8000-00000000a001',
  '00000000-0000-4000-8000-00000000a024',
  1,
  '00000000-0000-4000-8000-00000000a052',
  repeat('6', 64),
  'generated', 'verified', 0
);

UPDATE exec.run
SET current_target_revision_id = '00000000-0000-4000-8000-00000000a055'
WHERE tenant_id = '00000000-0000-4000-8000-00000000a001'
  AND id = '00000000-0000-4000-8000-00000000a024';

INSERT INTO verify.evidence_item (
  id, tenant_id, run_id, target_revision_id, evidence_kind, subject_kind,
  producer_kind, producer_id, source_event_seq, artifact_id, evidence_sha256,
  status, environment_revision_id, toolchain_revision_id
)
VALUES (
  '00000000-0000-4000-8000-00000000a056',
  '00000000-0000-4000-8000-00000000a001',
  '00000000-0000-4000-8000-00000000a024',
  '00000000-0000-4000-8000-00000000a055',
  'manual', 'run', 'verifier', 'runtime-scenario', 0,
  '00000000-0000-4000-8000-00000000a053', repeat('a', 64), 'passed',
  '00000000-0000-4000-8000-00000000a035',
  '00000000-0000-4000-8000-00000000a034'
);

INSERT INTO verify.evidence_bundle (
  id, tenant_id, run_id, target_revision_id, bundle_no, status,
  bundle_manifest_id, bundle_sha256, evidence_count, sealed_at
)
VALUES (
  '00000000-0000-4000-8000-00000000a057',
  '00000000-0000-4000-8000-00000000a001',
  '00000000-0000-4000-8000-00000000a024',
  '00000000-0000-4000-8000-00000000a055',
  1, 'sealed', '00000000-0000-4000-8000-00000000a054',
  repeat('b', 64), 1, clock_timestamp()
);

INSERT INTO verify.evidence_bundle_item (
  tenant_id, evidence_bundle_id, evidence_item_id, ordinal
)
VALUES (
  '00000000-0000-4000-8000-00000000a001',
  '00000000-0000-4000-8000-00000000a057',
  '00000000-0000-4000-8000-00000000a056',
  0
);

INSERT INTO verify.gate_evaluation (
  id, tenant_id, run_id, gate_kind, gate_policy_revision_id,
  source_repository_revision_id, target_revision_id, requirements_revision_id,
  policy_revision_id, workflow_revision_id, model_route_revision_id,
  toolchain_revision_id, environment_revision_id, evidence_bundle_id,
  decision, requirement_coverage, capability_coverage,
  unknown_gap_count, critical_failure_count, unresolved_side_effect_count,
  unfinished_task_count, evaluation_summary, evaluator_version
)
VALUES (
  '00000000-0000-4000-8000-00000000a058',
  '00000000-0000-4000-8000-00000000a001',
  '00000000-0000-4000-8000-00000000a024',
  'release_candidate',
  '00000000-0000-4000-8000-00000000a031',
  NULL,
  '00000000-0000-4000-8000-00000000a055',
  NULL,
  '00000000-0000-4000-8000-00000000a031',
  '00000000-0000-4000-8000-00000000a032',
  '00000000-0000-4000-8000-00000000a033',
  '00000000-0000-4000-8000-00000000a034',
  '00000000-0000-4000-8000-00000000a035',
  '00000000-0000-4000-8000-00000000a057',
  'pass', 100.000, 100.000, 0, 0, 0, 0,
  '{"bounded_fixture": true}'::jsonb,
  'runtime-scenario-v1'
);

DO $scenario$
BEGIN
  PERFORM integration.reserve_side_effect(
    '00000000-0000-4000-8000-00000000a001',
    '00000000-0000-4000-8000-00000000a024',
    NULL,
    NULL,
    NULL,
    'external_api_write',
    'runtime.invalid.example',
    'runtime-side-effect',
    repeat('c', 64)
  );
END;
$scenario$;

UPDATE integration.side_effect_receipt
SET status = 'unknown_result',
    first_dispatched_at = clock_timestamp(),
    last_checked_at = clock_timestamp()
WHERE tenant_id = '00000000-0000-4000-8000-00000000a001'
  AND run_id = '00000000-0000-4000-8000-00000000a024';

DO $scenario$
DECLARE
  v_p05_rejected boolean := false;
  v_run_status text;
  v_unresolved bigint;
BEGIN
  BEGIN
    PERFORM verify.complete_run_with_gate(
      '00000000-0000-4000-8000-00000000a001',
      '00000000-0000-4000-8000-00000000a024',
      '00000000-0000-4000-8000-00000000a058'
    );
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLERRM NOT LIKE 'completion invariants failed:%' THEN
        RAISE;
      END IF;
      v_p05_rejected := true;
  END;

  SELECT status INTO v_run_status
  FROM exec.run
  WHERE tenant_id = '00000000-0000-4000-8000-00000000a001'
    AND id = '00000000-0000-4000-8000-00000000a024';
  SELECT unresolved_side_effect_count INTO v_unresolved
  FROM verify.v_completion_readiness
  WHERE tenant_id = '00000000-0000-4000-8000-00000000a001'
    AND run_id = '00000000-0000-4000-8000-00000000a024';

  IF NOT v_p05_rejected OR v_run_status = 'completed' OR v_unresolved <> 1 THEN
    RAISE EXCEPTION
      'unresolved side effect did not block P05: rejected=%, status=%, unresolved=%',
      v_p05_rejected, v_run_status, v_unresolved;
  END IF;
END;
$scenario$;

-- The role setup makes the schema owner NOBYPASSRLS while retaining the table
-- privileges required to observe FORCE RLS. With no context it sees no tenant;
-- with tenant A it cannot read or insert tenant B rows.
SET LOCAL ROLE elmos_schema_owner;
SET LOCAL app.tenant_id = '';

DO $scenario$
DECLARE v_visible bigint;
BEGIN
  SELECT count(*) INTO v_visible
  FROM core.account
  WHERE id IN (
    '00000000-0000-4000-8000-00000000a002',
    '00000000-0000-4000-8000-00000000b002'
  );
  IF v_visible <> 0 THEN
    RAISE EXCEPTION 'RLS without tenant context exposed % fixture accounts', v_visible;
  END IF;
END;
$scenario$;

SET LOCAL app.tenant_id = '00000000-0000-4000-8000-00000000a001';

DO $scenario$
DECLARE
  v_visible_a bigint;
  v_visible_b bigint;
  v_cross_tenant_rejected boolean := false;
BEGIN
  SELECT count(*) INTO v_visible_a
  FROM core.account
  WHERE id = '00000000-0000-4000-8000-00000000a002';
  SELECT count(*) INTO v_visible_b
  FROM core.account
  WHERE id = '00000000-0000-4000-8000-00000000b002';

  BEGIN
    INSERT INTO core.account (
      id, tenant_id, external_subject, display_name, concurrency_limit
    ) VALUES (
      '00000000-0000-4000-8000-00000000b099',
      '00000000-0000-4000-8000-00000000b001',
      'db-runtime-forbidden-b',
      'Cross-tenant write must fail',
      3
    );
  EXCEPTION
    WHEN SQLSTATE '42501' THEN
      v_cross_tenant_rejected := true;
  END;

  IF v_visible_a <> 1 OR v_visible_b <> 0 OR NOT v_cross_tenant_rejected THEN
    RAISE EXCEPTION
      'two-tenant RLS invariant failed: visible_a=%, visible_b=%, write_rejected=%',
      v_visible_a, v_visible_b, v_cross_tenant_rejected;
  END IF;
END;
$scenario$;

RESET ROLE;
ROLLBACK;

SELECT 'ELMOS LARGE-REPOSITORY DATABASE RUNTIME SCENARIOS PASSED' AS result;
