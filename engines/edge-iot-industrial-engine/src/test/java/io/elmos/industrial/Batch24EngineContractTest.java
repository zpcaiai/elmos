package io.elmos.industrial;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.executiondomain.DomainDefinitions;
import io.elmos.executiondomain.EvidenceBoundDomainEngine;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class Batch24EngineContractTest {
    @Test void applicationAndAllAcceptanceScenariosArePackaged() throws Exception {
        assertNotNull(new EdgeIotIndustrialEngineApplication());
        try (var input = getClass().getResourceAsStream("/batch24-acceptance-scenarios.json")) {
            var scenarios = new ObjectMapper().readTree(input);
            assertEquals(36, scenarios.size());
            scenarios.forEach(s -> { assertEquals("FAIL_CLOSED", s.path("safeOutcome").asText()); assertFalse(s.path("autoApprovalAllowed").asBoolean()); });
        }
    }
    @Test void industrialEngineHasElevenUnavailableAdapters() {
        var capabilities = new EvidenceBoundDomainEngine(DomainDefinitions.industrial()).capabilities();
        assertEquals("ELMOS_EDGE_IOT_INDUSTRIAL", capabilities.engineName());
        assertEquals(11, capabilities.supportedFrameworks().size());
    }
}
