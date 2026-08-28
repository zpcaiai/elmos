package io.elmos.commercial;

import static io.elmos.commercial.PricingBillingFinancialRuntime.CreditKind.PAID;
import static io.elmos.commercial.PricingBillingFinancialRuntime.CreditKind.PROMOTIONAL;
import static io.elmos.commercial.PricingBillingFinancialRuntime.EvidenceState.RECONCILED;
import static io.elmos.commercial.PricingBillingFinancialRuntime.InvoiceState.CREDITED;
import static io.elmos.commercial.PricingBillingFinancialRuntime.InvoiceState.ISSUED;
import static io.elmos.commercial.PricingBillingFinancialRuntime.InvoiceState.PARTIALLY_PAID;
import static io.elmos.commercial.PricingBillingFinancialRuntime.MetricState.AVAILABLE;
import static io.elmos.commercial.PricingBillingFinancialRuntime.ReservationState.COMMITTED;
import static io.elmos.commercial.PricingBillingFinancialRuntime.ReservationState.RELEASED;
import static io.elmos.commercial.PricingBillingFinancialRuntime.TaxState.CALCULATED;
import static io.elmos.commercial.PricingBillingFinancialRuntime.UsageDecision.LATE_REVIEW;
import static io.elmos.commercial.PricingBillingFinancialRuntime.UsageFactType.CORRECTION;
import static io.elmos.commercial.PricingBillingFinancialRuntime.UsageFactType.ORIGINAL;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.elmos.commercial.PricingBillingFinancialRuntime.FinancialFact;
import io.elmos.commercial.PricingBillingFinancialRuntime.FxRate;
import io.elmos.commercial.PricingBillingFinancialRuntime.InvoiceBook;
import io.elmos.commercial.PricingBillingFinancialRuntime.InvoiceLine;
import io.elmos.commercial.PricingBillingFinancialRuntime.MarginAnalyzer;
import io.elmos.commercial.PricingBillingFinancialRuntime.MetricDefinition;
import io.elmos.commercial.PricingBillingFinancialRuntime.Money;
import io.elmos.commercial.PricingBillingFinancialRuntime.PaymentEvidence;
import io.elmos.commercial.PricingBillingFinancialRuntime.Scope;
import io.elmos.commercial.PricingBillingFinancialRuntime.TaxDecision;
import io.elmos.commercial.PricingBillingFinancialRuntime.UsageCommand;
import io.elmos.commercial.PricingBillingFinancialRuntime.UsageMeter;
import io.elmos.commercial.PricingBillingFinancialRuntime.WalletLedger;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class PricingBillingFinancialRuntimeTest {
    private static final Scope SCOPE = new Scope("tenant-a", "legal-cn");
    private static final Scope OTHER_SCOPE = new Scope("tenant-b", "legal-cn");
    private static final Instant START = Instant.parse("2026-08-01T00:00:00Z");
    private static final Instant END = Instant.parse("2026-09-01T00:00:00Z");

    @Test
    void bindsExactlyFortyNamespacedRequirements() {
        assertEquals(40, PricingBillingFinancialRuntime.REQUIREMENT_BINDINGS.size());
        assertTrue(PricingBillingFinancialRuntime.REQUIREMENT_BINDINGS
                .containsKey("elmos.pricing-billing.v1/EB04-001"));
        assertTrue(PricingBillingFinancialRuntime.REQUIREMENT_BINDINGS
                .containsKey("elmos.pricing-billing.v1/EB13-010"));
        assertEquals("NOT_CERTIFIED", PricingBillingFinancialRuntime.CERTIFICATION_STATE);
    }

    @Test
    void walletUsesAppendOnlyBalancedJournalAndOptimisticVersioning() {
        WalletLedger ledger = new WalletLedger();
        var granted = ledger.grant(SCOPE, "wallet-1", "paid-1", PAID, decimal("100"),
                "credit", START, END, "grant-1", 0, "PAID_PURCHASE");
        assertEquals(decimal("100"), granted.available());
        var reserved = ledger.reserve(SCOPE, "wallet-1", "reservation-1", decimal("35"),
                "credit", START.plusSeconds(1), "reserve-1", granted.version());
        assertEquals(decimal("65"), reserved.available());
        assertEquals(decimal("35"), reserved.reserved());
        assertThrows(IllegalStateException.class, () -> ledger.reserve(SCOPE, "wallet-1",
                "reservation-2", decimal("1"), "credit", START.plusSeconds(2),
                "reserve-stale", granted.version()));

        var committed = ledger.commit(SCOPE, "wallet-1", "reservation-1",
                START.plusSeconds(3), "commit-1", reserved.version());
        assertEquals(decimal("65"), committed.available());
        assertEquals(BigDecimal.ZERO, committed.reserved());
        assertEquals(COMMITTED, committed.reservations().get("reservation-1").state());
        assertTrue(ledger.journal(SCOPE, "wallet-1").stream()
                .allMatch(entry -> !entry.debitAccount().equals(entry.creditAccount())
                        && entry.amount().signum() > 0));
        assertEquals(ledger.journal(SCOPE, "wallet-1").size(), ledger.outbox().size());
    }

    @Test
    void walletIsIdempotentTenantIsolatedAndUsesExpiryThenPromotionOrdering() {
        WalletLedger ledger = new WalletLedger();
        var first = ledger.grant(SCOPE, "wallet", "paid", PAID, decimal("10"), "credit",
                START, END, "grant-paid", 0, "PAID_PURCHASE");
        var second = ledger.grant(SCOPE, "wallet", "promo", PROMOTIONAL, decimal("8"), "credit",
                START, END, "grant-promo", first.version(), "PROMOTION");
        var replay = ledger.grant(SCOPE, "wallet", "promo", PROMOTIONAL, decimal("8"), "credit",
                START, END, "grant-promo", first.version(), "PROMOTION");
        assertEquals(second, replay);

        var reservation = ledger.reserve(SCOPE, "wallet", "r", decimal("12"), "credit",
                START.plusSeconds(1), "reserve", second.version());
        assertEquals(decimal("8"), reservation.reservations().get("r").allocations().get("promo"));
        assertEquals(decimal("4"), reservation.reservations().get("r").allocations().get("paid"));
        var released = ledger.release(SCOPE, "wallet", "r", START.plusSeconds(2),
                "release", reservation.version());
        assertEquals(RELEASED, released.reservations().get("r").state());
        assertEquals(decimal("18"), released.available());
        assertEquals(BigDecimal.ZERO, ledger.balance(OTHER_SCOPE, "wallet", START).available());
        assertThrows(IllegalStateException.class, () -> ledger.grant(SCOPE, "wallet", "promo",
                PROMOTIONAL, decimal("9"), "credit", START, END, "grant-promo", first.version(),
                "PROMOTION"));
    }

    @Test
    void walletExpiryIsExplicitAndCannotSpendExpiredLots() {
        WalletLedger ledger = new WalletLedger();
        var granted = ledger.grant(SCOPE, "wallet", "short", PROMOTIONAL, decimal("5"), "credit",
                START, START.plusSeconds(60), "grant", 0, "PROMOTION");
        assertEquals(BigDecimal.ZERO,
                ledger.balance(SCOPE, "wallet", START.plusSeconds(61)).available());
        var expired = ledger.expire(SCOPE, "wallet", START.plusSeconds(61),
                "expire", granted.version());
        assertEquals(BigDecimal.ZERO, expired.available());
        assertThrows(IllegalStateException.class, () -> ledger.reserve(SCOPE, "wallet", "r",
                BigDecimal.ONE, "credit", START.plusSeconds(62), "reserve", expired.version()));
    }

    @Test
    void usageDeduplicatesCorrectsAndQuarantinesLateEvents() {
        UsageMeter meter = new UsageMeter();
        UsageCommand original = usage("cmd-1", "u-1", "provider-1", decimal("10"), ORIGINAL,
                null, null, START.plusSeconds(10), END.plus(Duration.ofHours(1)));
        var accepted = meter.ingest(original);
        assertTrue(accepted.billable());
        assertEquals(accepted, meter.ingest(original));

        UsageCommand correction = usage("cmd-2", "u-2", "provider-2", decimal("-2"), CORRECTION,
                "u-1", "provider correction", START.plusSeconds(10), END.plus(Duration.ofHours(2)));
        meter.ingest(correction);
        assertEquals(decimal("8"), meter.billableQuantity(SCOPE, "runner.seconds", START, END, "second"));

        UsageCommand late = usage("cmd-3", "u-3", "provider-3", decimal("4"), ORIGINAL,
                null, null, START.plusSeconds(20), END.plus(Duration.ofDays(2)));
        var quarantined = meter.ingest(late);
        assertEquals(LATE_REVIEW, quarantined.decision());
        assertFalse(quarantined.billable());
        assertEquals(decimal("8"), meter.billableQuantity(SCOPE, "runner.seconds", START, END, "second"));
        assertEquals(3, meter.outbox().size());
    }

    @Test
    void usageRejectsIdentityCollisionsAndCrossContractCorrections() {
        UsageMeter meter = new UsageMeter();
        meter.ingest(usage("cmd", "u-1", "provider", decimal("10"), ORIGINAL,
                null, null, START.plusSeconds(1), END));
        assertThrows(IllegalStateException.class, () -> meter.ingest(usage("cmd", "u-2",
                "provider-2", decimal("11"), ORIGINAL, null, null, START.plusSeconds(2), END)));
        UsageCommand wrongScopeCorrection = new UsageCommand("other-cmd", OTHER_SCOPE, "u-2",
                "source", "other", "runner.seconds", decimal("-1"), "second", CORRECTION,
                "u-1", "wrong tenant", START.plusSeconds(1), END, START, END,
                Duration.ofDays(1), "normalizer-v1", Map.of());
        assertThrows(IllegalStateException.class, () -> meter.ingest(wrongScopeCorrection));
    }

    @Test
    void unknownTaxAndUnreconciledPaymentFailClosed() {
        InvoiceBook invoices = new InvoiceBook();
        var unknownLine = line("line-1", PricingBillingFinancialRuntime.TaxState.UNKNOWN);
        var draft = invoices.createDraft(SCOPE, "invoice-1", List.of(unknownLine),
                "maker", "create", END);
        var review = invoices.submitForReview(SCOPE, "invoice-1", draft.version(),
                "review", "maker", END.plusSeconds(1));
        assertThrows(IllegalStateException.class, () -> invoices.finalizeInvoice(SCOPE,
                "invoice-1", review.version(), "finalize", "checker", END.plusSeconds(2)));

        InvoiceBook payable = issuedInvoice();
        var issued = payable.invoice(SCOPE, "invoice-payable");
        PaymentEvidence unknownPayment = new PaymentEvidence("pay-1", money("25"),
                PricingBillingFinancialRuntime.EvidenceState.UNKNOWN, RECONCILED,
                null, "bank-evidence", END.plusSeconds(20));
        assertThrows(IllegalStateException.class, () -> payable.recordPayment(SCOPE,
                "invoice-payable", issued.version(), "pay-command", "cashier", unknownPayment));
        assertEquals(ISSUED, payable.invoice(SCOPE, "invoice-payable").state());
    }

    @Test
    void invoiceSeparatesPartialPaidAndCreditedStatesWithLineage() {
        InvoiceBook invoices = issuedInvoice();
        var issued = invoices.invoice(SCOPE, "invoice-payable");
        assertEquals(money("100"), issued.total());
        assertEquals(Set.of("usage:u-1", "price:p-v1"), issued.lines().get(0).sourceFactRefs());
        var partial = invoices.recordPayment(SCOPE, "invoice-payable", issued.version(),
                "pay-1", "cashier", reconciledPayment("provider-pay-1", "40"));
        assertEquals(PARTIALLY_PAID, partial.state());
        assertEquals(money("60"), partial.balanceDue());
        assertEquals("provider:provider-pay-1", invoices.events(SCOPE, "invoice-payable")
                .stream().filter(event -> event.paymentEvidence() != null).findFirst()
                .orElseThrow().paymentEvidence().providerEvidenceRef());
        var paid = invoices.recordPayment(SCOPE, "invoice-payable", partial.version(),
                "pay-2", "cashier", reconciledPayment("provider-pay-2", "60"));
        assertEquals(PricingBillingFinancialRuntime.InvoiceState.PAID, paid.state());
        var credited = invoices.issueCreditNote(SCOPE, "invoice-payable", paid.version(),
                "credit-command", "checker", "credit-note-1", money("100"), END.plusSeconds(40));
        assertEquals(CREDITED, credited.state());
        assertEquals(BigDecimal.ZERO, credited.balanceDue().amount());
        assertEquals(invoices.events(SCOPE, "invoice-payable").size(), invoices.outbox().size());
    }

    @Test
    void invoiceRequiresMakerCheckerAndRejectsStaleVersion() {
        InvoiceBook invoices = new InvoiceBook();
        var draft = invoices.createDraft(SCOPE, "invoice", List.of(line("line", CALCULATED)),
                "maker", "create", END);
        var review = invoices.submitForReview(SCOPE, "invoice", draft.version(),
                "review", "maker", END.plusSeconds(1));
        assertThrows(IllegalStateException.class, () -> invoices.finalizeInvoice(SCOPE,
                "invoice", review.version(), "final", "maker", END.plusSeconds(2)));
        assertThrows(IllegalStateException.class, () -> invoices.issue(SCOPE,
                "invoice", draft.version(), "issue", "issuer", END.plusSeconds(3)));
    }

    @Test
    void marginUsesExactEffectiveFxAndVersionedDenominator() {
        MetricDefinition definition = new MetricDefinition("gross-margin", "v2",
                "tenant/legal-entity/month", "recognized-revenue", 6, RoundingMode.HALF_EVEN);
        FinancialFact revenue = fact("revenue", "SUBSCRIPTION_REVENUE", "CNY", "1000",
                RECONCILED, BigDecimal.ONE);
        FinancialFact runner = fact("runner", "RUNNER", "USD", "20",
                RECONCILED, BigDecimal.ONE);
        FinancialFact storage = fact("storage", "STORAGE", "CNY", "60",
                RECONCILED, BigDecimal.ONE);
        FxRate rate = new FxRate("USD", "CNY", decimal("7"), START, END,
                "fx:central-bank:2026-08", RECONCILED);
        var result = new MarginAnalyzer().grossMargin(SCOPE, definition, List.of(revenue),
                List.of(runner, storage), List.of(rate), "CNY", decimal("1000"),
                START.plusSeconds(100));
        assertEquals(AVAILABLE, result.state());
        assertEquals(decimal("0.800000"), result.value());
        assertEquals("v2", result.definition().version());
        assertEquals("recognized-revenue", result.definition().denominatorName());
        assertTrue(result.sourceRefs().contains("fx:central-bank:2026-08"));
    }

    @Test
    void marginReturnsUnknownForMissingFxUnreconciledOrIncompleteAllocation() {
        MetricDefinition definition = new MetricDefinition("gross-margin", "v1", "month",
                "revenue", 4, RoundingMode.HALF_EVEN);
        FinancialFact revenue = fact("revenue", "REVENUE", "CNY", "100",
                RECONCILED, BigDecimal.ONE);
        FinancialFact foreign = fact("cost", "PROVIDER", "USD", "1",
                RECONCILED, BigDecimal.ONE);
        var missingFx = new MarginAnalyzer().grossMargin(SCOPE, definition, List.of(revenue),
                List.of(foreign), List.of(), "CNY", decimal("100"), START.plusSeconds(1));
        assertEquals(PricingBillingFinancialRuntime.MetricState.UNKNOWN, missingFx.state());
        assertEquals("FX_RATE_MISSING_OR_UNRECONCILED", missingFx.reason());

        FinancialFact incomplete = fact("incomplete", "HUMAN_REVIEW", "CNY", "10",
                RECONCILED, decimal("0.8"));
        var unknownAllocation = new MarginAnalyzer().grossMargin(SCOPE, definition,
                List.of(revenue), List.of(incomplete), List.of(), "CNY", decimal("100"),
                START.plusSeconds(1));
        assertEquals(PricingBillingFinancialRuntime.MetricState.UNKNOWN, unknownAllocation.state());
        assertNotEquals(BigDecimal.ZERO, unknownAllocation.denominator());
    }

    private static UsageCommand usage(String commandId, String recordId, String sourceEventId,
                                      BigDecimal quantity,
                                      PricingBillingFinancialRuntime.UsageFactType factType,
                                      String correctionOf, String correctionReason,
                                      Instant eventTime, Instant receivedAt) {
        return new UsageCommand(commandId, SCOPE, recordId, "runner", sourceEventId,
                "runner.seconds", quantity, "second", factType, correctionOf, correctionReason,
                eventTime, receivedAt, START, END, Duration.ofDays(1), "normalizer-v1",
                Map.of("region", "cn-east"));
    }

    private static InvoiceBook issuedInvoice() {
        InvoiceBook invoices = new InvoiceBook();
        var draft = invoices.createDraft(SCOPE, "invoice-payable", List.of(line("line", CALCULATED)),
                "maker", "create", END);
        var review = invoices.submitForReview(SCOPE, "invoice-payable", draft.version(),
                "review", "maker", END.plusSeconds(1));
        var finalized = invoices.finalizeInvoice(SCOPE, "invoice-payable", review.version(),
                "finalize", "checker", END.plusSeconds(2));
        invoices.issue(SCOPE, "invoice-payable", finalized.version(),
                "issue", "issuer", END.plusSeconds(3));
        return invoices;
    }

    private static InvoiceLine line(String id,
                                    PricingBillingFinancialRuntime.TaxState taxState) {
        TaxDecision tax = taxState == CALCULATED
                ? new TaxDecision(CALCULATED, money("0"), "CN", "tax-v1", "tax:evidence")
                : new TaxDecision(PricingBillingFinancialRuntime.TaxState.UNKNOWN,
                        money("0"), "CN", "tax-v1", null);
        return new InvoiceLine(id, "runner usage", decimal("10"), money("10"), tax,
                "price-v1", START, END, Set.of("usage:u-1", "price:p-v1"));
    }

    private static PaymentEvidence reconciledPayment(String ref, String amount) {
        return new PaymentEvidence(ref, money(amount), RECONCILED, RECONCILED,
                "provider:" + ref, "bank:" + ref, END.plusSeconds(20));
    }

    private static FinancialFact fact(String id, String category, String currency, String amount,
                                      PricingBillingFinancialRuntime.EvidenceState state,
                                      BigDecimal coverage) {
        return new FinancialFact(id, SCOPE, category, new Money(currency, decimal(amount)),
                START, END, START, "source:" + id, state, coverage);
    }

    private static Money money(String amount) {
        return new Money("CNY", decimal(amount));
    }

    private static BigDecimal decimal(String value) {
        return new BigDecimal(value);
    }
}
