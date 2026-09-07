package io.elmos.securitycompliance;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class Batch17ContractFixtureTest {
    private final ObjectMapper json = new ObjectMapper();
    private final Path engineRoot = Path.of(System.getProperty("basedir"));
    private final Path repositoryRoot = engineRoot.resolve("../..").normalize();

    @Test void nineFixturesCarryEveryRequiredSchemaField() throws Exception {
        JsonNode matrix = json.readTree(engineRoot.resolve("test-fixtures/fixture-matrix.json").toFile());
        assertEquals(9, matrix.path("fixtures").size());
        assertEquals(61, matrix.path("scenarioFixtures").properties().stream()
                .mapToInt(entry -> entry.getValue().size()).sum());
        assertEquals("NOT_RUN", matrix.path("externalStatus").asText());
        for (JsonNode item : matrix.path("fixtures")) {
            JsonNode schema = json.readTree(repositoryRoot.resolve(item.path("schema").asText()).toFile());
            JsonNode instance = json.readTree(engineRoot.resolve("test-fixtures").resolve(item.path("instance").asText()).toFile());
            assertEquals("https://json-schema.org/draft/2020-12/schema", schema.path("$schema").asText());
            for (JsonNode required : schema.path("required")) {
                assertTrue(instance.has(required.asText()), item.path("instance").asText() + " missing " + required.asText());
            }
        }
    }

    @Test void acceptanceManifestDeclaresThirtyScenariosExactlyOnce() throws Exception {
        JsonNode fixture = json.readTree(engineRoot.resolve("test-fixtures/batch17-acceptance-scenarios.json").toFile());
        List<Integer> ids = new ArrayList<>(); fixture.path("scenarios").forEach(value -> ids.add(value.path("id").asInt()));
        assertEquals(java.util.stream.IntStream.rangeClosed(1, 30).boxed().toList(), ids);
    }

    @Test void adapterPolicyAndOpenApiStayFailClosed() throws Exception {
        JsonNode policy = json.readTree(engineRoot.resolve("policies/security-tool-adapters-v1.json").toFile());
        assertEquals("DENY", policy.path("defaultNetwork").asText());
        assertEquals(18, policy.path("adapters").size()); assertFalse(policy.path("secretValuesInEvidence").asBoolean());
        assertFalse(policy.path("agentRiskAcceptanceAllowed").asBoolean());
        String openApi = Files.readString(repositoryRoot.resolve("contracts/security-compliance-api/security-compliance-engine-api.yaml"));
        assertTrue(openApi.contains("/engine/v1/authorize")); assertTrue(openApi.contains("ELMOS_SECURITY_COMPLIANCE"));
    }
}
