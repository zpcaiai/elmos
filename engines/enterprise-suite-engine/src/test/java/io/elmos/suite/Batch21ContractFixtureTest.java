package io.elmos.suite;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class Batch21ContractFixtureTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Path ROOT = Path.of("../..").toAbsolutePath().normalize();

    @Test void eightSchemasUseDraft202012AndRequireIdentity() throws Exception {
        var schemas = List.of(
                "contracts/suite-estate-schema/suite-estate.schema.json",
                "contracts/suite-customization-schema/suite-customization.schema.json",
                "contracts/business-process-schema/business-process-step.schema.json",
                "contracts/enterprise-object-schema/enterprise-business-object.schema.json",
                "contracts/master-data-crosswalk-schema/master-data-crosswalk.schema.json",
                "contracts/suite-role-schema/suite-role.schema.json",
                "contracts/process-equivalence-schema/process-equivalence.schema.json",
                "contracts/suite-cutover-schema/suite-cutover-decision.schema.json");
        for (String path : schemas) {
            JsonNode schema = JSON.readTree(Files.readString(ROOT.resolve(path)));
            assertEquals("https://json-schema.org/draft/2020-12/schema", schema.path("$schema").asText());
            assertFalse(schema.path("required").isEmpty());
        }
        assertEquals(8, schemas.size());
    }

    @Test void acceptanceAndFixtureMatrixCoverAllRequiredDomains() throws Exception {
        JsonNode fixture = JSON.readTree(Files.readString(ROOT.resolve(
                "engines/enterprise-suite-engine/test-fixtures/batch21-acceptance-scenarios.json")));
        assertEquals(30, fixture.path("scenarios").size());
        assertEquals(1, fixture.path("scenarios").get(0).path("id").asInt());
        assertEquals(30, fixture.path("scenarios").get(29).path("id").asInt());
        JsonNode matrix = JSON.readTree(Files.readString(ROOT.resolve(
                "engines/enterprise-suite-engine/test-fixtures/fixture-matrix.json")));
        var domains = new ArrayList<String>();
        matrix.path("domains").fieldNames().forEachRemaining(domains::add);
        assertEquals(List.of("cutover", "dynamics", "master-data", "oracle", "process", "salesforce", "sap"),
                domains.stream().sorted().toList());
    }
}
