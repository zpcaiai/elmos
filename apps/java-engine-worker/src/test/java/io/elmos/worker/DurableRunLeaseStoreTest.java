package io.elmos.worker;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Queue;
import java.util.UUID;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class DurableRunLeaseStoreTest {
    @TempDir Path temporary;

    @Test
    void enforcesGlobalAndTenantCapacityAndReleasesWithReceipt() {
        MutableClock clock = new MutableClock(Instant.parse("2026-07-29T00:00:00Z"));
        DurableRunLeaseStore store = new DurableRunLeaseStore(
                temporary, "spring-upgrade", 2, 1,
                Duration.ofHours(1), Duration.ofMinutes(2), clock);
        String digest = "1".repeat(64);
        var first = store.acquire("tenant-a", UUID.randomUUID().toString(), clock.instant(), digest);

        var tenantFailure = assertThrows(DurableRunLeaseStore.LeaseException.class,
                () -> store.acquire(
                        "tenant-a", UUID.randomUUID().toString(), clock.instant(), digest));
        assertEquals(
                DurableRunLeaseStore.Failure.QUEUE_TENANT_CAPACITY_REACHED,
                tenantFailure.failure());

        var second = store.acquire(
                "tenant-b", UUID.randomUUID().toString(), clock.instant(), digest);
        var globalFailure = assertThrows(DurableRunLeaseStore.LeaseException.class,
                () -> store.acquire(
                        "tenant-c", UUID.randomUUID().toString(), clock.instant(), digest));
        assertEquals(
                DurableRunLeaseStore.Failure.QUEUE_GLOBAL_CAPACITY_REACHED,
                globalFailure.failure());

        first.release("SUCCEEDED");
        second.release("BLOCKED");
        var admitted = store.acquire(
                "tenant-a", UUID.randomUUID().toString(), clock.instant(), digest);
        admitted.release("CANCELLED");
    }

    @Test
    void expiresMissedHeartbeatAndRejectsQueueItemsPastTtl() {
        MutableClock clock = new MutableClock(Instant.parse("2026-07-29T00:00:00Z"));
        DurableRunLeaseStore store = new DurableRunLeaseStore(
                temporary, "spring-upgrade", 1, 1,
                Duration.ofMinutes(5), Duration.ofSeconds(30), clock);
        String digest = "2".repeat(64);
        var stale = store.acquire(
                "tenant-a", UUID.randomUUID().toString(), clock.instant(), digest);

        clock.advance(Duration.ofSeconds(31));
        var replacement = store.acquire(
                "tenant-b", UUID.randomUUID().toString(), clock.instant(), digest);
        var lost = assertThrows(
                DurableRunLeaseStore.LeaseException.class, stale::heartbeat);
        assertEquals(DurableRunLeaseStore.Failure.QUEUE_LEASE_LOST, lost.failure());
        replacement.release("SUCCEEDED");

        var expired = assertThrows(DurableRunLeaseStore.LeaseException.class,
                () -> store.acquire(
                        "tenant-a", UUID.randomUUID().toString(),
                        clock.instant().minus(Duration.ofMinutes(6)), digest));
        assertEquals(DurableRunLeaseStore.Failure.QUEUE_ITEM_EXPIRED, expired.failure());
    }

    /**
     * Regression guard for concurrent queue mutation inside one worker JVM.
     *
     * <p>{@link java.nio.channels.FileLock} is held on behalf of the whole JVM
     * rather than the acquiring thread, so the queue's file lock alone does not
     * serialise threads within one worker: an overlapping request raises
     * OverlappingFileLockException instead of blocking. That exception is
     * unchecked, so it escaped the store and reached the heartbeat handler in
     * {@code SpringUpgradeRunService}, which reads any heartbeat failure as a
     * lost lease and destroys the run's build process. One run being admitted
     * could therefore cancel an unrelated healthy run.</p>
     *
     * <p>Eight threads reproduce it deterministically; before the in-process
     * monitor was added only one of them survived.</p>
     */
    @Test
    void serialisesConcurrentQueueMutationsWithinOneJvm() throws Exception {
        int workers = 8;
        Clock clock = Clock.fixed(Instant.parse("2026-07-29T00:00:00Z"), ZoneOffset.UTC);
        DurableRunLeaseStore store = new DurableRunLeaseStore(
                temporary, "spring-upgrade", workers, workers,
                Duration.ofHours(1), Duration.ofMinutes(2), clock);
        String digest = "2".repeat(64);

        CyclicBarrier start = new CyclicBarrier(workers);
        Queue<Throwable> failures = new ConcurrentLinkedQueue<>();
        AtomicInteger completed = new AtomicInteger();
        List<Thread> threads = new ArrayList<>();
        for (int worker = 0; worker < workers; worker++) {
            String tenant = "tenant-" + worker;
            Thread thread = new Thread(() -> {
                try {
                    start.await();
                    DurableRunLeaseStore.Lease lease = store.acquire(
                            tenant, UUID.randomUUID().toString(), clock.instant(), digest);
                    for (int beat = 0; beat < 40; beat++) lease.heartbeat();
                    lease.release("SUCCEEDED");
                    completed.incrementAndGet();
                } catch (Throwable error) {
                    failures.add(error);
                }
            });
            threads.add(thread);
            thread.start();
        }
        for (Thread thread : threads) thread.join();

        assertEquals(List.of(), failures.stream().map(Throwable::toString).toList());
        assertEquals(workers, completed.get());
    }

    private static final class MutableClock extends Clock {
        private Instant current;
        private MutableClock(Instant current) { this.current = current; }
        void advance(Duration duration) { current = current.plus(duration); }
        @Override public ZoneId getZone() { return ZoneOffset.UTC; }
        @Override public Clock withZone(ZoneId zone) { return this; }
        @Override public Instant instant() { return current; }
    }
}
