package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;

class CasReconcilerTest {

    private final AtomicLong clock = new AtomicLong(5_000_000);
    private final InMemoryCasStore store = new InMemoryCasStore("l2");
    private final Map<CasDigest, CasManifest> manifests = new HashMap<>();
    private final Map<CasDigest, CasObjectModel.ObjectMetadata> catalog = new HashMap<>();

    private CasDigest store(String content) {
        byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(bytes);
        store.put(digest, bytes);
        catalog.put(digest, CasObjectModel.ObjectMetadata.blob("tenant-a", "project-a", "text/plain",
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, "eu-west", 0));
        return digest;
    }

    private CasReconciler reconciler() {
        return new CasReconciler(store, digest -> Optional.ofNullable(manifests.get(digest)));
    }

    @Test void aCleanStoreReportsNothing() {
        CasDigest blob = store("referenced");
        var report = reconciler().reconcile(Map.of("snapshot-1", List.of(blob)), catalog,
                Optional.empty(), 0, clock.get());
        assertTrue(report.clean());
    }

    @Test void aReferencedButAbsentObjectIsReportedWithItsOwner() {
        CasDigest missing = CasDigest.of("gone".getBytes(StandardCharsets.UTF_8));
        var report = reconciler().reconcile(Map.of("evidence-7", List.of(missing)), catalog,
                Optional.empty(), 0, clock.get());
        assertEquals(1, report.missingBlobs().size());
        assertEquals(missing, report.missingBlobs().get(0).digest());
        assertTrue(report.missingBlobs().get(0).detail().contains("evidence-7"));
    }

    @Test void unreferencedObjectsOlderThanTheThresholdAreReportedAsOrphans() {
        CasDigest orphan = store("orphan");
        var young = reconciler().reconcile(Map.of(), catalog, Optional.empty(), 60_000, 30_000);
        assertTrue(young.orphanedObjects().isEmpty());

        var aged = reconciler().reconcile(Map.of(), catalog, Optional.empty(), 60_000, 120_000);
        assertEquals(1, aged.orphanedObjects().size());
        assertEquals(orphan.sizeBytes(), aged.orphanedBytes());
    }

    @Test void aManifestPointingAtMissingContentIsReportedAsDangling() {
        CasDigest present = store("present");
        CasDigest absent = CasDigest.of("absent".getBytes(StandardCharsets.UTF_8));
        var tree = MerkleTree.canonicalize(List.of(new MerkleTree.FileNode("a", present, false)), List.of());
        tree.treeObjects().forEach(object -> {
            store.put(object.digest(), object.bytes());
            catalog.put(object.digest(), CasObjectModel.ObjectMetadata.blob("tenant-a", "project-a",
                    "application/vnd.elmos.tree", CasObjectModel.Sensitivity.GENERATED_OUTPUT, "eu-west", 0));
        });
        CasManifest manifest = CasManifest.output("tenant-a", "project-a", tree, List.of(present, absent));
        manifests.put(manifest.digest(), manifest);

        var report = reconciler().reconcile(Map.of("release-3", List.of(manifest.digest())), catalog,
                Optional.empty(), 0, clock.get());
        assertEquals(1, report.danglingManifests().size());
        assertEquals(1, report.missingBlobs().size());
        assertEquals(absent, report.missingBlobs().get(0).digest());
        assertFalse(report.clean());
    }

    @Test void incompleteUploadSessionsAppearInTheReport() {
        var uploads = new ResumableUploadService(store, clock::get);
        uploads.open("stalled", "tenant-a", 2_000, 1_000, Optional.empty(), 1_000, null);
        clock.addAndGet(10_000);

        var report = reconciler().reconcile(Map.of(), catalog, Optional.of(uploads), 0, clock.get());
        assertEquals(1, report.incompleteUploadSessions().size());
        assertTrue(report.incompleteUploadSessions().get(0).startsWith("stalled:EXPIRED"));
    }
}
