package io.elmos.domain;

import java.time.Instant;

public record RepositorySnapshot(SnapshotId id, OrganizationId organizationId, RepositoryId repositoryId, CommitSha commitSha, String branch, Instant capturedAt, String buildFilesHash, ArtifactRef sourceArchiveRef) {
    public RepositorySnapshot { if (id == null || organizationId == null || repositoryId == null || commitSha == null || capturedAt == null || sourceArchiveRef == null) throw new IllegalArgumentException("snapshot fields are required"); branch = Identifiers.require(branch, "branch"); buildFilesHash = Identifiers.require(buildFilesHash, "buildFilesHash"); }
}

