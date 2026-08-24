package io.elmos.cas;

import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Heap-backed store. Used as the L2 stand-in in tests and as the shared tier in single-process
 * deployments.
 *
 * <p>This is <em>not</em> the S3/MinIO adapter that ELMOS-CAS-014 asks for. It implements the
 * same port so the tiering logic above it is exercised for real, and it is honest about what it
 * is: an object store adapter with a real endpoint, credentials, multipart semantics and
 * regional policy remains unimplemented in this module.
 */
public final class InMemoryCasStore implements CasStore {

    private final String name;
    private final Map<CasDigest, byte[]> objects = new ConcurrentHashMap<>();
    private final Map<String, byte[]> quarantine = new ConcurrentHashMap<>();

    public InMemoryCasStore(String name) {
        this.name = CasText.required(name, "name");
    }

    @Override
    public String name() {
        return name;
    }

    @Override
    public boolean contains(CasDigest digest) {
        return objects.containsKey(digest);
    }

    @Override
    public void put(CasDigest expected, byte[] content) {
        CasDigest actual = CasDigest.of(content);
        if (!actual.equals(expected)) {
            throw new CasExceptions.CasCorruptionException(name, expected, actual);
        }
        objects.putIfAbsent(expected, content.clone());
    }

    @Override
    public byte[] get(CasDigest digest) {
        byte[] content = objects.get(digest);
        if (content == null) {
            throw new CasExceptions.CasNotFoundException(digest);
        }
        CasDigest actual = CasDigest.of(content);
        if (!actual.equals(digest)) {
            quarantine.put(digest.hex(), content);
            objects.remove(digest);
            throw new CasExceptions.CasCorruptionException(name, digest, actual);
        }
        return content.clone();
    }

    @Override
    public byte[] readRange(CasDigest digest, long offset, int length) {
        byte[] content = get(digest);
        if (offset < 0 || offset > content.length) {
            throw new IllegalArgumentException("range offset outside object: " + offset);
        }
        int end = (int) Math.min(content.length, offset + length);
        return Arrays.copyOfRange(content, (int) offset, end);
    }

    @Override
    public boolean delete(CasDigest digest) {
        return objects.remove(digest) != null;
    }

    @Override
    public Set<CasDigest> inventory() {
        return Collections.unmodifiableSet(new LinkedHashSet<>(objects.keySet()));
    }

    @Override
    public long totalBytes() {
        return objects.values().stream().mapToLong(value -> value.length).sum();
    }

    public Map<String, byte[]> quarantined() {
        return Collections.unmodifiableMap(new LinkedHashMap<>(quarantine));
    }

    /**
     * Fault injection for ELMOS-CAS-032. Replaces the bytes under a digest without updating the
     * key, which is exactly what a poisoned node or a silent disk fault looks like from above.
     */
    public void corruptForFaultInjection(CasDigest digest, byte[] replacement) {
        if (!objects.containsKey(digest)) {
            throw new CasExceptions.CasNotFoundException(digest);
        }
        objects.put(digest, replacement.clone());
    }
}
