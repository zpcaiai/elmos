package io.elmos.workflow;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class TaskFinopsWorkflowHistoryPolicyTest {
    @Test
    void continuesAsNewOnlyWhenAHistoryLimitIsReached() {
        TaskFinopsWorkflowHistoryPolicy.HistoryDecisionResult result =
                TaskFinopsWorkflowHistoryPolicy.evaluateHistory(
                        new TaskFinopsWorkflowHistoryPolicy.HistorySnapshot(
                                "mtf-task", 2, 100, 400, 1, false),
                        new TaskFinopsWorkflowHistoryPolicy.HistoryLimits(100, 1000, 3));

        assertEquals(TaskFinopsWorkflowHistoryPolicy.HistoryDecision.CONTINUE_AS_NEW,
                result.decision());
        assertEquals(3, result.nextRunNumber());
        assertEquals("NOT_RUN", result.runtimeEvidence());
    }

    @Test
    void duplicateStartWithUnknownOutcomeRequiresReconciliation() {
        TaskFinopsPort.AuthenticatedContext context =
                new TaskFinopsPort.AuthenticatedContext(
                        "org-1", "acct-1", "actor-1", "req-1", "SESSION");
        TaskFinopsWorkflowStartPayload payload = TaskFinopsWorkflowStartPayload.forTask(
                context, "task-1", 1, TaskFinopsPolicy.WorkloadClass.PARSING,
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
        TaskFinopsWorkflowHistoryPolicy.StartDecisionResult result =
                TaskFinopsWorkflowHistoryPolicy.evaluateStart(payload,
                        new TaskFinopsWorkflowHistoryPolicy.ExistingStart(
                                payload.payload().workflowId(), payload.payloadDigest(),
                                TaskFinopsWorkflowHistoryPolicy.ExistingOutcome.UNKNOWN));

        assertEquals(TaskFinopsWorkflowHistoryPolicy.StartDecision.REQUIRE_RECONCILIATION,
                result.decision());
        assertEquals("UNKNOWN_START_OUTCOME", result.reason());
    }
}
