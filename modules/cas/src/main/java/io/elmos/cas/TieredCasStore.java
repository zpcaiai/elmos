package io.elmos.cas;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.LongSupplier;

/**
 * ELMOS-CAS-015/016/017. Two tiers behind one port: a fast local L1 and a shared durable L2.
 *
 * <p>Read-through is the easy half. The half that decides whether the platform loses work is the
 * write path, and it has exactly two modes:
 *
 * <ul>
 *   <li>{@link #put} is best effort: the object lands in L1 immediately and is queued for L2.
 *       Correct for intermediates that can be recomputed.</li>
 *   <li>{@link #putDurable} does not return until L2 has the object. Anything an action result,
 *       an evidence pack or a release points at must go through this, because a runner can be
 *       reclaimed the instant after it reports success.</li>
 * </ul>
 *
 * <p>Eviction never removes an object that is still only in L1. A cache that can evict
 * not-yet-durable content is not a cache, it is a data-loss window with a hit rate.
 */
public final class TieredCasStore implements CasStore {

    public enum EvictionReason {
        CAPACITY_PRESSURE,
        OVERSIZED_FOR_LOCAL_TIER,
        MANUAL,
        TENANT_DELETED
    }

    public record Eviction(CasDigest digest, EvictionReason reason, long sizeBytes, long atEpochMillis) {
    }

    /**
     * @param localCapacityBytes  soft ceiling for L1; exceeded transiently while a single object
     *                            is admitted, then reclaimed
     * @param maxLocalObjectBytes objects above this never enter L1 at all, so one giant artifact
     *                            cannot flush an entire warm working set
     */
    public record TierPolicy(long localCapacityBytes, long maxLocalObjectBytes) {
        public TierPolicy {
            CasText.requirePositive(localCapacityBytes, "localCapacityBytes");
            CasText.requirePositive(maxLocalObjectBytes, "maxLocalObjectBytes");
        }

        public static TierPolicy unbounded() {
            return new TierPolicy(Long.MAX_VALUE, Long.MAX_VALUE);
        }
    }

    private final CasStore local;
    private final CasStore shared;
    private final TierPolicy policy;
    private final LongSupplier clock;
    private volatile CasTelemetry telemetry = CasTelemetry.noop();

    /**
     * Protects the local tier and every piece of metadata describing it. Keeping the object and
     * its access/durability records behind one lock prevents reclamation from observing a
     * half-admitted object or a read from racing an eviction between {@code contains} and
     * {@code get}.
     */
    private final Object stateLock = new Object();

    /**
     * Serializes operations that change the authoritative tier. Remote I/O is deliberately not
     * performed while {@link #stateLock} is held; the lock order, whenever both are needed, is
     * durabilityLock then stateLock.
     */
    private final Object durabilityLock = new Object();

    /** Access-ordered, so the head is the least recently used object. */
    private final LinkedHashMap<CasDigest, Long> localAccess = new LinkedHashMap<>(16, 0.75f, true);
    private final Deque<CasDigest> writeBackQueue = new ArrayDeque<>();
    private final Set<CasDigest> pendingDurability = new LinkedHashSet<>();
    private final List<Eviction> evictions = new ArrayList<>();

    public TieredCasStore(CasStore local, CasStore shared, TierPolicy policy, LongSupplier clock) {
        this.local = local;
        this.shared = shared;
        this.policy = policy;
        this.clock = clock;
    }

    /** ELMOS-CAS-039. Opt-in instrumentation; the default is a no-op so tests stay quiet. */
    public TieredCasStore withTelemetry(CasTelemetry telemetry) {
        this.telemetry = java.util.Objects.requireNonNull(telemetry, "telemetry");
        return this;
    }

    @Override
    public String name() {
        return local.name() + "+" + shared.name();
    }

    @Override
    public boolean contains(CasDigest digest) {
        synchronized (stateLock) {
            if (local.contains(digest)) {
                return true;
            }
        }
        return shared.contains(digest);
    }

    @Override
    public Set<CasDigest> missing(Collection<CasDigest> digests) {
        Set<CasDigest> absent = new LinkedHashSet<>();
        for (CasDigest digest : digests) {
            if (!contains(digest)) {
                absent.add(digest);
            }
        }
        return absent;
    }

    @Override
    public void put(CasDigest expected, byte[] content) {
        telemetry.histogram("cas.transfer.bytes", "By", content.length,
                java.util.Map.of("direction", "upload"));

        // An object that cannot enter L1 has nowhere from which a later write-back could read it.
        // Its best-effort write therefore becomes synchronous and must cross every nested tier.
        if (expected.sizeBytes() > policy.maxLocalObjectBytes()) {
            synchronized (durabilityLock) {
                putSharedDurableAndVerify(expected, content);
                synchronized (stateLock) {
                    clearPendingLocked(expected);
                    recordEvictionLocked(expected, EvictionReason.OVERSIZED_FOR_LOCAL_TIER);
                }
            }
            return;
        }

        synchronized (durabilityLock) {
            synchronized (stateLock) {
                boolean newlyPending = pendingDurability.add(expected);
                if (newlyPending) {
                    // The durability debt is registered before admission. Reclamation therefore
                    // cannot discard the only copy between local.put and queue publication.
                    // Do not replace this with shared.contains(): a nested write-back tier may
                    // expose an object from its own pending L1 without holding it authoritatively.
                    writeBackQueue.addLast(expected);
                }
                try {
                    local.put(expected, content);
                } catch (RuntimeException failure) {
                    if (newlyPending) {
                        clearPendingLocked(expected);
                    }
                    throw failure;
                }
                touchLocked(expected);
                reclaimLocked();
            }
        }
    }

    /**
     * ELMOS-CAS-011 + ELMOS-CAS-016. Batch variant of {@link #putDurable}: one existence probe,
     * per-item failure isolation, and no return until every accepted object is in the shared tier.
     */
    public CasBatch.WriteResult putAllDurable(java.util.Collection<CasBatch.WriteItem> items) {
        List<CasDigest> order = items.stream().map(CasBatch.WriteItem::digest).toList();
        Set<CasDigest> absent = missing(order);
        List<CasDigest> written = new ArrayList<>();
        List<CasDigest> skipped = new ArrayList<>();
        Map<CasDigest, String> failed = new LinkedHashMap<>();
        Set<CasDigest> handled = new LinkedHashSet<>();
        for (CasBatch.WriteItem item : items) {
            if (!handled.add(item.digest())) {
                skipped.add(item.digest());
                continue;
            }
            try {
                // Always cross the durable port, including for an object already visible in a
                // nested tier's L1. Visibility through contains does not prove final durability.
                putDurable(item.digest(), item.content());
                if (absent.contains(item.digest())) {
                    written.add(item.digest());
                } else {
                    skipped.add(item.digest());
                }
            } catch (RuntimeException error) {
                failed.put(item.digest(), error.getClass().getSimpleName() + ": " + error.getMessage());
            }
        }
        return new CasBatch.WriteResult(written, skipped, failed);
    }

    /** ELMOS-CAS-016. Returns only once the shared tier holds the object. */
    @Override
    public void putDurable(CasDigest expected, byte[] content) {
        telemetry.histogram("cas.transfer.bytes", "By", content.length,
                java.util.Map.of("direction", "upload"));
        synchronized (durabilityLock) {
            // putDurable, rather than put, is what makes composition safe when L2 is itself a
            // write-back TieredCasStore.
            putSharedDurableAndVerify(expected, content);
            synchronized (stateLock) {
                clearPendingLocked(expected);
                admitLocallyLocked(expected, content);
            }
        }
    }

    @Override
    public byte[] get(CasDigest digest) {
        try (CasTelemetry.Span span = telemetry.startSpan("cas.store.get", CasTelemetry.SpanKind.CLIENT,
                java.util.Optional.empty())) {
            span.attribute("cas.digest", digest.compact());
            TierRead result = read(digest);
            boolean localHit = result.localHit();
            byte[] content = result.content();
            span.attribute("cas.tier", localHit ? "L1" : "L2");
            span.attribute("cas.object_bytes", content.length);
            span.status(CasTelemetry.SpanStatus.OK, localHit ? "l1-hit" : "read-through");
            telemetry.counter("cas.store.reads", "1", 1,
                    java.util.Map.of("tier", localHit ? "L1" : "L2"));
            telemetry.histogram("cas.transfer.bytes", "By", content.length,
                    java.util.Map.of("direction", "download"));
            return content;
        }
    }

    private TierRead read(CasDigest digest) {
        CasExceptions.CasCorruptionException poisoned = null;
        synchronized (stateLock) {
            if (local.contains(digest)) {
                try {
                    byte[] content = local.get(digest);
                    touchLocked(digest);
                    return new TierRead(content, true);
                } catch (CasExceptions.CasCorruptionException corruption) {
                    dropPoisonedLocalLocked(digest);
                    poisoned = corruption;
                }
            }
        }

        // A second local check closes the miss/admission race, while durabilityLock prevents a
        // concurrent delete from removing L2 after this read but before the read-through admit.
        synchronized (durabilityLock) {
            synchronized (stateLock) {
                if (local.contains(digest)) {
                    try {
                        byte[] content = local.get(digest);
                        touchLocked(digest);
                        return new TierRead(content, true);
                    } catch (CasExceptions.CasCorruptionException corruption) {
                        dropPoisonedLocalLocked(digest);
                        poisoned = corruption;
                    }
                }
            }
            byte[] content;
            try {
                content = shared.get(digest);
            } catch (CasExceptions.CasNotFoundException notFound) {
                if (poisoned != null) {
                    throw poisoned;
                }
                throw notFound;
            }
            admitLocally(digest, content);
            return new TierRead(content, false);
        }
    }

    @Override
    public byte[] readRange(CasDigest digest, long offset, int length) {
        CasExceptions.CasCorruptionException poisoned = null;
        synchronized (stateLock) {
            if (local.contains(digest)) {
                try {
                    byte[] content = local.readRange(digest, offset, length);
                    touchLocked(digest);
                    return content;
                } catch (CasExceptions.CasCorruptionException corruption) {
                    dropPoisonedLocalLocked(digest);
                    poisoned = corruption;
                }
            }
        }
        synchronized (durabilityLock) {
            try {
                return shared.readRange(digest, offset, length);
            } catch (CasExceptions.CasNotFoundException notFound) {
                if (poisoned != null) {
                    throw poisoned;
                }
                throw notFound;
            }
        }
    }

    @Override
    public boolean delete(CasDigest digest) {
        synchronized (durabilityLock) {
            boolean removedShared = shared.delete(digest);
            synchronized (stateLock) {
                boolean removedLocal = local.delete(digest);
                localAccess.remove(digest);
                clearPendingLocked(digest);
                return removedLocal || removedShared;
            }
        }
    }

    @Override
    public Set<CasDigest> inventory() {
        Set<CasDigest> all = new LinkedHashSet<>(shared.inventory());
        synchronized (stateLock) {
            all.addAll(local.inventory());
        }
        return Collections.unmodifiableSet(all);
    }

    @Override
    public long totalBytes() {
        return inventory().stream().mapToLong(CasDigest::sizeBytes).sum();
    }

    /**
     * Drains the write-back queue. Deliberately explicit rather than a background thread: the
     * caller that knows a checkpoint is being taken is the caller that must decide when
     * durability is owed, and a hidden thread makes "did this reach L2" untestable.
     *
     * @return digests that reached the shared tier in this drain
     */
    public List<CasDigest> flushWriteBack() {
        synchronized (durabilityLock) {
            List<CasDigest> flushed = new ArrayList<>();
            while (true) {
                CasDigest digest;
                byte[] content;
                synchronized (stateLock) {
                    digest = writeBackQueue.peekFirst();
                    if (digest == null) {
                        return List.copyOf(flushed);
                    }
                    if (!pendingDurability.contains(digest)) {
                        writeBackQueue.removeFirst();
                        continue;
                    }
                    if (!local.contains(digest)) {
                        // Do not dequeue an unfulfilled durability debt. A retry after the local
                        // object is restored must see the same queue entry.
                        throw new CasExceptions.CasNotFoundException(digest);
                    }
                    try {
                        content = local.get(digest);
                    } catch (CasExceptions.CasCorruptionException corruption) {
                        dropPoisonedLocalLocked(digest);
                        throw corruption;
                    }
                }

                // The head remains queued until this returns successfully. Calling putDurable is
                // required even when shared.contains is true: a nested write-back tier may only
                // hold the object in its own L1.
                putSharedDurableAndVerify(digest, content);

                synchronized (stateLock) {
                    pendingDurability.remove(digest);
                    writeBackQueue.removeFirstOccurrence(digest);
                    flushed.add(digest);
                }
            }
        }
    }

    public Set<CasDigest> pendingDurability() {
        synchronized (stateLock) {
            return Set.copyOf(pendingDurability);
        }
    }

    public List<Eviction> evictions() {
        synchronized (stateLock) {
            return List.copyOf(evictions);
        }
    }

    public long localBytes() {
        synchronized (stateLock) {
            return localBytesLocked();
        }
    }

    public void evict(CasDigest digest, EvictionReason reason) {
        synchronized (stateLock) {
            // Explicit local eviction is still not allowed to discard the sole, pending copy.
            if (pendingDurability.contains(digest)) {
                return;
            }
            if (local.delete(digest)) {
                localAccess.remove(digest);
                recordEvictionLocked(digest, reason);
            }
        }
    }

    private void admitLocally(CasDigest digest, byte[] content) {
        telemetry.histogram("cas.transfer.bytes", "By", content.length,
                java.util.Map.of("direction", "upload"));
        synchronized (stateLock) {
            admitLocallyLocked(digest, content);
        }
    }

    /**
     * Crosses every composed durability boundary and verifies the bytes through the shared read
     * port before a pending debt may be cleared. A cheap existence probe cannot distinguish an
     * authoritative object from a nested L1 hit and cannot detect a poisoned object under the
     * expected key.
     */
    private void putSharedDurableAndVerify(CasDigest expected, byte[] content) {
        shared.putDurable(expected, content);
        byte[] persisted = shared.get(expected);
        CasDigest observed = CasDigest.of(persisted);
        if (!observed.equals(expected)) {
            throw new CasExceptions.CasCorruptionException(shared.name(), expected, observed);
        }
    }

    private void admitLocallyLocked(CasDigest digest, byte[] content) {
        if (digest.sizeBytes() > policy.maxLocalObjectBytes()) {
            recordEvictionLocked(digest, EvictionReason.OVERSIZED_FOR_LOCAL_TIER);
            return;
        }
        local.put(digest, content);
        touchLocked(digest);
        reclaimLocked();
    }

    private void touchLocked(CasDigest digest) {
        localAccess.put(digest, clock.getAsLong());
    }

    private void reclaimLocked() {
        while (localBytesLocked() > policy.localCapacityBytes()) {
            CasDigest victim = null;
            for (CasDigest candidate : localAccess.keySet()) {
                if (!pendingDurability.contains(candidate)) {
                    victim = candidate;
                    break;
                }
            }
            if (victim == null) {
                // Everything resident is still owed to L2. Holding above the soft ceiling is the
                // correct trade: over-capacity is recoverable, losing the only copy is not.
                return;
            }
            local.delete(victim);
            localAccess.remove(victim);
            recordEvictionLocked(victim, EvictionReason.CAPACITY_PRESSURE);
        }
    }

    public Map<CasDigest, Long> localAccessOrder() {
        synchronized (stateLock) {
            return Collections.unmodifiableMap(new LinkedHashMap<>(localAccess));
        }
    }

    private long localBytesLocked() {
        return localAccess.keySet().stream().mapToLong(CasDigest::sizeBytes).sum();
    }

    private void clearPendingLocked(CasDigest digest) {
        pendingDurability.remove(digest);
        writeBackQueue.removeFirstOccurrence(digest);
    }

    private void dropPoisonedLocalLocked(CasDigest digest) {
        local.delete(digest);
        localAccess.remove(digest);
    }

    private void recordEvictionLocked(CasDigest digest, EvictionReason reason) {
        evictions.add(new Eviction(digest, reason, digest.sizeBytes(), clock.getAsLong()));
    }

    private record TierRead(byte[] content, boolean localHit) {
    }
}
