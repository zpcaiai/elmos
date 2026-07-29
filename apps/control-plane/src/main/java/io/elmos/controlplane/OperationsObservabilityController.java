package io.elmos.controlplane;

import io.elmos.persistence.JdbcUserActivityStore;
import io.elmos.persistence.JdbcUserActivityStore.ActivityEvent;
import io.elmos.persistence.JdbcUserActivityStore.ActivitySummary;
import io.elmos.persistence.JdbcOperationsManagementStore;
import io.elmos.persistence.JdbcRunHistoryStore;
import io.elmos.persistence.JdbcOperationsManagementStore.EvaluationResult;
import io.elmos.persistence.JdbcOperationsManagementStore.OperationsConsole;
import io.elmos.persistence.JdbcOperationsManagementStore.RetentionRun;
import io.elmos.persistence.JdbcOperationsManagementStore.WorkflowResult;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.PathVariable;

import java.time.Clock;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/operations-observability")
public final class OperationsObservabilityController {
    private final JdbcUserActivityStore store;
    private final JdbcOperationsManagementStore management;
    private final JdbcRunHistoryStore runHistory;
    private final Clock clock;
    private final OperationsAuthorization authorization;
    private final boolean automationEnabled;
    private final boolean notificationEnabled;

    public OperationsObservabilityController(
            JdbcUserActivityStore store,
            JdbcOperationsManagementStore management,
            JdbcRunHistoryStore runHistory,
            Clock clock,
            OperationsAuthorization authorization,
            @Value("${elmos.operations.automation-enabled:false}") boolean automationEnabled,
            @Value("${elmos.operations.notification-enabled:false}") boolean notificationEnabled
    ) {
        this.store = Objects.requireNonNull(store, "store");
        this.management = Objects.requireNonNull(management, "management");
        this.runHistory = Objects.requireNonNull(runHistory, "runHistory");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.authorization = Objects.requireNonNull(authorization, "authorization");
        this.automationEnabled = automationEnabled;
        this.notificationEnabled = notificationEnabled;
    }

    public record EventBatch(List<ActivityEvent> events) {}
    public record AppendResult(int accepted, String persistence, String requestId) {}
    public record ConsoleView(
            ActivitySummary activity,
            OperationsConsole control,
            String role,
            String actorId
    ) {}
    public record VersionBody(int expectedVersion) {}
    public record AssignmentBody(String ownerActorId, int expectedVersion) {}
    public record ResolutionBody(String resolutionCode, int expectedVersion) {}
    public record DecisionBody(String decision, int expectedVersion) {}
    public record RetentionBody(int retentionDays) {}

    @PostMapping("/events")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public AppendResult append(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @RequestBody EventBatch batch
    ) {
        authorize(presentedKey, organizationId, actorId);
        String resolvedRequestId = requestId == null || requestId.isBlank()
                ? UUID.randomUUID().toString() : requestId;
        int accepted = store.appendTelemetry(
                organizationId, actorId, resolvedRequestId, batch.events());
        return new AppendResult(accepted, "POSTGRES_RETENTION_MANAGED", resolvedRequestId);
    }

    @PostMapping("/audit-events")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public AppendResult appendAudit(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @RequestBody EventBatch batch
    ) {
        authorize(presentedKey, organizationId, actorId);
        String resolvedRequestId = requestId(requestId);
        int accepted = store.append(
                organizationId, actorId, resolvedRequestId, batch.events());
        return new AppendResult(accepted, "POSTGRES_APPEND_ONLY", resolvedRequestId);
    }

    @GetMapping("/summary")
    public ActivitySummary summary(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader("X-ELMOS-Admin-Role") String role,
            @RequestParam(defaultValue = "24") int hours,
            @RequestParam(defaultValue = "ALL") String businessLine,
            @RequestParam(defaultValue = "ALL") String result,
            @RequestParam(defaultValue = "50") int limit
    ) {
        authorizeManagement(presentedKey, organizationId, actorId, role, "VIEWER");
        if (hours < 1 || hours > 24 * 31) {
            throw new IllegalArgumentException("hours must be between 1 and 744");
        }
        Instant to = clock.instant();
        return store.summary(
                organizationId, to.minus(hours, ChronoUnit.HOURS), to,
                businessLine, result, limit);
    }

    /**
     * One keyset page of the raw audit trail.
     *
     * <p>Unlike {@code /summary}, which aggregates, this returns the rows an
     * auditor has to be able to read and re-read. It is therefore paged rather
     * than windowed by a row cap: a cap would silently truncate the artifact,
     * and a truncated audit export is worse than a refused one.
     *
     * <p>{@code days} rather than {@code hours} because audit windows are
     * asked for in months; the store enforces the 366-day ceiling.
     */
    @GetMapping("/audit-export")
    public JdbcUserActivityStore.ExportPage auditExport(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader("X-ELMOS-Admin-Role") String role,
            @RequestParam(defaultValue = "7") int days,
            @RequestParam(defaultValue = "ALL") String businessLine,
            @RequestParam(defaultValue = "ALL") String result,
            @RequestParam(required = false) String afterOccurredAt,
            @RequestParam(required = false) String afterEventId,
            @RequestParam(defaultValue = "200") int limit
    ) {
        authorizeManagement(presentedKey, organizationId, actorId, role, "VIEWER");
        if (days < 1 || days > 366) {
            throw new IllegalArgumentException("days must be between 1 and 366");
        }
        Instant to = clock.instant();
        return store.export(
                organizationId,
                to.minus(days, ChronoUnit.DAYS),
                to,
                businessLine,
                result,
                parseCursorInstant(afterOccurredAt),
                blankToNull(afterEventId),
                limit);
    }

    /**
     * The full history of one migration run, reconstructed.
     *
     * <p>The other half of the audit loop. {@code /audit-export} answers what
     * happened across the tenant; this answers what happened to one run, with
     * its attempts, its evidence and the audit rows that name it.
     *
     * <p>GET, and backed by a store that runs in a read-only transaction: an
     * endpoint that reconstructs a past decision must not be able to alter the
     * record it is reconstructing. Same reason {@code /audit-export} is GET.
     *
     * <p>VIEWER, matching the export. A replay reveals nothing the export does
     * not already reveal to the same reader; requiring more here would only
     * push auditors toward the coarser tool.
     *
     * <p>A run that does not exist and a run belonging to another tenant are
     * both 404. The store returns empty for both so this layer cannot tell them
     * apart even if it wanted to -- which is the point, since a 403 here would
     * confirm that the id exists somewhere.
     */
    @GetMapping("/runs/{migrationRunId}/replay")
    public JdbcRunHistoryStore.RunTimeline replay(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader("X-ELMOS-Admin-Role") String role,
            @PathVariable String migrationRunId
    ) {
        authorizeManagement(presentedKey, organizationId, actorId, role, "VIEWER");
        return runHistory.replay(organizationId, migrationRunId)
                .orElseThrow(RunHistoryNotFoundException::new);
    }

    private static Instant parseCursorInstant(String value) {
        if (value == null || value.isBlank()) return null;
        try {
            return Instant.parse(value);
        } catch (DateTimeParseException error) {
            throw new IllegalArgumentException("afterOccurredAt must be an ISO-8601 instant");
        }
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }

    @GetMapping("/console")
    public ConsoleView console(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader("X-ELMOS-Admin-Role") String role,
            @RequestParam(defaultValue = "24") int hours,
            @RequestParam(defaultValue = "ALL") String businessLine,
            @RequestParam(defaultValue = "ALL") String result,
            @RequestParam(defaultValue = "50") int limit
    ) {
        authorizeManagement(presentedKey, organizationId, actorId, role, "VIEWER");
        if (hours < 1 || hours > 24 * 31) {
            throw new IllegalArgumentException("hours must be between 1 and 744");
        }
        Instant to = clock.instant();
        return new ConsoleView(
                store.summary(
                        organizationId, to.minus(hours, ChronoUnit.HOURS), to,
                        businessLine, result, limit),
                management.console(
                        organizationId,
                        actorId,
                        automationEnabled,
                        notificationEnabled),
                resolvedRole(role, organizationId),
                actorId);
    }

    @PostMapping("/evaluate")
    public EvaluationResult evaluate(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader("X-ELMOS-Admin-Role") String role,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId
    ) {
        authorizeManagement(presentedKey, organizationId, actorId, role, "OPERATOR");
        return management.evaluate(
                organizationId, actorId, requestId(requestId), clock.instant());
    }

    @PostMapping("/alerts/{alertId}/acknowledge")
    public WorkflowResult acknowledgeAlert(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader("X-ELMOS-Admin-Role") String role,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @PathVariable String alertId,
            @RequestBody VersionBody body
    ) {
        authorizeManagement(presentedKey, organizationId, actorId, role, "OPERATOR");
        return management.acknowledgeAlert(
                organizationId, actorId, requestId(requestId), alertId,
                body.expectedVersion(), clock.instant());
    }

    @PostMapping("/incidents/{incidentId}/assign")
    public WorkflowResult assignIncident(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader("X-ELMOS-Admin-Role") String role,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @PathVariable String incidentId,
            @RequestBody AssignmentBody body
    ) {
        authorizeManagement(presentedKey, organizationId, actorId, role, "OPERATOR");
        return management.assignIncident(
                organizationId, actorId, requestId(requestId), incidentId,
                body.ownerActorId(), body.expectedVersion(), clock.instant());
    }

    @PostMapping("/incidents/{incidentId}/resolve")
    public WorkflowResult resolveIncident(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader("X-ELMOS-Admin-Role") String role,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @PathVariable String incidentId,
            @RequestBody ResolutionBody body
    ) {
        authorizeManagement(presentedKey, organizationId, actorId, role, "OPERATOR");
        return management.resolveIncident(
                organizationId, actorId, requestId(requestId), incidentId,
                body.resolutionCode(), body.expectedVersion(), clock.instant());
    }

    @PostMapping("/remediations/{proposalId}/decision")
    public WorkflowResult decideRemediation(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader("X-ELMOS-Admin-Role") String role,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @PathVariable String proposalId,
            @RequestBody DecisionBody body
    ) {
        authorizeManagement(presentedKey, organizationId, actorId, role, "APPROVER");
        return management.decideRemediation(
                organizationId, actorId, requestId(requestId), proposalId,
                body.decision(), body.expectedVersion(), clock.instant());
    }

    @PostMapping("/remediations/{proposalId}/prepare-scm")
    public WorkflowResult prepareRemediationForScm(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader("X-ELMOS-Admin-Role") String role,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @PathVariable String proposalId,
            @RequestBody VersionBody body
    ) {
        authorizeManagement(presentedKey, organizationId, actorId, role, "APPROVER");
        return management.prepareRemediationForScm(
                organizationId, actorId, requestId(requestId), proposalId,
                body.expectedVersion(), clock.instant());
    }

    @PostMapping("/retention/enforce")
    public RetentionRun enforceRetention(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader("X-ELMOS-Admin-Role") String role,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @RequestBody RetentionBody body
    ) {
        authorizeManagement(presentedKey, organizationId, actorId, role, "APPROVER");
        return management.enforceRetention(
                organizationId, actorId, requestId(requestId),
                body.retentionDays(), clock.instant());
    }

    private void authorize(String presentedKey, String organizationId, String actorId) {
        authorization.requireView(presentedKey, organizationId, actorId);
    }

    private void authorizeManagement(
            String presentedKey,
            String organizationId,
            String actorId,
            String role,
            String requiredRole
    ) {
        authorization.requireManagement(presentedKey, organizationId, actorId, role, requiredRole);
    }

    private static String normalizeRole(String role) {
        return role == null ? "" : role.trim().toUpperCase(java.util.Locale.ROOT);
    }

    private static String resolvedRole(String legacyRole, String organizationId) {
        return ControlPlanePrincipal.current()
                .map(principal -> principal.adminRole(organizationId))
                .orElseGet(() -> normalizeRole(legacyRole));
    }

    private static String requestId(String value) {
        if (value != null && value.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
            return value;
        }
        return UUID.randomUUID().toString();
    }

    @ExceptionHandler(SecurityException.class)
    @ResponseStatus(HttpStatus.FORBIDDEN)
    Map<String, Object> forbidden() {
        return Map.of("errorCode", "OPERATIONS_OBSERVABILITY_FORBIDDEN",
                "message", "Operations observability authorization failed.", "retryable", false);
    }

    @ExceptionHandler(ObservabilityUnavailableException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    Map<String, Object> unavailable() {
        return Map.of("errorCode", "OPERATIONS_OBSERVABILITY_NOT_CONFIGURED",
                "message", "Operations observability is not configured.", "retryable", false);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> invalid() {
        return Map.of("errorCode", "OPERATIONS_OBSERVABILITY_REQUEST_INVALID",
                "message", "The observability request was rejected by its contract.", "retryable", false);
    }

    @ExceptionHandler(RunHistoryNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    Map<String, Object> runNotFound() {
        return Map.of("errorCode", "OPERATIONS_RUN_NOT_FOUND",
                "message", "No such run for this tenant.", "retryable", false);
    }

    /** Deliberately carries no detail: the absence of a run and the absence of permission to see it must look identical. */
    static final class RunHistoryNotFoundException extends RuntimeException {}

    @ExceptionHandler(IllegalStateException.class)
    @ResponseStatus(HttpStatus.CONFLICT)
    Map<String, Object> conflict() {
        return Map.of("errorCode", "OPERATIONS_WORKFLOW_CONFLICT",
                "message", "The operations workflow changed or rejected this transition.",
                "retryable", false);
    }

}
