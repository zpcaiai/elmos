package io.elmos.infrastructure;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class Batch16ContractFixtureTest {
    private final ObjectMapper json = new ObjectMapper();
    private final Path engineRoot = Path.of(System.getProperty("basedir"));
    private final Path repositoryRoot = engineRoot.resolve("../..").normalize();

    @Test void nineSchemaFixturesAreVersionedAndContainRequiredFields() throws Exception {
        JsonNode matrix = json.readTree(engineRoot.resolve("test-fixtures/fixture-matrix.json").toFile());
        assertEquals(9, matrix.path("fixtures").size());
        assertEquals(62, matrix.path("categories").properties().stream()
                .mapToInt(entry -> entry.getValue().size()).sum());
        assertEquals("NOT_RUN", matrix.path("externalStatus").asText());
        for (JsonNode item : matrix.path("fixtures")) {
            JsonNode schema = json.readTree(repositoryRoot.resolve(item.path("schema").asText()).toFile());
            JsonNode instance = json.readTree(engineRoot.resolve("test-fixtures")
                    .resolve(item.path("instance").asText()).toFile());
            assertEquals("https://json-schema.org/draft/2020-12/schema", schema.path("$schema").asText());
            for (JsonNode required : schema.path("required")) {
                assertTrue(instance.has(required.asText()),
                        item.path("instance").asText() + " missing " + required.asText());
            }
        }
    }

    @Test void acceptanceManifestDeclaresAllTwentySixScenariosExactlyOnce() throws Exception {
        JsonNode fixture = json.readTree(engineRoot.resolve("test-fixtures/batch16-acceptance-scenarios.json").toFile());
        List<Integer> ids = new ArrayList<>();
        fixture.path("scenarios").forEach(value -> ids.add(value.path("id").asInt()));
        assertEquals(java.util.stream.IntStream.rangeClosed(1, 26).boxed().toList(), ids);
    }

    @Test void runnerPolicyAndOpenApiStayFailClosed() throws Exception {
        JsonNode policy = json.readTree(engineRoot.resolve("policies/runner-profiles-v1.json").toFile());
        assertEquals("DENY", policy.path("defaultNetwork").asText());
        assertEquals(6, policy.path("profiles").size());
        policy.path("profiles").forEach(profile -> assertEquals("NOT_CONFIGURED", profile.path("status").asText()));
        JsonNode adapters = json.readTree(engineRoot.resolve("policies/provider-adapter-policy-v1.json").toFile());
        assertFalse(adapters.path("providerCredentialsStored").asBoolean());
        assertFalse(adapters.path("privateKeysStored").asBoolean());
        String openApi = Files.readString(repositoryRoot.resolve("contracts/infrastructure-api/infrastructure-engine-api.yaml"));
        assertTrue(openApi.contains("/engine/v1/execute-step"));
        assertTrue(openApi.contains("ELMOS_INFRASTRUCTURE"));
    }
}
