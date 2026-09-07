package io.elmos.persistence;

import io.elmos.cas.ActionCache;
import io.elmos.cas.ActionKey;
import io.elmos.cas.ActionKeyBuilder;
import io.elmos.cas.ActionResultRecord;
import io.elmos.cas.CachedActionExecutor;
import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.CasCatalog;
import io.elmos.cas.CasDigest;
import io.elmos.cas.CasGarbageCollector;
import io.elmos.cas.CasMetrics;
import io.elmos.cas.CasObjectModel;
import io.elmos.cas.CasStore;
import io.elmos.cas.CasTelemetry;
import io.elmos.cas.InMemoryCasStore;
import io.elmos.cas.JdbcActionCacheIndex;
import io.elmos.cas.JdbcCasCatalog;
import io.elmos.cas.ResultSignature;
import io.elmos.cas.TenantCasStore;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import javax.sql.DataSource;
import java.nio.charset.StandardCharsets;
import java.security.KeyPairGenerator;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
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
 * Holds {@link JdbcCasCatalog} to the same contract as the in-memory implementation, against the
 * real V65 schema.
 *
 * <p>This is the half the cloud build cannot run: the constraints, the row level security policy
 * and the append-only triggers only exist inside PostgreSQL. `CasCatalogTest` in `modules/cas`
 * covers the same behaviours against the heap implementation, and the two agreeing is the point —
 * a rule that only one of them enforces is a rule that gets violated in whichever environment the
 * other one runs in.
 */
@Testcontainers(disabledWithoutDocker = true)
class JdbcCasCatalogLiveTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:17.5-alpine");

    private static final long TRUST_NOW = 1_800_000_000_000L;
    private static final String PINNED_IMAGE =
            "registry.internal/elmos/java21@sha256:" + "a".repeat(64);
    private static final String APP_USER = "elmos_cas_live_app";
    private static final String APP_PASSWORD = "cas-live-test-only";

    private static DataSource dataSource;
    private static DataSource adminDataSource;

    private static CasDigest digest(String text) {
        return CasDigest.of(text.getBytes(StandardCharsets.UTF_8));
    }

    @BeforeAll
    static void migrate() throws SQLException {
        Flyway.configure()
                .dataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())
                .defaultSchema("public")
                .load()
                .migrate();
        DriverManagerDataSource admin = new DriverManagerDataSource(POSTGRES.getJdbcUrl(),
                POSTGRES.getUsername(), POSTGRES.getPassword());
        admin.setDriverClassName("org.postgresql.Driver");
        adminDataSource = admin;
        try (Connection connection = admin.getConnection(); Statement statement = connection.createStatement()) {
            statement.execute("CREATE ROLE " + APP_USER
                    + " LOGIN PASSWORD '" + APP_PASSWORD
                    + "' NOSUPERUSER NOBYPASSRLS NOINHERIT");
            statement.execute("GRANT USAGE ON SCHEMA public TO " + APP_USER);
            statement.execute("GRANT SELECT ON TABLE cas_object_catalog, cas_object_placement, "
                    + "cas_resource_bindings, cas_reference_roots, cas_deletion_manifests, "
                    + "cas_object_deletion_tombstones, cas_tenant_lifecycles, "
                    + "cas_resource_lifecycles, "
                    + "cas_quarantine_events, cas_action_cache_entries, "
                    + "cas_action_cache_invalidations, cas_action_cache_quarantined_nodes TO "
                    + APP_USER);
            statement.execute("GRANT INSERT, UPDATE ON TABLE cas_object_catalog, "
                    + "cas_object_placement, cas_resource_bindings, cas_reference_roots, "
                    + "cas_object_deletion_tombstones, cas_tenant_lifecycles, "
                    + "cas_resource_lifecycles, "
                    + "cas_action_cache_entries TO " + APP_USER);
            statement.execute("GRANT DELETE ON TABLE cas_object_deletion_tombstones TO "
                    + APP_USER);
            statement.execute("GRANT INSERT ON TABLE cas_deletion_manifests, "
                    + "cas_quarantine_events, cas_action_cache_invalidations, "
                    + "cas_action_cache_quarantined_nodes TO " + APP_USER);
        }
        DriverManagerDataSource application = new DriverManagerDataSource(
                POSTGRES.getJdbcUrl(), APP_USER, APP_PASSWORD);
        application.setDriverClassName("org.postgresql.Driver");
        dataSource = application;
    }

    private static CasCatalog.CatalogEntry entry(String tenant, CasDigest digest,
                                                 CasObjectModel.Sensitivity sensitivity,
                                                 Optional<CasDigest> provenance) {
        return new CasCatalog.CatalogEntry(tenant, digest, "project-a", CasObjectModel.ObjectKind.BLOB,
                "application/octet-stream", "elmos", "1.0", sensitivity,
                CasObjectModel.RetentionClass.STANDARD, "eu-west",
                CasAccessPolicy.SecurityTier.INTERNAL, provenance, Map.of("stage", "baseline"), false,
                1_800_000_000_000L);
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

    @Test void anEntryRoundTripsThroughTheRealSchema() {
        var catalog = new JdbcCasCatalog(dataSource);
        CasDigest object = digest("jdbc payload");
        CasDigest provenance = digest("provenance");
        CasCatalog.CatalogEntry expected = entry("tenant-jdbc-1", object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.of(provenance));
        catalog.record(expected);

        var found = catalog.find("tenant-jdbc-1", object).orElseThrow();
        assertEquals(expected, found,
                "the current schema must round-trip the complete catalog entry metadata");
        assertEquals(expected.metadata(), found.metadata());
        assertEquals(provenance.sizeBytes(),
                found.provenanceDigest().orElseThrow().sizeBytes(),
                "V66 must read back provenance_size_bytes rather than reconstructing it");
    }

    @Test void recordingTheSameObjectTwiceIsIdempotent() {
        var catalog = new JdbcCasCatalog(dataSource);
        CasDigest object = digest("recorded twice");
        catalog.record(entry("tenant-jdbc-2", object, CasObjectModel.Sensitivity.PRIVATE_SOURCE,
                Optional.empty()));
        catalog.record(entry("tenant-jdbc-2", object, CasObjectModel.Sensitivity.PRIVATE_SOURCE,
                Optional.empty()));
        assertEquals(1, catalog.load("tenant-jdbc-2", Set.of(object)).size());
    }

    @Test void rowLevelSecurityHidesOtherTenants() {
        var catalog = new JdbcCasCatalog(dataSource);
        CasDigest shared = digest("byte identical across tenants");
        catalog.record(entry("tenant-jdbc-3", shared, CasObjectModel.Sensitivity.PRIVATE_SOURCE,
                Optional.empty()));

        assertTrue(catalog.find("tenant-jdbc-3", shared).isPresent());
        assertTrue(catalog.find("tenant-jdbc-4", shared).isEmpty(),
                "the policy reads app.organization_id, which the catalogue sets per connection");

        assertRoleCannotBypassRls();
        try (Connection connection = dataSource.getConnection()) {
            assertEquals(0, countCatalogRows(connection, "tenant-jdbc-3"),
                    "a pooled connection without transaction-local tenant context must see nothing");
            connection.setAutoCommit(false);
            setTenant(connection, "tenant-jdbc-3");
            assertEquals(1, countCatalogRows(connection, "tenant-jdbc-3"));
            connection.commit();
            assertTenantSettingCleared(connection);

            connection.setAutoCommit(false);
            setTenant(connection, "tenant-jdbc-4");
            assertEquals(0, countCatalogRows(connection, "tenant-jdbc-3"),
                    "a reused physical connection must not retain the previous tenant");
            SQLException rejected = assertThrows(SQLException.class,
                    () -> insertCatalogRowForAnotherTenant(connection));
            assertEquals("42501", rejected.getSQLState(),
                    "the cross-tenant insert must fail because of RLS, not schema drift");
            connection.rollback();
        } catch (SQLException error) {
            throw new IllegalStateException(error);
        }
    }

    @Test void theDatabaseRefusesASecondPrimaryRegion() {
        var catalog = new JdbcCasCatalog(dataSource);
        CasDigest object = digest("placed by jdbc");
        catalog.record(entry("tenant-jdbc-5", object, CasObjectModel.Sensitivity.GENERATED_OUTPUT,
                Optional.empty()));
        catalog.placeObject(new CasCatalog.Placement("tenant-jdbc-5", object, "eu-west-1",
                CasCatalog.PlacementRole.PRIMARY, "L2"));
        catalog.placeObject(new CasCatalog.Placement("tenant-jdbc-5", object, "eu-central-1",
                CasCatalog.PlacementRole.REPLICA, "L2"));

        assertEquals(2, catalog.placements("tenant-jdbc-5", object).size());
        assertThrows(IllegalStateException.class,
                () -> catalog.placeObject(new CasCatalog.Placement("tenant-jdbc-5", object, "us-east-1",
                        CasCatalog.PlacementRole.PRIMARY, "L2")));
    }

    @Test void theDatabaseRefusesPlacementOfAnUncataloguedObject() {
        var catalog = new JdbcCasCatalog(dataSource);
        assertThrows(IllegalStateException.class,
                () -> catalog.placeObject(new CasCatalog.Placement("tenant-jdbc-6", digest("ghost"),
                        "eu-west-1", CasCatalog.PlacementRole.PRIMARY, "L2")));
    }

    @Test void referenceRootsAreActiveUntilReleased() {
        var catalog = new JdbcCasCatalog(dataSource);
        CasDigest object = digest("referenced by jdbc");
        CasDigest sibling = digest("second referenced by jdbc");
        long generation = catalog.addReferenceRoots(List.of(
                new CasCatalog.ReferenceRoot("tenant-jdbc-7",
                        CasGarbageCollector.RootKind.SNAPSHOT, "snap-1", object,
                        1_800_000_000_000L),
                new CasCatalog.ReferenceRoot("tenant-jdbc-7",
                        CasGarbageCollector.RootKind.SNAPSHOT, "snap-1", sibling,
                        1_800_000_000_001L)));
        catalog.addReferenceRoot(new CasCatalog.ReferenceRoot("tenant-jdbc-7",
                CasGarbageCollector.RootKind.ACTION_CACHE, "cache-unrelated",
                digest("unrelated jdbc root"), 1_800_000_000_001L));
        assertEquals(3, catalog.activeReferenceRoots("tenant-jdbc-7").size());
        List<CasCatalog.ReferenceRoot> snapshotRoots = catalog.activeReferenceRoots(
                "tenant-jdbc-7", CasGarbageCollector.RootKind.SNAPSHOT, "snap-1");
        assertEquals(Set.of(object, sibling), snapshotRoots.stream()
                .map(CasCatalog.ReferenceRoot::digest).collect(
                        java.util.stream.Collectors.toSet()));
        assertEquals(Set.of(generation), snapshotRoots.stream()
                .map(CasCatalog.ReferenceRoot::createdAtEpochMillis).collect(
                        java.util.stream.Collectors.toSet()),
                "a multi-object JDBC root must publish one lifecycle generation");

        catalog.releaseReferenceRoot("tenant-jdbc-7", CasGarbageCollector.RootKind.SNAPSHOT, "snap-1",
                1_800_000_100_000L);
        assertTrue(catalog.activeReferenceRoots(
                "tenant-jdbc-7", CasGarbageCollector.RootKind.SNAPSHOT, "snap-1").isEmpty());
        assertEquals(1, catalog.activeReferenceRoots("tenant-jdbc-7").size());
    }

    @Test void v76TombstoneBlocksRootAndResourcePublicationUntilDurableRepair() {
        String tenant = "tenant-jdbc-v76";
        var catalog = new JdbcCasCatalog(dataSource);
        var store = new InMemoryCasStore("jdbc-v76-tenant-store");
        byte[] bytes = "v76 deletion protocol".getBytes(StandardCharsets.UTF_8);
        CasDigest object = CasDigest.of(bytes);
        catalog.record(entry(tenant, object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));
        store.put(object, bytes);
        var candidate = new CasGarbageCollector.Candidate(
                object, object.sizeBytes(), tenant, "UNREACHABLE");

        assertEquals(CasGarbageCollector.AtomicDeletionOutcome.DELETED,
                catalog.deleteIfUnreferenced(candidate, tenantIsolated(store)));
        assertFalse(store.contains(object));
        CasCatalog.ReferenceRoot root = new CasCatalog.ReferenceRoot(
                tenant, CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-v76", object, TRUST_NOW);
        assertThrows(IllegalStateException.class,
                () -> catalog.addReferenceRoots(List.of(root)));
        assertThrows(IllegalStateException.class,
                () -> catalog.bindResource(new CasCatalog.ResourceBinding(
                        tenant, CasCatalog.ResourceKind.REPOSITORY,
                        "repository-v76", object, TRUST_NOW)));
        assertThrows(IllegalStateException.class,
                () -> catalog.setLegalHold(tenant, object, true));
        assertDirectRootActivationBlockedByTombstone(tenant, root);

        long generation = catalog.publishDurableReferenceRoots(
                List.of(root), () -> store.putDurable(object, bytes));

        assertTrue(store.contains(object));
        assertEquals(TRUST_NOW, generation);
        assertEquals(List.of(root), catalog.activeReferenceRoots(
                tenant, CasGarbageCollector.RootKind.SNAPSHOT, "snapshot-v76"));
    }

    @Test void activeResourceBindingIsAnAuthoritativeDeleteTimeReference() {
        String tenant = "tenant-jdbc-v76-binding";
        var catalog = new JdbcCasCatalog(dataSource);
        var store = new InMemoryCasStore("jdbc-v76-bound-store");
        byte[] bytes = "bound object".getBytes(StandardCharsets.UTF_8);
        CasDigest object = CasDigest.of(bytes);
        catalog.record(entry(tenant, object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));
        catalog.bindResource(new CasCatalog.ResourceBinding(
                tenant, CasCatalog.ResourceKind.REPOSITORY,
                "repository-v76", object, TRUST_NOW));
        store.put(object, bytes);
        var candidate = new CasGarbageCollector.Candidate(
                object, object.sizeBytes(), tenant, "UNREACHABLE");

        assertEquals(CasGarbageCollector.AtomicDeletionOutcome.LIVE_REFERENCE_OR_HOLD,
                catalog.deleteIfUnreferenced(candidate, tenantIsolated(store)));
        assertTrue(store.contains(object));

        catalog.releaseResource(tenant, CasCatalog.ResourceKind.REPOSITORY,
                "repository-v76", object, TRUST_NOW + 1);
        assertEquals(CasGarbageCollector.AtomicDeletionOutcome.DELETED,
                catalog.deleteIfUnreferenced(candidate, tenantIsolated(store)));
        assertFalse(store.contains(object));
    }

    @Test void jdbcResourceRetirementWaitsForMappedRootsAndAdvancesIncarnation() {
        String tenant = "tenant-jdbc-v76-resource-lifecycle";
        var catalog = new JdbcCasCatalog(dataSource);
        CasDigest object = digest("resource lifecycle object");
        catalog.record(entry(tenant, object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));
        CasCatalog.ResourceLifecycle active = catalog.ensureActiveResource(
                tenant, CasCatalog.ResourceKind.REPOSITORY, "repository-lifecycle");
        catalog.bindResource(new CasCatalog.ResourceBinding(
                tenant, CasCatalog.ResourceKind.REPOSITORY,
                "repository-lifecycle", object, TRUST_NOW));
        CasCatalog.ReferenceRoot root = new CasCatalog.ReferenceRoot(
                tenant, CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-resource-lifecycle", object, TRUST_NOW);
        long generation = catalog.publishDurableResourceReferenceRoots(
                active, List.of(root), () -> { });

        CasCatalog.ResourceLifecycle retiring = catalog.beginResourceRetirement(
                tenant, CasCatalog.ResourceKind.REPOSITORY,
                "repository-lifecycle", TRUST_NOW + 1);
        assertThrows(IllegalStateException.class,
                () -> catalog.finalizeResourceRetirement(retiring, TRUST_NOW + 2));
        assertTrue(catalog.releaseReferenceRootGeneration(
                tenant, CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-resource-lifecycle", generation, TRUST_NOW + 2));
        CasCatalog.ResourceLifecycle retired = catalog.finalizeResourceRetirement(
                retiring, TRUST_NOW + 3);

        assertEquals(CasCatalog.ResourceLifecycleState.RETIRED, retired.state());
        assertEquals(1, retired.releasedBindingCount());
        assertTrue(catalog.activeResourceBindings(
                tenant, CasCatalog.ResourceKind.REPOSITORY,
                "repository-lifecycle").isEmpty());
        CasCatalog.ResourceLifecycle reactivated = catalog.reactivateResource(
                retired, TRUST_NOW + 4);
        assertEquals(active.resourceEpoch() + 1, reactivated.resourceEpoch());
    }

    @Test void jdbcDurableResourcePublicationRepairsAndClearsADeletionTombstone() {
        String tenant = "tenant-jdbc-v76-resource-repair";
        var catalog = new JdbcCasCatalog(dataSource);
        var store = new InMemoryCasStore("jdbc-v76-resource-repair-store");
        byte[] bytes = "jdbc resource repair".getBytes(StandardCharsets.UTF_8);
        CasDigest object = CasDigest.of(bytes);
        CasCatalog.CatalogEntry entry = entry(tenant, object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty());
        catalog.record(entry);
        store.put(object, bytes);
        var candidate = new CasGarbageCollector.Candidate(
                object, object.sizeBytes(), tenant, "UNREACHABLE");
        assertEquals(CasGarbageCollector.AtomicDeletionOutcome.DELETED,
                catalog.deleteIfUnreferenced(candidate, tenantIsolated(store)));
        CasCatalog.ResourceBinding binding = new CasCatalog.ResourceBinding(
                tenant, CasCatalog.ResourceKind.REPOSITORY,
                "repository-repair", object, TRUST_NOW);

        catalog.recordAndBindDurableResource(
                entry, binding, () -> store.putDurable(object, bytes));

        assertTrue(store.contains(object));
        assertEquals(List.of(binding), catalog.activeResourceBindings(
                tenant, CasCatalog.ResourceKind.REPOSITORY, "repository-repair"));
    }

    @Test void pendingPhysicalDeleteFencesACompetingDurablePublisher() throws Exception {
        String tenant = "tenant-jdbc-v76-delete-fence";
        var catalog = new JdbcCasCatalog(dataSource);
        var delegate = new InMemoryCasStore("jdbc-v76-delete-fence-store");
        byte[] bytes = "pending deletion fence".getBytes(StandardCharsets.UTF_8);
        CasDigest object = CasDigest.of(bytes);
        CasCatalog.CatalogEntry entry = entry(tenant, object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty());
        catalog.record(entry);
        delegate.put(object, bytes);
        CountDownLatch deleteEntered = new CountDownLatch(1);
        CountDownLatch allowDelete = new CountDownLatch(1);
        CasStore blockingStore = new CasStore() {
            @Override public String name() { return delegate.name(); }
            @Override public boolean contains(CasDigest digest) { return delegate.contains(digest); }
            @Override public void put(CasDigest digest, byte[] content) {
                delegate.put(digest, content);
            }
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
                        throw new IllegalStateException("delete fence timed out");
                    }
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("delete fence interrupted", interrupted);
                }
                return delegate.delete(digest);
            }
            @Override public Set<CasDigest> inventory() { return delegate.inventory(); }
            @Override public long totalBytes() { return delegate.totalBytes(); }
        };
        var candidate = new CasGarbageCollector.Candidate(
                object, object.sizeBytes(), tenant, "UNREACHABLE");
        CasCatalog.ReferenceRoot root = new CasCatalog.ReferenceRoot(
                tenant, CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-delete-fence", object, TRUST_NOW);
        AtomicBoolean durableCallbackCalled = new AtomicBoolean();

        try (var executor = Executors.newSingleThreadExecutor()) {
            var deletion = executor.submit(() -> catalog.deleteIfUnreferenced(
                    candidate, tenantIsolated(blockingStore)));
            assertTrue(deleteEntered.await(5, TimeUnit.SECONDS));
            try {
                assertThrows(IllegalStateException.class,
                        () -> catalog.publishDurableReferenceRoots(List.of(root), () -> {
                            durableCallbackCalled.set(true);
                            delegate.putDurable(object, bytes);
                        }));
                assertFalse(durableCallbackCalled.get(),
                        "PENDING must fence the publisher before it rewrites bytes");
            } finally {
                allowDelete.countDown();
            }
            assertEquals(CasGarbageCollector.AtomicDeletionOutcome.DELETED,
                    deletion.get(5, TimeUnit.SECONDS));
        }

        catalog.publishDurableReferenceRoots(
                List.of(root), () -> delegate.putDurable(object, bytes));
        assertTrue(delegate.contains(object));
        assertEquals(List.of(root), catalog.activeReferenceRoots(
                tenant, CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-delete-fence"));
    }

    @Test void durablePublisherErrorRollsBackTombstoneAndRootTransaction() {
        String tenant = "tenant-jdbc-v76-error-rollback";
        var catalog = new JdbcCasCatalog(dataSource);
        var store = new InMemoryCasStore("jdbc-v76-error-rollback-store");
        byte[] bytes = "publisher error rollback".getBytes(StandardCharsets.UTF_8);
        CasDigest object = CasDigest.of(bytes);
        catalog.record(entry(tenant, object,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, Optional.empty()));
        store.put(object, bytes);
        assertEquals(CasGarbageCollector.AtomicDeletionOutcome.DELETED,
                catalog.deleteIfUnreferenced(
                        new CasGarbageCollector.Candidate(
                                object, object.sizeBytes(), tenant, "UNREACHABLE"),
                        tenantIsolated(store)));
        CasCatalog.ReferenceRoot root = new CasCatalog.ReferenceRoot(
                tenant, CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-error-rollback", object, TRUST_NOW);

        assertThrows(AssertionError.class,
                () -> catalog.publishDurableReferenceRoots(
                        List.of(root), () -> {
                            throw new AssertionError("simulated VM-level callback failure");
                        }));
        assertThrows(IllegalStateException.class,
                () -> catalog.addReferenceRoots(List.of(root)),
                "Error must not commit the tombstone delete when auto-commit is restored");
        assertTrue(catalog.activeReferenceRoots(
                tenant, CasGarbageCollector.RootKind.SNAPSHOT,
                "snapshot-error-rollback").isEmpty());

        catalog.publishDurableReferenceRoots(
                List.of(root), () -> store.putDurable(object, bytes));
        assertTrue(store.contains(object));
    }

    @Test void referenceRootGenerationSurvivesASecondCatalogAndRegressedClock() {
        CasGarbageCollector.RootKind kind = CasGarbageCollector.RootKind.SNAPSHOT;
        CasDigest object = digest("persistent reference generation");
        long first = new JdbcCasCatalog(dataSource).addReferenceRoots(List.of(
                new CasCatalog.ReferenceRoot("tenant-jdbc-generation", kind,
                        "snap-persistent-generation", object, 1_800_000_000_000L)));
        new JdbcCasCatalog(dataSource).releaseReferenceRoot(
                "tenant-jdbc-generation", kind, "snap-persistent-generation", first);

        JdbcCasCatalog restarted = new JdbcCasCatalog(dataSource);
        long second = restarted.addReferenceRoots(List.of(
                new CasCatalog.ReferenceRoot("tenant-jdbc-generation", kind,
                        "snap-persistent-generation", object, first - 10_000L)));

        assertTrue(second > first);
        assertThrows(IllegalArgumentException.class, () -> restarted.releaseReferenceRoot(
                "tenant-jdbc-generation", kind, "snap-persistent-generation", first));
        assertEquals(second, restarted.activeReferenceRoots("tenant-jdbc-generation")
                .get(0).createdAtEpochMillis());
    }

    @Test void exactGenerationReleaseIsAtomicAcrossCatalogInstances() {
        String tenant = "tenant-jdbc-generation-compare";
        CasGarbageCollector.RootKind kind = CasGarbageCollector.RootKind.ACTION_CACHE;
        String rootId = "cache-generation-compare";
        CasDigest object = digest("exact persistent generation");
        JdbcCasCatalog writer = new JdbcCasCatalog(dataSource);
        JdbcCasCatalog reconciler = new JdbcCasCatalog(dataSource);
        long first = writer.addReferenceRoots(List.of(new CasCatalog.ReferenceRoot(
                tenant, kind, rootId, object, 1_800_000_000_000L)));

        assertFalse(reconciler.releaseReferenceRootGeneration(
                tenant, kind, rootId, first - 1L, first + 100L));
        assertEquals(first, writer.activeReferenceRoots(tenant, kind, rootId)
                .get(0).createdAtEpochMillis());
        assertTrue(reconciler.releaseReferenceRootGeneration(
                tenant, kind, rootId, first, first + 100L));

        long second = writer.addReferenceRoots(List.of(new CasCatalog.ReferenceRoot(
                tenant, kind, rootId, object, first - 10_000L)));
        assertTrue(second > first);
        assertFalse(reconciler.releaseReferenceRootGeneration(
                tenant, kind, rootId, first, second + 100L),
                "a delayed token must not release the newer generation");
        assertEquals(second, writer.activeReferenceRoots(tenant, kind, rootId)
                .get(0).createdAtEpochMillis());
    }

    @Test void aDeletionManifestCannotBeRewritten() {
        var catalog = new JdbcCasCatalog(dataSource);
        var manifest = new CasGarbageCollector.DeletionManifest("jdbc-batch-1", false, List.of(),
                List.of(), List.of(), 0, 1_800_000_000_000L);
        catalog.recordDeletionManifest("tenant-jdbc-8", manifest, "gc");
        assertEquals(List.of("jdbc-batch-1"), catalog.deletionBatchIds("tenant-jdbc-8"));
        assertThrows(IllegalStateException.class,
                () -> catalog.recordDeletionManifest("tenant-jdbc-8", manifest, "gc"));
        String update = "UPDATE cas_deletion_manifests SET executed_by = 'rewriter' "
                + "WHERE organization_id = 'tenant-jdbc-8' AND batch_id = 'jdbc-batch-1'";
        String delete = "DELETE FROM cas_deletion_manifests "
                + "WHERE organization_id = 'tenant-jdbc-8' AND batch_id = 'jdbc-batch-1'";
        assertRuntimeMutationDenied(update);
        assertRuntimeMutationDenied(delete);
        assertOwnerAppendOnlyTrigger(update);
        assertOwnerAppendOnlyTrigger(delete);
    }

    @Test void aContentQuarantineNeedsBothDigests() {
        var catalog = new JdbcCasCatalog(dataSource);
        assertThrows(IllegalStateException.class,
                () -> catalog.recordQuarantine("tenant-jdbc-9", "q-1", "OBJECT", "subject",
                        Optional.of(digest("declared")), Optional.empty(), "half a record",
                        1_800_000_000_000L));
        catalog.recordQuarantine("tenant-jdbc-9", "q-2", "NODE", "ns/runners/sa/n1",
                Optional.empty(), Optional.empty(), "nondeterministic output", 1_800_000_000_000L);
        assertEquals(1, catalog.quarantineCount("tenant-jdbc-9"));
    }

    @Test void aSignedActionCacheHitRoundTripsAcrossInstancesAndRechecksCurrentTrust()
            throws Exception {
        InMemoryCasStore objectStore = new InMemoryCasStore("live-postgresql-action-objects");
        JdbcActionCacheIndex writerIndex = new JdbcActionCacheIndex(dataSource);
        JdbcActionCacheIndex readerIndex = new JdbcActionCacheIndex(dataSource);
        ActionKey key = actionKey("tenant-jdbc-action");
        byte[] outputBytes = "live PostgreSQL output manifest".getBytes(StandardCharsets.UTF_8);
        CasDigest outputManifest = CasDigest.of(outputBytes);
        objectStore.put(outputManifest, outputBytes);
        ActionResultRecord result = ActionResultRecord.succeeded(
                "action-live-postgresql", "receipt-live-postgresql", outputManifest,
                digest("live action provenance"),
                new ActionResultRecord.ResourceUsage(2, 256, 30, 40, 0, 3),
                "2026-08-24T00:00:00Z", "2026-08-24T00:00:03Z");
        CasAccessPolicy.ProducerContext producer = new CasAccessPolicy.ProducerContext(
                key.tenantId(), "project-a", Set.of("repo:read"), "eu-west",
                CasAccessPolicy.SecurityTier.INTERNAL,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, PINNED_IMAGE,
                Optional.of(digest("live producer provenance")));
        ActionCache.WriterIdentity writer = new ActionCache.WriterIdentity(
                "runner", "elmos.internal", "node-live-postgresql", true);

        var keyPair = KeyPairGenerator.getInstance(ResultSignature.ED25519).generateKeyPair();
        ResultSignature.KeyRegistry keys = ResultSignature.KeyRegistry.ed25519Only()
                .register(new ResultSignature.SigningKey(
                        "live-postgresql-signer", ResultSignature.ED25519,
                        keyPair.getPublic(), TRUST_NOW - 10_000, TRUST_NOW + 100_000));
        ResultSignature.Verifier verifier = new ResultSignature.Verifier(
                keys, ResultSignature.VerificationPolicy.standard());
        ResultSignature.Envelope envelope = ResultSignature.envelope(
                key, result, producer, writer, ActionCache.RiskTier.HIGH,
                "live-postgresql-signer", ResultSignature.ED25519, TRUST_NOW);
        ResultSignature.DetachedSignature signature = ResultSignature.sign(
                envelope, keyPair.getPrivate(), "live-postgresql-signer",
                ResultSignature.ED25519, TRUST_NOW);
        ActionCache.ResultAttestation attestation = verifier.attestation(
                key, result, producer, writer, ActionCache.RiskTier.HIGH,
                signature, TRUST_NOW);

        ActionCache writerCache = actionCache(
                objectStore, writerIndex, verifier.currentTrustRevalidator());
        writerCache.put(key, result, producer, writer, ActionCache.RiskTier.HIGH,
                Optional.of(attestation));
        ActionCache.Entry persisted = readerIndex.find(key).orElseThrow();
        assertEquals(result, persisted.result());
        assertEquals(attestation, persisted.attestation().orElseThrow());
        assertArrayEquals(signature.value(), persisted.attestation().orElseThrow()
                .signatureValue().orElseThrow(),
                "V69 must round-trip the detached signature bytes, not only their digest");
        assertEquals(writer, persisted.writer());

        ActionCache readerCache = actionCache(
                objectStore, readerIndex, verifier.currentTrustRevalidator());
        AtomicInteger executions = new AtomicInteger();
        CachedActionExecutor caller = new CachedActionExecutor(
                readerCache,
                (request, operation) -> CachedActionExecutor.AuthorizationDecision.allow(
                        "LIVE_POSTGRESQL_" + operation.name()),
                request -> {
                    executions.incrementAndGet();
                    return result;
                });
        CachedActionExecutor.Outcome hit = caller.execute(new CachedActionExecutor.Request(
                key, actionReader(key.tenantId()), false,
                CachedActionExecutor.Mode.CACHE_OR_EXECUTE));
        assertEquals(CachedActionExecutor.OutcomeKind.CACHE_HIT, hit.kind());
        assertEquals(result, hit.result().orElseThrow());
        assertEquals(0, executions.get(), "a durable hit must not invoke the action runner");

        assertTrue(keys.revoke("live-postgresql-signer"));
        ActionCache.Lookup revoked = readerCache.get(key, actionReader(key.tenantId()), false);
        assertEquals(ActionCache.CacheOutcome.INVALIDATED, revoked.outcome());
        assertEquals("CURRENT_TRUST_REVOKED", revoked.reason());
        ActionCache thirdInstance = actionCache(
                objectStore, new JdbcActionCacheIndex(dataSource),
                verifier.currentTrustRevalidator());
        assertEquals(ActionCache.CacheOutcome.MISS,
                thirdInstance.get(key, actionReader(key.tenantId()), false).outcome());
    }

    private static ActionCache actionCache(
            InMemoryCasStore objects,
            JdbcActionCacheIndex index,
            ActionCache.TrustRevalidator trustRevalidator
    ) {
        return new ActionCache(TenantCasStore.global(objects), new CasAccessPolicy(),
                ActionCache.FailureCachePolicy.none(),
                ActionCache.SampleRecomputePolicy.disabled(), () -> TRUST_NOW,
                new CasMetrics(), index, CasTelemetry.noop(), trustRevalidator);
    }

    private static ActionKey actionKey(String tenantId) {
        return new ActionKeyBuilder()
                .tenant(tenantId, "project-a")
                .sourceTree(digest("live source"))
                .toolchainImage(PINNED_IMAGE)
                .command(List.of("./mvnw", "verify"))
                .workingDirectory("/workspace/source")
                .declaredOutputs(List.of("target"))
                .policy(digest("live policy"))
                .permissionScope(Set.of("repo:read"))
                .sandbox("S2", digest("live sandbox"))
                .dataResidency("eu-west")
                .environmentContract(ActionKeyBuilder.EnvironmentContract.of())
                .environment(Map.of())
                .build();
    }

    private static CasAccessPolicy.ReaderContext actionReader(String tenantId) {
        return new CasAccessPolicy.ReaderContext(
                tenantId, Set.of("repo:read"), "eu-west",
                CasAccessPolicy.SecurityTier.INTERNAL, false);
    }

    private static void assertRoleCannotBypassRls() {
        try (Connection connection = adminDataSource.getConnection();
             PreparedStatement query = connection.prepareStatement(
                     "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = ?")) {
            query.setString(1, APP_USER);
            try (ResultSet rows = query.executeQuery()) {
                assertTrue(rows.next());
                assertFalse(rows.getBoolean("rolsuper"));
                assertFalse(rows.getBoolean("rolbypassrls"));
            }
            try (PreparedStatement privileges = connection.prepareStatement("""
                    SELECT has_table_privilege(?, 'cas_action_cache_entries', 'SELECT'),
                           has_table_privilege(?, 'cas_action_cache_entries', 'INSERT'),
                           has_table_privilege(?, 'cas_action_cache_entries', 'UPDATE'),
                           has_table_privilege(?, 'cas_action_cache_entries', 'DELETE'),
                           has_table_privilege(?, 'cas_deletion_manifests', 'DELETE')
                    """)) {
                for (int index = 1; index <= 5; index++) {
                    privileges.setString(index, APP_USER);
                }
                try (ResultSet rows = privileges.executeQuery()) {
                    assertTrue(rows.next());
                    assertTrue(rows.getBoolean(1));
                    assertTrue(rows.getBoolean(2));
                    assertTrue(rows.getBoolean(3));
                    assertFalse(rows.getBoolean(4));
                    assertFalse(rows.getBoolean(5));
                }
            }
        } catch (SQLException error) {
            throw new IllegalStateException(error);
        }
    }

    private static int countCatalogRows(Connection connection, String organizationId)
            throws SQLException {
        try (PreparedStatement query = connection.prepareStatement(
                "SELECT count(*) FROM cas_object_catalog WHERE organization_id = ?")) {
            query.setString(1, organizationId);
            try (ResultSet rows = query.executeQuery()) {
                assertTrue(rows.next());
                return rows.getInt(1);
            }
        }
    }

    private static void setTenant(Connection connection, String organizationId)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT set_config('app.organization_id', ?, true)")) {
            statement.setString(1, organizationId);
            statement.executeQuery().close();
        }
    }

    private static void assertTenantSettingCleared(Connection connection) throws SQLException {
        try (Statement statement = connection.createStatement();
             ResultSet rows = statement.executeQuery(
                     "SELECT nullif(current_setting('app.organization_id', true), '')")) {
            assertTrue(rows.next());
            assertNull(rows.getString(1),
                    "SET LOCAL tenant context must reset at transaction completion");
        }
    }

    private static void insertCatalogRowForAnotherTenant(Connection connection)
            throws SQLException {
        CasDigest injected = digest("cross-tenant direct insert");
        try (PreparedStatement insert = connection.prepareStatement("""
                INSERT INTO cas_object_catalog(
                    organization_id, digest_hex, size_bytes, object_kind,
                    media_type, source_system, schema_version, sensitivity, retention_class,
                    data_residency, security_tier, labels, legal_hold)
                VALUES ('tenant-jdbc-3', ?, ?, 'BLOB',
                    'application/octet-stream', 'adversarial-sql', '1.0', 'PRIVATE_SOURCE',
                    'STANDARD', 'eu-west', 'INTERNAL', '{}'::jsonb, false)
                """)) {
            insert.setString(1, injected.hex());
            insert.setLong(2, injected.sizeBytes());
            insert.executeUpdate();
        }
    }

    private static void assertDirectRootActivationBlockedByTombstone(
            String tenant,
            CasCatalog.ReferenceRoot root
    ) {
        SQLException rejected = assertThrows(SQLException.class, () -> {
            try (Connection connection = dataSource.getConnection()) {
                connection.setAutoCommit(false);
                setTenant(connection, tenant);
                try (PreparedStatement insert = connection.prepareStatement("""
                        INSERT INTO cas_reference_roots (
                            organization_id, root_kind, root_id, digest_hex,
                            size_bytes, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """)) {
                    insert.setString(1, tenant);
                    insert.setString(2, root.kind().name());
                    insert.setString(3, root.rootId());
                    insert.setString(4, root.digest().hex());
                    insert.setLong(5, root.digest().sizeBytes());
                    insert.setTimestamp(6, new java.sql.Timestamp(
                            root.createdAtEpochMillis()));
                    insert.executeUpdate();
                } finally {
                    connection.rollback();
                }
            }
        });
        assertEquals("P0001", rejected.getSQLState());
    }

    private static void assertRuntimeMutationDenied(String sql) {
        SQLException rejected = assertThrows(SQLException.class, () -> {
            try (Connection connection = dataSource.getConnection()) {
                connection.setAutoCommit(false);
                setTenant(connection, "tenant-jdbc-8");
                try (Statement statement = connection.createStatement()) {
                    statement.executeUpdate(sql);
                } finally {
                    connection.rollback();
                }
            }
        });
        assertEquals("42501", rejected.getSQLState());
    }

    private static void assertOwnerAppendOnlyTrigger(String sql) {
        SQLException rejected = assertThrows(SQLException.class, () -> {
            try (Connection connection = adminDataSource.getConnection();
                 Statement statement = connection.createStatement()) {
                statement.executeUpdate(sql);
            }
        });
        assertEquals("P0001", rejected.getSQLState());
    }
}
