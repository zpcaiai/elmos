package io.elmos.productionruntime;

import java.util.Objects;
import java.util.UUID;

/** Replays durable final-usage requests after a coordinator or billing restart. */
public final class ProductionRuntimeSettlementReconciler {
    private final ProductionRuntimeStore runtime;
    private final ProductionBillingPort billing;

    public ProductionRuntimeSettlementReconciler(ProductionRuntimeStore runtime, ProductionBillingPort billing) {
        this.runtime = Objects.requireNonNull(runtime, "runtime");
        this.billing = Objects.requireNonNull(billing, "billing");
    }

    public ReconciliationReport reconcile(UUID tenantId, int limit) {
        int inspected = 0;
        for (var request : runtime.pendingSettlementRequests(tenantId, limit)) {
            inspected++;
            billing.settle(request.usage());
            runtime.markSettlementSettled(tenantId, request.workItemId());
        }
        return new ReconciliationReport(inspected);
    }

    public record ReconciliationReport(int inspected) {}
}
