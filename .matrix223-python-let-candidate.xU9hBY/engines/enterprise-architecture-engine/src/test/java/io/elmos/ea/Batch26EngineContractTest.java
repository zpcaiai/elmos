package io.elmos.ea;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.executiondomain.DomainDefinitions;
import io.elmos.executiondomain.EvidenceBoundDomainEngine;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class Batch26EngineContractTest {
    @Test void applicationAndAllAcceptanceScenariosArePackaged() throws Exception {
        assertNotNull(new EnterpriseArchitectureEngineApplication());
        try (var input = getClass().getResourceAsStream("/batch26-acceptance-scenarios.json")) {
            var scenarios = new ObjectMapper().readTree(input);
            assertEquals(50, scenarios.size());
            scenarios.forEach(s -> { assertEquals("FAIL_CLOSED", s.path("safeOutcome").asText()); assertFalse(s.path("autoApprovalAllowed").asBoolean()); });
        }
    }
    @Test void enterpriseArchitectureEngineHasThirteenUnavailableAdapters() {
        var capabilities = new EvidenceBoundDomainEngine(DomainDefinitions.enterpriseArchitecture()).capabilities();
        assertEquals("ELMOS_ENTERPRISE_ARCHITECTURE", capabilities.engineName());
        assertEquals(13, capabilities.supportedFrameworks().size());
    }
}
