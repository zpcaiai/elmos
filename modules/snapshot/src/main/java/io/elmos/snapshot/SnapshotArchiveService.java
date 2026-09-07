package io.elmos.snapshot;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.util.Objects;
import java.util.UUID;

/**
 * Soft-deletes a snapshot before releasing its collector roots.
 *
 * <p>The archive database transition and DATABASE_COMMITTED journal phase are one transaction in
 * {@link SnapshotLifecyclePorts.SnapshotArchiveCoordinator}. Root release happens only after that
 * transaction returns. A lost acknowledgement therefore leaves reachable bytes and a durable
 * reconciliation record rather than an available row that points at collectable content.
 */
public final class SnapshotArchiveService {
    public record ArchiveRequest(
            String organizationId,
            String repositoryId,
            String snapshotId,
            String idempotencyKey
    ) { }

    public record ArchiveResult(
            String snapshotId,
            SnapshotModel.Status status,
            String reconciliationId
    ) { }

    private final SnapshotPorts.ArtifactStore artifacts;
    private final SnapshotLifecyclePorts.SnapshotArchiveCoordinator archives;
    private final SnapshotLifecyclePorts.RootReconciliationJournal reconciliations;
    private final Clock clock;

    public SnapshotArchiveService(
            SnapshotPorts.ArtifactStore artifacts,
            SnapshotLifecyclePorts.SnapshotArchiveCoordinator archives,
            SnapshotLifecyclePorts.RootReconciliationJournal reconciliations,
            Clock clock
    ) {
        this.artifacts = Objects.requireNonNull(artifacts, "artifacts");
        this.archives = Objects.requireNonNull(archives, "archives");
        this.reconciliations = Objects.requireNonNull(reconciliations, "reconciliations");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public ArchiveResult archive(ArchiveRequest request) {
        validate(request);
        SnapshotModel.RepositorySnapshot snapshot = archives.requireSnapshot(
                request.organizationId(), request.repositoryId(), request.snapshotId());
        var resource = new SnapshotPorts.ArtifactResourceContext(
                request.organizationId(), request.repositoryId());
        SnapshotCaptureService.requireOwnedBy(resource, snapshot);
        SnapshotCaptureService.requireArtifactReferences(snapshot);
        if (snapshot.status() == SnapshotModel.Status.ARCHIVED) {
            // A committed retry is completed by the durable reconciliation record created by the
            // winning transaction. Do not reactivate a root merely to release it again.
            return new ArchiveResult(snapshot.snapshotId(), snapshot.status(), null);
        }
        if (snapshot.status() != SnapshotModel.Status.AVAILABLE) {
            throw new IllegalStateException("only available snapshots may be archived");
        }

        SnapshotPorts.ArtifactRetention retention = artifacts.retainSnapshotGeneration(
                resource, snapshot.snapshotId(), SnapshotCaptureService.references(snapshot));
        SnapshotRootReconciliation reconciliation = new SnapshotRootReconciliation(
                "snapshot-archive-attempt-" + UUID.randomUUID(),
                logicalOperationId(request),
                SnapshotRootReconciliation.Kind.ARCHIVE_RELEASE,
                SnapshotRootReconciliation.Phase.PENDING,
                snapshot, retention, null, clock.instant());
        // If this write fails, keep the existing durable root. Releasing it would make the still
        // AVAILABLE database row unsafe.
        reconciliations.recordPending(reconciliation);

        SnapshotModel.RepositorySnapshot archived;
        try {
            archived = archives.archive(reconciliation);
        } catch (RuntimeException failure) {
            try {
                reconciliations.markCommitFailed(
                        resource.organizationId(), reconciliation.reconciliationId());
            } catch (RuntimeException journalFailure) {
                failure.addSuppressed(journalFailure);
            }
            throw failure;
        }
        SnapshotCaptureService.requireOwnedBy(resource, archived);
        requireEquivalent(snapshot, archived, SnapshotModel.Status.ARCHIVED);
        artifacts.releaseSnapshotGeneration(resource, retention);
        reconciliations.markResolved(
                resource.organizationId(), reconciliation.reconciliationId());
        return new ArchiveResult(archived.snapshotId(), archived.status(),
                reconciliation.reconciliationId());
    }

    static String logicalOperationId(ArchiveRequest request) {
        String preimage = "elmos-snapshot-archive-reconciliation/1\n"
                + request.organizationId() + "\n" + request.repositoryId() + "\n"
                + request.snapshotId() + "\n" + request.idempotencyKey();
        return "snapshot-archive-" + UUID.nameUUIDFromBytes(
                preimage.getBytes(StandardCharsets.UTF_8));
    }

    static void requireEquivalent(
            SnapshotModel.RepositorySnapshot intended,
            SnapshotModel.RepositorySnapshot stored,
            SnapshotModel.Status expectedStatus
    ) {
        Objects.requireNonNull(stored, "snapshot archive coordinator returned null");
        SnapshotCaptureService.requireOwnedBy(
                new SnapshotPorts.ArtifactResourceContext(
                        intended.organizationId(), intended.repositoryId()),
                stored);
        SnapshotCaptureService.requireArtifactReferences(stored);
        if (stored.status() != expectedStatus
                || !intended.snapshotId().equals(stored.snapshotId())
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
            throw new SecurityException(
                    "archive coordinator returned a conflicting snapshot");
        }
    }

    private static void validate(ArchiveRequest request) {
        Objects.requireNonNull(request, "request");
        new SnapshotPorts.ArtifactResourceContext(
                request.organizationId(), request.repositoryId());
        if (request.snapshotId() == null
                || !request.snapshotId().matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")) {
            throw new IllegalArgumentException("snapshotId must be a safe identifier");
        }
        if (request.idempotencyKey() == null
                || request.idempotencyKey().isBlank()
                || request.idempotencyKey().length() > 160) {
            throw new IllegalArgumentException("archive idempotencyKey is invalid");
        }
    }
}
