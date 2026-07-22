package io.elmos.snapshot;

import java.time.Instant;
import java.util.Objects;

public final class SnapshotModel {
    private SnapshotModel() {}

    public enum Status {
        REQUESTED, RESOLVING_REF, FETCHING, VERIFYING, ARCHIVING, UPLOADING,
        AVAILABLE, UNSUPPORTED_CONTENT, FAILED, QUARANTINED
    }

    public record RepositorySnapshot(String snapshotId, String organizationId, String repositoryId,
                                     String requestedRef, String resolvedCommitSha, String treeSha,
                                     String archiveArtifactRef, String archiveSha256, long archiveSize,
                                     String manifestArtifactRef, String manifestSha256, int snapshotSchemaVersion, Status status,
                                     Instant capturedAt) {
        public RepositorySnapshot {
            require(snapshotId, "snapshotId"); require(organizationId, "organizationId");
            require(repositoryId, "repositoryId"); require(requestedRef, "requestedRef");
            if (resolvedCommitSha == null || !resolvedCommitSha.matches("[0-9a-f]{40}")) throw new IllegalArgumentException("resolvedCommitSha must be 40 lowercase hex characters");
            if (archiveSha256 != null && !archiveSha256.matches("[0-9a-f]{64}")) throw new IllegalArgumentException("invalid archiveSha256");
            if (manifestSha256 != null && !manifestSha256.matches("[0-9a-f]{64}")) throw new IllegalArgumentException("invalid manifestSha256");
            if (snapshotSchemaVersion < 1) throw new IllegalArgumentException("snapshotSchemaVersion must be positive");
            Objects.requireNonNull(status); Objects.requireNonNull(capturedAt);
            if (status == Status.AVAILABLE && (archiveArtifactRef == null || archiveSha256 == null || manifestArtifactRef == null || manifestSha256 == null || archiveSize <= 0)) {
                throw new IllegalArgumentException("available snapshot requires immutable archive and manifest metadata");
            }
            if (status == Status.AVAILABLE && (archiveArtifactRef.isBlank() || manifestArtifactRef.isBlank()))
                throw new IllegalArgumentException("available snapshot artifact references must not be blank");
        }

        public RepositorySnapshot transition(Status next) {
            if (status == Status.AVAILABLE) throw new IllegalStateException("available snapshot is immutable");
            if (status == Status.FAILED || status == Status.QUARANTINED || status == Status.UNSUPPORTED_CONTENT) throw new IllegalStateException("terminal snapshot is immutable");
            return new RepositorySnapshot(snapshotId, organizationId, repositoryId, requestedRef, resolvedCommitSha,
                    treeSha, archiveArtifactRef, archiveSha256, archiveSize, manifestArtifactRef, manifestSha256, snapshotSchemaVersion, next, capturedAt);
        }

        private static void require(String value, String name) { if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required"); }
    }
}
