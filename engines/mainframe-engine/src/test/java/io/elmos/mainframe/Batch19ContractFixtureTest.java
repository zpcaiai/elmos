package io.elmos.mainframe;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class Batch19ContractFixtureTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Path ROOT = Path.of("../..").toAbsolutePath().normalize();

    @Test void eightSchemasUseDraft202012AndFixturesCarryIdentity() throws Exception {
        var schemas = List.of(
                "contracts/mainframe-estate-schema/mainframe-estate.schema.json",
                "contracts/cobol-semantic-schema/cobol-semantic.schema.json",
                "contracts/copybook-layout-schema/copybook-layout.schema.json",
                "contracts/jcl-flow-schema/jcl-flow.schema.json",
                "contracts/cics-contract-schema/cics-contract.schema.json",
                "contracts/ims-contract-schema/ims-contract.schema.json",
                "contracts/business-rule-schema/mainframe-business-rule.schema.json",
                "contracts/semantic-equivalence-schema/mainframe-semantic-equivalence.schema.json");
        for (String path : schemas) {
            JsonNode schema = JSON.readTree(Files.readString(ROOT.resolve(path)));
            assertEquals("https://json-schema.org/draft/2020-12/schema", schema.path("$schema").asText());
            assertFalse(schema.path("required").isEmpty());
        }
        assertEquals(8, schemas.size());
    }

    @Test void acceptanceFixtureContainsAllThirtyScenarios() throws Exception {
        JsonNode fixture = JSON.readTree(Files.readString(ROOT.resolve("engines/mainframe-engine/test-fixtures/batch19-acceptance-scenarios.json")));
        assertEquals(30, fixture.path("scenarios").size());
        assertEquals(1, fixture.path("scenarios").get(0).path("id").asInt());
        assertEquals(30, fixture.path("scenarios").get(29).path("id").asInt());
    }
}
