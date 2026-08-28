package io.elmos.controlplane;

import io.elmos.productionruntime.JdbcProductionProviderPayloadStore;
import io.elmos.productionruntime.ProductionBillingPort;
import io.elmos.productionruntime.ProductionRuntimeModels.FinalUsage;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ReserveRequest;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

/** Bounded zero-usage reserve/settle cycle for an approved target-gate tenant. */
@RestController
@RequestMapping("/internal/v1/production-runtime/gate")
@ConditionalOnProperty(
        prefix = "elmos.production-runtime.gate", name = "enabled", havingValue = "true")
@ConditionalOnExpression("'${component:scheduler}' == 'billing' and '${elmos.production-runtime.billing.adapter:jdbc}' == 'jdbc'")
class ProductionRuntimeBillingGateController {
    private final ProductionRuntimeGateAuthenticator authenticator;
    private final ProductionRuntimeGateFixture fixture;
    private final ProductionBillingPort billing;

    ProductionRuntimeBillingGateController(
            ProductionRuntimeGateAuthenticator authenticator,
            ProductionRuntimeGateFixture fixture,
            ProductionBillingPort billing
    ) {
        this.authenticator = authenticator;
        this.fixture = fixture;
        this.billing = billing;
    }

    @PostMapping("/billing-cycle")
    Map<String, Object> billingCycle(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestBody GateCycleRequest request
    ) {
        authenticator.require(authorization);
        if (request.idempotencyKey() == null
                || !request.idempotencyKey().matches("[A-Za-z0-9._:-]{16,200}")) {
            throw new IllegalArgumentException("gate idempotency key is malformed");
        }
        long started = System.nanoTime();
        var reservation = billing.reserve(new ReserveRequest(
                fixture.tenantId(), fixture.walletId(), fixture.projectId(), fixture.jobId(),
                fixture.workItemId(), "gate:reserve:" + request.idempotencyKey(),
                fixture.reservationAmount(), Instant.now().plusSeconds(300)));
        try {
            String requestHash = JdbcProductionProviderPayloadStore.sha256(
                    request.idempotencyKey().getBytes(java.nio.charset.StandardCharsets.UTF_8));
            var call = billing.beginModelCall(new ModelCallRequest(
                    fixture.tenantId(), fixture.accountId(), fixture.projectId(),
                    fixture.jobId(), fixture.stageId(), fixture.workItemId(), fixture.attemptId(),
                    fixture.provider(), fixture.model(),
                    "gate:model:" + request.idempotencyKey(), requestHash));
            billing.settle(new FinalUsage(
                    fixture.tenantId(), reservation.reservationId(), call.modelCallId(),
                    fixture.provider(), fixture.model(),
                    "gate:usage:" + request.idempotencyKey(),
                    fixture.providerPricingVersionId(),
                    fixture.commercialPricingVersionId(),
                    0, 0, 0, 0, BigDecimal.ZERO, BigDecimal.ZERO));
            return Map.of(
                    "status", "PASS",
                    "reservationId", reservation.reservationId(),
                    "modelCallId", call.modelCallId(),
                    "reserveSettleLatencyMs", (System.nanoTime() - started) / 1_000_000.0,
                    "measuredAt", Instant.now().toString());
        } catch (RuntimeException ex) {
            billing.release(
                    fixture.tenantId(), reservation.reservationId(),
                    "GATE_CYCLE_FAILED");
            throw ex;
        }
    }

    @ExceptionHandler(AccessDeniedException.class)
    ResponseEntity<Map<String, String>> denied(AccessDeniedException ex) {
        return ResponseEntity.status(401).body(Map.of("code", ex.getMessage()));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> invalid(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body(Map.of("code", "PRODUCTION_GATE_REQUEST_INVALID"));
    }

    record GateCycleRequest(String idempotencyKey) {}
}
