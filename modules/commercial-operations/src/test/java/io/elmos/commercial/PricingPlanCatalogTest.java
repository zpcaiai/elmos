package io.elmos.commercial;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.*;

class PricingPlanCatalogTest {
    @Test
    void activePriceVersionIsImmutable() {
        var catalog = PricingPlanCatalog.chinaSelfServeDraft();

        assertEquals(PricingPlanCatalog.CATALOG_VERSION, catalog.catalogVersion());
        assertThrows(UnsupportedOperationException.class, () -> catalog.plans().clear());
        assertThrows(UnsupportedOperationException.class, () -> catalog.meters().clear());
        assertThrows(UnsupportedOperationException.class, () -> catalog.plans().getFirst().features().clear());
    }

    @Test
    void cnyPlansExposeExactTokenAndCreditAllowances() {
        var trial = PricingPlanCatalog.requirePlan("elmos-free-trial");
        var monthly = PricingPlanCatalog.requirePlan("elmos-pro-monthly");
        var annual = PricingPlanCatalog.requirePlan("elmos-pro-annual");

        assertEquals(new BigDecimal("0.00"), trial.price().amount());
        assertEquals(new BigDecimal("2000000"), trial.allowance().modelTokens());
        assertEquals(new BigDecimal("60"), trial.allowance().platformCredits());

        assertEquals(new BigDecimal("129.00"), monthly.price().amount());
        assertEquals(new BigDecimal("20000000"), monthly.allowance().modelTokens());
        assertEquals(new BigDecimal("600"), monthly.allowance().platformCredits());

        assertEquals(new BigDecimal("1290.00"), annual.price().amount());
        assertEquals(new BigDecimal("25000000"), annual.allowance().modelTokens());
        assertEquals(new BigDecimal("750"), annual.allowance().platformCredits());
        assertEquals(new BigDecimal("300000000"), annual.annualTokenCeiling());
        assertEquals(new BigDecimal("9000"), annual.annualCreditCeiling());
        assertEquals("CNY", annual.price().currency());
        assertFalse(annual.allowance().rollover());
    }

    @Test
    void draftCatalogCannotFulfillOrders() {
        var catalog = PricingPlanCatalog.chinaSelfServeDraft();

        assertEquals(PricingPlanCatalog.CatalogStatus.DRAFT, catalog.status());
        assertEquals("NOT_CONFIGURED", catalog.paymentStatus());
        assertThrows(IllegalStateException.class, PricingPlanCatalog::requireOrderable);
    }

    @Test
    void missingUsageIsNotPresentedAsZero() {
        var catalog = PricingPlanCatalog.chinaSelfServeDraft();

        assertTrue(catalog.limitations().stream()
                .anyMatch(value -> value.contains("not treated as zero")));
        assertEquals("HARD_STOP_NO_AUTOMATIC_CHARGE", catalog.overagePolicy());
    }

    @Test
    void tokenAndCreditLimitsAreEvaluatedTogether() {
        var allowed = PricingPlanCatalog.previewUsage(
                "elmos-pro-monthly",
                new BigDecimal("19000000"),
                new BigDecimal("560"),
                new BigDecimal("1000000"),
                new BigDecimal("40")
        );
        assertEquals(PricingPlanCatalog.UsageDecisionType.ALLOW, allowed.decision());
        assertEquals(BigDecimal.ZERO, allowed.remainingTokens());
        assertEquals(BigDecimal.ZERO, allowed.remainingCredits());

        var tokenDenied = PricingPlanCatalog.previewUsage(
                "elmos-pro-monthly",
                new BigDecimal("19000000"),
                new BigDecimal("0"),
                new BigDecimal("1000001"),
                BigDecimal.ZERO
        );
        assertEquals(PricingPlanCatalog.UsageDecisionType.DENY_TOKEN_LIMIT, tokenDenied.decision());
        assertEquals(new BigDecimal("1000000"), tokenDenied.remainingTokens());

        var creditDenied = PricingPlanCatalog.previewUsage(
                "elmos-pro-annual",
                BigDecimal.ZERO,
                new BigDecimal("749"),
                BigDecimal.ZERO,
                new BigDecimal("2")
        );
        assertEquals(PricingPlanCatalog.UsageDecisionType.DENY_CREDIT_LIMIT, creditDenied.decision());
        assertEquals(BigDecimal.ONE, creditDenied.remainingCredits());
    }

    @Test
    void creditScheduleUsesExactIntegerQuantities() {
        assertEquals(new BigDecimal("40"),
                PricingPlanCatalog.priceCredits("verified-generation-or-migration", BigDecimal.ONE));
        assertEquals(new BigDecimal("90"),
                PricingPlanCatalog.priceCredits("migration-or-translation-plan", new BigDecimal("6")));
        assertThrows(IllegalArgumentException.class,
                () -> PricingPlanCatalog.priceCredits("isolated-runner-minute", new BigDecimal("0.5")));
    }
}
