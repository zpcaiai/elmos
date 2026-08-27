package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.FinalUsage;
import io.elmos.productionruntime.ProductionRuntimeModels.MeterSnapshot;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ReservationResult;
import io.elmos.productionruntime.ProductionRuntimeModels.ReserveRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.TopUpRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.TopUpResult;

import java.util.UUID;

/** Billing-owned boundary. Runtime code cannot mutate wallet or accounting tables directly. */
public interface ProductionBillingPort {
    ReservationResult reserve(ReserveRequest request);
    void release(UUID tenantId, UUID reservationId, String reason);
    void settle(FinalUsage usage);
    MeterSnapshot recordMeter(MeterSnapshot meter);
    ModelCallReceipt beginModelCall(ProductionRuntimeModels.ModelCallRequest request);
    void markProviderAccepted(UUID tenantId, UUID modelCallId, String providerRequestId);
    void markProviderUnknown(UUID tenantId, UUID modelCallId, String providerStatus);
    TopUpResult applyVerifiedTopUp(TopUpRequest request);
}
