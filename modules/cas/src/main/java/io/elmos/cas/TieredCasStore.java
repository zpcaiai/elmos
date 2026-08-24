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
    private CasTelemetry telemetry = CasTelemetry.noop();

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
        return local.contains(digest) || shared.contains(digest);
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
        // The durability debt is registered before the object is admitted, not after. Registering
        // it afterwards leaves a window in which reclamation sees a brand new object as evictable
        // and throws away the only copy that exists.
        if (!shared.contains(expected)) {
            synchronized (writeBackQueue) {
                if (pendingDurability.add(expected)) {
                    writeBackQueue.addLast(expected);
                }
            }
        }
        admitLocally(expected, content);
    }

    /**
     * ELMOS-CAS-011 + ELMOS-CAS-016. Batch variant of {@link #putDurable}: one existence probe,
     * per-item failure isolation, and no return until every accepted object is in the shared tier.
     */
    public CasBatch.WriteResult putAllDurable(java.util.Collection<CasBatch.WriteItem> items) {
        CasBatch.WriteResult result = putAll(items);
        flushWriteBack();
        return result;
    }

    /** ELMOS-CAS-016. Returns only once the shared tier holds the object. */
    public void putDurable(CasDigest expected, byte[] content) {
        shared.put(expected, content);
        synchronized (writeBackQueue) {
            pendingDurability.remove(expected);
            writeBackQueue.remove(expected);
        }
        admitLocally(expected, content);
    }

    @Override
    public byte[] get(CasDigest digest) {
        try (CasTelemetry.Span span = telemetry.startSpan("cas.store.get", CasTelemetry.SpanKind.CLIENT,
                java.util.Optional.empty())) {
            span.attribute("cas.digest", digest.compact());
            boolean localHit = local.contains(digest);
            span.attribute("cas.tier", localHit ? "L1" : "L2");
            byte[] content = read(digest);
            span.attribute("cas.object_bytes", content.length);
            span.status(CasTelemetry.SpanStatus.OK, localHit ? "l1-hit" : "read-through");
            telemetry.counter("cas.store.reads", "1", 1,
                    java.util.Map.of("tier", localHit ? "L1" : "L2"));
            telemetry.histogram("cas.transfer.bytes", "By", content.length,
                    java.util.Map.of("direction", "download"));
            return content;
        }
    }

    private byte[] read(CasDigest digest) {
        if (local.contains(digest)) {
            try {
                byte[] content = local.get(digest);
                touch(digest);
                return content;
            } catch (CasExceptions.CasCorruptionException poisoned) {
                // L1 is disposable. Drop the poisoned copy and fall through to the durable tier
                // rather than failing a build over a local disk fault.
                local.delete(digest);
                localAccess.remove(digest);
                if (!shared.contains(digest)) {
                    throw poisoned;
                }
            }
        }
        byte[] content = shared.get(digest);
        admitLocally(digest, content);
        return content;
    }

    @Override
    public byte[] readRange(CasDigest digest, long offset, int length) {
        if (local.contains(digest)) {
            touch(digest);
            return local.readRange(digest, offset, length);
        }
        return shared.readRange(digest, offset, length);
    }

    @Override
    public boolean delete(CasDigest digest) {
        boolean removedLocal = local.delete(digest);
        localAccess.remove(digest);
        boolean removedShared = shared.delete(digest);
        return removedLocal || removedShared;
    }

    @Override
    public Set<CasDigest> inventory() {
        Set<CasDigest> all = new LinkedHashSet<>(shared.inventory());
        all.addAll(local.inventory());
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
        List<CasDigest> flushed = new ArrayList<>();
        while (true) {
            CasDigest digest;
            synchronized (writeBackQueue) {
                digest = writeBackQueue.pollFirst();
            }
            if (digest == null) {
                return List.copyOf(flushed);
            }
            if (!shared.contains(digest) && local.contains(digest)) {
                shared.put(digest, local.get(digest));
            }
            synchronized (writeBackQueue) {
                pendingDurability.remove(digest);
            }
            flushed.add(digest);
        }
    }

    public Set<CasDigest> pendingDurability() {
        synchronized (writeBackQueue) {
            return Set.copyOf(pendingDurability);
        }
    }

    public List<Eviction> evictions() {
        return List.copyOf(evictions);
    }

    public long localBytes() {
        return localAccess.keySet().stream().mapToLong(CasDigest::sizeBytes).sum();
    }

    public void evict(CasDigest digest, EvictionReason reason) {
        if (local.delete(digest)) {
            localAccess.remove(digest);
            evictions.add(new Eviction(digest, reason, digest.sizeBytes(), clock.getAsLong()));
        }
    }

    private void admitLocally(CasDigest digest, byte[] content) {
        telemetry.histogram("cas.transfer.bytes", "By", content.length,
                java.util.Map.of("direction", "upload"));
        if (digest.sizeBytes() > policy.maxLocalObjectBytes()) {
            evictions.add(new Eviction(digest, EvictionReason.OVERSIZED_FOR_LOCAL_TIER,
                    digest.sizeBytes(), clock.getAsLong()));
            if (!shared.contains(digest)) {
                shared.put(digest, content);
            }
            return;
        }
        local.put(digest, content);
        touch(digest);
        reclaim();
    }

    private void touch(CasDigest digest) {
        localAccess.put(digest, clock.getAsLong());
    }

    private void reclaim() {
        Set<CasDigest> notDurable = pendingDurability();
        while (localBytes() > policy.localCapacityBytes()) {
            CasDigest victim = null;
            for (CasDigest candidate : localAccess.keySet()) {
                if (!notDurable.contains(candidate)) {
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
            evictions.add(new Eviction(victim, EvictionReason.CAPACITY_PRESSURE, victim.sizeBytes(),
                    clock.getAsLong()));
        }
    }

    public Map<CasDigest, Long> localAccessOrder() {
        return Collections.unmodifiableMap(new LinkedHashMap<>(localAccess));
    }
}
