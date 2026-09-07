package io.elmos.persistence;

import static io.elmos.persistence.SqlTimestamps.offset;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.support.TransactionTemplate;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.Clock;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Supplier;

/**
 * Tenant-isolated audit/telemetry storage and their unified privacy-safe read model.
 *
 * <p>Security and business audit events remain append-only. Product telemetry is
 * deliberately stored separately so an authorized retention run can delete raw
 * technical signals without weakening the immutable audit chain.</p>
 */
@Repository
public class JdbcUserActivityStore {
    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;
    private final ObjectMapper json;
    private final Clock clock;

    public JdbcUserActivityStore(
            JdbcClient jdbc,
            TransactionTemplate transactions,
            ObjectMapper json,
            Clock clock
    ) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
        this.json = Objects.requireNonNull(json, "json");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public record ActivityEvent(
            String eventId,
            String sessionId,
            String eventKind,
            String action,
            String businessLine,
            String route,
            String target,
            Instant occurredAt,
            Integer durationMs,
            String result,
            String errorCode,
            String metricName,
            Double metricValue,
            Map<String, String> metadata
    ) {}

    public record BusinessLineSummary(
            String businessLine,
            long eventCount,
            long sessionCount,
            long failureCount,
            double failureRate,
            Integer p95DurationMs
    ) {}

    public record ErrorSummary(String errorCode, long count, Instant lastSeenAt) {}

    public record RecentEvent(
            String eventId,
            String sessionId,
            String eventKind,
            String action,
            String businessLine,
            String route,
            String target,
            Instant occurredAt,
            Integer durationMs,
            String result,
            String errorCode,
            String metricName,
            Double metricValue
    ) {}

    public record ActivitySummary(
            Instant from,
            Instant to,
            long totalEvents,
            long activeSessions,
            long failedEvents,
            double failureRate,
            Integer p95DurationMs,
            List<BusinessLineSummary> businessLines,
            List<ErrorSummary> topErrors,
            List<RecentEvent> recentEvents,
            String persistence,
            String externalEvidence
    ) {}

    public int append(String organizationId, String actorId, String requestId, List<ActivityEvent> events) {
        requireIdentifier(actorId, "actorId");
        requireIdentifier(requestId, "requestId");
        if (events == null || events.isEmpty() || events.size() > 50) {
            throw new IllegalArgumentException("events must contain between 1 and 50 items");
        }
        return inTenant(organizationId, () -> {
            int inserted = 0;
            for (ActivityEvent event : events) {
                validate(event);
                inserted += jdbc.sql("""
                        insert into audit_events(
                            audit_id, organization_id, actor_type, actor_id, action,
                            resource_type, resource_id, occurred_at, request_id,
                            policy_decision, result, event_kind, business_line, route,
                            target, session_id, duration_ms, error_code, metric_name,
                            metric_value, metadata, received_at)
                        values (
                            :eventId, :organization, 'USER', :actor, :action,
                            'WEB_CONTROL', :target, :occurred, :request,
                            'NOT_APPLICABLE', :result, :eventKind, :businessLine, :route,
                            :target, :session, :duration, :errorCode, :metricName,
                            :metricValue, cast(:metadata as jsonb), current_timestamp)
                        on conflict (audit_id) do nothing
                        """)
                        .param("eventId", event.eventId())
                        .param("organization", organizationId)
                        .param("actor", actorId)
                        .param("action", event.action())
                        .param("target", event.target())
                        .param("occurred", offset(event.occurredAt()))
                        .param("request", requestId)
                        .param("result", event.result())
                        .param("eventKind", event.eventKind())
                        .param("businessLine", event.businessLine())
                        .param("route", event.route())
                        .param("session", event.sessionId())
                        .param("duration", event.durationMs())
                        .param("errorCode", blankToNull(event.errorCode()))
                        .param("metricName", blankToNull(event.metricName()))
                        .param("metricValue", event.metricValue())
                        .param("metadata", metadataJson(event.metadata()))
                        .update();
            }
            return inserted;
        });
    }

    public int appendTelemetry(
            String organizationId,
            String actorId,
            String requestId,
            List<ActivityEvent> events
    ) {
        requireIdentifier(actorId, "actorId");
        requireIdentifier(requestId, "requestId");
        if (events == null || events.isEmpty() || events.size() > 50) {
            throw new IllegalArgumentException("events must contain between 1 and 50 items");
        }
        return inTenant(organizationId, () -> {
            int inserted = 0;
            for (ActivityEvent event : events) {
                validate(event);
                inserted += jdbc.sql("""
                        insert into product_telemetry_events(
                            event_id, organization_id, actor_id, request_id, session_id,
                            event_kind, action, business_line, route, target, occurred_at,
                            duration_ms, result, error_code, metric_name, metric_value, metadata)
                        values (
                            :eventId, :organization, :actor, :request, :session,
                            :eventKind, :action, :businessLine, :route, :target, :occurred,
                            :duration, :result, :errorCode, :metricName, :metricValue,
                            cast(:metadata as jsonb))
                        on conflict (event_id) do nothing
                        """)
                        .param("eventId", event.eventId())
                        .param("organization", organizationId)
                        .param("actor", actorId)
                        .param("request", requestId)
                        .param("session", event.sessionId())
                        .param("eventKind", event.eventKind())
                        .param("action", event.action())
                        .param("businessLine", event.businessLine())
                        .param("route", event.route())
                        .param("target", event.target())
                        .param("occurred", offset(event.occurredAt()))
                        .param("duration", event.durationMs())
                        .param("result", event.result())
                        .param("errorCode", blankToNull(event.errorCode()))
                        .param("metricName", blankToNull(event.metricName()))
                        .param("metricValue", event.metricValue())
                        .param("metadata", metadataJson(event.metadata()))
                        .update();
            }
            return inserted;
        });
    }

    public ActivitySummary summary(
            String organizationId,
            Instant from,
            Instant to,
            String businessLine,
            String result,
            int limit
    ) {
        Objects.requireNonNull(from, "from");
        Objects.requireNonNull(to, "to");
        if (!to.isAfter(from) || to.isAfter(from.plusSeconds(31L * 24 * 60 * 60))) {
            throw new IllegalArgumentException("summary window must be positive and no longer than 31 days");
        }
        if (limit < 1 || limit > 200) throw new IllegalArgumentException("limit must be between 1 and 200");
        String line = normalizeFilter(businessLine);
        String outcome = normalizeFilter(result);
        SummaryFilter filters = SummaryFilter.forValues(line, outcome);
        return inTenant(organizationId, () -> {
            Totals totals = summaryStatement("""
                    with activity_events as (
                        select audit_id event_id, organization_id, session_id, event_kind, action,
                               business_line, route, target, occurred_at, duration_ms, result,
                               error_code, metric_name, metric_value, 'AUDIT' source
                          from audit_events
                        union all
                        select event_id, organization_id, session_id, event_kind, action,
                               business_line, route, target, occurred_at, duration_ms, result,
                               error_code, metric_name, metric_value, 'TELEMETRY' source
                          from product_telemetry_events
                    )
                    select count(*) event_count,
                           count(distinct session_id) filter (
                               where source = 'TELEMETRY' and session_id is not null
                           ) session_count,
                           count(*) filter (
                               where result = 'FAILURE'
                                 and ((source = 'AUDIT' and event_kind = 'SERVER_OPERATION')
                                   or (source = 'TELEMETRY' and event_kind = 'API_REQUEST'))
                           ) failure_count,
                           count(*) filter (
                               where (source = 'AUDIT' and event_kind = 'SERVER_OPERATION')
                                  or (source = 'TELEMETRY' and event_kind = 'API_REQUEST')
                           ) outcome_count,
                           percentile_cont(0.95) within group (order by duration_ms)
                               filter (
                                   where duration_ms is not null
                                     and ((source = 'AUDIT' and event_kind = 'SERVER_OPERATION')
                                       or (source = 'TELEMETRY' and event_kind = 'API_REQUEST'))
                               ) p95_duration
                     from activity_events
                     where organization_id = :organization
                       and occurred_at >= :from and occurred_at < :to
                       %s
                    """, organizationId, from, to, filters, line, outcome)
                    .query((rs, row) -> new Totals(
                            rs.getLong("event_count"), rs.getLong("session_count"),
                            rs.getLong("failure_count"), rs.getLong("outcome_count"),
                            nullableInteger(rs, "p95_duration")))
                    .single();

            List<BusinessLineSummary> lines = summaryStatement("""
                    with activity_events as (
                        select organization_id, session_id, business_line, occurred_at,
                               duration_ms, result, event_kind, 'AUDIT' source
                          from audit_events
                        union all
                        select organization_id, session_id, business_line, occurred_at,
                               duration_ms, result, event_kind, 'TELEMETRY' source
                          from product_telemetry_events
                    )
                    select business_line, count(*) event_count,
                           count(distinct session_id) filter (
                               where source = 'TELEMETRY' and session_id is not null
                           ) session_count,
                           count(*) filter (
                               where result = 'FAILURE'
                                 and ((source = 'AUDIT' and event_kind = 'SERVER_OPERATION')
                                   or (source = 'TELEMETRY' and event_kind = 'API_REQUEST'))
                           ) failure_count,
                           count(*) filter (
                               where (source = 'AUDIT' and event_kind = 'SERVER_OPERATION')
                                  or (source = 'TELEMETRY' and event_kind = 'API_REQUEST')
                           ) outcome_count,
                           percentile_cont(0.95) within group (order by duration_ms)
                               filter (
                                   where duration_ms is not null
                                     and ((source = 'AUDIT' and event_kind = 'SERVER_OPERATION')
                                       or (source = 'TELEMETRY' and event_kind = 'API_REQUEST'))
                               ) p95_duration
                     from activity_events
                     where organization_id = :organization
                       and occurred_at >= :from and occurred_at < :to
                       %s
                     group by business_line
                     order by event_count desc, business_line
                    """, organizationId, from, to, filters, line, outcome)
                    .query((rs, row) -> {
                        long count = rs.getLong("event_count");
                        long failures = rs.getLong("failure_count");
                        long outcomes = rs.getLong("outcome_count");
                        return new BusinessLineSummary(
                                rs.getString("business_line"), count, rs.getLong("session_count"),
                                failures, rate(failures, outcomes), nullableInteger(rs, "p95_duration"));
                    }).list();

            SummaryFilter errorFilters = SummaryFilter.forValues(line, null);
            List<ErrorSummary> errors = summaryStatement("""
                    with activity_events as (
                        select organization_id, business_line, occurred_at, result, error_code
                          from audit_events
                        union all
                        select organization_id, business_line, occurred_at, result, error_code
                          from product_telemetry_events
                    )
                    select coalesce(error_code, 'UNCLASSIFIED_FAILURE') error_code,
                           count(*) error_count, max(occurred_at) last_seen
                      from activity_events
                     where organization_id = :organization
                       and occurred_at >= :from and occurred_at < :to
                       and result = 'FAILURE'
                       %s
                     group by coalesce(error_code, 'UNCLASSIFIED_FAILURE')
                     order by error_count desc, error_code
                     limit 10
                    """, organizationId, from, to, errorFilters, line, null)
                    .query((rs, row) -> new ErrorSummary(
                            rs.getString("error_code"), rs.getLong("error_count"),
                            instant(rs.getObject("last_seen", OffsetDateTime.class))))
                    .list();

            List<RecentEvent> recent = summaryStatement("""
                    with activity_events as (
                        select audit_id event_id, organization_id, session_id, event_kind, action,
                               business_line, route, target, occurred_at, duration_ms, result,
                               error_code, metric_name, metric_value
                          from audit_events
                        union all
                        select event_id, organization_id, session_id, event_kind, action,
                               business_line, route, target, occurred_at, duration_ms, result,
                               error_code, metric_name, metric_value
                          from product_telemetry_events
                    )
                    select event_id, session_id, event_kind, action, business_line, route,
                           target, occurred_at, duration_ms, result, error_code,
                           metric_name, metric_value
                     from activity_events
                     where organization_id = :organization
                       and occurred_at >= :from and occurred_at < :to
                       %s
                     order by occurred_at desc, event_id desc
                     limit :limit
                    """, organizationId, from, to, filters, line, outcome)
                    .param("limit", limit)
                    .query(JdbcUserActivityStore::mapRecent)
                    .list();

            return new ActivitySummary(
                    from, to, totals.eventCount(), totals.sessionCount(), totals.failureCount(),
                    rate(totals.failureCount(), totals.outcomeCount()), totals.p95DurationMs(),
                    lines, errors, recent, "POSTGRES_DUAL_STORE", "NOT_RUN");
        });
    }

    /** One exported row. Carries `source` so an auditor can tell the two stores apart. */
    public record ExportRow(
            String eventId,
            String source,
            String sessionId,
            String eventKind,
            String action,
            String businessLine,
            String route,
            String target,
            Instant occurredAt,
            Integer durationMs,
            String result,
            String errorCode
    ) {}

    /**
     * One page of an export, with the cursor needed to fetch the next one.
     *
     * <p>{@code nextOccurredAt}/{@code nextEventId} are null exactly when
     * {@code hasMore} is false.
     */
    public record ExportPage(
            Instant from,
            Instant to,
            List<ExportRow> rows,
            boolean hasMore,
            Instant nextOccurredAt,
            String nextEventId
    ) {}

    /**
     * Read raw activity rows for an audit export, one keyset page at a time.
     *
     * <p>Paging is by {@code (occurred_at, event_id)} rather than an offset on
     * purpose. Events keep arriving while an export runs, and an offset would
     * silently skip or duplicate rows as the underlying set shifts -- for an
     * audit artifact that is a correctness defect, not a cosmetic one. The
     * keyset is stable because the pair is unique and the ordering matches it.
     *
     * <p>The window is capped at 366 days. Unbounded exports would let a single
     * request pin an arbitrary amount of the table in memory.
     */
    public ExportPage export(
            String organizationId,
            Instant from,
            Instant to,
            String businessLine,
            String result,
            Instant afterOccurredAt,
            String afterEventId,
            int limit
    ) {
        Objects.requireNonNull(from, "from");
        Objects.requireNonNull(to, "to");
        if (!to.isAfter(from) || to.isAfter(from.plusSeconds(366L * 24 * 60 * 60))) {
            throw new IllegalArgumentException("export window must be positive and no longer than 366 days");
        }
        if (limit < 1 || limit > 1000) throw new IllegalArgumentException("limit must be between 1 and 1000");
        if ((afterOccurredAt == null) != (afterEventId == null)) {
            throw new IllegalArgumentException("export cursor requires both occurredAt and eventId");
        }
        String line = normalizeFilter(businessLine);
        String outcome = normalizeFilter(result);
        return inTenant(organizationId, () -> {
            // One extra row is read so the caller learns whether another page
            // exists without paying for a second count query.
            List<ExportRow> rows = jdbc.sql("""
                    with activity_events as (
                        select audit_id event_id, organization_id, session_id, event_kind, action,
                               business_line, route, target, occurred_at, duration_ms, result,
                               error_code, 'AUDIT' source
                          from audit_events
                        union all
                        select event_id, organization_id, session_id, event_kind, action,
                               business_line, route, target, occurred_at, duration_ms, result,
                               error_code, 'TELEMETRY' source
                          from product_telemetry_events
                    )
                    select event_id, source, session_id, event_kind, action, business_line,
                           route, target, occurred_at, duration_ms, result, error_code
                      from activity_events
                     where organization_id = :organization
                       and occurred_at >= :from and occurred_at < :to
                       -- Every optional filter is cast explicitly. A bare
                       -- parameter in `? is null` gives PostgreSQL nothing to
                       -- infer a type from -- the column is not in the
                       -- expression, and a null binding carries no type of its
                       -- own -- so the statement fails to parse with "could not
                       -- determine data type of parameter". The comparison arms
                       -- (`business_line = :line`) infer from the column and
                       -- would be fine alone; it is the null test that has no
                       -- other source of type.
                       and (cast(:line as text) is null or business_line = :line)
                       and (cast(:result as text) is null or result = :result)
                       and (cast(:afterOccurredAt as timestamptz) is null
                            or (occurred_at, event_id)
                                > (cast(:afterOccurredAt as timestamptz),
                                   cast(:afterEventId as text)))
                     order by occurred_at, event_id
                     limit :limit
                    """)
                    .param("organization", organizationId).param("from", offset(from)).param("to", offset(to))
                    .param("line", line).param("result", outcome)
                    .param("afterOccurredAt", offset(afterOccurredAt)).param("afterEventId", afterEventId)
                    .param("limit", limit + 1)
                    .query(JdbcUserActivityStore::mapExport)
                    .list();
            boolean hasMore = rows.size() > limit;
            List<ExportRow> page = hasMore ? List.copyOf(rows.subList(0, limit)) : rows;
            ExportRow last = page.isEmpty() ? null : page.get(page.size() - 1);
            return new ExportPage(
                    from,
                    to,
                    page,
                    hasMore,
                    hasMore && last != null ? last.occurredAt() : null,
                    hasMore && last != null ? last.eventId() : null);
        });
    }

    private static ExportRow mapExport(ResultSet rs, int row) throws SQLException {
        return new ExportRow(
                rs.getString("event_id"),
                rs.getString("source"),
                rs.getString("session_id"),
                rs.getString("event_kind"),
                rs.getString("action"),
                rs.getString("business_line"),
                rs.getString("route"),
                rs.getString("target"),
                instant(rs.getObject("occurred_at", OffsetDateTime.class)),
                nullableInteger(rs, "duration_ms"),
                rs.getString("result"),
                rs.getString("error_code"));
    }

    /**
     * Builds one of four fixed predicate shapes. The selected fragment is an
     * internal enum constant, never request text, while every filter value
     * remains a named bind. Separate shapes let PostgreSQL use the
     * organization/business-line or organization/result indexes even after the
     * driver promotes a frequently used statement to a generic prepared plan.
     */
    private JdbcClient.StatementSpec summaryStatement(
            String sql,
            String organizationId,
            Instant from,
            Instant to,
            SummaryFilter filters,
            String businessLine,
            String result
    ) {
        JdbcClient.StatementSpec statement = jdbc.sql(sql.formatted(filters.predicate()))
                .param("organization", organizationId)
                .param("from", offset(from))
                .param("to", offset(to));
        if (filters.businessLine()) {
            statement = statement.param("line", businessLine);
        }
        if (filters.result()) {
            statement = statement.param("result", result);
        }
        return statement;
    }

    private enum SummaryFilter {
        NONE("", false, false),
        BUSINESS_LINE("and business_line = :line", true, false),
        RESULT("and result = :result", false, true),
        BUSINESS_LINE_AND_RESULT(
                "and business_line = :line and result = :result", true, true);

        private final String predicate;
        private final boolean businessLine;
        private final boolean result;

        SummaryFilter(String predicate, boolean businessLine, boolean result) {
            this.predicate = predicate;
            this.businessLine = businessLine;
            this.result = result;
        }

        static SummaryFilter forValues(String businessLine, String result) {
            if (businessLine != null && result != null) return BUSINESS_LINE_AND_RESULT;
            if (businessLine != null) return BUSINESS_LINE;
            if (result != null) return RESULT;
            return NONE;
        }

        String predicate() {
            return predicate;
        }

        boolean businessLine() {
            return businessLine;
        }

        boolean result() {
            return result;
        }
    }

    private record Totals(
            long eventCount,
            long sessionCount,
            long failureCount,
            long outcomeCount,
            Integer p95DurationMs
    ) {}

    private <T> T inTenant(String organizationId, Supplier<T> work) {
        requireIdentifier(organizationId, "organizationId");
        return transactions.execute(status -> {
            jdbc.sql("select set_config('app.organization_id', :organization, true)")
                    .param("organization", organizationId).query(String.class).single();
            return work.get();
        });
    }

    private static RecentEvent mapRecent(ResultSet rs, int row) throws SQLException {
        Number metric = (Number) rs.getObject("metric_value");
        return new RecentEvent(
                rs.getString("event_id"), rs.getString("session_id"), rs.getString("event_kind"),
                rs.getString("action"), rs.getString("business_line"), rs.getString("route"),
                rs.getString("target"), instant(rs.getObject("occurred_at", OffsetDateTime.class)),
                (Integer) rs.getObject("duration_ms"), rs.getString("result"), rs.getString("error_code"),
                rs.getString("metric_name"), metric == null ? null : metric.doubleValue());
    }

    private void validate(ActivityEvent event) {
        Objects.requireNonNull(event, "event");
        requireIdentifier(event.eventId(), "eventId");
        requireIdentifier(event.sessionId(), "sessionId");
        requireToken(event.eventKind(), "eventKind", 32);
        requireToken(event.action(), "action", 64);
        requireToken(event.businessLine(), "businessLine", 64);
        requireSafeText(event.route(), "route", 160);
        requireSafeText(event.target(), "target", 160);
        Objects.requireNonNull(event.occurredAt(), "occurredAt");
        Instant now = clock.instant();
        if (event.occurredAt().isBefore(now.minusSeconds(7L * 24 * 60 * 60))
                || event.occurredAt().isAfter(now.plusSeconds(5 * 60))) {
            throw new IllegalArgumentException("occurredAt is outside the accepted delivery window");
        }
        if (event.durationMs() != null && (event.durationMs() < 0 || event.durationMs() > 3_600_000)) {
            throw new IllegalArgumentException("durationMs is outside the accepted range");
        }
        if (!List.of("SUCCESS", "FAILURE", "CANCELLED").contains(event.result())) {
            throw new IllegalArgumentException("result is invalid");
        }
        if (event.errorCode() != null) requireToken(event.errorCode(), "errorCode", 96);
        if (event.metricName() != null) requireToken(event.metricName(), "metricName", 64);
        if (event.metricValue() != null && !Double.isFinite(event.metricValue())) {
            throw new IllegalArgumentException("metricValue must be finite");
        }
        Map<String, String> metadata = event.metadata() == null ? Map.of() : event.metadata();
        if (metadata.size() > 8) throw new IllegalArgumentException("metadata has too many dimensions");
        for (Map.Entry<String, String> entry : metadata.entrySet()) {
            requireToken(entry.getKey(), "metadata key", 32);
            requireSafeText(entry.getValue(), "metadata value", 64);
        }
    }

    private String metadataJson(Map<String, String> metadata) {
        try {
            return json.writeValueAsString(metadata == null ? Map.of() : metadata);
        } catch (JsonProcessingException error) {
            throw new IllegalArgumentException("metadata cannot be serialized", error);
        }
    }

    private static String normalizeFilter(String value) {
        if (value == null || value.isBlank() || "ALL".equalsIgnoreCase(value)) return null;
        requireToken(value, "filter", 64);
        return value;
    }

    private static void requireIdentifier(String value, String field) {
        requireSafeText(value, field, 128);
        if (!value.matches("[A-Za-z0-9][A-Za-z0-9._:-]*")) {
            throw new IllegalArgumentException(field + " contains unsupported characters");
        }
    }

    private static void requireToken(String value, String field, int maxLength) {
        requireSafeText(value, field, maxLength);
        if (!value.matches("[A-Z0-9][A-Z0-9._:-]*")) {
            throw new IllegalArgumentException(field + " must be an uppercase contract token");
        }
    }

    private static void requireSafeText(String value, String field, int maxLength) {
        if (value == null || value.isBlank() || value.length() > maxLength
                || value.indexOf('\n') >= 0 || value.indexOf('\r') >= 0 || value.indexOf('\0') >= 0) {
            throw new IllegalArgumentException(field + " is invalid");
        }
    }

    private static Integer nullableInteger(ResultSet rs, String column) throws SQLException {
        Number number = (Number) rs.getObject(column);
        return number == null ? null : (int) Math.round(number.doubleValue());
    }

    private static double rate(long numerator, long denominator) {
        return denominator == 0 ? 0.0 : Math.round((numerator * 10_000.0 / denominator)) / 100.0;
    }

    private static Instant instant(OffsetDateTime value) {
        return value.toInstant();
    }


    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }
}
