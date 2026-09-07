package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallRequest;

import java.util.UUID;

/** Stores provider response bytes before a model call can become COMPLETE. */
public interface ProductionProviderArtifactPort {
    UUID store(
            ModelCallRequest request,
            String providerRequestId,
            byte[] responseBytes,
            String mediaType
    );
}
