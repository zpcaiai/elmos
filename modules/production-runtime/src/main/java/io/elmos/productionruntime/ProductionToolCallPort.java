package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallRequest;

import java.util.UUID;

/** Distinct tool-call idempotency boundary; tool calls are never collapsed into model calls. */
public interface ProductionToolCallPort {
    ToolCallReceipt begin(ToolCallRequest request);
    void markProviderAccepted(UUID tenantId, UUID toolCallId, String providerRequestId);
    void markProviderUnknown(UUID tenantId, UUID toolCallId, String providerStatus);
    void complete(UUID tenantId, UUID toolCallId, UUID responseArtifactId);
}
