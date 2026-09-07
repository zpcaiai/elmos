package io.elmos.snapshot;

import java.time.Duration;
import java.time.Instant;
import java.util.List;

/** Private global queue used only to lease tenant-scoped reconciliation work. */
public interface SnapshotReconciliationWorkQueue {
    record WorkLease(
            String organizationId,
            String workerId,
            long fencingToken,
            Instant expiresAt
    ) {
        public WorkLease {
            new SnapshotPorts.ArtifactResourceContext(organizationId, "scheduler-scope");
            if (workerId == null
                    || !workerId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
                throw new IllegalArgumentException("workerId is invalid");
            }
            if (fencingToken < 1) {
                throw new IllegalArgumentException("fencingToken must be positive");
            }
            if (expiresAt == null) {
                throw new IllegalArgumentException("expiresAt is required");
            }
        }
    }

    List<WorkLease> claim(String workerId, int limit, Duration leaseDuration);

    /**
     * Releases exactly the claimed fence and durably schedules remaining work. A repeated
     * completion of the same fence is idempotent; a completion from an expired/stale fence fails.
     *
     * @return whether unresolved tenant work remains
     */
    boolean complete(WorkLease lease, boolean successful, Duration retryDelay);
}
