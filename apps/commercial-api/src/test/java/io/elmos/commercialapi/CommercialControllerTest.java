package io.elmos.commercialapi;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CommercialControllerTest {
    @Test void commercialBoundaryKeepsExternalFinanceOutOfScope() {
        var capabilities = new CommercialController().capabilities();
        assertEquals("AVAILABLE", capabilities.get("entitlement"));
        assertEquals("NOT_CONFIGURED", capabilities.get("externalCrm"));
        assertEquals("OUT_OF_SCOPE", capabilities.get("formalAccounting"));
    }
}
