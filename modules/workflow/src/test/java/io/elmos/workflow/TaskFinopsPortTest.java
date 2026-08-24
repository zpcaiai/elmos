package io.elmos.workflow;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TaskFinopsPortTest {
    private static final Instant START = Instant.parse("2026-08-24T00:00:00Z");
    private static final Instant END = Instant.parse("2026-08-24T01:00:00Z");
    private static final String DIGEST = "a".repeat(64);

    @Test
    void exactMoneyScaleIsNeverSilentlyRounded() {
        var entry = usage(
                TaskFinopsPort.CostState.POSTED,
                TaskFinopsPort.ReconciliationStatus.PENDING,
                new BigDecimal("1.234567"));
        assertEquals(new BigDecimal("1.234567"), entry.baseCostMinor());

        assertThrows(IllegalArgumentException.class, () -> usage(
                TaskFinopsPort.CostState.POSTED,
                TaskFinopsPort.ReconciliationStatus.PENDING,
                new BigDecimal("1.2345678")));
        assertThrows(IllegalArgumentException.class, () -> usage(
                TaskFinopsPort.CostState.POSTED,
                TaskFinopsPort.ReconciliationStatus.PENDING,
                new BigDecimal("1234567890123456789012345.000000")));
    }

    @Test
    void finalCostAndCurrentSummaryFailClosedUntilReconciled() {
        assertThrows(IllegalArgumentException.class, () -> usage(
                TaskFinopsPort.CostState.FINAL,
                TaskFinopsPort.ReconciliationStatus.UNKNOWN,
                new BigDecimal("1.000000")));

        assertThrows(IllegalArgumentException.class, () -> new TaskFinopsPort.FinancialSummary(
                "tenant-a", "account-a", "task-a", "CNY",
                money("1"), money("1"), money("1"), money("0"),
                money("2"), money("0"), money("0"), money("1"),
                new BigDecimal("0.500000000"), 1, 1, 1, 0,
                START, END, TaskFinopsPort.ReconciliationStatus.PENDING,
                TaskFinopsPort.FinancialQualification.CURRENT));
    }

    @Test
    void signedRefundAndAllocationAmountsRemainSigned() {
        var context = context();
        var revenue = new TaskFinopsPort.RevenueEntry(
                context, "rev-a", "task-a", "project-a", "entity-a",
                TaskFinopsPort.RevenueKind.REFUND,
                TaskFinopsPort.RevenueState.REFUNDED,
                "cny", money("-2.5"), END, START, END,
                "PAYMENT", "refund-a", null,
                TaskFinopsPort.ReconciliationStatus.PENDING,
                "ED25519", "key-a", DIGEST, "signed-value", "idem-revenue-a");
        assertEquals("CNY", revenue.currency());
        assertEquals(new BigDecimal("-2.500000"), revenue.amountMinor());
    }

    @Test
    void taxAndPaymentFeeAreSeparateNegativeNonRevenueEntries() {
        var tax = revenue(
                TaskFinopsPort.RevenueKind.TAX,
                TaskFinopsPort.RevenueState.POSTED,
                "-1.250000");
        var paymentFee = revenue(
                TaskFinopsPort.RevenueKind.PAYMENT_FEE,
                TaskFinopsPort.RevenueState.RECORDED,
                "-0.125000");

        assertEquals(new BigDecimal("-1.250000"), tax.amountMinor());
        assertEquals(new BigDecimal("-0.125000"), paymentFee.amountMinor());
        assertThrows(IllegalArgumentException.class, () -> revenue(
                TaskFinopsPort.RevenueKind.TAX,
                TaskFinopsPort.RevenueState.POSTED,
                "1.250000"));
        assertThrows(IllegalArgumentException.class, () -> revenue(
                TaskFinopsPort.RevenueKind.PAYMENT_FEE,
                TaskFinopsPort.RevenueState.RECOGNIZED,
                "-0.125000"));
    }

    @Test
    void halfEvenTieBreakingIsSymmetricForSignedMoney() {
        assertEquals(new BigDecimal("1.234566"),
                new TaskFinopsPolicy.Money("CNY", new BigDecimal("1.2345665"))
                        .minorUnits());
        assertEquals(new BigDecimal("1.234568"),
                new TaskFinopsPolicy.Money("CNY", new BigDecimal("1.2345675"))
                        .minorUnits());
        assertEquals(new BigDecimal("-1.234566"),
                new TaskFinopsPolicy.Money("CNY", new BigDecimal("-1.2345665"))
                        .minorUnits());
        assertEquals(new BigDecimal("-1.234568"),
                new TaskFinopsPolicy.Money("CNY", new BigDecimal("-1.2345675"))
                        .minorUnits());
    }

    @Test
    void databaseBackedIdentifiersStopAtVarcharNinetySix() {
        String maximum = "x".repeat(TaskFinopsPort.DATABASE_ID_MAX_LENGTH);
        var context = new TaskFinopsPort.AuthenticatedContext(
                maximum, maximum, "a".repeat(TaskFinopsPort.DATABASE_ACTOR_ID_MAX_LENGTH),
                "request-a");
        var command = new TaskFinopsPort.ControlCommand(
                context, maximum, "USER_REQUEST", "idempotency-a", DIGEST);
        assertEquals(TaskFinopsPort.DATABASE_ID_MAX_LENGTH, command.taskId().length());

        assertThrows(IllegalArgumentException.class, () ->
                new TaskFinopsPort.AuthenticatedContext(
                        maximum + "x", "account-a", "actor-a", "request-a"));
        assertThrows(IllegalArgumentException.class, () ->
                new TaskFinopsPort.ControlCommand(
                        context, maximum + "x", "USER_REQUEST", "idempotency-b", DIGEST));
        assertThrows(IllegalArgumentException.class, () -> usage(
                TaskFinopsPort.CostState.POSTED,
                TaskFinopsPort.ReconciliationStatus.PENDING,
                new BigDecimal("1.000000"), "01"));
    }

    private static TaskFinopsPort.UsageEntry usage(
            TaskFinopsPort.CostState costState,
            TaskFinopsPort.ReconciliationStatus reconciliation,
            BigDecimal baseCost
    ) {
        return usage(costState, reconciliation, baseCost, "1");
    }

    private static TaskFinopsPort.UsageEntry usage(
            TaskFinopsPort.CostState costState,
            TaskFinopsPort.ReconciliationStatus reconciliation,
            BigDecimal baseCost,
            String runId
    ) {
        return new TaskFinopsPort.UsageEntry(
                context(), "usage-a", "task-a", runId, "provider-a",
                "sku-a", "TOKEN", new BigDecimal("10.000000000"),
                "price-book-a", "v1", START, "USD", money("0.100000"),
                "fx-a", "CNY", new BigDecimal("7.000000000000"),
                money("1.000000"), baseCost, costState, reconciliation,
                null, START, END, END, "idem-usage-a", null);
    }

    private static TaskFinopsPort.AuthenticatedContext context() {
        return new TaskFinopsPort.AuthenticatedContext(
                "tenant-a", "account-a", "actor-a", "request-a");
    }

    private static TaskFinopsPort.RevenueEntry revenue(
            TaskFinopsPort.RevenueKind kind,
            TaskFinopsPort.RevenueState state,
            String amount
    ) {
        return new TaskFinopsPort.RevenueEntry(
                context(), "rev-" + kind.name().toLowerCase(), "task-a",
                "project-a", "entity-a", kind, state, "CNY", money(amount),
                END, START, END, "BILLING", "source-a", null,
                TaskFinopsPort.ReconciliationStatus.PENDING,
                "ED25519", "key-a", DIGEST, "signed-value",
                "idem-" + kind.name().toLowerCase());
    }

    private static BigDecimal money(String value) {
        return new BigDecimal(value).setScale(TaskFinopsPolicy.MONEY_SCALE);
    }
}
