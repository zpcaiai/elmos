package io.elmos.controlplane;

import io.elmos.application.DatabaseDataCutoverGovernance;
import org.springframework.http.HttpStatus;
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

    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(RuntimeException error) {
        return Map.of("errorCode", "DATABASE_DATA_REQUEST_REJECTED", "message", "The database and data request was rejected by its contract.",
                "retryable", false);
    }
}
