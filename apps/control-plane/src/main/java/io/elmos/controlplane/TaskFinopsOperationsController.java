package io.elmos.controlplane;

import io.elmos.workflow.TaskFinopsAnalytics;
import io.elmos.workflow.TaskFinopsAnalyticsService;
import io.elmos.workflow.TaskFinopsFeatureRollout;
import io.elmos.workflow.TaskFinopsOperationsPort;
import io.elmos.workflow.TaskFinopsPort;
import io.elmos.workflow.TenantLifecyclePolicy;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;

/** Account-bound recovery, lifecycle, rollout and analytics control surface. */
@RestController
@RequestMapping("/api/v1/task-finops")
public class TaskFinopsOperationsController {
    private final TaskFinopsOperationsPort operations;
    private final TaskFinopsAnalyticsService analytics;
    private final Clock clock;

    public TaskFinopsOperationsController(
            TaskFinopsOperationsPort operations,
            TaskFinopsAnalyticsService analytics,
            Clock clock
    ) {
        this.operations = operations;
        this.analytics = analytics;
        this.clock = clock;
    }

    public record RolloutRequest(String stage, int exposurePercent, long expectedVersion) {}

    public record ForkRequest(
            String recoveryForkId,
            String checkpointId,
            String compatibilityDecisionId,
            String childTaskId
    ) {}

    public record LifecycleRequest(
            String lifecycleJobId,
            String exportFormat,
            Instant retentionCutoff
    ) {}

    public record AnalyticsRebuildRequest(
            String rebuildId,
            Instant windowStart,
            Instant windowEnd,
            long expectedGeneration
    ) {}

    @PostMapping("/rollouts/{environment}/{feature}")
    public ResponseEntity<?> rollout(
            @PathVariable String environment,
            @PathVariable String feature,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestBody RolloutRequest request
    ) {
        TaskFinopsPort.AuthenticatedContext context = context("admin:operate");
        TaskFinopsFeatureRollout.Environment environmentValue = enumValue(
                TaskFinopsFeatureRollout.Environment.class, environment,
                "ELMOS_MTF_FEATURE_ENVIRONMENT_INVALID");
        TaskFinopsFeatureRollout.Feature featureValue = enumValue(
                TaskFinopsFeatureRollout.Feature.class, feature,
                "ELMOS_MTF_FEATURE_INVALID");
        TaskFinopsFeatureRollout.Stage stageValue = enumValue(
                TaskFinopsFeatureRollout.Stage.class,
                request == null ? null : request.stage(),
                "ELMOS_MTF_FEATURE_STAGE_INVALID");
        String idempotency = require(
                idempotencyKey, 160, "ELMOS_MTF_IDEMPOTENCY_INVALID");
        String requestDigest = digest(context, "FEATURE_ROLLOUT",
                environmentValue.name(), featureValue.name(), stageValue.name(),
                Integer.toString(request.exposurePercent()),
                Long.toString(request.expectedVersion()), idempotency);
        long version = operations.setFeatureRollout(
                new TaskFinopsOperationsPort.FeatureRolloutCommand(
                        context, environmentValue, featureValue.name(), stageValue,
                        request.exposurePercent(), request.expectedVersion(),
                        idempotency, requestDigest));
        return ResponseEntity.accepted().body(Map.of(
                "environment", environmentValue,
                "feature", featureValue,
                "stage", stageValue,
                "exposurePercent", request.exposurePercent(),
                "stateVersion", version,
                "productionCertification", "NOT_CERTIFIED"));
    }

    @PostMapping("/tasks/{taskId}/recoveries/fork")
    public ResponseEntity<?> forkRecovery(
            @PathVariable String taskId,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestBody ForkRequest request
    ) {
        TaskFinopsPort.AuthenticatedContext context = context("modernization:execute");
        if (request == null) {
            throw state("ELMOS_MTF_RECOVERY_FORK_INVALID");
        }
        String parent = require(taskId, 96, "ELMOS_MTF_TASK_INVALID");
        String idempotency = require(
                idempotencyKey, 140, "ELMOS_MTF_IDEMPOTENCY_INVALID");
        String requestDigest = digest(context, "FORK_RECOVERY", parent,
                request.recoveryForkId(), request.checkpointId(),
                request.compatibilityDecisionId(), request.childTaskId(), idempotency);
        var result = operations.forkRecovery(
                new TaskFinopsOperationsPort.ForkRecoveryCommand(
                        context, request.recoveryForkId(), parent,
                        request.checkpointId(), request.compatibilityDecisionId(),
                        request.childTaskId(), idempotency, requestDigest));
        return ResponseEntity.accepted().body(result);
    }

    @PostMapping("/tenant-lifecycle/{operation}")
    public ResponseEntity<?> requestLifecycle(
            @PathVariable String operation,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestBody LifecycleRequest request
    ) {
        TaskFinopsPort.AuthenticatedContext context = context("admin:operate");
        if (request == null || request.retentionCutoff() == null
                || request.retentionCutoff().isAfter(clock.instant())) {
            throw state("ELMOS_MTF_LIFECYCLE_REQUEST_INVALID");
        }
        TenantLifecyclePolicy.Operation operationValue = enumValue(
                TenantLifecyclePolicy.Operation.class, operation,
                "ELMOS_MTF_LIFECYCLE_OPERATION_INVALID");
        TenantLifecyclePolicy.ExportFormat format = enumValue(
                TenantLifecyclePolicy.ExportFormat.class, request.exportFormat(),
                "ELMOS_MTF_EXPORT_FORMAT_INVALID");
        String idempotency = require(
                idempotencyKey, 160, "ELMOS_MTF_IDEMPOTENCY_INVALID");
        String requestDigest = digest(context, "TENANT_LIFECYCLE",
                operationValue.name(), request.lifecycleJobId(), format.name(),
                request.retentionCutoff().toString(), idempotency);
        String jobId = operations.requestLifecycle(
                new TaskFinopsOperationsPort.LifecycleRequestCommand(
                        context, request.lifecycleJobId(), operationValue, format,
                        request.retentionCutoff(), idempotency, requestDigest));
        return operations.lifecycleStatus(context, jobId)
                .<ResponseEntity<?>>map(status -> ResponseEntity.accepted().body(status))
                .orElseThrow(() -> state("ELMOS_MTF_LIFECYCLE_JOB_UNKNOWN"));
    }

    @GetMapping("/tenant-lifecycle/jobs/{lifecycleJobId}")
    public ResponseEntity<?> lifecycleStatus(@PathVariable String lifecycleJobId) {
        TaskFinopsPort.AuthenticatedContext context = context("admin:read");
        return operations.lifecycleStatus(context, lifecycleJobId)
                .<ResponseEntity<?>>map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of(
                        "status", "ERROR",
                        "code", "ELMOS_MTF_LIFECYCLE_JOB_UNKNOWN")));
    }

    @PostMapping("/analytics/rebuilds")
    public ResponseEntity<?> rebuildAnalytics(
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestBody AnalyticsRebuildRequest request
    ) {
        TaskFinopsPort.AuthenticatedContext context = context("admin:operate");
        if (request == null || request.windowStart() == null || request.windowEnd() == null
                || request.windowEnd().isAfter(clock.instant().plusSeconds(60))) {
            throw state("ELMOS_MTF_ANALYTICS_WINDOW_INVALID");
        }
        String idempotency = require(
                idempotencyKey, 160, "ELMOS_MTF_IDEMPOTENCY_INVALID");
        String requestDigest = digest(context, "ANALYTICS_REBUILD",
                request.rebuildId(), request.windowStart().toString(),
                request.windowEnd().toString(),
                Long.toString(request.expectedGeneration()), idempotency);
        var receipt = analytics.rebuild(new TaskFinopsAnalyticsService.RebuildCommand(
                context, request.rebuildId(), request.windowStart(), request.windowEnd(),
                request.expectedGeneration(), idempotency, requestDigest));
        return ResponseEntity.accepted().body(receipt);
    }

    @GetMapping("/analytics/exports")
    public ResponseEntity<String> exportAnalytics(
            @RequestParam String grain,
            @RequestParam String format,
            @RequestParam Instant from,
            @RequestParam Instant to,
            @RequestParam(defaultValue = "5000") int limit
    ) {
        TaskFinopsPort.AuthenticatedContext context = context("usage:read");
        TaskFinopsAnalytics.ExportArtifact artifact = analytics.export(
                context,
                enumValue(TaskFinopsAnalytics.Grain.class, grain,
                        "ELMOS_MTF_ANALYTICS_GRAIN_INVALID"),
                enumValue(TaskFinopsAnalytics.ExportFormat.class, format,
                        "ELMOS_MTF_EXPORT_FORMAT_INVALID"),
                from, to, limit);
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(artifact.mediaType()))
                .header("X-ELMOS-Content-SHA256", artifact.digest())
                .header("X-ELMOS-Row-Count", Long.toString(artifact.rowCount()))
                .header("X-ELMOS-External-Evidence", artifact.externalEvidence().name())
                .header("X-ELMOS-Provider-Outcome", artifact.providerOutcome().name())
                .header("X-ELMOS-Production-Certification",
                        artifact.productionCertification().name())
                .body(artifact.body());
    }

    private TaskFinopsPort.AuthenticatedContext context(String permission) {
        ControlPlanePrincipal principal = ControlPlanePrincipal.current()
                .orElseThrow(() -> new AccessDeniedException("CONTROL_PLANE_AUTH_REQUIRED"));
        principal.require(principal.organizationId(), principal.actorId(), permission);
        return new TaskFinopsPort.AuthenticatedContext(
                principal.organizationId(), principal.accountId(), principal.actorId(),
                "mtf-ops-" + UUID.randomUUID());
    }

    private static String digest(
            TaskFinopsPort.AuthenticatedContext context,
            String... values
    ) {
        StringBuilder canonical = new StringBuilder()
                .append(context.organizationId()).append('\n')
                .append(context.accountId()).append('\n')
                .append(context.actorId()).append('\n');
        for (String value : values) {
            canonical.append(require(value, 1024, "ELMOS_MTF_REQUEST_FIELD_INVALID"))
                    .append('\n');
        }
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(canonical.toString().getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw new IllegalStateException("SHA-256 unavailable", exception);
        }
    }

    private static <T extends Enum<T>> T enumValue(
            Class<T> type,
            String value,
            String code
    ) {
        try {
            return Enum.valueOf(type,
                    value == null ? "" : value.trim().toUpperCase(java.util.Locale.ROOT));
        } catch (IllegalArgumentException exception) {
            throw state(code);
        }
    }

    private static String require(String value, int max, String code) {
        String candidate = value == null ? "" : value.trim();
        if (candidate.isEmpty() || candidate.length() > max
                || candidate.indexOf('\0') >= 0) {
            throw state(code);
        }
        return candidate;
    }

    private static TaskFinopsPort.TaskFinopsStateException state(String code) {
        return new TaskFinopsPort.TaskFinopsStateException(code);
    }

    @ExceptionHandler(TaskFinopsPort.TaskFinopsStateException.class)
    ResponseEntity<?> taskFinopsError(TaskFinopsPort.TaskFinopsStateException exception) {
        HttpStatus status = switch (exception.code()) {
            case "ELMOS_MTF_LIFECYCLE_JOB_UNKNOWN",
                 "ELMOS_MTF_TASK_UNKNOWN" -> HttpStatus.NOT_FOUND;
            case "ELMOS_MTF_ACCOUNT_CONTEXT_UNKNOWN",
                 "ELMOS_MTF_AUTHORITY_REQUIRED" -> HttpStatus.FORBIDDEN;
            case "ELMOS_MTF_IDEMPOTENCY_CONFLICT",
                 "ELMOS_MTF_ANALYTICS_GENERATION_CONFLICT",
                 "ELMOS_MTF_FEATURE_ROLLOUT_VERSION_CONFLICT",
                 "ELMOS_MTF_LIFECYCLE_VERSION_CONFLICT",
                 "ELMOS_MTF_ILLEGAL_TRANSITION",
                 "ELMOS_MTF_RECONCILIATION_REQUIRED" -> HttpStatus.CONFLICT;
            default -> HttpStatus.BAD_REQUEST;
        };
        return ResponseEntity.status(status).body(Map.of(
                "status", "ERROR", "code", exception.code()));
    }

    @ExceptionHandler(TaskFinopsAnalytics.AnalyticsException.class)
    ResponseEntity<?> analyticsError(TaskFinopsAnalytics.AnalyticsException exception) {
        HttpStatus status = switch (exception.code()) {
            case "ELMOS_MTF_ANALYTICS_PROJECTION_UNKNOWN" -> HttpStatus.NOT_FOUND;
            case "ELMOS_MTF_ANALYTICS_SEQUENCE_GAP",
                 "ELMOS_MTF_ANALYTICS_DUPLICATE_SEQUENCE",
                 "ELMOS_MTF_ANALYTICS_OUT_OF_ORDER_SEQUENCE",
                 "ELMOS_MTF_ANALYTICS_DUPLICATE_EVENT_ID",
                 "ELMOS_MTF_ANALYTICS_DUPLICATE_FINANCIAL_FACT",
                 "ELMOS_MTF_ANALYTICS_ILLEGAL_TRANSITION" -> HttpStatus.CONFLICT;
            default -> HttpStatus.BAD_REQUEST;
        };
        return ResponseEntity.status(status).body(Map.of(
                "status", "ERROR", "code", exception.code()));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<?> invalidRequest(IllegalArgumentException exception) {
        String message = exception.getMessage();
        String code = message != null && message.matches("ELMOS_MTF_[A-Z0-9_]+")
                ? message : "ELMOS_MTF_REQUEST_INVALID";
        return ResponseEntity.badRequest().body(Map.of(
                "status", "ERROR", "code", code));
    }
}
