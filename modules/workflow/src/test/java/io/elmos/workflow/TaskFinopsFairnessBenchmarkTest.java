package io.elmos.workflow;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class TaskFinopsFairnessBenchmarkTest {
    private static final Instant NOW = Instant.parse("2026-01-01T00:10:00Z");

    @Test
    void boundsNoisyNeighborAndRequiresEachTenantToAppear() {
        TaskFinopsFairnessBenchmark.BenchmarkReport report =
                TaskFinopsFairnessBenchmark.evaluate(
                        new TaskFinopsFairnessBenchmark.BenchmarkRequest(
                                List.of(
                                        candidate("a-1", "tenant-a", 1, 1),
                                        candidate("a-2", "tenant-a", 2, 1),
                                        candidate("b-1", "tenant-b", 1, 1)),
                                3, 2, 4, NOW));

        assertEquals(List.of("a-1", "b-1", "a-2"), report.dispatchOrder());
        assertEquals(2, report.dispatchesByTenant().get("tenant-a"));
        assertEquals(1, report.dispatchesByTenant().get("tenant-b"));
        assertTrue(report.starvationFree());
        assertTrue(report.noisyNeighborBounded());
        assertEquals(TaskFinopsFairnessBenchmark.RuntimeStatus.NOT_RUN,
                report.runtimeStatus());
    }

    private static TaskFinopsPolicy.QueueCandidate candidate(
            String taskId, String tenantId, int service, int resourceUnits) {
        return new TaskFinopsPolicy.QueueCandidate(
                taskId, tenantId, 100, NOW.minusSeconds(60), resourceUnits, 1, service);
    }
}
