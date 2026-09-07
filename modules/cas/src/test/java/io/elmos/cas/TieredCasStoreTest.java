package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;

class TieredCasStoreTest {

    private final AtomicLong clock = new AtomicLong(1_000);

    private static byte[] bytes(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    private TieredCasStore tiered(InMemoryCasStore local, InMemoryCasStore shared, TieredCasStore.TierPolicy policy) {
        return new TieredCasStore(local, shared, policy, clock::get);
    }

    @Test void readThroughPopulatesTheLocalTier() {
        InMemoryCasStore local = new InMemoryCasStore("l1");
        InMemoryCasStore shared = new InMemoryCasStore("l2");
        byte[] content = bytes("shared object");
        CasDigest digest = CasDigest.of(content);
        shared.put(digest, content);

        TieredCasStore store = tiered(local, shared, TieredCasStore.TierPolicy.unbounded());
        assertFalse(local.contains(digest));
        assertArrayEquals(content, store.get(digest));
        assertTrue(local.contains(digest));
    }

    @Test void bestEffortPutIsQueuedAndOnlyDurableAfterFlush() {
        InMemoryCasStore local = new InMemoryCasStore("l1");
        InMemoryCasStore shared = new InMemoryCasStore("l2");
        TieredCasStore store = tiered(local, shared, TieredCasStore.TierPolicy.unbounded());
        byte[] content = bytes("intermediate");
        CasDigest digest = CasDigest.of(content);

        store.put(digest, content);
        assertTrue(local.contains(digest));
        assertFalse(shared.contains(digest));
        assertEquals(java.util.Set.of(digest), store.pendingDurability());

        assertEquals(List.of(digest), store.flushWriteBack());
        assertTrue(shared.contains(digest));
        assertTrue(store.pendingDurability().isEmpty());
    }

    @Test void durablePutReachesSharedStorageBeforeReturning() {
        InMemoryCasStore local = new InMemoryCasStore("l1");
        InMemoryCasStore shared = new InMemoryCasStore("l2");
        TieredCasStore store = tiered(local, shared, TieredCasStore.TierPolicy.unbounded());
        byte[] content = bytes("critical output");
        CasDigest digest = CasDigest.of(content);

        store.putDurable(digest, content);
        assertTrue(shared.contains(digest));
        assertTrue(local.contains(digest));
        assertTrue(store.pendingDurability().isEmpty());
    }

    @Test void durablePutCrossesEveryNestedTierBeforeReturning() {
        InMemoryCasStore outerLocal = new InMemoryCasStore("outer-l1");
        InMemoryCasStore innerLocal = new InMemoryCasStore("inner-l1");
        InMemoryCasStore authoritative = new InMemoryCasStore("authoritative");
        TieredCasStore inner = tiered(innerLocal, authoritative, TieredCasStore.TierPolicy.unbounded());
        TieredCasStore outer = new TieredCasStore(outerLocal, inner,
                TieredCasStore.TierPolicy.unbounded(), clock::get);
        byte[] content = bytes("nested durable output");
        CasDigest digest = CasDigest.of(content);

        outer.putDurable(digest, content);

        assertTrue(authoritative.contains(digest));
        assertTrue(inner.pendingDurability().isEmpty());
        assertTrue(outer.pendingDurability().isEmpty());
    }

    @Test void writeBackFlushCrossesEveryNestedTier() {
        InMemoryCasStore outerLocal = new InMemoryCasStore("outer-l1");
        InMemoryCasStore innerLocal = new InMemoryCasStore("inner-l1");
        InMemoryCasStore authoritative = new InMemoryCasStore("authoritative");
        TieredCasStore inner = tiered(innerLocal, authoritative, TieredCasStore.TierPolicy.unbounded());
        TieredCasStore outer = new TieredCasStore(outerLocal, inner,
                TieredCasStore.TierPolicy.unbounded(), clock::get);
        byte[] content = bytes("nested write back");
        CasDigest digest = CasDigest.of(content);

        outer.put(digest, content);
        assertFalse(authoritative.contains(digest));

        assertEquals(List.of(digest), outer.flushWriteBack());
        assertTrue(authoritative.contains(digest));
        assertTrue(inner.pendingDurability().isEmpty());
        assertTrue(outer.pendingDurability().isEmpty());
    }

    @Test void writeBackFlushCrossesNestedTierThatAlreadyHasOnlyAPendingLocalCopy() {
        InMemoryCasStore outerLocal = new InMemoryCasStore("outer-l1");
        InMemoryCasStore innerLocal = new InMemoryCasStore("inner-l1");
        InMemoryCasStore authoritative = new InMemoryCasStore("authoritative");
        TieredCasStore inner = tiered(innerLocal, authoritative,
                TieredCasStore.TierPolicy.unbounded());
        TieredCasStore outer = new TieredCasStore(outerLocal, inner,
                TieredCasStore.TierPolicy.unbounded(), clock::get);
        byte[] content = bytes("inner pending before outer admission");
        CasDigest digest = CasDigest.of(content);
        inner.put(digest, content);
        assertTrue(inner.contains(digest));
        assertEquals(Set.of(digest), inner.pendingDurability());
        assertFalse(authoritative.contains(digest));

        outer.put(digest, content);

        assertEquals(Set.of(digest), outer.pendingDurability(),
                "nested L1 visibility must not clear the outer durability debt");
        assertEquals(List.of(digest), outer.flushWriteBack());
        assertTrue(authoritative.contains(digest));
        assertTrue(inner.pendingDurability().isEmpty());
        assertTrue(outer.pendingDurability().isEmpty());
    }

    @Test void poisonedSharedCopyKeepsWriteBackQueuedUntilVerifiedRetryRepairsIt() {
        InMemoryCasStore local = new InMemoryCasStore("l1");
        InMemoryCasStore shared = new InMemoryCasStore("l2");
        TieredCasStore store = tiered(local, shared, TieredCasStore.TierPolicy.unbounded());
        byte[] content = bytes("authoritative content");
        CasDigest digest = CasDigest.of(content);
        shared.put(digest, content);
        shared.corruptForFaultInjection(digest, bytes("poisoned shared bytes"));

        store.put(digest, content);

        assertEquals(Set.of(digest), store.pendingDurability());
        assertThrows(CasExceptions.CasCorruptionException.class, store::flushWriteBack);
        assertEquals(Set.of(digest), store.pendingDurability(),
                "failed read-back verification must preserve the debt");
        assertFalse(shared.contains(digest),
                "the verifying shared store quarantines the poisoned copy");
        assertEquals(List.of(digest), store.flushWriteBack());
        assertArrayEquals(content, shared.get(digest));
        assertTrue(store.pendingDurability().isEmpty());
    }

    @Test void batchDurablePutDoesNotMistakeNestedVisibilityForDurability() {
        InMemoryCasStore outerLocal = new InMemoryCasStore("outer-l1");
        InMemoryCasStore innerLocal = new InMemoryCasStore("inner-l1");
        InMemoryCasStore authoritative = new InMemoryCasStore("authoritative");
        TieredCasStore inner = tiered(innerLocal, authoritative, TieredCasStore.TierPolicy.unbounded());
        TieredCasStore outer = new TieredCasStore(outerLocal, inner,
                TieredCasStore.TierPolicy.unbounded(), clock::get);
        byte[] content = bytes("visible but not yet durable");
        CasDigest digest = CasDigest.of(content);
        inner.put(digest, content);
        assertTrue(inner.contains(digest));
        assertFalse(authoritative.contains(digest));

        CasBatch.WriteResult result = outer.putAllDurable(List.of(new CasBatch.WriteItem(digest, content)));

        assertTrue(result.complete());
        assertEquals(List.of(digest), result.skippedAlreadyPresent());
        assertTrue(authoritative.contains(digest));
        assertTrue(inner.pendingDurability().isEmpty());
    }

    @Test void failedWriteBackRemainsQueuedAndCanBeRetried() {
        InMemoryCasStore local = new InMemoryCasStore("l1");
        FailOnceDurableStore shared = new FailOnceDurableStore();
        TieredCasStore store = new TieredCasStore(local, shared,
                TieredCasStore.TierPolicy.unbounded(), clock::get);
        byte[] content = bytes("retryable write back");
        CasDigest digest = CasDigest.of(content);

        store.put(digest, content);
        assertThrows(IllegalStateException.class, store::flushWriteBack);
        assertEquals(Set.of(digest), store.pendingDurability());
        assertTrue(local.contains(digest));
        assertFalse(shared.contains(digest));

        assertEquals(List.of(digest), store.flushWriteBack());
        assertTrue(shared.contains(digest));
        assertTrue(store.pendingDurability().isEmpty());
        assertEquals(2, shared.durableAttempts());
    }

    @Test void capacityPressureEvictsLeastRecentlyUsedAndRecordsTheReason() {
        InMemoryCasStore local = new InMemoryCasStore("l1");
        InMemoryCasStore shared = new InMemoryCasStore("l2");
        TieredCasStore store = tiered(local, shared, new TieredCasStore.TierPolicy(20, 1_000));

        CasDigest first = CasDigest.of(bytes("aaaaaaaa"));
        CasDigest second = CasDigest.of(bytes("bbbbbbbb"));
        CasDigest third = CasDigest.of(bytes("cccccccc"));
        store.putDurable(first, bytes("aaaaaaaa"));
        store.putDurable(second, bytes("bbbbbbbb"));
        clock.addAndGet(10);
        store.get(first);
        store.putDurable(third, bytes("cccccccc"));

        assertFalse(local.contains(second));
        assertTrue(local.contains(first));
        assertTrue(local.contains(third));
        List<TieredCasStore.Eviction> evictions = store.evictions();
        assertEquals(1, evictions.size());
        assertEquals(second, evictions.get(0).digest());
        assertEquals(TieredCasStore.EvictionReason.CAPACITY_PRESSURE, evictions.get(0).reason());
    }

    @Test void objectsStillOwedToSharedStorageAreNeverEvicted() {
        InMemoryCasStore local = new InMemoryCasStore("l1");
        InMemoryCasStore shared = new InMemoryCasStore("l2");
        TieredCasStore store = tiered(local, shared, new TieredCasStore.TierPolicy(8, 1_000));

        CasDigest first = CasDigest.of(bytes("aaaaaaaa"));
        CasDigest second = CasDigest.of(bytes("bbbbbbbb"));
        store.put(first, bytes("aaaaaaaa"));
        store.put(second, bytes("bbbbbbbb"));

        assertTrue(local.contains(first));
        assertTrue(local.contains(second));
        assertTrue(store.evictions().isEmpty());

        store.flushWriteBack();
        store.put(CasDigest.of(bytes("dddddddd")), bytes("dddddddd"));
        assertFalse(store.evictions().isEmpty());
    }

    @Test void oversizedObjectsSkipTheLocalTierWithAnExplicitReason() {
        InMemoryCasStore local = new InMemoryCasStore("l1");
        InMemoryCasStore shared = new InMemoryCasStore("l2");
        TieredCasStore store = tiered(local, shared, new TieredCasStore.TierPolicy(1_000, 4));
        byte[] content = bytes("far too large for l1");
        CasDigest digest = CasDigest.of(content);

        store.put(digest, content);
        assertFalse(local.contains(digest));
        assertTrue(shared.contains(digest));
        assertEquals(TieredCasStore.EvictionReason.OVERSIZED_FOR_LOCAL_TIER, store.evictions().get(0).reason());
        assertArrayEquals(content, store.get(digest));
    }

    @Test void aPoisonedLocalCopyFallsBackToSharedStorage() {
        InMemoryCasStore local = new InMemoryCasStore("l1");
        InMemoryCasStore shared = new InMemoryCasStore("l2");
        TieredCasStore store = tiered(local, shared, TieredCasStore.TierPolicy.unbounded());
        byte[] content = bytes("recoverable");
        CasDigest digest = CasDigest.of(content);
        store.putDurable(digest, content);

        local.corruptForFaultInjection(digest, bytes("tampered!!!"));
        assertArrayEquals(content, store.get(digest));
    }

    @Test void aPoisonedObjectWithNoDurableCopyIsReportedNotHidden() {
        InMemoryCasStore local = new InMemoryCasStore("l1");
        InMemoryCasStore shared = new InMemoryCasStore("l2");
        TieredCasStore store = tiered(local, shared, TieredCasStore.TierPolicy.unbounded());
        byte[] content = bytes("only local");
        CasDigest digest = CasDigest.of(content);
        store.put(digest, content);

        local.corruptForFaultInjection(digest, bytes("tampered!!"));
        assertThrows(CasExceptions.CasCorruptionException.class, () -> store.get(digest));
    }

    @Test void concurrentReadWriteTouchReclaimAndEvictKeepLocalStateConsistent() throws Exception {
        InMemoryCasStore local = new InMemoryCasStore("l1");
        InMemoryCasStore shared = new InMemoryCasStore("l2");
        TieredCasStore store = tiered(local, shared, new TieredCasStore.TierPolicy(96, 1_000));
        List<byte[]> contents = new ArrayList<>();
        List<CasDigest> digests = new ArrayList<>();
        for (int index = 0; index < 32; index++) {
            byte[] content = bytes("concurrent-payload-" + index);
            contents.add(content);
            digests.add(CasDigest.of(content));
            store.putDurable(digests.get(index), content);
        }

        ExecutorService executor = Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();
        try {
            for (int worker = 0; worker < 8; worker++) {
                int workerIndex = worker;
                futures.add(executor.submit(() -> {
                    start.await();
                    for (int iteration = 0; iteration < 200; iteration++) {
                        int index = Math.floorMod(workerIndex * 37 + iteration, digests.size());
                        CasDigest digest = digests.get(index);
                        switch ((workerIndex + iteration) % 4) {
                            case 0 -> assertArrayEquals(contents.get(index), store.get(digest));
                            case 1 -> store.putDurable(digest, contents.get(index));
                            case 2 -> {
                                store.evict(digest, TieredCasStore.EvictionReason.MANUAL);
                                assertArrayEquals(contents.get(index), store.get(digest));
                            }
                            default -> {
                                store.localBytes();
                                store.localAccessOrder();
                                store.evictions();
                            }
                        }
                    }
                    return null;
                }));
            }
            start.countDown();
            for (Future<?> future : futures) {
                future.get(20, TimeUnit.SECONDS);
            }
        } finally {
            executor.shutdownNow();
            assertTrue(executor.awaitTermination(5, TimeUnit.SECONDS));
        }

        assertTrue(store.pendingDurability().isEmpty());
        assertTrue(digests.stream().allMatch(shared::contains));
        assertEquals(local.inventory(), store.localAccessOrder().keySet());
        assertEquals(local.inventory().stream().mapToLong(CasDigest::sizeBytes).sum(), store.localBytes());
        assertFalse(store.evictions().isEmpty());
    }

    private static final class FailOnceDurableStore implements CasStore {
        private final InMemoryCasStore delegate = new InMemoryCasStore("fail-once-shared");
        private final AtomicInteger durableAttempts = new AtomicInteger();

        @Override public String name() {
            return delegate.name();
        }

        @Override public boolean contains(CasDigest digest) {
            return delegate.contains(digest);
        }

        @Override public Set<CasDigest> missing(Collection<CasDigest> digests) {
            return delegate.missing(digests);
        }

        @Override public void put(CasDigest expected, byte[] content) {
            delegate.put(expected, content);
        }

        @Override public void putDurable(CasDigest expected, byte[] content) {
            if (durableAttempts.incrementAndGet() == 1) {
                throw new IllegalStateException("injected durable write failure");
            }
            delegate.putDurable(expected, content);
        }

        @Override public byte[] get(CasDigest digest) {
            return delegate.get(digest);
        }

        @Override public byte[] readRange(CasDigest digest, long offset, int length) {
            return delegate.readRange(digest, offset, length);
        }

        @Override public boolean delete(CasDigest digest) {
            return delegate.delete(digest);
        }

        @Override public Set<CasDigest> inventory() {
            return delegate.inventory();
        }

        @Override public long totalBytes() {
            return delegate.totalBytes();
        }

        int durableAttempts() {
            return durableAttempts.get();
        }
    }
}
