package io.elmos.snapshot;

import java.time.Instant;
import java.util.List;

/** Ports that keep snapshot database transitions and collector-root reconciliation explicit. */
public final class SnapshotLifecyclePorts {
    private SnapshotLifecyclePorts() { }

    public interface RootReconciliationJournal {
        void recordPending(SnapshotRootReconciliation reconciliation);

        /**
         * This update must execute in the same database transaction as the snapshot insert or
         * archive transition. Implementations must reject a missing or non-pending record.
         */
        void markDatabaseCommitted(String organizationId, String reconciliationId,
                                   String durableSnapshotId);

        /**
         * Serializes with {@link #markDatabaseCommitted}; it may only turn PENDING into
         * COMMIT_FAILED. If the database transaction committed first, the committed phase wins.
         */
        void markCommitFailed(String organizationId, String reconciliationId);

        void markResolved(String organizationId, String reconciliationId);

        /**
         * Atomically converts abandoned PENDING attempts into COMMIT_FAILED while serializing
         * with the coordinator's row lock. A coordinator transaction that is still in flight must
         * win or make the row unavailable to this operation; after this transition a late
         * coordinator must roll back rather than publishing a snapshot whose root was released.
         */
        default int failStalePending(
                String organizationId,
                Instant staleBefore,
                int limit
        ) {
            return 0;
        }

        /** Returns actionable phases before still-PENDING attempts so ambiguity cannot starve work. */
        List<SnapshotRootReconciliation> pending(String organizationId, int limit);
    }

    public interface SnapshotCommitCoordinator {
        /** Saves the snapshot and marks its journal record committed in one transaction. */
        SnapshotModel.RepositorySnapshot saveAvailable(
                SnapshotRootReconciliation reconciliation);
    }

    public interface SnapshotArchiveCoordinator {
        SnapshotModel.RepositorySnapshot requireSnapshot(
                String organizationId, String repositoryId, String snapshotId);

        /** Archives the snapshot and marks its journal record committed in one transaction. */
        SnapshotModel.RepositorySnapshot archive(
                SnapshotRootReconciliation reconciliation);
    }
}
