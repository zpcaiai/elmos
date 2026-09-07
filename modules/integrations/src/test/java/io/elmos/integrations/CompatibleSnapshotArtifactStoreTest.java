package io.elmos.integrations;

import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.CasDigest;
import io.elmos.cas.InMemoryCasCatalog;
import io.elmos.cas.InMemoryCasStore;
import io.elmos.snapshot.SnapshotPorts;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CompatibleSnapshotArtifactStoreTest {

    private static final long NOW = 1_800_000_000_000L;
    private static final SnapshotPorts.ArtifactResourceContext RESOURCE =
            new SnapshotPorts.ArtifactResourceContext("tenant-a", "repository-a");

    @TempDir
    Path temporary;

    @Test void casWriterModeStillReadsVerifiedLegacyReferences() throws Exception {
        Backends backends = backends();
        byte[] content = bytes("snapshot written before CAS rollout");
        CasDigest digest = CasDigest.of(content);
        String legacyReference = backends.legacy().putIfAbsent(
                RESOURCE, digest.hex(), content.length,
                new ByteArrayInputStream(content), "application/zstd");
        var compatible = backends.compatible(CompatibleSnapshotArtifactStore.WriterMode.CAS);

        assertArrayEquals(content, compatible.open(RESOURCE, legacyReference).readAllBytes());
        String newReference = compatible.putIfAbsent(
                RESOURCE, digest.hex(), content.length,
                new ByteArrayInputStream(content), "application/zstd");
        assertTrue(newReference.startsWith(CasBackedArtifactStore.SCHEME));
    }

    @Test void rollbackWriterModeStillReadsAndRetainsCasReferences() throws Exception {
        Backends backends = backends();
        byte[] content = bytes("snapshot written while CAS was enabled");
        CasDigest digest = CasDigest.of(content);
        String casReference = backends.cas().putIfAbsent(
                RESOURCE, digest.hex(), content.length,
                new ByteArrayInputStream(content), "application/zstd");
        var compatible = backends.compatible(CompatibleSnapshotArtifactStore.WriterMode.LEGACY);

        assertArrayEquals(content, compatible.open(RESOURCE, casReference).readAllBytes());
        SnapshotPorts.ArtifactRetention retention = compatible.retainSnapshotGeneration(
                RESOURCE, "snapshot-before-rollback", List.of(casReference));
        assertEquals(1, backends.catalog().activeReferenceRoots("tenant-a").size());

        assertThrows(UnsupportedOperationException.class,
                () -> compatible.releaseSnapshot(RESOURCE, "snapshot-before-rollback"));
        compatible.releaseSnapshotGeneration(RESOURCE, retention);
        assertTrue(backends.catalog().activeReferenceRoots("tenant-a").isEmpty());

        String newReference = compatible.putIfAbsent(
                RESOURCE, digest.hex(), content.length,
                new ByteArrayInputStream(content), "application/zstd");
        assertTrue(newReference.startsWith("cas:sha256:"));
    }

    @Test void malformedMixedRetentionBatchHasNoLifecycleSideEffects() {
        Backends backends = backends();
        byte[] content = bytes("valid content");
        CasDigest digest = CasDigest.of(content);
        String casReference = backends.cas().putIfAbsent(
                RESOURCE, digest.hex(), content.length,
                new ByteArrayInputStream(content), "application/zstd");
        var compatible = backends.compatible(CompatibleSnapshotArtifactStore.WriterMode.CAS);

        assertThrows(IllegalArgumentException.class, () -> compatible.retainSnapshot(
                RESOURCE, "snapshot-invalid", List.of(casReference, "file:///tmp/escape")));
        assertTrue(backends.catalog().activeReferenceRoots("tenant-a").isEmpty());
    }

    @Test void conflictingRetryNeverReleasesAPreExistingCasRoot() {
        Backends backends = backends();
        byte[] archive = bytes("existing archive root");
        byte[] manifest = bytes("existing manifest root");
        CasDigest archiveDigest = CasDigest.of(archive);
        CasDigest manifestDigest = CasDigest.of(manifest);
        String archiveReference = backends.cas().putIfAbsent(
                RESOURCE, archiveDigest.hex(), archive.length,
                new ByteArrayInputStream(archive), "application/zstd");
        String manifestReference = backends.cas().putIfAbsent(
                RESOURCE, manifestDigest.hex(), manifest.length,
                new ByteArrayInputStream(manifest), "application/json");
        backends.cas().retainSnapshot(RESOURCE, "snapshot-existing",
                List.of(archiveReference, manifestReference));
        var compatible = backends.compatible(CompatibleSnapshotArtifactStore.WriterMode.CAS);

        assertThrows(IllegalStateException.class, () -> compatible.retainSnapshot(
                RESOURCE, "snapshot-existing", List.of(archiveReference)));

        assertEquals(2, backends.catalog().activeReferenceRoots("tenant-a").size());
    }

    @Test void generationReleaseDispatchesOnlyToParticipatingBackends() {
        StrictLifecycleStore legacy = new StrictLifecycleStore("test.legacy");
        StrictLifecycleStore cas = new StrictLifecycleStore("test.cas");
        var compatible = new CompatibleSnapshotArtifactStore(
                CompatibleSnapshotArtifactStore.WriterMode.CAS,
                legacy, legacy, cas, cas);
        String legacyReference = "cas:sha256:" + "a".repeat(64);
        String casReference = "cas://sha256/" + "b".repeat(64) + "/10";

        SnapshotPorts.ArtifactRetention legacyOnly =
                compatible.retainSnapshotGeneration(
                        RESOURCE, "snapshot-legacy", List.of(legacyReference));
        compatible.releaseSnapshotGeneration(RESOURCE, legacyOnly);
        compatible.releaseSnapshotGeneration(RESOURCE, legacyOnly);
        assertEquals(List.of("snapshot-legacy", "snapshot-legacy"), legacy.released);
        assertTrue(cas.released.isEmpty());

        SnapshotPorts.ArtifactRetention casOnly =
                compatible.retainSnapshotGeneration(
                        RESOURCE, "snapshot-cas", List.of(casReference));
        compatible.releaseSnapshotGeneration(RESOURCE, casOnly);
        compatible.releaseSnapshotGeneration(RESOURCE, casOnly);
        assertEquals(List.of("snapshot-cas", "snapshot-cas"), cas.released);
        assertEquals(List.of("snapshot-legacy", "snapshot-legacy"), legacy.released);

        SnapshotPorts.ArtifactRetention mixed =
                compatible.retainSnapshotGeneration(
                        RESOURCE, "snapshot-mixed",
                        List.of(legacyReference, casReference));
        compatible.releaseSnapshotGeneration(RESOURCE, mixed);
        compatible.releaseSnapshotGeneration(RESOURCE, mixed);
        assertEquals(List.of("snapshot-legacy", "snapshot-legacy",
                "snapshot-mixed", "snapshot-mixed"), legacy.released);
        assertEquals(List.of("snapshot-cas", "snapshot-cas",
                "snapshot-mixed", "snapshot-mixed"), cas.released);
    }

    @Test void rejectsNonCanonicalSnapshotIdBeforeDispatchingToEitherBackend() {
        StrictLifecycleStore legacy = new StrictLifecycleStore("test.legacy");
        StrictLifecycleStore cas = new StrictLifecycleStore("test.cas");
        var compatible = new CompatibleSnapshotArtifactStore(
                CompatibleSnapshotArtifactStore.WriterMode.CAS,
                legacy, legacy, cas, cas);
        String legacyReference = "cas:sha256:" + "a".repeat(64);
        String casReference = "cas://sha256/" + "b".repeat(64) + "/10";

        assertThrows(IllegalArgumentException.class,
                () -> compatible.retainSnapshotGeneration(
                        RESOURCE, "s".repeat(65), List.of(legacyReference, casReference)));

        assertTrue(legacy.retained.isEmpty());
        assertTrue(cas.retained.isEmpty());
        assertTrue(legacy.released.isEmpty());
        assertTrue(cas.released.isEmpty());
    }

    private Backends backends() {
        var legacy = new LocalContentAddressedArtifactStore(
                temporary.resolve("legacy"), 64L * 1024 * 1024);
        var store = new InMemoryCasStore("snapshot-cas");
        var catalog = new InMemoryCasCatalog();
        var cas = new CasBackedArtifactStore(
                store, catalog, "cn-east",
                CasAccessPolicy.SecurityTier.CONFIDENTIAL,
                64L * 1024 * 1024, () -> NOW);
        return new Backends(legacy, cas, catalog);
    }

    private static byte[] bytes(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    private record Backends(
            LocalContentAddressedArtifactStore legacy,
            CasBackedArtifactStore cas,
            InMemoryCasCatalog catalog
    ) {
        CompatibleSnapshotArtifactStore compatible(
                CompatibleSnapshotArtifactStore.WriterMode mode) {
            return new CompatibleSnapshotArtifactStore(mode, legacy, legacy, cas, cas);
        }
    }

    private static final class StrictLifecycleStore implements
            SnapshotPorts.ArtifactStore, SnapshotPorts.ArtifactReader {
        private final String generationName;
        private final List<String> retained = new ArrayList<>();
        private final List<String> released = new ArrayList<>();
        private StrictLifecycleStore(String generationName) {
            this.generationName = generationName;
        }
        @Override public String putIfAbsent(SnapshotPorts.ArtifactResourceContext resource,
                String sha256, long size, java.io.InputStream content, String mediaType) {
            throw new UnsupportedOperationException();
        }
        @Override public java.io.InputStream open(
                SnapshotPorts.ArtifactResourceContext resource, String reference) {
            throw new UnsupportedOperationException();
        }
        @Override public SnapshotPorts.ArtifactRetention retainSnapshotGeneration(
                SnapshotPorts.ArtifactResourceContext resource, String snapshotId,
                List<String> references) {
            retained.add(snapshotId);
            return new SnapshotPorts.ArtifactRetention(
                    snapshotId, Map.of(generationName, 1L));
        }
        @Override public void releaseSnapshotGeneration(
                SnapshotPorts.ArtifactResourceContext resource,
                SnapshotPorts.ArtifactRetention retention) {
            retention.requireGeneration(generationName);
            released.add(retention.snapshotId());
        }
    }
}
