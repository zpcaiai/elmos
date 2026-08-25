package io.elmos.operations;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.executiondomain.DomainDefinitions;
import io.elmos.executiondomain.EvidenceBoundDomainEngine;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class Batch25EngineContractTest {
    @Test void applicationAndAllAcceptanceScenariosArePackaged() throws Exception {
        assertNotNull(new OperationsSreItsmEngineApplication());
        try (var input = getClass().getResourceAsStream("/batch25-acceptance-scenarios.json")) {
            var scenarios = new ObjectMapper().readTree(input);
            assertEquals(44, scenarios.size());
            scenarios.forEach(s -> { assertEquals("FAIL_CLOSED", s.path("safeOutcome").asText()); assertFalse(s.path("autoApprovalAllowed").asBoolean()); });
        }
    }
    @Test void operationsEngineHasFourteenUnavailableAdapters() {
        var capabilities = new EvidenceBoundDomainEngine(DomainDefinitions.operations()).capabilities();
        assertEquals("ELMOS_OPERATIONS_SRE_ITSM", capabilities.engineName());
        assertEquals(14, capabilities.supportedFrameworks().size());
    }
}
