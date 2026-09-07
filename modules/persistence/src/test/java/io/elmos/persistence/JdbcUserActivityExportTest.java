package io.elmos.persistence;

import com.fasterxml.jackson.databind.ObjectMapper;
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
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Behaviour of {@link JdbcUserActivityStore#export}.
 *
 * <p>The export exists to produce an audit artifact, so the properties that
 * matter are the ones a spot check would not catch: that paging returns every
 * row exactly once even when timestamps collide, that the cursor terminates,
 * and that the guards refuse a half-formed request rather than silently
 * returning a partial answer.
 */
@Testcontainers(disabledWithoutDocker = true)
class JdbcUserActivityExportTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:17.5-alpine");

    private static final String ORGANIZATION = "org-export-test";
    private static final Instant NOW = Instant.parse("2026-07-28T12:00:00Z");
    private static final Clock CLOCK = Clock.fixed(NOW, ZoneOffset.UTC);

    private static JdbcUserActivityStore store;

    @BeforeAll
    static void migrateAndSeed() {
        Flyway.configure()
                .dataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())
                // See FlywayMigrationTest: V45 creates a schema named "test",
                // which is also this container's username, so an unpinned
                // Flyway relocates its history table the moment that schema
                // appears. Harmless for a single migrate(), pinned anyway so
                // the trap is not re-armed for whoever adds a second call.
                .defaultSchema("public")
                .load()
                .migrate();
        var dataSource = new DriverManagerDataSource(
                POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
        var jdbc = JdbcClient.create(dataSource);

        // product_telemetry_events carries a foreign key to organizations;
        // audit_events does not, because its organization_id was retrofitted by
        // a later tenant migration without one. Seeding the tenant is what the
        // schema actually requires -- and the asymmetry is why the six audit
        // rows below land before the single telemetry row is rejected.
        jdbc.sql("insert into organizations(organization_id) values (?) on conflict do nothing")
                .param(ORGANIZATION)
                .update();

        store = new JdbcUserActivityStore(
                jdbc,
                new TransactionTemplate(new DataSourceTransactionManager(dataSource)),
                new ObjectMapper(),
                CLOCK);

        // Six audit rows. Two share an occurred_at so the keyset has to fall
        // through to event_id -- a naive `occurred_at >` cursor loses or
        // repeats one of them, and that is invisible on distinct timestamps.
        store.append(ORGANIZATION, "actor-1", "request-1", List.of(
                event("evt-a", NOW.minusSeconds(600), "GENERATION", "SUCCESS", null),
                event("evt-b", NOW.minusSeconds(500), "GENERATION", "SUCCESS", null),
                event("evt-c", NOW.minusSeconds(400), "GENERATION", "FAILURE", "UPSTREAM.TIMEOUT"),
                event("evt-d", NOW.minusSeconds(400), "TRANSLATION", "SUCCESS", null),
                event("evt-e", NOW.minusSeconds(300), "TRANSLATION", "SUCCESS", null),
                event("evt-f", NOW.minusSeconds(200), "SPRING", "FAILURE", "BUILD.FAILED")));

        // One telemetry row: the export unions two tables and must label which
        // store a row came from.
        store.appendTelemetry(ORGANIZATION, "actor-1", "request-2", List.of(
                event("evt-t", NOW.minusSeconds(100), "GENERATION", "SUCCESS", null)));
    }

    private static JdbcUserActivityStore.ActivityEvent event(
            String id, Instant at, String businessLine, String result, String errorCode) {
        return new JdbcUserActivityStore.ActivityEvent(
                id, "session-1", "SERVER_OPERATION", "READ", businessLine,
                "/api/v1/example", "example", at, 12, result, errorCode,
                null, null, Map.of());
    }

    private JdbcUserActivityStore.ExportPage firstPage(int limit) {
        return store.export(ORGANIZATION, NOW.minusSeconds(3_600), NOW.plusSeconds(60),
                "ALL", "ALL", null, null, limit);
    }

    /**
     * The property that makes the export trustworthy: walking the cursor visits
     * every row exactly once, in order, including across the duplicated
     * timestamp.
     */
    @Test
    void pagingVisitsEveryRowExactlyOnceInOrder() {
        List<String> whole = firstPage(100).rows().stream()
                .map(JdbcUserActivityStore.ExportRow::eventId).toList();
        assertEquals(7, whole.size());

        List<String> paged = new ArrayList<>();
        Instant afterAt = null;
        String afterId = null;
        for (int guard = 0; guard < 20; guard++) {
            var page = store.export(ORGANIZATION, NOW.minusSeconds(3_600), NOW.plusSeconds(60),
                    "ALL", "ALL", afterAt, afterId, 2);
            page.rows().forEach(row -> paged.add(row.eventId()));
            if (!page.hasMore()) {
                assertNull(page.nextOccurredAt(), "exhausted page must not carry a cursor");
                assertNull(page.nextEventId(), "exhausted page must not carry a cursor");
                break;
            }
            assertNotNull(page.nextOccurredAt());
            assertNotNull(page.nextEventId());
            afterAt = page.nextOccurredAt();
            afterId = page.nextEventId();
        }
        assertEquals(whole, paged, "keyset paging must reproduce the unpaged order exactly");
        assertEquals(whole.size(), List.copyOf(new java.util.LinkedHashSet<>(paged)).size(),
                "keyset paging must not repeat a row");
    }

    @Test
    void ordersAscendingAndBreaksTimestampTiesByEventId() {
        var rows = firstPage(100).rows();
        for (int index = 1; index < rows.size(); index++) {
            var previous = rows.get(index - 1);
            var current = rows.get(index);
            boolean ordered = previous.occurredAt().isBefore(current.occurredAt())
                    || (previous.occurredAt().equals(current.occurredAt())
                        && previous.eventId().compareTo(current.eventId()) < 0);
            assertTrue(ordered, "row " + index + " breaks the (occurred_at, event_id) ordering");
        }
    }

    @Test
    void labelsRowsWithTheStoreTheyCameFrom() {
        var rows = firstPage(100).rows();
        assertEquals(6, rows.stream().filter(row -> "AUDIT".equals(row.source())).count());
        assertEquals(1, rows.stream().filter(row -> "TELEMETRY".equals(row.source())).count());
        assertEquals("evt-t", rows.stream()
                .filter(row -> "TELEMETRY".equals(row.source())).findFirst().orElseThrow().eventId());
    }

    @Test
    void reportsHasMoreOnlyWhileRowsRemain() {
        assertTrue(firstPage(3).hasMore());
        var exact = firstPage(7);
        assertFalse(exact.hasMore(), "a page holding the final row must not claim more");
        assertEquals(7, exact.rows().size());
    }

    @Test
    void filtersByBusinessLineAndResult() {
        var generation = store.export(ORGANIZATION, NOW.minusSeconds(3_600), NOW.plusSeconds(60),
                "GENERATION", "ALL", null, null, 100);
        assertEquals(4, generation.rows().size());
        assertTrue(generation.rows().stream().allMatch(row -> "GENERATION".equals(row.businessLine())));

        var failures = store.export(ORGANIZATION, NOW.minusSeconds(3_600), NOW.plusSeconds(60),
                "ALL", "FAILURE", null, null, 100);
        assertEquals(2, failures.rows().size());
        assertTrue(failures.rows().stream().allMatch(row -> "FAILURE".equals(row.result())));
        assertTrue(failures.rows().stream().anyMatch(row -> "UPSTREAM.TIMEOUT".equals(row.errorCode())));
    }

    @Test
    void isolatesOtherOrganizations() {
        var other = store.export("org-somebody-else", NOW.minusSeconds(3_600), NOW.plusSeconds(60),
                "ALL", "ALL", null, null, 100);
        assertTrue(other.rows().isEmpty(), "an export must not cross the tenant boundary");
    }

    // Argument guards live in JdbcUserActivityExportGuardTest: they reject
    // before any database access, so keeping them here would make them share
    // this class's Docker requirement for no reason.
}
