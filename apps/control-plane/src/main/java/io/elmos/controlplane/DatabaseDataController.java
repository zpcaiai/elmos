package io.elmos.controlplane;

import com.fasterxml.jackson.databind.JsonNode;
import io.elmos.application.DatabaseDataCutoverGovernance;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/** Batch 15 governance API. Vendor execution remains in the isolated worker and approved Runners. */
@RestController
@RequestMapping("/api/v1/database-data")
public final class DatabaseDataController {
    private final DatabaseDataCutoverGovernance governance = new DatabaseDataCutoverGovernance();
    private final ChinaDbSqlPreflightGateway sqlPreflight;

    public DatabaseDataController(ChinaDbSqlPreflightGateway sqlPreflight) {
        this.sqlPreflight = sqlPreflight;
    }

    public record Capabilities(String engine, String workerContract, String status,
                               List<String> tracks, List<String> sharedAuthorities,
                               List<String> prohibitedActions) {}

    @GetMapping("/capabilities")
    public Capabilities capabilities() {
        return new Capabilities("ELMOS_DATABASE_DATA", "/engine/v1",
                "POLICY_CORE_READY_EXTERNAL_RUNNERS_NOT_CONFIGURED",
                List.of("OLTP_DATABASE", "ANALYTICS_PLATFORM", "BI_SEMANTIC"),
                List.of("TENANT", "WORKFLOW", "RISK", "APPROVAL", "EVIDENCE", "DELIVERY",
                        "PORTFOLIO", "AUDIT", "BILLING"),
                List.of("CONNECT_TO_CUSTOMER_DATABASE", "EXECUTE_VENDOR_CLI", "CHANGE_LOGGING",
                        "START_CDC", "WRITE_PRODUCTION_DATA", "SWITCH_AUTHORITATIVE_WRITER",
                        "AUTO_APPROVE_METRIC", "AUTO_DECOMMISSION_SOURCE"));
    }

    @PostMapping("/cutover/evaluate")
    public DatabaseDataCutoverGovernance.Result evaluateCutover(
            @RequestBody DatabaseDataCutoverGovernance.Evidence evidence) {
        return governance.evaluate(evidence);
    }

    @GetMapping(value = "/sql-preflight/capabilities", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<JsonNode> sqlPreflightCapabilities() {
        principal("workspace:view");
        return ResponseEntity.ok()
                .header("Cache-Control", "private, no-store")
                .body(sqlPreflight.capabilities());
    }

    @PostMapping(
            value = "/sql-preflight/assess",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<JsonNode> assessSql(@RequestBody byte[] request) {
        ControlPlanePrincipal principal = principal("translation:execute");
        return ResponseEntity.ok()
                .header("Cache-Control", "private, no-store")
                .body(sqlPreflight.assess(
                        request, principal.organizationId(), principal.actorId()));
    }

    @ExceptionHandler(ChinaDbSqlPreflightFailure.class)
    ResponseEntity<Map<String, Object>> sqlPreflightFailure(ChinaDbSqlPreflightFailure error) {
        return ResponseEntity.status(error.status())
                .header("Cache-Control", "private, no-store")
                .body(error.body());
    }

    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(RuntimeException error) {
        return Map.of("errorCode", "DATABASE_DATA_REQUEST_REJECTED", "message", "The database and data request was rejected by its contract.",
                "retryable", false);
    }

    private static ControlPlanePrincipal principal(String permission) {
        ControlPlanePrincipal principal = ControlPlanePrincipal.current()
                .orElseThrow(() -> new AccessDeniedException("CONTROL_PLANE_AUTH_REQUIRED"));
        principal.require(principal.organizationId(), principal.actorId(), permission);
        return principal;
    }
}
