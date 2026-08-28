package io.elmos.workflow;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PaymentSettlementReconcilerTest {
    private static final String DIGEST = "a".repeat(64);
    private static final PaymentSettlementReconciler.SettlementPeriod PERIOD =
            new PaymentSettlementReconciler.SettlementPeriod(
                    Instant.parse("2026-08-01T00:00:00Z"),
                    Instant.parse("2026-09-01T00:00:00Z"));

    @Test
    void exactDetailAndIndependentActorsReconcile() {
        var amounts = amounts("100", "10", "2.5", "87.5");
        var result = PaymentSettlementReconciler.reconcile(request(
                ledger("CNY", PERIOD, amounts, "ledger-actor"),
                provider("CNY", PERIOD,
                        PaymentSettlementReconciler.ProviderOutcome.CONFIRMED,
                        amounts, "provider-actor"),
                "reconciler-actor"));

        assertEquals(PaymentSettlementReconciler.ReconciliationStatus.RECONCILED,
                result.status());
        assertEquals(java.util.List.of(
                PaymentSettlementReconciler.ReasonCode.MATCHED),
                result.reasonCodes());
        assertTrue(result.amountDelta().isZero());
        assertTrue(result.mayFinalizeSettlement());
    }

    @Test
    void unknownAndRejectedProviderOutcomesFailClosed() {
        var unknown = PaymentSettlementReconciler.reconcile(request(
                ledger("CNY", PERIOD, amounts("100", "10", "2", "88"),
                        "ledger-actor"),
                provider("CNY", PERIOD,
                        PaymentSettlementReconciler.ProviderOutcome.UNKNOWN,
                        null, "provider-actor"),
                "reconciler-actor"));
        assertEquals(PaymentSettlementReconciler.ReconciliationStatus.UNKNOWN,
                unknown.status());
        assertTrue(unknown.reasonCodes().contains(
                PaymentSettlementReconciler.ReasonCode.PROVIDER_RESULT_UNKNOWN));
        assertNull(unknown.amountDelta());
        assertFalse(unknown.mayFinalizeSettlement());

        var rejected = PaymentSettlementReconciler.reconcile(request(
                ledger("CNY", PERIOD, amounts("100", "10", "2", "88"),
                        "ledger-actor"),
                provider("CNY", PERIOD,
                        PaymentSettlementReconciler.ProviderOutcome.REJECTED,
                        null, "provider-actor"),
                "reconciler-actor"));
        assertEquals(PaymentSettlementReconciler.ReconciliationStatus.UNRECONCILED,
                rejected.status());
        assertTrue(rejected.reasonCodes().contains(
                PaymentSettlementReconciler.ReasonCode.PROVIDER_RESULT_REJECTED));
        assertFalse(rejected.mayFinalizeSettlement());
    }

    @Test
    void detailMismatchReportsExactLedgerMinusProviderDelta() {
        var result = PaymentSettlementReconciler.reconcile(request(
                ledger("CNY", PERIOD, amounts("100", "10", "2.5", "87.5"),
                        "ledger-actor"),
                provider("CNY", PERIOD,
                        PaymentSettlementReconciler.ProviderOutcome.CONFIRMED,
                        amounts("100", "9", "2.5", "88.5"),
                        "provider-actor"),
                "reconciler-actor"));

        assertEquals(PaymentSettlementReconciler.ReconciliationStatus.UNRECONCILED,
                result.status());
        assertEquals(new BigDecimal("1.000000"), result.amountDelta().refundMinor());
        assertEquals(new BigDecimal("-1.000000"), result.amountDelta().netMinor());
        assertTrue(result.reasonCodes().contains(
                PaymentSettlementReconciler.ReasonCode.REFUND_AMOUNT_MISMATCH));
        assertTrue(result.reasonCodes().contains(
                PaymentSettlementReconciler.ReasonCode.NET_AMOUNT_MISMATCH));
        assertFalse(result.mayFinalizeSettlement());
    }

    @Test
    void currencyAndPeriodAreExactReconciliationDimensions() {
        var nextPeriod = new PaymentSettlementReconciler.SettlementPeriod(
                PERIOD.endExclusive(), Instant.parse("2026-10-01T00:00:00Z"));
        var amounts = amounts("100", "10", "2", "88");
        var result = PaymentSettlementReconciler.reconcile(request(
                ledger("CNY", PERIOD, amounts, "ledger-actor"),
                provider("USD", nextPeriod,
                        PaymentSettlementReconciler.ProviderOutcome.CONFIRMED,
                        amounts, "provider-actor"),
                "reconciler-actor"));

        assertEquals(PaymentSettlementReconciler.ReconciliationStatus.UNRECONCILED,
                result.status());
        assertTrue(result.reasonCodes().contains(
                PaymentSettlementReconciler.ReasonCode.CURRENCY_MISMATCH));
        assertTrue(result.reasonCodes().contains(
                PaymentSettlementReconciler.ReasonCode.PERIOD_MISMATCH));
        assertNull(result.amountDelta());
        assertFalse(result.mayFinalizeSettlement());
    }

    @Test
    void segregationOfDutiesViolationBlocksAnOtherwiseExactMatch() {
        var amounts = amounts("100", "10", "2", "88");
        var result = PaymentSettlementReconciler.reconcile(request(
                ledger("CNY", PERIOD, amounts, "actor-a"),
                provider("CNY", PERIOD,
                        PaymentSettlementReconciler.ProviderOutcome.CONFIRMED,
                        amounts, "actor-a"),
                "actor-a"));

        assertEquals(PaymentSettlementReconciler.ReconciliationStatus.UNRECONCILED,
                result.status());
        assertTrue(result.reasonCodes().contains(
                PaymentSettlementReconciler.ReasonCode.RECONCILER_IS_LEDGER_PREPARER));
        assertTrue(result.reasonCodes().contains(
                PaymentSettlementReconciler.ReasonCode.RECONCILER_IS_PROVIDER_RECORDER));
        assertTrue(result.reasonCodes().contains(
                PaymentSettlementReconciler.ReasonCode.LEDGER_PREPARER_IS_PROVIDER_RECORDER));
        assertFalse(result.mayFinalizeSettlement());
    }

    @Test
    void decimalPrecisionConservationAndCurrencyAreValidatedAtConstruction() {
        assertThrows(IllegalArgumentException.class, () ->
                amounts("100", "1", "1", "99"));
        assertThrows(IllegalArgumentException.class, () ->
                amounts("1.0000001", "0", "0", "1.0000001"));
        assertThrows(IllegalArgumentException.class, () ->
                ledger("cny", PERIOD, amounts("1", "0", "0", "1"),
                        "ledger-actor"));
        assertThrows(IllegalArgumentException.class, () ->
                provider("CNY", PERIOD,
                        PaymentSettlementReconciler.ProviderOutcome.UNKNOWN,
                        amounts("1", "0", "0", "1"),
                        "provider-actor"));
        String tooManyIntegerDigits = "1" + "0".repeat(24);
        assertThrows(IllegalArgumentException.class, () ->
                amounts(tooManyIntegerDigits, "0", "0", tooManyIntegerDigits));
    }

    @Test
    void durableCommandBindsReconcilerAndIdempotencyToAuthenticatedContext() {
        var exactAmounts = amounts("100", "10", "2", "88");
        var reconciliation = request(
                ledger("CNY", PERIOD, exactAmounts, "ledger-actor"),
                provider("CNY", PERIOD,
                        PaymentSettlementReconciler.ProviderOutcome.CONFIRMED,
                        exactAmounts, "provider-actor"),
                "reconciler-actor");
        var wrongActor = new TaskFinopsPort.AuthenticatedContext(
                "organization-a", "account-a", "different-actor", "request-a");
        assertThrows(IllegalArgumentException.class, () ->
                new TaskFinopsOperationsPort.SettlementCommand(
                        wrongActor, reconciliation, "provider-a", null, null,
                        reconciliation.idempotencyKey(), DIGEST));

        var correctActor = new TaskFinopsPort.AuthenticatedContext(
                "organization-a", "account-a", "reconciler-actor", "request-a");
        assertThrows(IllegalArgumentException.class, () ->
                new TaskFinopsOperationsPort.SettlementCommand(
                        correctActor, reconciliation, "provider-a", null, null,
                        "different-idempotency", DIGEST));
    }

    private static PaymentSettlementReconciler.ReconciliationRequest request(
            PaymentSettlementReconciler.LedgerSettlement ledger,
            PaymentSettlementReconciler.ProviderSettlement provider,
            String reconciledBy
    ) {
        return new PaymentSettlementReconciler.ReconciliationRequest(
                "reconciliation-a", "idem-reconciliation-a",
                ledger, provider, reconciledBy);
    }

    private static PaymentSettlementReconciler.LedgerSettlement ledger(
            String currency,
            PaymentSettlementReconciler.SettlementPeriod period,
            PaymentSettlementReconciler.SettlementAmounts amounts,
            String preparedBy
    ) {
        return new PaymentSettlementReconciler.LedgerSettlement(
                "settlement-a", currency, period, amounts, preparedBy);
    }

    private static PaymentSettlementReconciler.ProviderSettlement provider(
            String currency,
            PaymentSettlementReconciler.SettlementPeriod period,
            PaymentSettlementReconciler.ProviderOutcome outcome,
            PaymentSettlementReconciler.SettlementAmounts amounts,
            String recordedBy
    ) {
        return new PaymentSettlementReconciler.ProviderSettlement(
                "provider-settlement-a", currency, period, outcome, amounts, recordedBy);
    }

    private static PaymentSettlementReconciler.SettlementAmounts amounts(
            String gross,
            String refund,
            String fee,
            String net
    ) {
        return new PaymentSettlementReconciler.SettlementAmounts(
                new BigDecimal(gross), new BigDecimal(refund),
                new BigDecimal(fee), new BigDecimal(net));
    }
}
