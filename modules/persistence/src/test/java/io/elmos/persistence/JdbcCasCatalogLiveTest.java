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
                    + "cas_quarantine_events, cas_action_cache_entries, "
                    + "cas_action_cache_invalidations, cas_action_cache_quarantined_nodes TO "
                    + APP_USER);
            statement.execute("GRANT INSERT, UPDATE ON TABLE cas_object_catalog, "
                    + "cas_object_placement, cas_resource_bindings, cas_reference_roots, "
                    + "cas_action_cache_entries TO " + APP_USER);
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

    @Test void anEntryRoundTripsThroughTheRealSchema() {
        var catalog = new JdbcCasCatalog(dataSource);
        CasDigest object = digest("jdbc payload");
        catalog.record(entry("tenant-jdbc-1", object, CasObjectModel.Sensitivity.GENERATED_OUTPUT,
                Optional.of(digest("provenance"))));

        var found = catalog.find("tenant-jdbc-1", object).orElseThrow();
        assertEquals(object.hex(), found.digest().hex());
        assertEquals(object.sizeBytes(), found.digest().sizeBytes());
        assertEquals(CasObjectModel.Sensitivity.GENERATED_OUTPUT, found.sensitivity());
        assertEquals(CasAccessPolicy.SecurityTier.INTERNAL, found.securityTier());
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
            assertThrows(SQLException.class, () -> insertCatalogRowForAnotherTenant(connection));
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
        catalog.addReferenceRoot(new CasCatalog.ReferenceRoot("tenant-jdbc-7",
                CasGarbageCollector.RootKind.SNAPSHOT, "snap-1", object, 1_800_000_000_000L));
        assertEquals(1, catalog.activeReferenceRoots("tenant-jdbc-7").size());

        catalog.releaseReferenceRoot("tenant-jdbc-7", CasGarbageCollector.RootKind.SNAPSHOT, "snap-1",
                1_800_000_100_000L);
        assertTrue(catalog.activeReferenceRoots("tenant-jdbc-7").isEmpty());
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
                    organization_id, digest_hex, size_bytes, project_id, object_kind,
                    media_type, source_system, schema_version, sensitivity, retention_class,
                    data_residency, security_tier, labels, legal_hold)
                VALUES ('tenant-jdbc-3', ?, ?, 'project-a', 'BLOB',
                    'application/octet-stream', 'adversarial-sql', '1.0', 'PRIVATE_SOURCE',
                    'STANDARD', 'eu-west', 'INTERNAL', '{}'::jsonb, false)
                """)) {
            insert.setString(1, injected.hex());
            insert.setLong(2, injected.sizeBytes());
            insert.executeUpdate();
        }
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
