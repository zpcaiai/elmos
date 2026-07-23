package io.elmos.controlplane;

import io.elmos.composite.CompositeModernizationOrchestrator;
import io.elmos.composite.ProgressiveTrafficController;
import io.elmos.composite.SystemCutoverOrchestrator;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/** Read/evaluate-only Batch 13 API. Provider mutations remain behind approved external ports. */
@RestController
@RequestMapping("/api/v1/composite")
public final class CompositeController {
    private final CompositeModernizationOrchestrator orchestrator = new CompositeModernizationOrchestrator();
    private final ProgressiveTrafficController traffic = new ProgressiveTrafficController();
    private final SystemCutoverOrchestrator cutover = new SystemCutoverOrchestrator();

    @GetMapping("/capabilities")
    public CompositeModernizationOrchestrator.Capabilities capabilities() {
        return orchestrator.capabilities();
    }

    @PostMapping("/traffic/evaluate")
    public ProgressiveTrafficController.PromotionDecision evaluateTraffic(
            @RequestBody ProgressiveTrafficController.TrafficStageRequest request) {
        return traffic.evaluate(request);
    }

    @PostMapping("/decommission/evaluate")
    public SystemCutoverOrchestrator.DecommissionDecision evaluateDecommission(
            @RequestBody SystemCutoverOrchestrator.DecommissionEvidence request) {
        return cutover.decommission(request);
    }

    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(RuntimeException error) {
        return Map.of("errorCode", "COMPOSITE_REQUEST_REJECTED", "message", "The composite modernization request was rejected by its contract.",
                "retryable", false);
    }
}
