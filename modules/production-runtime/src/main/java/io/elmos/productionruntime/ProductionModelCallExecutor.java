package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallStatus;

import java.util.Objects;
import java.util.UUID;

/**
 * Executes a provider-neutral model call through the durable receipt state
 * machine. It never retries a provider call after an uncertain outcome.
 */
public final class ProductionModelCallExecutor {
    private final ProductionBillingPort billing;

    public ProductionModelCallExecutor(ProductionBillingPort billing) {
        this.billing = Objects.requireNonNull(billing, "billing");
    }

    public ModelCallReceipt execute(ModelCallRequest request, ProductionModelProviderPort provider) {
        Objects.requireNonNull(request, "request");
        Objects.requireNonNull(provider, "provider");
        ModelCallReceipt existing = billing.beginModelCall(request);
        if (existing.status() != ModelCallStatus.CREATED) return existing;
        // This durable transition must commit before any network side effect.
        // Concurrent/replayed callers cannot both claim a CREATED row.
        billing.claimProviderDispatch(request.tenantId(), existing.modelCallId());
        ProductionModelProviderPort.ProviderResult result = provider.execute(request);
        return apply(request.tenantId(), existing.modelCallId(), existing, result);
    }

    public ModelCallReceipt reconcile(UUID tenantId, UUID modelCallId, String providerRequestId, ProductionModelProviderPort provider) {
        ProductionRuntimeModels.require(tenantId, "tenantId");
        ProductionRuntimeModels.require(modelCallId, "modelCallId");
        ProductionRuntimeModels.requireText(providerRequestId, "providerRequestId", 500);
        Objects.requireNonNull(provider, "provider");
        ProductionModelProviderPort.ProviderResult result = provider.reconcile(providerRequestId);
        return apply(tenantId, modelCallId, new ModelCallReceipt(modelCallId, ModelCallStatus.UNKNOWN, providerRequestId, null), result);
    }

    public ModelCallReceipt reconcile(
            ModelCallRequest originalRequest,
            UUID modelCallId,
            String providerRequestId,
            ProductionModelProviderPort provider
    ) {
        Objects.requireNonNull(originalRequest, "originalRequest");
        ProductionRuntimeModels.require(modelCallId, "modelCallId");
        ProductionRuntimeModels.requireText(providerRequestId, "providerRequestId", 500);
        Objects.requireNonNull(provider, "provider");
        var reconciliation = new ProductionModelProviderPort.ProviderReconciliationRequest(
                originalRequest, modelCallId, providerRequestId);
        ProductionModelProviderPort.ProviderResult result = provider.reconcile(reconciliation);
        return apply(originalRequest.tenantId(), modelCallId,
                new ModelCallReceipt(modelCallId, ModelCallStatus.UNKNOWN, providerRequestId, null), result);
    }

    private ModelCallReceipt apply(UUID tenantId, UUID modelCallId, ModelCallReceipt prior, ProductionModelProviderPort.ProviderResult result) {
        return switch (result.status()) {
            case ACCEPTED -> {
                billing.markProviderAccepted(tenantId, modelCallId, result.providerRequestId());
                yield new ModelCallReceipt(modelCallId, ModelCallStatus.PROVIDER_ACCEPTED, result.providerRequestId(), null);
            }
            case COMPLETE -> {
                billing.completeModelCall(tenantId, modelCallId, result.providerRequestId(), result.responseArtifactId());
                yield new ModelCallReceipt(modelCallId, ModelCallStatus.COMPLETE, result.providerRequestId(), result.responseArtifactId().toString());
            }
            case REJECTED -> {
                billing.markProviderFailed(tenantId, modelCallId, result.providerStatus());
                yield new ModelCallReceipt(modelCallId, ModelCallStatus.FAILED, null, null);
            }
            case UNKNOWN -> {
                String providerRequestId = result.providerRequestId() == null
                        ? prior.providerRequestId() : result.providerRequestId();
                billing.markProviderUnknown(
                        tenantId, modelCallId, providerRequestId, result.providerStatus());
                yield new ModelCallReceipt(
                        modelCallId, ModelCallStatus.UNKNOWN, providerRequestId, null);
            }
        };
    }
}
