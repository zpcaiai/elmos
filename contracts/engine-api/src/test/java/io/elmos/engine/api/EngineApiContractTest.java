package io.elmos.engine.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EngineApiContractTest {
    @Test void oldClientIgnoresUnknownFields() throws Exception {
        var json = """
                {"organizationId":"org-1","repositorySnapshotRef":"artifact:snap","workspaceRef":"workspace:1",
                 "profile":"java-health","correlationId":"corr-1","idempotencyKey":"idem-1","futureField":true}
                """;
        var request = new ObjectMapper().readValue(json, EngineApi.JobRequest.class);
        assertEquals("idem-1", request.idempotencyKey());
    }

    @Test void openApiDocumentsFailClosedNotRunAndConflictSemantics() throws IOException {
        try (var stream = getClass().getResourceAsStream("/engine-api.yaml")) {
            assertTrue(stream != null, "engine-api.yaml must be packaged");
            var contract = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
            assertTrue(contract.contains("configured=false"));
            assertTrue(contract.contains("executed=false"));
            assertTrue(contract.contains("#/components/responses/JobConflict"));
            assertFalse(contract.contains("artifact://simulated"));
        }
    }
}
