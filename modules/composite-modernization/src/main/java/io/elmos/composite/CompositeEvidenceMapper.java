package io.elmos.composite;

import java.time.Instant;
import java.util.List;

import static io.elmos.composite.CompositeModels.*;

public final class CompositeEvidenceMapper {
    public record CompositeEvidence(String schemaVersion, String scope, String engine,
                                    String organizationId, String artifactType, String sourceRef,
                                    String status, String contentHash, Instant createdAt,
                                    List<String> languageEvidenceRefs, String artifactCanonical) {
        public CompositeEvidence { languageEvidenceRefs = immutable(languageEvidenceRefs); }
    }

    public CompositeEvidence map(String organizationId, String artifactType, String sourceRef,
                                 String status, Object artifact, Instant createdAt,
                                 List<String> languageEvidenceRefs) {
        require(organizationId, "organizationId"); require(artifactType, "artifactType");
        require(sourceRef, "sourceRef"); require(status, "status");
        String canonical = String.valueOf(artifact);
        String hash = CompositeIds.hash("elmos.composite-evidence.v1", organizationId, artifactType,
                sourceRef, status, canonical, immutable(languageEvidenceRefs));
        return new CompositeEvidence("1.0", "COMPOSITE_SYSTEM", "ELMOS_COMPOSITE", organizationId,
                artifactType, sourceRef, status, hash, createdAt,
                immutable(languageEvidenceRefs).stream().distinct().sorted().toList(), canonical);
    }
}
