package io.elmos.workflow;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TaskFinopsAnalyticsExportTest {
    private static final TaskFinopsPort.AuthenticatedContext CONTEXT =
            new TaskFinopsPort.AuthenticatedContext(
                    "org-1", "account-1", "actor-1", "request-1");

    @Test
    void createsUtcHourlyBucketsWithoutMixingCurrencyBasisOrCompleteness() {
        List<TaskFinopsAnalytics.FinancialFact> facts = List.of(
                fact("f-1", "task-1", "CNY", TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                        "1.100000", "4.000000", "2026-08-25T23:15:00Z",
                        TaskFinopsAnalytics.DataCompleteness.COMPLETE,
                        TaskFinopsPort.ReconciliationStatus.RECONCILED),
                fact("f-2", "task-1", "CNY", TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                        "0.200000", "1.000000", "2026-08-25T23:59:59Z",
                        TaskFinopsAnalytics.DataCompleteness.UNKNOWN,
                        TaskFinopsPort.ReconciliationStatus.UNKNOWN),
                fact("f-3", "task-1", "USD", TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                        "2.000000", "3.000000", "2026-08-25T23:20:00Z",
                        TaskFinopsAnalytics.DataCompleteness.COMPLETE,
                        TaskFinopsPort.ReconciliationStatus.RECONCILED),
                fact("f-4", "task-1", "CNY", TaskFinopsPort.AllocationBasis.MILESTONE,
                        "5.000000", "7.000000", "2026-08-25T23:20:00Z",
                        TaskFinopsAnalytics.DataCompleteness.PARTIAL,
                        TaskFinopsPort.ReconciliationStatus.PENDING));

        var result = TaskFinopsAnalytics.aggregate(
                CONTEXT, facts, TaskFinopsAnalytics.Grain.HOUR);

        assertEquals(3, result.rows().size());
        assertEquals(4, result.factCount());
        var directCny = result.rows().stream()
                .filter(row -> row.currency().equals("CNY"))
                .filter(row -> row.allocationBasis()
                        == TaskFinopsPort.AllocationBasis.DIRECT_TASK)
                .findFirst().orElseThrow();
        assertEquals(Instant.parse("2026-08-25T23:00:00Z"), directCny.bucketStart());
        assertEquals(Instant.parse("2026-08-26T00:00:00Z"), directCny.bucketEnd());
        assertEquals(new BigDecimal("1.300000"), directCny.costDeltaMinor());
        assertEquals(new BigDecimal("5.000000"), directCny.revenueDeltaMinor());
        assertEquals(new BigDecimal("3.700000"), directCny.grossDeltaMinor());
        assertEquals(2, directCny.factCount());
        assertEquals(TaskFinopsAnalytics.DataCompleteness.UNKNOWN,
                directCny.completeness());
        assertEquals(TaskFinopsPort.ReconciliationStatus.UNKNOWN,
                directCny.reconciliationStatus());
    }

    @Test
    void createsUtcCalendarDayBucketsAtMidnight() {
        var result = TaskFinopsAnalytics.aggregate(CONTEXT, List.of(
                fact("f-before", "task-1", "CNY",
                        TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                        "1", "2", "2026-08-25T23:59:59Z",
                        TaskFinopsAnalytics.DataCompleteness.COMPLETE,
                        TaskFinopsPort.ReconciliationStatus.RECONCILED),
                fact("f-after", "task-1", "CNY",
                        TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                        "1", "2", "2026-08-26T00:00:00Z",
                        TaskFinopsAnalytics.DataCompleteness.COMPLETE,
                        TaskFinopsPort.ReconciliationStatus.RECONCILED)),
                TaskFinopsAnalytics.Grain.DAY);

        assertEquals(2, result.rows().size());
        assertEquals(Instant.parse("2026-08-25T00:00:00Z"),
                result.rows().get(0).bucketStart());
        assertEquals(Instant.parse("2026-08-26T00:00:00Z"),
                result.rows().get(1).bucketStart());
    }

    @Test
    void aggregationIsCanonicalButStillBindsSourceFacts() {
        var first = fact("f-1", "task-1", "CNY",
                TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                "1", "2", "2026-08-25T01:00:00Z",
                TaskFinopsAnalytics.DataCompleteness.COMPLETE,
                TaskFinopsPort.ReconciliationStatus.RECONCILED);
        var second = fact("f-2", "task-1", "CNY",
                TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                "3", "5", "2026-08-25T01:30:00Z",
                TaskFinopsAnalytics.DataCompleteness.COMPLETE,
                TaskFinopsPort.ReconciliationStatus.RECONCILED);

        var forward = TaskFinopsAnalytics.aggregate(
                CONTEXT, List.of(first, second), TaskFinopsAnalytics.Grain.HOUR);
        var reverse = TaskFinopsAnalytics.aggregate(
                CONTEXT, List.of(second, first), TaskFinopsAnalytics.Grain.HOUR);
        var changedIdentity = TaskFinopsAnalytics.aggregate(CONTEXT, List.of(
                fact("replacement", "task-1", "CNY",
                        TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                        "1", "2", "2026-08-25T01:00:00Z",
                        TaskFinopsAnalytics.DataCompleteness.COMPLETE,
                        TaskFinopsPort.ReconciliationStatus.RECONCILED), second),
                TaskFinopsAnalytics.Grain.HOUR);

        assertEquals(forward.checksum(), reverse.checksum());
        assertNotEquals(forward.checksum(), changedIdentity.checksum());
    }

    @Test
    void rejectsUnknownPresentedAsCompleteDuplicatesAndCrossTenantFacts() {
        assertThrows(IllegalArgumentException.class, () -> fact(
                "f-1", "task-1", "CNY", TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                "1", "2", "2026-08-25T01:00:00Z",
                TaskFinopsAnalytics.DataCompleteness.COMPLETE,
                TaskFinopsPort.ReconciliationStatus.UNKNOWN));

        var fact = fact("f-1", "task-1", "CNY",
                TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                "1", "2", "2026-08-25T01:00:00Z",
                TaskFinopsAnalytics.DataCompleteness.COMPLETE,
                TaskFinopsPort.ReconciliationStatus.RECONCILED);
        assertCode("ELMOS_MTF_ANALYTICS_DUPLICATE_FINANCIAL_FACT", () ->
                TaskFinopsAnalytics.aggregate(CONTEXT, List.of(fact, fact),
                        TaskFinopsAnalytics.Grain.HOUR));

        var otherTenant = new TaskFinopsAnalytics.FinancialFact(
                "org-other", "account-1", "task-1", 1, "f-other",
                TaskFinopsPolicy.WorkloadClass.GENERATION, "CNY",
                TaskFinopsPort.AllocationBasis.DIRECT_TASK, BigDecimal.ONE,
                new BigDecimal("2"), Instant.parse("2026-08-25T01:00:00Z"),
                TaskFinopsAnalytics.DataCompleteness.COMPLETE,
                TaskFinopsPort.ReconciliationStatus.RECONCILED);
        assertCode("ELMOS_MTF_ANALYTICS_SCOPE_MISMATCH", () ->
                TaskFinopsAnalytics.aggregate(CONTEXT, List.of(otherTenant),
                        TaskFinopsAnalytics.Grain.HOUR));
    }

    @Test
    void stableExportsBindBytesRowsAndFailClosedEvidenceState() {
        var result = TaskFinopsAnalytics.aggregate(CONTEXT, List.of(
                fact("f-1", "task-1", "CNY",
                        TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                        "1.250000", "2.750000", "2026-08-25T01:00:00Z",
                        TaskFinopsAnalytics.DataCompleteness.UNKNOWN,
                        TaskFinopsPort.ReconciliationStatus.UNKNOWN)),
                TaskFinopsAnalytics.Grain.HOUR);

        var json = TaskFinopsAnalytics.exportJson(CONTEXT, result);
        var csv = TaskFinopsAnalytics.exportCsv(CONTEXT, result);

        assertEquals(1, json.rowCount());
        assertEquals(json.body(), TaskFinopsAnalytics.exportJson(CONTEXT, result).body());
        assertEquals(csv.body(), TaskFinopsAnalytics.exportCsv(CONTEXT, result).body());
        assertEquals(sha256(json.body()), json.digest());
        assertEquals(sha256(csv.body()), csv.digest());
        assertTrue(json.body().contains("\"externalEvidence\":\"NOT_RUN\""));
        assertTrue(json.body().contains("\"providerOutcome\":\"UNKNOWN\""));
        assertTrue(json.body().contains(
                "\"productionCertification\":\"NOT_CERTIFIED\""));
        assertTrue(csv.body().contains(",\"NOT_RUN\",\"UNKNOWN\",\"NOT_CERTIFIED\""));
        assertEquals(TaskFinopsAnalytics.ExternalEvidenceState.NOT_RUN,
                csv.externalEvidence());
        assertEquals(TaskFinopsAnalytics.ProductionCertification.NOT_CERTIFIED,
                csv.productionCertification());
    }

    @Test
    void csvNeutralizesSpreadsheetFormulaIdentifiers() {
        var formulaContext = new TaskFinopsPort.AuthenticatedContext(
                "=2+2", "account-1", "actor-1", "request-1");
        var fact = new TaskFinopsAnalytics.FinancialFact(
                "=2+2", "account-1", "+cmd", 1, "f-1",
                TaskFinopsPolicy.WorkloadClass.GENERATION, "CNY",
                TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                BigDecimal.ONE, new BigDecimal("2"),
                Instant.parse("2026-08-25T01:00:00Z"),
                TaskFinopsAnalytics.DataCompleteness.COMPLETE,
                TaskFinopsPort.ReconciliationStatus.RECONCILED);
        var result = TaskFinopsAnalytics.aggregate(
                formulaContext, List.of(fact), TaskFinopsAnalytics.Grain.HOUR);

        String body = TaskFinopsAnalytics.exportCsv(formulaContext, result).body();

        assertTrue(body.contains("\"'=2+2\""));
        assertTrue(body.contains("\"'+cmd\""));
    }

    @Test
    void csvPreservesTrustedNegativeMoneyAsAnExactNumber() {
        var result = TaskFinopsAnalytics.aggregate(CONTEXT, List.of(
                fact("correction", "task-1", "CNY",
                        TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                        "-1.250000", "-2.500000", "2026-08-25T01:00:00Z",
                        TaskFinopsAnalytics.DataCompleteness.COMPLETE,
                        TaskFinopsPort.ReconciliationStatus.RECONCILED)),
                TaskFinopsAnalytics.Grain.HOUR);

        String body = TaskFinopsAnalytics.exportCsv(CONTEXT, result).body();

        assertTrue(body.contains("\"-1.250000\",\"-2.500000\",\"-1.250000\""));
    }

    private static TaskFinopsAnalytics.FinancialFact fact(
            String factId,
            String taskId,
            String currency,
            TaskFinopsPort.AllocationBasis basis,
            String cost,
            String revenue,
            String occurredAt,
            TaskFinopsAnalytics.DataCompleteness completeness,
            TaskFinopsPort.ReconciliationStatus reconciliation
    ) {
        return new TaskFinopsAnalytics.FinancialFact(
                "org-1", "account-1", taskId, 1, factId,
                TaskFinopsPolicy.WorkloadClass.GENERATION, currency, basis,
                new BigDecimal(cost), new BigDecimal(revenue), Instant.parse(occurredAt),
                completeness, reconciliation);
    }

    private static void assertCode(String expected, Runnable action) {
        var exception = assertThrows(TaskFinopsAnalytics.AnalyticsException.class, action::run);
        assertEquals(expected, exception.code());
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new AssertionError(exception);
        }
    }
}
