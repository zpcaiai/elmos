package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallRequest;

import java.util.Objects;
import java.util.UUID;

/**
 * Provider-neutral boundary for a real model provider adapter.
 *
 * <p>Provider SDKs, credentials, retries, and network policy belong behind
 * this interface. An adapter must make UNKNOWN explicit; callers may not
 * turn a timeout into a new provider call.</p>
 */
public interface ProductionModelProviderPort {
    ProviderResult execute(ModelCallRequest request);

    ProviderResult reconcile(String providerRequestId);

    /**
     * Context-bound reconciliation used by adapters that must persist a
     * recovered response artifact. The legacy method remains for bounded test
     * adapters, but production callers use this overload.
     */
    default ProviderResult reconcile(ProviderReconciliationRequest request) {
        Objects.requireNonNull(request, "request");
        return reconcile(request.providerRequestId());
    }

    record ProviderReconciliationRequest(
            ModelCallRequest request,
            UUID modelCallId,
            String providerRequestId
    ) {
        public ProviderReconciliationRequest {
            Objects.requireNonNull(request, "request");
            Objects.requireNonNull(modelCallId, "modelCallId");
            ProductionRuntimeModels.requireText(providerRequestId, "providerRequestId", 500);
        }
    }

    enum Status { ACCEPTED, COMPLETE, REJECTED, UNKNOWN }

    record ProviderResult(Status status, String providerRequestId, UUID responseArtifactId, String providerStatus) {
        public ProviderResult {
            Objects.requireNonNull(status, "status");
            if (providerRequestId != null
                    && !providerRequestId.matches("[A-Za-z0-9._:-]{1,500}")) {
                throw new IllegalArgumentException("providerRequestId is malformed");
            }
            if ((status == Status.ACCEPTED || status == Status.COMPLETE)
                    && providerRequestId == null) {
                throw new IllegalArgumentException("accepted or complete provider results require providerRequestId");
            }
            if (status == Status.COMPLETE && responseArtifactId == null) {
                throw new IllegalArgumentException("complete provider results require responseArtifactId");
            }
            if ((status == Status.UNKNOWN || status == Status.REJECTED) && (providerStatus == null || providerStatus.isBlank())) {
                throw new IllegalArgumentException("unknown or rejected provider results require providerStatus");
            }
        }

        public static ProviderResult accepted(String providerRequestId) {
            return new ProviderResult(Status.ACCEPTED, providerRequestId, null, null);
        }

        public static ProviderResult complete(String providerRequestId, UUID responseArtifactId) {
            return new ProviderResult(Status.COMPLETE, providerRequestId, responseArtifactId, null);
        }

        public static ProviderResult rejected(String providerStatus) {
            return new ProviderResult(Status.REJECTED, null, null, providerStatus);
        }

        public static ProviderResult unknown(String providerStatus) {
            return new ProviderResult(Status.UNKNOWN, null, null, providerStatus);
        }

        public static ProviderResult unknown(String providerRequestId, String providerStatus) {
            ProductionRuntimeModels.requireText(providerRequestId, "providerRequestId", 500);
            return new ProviderResult(Status.UNKNOWN, providerRequestId, null, providerStatus);
        }
    }
}
