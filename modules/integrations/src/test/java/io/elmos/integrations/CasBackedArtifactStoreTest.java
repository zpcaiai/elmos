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

        artifacts.retainSnapshot(TENANT_A, "snapshot-live",
                List.of(archiveReference, manifestReference));
        artifacts.retainSnapshot(TENANT_A, "snapshot-live",
                List.of(archiveReference, manifestReference));
        assertThrows(IllegalStateException.class, () -> artifacts.retainSnapshot(
                TENANT_A, "snapshot-live", List.of(archiveReference)),
                "an incomplete retry must not replace a live archive+manifest root set");
        assertEquals(2, catalog.activeReferenceRoots("tenant-a").size());
        artifacts.releaseSnapshot(
                new SnapshotPorts.ArtifactResourceContext("tenant-a", "project-b"),
                "snapshot-live");
        assertEquals(2, catalog.activeReferenceRoots("tenant-a").size(),
                "another repository cannot release this snapshot's roots");
        List<CasGarbageCollector.ReferenceRoot> roots = catalog.activeReferenceRoots("tenant-a")
                .stream()
                .map(root -> new CasGarbageCollector.ReferenceRoot(
                        root.kind(), root.rootId(), root.tenantId(), List.of(root.digest())))
                .toList();
        var collector = new CasGarbageCollector(store, ignored -> Optional.empty(), () -> NOW + 1);
        Map<CasDigest, CasObjectModel.ObjectMetadata> metadata = catalog.load(
                "tenant-a", Set.of(archiveDigest, manifestDigest));

        var whileLive = collector.collect(roots, metadata,
                CasGarbageCollector.CollectionPolicy.dryRun(0).executing(), "while-live");

        assertTrue(whileLive.collected().isEmpty());
        assertEquals(2, whileLive.retained().stream()
                .filter(retained -> retained.reason().equals("REACHABLE")).count());

        artifacts.releaseSnapshot(TENANT_A, "snapshot-live");
        var afterRelease = collector.collect(List.of(), metadata,
                CasGarbageCollector.CollectionPolicy.dryRun(0).executing(), "after-release");
        assertEquals(Set.of(archiveDigest, manifestDigest), afterRelease.collected().stream()
                .map(CasGarbageCollector.Candidate::digest).collect(java.util.stream.Collectors.toSet()));
        assertTrue(store.inventory().isEmpty());
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
}
