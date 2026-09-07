package io.elmos.engine.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

class EngineApiContractTest {
    @Test void oldClientIgnoresUnknownFields() throws Exception {
        var json = """
                {"organizationId":"org-1","repositorySnapshotRef":"artifact:snap","workspaceRef":"workspace:1",
                 "profile":"java-health","correlationId":"corr-1","idempotencyKey":"idem-1","futureField":true}
                """;
        var request = new ObjectMapper().readValue(json, EngineApi.JobRequest.class);
        assertEquals("idem-1", request.idempotencyKey());
        assertEquals(Map.of(), request.options());
    }

    @Test void optionsArePreservedAndParticipateInTheTypedRequest() throws Exception {
        var json = """
                {"organizationId":"org-1","repositorySnapshotRef":"artifact:snap","workspaceRef":"workspace:1",
                 "profile":"java-health","correlationId":"corr-1","idempotencyKey":"idem-1",
                 "options":{"mode":"strict","attempt":2,"nullable":null,"nested":{"z":1,"a":2}}}
                """;
        var request = new ObjectMapper().readValue(json, EngineApi.JobRequest.class);
        assertEquals("strict", request.options().get("mode"));
        assertEquals(2, request.options().get("attempt"));
        assertTrue(request.options().containsKey("nullable"));
        assertNull(request.options().get("nullable"));
        assertThrows(UnsupportedOperationException.class, () -> request.options().put("mode", "permissive"));

        var reordered = new EngineApi.JobRequest("org-1", "artifact:snap", "workspace:1", "java-health",
                "corr-1", "idem-1", Map.of("nested", Map.of("a", 2, "z", 1), "attempt", 2,
                "mode", "strict"));
        var withoutNull = new EngineApi.JobRequest(request.organizationId(), request.repositorySnapshotRef(),
                request.workspaceRef(), request.profile(), request.correlationId(), request.idempotencyKey(),
                request.options().entrySet().stream().filter(entry -> entry.getValue() != null)
                        .collect(Collectors.toMap(Map.Entry::getKey, Map.Entry::getValue)));
        assertEquals(EngineApi.idempotencyMaterial(reordered), EngineApi.idempotencyMaterial(withoutNull),
                "map key order must not change idempotency material");
        var retriedWithNewTrace = new EngineApi.JobRequest(reordered.organizationId(), reordered.repositorySnapshotRef(),
                reordered.workspaceRef(), reordered.profile(), "corr-retry", reordered.idempotencyKey(), reordered.options());
        assertEquals(EngineApi.idempotencyMaterial(reordered), EngineApi.idempotencyMaterial(retriedWithNewTrace),
                "correlation ids are observability context, not immutable business input");
        assertNotEquals(EngineApi.idempotencyMaterial(request), EngineApi.idempotencyMaterial(reordered),
                "adding an explicit null option remains a semantic input change");
        var delimiterLikeValue = new EngineApi.JobRequest("org-1", "artifact:snap", "workspace:1", "java-health",
                "corr", "collision", Map.of("a", "b, c=d"));
        var separateEntries = new EngineApi.JobRequest("org-1", "artifact:snap", "workspace:1", "java-health",
                "corr", "collision", Map.of("a", "b", "c", "d"));
        assertNotEquals(EngineApi.idempotencyMaterial(delimiterLikeValue), EngineApi.idempotencyMaterial(separateEntries),
                "map delimiters inside user values must not create fingerprint collisions");
    }

    @Test void invalidNestedExecutionInputsFailBeforeAnyEngineCanRun() {
        assertThrows(IllegalArgumentException.class, () -> new EngineApi.ExecutionBudget(0, 1, 1, 0));
        assertThrows(IllegalArgumentException.class, () -> new EngineApi.ExecutionBudget(1, -1, 1, 0));
        assertThrows(IllegalArgumentException.class, () -> new EngineApi.ExecutionBudget(1, 1, -1, 0));
        assertThrows(IllegalArgumentException.class, () -> new EngineApi.ExecuteStepRequest(
                "org", "run", 0, new EngineApi.StepDefinition("step", EngineApi.ExecutorType.SCANNER, Map.of()),
                "workspace", "sha", new EngineApi.ExecutionBudget(1, 1, 0, 0), Map.of(), "corr", "idem"));
    }

    @Test void openApiDocumentsFailClosedNotRunAndConflictSemantics() throws IOException {
        try (var stream = getClass().getResourceAsStream("/engine-api.yaml")) {
            assertTrue(stream != null, "engine-api.yaml must be packaged");
            var contract = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
            assertTrue(contract.contains("configured=false"));
            assertTrue(contract.contains("executed=false"));
            assertTrue(contract.contains("#/components/responses/JobConflict"));
            assertTrue(contract.contains("#/components/responses/JobNotFound"));
            assertTrue(contract.contains("executionBudget: { $ref: '#/components/schemas/ExecutionBudget' }"));
            assertFalse(contract.contains("artifact://simulated"));

            var matcher = Pattern.compile("executorType:\\s*\\R\\s*enum: \\[(?<values>[^]]+)]")
                    .matcher(contract);
            assertTrue(matcher.find(), "executorType enum must be explicit");
            Set<String> documented = Arrays.stream(matcher.group("values").split(","))
                    .map(String::trim).collect(Collectors.toSet());
            Set<String> implemented = EnumSet.allOf(EngineApi.ExecutorType.class).stream()
                    .map(Enum::name).collect(Collectors.toSet());
            assertEquals(implemented, documented, "OpenAPI executor types must exactly match the Java contract");
        }
    }
}
