package io.elmos.commercialapi;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CommercialControllerTest {
    @Test void commercialBoundaryKeepsExternalFinanceOutOfScope() {
        var capabilities = new CommercialController().capabilities();
        assertEquals("AVAILABLE", capabilities.get("entitlement"));
        assertEquals("NOT_CONFIGURED", capabilities.get("externalCrm"));
        assertEquals("OUT_OF_SCOPE", capabilities.get("formalAccounting"));
    }

    @Test void pricingCatalogUsesCnyAndRemainsFailClosedForPayment() {
        var controller = new CommercialController();
        var catalog = controller.pricingCatalog();

        assertEquals("CNY", catalog.currency());
        assertEquals("DRAFT", catalog.status().name());
        assertEquals("NOT_CONFIGURED", catalog.paymentStatus());
        assertEquals(new BigDecimal("129.00"), catalog.plans().get(1).price().amount());
        assertEquals(new BigDecimal("20000000"), catalog.plans().get(1).allowance().modelTokens());
        assertEquals(new BigDecimal("600"), catalog.plans().get(1).allowance().platformCredits());
    }

    @Test void usagePreviewRejectsRequestsBeyondEitherAllowance() {
        var controller = new CommercialController();
        var decision = controller.usagePreview(new CommercialController.UsagePreviewRequest(
                "elmos-free-trial",
                new BigDecimal("1900000"),
                new BigDecimal("60"),
                new BigDecimal("100000"),
                BigDecimal.ONE
        ));

        assertEquals("DENY_CREDIT_LIMIT", decision.decision().name());
        assertEquals(BigDecimal.ZERO, decision.remainingCredits());
    }
}
