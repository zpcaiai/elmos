package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;

class CasGarbageCollectorTest {

    private final AtomicLong clock = new AtomicLong(10_000_000);
    private final InMemoryCasStore store = new InMemoryCasStore("l2");
    private final Map<CasDigest, CasManifest> manifests = new HashMap<>();
    private final Map<CasDigest, CasObjectModel.ObjectMetadata> catalog = new HashMap<>();

    private CasDigest store(String content, long createdAt, CasObjectModel.RetentionClass retention) {
        byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(bytes);
        store.put(digest, bytes);
        catalog.put(digest, CasObjectModel.ObjectMetadata
                .blob("tenant-a", "project-a", "text/plain", CasObjectModel.Sensitivity.GENERATED_OUTPUT,
                        "eu-west", createdAt)
                .withRetention(retention));
        return digest;
    }

    private CasGarbageCollector collector() {
        return new CasGarbageCollector(store, digest -> Optional.ofNullable(manifests.get(digest)), clock::get);
    }

    @Test void reachableObjectsSurviveAndUnreferencedOnesAreCollected() {
        CasDigest live = store("live blob", 0, CasObjectModel.RetentionClass.STANDARD);
        CasDigest orphan = store("orphan blob", 0, CasObjectModel.RetentionClass.STANDARD);

        var tree = MerkleTree.canonicalize(List.of(new MerkleTree.FileNode("a.txt", live, false)), List.of());
        tree.treeObjects().forEach(object -> store.put(object.digest(), object.bytes()));
        catalog.put(tree.rootDigest(), CasObjectModel.ObjectMetadata.blob("tenant-a", "project-a",
                "application/vnd.elmos.tree", CasObjectModel.Sensitivity.GENERATED_OUTPUT, "eu-west", 0));

        var root = new CasGarbageCollector.ReferenceRoot(CasGarbageCollector.RootKind.SNAPSHOT, "snap-1",
                "tenant-a", List.of(tree.rootDigest()));

        var manifest = collector().collect(List.of(root), catalog,
                CasGarbageCollector.CollectionPolicy.dryRun(0).executing(), "batch-1");

        assertEquals(List.of(orphan), manifest.collected().stream().map(CasGarbageCollector.Candidate::digest).toList());
        assertFalse(store.contains(orphan));
        assertTrue(store.contains(live));
        assertTrue(store.contains(tree.rootDigest()));
        assertEquals(orphan.sizeBytes(), manifest.reclaimedBytes());
    }

    @Test void manifestsExtendReachabilityToEveryObjectTheyName() {
        CasDigest blob = store("referenced by manifest", 0, CasObjectModel.RetentionClass.STANDARD);
        var tree = MerkleTree.canonicalize(List.of(new MerkleTree.FileNode("x", blob, false)), List.of());
        tree.treeObjects().forEach(object -> store.put(object.digest(), object.bytes()));
        catalog.put(tree.rootDigest(), CasObjectModel.ObjectMetadata.blob("tenant-a", "project-a",
                "application/vnd.elmos.tree", CasObjectModel.Sensitivity.GENERATED_OUTPUT, "eu-west", 0));

        CasManifest manifest = CasManifest.output("tenant-a", "project-a", tree, List.of(blob));
        manifests.put(manifest.digest(), manifest);

        var root = new CasGarbageCollector.ReferenceRoot(CasGarbageCollector.RootKind.EVIDENCE, "evidence-1",
                "tenant-a", List.of(manifest.digest()));
        var result = collector().collect(List.of(root), catalog,
                CasGarbageCollector.CollectionPolicy.dryRun(0).executing(), "batch-2");

        assertTrue(result.collected().isEmpty());
        assertTrue(store.contains(blob));
    }

    @Test void dryRunReportsWithoutDeleting() {
        CasDigest orphan = store("orphan", 0, CasObjectModel.RetentionClass.STANDARD);
        var result = collector().collect(List.of(), catalog,
                CasGarbageCollector.CollectionPolicy.dryRun(0), "batch-3");
        assertEquals(1, result.collected().size());
        assertTrue(result.dryRun());
        assertTrue(store.contains(orphan));
    }

    @Test void aNegativeMinimumAgeCannotTurnFreshObjectsIntoDeletionCandidates() {
        assertThrows(IllegalArgumentException.class,
                () -> CasGarbageCollector.CollectionPolicy.dryRun(-1));
    }

    @Test void legalHoldOutranksUnreachabilityAndTenantDeletion() {
        CasDigest held = store("held for litigation", 0, CasObjectModel.RetentionClass.STANDARD);
        var policy = new CasGarbageCollector.CollectionPolicy(false, 0,
                Set.of(CasObjectModel.RetentionClass.STANDARD), Set.of(held), Set.of(), Set.of("tenant-a"));
        var result = collector().collect(List.of(), catalog, policy, "batch-4");
        assertTrue(result.collected().isEmpty());
        assertEquals("LEGAL_HOLD", result.retained().get(0).reason());
        assertTrue(store.contains(held));
    }

    @Test void objectsYoungerThanTheMinimumAgeAreLeftAlone() {
        CasDigest fresh = store("just written", clock.get() - 5_000, CasObjectModel.RetentionClass.STANDARD);
        var result = collector().collect(List.of(), catalog,
                CasGarbageCollector.CollectionPolicy.dryRun(60_000).executing(), "batch-5");
        assertTrue(result.collected().isEmpty());
        assertEquals("YOUNGER_THAN_MINIMUM_AGE", result.retained().get(0).reason());
        assertTrue(store.contains(fresh));
    }

    @Test void retentionClassKeepsEvidenceOutOfReach() {
        CasDigest evidence = store("evidence pack", 0, CasObjectModel.RetentionClass.EVIDENCE);
        var result = collector().collect(List.of(), catalog,
                CasGarbageCollector.CollectionPolicy.dryRun(0).executing(), "batch-6");
        assertTrue(result.collected().isEmpty());
        assertEquals("RETENTION_CLASS:EVIDENCE", result.retained().get(0).reason());
        assertTrue(store.contains(evidence));
    }

    @Test void tenantDeletionOverridesRetentionClassButNotLegalHold() {
        CasDigest evidence = store("evidence pack", 0, CasObjectModel.RetentionClass.EVIDENCE);
        var policy = new CasGarbageCollector.CollectionPolicy(false, 60_000,
                Set.of(CasObjectModel.RetentionClass.STANDARD), Set.of(), Set.of(), Set.of("tenant-a"));
        var result = collector().collect(List.of(), catalog, policy, "batch-7");
        assertEquals("TENANT_DELETION", result.collected().get(0).reason());
        assertFalse(store.contains(evidence));
    }

    @Test void unknownObjectsAreRetainedAndReportedRatherThanCollected() {
        byte[] bytes = "uncatalogued".getBytes(StandardCharsets.UTF_8);
        CasDigest stray = CasDigest.of(bytes);
        store.put(stray, bytes);
        var result = collector().collect(List.of(), catalog,
                CasGarbageCollector.CollectionPolicy.dryRun(0).executing(), "batch-8");
        assertTrue(result.collected().isEmpty());
        assertEquals("UNCATALOGUED", result.retained().get(0).reason());
    }

    @Test void anUnresolvableReferenceBlocksTheWholeSweep() {
        CasDigest missing = CasDigest.of("never stored".getBytes(StandardCharsets.UTF_8));
        CasDigest otherwiseCollectable = store("must survive an incomplete mark", 0,
                CasObjectModel.RetentionClass.STANDARD);
        var root = new CasGarbageCollector.ReferenceRoot(CasGarbageCollector.RootKind.RELEASE, "release-1",
                "tenant-a", List.of(missing));
        var result = collector().collect(List.of(root), catalog,
                CasGarbageCollector.CollectionPolicy.dryRun(0).executing(), "batch-9");
        assertEquals(List.of(missing), result.unresolvedReferences());
        assertTrue(result.collected().isEmpty());
        assertTrue(store.contains(otherwiseCollectable));
        assertEquals("UNRESOLVED_ROOT_GRAPH", result.retained().stream()
                .filter(retained -> retained.digest().equals(otherwiseCollectable))
                .findFirst().orElseThrow().reason());
    }

    @Test void anUnreadableRootIsUnresolvedAndCannotDeleteItsUnknownChildren() {
        CasDigest child = store("child that only the unreadable tree names", 0,
                CasObjectModel.RetentionClass.STANDARD);
        var tree = MerkleTree.canonicalize(
                List.of(new MerkleTree.FileNode("child.txt", child, false)), List.of());
        tree.treeObjects().forEach(object -> store.put(object.digest(), object.bytes()));
        catalog.put(tree.rootDigest(), CasObjectModel.ObjectMetadata.blob("tenant-a", "project-a",
                "application/vnd.elmos.tree", CasObjectModel.Sensitivity.GENERATED_OUTPUT, "eu-west", 0));
        store.corruptForFaultInjection(tree.rootDigest(), "poisoned".getBytes(StandardCharsets.UTF_8));

        var root = new CasGarbageCollector.ReferenceRoot(CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-with-temporary-read-failure", "tenant-a", List.of(tree.rootDigest()));
        var result = collector().collect(List.of(root), catalog,
                CasGarbageCollector.CollectionPolicy.dryRun(0).executing(), "batch-unreadable");

        assertEquals(List.of(tree.rootDigest()), result.unresolvedReferences());
        assertTrue(result.collected().isEmpty());
        assertTrue(store.contains(child));
    }

    @Test void anUnavailableKnownManifestResolverFailsClosedInsteadOfCallingItALeaf() {
        CasDigest manifest = store("manifest bytes whose decoder is temporarily unavailable", 0,
                CasObjectModel.RetentionClass.STANDARD);
        catalog.put(manifest, new CasObjectModel.ObjectMetadata("tenant-a",
                CasObjectModel.ObjectKind.MANIFEST, "application/vnd.elmos.manifest", "test",
                "1.0", CasObjectModel.Sensitivity.GENERATED_OUTPUT,
                CasObjectModel.RetentionClass.STANDARD, "eu-west", Optional.empty(), 0, Map.of()));
        CasDigest possibleChild = store("possible child", 0, CasObjectModel.RetentionClass.STANDARD);
        var root = new CasGarbageCollector.ReferenceRoot(CasGarbageCollector.RootKind.ACTION_CACHE,
                "action-result", "tenant-a", List.of(manifest));

        var result = collector().collect(List.of(root), catalog,
                CasGarbageCollector.CollectionPolicy.dryRun(0).executing(), "batch-resolver-down");

        assertEquals(List.of(manifest), result.unresolvedReferences());
        assertTrue(result.collected().isEmpty());
        assertTrue(store.contains(possibleChild));
    }

    @Test void aResolverCannotSubstituteAnotherManifestForTheRootDigest() {
        CasDigest actualChild = store("actual child", 0, CasObjectModel.RetentionClass.STANDARD);
        CasDigest substitutedChild = store("substituted child", 0,
                CasObjectModel.RetentionClass.STANDARD);
        var actualTree = MerkleTree.canonicalize(
                List.of(new MerkleTree.FileNode("actual", actualChild, false)), List.of());
        var substitutedTree = MerkleTree.canonicalize(
                List.of(new MerkleTree.FileNode("substituted", substitutedChild, false)), List.of());
        CasManifest actual = CasManifest.output("tenant-a", "project-a", actualTree,
                List.of(actualChild));
        CasManifest substituted = CasManifest.output("tenant-a", "project-a", substitutedTree,
                List.of(substitutedChild));
        manifests.put(actual.digest(), substituted);
        var root = new CasGarbageCollector.ReferenceRoot(CasGarbageCollector.RootKind.ACTION_CACHE,
                "action-result-substitution", "tenant-a", List.of(actual.digest()));

        var result = collector().collect(List.of(root), catalog,
                CasGarbageCollector.CollectionPolicy.dryRun(0).executing(), "batch-wrong-manifest");

        assertEquals(List.of(actual.digest()), result.unresolvedReferences());
        assertTrue(result.collected().isEmpty());
        assertTrue(store.contains(actualChild));
        assertTrue(store.contains(substitutedChild));
    }

    @Test void theDeletionManifestIsItselfAddressable() {
        store("orphan", 0, CasObjectModel.RetentionClass.STANDARD);
        var first = collector().collect(List.of(), catalog,
                CasGarbageCollector.CollectionPolicy.dryRun(0), "batch-10");
        var second = collector().collect(List.of(), catalog,
                CasGarbageCollector.CollectionPolicy.dryRun(0), "batch-10");
        assertEquals(first.digest(), second.digest());
    }

    @Test void theDeletionManifestDigestBindsReasonsAndUnresolvedReferences() {
        CasDigest object = CasDigest.of("same-object".getBytes(StandardCharsets.UTF_8));
        var collected = new CasGarbageCollector.DeletionManifest("batch", true,
                List.of(new CasGarbageCollector.Candidate(object, object.sizeBytes(),
                        "tenant-a", "UNREACHABLE")), List.of(), List.of(), object.sizeBytes(), 1);
        var tenantDeletion = new CasGarbageCollector.DeletionManifest("batch", true,
                List.of(new CasGarbageCollector.Candidate(object, object.sizeBytes(),
                        "tenant-a", "TENANT_DELETION")), List.of(), List.of(), object.sizeBytes(), 1);
        var unresolved = new CasGarbageCollector.DeletionManifest("batch", true,
                List.of(new CasGarbageCollector.Candidate(object, object.sizeBytes(),
                        "tenant-a", "UNREACHABLE")), List.of(), List.of(object), object.sizeBytes(), 1);

        assertNotEquals(collected.digest(), tenantDeletion.digest());
        assertNotEquals(collected.digest(), unresolved.digest());
    }
}
