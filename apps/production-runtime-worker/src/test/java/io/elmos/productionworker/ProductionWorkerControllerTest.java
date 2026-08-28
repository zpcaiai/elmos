package io.elmos.productionworker;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.OwnerOnlyProviderCredentialFile;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchEnvelope;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ProductionWorkerControllerTest {
    private static final String TOKEN = "worker-controller-test-token-123456";

    @TempDir
    Path temporary;

    private ProductionWorkerAttemptService attempts;
    private MockMvc mvc;
    private ObjectMapper json;
    private DispatchEnvelope envelope;

    @BeforeEach
    void setUp() throws Exception {
        Path token = temporary.resolve("workload-token");
        Files.writeString(token, TOKEN);
        try {
            Files.setPosixFilePermissions(token, Set.of(
                    PosixFilePermission.OWNER_READ,
                    PosixFilePermission.OWNER_WRITE));
        } catch (UnsupportedOperationException ignored) {
            // The production credential reader applies the platform ACL check.
        }
        attempts = mock(ProductionWorkerAttemptService.class);
        when(attempts.accept(any())).thenReturn(
                new ProductionWorkerAttemptService.Acceptance(
                        ProductionWorkerAttemptService.LocalStatus.ACKED, false));
        mvc = MockMvcBuilders.standaloneSetup(new ProductionWorkerController(
                attempts, new OwnerOnlyProviderCredentialFile(token))).build();
        json = new ObjectMapper();
        envelope = new DispatchEnvelope(
                UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
                UUID.randomUUID(), 7L, "https://worker.example/internal",
                "dispatch-key-1", Map.of("jobType", "A", "workType", "B"));
    }

    @Test
    void dispatchRequiresExactAuthenticatedEnvelopeHeaders() throws Exception {
        mvc.perform(post("/internal/v1/production-runtime/dispatch")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer " + TOKEN)
                        .header("X-ELMOS-Tenant-Id", envelope.tenantId())
                        .header("X-ELMOS-Worker-Id", envelope.workerId())
                        .header("X-ELMOS-Attempt-Id", envelope.attemptId())
                        .header("X-ELMOS-Fencing-Token", envelope.fencingToken())
                        .header("Idempotency-Key", envelope.dispatchIdempotencyKey())
                        .content(json.writeValueAsBytes(envelope)))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value("ACKED"));

        mvc.perform(post("/internal/v1/production-runtime/dispatch")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer " + TOKEN)
                        .header("X-ELMOS-Tenant-Id", UUID.randomUUID())
                        .header("X-ELMOS-Worker-Id", envelope.workerId())
                        .header("X-ELMOS-Attempt-Id", envelope.attemptId())
                        .header("X-ELMOS-Fencing-Token", envelope.fencingToken())
                        .header("Idempotency-Key", envelope.dispatchIdempotencyKey())
                        .content(json.writeValueAsBytes(envelope)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("WORKER_DISPATCH_HEADER_MISMATCH"));

        mvc.perform(post("/internal/v1/production-runtime/dispatch")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer wrong")
                        .header("X-ELMOS-Tenant-Id", envelope.tenantId())
                        .header("X-ELMOS-Worker-Id", envelope.workerId())
                        .header("X-ELMOS-Attempt-Id", envelope.attemptId())
                        .header("X-ELMOS-Fencing-Token", envelope.fencingToken())
                        .header("Idempotency-Key", envelope.dispatchIdempotencyKey())
                        .content(json.writeValueAsBytes(envelope)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("WORKER_AUTH_INVALID"));
    }
}
