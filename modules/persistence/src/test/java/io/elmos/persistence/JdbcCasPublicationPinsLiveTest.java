package io.elmos.persistence;

import io.elmos.cas.*;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import javax.sql.DataSource;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.SQLException;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/** Real PostgreSQL controlled schedules, never enabled for an unconfirmed database. */
@EnabledIfEnvironmentVariable(named = "ELMOS_CAS_TEST_JDBC_URL", matches = "jdbc:postgresql:.*")
class JdbcCasPublicationPinsLiveTest {
    private static DriverManagerDataSource admin;
    private static DataSource application;

    @BeforeAll static void migrate() throws Exception {
        assumeTrue("true".equals(System.getenv("ELMOS_CAS_TEST_DISPOSABLE_CONFIRMED")));
        String url = System.getenv("ELMOS_CAS_TEST_JDBC_URL");
        String user = System.getenv().getOrDefault("ELMOS_CAS_TEST_USERNAME", "postgres");
        String password = System.getenv().getOrDefault("ELMOS_CAS_TEST_PASSWORD", "");
        admin = new DriverManagerDataSource(url, user, password);
        Flyway.configure().dataSource(admin).load().migrate();
        String role = "elmos_cas_pins_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        try (var connection = admin.getConnection(); var statement = connection.createStatement()) {
            statement.execute("CREATE ROLE " + role + " LOGIN PASSWORD 'disposable-test-only' NOSUPERUSER NOBYPASSRLS NOINHERIT");
            statement.execute("GRANT USAGE ON SCHEMA public TO " + role);
            statement.execute("GRANT SELECT, INSERT, UPDATE ON TABLE cas_tenant_lifecycles, cas_resource_lifecycles, "
                    + "cas_object_catalog, cas_resource_bindings, cas_reference_roots, cas_object_deletion_tombstones, "
                    + "cas_object_publication_pins TO " + role);
            statement.execute("GRANT DELETE ON TABLE cas_object_publication_pins, cas_object_deletion_tombstones TO " + role);
        }
        application = new DriverManagerDataSource(url, role, "disposable-test-only");
    }

    private static String tenant() { return "pins-" + UUID.randomUUID(); }
    private static CasCatalog.CatalogEntry entry(String tenant, CasDigest digest) {
        return new CasCatalog.CatalogEntry(tenant, digest, "repo", CasObjectModel.ObjectKind.BLOB,
                "application/octet-stream", "elmos", "1.0", CasObjectModel.Sensitivity.GENERATED_OUTPUT,
                CasObjectModel.RetentionClass.STANDARD, "local", CasAccessPolicy.SecurityTier.INTERNAL,
                Optional.empty(), Map.of(), false, System.currentTimeMillis());
    }
    private static CasCatalog.ReferenceRoot root(String tenant, CasDigest digest) {
        return new CasCatalog.ReferenceRoot(tenant, CasGarbageCollector.RootKind.SNAPSHOT,
                "root-" + digest.hex().substring(0, 12), digest, System.currentTimeMillis());
    }
    private static CasCatalog.ResourceBinding binding(String tenant, CasDigest digest, String repository) {
        return new CasCatalog.ResourceBinding(tenant, CasCatalog.ResourceKind.REPOSITORY,
                repository, digest, System.currentTimeMillis());
    }
    private static void await(CountDownLatch latch) {
        try { if (!latch.await(30, TimeUnit.SECONDS)) throw new AssertionError("controlled schedule timed out"); }
        catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new AssertionError(error); }
    }
    private static long count(String tenant, String predicate) throws Exception {
        try (var connection = admin.getConnection(); var query = connection.prepareStatement(
                "SELECT count(*) FROM cas_object_publication_pins WHERE organization_id = ? AND " + predicate)) {
            query.setString(1, tenant);
            try (var result = query.executeQuery()) { result.next(); return result.getLong(1); }
        }
    }

    @Test void blockedPhysicalWriterUsesNoConnectionAndOtherObjectsOfSameTenantPublish() throws Exception {
        String tenant = tenant();
        var counted = new CountedDataSource(application);
        var catalog = new JdbcCasCatalog(counted);
        var first = CasDigest.ofUtf8("slow");
        var second = CasDigest.ofUtf8("fast");
        var resource = catalog.ensureActiveResource(tenant, CasCatalog.ResourceKind.REPOSITORY, "repo");
        var entered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(2)) {
            var slow = pool.submit(() -> catalog.recordAndBindDurableResource(entry(tenant, first),
                    binding(tenant, first, "repo"), resource, () -> {
                        assertEquals(0, counted.borrowed.get());
                        entered.countDown(); await(release);
                    }));
            try {
                assertTrue(entered.await(30, TimeUnit.SECONDS));
                assertEquals(0, counted.borrowed.get());
                pool.submit(() -> catalog.recordAndBindDurableResource(entry(tenant, second),
                        binding(tenant, second, "repo"), resource, () -> assertEquals(0, counted.borrowed.get())))
                        .get(30, TimeUnit.SECONDS);
                assertTrue(catalog.findBound(tenant, CasCatalog.ResourceKind.REPOSITORY, "repo", second).isPresent());
                assertFalse(slow.isDone(), "the first callback remains intentionally paused");
            } finally { release.countDown(); }
            slow.get(30, TimeUnit.SECONDS);
        }
        assertEquals(0, count(tenant, "pin_state <> 'RELEASED'"));
    }

    @Test void gcAndDirectSqlDeletionCannotCrossUncommittedPhysicalPublication() throws Exception {
        String tenant = tenant();
        var catalog = new JdbcCasCatalog(application);
        var digest = CasDigest.ofUtf8("pinned bytes");
        var store = new InMemoryCasStore("test");
        store.put(digest, "pinned bytes".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        catalog.record(entry(tenant, digest));
        var entered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        try (var pool = Executors.newSingleThreadExecutor()) {
            var publication = pool.submit(() -> catalog.publishDurableReferenceRoots(List.of(root(tenant, digest)), () -> {
                entered.countDown(); await(release);
            }));
            try {
                assertTrue(entered.await(30, TimeUnit.SECONDS));
                assertEquals(CasGarbageCollector.AtomicDeletionOutcome.LIVE_REFERENCE_OR_HOLD,
                        catalog.deleteIfUnreferenced(candidate(tenant, digest), isolated(store)));
                try (var connection = admin.getConnection(); var insert = connection.prepareStatement("""
                        INSERT INTO cas_object_deletion_tombstones
                        (organization_id,digest_hex,size_bytes,deletion_state,created_at,updated_at)
                        VALUES (?, ?, ?, 'PENDING', now(), now())
                        """)) {
                    insert.setString(1, tenant); insert.setString(2, digest.hex()); insert.setLong(3, digest.sizeBytes());
                    assertThrows(SQLException.class, insert::executeUpdate);
                }
                assertTrue(store.contains(digest));
            } finally { release.countDown(); }
            publication.get(30, TimeUnit.SECONDS);
        }
        assertEquals(1, catalog.activeReferenceRoots(tenant).size());
    }

    @Test void retirementDuringIoFencesLatePublicationWithoutBlockingRetirement() throws Exception {
        String tenant = tenant();
        var catalog = new JdbcCasCatalog(application);
        var digest = CasDigest.ofUtf8("retiring bytes");
        var resource = catalog.ensureActiveResource(tenant, CasCatalog.ResourceKind.REPOSITORY, "repo");
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        try (var pool = Executors.newSingleThreadExecutor()) {
            var publication = pool.submit(() -> catalog.recordAndBindDurableResource(entry(tenant, digest),
                    binding(tenant, digest, "repo"), resource, () -> { entered.countDown(); await(release); }));
            try {
                assertTrue(entered.await(30, TimeUnit.SECONDS));
                var retiring = catalog.beginResourceRetirement(tenant, CasCatalog.ResourceKind.REPOSITORY,
                        "repo", System.currentTimeMillis());
                catalog.finalizeResourceRetirement(retiring, System.currentTimeMillis());
            } finally { release.countDown(); }
            assertInstanceOf(IllegalStateException.class,
                    assertThrows(java.util.concurrent.ExecutionException.class,
                            () -> publication.get(30, TimeUnit.SECONDS)).getCause());
        }
        assertTrue(catalog.find(tenant, digest).isEmpty());
        assertEquals(0, count(tenant, "pin_state <> 'RELEASED'"));
    }

    @Test void expiredPinFailsPublicationButOnlyTerminatedOwnerReleasesIt() throws Exception {
        String tenant = tenant();
        var catalog = new JdbcCasCatalog(application, Duration.ofSeconds(1));
        var digest = CasDigest.ofUtf8("expired bytes");
        catalog.record(entry(tenant, digest));
        assertThrows(IllegalStateException.class, () -> catalog.publishDurableReferenceRoots(List.of(root(tenant, digest)), () -> {
            try { Thread.sleep(1200); } catch (InterruptedException error) { throw new AssertionError(error); }
            assertEquals(1, catalog.reconcilePublicationPins(tenant));
            try { assertEquals(1, count(tenant, "pin_state = 'OUTCOME_UNKNOWN'")); }
            catch (Exception error) { throw new AssertionError(error); }
            assertEquals(CasGarbageCollector.AtomicDeletionOutcome.LIVE_REFERENCE_OR_HOLD,
                    catalog.deleteIfUnreferenced(candidate(tenant, digest), isolated(new InMemoryCasStore("test"))));
        }));
        assertEquals(0, count(tenant, "pin_state <> 'RELEASED'"));
        assertTrue(catalog.activeReferenceRoots(tenant).isEmpty());
        new JdbcCasCatalog(application).publishDurableReferenceRoots(List.of(root(tenant, digest)), () -> { });
        assertEquals(1, catalog.activeReferenceRoots(tenant).size(), "retry uses a new epoch-checked pin");
    }

    @Test void genericCallbackErrorLeavesNoRootAndUnknownProviderFence() throws Exception {
        String tenant = tenant();
        var catalog = new JdbcCasCatalog(application);
        var digest = CasDigest.ofUtf8("failing bytes");
        assertThrows(AssertionError.class, () -> catalog.recordAndPublishDurableReferenceRoots(
                entry(tenant, digest), List.of(root(tenant, digest)), () -> { throw new AssertionError("simulated callback error"); }));
        assertTrue(catalog.find(tenant, digest).isEmpty());
        assertTrue(catalog.activeReferenceRoots(tenant).isEmpty());
        assertEquals(1, count(tenant, "pin_state = 'OUTCOME_UNKNOWN'"));
    }

    @Test void exactLocalStoreFailureCanProveIoTerminatedWithoutAUserBoolean() throws Exception {
        String tenant = tenant();
        var catalog = new JdbcCasCatalog(application);
        byte[] bytes = "verified staged local bytes".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        var digest = CasDigest.of(bytes);
        java.nio.file.Path directory = java.nio.file.Files.createTempDirectory("elmos-cas-pin-local-");
        try {
            var store = new LocalDiskCasStore("local", directory);
            java.nio.file.Files.createDirectories(store.pathFor(digest).getParent());
            java.nio.file.Files.write(store.pathFor(digest), new byte[bytes.length]);
            try (var staged = CasContent.capture(digest, new java.io.ByteArrayInputStream(bytes))) {
                assertThrows(CasExceptions.CasCorruptionException.class,
                        () -> catalog.recordAndPublishDurableReferenceRoots(entry(tenant, digest),
                                List.of(root(tenant, digest)), store.publicationEnsurer(Map.of(digest, staged))));
            }
            assertEquals(1, count(tenant, "pin_state = 'RELEASED'"));
            assertTrue(catalog.find(tenant, digest).isEmpty());
        } finally {
            try (var files = java.nio.file.Files.walk(directory)) {
                for (var file : files.sorted(java.util.Comparator.reverseOrder()).toList()) java.nio.file.Files.delete(file);
            }
        }
    }

    @Test void crashedPinsRemainUnknownAndRlsNeverExposesAnotherTenant() throws Exception {
        String tenant = tenant();
        var catalog = new JdbcCasCatalog(application);
        var digest = CasDigest.ofUtf8("crashed bytes");
        catalog.record(entry(tenant, digest));
        // Durable post-crash fixture: no live callback can attest that the old writer has stopped.
        try (var connection = admin.getConnection(); var insert = connection.prepareStatement("""
                INSERT INTO cas_object_publication_pins
                    (organization_id,publication_id,digest_hex,size_bytes,tenant_epoch,lease_expires_at)
                VALUES (?, ?, ?, ?, 1, now() - interval '1 second')
                """)) {
            insert.setString(1, tenant); insert.setString(2, UUID.randomUUID().toString());
            insert.setString(3, digest.hex()); insert.setLong(4, digest.sizeBytes()); insert.executeUpdate();
        }
        assertEquals(1, catalog.reconcilePublicationPins(tenant));
        assertEquals(CasGarbageCollector.AtomicDeletionOutcome.LIVE_REFERENCE_OR_HOLD,
                catalog.deleteIfUnreferenced(candidate(tenant, digest), isolated(new InMemoryCasStore("test"))));
        try (var connection = application.getConnection(); var query = connection.createStatement()) {
            try (var result = query.executeQuery("SELECT count(*) FROM cas_object_publication_pins")) {
                result.next(); assertEquals(0, result.getLong(1));
            }
        }
        assertEquals(1, count(tenant, "pin_state = 'OUTCOME_UNKNOWN'"));
    }

    @Test void abruptWriterProcessExitLeavesDurableFenceInsteadOfInventingCleanup() throws Exception {
        String tenant = tenant();
        var digest = CasDigest.ofUtf8("process crash bytes");
        var catalog = new JdbcCasCatalog(application);
        catalog.record(entry(tenant, digest));
        var runtime = (DriverManagerDataSource) application;
        String classpath = System.getProperty("surefire.test.class.path", System.getProperty("java.class.path"));
        Process process = new ProcessBuilder(System.getProperty("java.home") + "/bin/java", "-cp", classpath,
                CrashWriter.class.getName(), runtime.getUrl(), runtime.getUsername(), tenant)
                .redirectErrorStream(true).start();
        try {
            assertTrue(process.waitFor(60, TimeUnit.SECONDS), "writer crash probe exceeded its budget");
            assertEquals(23, process.exitValue(), new String(process.getInputStream().readAllBytes(),
                    java.nio.charset.StandardCharsets.UTF_8));
        } finally { if (process.isAlive()) process.destroyForcibly(); }
        assertEquals(1, count(tenant, "pin_state = 'ACTIVE'"));
        Thread.sleep(1200);
        assertEquals(1, catalog.reconcilePublicationPins(tenant));
        assertEquals(CasGarbageCollector.AtomicDeletionOutcome.LIVE_REFERENCE_OR_HOLD,
                catalog.deleteIfUnreferenced(candidate(tenant, digest), isolated(new InMemoryCasStore("test"))));
        assertEquals(1, count(tenant, "pin_state = 'OUTCOME_UNKNOWN'"));
    }

    public static final class CrashWriter {
        public static void main(String[] args) {
            var source = new DriverManagerDataSource(args[0], args[1], "disposable-test-only");
            var catalog = new JdbcCasCatalog(source, Duration.ofSeconds(1));
            catalog.publishDurableReferenceRoots(List.of(root(args[2], CasDigest.ofUtf8("process crash bytes"))),
                    () -> Runtime.getRuntime().halt(23));
            throw new AssertionError("crash callback did not run");
        }
    }

    @Test void unresolvedPinBudgetRejectsBeforeAnyPhysicalCallback() throws Exception {
        String tenant = tenant();
        var catalog = new JdbcCasCatalog(application);
        var digest = CasDigest.ofUtf8("pin budget");
        catalog.record(entry(tenant, digest));
        try (var connection = admin.getConnection(); var insert = connection.prepareStatement("""
                INSERT INTO cas_object_publication_pins
                    (organization_id,publication_id,digest_hex,size_bytes,tenant_epoch,lease_expires_at)
                VALUES (?, ?, ?, ?, 1, now() + interval '1 hour')
                """)) {
            for (int index = 0; index < 128; index++) {
                insert.setString(1, tenant); insert.setString(2, UUID.randomUUID().toString());
                insert.setString(3, digest.hex()); insert.setLong(4, digest.sizeBytes()); insert.addBatch();
            }
            insert.executeBatch();
        }
        var entered = new java.util.concurrent.atomic.AtomicBoolean();
        assertEquals("CAS_PUBLICATION_PIN_CAPACITY_EXCEEDED", assertThrows(IllegalStateException.class,
                () -> catalog.publishDurableReferenceRoots(List.of(root(tenant, digest)), () -> entered.set(true))).getMessage());
        assertFalse(entered.get());
        assertEquals(128, count(tenant, "pin_state <> 'RELEASED'"));
    }

    @Test void tenantRevocationDuringIoPreventsPublicationEvenIfResourceEpochDidNotChange() throws Exception {
        String tenant = tenant();
        var catalog = new JdbcCasCatalog(application);
        var digest = CasDigest.ofUtf8("revoked tenant bytes");
        var resource = catalog.ensureActiveResource(tenant, CasCatalog.ResourceKind.REPOSITORY, "repo");
        assertThrows(IllegalStateException.class, () -> catalog.recordAndBindDurableResource(entry(tenant, digest),
                binding(tenant, digest, "repo"), resource, () -> {
                    try (var connection = admin.getConnection(); var statement = connection.prepareStatement(
                            "UPDATE cas_tenant_lifecycles SET lifecycle_state = 'RETIRING' WHERE organization_id = ?")) {
                        statement.setString(1, tenant); assertEquals(1, statement.executeUpdate());
                    } catch (SQLException error) { throw new AssertionError(error); }
                }));
        assertTrue(catalog.find(tenant, digest).isEmpty());
        assertEquals(0, count(tenant, "pin_state <> 'RELEASED'"));
    }

    private static CasGarbageCollector.Candidate candidate(String tenant, CasDigest digest) {
        return new CasGarbageCollector.Candidate(digest, digest.sizeBytes(), tenant, "TEST_UNREACHABLE");
    }
    private static TenantCasStore isolated(CasStore store) {
        return new TenantCasStore() {
            public CasStore forTenant(String tenant) { return store; }
            public String atRestProtection() { return "TEST_ONLY"; }
            public String physicalNamespace() { return "TEST_ONLY"; }
            public DeletionScope deletionScope() { return DeletionScope.TENANT_ISOLATED; }
        };
    }

    private static final class CountedDataSource extends org.springframework.jdbc.datasource.AbstractDataSource {
        private final DataSource delegate;
        final AtomicInteger borrowed = new AtomicInteger();
        CountedDataSource(DataSource delegate) { this.delegate = delegate; }
        @Override public Connection getConnection() throws SQLException { return wrap(delegate.getConnection()); }
        @Override public Connection getConnection(String user, String password) throws SQLException {
            return wrap(delegate.getConnection(user, password));
        }
        private Connection wrap(Connection connection) {
            borrowed.incrementAndGet();
            var closed = new java.util.concurrent.atomic.AtomicBoolean();
            return (Connection) Proxy.newProxyInstance(Connection.class.getClassLoader(), new Class<?>[]{Connection.class},
                    (proxy, method, arguments) -> {
                        try { return method.invoke(connection, arguments); }
                        catch (InvocationTargetException error) { throw error.getCause(); }
                        finally {
                            if (method.getName().equals("close") && closed.compareAndSet(false, true)) borrowed.decrementAndGet();
                        }
                    });
        }
    }
}
