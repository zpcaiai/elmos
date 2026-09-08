-- Hosted translation commercial binding and non-resurrectable object reclaim.
-- Both capabilities remain disabled until an operator supplies the exact
-- published price/provider verification facts. Configuration flags alone do
-- not manufacture either authority.

-- -------------------------------------------------------------------------
-- 1. Provider-verified, write-once upload protocol
-- -------------------------------------------------------------------------

ALTER TABLE object_storage_backends
    ADD COLUMN upload_fencing_protocol varchar(48) NOT NULL DEFAULT 'LEGACY_UNFENCED',
    ADD COLUMN upload_fencing_verified_at timestamptz,
    ADD COLUMN upload_fencing_verified_by_actor_id varchar(128),
    ADD CONSTRAINT object_storage_upload_fencing_protocol CHECK (
        upload_fencing_protocol IN (
            'LEGACY_UNFENCED', 'WRITE_ONCE_RECLAIM_FENCE_V1'
        )
    ),
    ADD CONSTRAINT object_storage_upload_fencing_verification CHECK (
        (upload_fencing_protocol = 'LEGACY_UNFENCED'
            AND upload_fencing_verified_at IS NULL
            AND upload_fencing_verified_by_actor_id IS NULL)
        OR
        (upload_fencing_protocol = 'WRITE_ONCE_RECLAIM_FENCE_V1'
            AND backend_kind IN ('S3', 'MINIO', 'OSS')
            AND upload_fencing_verified_at IS NOT NULL
            AND upload_fencing_verified_by_actor_id IS NOT NULL)
    );

COMMENT ON COLUMN object_storage_backends.upload_fencing_protocol IS
    'Operator-verified provider contract. WRITE_ONCE_RECLAIM_FENCE_V1 means signed create-only PUT plus atomic in-place reclaim fence on a non-versioned bucket. It is not inferred from backend kind.';

ALTER TABLE content_objects
    ADD COLUMN upload_protocol varchar(48) NOT NULL DEFAULT 'LEGACY_UNFENCED',
    ADD CONSTRAINT content_objects_upload_protocol CHECK (
        upload_protocol IN (
            'LEGACY_UNFENCED', 'WRITE_ONCE_RECLAIM_FENCE_V1'
        )
    ),
    ADD CONSTRAINT content_objects_purge_pending_requires_fence CHECK (
        object_state <> 'PURGE_PENDING'
        OR upload_protocol = 'WRITE_ONCE_RECLAIM_FENCE_V1'
    );

COMMENT ON COLUMN content_objects.upload_protocol IS
    'Immutable upload-generation safety contract captured when the PUT ticket is created. Legacy objects are never promoted merely because a backend is later reconfigured.';

ALTER TABLE artifact.content_objects
    ADD COLUMN upload_protocol varchar(48) NOT NULL DEFAULT 'LEGACY_UNFENCED',
    ADD CONSTRAINT production_content_objects_upload_protocol CHECK (
        upload_protocol IN (
            'LEGACY_UNFENCED', 'WRITE_ONCE_RECLAIM_FENCE_V1'
        )
    );

-- V89 could only be reached by direct privileged SQL because the Java host was
-- startup-blocked. Refuse to reinterpret unresolved legacy work as fenced.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM object_gc_host_items
         WHERE item_state <> 'CONFIRMED'
    ) THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_LEGACY_RECONCILIATION_REQUIRED';
    END IF;
END $$;

ALTER TABLE object_gc_host_items
    ADD COLUMN provider_request_id varchar(240),
    ADD COLUMN reclaim_fence_sha256 varchar(64),
    ADD COLUMN reclaim_fence_bytes bigint,
    ADD COLUMN reclaim_protocol varchar(48),
    ADD CONSTRAINT object_gc_host_receipt_shape CHECK (
        item_state <> 'CONFIRMED'
        OR reclaim_protocol IS NULL
        OR (
            reclaim_protocol = 'WRITE_ONCE_RECLAIM_FENCE_V1'
            AND provider_request_id IS NOT NULL
            AND reclaim_fence_sha256 ~ '^[0-9a-f]{64}$'
            AND reclaim_fence_bytes > 0
        )
    );

-- Artifact metadata may expire for every protocol, but only objects whose
-- create-only condition was signature-bound can become physical candidates.
CREATE OR REPLACE FUNCTION elmos_expire_artifacts(
    p_gc_run_id varchar, p_batch_limit integer
) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_expired integer := 0;
    v_held integer := 0;
    v_object varchar;
    v_org text := nullif(current_setting('app.organization_id', true), '');
BEGIN
    IF row_security_active('content_objects') AND v_org IS NULL THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_TENANT_CONTEXT_REQUIRED';
    END IF;
    IF p_batch_limit IS NULL OR p_batch_limit < 1 OR p_batch_limit > 5000 THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_BATCH_INVALID';
    END IF;
    INSERT INTO object_gc_runs(gc_run_id) VALUES(p_gc_run_id)
        ON CONFLICT(gc_run_id) DO NOTHING;
    SELECT count(*) INTO v_held FROM job_artifacts
     WHERE deleted_at IS NULL AND legal_hold
       AND (v_org IS NULL OR organization_id = v_org);
    WITH due AS (
        SELECT artifact_id FROM job_artifacts
         WHERE deleted_at IS NULL AND NOT legal_hold
           AND (v_org IS NULL OR organization_id = v_org)
           AND expires_at IS NOT NULL AND expires_at < now()
         ORDER BY expires_at LIMIT p_batch_limit FOR UPDATE SKIP LOCKED
    ), marked AS (
        UPDATE job_artifacts artifact
           SET deleted_at = now(), deletion_reason = 'RETENTION_EXPIRED'
          FROM due
         WHERE artifact.artifact_id = due.artifact_id
           AND (v_org IS NULL OR artifact.organization_id = v_org)
        RETURNING 1
    ) SELECT count(*) INTO v_expired FROM marked;
    FOR v_object IN
        SELECT object.content_object_id FROM content_objects object
         WHERE object.object_state = 'AVAILABLE'
           AND object.upload_protocol = 'WRITE_ONCE_RECLAIM_FENCE_V1'
           AND (v_org IS NULL OR object.organization_id = v_org)
           AND NOT EXISTS (
                SELECT 1 FROM job_artifacts artifact
                 WHERE artifact.content_object_ref = object.content_object_id
                   AND artifact.organization_id = object.organization_id
                   AND artifact.deleted_at IS NULL)
           AND NOT elmos_execution_input_retained(object.content_object_id)
         ORDER BY object.created_at, object.content_object_id
         LIMIT p_batch_limit FOR UPDATE SKIP LOCKED
    LOOP
        UPDATE content_objects object SET object_state = 'PURGE_PENDING'
         WHERE object.content_object_id = v_object
           AND object.object_state = 'AVAILABLE'
           AND object.upload_protocol = 'WRITE_ONCE_RECLAIM_FENCE_V1'
           AND (v_org IS NULL OR object.organization_id = v_org)
           AND NOT EXISTS (
                SELECT 1 FROM job_artifacts artifact
                 WHERE artifact.content_object_ref = object.content_object_id
                   AND artifact.organization_id = object.organization_id
                   AND artifact.deleted_at IS NULL)
           AND NOT elmos_execution_input_retained(object.content_object_id);
    END LOOP;
    UPDATE object_gc_runs
       SET expired_count = v_expired, held_count = v_held
     WHERE gc_run_id = p_gc_run_id;
    RETURN v_expired;
END $$;

DROP FUNCTION elmos_object_gc_host_confirm(
    varchar, varchar, varchar, varchar, varchar, varchar
);

CREATE FUNCTION elmos_object_gc_host_confirm(
    p_run varchar,
    p_object varchar,
    p_org varchar,
    p_sha varchar,
    p_backend varchar,
    p_key varchar,
    p_provider_request varchar,
    p_fence_sha varchar,
    p_fence_bytes bigint
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_previous text := coalesce(
        current_setting('app.organization_id', true), '');
    v_item public.object_gc_host_items%ROWTYPE;
    v_state varchar;
    v_protocol varchar;
    v_confirmed integer;
BEGIN
    IF p_provider_request IS NULL
       OR length(p_provider_request) NOT BETWEEN 1 AND 240
       OR p_fence_sha IS DISTINCT FROM
            'd835c506a9a8f23ea6cacb3272645449d3063d9e11720b92adff6fac0dd4739e'
       OR p_fence_bytes IS DISTINCT FROM 25 THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_HOST_RECEIPT_INVALID';
    END IF;
    PERFORM 1 FROM public.object_gc_host_runs run
     WHERE run.run_id = p_run FOR UPDATE;
    SELECT * INTO v_item FROM public.object_gc_host_items item
     WHERE item.run_id = p_run AND item.content_object_id = p_object;
    IF NOT FOUND
       OR v_item.organization_id IS DISTINCT FROM p_org
       OR v_item.content_sha256 IS DISTINCT FROM p_sha
       OR v_item.backend_id IS DISTINCT FROM p_backend
       OR v_item.storage_key IS DISTINCT FROM p_key THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_HOST_BINDING_MISMATCH';
    END IF;
    PERFORM set_config('app.organization_id', v_item.organization_id, true);
    SELECT object.object_state, object.upload_protocol
      INTO v_state, v_protocol
      FROM public.content_objects object
     WHERE object.organization_id = v_item.organization_id
       AND object.content_object_id = v_item.content_object_id
       AND object.content_sha256 = v_item.content_sha256
       AND object.backend_id = v_item.backend_id
       AND object.storage_key = v_item.storage_key
     FOR UPDATE;
    IF NOT FOUND
       OR v_state NOT IN ('PURGE_PENDING', 'PURGED')
       OR v_protocol <> 'WRITE_ONCE_RECLAIM_FENCE_V1' THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_HOST_OBJECT_CHANGED';
    END IF;
    IF v_state = 'PURGE_PENDING' THEN
        IF NOT public.elmos_confirm_object_purged(
                v_item.organization_id, v_item.content_object_id) THEN
            RAISE EXCEPTION 'ELMOS_OBJECT_GC_HOST_CONFIRM_FAILED';
        END IF;
    END IF;
    UPDATE public.object_gc_host_items
       SET item_state = 'CONFIRMED',
           provider_request_id = coalesce(provider_request_id,
                                          p_provider_request),
           reclaim_fence_sha256 = coalesce(reclaim_fence_sha256,
                                           p_fence_sha),
           reclaim_fence_bytes = coalesce(reclaim_fence_bytes,
                                          p_fence_bytes),
           reclaim_protocol = coalesce(reclaim_protocol,
                                       'WRITE_ONCE_RECLAIM_FENCE_V1'),
           confirmed_at = coalesce(confirmed_at, clock_timestamp())
     WHERE run_id = p_run AND content_object_id = p_object;
    IF NOT EXISTS (
        SELECT 1 FROM public.object_gc_host_items
         WHERE run_id = p_run AND item_state <> 'CONFIRMED'
    ) THEN
        UPDATE public.object_gc_host_runs
           SET run_state = 'COMPLETED', finished_at = clock_timestamp()
         WHERE object_gc_host_runs.run_id = p_run
           AND run_state = 'UNRESOLVED';
        IF FOUND THEN
            SELECT count(*) INTO v_confirmed
              FROM public.object_gc_host_items WHERE run_id = p_run;
            PERFORM public.elmos_finish_object_gc(
                p_run, v_confirmed, 0);
        END IF;
    END IF;
    PERFORM set_config('app.organization_id', v_previous, true);
    RETURN true;
END $$;

REVOKE ALL ON FUNCTION elmos_object_gc_host_confirm(
    varchar, varchar, varchar, varchar, varchar, varchar,
    varchar, varchar, bigint
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION elmos_object_gc_host_confirm(
    varchar, varchar, varchar, varchar, varchar, varchar,
    varchar, varchar, bigint
) TO elmos_object_gc_host;

-- -------------------------------------------------------------------------
-- 2. Hosted translation billing contract
-- -------------------------------------------------------------------------

-- A job-backed hold is owned by the execution lifecycle. It must resolve only
-- through the terminal-state settlement outbox, including after an UNKNOWN
-- settlement result. Releasing such a hold on the generic reservation TTL
-- would silently turn a settlement outage into free work. The TTL remains
-- available for reservations that never acquired an execution job.
CREATE OR REPLACE FUNCTION elmos_wallet_expire_reservations(
    p_organization_id varchar,
    p_limit integer DEFAULT 500
) RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_previous text;
    v_row record;
    v_count integer := 0;
BEGIN
    v_previous := elmos_wallet_bind_tenant(p_organization_id);
    FOR v_row IN
        SELECT reservation.reservation_id, reservation.amount_minor
          FROM wallet_reservations reservation
         WHERE reservation.organization_id = p_organization_id
           AND reservation.status = 'HELD'
           AND reservation.expires_at <= now()
           AND NOT EXISTS (
                SELECT 1 FROM execution_jobs job
                 WHERE job.organization_id = reservation.organization_id
                   AND job.job_id = reservation.job_id)
           AND NOT EXISTS (
                SELECT 1 FROM wallet_settlement_outbox settlement
                 WHERE settlement.organization_id = reservation.organization_id
                   AND settlement.reservation_id = reservation.reservation_id
                   AND settlement.resolved_at IS NULL)
         ORDER BY reservation.expires_at
         LIMIT greatest(coalesce(p_limit, 500), 1)
         FOR UPDATE OF reservation SKIP LOCKED
    LOOP
        PERFORM set_config('app.wallet_posting', 'on', true);
        UPDATE wallet_accounts
           SET reserved_minor = reserved_minor - v_row.amount_minor
         WHERE organization_id = p_organization_id;
        PERFORM set_config('app.wallet_posting', 'off', true);

        UPDATE wallet_reservations
           SET status = 'EXPIRED', resolved_at = now(),
               resolution_code = 'TTL_EXPIRED_NO_EXECUTION_JOB'
         WHERE reservation_id = v_row.reservation_id;

        v_count := v_count + 1;
    END LOOP;
    PERFORM set_config('app.organization_id', v_previous, true);
    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION elmos_wallet_expire_reservations(varchar, integer) IS
    'Expires orphan holds only. Job-backed holds remain reserved until the terminal settlement outbox is durably reconciled; UNKNOWN settlement never becomes a free release by TTL.';

-- A deterministic draft records the intended mechanics without publishing a
-- customer price. Finance must publish an exact version and point the switch at
-- it; the wildcard fallback is deliberately insufficient for hosted execution.
INSERT INTO wallet_price_book(
    catalog_version, business_line, job_kind, currency,
    reserve_minor, unit, unit_price_minor, min_charge_minor,
    effective_from, source_ref, status
) VALUES (
    '2026-09-08.translation-hosted-v1',
    'TRANSLATION', 'translate-pipeline-v1', 'CNY',
    2000, 'WALL_SECOND', 2, 100,
    '2026-09-08T00:00:00Z',
    'modules/persistence/src/main/resources/db/migration/V92__hosted_billing_and_object_reclaim_fencing.sql',
    'DRAFT'
);

CREATE FUNCTION elmos_translation_billing_guard(
    p_require_enabled boolean
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
DECLARE
    v_enabled boolean;
    v_catalog varchar(64);
    v_prices integer;
BEGIN
    SELECT enabled, catalog_version INTO v_enabled, v_catalog
      FROM wallet_enforcement_settings WHERE singleton FOR SHARE;
    IF NOT FOUND OR v_enabled IS NULL THEN
        RAISE EXCEPTION 'TRANSLATION_HOSTED_BILLING_STATE_UNKNOWN';
    END IF;
    IF p_require_enabled AND NOT v_enabled THEN
        RAISE EXCEPTION 'TRANSLATION_HOSTED_BILLING_NOT_ENABLED';
    END IF;
    IF NOT v_enabled THEN
        RETURN true;
    END IF;
    SELECT count(*) INTO v_prices FROM wallet_price_book price
     WHERE price.catalog_version = v_catalog
       AND price.business_line = 'TRANSLATION'
       AND price.job_kind = 'translate-pipeline-v1'
       AND price.currency = 'CNY'
       AND price.unit = 'WALL_SECOND'
       AND price.reserve_minor > 0
       AND price.unit_price_minor >= 0
       AND price.min_charge_minor >= 0
       AND price.min_charge_minor <= price.reserve_minor
       AND price.status = 'PUBLISHED'
       AND price.effective_from <= clock_timestamp()
       AND (price.effective_until IS NULL
            OR price.effective_until > clock_timestamp());
    IF v_prices <> 1 THEN
        RAISE EXCEPTION 'TRANSLATION_HOSTED_BILLING_CONTRACT_REQUIRED';
    END IF;
    RETURN true;
END $$;

CREATE OR REPLACE FUNCTION elmos_translation_billing_guard()
RETURNS boolean
LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT public.elmos_translation_billing_guard(false);
$$;

REVOKE ALL ON FUNCTION elmos_translation_billing_guard(boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_translation_billing_guard() FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles
         WHERE rolname = 'elmos_translation_input_runtime'
    ) THEN
        GRANT EXECUTE ON FUNCTION elmos_translation_billing_guard(boolean)
            TO elmos_translation_input_runtime;
        GRANT EXECUTE ON FUNCTION elmos_translation_billing_guard()
            TO elmos_translation_input_runtime;
    END IF;
END $$;
