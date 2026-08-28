package io.elmos.controlplane;

import io.elmos.productionruntime.ProductionBillingPort;
import io.elmos.productionruntime.ProductionRuntimeException;
import io.elmos.productionruntime.ProductionRuntimeModels.FinalUsage;
import io.elmos.productionruntime.ProductionRuntimeModels.MeterSnapshot;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ReserveRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.TopUpRequest;
import io.elmos.productionruntime.JdbcProductionProviderPayloadStore;
import io.elmos.productionruntime.ProductionModelCallExecutor;
import io.elmos.productionruntime.ProductionModelProviderRegistry;
import io.elmos.productionruntime.ProductionToolCallPort;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallRequest;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.Base64;

/** Billing-owned mutation API in the dedicated runtime; scheduler pods never receive billing grants. */
@RestController
@RequestMapping("/internal/v1/production-runtime/billing")
@ConditionalOnProperty(prefix = "elmos.production-runtime", name = "enabled", havingValue = "true")
@ConditionalOnExpression("'${component:scheduler}' == 'billing' and '${elmos.production-runtime.billing.adapter:jdbc}' == 'jdbc'")
class ProductionRuntimeBillingController {
    private final ProductionRuntimeInternalAuthenticator authenticator;
    private final ProductionRuntimeTopUpAuthenticator topUpAuthenticator;
    private final ProductionBillingPort billing;
    private final JdbcProductionProviderPayloadStore providerPayloads;
    private final ProductionModelCallExecutor modelCalls;
    private final ProductionToolCallPort toolCalls;
    private final ObjectProvider<ProductionModelProviderRegistry> providers;

    ProductionRuntimeBillingController(
            ProductionRuntimeInternalAuthenticator authenticator,
            ProductionRuntimeTopUpAuthenticator topUpAuthenticator,
            ProductionBillingPort billing,
            JdbcProductionProviderPayloadStore providerPayloads,
            ProductionModelCallExecutor modelCalls,
            ProductionToolCallPort toolCalls,
            ObjectProvider<ProductionModelProviderRegistry> providers
    ) {
        this.authenticator = authenticator;
        this.topUpAuthenticator = topUpAuthenticator;
        this.billing = billing;
        this.providerPayloads = providerPayloads;
        this.modelCalls = modelCalls;
        this.toolCalls = toolCalls;
        this.providers = providers;
    }

    @PostMapping("/tool-calls")
    Object beginToolCall(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestBody ToolCallRequest request
    ) {
        authenticate(authorization);
        return toolCalls.begin(request);
    }

    @PostMapping("/tool-calls/{toolCallId}/claim-provider-dispatch")
    void claimToolProviderDispatch(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @PathVariable UUID toolCallId,
            @RequestBody TenantRequest request
    ) {
        authenticate(authorization);
        toolCalls.claimProviderDispatch(request.tenantId(), toolCallId);
    }

    @PostMapping("/tool-calls/{toolCallId}/accepted")
    void toolAccepted(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @PathVariable UUID toolCallId,
            @RequestBody ProviderAccepted request
    ) {
        authenticate(authorization);
        toolCalls.markProviderAccepted(
                request.tenantId(), toolCallId, request.providerRequestId());
    }

    @PostMapping("/tool-calls/{toolCallId}/unknown")
    void toolUnknown(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @PathVariable UUID toolCallId,
            @RequestBody ProviderUnknown request
    ) {
        authenticate(authorization);
        toolCalls.markProviderUnknown(
                request.tenantId(), toolCallId,
                request.providerRequestId(), request.providerStatus());
    }

    @PostMapping("/tool-calls/{toolCallId}/complete")
    void toolComplete(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @PathVariable UUID toolCallId,
            @RequestBody ToolProviderComplete request
    ) {
        authenticate(authorization);
        toolCalls.complete(
                request.tenantId(), toolCallId, request.responseArtifactId());
    }

    @PostMapping("/tool-calls/{toolCallId}/failed")
    void toolFailed(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @PathVariable UUID toolCallId,
            @RequestBody ProviderFailed request
    ) {
        authenticate(authorization);
        toolCalls.markProviderFailed(
                request.tenantId(), toolCallId, request.providerStatus());
    }

    @PostMapping("/reservations")
    Object reserve(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestBody ReserveRequest request
    ) {
        authenticate(authorization);
        return billing.reserve(request);
    }

    @PostMapping("/reservations/{reservationId}/release")
    void release(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @PathVariable UUID reservationId,
            @RequestBody ReleaseRequest request
    ) {
        authenticate(authorization);
        billing.release(request.tenantId(), reservationId, request.reason());
    }

    @PostMapping("/settlements")
    void settle(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestBody FinalUsage usage
    ) {
        authenticate(authorization);
        billing.settle(usage);
    }

    @PostMapping("/meters")
    Object meter(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestBody MeterSnapshot meter
    ) {
        authenticate(authorization);
        return billing.recordMeter(meter);
    }

    @PostMapping("/model-calls")
    Object beginModelCall(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestBody ModelCallRequest request
    ) {
        authenticate(authorization);
        return billing.beginModelCall(request);
    }

    @PostMapping("/model-calls/{modelCallId}/claim-provider-dispatch")
    void claimProviderDispatch(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @PathVariable UUID modelCallId,
            @RequestBody TenantRequest request
    ) {
        authenticate(authorization);
        billing.claimProviderDispatch(request.tenantId(), modelCallId);
    }

    @PostMapping("/model-calls/{modelCallId}/accepted")
    void accepted(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @PathVariable UUID modelCallId,
            @RequestBody ProviderAccepted request
    ) {
        authenticate(authorization);
        billing.markProviderAccepted(
                request.tenantId(), modelCallId, request.providerRequestId());
    }

    @PostMapping("/model-calls/{modelCallId}/unknown")
    void unknown(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @PathVariable UUID modelCallId,
            @RequestBody ProviderUnknown request
    ) {
        authenticate(authorization);
        billing.markProviderUnknown(
                request.tenantId(), modelCallId,
                request.providerRequestId(), request.providerStatus());
    }

    @PostMapping("/model-calls/{modelCallId}/complete")
    void complete(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @PathVariable UUID modelCallId,
            @RequestBody ProviderComplete request
    ) {
        authenticate(authorization);
        billing.completeModelCall(
                request.tenantId(), modelCallId,
                request.providerRequestId(), request.responseArtifactId());
    }

    @PostMapping("/model-calls/{modelCallId}/failed")
    void failed(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @PathVariable UUID modelCallId,
            @RequestBody ProviderFailed request
    ) {
        authenticate(authorization);
        billing.markProviderFailed(
                request.tenantId(), modelCallId, request.providerStatus());
    }

    @PostMapping("/topups")
    Object topUp(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestBody TopUpRequest request
    ) {
        topUpAuthenticator.require(authorization);
        return billing.applyVerifiedTopUp(request);
    }

    @PostMapping("/providers/model-calls")
    Object executeProviderModelCall(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestBody ModelCallExecutionRequest request
    ) {
        authenticate(authorization);
        byte[] bytes;
        try {
            bytes = Base64.getDecoder().decode(request.payloadBase64());
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("payloadBase64 is invalid", ex);
        }
        providerPayloads.persist(request.request(), bytes);
        var registry = providers.getIfAvailable(() -> {
            throw new IllegalStateException("production model providers are not configured");
        });
        return modelCalls.execute(
                request.request(),
                registry.require(request.request().provider(), request.request().model()));
    }

    @PostMapping("/providers/model-calls/{modelCallId}/reconcile")
    Object reconcileProviderModelCall(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @PathVariable UUID modelCallId,
            @RequestBody ModelCallReconciliationRequest request
    ) {
        authenticate(authorization);
        var registry = providers.getIfAvailable(() -> {
            throw new IllegalStateException("production model providers are not configured");
        });
        return modelCalls.reconcile(
                request.request(), modelCallId, request.providerRequestId(),
                registry.require(request.request().provider(), request.request().model()));
    }

    @PostMapping("/recovery/expire-reservations")
    Map<String, Integer> expire(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestBody LimitRequest request
    ) {
        authenticate(authorization);
        return Map.of("expired", billing.expireReservations(request.limit()));
    }

    @GetMapping("/recovery/model-calls")
    List<?> uncertain(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestParam(defaultValue = "64") int limit
    ) {
        authenticate(authorization);
        return billing.uncertainModelCalls(limit);
    }

    @ExceptionHandler(ProductionRuntimeException.class)
    ResponseEntity<Map<String, String>> runtimeError(ProductionRuntimeException ex) {
        int status = "CREDIT_EXHAUSTED".equals(ex.code()) ? 402
                : ex.code().contains("CONFLICT") || ex.code().contains("IN_PROGRESS") ? 409
                : 422;
        return ResponseEntity.status(status).body(Map.of("code", ex.code()));
    }

    @ExceptionHandler(AccessDeniedException.class)
    ResponseEntity<Map<String, String>> denied(AccessDeniedException ex) {
        return ResponseEntity.status(401).body(Map.of("code", ex.getMessage()));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> invalid(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body(Map.of("code", "BILLING_REQUEST_INVALID"));
    }

    private void authenticate(String authorization) {
        authenticator.require(authorization);
    }

    record ReleaseRequest(UUID tenantId, String reason) {}
    record TenantRequest(UUID tenantId) {}
    record ProviderAccepted(UUID tenantId, String providerRequestId) {}
    record ProviderUnknown(UUID tenantId, String providerRequestId, String providerStatus) {}
    record ProviderComplete(UUID tenantId, String providerRequestId, UUID responseArtifactId) {}
    record ToolProviderComplete(UUID tenantId, UUID responseArtifactId) {}
    record ProviderFailed(UUID tenantId, String providerStatus) {}
    record LimitRequest(int limit) {}
    record ModelCallExecutionRequest(ModelCallRequest request, String payloadBase64) {}
    record ModelCallReconciliationRequest(
            ModelCallRequest request,
            String providerRequestId
    ) {}
}
