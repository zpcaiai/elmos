package io.elmos.databasedata;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class Batch15ContractFixtureTest {
    private final ObjectMapper json = new ObjectMapper();
    private final Path engineRoot = Path.of(System.getProperty("basedir"));
    private final Path repositoryRoot = engineRoot.resolve("../..").normalize();

    @Test void fiveSchemaFixturesAreVersionedAndContainRequiredFields() throws Exception {
        JsonNode matrix = json.readTree(engineRoot.resolve("test-fixtures/fixture-matrix.json").toFile());
        assertEquals(5, matrix.path("fixtures").size());
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

    @Test void acceptanceManifestDeclaresAllTwentyFourScenariosExactlyOnce() throws Exception {
        JsonNode fixture = json.readTree(engineRoot.resolve(
                "test-fixtures/batch15-acceptance-scenarios.json").toFile());
        List<Integer> ids = new ArrayList<>();
        fixture.path("scenarios").forEach(value -> ids.add(value.path("id").asInt()));
        assertEquals(java.util.stream.IntStream.rangeClosed(1, 24).boxed().toList(), ids);
    }

    @Test void runnerPolicyAndOpenApiStayFailClosed() throws Exception {
        JsonNode policy = json.readTree(engineRoot.resolve("policies/runner-profiles-v1.json").toFile());
        assertEquals("DENY", policy.path("defaultNetwork").asText());
        assertEquals(6, policy.path("profiles").size());
        policy.path("profiles").forEach(profile ->
                assertEquals("NOT_CONFIGURED", profile.path("status").asText()));
        String openApi = Files.readString(repositoryRoot.resolve(
                "contracts/database-data-api/database-data-api.yaml"));
        assertTrue(openApi.contains("/engine/v1/execute-step"));
        assertTrue(openApi.contains("ELMOS_DATABASE_DATA"));
    }
}
