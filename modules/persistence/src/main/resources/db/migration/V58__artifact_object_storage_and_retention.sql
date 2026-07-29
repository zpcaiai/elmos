-- ELMOS V58: content-addressed artifact storage, download grants and retention.
--
-- Why this migration exists
-- -------------------------
-- Generation ZIPs, evidence packs and build logs are written to the local disk
-- of whichever process produced them. deploy/compose already starts MinIO, but
-- nothing is wired to it: the control plane has no object-storage configuration
-- and no S3 client. With more than one replica a download can therefore 404,
-- and a full disk takes the whole product down.
--
-- V54 keeps the existing content-addressing semantics (SHA-256 identity, the
-- browser recomputes the digest before accepting a download) and moves the bytes
-- to an object store behind a fail-closed backend registry.
--
-- Deliberate decision: content objects are TENANT SCOPED, not globally
-- deduplicated. Global dedup by digest would turn the artifact store into a
-- cross-tenant existence oracle - tenant B could learn that tenant A already
-- holds a byte-identical file. The storage saving is not worth that leak.

-- ---------------------------------------------------------------------------
-- 1. Backend registry - fail closed
-- ---------------------------------------------------------------------------

CREATE TABLE object_storage_backends (
    backend_id varchar(64) PRIMARY KEY,
    backend_kind varchar(24) NOT NULL,
    endpoint varchar(512),
    region varchar(64),
    bucket varchar(128),
    path_style boolean NOT NULL DEFAULT false,
    server_side_encryption varchar(24) NOT NULL DEFAULT 'NONE',
    cmk_reference varchar(160),
    credential_reference varchar(160),
    backend_state varchar(24) NOT NULL DEFAULT 'NOT_CONFIGURED',
    data_region varchar(64) NOT NULL DEFAULT 'cn-north',
    max_object_bytes bigint NOT NULL DEFAULT 5368709120,
    verified_at timestamptz,
    verified_by_actor_id varchar(128),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT object_storage_kind CHECK (backend_kind IN ('S3', 'OSS', 'MINIO', 'LOCAL_FS')),
    CONSTRAINT object_storage_state CHECK (
        backend_state IN ('NOT_CONFIGURED', 'ACTIVE', 'READ_ONLY', 'DISABLED')
    ),
    CONSTRAINT object_storage_sse CHECK (
        server_side_encryption IN ('NONE', 'SSE_S3', 'SSE_KMS', 'SSE_C')
    ),
    -- A backend cannot serve production traffic until it is verified, bucketed,
    -- credential-referenced and encrypting. LOCAL_FS can never be ACTIVE.
    CONSTRAINT object_storage_active_shape CHECK (
        backend_state <> 'ACTIVE' OR (
            backend_kind <> 'LOCAL_FS'
            AND endpoint IS NOT NULL
            AND bucket IS NOT NULL
            AND credential_reference IS NOT NULL
            AND server_side_encryption IN ('SSE_KMS', 'SSE_S3')
            AND (server_side_encryption <> 'SSE_KMS' OR cmk_reference IS NOT NULL)
            AND verified_at IS NOT NULL
            AND verified_by_actor_id IS NOT NULL
        )
    ),
    CONSTRAINT object_storage_max_object CHECK (max_object_bytes BETWEEN 1048576 AND 549755813888)
);

INSERT INTO object_storage_backends (backend_id, backend_kind, backend_state, data_region)
VALUES ('primary', 'S3', 'NOT_CONFIGURED', 'cn-north');

COMMENT ON TABLE object_storage_backends IS
    'Fail-closed registry. The shipped row is NOT_CONFIGURED on purpose: until an operator supplies bucket, credential reference and server-side encryption, artifact publication is refused rather than silently falling back to local disk.';
COMMENT ON COLUMN object_storage_backends.credential_reference IS
    'Secret reference resolved through the V9 secret lease authority. Inline access keys are prohibited.';

-- ---------------------------------------------------------------------------
-- 2. Content objects - tenant scoped
-- ---------------------------------------------------------------------------

CREATE TABLE content_objects (
    content_object_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    content_sha256 varchar(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    byte_size bigint NOT NULL,
    media_type varchar(128) NOT NULL DEFAULT 'application/octet-stream',
    backend_id varchar(64) NOT NULL REFERENCES object_storage_backends(backend_id),
    storage_key varchar(512) NOT NULL,
    encryption_context_ref varchar(160),
    object_state varchar(24) NOT NULL DEFAULT 'PENDING_UPLOAD',
    uploaded_at timestamptz,
    verified_at timestamptz,
    last_referenced_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, content_sha256),
    CONSTRAINT content_objects_state CHECK (
        object_state IN ('PENDING_UPLOAD', 'AVAILABLE', 'QUARANTINED', 'PURGED')
    ),
    CONSTRAINT content_objects_size CHECK (byte_size >= 0 AND byte_size <= 549755813888),
    CONSTRAINT content_objects_available_shape CHECK (
        object_state <> 'AVAILABLE' OR (uploaded_at IS NOT NULL AND verified_at IS NOT NULL AND byte_size > 0)
    )
);

CREATE INDEX content_objects_org_state_idx ON content_objects (organization_id, object_state);
CREATE INDEX content_objects_backend_idx ON content_objects (backend_id, object_state);

COMMENT ON COLUMN content_objects.verified_at IS
    'Set only after the server has recomputed SHA-256 over the stored bytes. A client-declared digest is never trusted; an unverified object stays PENDING_UPLOAD and is not downloadable.';
COMMENT ON COLUMN content_objects.storage_key IS
    'Object key. It embeds the organization prefix so a bucket policy can enforce tenant separation independently of the application.';

-- ---------------------------------------------------------------------------
-- 3. Artifacts published by a job
-- ---------------------------------------------------------------------------

CREATE TABLE job_artifacts (
    artifact_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    job_id varchar(96) NOT NULL REFERENCES execution_jobs(job_id),
    artifact_role varchar(32) NOT NULL,
    filename varchar(255) NOT NULL,
    content_object_ref varchar(96) NOT NULL REFERENCES content_objects(content_object_id),
    retention_class varchar(24) NOT NULL DEFAULT 'STANDARD',
    legal_hold boolean NOT NULL DEFAULT false,
    published_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    deleted_at timestamptz,
    deletion_reason varchar(64),
    UNIQUE (job_id, artifact_role, filename),
    CONSTRAINT job_artifacts_role CHECK (
        artifact_role IN (
            'PROJECT_ARCHIVE', 'EVIDENCE_PACK', 'BUILD_LOG', 'TEST_REPORT',
            'SBOM', 'DIFF', 'PULL_REQUEST_BODY', 'GATE_REPORT'
        )
    ),
    CONSTRAINT job_artifacts_retention CHECK (
        retention_class IN ('EPHEMERAL', 'STANDARD', 'EVIDENCE', 'LEGAL_HOLD')
    ),
    CONSTRAINT job_artifacts_deletion_shape CHECK (
        deleted_at IS NULL OR deletion_reason IS NOT NULL
    ),
    -- Legal hold overrides every retention rule, including an expiry that was
    -- already set before the hold was placed.
    CONSTRAINT job_artifacts_legal_hold_not_expiring CHECK (NOT legal_hold OR expires_at IS NULL)
);

CREATE INDEX job_artifacts_job_idx ON job_artifacts (job_id, artifact_role);
CREATE INDEX job_artifacts_org_published_idx ON job_artifacts (organization_id, published_at DESC);
CREATE INDEX job_artifacts_expiry_idx ON job_artifacts (expires_at)
    WHERE deleted_at IS NULL AND expires_at IS NOT NULL AND NOT legal_hold;

-- ---------------------------------------------------------------------------
-- 4. Download grants - the audit trail for every presigned URL
-- ---------------------------------------------------------------------------

CREATE TABLE artifact_download_grants (
    grant_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    artifact_id varchar(96) NOT NULL REFERENCES job_artifacts(artifact_id),
    actor_id varchar(128) NOT NULL,
    issued_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    max_downloads smallint NOT NULL DEFAULT 3,
    download_count smallint NOT NULL DEFAULT 0,
    first_downloaded_at timestamptz,
    last_downloaded_at timestamptz,
    revoked_at timestamptz,
    revocation_code varchar(96),
    CONSTRAINT artifact_grant_expiry CHECK (expires_at > issued_at),
    -- A presigned URL is a bearer credential. Fifteen minutes is the ceiling.
    CONSTRAINT artifact_grant_max_ttl CHECK (expires_at <= issued_at + interval '15 minutes'),
    CONSTRAINT artifact_grant_downloads CHECK (
        max_downloads BETWEEN 1 AND 10 AND download_count >= 0 AND download_count <= max_downloads
    )
);

CREATE INDEX artifact_download_grants_artifact_idx
    ON artifact_download_grants (artifact_id, issued_at DESC);
CREATE INDEX artifact_download_grants_org_idx
    ON artifact_download_grants (organization_id, issued_at DESC);

COMMENT ON TABLE artifact_download_grants IS
    'One row per issued presigned URL. The URL and its signature are never stored - only who asked, for what, when it expires and how many times it was used. This is what makes "who downloaded the customer archive" answerable.';

-- ---------------------------------------------------------------------------
-- 5. Retention policy and garbage collection evidence
-- ---------------------------------------------------------------------------

CREATE TABLE object_retention_policies (
    retention_policy_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    retention_class varchar(24) NOT NULL,
    retain_days integer NOT NULL,
    updated_by_actor_id varchar(128) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, retention_class),
    CONSTRAINT object_retention_class CHECK (
        retention_class IN ('EPHEMERAL', 'STANDARD', 'EVIDENCE')
    ),
    CONSTRAINT object_retention_days CHECK (retain_days BETWEEN 1 AND 3650)
);

COMMENT ON TABLE object_retention_policies IS
    'Per-tenant override. When absent the effective retention comes from the CNY plan catalog column self_service_pricing_plan_versions.artifact_retention_days, so a plan change automatically changes retention without a second source of truth.';

CREATE TABLE object_gc_runs (
    gc_run_id varchar(96) PRIMARY KEY,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    scanned_count integer NOT NULL DEFAULT 0,
    expired_count integer NOT NULL DEFAULT 0,
    purged_count integer NOT NULL DEFAULT 0,
    held_count integer NOT NULL DEFAULT 0,
    failure_code varchar(96),
    run_state varchar(24) NOT NULL DEFAULT 'RUNNING',
    CONSTRAINT object_gc_run_state CHECK (run_state IN ('RUNNING', 'COMPLETED', 'FAILED'))
);

CREATE TRIGGER object_gc_runs_append_only
BEFORE DELETE ON object_gc_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

-- ---------------------------------------------------------------------------
-- 6. Effective retention and publication
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION elmos_effective_retention_days(
    p_organization_id varchar,
    p_retention_class varchar
) RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT coalesce(
        (SELECT retain_days FROM object_retention_policies
          WHERE organization_id = p_organization_id AND retention_class = p_retention_class),
        (SELECT p.artifact_retention_days
           FROM subscriptions s
           JOIN self_service_pricing_plan_versions p
             ON p.catalog_version = s.catalog_version AND p.plan_id = s.plan_id
          WHERE s.organization_id = p_organization_id
            AND s.plan_id IS NOT NULL
            AND s.status IN ('ACTIVE', 'TRIALING')
            AND s.current_period_end > now()
          ORDER BY p.artifact_retention_days DESC
          LIMIT 1),
        7);
$$;

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
     WHERE content_object_id = p_content_object_id AND organization_id = p_organization_id;
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

CREATE OR REPLACE FUNCTION elmos_issue_download_grant(
    p_grant_id varchar,
    p_organization_id varchar,
    p_artifact_id varchar,
    p_actor_id varchar,
    p_ttl_seconds integer
) RETURNS TABLE (
    backend_id varchar,
    storage_key varchar,
    content_sha256 varchar,
    byte_size bigint,
    media_type varchar,
    filename varchar,
    expires_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_artifact job_artifacts%ROWTYPE;
    v_object content_objects%ROWTYPE;
    v_expires timestamptz;
BEGIN
    IF p_ttl_seconds IS NULL OR p_ttl_seconds < 30 OR p_ttl_seconds > 900 THEN
        RAISE EXCEPTION 'ELMOS_DOWNLOAD_GRANT_TTL_INVALID';
    END IF;

    SELECT * INTO v_artifact FROM job_artifacts
     WHERE artifact_id = p_artifact_id AND organization_id = p_organization_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'ELMOS_ARTIFACT_UNKNOWN'; END IF;
    IF v_artifact.deleted_at IS NOT NULL THEN RAISE EXCEPTION 'ELMOS_ARTIFACT_DELETED'; END IF;

    SELECT * INTO v_object FROM content_objects
     WHERE content_object_id = v_artifact.content_object_ref;
    IF v_object.object_state <> 'AVAILABLE' THEN RAISE EXCEPTION 'ELMOS_ARTIFACT_NOT_AVAILABLE'; END IF;

    v_expires := now() + make_interval(secs => p_ttl_seconds);

    INSERT INTO artifact_download_grants (
        grant_id, organization_id, artifact_id, actor_id, expires_at
    ) VALUES (
        p_grant_id, p_organization_id, p_artifact_id, p_actor_id, v_expires
    );

    backend_id := v_object.backend_id;
    storage_key := v_object.storage_key;
    content_sha256 := v_object.content_sha256;
    byte_size := v_object.byte_size;
    media_type := v_object.media_type;
    filename := v_artifact.filename;
    expires_at := v_expires;
    RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION elmos_expire_artifacts(p_gc_run_id varchar, p_batch_limit integer)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_expired integer := 0;
    v_held integer := 0;
BEGIN
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
         LIMIT coalesce(p_batch_limit, 500)
    ), marked AS (
        UPDATE job_artifacts a
           SET deleted_at = now(), deletion_reason = 'RETENTION_EXPIRED'
          FROM due
         WHERE a.artifact_id = due.artifact_id
        RETURNING 1
    )
    SELECT count(*) INTO v_expired FROM marked;

    -- An object becomes purgeable only once no live artifact references it.
    UPDATE content_objects o
       SET object_state = 'PURGED'
     WHERE o.object_state = 'AVAILABLE'
       AND NOT EXISTS (
            SELECT 1 FROM job_artifacts a
             WHERE a.content_object_ref = o.content_object_id AND a.deleted_at IS NULL
       );

    UPDATE object_gc_runs
       SET finished_at = now(), run_state = 'COMPLETED',
           expired_count = v_expired, held_count = v_held
     WHERE gc_run_id = p_gc_run_id;

    RETURN v_expired;
END;
$$;

-- ---------------------------------------------------------------------------
-- 7. Row level security and grants
-- ---------------------------------------------------------------------------

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'content_objects',
        'job_artifacts',
        'artifact_download_grants',
        'object_retention_policies'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name
        );
    END LOOP;
END;
$$;

REVOKE ALL ON object_storage_backends FROM PUBLIC;
REVOKE ALL ON object_gc_runs FROM PUBLIC;

DO $$
DECLARE v_function record;
BEGIN
    FOR v_function IN
        SELECT p.oid::regprocedure AS signature
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND p.proname IN (
               'elmos_effective_retention_days',
               'elmos_publish_job_artifact',
               'elmos_issue_download_grant',
               'elmos_expire_artifacts'
           )
    LOOP
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', v_function.signature);
    END LOOP;
END;
$$;
