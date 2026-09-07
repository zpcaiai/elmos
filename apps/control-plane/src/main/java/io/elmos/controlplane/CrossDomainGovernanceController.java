package io.elmos.controlplane;

import io.elmos.application.CrossDomainDecisionGovernance;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/domain-governance")
public final class CrossDomainGovernanceController {
    private final CrossDomainDecisionGovernance governance = new CrossDomainDecisionGovernance();
    @PostMapping("/evaluate")
    public CrossDomainDecisionGovernance.Result evaluate(@RequestBody CrossDomainDecisionGovernance.Request request) {
        return governance.evaluate(request, Instant.now());
    }
    @ExceptionHandler(IllegalArgumentException.class) @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String,Object> badRequest(IllegalArgumentException error) {
        return Map.of("errorCode", "DOMAIN_GOVERNANCE_REQUEST_REJECTED", "message", "The cross-domain governance request was rejected by its contract.", "retryable", false);
    }
}
