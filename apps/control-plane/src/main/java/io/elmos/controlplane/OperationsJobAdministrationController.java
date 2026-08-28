package io.elmos.controlplane;

import io.elmos.workflow.ExecutionJobPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Operations-console view of the durable execution queue.
 *
 * <p>The route deliberately lives below the already dual-authorized operations
 * namespace. The Spring filter chain only makes the controller reachable; this
 * controller still requires either an OIDC administrator or the exact
 * tenant-bound, short-lived operations credential through
 * {@link OperationsAuthorization}.</p>
 */
@RestController
@RequestMapping("/api/v1/operations-observability/jobs")
public final class OperationsJobAdministrationController {
    private static final int MAX_LIMIT = 100;
    private static final int MAX_STATUS_SCAN = 500;
    private static final int SCAN_PAGE_SIZE = 100;
    private static final String IDENTIFIER = "[A-Za-z0-9][A-Za-z0-9._:-]{0,127}";

    private final ExecutionJobPort jobs;
    private final OperationsAuthorization authorization;

    public OperationsJobAdministrationController(
            ExecutionJobPort jobs,
            OperationsAuthorization authorization
    ) {
        this.jobs = jobs;
        this.authorization = authorization;
    }

    public record JobListView(
            String schemaVersion,
            List<ExecutionJobPort.JobView> items,
            int limit,
            int scanned,
            boolean scanTruncated,
            String businessLine,
            String status
    ) {}

    public record CancellationView(
            String schemaVersion,
            String jobId,
            ExecutionJobPort.Status status,
            boolean cancelRequested,
            boolean idempotentReplay
    ) {}

    @GetMapping
    public JobListView list(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader(value = "X-ELMOS-Organization-ID", required = false) String organizationId,
            @RequestHeader(value = "X-ELMOS-Actor-ID", required = false) String actorId,
            @RequestHeader(value = "X-ELMOS-Admin-Role", required = false) String role,
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(required = false) String businessLine,
            @RequestParam(required = false) String status
    ) {
        authorization.requireManagement(
                presentedKey, organizationId, actorId, role, "VIEWER");
        int boundedLimit = requireLimit(limit);
        ExecutionJobPort.BusinessLine line = parseBusinessLine(businessLine);
        ExecutionJobPort.Status statusFilter = parseStatus(status);

        List<ExecutionJobPort.JobView> selected = new ArrayList<>();
        int scanned = 0;
        boolean exhausted = false;
        int maximumScan = statusFilter == null ? boundedLimit : MAX_STATUS_SCAN;
        while (scanned < maximumScan && selected.size() < boundedLimit) {
            int pageSize = Math.min(SCAN_PAGE_SIZE, maximumScan - scanned);
            List<ExecutionJobPort.JobView> page = jobs.list(
                    organizationId, line, pageSize, scanned);
            scanned += page.size();
            for (ExecutionJobPort.JobView job : page) {
                if (statusFilter == null || job.status() == statusFilter) {
                    selected.add(job);
                    if (selected.size() == boundedLimit) break;
                }
            }
            if (page.size() < pageSize) {
                exhausted = true;
                break;
            }
            if (statusFilter == null) break;
        }

        boolean scanTruncated = statusFilter != null
                && selected.size() < boundedLimit
                && !exhausted
                && scanned >= MAX_STATUS_SCAN;
        return new JobListView(
                "1.0.0",
                List.copyOf(selected),
                boundedLimit,
                scanned,
                scanTruncated,
                line == null ? null : line.name(),
                statusFilter == null ? null : statusFilter.name());
    }

    @PostMapping("/{jobId}/cancel")
    public ResponseEntity<CancellationView> cancel(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader(value = "X-ELMOS-Organization-ID", required = false) String organizationId,
            @RequestHeader(value = "X-ELMOS-Actor-ID", required = false) String actorId,
            @RequestHeader(value = "X-ELMOS-Admin-Role", required = false) String role,
            @PathVariable String jobId
    ) {
        authorization.requireManagement(
                presentedKey, organizationId, actorId, role, "OPERATOR");
        requireIdentifier(jobId);
        ExecutionJobPort.JobView job = jobs.find(organizationId, jobId)
                .orElseThrow(() -> new ExecutionJobPort.ExecutionStateException(
                        "ELMOS_EXECUTION_JOB_UNKNOWN"));
        if (terminal(job.status())) {
            throw new ExecutionJobPort.ExecutionStateException(
                    "ELMOS_EXECUTION_JOB_TERMINAL");
        }
        if (job.cancelRequested()) {
            return ResponseEntity.ok(new CancellationView(
                    "1.0.0", jobId, job.status(), true, true));
        }
        ExecutionJobPort.Status current = jobs.requestCancel(
                organizationId, jobId, actorId);
        return ResponseEntity.accepted().body(new CancellationView(
                "1.0.0", jobId, current, true, false));
    }

    private static int requireLimit(int value) {
        if (value < 1 || value > MAX_LIMIT) {
            throw new IllegalArgumentException("limit must be between 1 and 100");
        }
        return value;
    }

    private static ExecutionJobPort.BusinessLine parseBusinessLine(String value) {
        if (value == null || value.isBlank()) return null;
        try {
            return ExecutionJobPort.BusinessLine.valueOf(
                    value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException rejected) {
            throw new IllegalArgumentException("businessLine is invalid");
        }
    }

    private static ExecutionJobPort.Status parseStatus(String value) {
        if (value == null || value.isBlank()) return null;
        try {
            return ExecutionJobPort.Status.valueOf(
                    value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException rejected) {
            throw new IllegalArgumentException("status is invalid");
        }
    }

    private static void requireIdentifier(String value) {
        if (value == null || !value.matches(IDENTIFIER)) {
            throw new IllegalArgumentException("jobId is invalid");
        }
    }

    private static boolean terminal(ExecutionJobPort.Status status) {
        return switch (status) {
            case SUCCEEDED, PARTIAL, FAILED, CANCELLED, LOST -> true;
            case QUEUED, CLAIMED, RUNNING -> false;
        };
    }

    @ExceptionHandler(SecurityException.class)
    ResponseEntity<Map<String, Object>> forbidden() {
        return error(HttpStatus.FORBIDDEN, "OPERATIONS_JOB_FORBIDDEN");
    }

    @ExceptionHandler(ObservabilityUnavailableException.class)
    ResponseEntity<Map<String, Object>> unavailable() {
        return error(HttpStatus.SERVICE_UNAVAILABLE, "OPERATIONS_JOB_NOT_CONFIGURED");
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, Object>> invalid() {
        return error(HttpStatus.BAD_REQUEST, "OPERATIONS_JOB_REQUEST_INVALID");
    }

    @ExceptionHandler(ExecutionJobPort.ExecutionStateException.class)
    ResponseEntity<Map<String, Object>> executionState(
            ExecutionJobPort.ExecutionStateException failure
    ) {
        HttpStatus status = switch (failure.code()) {
            case "ELMOS_EXECUTION_JOB_UNKNOWN" -> HttpStatus.NOT_FOUND;
            case "ELMOS_EXECUTION_JOB_TERMINAL" -> HttpStatus.CONFLICT;
            default -> HttpStatus.CONFLICT;
        };
        String code = switch (failure.code()) {
            case "ELMOS_EXECUTION_JOB_UNKNOWN", "ELMOS_EXECUTION_JOB_TERMINAL" -> failure.code();
            default -> "ELMOS_EXECUTION_JOB_STATE_CONFLICT";
        };
        return error(status, code);
    }

    private static ResponseEntity<Map<String, Object>> error(
            HttpStatus status,
            String code
    ) {
        return ResponseEntity.status(status).body(Map.of(
                "status", "ERROR",
                "errorCode", code,
                "retryable", false));
    }
}
