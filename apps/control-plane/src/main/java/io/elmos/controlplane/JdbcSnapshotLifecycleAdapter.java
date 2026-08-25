package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import io.elmos.persistence.JdbcSnapshotStore;
import io.elmos.snapshot.SnapshotLifecyclePorts;
import io.elmos.snapshot.SnapshotModel;
import io.elmos.snapshot.SnapshotRootReconciliation;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Objects;

/**
 * PostgreSQL-backed snapshot lifecycle journal and transaction coordinator.
 *
 * <p>The dedicated reconciliation row is deliberately updated in the same transaction as snapshot insertion or
 * archival. A client timeout can therefore never produce an unclassified "maybe committed"
 * release: the row remains PENDING/COMMIT_FAILED when the transaction rolls back and becomes
 * DATABASE_COMMITTED when it commits.
 */
public class JdbcSnapshotLifecycleAdapter implements
        SnapshotLifecyclePorts.RootReconciliationJournal,
        SnapshotLifecyclePorts.SnapshotCommitCoordinator,
        SnapshotLifecyclePorts.SnapshotArchiveCoordinator {

    private final JdbcClient jdbc;
    private final JdbcSnapshotStore snapshots;
    private final ObjectMapper mapper;
    private final Clock clock;

    public JdbcSnapshotLifecycleAdapter(
            JdbcClient jdbc,
            JdbcSnapshotStore snapshots,
            ObjectMapper mapper,
            Clock clock
    ) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.snapshots = Objects.requireNonNull(snapshots, "snapshots");
        this.mapper = Objects.requireNonNull(mapper, "mapper")
                .copy()
                .findAndRegisterModules()
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    @Override
    @Transactional
    public void recordPending(SnapshotRootReconciliation reconciliation) {
        Objects.requireNonNull(reconciliation, "reconciliation");
        if (reconciliation.phase() != SnapshotRootReconciliation.Phase.PENDING) {
            throw new IllegalArgumentException("new reconciliation must be pending");
        }
        setTenant(reconciliation.snapshot().organizationId());
        int inserted = jdbc.sql("""
                insert into snapshot_root_reconciliations(
                    organization_id, repository_id, attempt_id, logical_operation_id,
                    snapshot_id, reconciliation_kind, phase, durable_snapshot_id,
                    reconciliation_payload, retention_generations, recorded_at, updated_at)
                values(:organization, :repository, :attempt, :logicalOperation,
                    :snapshot, :kind, :phase, null,
                    cast(:payload as jsonb), cast(:generations as jsonb), :recordedAt, :recordedAt)
                on conflict (organization_id, attempt_id) do nothing
                """)
                .param("organization", reconciliation.snapshot().organizationId())
                .param("repository", reconciliation.snapshot().repositoryId())
                .param("attempt", reconciliation.reconciliationId())
                .param("logicalOperation", reconciliation.logicalOperationId())
                .param("snapshot", reconciliation.snapshot().snapshotId())
                .param("kind", reconciliation.kind().name())
                .param("phase", reconciliation.phase().name())
                .param("payload", write(reconciliation))
                .param("generations", writeGenerations(reconciliation))
                .param("recordedAt", databaseTimestamp(reconciliation.recordedAt()))
                .update();
        if (inserted == 0) {
            SnapshotRootReconciliation existing = locked(
                    reconciliation.snapshot().organizationId(),
                    reconciliation.reconciliationId());
            if (!sameIdentity(existing, reconciliation)) {
                throw new SecurityException(
                        "reconciliation id is already bound to another snapshot lifecycle");
            }
        }
    }

    @Override
    @Transactional
    public SnapshotModel.RepositorySnapshot saveAvailable(
            SnapshotRootReconciliation reconciliation
    ) {
        requirePendingKind(reconciliation,
                SnapshotRootReconciliation.Kind.CAPTURE_COMMIT);
        setTenant(reconciliation.snapshot().organizationId());
        SnapshotModel.RepositorySnapshot stored = snapshots.saveAvailable(
                reconciliation.snapshot());
        markDatabaseCommittedInternal(
                reconciliation.snapshot().organizationId(),
                reconciliation.reconciliationId(), stored.snapshotId());
        return stored;
    }

    @Override
    @Transactional
    public int failStalePending(
            String organizationId,
            Instant staleBefore,
            int limit
    ) {
        if (staleBefore == null) {
            throw new IllegalArgumentException("staleBefore is required");
        }
        if (limit < 1 || limit > 1_000) {
            throw new IllegalArgumentException("reconciliation limit is invalid");
        }
        setTenant(organizationId);
        Instant updatedAt = clock.instant();
        if (staleBefore.isAfter(updatedAt)) {
            throw new IllegalArgumentException("staleBefore cannot be in the future");
        }
        return jdbc.sql("""
                with stale as (
                    select organization_id, attempt_id
                      from snapshot_root_reconciliations
                     where organization_id = :organization
                       and phase = 'PENDING'
                       and updated_at <= :staleBefore
                     order by updated_at, attempt_id
                     for update skip locked
                     limit :limit
                )
                update snapshot_root_reconciliations reconciliation
                   set phase = 'COMMIT_FAILED',
                       reconciliation_payload = jsonb_set(
                           reconciliation.reconciliation_payload,
                           '{phase}', to_jsonb('COMMIT_FAILED'::text), false),
                       updated_at = :updatedAt
                  from stale
                 where reconciliation.organization_id = stale.organization_id
                   and reconciliation.attempt_id = stale.attempt_id
                   and reconciliation.phase = 'PENDING'
                """)
                .param("organization", organizationId)
                .param("staleBefore", databaseTimestamp(staleBefore))
                .param("updatedAt", databaseTimestamp(updatedAt))
                .param("limit", limit)
                .update();
    }

    @Override
    @Transactional(readOnly = true)
    public SnapshotModel.RepositorySnapshot requireSnapshot(
            String organizationId,
            String repositoryId,
            String snapshotId
    ) {
        setTenant(organizationId);
        return jdbc.sql("""
                select snapshot_id, organization_id, repository_id, requested_ref, commit_sha,
                       tree_sha, archive_artifact_ref, archive_sha256, archive_size,
                       manifest_artifact_ref, manifest_sha256, snapshot_schema_version, status,
                       captured_at
                  from repository_snapshots
                 where organization_id = :organization
                   and repository_id = :repository
                   and snapshot_id = :snapshot
                """)
                .param("organization", organizationId)
                .param("repository", repositoryId)
                .param("snapshot", snapshotId)
                .query(JdbcSnapshotLifecycleAdapter::mapSnapshot)
                .optional()
                .orElseThrow(() -> new SecurityException(
                        "snapshot is unavailable for resource context"));
    }

    @Override
    @Transactional
    public SnapshotModel.RepositorySnapshot archive(
            SnapshotRootReconciliation reconciliation
    ) {
        requirePendingKind(reconciliation,
                SnapshotRootReconciliation.Kind.ARCHIVE_RELEASE);
        SnapshotModel.RepositorySnapshot intended = reconciliation.snapshot();
        setTenant(intended.organizationId());
        SnapshotModel.RepositorySnapshot current = jdbc.sql("""
                select snapshot_id, organization_id, repository_id, requested_ref, commit_sha,
                       tree_sha, archive_artifact_ref, archive_sha256, archive_size,
                       manifest_artifact_ref, manifest_sha256, snapshot_schema_version, status,
                       captured_at
                  from repository_snapshots
                 where organization_id = :organization
                   and repository_id = :repository
                   and snapshot_id = :snapshot
                 for update
                """)
                .param("organization", intended.organizationId())
                .param("repository", intended.repositoryId())
                .param("snapshot", intended.snapshotId())
                .query(JdbcSnapshotLifecycleAdapter::mapSnapshot)
                .optional()
                .orElseThrow(() -> new SecurityException(
                        "snapshot is unavailable for resource context"));
        requireSameImmutableSnapshot(intended, current);
        if (current.status() == SnapshotModel.Status.AVAILABLE) {
            int updated = jdbc.sql("""
                    update repository_snapshots set status = 'ARCHIVED'
                     where organization_id = :organization
                       and repository_id = :repository
                       and snapshot_id = :snapshot
                       and status = 'AVAILABLE'
                    """)
                    .param("organization", current.organizationId())
                    .param("repository", current.repositoryId())
                    .param("snapshot", current.snapshotId())
                    .update();
            if (updated != 1) {
                throw new IllegalStateException("snapshot archive transition was lost");
            }
        } else if (current.status() != SnapshotModel.Status.ARCHIVED) {
            throw new IllegalStateException("snapshot cannot be archived from current status");
        }
        markDatabaseCommittedInternal(
                intended.organizationId(), reconciliation.reconciliationId(),
                current.snapshotId());
        return withStatus(current, SnapshotModel.Status.ARCHIVED);
    }

    @Override
    @Transactional
    public void markDatabaseCommitted(
            String organizationId,
            String reconciliationId,
            String durableSnapshotId
    ) {
        setTenant(organizationId);
        markDatabaseCommittedInternal(
                organizationId, reconciliationId, durableSnapshotId);
    }

    @Override
    @Transactional
    public void markCommitFailed(String organizationId, String reconciliationId) {
        setTenant(organizationId);
        SnapshotRootReconciliation current = locked(organizationId, reconciliationId);
        if (current.phase() == SnapshotRootReconciliation.Phase.DATABASE_COMMITTED
                || current.phase() == SnapshotRootReconciliation.Phase.COMMIT_FAILED
                || current.phase() == SnapshotRootReconciliation.Phase.RESOLVED) {
            return;
        }
        if (current.phase() != SnapshotRootReconciliation.Phase.PENDING) {
            throw new IllegalStateException("reconciliation phase is invalid");
        }
        update(current.failed(), null);
    }

    @Override
    @Transactional
    public void markResolved(String organizationId, String reconciliationId) {
        setTenant(organizationId);
        SnapshotRootReconciliation current = locked(organizationId, reconciliationId);
        if (current.phase() == SnapshotRootReconciliation.Phase.RESOLVED) {
            return;
        }
        if (current.phase() != SnapshotRootReconciliation.Phase.DATABASE_COMMITTED
                && current.phase() != SnapshotRootReconciliation.Phase.COMMIT_FAILED) {
            throw new IllegalStateException(
                    "ambiguous reconciliation cannot be marked resolved");
        }
        update(current.resolved(), clock.instant());
    }

    @Override
    @Transactional(readOnly = true)
    public List<SnapshotRootReconciliation> pending(
            String organizationId,
            int limit
    ) {
        if (limit < 1 || limit > 1_000) {
            throw new IllegalArgumentException("reconciliation limit is invalid");
        }
        setTenant(organizationId);
        return jdbc.sql("""
                select reconciliation_payload
                  from snapshot_root_reconciliations
                 where organization_id = :organization
                   and phase <> 'RESOLVED'
                 order by case when phase = 'PENDING' then 1 else 0 end,
                          recorded_at, attempt_id
                 limit :limit
                """)
                .param("organization", organizationId)
                .param("limit", limit)
                .query((row, number) -> read(row.getString("reconciliation_payload")))
                .list();
    }

    private void markDatabaseCommittedInternal(
            String organizationId,
            String reconciliationId,
            String durableSnapshotId
    ) {
        SnapshotRootReconciliation current = locked(organizationId, reconciliationId);
        if (current.phase() == SnapshotRootReconciliation.Phase.DATABASE_COMMITTED) {
            if (!Objects.equals(current.durableSnapshotId(), durableSnapshotId)) {
                throw new SecurityException(
                        "reconciliation is committed to another snapshot");
            }
            return;
        }
        if (current.phase() != SnapshotRootReconciliation.Phase.PENDING) {
            throw new IllegalStateException(
                    "only a pending reconciliation may commit");
        }
        update(current.committed(durableSnapshotId), null);
    }

    private SnapshotRootReconciliation locked(
            String organizationId,
            String reconciliationId
    ) {
        return jdbc.sql("""
                select reconciliation_payload
                  from snapshot_root_reconciliations
                 where organization_id = :organization and attempt_id = :attempt
                 for update
                """)
                .param("organization", organizationId)
                .param("attempt", reconciliationId)
                .query((row, number) -> read(row.getString("reconciliation_payload")))
                .optional()
                .orElseThrow(() -> new IllegalStateException(
                        "snapshot reconciliation journal record is missing"));
    }

    private void update(SnapshotRootReconciliation reconciliation, Instant resolvedAt) {
        Instant updatedAt = resolvedAt == null ? clock.instant() : resolvedAt;
        int updated = jdbc.sql("""
                update snapshot_root_reconciliations
                   set phase = :phase,
                       durable_snapshot_id = :durableSnapshot,
                       reconciliation_payload = cast(:payload as jsonb),
                       updated_at = :updatedAt,
                       resolved_at = :resolvedAt
                 where organization_id = :organization and attempt_id = :attempt
                """)
                .param("phase", reconciliation.phase().name())
                .param("durableSnapshot", reconciliation.durableSnapshotId())
                .param("payload", write(reconciliation))
                .param("updatedAt", databaseTimestamp(updatedAt))
                .param("resolvedAt", databaseTimestamp(resolvedAt))
                .param("organization", reconciliation.snapshot().organizationId())
                .param("attempt", reconciliation.reconciliationId())
                .update();
        if (updated != 1) {
            throw new IllegalStateException(
                    "snapshot reconciliation journal update was lost");
        }
    }

    private String write(SnapshotRootReconciliation reconciliation) {
        try {
            return mapper.writeValueAsString(reconciliation);
        } catch (Exception error) {
            throw new IllegalStateException("cannot serialize snapshot reconciliation", error);
        }
    }

    private String writeGenerations(SnapshotRootReconciliation reconciliation) {
        try {
            return mapper.writeValueAsString(reconciliation.retention().generations());
        } catch (Exception error) {
            throw new IllegalStateException(
                    "cannot serialize snapshot retention generations", error);
        }
    }

    private SnapshotRootReconciliation read(String value) {
        try {
            return mapper.readValue(value, SnapshotRootReconciliation.class);
        } catch (Exception error) {
            throw new IllegalStateException("cannot read snapshot reconciliation", error);
        }
    }

    static OffsetDateTime databaseTimestamp(Instant value) {
        return value == null ? null : value.atOffset(ZoneOffset.UTC);
    }

    private void setTenant(String organizationId) {
        if (organizationId == null || organizationId.isBlank()) {
            throw new IllegalArgumentException("organizationId is required");
        }
        jdbc.sql("select set_config('app.organization_id', :organization, true)")
                .param("organization", organizationId)
                .query(String.class)
                .single();
    }

    private static void requirePendingKind(
            SnapshotRootReconciliation reconciliation,
            SnapshotRootReconciliation.Kind kind
    ) {
        Objects.requireNonNull(reconciliation, "reconciliation");
        if (reconciliation.kind() != kind
                || reconciliation.phase() != SnapshotRootReconciliation.Phase.PENDING) {
            throw new IllegalArgumentException("snapshot reconciliation kind or phase is invalid");
        }
    }

    private static boolean sameIdentity(
            SnapshotRootReconciliation first,
            SnapshotRootReconciliation second
    ) {
        return first.reconciliationId().equals(second.reconciliationId())
                && first.logicalOperationId().equals(second.logicalOperationId())
                && first.kind() == second.kind()
                && first.snapshot().equals(second.snapshot())
                && first.retention().equals(second.retention())
                && first.recordedAt().equals(second.recordedAt());
    }

    private static void requireSameImmutableSnapshot(
            SnapshotModel.RepositorySnapshot intended,
            SnapshotModel.RepositorySnapshot stored
    ) {
        if (!intended.snapshotId().equals(stored.snapshotId())
                || !intended.organizationId().equals(stored.organizationId())
                || !intended.repositoryId().equals(stored.repositoryId())
                || !intended.requestedRef().equals(stored.requestedRef())
                || !intended.resolvedCommitSha().equals(stored.resolvedCommitSha())
                || !Objects.equals(intended.treeSha(), stored.treeSha())
                || !intended.archiveArtifactRef().equals(stored.archiveArtifactRef())
                || !intended.archiveSha256().equals(stored.archiveSha256())
                || intended.archiveSize() != stored.archiveSize()
                || !intended.manifestArtifactRef().equals(stored.manifestArtifactRef())
                || !intended.manifestSha256().equals(stored.manifestSha256())
                || intended.snapshotSchemaVersion() != stored.snapshotSchemaVersion()
                || !intended.capturedAt().equals(stored.capturedAt())) {
            throw new SecurityException("snapshot changed before archive transition");
        }
    }

    private static SnapshotModel.RepositorySnapshot mapSnapshot(
            ResultSet result,
            int row
    ) throws SQLException {
        return new SnapshotModel.RepositorySnapshot(
                result.getString("snapshot_id"),
                result.getString("organization_id"),
                result.getString("repository_id"),
                result.getString("requested_ref"),
                result.getString("commit_sha"),
                result.getString("tree_sha"),
                result.getString("archive_artifact_ref"),
                result.getString("archive_sha256"),
                result.getLong("archive_size"),
                result.getString("manifest_artifact_ref"),
                result.getString("manifest_sha256"),
                result.getInt("snapshot_schema_version"),
                SnapshotModel.Status.valueOf(result.getString("status")),
                result.getObject("captured_at", OffsetDateTime.class).toInstant());
    }

    private static SnapshotModel.RepositorySnapshot withStatus(
            SnapshotModel.RepositorySnapshot snapshot,
            SnapshotModel.Status status
    ) {
        return new SnapshotModel.RepositorySnapshot(
                snapshot.snapshotId(), snapshot.organizationId(), snapshot.repositoryId(),
                snapshot.requestedRef(), snapshot.resolvedCommitSha(), snapshot.treeSha(),
                snapshot.archiveArtifactRef(), snapshot.archiveSha256(), snapshot.archiveSize(),
                snapshot.manifestArtifactRef(), snapshot.manifestSha256(),
                snapshot.snapshotSchemaVersion(), status, snapshot.capturedAt());
    }
}
