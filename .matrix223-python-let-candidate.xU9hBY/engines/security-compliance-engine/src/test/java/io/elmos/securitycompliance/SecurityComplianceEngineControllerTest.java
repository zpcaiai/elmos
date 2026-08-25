package io.elmos.securitycompliance;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SecurityComplianceEngineControllerTest {
    @Test void exposesSecurityEngineCapabilities() {
        var controller = new SecurityComplianceEngineController(new SecurityComplianceEngineService());
        assertEquals("ELMOS_SECURITY_COMPLIANCE", controller.capabilities().engineName());
    }
}
