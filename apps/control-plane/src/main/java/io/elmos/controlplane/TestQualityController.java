package io.elmos.controlplane;

import io.elmos.application.TestQualityGateGovernance;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/** Batch 18 read/evaluate API. Test execution remains in isolated short-lived runners. */
@RestController
@RequestMapping("/api/v1/test-quality")
public final class TestQualityController {
    private final TestQualityGateGovernance governance = new TestQualityGateGovernance();

    public record Capabilities(String engine, String workerContract, String status,
                               List<String> domains, List<String> sharedAuthorities,
                               List<String> prohibitedActions) {}

    @GetMapping("/capabilities")
    public Capabilities capabilities() {
        return new Capabilities("ELMOS_TEST_QUALITY", "/engine/v1",
                "POLICY_CORE_READY_EXTERNAL_RUNNERS_NOT_CONFIGURED",
                List.of("DISCOVERY", "QUALITY_RISK", "PORTFOLIO", "CHARACTERIZATION", "CONTRACT",
                        "PROPERTY", "MUTATION", "TEST_DATA", "ENVIRONMENT", "JOURNEY", "AI_CANDIDATE",
                        "FLAKY", "TEST_IMPACT", "QUALITY_GATE", "CONTINUOUS_VALIDATION"),
                List.of("TENANT", "WORKFLOW", "RISK", "APPROVAL", "EVIDENCE", "DELIVERY", "AUDIT", "BILLING"),
                List.of("RUN_TESTS_ON_CONTROL_PLANE", "MODIFY_QUALITY_GATE", "AUTO_PROMOTE_AI_TEST",
                        "AUTO_APPROVE_SNAPSHOT", "HIDE_FLAKY_RETRY", "TREAT_NOT_RUN_AS_PASS", "USE_PRODUCTION_SECRETS"));
    }

    @PostMapping("/quality-decisions/evaluate")
    public TestQualityGateGovernance.Result evaluate(@RequestBody TestQualityGateGovernance.Evidence evidence) {
        return governance.evaluate(evidence, Instant.now());
    }

    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(RuntimeException error) {
        return Map.of("errorCode", "TEST_QUALITY_REQUEST_REJECTED", "message", "The test quality request was rejected by its contract.", "retryable", false);
    }
}
