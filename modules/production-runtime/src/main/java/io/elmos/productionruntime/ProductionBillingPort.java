package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.FinalUsage;
import io.elmos.productionruntime.ProductionRuntimeModels.MeterSnapshot;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ReservationResult;
import io.elmos.productionruntime.ProductionRuntimeModels.ReserveRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.TopUpRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.TopUpResult;

import java.util.UUID;
import java.util.List;

/** Billing-owned boundary. Runtime code cannot mutate wallet or accounting tables directly. */
public interface ProductionBillingPort {
    ReservationResult reserve(ReserveRequest request);
    void release(UUID tenantId, UUID reservationId, String reason);
    void settle(FinalUsage usage);
    MeterSnapshot recordMeter(MeterSnapshot meter);
    ModelCallReceipt beginModelCall(ProductionRuntimeModels.ModelCallRequest request);
    /**
     * Atomically moves one newly-created call into the fail-closed pre-send
     * state. Exactly one caller may obtain this claim; a crash after the claim
     * leaves UNKNOWN and can never turn into a blind second provider create.
     */
    void claimProviderDispatch(UUID tenantId, UUID modelCallId);
    void markProviderAccepted(UUID tenantId, UUID modelCallId, String providerRequestId);
    void markProviderUnknown(UUID tenantId, UUID modelCallId, String providerStatus);
    default void markProviderUnknown(
            UUID tenantId,
            UUID modelCallId,
            String providerRequestId,
            String providerStatus
    ) {
        markProviderUnknown(tenantId, modelCallId, providerStatus);
    }
    void completeModelCall(UUID tenantId, UUID modelCallId, String providerRequestId, UUID responseArtifactId);
    void markProviderFailed(UUID tenantId, UUID modelCallId, String providerStatus);
    TopUpResult applyVerifiedTopUp(TopUpRequest request);
    int expireReservations(int limit);
    List<ProductionRuntimeModels.ModelCallRecoveryCandidate> uncertainModelCalls(int limit);
}
