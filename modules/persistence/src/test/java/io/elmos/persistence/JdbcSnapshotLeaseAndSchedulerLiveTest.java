package io.elmos.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import io.elmos.snapshot.SnapshotMaterializationLease;
import io.elmos.snapshot.SnapshotModel;
import io.elmos.snapshot.SnapshotPorts;
import io.elmos.snapshot.SnapshotReconciliationWorkQueue;
import io.elmos.snapshot.SnapshotRootReconciliation;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.function.Supplier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Real PostgreSQL proof for V72 fencing, archive exclusion, and global queue leases. */
@Testcontainers(disabledWithoutDocker = true)
class JdbcSnapshotLeaseAndSchedulerLiveTest {
    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:17.5-alpine");

    private static final String APP_USER = "elmos_snapshot_lease_live";
    private static final String APP_PASSWORD = "snapshot-lease-live-only";
    private static final ObjectMapper MAPPER = new ObjectMapper()
            .findAndRegisterModules()
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    private static JdbcClient runtimeJdbc;
    private static JdbcClient adminJdbc;
    private static TransactionTemplate transactions;
    private static JdbcSnapshotMaterializationLeaseStore leases;
    private static JdbcSnapshotReconciliationWorkQueue work;

    @BeforeAll
    static void migrateAndCreateRuntimeRole() throws Exception {
        Flyway.configure()
                .dataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())
                .defaultSchema("public")
                .load()
                .migrate();
        DriverManagerDataSource admin = dataSource(
                POSTGRES.getUsername(), POSTGRES.getPassword());
        adminJdbc = JdbcClient.create(admin);
        try (Connection connection = admin.getConnection(); Statement statement = connection.createStatement()) {
            statement.execute("CREATE ROLE " + APP_USER
                    + " LOGIN PASSWORD '" + APP_PASSWORD
                    + "' NOSUPERUSER NOBYPASSRLS NOINHERIT");
            statement.execute("GRANT USAGE ON SCHEMA public TO " + APP_USER);
            statement.execute("GRANT SELECT ON TABLE repository_snapshots TO " + APP_USER);
            statement.execute("GRANT UPDATE (status) ON TABLE repository_snapshots TO "
                    + APP_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION "
                    + "elmos_acquire_snapshot_materialization_lease(varchar,varchar,"
                    + "varchar,varchar,varchar,integer) TO " + APP_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION "
                    + "elmos_renew_snapshot_materialization_lease(varchar,varchar,"
                    + "varchar,varchar,varchar,bigint,integer) TO " + APP_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION "
                    + "elmos_require_active_snapshot_materialization_lease(varchar,varchar,"
                    + "varchar,varchar,varchar,bigint) TO " + APP_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION "
                    + "elmos_release_snapshot_materialization_lease(varchar,varchar,"
                    + "varchar,varchar,varchar,bigint) TO " + APP_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION "
                    + "elmos_claim_snapshot_reconciliation_work(varchar,integer,integer) TO "
                    + APP_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION "
                    + "elmos_complete_snapshot_reconciliation_work(varchar,varchar,bigint,"
                    + "boolean,integer) TO " + APP_USER);
        }

        insertTenantFixture("lease-live-a", "lease-repo-a", "lease-snapshot-a", 'a');
        insertTenantFixture("lease-live-b", "lease-repo-b", "lease-snapshot-b", 'b');
        insertTenantFixture("lease-live-c", "lease-repo-c", "lease-snapshot-c", 'c');
        insertPendingReconciliation();

        DriverManagerDataSource runtime = dataSource(APP_USER, APP_PASSWORD);
        runtimeJdbc = JdbcClient.create(runtime);
        transactions = new TransactionTemplate(new DataSourceTransactionManager(runtime));
        leases = new JdbcSnapshotMaterializationLeaseStore(runtimeJdbc);
        work = new JdbcSnapshotReconciliationWorkQueue(runtimeJdbc);
    }

    @Test void activeLeaseBlocksArchiveThenExactIdempotentReleaseAllowsIt() {
        SnapshotPorts.ArtifactResourceContext resource =
                new SnapshotPorts.ArtifactResourceContext("lease-live-a", "lease-repo-a");
        SnapshotMaterializationLease lease = inTransaction(() -> leases.acquire(
                resource, "lease-snapshot-a", "materialization-a", "worker-a",
                Duration.ofMinutes(2)));

        RuntimeException blocked = assertThrows(RuntimeException.class,
                () -> inTransaction(() -> archive(
                        "lease-live-a", "lease-repo-a", "lease-snapshot-a")));
        assertTrue(hasSqlState(blocked, "55006"));
        assertEquals(lease, inTransaction(() -> leases.requireActive(lease)));

        inTransaction(() -> {
            leases.release(lease);
            leases.release(lease);
            return null;
        });
        assertEquals(1, inTransaction(() -> archive(
                "lease-live-a", "lease-repo-a", "lease-snapshot-a")));
    }

    @Test void staleFenceCannotReleaseTheNewOwner() {
        SnapshotPorts.ArtifactResourceContext resource =
                new SnapshotPorts.ArtifactResourceContext("lease-live-b", "lease-repo-b");
        SnapshotMaterializationLease first = inTransaction(() -> leases.acquire(
                resource, "lease-snapshot-b", "materialization-b-1", "worker-a",
                Duration.ofMinutes(2)));
        inTransaction(() -> {
            leases.release(first);
            return null;
        });
        SnapshotMaterializationLease second = inTransaction(() -> leases.acquire(
                resource, "lease-snapshot-b", "materialization-b-2", "worker-b",
                Duration.ofMinutes(2)));
        assertTrue(second.fencingToken() > first.fencingToken());
        SnapshotMaterializationLease forged = new SnapshotMaterializationLease(
                second.organizationId(), second.repositoryId(), second.snapshotId(),
                second.leaseId(), second.holderId(), first.fencingToken(),
                second.acquiredAt(), second.expiresAt());

        assertThrows(RuntimeException.class,
                () -> inTransaction(() -> {
                    leases.release(forged);
                    return null;
                }));
        assertEquals(second, inTransaction(() -> leases.requireActive(second)));
        inTransaction(() -> {
            leases.release(second);
            return null;
        });
    }

    @Test void globalWorkClaimIsExclusiveBoundedFencedAndExactlyIdempotent() {
        List<SnapshotReconciliationWorkQueue.WorkLease> claimed = inTransaction(
                () -> work.claim("scheduler-a", 1, Duration.ofMinutes(2)));
        assertEquals(1, claimed.size());
        SnapshotReconciliationWorkQueue.WorkLease lease = claimed.getFirst();
        assertEquals("lease-live-c", lease.organizationId());
        assertTrue(inTransaction(
                () -> work.claim("scheduler-b", 1, Duration.ofMinutes(2))).isEmpty());

        assertTrue(inTransaction(
                () -> work.complete(lease, false, Duration.ofMinutes(1))));
        assertTrue(inTransaction(
                () -> work.complete(lease, false, Duration.ofMinutes(1))));
        SnapshotReconciliationWorkQueue.WorkLease wrongWorker =
                new SnapshotReconciliationWorkQueue.WorkLease(
                        lease.organizationId(), "scheduler-b",
                        lease.fencingToken(), lease.expiresAt());
        assertThrows(RuntimeException.class,
                () -> inTransaction(
                        () -> work.complete(wrongWorker, false, Duration.ofMinutes(1))));
    }

    private static int archive(String organization, String repository, String snapshot) {
        setTenant(organization);
        return runtimeJdbc.sql("""
                update repository_snapshots set status = 'ARCHIVED'
                 where organization_id = :organization
                   and repository_id = :repository
                   and snapshot_id = :snapshot
                   and status = 'AVAILABLE'
                """)
                .param("organization", organization)
                .param("repository", repository)
                .param("snapshot", snapshot)
                .update();
    }

    private static void setTenant(String organization) {
        runtimeJdbc.sql("select set_config('app.organization_id', :organization, true)")
                .param("organization", organization)
                .query(String.class)
                .single();
    }

    private static void insertTenantFixture(
            String organization, String repository, String snapshot, char digest
    ) {
        adminJdbc.sql("insert into organizations(organization_id) values(:organization)")
                .param("organization", organization)
                .update();
        adminJdbc.sql("""
                insert into repositories(
                    repository_id, organization_id, scm_provider, external_id, default_branch)
                values(:repository, :organization, 'github', :external, 'main')
                """)
                .param("repository", repository)
                .param("organization", organization)
                .param("external", "native-" + repository)
                .update();
        adminJdbc.sql("""
                insert into repository_snapshots(
                    snapshot_id, organization_id, repository_id, commit_sha, requested_ref,
                    captured_at, build_files_hash, archive_artifact_ref, tree_sha,
                    archive_sha256, archive_size, manifest_artifact_ref, manifest_sha256,
                    snapshot_schema_version, status)
                values(:snapshot, :organization, :repository, :commit, 'refs/heads/main',
                    :captured, :buildHash, :archiveRef, :tree, :archiveHash, 10,
                    :manifestRef, :manifestHash, 1, 'AVAILABLE')
                """)
                .param("snapshot", snapshot)
                .param("organization", organization)
                .param("repository", repository)
                .param("commit", Character.toString(digest).repeat(40))
                .param("captured", Instant.parse("2026-08-24T00:00:00Z")
                        .atOffset(ZoneOffset.UTC))
                .param("buildHash", "sha256:" + Character.toString(digest).repeat(64))
                .param("archiveRef", "cas:sha256:" + Character.toString(digest).repeat(64))
                .param("tree", Character.toString(digest).repeat(40))
                .param("archiveHash", Character.toString(digest).repeat(64))
                .param("manifestRef", "cas:sha256:" + nextDigest(digest).repeat(64))
                .param("manifestHash", nextDigest(digest).repeat(64))
                .update();
    }

    private static void insertPendingReconciliation() throws Exception {
        SnapshotModel.RepositorySnapshot snapshot = snapshot(
                "lease-snapshot-c", "lease-live-c", "lease-repo-c", 'c');
        Instant recordedAt = Instant.parse("2026-08-24T00:01:00Z");
        SnapshotRootReconciliation reconciliation = new SnapshotRootReconciliation(
                "lease-reconciliation-c", "lease-operation-c",
                SnapshotRootReconciliation.Kind.CAPTURE_COMMIT,
                SnapshotRootReconciliation.Phase.PENDING,
                snapshot, SnapshotPorts.ArtifactRetention.untracked(snapshot.snapshotId()),
                null, recordedAt);
        adminJdbc.sql("""
                insert into snapshot_root_reconciliations(
                    organization_id, repository_id, attempt_id, logical_operation_id,
                    snapshot_id, reconciliation_kind, phase, durable_snapshot_id,
                    reconciliation_payload, retention_generations, recorded_at, updated_at)
                values(:organization, :repository, :attempt, :operation, :snapshot,
                    'CAPTURE_COMMIT', 'PENDING', null, cast(:payload as jsonb),
                    cast('{}' as jsonb), :recorded, :recorded)
                """)
                .param("organization", snapshot.organizationId())
                .param("repository", snapshot.repositoryId())
                .param("attempt", reconciliation.reconciliationId())
                .param("operation", reconciliation.logicalOperationId())
                .param("snapshot", snapshot.snapshotId())
                .param("payload", MAPPER.writeValueAsString(reconciliation))
                .param("recorded", recordedAt.atOffset(ZoneOffset.UTC))
                .update();
    }

    private static SnapshotModel.RepositorySnapshot snapshot(
            String snapshotId, String organization, String repository, char digest
    ) {
        String hash = Character.toString(digest);
        String manifestHash = nextDigest(digest);
        return new SnapshotModel.RepositorySnapshot(
                snapshotId, organization, repository, "refs/heads/main",
                hash.repeat(40), hash.repeat(40), "cas:sha256:" + hash.repeat(64),
                hash.repeat(64), 10, "cas:sha256:" + manifestHash.repeat(64),
                manifestHash.repeat(64), 1, SnapshotModel.Status.AVAILABLE,
                Instant.parse("2026-08-24T00:00:00Z"));
    }

    private static String nextDigest(char digest) {
        return Character.toString((char) (digest + 1));
    }

    private static DriverManagerDataSource dataSource(String user, String password) {
        DriverManagerDataSource source = new DriverManagerDataSource(
                POSTGRES.getJdbcUrl(), user, password);
        source.setDriverClassName("org.postgresql.Driver");
        return source;
    }

    private static <T> T inTransaction(Supplier<T> operation) {
        return transactions.execute(status -> operation.get());
    }

    private static boolean hasSqlState(Throwable failure, String sqlState) {
        Throwable current = failure;
        while (current != null) {
            if (current instanceof SQLException sql && sqlState.equals(sql.getSQLState())) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }
}
