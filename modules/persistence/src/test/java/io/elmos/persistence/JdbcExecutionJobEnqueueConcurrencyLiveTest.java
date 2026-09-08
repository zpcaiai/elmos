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
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * Controlled concurrent schedules for the V80 PostgreSQL 17.5 admission contract.
 * An environment-provided database is accepted only with an explicit disposable-data
 * acknowledgement; the fallback Testcontainers database is disposable by construction.
 */
class JdbcExecutionJobEnqueueConcurrencyLiveTest {

    private static final String APP_USER = "elmos_enqueue_live_"
            + java.util.UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    private static final String APP_PASSWORD = "execution-enqueue-live-only";
    private static final String IMAGE = "registry.example.test/elmos/runner@sha256:" + "a".repeat(64);
    private static final int FREE_TRIAL_QUEUE_LIMIT = 10;

    private static PostgreSQLContainer<?> postgres;
    private static JdbcClient adminJdbc;
    private static JdbcClient runtimeJdbc;
    private static JdbcExecutionJobStore jobs;
    private static DriverManagerDataSource adminConnections;

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
        adminConnections = adminDataSource;
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
        adminJdbc.sql("GRANT EXECUTE ON FUNCTION elmos_claim_execution_jobs("
                + "varchar,text[],integer,integer,text[],text[]) TO " + APP_USER).update();
        adminJdbc.sql("GRANT EXECUTE ON FUNCTION elmos_heartbeat_execution_lease("
                + "varchar,varchar,varchar,varchar,smallint,jsonb,integer) TO " + APP_USER).update();
        adminJdbc.sql("GRANT EXECUTE ON FUNCTION elmos_complete_execution_job("
                + "varchar,varchar,varchar,varchar,varchar,varchar) TO " + APP_USER).update();

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

    @Test
    void simultaneousRunnersRespectTenantCapacityAndLeaseCredentials() throws Exception {
        String suffix = java.util.UUID.randomUUID().toString().substring(0, 8);
        String organization = "org-v82-claims-" + suffix;
        seedTrial(organization);
        String capability = "fixture:" + organization;
        for (int i = 0; i < 8; i++) {
            jobs.enqueue(new ExecutionJobPort.EnqueueCommand("job-v82-" + suffix + "-" + i, organization,
                    "actor-v82", ExecutionJobPort.BusinessLine.TRANSLATION, "translate",
                    "idem-v82-" + i, String.format("%064x", i + 32), java.util.Map.of(),
                    capability, IMAGE, (short) 100, 120, (short) 1));
            seedRunner(organization, "runner-v82-" + suffix + "-" + i, capability);
        }
        var grants = new ArrayList<ExecutionJobPort.LeaseGrant>();
        var start = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(8)) {
            var futures = new ArrayList<Future<List<ExecutionJobPort.LeaseGrant>>>();
            for (int i = 0; i < 8; i++) {
                String runner = "runner-v82-" + suffix + "-" + i;
                futures.add(pool.submit(() -> {
                    start.await();
                    return jobs.claim(runner, List.of(capability), 4, 120);
                }));
            }
            start.countDown();
            for (var future : futures) grants.addAll(future.get(20, TimeUnit.SECONDS));
        }
        assertEquals(1, grants.size(), "trial plan permits only one lease across all runners");
        var grant = grants.getFirst();
        assertEquals(1L, adminJdbc.sql("SELECT leased_count FROM execution_dispatch_org_counters "
                + "WHERE organization_id = :org").param("org", organization).query(Long.class).single());
        String runner = adminJdbc.sql("SELECT runner_node_ref FROM execution_job_dispatch WHERE job_id = :job")
                .param("job", grant.jobId()).query(String.class).single();
        var bad = org.junit.jupiter.api.Assertions.assertThrows(ExecutionJobPort.ExecutionStateException.class,
                () -> jobs.heartbeat(new ExecutionJobPort.HeartbeatCommand(grant.leaseId(), runner,
                        "wrong-token", "running", (short) 1, java.util.Map.of(), 120)));
        assertEquals("ELMOS_LEASE_CREDENTIAL_MISMATCH", bad.code());
        jobs.heartbeat(new ExecutionJobPort.HeartbeatCommand(grant.leaseId(), runner,
                grant.leaseToken(), "running", (short) 1, java.util.Map.of(), 120));
        adminJdbc.sql("UPDATE runner_job_leases SET issued_at = now() - interval '5 seconds', "
                + "last_heartbeat_at = now() - interval '2 seconds', expires_at = now() - interval '1 second' "
                + "WHERE runner_job_lease_id = :lease").param("lease", grant.leaseId()).update();
        var expired = org.junit.jupiter.api.Assertions.assertThrows(ExecutionJobPort.ExecutionStateException.class,
                () -> jobs.complete(new ExecutionJobPort.CompletionCommand(grant.leaseId(), runner,
                        grant.leaseToken(), ExecutionJobPort.Status.SUCCEEDED,
                        ExecutionJobPort.ResultStatus.PASSED, null)));
        assertEquals("ELMOS_LEASE_EXPIRED", expired.code());
        assertEquals(ExecutionJobPort.Status.RUNNING, jobs.find(organization, grant.jobId()).orElseThrow().status());
    }

    @Test
    void busyTenantCounterDoesNotBlockAClaimAndRollbackRestoresAdmission() throws Exception {
        String suffix = java.util.UUID.randomUUID().toString().substring(0, 8);
        String organization = "org-v82-lock-" + suffix;
        String runner = "runner-lock-" + suffix;
        String capability = "fixture:lock:" + suffix;
        seedTrial(organization);
        seedRunner(organization, runner, capability);
        jobs.enqueue(new ExecutionJobPort.EnqueueCommand("job-lock-" + suffix, organization,
                "actor-v82", ExecutionJobPort.BusinessLine.TRANSLATION, "translate",
                "idem-lock", "b".repeat(64), java.util.Map.of(), capability, IMAGE,
                (short) 100, 120, (short) 1));
        try (var connection = adminConnections.getConnection()) {
            connection.setAutoCommit(false);
            try (var lock = connection.prepareStatement("SELECT leased_count FROM "
                    + "execution_dispatch_org_counters WHERE organization_id = ? FOR UPDATE")) {
                lock.setString(1, organization);
                try (var result = lock.executeQuery()) { assertTrue(result.next()); }
            }
            var worker = Executors.newSingleThreadExecutor();
            try {
                assertTrue(worker.submit(() -> jobs.claim(runner, List.of(capability), 1, 120))
                        .get(5, TimeUnit.SECONDS).isEmpty());
            } finally {
                connection.rollback();
                worker.shutdownNow();
                assertTrue(worker.awaitTermination(5, TimeUnit.SECONDS));
            }
        }
        assertEquals(1, jobs.claim(runner, List.of(capability), 1, 120).size());
    }

    private static void seedRunner(String organization, String runner, String capability) {
        adminJdbc.sql("INSERT INTO runner_pools (runner_pool_id, organization_id) VALUES (:pool,:org)")
                .param("pool", "pool-" + runner).param("org", organization).update();
        adminJdbc.sql("""
                INSERT INTO runner_nodes (runner_node_id, organization_id, runner_pool_ref,
                    agent_version, fleet_status, capabilities, max_concurrency,
                    rootless_attested, readonly_root_attested, capability_drop_attested,
                    network_default_deny_attested, attestation_verified_at,
                    attestation_verifier_actor_id, image_allowlist_version, last_heartbeat_at)
                VALUES (:runner,:org,:pool,'fixture','READY',ARRAY[:capability],4,
                    true,true,true,true,now(),'fixture-verifier','fixture',now())
                """).param("runner", runner).param("org", organization)
                .param("pool", "pool-" + runner).param("capability", capability).update();
        adminJdbc.sql("""
                INSERT INTO runner_enrollment_credentials (enrollment_credential_id, organization_id,
                    runner_pool_id, token_sha256, expires_at, issued_by_actor_id)
                VALUES (:credential,:org,:pool,md5(:runner) || md5(:runner),now()+interval '1 hour','fixture')
                """).param("credential", "cred-" + runner).param("org", organization)
                .param("pool", "pool-" + runner).param("runner", runner).update();
        adminJdbc.sql("""
                INSERT INTO runner_node_authentication (runner_node_id, organization_id,
                    runner_pool_id, enrollment_credential_id) VALUES (:runner,:org,:pool,:credential)
                """).param("runner", runner).param("org", organization)
                .param("pool", "pool-" + runner).param("credential", "cred-" + runner).update();
    }

    @Test
    void boundedTenantWindowRotatesPastSaturatedTenants() {
        String suffix = java.util.UUID.randomUUID().toString().substring(0,8);
        String prefix = "org-v84-window-" + suffix + "-";
        String capability = "fixture:v84-window:" + suffix;
        for (int i = 0; i < 40; i++) {
            String org = prefix + String.format("%02d", i);
            seedTrial(org);
            jobs.enqueue(new ExecutionJobPort.EnqueueCommand("job-window-" + suffix + "-" + i, org,
                    "actor-v84", ExecutionJobPort.BusinessLine.TRANSLATION, "translate",
                    "idem-window", String.format("%064x", i + 100), java.util.Map.of(),
                    capability, IMAGE, (short) 100, 120, (short) 1));
            if (i < 39) adminJdbc.sql("UPDATE execution_dispatch_org_counters SET leased_count=1 "
                    + "WHERE organization_id=:org").param("org", org).update();
        }
        // Least-loaded tenants win within a round. Put the healthy tenant in a
        // later round to exercise rotation past an actually saturated window.
        adminJdbc.sql("UPDATE execution_dispatch_org_counters SET last_claim_probe_at=now() "
                + "WHERE organization_id=:org").param("org",prefix+"39").update();
        String runner = "runner-v84-window-" + suffix;
        seedRunner(prefix + "39", runner, capability);
        assertTrue(jobs.claim(runner, List.of(capability), 1, 120).isEmpty());
        assertEquals(32, adminJdbc.sql("SELECT count(*) FROM execution_dispatch_org_counters "
                + "WHERE organization_id LIKE :prefix AND organization_id<>:healthy AND last_claim_probe_at > '-infinity'")
                .param("prefix",prefix+"%").param("healthy",prefix+"39")
                .query(Integer.class).single());
        var second = jobs.claim(runner, List.of(capability), 1, 120);
        assertEquals(1, second.size());
        assertEquals("job-window-" + suffix + "-39", second.getFirst().jobId());
    }

    @Test
    void claimPrefetchLocksOnlyRemainingCapacityAcrossTenantWindows() throws Exception {
        String suffix = java.util.UUID.randomUUID().toString().substring(0, 8);
        String prefix = "org-v84-prefetch-" + suffix + "-";
        String capability = "fixture:prefetch:" + suffix;
        for (int i = 0; i < 16; i++) {
            String org = prefix + String.format("%02d", i);
            seedTrial(org);
            // Ten READY rows per tenant, each with exactly one lease slot.
            adminJdbc.sql("""
                    INSERT INTO execution_jobs(job_id,organization_id,actor_id,business_line,job_kind,
                        idempotency_key,request_digest,required_capability)
                    SELECT :org || '-job-' || n,:org,'fixture','TRANSLATION','translate',
                        :org || '-idem-' || n,repeat('a',64),:capability FROM generate_series(0,9) n
                    """).param("org", org).param("capability", capability).update();
            adminJdbc.sql("""
                    INSERT INTO execution_job_dispatch(job_id,organization_id,required_capability,enqueued_at)
                    SELECT :org || '-job-' || n,:org,:capability,now()+make_interval(secs => n)
                      FROM generate_series(0,9) n
                    """).param("org", org).param("capability", capability).update();
            adminJdbc.sql("INSERT INTO execution_dispatch_org_counters(organization_id,queued_count) VALUES(:org,10)")
                    .param("org", org).update();
        }
        String runner = "runner-prefetch-" + suffix;
        seedRunner(prefix + "15", runner, capability);
        adminJdbc.sql("UPDATE runner_nodes SET max_concurrency=16 WHERE runner_node_id=:runner")
                .param("runner", runner).update();
        var worker = Executors.newSingleThreadExecutor();
        try (var blocking = adminConnections.getConnection()) {
            blocking.setAutoCommit(false);
            int blocker = backendPid(blocking);
            try (var lock = blocking.prepareStatement("SELECT job_id FROM execution_jobs WHERE job_id=? FOR UPDATE")) {
                lock.setString(1, prefix + "15-job-0");
                try (var row = lock.executeQuery()) { assertTrue(row.next()); }
            }
            var claim = worker.submit(() -> jobs.claim(runner, List.of(capability), 16, 120));
            awaitRuntimeBlockedBy(blocker);
            // While the last tenant's job row pauses the real claim, a second
            // connection measures actual row-lock exclusion (not pg_locks,
            // which need not list uncontended tuple locks, or returned rows).
            int stillLockable = adminJdbc.sql("""
                    SELECT count(*) FROM (
                        SELECT job_id FROM execution_job_dispatch
                         WHERE organization_id LIKE :prefix AND dispatch_state='READY'
                         FOR UPDATE SKIP LOCKED
                    ) unlocked
                    """).param("prefix", prefix + "%").query(Integer.class).single();
            assertEquals(16, 160 - stillLockable,
                    "one reserved candidate per tenant; implicit cursor prefetch must not lock all 160");
            blocking.rollback();
            var grants = claim.get(30, TimeUnit.SECONDS);
            assertEquals(16, grants.size());
            assertEquals(16, grants.stream().map(ExecutionJobPort.LeaseGrant::jobId).distinct().count());
            assertEquals(16, adminJdbc.sql("SELECT sum(leased_count)::integer FROM execution_dispatch_org_counters "
                    + "WHERE organization_id LIKE :prefix").param("prefix", prefix + "%").query(Integer.class).single());
        } finally {
            worker.shutdownNow();
            assertTrue(worker.awaitTermination(30, TimeUnit.SECONDS));
        }
    }

    @Test
    void heartbeatCannotRenewOrStartMeteringAfterWaitingPastLeaseExpiry() throws Exception {
        for (String target : List.of("runner", "job")) {
            String suffix = java.util.UUID.randomUUID().toString().substring(0, 8);
            String org = "org-v85-expiry-" + suffix;
            String runner = "runner-v85-expiry-" + suffix;
            String capability = "fixture:expiry:" + suffix;
            seedTrial(org);
            seedRunner(org, runner, capability);
            jobs.enqueue(new ExecutionJobPort.EnqueueCommand("job-expiry-" + suffix, org,
                    "fixture", ExecutionJobPort.BusinessLine.TRANSLATION, "translate-pipeline-v1",
                    "idem-expiry", "f".repeat(64), java.util.Map.of(), capability, IMAGE,
                    (short) 100, 120, (short) 1));
            var grant = jobs.claim(runner, List.of(capability), 1, 120).getFirst();
            var worker = Executors.newSingleThreadExecutor();
            try (var blocking = adminConnections.getConnection()) {
                blocking.setAutoCommit(false);
                int blocker = backendPid(blocking);
                String sql = target.equals("runner")
                        ? "SELECT runner_node_id FROM runner_nodes WHERE runner_node_id=? FOR UPDATE"
                        : "SELECT job_id FROM execution_jobs WHERE job_id=? FOR UPDATE";
                try (var lock = blocking.prepareStatement(sql)) {
                    lock.setString(1, target.equals("runner") ? runner : grant.jobId());
                    try (var row = lock.executeQuery()) { assertTrue(row.next()); }
                }
                String expiry = adminJdbc.sql("UPDATE runner_job_leases SET expires_at=clock_timestamp()+interval '5 seconds' "
                        + "WHERE runner_job_lease_id=:lease RETURNING expires_at::text")
                        .param("lease", grant.leaseId()).query(String.class).single();
                var heartbeat = worker.submit(() -> assertThrows(ExecutionJobPort.ExecutionStateException.class,
                        () -> jobs.heartbeat(new ExecutionJobPort.HeartbeatCommand(grant.leaseId(), runner,
                                grant.leaseToken(), "pipeline", (short) 1, java.util.Map.of(), 30))));
                awaitRuntimeBlockedBy(blocker);
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
                while (!adminJdbc.sql("SELECT clock_timestamp() >= expires_at FROM runner_job_leases WHERE runner_job_lease_id=:lease")
                        .param("lease", grant.leaseId()).query(Boolean.class).single()) {
                    assertTrue(System.nanoTime() < deadline, "fixture lease must expire while heartbeat is blocked");
                    Thread.sleep(20);
                }
                blocking.rollback();
                assertEquals("ELMOS_LEASE_EXPIRED", heartbeat.get(20, TimeUnit.SECONDS).code(), target);
                assertEquals(expiry, adminJdbc.sql("SELECT expires_at::text FROM runner_job_leases WHERE runner_job_lease_id=:lease")
                        .param("lease", grant.leaseId()).query(String.class).single(), "no renewal committed");
                assertEquals(0, adminJdbc.sql("SELECT count(*) FROM execution_jobs WHERE job_id=:job AND metering_started_at IS NOT NULL")
                        .param("job", grant.jobId()).query(Integer.class).single(), "no chargeable work start committed");
                assertEquals(ExecutionJobPort.Status.CLAIMED, jobs.find(org, grant.jobId()).orElseThrow().status());
            } finally {
                worker.shutdownNow();
                assertTrue(worker.awaitTermination(30, TimeUnit.SECONDS));
            }
        }
    }

    private static int backendPid(java.sql.Connection connection) throws java.sql.SQLException {
        try (var query = connection.prepareStatement("SELECT pg_backend_pid()"); var result = query.executeQuery()) {
            assertTrue(result.next());
            return result.getInt(1);
        }
    }

    private static void awaitRuntimeBlockedBy(int blocker) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(30);
        while (!adminJdbc.sql("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE usename=:role "
                + "AND :blocker=ANY(pg_blocking_pids(pid)))")
                .param("role", APP_USER).param("blocker", blocker).query(Boolean.class).single()) {
            assertTrue(System.nanoTime() < deadline, "real runtime call must reach the controlled row lock");
            Thread.sleep(20);
        }
    }

    @Test
    void translationMeteringStartsOnlyAtValidUncancelledPipelineHeartbeat() {
        String org = "org-v85-metering";
        String capability = "fixture:v85-metering";
        String runner = "runner-v85-metering";
        seedTrial(org);
        seedRunner(org,runner,capability);
        jobs.enqueue(new ExecutionJobPort.EnqueueCommand("job-v85-metering", org,
                "fixture", ExecutionJobPort.BusinessLine.TRANSLATION, "translate-pipeline-v1",
                "idem-v85-metering", "d".repeat(64), java.util.Map.of(), capability,
                IMAGE,(short)100,120,(short)1));
        var grant=jobs.claim(runner,List.of(capability),1,120).getFirst();
        adminJdbc.sql("UPDATE execution_jobs SET started_at=now()-interval '5 minutes' WHERE job_id=:job")
                .param("job",grant.jobId()).update();
        assertThrows(ExecutionJobPort.ExecutionStateException.class,
                () -> jobs.heartbeat(new ExecutionJobPort.HeartbeatCommand(grant.leaseId(),runner,
                        "wrong-token","pipeline",(short)1,java.util.Map.of(),120)));
        jobs.heartbeat(new ExecutionJobPort.HeartbeatCommand(grant.leaseId(),runner,grant.leaseToken(),
                "preflight",(short)1,java.util.Map.of(),120));
        assertEquals(0,adminJdbc.sql("SELECT elapsed_seconds FROM elmos_wallet_settlement_facts(:org,:job)")
                .param("org",org).param("job",grant.jobId()).query(Integer.class).single());
        assertThrows(org.springframework.dao.DataAccessException.class,
                () -> adminJdbc.sql("UPDATE execution_jobs SET status='SUCCEEDED', finished_at=now() WHERE job_id=:job")
                        .param("job",grant.jobId()).update());
        jobs.heartbeat(new ExecutionJobPort.HeartbeatCommand(grant.leaseId(),runner,grant.leaseToken(),
                "pipeline",(short)2,java.util.Map.of(),120));
        String first=adminJdbc.sql("SELECT metering_started_at::text FROM execution_jobs WHERE job_id=:job")
                .param("job",grant.jobId()).query(String.class).single();
        jobs.heartbeat(new ExecutionJobPort.HeartbeatCommand(grant.leaseId(),runner,grant.leaseToken(),
                "pipeline",(short)3,java.util.Map.of(),120));
        assertEquals(first,adminJdbc.sql("SELECT metering_started_at::text FROM execution_jobs WHERE job_id=:job")
                .param("job",grant.jobId()).query(String.class).single());
        assertTrue(adminJdbc.sql("SELECT elapsed_seconds FROM elmos_wallet_settlement_facts(:org,:job)")
                .param("org",org).param("job",grant.jobId()).query(Integer.class).single()<120,
                "five minutes of input/preflight time must not be charged");
        jobs.complete(new ExecutionJobPort.CompletionCommand(grant.leaseId(),runner,grant.leaseToken(),
                ExecutionJobPort.Status.SUCCEEDED,ExecutionJobPort.ResultStatus.PASSED,null));

        jobs.enqueue(new ExecutionJobPort.EnqueueCommand("job-v85-cancel",org,"fixture",
                ExecutionJobPort.BusinessLine.TRANSLATION,"translate-pipeline-v1","idem-v85-cancel",
                "e".repeat(64),java.util.Map.of(),capability,IMAGE,(short)100,120,(short)1));
        var cancelled=jobs.claim(runner,List.of(capability),1,120).getFirst();
        adminJdbc.sql("UPDATE execution_jobs SET cancel_requested_at=now(),cancel_requested_by='fixture' WHERE job_id=:job")
                .param("job",cancelled.jobId()).update();
        assertTrue(jobs.heartbeat(new ExecutionJobPort.HeartbeatCommand(cancelled.leaseId(),runner,
                cancelled.leaseToken(),"pipeline",(short)1,java.util.Map.of(),120)).cancelRequested());
        assertEquals(0,adminJdbc.sql("SELECT count(*) FROM execution_jobs WHERE job_id=:job AND metering_started_at IS NOT NULL")
                .param("job",cancelled.jobId()).query(Integer.class).single());
    }

    @Test
    void boundedCounterRepairRotatesAndIsNotGrantedToRuntime() {
        String prefix = "org-v84-reconcile-";
        // Isolate rotation from other fixtures without deleting any authoritative data.
        adminJdbc.sql("UPDATE execution_dispatch_org_counters SET last_reconciled_at=now()").update();
        for (int i = 0; i < 40; i++) {
            String org = prefix + String.format("%02d", i);
            seedTrial(org);
            adminJdbc.sql("INSERT INTO execution_dispatch_org_counters(organization_id,queued_count) "
                    + "VALUES(:org,7)").param("org", org).update();
        }
        assertEquals(32, adminJdbc.sql("SELECT elmos_reconcile_dispatch_counters_batch(32)")
                .query(Integer.class).single());
        assertEquals(8, adminJdbc.sql("SELECT count(*) FROM execution_dispatch_org_counters "
                + "WHERE organization_id LIKE 'org-v84-reconcile-%' AND queued_count=7")
                .query(Integer.class).single());
        adminJdbc.sql("SELECT elmos_reconcile_dispatch_counters_batch(32)").query(Integer.class).single();
        assertEquals(0, adminJdbc.sql("SELECT count(*) FROM execution_dispatch_org_counters "
                + "WHERE organization_id LIKE 'org-v84-reconcile-%' AND queued_count<>0")
                .query(Integer.class).single());
        assertFalse(runtimeJdbc.sql("SELECT has_function_privilege(current_user, "
                + "'elmos_reconcile_dispatch_counters_batch(integer)', 'EXECUTE')")
                .query(Boolean.class).single());
        org.junit.jupiter.api.Assertions.assertThrows(org.springframework.dao.DataAccessException.class,
                () -> adminJdbc.sql("SELECT elmos_reconcile_dispatch_counters_batch(129)").query(Integer.class).single());
    }

    @Test
    void reaperProcessesAtMost128ExpiredLeasesAnd64RunnerProbesPerTransaction() throws Exception {
        String org = "org-v84-reaper";
        String runner = "runner-v84-reaper";
        seedTrial(org);
        seedRunner(org, runner, "fixture:v84-reaper");
        // Synthetic expired records exercise the real SQL state machine, not a mocked store.
        adminJdbc.sql("""
                INSERT INTO execution_jobs(job_id,organization_id,actor_id,business_line,job_kind,
                    idempotency_key,request_digest,required_capability,status,attempt,max_attempts)
                SELECT 'job-v84-reap-'||n,:org,'fixture','TRANSLATION','translate',
                    'idem-reap-'||n,repeat('a',64),'fixture:v84-reaper','CLAIMED',1,1
                  FROM generate_series(1,130) n
                """).param("org", org).update();
        adminJdbc.sql("""
                INSERT INTO runner_job_leases(runner_job_lease_id,organization_id,schema_version,status,
                    idempotency_key,payload,job_ref,runner_node_ref,actor_id,lease_state,token_sha256,
                    issued_at,expires_at,last_heartbeat_at)
                SELECT 'lease-v84-reap-'||n,:org,'2.0','ISSUED','lease-v84-reap-'||n,'{}'::jsonb,
                    'job-v84-reap-'||n,:runner,'fixture','ISSUED',repeat('b',64),
                    now()-interval '5 minutes',now()-interval '1 minute',now()-interval '2 minutes'
                  FROM generate_series(1,130) n
                """).param("org",org).param("runner",runner).update();
        adminJdbc.sql("""
                INSERT INTO execution_job_dispatch(job_id,organization_id,required_capability,
                    dispatch_state,lease_ref,runner_node_ref,lease_expires_at,attempt)
                SELECT 'job-v84-reap-'||n,:org,'fixture:v84-reaper','LEASED',
                    'lease-v84-reap-'||n,:runner,now()-interval '1 minute',1
                  FROM generate_series(1,130) n
                """).param("org",org).param("runner",runner).update();
        adminJdbc.sql("INSERT INTO execution_dispatch_org_counters(organization_id,leased_count) VALUES(:org,130)")
                .param("org",org).update();
        for (int i=0;i<65;i++) seedRunner(org,"runner-v84-probe-"+i,"fixture:v84-reaper");
        adminJdbc.sql("UPDATE runner_node_authentication SET last_reaped_at=now() "
                + "WHERE runner_node_id NOT LIKE 'runner-v84-probe-%'").update();
        adminJdbc.sql("UPDATE runner_nodes SET last_heartbeat_at=now()-interval '5 minutes' "
                + "WHERE runner_node_id LIKE 'runner-v84-probe-%'").update();
        // The reaper is global: other tests' short real leases may expire while
        // this fixture is built on a busy host. Hold their dispatch rows on a
        // separate connection so actual SKIP LOCKED isolates our 130 records.
        // Do not rewrite other fixtures' status, expiry or counters, or weaken
        // the exact 128/2 work-budget assertions into a tenant-filtered count.
        try (var unrelated = adminConnections.getConnection()) {
            unrelated.setAutoCommit(false);
            try (var lock = unrelated.prepareStatement("SELECT job_id FROM execution_job_dispatch "
                    + "WHERE organization_id<>? AND dispatch_state='LEASED' FOR UPDATE")) {
                lock.setString(1, org);
                try (var rows = lock.executeQuery()) { while (rows.next()) { /* lock every unrelated fixture lease */ } }
            }
            assertEquals(128,adminJdbc.sql("SELECT elmos_reap_execution_leases()").query(Integer.class).single());
            assertEquals(2,adminJdbc.sql("SELECT count(*) FROM execution_job_dispatch "
                    + "WHERE organization_id=:org AND dispatch_state='LEASED'")
                    .param("org",org).query(Integer.class).single());
            assertEquals(64,adminJdbc.sql("SELECT count(*) FROM runner_nodes "
                    + "WHERE runner_node_id LIKE 'runner-v84-probe-%' AND fleet_status='LOST'")
                    .query(Integer.class).single());
            assertEquals(2,adminJdbc.sql("SELECT elmos_reap_execution_leases()").query(Integer.class).single());
            assertEquals(65,adminJdbc.sql("SELECT count(*) FROM runner_nodes "
                    + "WHERE runner_node_id LIKE 'runner-v84-probe-%' AND fleet_status='LOST'")
                    .query(Integer.class).single());
            unrelated.rollback();
        }
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
