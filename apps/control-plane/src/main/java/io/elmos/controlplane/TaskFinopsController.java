package io.elmos.controlplane;

import io.elmos.workflow.TaskFinopsPolicy;
import io.elmos.workflow.TaskFinopsPort;
import org.springframework.http.HttpStatus;
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
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Tenant-safe task status and control API.
 *
 * <p>Organization, account, and actor are taken exclusively from the database-
 * bound {@link ControlPlanePrincipal}; none is accepted as a path, query, header,
 * or request-body value.  The API intentionally has no usage, revenue,
 * allocation, correction, or manual-reconciliation mutation endpoint.</p>
 */
@RestController
@RequestMapping("/api/v1/task-finops")
public class TaskFinopsController {
    private final TaskFinopsPort taskFinops;
    private final Clock clock;

    public TaskFinopsController(TaskFinopsPort taskFinops, Clock clock) {
        this.taskFinops = taskFinops;
        this.clock = clock;
    }

    public record ControlRequest(String reasonCode) {}

    @GetMapping("/concurrency")
    public TaskFinopsPort.ConcurrencyStatus concurrency() {
        return taskFinops.concurrencyStatus(context("workspace:view"));
    }

    @GetMapping("/tasks/{taskId}/events")
    public List<TaskFinopsPort.TaskEvent> events(
            @PathVariable String taskId,
            @RequestParam(defaultValue = "0") long afterSequence,
            @RequestParam(defaultValue = "100") int limit
    ) {
        return taskFinops.events(
                context("workspace:view"), taskId, afterSequence, limit);
    }

    @GetMapping("/tasks/{taskId}/progress")
    public ResponseEntity<?> progress(@PathVariable String taskId) {
        return taskFinops.progress(context("workspace:view"), taskId)
                .<ResponseEntity<?>>map(ResponseEntity::ok)
                .orElseGet(() -> notFound(taskId));
    }

    @GetMapping("/tasks/{taskId}/financial-summary")
    public ResponseEntity<?> financialSummary(
            @PathVariable String taskId,
            @RequestParam(required = false) Instant asOf
    ) {
        Instant requestedAsOf = asOf == null ? clock.instant() : asOf;
        if (requestedAsOf.isAfter(clock.instant().plusSeconds(60))) {
            throw new TaskFinopsPort.TaskFinopsStateException(
                    "ELMOS_MTF_FINANCIAL_AS_OF_INVALID");
        }
        return taskFinops.financialSummary(
                        context("usage:read"), taskId, requestedAsOf)
                .<ResponseEntity<?>>map(ResponseEntity::ok)
                .orElseGet(() -> notFound(taskId));
    }

    @PostMapping("/tasks/{taskId}/pause")
    public ResponseEntity<?> pause(
            @PathVariable String taskId,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestBody ControlRequest request
    ) {
        return control("PAUSE", taskId, idempotencyKey, request, true);
    }

    @PostMapping("/tasks/{taskId}/resume")
    public ResponseEntity<?> resume(
            @PathVariable String taskId,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestBody ControlRequest request
    ) {
        return control("RESUME", taskId, idempotencyKey, request, false);
    }

    private ResponseEntity<?> control(
            String action,
            String taskId,
            String idempotencyKey,
            ControlRequest request,
            boolean pause
    ) {
        TaskFinopsPort.AuthenticatedContext context = context("modernization:execute");
        String task = require(taskId, TaskFinopsPort.DATABASE_ID_MAX_LENGTH,
                "ELMOS_MTF_TASK_INVALID");
        String reasonCode = require(request == null ? null : request.reasonCode(),
                96, "ELMOS_MTF_REASON_INVALID");
        String idempotency = require(
                idempotencyKey, 160, "ELMOS_MTF_IDEMPOTENCY_INVALID");
        String requestDigest = sha256(String.join("\n",
                context.organizationId(), context.accountId(), context.actorId(),
                action, task, reasonCode, idempotency));
        TaskFinopsPort.ControlCommand command = new TaskFinopsPort.ControlCommand(
                context, task, reasonCode, idempotency, requestDigest);
        TaskFinopsPolicy.TaskState state = pause
                ? taskFinops.pause(command)
                : taskFinops.resume(command);
        return ResponseEntity.accepted().body(Map.of(
                "taskId", task,
                "state", state,
                "requestId", context.requestId()));
    }

    private TaskFinopsPort.AuthenticatedContext context(String permission) {
        ControlPlanePrincipal principal = ControlPlanePrincipal.current()
                .orElseThrow(() -> new AccessDeniedException(
                        "CONTROL_PLANE_AUTH_REQUIRED"));
        principal.require(
                principal.organizationId(), principal.actorId(), permission);
        // The caller cannot choose this value. Idempotency is a separate,
        // caller-provided key whose payload is digest-bound for replay safety.
        String requestId = "mtf-api-" + UUID.randomUUID();
        return new TaskFinopsPort.AuthenticatedContext(
                principal.organizationId(),
                principal.accountId(),
                principal.actorId(),
                requestId);
    }

    private static ResponseEntity<?> notFound(String taskId) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of(
                "status", "ERROR",
                "code", "ELMOS_MTF_TASK_UNKNOWN",
                "taskId", taskId));
    }

    private static String require(String value, int maxLength, String code) {
        String candidate = value == null ? "" : value.trim();
        if (candidate.isEmpty() || candidate.length() > maxLength
                || candidate.indexOf('\u0000') >= 0) {
            throw new TaskFinopsPort.TaskFinopsStateException(code);
        }
        return candidate;
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw new IllegalStateException("SHA-256 unavailable", exception);
        }
    }

    @ExceptionHandler(TaskFinopsPort.TaskFinopsStateException.class)
    ResponseEntity<?> taskFinopsError(TaskFinopsPort.TaskFinopsStateException exception) {
        HttpStatus status = switch (exception.code()) {
            case "ELMOS_MTF_TASK_UNKNOWN" -> HttpStatus.NOT_FOUND;
            case "ELMOS_MTF_IDEMPOTENCY_CONFLICT",
                 "ELMOS_MTF_ILLEGAL_TRANSITION",
                 "ELMOS_MTF_RECONCILIATION_REQUIRED" -> HttpStatus.CONFLICT;
            case "ELMOS_MTF_ACCOUNT_CONTEXT_UNKNOWN" -> HttpStatus.FORBIDDEN;
            default -> HttpStatus.BAD_REQUEST;
        };
        return ResponseEntity.status(status).body(Map.of(
                "status", "ERROR", "code", exception.code()));
    }
}
