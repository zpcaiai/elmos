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
import java.util.List;

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
        compatible.retainSnapshot(RESOURCE, "snapshot-before-rollback", List.of(casReference));
        assertEquals(1, backends.catalog().activeReferenceRoots("tenant-a").size());

        compatible.releaseSnapshot(RESOURCE, "snapshot-before-rollback");
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
}
