package io.elmos.workflow;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TaskFinopsModelCacheAnalyticsTest {
    private static final Instant AS_OF = Instant.parse("2026-08-26T02:00:00Z");

    @Test
    void aggregatesCacheEfficiencyByModelProviderAndCurrency() {
        var context = context("request-1");
        var result = TaskFinopsModelCacheAnalytics.aggregate(context, List.of(
                observation(context, "obs-1", "gpt-5", true, 100, 20, 80,
                        new BigDecimal("1.00"), TaskFinopsPort.ReconciliationStatus.RECONCILED),
                observation(context, "obs-2", "gpt-5", false, 100, 10, 0,
                        new BigDecimal("2.00"), TaskFinopsPort.ReconciliationStatus.PENDING)));

        assertEquals(1, result.rows().size());
        var row = result.rows().getFirst();
        assertEquals(2, row.observationCount());
        assertEquals(1, row.cacheHitCount());
        assertEquals(200, row.inputTokens());
        assertEquals(30, row.outputTokens());
        assertEquals(80, row.cacheReadTokens());
        assertEquals(new BigDecimal("0.500000000"), row.cacheHitRatio());
        assertEquals(new BigDecimal("3.000000"), row.totalCostMinor());
        assertEquals(new BigDecimal("0.100000"), row.costPerOutputTokenMinor());
        assertEquals(TaskFinopsModelCacheAnalytics.Completeness.PARTIAL,
                row.completeness());
        assertEquals(TaskFinopsPort.ReconciliationStatus.PENDING,
                row.reconciliationStatus());
        assertEquals(TaskFinopsModelCacheAnalytics.ExternalEvidenceState.NOT_RUN,
                result.externalEvidence());
    }

    @Test
    void keepsModelCacheRowsTenantAndAccountBound() {
        var context = context("request-2");
        var other = new TaskFinopsPort.AuthenticatedContext(
                "org-1", "acct-2", "actor-1", "request-3");
        assertThrows(IllegalArgumentException.class, () ->
                TaskFinopsModelCacheAnalytics.aggregate(context, List.of(
                        observation(other, "obs-3", "gpt-5", true, 10, 2, 8,
                                BigDecimal.ONE, TaskFinopsPort.ReconciliationStatus.RECONCILED))));
    }

    @Test
    void unknownProviderReconciliationCannotBecomeComplete() {
        var context = context("request-4");
        var result = TaskFinopsModelCacheAnalytics.aggregate(context, List.of(
                observation(context, "obs-4", "gpt-5", true, 10, 2, 8,
                        BigDecimal.ONE, TaskFinopsPort.ReconciliationStatus.UNKNOWN)));
        assertEquals(TaskFinopsModelCacheAnalytics.Completeness.UNKNOWN,
                result.rows().getFirst().completeness());
        assertEquals(TaskFinopsPort.ReconciliationStatus.UNKNOWN,
                result.rows().getFirst().reconciliationStatus());
    }

    @Test
    void rejectsAClaimedCacheHitWithoutReadTokens() {
        var context = context("request-5");
        assertThrows(IllegalArgumentException.class, () -> new TaskFinopsModelCacheAnalytics.Observation(
                context, "obs-5", "task-1", 1, "gpt-5", "provider-1",
                true, 10, 2, 0, 0, 100, "CNY", BigDecimal.ONE, AS_OF,
                TaskFinopsPort.ReconciliationStatus.RECONCILED));
    }

    private static TaskFinopsPort.AuthenticatedContext context(String requestId) {
        return new TaskFinopsPort.AuthenticatedContext("org-1", "acct-1", "actor-1", requestId);
    }

    private static TaskFinopsModelCacheAnalytics.Observation observation(
            TaskFinopsPort.AuthenticatedContext context,
            String observationId,
            String model,
            boolean cacheHit,
            long inputTokens,
            long outputTokens,
            long cacheReadTokens,
            BigDecimal cost,
            TaskFinopsPort.ReconciliationStatus reconciliationStatus
    ) {
        return new TaskFinopsModelCacheAnalytics.Observation(
                context, observationId, "task-1", 1, model, "provider-1", cacheHit,
                inputTokens, outputTokens, cacheReadTokens, 0, 100, "CNY", cost,
                AS_OF, reconciliationStatus);
    }
}
