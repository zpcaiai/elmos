package io.elmos.workflow;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TaskFinopsWorkflowStartPayloadTest {
    private static final String DIGEST = "a".repeat(64);
    private static final Instant COMPLETED_AT = Instant.parse("2026-08-26T00:00:00Z");

    @Test
    void bindsTypedPayloadDigestAndSearchAttributesToAuthenticatedContext() {
        var context = context();
        var payload = TaskFinopsWorkflowStartPayload.forTask(
                context, "task-a", 1, TaskFinopsPolicy.WorkloadClass.GENERATION, DIGEST);

        assertEquals(1, payload.payloadVersion());
        assertEquals(TaskFinopsWorkflowStartPayload.SCHEMA_VERSION, payload.schemaVersion());
        assertEquals("mtf-task-a", payload.payload().workflowId());
        assertEquals(DIGEST, payload.payload().requestDigest());
        assertEquals(payload.payloadDigest(), payload.searchAttributes().get(
                TaskFinopsWorkflowStartPayload.PAYLOAD_DIGEST_ATTRIBUTE));
        assertEquals(Map.of(
                "organization_id", "org-a",
                "account_id", "account-a",
                "actor_id", "actor-a",
                "request_id", "request-a",
                "task_id", "task-a",
                "run_number", "1",
                "workflow_id", "mtf-task-a",
                "workload_class", "GENERATION",
                "policy_version", WorkloadAwareScheduler.POLICY_VERSION,
                "schema_version", TaskFinopsWorkflowStartPayload.SCHEMA_VERSION,
                "payload_version", "1",
                "payload_digest", payload.payloadDigest()),
                payload.searchAttributes());
        assertThrows(UnsupportedOperationException.class, () ->
                payload.searchAttributes().put("task_id", "other-task"));

        var differentActor = new TaskFinopsWorkflowStartPayload(
                new TaskFinopsPort.AuthenticatedContext(
                        "org-a", "account-a", "actor-b", "request-a"),
                payload.payload());
        assertNotEquals(payload.payloadDigest(), differentActor.payloadDigest());

        var retryRequest = new TaskFinopsWorkflowStartPayload(
                new TaskFinopsPort.AuthenticatedContext(
                        "org-a", "account-a", "actor-a", "request-b"),
                payload.payload());
        assertEquals(payload.payloadDigest(), retryRequest.payloadDigest());
    }

    @Test
    void rejectsUnboundOrUnversionedWorkflowInputs() {
        assertThrows(IllegalArgumentException.class, () ->
                new TaskFinopsWorkflowStartPayload.TypedPayload(
                        "task-a", 1, "mtf-task-a",
                        TaskFinopsPolicy.WorkloadClass.GENERATION,
                        1, DIGEST, null, WorkloadAwareScheduler.POLICY_VERSION));
        assertThrows(IllegalArgumentException.class, () ->
                TaskFinopsWorkflowStartPayload.forTask(
                        context(), "task-a", 1,
                        TaskFinopsPolicy.WorkloadClass.GENERATION, "not-a-digest"));
        assertThrows(IllegalArgumentException.class, () ->
                TaskFinopsWorkflowStartPayload.deterministicWorkflowId("task-a", 0));
        assertEquals("mtf-task-a-r2",
                TaskFinopsWorkflowStartPayload.deterministicWorkflowId("task-a", 2));
    }

    @Test
    void terminalProjectionPreservesLocalOnlyEvidenceBoundary() {
        var payload = TaskFinopsWorkflowStartPayload.forTask(
                context(), "task-a", 1, TaskFinopsPolicy.WorkloadClass.GENERATION, DIGEST);
        var progress = new TaskFinopsPolicy.Progress((short) 100, 2_000, 0, 0);
        var projection = payload.terminalProjection(
                TaskFinopsPolicy.TaskState.SUCCEEDED, progress, COMPLETED_AT, DIGEST);

        assertEquals(context(), projection.context());
        assertEquals("task-a", projection.taskId());
        assertEquals("mtf-task-a", projection.workflowId());
        assertEquals(TaskFinopsAnalytics.ExternalEvidenceState.NOT_RUN,
                projection.externalEvidence());
        assertEquals(TaskFinopsAnalytics.ProviderOutcome.UNKNOWN,
                projection.providerOutcome());
        assertEquals(TaskFinopsAnalytics.ProductionCertification.NOT_CERTIFIED,
                projection.productionCertification());
        assertEquals(64, projection.projectionDigest().length());
        assertEquals(projection.projectionDigest(), payload.terminalProjection(
                TaskFinopsPolicy.TaskState.SUCCEEDED, progress, COMPLETED_AT, DIGEST)
                .projectionDigest());

        assertThrows(IllegalArgumentException.class, () -> payload.terminalProjection(
                TaskFinopsPolicy.TaskState.RUNNING, progress, COMPLETED_AT, DIGEST));
        assertThrows(IllegalArgumentException.class, () -> payload.terminalProjection(
                TaskFinopsPolicy.TaskState.SUCCEEDED, progress, COMPLETED_AT, null));
        assertThrows(IllegalArgumentException.class, () -> payload.terminalProjection(
                TaskFinopsPolicy.TaskState.FAILED,
                new TaskFinopsPolicy.Progress((short) 100, 2_000, 0, 0),
                COMPLETED_AT, null));
    }

    private static TaskFinopsPort.AuthenticatedContext context() {
        return new TaskFinopsPort.AuthenticatedContext(
                "org-a", "account-a", "actor-a", "request-a");
    }
}
