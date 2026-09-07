package io.elmos.evidence;

import io.elmos.domain.*;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ValidationPolicyTest {
    @Test void notRunIsNeverPass() {
        var policy = new ValidationPolicy(List.of(EvidenceType.BUILD_RESULT));
        assertFalse(policy.evaluate(List.of(evidence(EvidenceStatus.NOT_RUN))).passed());
        assertTrue(policy.evaluate(List.of(evidence(EvidenceStatus.PASS))).passed());
        assertThrows(IllegalArgumentException.class, () -> new ValidationPolicy(List.of()));
    }
    private Evidence evidence(EvidenceStatus status) {
        return new Evidence(EvidenceId.random(), OrganizationId.random(), MigrationRunId.random(), null,
                EvidenceType.BUILD_RESULT, "WORKER", "simulator", "0.1.0", new CommitSha("abcdef1"), null,
                Instant.parse("2026-07-20T12:00:00Z"), status, "simulated build", new ArtifactRef("s3://evidence/build.json"),
                "sha256:" + "0".repeat(64), "1.0", "corr-1");
    }
}
