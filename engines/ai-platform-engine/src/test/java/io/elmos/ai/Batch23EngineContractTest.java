package io.elmos.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.executiondomain.DomainDefinitions;
import io.elmos.executiondomain.EvidenceBoundDomainEngine;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class Batch23EngineContractTest {
    @Test void applicationAndAllAcceptanceScenariosArePackaged() throws Exception {
        assertNotNull(new AiPlatformEngineApplication());
        try (var input = getClass().getResourceAsStream("/batch23-acceptance-scenarios.json")) {
            var scenarios = new ObjectMapper().readTree(input);
            assertEquals(44, scenarios.size());
            scenarios.forEach(s -> { assertEquals("FAIL_CLOSED", s.path("safeOutcome").asText()); assertFalse(s.path("autoApprovalAllowed").asBoolean()); });
        }
    }
    @Test void aiEngineHasElevenUnavailableAdapters() {
        var capabilities = new EvidenceBoundDomainEngine(DomainDefinitions.aiPlatform()).capabilities();
        assertEquals("ELMOS_AI_PLATFORM", capabilities.engineName());
        assertEquals(11, capabilities.supportedFrameworks().size());
    }
}
