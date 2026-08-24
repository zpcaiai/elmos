package io.elmos.cas;

import java.util.Map;
import java.util.Optional;

/**
 * Durable source of truth for {@link ActionCache} entries.
 *
 * <p>Every operation is tenant scoped. Implementations backed by a database must bind that
 * tenant to the same transaction that performs the query; accepting a caller-supplied digest
 * without the tenant would turn an action-cache hit into a cross-tenant object oracle.
 */
public interface ActionCacheIndex {

    /**
     * Exact semantic replay check. Wall-clock storage instants may differ across retrying
     * processes, but no signed/result/producer/writer field may drift and a failure retry must
     * preserve the original TTL duration rather than silently extending policy.
     */
    static boolean isIdempotentReplay(ActionCache.Entry current, ActionCache.Entry replay) {
        return current.key().equals(replay.key())
                && current.result().equals(replay.result())
                && current.producer().equals(replay.producer())
                && current.writer().equals(replay.writer())
                && current.attestation().equals(replay.attestation())
                && current.riskTier() == replay.riskTier()
                && ttlMillis(current).equals(ttlMillis(replay));
    }

    private static Optional<Long> ttlMillis(ActionCache.Entry entry) {
        return entry.expiresAtEpochMillis()
                .map(expiry -> expiry - entry.storedAtEpochMillis());
    }

    Optional<ActionCache.Entry> find(ActionKey key);

    /**
     * Stores an entry or confirms an idempotent replay.
     *
     * @throws CasExceptions.CasAccessDeniedException if an active entry with the same action key
     *                                                resolves to a different output
     */
    void store(ActionCache.Entry entry);

    boolean invalidate(ActionKey key, String reason, long atEpochMillis);

    int invalidateByWriter(String tenantId, String nodeId, String reason, long atEpochMillis);

    void quarantineNode(String tenantId, String nodeId, String reason, long atEpochMillis);

    boolean isNodeQuarantined(String tenantId, String nodeId);

    Map<CasDigest, CasDigest> liveOutputManifests(String tenantId);

    int size(String tenantId);
}
