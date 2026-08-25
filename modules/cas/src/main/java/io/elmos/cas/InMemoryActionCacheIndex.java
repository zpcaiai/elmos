package io.elmos.cas;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/** Thread-safe reference implementation of {@link ActionCacheIndex}. */
public final class InMemoryActionCacheIndex implements ActionCacheIndex {

    private record EntryKey(String tenantId, CasDigest actionKey) {
    }

    private record NodeKey(String tenantId, String nodeId) {
    }

    private final Map<EntryKey, ActionCache.Entry> entries = new ConcurrentHashMap<>();
    private final Map<NodeKey, String> quarantinedNodes = new ConcurrentHashMap<>();

    @Override
    public Optional<ActionCache.Entry> find(ActionKey key) {
        ActionKeyBuilder.verifyCanonical(key);
        return Optional.ofNullable(entries.get(new EntryKey(key.tenantId(), key.digest())));
    }

    @Override
    public void store(ActionCache.Entry entry) {
        ActionKeyBuilder.verifyCanonical(entry.key());
        EntryKey key = new EntryKey(entry.key().tenantId(), entry.key().digest());
        entries.compute(key, (ignored, current) -> {
            if (current != null && !ActionCacheIndex.isIdempotentReplay(current, entry)) {
                throw new CasExceptions.CasAccessDeniedException(
                        "ACTION_KEY_RESULT_CONFLICT", entry.key().shortForm());
            }
            return current == null ? entry : current;
        });
    }

    @Override
    public boolean invalidate(ActionKey key, String reason, long atEpochMillis) {
        ActionKeyBuilder.verifyCanonical(key);
        return entries.remove(new EntryKey(key.tenantId(), key.digest())) != null;
    }

    @Override
    public int invalidateByWriter(String tenantId, String nodeId, String reason, long atEpochMillis) {
        int removed = 0;
        for (Map.Entry<EntryKey, ActionCache.Entry> candidate : entries.entrySet()) {
            if (candidate.getKey().tenantId().equals(tenantId)
                    && candidate.getValue().writer().nodeId().equals(nodeId)
                    && entries.remove(candidate.getKey(), candidate.getValue())) {
                removed++;
            }
        }
        return removed;
    }

    @Override
    public void quarantineNode(String tenantId, String nodeId, String reason, long atEpochMillis) {
        quarantinedNodes.putIfAbsent(new NodeKey(CasText.required(tenantId, "tenantId"),
                CasText.required(nodeId, "nodeId")), CasText.required(reason, "reason"));
    }

    @Override
    public boolean isNodeQuarantined(String tenantId, String nodeId) {
        return quarantinedNodes.containsKey(new NodeKey(tenantId, nodeId));
    }

    @Override
    public Map<CasDigest, CasDigest> liveOutputManifests(String tenantId) {
        Map<CasDigest, CasDigest> live = new LinkedHashMap<>();
        entries.forEach((key, entry) -> {
            if (key.tenantId().equals(tenantId)) {
                live.put(key.actionKey(), entry.result().outputManifestDigest());
            }
        });
        return Collections.unmodifiableMap(live);
    }

    @Override
    public int size(String tenantId) {
        return (int) entries.keySet().stream().filter(key -> key.tenantId().equals(tenantId)).count();
    }
}
