package io.elmos.controlplane;

import io.elmos.productionruntime.ProductionRuntimeScheduler;
import io.elmos.productionruntime.ProductionRuntimeStore;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.Map;

/** Read-only target gate on the dedicated scheduler service and its exact fixture. */
@RestController
@RequestMapping("/internal/v1/production-runtime/gate")
@ConditionalOnProperty(
        prefix = "elmos.production-runtime.gate", name = "enabled", havingValue = "true")
@ConditionalOnExpression("'${component:scheduler}' == 'scheduler'")
class ProductionRuntimeSchedulerGateController {
    private final ProductionRuntimeGateAuthenticator authenticator;
    private final ProductionRuntimeGateFixture fixture;
    private final ProductionRuntimeStore runtime;
    private final ProductionRuntimeScheduler scheduler;

    ProductionRuntimeSchedulerGateController(
            ProductionRuntimeGateAuthenticator authenticator,
            ProductionRuntimeGateFixture fixture,
            ProductionRuntimeStore runtime,
            ProductionRuntimeScheduler scheduler
    ) {
        this.authenticator = authenticator;
        this.fixture = fixture;
        this.runtime = runtime;
        this.scheduler = scheduler;
    }

    @GetMapping("/scheduler-frontier")
    Map<String, Object> schedulerFrontier(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestParam(defaultValue = "32") int limit
    ) {
        authenticator.require(authorization);
        long started = System.nanoTime();
        var frontier = scheduler.fairFrontier(limit);
        double elapsedMs = (System.nanoTime() - started) / 1_000_000.0;
        long blocked = frontier.stream()
                .filter(item -> item.walletId() == null || item.workerId() == null).count();
        return Map.of(
                "status", "PASS",
                "claimLatencyMs", elapsedMs,
                "candidateCount", frontier.size(),
                "blockedCandidateCount", blocked,
                "measuredAt", Instant.now().toString());
    }

    @GetMapping("/projection-freshness")
    Map<String, Object> projectionFreshness(
            @RequestHeader(name = "Authorization", required = false) String authorization
    ) {
        authenticator.require(authorization);
        long freshness = runtime.projectionFreshness(
                fixture.tenantId(), fixture.jobId()).toMillis();
        return Map.of(
                "status", freshness < 2_000 ? "PASS" : "FAIL",
                "tenantId", fixture.tenantId(),
                "jobId", fixture.jobId(),
                "freshnessMs", freshness,
                "measuredAt", Instant.now().toString());
    }

    @GetMapping("/invariants")
    Map<String, Object> invariants(
            @RequestHeader(name = "Authorization", required = false) String authorization
    ) {
        authenticator.require(authorization);
        var violations = runtime.invariantViolations(fixture.tenantId());
        return Map.of(
                "status", violations.isEmpty() ? "PASS" : "FAIL",
                "tenantId", fixture.tenantId(),
                "violations", violations,
                "measuredAt", Instant.now().toString());
    }

    @ExceptionHandler(AccessDeniedException.class)
    ResponseEntity<Map<String, String>> denied(AccessDeniedException ex) {
        return ResponseEntity.status(401).body(Map.of("code", "UNAUTHORIZED"));
    }
}
