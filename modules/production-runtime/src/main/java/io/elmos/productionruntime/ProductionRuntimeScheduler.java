package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.DispatchIntent;
import io.elmos.productionruntime.ProductionRuntimeModels.ProgressSnapshot;
import io.elmos.productionruntime.ProductionRuntimeModels.ReadyWorkItem;

import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

/** Bounded scheduler/recovery facade; all durable decisions remain in PostgreSQL. */
public final class ProductionRuntimeScheduler {
    private final ProductionRuntimeStore store;

    public ProductionRuntimeScheduler(ProductionRuntimeStore store) {
        this.store = Objects.requireNonNull(store, "store");
    }

    public List<ReadyWorkItem> fairFrontier(int limit) { return store.selectFairReady(limit); }

    public List<DispatchIntent> recoveryFrontier(int limit) { return store.recoveryCandidates(limit); }

    public int expireLeases(Duration gracePeriod) { return store.expireLeases(gracePeriod); }

    public int resumeAfterTopUp(UUID tenantId, int limit) { return store.resumeCreditWaiting(tenantId, limit); }

    public ProgressSnapshot rebuildProgress(UUID tenantId, UUID jobId) { return store.rebuildProgress(tenantId, jobId); }
}
