package io.elmos.integration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class Batch20ContractFixtureTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Path ROOT = Path.of("../..").toAbsolutePath().normalize();

    @Test void sevenSchemasUseDraft202012AndRequireIdentity() throws Exception {
        var schemas = List.of(
                "contracts/integration-estate-schema/integration-estate.schema.json",
                "contracts/integration-route-schema/integration-route.schema.json",
                "contracts/message-contract-schema/message-contract.schema.json",
                "contracts/delivery-policy-schema/message-delivery-policy.schema.json",
                "contracts/partner-agreement-schema/trading-partner-agreement.schema.json",
                "contracts/workflow-schema/workflow.schema.json",
                "contracts/integration-cutover-schema/integration-cutover-decision.schema.json");
        for (String path : schemas) {
            JsonNode schema = JSON.readTree(Files.readString(ROOT.resolve(path)));
            assertEquals("https://json-schema.org/draft/2020-12/schema", schema.path("$schema").asText());
            assertFalse(schema.path("required").isEmpty());
        }
        assertEquals(7, schemas.size());
    }

    @Test void acceptanceAndFixtureMatrixCoverAllRequiredDomains() throws Exception {
        JsonNode fixture = JSON.readTree(Files.readString(ROOT.resolve(
                "engines/enterprise-integration-engine/test-fixtures/batch20-acceptance-scenarios.json")));
        assertEquals(30, fixture.path("scenarios").size());
        assertEquals(1, fixture.path("scenarios").get(0).path("id").asInt());
        assertEquals(30, fixture.path("scenarios").get(29).path("id").asInt());
        JsonNode matrix = JSON.readTree(Files.readString(ROOT.resolve(
                "engines/enterprise-integration-engine/test-fixtures/fixture-matrix.json")));
        var domains = new ArrayList<String>();
        matrix.path("domains").fieldNames().forEachRemaining(domains::add);
        assertEquals(List.of("api-gateway", "b2b", "cutover", "esb", "ibm-mq", "kafka", "rabbitmq", "workflow"),
                domains.stream().sorted().toList());
    }
}
