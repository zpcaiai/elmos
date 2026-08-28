-- ELMOS V65.1: authoritative state for the content-addressed store and the action cache.
--
-- The content itself lives in object storage; this schema holds only what must be
-- transactional, queryable, or authorising:
--
--   * the object catalogue, because sensitivity, residency and retention are the
--     inputs to every read decision and to garbage collection, and they must not
--     live inside the immutable content they describe;
--   * regional placement, because "where may these bytes exist" has to be settled
--     before a write and audited after one;
--   * action cache entries, because a cache hit is an authorisation decision and
--     an unlogged one is indistinguishable from not having run the action;
--   * reference roots, because the collector deletes on the strength of this table
--     and an incomplete read here destroys data;
--   * upload sessions, deletion manifests and quarantine events, which are the
--     record of what the store did when something went wrong.
--
-- Digest columns store the lowercase hex only. The algorithm is fixed at sha256 by
-- io.elmos.cas.CasDigest and a second algorithm would be a new column plus a
-- migration, not a silently widened CHECK.

CREATE TABLE cas_object_catalog (
    organization_id varchar(64) NOT NULL,
    digest_hex varchar(64) NOT NULL
        CHECK (digest_hex ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    project_id varchar(64) NOT NULL,
    object_kind varchar(16) NOT NULL
        CHECK (object_kind IN ('BLOB', 'TREE', 'MANIFEST', 'ACTION_RESULT')),
    media_type varchar(128) NOT NULL,
    source_system varchar(64) NOT NULL,
    schema_version varchar(16) NOT NULL,
    sensitivity varchar(24) NOT NULL
        CHECK (sensitivity IN ('PUBLIC_DEPENDENCY', 'PRIVATE_SOURCE', 'GENERATED_OUTPUT', 'EVIDENCE')),
    retention_class varchar(16) NOT NULL
        CHECK (retention_class IN ('EPHEMERAL', 'STANDARD', 'EVIDENCE', 'REGULATORY')),
    data_residency varchar(64) NOT NULL,
    security_tier varchar(16) NOT NULL
        CHECK (security_tier IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')),
    provenance_digest_hex varchar(64)
        CHECK (provenance_digest_hex IS NULL OR provenance_digest_hex ~ '^[0-9a-f]{64}$'),
    labels jsonb NOT NULL DEFAULT '{}'::jsonb,
    legal_hold boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_referenced_at timestamptz,
    -- One row per (tenant, object). Two tenants storing byte-identical content share
    -- the digest by design and must not share the catalogue row: their sensitivity,
    -- residency and legal hold are independent facts about the same bytes.
    PRIMARY KEY (organization_id, digest_hex),
    -- Cross-tenant reuse is only ever considered for public dependency content, and
    -- only when its origin can be attributed. Enforcing it here means a row that
    -- could not pass io.elmos.cas.CasAccessPolicy cannot be written in the first place.
    CONSTRAINT cas_object_catalog_shared_needs_provenance CHECK (
        sensitivity <> 'PUBLIC_DEPENDENCY' OR provenance_digest_hex IS NOT NULL
    )
);

CREATE INDEX cas_object_catalog_collection_idx
    ON cas_object_catalog (organization_id, retention_class, created_at)
    WHERE legal_hold = false;
CREATE INDEX cas_object_catalog_residency_idx
    ON cas_object_catalog (organization_id, data_residency);

CREATE TABLE cas_object_placement (
    organization_id varchar(64) NOT NULL,
    digest_hex varchar(64) NOT NULL
        CHECK (digest_hex ~ '^[0-9a-f]{64}$'),
    region varchar(64) NOT NULL,
    placement_role varchar(16) NOT NULL CHECK (placement_role IN ('PRIMARY', 'REPLICA')),
    storage_tier varchar(8) NOT NULL CHECK (storage_tier IN ('L1', 'L2')),
    placed_at timestamptz NOT NULL DEFAULT now(),
    verified_at timestamptz,
    PRIMARY KEY (organization_id, digest_hex, region),
    FOREIGN KEY (organization_id, digest_hex)
        REFERENCES cas_object_catalog (organization_id, digest_hex) ON DELETE CASCADE
);

-- Exactly one primary per object. Replication without a single authoritative copy is
-- a set of copies nobody can reconcile.
CREATE UNIQUE INDEX cas_object_placement_single_primary_uq
    ON cas_object_placement (organization_id, digest_hex)
    WHERE placement_role = 'PRIMARY';

CREATE TABLE cas_action_cache_entries (
    organization_id varchar(64) NOT NULL,
    action_key_hex varchar(64) NOT NULL
        CHECK (action_key_hex ~ '^[0-9a-f]{64}$'),
    project_id varchar(64) NOT NULL,
    action_id varchar(96) NOT NULL,
    receipt_id varchar(96) NOT NULL,
    attempt integer NOT NULL CHECK (attempt >= 1),
    lease_generation integer NOT NULL CHECK (lease_generation >= 1),
    result_status varchar(16) NOT NULL
        CHECK (result_status IN ('SUCCEEDED', 'FAILED', 'CANCELLED', 'UNKNOWN_RESULT')),
    exit_code integer NOT NULL,
    failure_class varchar(16)
        CHECK (failure_class IS NULL OR failure_class IN (
            'ENVIRONMENT', 'DEPENDENCY', 'CODE', 'POLICY', 'SECURITY',
            'DATA', 'CAPACITY', 'PROVIDER', 'UNKNOWN')),
    validation_status varchar(8) NOT NULL
        CHECK (validation_status IN ('NOT_RUN', 'PASS', 'FAIL', 'PARTIAL')),
    output_manifest_hex varchar(64) NOT NULL
        CHECK (output_manifest_hex ~ '^[0-9a-f]{64}$'),
    output_manifest_bytes bigint NOT NULL CHECK (output_manifest_bytes >= 0),
    provenance_digest_hex varchar(64) NOT NULL
        CHECK (provenance_digest_hex ~ '^[0-9a-f]{64}$'),
    stdout_digest_hex varchar(64)
        CHECK (stdout_digest_hex IS NULL OR stdout_digest_hex ~ '^[0-9a-f]{64}$'),
    stderr_digest_hex varchar(64)
        CHECK (stderr_digest_hex IS NULL OR stderr_digest_hex ~ '^[0-9a-f]{64}$'),
    toolchain_image varchar(512) NOT NULL
        -- ELMOS-CAS-021. A tag is mutable; an entry keyed on one is a stale hit waiting
        -- to happen, so the shape is refused at the column rather than in review.
        CHECK (toolchain_image ~ '@sha256:[0-9a-f]{64}$'),
    producer_permission_scope text[] NOT NULL,
    producer_residency varchar(64) NOT NULL,
    producer_security_tier varchar(16) NOT NULL
        CHECK (producer_security_tier IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')),
    producer_sensitivity varchar(24) NOT NULL
        CHECK (producer_sensitivity IN ('PUBLIC_DEPENDENCY', 'PRIVATE_SOURCE', 'GENERATED_OUTPUT', 'EVIDENCE')),
    risk_tier varchar(16) NOT NULL CHECK (risk_tier IN ('STANDARD', 'HIGH')),
    writer_service_id varchar(96) NOT NULL,
    writer_trust_domain varchar(128) NOT NULL,
    writer_node_id varchar(256) NOT NULL,
    attestation_key_id varchar(96),
    attestation_signature_hex varchar(64)
        CHECK (attestation_signature_hex IS NULL OR attestation_signature_hex ~ '^[0-9a-f]{64}$'),
    wall_seconds numeric(12, 3) NOT NULL DEFAULT 0 CHECK (wall_seconds >= 0),
    cpu_seconds numeric(12, 3) NOT NULL DEFAULT 0 CHECK (cpu_seconds >= 0),
    stored_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    invalidated_at timestamptz,
    invalidation_reason varchar(128),
    PRIMARY KEY (organization_id, action_key_hex),
    -- ELMOS-CAS-027. A high-risk result without a verified signature must not exist as
    -- a row, not merely be refused by the service that usually writes it.
    CONSTRAINT cas_action_cache_high_risk_signed CHECK (
        risk_tier <> 'HIGH' OR (attestation_key_id IS NOT NULL AND attestation_signature_hex IS NOT NULL)
    ),
    CONSTRAINT cas_action_cache_success_has_zero_exit CHECK (
        result_status <> 'SUCCEEDED' OR exit_code = 0
    ),
    CONSTRAINT cas_action_cache_failure_is_classified CHECK (
        result_status <> 'FAILED' OR failure_class IS NOT NULL
    ),
    -- ELMOS-CAS-024. Only failures that are deterministic given the inputs may be
    -- remembered at all, and only with an expiry.
    CONSTRAINT cas_action_cache_failure_ttl CHECK (
        result_status <> 'FAILED' OR (
            failure_class IN ('CODE', 'POLICY', 'SECURITY') AND expires_at IS NOT NULL
        )
    ),
    CONSTRAINT cas_action_cache_expiry_after_store CHECK (
        expires_at IS NULL OR expires_at > stored_at
    ),
    CONSTRAINT cas_action_cache_invalidation_has_reason CHECK (
        (invalidated_at IS NULL) = (invalidation_reason IS NULL)
    )
);

CREATE INDEX cas_action_cache_expiry_idx
    ON cas_action_cache_entries (expires_at)
    WHERE expires_at IS NOT NULL AND invalidated_at IS NULL;
CREATE INDEX cas_action_cache_node_idx
    ON cas_action_cache_entries (organization_id, writer_node_id)
    WHERE invalidated_at IS NULL;
CREATE INDEX cas_action_cache_output_idx
    ON cas_action_cache_entries (organization_id, output_manifest_hex);

CREATE TABLE cas_reference_roots (
    organization_id varchar(64) NOT NULL,
    root_kind varchar(24) NOT NULL
        CHECK (root_kind IN ('SNAPSHOT', 'STAGING', 'WORKFLOW', 'EVIDENCE', 'RELEASE',
                             'LEGAL_HOLD', 'ACTION_CACHE')),
    root_id varchar(128) NOT NULL,
    digest_hex varchar(64) NOT NULL
        CHECK (digest_hex ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    released_at timestamptz,
    PRIMARY KEY (organization_id, root_kind, root_id, digest_hex)
);

CREATE INDEX cas_reference_roots_digest_idx
    ON cas_reference_roots (organization_id, digest_hex)
    WHERE released_at IS NULL;

CREATE TABLE cas_upload_sessions (
    organization_id varchar(64) NOT NULL,
    session_id varchar(128) NOT NULL,
    declared_size_bytes bigint NOT NULL CHECK (declared_size_bytes >= 0),
    chunk_size_bytes integer NOT NULL CHECK (chunk_size_bytes > 0),
    declared_digest_hex varchar(64)
        CHECK (declared_digest_hex IS NULL OR declared_digest_hex ~ '^[0-9a-f]{64}$'),
    session_state varchar(16) NOT NULL
        CHECK (session_state IN ('OPEN', 'COMPLETED', 'ABORTED', 'QUARANTINED', 'EXPIRED')),
    received_chunks integer NOT NULL DEFAULT 0 CHECK (received_chunks >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    deadline_at timestamptz NOT NULL,
    settled_at timestamptz,
    quarantine_id varchar(128),
    PRIMARY KEY (organization_id, session_id),
    CONSTRAINT cas_upload_sessions_deadline_after_creation CHECK (deadline_at > created_at),
    CONSTRAINT cas_upload_sessions_quarantine_state CHECK (
        (session_state = 'QUARANTINED') = (quarantine_id IS NOT NULL)
    )
);

CREATE INDEX cas_upload_sessions_sweep_idx
    ON cas_upload_sessions (deadline_at)
    WHERE session_state = 'OPEN';

-- ELMOS-CAS-036. Append only: a deletion manifest is the record of what the collector
-- removed. A table where that record can be edited afterwards proves nothing.
CREATE TABLE cas_deletion_manifests (
    organization_id varchar(64) NOT NULL,
    batch_id varchar(128) NOT NULL,
    dry_run boolean NOT NULL,
    collected_objects integer NOT NULL CHECK (collected_objects >= 0),
    retained_objects integer NOT NULL CHECK (retained_objects >= 0),
    unresolved_references integer NOT NULL DEFAULT 0 CHECK (unresolved_references >= 0),
    reclaimed_bytes bigint NOT NULL CHECK (reclaimed_bytes >= 0),
    manifest_digest_hex varchar(64) NOT NULL
        CHECK (manifest_digest_hex ~ '^[0-9a-f]{64}$'),
    executed_at timestamptz NOT NULL DEFAULT now(),
    executed_by varchar(96) NOT NULL,
    PRIMARY KEY (organization_id, batch_id),
    CONSTRAINT cas_deletion_manifests_dry_run_reclaims_nothing CHECK (
        dry_run = false OR reclaimed_bytes = 0 OR collected_objects > 0
    )
);

CREATE TABLE cas_quarantine_events (
    organization_id varchar(64) NOT NULL,
    quarantine_id varchar(128) NOT NULL,
    subject_kind varchar(16) NOT NULL CHECK (subject_kind IN ('OBJECT', 'UPLOAD', 'NODE')),
    subject varchar(256) NOT NULL,
    declared_digest_hex varchar(64)
        CHECK (declared_digest_hex IS NULL OR declared_digest_hex ~ '^[0-9a-f]{64}$'),
    observed_digest_hex varchar(64)
        CHECK (observed_digest_hex IS NULL OR observed_digest_hex ~ '^[0-9a-f]{64}$'),
    detail text NOT NULL,
    detected_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, quarantine_id),
    -- A content quarantine without both digests cannot be investigated later.
    CONSTRAINT cas_quarantine_events_content_has_both_digests CHECK (
        subject_kind = 'NODE' OR (declared_digest_hex IS NOT NULL AND observed_digest_hex IS NOT NULL)
    )
);

CREATE TRIGGER cas_deletion_manifests_append_only BEFORE UPDATE OR DELETE ON cas_deletion_manifests
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER cas_quarantine_events_append_only BEFORE UPDATE OR DELETE ON cas_quarantine_events
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

DO $$
DECLARE cas_table text;
BEGIN
    FOREACH cas_table IN ARRAY ARRAY[
        'cas_object_catalog', 'cas_object_placement', 'cas_action_cache_entries',
        'cas_reference_roots', 'cas_upload_sessions', 'cas_deletion_manifests',
        'cas_quarantine_events'
    ] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', cas_table);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', cas_table);
        EXECUTE format(
            'CREATE POLICY cas_b65_tenant_isolation ON public.%I '
            || 'USING (organization_id = current_setting(''app.organization_id'', true)) '
            || 'WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            cas_table);
    END LOOP;
END;
$$;
