package io.elmos.controlplane;

import io.elmos.application.IntegrationCutoverGovernance;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/integration")
public final class EnterpriseIntegrationController {
    private static final List<String> PROHIBITED_DIRECT_ACTIONS = List.of(
            "PURGE_PRODUCTION_QUEUE", "RESET_PRODUCTION_OFFSET", "DELETE_TOPIC",
            "MODIFY_PARTNER_CERTIFICATE", "REPLAY_PRODUCTION_MESSAGE",
            "CREATE_PUBLIC_GATEWAY_ROUTE", "SWITCH_PRODUCER", "ACCEPT_MESSAGE_LOSS",
            "AUTO_CUTOVER", "AUTO_DECOMMISSION");
    private final IntegrationCutoverGovernance governance = new IntegrationCutoverGovernance();

    @GetMapping("/capabilities")
    public Capabilities capabilities() {
        return new Capabilities("ELMOS_ENTERPRISE_INTEGRATION", "/engine/v1", false,
                "INDEPENDENT_CONTROL_PLANE", PROHIBITED_DIRECT_ACTIONS);
    }

    @PostMapping("/cutover/evaluate")
    public IntegrationCutoverGovernance.Result evaluateCutover(@RequestBody IntegrationCutoverGovernance.Evidence evidence) {
        return governance.evaluateCutover(evidence, Instant.now());
    }

    @PostMapping("/decommission/evaluate")
    public IntegrationCutoverGovernance.Result evaluateDecommission(@RequestBody IntegrationCutoverGovernance.Evidence evidence) {
        return governance.evaluateDecommission(evidence, Instant.now());
    }

    @ExceptionHandler(IllegalArgumentException.class) @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(IllegalArgumentException error) {
        return Map.of("errorCode", "INTEGRATION_REQUEST_REJECTED", "message", "The enterprise integration request was rejected by its contract.", "retryable", false);
    }

    public record Capabilities(String engine, String workerApi, boolean executesIntegrationChanges,
                               String decisionAuthority, List<String> prohibitedDirectActions) {}
}
