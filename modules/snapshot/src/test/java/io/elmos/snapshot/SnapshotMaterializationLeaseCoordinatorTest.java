package io.elmos.snapshot;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.LockSupport;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SnapshotMaterializationLeaseCoordinatorTest {
    private final ScheduledExecutorService heartbeat =
            Executors.newSingleThreadScheduledExecutor();

    @AfterEach void stopExecutor() {
        heartbeat.shutdownNow();
    }

    @Test void heartbeatsValidatesFenceAndReleasesAfterPublication() throws Exception {
        RecordingStore leases = new RecordingStore(false);
        SnapshotMaterializationLeaseCoordinator coordinator =
                new SnapshotMaterializationLeaseCoordinator(
                        leases, heartbeat, "control-plane-a",
                        Duration.ofSeconds(15), Duration.ofMillis(10));

        String result = coordinator.withLease(snapshot(), () -> {
            awaitHeartbeats(leases.renewals, 2);
            return "published";
        });

        assertEquals("published", result);
        assertTrue(leases.renewals.get() >= 2);
        assertEquals(1, leases.validations.get());
        assertEquals(1, leases.releases.get());
        assertTrue(leases.releasedAfterValidation.get());
    }

    @Test void heartbeatFailureFailsClosedAndStillReleasesExactFence() {
        RecordingStore leases = new RecordingStore(true);
        SnapshotMaterializationLeaseCoordinator coordinator =
                new SnapshotMaterializationLeaseCoordinator(
                        leases, heartbeat, "control-plane-a",
                        Duration.ofSeconds(15), Duration.ofMillis(10));

        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> coordinator.withLease(snapshot(), () -> {
                    awaitHeartbeats(leases.renewals, 1);
                    LockSupport.parkNanos(Duration.ofMillis(50).toNanos());
                    return "must-not-publish";
                }));

        assertTrue(failure.getMessage().contains("heartbeat failed"));
        assertEquals(0, leases.validations.get());
        assertEquals(1, leases.releases.get());
    }

    @Test void foreignLeaseIdentityIsRejectedBeforeTheOperationRuns() {
        RecordingStore leases = new RecordingStore(false) {
            @Override public SnapshotMaterializationLease acquire(
                    SnapshotPorts.ArtifactResourceContext resource,
                    String snapshotId,
                    String leaseId,
                    String holderId,
                    Duration duration
            ) {
                return lease("foreign-snapshot", leaseId, holderId, 1);
            }
        };
        SnapshotMaterializationLeaseCoordinator coordinator =
                new SnapshotMaterializationLeaseCoordinator(
                        leases, heartbeat, "control-plane-a",
                        Duration.ofSeconds(15), Duration.ofMillis(10));
        AtomicBoolean invoked = new AtomicBoolean();

        assertThrows(SecurityException.class,
                () -> coordinator.withLease(snapshot(), () -> {
                    invoked.set(true);
                    return "unsafe";
                }));

        assertTrue(!invoked.get());
        assertEquals(0, leases.releases.get());
    }

    private static void awaitHeartbeats(AtomicInteger count, int expected) {
        long deadline = System.nanoTime() + Duration.ofSeconds(2).toNanos();
        while (count.get() < expected && System.nanoTime() < deadline) {
            LockSupport.parkNanos(Duration.ofMillis(1).toNanos());
        }
        if (count.get() < expected) {
            throw new IllegalStateException("heartbeat did not run in time");
        }
    }

    private static SnapshotModel.RepositorySnapshot snapshot() {
        return new SnapshotModel.RepositorySnapshot(
                "snapshot-1", "org-a", "repo-1", "refs/heads/main",
                "a".repeat(40), "b".repeat(40),
                "cas:sha256:" + "c".repeat(64), "c".repeat(64), 10,
                "cas:sha256:" + "d".repeat(64), "d".repeat(64), 1,
                SnapshotModel.Status.AVAILABLE,
                Instant.parse("2026-08-24T00:00:00Z"));
    }

    private static SnapshotMaterializationLease lease(
            String snapshotId, String leaseId, String holderId, long fence
    ) {
        Instant acquired = Instant.parse("2026-08-24T00:00:00Z");
        return new SnapshotMaterializationLease(
                "org-a", "repo-1", snapshotId, leaseId, holderId, fence,
                acquired, acquired.plusSeconds(15));
    }

    private static class RecordingStore implements SnapshotMaterializationLease.Store {
        private final boolean failRenewal;
        private final AtomicInteger renewals = new AtomicInteger();
        private final AtomicInteger validations = new AtomicInteger();
        private final AtomicInteger releases = new AtomicInteger();
        private final AtomicBoolean releasedAfterValidation = new AtomicBoolean();

        RecordingStore(boolean failRenewal) {
            this.failRenewal = failRenewal;
        }

        @Override public SnapshotMaterializationLease acquire(
                SnapshotPorts.ArtifactResourceContext resource,
                String snapshotId,
                String leaseId,
                String holderId,
                Duration duration
        ) {
            return lease(snapshotId, leaseId, holderId, 1);
        }

        @Override public SnapshotMaterializationLease renew(
                SnapshotMaterializationLease lease,
                Duration duration
        ) {
            renewals.incrementAndGet();
            if (failRenewal) throw new IllegalStateException("database unavailable");
            return new SnapshotMaterializationLease(
                    lease.organizationId(), lease.repositoryId(), lease.snapshotId(),
                    lease.leaseId(), lease.holderId(), lease.fencingToken(),
                    lease.acquiredAt(), lease.expiresAt().plusSeconds(15));
        }

        @Override public SnapshotMaterializationLease requireActive(
                SnapshotMaterializationLease lease
        ) {
            validations.incrementAndGet();
            return lease;
        }

        @Override public void release(SnapshotMaterializationLease lease) {
            releasedAfterValidation.set(validations.get() > 0);
            releases.incrementAndGet();
        }
    }
}
