package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallStatus;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * Reconciles provider-accepted and uncertain model calls without issuing a
 * second provider create request.
 */
public final class ProductionModelCallRecoveryService {
    private final ProductionBillingPort billing;
    private final ProductionModelCallExecutor executor;
    private final ProductionModelProviderRegistry providers;
    private final int maximumAttempts;

    public ProductionModelCallRecoveryService(
            ProductionBillingPort billing,
            ProductionModelCallExecutor executor,
            ProductionModelProviderRegistry providers,
            int maximumAttempts
    ) {
        this.billing = Objects.requireNonNull(billing, "billing");
        this.executor = Objects.requireNonNull(executor, "executor");
        this.providers = Objects.requireNonNull(providers, "providers");
        if (maximumAttempts < 1 || maximumAttempts > 100) {
            throw new IllegalArgumentException("maximumAttempts must be between 1 and 100");
        }
        this.maximumAttempts = maximumAttempts;
    }

    public RecoveryReport recover(int limit) {
        int inspected = 0;
        int completed = 0;
        int failed = 0;
        int pending = 0;
        List<String> blockers = new ArrayList<>();
        for (var candidate : billing.uncertainModelCalls(limit)) {
            inspected++;
            if (candidate.reconcileAttempts() >= maximumAttempts) {
                billing.markProviderUnknown(
                        candidate.request().tenantId(), candidate.modelCallId(),
                        candidate.providerRequestId(),
                        "MODEL_CALL_RECONCILIATION_ATTEMPTS_EXHAUSTED");
                pending++;
                blockers.add("MODEL_CALL_RECONCILIATION_ATTEMPTS_EXHAUSTED:" + candidate.modelCallId());
                continue;
            }
            if (candidate.providerRequestId() == null || candidate.providerRequestId().isBlank()) {
                billing.markProviderUnknown(
                        candidate.request().tenantId(), candidate.modelCallId(),
                        null, "MODEL_CALL_PROVIDER_ID_UNKNOWN");
                pending++;
                blockers.add("MODEL_CALL_PROVIDER_ID_UNKNOWN:" + candidate.modelCallId());
                continue;
            }
            var adapter = providers.require(
                    candidate.request().provider(), candidate.request().model());
            var receipt = executor.reconcile(
                    candidate.request(), candidate.modelCallId(),
                    candidate.providerRequestId(), adapter);
            if (receipt.status() == ModelCallStatus.COMPLETE) completed++;
            else if (receipt.status() == ModelCallStatus.FAILED) failed++;
            else pending++;
        }
        return new RecoveryReport(
                inspected, completed, failed, pending, List.copyOf(blockers));
    }

    public record RecoveryReport(
            int inspected,
            int completed,
            int failed,
            int pending,
            List<String> blockers
    ) {}
}
