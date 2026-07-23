package io.elmos.controlplane;

import io.elmos.application.FrontendClientReleaseGovernance;
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

/** Batch 14 governance API. Execution remains in the isolated TypeScript worker and Runners. */
@RestController
@RequestMapping("/api/v1/frontend-client")
public final class FrontendClientController {
    private final FrontendClientReleaseGovernance releaseGovernance = new FrontendClientReleaseGovernance();

    public record Capabilities(String engine, String workerContract, String status,
                               List<String> sharedAuthorities, List<String> prohibitedActions) {}

    @GetMapping("/capabilities")
    public Capabilities capabilities() {
        return new Capabilities("ELMOS_FRONTEND_CLIENT", "/engine/v1",
                "STATIC_CORE_READY_EXTERNAL_RUNNERS_NOT_CONFIGURED",
                List.of("TENANT", "WORKFLOW", "RISK", "APPROVAL", "EVIDENCE", "DELIVERY",
                        "PORTFOLIO", "AUDIT", "BILLING"),
                List.of("EXECUTE_CUSTOMER_CODE", "USE_CUSTOMER_LOGIN_CREDENTIALS",
                        "AUTO_ACCEPT_VISUAL_CHANGE", "AUTO_CLOSE_ACCESSIBILITY_FINDING",
                        "AUTO_SIGN_CLIENT", "AUTO_PUBLISH_APP_STORE", "AUTO_FORCE_UPGRADE"));
    }

    @PostMapping("/release/evaluate")
    public FrontendClientReleaseGovernance.ReleaseDecision evaluateRelease(
            @RequestBody FrontendClientReleaseGovernance.ReleaseEvidence evidence) {
        return releaseGovernance.evaluate(evidence);
    }

    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(RuntimeException error) {
        return Map.of("errorCode", "FRONTEND_CLIENT_REQUEST_REJECTED", "message", "The frontend client request was rejected by its contract.",
                "retryable", false);
    }
}
