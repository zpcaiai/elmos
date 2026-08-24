package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import io.elmos.persistence.JdbcSnapshotStore;
import io.elmos.persistence.JdbcWebhookDeliveryStore;
import io.elmos.scm.WebhookIngestionService;
import io.elmos.snapshot.SnapshotModel;
import io.elmos.snapshot.SnapshotPorts;
import io.elmos.snapshot.SnapshotRootReconciliation;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Types;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Real PostgreSQL proof for V68 tenant RLS, transitions and adapter timestamp binding. */
@Testcontainers(disabledWithoutDocker = true)
class JdbcSnapshotLifecycleAdapterLiveTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:17.5-alpine");

    private static final String APP_USER = "elmos_snapshot_live_app";
    private static final String APP_PASSWORD = "snapshot-live-test-only";
    private static final Instant CLOCK_TIME =
            Instant.parse("2026-08-24T13:15:16.654321Z");
    private static final ObjectMapper MAPPER = new ObjectMapper()
            .findAndRegisterModules()
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    private static HikariDataSource applicationDataSource;
    private static JdbcClient jdbc;
    private static JdbcSnapshotLifecycleAdapter adapter;
    private static TransactionTemplate transactions;

    @BeforeAll
    static void setUpDatabase() throws SQLException {
        Flyway.configure()
                .dataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())
                .defaultSchema("public")
                .load()
                .migrate();
        try (Connection admin = adminConnection(); Statement statement = admin.createStatement()) {
            statement.execute("CREATE ROLE " + APP_USER
                    + " LOGIN PASSWORD '" + APP_PASSWORD
                    + "' NOSUPERUSER NOBYPASSRLS NOINHERIT");
            statement.execute("GRANT USAGE ON SCHEMA public TO " + APP_USER);
            statement.execute("GRANT SELECT, INSERT ON TABLE repository_snapshots TO "
                    + APP_USER);
            statement.execute("GRANT UPDATE (status) ON TABLE repository_snapshots TO "
                    + APP_USER);
            statement.execute("GRANT SELECT, INSERT, UPDATE ON TABLE "
                    + "snapshot_root_reconciliations TO " + APP_USER);
            statement.execute("GRANT SELECT, INSERT ON TABLE github_webhook_deliveries TO "
                    + APP_USER);
            statement.execute("GRANT UPDATE (duplicate_count) ON TABLE "
                    + "github_webhook_deliveries TO " + APP_USER);
            statement.execute("GRANT INSERT ON TABLE outbox_events TO " + APP_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION "
                    + "elmos_resolve_github_webhook_organization(bigint, bigint) TO "
                    + APP_USER);
            statement.executeUpdate("""
                    INSERT INTO organizations(organization_id) VALUES
                        ('snapshot-live-a'), ('snapshot-live-b'), ('snapshot-live-c')
                    """);
            statement.executeUpdate("""
                    INSERT INTO repositories(
                        repository_id, organization_id, scm_provider, external_id, default_branch)
                    VALUES
                        ('snapshot-repo-a', 'snapshot-live-a', 'github', 'native-a', 'main'),
                        ('snapshot-repo-b', 'snapshot-live-b', 'github', 'native-b', 'main'),
                        ('snapshot-repo-c', 'snapshot-live-c', 'github', 'native-c', 'main')
                    """);
            statement.executeUpdate("""
                    INSERT INTO scm_connections(
                        connection_id, organization_id, provider, status, created_at, updated_at)
                    VALUES
                        ('snapshot-connection-a', 'snapshot-live-a', 'GITHUB', 'ACTIVE', now(), now()),
                        ('snapshot-connection-b', 'snapshot-live-b', 'GITHUB', 'ACTIVE', now(), now())
                    """);
            statement.executeUpdate("""
                    INSERT INTO github_app_installations(
                        organization_id, installation_id, connection_id,
                        github_installation_id, account_external_id, account_login,
                        target_type, installed_at, permissions, repository_selection,
                        status, last_synced_at)
                    VALUES
                        ('snapshot-live-a', 'snapshot-install-a', 'snapshot-connection-a',
                         91001, 81001, 'snapshot-a', 'Organization', now(),
                         '{"contents":"read"}'::jsonb, 'selected', 'ACTIVE', now()),
                        ('snapshot-live-b', 'snapshot-install-b', 'snapshot-connection-b',
                         91002, 81002, 'snapshot-b', 'Organization', now(),
                         '{"contents":"read"}'::jsonb, 'selected', 'ACTIVE', now())
                    """);
            statement.executeUpdate("""
                    INSERT INTO scm_repositories(
                        organization_id, scm_repository_id, repository_id, installation_id,
                        github_repository_id, owner_login, repository_name, full_name,
                        clone_url, html_url, default_branch, visibility, archived, disabled,
                        fork, authorization_status, synced_at)
                    VALUES
                        ('snapshot-live-a', 'snapshot-scm-repo-a', 'snapshot-repo-a',
                         'snapshot-install-a', 71001, 'snapshot-a', 'repo-a', 'snapshot-a/repo-a',
                         'https://github.com/snapshot-a/repo-a.git',
                         'https://github.com/snapshot-a/repo-a', 'main', 'private',
                         false, false, false, 'AUTHORIZED', now()),
                        ('snapshot-live-b', 'snapshot-scm-repo-b', 'snapshot-repo-b',
                         'snapshot-install-b', 71002, 'snapshot-b', 'repo-b', 'snapshot-b/repo-b',
                         'https://github.com/snapshot-b/repo-b.git',
                         'https://github.com/snapshot-b/repo-b', 'main', 'private',
                         false, false, false, 'AUTHORIZED', now())
                    """);
        }

        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(POSTGRES.getJdbcUrl());
        config.setUsername(APP_USER);
        config.setPassword(APP_PASSWORD);
        config.setMaximumPoolSize(1);
        config.setMinimumIdle(1);
        config.setPoolName("snapshot-lifecycle-live");
        applicationDataSource = new HikariDataSource(config);
        jdbc = JdbcClient.create(applicationDataSource);
        adapter = new JdbcSnapshotLifecycleAdapter(
                jdbc,
                new JdbcSnapshotStore(jdbc),
                MAPPER,
                Clock.fixed(CLOCK_TIME, ZoneOffset.UTC));
        transactions = new TransactionTemplate(
                new DataSourceTransactionManager(applicationDataSource));
    }

    @AfterAll
    static void closePool() {
        if (applicationDataSource != null) {
            applicationDataSource.close();
        }
    }

    @Test void realCoordinatorRoundTripResetsTenantContextOnTheSamePooledBackend()
            throws Exception {
        assertRlsIsForcedAndRoleCannotBypass();
        SnapshotRootReconciliation pending = pending(
                "attempt-roundtrip", "operation-roundtrip",
                snapshot("snap-roundtrip", "snapshot-live-a", "snapshot-repo-a", 'a'));
        assertTrue(MAPPER.writeValueAsString(pending).contains(
                "\"recordedAt\":\"2026-08-24T12:34:56.123456Z\""),
                "the production journal contract requires ISO-8601 string timestamps");
        AtomicInteger transactionBackend = new AtomicInteger();

        inTransaction(() -> {
            transactionBackend.set(jdbc.sql("select pg_backend_pid()")
                    .query(Integer.class).single());
            adapter.recordPending(pending);
            return null;
        });

        try (Connection connection = applicationDataSource.getConnection()) {
            assertEquals(transactionBackend.get(), backendPid(connection));
            assertTenantSettingCleared(connection);
            assertEquals(0, scalarInt(connection,
                    "SELECT count(*) FROM snapshot_root_reconciliations"),
                    "a connection without tenant context must not see journal rows");
        }

        SnapshotModel.RepositorySnapshot stored = inTransaction(
                () -> adapter.saveAvailable(pending));
        assertEquals(pending.snapshot(), stored);
        JdbcSnapshotStore independentLookup = new JdbcSnapshotStore(jdbc);
        assertEquals(stored, inTransaction(() -> independentLookup.findReusable(
                "snapshot-live-a", "snapshot-repo-a",
                stored.resolvedCommitSha(), stored.snapshotSchemaVersion())));
        assertNull(inTransaction(() -> independentLookup.findReusable(
                "snapshot-live-b", "snapshot-repo-a",
                stored.resolvedCommitSha(), stored.snapshotSchemaVersion())));
        try (Connection connection = applicationDataSource.getConnection()) {
            assertTenantSettingCleared(connection);
        }
        List<SnapshotRootReconciliation> actionable = inTransaction(
                () -> adapter.pending("snapshot-live-a", 10));
        SnapshotRootReconciliation committed = find(actionable, pending.reconciliationId());
        assertEquals(SnapshotRootReconciliation.Phase.DATABASE_COMMITTED, committed.phase());
        assertEquals(pending.snapshot().snapshotId(), committed.durableSnapshotId());
        assertTrue(inTransaction(() -> adapter.pending("snapshot-live-b", 10)).stream()
                .noneMatch(item -> item.reconciliationId().equals(pending.reconciliationId())));

        inTransaction(() -> {
            adapter.markResolved("snapshot-live-a", pending.reconciliationId());
            return null;
        });
        assertTrue(inTransaction(() -> adapter.pending("snapshot-live-a", 10)).stream()
                .noneMatch(item -> item.reconciliationId().equals(pending.reconciliationId())));

        try (Connection admin = adminConnection(); PreparedStatement query = admin.prepareStatement("""
                SELECT phase, recorded_at, updated_at, resolved_at
                  FROM snapshot_root_reconciliations
                 WHERE organization_id = 'snapshot-live-a' AND attempt_id = ?
                """)) {
            query.setString(1, pending.reconciliationId());
            try (ResultSet rows = query.executeQuery()) {
                assertTrue(rows.next());
                assertEquals("RESOLVED", rows.getString("phase"));
                assertEquals(pending.recordedAt(),
                        rows.getObject("recorded_at", OffsetDateTime.class).toInstant());
                assertEquals(CLOCK_TIME,
                        rows.getObject("updated_at", OffsetDateTime.class).toInstant());
                assertEquals(CLOCK_TIME,
                        rows.getObject("resolved_at", OffsetDateTime.class).toInstant());
            }
        }
    }

    @Test void stalePendingRowsBecomeExplicitCommitFailuresWithinTheirTenant() {
        SnapshotRootReconciliation stale = pending(
                "attempt-stale", "operation-stale",
                snapshot("snap-stale", "snapshot-live-c", "snapshot-repo-c", '8'));
        inTransaction(() -> {
            adapter.recordPending(stale);
            return null;
        });

        int failed = inTransaction(() -> adapter.failStalePending(
                "snapshot-live-c", Instant.parse("2026-08-24T13:00:00Z"), 10));

        assertEquals(1, failed);
        SnapshotRootReconciliation recovered = find(
                inTransaction(() -> adapter.pending("snapshot-live-c", 10)),
                stale.reconciliationId());
        assertEquals(SnapshotRootReconciliation.Phase.COMMIT_FAILED, recovered.phase());
        assertEquals(stale.recordedAt(), recovered.recordedAt());
    }

    @Test void signedWebhookStorageResolvesTenantAndRejectsCrossTenantResources()
            throws Exception {
        JdbcWebhookDeliveryStore store = new JdbcWebhookDeliveryStore(jdbc, MAPPER);
        WebhookIngestionService.Delivery delivery = new WebhookIngestionService.Delivery(
                "delivery-live-a", "push", null, 71001L, 91001L,
                "9".repeat(64), Instant.parse("2026-08-24T13:00:00Z"),
                "GithubPushObserved");

        assertTrue(inTransaction(() -> store.recordAndEnqueueIfAbsent(delivery)));
        assertFalse(inTransaction(() -> store.recordAndEnqueueIfAbsent(delivery)));

        try (Connection admin = adminConnection(); PreparedStatement query = admin.prepareStatement("""
                SELECT delivery.organization_id, delivery.duplicate_count,
                       outbox.organization_id, outbox.aggregate_id
                  FROM github_webhook_deliveries delivery
                  JOIN outbox_events outbox
                    ON outbox.aggregate_id = delivery.webhook_delivery_id
                 WHERE delivery.github_delivery_id = 'delivery-live-a'
                """)) {
            try (ResultSet rows = query.executeQuery()) {
                assertTrue(rows.next());
                assertEquals("snapshot-live-a", rows.getString(1));
                assertEquals(1, rows.getInt(2));
                assertEquals("snapshot-live-a", rows.getString(3));
                assertEquals(36, rows.getString(4).length());
                assertFalse(rows.next());
            }
        }

        WebhookIngestionService.Delivery crossed = new WebhookIngestionService.Delivery(
                "delivery-crossed", "push", null, 71002L, 91001L,
                "8".repeat(64), Instant.parse("2026-08-24T13:00:01Z"),
                "GithubPushObserved");
        assertThrows(WebhookIngestionService.ResourceBindingException.class,
                () -> inTransaction(() -> store.recordAndEnqueueIfAbsent(crossed)));

        WebhookIngestionService.Delivery unknown = new WebhookIngestionService.Delivery(
                "delivery-unknown", "push", null, 71999L, 91999L,
                "7".repeat(64), Instant.parse("2026-08-24T13:00:02Z"),
                "GithubPushObserved");
        assertThrows(WebhookIngestionService.ResourceBindingException.class,
                () -> inTransaction(() -> store.recordAndEnqueueIfAbsent(unknown)));
    }

    @Test void organizationAndAttemptFormTheTransitionAuthority() {
        String sharedAttempt = "same-attempt-across-tenants";
        SnapshotRootReconciliation tenantA = pending(
                sharedAttempt, "operation-a",
                snapshot("snap-same-a", "snapshot-live-a", "snapshot-repo-a", 'b'));
        SnapshotRootReconciliation tenantB = pending(
                sharedAttempt, "operation-b",
                snapshot("snap-same-b", "snapshot-live-b", "snapshot-repo-b", 'c'));
        inTransaction(() -> {
            adapter.recordPending(tenantA);
            return null;
        });
        inTransaction(() -> {
            adapter.recordPending(tenantB);
            return null;
        });

        inTransaction(() -> {
            adapter.markCommitFailed("snapshot-live-a", sharedAttempt);
            return null;
        });
        assertEquals(SnapshotRootReconciliation.Phase.COMMIT_FAILED,
                find(inTransaction(() -> adapter.pending("snapshot-live-a", 20)), sharedAttempt).phase());
        assertEquals(SnapshotRootReconciliation.Phase.PENDING,
                find(inTransaction(() -> adapter.pending("snapshot-live-b", 20)), sharedAttempt).phase());
        assertThrows(IllegalStateException.class, () -> inTransaction(() -> {
            adapter.markDatabaseCommitted("snapshot-live-a", sharedAttempt, "snap-same-a");
            return null;
        }));
    }

    @Test void migrationRejectsTerminalInsertMalformedPayloadForeignTenantAndDelete()
            throws Exception {
        SnapshotRootReconciliation terminal = pending(
                "attempt-terminal", "operation-terminal",
                snapshot("snap-terminal", "snapshot-live-a", "snapshot-repo-a", 'd')).failed();
        SQLException terminalFailure = assertThrows(SQLException.class,
                () -> directInsert(terminal, MAPPER.writeValueAsString(terminal)));
        assertEquals("P0001", terminalFailure.getSQLState());

        SnapshotRootReconciliation malformed = pending(
                "attempt-malformed", "operation-malformed",
                snapshot("snap-malformed", "snapshot-live-a", "snapshot-repo-a", 'e'));
        assertThrows(SQLException.class, () -> directInsert(malformed, "{}"));

        SnapshotRootReconciliation foreignRepository = pending(
                "attempt-foreign-repository", "operation-foreign-repository",
                snapshot("snap-foreign", "snapshot-live-a", "snapshot-repo-b", 'f'));
        assertThrows(RuntimeException.class, () -> inTransaction(() -> {
            adapter.recordPending(foreignRepository);
            return null;
        }));

        SnapshotModel.RepositorySnapshot foreignSnapshot = snapshot(
                "snap-foreign-row", "snapshot-live-a", "snapshot-repo-b", '6');
        JdbcSnapshotStore snapshotStore = new JdbcSnapshotStore(jdbc);
        assertThrows(RuntimeException.class, () -> inTransaction(
                () -> snapshotStore.saveAvailable(foreignSnapshot)));

        SnapshotRootReconciliation deletable = pending(
                "attempt-delete", "operation-delete",
                snapshot("snap-delete", "snapshot-live-a", "snapshot-repo-a", '1'));
        inTransaction(() -> {
            adapter.recordPending(deletable);
            return null;
        });
        SnapshotRootReconciliation malformedRetention = pending(
                "attempt-malformed-retention", "operation-malformed-retention",
                snapshot("snap-malformed-retention", "snapshot-live-a", "snapshot-repo-a", '4'));
        String malformedGenerations = "{\"Bad\":-1}";
        assertThrows(SQLException.class, () -> directInsert(
                malformedRetention,
                payloadWithGenerations(malformedRetention, malformedGenerations),
                malformedGenerations));

        SQLException deleteFailure = assertThrows(SQLException.class,
                () -> directDelete("snapshot-live-a", deletable.reconciliationId()));
        assertEquals("42501", deleteFailure.getSQLState(),
                "the runtime role must not receive DELETE on the append-preserving journal");
        SQLException ownerDeleteFailure = assertThrows(SQLException.class,
                () -> directAdminDelete("snapshot-live-a", deletable.reconciliationId()));
        assertEquals("P0001", ownerDeleteFailure.getSQLState(),
                "the transition trigger remains a second line of defense for privileged callers");

        SnapshotModel.RepositorySnapshot protectedSnapshot = snapshot(
                "snap-protected", "snapshot-live-a", "snapshot-repo-a", '7');
        inTransaction(() -> {
            new JdbcSnapshotStore(jdbc).saveAvailable(protectedSnapshot);
            return null;
        });

        SQLException immutableUpdate = assertThrows(SQLException.class,
                () -> directSnapshotContentUpdate("snapshot-live-a", "snap-protected"));
        assertEquals("42501", immutableUpdate.getSQLState());
        SQLException ownerImmutableUpdate = assertThrows(SQLException.class,
                () -> directAdminSnapshotContentUpdate("snapshot-live-a", "snap-protected"));
        assertEquals("P0001", ownerImmutableUpdate.getSQLState());
        SQLException snapshotDelete = assertThrows(SQLException.class,
                () -> directSnapshotDelete("snapshot-live-a", "snap-protected"));
        assertEquals("42501", snapshotDelete.getSQLState());
        SQLException ownerSnapshotDelete = assertThrows(SQLException.class,
                () -> directAdminSnapshotDelete("snapshot-live-a", "snap-protected"));
        assertEquals("P0001", ownerSnapshotDelete.getSQLState());
    }

    private static <T> T inTransaction(Supplier<T> operation) {
        return transactions.execute(status -> operation.get());
    }

    private static SnapshotRootReconciliation pending(
            String attemptId,
            String logicalOperationId,
            SnapshotModel.RepositorySnapshot snapshot
    ) {
        return new SnapshotRootReconciliation(
                attemptId,
                logicalOperationId,
                SnapshotRootReconciliation.Kind.CAPTURE_COMMIT,
                SnapshotRootReconciliation.Phase.PENDING,
                snapshot,
                new SnapshotPorts.ArtifactRetention(snapshot.snapshotId(), Map.of("cas", 1L)),
                null,
                Instant.parse("2026-08-24T12:34:56.123456Z"));
    }

    private static SnapshotModel.RepositorySnapshot snapshot(
            String snapshotId,
            String organizationId,
            String repositoryId,
            char digestSeed
    ) {
        String archiveDigest = Character.toString(digestSeed).repeat(64);
        String manifestDigest = "3".repeat(64);
        return new SnapshotModel.RepositorySnapshot(
                snapshotId,
                organizationId,
                repositoryId,
                "refs/heads/main",
                Character.toString(digestSeed).repeat(40),
                "2".repeat(40),
                "cas://sha256/" + archiveDigest + "/4096",
                archiveDigest,
                4096,
                "cas://sha256/" + manifestDigest + "/128",
                manifestDigest,
                1,
                SnapshotModel.Status.AVAILABLE,
                Instant.parse("2026-08-24T12:30:00.123456Z"));
    }

    private static SnapshotRootReconciliation find(
            List<SnapshotRootReconciliation> rows,
            String attemptId
    ) {
        return rows.stream()
                .filter(item -> item.reconciliationId().equals(attemptId))
                .findFirst()
                .orElseThrow();
    }

    private static void assertRlsIsForcedAndRoleCannotBypass() throws SQLException {
        try (Connection admin = adminConnection(); PreparedStatement query = admin.prepareStatement("""
                SELECT c.relrowsecurity, c.relforcerowsecurity, r.rolsuper, r.rolbypassrls
                  FROM pg_class c CROSS JOIN pg_roles r
                 WHERE c.oid = 'snapshot_root_reconciliations'::regclass AND r.rolname = ?
                """)) {
            query.setString(1, APP_USER);
            try (ResultSet rows = query.executeQuery()) {
                assertTrue(rows.next());
                assertTrue(rows.getBoolean("relrowsecurity"));
                assertTrue(rows.getBoolean("relforcerowsecurity"));
                assertFalse(rows.getBoolean("rolsuper"));
                assertFalse(rows.getBoolean("rolbypassrls"));
            }
        }
        try (Connection admin = adminConnection(); PreparedStatement query = admin.prepareStatement("""
                SELECT has_table_privilege(?, 'repository_snapshots', 'SELECT'),
                       has_table_privilege(?, 'repository_snapshots', 'INSERT'),
                       has_table_privilege(?, 'repository_snapshots', 'UPDATE'),
                       has_table_privilege(?, 'repository_snapshots', 'DELETE'),
                       has_column_privilege(?, 'repository_snapshots', 'status', 'UPDATE'),
                       has_column_privilege(?, 'repository_snapshots', 'archive_sha256', 'UPDATE')
                """)) {
            for (int index = 1; index <= 6; index++) {
                query.setString(index, APP_USER);
            }
            try (ResultSet rows = query.executeQuery()) {
                assertTrue(rows.next());
                assertTrue(rows.getBoolean(1));
                assertTrue(rows.getBoolean(2));
                assertFalse(rows.getBoolean(3));
                assertFalse(rows.getBoolean(4));
                assertTrue(rows.getBoolean(5));
                assertFalse(rows.getBoolean(6));
            }
        }
        try (Connection admin = adminConnection(); PreparedStatement query = admin.prepareStatement("""
                SELECT has_table_privilege(?, 'snapshot_root_reconciliations', 'SELECT'),
                       has_table_privilege(?, 'snapshot_root_reconciliations', 'INSERT'),
                       has_table_privilege(?, 'snapshot_root_reconciliations', 'UPDATE'),
                       has_table_privilege(?, 'snapshot_root_reconciliations', 'DELETE')
                """)) {
            for (int index = 1; index <= 4; index++) {
                query.setString(index, APP_USER);
            }
            try (ResultSet rows = query.executeQuery()) {
                assertTrue(rows.next());
                assertTrue(rows.getBoolean(1));
                assertTrue(rows.getBoolean(2));
                assertTrue(rows.getBoolean(3));
                assertFalse(rows.getBoolean(4));
            }
        }
    }

    private static void directInsert(
            SnapshotRootReconciliation reconciliation,
            String payload
    ) throws SQLException {
        try {
            directInsert(reconciliation, payload,
                    MAPPER.writeValueAsString(reconciliation.retention().generations()));
        } catch (SQLException failure) {
            throw failure;
        } catch (Exception failure) {
            throw new IllegalStateException(failure);
        }
    }

    private static void directInsert(
            SnapshotRootReconciliation reconciliation,
            String payload,
            String generations
    ) throws SQLException {
        try (Connection connection = applicationDataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                setTenant(connection, reconciliation.snapshot().organizationId());
                try (PreparedStatement insert = connection.prepareStatement("""
                        INSERT INTO snapshot_root_reconciliations(
                            organization_id, repository_id, attempt_id, logical_operation_id,
                            snapshot_id, reconciliation_kind, phase, durable_snapshot_id,
                            reconciliation_payload, retention_generations, recorded_at, updated_at,
                            resolved_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, cast(? as jsonb), cast(? as jsonb), ?, ?, ?)
                        """)) {
                    insert.setString(1, reconciliation.snapshot().organizationId());
                    insert.setString(2, reconciliation.snapshot().repositoryId());
                    insert.setString(3, reconciliation.reconciliationId());
                    insert.setString(4, reconciliation.logicalOperationId());
                    insert.setString(5, reconciliation.snapshot().snapshotId());
                    insert.setString(6, reconciliation.kind().name());
                    insert.setString(7, reconciliation.phase().name());
                    if (reconciliation.durableSnapshotId() == null) {
                        insert.setNull(8, Types.VARCHAR);
                    } else {
                        insert.setString(8, reconciliation.durableSnapshotId());
                    }
                    insert.setString(9, payload);
                    insert.setString(10, generations);
                    OffsetDateTime recorded = reconciliation.recordedAt().atOffset(ZoneOffset.UTC);
                    insert.setObject(11, recorded);
                    insert.setObject(12, recorded);
                    insert.setNull(13, Types.TIMESTAMP_WITH_TIMEZONE);
                    insert.executeUpdate();
                }
                connection.commit();
            } catch (Exception failure) {
                connection.rollback();
                if (failure instanceof SQLException sql) {
                    throw sql;
                }
                throw new IllegalStateException(failure);
            }
        }
    }

    private static String payloadWithGenerations(
            SnapshotRootReconciliation reconciliation,
            String generations
    ) throws Exception {
        ObjectNode payload = MAPPER.valueToTree(reconciliation);
        ObjectNode retention = (ObjectNode) payload.get("retention");
        retention.set("generations", MAPPER.readTree(generations));
        return MAPPER.writeValueAsString(payload);
    }

    private static void directDelete(String organizationId, String attemptId) throws SQLException {
        try (Connection connection = applicationDataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                setTenant(connection, organizationId);
                try (PreparedStatement delete = connection.prepareStatement("""
                        DELETE FROM snapshot_root_reconciliations
                         WHERE organization_id = ? AND attempt_id = ?
                        """)) {
                    delete.setString(1, organizationId);
                    delete.setString(2, attemptId);
                    delete.executeUpdate();
                }
                connection.commit();
            } catch (SQLException failure) {
                connection.rollback();
                throw failure;
            }
        }
    }

    private static void directAdminDelete(String organizationId, String attemptId)
            throws SQLException {
        try (Connection connection = adminConnection(); PreparedStatement delete =
                     connection.prepareStatement("""
                             DELETE FROM snapshot_root_reconciliations
                              WHERE organization_id = ? AND attempt_id = ?
                             """)) {
            delete.setString(1, organizationId);
            delete.setString(2, attemptId);
            delete.executeUpdate();
        }
    }

    private static void directSnapshotContentUpdate(String organizationId, String snapshotId)
            throws SQLException {
        directSnapshotMutation(applicationDataSource.getConnection(), organizationId,
                "UPDATE repository_snapshots SET archive_sha256 = '0' || "
                        + "substring(archive_sha256 from 2) WHERE snapshot_id = ?",
                snapshotId);
    }

    private static void directAdminSnapshotContentUpdate(
            String organizationId, String snapshotId) throws SQLException {
        directSnapshotMutation(adminConnection(), organizationId,
                "UPDATE repository_snapshots SET archive_sha256 = '0' || "
                        + "substring(archive_sha256 from 2) WHERE snapshot_id = ?",
                snapshotId);
    }

    private static void directSnapshotDelete(String organizationId, String snapshotId)
            throws SQLException {
        directSnapshotMutation(applicationDataSource.getConnection(), organizationId,
                "DELETE FROM repository_snapshots WHERE snapshot_id = ?", snapshotId);
    }

    private static void directAdminSnapshotDelete(String organizationId, String snapshotId)
            throws SQLException {
        directSnapshotMutation(adminConnection(), organizationId,
                "DELETE FROM repository_snapshots WHERE snapshot_id = ?", snapshotId);
    }

    private static void directSnapshotMutation(
            Connection connection, String organizationId, String sql, String snapshotId
    ) throws SQLException {
        try (connection) {
            connection.setAutoCommit(false);
            try {
                setTenant(connection, organizationId);
                try (PreparedStatement mutation = connection.prepareStatement(sql)) {
                    mutation.setString(1, snapshotId);
                    mutation.executeUpdate();
                }
                connection.commit();
            } catch (SQLException failure) {
                connection.rollback();
                throw failure;
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

    private static int backendPid(Connection connection) throws SQLException {
        return scalarInt(connection, "SELECT pg_backend_pid()");
    }

    private static int scalarInt(Connection connection, String sql) throws SQLException {
        try (Statement statement = connection.createStatement();
             ResultSet rows = statement.executeQuery(sql)) {
            assertTrue(rows.next());
            return rows.getInt(1);
        }
    }

    private static void assertTenantSettingCleared(Connection connection) throws SQLException {
        try (Statement statement = connection.createStatement();
             ResultSet rows = statement.executeQuery(
                     "SELECT nullif(current_setting('app.organization_id', true), '')")) {
            assertTrue(rows.next());
            assertNull(rows.getString(1));
        }
    }

    private static Connection adminConnection() throws SQLException {
        return java.sql.DriverManager.getConnection(
                POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
    }
}
