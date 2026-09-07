-- Snapshot rows and their CAS reachability roots cross two durable systems.  This table records
-- the exact root generation before a snapshot insert/archive transaction and advances phase in
-- that same transaction, so a lost acknowledgement never requires guessing whether release is
-- safe.  It is intentionally not an outbox table: message publication is unrelated to GC root
-- completion and must never hide an unresolved reconciliation.

ALTER TABLE repositories
    ADD CONSTRAINT repositories_organization_repository_uq
    UNIQUE (organization_id, repository_id);

ALTER TABLE repository_snapshots
    ADD CONSTRAINT repository_snapshots_organization_repository_snapshot_uq
    UNIQUE (organization_id, repository_id, snapshot_id);

-- A CHECK constraint cannot contain a subquery directly.  Keep the validator immutable and
-- schema-qualified so malformed collector generations cannot poison an entire reconciliation
-- batch during JSON deserialization.
CREATE FUNCTION public.elmos_valid_snapshot_retention_generations(generations jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT jsonb_typeof(generations) = 'object'
       AND NOT EXISTS (
            SELECT 1
              FROM jsonb_each(generations) AS entry(generation_name, generation_value)
             WHERE generation_name !~ '^[a-z][a-z0-9.-]{0,63}$'
                OR CASE
                       WHEN jsonb_typeof(generation_value) = 'number'
                        AND generation_value::text ~ '^(0|[1-9][0-9]{0,18})$'
                       THEN generation_value::text::numeric > 9223372036854775807
                       ELSE true
                   END
       )
$$;

CREATE TABLE snapshot_root_reconciliations (
    organization_id varchar(64) NOT NULL REFERENCES organizations(organization_id),
    repository_id varchar(64) NOT NULL,
    attempt_id varchar(64) NOT NULL
        CHECK (attempt_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'),
    logical_operation_id varchar(64) NOT NULL
        CHECK (logical_operation_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$'),
    snapshot_id varchar(128) NOT NULL
        CHECK (snapshot_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    reconciliation_kind varchar(32) NOT NULL
        CHECK (reconciliation_kind IN ('CAPTURE_COMMIT', 'ARCHIVE_RELEASE')),
    phase varchar(32) NOT NULL
        CHECK (phase IN ('PENDING', 'DATABASE_COMMITTED', 'COMMIT_FAILED', 'RESOLVED')),
    durable_snapshot_id varchar(64),
    reconciliation_payload jsonb NOT NULL
        CHECK (jsonb_typeof(reconciliation_payload) = 'object'),
    retention_generations jsonb NOT NULL
        CHECK (public.elmos_valid_snapshot_retention_generations(retention_generations)),
    recorded_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    resolved_at timestamptz,
    PRIMARY KEY (organization_id, attempt_id),
    UNIQUE (organization_id, logical_operation_id, attempt_id),
    FOREIGN KEY (organization_id, repository_id)
        REFERENCES repositories(organization_id, repository_id),
    FOREIGN KEY (organization_id, repository_id, durable_snapshot_id)
        REFERENCES repository_snapshots(organization_id, repository_id, snapshot_id),
    CONSTRAINT snapshot_root_reconciliation_payload_required_keys CHECK (
        reconciliation_payload ?& ARRAY[
            'reconciliationId', 'logicalOperationId', 'kind', 'phase',
            'snapshot', 'retention', 'durableSnapshotId', 'recordedAt'
        ]
        AND jsonb_typeof(reconciliation_payload -> 'snapshot') = 'object'
        AND (reconciliation_payload -> 'snapshot') ?& ARRAY[
            'snapshotId', 'organizationId', 'repositoryId', 'requestedRef',
            'resolvedCommitSha', 'treeSha', 'archiveArtifactRef',
            'archiveSha256', 'archiveSize', 'manifestArtifactRef',
            'manifestSha256', 'snapshotSchemaVersion', 'status', 'capturedAt'
        ]
        AND jsonb_typeof(reconciliation_payload -> 'retention') = 'object'
        AND (reconciliation_payload -> 'retention') ?& ARRAY[
            'snapshotId', 'generations'
        ]
    ),
    CONSTRAINT snapshot_root_reconciliation_payload_field_types CHECK (
        jsonb_typeof(reconciliation_payload -> 'reconciliationId') = 'string'
        AND jsonb_typeof(reconciliation_payload -> 'logicalOperationId') = 'string'
        AND jsonb_typeof(reconciliation_payload -> 'kind') = 'string'
        AND jsonb_typeof(reconciliation_payload -> 'phase') = 'string'
        AND jsonb_typeof(reconciliation_payload -> 'recordedAt') = 'string'
        AND jsonb_typeof(reconciliation_payload -> 'durableSnapshotId') IN ('null', 'string')
        AND jsonb_typeof(reconciliation_payload #> '{snapshot,snapshotId}') = 'string'
        AND jsonb_typeof(reconciliation_payload #> '{snapshot,organizationId}') = 'string'
        AND jsonb_typeof(reconciliation_payload #> '{snapshot,repositoryId}') = 'string'
        AND jsonb_typeof(reconciliation_payload #> '{snapshot,requestedRef}') = 'string'
        AND length(reconciliation_payload #>> '{snapshot,requestedRef}') > 0
        AND jsonb_typeof(reconciliation_payload #> '{snapshot,resolvedCommitSha}') = 'string'
        AND (reconciliation_payload #>> '{snapshot,resolvedCommitSha}')
            ~ '^[0-9a-f]{40}$'
        AND jsonb_typeof(reconciliation_payload #> '{snapshot,treeSha}') IN ('null', 'string')
        AND (
            jsonb_typeof(reconciliation_payload #> '{snapshot,treeSha}') = 'null'
            OR (reconciliation_payload #>> '{snapshot,treeSha}') ~ '^[0-9a-f]{40}$'
        )
        AND jsonb_typeof(reconciliation_payload #> '{snapshot,archiveArtifactRef}') = 'string'
        AND length(reconciliation_payload #>> '{snapshot,archiveArtifactRef}') > 0
        AND jsonb_typeof(reconciliation_payload #> '{snapshot,archiveSha256}') = 'string'
        AND (reconciliation_payload #>> '{snapshot,archiveSha256}') ~ '^[0-9a-f]{64}$'
        AND jsonb_typeof(reconciliation_payload #> '{snapshot,archiveSize}') = 'number'
        AND (reconciliation_payload #>> '{snapshot,archiveSize}') ~ '^[0-9]+$'
        AND (reconciliation_payload #>> '{snapshot,archiveSize}')::bigint > 0
        AND (
            (reconciliation_payload #>> '{snapshot,archiveArtifactRef}') =
                'cas:sha256:' || (reconciliation_payload #>> '{snapshot,archiveSha256}')
            OR (reconciliation_payload #>> '{snapshot,archiveArtifactRef}') =
                'cas://sha256/' || (reconciliation_payload #>> '{snapshot,archiveSha256}') ||
                '/' || (reconciliation_payload #>> '{snapshot,archiveSize}')
        )
        AND jsonb_typeof(reconciliation_payload #> '{snapshot,manifestArtifactRef}') = 'string'
        AND length(reconciliation_payload #>> '{snapshot,manifestArtifactRef}') > 0
        AND jsonb_typeof(reconciliation_payload #> '{snapshot,manifestSha256}') = 'string'
        AND (reconciliation_payload #>> '{snapshot,manifestSha256}') ~ '^[0-9a-f]{64}$'
        AND (
            (reconciliation_payload #>> '{snapshot,manifestArtifactRef}') =
                'cas:sha256:' || (reconciliation_payload #>> '{snapshot,manifestSha256}')
            OR (reconciliation_payload #>> '{snapshot,manifestArtifactRef}') ~
                ('^cas://sha256/' ||
                 (reconciliation_payload #>> '{snapshot,manifestSha256}') || '/[0-9]+$')
        )
        AND jsonb_typeof(reconciliation_payload #> '{snapshot,snapshotSchemaVersion}') = 'number'
        AND (reconciliation_payload #>> '{snapshot,snapshotSchemaVersion}') ~ '^[0-9]+$'
        AND (reconciliation_payload #>> '{snapshot,snapshotSchemaVersion}')::integer > 0
        AND jsonb_typeof(reconciliation_payload #> '{snapshot,status}') = 'string'
        AND (reconciliation_payload #>> '{snapshot,status}') IN ('AVAILABLE', 'ARCHIVED')
        AND jsonb_typeof(reconciliation_payload #> '{snapshot,capturedAt}') = 'string'
        AND (reconciliation_payload #>> '{snapshot,capturedAt}')::timestamptz IS NOT NULL
        AND jsonb_typeof(reconciliation_payload #> '{retention,snapshotId}') = 'string'
        AND jsonb_typeof(reconciliation_payload #> '{retention,generations}') = 'object'
    ),
    CONSTRAINT snapshot_root_reconciliation_payload_scope CHECK (
        (reconciliation_payload #>> '{snapshot,organizationId}')
            IS NOT DISTINCT FROM organization_id
        AND (reconciliation_payload #>> '{snapshot,repositoryId}')
            IS NOT DISTINCT FROM repository_id
        AND (reconciliation_payload #>> '{snapshot,snapshotId}')
            IS NOT DISTINCT FROM snapshot_id
        AND (reconciliation_payload ->> 'logicalOperationId')
            IS NOT DISTINCT FROM logical_operation_id
        AND (reconciliation_payload ->> 'reconciliationId')
            IS NOT DISTINCT FROM attempt_id
        AND (reconciliation_payload ->> 'kind')
            IS NOT DISTINCT FROM reconciliation_kind
        AND (reconciliation_payload ->> 'phase')
            IS NOT DISTINCT FROM phase
        AND (reconciliation_payload ->> 'durableSnapshotId')
            IS NOT DISTINCT FROM durable_snapshot_id
    ),
    CONSTRAINT snapshot_root_reconciliation_retention_identity CHECK (
        (reconciliation_payload #>> '{retention,snapshotId}')
            IS NOT DISTINCT FROM snapshot_id
        AND (reconciliation_payload #> '{retention,generations}')
            IS NOT DISTINCT FROM retention_generations
    ),
    CONSTRAINT snapshot_root_reconciliation_durable_shape CHECK (
        (phase = 'DATABASE_COMMITTED' AND durable_snapshot_id IS NOT NULL)
        OR (phase IN ('PENDING', 'COMMIT_FAILED') AND durable_snapshot_id IS NULL)
        OR phase = 'RESOLVED'
    ),
    CONSTRAINT snapshot_root_reconciliation_resolution_shape CHECK (
        (phase = 'RESOLVED') = (resolved_at IS NOT NULL)
    ),
    CONSTRAINT snapshot_root_reconciliation_time_identity CHECK (
        (reconciliation_payload ->> 'recordedAt')::timestamptz
            IS NOT DISTINCT FROM recorded_at
        AND updated_at >= recorded_at
        AND (resolved_at IS NULL OR resolved_at >= updated_at)
    )
);

CREATE INDEX snapshot_root_reconciliation_pending_idx
    ON snapshot_root_reconciliations (organization_id, recorded_at, attempt_id)
    WHERE phase <> 'RESOLVED';

CREATE INDEX snapshot_root_reconciliation_operation_idx
    ON snapshot_root_reconciliations (
        organization_id, repository_id, logical_operation_id, recorded_at);

CREATE OR REPLACE FUNCTION enforce_snapshot_root_reconciliation_transition()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.phase <> 'PENDING'
           OR NEW.durable_snapshot_id IS NOT NULL
           OR NEW.resolved_at IS NOT NULL
           OR NEW.updated_at IS DISTINCT FROM NEW.recorded_at THEN
            RAISE EXCEPTION 'snapshot root reconciliation must start pending';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'snapshot root reconciliations are append-preserving';
    END IF;
    IF NEW.organization_id <> OLD.organization_id
       OR NEW.repository_id <> OLD.repository_id
       OR NEW.attempt_id <> OLD.attempt_id
       OR NEW.logical_operation_id <> OLD.logical_operation_id
       OR NEW.snapshot_id <> OLD.snapshot_id
       OR NEW.reconciliation_kind <> OLD.reconciliation_kind
       OR NEW.recorded_at <> OLD.recorded_at
       OR NEW.retention_generations <> OLD.retention_generations
       OR (NEW.reconciliation_payload - 'phase' - 'durableSnapshotId') <>
          (OLD.reconciliation_payload - 'phase' - 'durableSnapshotId') THEN
        RAISE EXCEPTION 'snapshot root reconciliation identity is immutable';
    END IF;
    IF NEW.phase = OLD.phase THEN
        IF NEW IS DISTINCT FROM OLD THEN
            RAISE EXCEPTION 'snapshot root reconciliation phase is immutable after transition';
        END IF;
        RETURN NEW;
    END IF;
    IF NOT (
        (OLD.phase = 'PENDING'
         AND NEW.phase IN ('DATABASE_COMMITTED', 'COMMIT_FAILED'))
        OR (OLD.phase IN ('DATABASE_COMMITTED', 'COMMIT_FAILED')
            AND NEW.phase = 'RESOLVED')
    ) THEN
        RAISE EXCEPTION 'invalid snapshot root reconciliation phase transition';
    END IF;
    IF NEW.updated_at < OLD.updated_at THEN
        RAISE EXCEPTION 'snapshot root reconciliation time moved backwards';
    END IF;
    IF OLD.phase = 'PENDING' AND NEW.phase = 'DATABASE_COMMITTED' THEN
        IF OLD.durable_snapshot_id IS NOT NULL OR NEW.durable_snapshot_id IS NULL
           OR OLD.resolved_at IS NOT NULL OR NEW.resolved_at IS NOT NULL THEN
            RAISE EXCEPTION 'committed reconciliation durable identity is invalid';
        END IF;
    ELSIF OLD.phase = 'PENDING' AND NEW.phase = 'COMMIT_FAILED' THEN
        IF OLD.durable_snapshot_id IS NOT NULL OR NEW.durable_snapshot_id IS NOT NULL
           OR OLD.resolved_at IS NOT NULL OR NEW.resolved_at IS NOT NULL THEN
            RAISE EXCEPTION 'failed reconciliation cannot bind a durable snapshot';
        END IF;
    ELSIF NEW.phase = 'RESOLVED' THEN
        IF NEW.durable_snapshot_id IS DISTINCT FROM OLD.durable_snapshot_id
           OR OLD.resolved_at IS NOT NULL OR NEW.resolved_at IS NULL THEN
            RAISE EXCEPTION 'resolved reconciliation identity is invalid';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER snapshot_root_reconciliation_transition
BEFORE INSERT OR UPDATE OR DELETE ON snapshot_root_reconciliations
FOR EACH ROW EXECUTE FUNCTION enforce_snapshot_root_reconciliation_transition();

ALTER TABLE snapshot_root_reconciliations ENABLE ROW LEVEL SECURITY;
ALTER TABLE snapshot_root_reconciliations FORCE ROW LEVEL SECURITY;
CREATE POLICY snapshot_root_reconciliation_tenant_isolation
ON snapshot_root_reconciliations
USING (organization_id = current_setting('app.organization_id', true))
WITH CHECK (organization_id = current_setting('app.organization_id', true));
