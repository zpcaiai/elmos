package io.elmos.snapshot;

import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

/**
 * Durable, fenced permission to read one immutable snapshot's artifacts.
 *
 * <p>The database implementation serializes acquisition with the snapshot row used by archival.
 * A lease identity is exact and tenant/repository bound; a stale fencing token must never renew,
 * validate, or release a later owner's lease.
 */
public record SnapshotMaterializationLease(
        String organizationId,
        String repositoryId,
        String snapshotId,
        String leaseId,
        String holderId,
        long fencingToken,
        Instant acquiredAt,
        Instant expiresAt
) {
    public SnapshotMaterializationLease {
        new SnapshotPorts.ArtifactResourceContext(organizationId, repositoryId);
        snapshotId = requireIdentifier(snapshotId, "snapshotId", 64);
        leaseId = requireIdentifier(leaseId, "leaseId", 64);
        holderId = requireIdentifier(holderId, "holderId", 128);
        if (fencingToken < 1) {
            throw new IllegalArgumentException("fencingToken must be positive");
        }
        Objects.requireNonNull(acquiredAt, "acquiredAt");
        Objects.requireNonNull(expiresAt, "expiresAt");
        if (!expiresAt.isAfter(acquiredAt)) {
            throw new IllegalArgumentException("materialization lease must expire after acquisition");
        }
    }

    public SnapshotPorts.ArtifactResourceContext resource() {
        return new SnapshotPorts.ArtifactResourceContext(organizationId, repositoryId);
    }

    public boolean sameFence(SnapshotMaterializationLease other) {
        return other != null
                && organizationId.equals(other.organizationId)
                && repositoryId.equals(other.repositoryId)
                && snapshotId.equals(other.snapshotId)
                && leaseId.equals(other.leaseId)
                && holderId.equals(other.holderId)
                && fencingToken == other.fencingToken;
    }

    private static String requireIdentifier(String value, String field, int maximumLength) {
        int suffix = maximumLength - 1;
        if (value == null
                || !value.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0," + suffix + "}")) {
            throw new IllegalArgumentException(field + " must be a safe identifier");
        }
        return value;
    }

    /** Persistence port whose implementation must use database-authoritative time. */
    public interface Store {
        SnapshotMaterializationLease acquire(
                SnapshotPorts.ArtifactResourceContext resource,
                String snapshotId,
                String leaseId,
                String holderId,
                Duration duration);

        SnapshotMaterializationLease renew(
                SnapshotMaterializationLease lease,
                Duration duration);

        SnapshotMaterializationLease requireActive(SnapshotMaterializationLease lease);

        /** Exact-fence release. Repeating the same successful release is idempotent. */
        void release(SnapshotMaterializationLease lease);
    }
}
