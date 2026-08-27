package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.ArtifactRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.RepositorySnapshotRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ValidationRunRequest;

import java.util.UUID;

/** Immutable repository snapshot, artifact, and validation-run ownership boundary. */
public interface ProductionRepositoryArtifactPort {
    UUID registerSnapshot(RepositorySnapshotRequest request);
    void bindInputSnapshot(UUID tenantId, UUID jobId, UUID snapshotId);
    UUID registerArtifact(ArtifactRequest request);
    UUID startValidation(ValidationRunRequest request);
    void completeValidation(UUID tenantId, UUID validationRunId, long passed, long failed);
}
