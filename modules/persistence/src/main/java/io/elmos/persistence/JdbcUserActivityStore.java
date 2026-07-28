package io.elmos.persistence;

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
 * Tenant-isolated, append-only storage and read model for privacy-safe user activity.
 */
@Repository
public final class JdbcUserActivityStore {
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
                        .param("occurred", event.occurredAt())
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
        return inTenant(organizationId, () -> {
            Totals totals = jdbc.sql("""
                    select count(*) event_count,
                           count(distinct session_id) filter (where session_id is not null) session_count,
                           count(*) filter (where result = 'FAILURE') failure_count,
                           percentile_cont(0.95) within group (order by duration_ms)
                               filter (where duration_ms is not null) p95_duration
                      from audit_events
                     where organization_id = :organization
                       and occurred_at >= :from and occurred_at < :to
                       and (:line is null or business_line = :line)
                       and (:result is null or result = :result)
                    """)
                    .param("organization", organizationId).param("from", from).param("to", to)
                    .param("line", line).param("result", outcome)
                    .query((rs, row) -> new Totals(
                            rs.getLong("event_count"), rs.getLong("session_count"),
                            rs.getLong("failure_count"), nullableInteger(rs, "p95_duration")))
                    .single();

            List<BusinessLineSummary> lines = jdbc.sql("""
                    select business_line, count(*) event_count,
                           count(distinct session_id) filter (where session_id is not null) session_count,
                           count(*) filter (where result = 'FAILURE') failure_count,
                           percentile_cont(0.95) within group (order by duration_ms)
                               filter (where duration_ms is not null) p95_duration
                      from audit_events
                     where organization_id = :organization
                       and occurred_at >= :from and occurred_at < :to
                       and (:line is null or business_line = :line)
                       and (:result is null or result = :result)
                     group by business_line
                     order by event_count desc, business_line
                    """)
                    .param("organization", organizationId).param("from", from).param("to", to)
                    .param("line", line).param("result", outcome)
                    .query((rs, row) -> {
                        long count = rs.getLong("event_count");
                        long failures = rs.getLong("failure_count");
                        return new BusinessLineSummary(
                                rs.getString("business_line"), count, rs.getLong("session_count"),
                                failures, rate(failures, count), nullableInteger(rs, "p95_duration"));
                    }).list();

            List<ErrorSummary> errors = jdbc.sql("""
                    select coalesce(error_code, 'UNCLASSIFIED_FAILURE') error_code,
                           count(*) error_count, max(occurred_at) last_seen
                      from audit_events
                     where organization_id = :organization
                       and occurred_at >= :from and occurred_at < :to
                       and result = 'FAILURE'
                       and (:line is null or business_line = :line)
                     group by coalesce(error_code, 'UNCLASSIFIED_FAILURE')
                     order by error_count desc, error_code
                     limit 10
                    """)
                    .param("organization", organizationId).param("from", from).param("to", to)
                    .param("line", line)
                    .query((rs, row) -> new ErrorSummary(
                            rs.getString("error_code"), rs.getLong("error_count"),
                            instant(rs.getObject("last_seen", OffsetDateTime.class))))
                    .list();

            List<RecentEvent> recent = jdbc.sql("""
                    select audit_id, session_id, event_kind, action, business_line, route,
                           target, occurred_at, duration_ms, result, error_code,
                           metric_name, metric_value
                      from audit_events
                     where organization_id = :organization
                       and occurred_at >= :from and occurred_at < :to
                       and (:line is null or business_line = :line)
                       and (:result is null or result = :result)
                     order by occurred_at desc, audit_id desc
                     limit :limit
                    """)
                    .param("organization", organizationId).param("from", from).param("to", to)
                    .param("line", line).param("result", outcome).param("limit", limit)
                    .query(JdbcUserActivityStore::mapRecent)
                    .list();

            return new ActivitySummary(
                    from, to, totals.eventCount(), totals.sessionCount(), totals.failureCount(),
                    rate(totals.failureCount(), totals.eventCount()), totals.p95DurationMs(),
                    lines, errors, recent, "POSTGRES_APPEND_ONLY", "NOT_RUN");
        });
    }

    private record Totals(long eventCount, long sessionCount, long failureCount, Integer p95DurationMs) {}

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
                rs.getString("audit_id"), rs.getString("session_id"), rs.getString("event_kind"),
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
