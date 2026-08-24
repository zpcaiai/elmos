package io.elmos.snapshot;

import java.time.Instant;
import java.util.Objects;

/**
 * Durable description of a snapshot root whose database outcome and collector lifetime must be
 * reconciled.
 */
public record SnapshotRootReconciliation(
        String reconciliationId,
        String logicalOperationId,
        Kind kind,
        Phase phase,
        SnapshotModel.RepositorySnapshot snapshot,
        SnapshotPorts.ArtifactRetention retention,
        String durableSnapshotId,
        Instant recordedAt
) {
    public enum Kind {
        CAPTURE_COMMIT,
        ARCHIVE_RELEASE
    }

    public enum Phase {
        /** A database transaction may still be in flight. Roots must not be released. */
        PENDING,
        /** The snapshot insert or archive transition committed with the journal update. */
        DATABASE_COMMITTED,
        /** The transaction definitely rolled back after serialization with its journal row. */
        COMMIT_FAILED,
        /** Root handoff or release completed. */
        RESOLVED
    }

    public SnapshotRootReconciliation {
        if (reconciliationId == null
                || !reconciliationId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")) {
            throw new IllegalArgumentException("reconciliationId must be a safe identifier");
        }
        if (logicalOperationId == null
                || !logicalOperationId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")) {
            throw new IllegalArgumentException("logicalOperationId must be a safe identifier");
        }
        Objects.requireNonNull(kind, "kind");
        Objects.requireNonNull(phase, "phase");
        Objects.requireNonNull(snapshot, "snapshot");
        Objects.requireNonNull(retention, "retention");
        Objects.requireNonNull(recordedAt, "recordedAt");
        if (!snapshot.snapshotId().equals(retention.snapshotId())) {
            throw new IllegalArgumentException(
                    "snapshot and artifact retention identities differ");
        }
        if (durableSnapshotId != null
                && !durableSnapshotId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
            throw new IllegalArgumentException("durableSnapshotId must be a safe identifier");
        }
        if (phase == Phase.PENDING && durableSnapshotId != null) {
            throw new IllegalArgumentException(
                    "pending reconciliation cannot name a durable snapshot");
        }
        if (phase == Phase.DATABASE_COMMITTED && durableSnapshotId == null) {
            throw new IllegalArgumentException(
                    "committed reconciliation requires a durable snapshot");
        }
    }

    public SnapshotRootReconciliation committed(String snapshotId) {
        return new SnapshotRootReconciliation(reconciliationId, logicalOperationId, kind,
                Phase.DATABASE_COMMITTED, snapshot, retention,
                Objects.requireNonNull(snapshotId, "snapshotId"), recordedAt);
    }

    public SnapshotRootReconciliation failed() {
        return new SnapshotRootReconciliation(reconciliationId, logicalOperationId, kind,
                Phase.COMMIT_FAILED, snapshot, retention, null, recordedAt);
    }

    public SnapshotRootReconciliation resolved() {
        return new SnapshotRootReconciliation(reconciliationId, logicalOperationId, kind,
                Phase.RESOLVED, snapshot, retention, durableSnapshotId, recordedAt);
    }
}
