package io.elmos.testquality;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class Batch18ContractFixtureTest {
    private final Path root = Path.of(System.getProperty("basedir")).resolve("../..").normalize();
    private final ObjectMapper json = new ObjectMapper();

    @Test void eightSchemasAndFixturesAreParseable() throws Exception {
        var schemas = List.of(
                "contracts/test-case-schema/test-case-identity.schema.json",
                "contracts/test-result-schema/test-result.schema.json",
                "contracts/quality-risk-schema/quality-risk.schema.json",
                "contracts/contract-test-schema/contract-verification.schema.json",
                "contracts/property-test-schema/property-test-result.schema.json",
                "contracts/mutation-schema/mutation-result.schema.json",
                "contracts/flaky-schema/flaky-test-profile.schema.json",
                "contracts/quality-decision-schema/quality-decision.schema.json");
        for (String schema : schemas) {
            JsonNode node = json.readTree(root.resolve(schema).toFile());
            assertEquals("https://json-schema.org/draft/2020-12/schema", node.get("$schema").asText());
            assertFalse(node.get("required").isEmpty());
        }
        try (var files = Files.list(root.resolve("engines/test-quality-engine/test-fixtures"))) {
            for (Path fixture : files.filter(path -> path.toString().endsWith(".json")).toList()) json.readTree(fixture.toFile());
        }
    }

    @Test void fixtureMatrixAndAllThirtyScenariosArePresent() throws Exception {
        JsonNode matrix = json.readTree(root.resolve("engines/test-quality-engine/test-fixtures/fixture-matrix.json").toFile());
        assertEquals(9, matrix.size());
        JsonNode scenarios = json.readTree(root.resolve("engines/test-quality-engine/test-fixtures/batch18-acceptance-scenarios.json").toFile());
        assertEquals(30, scenarios.size());
        for (int index = 0; index < 30; index++) assertEquals(index + 1, scenarios.get(index).get("id").asInt());
    }
}
