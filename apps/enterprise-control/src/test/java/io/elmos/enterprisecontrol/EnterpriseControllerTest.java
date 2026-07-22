package io.elmos.enterprisecontrol;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class EnterpriseControllerTest {
    @Test void externalAdaptersRemainFailClosedUntilConfigured() {
        var capabilities = new EnterpriseController().capabilities();
        assertEquals("AVAILABLE", capabilities.get("tenantPolicy"));
        assertEquals("NOT_CONFIGURED", capabilities.get("privateRunnerChannel"));
        assertEquals("NOT_CONFIGURED", capabilities.get("externalSecretProvider"));
    }
}
