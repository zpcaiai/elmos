package io.elmos.controlplane;

import io.elmos.application.SuiteCutoverGovernance;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/enterprise-suite")
public final class EnterpriseSuiteController {
    private static final List<String> PROHIBITED_DIRECT_ACTIONS = List.of(
            "MODIFY_PRODUCTION_CONFIGURATION", "PUBLISH_PRODUCTION_TRANSPORT",
            "DEPLOY_PRODUCTION_SOLUTION", "DEPLOY_SALESFORCE_PRODUCTION",
            "MODIFY_USER_PERMISSION", "BULK_DELETE_BUSINESS_DATA",
            "ACCEPT_PROCESS_DIFFERENCE", "ACCEPT_FINANCIAL_DIFFERENCE",
            "ACCEPT_SOD_CONFLICT", "AUTO_CUTOVER", "AUTO_DECOMMISSION");
    private final SuiteCutoverGovernance governance = new SuiteCutoverGovernance();

    @GetMapping("/capabilities")
    public Capabilities capabilities() {
        return new Capabilities("ELMOS_ENTERPRISE_SUITE", "/engine/v1", false,
                "INDEPENDENT_CONTROL_PLANE", PROHIBITED_DIRECT_ACTIONS);
    }
    @PostMapping("/cutover/evaluate")
    public SuiteCutoverGovernance.Result evaluateCutover(@RequestBody SuiteCutoverGovernance.Evidence evidence) {
        return governance.evaluateCutover(evidence, Instant.now());
    }
    @PostMapping("/decommission/evaluate")
    public SuiteCutoverGovernance.Result evaluateDecommission(@RequestBody SuiteCutoverGovernance.Evidence evidence) {
        return governance.evaluateDecommission(evidence, Instant.now());
    }
    @ExceptionHandler(IllegalArgumentException.class) @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(IllegalArgumentException error) {
        return Map.of("errorCode", "SUITE_REQUEST_REJECTED", "message", "The enterprise suite request was rejected by its contract.", "retryable", false);
    }
    public record Capabilities(String engine, String workerApi, boolean executesSuiteChanges,
                               String decisionAuthority, List<String> prohibitedDirectActions) {}
}
