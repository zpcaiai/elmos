package io.elmos.controlplane;

import io.elmos.application.SecurityAuthorizationGovernance;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/** Batch 17 read/evaluate API. Security tools execute only in isolated approved adapters. */
@RestController
@RequestMapping("/api/v1/security-compliance")
public final class SecurityComplianceController {
    private final SecurityAuthorizationGovernance governance = new SecurityAuthorizationGovernance();

    public record Capabilities(String engine, String workerContract, String status,
                               List<String> domains, List<String> sharedAuthorities,
                               List<String> prohibitedActions) {}

    @GetMapping("/capabilities")
    public Capabilities capabilities() {
        return new Capabilities("ELMOS_SECURITY_COMPLIANCE", "/engine/v1",
                "POLICY_CORE_READY_EXTERNAL_ADAPTERS_NOT_CONFIGURED",
                List.of("ESTATE", "IDENTITY", "SECRETS_CRYPTO", "SECURE_SDLC", "SUPPLY_CHAIN",
                        "STATIC_DYNAMIC_RUNTIME", "VULNERABILITY_RISK", "CLOUD", "DATA_PRIVACY",
                        "THREAT_MODEL", "DETECTION_RESPONSE", "COMPLIANCE_OSCAL", "CONTINUOUS_AUTHORIZATION"),
                List.of("TENANT", "WORKFLOW", "RISK", "APPROVAL", "EVIDENCE", "DELIVERY",
                        "PORTFOLIO", "AUDIT", "BILLING", "SECRET_BROKER"),
                List.of("RUN_HOST_SCANNER", "UNAUTHORIZED_ACTIVE_TEST", "MODIFY_PRODUCTION",
                        "DUMP_SECRET", "DISABLE_CONTROL", "DELETE_EVIDENCE", "ACCEPT_RISK",
                        "GRANT_FORMAL_CERTIFICATION", "ISSUE_FORMAL_ATO"));
    }

    @PostMapping("/authorization/evaluate")
    public SecurityAuthorizationGovernance.Result evaluate(@RequestBody SecurityAuthorizationGovernance.Evidence evidence) {
        return governance.evaluate(evidence, Instant.now());
    }

    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(RuntimeException error) {
        return Map.of("errorCode", "SECURITY_REQUEST_REJECTED", "message", error.getMessage(), "retryable", false);
    }
}
