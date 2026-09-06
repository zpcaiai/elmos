package io.elmos.cas;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.Map;

/** Repository-owned proof of local synchronous I/O termination; not a caller-supplied boolean. */
final class LocalCasPublication implements CasCatalog.DurableObjectEnsurer {
    private final CasStore store;
    private final Map<CasDigest, CasContent> staged;
    private final java.util.concurrent.atomic.AtomicInteger active = new java.util.concurrent.atomic.AtomicInteger();

    LocalCasPublication(CasStore store, Map<CasDigest, CasContent> staged) {
        if (!(store instanceof LocalDiskCasStore) && !TenantEncryptedLocalCasStore.isLocalScopedStore(store)) {
            throw new IllegalArgumentException("local publication requires an exact repository-owned disk store");
        }
        this.store = store;
        this.staged = Map.copyOf(staged);
    }

    @Override public void ensureDurable() {
        active.incrementAndGet();
        try { persist(store, staged); }
        finally { active.decrementAndGet(); }
    }

    boolean stopped() { return active.get() == 0; }

    static void persist(CasStore store, Map<CasDigest, CasContent> staged) {
        staged.forEach((digest, content) -> {
            try (var input = content.openStream()) {
                store.putDurable(digest, input);
                try (var verified = store.openVerified(digest)) { /* No exposure before verification. */ }
            } catch (IOException error) { throw new UncheckedIOException(error); }
        });
    }
}
