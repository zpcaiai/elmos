package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.AttemptStatus;
import io.elmos.productionruntime.ProductionRuntimeModels.Checkpoint;
import io.elmos.productionruntime.ProductionRuntimeModels.Completion;
import io.elmos.productionruntime.ProductionRuntimeModels.OutputVerificationReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.WorkerRegistration;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ProductionRuntimeModelsTest {
    @Test
    void completionAcceptsOnlyBoundedTerminalOutcomes() {
        UUID tenant = UUID.randomUUID();
        UUID workItem = UUID.randomUUID();
        UUID attempt = UUID.randomUUID();
        UUID worker = UUID.randomUUID();

        assertThrows(IllegalArgumentException.class, () -> new Completion(
                tenant, workItem, attempt, worker, 1,
                AttemptStatus.RUNNING, null, null));
        assertThrows(IllegalArgumentException.class, () -> new Completion(
                tenant, workItem, attempt, worker, 1,
                AttemptStatus.SUCCEEDED, "UNEXPECTED_ERROR", null));
        assertThrows(IllegalArgumentException.class, () -> new Completion(
                tenant, workItem, attempt, worker, 0,
                AttemptStatus.FAILED, "FAILED", null));
    }

    @Test
    void checkpointRequiresAndCanonicalizesSha256() {
        assertThrows(IllegalArgumentException.class, () -> checkpoint("not-a-digest"));
        assertEquals("a".repeat(64), checkpoint("A".repeat(64)).stateHash());
    }

    @Test
    void outputVerificationCannotClaimCertificationOrUseMutableLocalArtifacts() {
        assertThrows(IllegalArgumentException.class, () -> outputReceipt(
                "file:///tmp/output", "NOT_CERTIFIED"));
        assertThrows(IllegalArgumentException.class, () -> outputReceipt(
                "cas://sha256/" + "a".repeat(64), "CERTIFIED"));
        assertEquals("a".repeat(64), outputReceipt(
                "cas://sha256/" + "a".repeat(64), "NOT_CERTIFIED").artifactSha256());
    }

    @Test
    void workerRegistrationRequiresExactPlacementIdentity() {
        assertThrows(IllegalArgumentException.class, () -> new WorkerRegistration(
                UUID.randomUUID(), "worker", "POLYGLOT", "https://worker.example.test",
                "", "zone-a", Map.of(
                        "routeTuples", List.of("PROJECT_GENERATION:synthesize"),
                        "maxConcurrent", 4)));
    }

    private static Checkpoint checkpoint(String stateHash) {
        return new Checkpoint(
                UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
                "WORKSPACE", 1, "s3://checkpoint/object", stateHash);
    }

    private static OutputVerificationReceipt outputReceipt(
            String artifactUri,
            String certificationStatus
    ) {
        return new OutputVerificationReceipt(
                OutputVerificationReceipt.SCHEMA_VERSION,
                "spring-modernization-v1",
                "SPRING_MODERNIZATION",
                "compile",
                artifactUri,
                "A".repeat(64),
                "repository-owned-output-gate",
                "PASSED",
                certificationStatus,
                Map.of("target_build_pass", true));
    }
}
