package io.elmos.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.workflow.ExecutionJobPort;
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

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * PostgreSQL regression coverage for the management read paths.
 *
 * <p>These queries intentionally run against the exact PostgreSQL major used by
 * the local commercial stack. An in-memory database accepts untyped null binds
 * that PostgreSQL rejects while parsing, so a mock or H2 test cannot protect
 * this boundary.</p>
 */
@Testcontainers(disabledWithoutDocker = true)
class JdbcOperationalReadQueryTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:17.5-alpine");

    private static final String ORGANIZATION = "org-operational-read";
    private static final String OTHER_ORGANIZATION = "org-operational-read-other";
    private static final Instant NOW = Instant.parse("2026-08-09T00:00:00Z");

    private static JdbcUserActivityStore activity;
    private static JdbcExecutionJobStore jobs;
    private static JdbcClient readerJdbc;

    @BeforeAll
    static void migrateAndSeed() {
        Flyway.configure()
                .dataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())
                .defaultSchema("public")
                .load()
                .migrate();
        var dataSource = new DriverManagerDataSource(
                POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
        var jdbc = JdbcClient.create(dataSource);
        var transactions = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource));
        jdbc.sql("insert into organizations(organization_id) values (:organization)")
                .param("organization", ORGANIZATION)
                .update();
        jdbc.sql("insert into organizations(organization_id) values (:organization)")
                .param("organization", OTHER_ORGANIZATION)
                .update();

        var seedActivity = new JdbcUserActivityStore(
                jdbc, transactions, new ObjectMapper(), Clock.fixed(NOW, ZoneOffset.UTC));
        seedActivity.append(ORGANIZATION, "actor-1", "request-1", List.of(
                event("event-generation", "GENERATION", "SUCCESS", "SERVER_OPERATION")));
        seedActivity.appendTelemetry(ORGANIZATION, "actor-1", "request-2", List.of(
                event("event-translation", "TRANSLATION", "FAILURE", "API_REQUEST")));
        seedActivity.append(OTHER_ORGANIZATION, "actor-2", "request-3", List.of(
                event("event-other-tenant", "GENERATION", "SUCCESS", "SERVER_OPERATION")));

        // Seed the disposable database directly. Calling enqueue here would
        // intentionally exercise the separate commercial-entitlement gate,
        // which is not part of this read-query regression fixture.
        seedJob(jdbc, ORGANIZATION, "job-generation", "GENERATION", "generate",
                "idem-generation", "1".repeat(64), "generation:java", "2".repeat(64));
        seedJob(jdbc, ORGANIZATION, "job-translation", "TRANSLATION", "translate",
                "idem-translation", "3".repeat(64), "translation:java", "4".repeat(64));
        seedJob(jdbc, OTHER_ORGANIZATION, "job-other-tenant", "GENERATION", "generate",
                "idem-other", "5".repeat(64), "generation:java", "6".repeat(64));

        // Testcontainers' default PostgreSQL user is a superuser and therefore
        // bypasses RLS even when FORCE ROW LEVEL SECURITY is enabled. Exercise
        // the store through a deliberately constrained application role.
        jdbc.sql("create role elmos_operational_reader login password 'test-only-password' "
                        + "nosuperuser nocreatedb nocreaterole noinherit nobypassrls")
                .update();
        jdbc.sql("grant usage on schema public to elmos_operational_reader").update();
        jdbc.sql("grant select on execution_jobs, audit_events, product_telemetry_events "
                        + "to elmos_operational_reader")
                .update();
        var applicationDataSource = new DriverManagerDataSource(
                POSTGRES.getJdbcUrl(), "elmos_operational_reader", "test-only-password");
        readerJdbc = JdbcClient.create(applicationDataSource);
        var readerTransactions = new TransactionTemplate(
                new DataSourceTransactionManager(applicationDataSource));
        activity = new JdbcUserActivityStore(
                readerJdbc, readerTransactions, new ObjectMapper(), Clock.fixed(NOW, ZoneOffset.UTC));
        jobs = new JdbcExecutionJobStore(
                readerJdbc,
                readerTransactions,
                new ObjectMapper());
    }

    @Test
    void activitySummaryAcceptsAbsentAndExactFiltersOnPostgres() {
        var all = activity.summary(
                ORGANIZATION, NOW.minusSeconds(3_600), NOW.plusSeconds(60),
                "ALL", "ALL", 20);
        assertEquals(2, all.totalEvents());
        assertEquals(2, all.recentEvents().size());

        var generation = activity.summary(
                ORGANIZATION, NOW.minusSeconds(3_600), NOW.plusSeconds(60),
                "GENERATION", "ALL", 20);
        assertEquals(1, generation.totalEvents());
        assertEquals("event-generation", generation.recentEvents().getFirst().eventId());

        var failures = activity.summary(
                ORGANIZATION, NOW.minusSeconds(3_600), NOW.plusSeconds(60),
                "ALL", "FAILURE", 20);
        assertEquals(1, failures.totalEvents());
        assertEquals("event-translation", failures.recentEvents().getFirst().eventId());

        var translationFailures = activity.summary(
                ORGANIZATION, NOW.minusSeconds(3_600), NOW.plusSeconds(60),
                "TRANSLATION", "FAILURE", 20);
        assertEquals(1, translationFailures.totalEvents());
        assertEquals("event-translation", translationFailures.recentEvents().getFirst().eventId());
    }

    @Test
    void constrainedActivityReaderHasNoRowsWithoutTenantContext() {
        assertEquals(0L, readerJdbc.sql("select count(*) from audit_events")
                .query(Long.class).single());
        assertEquals(0L, readerJdbc.sql("select count(*) from product_telemetry_events")
                .query(Long.class).single());
    }

    @Test
    void executionJobListUsesSeparateBoundedSqlShapes() {
        var all = jobs.list(ORGANIZATION, null, 10, 0);
        assertEquals(2, all.size());

        var generation = jobs.list(
                ORGANIZATION, ExecutionJobPort.BusinessLine.GENERATION, 10, 0);
        assertEquals(1, generation.size());
        assertEquals("job-generation", generation.getFirst().jobId());
        var other = jobs.list(OTHER_ORGANIZATION, null, 10, 0);
        assertEquals(1, other.size());
        assertEquals("job-other-tenant", other.getFirst().jobId());
    }

    @Test
    void executionJobListRejectsUnboundedPaginationAtTheStoreBoundary() {
        var zeroLimit = assertThrows(
                ExecutionJobPort.ExecutionStateException.class,
                () -> jobs.list(ORGANIZATION, null, 0, 0));
        assertEquals("ELMOS_EXECUTION_LIMIT_INVALID", zeroLimit.code());

        var excessiveLimit = assertThrows(
                ExecutionJobPort.ExecutionStateException.class,
                () -> jobs.list(ORGANIZATION, null, 101, 0));
        assertEquals("ELMOS_EXECUTION_LIMIT_INVALID", excessiveLimit.code());

        var negativeOffset = assertThrows(
                ExecutionJobPort.ExecutionStateException.class,
                () -> jobs.list(ORGANIZATION, null, 10, -1));
        assertEquals("ELMOS_EXECUTION_OFFSET_INVALID", negativeOffset.code());

        var excessiveOffset = assertThrows(
                ExecutionJobPort.ExecutionStateException.class,
                () -> jobs.list(ORGANIZATION, null, 10, 10_001));
        assertEquals("ELMOS_EXECUTION_OFFSET_INVALID", excessiveOffset.code());
    }

    private static JdbcUserActivityStore.ActivityEvent event(
            String id,
            String businessLine,
            String result,
            String eventKind
    ) {
        return new JdbcUserActivityStore.ActivityEvent(
                id,
                "session-1",
                eventKind,
                "READ",
                businessLine,
                "/api/v1/example",
                "example",
                NOW.minusSeconds(60),
                12,
                result,
                "FAILURE".equals(result) ? "EXPECTED.FAILURE" : null,
                null,
                null,
                Map.of());
    }

    private static void seedJob(
            JdbcClient jdbc,
            String organizationId,
            String jobId,
            String businessLine,
            String jobKind,
            String idempotencyKey,
            String requestDigest,
            String requiredCapability,
            String imageDigest
    ) {
        jdbc.sql("""
                insert into execution_jobs(
                    job_id, organization_id, actor_id, business_line, job_kind,
                    idempotency_key, request_digest, request_payload,
                    required_capability, runner_image)
                values (
                    :jobId, :organization, 'actor-1', :businessLine, :jobKind,
                    :idempotencyKey, :requestDigest, '{"request":"bounded"}'::jsonb,
                    :requiredCapability, :runnerImage)
                """)
                .param("jobId", jobId)
                .param("organization", organizationId)
                .param("businessLine", businessLine)
                .param("jobKind", jobKind)
                .param("idempotencyKey", idempotencyKey)
                .param("requestDigest", requestDigest)
                .param("requiredCapability", requiredCapability)
                .param("runnerImage", "registry.example.test/elmos/runner@sha256:" + imageDigest)
                .update();
    }
}
