package io.elmos.controlplane;

import io.elmos.workflow.RunnerRegistrationPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Tenant-bound, secret-free fleet inventory for the operations console.
 *
 * <p>The Spring filter chain exposes exactly this GET route to the existing
 * short-lived operations credential. Reachability is not authorization: the
 * same dual OIDC/credential decision used by the other operations controllers
 * must succeed before the persistence port is touched.</p>
 */
@RestController
@RequestMapping("/api/v1/operations-observability/runners")
public final class OperationsRunnerFleetAdministrationController {
    private static final int MAX_LIMIT = 100;

    private final RunnerRegistrationPort fleet;
    private final OperationsAuthorization authorization;

    public OperationsRunnerFleetAdministrationController(
            RunnerRegistrationPort fleet,
            OperationsAuthorization authorization
    ) {
        this.fleet = fleet;
        this.authorization = authorization;
    }

    public record FleetListView(
            String schemaVersion,
            List<RunnerRegistrationPort.FleetNodeView> items,
            int limit,
            int returned,
            boolean truncated,
            String status
    ) {
    }

    @GetMapping
    public FleetListView list(
            @RequestHeader(value = "X-ELMOS-Operations-Key", required = false) String presentedKey,
            @RequestHeader(value = "X-ELMOS-Organization-ID", required = false) String organizationId,
            @RequestHeader(value = "X-ELMOS-Actor-ID", required = false) String actorId,
            @RequestHeader(value = "X-ELMOS-Admin-Role", required = false) String role,
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(required = false) String status
    ) {
        authorization.requireManagement(
                presentedKey, organizationId, actorId, role, "VIEWER");
        int boundedLimit = requireLimit(limit);
        RunnerRegistrationPort.FleetStatus fleetStatus = parseStatus(status);

        // One bounded look-ahead row is enough to signal truncation without a
        // separate count that could become an unbounded fleet scan.
        List<RunnerRegistrationPort.FleetNodeView> result = fleet.listFleet(
                organizationId, fleetStatus, boundedLimit + 1);
        boolean truncated = result.size() > boundedLimit;
        List<RunnerRegistrationPort.FleetNodeView> items = truncated
                ? List.copyOf(result.subList(0, boundedLimit))
                : List.copyOf(result);
        return new FleetListView(
                "1.0.0",
                items,
                boundedLimit,
                items.size(),
                truncated,
                fleetStatus == null ? null : fleetStatus.name());
    }

    private static int requireLimit(int value) {
        if (value < 1 || value > MAX_LIMIT) {
            throw new IllegalArgumentException("limit must be between 1 and 100");
        }
        return value;
    }

    private static RunnerRegistrationPort.FleetStatus parseStatus(String value) {
        if (value == null || value.isBlank()) return null;
        try {
            return RunnerRegistrationPort.FleetStatus.valueOf(
                    value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException rejected) {
            throw new IllegalArgumentException("status is invalid");
        }
    }

    @ExceptionHandler(SecurityException.class)
    ResponseEntity<Map<String, Object>> forbidden() {
        return error(HttpStatus.FORBIDDEN, "OPERATIONS_RUNNER_FLEET_FORBIDDEN");
    }

    @ExceptionHandler(ObservabilityUnavailableException.class)
    ResponseEntity<Map<String, Object>> unavailable() {
        return error(
                HttpStatus.SERVICE_UNAVAILABLE,
                "OPERATIONS_RUNNER_FLEET_NOT_CONFIGURED");
    }

    @ExceptionHandler({IllegalArgumentException.class,
            RunnerRegistrationPort.RunnerAuthenticationException.class})
    ResponseEntity<Map<String, Object>> invalid() {
        return error(
                HttpStatus.BAD_REQUEST,
                "OPERATIONS_RUNNER_FLEET_REQUEST_INVALID");
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
