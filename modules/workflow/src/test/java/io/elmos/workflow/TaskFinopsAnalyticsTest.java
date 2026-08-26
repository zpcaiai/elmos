package io.elmos.workflow;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TaskFinopsAnalyticsTest {
    private static final TaskFinopsPort.AuthenticatedContext CONTEXT =
            new TaskFinopsPort.AuthenticatedContext(
                    "org-1", "account-1", "actor-1", "request-1");

    @Test
    void replaysInterleavedRunsToOneCanonicalChecksum() {
        List<TaskFinopsAnalytics.JournalEvent> firstOrder = List.of(
                event("task-b", 1, 1, "b-1",
                        TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT, 0, "00:00:01Z"),
                event("task-a", 1, 1, "a-1",
                        TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT, 0, "00:00:00Z"),
                event("task-b", 1, 2, "b-2",
                        TaskFinopsPolicy.TaskState.ADMITTED, 5, "00:00:03Z"),
                event("task-a", 1, 2, "a-2",
                        TaskFinopsPolicy.TaskState.ADMITTED, 10, "00:00:02Z"),
                event("task-a", 1, 3, "a-3",
                        TaskFinopsPolicy.TaskState.RUNNING, 50, "00:00:04Z"),
                event("task-a", 1, 4, "a-4",
                        TaskFinopsPolicy.TaskState.SUCCEEDED, 100, "00:00:05Z"));
        List<TaskFinopsAnalytics.JournalEvent> secondOrder = List.of(
                firstOrder.get(1), firstOrder.get(0), firstOrder.get(3),
                firstOrder.get(2), firstOrder.get(4), firstOrder.get(5));

        var first = TaskFinopsAnalytics.rebuild(CONTEXT, firstOrder);
        var second = TaskFinopsAnalytics.rebuild(CONTEXT, secondOrder);

        assertEquals(first.checksum(), second.checksum());
        assertEquals(6, first.eventCount());
        assertEquals(List.of("task-a", "task-b"), first.runs().stream()
                .map(TaskFinopsAnalytics.RunProjection::taskId).toList());
        assertEquals(TaskFinopsPolicy.TaskState.SUCCEEDED,
                first.runs().getFirst().taskState());
        assertEquals(TaskFinopsAnalytics.InputContinuity.COMPLETE,
                first.inputContinuity());
        assertEquals(TaskFinopsAnalytics.ExternalEvidenceState.NOT_RUN,
                first.externalEvidence());
        assertEquals(TaskFinopsAnalytics.ProviderOutcome.UNKNOWN,
                first.providerOutcome());
        assertEquals(TaskFinopsAnalytics.ProductionCertification.NOT_CERTIFIED,
                first.productionCertification());
    }

    @Test
    void checksumBindsEveryJournalFact() {
        var baseline = TaskFinopsAnalytics.rebuild(CONTEXT, List.of(
                event("task-a", 1, 1, "a-1",
                        TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT, 0, "00:00:00Z"),
                event("task-a", 1, 2, "a-2",
                        TaskFinopsPolicy.TaskState.ADMITTED, 10, "00:00:02Z")));
        var changed = TaskFinopsAnalytics.rebuild(CONTEXT, List.of(
                event("task-a", 1, 1, "a-1",
                        TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT, 0, "00:00:00Z"),
                event("task-a", 1, 2, "different-event-id",
                        TaskFinopsPolicy.TaskState.ADMITTED, 10, "00:00:02Z")));

        assertNotEquals(baseline.checksum(), changed.checksum());
    }

    @Test
    void rejectsSequenceGapDuplicateAndOutOfOrderEvents() {
        var genesis = event("task-a", 1, 1, "a-1",
                TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT, 0, "00:00:00Z");

        assertCode("ELMOS_MTF_ANALYTICS_SEQUENCE_GAP", () ->
                TaskFinopsAnalytics.rebuild(CONTEXT, List.of(genesis,
                        event("task-a", 1, 3, "a-3",
                                TaskFinopsPolicy.TaskState.ADMITTED, 5, "00:00:02Z"))));
        assertCode("ELMOS_MTF_ANALYTICS_DUPLICATE_SEQUENCE", () ->
                TaskFinopsAnalytics.rebuild(CONTEXT, List.of(genesis,
                        event("task-a", 1, 1, "a-copy",
                                TaskFinopsPolicy.TaskState.ADMITTED, 5, "00:00:02Z"))));
        assertCode("ELMOS_MTF_ANALYTICS_OUT_OF_ORDER_SEQUENCE", () ->
                TaskFinopsAnalytics.rebuild(CONTEXT, List.of(
                        genesis,
                        event("task-a", 1, 2, "a-2",
                                TaskFinopsPolicy.TaskState.ADMITTED, 5, "00:00:01Z"),
                        event("task-a", 1, 1, "a-late",
                                TaskFinopsPolicy.TaskState.RUNNING, 10, "00:00:02Z"))));
    }

    @Test
    void rejectsDuplicateIdentityIllegalTransitionAndProgressRegression() {
        var genesis = event("task-a", 1, 1, "shared-id",
                TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT, 0, "00:00:00Z");

        assertCode("ELMOS_MTF_ANALYTICS_DUPLICATE_EVENT_ID", () ->
                TaskFinopsAnalytics.rebuild(CONTEXT, List.of(
                        genesis,
                        event("task-b", 1, 1, "shared-id",
                                TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT, 0, "00:00:01Z"))));
        assertCode("ELMOS_MTF_ANALYTICS_ILLEGAL_TRANSITION", () ->
                TaskFinopsAnalytics.rebuild(CONTEXT, List.of(
                        genesis,
                        event("task-a", 1, 2, "a-2",
                                TaskFinopsPolicy.TaskState.RUNNING, 10, "00:00:01Z"))));
        assertCode("ELMOS_MTF_ANALYTICS_PROGRESS_REGRESSION", () ->
                TaskFinopsAnalytics.rebuild(CONTEXT, List.of(
                        genesis,
                        event("task-a", 1, 2, "a-2",
                                TaskFinopsPolicy.TaskState.ADMITTED, 20, "00:00:01Z"),
                        event("task-a", 1, 3, "a-3",
                                TaskFinopsPolicy.TaskState.RUNNING, 19, "00:00:02Z"))));
        assertCode("ELMOS_MTF_ANALYTICS_TIME_REGRESSION", () ->
                TaskFinopsAnalytics.rebuild(CONTEXT, List.of(
                        genesis,
                        event("task-a", 1, 2, "a-time-regression",
                                TaskFinopsPolicy.TaskState.ADMITTED, 5,
                                "00:00:02Z"),
                        event("task-a", 1, 3, "a-earlier",
                                TaskFinopsPolicy.TaskState.RUNNING, 10,
                                "00:00:01Z"))));
    }

    @Test
    void rejectsPayloadSelectedTenantAndInvalidGenesis() {
        var wrongScope = new TaskFinopsAnalytics.JournalEvent(
                "org-other", "account-1", "task-a", 1, 1, "a-1",
                TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT, (short) 0,
                Instant.parse("2026-08-25T00:00:00Z"));
        assertCode("ELMOS_MTF_ANALYTICS_SCOPE_MISMATCH", () ->
                TaskFinopsAnalytics.rebuild(CONTEXT, List.of(wrongScope)));
        assertCode("ELMOS_MTF_ANALYTICS_GENESIS_STATE_INVALID", () ->
                TaskFinopsAnalytics.rebuild(CONTEXT, List.of(
                        event("task-a", 1, 1, "a-1",
                                TaskFinopsPolicy.TaskState.ADMITTED, 0, "00:00:00Z"))));
    }

    @Test
    void rejectsMissingRunAndAllowsProgressEventsWithinOneState() {
        assertCode("ELMOS_MTF_ANALYTICS_RUN_GAP", () ->
                TaskFinopsAnalytics.rebuild(CONTEXT, List.of(
                        event("task-a", 2, 1, "run-2-event-1",
                                TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT,
                                0, "00:00:00Z"))));

        var result = TaskFinopsAnalytics.rebuild(CONTEXT, List.of(
                event("task-a", 1, 1, "a-1",
                        TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT, 0, "00:00:00Z"),
                event("task-a", 1, 2, "a-2",
                        TaskFinopsPolicy.TaskState.ADMITTED, 10, "00:00:01Z"),
                event("task-a", 1, 3, "a-3",
                        TaskFinopsPolicy.TaskState.RUNNING, 20, "00:00:02Z"),
                event("task-a", 1, 4, "a-4",
                        TaskFinopsPolicy.TaskState.RUNNING, 30, "00:00:03Z")));
        assertEquals(4, result.runs().getFirst().lastEventSequence());
    }

    @Test
    void emptyInputIsExplicitlyUnknownRatherThanComplete() {
        var result = TaskFinopsAnalytics.rebuild(CONTEXT, List.of());
        assertEquals(TaskFinopsAnalytics.InputContinuity.UNKNOWN,
                result.inputContinuity());
        assertEquals(Instant.EPOCH, result.asOf());
        assertEquals(0, result.eventCount());
    }

    private static TaskFinopsAnalytics.JournalEvent event(
            String taskId,
            long run,
            long sequence,
            String eventId,
            TaskFinopsPolicy.TaskState state,
            int progress,
            String time
    ) {
        return new TaskFinopsAnalytics.JournalEvent(
                "org-1", "account-1", taskId, run, sequence, eventId, state,
                (short) progress, Instant.parse("2026-08-25T" + time));
    }

    private static void assertCode(String expected, Runnable action) {
        var exception = assertThrows(TaskFinopsAnalytics.AnalyticsException.class, action::run);
        assertEquals(expected, exception.code());
    }
}
