package io.elmos.cas;

import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * The storage port. One interface for every tier so that a tier can be composed, swapped, or
 * fronted by a policy decorator without the callers above it knowing.
 *
 * <p>Implementations must verify on read (ELMOS-CAS-030 sampling is a second line of defence,
 * not the first) and must be safe under concurrent writes of the same digest, which is the
 * normal case rather than the exception: content addressing means two runners producing the
 * same bytes will race to store them, and both must win.
 */
public interface CasStore {

    String name();

    boolean contains(CasDigest digest);

    /**
     * ELMOS-CAS-006. Batch existence query. Returned in the caller's iteration order so that an
     * upload plan is stable across runs.
     */
    default Set<CasDigest> missing(Collection<CasDigest> digests) {
        Set<CasDigest> absent = new LinkedHashSet<>();
        for (CasDigest digest : digests) {
            if (!contains(digest)) {
                absent.add(digest);
            }
        }
        return absent;
    }

    /**
     * ELMOS-CAS-011. Stores a set of objects, skipping those already present, and reporting
     * per-item failures instead of aborting.
     *
     * <p>The existence probe happens once for the whole batch. Implementations backed by a remote
     * tier should override {@link #missing} rather than this method.
     */
    default CasBatch.WriteResult putAll(Collection<CasBatch.WriteItem> items) {
        List<CasDigest> order = items.stream().map(CasBatch.WriteItem::digest).toList();
        Set<CasDigest> absent = missing(order);
        List<CasDigest> written = new ArrayList<>();
        List<CasDigest> skipped = new ArrayList<>();
        Map<CasDigest, String> failed = new LinkedHashMap<>();
        Set<CasDigest> handled = new LinkedHashSet<>();
        for (CasBatch.WriteItem item : items) {
            if (!handled.add(item.digest())) {
                // A duplicate inside one batch is not an error; content addressing makes the
                // second copy identical by definition. Sending it twice is just waste.
                skipped.add(item.digest());
                continue;
            }
            if (!absent.contains(item.digest())) {
                skipped.add(item.digest());
                continue;
            }
            try {
                put(item.digest(), item.content());
                written.add(item.digest());
            } catch (RuntimeException error) {
                failed.put(item.digest(), error.getClass().getSimpleName() + ": " + error.getMessage());
            }
        }
        return new CasBatch.WriteResult(written, skipped, failed);
    }

    /** ELMOS-CAS-011. Reads a set of objects; absent and failed digests are reported, not thrown. */
    default CasBatch.ReadResult getAll(Collection<CasDigest> digests) {
        Map<CasDigest, byte[]> found = new LinkedHashMap<>();
        List<CasDigest> absent = new ArrayList<>();
        Map<CasDigest, String> failed = new LinkedHashMap<>();
        for (CasDigest digest : digests) {
            if (found.containsKey(digest) || absent.contains(digest) || failed.containsKey(digest)) {
                continue;
            }
            try {
                found.put(digest, get(digest));
            } catch (CasExceptions.CasNotFoundException notFound) {
                absent.add(digest);
            } catch (RuntimeException error) {
                failed.put(digest, error.getClass().getSimpleName() + ": " + error.getMessage());
            }
        }
        return new CasBatch.ReadResult(found, absent, failed);
    }

    /**
     * Stores content under its own digest. Idempotent: storing content that is already present
     * is a no-op and must not rewrite the object.
     *
     * @throws CasExceptions.CasCorruptionException if the content does not hash to {@code expected}
     */
    void put(CasDigest expected, byte[] content);

    /**
     * @throws CasExceptions.CasNotFoundException   if absent
     * @throws CasExceptions.CasCorruptionException if present but poisoned
     */
    byte[] get(CasDigest digest);

    /** ELMOS-CAS-008. Range read, so a consumer can stream a large object without buffering it. */
    byte[] readRange(CasDigest digest, long offset, int length);

    boolean delete(CasDigest digest);

    Set<CasDigest> inventory();

    long totalBytes();
}
