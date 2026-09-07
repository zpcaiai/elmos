package io.elmos.persistence;

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

import javax.sql.DataSource;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Behaviour of {@link JdbcRunHistoryStore#replay} against real PostgreSQL.
 *
 * <p>Two kinds of claim are proved here, and they are not the same kind. The
 * reconstruction claims -- ordering, retained attempts, tenant isolation,
 * honest truncation -- are ordinary behaviour. The read-only claim is a
 * security property, and it is checked twice on purpose: once by observing that
 * a replay changes nothing, and once by confirming that the mechanism it relies
 * on actually refuses a write. The first alone would pass for a store that
 * simply happens not to write today; the second alone would prove PostgreSQL
 * works but say nothing about this class.
 */
@Testcontainers(disabledWithoutDocker = true)
class JdbcRunHistoryReplayTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:17.5-alpine");

    private static final String ORGANIZATION = "org-replay-test";
    private static final String OTHER_ORGANIZATION = "org-replay-other";
    private static final String RUN = "run-replay-1";
    private static final String OTHER_RUN = "run-replay-other";
    private static final Instant T0 = Instant.parse("2026-07-28T09:00:00Z");

    private static DataSource dataSource;
    private static JdbcClient jdbc;
    private static DataSourceTransactionManager transactionManager;
    private static JdbcRunHistoryStore store;

    @BeforeAll
    static void migrateAndSeed() {
        Flyway.configure()
                .dataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())
                // See FlywayMigrationTest: a product schema shares its name with
                // this container's user, so an unpinned Flyway relocates its
                // history table mid-run.
                .defaultSchema("public")
                .load()
                .migrate();
        dataSource = new DriverManagerDataSource(
                POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
        jdbc = JdbcClient.create(dataSource);
        transactionManager = new DataSourceTransactionManager(dataSource);
        store = new JdbcRunHistoryStore(jdbc, transactionManager);

        // organizations is the tenant registry itself and is excluded from the
        // row-level security retrofit, so it is the one table seeded plainly.
        for (String organization : List.of(ORGANIZATION, OTHER_ORGANIZATION)) {
            jdbc.sql("insert into organizations(organization_id) values (?) on conflict do nothing")
                    .param(organization).update();
        }

        seedRun(ORGANIZATION, RUN, "repo-1", "snap-1", "plan-1");
        seedRun(OTHER_ORGANIZATION, OTHER_RUN, "repo-2", "snap-2", "plan-2");

        inTenant(ORGANIZATION, () -> {
            // Three steps whose story only survives if attempts are kept and
            // order is by clock: compile fails, compile is retried and succeeds,
            // and a publish step that never began.
            step("sr-1", RUN, "compile", 1, "FAILED", at(60), at(120), "COMPILE.ERROR");
            step("sr-2", RUN, "compile", 2, "SUCCEEDED", at(180), at(240), null);
            step("sr-3", RUN, "verify", 1, "SUCCEEDED", at(300), at(360), null);
            step("sr-4", RUN, "publish", 1, "PENDING", null, null, null);

            evidence("ev-1", ORGANIZATION, RUN, "sr-2", "BUILD_LOG", at(240));
            evidence("ev-2", ORGANIZATION, RUN, "sr-3", "TEST_REPORT", at(360));

            audit("au-1", ORGANIZATION, RUN, "MIGRATION_RUN_STARTED", at(0));
            audit("au-2", ORGANIZATION, RUN, "MIGRATION_RUN_COMPLETED", at(400));
            return null;
        });
    }

    private static OffsetDateTime at(long secondsAfterStart) {
        return T0.plusSeconds(secondsAfterStart).atOffset(ZoneOffset.UTC);
    }

    private static void seedRun(
            String organization, String run, String repository, String snapshot, String plan) {
        inTenant(organization, () -> {
            jdbc.sql("""
                    insert into repositories(repository_id, organization_id, scm_provider,
                                             external_id, default_branch)
                    values (:repository, :organization, 'GITHUB', :repository, 'main')
                    """)
                    .param("repository", repository).param("organization", organization).update();
            jdbc.sql("""
                    insert into repository_snapshots(snapshot_id, organization_id, repository_id,
                            commit_sha, requested_ref, captured_at, build_files_hash, archive_artifact_ref)
                    values (:snapshot, :organization, :repository, 'abc123', 'main',
                            :capturedAt, 'hash', 'ref')
                    """)
                    .param("snapshot", snapshot).param("organization", organization)
                    .param("repository", repository).param("capturedAt", at(0)).update();
            jdbc.sql("""
                    insert into migration_plans(migration_plan_id, organization_id, snapshot_id,
                            plan_version, status, source_profile, target_profile)
                    values (:plan, :organization, :snapshot, 1, 'APPROVED', 'boot-1.5', 'boot-3.5')
                    """)
                    .param("plan", plan).param("organization", organization)
                    .param("snapshot", snapshot).update();
            jdbc.sql("""
                    insert into migration_runs(migration_run_id, organization_id, snapshot_id,
                            migration_plan_id, plan_version, state)
                    values (:run, :organization, :snapshot, :plan, 1, 'COMPLETED')
                    """)
                    .param("run", run).param("organization", organization)
                    .param("snapshot", snapshot).param("plan", plan).update();
            return null;
        });
    }

    private static void step(
            String stepRunId, String run, String stepId, int attempt, String state,
            OffsetDateTime startedAt, OffsetDateTime finishedAt, String failureCode) {
        jdbc.sql("""
                insert into migration_step_runs(step_run_id, organization_id, migration_run_id,
                        step_id, attempt, executor_type, state, started_at, finished_at, failure_code)
                values (:stepRunId, :organization, :run, :stepId, :attempt, 'RECIPE', :state,
                        :startedAt, :finishedAt, :failureCode)
                """)
                .param("stepRunId", stepRunId).param("organization", ORGANIZATION)
                .param("run", run).param("stepId", stepId)
                .param("attempt", attempt).param("state", state)
                .param("startedAt", startedAt).param("finishedAt", finishedAt)
                .param("failureCode", failureCode).update();
    }

    private static void evidence(
            String evidenceId, String organization, String run, String stepRunId,
            String evidenceType, OffsetDateTime createdAt) {
        jdbc.sql("""
                insert into evidence(evidence_id, organization_id, migration_run_id, step_run_id,
                        evidence_type, producer_type, producer_name, producer_version,
                        source_commit, created_at, status, summary, artifact_ref,
                        content_hash, schema_version, correlation_id)
                values (:evidenceId, :organization, :run, :stepRunId, :evidenceType,
                        'ENGINE', 'elmos-java-engine', '1.0.0', 'abc123', :createdAt,
                        'PASSED', 'summary', 'ref', 'sha256:0', '1.0', :run)
                """)
                .param("evidenceId", evidenceId).param("organization", organization)
                .param("run", run).param("stepRunId", stepRunId)
                .param("evidenceType", evidenceType).param("createdAt", createdAt).update();
    }

    private static void audit(
            String auditId, String organization, String run, String action, OffsetDateTime occurredAt) {
        jdbc.sql("""
                insert into audit_events(audit_id, organization_id, actor_type, actor_id, action,
                        resource_type, resource_id, occurred_at, request_id,
                        policy_decision, result)
                values (:auditId, :organization, 'USER', 'actor-1', :action,
                        'MIGRATION_RUN', :run, :occurredAt, 'req-1', 'ALLOW', 'SUCCESS')
                """)
                .param("auditId", auditId).param("organization", organization)
                .param("action", action).param("run", run)
                .param("occurredAt", occurredAt).update();
    }

    private static <T> T inTenant(String organization, java.util.function.Supplier<T> work) {
        return new TransactionTemplate(transactionManager).execute(status -> {
            jdbc.sql("select set_config('app.organization_id', :organization, true)")
                    .param("organization", organization).query(String.class).single();
            return work.get();
        });
    }

    private static JdbcRunHistoryStore.RunTimeline timeline() {
        return store.replay(ORGANIZATION, RUN).orElseThrow();
    }

    /**
     * The property that makes a replay usable as evidence: the attempts are all
     * there, in the order they happened. Collapsing {@code compile} to its
     * final success would erase the failure that explains why the run took the
     * shape it did.
     */
    @Test
    void keepsEveryAttemptInChronologicalOrder() {
        List<JdbcRunHistoryStore.StepAttempt> steps = timeline().steps().rows();
        assertEquals(
                List.of("sr-1", "sr-2", "sr-3", "sr-4"),
                steps.stream().map(JdbcRunHistoryStore.StepAttempt::stepRunId).toList());
        assertEquals(2, steps.get(1).attempt(), "the retry must keep its attempt number");
        assertEquals("COMPILE.ERROR", steps.get(0).failureCode());
        assertNull(steps.get(1).failureCode(), "the successful retry carries no failure code");
    }

    /** A step that never started still belongs in the story, at the end rather than dropped. */
    @Test
    void placesAStepThatNeverStartedLast() {
        List<JdbcRunHistoryStore.StepAttempt> steps = timeline().steps().rows();
        JdbcRunHistoryStore.StepAttempt last = steps.get(steps.size() - 1);
        assertEquals("publish", last.stepId());
        assertNull(last.startedAt());
    }

    @Test
    void carriesTheRunHeaderEvidenceAndAudit() {
        JdbcRunHistoryStore.RunTimeline run = timeline();
        assertEquals("snap-1", run.snapshotId());
        assertEquals("plan-1", run.migrationPlanId());
        assertEquals(1, run.planVersion());
        assertEquals("COMPLETED", run.state());

        assertEquals(
                List.of("ev-1", "ev-2"),
                run.evidence().rows().stream().map(JdbcRunHistoryStore.EvidenceRef::evidenceId).toList());
        assertEquals("sr-2", run.evidence().rows().get(0).stepRunId());

        assertEquals(
                List.of("au-1", "au-2"),
                run.audit().rows().stream().map(JdbcRunHistoryStore.AuditEntry::auditId).toList());
    }

    @Test
    void reportsCompleteSectionsAsNotTruncated() {
        JdbcRunHistoryStore.RunTimeline run = timeline();
        assertFalse(run.steps().truncated());
        assertFalse(run.evidence().truncated());
        assertFalse(run.audit().truncated());
    }

    /**
     * A cap the seed can actually reach. Without this the flag would only ever
     * be exercised at 2000 rows, which is to say never.
     */
    @Test
    void reportsTruncationRatherThanSilentlyShortening() {
        var capped = new JdbcRunHistoryStore(jdbc, transactionManager, 2);
        JdbcRunHistoryStore.RunTimeline run = capped.replay(ORGANIZATION, RUN).orElseThrow();
        assertEquals(2, run.steps().rows().size());
        assertTrue(run.steps().truncated(), "four steps under a cap of two must be reported as truncated");
        assertFalse(run.evidence().truncated(), "two evidence rows fit exactly and are not truncated");
    }

    /** A run belonging to another tenant is indistinguishable from one that does not exist. */
    @Test
    void refusesAnotherTenantsRun() {
        assertTrue(store.replay(ORGANIZATION, OTHER_RUN).isEmpty());
        assertTrue(store.replay(ORGANIZATION, "run-does-not-exist").isEmpty());
    }

    /**
     * Observational half of the read-only claim: a replay leaves the rows it
     * read exactly as it found them.
     */
    @Test
    void leavesTheSourceRowsUnchanged() {
        List<String> before = fingerprint();
        timeline();
        assertEquals(before, fingerprint(), "replay must not alter what it reconstructs");
    }

    /**
     * Mechanical half: the read-only transaction the store runs in is one
     * PostgreSQL genuinely refuses to write from. This asserts the mechanism,
     * not the class -- but without it, {@link #leavesTheSourceRowsUnchanged}
     * would only be saying that today's implementation happens not to write.
     */
    @Test
    void theReadOnlyTransactionRefusesAWrite() {
        TransactionTemplate readOnly = new TransactionTemplate(transactionManager);
        readOnly.setReadOnly(true);
        assertThrows(Exception.class, () -> readOnly.execute(status -> {
            jdbc.sql("select set_config('app.organization_id', :organization, true)")
                    .param("organization", ORGANIZATION).query(String.class).single();
            return jdbc.sql("update migration_runs set state = 'TAMPERED' where migration_run_id = :run")
                    .param("run", RUN).update();
        }), "a read-only transaction must refuse an update");

        assertEquals("COMPLETED", timeline().state(), "the refused write must have left no trace");
    }

    private static List<String> fingerprint() {
        return inTenant(ORGANIZATION, () -> jdbc.sql("""
                select 'runs=' || (select count(*) || ':' || coalesce(max(state), '')
                                     from migration_runs where migration_run_id = :run)
                    || ' steps=' || (select count(*) || ':' || coalesce(string_agg(state, ',' order by step_run_id), '')
                                     from migration_step_runs where migration_run_id = :run)
                    || ' evidence=' || (select count(*) || ':' || coalesce(string_agg(status, ',' order by evidence_id), '')
                                     from evidence where migration_run_id = :run)
                    || ' audit=' || (select count(*) || ':' || coalesce(string_agg(result, ',' order by audit_id), '')
                                     from audit_events where resource_id = :run)
                """).param("run", RUN).query(String.class).list());
    }
}
