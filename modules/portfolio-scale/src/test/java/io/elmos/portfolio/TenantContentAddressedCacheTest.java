package io.elmos.portfolio;

import io.elmos.cas.CasDigest;
import io.elmos.cas.InMemoryCasStore;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Covers the behaviour the delegation to {@code modules/cas} added, on top of what
 * {@code PortfolioScaleTest} already asserts about this class.
 */
class TenantContentAddressedCacheTest {

    private static byte[] bytes(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    private static TenantContentAddressedCache.InputManifest manifest(String source) {
        return new TenantContentAddressedCache.InputManifest(source, "deps", "toolchain", "profile",
                "policy", "env", "generator");
    }

    @Test void storeAndFetchRoundTripThroughTheContentAddressedStore() {
        InMemoryCasStore store = new InMemoryCasStore("shared");
        var cache = new TenantContentAddressedCache(store);
        byte[] artifact = bytes("built artifact");

        var ref = cache.put("tenant-a", "trust-a", manifest("source"), artifact,
                TenantContentAddressedCache.digest(artifact), true);

        assertEquals("tenant-a", ref.tenantId());
        assertEquals(artifact.length, ref.sizeBytes());
        assertTrue(store.contains(CasDigest.of(artifact)), "bytes must land in the real store");
        assertArrayEquals(artifact, cache.get("tenant-a", "trust-a", ref).orElseThrow());
    }

    @Test void aDifferentInputSetProducesADifferentCacheKey() {
        var cache = new TenantContentAddressedCache();
        byte[] artifact = bytes("artifact");
        var first = cache.put("tenant-a", "trust-a", manifest("source-1"), artifact,
                TenantContentAddressedCache.digest(artifact), true);
        var second = cache.put("tenant-a", "trust-a", manifest("source-2"), artifact,
                TenantContentAddressedCache.digest(artifact), true);
        assertNotEquals(first.cacheKey(), second.cacheKey());
    }

    @Test void separatorInjectionCannotCollapseTwoInputSetsOntoOneKey() {
        var cache = new TenantContentAddressedCache();
        byte[] artifact = bytes("artifact");
        // The old implementation joined fields with NUL, so these two manifests produced the
        // same key and the second build silently reused the first one's output.
        var injected = new TenantContentAddressedCache.InputManifest("a\0b", "deps", "toolchain",
                "profile", "policy", "env", "generator");
        var split = new TenantContentAddressedCache.InputManifest("a", "b\0deps", "toolchain",
                "profile", "policy", "env", "generator");

        var first = cache.put("tenant-a", "trust-a", injected, artifact,
                TenantContentAddressedCache.digest(artifact), true);
        var second = cache.put("tenant-a", "trust-a", split, artifact,
                TenantContentAddressedCache.digest(artifact), true);
        assertNotEquals(first.cacheKey(), second.cacheKey());
    }

    @Test void anotherTenantCannotFetchWithAStolenReference() {
        var cache = new TenantContentAddressedCache();
        byte[] artifact = bytes("private artifact");
        var ref = cache.put("tenant-a", "trust-a", manifest("source"), artifact,
                TenantContentAddressedCache.digest(artifact), true);

        assertEquals(Optional.empty(), cache.get("tenant-b", "trust-a", ref));
        assertEquals(Optional.empty(), cache.get("tenant-a", "trust-b", ref));
    }

    @Test void anUnverifiedSignatureAndAMismatchedDigestAreBothRefused() {
        var cache = new TenantContentAddressedCache();
        byte[] artifact = bytes("artifact");
        assertThrows(IllegalArgumentException.class, () -> cache.put("tenant-a", "trust-a",
                manifest("source"), artifact, TenantContentAddressedCache.digest(artifact), false));
        assertThrows(IllegalArgumentException.class, () -> cache.put("tenant-a", "trust-a",
                manifest("source"), artifact, TenantContentAddressedCache.digest(bytes("other")), true));
    }

    @Test void aPoisonedEntryIsDetectedByTheStoreRatherThanServed() {
        InMemoryCasStore store = new InMemoryCasStore("shared");
        var cache = new TenantContentAddressedCache(store);
        byte[] artifact = bytes("trusted artifact");
        var ref = cache.put("tenant-a", "trust-a", manifest("source"), artifact,
                TenantContentAddressedCache.digest(artifact), true);

        store.corruptForFaultInjection(CasDigest.of(artifact), bytes("tampered artifact"));
        var error = assertThrows(IllegalStateException.class, () -> cache.get("tenant-a", "trust-a", ref));
        assertTrue(error.getMessage().contains("corruption"));
    }

    @Test void anEntryWhoseObjectWasCollectedReportsAMissRatherThanFailing() {
        InMemoryCasStore store = new InMemoryCasStore("shared");
        var cache = new TenantContentAddressedCache(store);
        byte[] artifact = bytes("collectable artifact");
        var ref = cache.put("tenant-a", "trust-a", manifest("source"), artifact,
                TenantContentAddressedCache.digest(artifact), true);

        store.delete(CasDigest.of(artifact));
        assertEquals(Optional.empty(), cache.get("tenant-a", "trust-a", ref));
    }
}
