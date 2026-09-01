package io.elmos.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.workflow.ExecutionJobPort;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.DockerClientFactory;
import org.testcontainers.containers.PostgreSQLContainer;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Controlled concurrent schedules for the V80 PostgreSQL 17.5 admission contract.
 * An environment-provided database is accepted only with an explicit disposable-data
 * acknowledgement; the fallback Testcontainers database is disposable by construction.
 */
class JdbcExecutionJobEnqueueConcurrencyLiveTest {

    private static final String APP_USER = "elmos_execution_enqueue_live";
    private static final String APP_PASSWORD = "execution-enqueue-live-only";
    private static final String IMAGE = "registry.example.test/elmos/runner@sha256:" + "a".repeat(64);
    private static final int FREE_TRIAL_QUEUE_LIMIT = 10;

    private static PostgreSQLContainer<?> postgres;
    private static JdbcClient adminJdbc;
    private static JdbcClient runtimeJdbc;
    private static JdbcExecutionJobStore jobs;

    @BeforeAll
    static void migrateDisposablePostgresAndCreateRuntimeRole() {
        DatabaseTarget target = databaseTarget();
        Flyway.configure()
                .dataSource(target.jdbcUrl(), target.user(), target.password())
                .defaultSchema("public")
                .load()
                .migrate();

        var adminDataSource = new DriverManagerDataSource(
                target.jdbcUrl(), target.user(), target.password());
        adminJdbc = JdbcClient.create(adminDataSource);
        adminJdbc.sql("CREATE ROLE " + APP_USER
                        + " LOGIN PASSWORD '" + APP_PASSWORD
                        + "' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS")
                .update();
        adminJdbc.sql("GRANT USAGE ON SCHEMA public TO " + APP_USER).update();
        adminJdbc.sql("GRANT SELECT ON TABLE execution_jobs TO " + APP_USER).update();
        adminJdbc.sql("GRANT EXECUTE ON FUNCTION elmos_enqueue_execution_job("
                        + "varchar,varchar,varchar,varchar,varchar,varchar,varchar,jsonb,"
                        + "varchar,varchar,smallint,integer,smallint) TO " + APP_USER)
                .update();

        var runtimeDataSource = new DriverManagerDataSource(
                target.jdbcUrl(), APP_USER, APP_PASSWORD);
        runtimeJdbc = JdbcClient.create(runtimeDataSource);
        jobs = new JdbcExecutionJobStore(
                runtimeJdbc,
                new TransactionTemplate(new DataSourceTransactionManager(runtimeDataSource)),
                new ObjectMapper());
    }

    @AfterAll
    static void stopDisposableContainer() {
        if (postgres != null) {
            postgres.stop();
        }
    }

    @Test
    void concurrentSameKeyAndDigestReturnsOneAuthoritativeJobId() throws Exception {
        String organization = "org-v80-same-key";
        seedTrial(organization);
        List<ExecutionJobPort.EnqueueCommand> commands = new ArrayList<>();
        for (int i = 0; i < 16; i++) {
            commands.add(command(
                    "job-v80-same-" + i, organization, "idem-v80-same", "1".repeat(64)));
        }

        List<Outcome> outcomes = concurrently(commands);

        assertTrue(outcomes.stream().allMatch(Outcome::succeeded));
        Set<String> jobIds = new HashSet<>(outcomes.stream().map(Outcome::jobId).toList());
        assertEquals(1, jobIds.size(), "every successful replay must return the first job id");
        assertProjection(organization, 1, 1);
    }

    @Test
    void concurrentDigestDriftReturnsOnlySuccessOrExplicitConflict() throws Exception {
        String organization = "org-v80-digest-race";
        seedTrial(organization);
        List<ExecutionJobPort.EnqueueCommand> commands = new ArrayList<>();
        for (int i = 0; i < 12; i++) {
            String digest = i % 2 == 0 ? "2".repeat(64) : "3".repeat(64);
            commands.add(command(
                    "job-v80-digest-" + i, organization, "idem-v80-digest", digest));
        }

        List<Outcome> outcomes = concurrently(commands);

        List<Outcome> successes = outcomes.stream().filter(Outcome::succeeded).toList();
        List<Outcome> conflicts = outcomes.stream().filter(outcome -> !outcome.succeeded()).toList();
        assertEquals(6, successes.size());
        assertEquals(6, conflicts.size());
        assertEquals(1, new HashSet<>(successes.stream().map(Outcome::jobId).toList()).size());
        assertTrue(conflicts.stream().allMatch(outcome ->
                "ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT".equals(outcome.code())));
        assertProjection(organization, 1, 1);
    }

    @Test
    void concurrentDistinctKeysNeverExceedTenantQueueCapacity() throws Exception {
        String organization = "org-v80-capacity";
        seedTrial(organization);
        List<ExecutionJobPort.EnqueueCommand> commands = new ArrayList<>();
        for (int i = 0; i < 32; i++) {
            commands.add(command(
                    "job-v80-capacity-" + i,
                    organization,
                    "idem-v80-capacity-" + i,
                    String.format("%064x", i + 16)));
        }

        List<Outcome> outcomes = concurrently(commands);

        assertEquals(FREE_TRIAL_QUEUE_LIMIT,
                outcomes.stream().filter(Outcome::succeeded).count());
        assertTrue(outcomes.stream().filter(outcome -> !outcome.succeeded()).allMatch(outcome ->
                "ELMOS_EXECUTION_QUEUE_DEPTH_EXCEEDED".equals(outcome.code())));
        assertProjection(organization, FREE_TRIAL_QUEUE_LIMIT, FREE_TRIAL_QUEUE_LIMIT);
    }

    @Test
    void unrelatedUniqueViolationBecomesStableNonLeakingDomainFailure() {
        String organization = "org-v80-unique";
        seedTrial(organization);
        assertEquals("job-v80-shared",
                jobs.enqueue(command("job-v80-shared", organization, "idem-v80-first", "4".repeat(64))));

        Outcome collision = enqueue(command(
                "job-v80-shared", organization, "idem-v80-second", "5".repeat(64)));

        assertEquals("ELMOS_EXECUTION_STORAGE_CONFLICT", collision.code());
        assertFalse(collision.code().contains("execution_jobs"));
        assertProjection(organization, 1, 1);
    }

    @Test
    void sameIdempotencyKeyRemainsTenantScopedUnderForcedRls() {
        String firstOrganization = "org-v80-tenant-a";
        String secondOrganization = "org-v80-tenant-b";
        seedTrial(firstOrganization);
        seedTrial(secondOrganization);

        String firstJob = jobs.enqueue(command(
                "job-v80-tenant-a", firstOrganization, "idem-v80-shared-tenant", "6".repeat(64)));
        String secondJob = jobs.enqueue(command(
                "job-v80-tenant-b", secondOrganization, "idem-v80-shared-tenant", "6".repeat(64)));

        assertFalse(firstJob.equals(secondJob));
        assertTrue(jobs.find(firstOrganization, firstJob).isPresent());
        assertTrue(jobs.find(firstOrganization, secondJob).isEmpty());
        assertTrue(jobs.find(secondOrganization, firstJob).isEmpty());
        assertTrue(jobs.find(secondOrganization, secondJob).isPresent());
        assertEquals(0L, runtimeJdbc.sql("SELECT count(*) FROM execution_jobs")
                .query(Long.class).single(),
                "the constrained role must see no tenant rows outside a bound transaction");
    }

    private static DatabaseTarget databaseTarget() {
        String configuredUrl = trimToNull(System.getenv("ELMOS_EXECUTION_QUEUE_TEST_JDBC_URL"));
        if (configuredUrl != null) {
            if (!"true".equalsIgnoreCase(System.getenv(
                    "ELMOS_EXECUTION_QUEUE_TEST_DISPOSABLE"))) {
                throw new IllegalStateException(
                        "ELMOS_EXECUTION_QUEUE_TEST_DISPOSABLE=true is required for an external test database");
            }
            return new DatabaseTarget(
                    configuredUrl,
                    System.getenv().getOrDefault(
                            "ELMOS_EXECUTION_QUEUE_TEST_DATABASE_USER", System.getProperty("user.name")),
                    System.getenv().getOrDefault(
                            "ELMOS_EXECUTION_QUEUE_TEST_DATABASE_PASSWORD", ""));
        }
        Assumptions.assumeTrue(DockerClientFactory.instance().isDockerAvailable(),
                "requires Docker or ELMOS_EXECUTION_QUEUE_TEST_JDBC_URL");
        postgres = new PostgreSQLContainer<>("postgres:17.5-alpine");
        postgres.start();
        return new DatabaseTarget(
                postgres.getJdbcUrl(), postgres.getUsername(), postgres.getPassword());
    }

    private static void seedTrial(String organization) {
        adminJdbc.sql("INSERT INTO organizations (organization_id) VALUES (:organization)")
                .param("organization", organization)
                .update();
        adminJdbc.sql("""
                INSERT INTO subscriptions (
                    subscription_id, organization_id, status, catalog_version,
                    plan_id, actor_id, billing_period, currency, price_minor,
                    current_period_start, current_period_end)
                VALUES (
                    :subscription, :organization, 'TRIALING', '2026-07-28.2',
                    'elmos-free-trial', 'actor-v80', 'TRIAL', 'CNY', 0,
                    now() - interval '1 hour', now() + interval '1 day')
                """)
                .param("subscription", "sub-" + organization)
                .param("organization", organization)
                .update();
    }

    private static ExecutionJobPort.EnqueueCommand command(
            String jobId,
            String organization,
            String idempotencyKey,
            String requestDigest
    ) {
        return new ExecutionJobPort.EnqueueCommand(
                jobId,
                organization,
                "actor-v80",
                ExecutionJobPort.BusinessLine.GENERATION,
                "generate",
                idempotencyKey,
                requestDigest,
                java.util.Map.of("fixture", "v80"),
                "generation:multi",
                IMAGE,
                (short) 100,
                3600,
                (short) 1);
    }

    private static List<Outcome> concurrently(
            List<ExecutionJobPort.EnqueueCommand> commands
    ) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(commands.size());
        CountDownLatch ready = new CountDownLatch(commands.size());
        CountDownLatch start = new CountDownLatch(1);
        try {
            List<Future<Outcome>> futures = commands.stream()
                    .map(command -> executor.submit(() -> {
                        ready.countDown();
                        assertTrue(start.await(20, TimeUnit.SECONDS));
                        return enqueue(command);
                    }))
                    .toList();
            assertTrue(ready.await(20, TimeUnit.SECONDS));
            start.countDown();
            List<Outcome> outcomes = new ArrayList<>(futures.size());
            for (Future<Outcome> future : futures) {
                outcomes.add(future.get(60, TimeUnit.SECONDS));
            }
            return outcomes;
        } finally {
            start.countDown();
            executor.shutdownNow();
            assertTrue(executor.awaitTermination(20, TimeUnit.SECONDS));
        }
    }

    private static Outcome enqueue(ExecutionJobPort.EnqueueCommand command) {
        try {
            return new Outcome(jobs.enqueue(command), null);
        } catch (ExecutionJobPort.ExecutionStateException failure) {
            return new Outcome(null, failure.code());
        }
    }

    private static void assertProjection(String organization, int jobsExpected, int queuedExpected) {
        assertEquals(jobsExpected, adminJdbc.sql("""
                SELECT count(*) FROM execution_jobs WHERE organization_id = :organization
                """).param("organization", organization).query(Integer.class).single());
        assertEquals(jobsExpected, adminJdbc.sql("""
                SELECT count(*) FROM execution_job_dispatch WHERE organization_id = :organization
                """).param("organization", organization).query(Integer.class).single());
        assertEquals(jobsExpected, adminJdbc.sql("""
                SELECT count(*) FROM execution_job_events WHERE organization_id = :organization
                """).param("organization", organization).query(Integer.class).single());
        assertEquals(queuedExpected, adminJdbc.sql("""
                SELECT queued_count FROM execution_dispatch_org_counters
                 WHERE organization_id = :organization
                """).param("organization", organization).query(Integer.class).single());
    }

    private static String trimToNull(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }

    private record DatabaseTarget(String jdbcUrl, String user, String password) {}

    private record Outcome(String jobId, String code) {
        boolean succeeded() {
            return jobId != null && code == null;
        }
    }
}
