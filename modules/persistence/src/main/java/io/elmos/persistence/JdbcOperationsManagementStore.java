package io.elmos.persistence;

import static io.elmos.persistence.SqlTimestamps.offset;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.support.TransactionTemplate;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.temporal.ChronoUnit;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.function.Supplier;

/**
 * Tenant-scoped SLO, alert, incident, remediation and retention workflow store.
 *
 * <p>The automation deliberately stops at a digest-bound, reviewable remediation
 * plan. Source changes, test execution, SCM publication and deployment require
 * their own authorized systems and evidence; they are never simulated here.</p>
 */
@Repository
public class JdbcOperationsManagementStore {
    public static final List<String> BUSINESS_LINES = List.of(
            "PRODUCT_OVERVIEW",
            "SPRING_MODERNIZATION",
            "LANGUAGE_TRANSLATION",
            "PROJECT_SYNTHESIS",
            "REPOSITORY_WORKSPACE",
            "MIGRATION_GOVERNANCE",
            "DATABASE_DATA",
            "CLIENT_MODERNIZATION",
            "CLOUD_INFRASTRUCTURE",
            "SECURITY_COMPLIANCE",
            "DELIVERY_GOVERNANCE",
            "COMMERCIALIZATION",
            "PRICING_USAGE",
            "SKILLS_QUALIFICATION",
            "ENTERPRISE_MODERNIZATION",
            "MAINFRAME_MODERNIZATION",
            "SYSTEM_INTEGRATION",
            "ADMIN_OPERATIONS"
    );

    public record SloPolicy(
            String policyId,
            String businessLine,
            int latencyP95BudgetMs,
            int failureRateBudgetBps,
            int minimumEventCount,
            int evaluationWindowMinutes,
            String ownerActorId,
            String runbookUrl,
            boolean enabled,
            int version
    ) {}

    public record Alert(
            String alertId,
            String businessLine,
            String signal,
            String severity,
            String status,
            BigDecimal observedValue,
            BigDecimal thresholdValue,
            int occurrenceCount,
            String ownerActorId,
            String runbookUrl,
            Instant firstSeenAt,
            Instant lastSeenAt,
            Instant silenceUntil,
            int version
    ) {}

    public record Incident(
            String incidentId,
            String alertId,
            String businessLine,
            String severity,
            String status,
            String summaryCode,
            String ownerActorId,
            Instant openedAt,
            String resolutionCode,
            int version
    ) {}

    public record Remediation(
            String proposalId,
            String incidentId,
            String recipeId,
            String remediationKind,
            String riskLevel,
            String status,
            String titleCode,
            String preconditionDigest,
            String artifactDigest,
            String patchPreview,
            String expectedDiagnosticDelta,
            String requiredTests,
            String rollbackPlan,
            Instant createdAt,
            String decidedBy,
            int version
    ) {}

    public record RetentionRun(
            String retentionRunId,
            String actorId,
            int retentionDays,
            Instant cutoffAt,
            long deletedEventCount,
            String aggregateEvidence,
            Instant occurredAt
    ) {}

    public record PendingNotification(
            String notificationId,
            String alertId,
            String channel,
            String payload,
            int attemptCount
    ) {}

    public record OperationsConsole(
            List<SloPolicy> policies,
            List<Alert> alerts,
            List<Incident> incidents,
            List<Remediation> remediations,
            List<RetentionRun> retentionRuns,
            long pendingNotifications,
            String automationMode,
            String sourceMutationMode,
            String notificationDeliveryEvidence,
            String productionDeploymentEvidence
    ) {}

    public record EvaluationResult(
            int evaluatedPolicies,
            int breachedSignals,
            int openAlerts,
            int openIncidents,
            int proposedRemediations,
            String decision
    ) {}

    public record WorkflowResult(
            String aggregateId,
            String status,
            int version,
            String externalAction
    ) {}

    private record Breach(
            SloPolicy policy,
            String signal,
            BigDecimal observed,
            BigDecimal threshold,
            String severity
    ) {}

    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;
    private final ObjectMapper json;

    public JdbcOperationsManagementStore(
            JdbcClient jdbc,
            TransactionTemplate transactions,
            ObjectMapper json
    ) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
        this.transactions = Objects.requireNonNull(transactions, "transactions");
        this.json = Objects.requireNonNull(json, "json");
    }

    public OperationsConsole console(
            String organizationId,
            String ownerActorId,
            boolean automationEnabled,
            boolean notificationEnabled
    ) {
        return inTenant(organizationId, () -> {
            ensurePolicies(organizationId, ownerActorId);
            return new OperationsConsole(
                    policies(organizationId),
                    jdbc.sql("""
                            select * from operations_alerts
                             where organization_id = :organization
                             order by case status when 'OPEN' then 0 when 'ACKNOWLEDGED' then 1
                                               when 'SILENCED' then 2 else 3 end,
                                      last_seen_at desc
                             limit 100
                            """)
                            .param("organization", organizationId)
                            .query(JdbcOperationsManagementStore::mapAlert).list(),
                    jdbc.sql("""
                            select * from operations_incidents
                             where organization_id = :organization
                             order by case status when 'OPEN' then 0 when 'ACKNOWLEDGED' then 1
                                               when 'MITIGATED' then 2 else 3 end,
                                      opened_at desc
                             limit 100
                            """)
                            .param("organization", organizationId)
                            .query(JdbcOperationsManagementStore::mapIncident).list(),
                    jdbc.sql("""
                            select * from operations_remediation_proposals
                             where organization_id = :organization
                             order by created_at desc
                             limit 100
                            """)
                            .param("organization", organizationId)
                            .query(JdbcOperationsManagementStore::mapRemediation).list(),
                    jdbc.sql("""
                            select * from operations_retention_runs
                             where organization_id = :organization
                             order by occurred_at desc
                             limit 20
                            """)
                            .param("organization", organizationId)
                            .query(JdbcOperationsManagementStore::mapRetention).list(),
                    jdbc.sql("""
                            select count(*) from operations_notification_outbox
                             where organization_id = :organization and status = 'PENDING'
                            """)
                            .param("organization", organizationId).query(Long.class).single(),
                    automationEnabled
                            ? "DETECT_DIAGNOSE_PROPOSE_AUTOMATIC"
                            : "DISABLED_CONFIGURATION_REQUIRED",
                    "APPROVAL_AND_EXTERNAL_SCM_REQUIRED",
                    notificationEnabled
                            ? "WEBHOOK_EXECUTOR_ENABLED_EXTERNAL_DELIVERY_NOT_RUN"
                            : "DISABLED_CONFIGURATION_REQUIRED",
                    "NOT_RUN"
            );
        });
    }

    public EvaluationResult evaluate(
            String organizationId,
            String actorId,
            String requestId,
            Instant now
    ) {
        return inTenant(organizationId, () -> {
            ensurePolicies(organizationId, actorId);
            List<SloPolicy> policies = policies(organizationId);
            int breached = 0;
            int alerts = 0;
            int incidents = 0;
            int proposals = 0;
            for (SloPolicy policy : policies) {
                if (!policy.enabled()) continue;
                Instant from = now.minus(policy.evaluationWindowMinutes(), ChronoUnit.MINUTES);
                SignalWindow window = signalWindow(organizationId, policy.businessLine(), from, now);
                if (window.eventCount() < policy.minimumEventCount()) continue;
                if (window.failureRateBps() > policy.failureRateBudgetBps()) {
                    breached++;
                    WorkflowCounts counts = upsertBreach(
                            organizationId, actorId, requestId, now,
                            new Breach(policy, "FAILURE_RATE_BPS",
                                    BigDecimal.valueOf(window.failureRateBps()),
                                    BigDecimal.valueOf(policy.failureRateBudgetBps()),
                                    severity(window.failureRateBps(), policy.failureRateBudgetBps())));
                    alerts += counts.alerts();
                    incidents += counts.incidents();
                    proposals += counts.proposals();
                }
                if (window.p95DurationMs() != null
                        && window.p95DurationMs() > policy.latencyP95BudgetMs()) {
                    breached++;
                    WorkflowCounts counts = upsertBreach(
                            organizationId, actorId, requestId, now,
                            new Breach(policy, "LATENCY_P95_MS",
                                    BigDecimal.valueOf(window.p95DurationMs()),
                                    BigDecimal.valueOf(policy.latencyP95BudgetMs()),
                                    severity(window.p95DurationMs(), policy.latencyP95BudgetMs())));
                    alerts += counts.alerts();
                    incidents += counts.incidents();
                    proposals += counts.proposals();
                }
            }
            return new EvaluationResult(
                    policies.size(), breached, alerts, incidents, proposals,
                    breached == 0 ? "WITHIN_BUDGET" : "ACTION_REQUIRED");
        });
    }

    public WorkflowResult acknowledgeAlert(
            String organizationId,
            String actorId,
            String requestId,
            String alertId,
            int expectedVersion,
            Instant now
    ) {
        return transition(
                organizationId, actorId, requestId, "ALERT", alertId,
                "operations_alerts", "alert_id", expectedVersion,
                "status = 'ACKNOWLEDGED', acknowledged_at = :now",
                List.of("OPEN", "SILENCED"), "ACKNOWLEDGED", now, "NONE");
    }

    public WorkflowResult assignIncident(
            String organizationId,
            String actorId,
            String requestId,
            String incidentId,
            String ownerActorId,
            int expectedVersion,
            Instant now
    ) {
        requireIdentifier(ownerActorId, "ownerActorId");
        return inTenant(organizationId, () -> {
            CurrentState current = currentState(
                    organizationId, "operations_incidents", "incident_id", incidentId);
            requireVersion(current, expectedVersion);
            if ("RESOLVED".equals(current.status())) {
                throw new IllegalStateException("resolved incidents cannot be reassigned");
            }
            int updated = jdbc.sql("""
                    update operations_incidents
                       set owner_actor_id = :owner, version = version + 1
                     where organization_id = :organization and incident_id = :id
                       and version = :version
                    """)
                    .param("owner", ownerActorId).param("organization", organizationId)
                    .param("id", incidentId).param("version", expectedVersion).update();
            if (updated != 1) throw new IllegalStateException("incident changed concurrently");
            workflowEvent(organizationId, actorId, requestId, "INCIDENT", incidentId,
                    "INCIDENT_ASSIGNED", current.status(), current.status(), now,
                    Map.of("ownerActorId", ownerActorId));
            return new WorkflowResult(incidentId, current.status(), expectedVersion + 1, "NONE");
        });
    }

    public WorkflowResult resolveIncident(
            String organizationId,
            String actorId,
            String requestId,
            String incidentId,
            String resolutionCode,
            int expectedVersion,
            Instant now
    ) {
        requireToken(resolutionCode, "resolutionCode", 96);
        return inTenant(organizationId, () -> {
            CurrentState current = currentState(
                    organizationId, "operations_incidents", "incident_id", incidentId);
            requireVersion(current, expectedVersion);
            if ("RESOLVED".equals(current.status())) {
                throw new IllegalStateException("incident is already resolved");
            }
            int updated = jdbc.sql("""
                    update operations_incidents
                       set status = 'RESOLVED', resolved_at = :now,
                           resolution_code = :resolution, version = version + 1
                     where organization_id = :organization and incident_id = :id
                       and version = :version
                    """)
                    .param("now", offset(now)).param("resolution", resolutionCode)
                    .param("organization", organizationId).param("id", incidentId)
                    .param("version", expectedVersion).update();
            if (updated != 1) throw new IllegalStateException("incident changed concurrently");
            workflowEvent(organizationId, actorId, requestId, "INCIDENT", incidentId,
                    "INCIDENT_RESOLVED", current.status(), "RESOLVED", now,
                    Map.of("resolutionCode", resolutionCode));
            return new WorkflowResult(incidentId, "RESOLVED", expectedVersion + 1, "NONE");
        });
    }

    public WorkflowResult decideRemediation(
            String organizationId,
            String actorId,
            String requestId,
            String proposalId,
            String decision,
            int expectedVersion,
            Instant now
    ) {
        String targetStatus = switch (decision) {
            case "APPROVE" -> "APPROVED";
            case "REJECT" -> "REJECTED";
            default -> throw new IllegalArgumentException("decision must be APPROVE or REJECT");
        };
        return inTenant(organizationId, () -> {
            CurrentState current = currentState(
                    organizationId, "operations_remediation_proposals", "proposal_id", proposalId);
            requireVersion(current, expectedVersion);
            if (!"PROPOSED".equals(current.status())) {
                throw new IllegalStateException("only proposed remediation can be decided");
            }
            int updated = jdbc.sql("""
                    update operations_remediation_proposals
                       set status = :status, decided_at = :now, decided_by = :actor,
                           version = version + 1
                     where organization_id = :organization and proposal_id = :id
                       and version = :version and status = 'PROPOSED'
                    """)
                    .param("status", targetStatus).param("now", offset(now)).param("actor", actorId)
                    .param("organization", organizationId).param("id", proposalId)
                    .param("version", expectedVersion).update();
            if (updated != 1) throw new IllegalStateException("remediation changed concurrently");
            workflowEvent(organizationId, actorId, requestId, "REMEDIATION", proposalId,
                    "REMEDIATION_" + targetStatus, current.status(), targetStatus, now, Map.of());
            return new WorkflowResult(proposalId, targetStatus, expectedVersion + 1, "NONE");
        });
    }

    public WorkflowResult prepareRemediationForScm(
            String organizationId,
            String actorId,
            String requestId,
            String proposalId,
            int expectedVersion,
            Instant now
    ) {
        return inTenant(organizationId, () -> {
            CurrentState current = currentState(
                    organizationId, "operations_remediation_proposals", "proposal_id", proposalId);
            requireVersion(current, expectedVersion);
            if (!"APPROVED".equals(current.status())) {
                throw new IllegalStateException("remediation must be approved before SCM preparation");
            }
            String plan = jdbc.sql("""
                    select patch_preview::text || expected_diagnostic_delta::text
                           || required_tests::text || rollback_plan::text
                      from operations_remediation_proposals
                     where organization_id = :organization and proposal_id = :id
                    """)
                    .param("organization", organizationId).param("id", proposalId)
                    .query(String.class).single();
            String digest = digest(plan);
            int updated = jdbc.sql("""
                    update operations_remediation_proposals
                       set status = 'READY_FOR_SCM', artifact_digest = :digest,
                           version = version + 1
                     where organization_id = :organization and proposal_id = :id
                       and version = :version and status = 'APPROVED'
                    """)
                    .param("digest", digest).param("organization", organizationId)
                    .param("id", proposalId).param("version", expectedVersion).update();
            if (updated != 1) throw new IllegalStateException("remediation changed concurrently");
            workflowEvent(organizationId, actorId, requestId, "REMEDIATION", proposalId,
                    "SCM_PLAN_PREPARED", current.status(), "READY_FOR_SCM", now,
                    Map.of("artifactDigest", digest));
            return new WorkflowResult(
                    proposalId, "READY_FOR_SCM", expectedVersion + 1,
                    "SCM_EXECUTION_NOT_RUN");
        });
    }

    public RetentionRun enforceRetention(
            String organizationId,
            String actorId,
            String requestId,
            int retentionDays,
            Instant now
    ) {
        if (retentionDays < 7 || retentionDays > 365) {
            throw new IllegalArgumentException("retentionDays must be between 7 and 365");
        }
        return inTenant(organizationId, () -> {
            Instant cutoff = now.minus(retentionDays, ChronoUnit.DAYS);
            List<Map<String, Object>> aggregates = jdbc.sql("""
                    select business_line, count(*) event_count,
                           min(occurred_at) first_event_at, max(occurred_at) last_event_at
                      from product_telemetry_events
                     where organization_id = :organization and occurred_at < :cutoff
                     group by business_line order by business_line
                    """)
                    .param("organization", organizationId).param("cutoff", offset(cutoff))
                    .query((rs, row) -> Map.<String, Object>of(
                            "businessLine", rs.getString("business_line"),
                            "eventCount", rs.getLong("event_count"),
                            "firstEventAt", instant(rs.getObject("first_event_at", OffsetDateTime.class)).toString(),
                            "lastEventAt", instant(rs.getObject("last_event_at", OffsetDateTime.class)).toString()
                    )).list();
            int deleted = jdbc.sql("""
                    delete from product_telemetry_events
                     where organization_id = :organization and occurred_at < :cutoff
                    """)
                    .param("organization", organizationId).param("cutoff", offset(cutoff)).update();
            String evidence = toJson(Map.of(
                    "schemaVersion", "1.0.0",
                    "classification", "PSEUDONYMOUS_TECHNICAL",
                    "cutoffAt", cutoff.toString(),
                    "aggregates", aggregates,
                    "auditEventsDeleted", false
            ));
            String runId = UUID.randomUUID().toString();
            jdbc.sql("""
                    insert into operations_retention_runs(
                        retention_run_id, organization_id, actor_id, request_id,
                        retention_days, cutoff_at, deleted_event_count,
                        aggregate_evidence, occurred_at)
                    values (
                        :id, :organization, :actor, :request, :days, :cutoff,
                        :deleted, cast(:evidence as jsonb), :now)
                    """)
                    .param("id", runId).param("organization", organizationId)
                    .param("actor", actorId).param("request", requestId)
                    .param("days", retentionDays).param("cutoff", offset(cutoff))
                    .param("deleted", deleted).param("evidence", evidence).param("now", offset(now))
                    .update();
            workflowEvent(organizationId, actorId, requestId, "RETENTION", runId,
                    "TELEMETRY_RETENTION_ENFORCED", null, "COMPLETED", now,
                    Map.of("deletedEventCount", String.valueOf(deleted), "cutoffAt", cutoff.toString()));
            return new RetentionRun(runId, actorId, retentionDays, cutoff, deleted, evidence, now);
        });
    }

    /**
     * Claims notification rows with a five-minute lease. Expired DELIVERING rows
     * are reclaimable after a worker crash; SKIP LOCKED prevents duplicate
     * claims between healthy replicas.
     */
    public List<PendingNotification> claimPendingNotifications(
            String organizationId,
            Instant now,
            int limit
    ) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("notification claim limit must be between 1 and 100");
        }
        return inTenant(organizationId, () -> {
            List<PendingNotification> claimed = jdbc.sql("""
                    select notification_id, alert_id, channel, payload::text, attempt_count
                      from operations_notification_outbox
                     where organization_id = :organization
                       and (
                           (status = 'PENDING' and available_at <= :now)
                           or (status = 'DELIVERING' and available_at <= :now)
                       )
                     order by available_at, notification_id
                     for update skip locked
                     limit :limit
                    """)
                    .param("organization", organizationId)
                    .param("now", offset(now))
                    .param("limit", limit)
                    .query((rs, row) -> new PendingNotification(
                            rs.getString("notification_id"),
                            rs.getString("alert_id"),
                            rs.getString("channel"),
                            rs.getString("payload"),
                            rs.getInt("attempt_count") + 1))
                    .list();
            for (PendingNotification notification : claimed) {
                jdbc.sql("""
                        update operations_notification_outbox
                           set status = 'DELIVERING',
                               attempt_count = attempt_count + 1,
                               available_at = :leaseUntil,
                               last_error_code = null
                         where organization_id = :organization
                           and notification_id = :id
                        """)
                        .param("leaseUntil", offset(now.plus(5, ChronoUnit.MINUTES)))
                        .param("organization", organizationId)
                        .param("id", notification.notificationId())
                        .update();
            }
            return claimed;
        });
    }

    public void completeNotificationDelivery(
            String organizationId,
            String actorId,
            String requestId,
            PendingNotification notification,
            boolean delivered,
            String errorCode,
            Instant now
    ) {
        requireIdentifier(notification.notificationId(), "notificationId");
        requireIdentifier(actorId, "actorId");
        if (!delivered) requireToken(errorCode, "errorCode", 96);
        inTenant(organizationId, () -> {
            boolean terminal = !delivered && notification.attemptCount() >= 20;
            String status = delivered ? "DELIVERED" : terminal ? "FAILED" : "PENDING";
            long retrySeconds = Math.min(
                    3_600L,
                    15L * (1L << Math.min(notification.attemptCount(), 8)));
            int updated = jdbc.sql("""
                    update operations_notification_outbox
                       set status = :status,
                           delivered_at = case when :delivered then :now else null end,
                           available_at = :availableAt,
                           last_error_code = :error
                     where organization_id = :organization
                       and notification_id = :id
                       and status = 'DELIVERING'
                       and attempt_count = :attempt
                    """)
                    .param("status", status)
                    .param("delivered", delivered)
                    .param("now", offset(now))
                    .param("availableAt", delivered || terminal
                            ? now : now.plusSeconds(retrySeconds))
                    .param("error", delivered ? null : errorCode)
                    .param("organization", organizationId)
                    .param("id", notification.notificationId())
                    .param("attempt", notification.attemptCount())
                    .update();
            if (updated != 1) {
                throw new IllegalStateException("notification delivery lease changed");
            }
            workflowEvent(
                    organizationId, actorId, requestId, "NOTIFICATION",
                    notification.notificationId(),
                    delivered ? "NOTIFICATION_DELIVERED"
                            : terminal ? "NOTIFICATION_FAILED" : "NOTIFICATION_RETRY_SCHEDULED",
                    "DELIVERING", status, now,
                    Map.of(
                            "attemptCount", String.valueOf(notification.attemptCount()),
                            "alertId", notification.alertId(),
                            "errorCode", delivered ? "NONE" : errorCode
                    ));
            return null;
        });
    }

    private record SignalWindow(long eventCount, long failureRateBps, Integer p95DurationMs) {}
    private record WorkflowCounts(int alerts, int incidents, int proposals) {}
    private record CurrentState(String status, int version) {}

    private SignalWindow signalWindow(
            String organizationId,
            String businessLine,
            Instant from,
            Instant to
    ) {
        return jdbc.sql("""
                with activity_events as (
                    select organization_id, business_line, occurred_at, duration_ms, result,
                           event_kind, 'AUDIT' source
                      from audit_events
                    union all
                    select organization_id, business_line, occurred_at, duration_ms, result,
                           event_kind, 'TELEMETRY' source
                      from product_telemetry_events
                )
                select count(*) event_count,
                       round(
                           count(*) filter (where result = 'FAILURE') * 10000.0
                           / greatest(count(*), 1)
                       ) failure_rate_bps,
                       percentile_cont(0.95) within group (order by duration_ms)
                           filter (where duration_ms is not null) p95_duration
                  from activity_events
                 where organization_id = :organization and business_line = :line
                   and occurred_at >= :from and occurred_at < :to
                   and ((source = 'AUDIT' and event_kind = 'SERVER_OPERATION')
                     or (source = 'TELEMETRY' and event_kind = 'API_REQUEST'))
                """)
                .param("organization", organizationId).param("line", businessLine)
                .param("from", offset(from)).param("to", offset(to))
                .query((rs, row) -> new SignalWindow(
                        rs.getLong("event_count"),
                        rs.getLong("failure_rate_bps"),
                        nullableInteger(rs, "p95_duration")))
                .single();
    }

    private WorkflowCounts upsertBreach(
            String organizationId,
            String actorId,
            String requestId,
            Instant now,
            Breach breach
    ) {
        String fingerprint = digest(
                organizationId + "\n" + breach.policy().businessLine() + "\n" + breach.signal());
        String alertId = stableId("alert", fingerprint);
        int insertedAlert = jdbc.sql("""
                insert into operations_alerts(
                    alert_id, organization_id, fingerprint, business_line, signal,
                    severity, status, observed_value, threshold_value, occurrence_count,
                    owner_actor_id, runbook_url, first_seen_at, last_seen_at)
                values (
                    :id, :organization, :fingerprint, :line, :signal, :severity, 'OPEN',
                    :observed, :threshold, 1, :owner, :runbook, :now, :now)
                on conflict (organization_id, fingerprint) do update set
                    severity = excluded.severity,
                    observed_value = excluded.observed_value,
                    threshold_value = excluded.threshold_value,
                    occurrence_count = operations_alerts.occurrence_count + 1,
                    last_seen_at = excluded.last_seen_at,
                    status = case when operations_alerts.status = 'RESOLVED'
                                  then 'OPEN' else operations_alerts.status end,
                    resolved_at = case when operations_alerts.status = 'RESOLVED'
                                       then null else operations_alerts.resolved_at end,
                    version = operations_alerts.version + 1
                """)
                .param("id", alertId).param("organization", organizationId)
                .param("fingerprint", fingerprint).param("line", breach.policy().businessLine())
                .param("signal", breach.signal()).param("severity", breach.severity())
                .param("observed", breach.observed()).param("threshold", breach.threshold())
                .param("owner", breach.policy().ownerActorId())
                .param("runbook", breach.policy().runbookUrl()).param("now", offset(now)).update();

        String incidentId = stableId("incident", alertId);
        int insertedIncident = jdbc.sql("""
                insert into operations_incidents(
                    incident_id, organization_id, alert_id, business_line, severity,
                    status, summary_code, owner_actor_id, opened_at)
                values (
                    :id, :organization, :alert, :line, :severity, 'OPEN',
                    :summary, :owner, :now)
                on conflict (organization_id, alert_id) do nothing
                """)
                .param("id", incidentId).param("organization", organizationId)
                .param("alert", alertId).param("line", breach.policy().businessLine())
                .param("severity", breach.severity())
                .param("summary", breach.signal() + "_BUDGET_BREACH")
                .param("owner", breach.policy().ownerActorId()).param("now", offset(now)).update();

        String kind = "FAILURE_RATE_BPS".equals(breach.signal()) ? "BUG_FIX" : "PERFORMANCE";
        String recipe = "BUG_FIX".equals(kind)
                ? "STABLE_ERROR_DIAGNOSTIC_V1" : "LATENCY_BUDGET_DIAGNOSTIC_V1";
        String proposalId = stableId("remediation", incidentId + "\n" + recipe);
        String precondition = digest(
                breach.policy().businessLine() + "\n" + breach.signal() + "\n"
                        + breach.observed().toPlainString() + "\n" + breach.threshold().toPlainString());
        int insertedProposal = jdbc.sql("""
                insert into operations_remediation_proposals(
                    proposal_id, organization_id, incident_id, recipe_id,
                    remediation_kind, risk_level, status, title_code,
                    precondition_digest, patch_preview, expected_diagnostic_delta,
                    required_tests, rollback_plan, created_at)
                values (
                    :id, :organization, :incident, :recipe, :kind, 'MEDIUM',
                    'PROPOSED', :title, :precondition, cast(:preview as jsonb),
                    cast(:delta as jsonb), cast(:tests as jsonb),
                    cast(:rollback as jsonb), :now)
                on conflict (organization_id, incident_id, recipe_id) do nothing
                """)
                .param("id", proposalId).param("organization", organizationId)
                .param("incident", incidentId).param("recipe", recipe).param("kind", kind)
                .param("title", breach.signal() + "_REMEDIATION")
                .param("precondition", precondition)
                .param("preview", toJson(Map.of(
                        "format", "TYPED_CHANGE_PLAN",
                        "businessLine", breach.policy().businessLine(),
                        "signal", breach.signal(),
                        "sourceMutation", false,
                        "instruction", "INSPECT_OWNER_APPROVED_CODE_AND_CONFIGURATION"
                )))
                .param("delta", toJson(Map.of(
                        "signal", breach.signal(),
                        "before", breach.observed(),
                        "requiredMaximum", breach.threshold()
                )))
                .param("tests", toJson(List.of(
                        "REPRODUCE_DIAGNOSTIC",
                        "TARGETED_REGRESSION",
                        "NEGATIVE_POLICY_TEST",
                        "OWNER_SELECTED_BUILD",
                        "POST_CHANGE_SLO_REPLAY"
                )))
                .param("rollback", toJson(Map.of(
                        "strategy", "REVERT_DIGEST_BOUND_CHANGE",
                        "trigger", "REGRESSION_OR_POLICY_FAILURE",
                        "automaticDeployment", false
                )))
                .param("now", offset(now)).update();

        if (insertedIncident == 1) {
            workflowEvent(organizationId, actorId, requestId, "INCIDENT", incidentId,
                    "INCIDENT_OPENED", null, "OPEN", now, Map.of("alertId", alertId));
        }
        if (insertedProposal == 1) {
            workflowEvent(organizationId, actorId, requestId, "REMEDIATION", proposalId,
                    "REMEDIATION_PROPOSED", null, "PROPOSED", now,
                    Map.of("preconditionDigest", precondition, "sourceMutation", "false"));
        }
        jdbc.sql("""
                insert into operations_notification_outbox(
                    notification_id, organization_id, alert_id, channel,
                    destination_ref, payload, available_at)
                values (
                    :id, :organization, :alert, 'WEBHOOK', 'CONFIGURATION_REQUIRED',
                    cast(:payload as jsonb), :now)
                on conflict (organization_id, alert_id, channel, destination_ref) do nothing
                """)
                .param("id", stableId("notification", alertId))
                .param("organization", organizationId).param("alert", alertId)
                .param("payload", toJson(Map.of(
                        "schemaVersion", "1.0.0",
                        "alertId", alertId,
                        "severity", breach.severity(),
                        "signal", breach.signal(),
                        "businessLine", breach.policy().businessLine()
                )))
                .param("now", offset(now)).update();
        return new WorkflowCounts(insertedAlert, insertedIncident, insertedProposal);
    }

    private WorkflowResult transition(
            String organizationId,
            String actorId,
            String requestId,
            String aggregateType,
            String aggregateId,
            String table,
            String idColumn,
            int expectedVersion,
            String assignment,
            List<String> allowedBefore,
            String after,
            Instant now,
            String externalAction
    ) {
        return inTenant(organizationId, () -> {
            CurrentState current = currentState(organizationId, table, idColumn, aggregateId);
            requireVersion(current, expectedVersion);
            if (!allowedBefore.contains(current.status())) {
                throw new IllegalStateException("workflow transition is not allowed");
            }
            String sql = "update " + table + " set " + assignment
                    + ", version = version + 1 where organization_id = :organization and "
                    + idColumn + " = :id and version = :version";
            int updated = jdbc.sql(sql)
                    .param("now", offset(now)).param("organization", organizationId)
                    .param("id", aggregateId).param("version", expectedVersion).update();
            if (updated != 1) throw new IllegalStateException("workflow changed concurrently");
            workflowEvent(organizationId, actorId, requestId, aggregateType, aggregateId,
                    aggregateType + "_" + after, current.status(), after, now, Map.of());
            return new WorkflowResult(aggregateId, after, expectedVersion + 1, externalAction);
        });
    }

    private CurrentState currentState(
            String organizationId,
            String table,
            String idColumn,
            String id
    ) {
        requireIdentifier(id, "aggregateId");
        return jdbc.sql("select status, version from " + table
                        + " where organization_id = :organization and " + idColumn + " = :id")
                .param("organization", organizationId).param("id", id)
                .query((rs, row) -> new CurrentState(rs.getString("status"), rs.getInt("version")))
                .optional().orElseThrow(() -> new IllegalArgumentException("aggregate was not found"));
    }

    private void ensurePolicies(String organizationId, String ownerActorId) {
        requireIdentifier(ownerActorId, "ownerActorId");
        for (String businessLine : BUSINESS_LINES) {
            jdbc.sql("""
                    insert into operations_slo_policies(
                        policy_id, organization_id, business_line, latency_p95_budget_ms,
                        failure_rate_budget_bps, minimum_event_count,
                        evaluation_window_minutes, owner_actor_id, runbook_url)
                    values (
                        :id, :organization, :line, :latency, :failure, :minimum,
                        15, :owner, :runbook)
                    on conflict (organization_id, business_line) do nothing
                    """)
                    .param("id", stableId("slo", organizationId + "\n" + businessLine))
                    .param("organization", organizationId).param("line", businessLine)
                    .param("latency", defaultLatency(businessLine))
                    .param("failure", defaultFailureRate(businessLine))
                    .param("minimum", 20).param("owner", ownerActorId)
                    .param("runbook", "urn:elmos:runbook:" + businessLine.toLowerCase())
                    .update();
        }
    }

    private List<SloPolicy> policies(String organizationId) {
        return jdbc.sql("""
                select * from operations_slo_policies
                 where organization_id = :organization
                 order by business_line
                """)
                .param("organization", organizationId)
                .query((rs, row) -> new SloPolicy(
                        rs.getString("policy_id"), rs.getString("business_line"),
                        rs.getInt("latency_p95_budget_ms"), rs.getInt("failure_rate_budget_bps"),
                        rs.getInt("minimum_event_count"), rs.getInt("evaluation_window_minutes"),
                        rs.getString("owner_actor_id"), rs.getString("runbook_url"),
                        rs.getBoolean("enabled"), rs.getInt("version")))
                .list();
    }

    private void workflowEvent(
            String organizationId,
            String actorId,
            String requestId,
            String aggregateType,
            String aggregateId,
            String action,
            String before,
            String after,
            Instant now,
            Map<String, String> evidence
    ) {
        jdbc.sql("""
                insert into operations_workflow_events(
                    workflow_event_id, organization_id, aggregate_type, aggregate_id,
                    action, actor_id, request_id, before_status, after_status,
                    occurred_at, evidence)
                values (
                    :id, :organization, :type, :aggregate, :action, :actor,
                    :request, :before, :after, :now, cast(:evidence as jsonb))
                """)
                .param("id", UUID.randomUUID().toString()).param("organization", organizationId)
                .param("type", aggregateType).param("aggregate", aggregateId)
                .param("action", action).param("actor", actorId).param("request", requestId)
                .param("before", before).param("after", after).param("now", offset(now))
                .param("evidence", toJson(evidence)).update();
    }

    private <T> T inTenant(String organizationId, Supplier<T> work) {
        requireIdentifier(organizationId, "organizationId");
        return transactions.execute(status -> {
            jdbc.sql("select set_config('app.organization_id', :organization, true)")
                    .param("organization", organizationId).query(String.class).single();
            return work.get();
        });
    }

    private String toJson(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (JsonProcessingException error) {
            throw new IllegalArgumentException("workflow evidence cannot be serialized", error);
        }
    }

    private static Alert mapAlert(ResultSet rs, int row) throws SQLException {
        return new Alert(
                rs.getString("alert_id"), rs.getString("business_line"), rs.getString("signal"),
                rs.getString("severity"), rs.getString("status"),
                rs.getBigDecimal("observed_value"), rs.getBigDecimal("threshold_value"),
                rs.getInt("occurrence_count"), rs.getString("owner_actor_id"),
                rs.getString("runbook_url"), instant(rs.getObject("first_seen_at", OffsetDateTime.class)),
                instant(rs.getObject("last_seen_at", OffsetDateTime.class)),
                nullableInstant(rs, "silence_until"), rs.getInt("version"));
    }

    private static Incident mapIncident(ResultSet rs, int row) throws SQLException {
        return new Incident(
                rs.getString("incident_id"), rs.getString("alert_id"),
                rs.getString("business_line"), rs.getString("severity"), rs.getString("status"),
                rs.getString("summary_code"), rs.getString("owner_actor_id"),
                instant(rs.getObject("opened_at", OffsetDateTime.class)),
                rs.getString("resolution_code"), rs.getInt("version"));
    }

    private static Remediation mapRemediation(ResultSet rs, int row) throws SQLException {
        return new Remediation(
                rs.getString("proposal_id"), rs.getString("incident_id"),
                rs.getString("recipe_id"), rs.getString("remediation_kind"),
                rs.getString("risk_level"), rs.getString("status"), rs.getString("title_code"),
                rs.getString("precondition_digest"), rs.getString("artifact_digest"),
                rs.getString("patch_preview"), rs.getString("expected_diagnostic_delta"),
                rs.getString("required_tests"), rs.getString("rollback_plan"),
                instant(rs.getObject("created_at", OffsetDateTime.class)),
                rs.getString("decided_by"), rs.getInt("version"));
    }

    private static RetentionRun mapRetention(ResultSet rs, int row) throws SQLException {
        return new RetentionRun(
                rs.getString("retention_run_id"), rs.getString("actor_id"),
                rs.getInt("retention_days"),
                instant(rs.getObject("cutoff_at", OffsetDateTime.class)),
                rs.getLong("deleted_event_count"), rs.getString("aggregate_evidence"),
                instant(rs.getObject("occurred_at", OffsetDateTime.class)));
    }

    private static Instant nullableInstant(ResultSet rs, String column) throws SQLException {
        OffsetDateTime value = rs.getObject(column, OffsetDateTime.class);
        return value == null ? null : value.toInstant();
    }

    private static Instant instant(OffsetDateTime value) {
        return value.toInstant();
    }

    private static Integer nullableInteger(ResultSet rs, String column) throws SQLException {
        Number value = (Number) rs.getObject(column);
        return value == null ? null : (int) Math.round(value.doubleValue());
    }

    private static String severity(long observed, long threshold) {
        if (threshold == 0) return observed > 0 ? "P0" : "P2";
        double ratio = observed / (double) threshold;
        return ratio >= 3.0 ? "P0" : ratio >= 1.5 ? "P1" : "P2";
    }

    private static int defaultLatency(String businessLine) {
        return switch (businessLine) {
            case "PROJECT_SYNTHESIS", "LANGUAGE_TRANSLATION", "SPRING_MODERNIZATION" -> 2_000;
            case "REPOSITORY_WORKSPACE" -> 1_500;
            default -> 750;
        };
    }

    private static int defaultFailureRate(String businessLine) {
        return switch (businessLine) {
            case "ADMIN_OPERATIONS", "SECURITY_COMPLIANCE", "PRICING_USAGE" -> 100;
            default -> 500;
        };
    }

    private static void requireVersion(CurrentState current, int expectedVersion) {
        if (expectedVersion < 1 || current.version() != expectedVersion) {
            throw new IllegalStateException("workflow version is stale");
        }
    }

    private static void requireIdentifier(String value, String field) {
        if (value == null || !value.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
            throw new IllegalArgumentException(field + " is invalid");
        }
    }

    private static void requireToken(String value, String field, int maximum) {
        if (value == null || value.length() > maximum
                || !value.matches("[A-Z0-9][A-Z0-9._:-]*")) {
            throw new IllegalArgumentException(field + " is invalid");
        }
    }

    private static String stableId(String prefix, String value) {
        return prefix + "-" + digest(value).substring("sha256:".length(), "sha256:".length() + 32);
    }

    private static String digest(String value) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return "sha256:" + HexFormat.of().formatHex(bytes);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 is unavailable", error);
        }
    }
}
