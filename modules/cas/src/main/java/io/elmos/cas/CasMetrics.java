package io.elmos.cas;

import java.util.Collections;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * ELMOS-CAS-039 through ELMOS-CAS-042.
 *
 * <p>Two kinds of number, and conflating them is the usual mistake. The <em>outcome</em> counters
 * answer "is the cache working"; the <em>savings</em> counters answer "is it worth what it costs".
 * A cache can have a 90 percent hit rate on work that took 40 milliseconds and save nothing.
 *
 * <p>Miss reasons are counted per reason string rather than aggregated, because the actionable
 * question is never "how many misses" but "which input keeps moving".
 */
public final class CasMetrics {

    /** The layers the platform caches at. Each is measured separately (ELMOS-CAS-039). */
    public enum Layer {
        SOURCE,
        PARSE,
        SEMANTIC,
        IR,
        DEPENDENCY,
        TOOLCHAIN,
        BUILD,
        TEST,
        MODEL_PREFIX,
        MODEL_RESPONSE,
        ACTION
    }

    private final Map<Layer, Map<ActionCache.CacheOutcome, AtomicLong>> outcomes = new EnumMap<>(Layer.class);
    private final Map<String, AtomicLong> reasons = new LinkedHashMap<>();
    private final AtomicLong bytesAvoided = new AtomicLong();
    private final AtomicLong modelTokensAvoided = new AtomicLong();
    private final AtomicLong computeMillisAvoided = new AtomicLong();
    private final AtomicLong wallMillisAvoided = new AtomicLong();

    public synchronized void record(Layer layer, ActionCache.CacheOutcome outcome, String reason) {
        outcomes.computeIfAbsent(layer, key -> new EnumMap<>(ActionCache.CacheOutcome.class))
                .computeIfAbsent(outcome, key -> new AtomicLong())
                .incrementAndGet();
        reasons.computeIfAbsent(layer.name() + "/" + outcome.name() + "/" + reason, key -> new AtomicLong())
                .incrementAndGet();
    }

    /** ELMOS-CAS-040. What the hit did not cost, taken from the recorded result rather than guessed. */
    public void recordSavings(double wallSeconds, long bytes, double cpuSeconds) {
        wallMillisAvoided.addAndGet(Math.round(wallSeconds * 1000));
        computeMillisAvoided.addAndGet(Math.round(cpuSeconds * 1000));
        bytesAvoided.addAndGet(bytes);
    }

    public void recordModelTokensAvoided(long tokens) {
        modelTokensAvoided.addAndGet(tokens);
    }

    public synchronized long count(Layer layer, ActionCache.CacheOutcome outcome) {
        return outcomes.getOrDefault(layer, Map.of())
                .getOrDefault(outcome, new AtomicLong())
                .get();
    }

    /**
     * ELMOS-CAS-041. Hits over the lookups that could have hit. Bypasses are excluded on purpose:
     * a caller that asked to skip the cache is not a cache failure, and counting it as one hides
     * the metric the benchmark is actually gated on.
     */
    public synchronized double exactHitRate(Layer layer) {
        long hits = count(layer, ActionCache.CacheOutcome.HIT);
        long considered = hits
                + count(layer, ActionCache.CacheOutcome.MISS)
                + count(layer, ActionCache.CacheOutcome.STALE)
                + count(layer, ActionCache.CacheOutcome.INVALIDATED);
        return considered == 0 ? 0d : (double) hits / considered;
    }

    /** ELMOS-CAS-042. Reason counters, highest first, so an unexpected miss has a named cause. */
    public synchronized Map<String, Long> explain() {
        Map<String, Long> explained = new LinkedHashMap<>();
        reasons.entrySet().stream()
                .sorted((left, right) -> Long.compare(right.getValue().get(), left.getValue().get()))
                .forEach(entry -> explained.put(entry.getKey(), entry.getValue().get()));
        return Collections.unmodifiableMap(explained);
    }

    public long bytesAvoided() {
        return bytesAvoided.get();
    }

    public long computeMillisAvoided() {
        return computeMillisAvoided.get();
    }

    public long wallMillisAvoided() {
        return wallMillisAvoided.get();
    }

    public long modelTokensAvoided() {
        return modelTokensAvoided.get();
    }
}
