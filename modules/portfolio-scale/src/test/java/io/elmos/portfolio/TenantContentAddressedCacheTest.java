package io.elmos.portfolio;

import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.CasDigest;
import io.elmos.cas.CasGarbageCollector;
import io.elmos.cas.CasObjectModel;
import io.elmos.cas.InMemoryCasCatalog;
import io.elmos.cas.InMemoryCasStore;
import io.elmos.cas.TieredCasStore;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;

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

    private static TenantContentAddressedCache.ArtifactPolicy policy(String residency) {
        return new TenantContentAddressedCache.ArtifactPolicy(
                residency,
                CasAccessPolicy.SecurityTier.CONFIDENTIAL,
                CasObjectModel.RetentionClass.STANDARD);
    }

    @Test void storeAndFetchRoundTripThroughTheContentAddressedStore() {
        InMemoryCasStore store = new InMemoryCasStore("shared");
        InMemoryCasCatalog catalog = new InMemoryCasCatalog();
        var cache = new TenantContentAddressedCache(store, catalog, policy("cn-north"));
        byte[] artifact = bytes("built artifact");

        var ref = cache.put("tenant-a", "trust-a", manifest("source"), artifact,
                TenantContentAddressedCache.digest(artifact), true);

        assertEquals("tenant-a", ref.tenantId());
        assertEquals(artifact.length, ref.sizeBytes());
        assertTrue(ref.hasKnownGeneration());
        assertTrue(store.contains(CasDigest.of(artifact)), "bytes must land in the real store");
        assertEquals(1, catalog.activeReferenceRoots("tenant-a").stream()
                .filter(root -> root.kind() == CasGarbageCollector.RootKind.ACTION_CACHE)
                .count(), "the durable index must also retain the object as an action-cache root");
        var metadata = catalog.find("tenant-a", CasDigest.of(artifact)).orElseThrow();
        assertEquals(CasObjectModel.ObjectKind.ACTION_RESULT, metadata.kind());
        assertEquals(CasObjectModel.Sensitivity.GENERATED_OUTPUT, metadata.sensitivity());
        assertEquals("cn-north", metadata.dataResidency());
        assertEquals(CasAccessPolicy.SecurityTier.CONFIDENTIAL, metadata.securityTier());
        assertArrayEquals(artifact, cache.get("tenant-a", "trust-a", ref).orElseThrow());
    }

    @Test void anotherCacheInstanceCanResolveTheSharedCatalogMapping() {
        InMemoryCasStore sharedStore = new InMemoryCasStore("shared");
        InMemoryCasCatalog sharedCatalog = new InMemoryCasCatalog();
        var writer = new TenantContentAddressedCache(
                sharedStore, sharedCatalog, policy("cn-north"));
        var reader = new TenantContentAddressedCache(
                sharedStore, sharedCatalog, policy("cn-north"));
        byte[] artifact = bytes("cross-instance artifact");

        for (int index = 0; index < 128; index++) {
            writer.put("tenant-a", "trust-a", manifest("unrelated-" + index), artifact,
                    TenantContentAddressedCache.digest(artifact), true);
        }
        writer.put("tenant-a", "trust-a", manifest("source"), artifact,
                TenantContentAddressedCache.digest(artifact), true);

        var hit = reader.lookup("tenant-a", "trust-a", manifest("source")).orElseThrow();
        assertArrayEquals(artifact, hit.bytes());
        assertTrue(hit.ref().hasKnownGeneration());
        assertEquals(TenantContentAddressedCache.digest(artifact), hit.ref().artifactDigest());
    }

    @Test void aPublishedRootIsDurableAcrossIndependentLocalTiers() {
        InMemoryCasStore shared = new InMemoryCasStore("shared-l2");
        InMemoryCasCatalog catalog = new InMemoryCasCatalog();
        TieredCasStore writerStore = new TieredCasStore(
                new InMemoryCasStore("writer-l1"), shared,
                TieredCasStore.TierPolicy.unbounded(), System::currentTimeMillis);
        TieredCasStore readerStore = new TieredCasStore(
                new InMemoryCasStore("reader-l1"), shared,
                TieredCasStore.TierPolicy.unbounded(), System::currentTimeMillis);
        var writer = new TenantContentAddressedCache(writerStore, catalog, policy("cn-north"));
        var reader = new TenantContentAddressedCache(readerStore, catalog, policy("cn-north"));
        byte[] artifact = bytes("authoritative tier artifact");

        writer.put("tenant-a", "trust-a", manifest("source"), artifact,
                TenantContentAddressedCache.digest(artifact), true);

        assertTrue(shared.contains(CasDigest.of(artifact)),
                "a published root must never point only at the writer's L1");
        assertTrue(writerStore.pendingDurability().isEmpty());
        assertArrayEquals(artifact,
                reader.lookup("tenant-a", "trust-a", manifest("source"))
                        .orElseThrow().bytes());
    }

    @Test void deploymentPolicyDriftCannotTurnACrossInstanceRootIntoAHit() {
        InMemoryCasStore sharedStore = new InMemoryCasStore("shared");
        InMemoryCasCatalog sharedCatalog = new InMemoryCasCatalog();
        var writer = new TenantContentAddressedCache(
                sharedStore, sharedCatalog, policy("cn-north"));
        var driftedReader = new TenantContentAddressedCache(
                sharedStore, sharedCatalog, policy("us-east"));
        byte[] artifact = bytes("regional artifact");

        writer.put("tenant-a", "trust-a", manifest("source"), artifact,
                TenantContentAddressedCache.digest(artifact), true);

        assertThrows(SecurityException.class,
                () -> driftedReader.lookup("tenant-a", "trust-a", manifest("source")));
    }

    @Test void weakerPersistedRetentionCannotSatisfyAStrongerReaderPolicy() {
        InMemoryCasStore sharedStore = new InMemoryCasStore("shared");
        InMemoryCasCatalog sharedCatalog = new InMemoryCasCatalog();
        var weakPolicy = new TenantContentAddressedCache.ArtifactPolicy(
                "cn-north", CasAccessPolicy.SecurityTier.CONFIDENTIAL,
                CasObjectModel.RetentionClass.EPHEMERAL);
        var strongPolicy = new TenantContentAddressedCache.ArtifactPolicy(
                "cn-north", CasAccessPolicy.SecurityTier.CONFIDENTIAL,
                CasObjectModel.RetentionClass.EVIDENCE);
        var writer = new TenantContentAddressedCache(sharedStore, sharedCatalog, weakPolicy);
        var reader = new TenantContentAddressedCache(sharedStore, sharedCatalog, strongPolicy);
        byte[] artifact = bytes("short-lived artifact");

        writer.put("tenant-a", "trust-a", manifest("source"), artifact,
                TenantContentAddressedCache.digest(artifact), true);

        assertThrows(SecurityException.class,
                () -> reader.lookup("tenant-a", "trust-a", manifest("source")));
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
        InMemoryCasStore store = new InMemoryCasStore("shared");
        InMemoryCasCatalog catalog = new InMemoryCasCatalog();
        var cache = new TenantContentAddressedCache(store, catalog);
        byte[] artifact = bytes("private artifact");
        var ref = cache.put("tenant-a", "trust-a", manifest("source"), artifact,
                TenantContentAddressedCache.digest(artifact), true);

        assertEquals(Optional.empty(), cache.get("tenant-b", "trust-a", ref));
        assertEquals(Optional.empty(), cache.get("tenant-a", "trust-b", ref));
        assertTrue(catalog.activeReferenceRoots("tenant-b").isEmpty());
    }

    @Test void relabellingAStolenReferenceCannotCrossATrustDomain() {
        InMemoryCasStore store = new InMemoryCasStore("shared");
        InMemoryCasCatalog catalog = new InMemoryCasCatalog();
        var cache = new TenantContentAddressedCache(store, catalog);
        byte[] artifact = bytes("private artifact");
        var original = cache.put("tenant-a", "trust-a", manifest("source"), artifact,
                TenantContentAddressedCache.digest(artifact), true);
        var relabelled = new TenantContentAddressedCache.ArtifactRef(
                original.tenantId(), "trust-b", original.cacheKey(), original.artifactDigest(),
                original.sizeBytes());

        assertEquals(Optional.empty(), cache.get("tenant-a", "trust-b", relabelled));
    }

    @Test void aCacheKeyCannotBeReboundToDifferentBytes() {
        InMemoryCasStore store = new InMemoryCasStore("shared");
        InMemoryCasCatalog catalog = new InMemoryCasCatalog();
        var firstInstance = new TenantContentAddressedCache(store, catalog);
        var competingInstance = new TenantContentAddressedCache(store, catalog);
        byte[] first = bytes("deterministic output");
        byte[] conflicting = bytes("different output for the same complete inputs");

        var firstRef = firstInstance.put("tenant-a", "trust-a", manifest("source"), first,
                TenantContentAddressedCache.digest(first), true);

        assertThrows(IllegalStateException.class, () -> competingInstance.put(
                "tenant-a", "trust-a", manifest("source"), conflicting,
                TenantContentAddressedCache.digest(conflicting), true));

        assertTrue(firstInstance.invalidate("tenant-a", "trust-a", firstRef));
        var replacement = competingInstance.put(
                "tenant-a", "trust-a", manifest("source"), conflicting,
                TenantContentAddressedCache.digest(conflicting), true);
        assertTrue(replacement.generation() > firstRef.generation());
        assertArrayEquals(conflicting,
                firstInstance.lookup("tenant-a", "trust-a", manifest("source"))
                        .orElseThrow().bytes());
    }

    @Test void lateInvalidationCannotReleaseARebuiltGeneration() {
        InMemoryCasStore store = new InMemoryCasStore("shared");
        InMemoryCasCatalog catalog = new InMemoryCasCatalog();
        AtomicLong clock = new AtomicLong(100L);
        var firstInstance = new TenantContentAddressedCache(
                store, catalog, policy("cn-north"), clock::get);
        var secondInstance = new TenantContentAddressedCache(
                store, catalog, policy("cn-north"), clock::get);
        byte[] first = bytes("first generation");
        byte[] replacement = first.clone();

        var staleRef = firstInstance.put(
                "tenant-a", "trust-a", manifest("source"), first,
                TenantContentAddressedCache.digest(first), true);
        assertTrue(firstInstance.invalidate("tenant-a", "trust-a", staleRef));

        // Even with a restarted caller whose wall clock moved backwards, the durable catalogue
        // allocates a generation above the released history.
        clock.set(50L);
        var currentRef = secondInstance.put(
                "tenant-a", "trust-a", manifest("source"), replacement,
                TenantContentAddressedCache.digest(replacement), true);
        assertTrue(currentRef.generation() > staleRef.generation());

        assertFalse(firstInstance.invalidate("tenant-a", "trust-a", staleRef));
        assertEquals(Optional.empty(), firstInstance.get("tenant-a", "trust-a", staleRef));
        assertArrayEquals(replacement,
                firstInstance.lookup("tenant-a", "trust-a", manifest("source"))
                        .orElseThrow().bytes());
        assertTrue(secondInstance.invalidate("tenant-a", "trust-a", currentRef));
        assertEquals(Optional.empty(),
                firstInstance.lookup("tenant-a", "trust-a", manifest("source")));
    }

    @Test void compatibilityReferenceWithUnknownGenerationCannotInvalidate() {
        InMemoryCasStore store = new InMemoryCasStore("shared");
        InMemoryCasCatalog catalog = new InMemoryCasCatalog();
        var cache = new TenantContentAddressedCache(store, catalog, policy("cn-north"));
        byte[] artifact = bytes("current artifact");
        var current = cache.put(
                "tenant-a", "trust-a", manifest("source"), artifact,
                TenantContentAddressedCache.digest(artifact), true);
        var legacy = new TenantContentAddressedCache.ArtifactRef(
                current.tenantId(), current.trustDomain(), current.cacheKey(),
                current.artifactDigest(), current.sizeBytes());

        assertFalse(legacy.hasKnownGeneration());
        var missingPrimitiveGeneration = new TenantContentAddressedCache.ArtifactRef(
                current.tenantId(), current.trustDomain(), current.cacheKey(),
                current.artifactDigest(), current.sizeBytes(), 0L);
        assertFalse(missingPrimitiveGeneration.hasKnownGeneration(),
                "a missing serialized primitive generation must fail closed as unknown");
        assertThrows(IllegalArgumentException.class,
                () -> cache.invalidate("tenant-a", "trust-a", legacy));
        assertArrayEquals(artifact,
                cache.lookup("tenant-a", "trust-a", manifest("source"))
                        .orElseThrow().bytes());
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

    @Test void oneMissingReadCannotGloballyReleaseTheDurableRoot() {
        InMemoryCasStore store = new InMemoryCasStore("shared");
        InMemoryCasCatalog catalog = new InMemoryCasCatalog();
        var cache = new TenantContentAddressedCache(store, catalog);
        byte[] artifact = bytes("collectable artifact");
        var ref = cache.put("tenant-a", "trust-a", manifest("source"), artifact,
                TenantContentAddressedCache.digest(artifact), true);

        store.delete(CasDigest.of(artifact));
        assertEquals(Optional.empty(), cache.get("tenant-a", "trust-a", ref));
        assertTrue(catalog.activeReferenceRoots("tenant-a").stream()
                .anyMatch(root -> root.kind() == CasGarbageCollector.RootKind.ACTION_CACHE),
                "a lagging or transiently missing reader must not revoke a global root");
        assertTrue(cache.invalidate("tenant-a", "trust-a", ref),
                "explicit generation-bound reconciliation may release the missing object");
        assertTrue(catalog.activeReferenceRoots("tenant-a").stream()
                .noneMatch(root -> root.kind() == CasGarbageCollector.RootKind.ACTION_CACHE));
    }

    @Test void referenceDigestAndSizeMustBothMatchTheDurableMapping() {
        InMemoryCasStore store = new InMemoryCasStore("shared");
        InMemoryCasCatalog catalog = new InMemoryCasCatalog();
        var cache = new TenantContentAddressedCache(store, catalog);
        byte[] artifact = bytes("sized artifact");
        var ref = cache.put("tenant-a", "trust-a", manifest("source"), artifact,
                TenantContentAddressedCache.digest(artifact), true);
        var wrongSize = new TenantContentAddressedCache.ArtifactRef(
                ref.tenantId(), ref.trustDomain(), ref.cacheKey(), ref.artifactDigest(),
                ref.sizeBytes() + 1);

        assertThrows(IllegalStateException.class,
                () -> cache.get("tenant-a", "trust-a", wrongSize));
    }
}
