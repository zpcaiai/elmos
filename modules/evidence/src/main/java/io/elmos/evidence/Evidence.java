package io.elmos.evidence;

import io.elmos.domain.ArtifactRef;
import io.elmos.domain.CommitSha;
import io.elmos.domain.EvidenceId;
import io.elmos.domain.MigrationRunId;
import io.elmos.domain.OrganizationId;
import io.elmos.domain.StepRunId;

import java.time.Instant;
import java.util.Objects;

public record Evidence(EvidenceId evidenceId, OrganizationId organizationId, MigrationRunId migrationRunId,
                       StepRunId stepRunId, EvidenceType evidenceType, String producerType, String producerName,
                       String producerVersion, CommitSha sourceCommit, CommitSha targetCommit, Instant createdAt,
                       EvidenceStatus status, String summary, ArtifactRef artifactRef, String contentHash,
                       String schemaVersion, String correlationId) {
    public Evidence {
        Objects.requireNonNull(evidenceId); Objects.requireNonNull(organizationId); Objects.requireNonNull(migrationRunId);
        Objects.requireNonNull(evidenceType); Objects.requireNonNull(sourceCommit); Objects.requireNonNull(createdAt);
        Objects.requireNonNull(status); Objects.requireNonNull(artifactRef);
        require(producerType,"producerType"); require(producerName,"producerName"); require(producerVersion,"producerVersion");
        require(summary,"summary"); require(schemaVersion,"schemaVersion"); require(correlationId,"correlationId");
        if (!contentHash.matches("sha256:[0-9a-f]{64}")) throw new IllegalArgumentException("contentHash must be sha256:<hex>");
    }
    private static void require(String value,String field){if(value==null||value.isBlank())throw new IllegalArgumentException(field+" is required");}
}

