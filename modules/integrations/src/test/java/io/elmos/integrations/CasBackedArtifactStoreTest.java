package io.elmos.integrations;

import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.CasCatalog;
import io.elmos.cas.CasDigest;
import io.elmos.cas.CasExceptions;
import io.elmos.cas.CasGarbageCollector;
import io.elmos.cas.CasObjectModel;
import io.elmos.cas.CasStore;
import io.elmos.cas.InMemoryCasCatalog;
import io.elmos.cas.InMemoryCasStore;
import io.elmos.cas.TenantCasStore;
import io.elmos.cas.TieredCasStore;
import io.elmos.snapshot.SnapshotPorts;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class CasBackedArtifactStoreTest {

    private static final long NOW = 1_800_000_000_000L;

    private final InMemoryCasStore store = new InMemoryCasStore("l2");
    private final InMemoryCasCatalog catalog = new InMemoryCasCatalog();
    private static final SnapshotPorts.ArtifactResourceContext TENANT_A =
            new SnapshotPorts.ArtifactResourceContext("tenant-a", "project-a");
    private static final SnapshotPorts.ArtifactResourceContext TENANT_B =
            new SnapshotPorts.ArtifactResourceContext("tenant-b", "project-b");

    private CasBackedArtifactStore artifacts() {
        return new CasBackedArtifactStore(store, catalog, "eu-west",
                CasAccessPolicy.SecurityTier.CONFIDENTIAL, 64L * 1024 * 1024, () -> NOW);
    }

    private TenantCasStore tenantIsolatedStore() {
        return new TenantCasStore() {
            @Override
            public CasStore forTenant(String tenantId) {
                return store;
            }

            @Override
            public String atRestProtection() {
                return "TEST_ONLY";
            }

            @Override
            public String physicalNamespace() {
                return "TEST_TENANT_ISOLATED";
            }

            @Override
            public DeletionScope deletionScope() {
                return DeletionScope.TENANT_ISOLATED;
            }
        };
    }

    private static byte[] bytes(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    private static InputStream stream(String text) {
        return new ByteArrayInputStream(bytes(text));
    }

    @Test void itSatisfiesTheSnapshotPortsSoTheMaterialiserCanUseIt() {
        SnapshotPorts.ArtifactStore writer = artifacts();
        SnapshotPorts.ArtifactReader reader = artifacts();
        assertNotNull(writer);
        assertNotNull(reader);
    }

    @Test void anArtifactIsStoredCataloguedAndReadableByItsReference() throws Exception {
        var artifacts = artifacts();
        byte[] content = bytes("snapshot archive");
        CasDigest digest = CasDigest.of(content);

        String reference = artifacts.putIfAbsent(TENANT_A, digest.hex(), content.length, stream("snapshot archive"),
                "application/zstd");

        assertEquals("cas://sha256/" + digest.hex() + "/" + content.length, reference);
        assertTrue(store.contains(digest));
        try (InputStream opened = artifacts.open(TENANT_A, reference)) {
            assertArrayEquals(content, opened.readAllBytes());
        }

        var entry = catalog.find("tenant-a", digest).orElseThrow();
        assertEquals("application/zstd", entry.mediaType());
        assertEquals("eu-west", entry.dataResidency());
        assertEquals(CasAccessPolicy.SecurityTier.CONFIDENTIAL, entry.securityTier());
        assertEquals(CasObjectModel.Sensitivity.PRIVATE_SOURCE, entry.sensitivity(),
                "content derived from customer source is never cross-tenant shareable");
        assertEquals(NOW, entry.createdAtEpochMillis());
        assertEquals(List.of(new CasCatalog.ResourceBinding(
                        "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                        "project-a", digest, NOW)),
                catalog.activeResourceBindings(
                        "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                        "project-a"));
    }

    @Test void storingTheSameArtifactTwiceDoesNotResendTheBytesButStillCatalogues() {
        var artifacts = artifacts();
        byte[] content = bytes("repeated archive");
        CasDigest digest = CasDigest.of(content);

        artifacts.putIfAbsent(TENANT_A, digest.hex(), content.length,
                stream("repeated archive"), "application/zstd");
        assertEquals(1, store.inventory().size());

        // Second call: a stream that would fail if it were read at all.
        artifacts.putIfAbsent(TENANT_A, digest.hex(), content.length,
                InputStream.nullInputStream(), "application/zstd");
        assertEquals(1, store.inventory().size());
        assertEquals(1, catalog.load("tenant-a", Set.of(digest)).size());
    }

    @Test void aSnapshotRootOnlyPublishesAfterBytesReachTheSharedTier() throws Exception {
        InMemoryCasStore shared = new InMemoryCasStore("shared-l2");
        InMemoryCasCatalog sharedCatalog = new InMemoryCasCatalog();
        TieredCasStore writerStore = new TieredCasStore(
                new InMemoryCasStore("writer-l1"), shared,
                TieredCasStore.TierPolicy.unbounded(), () -> NOW);
        TieredCasStore readerStore = new TieredCasStore(
                new InMemoryCasStore("reader-l1"), shared,
                TieredCasStore.TierPolicy.unbounded(), () -> NOW);
        var writer = new CasBackedArtifactStore(
                writerStore, sharedCatalog, "eu-west",
                CasAccessPolicy.SecurityTier.CONFIDENTIAL, 64L * 1024 * 1024, () -> NOW);
        var reader = new CasBackedArtifactStore(
                readerStore, sharedCatalog, "eu-west",
                CasAccessPolicy.SecurityTier.CONFIDENTIAL, 64L * 1024 * 1024, () -> NOW);
        byte[] archive = bytes("durable tiered archive");
        byte[] manifest = bytes("durable tiered manifest");
        CasDigest archiveDigest = CasDigest.of(archive);
        CasDigest manifestDigest = CasDigest.of(manifest);

        String archiveReference = writer.putIfAbsent(
                TENANT_A, archiveDigest.hex(), archive.length,
                new ByteArrayInputStream(archive), "application/zstd");
        String manifestReference = writer.putIfAbsent(
                TENANT_A, manifestDigest.hex(), manifest.length,
                new ByteArrayInputStream(manifest), "application/json");
        assertTrue(shared.contains(archiveDigest),
                "putIfAbsent must complete authoritative storage before binding");
        assertTrue(shared.contains(manifestDigest),
                "putIfAbsent must complete authoritative storage before binding");

        // Simulate a legacy/write-back state whose catalogue bindings and writer L1 survived but
        // whose authoritative copies are absent. Root publication must repair L2 first.
        assertTrue(shared.delete(archiveDigest));
        assertTrue(shared.delete(manifestDigest));
        writer.retainSnapshotGeneration(
                TENANT_A, "snapshot-tiered-durable",
                List.of(archiveReference, manifestReference));

        assertTrue(shared.contains(archiveDigest));
        assertTrue(shared.contains(manifestDigest));
        assertTrue(writerStore.pendingDurability().isEmpty());
        assertEquals(2, sharedCatalog.activeReferenceRoots("tenant-a").size());
        try (InputStream openedArchive = reader.open(TENANT_A, archiveReference);
             InputStream openedManifest = reader.open(TENANT_A, manifestReference)) {
            assertArrayEquals(archive, openedArchive.readAllBytes());
            assertArrayEquals(manifest, openedManifest.readAllBytes());
        }
    }

    @Test void anExistingBoundWeakRetentionIsUpgradedBeforeSnapshotReuse() {
        var artifacts = artifacts();
        byte[] content = bytes("legacy ephemeral snapshot artifact");
        CasDigest digest = CasDigest.of(content);
        store.put(digest, content);
        catalog.record(new CasCatalog.CatalogEntry(
                "tenant-a", digest, CasObjectModel.ObjectKind.BLOB,
                "application/zstd", "snapshot", "1.0",
                CasObjectModel.Sensitivity.PRIVATE_SOURCE,
                CasObjectModel.RetentionClass.EPHEMERAL,
                "eu-west", CasAccessPolicy.SecurityTier.CONFIDENTIAL,
                Optional.empty(), Map.of(), false, NOW - 1));
        catalog.bindResource(new CasCatalog.ResourceBinding(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "project-a", digest, NOW - 1));

        String legacyReference = CasBackedArtifactStore.reference(digest);
        assertThrows(SecurityException.class, () -> artifacts.retainSnapshotGeneration(
                TENANT_A, "snapshot-weak-retention", List.of(legacyReference)));
        assertTrue(catalog.activeReferenceRoots("tenant-a").isEmpty(),
                "weak legacy metadata must not become a snapshot root");

        String reference = artifacts.putIfAbsent(
                TENANT_A, digest.hex(), content.length,
                InputStream.nullInputStream(), "application/zstd");

        assertEquals(CasObjectModel.RetentionClass.STANDARD,
                catalog.find("tenant-a", digest).orElseThrow().retentionClass());
        assertDoesNotThrow(() -> artifacts.retainSnapshotGeneration(
                TENANT_A, "snapshot-upgraded-retention", List.of(reference)));
    }

    @Test void aDeclaredDigestThatDoesNotMatchTheStreamIsRefused() {
        var artifacts = artifacts();
        CasDigest lie = CasDigest.of(bytes("what was promised"));
        assertThrows(CasExceptions.CasCorruptionException.class,
                () -> artifacts.putIfAbsent(TENANT_A, lie.hex(), bytes("what arrived").length,
                        stream("what arrived"), "application/zstd"));
        assertTrue(store.inventory().isEmpty());
        assertTrue(catalog.find("tenant-a", lie).isEmpty());
    }

    @Test void aStreamLongerThanItsDeclaredSizeIsRefused() {
        var artifacts = artifacts();
        CasDigest digest = CasDigest.of(bytes("short"));
        var error = assertThrows(IllegalArgumentException.class,
                () -> artifacts.putIfAbsent(TENANT_A, digest.hex(), 5,
                        stream("short but actually longer"),
                        "application/octet-stream"));
        assertTrue(error.getMessage().contains("longer than its declared size"));
    }

    @Test void aStreamShorterThanItsDeclaredSizeIsRefused() {
        var artifacts = artifacts();
        CasDigest digest = CasDigest.of(bytes("declared long"));
        var error = assertThrows(IllegalArgumentException.class,
                () -> artifacts.putIfAbsent(TENANT_A, digest.hex(), 1_000,
                        stream("declared long"),
                        "application/octet-stream"));
        assertTrue(error.getMessage().contains("ended after"));
    }

    @Test void anInvalidIdentityOrOversizedArtifactNeverReachesTheStore() {
        var artifacts = artifacts();
        assertThrows(IllegalArgumentException.class,
                () -> artifacts.putIfAbsent(TENANT_A, "NOTHEX", 4, stream("data"), "text/plain"));
        assertThrows(IllegalArgumentException.class,
                () -> artifacts.putIfAbsent(TENANT_A, CasDigest.of(bytes("x")).hex(),
                        -1, stream("x"), "text/plain"));
        assertThrows(IllegalArgumentException.class,
                () -> artifacts.putIfAbsent(TENANT_A, CasDigest.of(bytes("x")).hex(),
                        1_000_000_000L, stream("x"),
                        "text/plain"));
        assertTrue(store.inventory().isEmpty());
    }

    @Test void aPoisonedArtifactIsCaughtOnTheWayOutRatherThanUnpacked() {
        var artifacts = artifacts();
        byte[] content = bytes("trusted archive");
        CasDigest digest = CasDigest.of(content);
        String reference = artifacts.putIfAbsent(TENANT_A, digest.hex(), content.length,
                stream("trusted archive"),
                "application/zstd");

        store.corruptForFaultInjection(digest, bytes("tampered archive!"));
        assertThrows(CasExceptions.CasCorruptionException.class,
                () -> artifacts.open(TENANT_A, reference));
    }

    @Test void aDigestReferenceNeverAuthorizesAnotherTenantOrRepository() {
        var artifacts = artifacts();
        byte[] content = bytes("tenant-private archive");
        CasDigest digest = CasDigest.of(content);
        String reference = artifacts.putIfAbsent(TENANT_A, digest.hex(), content.length,
                new ByteArrayInputStream(content), "application/zstd");

        assertThrows(SecurityException.class, () -> artifacts.open(TENANT_B, reference));
        assertThrows(SecurityException.class, () -> artifacts.open(
                new SnapshotPorts.ArtifactResourceContext("tenant-a", "project-b"), reference));
        assertTrue(catalog.find("tenant-b", digest).isEmpty());
    }

    @Test void anExistingGlobalBlobCannotBeClaimedByDigestWithoutProvidingItsBytes() throws Exception {
        var artifacts = artifacts();
        byte[] content = bytes("already in the global store");
        CasDigest digest = CasDigest.of(content);
        artifacts.putIfAbsent(TENANT_A, digest.hex(), content.length,
                new ByteArrayInputStream(content), "application/zstd");

        assertThrows(IllegalArgumentException.class,
                () -> artifacts.putIfAbsent(TENANT_B, digest.hex(), content.length,
                        InputStream.nullInputStream(), "application/zstd"));
        assertTrue(catalog.find("tenant-b", digest).isEmpty());

        // A second tenant that really supplies the complete bytes may own an independent
        // catalogue row; it still cannot read tenant A's project binding.
        String tenantBReference = artifacts.putIfAbsent(TENANT_B, digest.hex(), content.length,
                new ByteArrayInputStream(content), "application/zstd");
        assertArrayEquals(content, artifacts.open(TENANT_B, tenantBReference).readAllBytes());
        assertThrows(SecurityException.class, () -> artifacts.open(
                new SnapshotPorts.ArtifactResourceContext("tenant-b", "another-project"),
                tenantBReference));
    }

    @Test void tenantStoreResolutionKeepsIdenticalPrivateBytesInSeparatePhysicalNamespaces()
            throws Exception {
        Map<String, InMemoryCasStore> tenantStores = new LinkedHashMap<>();
        TenantCasStore scoped = new TenantCasStore() {
            @Override
            public CasStore forTenant(String tenantId) {
                return tenantStores.computeIfAbsent(
                        tenantId, id -> new InMemoryCasStore("tenant-" + id));
            }

            @Override
            public String atRestProtection() {
                return "TEST_TENANT_SCOPED";
            }

            @Override
            public String physicalNamespace() {
                return "TEST_TENANT_NAMESPACE";
            }
        };
        var artifacts = new CasBackedArtifactStore(
                scoped, catalog, "eu-west", CasAccessPolicy.SecurityTier.CONFIDENTIAL,
                64L * 1024 * 1024, () -> NOW);
        byte[] content = bytes("same private bytes");
        CasDigest digest = CasDigest.of(content);

        String tenantA = artifacts.putIfAbsent(
                TENANT_A, digest.hex(), content.length,
                new ByteArrayInputStream(content), "application/zstd");
        String tenantB = artifacts.putIfAbsent(
                TENANT_B, digest.hex(), content.length,
                new ByteArrayInputStream(content), "application/zstd");

        assertEquals(1, tenantStores.get("tenant-a").inventory().size());
        assertEquals(1, tenantStores.get("tenant-b").inventory().size());
        tenantStores.get("tenant-a").corruptForFaultInjection(digest, bytes("poisoned tenant A"));
        assertThrows(CasExceptions.CasCorruptionException.class,
                () -> artifacts.open(TENANT_A, tenantA));
        assertArrayEquals(content, artifacts.open(TENANT_B, tenantB).readAllBytes());
    }

    @Test void twoRepositoriesInOneTenantCanBindIdenticalVerifiedBytesIndependently()
            throws Exception {
        var artifacts = artifacts();
        byte[] content = bytes("same source bytes");
        CasDigest digest = CasDigest.of(content);
        var repositoryB = new SnapshotPorts.ArtifactResourceContext("tenant-a", "project-b");

        String repositoryAReference = artifacts.putIfAbsent(
                TENANT_A, digest.hex(), content.length,
                new ByteArrayInputStream(content), "application/zstd");
        assertThrows(IllegalArgumentException.class, () -> artifacts.putIfAbsent(
                repositoryB, digest.hex(), content.length,
                InputStream.nullInputStream(), "application/zstd"));

        String repositoryBReference = artifacts.putIfAbsent(
                repositoryB, digest.hex(), content.length,
                new ByteArrayInputStream(content), "application/zstd");

        assertEquals(repositoryAReference, repositoryBReference);
        assertArrayEquals(content, artifacts.open(repositoryB, repositoryBReference).readAllBytes());
        assertEquals(1, store.inventory().size());
        assertEquals(1, catalog.activeResourceBindings(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "project-a").size());
        assertEquals(1, catalog.activeResourceBindings(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "project-b").size());
    }

    @Test void activeSnapshotRootsProtectBothArtifactsUntilExplicitRelease() {
        var artifacts = artifacts();
        byte[] archive = bytes("rooted archive");
        byte[] manifest = bytes("rooted manifest");
        CasDigest archiveDigest = CasDigest.of(archive);
        CasDigest manifestDigest = CasDigest.of(manifest);
        String archiveReference = artifacts.putIfAbsent(
                TENANT_A, archiveDigest.hex(), archive.length,
                new ByteArrayInputStream(archive), "application/zstd");
        String manifestReference = artifacts.putIfAbsent(
                TENANT_A, manifestDigest.hex(), manifest.length,
                new ByteArrayInputStream(manifest), "application/json");

        SnapshotPorts.ArtifactRetention retention = artifacts.retainSnapshotGeneration(
                TENANT_A, "snapshot-live", List.of(archiveReference, manifestReference));
        artifacts.retainSnapshot(TENANT_A, "snapshot-live",
                List.of(archiveReference, manifestReference));
        assertThrows(IllegalStateException.class, () -> artifacts.retainSnapshot(
                TENANT_A, "snapshot-live", List.of(archiveReference)),
                "an incomplete retry must not replace a live archive+manifest root set");
        assertEquals(2, catalog.activeReferenceRoots("tenant-a").size());
        artifacts.releaseSnapshotGeneration(
                new SnapshotPorts.ArtifactResourceContext("tenant-a", "project-b"),
                retention);
        assertEquals(2, catalog.activeReferenceRoots("tenant-a").size(),
                "another repository cannot release this snapshot's roots");
        List<CasGarbageCollector.ReferenceRoot> roots = catalog.activeReferenceRoots("tenant-a")
                .stream()
                .map(root -> new CasGarbageCollector.ReferenceRoot(
                        root.kind(), root.rootId(), root.tenantId(), List.of(root.digest())))
                .toList();
        var collector = new CasGarbageCollector(
                store, ignored -> Optional.empty(), () -> NOW + 1,
                candidate -> catalog.deleteIfUnreferenced(
                        candidate, tenantIsolatedStore()));
        Map<CasDigest, CasObjectModel.ObjectMetadata> metadata = catalog.load(
                "tenant-a", Set.of(archiveDigest, manifestDigest));

        var whileLive = collector.collect(roots, metadata,
                CasGarbageCollector.CollectionPolicy.dryRun(0).executing(), "while-live");

        assertTrue(whileLive.collected().isEmpty());
        assertEquals(2, whileLive.retained().stream()
                .filter(retained -> retained.reason().equals("REACHABLE")).count());

        artifacts.releaseSnapshotGeneration(TENANT_A, retention);
        var whileResourceBound = collector.collect(List.of(), metadata,
                CasGarbageCollector.CollectionPolicy.dryRun(0).executing(), "after-release");
        assertTrue(whileResourceBound.collected().isEmpty(),
                "an active repository binding remains a live reference after snapshot release");
        assertEquals(2, whileResourceBound.retained().stream()
                .filter(retained -> retained.reason().equals(
                        "LIVE_REFERENCE_RECHECK_BLOCKED")).count());

        catalog.releaseResource("tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "project-a", archiveDigest, NOW + 2);
        catalog.releaseResource("tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "project-a", manifestDigest, NOW + 2);
        var afterRelease = collector.collect(List.of(), metadata,
                CasGarbageCollector.CollectionPolicy.dryRun(0).executing(),
                "after-resource-release");
        assertEquals(Set.of(archiveDigest, manifestDigest), afterRelease.collected().stream()
                .map(CasGarbageCollector.Candidate::digest).collect(java.util.stream.Collectors.toSet()));
        assertTrue(store.inventory().isEmpty());
    }

    @Test void unconditionalCollectorReleaseIsRejectedBeforeChangingRoots() {
        var artifacts = artifacts();
        byte[] content = bytes("generation required");
        CasDigest digest = CasDigest.of(content);
        String reference = artifacts.putIfAbsent(
                TENANT_A, digest.hex(), content.length,
                new ByteArrayInputStream(content), "application/zstd");
        artifacts.retainSnapshotGeneration(
                TENANT_A, "snapshot-token-only", List.of(reference));

        assertThrows(UnsupportedOperationException.class,
                () -> artifacts.releaseSnapshot(TENANT_A, "snapshot-token-only"));
        assertEquals(1, catalog.activeReferenceRoots("tenant-a").size());
    }

    @Test void referencesRoundTripAndMalformedOnesAreRefused() {
        CasDigest digest = CasDigest.of(bytes("round trip"));
        assertEquals(digest, CasBackedArtifactStore.parse(CasBackedArtifactStore.reference(digest)));
        assertThrows(IllegalArgumentException.class, () -> CasBackedArtifactStore.parse("file:///tmp/x"));
        assertThrows(IllegalArgumentException.class,
                () -> CasBackedArtifactStore.parse("cas://sha1/" + digest.hex() + "/10"));
        assertThrows(IllegalArgumentException.class,
                () -> CasBackedArtifactStore.parse("cas://sha256/" + digest.hex()));
        assertThrows(IllegalArgumentException.class,
                () -> CasBackedArtifactStore.parse(
                        "cas://sha256/" + digest.hex() + "/" + digest.sizeBytes() + "/"));
        assertThrows(IllegalArgumentException.class,
                () -> CasBackedArtifactStore.parse(
                        "cas://sha256/" + digest.hex() + "/+" + digest.sizeBytes()));
        assertThrows(IllegalArgumentException.class,
                () -> CasBackedArtifactStore.parse(
                        "cas://sha256/" + digest.hex() + "/0" + digest.sizeBytes()));
    }

    @Test void snapshotIdBoundaryIsRejectedBeforeAnyRootPublication() {
        var artifacts = artifacts();
        byte[] content = bytes("snapshot id boundary artifact");
        CasDigest digest = CasDigest.of(content);
        String reference = artifacts.putIfAbsent(
                TENANT_A, digest.hex(), content.length,
                new ByteArrayInputStream(content), "application/zstd");
        String maximumSnapshotId = "s".repeat(64);

        SnapshotPorts.ArtifactRetention retention = artifacts.retainSnapshotGeneration(
                TENANT_A, maximumSnapshotId, List.of(reference));
        assertEquals(maximumSnapshotId, retention.snapshotId());
        artifacts.releaseSnapshotGeneration(TENANT_A, retention);
        assertTrue(catalog.activeReferenceRoots("tenant-a").isEmpty());

        assertThrows(IllegalArgumentException.class,
                () -> artifacts.retainSnapshotGeneration(
                        TENANT_A, "s".repeat(65), List.of(reference)));
        assertTrue(catalog.activeReferenceRoots("tenant-a").isEmpty(),
                "an invalid receipt identity must fail before publishing a root");
    }

    @Test void delayedGenerationReleaseCannotHideAReactivatedSnapshotRoot() {
        java.util.concurrent.atomic.AtomicLong clock =
                new java.util.concurrent.atomic.AtomicLong(NOW);
        var artifacts = new CasBackedArtifactStore(
                store, catalog, "cn-east",
                CasAccessPolicy.SecurityTier.CONFIDENTIAL,
                64L * 1024 * 1024, clock::get);
        byte[] archive = bytes("generation archive");
        byte[] manifest = bytes("generation manifest");
        String archiveReference = artifacts.putIfAbsent(
                TENANT_A, CasDigest.of(archive).hex(), archive.length,
                new ByteArrayInputStream(archive), "application/zstd");
        String manifestReference = artifacts.putIfAbsent(
                TENANT_A, CasDigest.of(manifest).hex(), manifest.length,
                new ByteArrayInputStream(manifest), "application/json");

        SnapshotPorts.ArtifactRetention oldGeneration =
                artifacts.retainSnapshotGeneration(TENANT_A, "snapshot-generation",
                        List.of(archiveReference, manifestReference));
        artifacts.releaseSnapshotGeneration(TENANT_A, oldGeneration);
        // Re-acquire through a new adapter after its clock moved backwards. Generation authority
        // must live in the shared catalogue, not in process memory or wall-clock monotonicity.
        clock.set(NOW - 10_000L);
        var restartedArtifacts = new CasBackedArtifactStore(
                store, catalog, "cn-east",
                CasAccessPolicy.SecurityTier.CONFIDENTIAL,
                64L * 1024 * 1024, clock::get);
        SnapshotPorts.ArtifactRetention newGeneration =
                restartedArtifacts.retainSnapshotGeneration(TENANT_A, "snapshot-generation",
                        List.of(archiveReference, manifestReference));

        artifacts.releaseSnapshotGeneration(TENANT_A, oldGeneration);

        assertEquals(2, catalog.activeReferenceRoots("tenant-a").size(),
                "a delayed old attempt must leave the new generation active");
        assertTrue(newGeneration.requireGeneration(CasBackedArtifactStore.ROOT_GENERATION)
                > oldGeneration.requireGeneration(CasBackedArtifactStore.ROOT_GENERATION));
    }

    @Test void repositoryRetirementReconcilesEverySnapshotBeforeReleasingSharedBindings() {
        java.util.concurrent.atomic.AtomicLong clock =
                new java.util.concurrent.atomic.AtomicLong(NOW);
        var artifacts = new CasBackedArtifactStore(
                store, catalog, "eu-west",
                CasAccessPolicy.SecurityTier.CONFIDENTIAL,
                64L * 1024 * 1024, clock::get);
        byte[] archive = bytes("retiring repository archive");
        byte[] manifest = bytes("retiring repository manifest");
        String archiveReference = artifacts.putIfAbsent(
                TENANT_A, CasDigest.of(archive).hex(), archive.length,
                new ByteArrayInputStream(archive), "application/zstd");
        String manifestReference = artifacts.putIfAbsent(
                TENANT_A, CasDigest.of(manifest).hex(), manifest.length,
                new ByteArrayInputStream(manifest), "application/json");
        List<String> references = List.of(archiveReference, manifestReference);

        clock.set(NOW + 100L);
        SnapshotPorts.ArtifactRetention first = artifacts.retainSnapshotGeneration(
                TENANT_A, "snapshot-retirement-one", references);
        clock.set(NOW + 200L);
        SnapshotPorts.ArtifactRetention second = artifacts.retainSnapshotGeneration(
                TENANT_A, "snapshot-retirement-two", references);
        assertEquals(2, catalog.activeResourceBindings(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "project-a").size(),
                "two snapshots share the repository bindings rather than duplicating them");

        clock.set(NOW + 300L);
        CasCatalog.ResourceLifecycle retiring =
                artifacts.beginRepositoryRetirement(TENANT_A);
        assertEquals(CasCatalog.ResourceLifecycleState.RETIRING, retiring.state());

        byte[] lateArtifact = bytes("late repository artifact");
        assertThrows(IllegalStateException.class, () -> artifacts.putIfAbsent(
                TENANT_A, CasDigest.of(lateArtifact).hex(), lateArtifact.length,
                new ByteArrayInputStream(lateArtifact), "application/zstd"));
        assertThrows(IllegalStateException.class,
                () -> artifacts.retainSnapshotGeneration(
                        TENANT_A, "snapshot-after-retirement", references));
        assertFalse(store.contains(CasDigest.of(lateArtifact)));
        assertTrue(catalog.activeReferenceRoots(
                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                CasBackedArtifactStore.snapshotRootOwner(
                        TENANT_A, "snapshot-after-retirement")).isEmpty());

        clock.set(NOW + 400L);
        long firstGeneration =
                first.requireGeneration(CasBackedArtifactStore.ROOT_GENERATION);
        artifacts.releaseSnapshotGeneration(
                TENANT_A,
                new SnapshotPorts.ArtifactRetention(
                        first.snapshotId(),
                        Map.of(CasBackedArtifactStore.ROOT_GENERATION,
                                firstGeneration - 1)));
        assertThrows(IllegalStateException.class,
                () -> artifacts.finalizeRepositoryRetirement(retiring),
                "an inexact old snapshot receipt must not advance retirement");

        artifacts.releaseSnapshotGeneration(TENANT_A, first);
        assertThrows(IllegalStateException.class,
                () -> artifacts.finalizeRepositoryRetirement(retiring),
                "the second snapshot still protects both shared bindings");
        assertEquals(2, catalog.activeResourceBindings(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "project-a").size());

        clock.set(NOW + 500L);
        artifacts.releaseSnapshotGeneration(TENANT_A, second);
        clock.set(NOW + 600L);
        CasCatalog.ResourceLifecycle retired =
                artifacts.finalizeRepositoryRetirement(retiring);
        assertEquals(CasCatalog.ResourceLifecycleState.RETIRED, retired.state());
        assertEquals(2L, retired.releasedBindingCount());
        assertTrue(catalog.activeResourceBindings(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "project-a").isEmpty());
        assertThrows(SecurityException.class,
                () -> artifacts.open(TENANT_A, archiveReference));
        assertThrows(IllegalStateException.class, () -> artifacts.putIfAbsent(
                TENANT_A, CasDigest.of(lateArtifact).hex(), lateArtifact.length,
                new ByteArrayInputStream(lateArtifact), "application/zstd"));

        clock.set(NOW + 700L);
        CasCatalog.ResourceLifecycle reactivated =
                artifacts.reactivateRepository(retired);
        assertEquals(retired.resourceEpoch() + 1, reactivated.resourceEpoch());
        clock.set(NOW + 800L);
        assertThrows(IllegalStateException.class,
                () -> artifacts.finalizeRepositoryRetirement(retiring));
        assertThrows(IllegalStateException.class,
                () -> artifacts.reactivateRepository(retired));
        assertEquals(reactivated, catalog.ensureActiveResource(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "project-a"));

        assertDoesNotThrow(() -> artifacts.putIfAbsent(
                TENANT_A, CasDigest.of(lateArtifact).hex(), lateArtifact.length,
                new ByteArrayInputStream(lateArtifact), "application/zstd"));
    }
}
