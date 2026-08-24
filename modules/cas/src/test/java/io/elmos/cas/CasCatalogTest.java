package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.lang.reflect.Modifier;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Contract for {@link CasCatalog}. Exercised here against {@link InMemoryCasCatalog}; the JDBC
 * implementation is held to the same contract by `JdbcCasCatalogLiveTest` in `modules/persistence`,
 * which needs a real PostgreSQL and therefore Docker.
 */
class CasCatalogTest {

    private final InMemoryCasCatalog catalog = new InMemoryCasCatalog();

    @Test
    void everyInMemoryCatalogOperationUsesTheSameObjectLock() throws Exception {
        for (var contractMethod : CasCatalog.class.getDeclaredMethods()) {
            var implementation = InMemoryCasCatalog.class.getMethod(
                    contractMethod.getName(), contractMethod.getParameterTypes());
            assertTrue(Modifier.isSynchronized(implementation.getModifiers()),
                    () -> implementation.getName() + " must serialize compound catalog state");
        }
    }

    private static CasDigest digest(String text) {
        return CasDigest.of(text.getBytes(StandardCharsets.UTF_8));
    }

    private static CasCatalog.CatalogEntry entry(String tenant, CasDigest digest,
                                                 CasObjectModel.Sensitivity sensitivity,
                                                 Optional<CasDigest> provenance) {
        return new CasCatalog.CatalogEntry(tenant, digest, CasObjectModel.ObjectKind.BLOB,
                "application/octet-stream", "elmos", "1.0", sensitivity,
                CasObjectModel.RetentionClass.STANDARD, "eu-west",
                CasAccessPolicy.SecurityTier.INTERNAL, provenance, Map.of(), false, 1_800_000_000_000L);
    }

    @Test void anEntryRoundTripsAndProducesTheSameMetadataTheStoreUses() {
        CasDigest object = digest("payload");
        CasDigest provenance = digest("provenance with an exact nonzero size");
        CasCatalog.CatalogEntry intended = new CasCatalog.CatalogEntry("tenant-a", object,
                CasObjectModel.ObjectKind.MANIFEST, "application/vnd.elmos.manifest+json",
                "snapshot-service", "2.7", CasObjectModel.Sensitivity.GENERATED_OUTPUT,
                CasObjectModel.RetentionClass.EVIDENCE, "eu-west",
                CasAccessPolicy.SecurityTier.CONFIDENTIAL, Optional.of(provenance),
                Map.of("repository", "repo-a", "format", "tar+zstd"), true,
                1_800_000_000_000L);
        catalog.record(intended);

        var found = catalog.find("tenant-a", object).orElseThrow();
        assertEquals(intended, found);
        assertEquals(provenance, found.provenanceDigest().orElseThrow());
        assertEquals(Map.of("repository", "repo-a", "format", "tar+zstd"), found.labels());
        var metadata = found.metadata();
        assertEquals(CasObjectModel.Sensitivity.GENERATED_OUTPUT, metadata.sensitivity());
        assertEquals("eu-west", metadata.dataResidency());
        assertEquals(1_800_000_000_000L, metadata.createdAtEpochMillis());
    }

    @Test void oneTenantCannotSeeAnothersCatalogueRowForTheSameContent() {
        CasDigest shared = digest("byte identical");
        catalog.record(entry("tenant-a", shared, CasObjectModel.Sensitivity.PRIVATE_SOURCE, Optional.empty()));
        assertTrue(catalog.find("tenant-b", shared).isEmpty());

        catalog.record(entry("tenant-b", shared, CasObjectModel.Sensitivity.PRIVATE_SOURCE, Optional.empty()));
        assertEquals(2, catalog.load("tenant-a", Set.of(shared)).size()
                + catalog.load("tenant-b", Set.of(shared)).size());
    }

    @Test void aTenantCannotRebindAnExistingDigestToDifferentObjectMetadata() {
        CasDigest shared = digest("same tenant bytes");
        CasCatalog.CatalogEntry original = entry("tenant-a", shared,
                CasObjectModel.Sensitivity.PRIVATE_SOURCE, Optional.empty());
        catalog.record(original);
        CasCatalog.CatalogEntry conflicting = new CasCatalog.CatalogEntry(
                "tenant-a", shared, CasObjectModel.ObjectKind.TREE, original.mediaType(),
                original.sourceSystem(), original.schemaVersion(), original.sensitivity(),
                original.retentionClass(), original.dataResidency(), original.securityTier(),
                original.provenanceDigest(), original.labels(), original.legalHold(),
                original.createdAtEpochMillis());

        assertThrows(IllegalStateException.class, () -> catalog.record(conflicting));
        assertEquals(CasObjectModel.ObjectKind.BLOB,
                catalog.find("tenant-a", shared).orElseThrow().kind());
    }

    @Test void oneObjectCanBeBoundToMultipleRepositoriesWithoutSharingTheirAuthorization() {
        CasDigest shared = digest("same bytes used by two repositories");
        catalog.record(entry("tenant-a", shared,
                CasObjectModel.Sensitivity.PRIVATE_SOURCE, Optional.empty()));
        catalog.bindResource(new CasCatalog.ResourceBinding("tenant-a",
                CasCatalog.ResourceKind.REPOSITORY, "repo-a", shared, 1_800_000_000_000L));
        catalog.bindResource(new CasCatalog.ResourceBinding("tenant-a",
                CasCatalog.ResourceKind.REPOSITORY, "repo-b", shared, 1_800_000_000_001L));

        assertTrue(catalog.findBound("tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "repo-a", shared).isPresent());
        assertTrue(catalog.findBound("tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "repo-b", shared).isPresent());
        assertTrue(catalog.findBound("tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "repo-c", shared).isEmpty());
        assertTrue(catalog.findBound("tenant-b", CasCatalog.ResourceKind.REPOSITORY,
                "repo-a", shared).isEmpty());

        catalog.releaseResource("tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "repo-a", shared, 1_800_000_100_000L);
        assertTrue(catalog.findBound("tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "repo-a", shared).isEmpty());
        assertTrue(catalog.findBound("tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "repo-b", shared).isPresent());
        assertEquals(List.of("repo-b"), catalog.activeResourceBindings("tenant-a",
                        CasCatalog.ResourceKind.REPOSITORY, "repo-b").stream()
                .map(CasCatalog.ResourceBinding::resourceId).toList());
    }

    @SuppressWarnings("deprecation")
    @Test void theLegacyProjectConstructorDoesNotManufactureAResourceBinding() {
        CasDigest object = digest("legacy constructor object");
        CasCatalog.CatalogEntry legacy = new CasCatalog.CatalogEntry("tenant-a", object,
                "project-a", CasObjectModel.ObjectKind.BLOB, "application/octet-stream",
                "legacy", "1.0", CasObjectModel.Sensitivity.PRIVATE_SOURCE,
                CasObjectModel.RetentionClass.STANDARD, "eu-west",
                CasAccessPolicy.SecurityTier.INTERNAL, Optional.empty(), Map.of(), false,
                1_800_000_000_000L);

        catalog.record(legacy);

        assertTrue(catalog.find("tenant-a", object).isPresent());
        assertTrue(catalog.findBound("tenant-a", CasCatalog.ResourceKind.PROJECT,
                "project-a", object).isEmpty());
    }

    @Test void resourceBindingRequiresTheExactKnownDigestIncludingSize() {
        CasDigest object = digest("sized object");
        catalog.record(entry("tenant-a", object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));
        CasDigest wrongSize = new CasDigest(object.algorithm(), object.hex(), object.sizeBytes() + 1);

        assertThrows(CasExceptions.CasNotFoundException.class,
                () -> catalog.bindResource(new CasCatalog.ResourceBinding("tenant-a",
                        CasCatalog.ResourceKind.REPOSITORY, "repo-a", wrongSize,
                        1_800_000_000_000L)));
        assertTrue(catalog.find("tenant-a", wrongSize).isEmpty());
        assertThrows(IllegalArgumentException.class,
                () -> new CasCatalog.ResourceBinding("tenant-a\0tenant-b",
                        CasCatalog.ResourceKind.REPOSITORY, "repo-a", object,
                        1_800_000_000_000L));
    }

    @Test void activeBindingRetriesAreIdempotentButAReleasedBindingGetsANewEpoch() {
        CasDigest object = digest("binding epoch");
        catalog.record(entry("tenant-a", object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));
        catalog.bindResource(new CasCatalog.ResourceBinding("tenant-a",
                CasCatalog.ResourceKind.REPOSITORY, "repo-a", object, 100L));
        catalog.bindResource(new CasCatalog.ResourceBinding("tenant-a",
                CasCatalog.ResourceKind.REPOSITORY, "repo-a", object, 200L));
        assertEquals(100L, catalog.activeResourceBindings("tenant-a",
                CasCatalog.ResourceKind.REPOSITORY, "repo-a").get(0).boundAtEpochMillis());

        catalog.releaseResource("tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "repo-a", object, 150L);
        catalog.bindResource(new CasCatalog.ResourceBinding("tenant-a",
                CasCatalog.ResourceKind.REPOSITORY, "repo-a", object, 200L));
        assertEquals(200L, catalog.activeResourceBindings("tenant-a",
                CasCatalog.ResourceKind.REPOSITORY, "repo-a").get(0).boundAtEpochMillis());
    }

    @Test void shareableContentWithoutProvenanceCannotBeCatalogued() {
        var error = assertThrows(IllegalArgumentException.class,
                () -> entry("tenant-a", digest("jar"), CasObjectModel.Sensitivity.PUBLIC_DEPENDENCY,
                        Optional.empty()));
        assertTrue(error.getMessage().contains("provenance"));
    }

    @Test void bulkLoadReturnsOnlyWhatIsCatalogued() {
        CasDigest known = digest("known");
        CasDigest unknown = digest("unknown");
        catalog.record(entry("tenant-a", known, CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));

        var loaded = catalog.load("tenant-a", Set.of(known, unknown));
        assertEquals(1, loaded.size());
        assertTrue(loaded.containsKey(known));
    }

    @Test void anObjectCanHaveOnlyOnePrimaryRegion() {
        CasDigest object = digest("placed");
        catalog.record(entry("tenant-a", object, CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));
        catalog.placeObject(new CasCatalog.Placement("tenant-a", object, "eu-west-1",
                CasCatalog.PlacementRole.PRIMARY, "L2"));
        catalog.placeObject(new CasCatalog.Placement("tenant-a", object, "eu-central-1",
                CasCatalog.PlacementRole.REPLICA, "L2"));

        assertEquals(2, catalog.placements("tenant-a", object).size());
        var error = assertThrows(IllegalStateException.class,
                () -> catalog.placeObject(new CasCatalog.Placement("tenant-a", object, "us-east-1",
                        CasCatalog.PlacementRole.PRIMARY, "L2")));
        assertTrue(error.getMessage().contains("primary"));
    }

    @Test void anUncataloguedObjectCannotBePlaced() {
        assertThrows(IllegalStateException.class,
                () -> catalog.placeObject(new CasCatalog.Placement("tenant-a", digest("ghost"), "eu-west-1",
                        CasCatalog.PlacementRole.PRIMARY, "L2")));
    }

    @Test void placementAndLegalHoldRequireTheExactCataloguedSize() {
        CasDigest object = digest("exact placement");
        catalog.record(entry("tenant-a", object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));
        CasDigest wrongSize = new CasDigest(object.algorithm(), object.hex(), object.sizeBytes() + 1);

        assertThrows(IllegalStateException.class,
                () -> catalog.placeObject(new CasCatalog.Placement("tenant-a", wrongSize,
                        "eu-west-1", CasCatalog.PlacementRole.PRIMARY, "L2")));
        assertTrue(catalog.placements("tenant-a", wrongSize).isEmpty());
        assertThrows(CasExceptions.CasNotFoundException.class,
                () -> catalog.setLegalHold("tenant-a", wrongSize, true));
        assertFalse(catalog.find("tenant-a", object).orElseThrow().legalHold());
    }

    @Test void referenceRootsAreActiveUntilReleased() {
        CasDigest object = digest("referenced");
        catalog.addReferenceRoot(new CasCatalog.ReferenceRoot("tenant-a",
                CasGarbageCollector.RootKind.SNAPSHOT, "snap-1", object, 1_800_000_000_000L));
        catalog.addReferenceRoot(new CasCatalog.ReferenceRoot("tenant-a",
                CasGarbageCollector.RootKind.EVIDENCE, "ev-1", object, 1_800_000_000_000L));
        catalog.addReferenceRoot(new CasCatalog.ReferenceRoot("tenant-a",
                CasGarbageCollector.RootKind.SNAPSHOT, "snap-10", object, 1_800_000_000_000L));
        assertEquals(3, catalog.activeReferenceRoots("tenant-a").size());

        catalog.releaseReferenceRoot("tenant-a", CasGarbageCollector.RootKind.SNAPSHOT, "snap-1",
                1_800_000_100_000L);
        List<CasCatalog.ReferenceRoot> active = catalog.activeReferenceRoots("tenant-a");
        assertEquals(2, active.size());
        assertTrue(active.stream().anyMatch(root -> root.rootId().equals("snap-10")),
                "releasing snap-1 must not prefix-match snap-10");
        assertTrue(active.stream().anyMatch(root -> root.kind() == CasGarbageCollector.RootKind.EVIDENCE));
        assertTrue(catalog.activeReferenceRoots("tenant-b").isEmpty());
    }

    @Test void referenceRootBatchRepairsASubsetAtomicallyButRefusesUnexpectedActiveDigests() {
        CasDigest first = digest("root-a");
        CasDigest second = digest("root-b");
        CasDigest conflicting = digest("root-c");
        CasCatalog.ReferenceRoot rootA = new CasCatalog.ReferenceRoot("tenant-a",
                CasGarbageCollector.RootKind.SNAPSHOT, "snap-batch", first,
                1_800_000_000_000L);
        CasCatalog.ReferenceRoot rootB = new CasCatalog.ReferenceRoot("tenant-a",
                CasGarbageCollector.RootKind.SNAPSHOT, "snap-batch", second,
                1_800_000_000_001L);
        CasCatalog.ReferenceRoot rootC = new CasCatalog.ReferenceRoot("tenant-a",
                CasGarbageCollector.RootKind.SNAPSHOT, "snap-batch", conflicting,
                1_800_000_000_002L);

        catalog.addReferenceRoot(rootA);
        catalog.addReferenceRoots(List.of(rootA, rootB));
        assertEquals(Set.of(first, second), catalog.activeReferenceRoots("tenant-a").stream()
                .filter(root -> root.rootId().equals("snap-batch"))
                .map(CasCatalog.ReferenceRoot::digest).collect(java.util.stream.Collectors.toSet()));

        assertThrows(IllegalStateException.class,
                () -> catalog.addReferenceRoots(List.of(rootA, rootC)));
        assertEquals(Set.of(first, second), catalog.activeReferenceRoots("tenant-a").stream()
                .filter(root -> root.rootId().equals("snap-batch"))
                .map(CasCatalog.ReferenceRoot::digest).collect(java.util.stream.Collectors.toSet()));
    }

    @Test void aMixedIdentityReferenceRootBatchHasNoSideEffects() {
        CasCatalog.ReferenceRoot tenantA = new CasCatalog.ReferenceRoot("tenant-a",
                CasGarbageCollector.RootKind.SNAPSHOT, "snap-mixed", digest("a"),
                1_800_000_000_000L);
        CasCatalog.ReferenceRoot tenantB = new CasCatalog.ReferenceRoot("tenant-b",
                CasGarbageCollector.RootKind.SNAPSHOT, "snap-mixed", digest("b"),
                1_800_000_000_000L);

        assertThrows(IllegalArgumentException.class,
                () -> catalog.addReferenceRoots(List.of(tenantA, tenantB)));
        assertTrue(catalog.activeReferenceRoots("tenant-a").isEmpty());
        assertTrue(catalog.activeReferenceRoots("tenant-b").isEmpty());
    }

    @Test void releaseBeforeAnyRootCreationFailsWithoutHidingTheOlderRoots() {
        CasCatalog.ReferenceRoot older = new CasCatalog.ReferenceRoot("tenant-a",
                CasGarbageCollector.RootKind.SNAPSHOT, "snap-time", digest("older"), 100L);
        CasCatalog.ReferenceRoot newer = new CasCatalog.ReferenceRoot("tenant-a",
                CasGarbageCollector.RootKind.SNAPSHOT, "snap-time", digest("newer"), 200L);
        catalog.addReferenceRoots(List.of(older, newer));

        assertThrows(IllegalArgumentException.class,
                () -> catalog.releaseReferenceRoot("tenant-a",
                        CasGarbageCollector.RootKind.SNAPSHOT, "snap-time", 150L));
        assertEquals(2, catalog.activeReferenceRoots("tenant-a").size(),
                "the release batch must be all-or-none when one root is newer");

        catalog.releaseReferenceRoot("tenant-a",
                CasGarbageCollector.RootKind.SNAPSHOT, "snap-time", 200L);
        assertTrue(catalog.activeReferenceRoots("tenant-a").isEmpty());
    }

    @Test void reactivatedRootRejectsADelayedReleaseFromItsPriorGeneration() {
        CasDigest object = digest("reactivated-root");
        CasGarbageCollector.RootKind kind = CasGarbageCollector.RootKind.SNAPSHOT;
        catalog.addReferenceRoot(new CasCatalog.ReferenceRoot(
                "tenant-a", kind, "snap-reactivated", object, 100L));
        catalog.releaseReferenceRoot("tenant-a", kind, "snap-reactivated", 200L);
        catalog.addReferenceRoot(new CasCatalog.ReferenceRoot(
                "tenant-a", kind, "snap-reactivated", object, 300L));

        assertThrows(IllegalArgumentException.class,
                () -> catalog.releaseReferenceRoot(
                        "tenant-a", kind, "snap-reactivated", 250L));
        CasCatalog.ReferenceRoot active = catalog.activeReferenceRoots("tenant-a").stream()
                .filter(root -> root.rootId().equals("snap-reactivated"))
                .findFirst().orElseThrow();
        assertEquals(300L, active.createdAtEpochMillis());
    }

    @Test void reactivatedRootAdvancesPastHistoryWhenCallerClockMovesBackwards() {
        CasDigest object = digest("clock-regressed-root");
        CasGarbageCollector.RootKind kind = CasGarbageCollector.RootKind.SNAPSHOT;
        long first = catalog.addReferenceRoots(List.of(new CasCatalog.ReferenceRoot(
                "tenant-a", kind, "snap-clock-regressed", object, 500L)));
        catalog.releaseReferenceRoot(
                "tenant-a", kind, "snap-clock-regressed", first);

        long reactivated = catalog.addReferenceRoots(List.of(new CasCatalog.ReferenceRoot(
                "tenant-a", kind, "snap-clock-regressed", object, 100L)));

        assertEquals(501L, reactivated);
        assertThrows(IllegalArgumentException.class, () -> catalog.releaseReferenceRoot(
                "tenant-a", kind, "snap-clock-regressed", first));
        assertEquals(reactivated, catalog.activeReferenceRoots("tenant-a").stream()
                .filter(root -> root.rootId().equals("snap-clock-regressed"))
                .findFirst().orElseThrow().createdAtEpochMillis());
    }

    @Test void legalHoldIsRecordedAgainstAKnownObjectOnly() {
        CasDigest object = digest("held");
        catalog.record(entry("tenant-a", object, CasObjectModel.Sensitivity.EVIDENCE, Optional.empty()));
        catalog.setLegalHold("tenant-a", object, true);
        assertTrue(catalog.find("tenant-a", object).orElseThrow().legalHold());
        assertTrue(catalog.load("tenant-a", Set.of(object)).get(object).legalHold(),
                "the collector view must preserve the authoritative legal hold");
        catalog.record(entry("tenant-a", object,
                CasObjectModel.Sensitivity.EVIDENCE, Optional.empty()));
        assertTrue(catalog.find("tenant-a", object).orElseThrow().legalHold(),
                "an idempotent write from another binding must not clear a legal hold");
        catalog.setLegalHold("tenant-a", object, false);
        assertFalse(catalog.find("tenant-a", object).orElseThrow().legalHold());

        assertThrows(CasExceptions.CasNotFoundException.class,
                () -> catalog.setLegalHold("tenant-a", digest("never stored"), true));
    }

    @Test void aSecondBindingCannotDowngradeTenantObjectRetention() {
        CasDigest object = digest("regulated object");
        CasCatalog.CatalogEntry standard = entry("tenant-a", object,
                CasObjectModel.Sensitivity.EVIDENCE, Optional.empty());
        CasCatalog.CatalogEntry regulatory = new CasCatalog.CatalogEntry(
                standard.tenantId(), standard.digest(), standard.kind(), standard.mediaType(),
                standard.sourceSystem(), standard.schemaVersion(), standard.sensitivity(),
                CasObjectModel.RetentionClass.REGULATORY, standard.dataResidency(),
                standard.securityTier(), standard.provenanceDigest(), standard.labels(),
                standard.legalHold(), standard.createdAtEpochMillis());

        catalog.record(regulatory);
        catalog.record(standard);

        assertEquals(CasObjectModel.RetentionClass.REGULATORY,
                catalog.find("tenant-a", object).orElseThrow().retentionClass());
    }

    @Test void deletionManifestsAndQuarantinesAreAppendOnly() {
        var manifest = new CasGarbageCollector.DeletionManifest("batch-1", false, List.of(), List.of(),
                List.of(), 0, 1_800_000_000_000L);
        catalog.recordDeletionManifest("tenant-a", manifest, "gc");
        assertEquals(List.of("batch-1"), catalog.deletionBatchIds("tenant-a"));
        assertThrows(IllegalStateException.class,
                () -> catalog.recordDeletionManifest("tenant-a", manifest, "gc"));

        catalog.recordQuarantine("tenant-a", "q-1", "OBJECT", digest("bad").hex(),
                Optional.of(digest("bad")), Optional.of(digest("worse")), "digest mismatch",
                1_800_000_000_000L);
        assertEquals(1, catalog.quarantineCount("tenant-a"));
        assertThrows(IllegalStateException.class,
                () -> catalog.recordQuarantine("tenant-a", "q-1", "OBJECT", digest("bad").hex(),
                        Optional.of(digest("bad")), Optional.of(digest("worse")), "again",
                        1_800_000_000_000L));
    }

    @Test void aContentQuarantineWithoutBothDigestsIsRefusedButANodeOneIsNot() {
        assertThrows(IllegalArgumentException.class,
                () -> catalog.recordQuarantine("tenant-a", "q-2", "OBJECT", "subject",
                        Optional.of(digest("declared")), Optional.empty(), "half a record",
                        1_800_000_000_000L));
        catalog.recordQuarantine("tenant-a", "q-3", "NODE", "ns/runners/sa/n1",
                Optional.empty(), Optional.empty(), "nondeterministic output", 1_800_000_000_000L);
        assertEquals(1, catalog.quarantineCount("tenant-a"));
    }

    @Test void theCatalogueFeedsTheCollectorsSweep() {
        InMemoryCasStore store = new InMemoryCasStore("l2");
        CasDigest live = digest("live");
        CasDigest orphan = digest("orphan");
        CasDigest held = digest("held during tenant deletion");
        store.put(live, "live".getBytes(StandardCharsets.UTF_8));
        store.put(orphan, "orphan".getBytes(StandardCharsets.UTF_8));
        store.put(held, "held during tenant deletion".getBytes(StandardCharsets.UTF_8));
        catalog.record(entry("tenant-a", live, CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));
        catalog.record(entry("tenant-a", orphan, CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));
        catalog.record(entry("tenant-a", held, CasObjectModel.Sensitivity.EVIDENCE, Optional.empty()));
        catalog.setLegalHold("tenant-a", held, true);
        catalog.addReferenceRoot(new CasCatalog.ReferenceRoot("tenant-a",
                CasGarbageCollector.RootKind.SNAPSHOT, "snap-1", live, 1_800_000_000_000L));

        var roots = catalog.activeReferenceRoots("tenant-a").stream()
                .map(root -> new CasGarbageCollector.ReferenceRoot(root.kind(), root.rootId(),
                        root.tenantId(), List.of(root.digest())))
                .toList();
        var collector = new CasGarbageCollector(store, ignored -> Optional.empty(),
                () -> 1_900_000_000_000L);
        var deletionPolicy = new CasGarbageCollector.CollectionPolicy(false, 0,
                Set.of(CasObjectModel.RetentionClass.STANDARD), Set.of(), Set.of(),
                Set.of("tenant-a"));
        var manifest = collector.collect(roots, catalog.load("tenant-a", store.inventory()),
                deletionPolicy, "batch-9");

        assertEquals(List.of(orphan),
                manifest.collected().stream().map(CasGarbageCollector.Candidate::digest).toList());
        assertTrue(store.contains(live));
        assertFalse(store.contains(orphan));
        assertTrue(store.contains(held));
        assertEquals("LEGAL_HOLD", manifest.retained().stream()
                .filter(retained -> retained.digest().equals(held))
                .findFirst().orElseThrow().reason());

        catalog.recordDeletionManifest("tenant-a", manifest, "gc");
        assertEquals(List.of("batch-9"), catalog.deletionBatchIds("tenant-a"));
    }
}
