-- ELMOS V61: retention means physical object deletion, not only hidden rows.
--
-- PURGE_PENDING separates "no longer downloadable" from "confirmed absent in
-- the object provider". A provider timeout or unknown response never advances
-- the object to PURGED; DELETE is retried idempotently until 2xx/404 is observed.

ALTER TABLE content_objects DROP CONSTRAINT content_objects_state;
ALTER TABLE content_objects
    ADD CONSTRAINT content_objects_state CHECK (
        object_state IN (
            'PENDING_UPLOAD', 'AVAILABLE', 'QUARANTINED',
            'PURGE_PENDING', 'PURGED'
        )
    );

ALTER TABLE object_gc_runs
    ADD COLUMN purge_failed_count integer NOT NULL DEFAULT 0,
    ADD CONSTRAINT object_gc_runs_purge_failed_nonnegative
        CHECK (purge_failed_count >= 0);

CREATE OR REPLACE FUNCTION elmos_expire_artifacts(
    p_gc_run_id varchar, p_batch_limit integer
) RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_expired integer := 0;
    v_held integer := 0;
BEGIN
    IF p_batch_limit < 1 OR p_batch_limit > 5000 THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_BATCH_INVALID';
    END IF;
    INSERT INTO object_gc_runs (gc_run_id) VALUES (p_gc_run_id)
    ON CONFLICT (gc_run_id) DO NOTHING;

    SELECT count(*) INTO v_held FROM job_artifacts
     WHERE deleted_at IS NULL AND legal_hold;
    WITH due AS (
        SELECT artifact_id FROM job_artifacts
         WHERE deleted_at IS NULL
           AND NOT legal_hold
           AND expires_at IS NOT NULL
           AND expires_at < now()
         ORDER BY expires_at
         LIMIT p_batch_limit
    ), marked AS (
        UPDATE job_artifacts artifact
           SET deleted_at = now(), deletion_reason = 'RETENTION_EXPIRED'
          FROM due
         WHERE artifact.artifact_id = due.artifact_id
        RETURNING 1
    )
    SELECT count(*) INTO v_expired FROM marked;

    UPDATE content_objects object
       SET object_state = 'PURGE_PENDING'
     WHERE object.object_state = 'AVAILABLE'
       AND NOT EXISTS (
            SELECT 1 FROM job_artifacts artifact
             WHERE artifact.content_object_ref = object.content_object_id
               AND artifact.deleted_at IS NULL
       );

    UPDATE object_gc_runs
       SET expired_count = v_expired, held_count = v_held
     WHERE gc_run_id = p_gc_run_id;
    RETURN v_expired;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_finish_object_gc(
    p_gc_run_id varchar,
    p_purged_count integer,
    p_purge_failed_count integer
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF p_purged_count < 0 OR p_purge_failed_count < 0 THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_COUNT_INVALID';
    END IF;
    UPDATE object_gc_runs
       SET finished_at = now(),
           purged_count = p_purged_count,
           purge_failed_count = p_purge_failed_count,
           failure_code = CASE
               WHEN p_purge_failed_count > 0
                   THEN 'OBJECT_PROVIDER_RESULT_UNKNOWN'
               ELSE NULL
           END,
           run_state = CASE
               WHEN p_purge_failed_count > 0 THEN 'FAILED'
               ELSE 'COMPLETED'
           END
     WHERE gc_run_id = p_gc_run_id
       AND run_state = 'RUNNING';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_RUN_NOT_ACTIVE';
    END IF;
    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_pending_object_purges(p_batch_limit integer)
RETURNS TABLE (
    organization_id varchar,
    content_object_id varchar,
    content_sha256 varchar
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF p_batch_limit < 1 OR p_batch_limit > 1000 THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_PURGE_BATCH_INVALID';
    END IF;
    RETURN QUERY
    SELECT object.organization_id, object.content_object_id, object.content_sha256
      FROM content_objects object
     WHERE object.object_state = 'PURGE_PENDING'
     ORDER BY object.created_at, object.content_object_id
     LIMIT p_batch_limit;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_confirm_object_purged(
    p_organization_id varchar,
    p_content_object_id varchar
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    PERFORM set_config('app.organization_id', p_organization_id, true);
    UPDATE content_objects
       SET object_state = 'PURGED'
     WHERE organization_id = p_organization_id
       AND content_object_id = p_content_object_id
       AND object_state = 'PURGE_PENDING';
    RETURN FOUND;
END;
$$;

REVOKE EXECUTE ON FUNCTION elmos_expire_artifacts(varchar, integer) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION elmos_pending_object_purges(integer) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION elmos_confirm_object_purged(varchar, varchar) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION elmos_finish_object_gc(varchar, integer, integer) FROM PUBLIC;
