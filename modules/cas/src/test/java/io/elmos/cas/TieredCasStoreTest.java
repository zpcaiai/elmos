package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.List;
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
}
