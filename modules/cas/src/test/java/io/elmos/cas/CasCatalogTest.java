package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.lang.reflect.Modifier;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

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
            if (!Modifier.isPublic(contractMethod.getModifiers())
                    || contractMethod.isSynthetic()) {
                continue;
            }
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

    private static TenantCasStore tenantIsolated(CasStore store) {
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

    @Test void exactLogicalRootLookupDoesNotReturnUnrelatedTenantRoots() {
        CasDigest selected = digest("selected cache result");
        catalog.addReferenceRoot(new CasCatalog.ReferenceRoot(
                "tenant-a", CasGarbageCollector.RootKind.ACTION_CACHE,
                "cache-selected", selected, 1_800_000_000_000L));
        for (int index = 0; index < 100; index++) {
            catalog.addReferenceRoot(new CasCatalog.ReferenceRoot(
                    "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                    "snapshot-" + index, digest("snapshot-" + index),
                    1_800_000_000_001L + index));
        }
        catalog.addReferenceRoot(new CasCatalog.ReferenceRoot(
                "tenant-b", CasGarbageCollector.RootKind.ACTION_CACHE,
                "cache-selected", digest("other tenant"), 1_800_000_000_200L));

        assertEquals(List.of(selected), catalog.activeReferenceRoots(
                        "tenant-a", CasGarbageCollector.RootKind.ACTION_CACHE,
                        "cache-selected").stream()
                .map(CasCatalog.ReferenceRoot::digest)
                .toList());
        assertTrue(catalog.activeReferenceRoots(
                "tenant-a", CasGarbageCollector.RootKind.ACTION_CACHE,
                "missing").isEmpty());
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

    @Test void firstMultiDigestPublicationUsesOneAuthoritativeGeneration() {
        CasDigest first = digest("first generation member");
        CasDigest second = digest("second generation member");
        CasGarbageCollector.RootKind kind = CasGarbageCollector.RootKind.SNAPSHOT;

        long generation = catalog.addReferenceRoots(List.of(
                new CasCatalog.ReferenceRoot("tenant-a", kind, "snap-generation", first, 100L),
                new CasCatalog.ReferenceRoot("tenant-a", kind, "snap-generation", second, 200L)));

        assertEquals(200L, generation);
        List<CasCatalog.ReferenceRoot> active = catalog.activeReferenceRoots(
                "tenant-a", kind, "snap-generation");
        assertEquals(Set.of(first, second), active.stream()
                .map(CasCatalog.ReferenceRoot::digest)
                .collect(java.util.stream.Collectors.toSet()));
        assertEquals(Set.of(generation), active.stream()
                .map(CasCatalog.ReferenceRoot::createdAtEpochMillis)
                .collect(java.util.stream.Collectors.toSet()),
                "one logical publication must never expose split lifecycle generations");
    }

    @Test void compareAndReleaseOnlyRemovesTheExactActiveGeneration() {
        CasDigest object = digest("generation compare and release");
        CasGarbageCollector.RootKind kind = CasGarbageCollector.RootKind.ACTION_CACHE;
        long generation = catalog.addReferenceRoots(List.of(new CasCatalog.ReferenceRoot(
                "tenant-a", kind, "action-generation", object, 400L)));

        assertFalse(catalog.releaseReferenceRootGeneration(
                "tenant-a", kind, "action-generation", generation - 1, 500L));
        assertEquals(List.of(object), catalog.activeReferenceRoots(
                        "tenant-a", kind, "action-generation").stream()
                .map(CasCatalog.ReferenceRoot::digest)
                .toList());
        assertTrue(catalog.releaseReferenceRootGeneration(
                "tenant-a", kind, "action-generation", generation, 500L));
        assertTrue(catalog.activeReferenceRoots(
                "tenant-a", kind, "action-generation").isEmpty());
        assertFalse(catalog.releaseReferenceRootGeneration(
                "tenant-a", kind, "action-generation", generation, 500L),
                "an already released generation is an idempotent compare miss");
    }

    @Test void repositoryRetirementWaitsForEverySharedSnapshotRootGeneration() {
        CasDigest archive = digest("repository retirement archive");
        CasDigest manifest = digest("repository retirement manifest");
        long boundAt = 1_800_000_000_100L;
        CasCatalog.ResourceLifecycle repository = catalog.ensureActiveResource(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY, "repository-retiring");
        catalog.recordAndBindDurableResource(
                entry("tenant-a", archive,
                        CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()),
                new CasCatalog.ResourceBinding(
                        "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                        "repository-retiring", archive, boundAt),
                repository, () -> { });
        catalog.recordAndBindDurableResource(
                entry("tenant-a", manifest,
                        CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()),
                new CasCatalog.ResourceBinding(
                        "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                        "repository-retiring", manifest, boundAt),
                repository, () -> { });

        long firstGeneration = catalog.publishDurableResourceReferenceRoots(
                repository,
                List.of(
                        new CasCatalog.ReferenceRoot(
                                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                                "snapshot-retiring-one", archive, boundAt + 100L),
                        new CasCatalog.ReferenceRoot(
                                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                                "snapshot-retiring-one", manifest, boundAt + 100L)),
                () -> { });
        long secondGeneration = catalog.publishDurableResourceReferenceRoots(
                repository,
                List.of(
                        new CasCatalog.ReferenceRoot(
                                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                                "snapshot-retiring-two", archive, boundAt + 200L),
                        new CasCatalog.ReferenceRoot(
                                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                                "snapshot-retiring-two", manifest, boundAt + 200L)),
                () -> { });
        CasCatalog.ResourceLifecycle retiring = catalog.beginResourceRetirement(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "repository-retiring", boundAt + 300L);

        assertFalse(catalog.releaseReferenceRootGeneration(
                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-retiring-one", firstGeneration - 1, boundAt + 400L));
        assertThrows(IllegalStateException.class,
                () -> catalog.finalizeResourceRetirement(retiring, boundAt + 400L),
                "an inexact acknowledgement must not release shared bindings");
        assertTrue(catalog.releaseReferenceRootGeneration(
                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-retiring-one", firstGeneration, boundAt + 400L));
        assertThrows(IllegalStateException.class,
                () -> catalog.finalizeResourceRetirement(retiring, boundAt + 400L),
                "the second snapshot still protects the same repository bindings");
        assertEquals(2, catalog.activeResourceBindings(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "repository-retiring").size());

        assertTrue(catalog.releaseReferenceRootGeneration(
                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-retiring-two", secondGeneration, boundAt + 500L));
        CasCatalog.ResourceLifecycle retired =
                catalog.finalizeResourceRetirement(retiring, boundAt + 600L);

        assertEquals(CasCatalog.ResourceLifecycleState.RETIRED, retired.state());
        assertEquals(2L, retired.releasedBindingCount());
        assertTrue(catalog.activeResourceBindings(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "repository-retiring").isEmpty());
    }

    @Test void retiringRepositoryBlocksNewBindingsAndRootsBeforeDurabilityCallbacks() {
        CasDigest existing = digest("retiring repository existing object");
        long boundAt = 1_800_000_000_100L;
        CasCatalog.ResourceLifecycle active = catalog.ensureActiveResource(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY, "repository-fenced");
        catalog.recordAndBindDurableResource(
                entry("tenant-a", existing,
                        CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()),
                new CasCatalog.ResourceBinding(
                        "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                        "repository-fenced", existing, boundAt),
                active, () -> { });
        catalog.beginResourceRetirement(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "repository-fenced", boundAt + 100L);

        CasDigest newObject = digest("retiring repository new object");
        AtomicBoolean bindingDurabilityCalled = new AtomicBoolean();
        assertThrows(IllegalStateException.class,
                () -> catalog.recordAndBindDurableResource(
                        entry("tenant-a", newObject,
                                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()),
                        new CasCatalog.ResourceBinding(
                                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                                "repository-fenced", newObject, boundAt + 200L),
                        active, () -> bindingDurabilityCalled.set(true)));
        assertFalse(bindingDurabilityCalled.get());
        assertTrue(catalog.find("tenant-a", newObject).isEmpty());

        AtomicBoolean rootDurabilityCalled = new AtomicBoolean();
        assertThrows(IllegalStateException.class,
                () -> catalog.publishDurableResourceReferenceRoots(
                        active,
                        List.of(new CasCatalog.ReferenceRoot(
                                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                                "snapshot-after-retirement", existing, boundAt + 200L)),
                        () -> rootDurabilityCalled.set(true)));
        assertFalse(rootDurabilityCalled.get());
        assertTrue(catalog.activeReferenceRoots(
                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-after-retirement").isEmpty());
    }

    @Test void priorIncarnationTokensCannotFinalizeOrReactivateANewerRepositoryEpoch() {
        CasCatalog.ResourceLifecycle firstActive = catalog.ensureActiveResource(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY, "repository-reused");
        CasCatalog.ResourceLifecycle firstRetiring = catalog.beginResourceRetirement(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "repository-reused", 100L);
        CasCatalog.ResourceLifecycle firstRetired =
                catalog.finalizeResourceRetirement(firstRetiring, 200L);
        CasCatalog.ResourceLifecycle secondActive =
                catalog.reactivateResource(firstRetired, 300L);

        assertEquals(firstActive.resourceEpoch() + 1, secondActive.resourceEpoch());
        assertThrows(IllegalStateException.class,
                () -> catalog.finalizeResourceRetirement(firstRetiring, 400L));
        assertThrows(IllegalStateException.class,
                () -> catalog.reactivateResource(firstRetired, 400L));

        CasCatalog.ResourceLifecycle secondRetiring = catalog.beginResourceRetirement(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "repository-reused", 500L);
        assertThrows(IllegalStateException.class,
                () -> catalog.finalizeResourceRetirement(firstRetiring, 600L));
        assertThrows(IllegalStateException.class,
                () -> catalog.reactivateResource(firstRetired, 600L));

        CasCatalog.ResourceLifecycle secondRetired =
                catalog.finalizeResourceRetirement(secondRetiring, 700L);
        assertEquals(secondActive.resourceEpoch(), secondRetired.resourceEpoch(),
                "stale tokens must leave the current incarnation unchanged");
    }

    @Test void competingRootRollsBackTheCombinedCatalogPublication() {
        CasGarbageCollector.RootKind kind = CasGarbageCollector.RootKind.SNAPSHOT;
        CasDigest incumbent = digest("incumbent root member");
        CasDigest candidate = digest("candidate root member");
        catalog.addReferenceRoot(new CasCatalog.ReferenceRoot(
                "tenant-a", kind, "snap-atomic", incumbent, 100L));
        CasCatalog.CatalogEntry candidateEntry = entry(
                "tenant-a", candidate, CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty());

        assertThrows(IllegalStateException.class, () -> catalog.recordAndAddReferenceRoots(
                candidateEntry,
                List.of(new CasCatalog.ReferenceRoot(
                        "tenant-a", kind, "snap-atomic", candidate, 200L))));

        assertTrue(catalog.find("tenant-a", candidate).isEmpty(),
                "failed root publication must roll back the metadata insert");
        assertEquals(List.of(incumbent), catalog.activeReferenceRoots(
                        "tenant-a", kind, "snap-atomic").stream()
                .map(CasCatalog.ReferenceRoot::digest)
                .toList());
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
                () -> 1_900_000_000_000L,
                candidate -> catalog.deleteIfUnreferenced(
                        candidate, tenantIsolated(store)));
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

    @Test void globallySharedPhysicalBytesRequireACrossTenantDeletionAuthority() {
        InMemoryCasStore store = new InMemoryCasStore("global");
        CasDigest object = digest("shared physical bytes");
        byte[] bytes = "shared physical bytes".getBytes(StandardCharsets.UTF_8);
        store.put(object, bytes);
        catalog.record(entry("tenant-a", object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));

        var outcome = catalog.deleteIfUnreferenced(
                new CasGarbageCollector.Candidate(
                        object, object.sizeBytes(), "tenant-a", "UNREACHABLE"),
                TenantCasStore.global(store));

        assertEquals(CasGarbageCollector.AtomicDeletionOutcome.UNAVAILABLE, outcome);
        assertTrue(store.contains(object));
    }

    @Test void tombstoneBlocksEveryReferenceUntilDurablePublicationRepairsTheBytes() {
        InMemoryCasStore store = new InMemoryCasStore("tenant-a");
        byte[] bytes = "repair after delete".getBytes(StandardCharsets.UTF_8);
        CasDigest object = CasDigest.of(bytes);
        catalog.record(entry("tenant-a", object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));
        store.put(object, bytes);
        var candidate = new CasGarbageCollector.Candidate(
                object, object.sizeBytes(), "tenant-a", "UNREACHABLE");

        assertEquals(CasGarbageCollector.AtomicDeletionOutcome.DELETED,
                catalog.deleteIfUnreferenced(candidate, tenantIsolated(store)));
        assertFalse(store.contains(object));
        CasCatalog.ReferenceRoot root = new CasCatalog.ReferenceRoot(
                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-repair", object, 1_900_000_000_000L);
        assertThrows(IllegalStateException.class,
                () -> catalog.addReferenceRoots(List.of(root)));
        assertThrows(IllegalStateException.class,
                () -> catalog.bindResource(new CasCatalog.ResourceBinding(
                        "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                        "repository-a", object, 1_900_000_000_000L)));
        assertThrows(IllegalStateException.class,
                () -> catalog.setLegalHold("tenant-a", object, true));

        catalog.publishDurableReferenceRoots(
                List.of(root), () -> store.putDurable(object, bytes));

        assertTrue(store.contains(object));
        assertEquals(List.of(root), catalog.activeReferenceRoots(
                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT, "snapshot-repair"));
    }

    @Test void durableResourcePublicationRecoversAFirstBindingThatLostTheDeleteRace() {
        InMemoryCasStore store = new InMemoryCasStore("tenant-a");
        byte[] bytes = "resource repair after delete".getBytes(StandardCharsets.UTF_8);
        CasDigest object = CasDigest.of(bytes);
        CasCatalog.CatalogEntry entry = entry("tenant-a", object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty());
        catalog.record(entry);
        store.put(object, bytes);
        assertEquals(CasGarbageCollector.AtomicDeletionOutcome.DELETED,
                catalog.deleteIfUnreferenced(
                        new CasGarbageCollector.Candidate(
                                object, object.sizeBytes(), "tenant-a", "UNREACHABLE"),
                        tenantIsolated(store)));
        CasCatalog.ResourceBinding binding = new CasCatalog.ResourceBinding(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY,
                "repository-repair", object, 1_900_000_000_000L);

        catalog.recordAndBindDurableResource(
                entry, binding, () -> store.putDurable(object, bytes));

        assertTrue(store.contains(object));
        assertEquals(List.of(binding), catalog.activeResourceBindings(
                "tenant-a", CasCatalog.ResourceKind.REPOSITORY, "repository-repair"));
    }

    @Test void outcomeUnknownFencesDeleteRetryAndDurableRepairUntilReconciliation() {
        InMemoryCasStore delegate = new InMemoryCasStore("tenant-a");
        byte[] bytes = "ambiguous deletion".getBytes(StandardCharsets.UTF_8);
        CasDigest object = CasDigest.of(bytes);
        delegate.put(object, bytes);
        catalog.record(entry("tenant-a", object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));
        AtomicInteger deleteAttempts = new AtomicInteger();
        CasStore ambiguousStore = new CasStore() {
            @Override public String name() { return delegate.name(); }
            @Override public boolean contains(CasDigest digest) { return delegate.contains(digest); }
            @Override public void put(CasDigest digest, byte[] content) { delegate.put(digest, content); }
            @Override public byte[] get(CasDigest digest) { return delegate.get(digest); }
            @Override public byte[] readRange(CasDigest digest, long offset, int length) {
                return delegate.readRange(digest, offset, length);
            }
            @Override public boolean delete(CasDigest digest) {
                deleteAttempts.incrementAndGet();
                throw new IllegalStateException("provider acknowledgement lost");
            }
            @Override public Set<CasDigest> inventory() { return delegate.inventory(); }
            @Override public long totalBytes() { return delegate.totalBytes(); }
        };
        var candidate = new CasGarbageCollector.Candidate(
                object, object.sizeBytes(), "tenant-a", "UNREACHABLE");

        assertEquals(CasGarbageCollector.AtomicDeletionOutcome.UNAVAILABLE,
                catalog.deleteIfUnreferenced(candidate, tenantIsolated(ambiguousStore)));
        assertEquals(CasGarbageCollector.AtomicDeletionOutcome.UNAVAILABLE,
                catalog.deleteIfUnreferenced(candidate, tenantIsolated(ambiguousStore)));
        assertEquals(1, deleteAttempts.get(),
                "OUTCOME_UNKNOWN must not start a second provider delete");
        AtomicBoolean repairCalled = new AtomicBoolean();
        CasCatalog.ReferenceRoot root = new CasCatalog.ReferenceRoot(
                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-ambiguous", object, 1_900_000_000_000L);
        assertThrows(IllegalStateException.class,
                () -> catalog.publishDurableReferenceRoots(List.of(root), () -> {
                    repairCalled.set(true);
                    delegate.putDurable(object, bytes);
                }));
        assertFalse(repairCalled.get());
        assertTrue(catalog.activeReferenceRoots(
                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-ambiguous").isEmpty());
    }

    @Test void competingDeleteAndDurablePublicationCannotCreateADanglingRoot() throws Exception {
        InMemoryCasStore delegate = new InMemoryCasStore("tenant-a");
        byte[] bytes = "barrier protected publication".getBytes(StandardCharsets.UTF_8);
        CasDigest object = CasDigest.of(bytes);
        delegate.put(object, bytes);
        catalog.record(entry("tenant-a", object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));
        CountDownLatch deleteEntered = new CountDownLatch(1);
        CountDownLatch allowDelete = new CountDownLatch(1);
        CasStore blockingStore = new CasStore() {
            @Override public String name() { return delegate.name(); }
            @Override public boolean contains(CasDigest digest) { return delegate.contains(digest); }
            @Override public void put(CasDigest digest, byte[] content) { delegate.put(digest, content); }
            @Override public void putDurable(CasDigest digest, byte[] content) {
                delegate.putDurable(digest, content);
            }
            @Override public byte[] get(CasDigest digest) { return delegate.get(digest); }
            @Override public byte[] readRange(CasDigest digest, long offset, int length) {
                return delegate.readRange(digest, offset, length);
            }
            @Override public boolean delete(CasDigest digest) {
                deleteEntered.countDown();
                try {
                    if (!allowDelete.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("delete barrier timed out");
                    }
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("delete barrier interrupted", interrupted);
                }
                return delegate.delete(digest);
            }
            @Override public Set<CasDigest> inventory() { return delegate.inventory(); }
            @Override public long totalBytes() { return delegate.totalBytes(); }
        };
        CasCatalog.ReferenceRoot root = new CasCatalog.ReferenceRoot(
                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-barrier", object, 1_900_000_000_000L);
        CountDownLatch publisherStarted = new CountDownLatch(1);
        CountDownLatch durableRepairEntered = new CountDownLatch(1);
        try (var executor = Executors.newFixedThreadPool(2)) {
            var deletion = executor.submit(() -> catalog.deleteIfUnreferenced(
                    new CasGarbageCollector.Candidate(
                            object, object.sizeBytes(), "tenant-a", "UNREACHABLE"),
                    tenantIsolated(blockingStore)));
            assertTrue(deleteEntered.await(5, TimeUnit.SECONDS));
            var publication = executor.submit(() -> {
                publisherStarted.countDown();
                return catalog.publishDurableReferenceRoots(List.of(root), () -> {
                    durableRepairEntered.countDown();
                    blockingStore.putDurable(object, bytes);
                });
            });
            assertTrue(publisherStarted.await(5, TimeUnit.SECONDS));
            assertEquals(1L, durableRepairEntered.getCount(),
                    "publication must wait until the deletion protocol releases the object lock");
            allowDelete.countDown();
            assertEquals(CasGarbageCollector.AtomicDeletionOutcome.DELETED,
                    deletion.get(5, TimeUnit.SECONDS));
            publication.get(5, TimeUnit.SECONDS);
        }

        assertTrue(delegate.contains(object));
        assertEquals(List.of(root), catalog.activeReferenceRoots(
                "tenant-a", CasGarbageCollector.RootKind.SNAPSHOT, "snapshot-barrier"));
    }
}
