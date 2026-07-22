package io.elmos.controlplane;

import io.elmos.application.MainframeCutoverGovernance;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/mainframe")
public final class MainframeController {
    private final MainframeCutoverGovernance governance = new MainframeCutoverGovernance();
    public record Capabilities(String engine, String workerBasePath, List<String> sharedAuthorities,
                               List<String> decisionGates, List<String> prohibitedActions) {}

    @GetMapping("/capabilities")
    public Capabilities capabilities() {
        return new Capabilities("ELMOS_MAINFRAME", "/engine/v1",
                List.of("TENANT", "WORKFLOW", "RISK", "APPROVAL", "EVIDENCE", "AUDIT", "BILLING", "DELIVERY"),
                List.of("SOURCE_RUNTIME", "COPYBOOK", "JCL_BATCH", "CICS", "IMS", "DATA_AUTHORITY", "SEMANTIC_EQUIVALENCE", "PARALLEL_RUN", "CUTOVER", "DECOMMISSION"),
                List.of("EXECUTE_ZOS_ON_CONTROL_PLANE", "SUBMIT_ARBITRARY_JCL", "WRITE_PRODUCTION_DATASET",
                        "AUTO_APPROVE_RULE", "AUTO_APPROVE_TRANSFORMATION", "AUTO_SWITCH_DATA_AUTHORITY", "AUTO_DECOMMISSION"));
    }

    @PostMapping("/cutover-decisions/evaluate")
    public MainframeCutoverGovernance.Result evaluateCutover(@RequestBody MainframeCutoverGovernance.Evidence evidence) {
        return governance.evaluateCutover(evidence, Instant.now());
    }

    @PostMapping("/decommission-decisions/evaluate")
    public MainframeCutoverGovernance.Result evaluateDecommission(@RequestBody MainframeCutoverGovernance.Evidence evidence) {
        return governance.evaluateDecommission(evidence, Instant.now());
    }

    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String,Object> badRequest(RuntimeException error) {
        return Map.of("errorCode", "MAINFRAME_REQUEST_REJECTED", "message", error.getMessage(), "retryable", false);
    }
}
