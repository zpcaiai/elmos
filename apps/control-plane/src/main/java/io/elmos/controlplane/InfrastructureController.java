package io.elmos.controlplane;

import io.elmos.application.InfrastructureCutoverGovernance;
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

/** Batch 16 governance API. Provider execution remains in isolated approved Runners. */
@RestController
@RequestMapping("/api/v1/infrastructure")
public final class InfrastructureController {
    private final InfrastructureCutoverGovernance governance = new InfrastructureCutoverGovernance();

    public record Capabilities(String engine, String workerContract, String status,
                               List<String> tracks, List<String> sharedAuthorities,
                               List<String> prohibitedActions) {}

    @GetMapping("/capabilities")
    public Capabilities capabilities() {
        return new Capabilities("ELMOS_INFRASTRUCTURE", "/engine/v1",
                "POLICY_CORE_READY_EXTERNAL_RUNNERS_NOT_CONFIGURED",
                List.of("VM_MODERNIZATION", "CONTAINER_KUBERNETES", "SERVERLESS_EVENT_DRIVEN", "CLOUD_GOVERNANCE"),
                List.of("TENANT", "WORKFLOW", "RISK", "APPROVAL", "EVIDENCE", "DELIVERY",
                        "PORTFOLIO", "AUDIT", "BILLING", "SECRET_BROKER"),
                List.of("CALL_CLOUD_PROVIDER", "OPEN_SSH_OR_WINRM", "RUN_TERRAFORM_OR_OPENTOFU",
                        "APPLY_PRODUCTION", "MODIFY_IAM", "OPEN_PUBLIC_ACCESS", "CHANGE_DNS",
                        "SHIFT_TRAFFIC", "RUN_PRODUCTION_CHAOS", "DELETE_RESOURCE", "DECOMMISSION_LEGACY"));
    }

    @PostMapping("/cutover/evaluate")
    public InfrastructureCutoverGovernance.Result evaluateCutover(
            @RequestBody InfrastructureCutoverGovernance.Evidence evidence) {
        return governance.evaluate(evidence);
    }

    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(RuntimeException error) {
        return Map.of("errorCode", "INFRASTRUCTURE_REQUEST_REJECTED", "message", error.getMessage(), "retryable", false);
    }
}
