package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallRequest;

import java.util.UUID;

/** Distinct tool-call idempotency boundary; tool calls are never collapsed into model calls. */
public interface ProductionToolCallPort {
    ToolCallReceipt begin(ToolCallRequest request);
    /**
     * Atomically persists the provider-send uncertainty boundary. Exactly one
     * caller may claim a newly-created call; a crash after this method must be
     * reconciled and must never result in a blind provider retry.
     */
    void claimProviderDispatch(UUID tenantId, UUID toolCallId);
    void markProviderAccepted(UUID tenantId, UUID toolCallId, String providerRequestId);
    void markProviderUnknown(UUID tenantId, UUID toolCallId, String providerStatus);
    default void markProviderUnknown(
            UUID tenantId,
            UUID toolCallId,
            String providerRequestId,
            String providerStatus
    ) {
        markProviderUnknown(tenantId, toolCallId, providerStatus);
    }
    void markProviderFailed(UUID tenantId, UUID toolCallId, String providerStatus);
    void complete(UUID tenantId, UUID toolCallId, UUID responseArtifactId);
}
