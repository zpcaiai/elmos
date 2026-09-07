-- Elmos Formal Assurance Kernel V4: immutable evidence and anti-status-inflation
CREATE OR REPLACE FUNCTION formal_assurance.reject_artifact_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'proof artifacts are immutable; create a new artifact';
END $$;

DROP TRIGGER IF EXISTS trg_proof_artifact_immutable ON formal_assurance.proof_artifact;
CREATE TRIGGER trg_proof_artifact_immutable
BEFORE UPDATE OR DELETE ON formal_assurance.proof_artifact
FOR EACH ROW EXECUTE FUNCTION formal_assurance.reject_artifact_mutation();

CREATE OR REPLACE FUNCTION formal_assurance.guard_proof_status()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.result_status = 'BOUNDED_NO_COUNTEREXAMPLE' AND NEW.mode <> 'BOUNDED' THEN
    RAISE EXCEPTION 'bounded status requires BOUNDED mode';
  END IF;
  IF NEW.result_status IN ('PROVED_CERTIFIED','PROVED_INDUCTIVE','PROVED_SOLVER_TRUSTED','PROVED_FOR_SUPPORTED_FRAGMENT')
     AND NEW.state <> 'SUCCEEDED' THEN
    RAISE EXCEPTION 'proved status requires SUCCEEDED state';
  END IF;
  IF NEW.result_status IN ('PROVED_CERTIFIED','PROVED_INDUCTIVE','PROVED_SOLVER_TRUSTED','PROVED_FOR_SUPPORTED_FRAGMENT')
     AND (NEW.assumption_hash IS NULL OR NEW.tcb_hash IS NULL) THEN
    RAISE EXCEPTION 'proved status requires assumption and TCB hashes';
  END IF;
  IF NEW.state IN ('SUCCEEDED','FAILED','CANCELLED','TIMED_OUT')
     AND OLD.state IN ('SUCCEEDED','FAILED','CANCELLED','TIMED_OUT')
     AND NEW.state <> OLD.state THEN
    RAISE EXCEPTION 'terminal proof run state cannot transition';
  END IF;
  IF NEW.fencing_token < OLD.fencing_token THEN
    RAISE EXCEPTION 'fencing token cannot decrease';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_guard_proof_status ON formal_assurance.proof_run;
CREATE TRIGGER trg_guard_proof_status
BEFORE UPDATE ON formal_assurance.proof_run
FOR EACH ROW EXECUTE FUNCTION formal_assurance.guard_proof_status();

CREATE OR REPLACE FUNCTION formal_assurance.mark_dependency_stale(
  p_dependency_kind text,
  p_dependency_id text,
  p_new_hash char(64)
) RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE
  affected bigint;
BEGIN
  UPDATE formal_assurance.proof_run r
     SET stale = true, updated_at = clock_timestamp()
   WHERE EXISTS (
     SELECT 1
       FROM formal_assurance.proof_dependency d
      WHERE d.proof_run_id = r.id
        AND d.dependency_kind = p_dependency_kind
        AND d.dependency_id = p_dependency_id
        AND d.dependency_hash <> p_new_hash
   );
  GET DIAGNOSTICS affected = ROW_COUNT;

  UPDATE formal_assurance.proof_cache c
     SET stale = true
   WHERE c.result_run_id IN (
     SELECT r.id FROM formal_assurance.proof_run r WHERE r.stale = true
   );

  RETURN affected;
END $$;

CREATE OR REPLACE FUNCTION formal_assurance.acquire_proof_run_lease(
  p_run_id text,
  p_owner_id text,
  p_expected_token bigint,
  p_lease_seconds integer
) RETURNS TABLE(fencing_token bigint, lease_expires_at timestamptz)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  UPDATE formal_assurance.proof_run
     SET owner_id = p_owner_id,
         fencing_token = formal_assurance.proof_run.fencing_token + 1,
         lease_expires_at = clock_timestamp() + make_interval(secs => p_lease_seconds),
         state = 'LEASED',
         updated_at = clock_timestamp()
   WHERE id = p_run_id
     AND fencing_token = p_expected_token
     AND (lease_expires_at IS NULL OR lease_expires_at < clock_timestamp() OR owner_id = p_owner_id)
  RETURNING formal_assurance.proof_run.fencing_token, formal_assurance.proof_run.lease_expires_at;
END $$;

CREATE OR REPLACE VIEW formal_assurance.latest_gate_decision AS
SELECT DISTINCT ON (tenant_id, subject_id, gate)
       tenant_id, account_id, subject_id, gate, decision, policy_revision,
       blocking_reasons, evidence_hash, evaluator_identity, evaluated_at, expires_at
  FROM formal_assurance.release_gate_decision
 ORDER BY tenant_id, subject_id, gate, evaluated_at DESC;
