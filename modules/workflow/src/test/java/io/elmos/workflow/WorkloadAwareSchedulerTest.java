package io.elmos.workflow;

import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class WorkloadAwareSchedulerTest {
    @Test
    void exposesTheSameVersionedQueuesAsTheDurableAdmissionProfile() {
        assertEquals("mtf.parsing.v1",
                WorkloadAwareScheduler.profileFor(TaskFinopsPolicy.WorkloadClass.PARSING).taskQueue());
        assertEquals("mtf.model-gpu.v1",
                WorkloadAwareScheduler.profileFor(TaskFinopsPolicy.WorkloadClass.MODEL_GPU).taskQueue());
        assertEquals(6, WorkloadAwareScheduler.queueCatalog().size());
        assertTrue(WorkloadAwareScheduler.queueCatalog().values().stream()
                .allMatch(profile -> profile.runtimeStatus()
                        == WorkloadAwareScheduler.RuntimeStatus.NOT_RUN));
    }

    @Test
    void metricsAreAccountBoundAndDoNotHideSaturationOrThrottling() {
        var context = new TaskFinopsPort.AuthenticatedContext(
                "org-1", "acct-1", "actor-1", "request-1");
        var snapshot = new WorkloadAwareScheduler.QueueSnapshot(
                context,
                WorkloadAwareScheduler.profileFor(TaskFinopsPolicy.WorkloadClass.GENERATION),
                17,
                Duration.ofSeconds(45),
                10,
                3,
                Instant.parse("2026-08-26T02:00:00Z"));
        List<WorkloadAwareScheduler.Metric> metrics = WorkloadAwareScheduler.metrics(snapshot);

        assertEquals(5, metrics.size());
        assertEquals("1.250000000",
                metrics.stream()
                        .filter(metric -> metric.name().endsWith("saturation_ratio"))
                        .findFirst().orElseThrow().value().toPlainString());
        assertEquals("acct-1", metrics.getFirst().labels().get("account_id"));
        assertEquals("mtf.generation.v1", metrics.getFirst().labels().get("task_queue"));
        assertEquals("45.000", metrics.stream()
                .filter(metric -> metric.name().endsWith("age_seconds"))
                .findFirst().orElseThrow().value().toPlainString());
    }

    @Test
    void metricSinkIsTheOnlyEffectBoundary() {
        var context = new TaskFinopsPort.AuthenticatedContext(
                "org-1", "acct-1", "actor-1", "request-2");
        var snapshot = new WorkloadAwareScheduler.QueueSnapshot(
                context,
                WorkloadAwareScheduler.profileFor(TaskFinopsPolicy.WorkloadClass.PARSING),
                0, Duration.ZERO, 0, 0,
                Instant.parse("2026-08-26T02:00:00Z"));
        List<WorkloadAwareScheduler.Metric> received = new ArrayList<>();
        WorkloadAwareScheduler.emit(snapshot, received::add);

        assertEquals(5, received.size());
        assertFalse(received.isEmpty());
        assertTrue(received.stream().allMatch(metric -> metric.asOf()
                .equals(Instant.parse("2026-08-26T02:00:00Z"))));
    }

    @Test
    void rejectsNegativeQueueObservations() {
        var context = new TaskFinopsPort.AuthenticatedContext(
                "org-1", "acct-1", "actor-1", "request-3");
        assertThrows(IllegalArgumentException.class, () -> new WorkloadAwareScheduler.QueueSnapshot(
                context,
                WorkloadAwareScheduler.profileFor(TaskFinopsPolicy.WorkloadClass.PARSING),
                -1, Duration.ZERO, 0, 0, Instant.EPOCH));
    }
}
