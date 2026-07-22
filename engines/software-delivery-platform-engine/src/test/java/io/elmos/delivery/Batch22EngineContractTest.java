package io.elmos.deliveryplatform;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.executiondomain.DomainDefinitions;
import io.elmos.executiondomain.EvidenceBoundDomainEngine;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class Batch22EngineContractTest {
    @Test void applicationAndAllAcceptanceScenariosArePackaged() throws Exception {
        assertNotNull(new SoftwareDeliveryPlatformEngineApplication());
        try (var input = getClass().getResourceAsStream("/batch22-acceptance-scenarios.json")) {
            var scenarios = new ObjectMapper().readTree(input);
            assertEquals(36, scenarios.size());
            scenarios.forEach(s -> { assertEquals("FAIL_CLOSED", s.path("safeOutcome").asText()); assertFalse(s.path("autoApprovalAllowed").asBoolean()); });
        }
    }
    @Test void platformEngineHasFourteenUnavailableAdapters() {
        var capabilities = new EvidenceBoundDomainEngine(DomainDefinitions.softwareDelivery()).capabilities();
        assertEquals("ELMOS_SOFTWARE_DELIVERY_PLATFORM", capabilities.engineName());
        assertEquals(14, capabilities.supportedFrameworks().size());
    }
}
