package io.elmos.snapshot;

import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SnapshotGlobalReconciliationSchedulerTest {
    @Test void isolatesTenantFailureAndCompletesEveryClaimedFence() {
        RecordingQueue queue = new RecordingQueue(List.of(
                lease("org-a", 4), lease("org-b", 8)));
        List<String> visited = new ArrayList<>();
        SnapshotGlobalReconciliationScheduler scheduler =
                new SnapshotGlobalReconciliationScheduler(queue, (organization, limit) -> {
                    visited.add(organization + ":" + limit);
                    if (organization.equals("org-a")) {
                        throw new SecurityException("corrupt tenant journal");
                    }
                    return new SnapshotProvisionalRootReconciler.ReconciliationReport(
                            1, 1, 0, List.of());
                });

        SnapshotGlobalReconciliationScheduler.RunReport report = scheduler.runOnce(
                "scheduler-a", 8, 100, Duration.ofSeconds(30), Duration.ofMinutes(2));

        assertEquals(List.of("org-a:100", "org-b:100"), visited);
        assertEquals(2, report.claimed());
        assertEquals(2, report.completed());
        assertEquals(1, report.remaining());
        assertEquals(1, report.failures().size());
        assertEquals("SecurityException", report.failures().getFirst().code());
        assertEquals(2, queue.completions.size());
        assertFalse(queue.completions.getFirst().successful());
        assertEquals(Duration.ofMinutes(2), queue.completions.getFirst().retry());
        assertTrue(queue.completions.getLast().successful());
        assertEquals(Duration.ZERO, queue.completions.getLast().retry());
    }

    @Test void rejectsAnAdapterThatBreaksTheClaimBound() {
        RecordingQueue queue = new RecordingQueue(List.of(
                lease("org-a", 1), lease("org-b", 2)));
        SnapshotGlobalReconciliationScheduler scheduler =
                new SnapshotGlobalReconciliationScheduler(queue,
                        (organization, limit) -> new
                                SnapshotProvisionalRootReconciler.ReconciliationReport(
                                0, 0, 0, List.of()));

        assertThrows(IllegalStateException.class, () -> scheduler.runOnce(
                "scheduler-a", 1, 10,
                Duration.ofSeconds(30), Duration.ofSeconds(30)));
        assertTrue(queue.completions.isEmpty());
    }

    private static SnapshotReconciliationWorkQueue.WorkLease lease(
            String organizationId, long fence
    ) {
        return new SnapshotReconciliationWorkQueue.WorkLease(
                organizationId, "scheduler-a", fence,
                Instant.parse("2026-08-24T01:00:00Z"));
    }

    private record Completion(
            SnapshotReconciliationWorkQueue.WorkLease lease,
            boolean successful,
            Duration retry
    ) { }

    private static final class RecordingQueue
            implements SnapshotReconciliationWorkQueue {
        private final List<WorkLease> claims;
        private final List<Completion> completions = new ArrayList<>();

        private RecordingQueue(List<WorkLease> claims) {
            this.claims = claims;
        }

        @Override public List<WorkLease> claim(
                String workerId, int limit, Duration leaseDuration
        ) {
            return claims;
        }

        @Override public boolean complete(
                WorkLease lease, boolean successful, Duration retryDelay
        ) {
            completions.add(new Completion(lease, successful, retryDelay));
            return !successful;
        }
    }
}
