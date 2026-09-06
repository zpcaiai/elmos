-- Input bytes use the existing tenant content-object authority, never job JSON.
-- A PREPARED binding covers upload/verification uncertainty WITHOUT TTL GC.
-- Its expiry restricts attach only: URL expiry does not stop an in-flight PUT.
-- Unknown roots consume a finite budget until trusted operator reconciliation.
-- ATTACHED bindings
-- live through the job and the tenant's STANDARD post-terminal retention.
CREATE TABLE execution_input_bindings (
    binding_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    idempotency_key varchar(160) NOT NULL,
    content_object_ref varchar(96) NOT NULL REFERENCES content_objects(content_object_id),
    content_sha256 varchar(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    byte_size bigint NOT NULL CHECK (byte_size BETWEEN 1 AND 100663296),
    job_ref varchar(96) REFERENCES execution_jobs(job_id),
    binding_state varchar(16) NOT NULL DEFAULT 'PREPARED' CHECK (binding_state IN ('PREPARED', 'ATTACHED')),
    prepared_expires_at timestamptz NOT NULL DEFAULT now() + interval '1 hour',
    retain_days integer NOT NULL CHECK (retain_days BETWEEN 1 AND 3650),
    legal_hold boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key),
    UNIQUE (job_ref),
    CHECK ((binding_state = 'PREPARED' AND job_ref IS NULL) OR (binding_state = 'ATTACHED' AND job_ref IS NOT NULL))
);
CREATE INDEX execution_input_object_idx ON execution_input_bindings(content_object_ref);
ALTER TABLE execution_input_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE execution_input_bindings FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON execution_input_bindings
    USING (organization_id = current_setting('app.organization_id', true))
    WITH CHECK (organization_id = current_setting('app.organization_id', true));
REVOKE ALL ON execution_input_bindings FROM PUBLIC;

CREATE FUNCTION elmos_prepare_execution_input(
    p_id varchar, p_org varchar, p_key varchar, p_object varchar, p_sha varchar, p_bytes bigint
) RETURNS varchar LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_object content_objects%ROWTYPE; v_binding execution_input_bindings%ROWTYPE;
BEGIN
    IF p_org IS DISTINCT FROM current_setting('app.organization_id', true)
        OR p_key IS NULL OR length(p_key) NOT BETWEEN 1 AND 160 THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_INPUT_SUBJECT_INVALID';
    END IF;
    -- Short metadata-only admission lock; never held over provider I/O.
    PERFORM pg_advisory_xact_lock(8601, 1);
    IF NOT EXISTS (SELECT 1 FROM execution_input_bindings WHERE organization_id = p_org AND idempotency_key = p_key)
      AND ((SELECT count(*) FROM execution_input_bindings WHERE binding_state = 'PREPARED') >= 128
        OR (SELECT coalesce(sum(byte_size),0) FROM execution_input_bindings WHERE binding_state = 'PREPARED') + p_bytes > 4294967296
        OR (SELECT count(*) FROM execution_input_bindings WHERE binding_state = 'PREPARED' AND organization_id = p_org) >= 8
        OR (SELECT coalesce(sum(byte_size),0) FROM execution_input_bindings WHERE binding_state = 'PREPARED' AND organization_id = p_org) + p_bytes > 536870912) THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_INPUT_UNRECONCILED_CAPACITY';
    END IF;
    -- Every root creator locks the object BEFORE testing state. GC uses the
    -- same lock, and tests roots in a separate command after acquiring it.
    SELECT * INTO v_object FROM content_objects
      WHERE organization_id = p_org AND content_object_id = p_object FOR UPDATE;
    IF NOT FOUND OR v_object.content_sha256 IS DISTINCT FROM p_sha
        OR v_object.byte_size IS DISTINCT FROM p_bytes
        OR v_object.object_state NOT IN ('PENDING_UPLOAD', 'AVAILABLE') THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_INPUT_OBJECT_INVALID';
    END IF;
    INSERT INTO execution_input_bindings(binding_id, organization_id, idempotency_key,
        content_object_ref, content_sha256, byte_size, retain_days)
      VALUES (p_id, p_org, p_key, p_object, p_sha, p_bytes,
        elmos_effective_retention_days(p_org, 'STANDARD'))
      ON CONFLICT (organization_id, idempotency_key) DO NOTHING;
    SELECT * INTO v_binding FROM execution_input_bindings
      WHERE organization_id = p_org AND idempotency_key = p_key FOR UPDATE;
    IF v_binding.content_object_ref IS DISTINCT FROM p_object
        OR v_binding.content_sha256 IS DISTINCT FROM p_sha OR v_binding.byte_size IS DISTINCT FROM p_bytes THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_INPUT_IDEMPOTENCY_CONFLICT';
    END IF;
    IF v_binding.binding_state = 'PREPARED' THEN
        UPDATE execution_input_bindings SET prepared_expires_at = clock_timestamp() + interval '1 hour'
          WHERE binding_id = v_binding.binding_id;
    END IF;
    RETURN v_binding.binding_id;
END $$;

CREATE FUNCTION elmos_attach_execution_input(p_org varchar, p_job varchar, p_binding varchar)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_job execution_jobs%ROWTYPE; v_binding execution_input_bindings%ROWTYPE; v_object content_objects%ROWTYPE;
BEGIN
    IF p_org IS DISTINCT FROM current_setting('app.organization_id', true) THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_INPUT_SUBJECT_INVALID';
    END IF;
    SELECT * INTO v_binding FROM execution_input_bindings WHERE organization_id = p_org AND binding_id = p_binding;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_EXECUTION_INPUT_UNKNOWN'; END IF;
    SELECT * INTO v_object FROM content_objects WHERE content_object_id = v_binding.content_object_ref
        AND organization_id = p_org FOR UPDATE;
    SELECT * INTO v_binding FROM execution_input_bindings WHERE organization_id = p_org AND binding_id = p_binding FOR UPDATE;
    SELECT * INTO v_job FROM execution_jobs WHERE organization_id = p_org AND job_id = p_job FOR UPDATE;
    IF NOT FOUND OR v_job.business_line <> 'TRANSLATION' OR v_job.job_kind <> 'translate-pipeline-v1'
        OR v_object.object_state <> 'AVAILABLE'
        OR v_job.request_payload->'input' IS DISTINCT FROM jsonb_build_object(
            'bindingId', p_binding, 'objectId', v_object.content_object_id,
            'sha256', v_binding.content_sha256, 'byteSize', v_binding.byte_size)
        OR (v_binding.job_ref IS NOT NULL AND v_binding.job_ref <> p_job)
        OR (v_binding.binding_state = 'PREPARED' AND v_binding.prepared_expires_at <= clock_timestamp()) THEN
        RAISE EXCEPTION 'ELMOS_EXECUTION_INPUT_BINDING_INVALID';
    END IF;
    UPDATE execution_input_bindings SET binding_state = 'ATTACHED', job_ref = p_job WHERE binding_id = p_binding;
    UPDATE content_objects SET last_referenced_at = clock_timestamp() WHERE content_object_id = v_object.content_object_id;
    RETURN true;
END $$;

CREATE FUNCTION elmos_execution_input_retained(p_object varchar) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT EXISTS (
        SELECT 1 FROM execution_input_bindings b LEFT JOIN execution_jobs j
          ON j.job_id = b.job_ref AND j.organization_id = b.organization_id
        WHERE b.content_object_ref = p_object AND (
            b.legal_hold OR b.binding_state = 'PREPARED'
            OR (b.binding_state = 'ATTACHED' AND (
                j.job_id IS NULL OR j.status NOT IN ('SUCCEEDED', 'PARTIAL', 'FAILED', 'CANCELLED', 'LOST')
                OR j.finished_at IS NULL OR j.finished_at + make_interval(days => b.retain_days) > clock_timestamp()))
        )
    )
$$;

CREATE OR REPLACE FUNCTION elmos_expire_artifacts(p_gc_run_id varchar, p_batch_limit integer)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_expired integer := 0; v_held integer := 0; v_object varchar;
BEGIN
    IF p_batch_limit IS NULL OR p_batch_limit < 1 OR p_batch_limit > 5000 THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_BATCH_INVALID';
    END IF;
    INSERT INTO object_gc_runs(gc_run_id) VALUES(p_gc_run_id) ON CONFLICT(gc_run_id) DO NOTHING;
    SELECT count(*) INTO v_held FROM job_artifacts WHERE deleted_at IS NULL AND legal_hold;
    WITH due AS (
        SELECT artifact_id FROM job_artifacts WHERE deleted_at IS NULL AND NOT legal_hold
          AND expires_at IS NOT NULL AND expires_at < now()
          ORDER BY expires_at LIMIT p_batch_limit FOR UPDATE SKIP LOCKED
    ), marked AS (
        UPDATE job_artifacts a SET deleted_at = now(), deletion_reason = 'RETENTION_EXPIRED'
          FROM due WHERE a.artifact_id = due.artifact_id RETURNING 1
    ) SELECT count(*) INTO v_expired FROM marked;
    FOR v_object IN SELECT o.content_object_id FROM content_objects o
        WHERE o.object_state = 'AVAILABLE'
          AND NOT EXISTS (SELECT 1 FROM job_artifacts a WHERE a.content_object_ref = o.content_object_id AND a.deleted_at IS NULL)
          AND NOT elmos_execution_input_retained(o.content_object_id)
        ORDER BY o.created_at, o.content_object_id LIMIT p_batch_limit FOR UPDATE SKIP LOCKED
    LOOP
        -- New READ COMMITTED command snapshot after obtaining the object lock:
        -- a concurrent prepare/attach committed before our lock is visible.
        UPDATE content_objects o SET object_state = 'PURGE_PENDING'
          WHERE o.content_object_id = v_object AND o.object_state = 'AVAILABLE'
            AND NOT EXISTS (SELECT 1 FROM job_artifacts a WHERE a.content_object_ref = o.content_object_id AND a.deleted_at IS NULL)
            AND NOT elmos_execution_input_retained(o.content_object_id);
    END LOOP;
    UPDATE object_gc_runs SET expired_count = v_expired, held_count = v_held WHERE gc_run_id = p_gc_run_id;
    RETURN v_expired;
END $$;

REVOKE EXECUTE ON FUNCTION elmos_prepare_execution_input(varchar,varchar,varchar,varchar,varchar,bigint) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION elmos_attach_execution_input(varchar,varchar,varchar) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION elmos_execution_input_retained(varchar) FROM PUBLIC;

-- Existing artifact publishers are root creators too. Acquire the same object
-- lock before observing AVAILABLE; publishing may not resurrect PURGE_PENDING.
CREATE OR REPLACE FUNCTION elmos_publish_job_artifact(
    p_artifact_id varchar,
    p_organization_id varchar,
    p_job_id varchar,
    p_artifact_role varchar,
    p_filename varchar,
    p_content_object_id varchar,
    p_retention_class varchar
) RETURNS varchar
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_object content_objects%ROWTYPE;
    v_days integer;
    v_seq integer;
BEGIN
    SELECT * INTO v_object FROM content_objects
     WHERE content_object_id = p_content_object_id AND organization_id = p_organization_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_CONTENT_OBJECT_UNKNOWN'; END IF;
    IF v_object.object_state <> 'AVAILABLE' THEN
        -- Publication before server-side digest verification is the exact
        -- failure mode that lets a truncated upload look like a good archive.
        RAISE EXCEPTION 'ELMOS_CONTENT_OBJECT_NOT_VERIFIED';
    END IF;

    v_days := elmos_effective_retention_days(p_organization_id, p_retention_class);

    INSERT INTO job_artifacts (
        artifact_id, organization_id, job_id, artifact_role, filename,
        content_object_ref, retention_class, expires_at
    ) VALUES (
        p_artifact_id, p_organization_id, p_job_id, p_artifact_role, p_filename,
        p_content_object_id, p_retention_class,
        CASE WHEN p_retention_class = 'LEGAL_HOLD' THEN NULL
             ELSE now() + make_interval(days => v_days) END
    );

    UPDATE content_objects SET last_referenced_at = now()
     WHERE content_object_id = p_content_object_id;

    SELECT coalesce(max(sequence_no), 0) + 1 INTO v_seq
      FROM execution_job_events e WHERE e.job_id = p_job_id;
    INSERT INTO execution_job_events (
        job_event_id, organization_id, job_id, sequence_no, event_type, metadata
    ) VALUES (
        'jev-' || md5(p_job_id || ':' || v_seq), p_organization_id, p_job_id, v_seq,
        'ARTIFACT_PUBLISHED',
        jsonb_build_object('artifact_role', p_artifact_role, 'byte_size', v_object.byte_size)
    );

    RETURN p_artifact_id;
END;
$$;

CREATE FUNCTION elmos_translation_billing_guard() RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE v_enabled boolean;
BEGIN
    SELECT enabled INTO v_enabled FROM wallet_enforcement_settings WHERE singleton FOR SHARE;
    IF v_enabled IS DISTINCT FROM false THEN
        RAISE EXCEPTION 'TRANSLATION_HOSTED_BILLING_CONTRACT_REQUIRED';
    END IF;
    RETURN true;
END $$;
CREATE FUNCTION elmos_translation_enqueue_billing_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    IF NEW.business_line = 'TRANSLATION' AND NEW.job_kind = 'translate-pipeline-v1' THEN
        PERFORM elmos_translation_billing_guard();
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER translation_enqueue_billing_guard BEFORE INSERT OR UPDATE OF business_line, job_kind ON execution_jobs
FOR EACH ROW EXECUTE FUNCTION elmos_translation_enqueue_billing_guard();
REVOKE EXECUTE ON FUNCTION elmos_translation_billing_guard() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION elmos_translation_enqueue_billing_guard() FROM PUBLIC;
