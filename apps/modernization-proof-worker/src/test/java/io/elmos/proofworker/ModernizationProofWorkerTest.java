package io.elmos.proofworker;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.proofloop.ProofLoopModels;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ModernizationProofWorkerTest {
    @Test
    void workerEnvelopeRoundTripsWithoutTenantOrActorReinterpretation() throws Exception {
        var execution = new ProofLoopModels.ExecutionRequest(
                "job-1", "job-1:B105-S01", "B105-S01", "actor-1",
                new ProofLoopModels.Subject("org-1", "project-1", "repo-1", "a".repeat(40), null, null,
                        "sha256:" + "0".repeat(64)),
                Instant.parse("2026-08-05T12:00:00Z"), Map.of(), Map.of());
        var envelope = new ModernizationProofWorker.WorkerRequest(1, "B105-S01", execution);
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
        var decoded = mapper.readValue(mapper.writeValueAsBytes(envelope), ModernizationProofWorker.WorkerRequest.class);
        assertEquals("org-1", decoded.execution().subject().organizationId());
        assertEquals("actor-1", decoded.execution().actorId());
    }

    @Test
    void targetMismatchFailsClosed() {
        var execution = new ProofLoopModels.ExecutionRequest(
                "job-1", "job-1:B105-S01", "B105-S01", "actor-1",
                new ProofLoopModels.Subject("org-1", "project-1", "repo-1", null, null, null,
                        "sha256:" + "0".repeat(64)), Instant.now(), Map.of(), Map.of());
        assertThrows(IllegalArgumentException.class,
                () -> new ModernizationProofWorker.WorkerRequest(1, "B108-S16", execution));
    }
}
