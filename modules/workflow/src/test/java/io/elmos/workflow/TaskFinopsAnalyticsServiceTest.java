package io.elmos.workflow;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TaskFinopsAnalyticsServiceTest {
    private static final String DIGEST = "a".repeat(64);
    private static final Instant START = Instant.parse("2026-08-26T08:00:00Z");
    private final FakeOperations operations = new FakeOperations();
    private final TaskFinopsPort.AuthenticatedContext context =
            new TaskFinopsPort.AuthenticatedContext(
                    "organization-a", "account-a", "actor-a", "request-a");

    @Test
    void rebuildUsesBoundedSourceFactsAndPublishesOneAtomicGeneration() {
        operations.source = new TaskFinopsOperationsPort.AnalyticsSource(
                List.of(
                        event(1, TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT, 0),
                        event(2, TaskFinopsPolicy.TaskState.ADMITTED, 1),
                        event(3, TaskFinopsPolicy.TaskState.RUNNING, 50),
                        event(4, TaskFinopsPolicy.TaskState.SUCCEEDED, 100)),
                List.of(new TaskFinopsAnalytics.FinancialFact(
                        context.organizationId(), context.accountId(), "task-a", 1,
                        "fact-a", TaskFinopsPolicy.WorkloadClass.GENERATION,
                        "CNY", TaskFinopsPort.AllocationBasis.DIRECT_TASK,
                        new BigDecimal("1.000000"), new BigDecimal("3.000000"),
                        START.plusSeconds(1_800),
                        TaskFinopsAnalytics.DataCompleteness.COMPLETE,
                        TaskFinopsPort.ReconciliationStatus.RECONCILED)));

        var receipt = new TaskFinopsAnalyticsService(operations).rebuild(
                new TaskFinopsAnalyticsService.RebuildCommand(
                        context, "rebuild-a", START, START.plusSeconds(3_600),
                        1, "rebuild-idem-a", DIGEST));

        assertEquals(2, receipt.generation());
        assertEquals(4, receipt.eventCount());
        assertEquals(1, receipt.factCount());
        assertEquals(1, receipt.runCount());
        assertEquals(2, receipt.bucketCount());
        assertSame(TaskFinopsAnalytics.ExternalEvidenceState.NOT_RUN,
                receipt.externalEvidence());
        assertSame(TaskFinopsAnalytics.ProviderOutcome.UNKNOWN,
                receipt.providerOutcome());
        assertSame(TaskFinopsAnalytics.ProductionCertification.NOT_CERTIFIED,
                receipt.productionCertification());

        assertEquals(1, operations.sourceReads);
        assertNotNull(operations.sourceWindow);
        assertSame(context, operations.sourceWindow.context());
        assertEquals(START, operations.sourceWindow.windowStart());
        assertEquals(START.plusSeconds(3_600), operations.sourceWindow.windowEnd());
        assertEquals(TaskFinopsOperationsPort.MAX_ANALYTICS_SOURCE_ROWS,
                operations.sourceWindow.limit());
        assertNotNull(operations.publication);
        assertEquals(TaskFinopsAnalytics.Grain.HOUR,
                operations.publication.hourly().grain());
        assertEquals(TaskFinopsAnalytics.Grain.DAY,
                operations.publication.daily().grain());
    }

    @Test
    void exportRejectsAProjectionWhoseInputContinuityIsUnknown() {
        operations.projection = new TaskFinopsOperationsPort.ProjectionSnapshot(
                "rebuild-a", 1, START,
                TaskFinopsAnalytics.InputContinuity.UNKNOWN,
                TaskFinopsAnalytics.ExternalEvidenceState.NOT_RUN,
                TaskFinopsAnalytics.ProviderOutcome.UNKNOWN,
                TaskFinopsAnalytics.ProductionCertification.NOT_CERTIFIED,
                DIGEST, DIGEST, List.of());

        var rejected = assertThrows(TaskFinopsAnalytics.AnalyticsException.class,
                () -> new TaskFinopsAnalyticsService(operations).export(
                        context, TaskFinopsAnalytics.Grain.HOUR,
                        TaskFinopsAnalytics.ExportFormat.JSON,
                        START, START.plusSeconds(3_600), 10));
        assertEquals("ELMOS_MTF_ANALYTICS_INPUT_CONTINUITY_INCOMPLETE",
                rejected.code());
    }

    private TaskFinopsAnalytics.JournalEvent event(
            long sequence,
            TaskFinopsPolicy.TaskState state,
            int progress
    ) {
        return new TaskFinopsAnalytics.JournalEvent(
                context.organizationId(), context.accountId(), "task-a", 1,
                sequence, "event-" + sequence, state, (short) progress,
                START.plusSeconds(sequence));
    }

    /** Dependency-free fake that rejects every operation outside this test's contract. */
    private static final class FakeOperations implements TaskFinopsOperationsPort {
        private AnalyticsSource source;
        private AnalyticsWindow sourceWindow;
        private int sourceReads;
        private ProjectionPublication publication;
        private ProjectionSnapshot projection;

        @Override
        public AnalyticsSource analyticsSource(AnalyticsWindow window) {
            if (source == null) {
                throw new AssertionError("analytics source not configured");
            }
            sourceWindow = window;
            sourceReads++;
            return source;
        }

        @Override
        public long publishProjection(ProjectionPublication value) {
            if (publication != null) {
                throw new AssertionError("projection published more than once");
            }
            publication = value;
            return 2L;
        }

        @Override
        public List<TaskFinopsAnalytics.JournalEvent> journal(AnalyticsWindow window) {
            throw unexpected("journal");
        }

        @Override
        public List<TaskFinopsAnalytics.FinancialFact> financialFacts(AnalyticsWindow window) {
            throw unexpected("financialFacts");
        }

        @Override
        public long setFeatureRollout(FeatureRolloutCommand command) {
            throw unexpected("setFeatureRollout");
        }

        @Override
        public String recordCheckpointCompatibility(CheckpointCompatibilityCommand command) {
            throw unexpected("recordCheckpointCompatibility");
        }

        @Override
        public RecoveryForkResult forkRecovery(ForkRecoveryCommand command) {
            throw unexpected("forkRecovery");
        }

        @Override
        public String requestLifecycle(LifecycleRequestCommand command) {
            throw unexpected("requestLifecycle");
        }

        @Override
        public Optional<LifecycleStatus> lifecycleStatus(
                TaskFinopsPort.AuthenticatedContext context,
                String lifecycleJobId
        ) {
            throw unexpected("lifecycleStatus");
        }

        @Override
        public long advanceLifecycle(LifecycleTransitionCommand command) {
            throw unexpected("advanceLifecycle");
        }

        @Override
        public long checkpointExportPage(ExportPageCommand command) {
            throw unexpected("checkpointExportPage");
        }

        @Override
        public long recordPurgeResult(PurgeResultCommand command) {
            throw unexpected("recordPurgeResult");
        }

        @Override
        public SettlementReceipt recordSettlement(SettlementCommand command) {
            throw unexpected("recordSettlement");
        }

        @Override
        public long currentProjectionGeneration(TaskFinopsPort.AuthenticatedContext context) {
            throw unexpected("currentProjectionGeneration");
        }

        @Override
        public Optional<ProjectionSnapshot> currentProjection(
                TaskFinopsPort.AuthenticatedContext context,
                TaskFinopsAnalytics.Grain grain,
                Instant from,
                Instant to,
                int limit
        ) {
            return Optional.ofNullable(projection);
        }

        private static AssertionError unexpected(String operation) {
            return new AssertionError("unexpected operation: " + operation);
        }
    }
}
