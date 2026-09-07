package io.elmos.snapshot;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

/** Runs a bounded, crash-reclaimable batch across tenant reconciliation queues. */
public final class SnapshotGlobalReconciliationScheduler {
    @FunctionalInterface
    public interface TenantReconciler {
        SnapshotProvisionalRootReconciler.ReconciliationReport reconcile(
                String organizationId, int limit);
    }

    public record TenantFailure(String organizationId, String code) { }

    public record RunReport(
            int claimed,
            int completed,
            int remaining,
            List<TenantFailure> failures
    ) {
        public RunReport {
            failures = List.copyOf(failures);
        }
    }

    private final SnapshotReconciliationWorkQueue work;
    private final TenantReconciler reconciler;

    public SnapshotGlobalReconciliationScheduler(
            SnapshotReconciliationWorkQueue work,
            SnapshotProvisionalRootReconciler reconciler
    ) {
        this(work, reconciler::reconcile);
    }

    public SnapshotGlobalReconciliationScheduler(
            SnapshotReconciliationWorkQueue work,
            TenantReconciler reconciler
    ) {
        this.work = Objects.requireNonNull(work, "work");
        this.reconciler = Objects.requireNonNull(reconciler, "reconciler");
    }

    public RunReport runOnce(
            String workerId,
            int tenantLimit,
            int perTenantLimit,
            Duration leaseDuration,
            Duration failureRetryDelay
    ) {
        if (tenantLimit < 1 || tenantLimit > 64) {
            throw new IllegalArgumentException("tenantLimit must be between 1 and 64");
        }
        if (perTenantLimit < 1 || perTenantLimit > 1_000) {
            throw new IllegalArgumentException("perTenantLimit must be between 1 and 1000");
        }
        requireDuration(leaseDuration, "leaseDuration", 15, 900);
        requireDuration(failureRetryDelay, "failureRetryDelay", 1, 86_400);
        List<SnapshotReconciliationWorkQueue.WorkLease> claimed =
                Objects.requireNonNull(
                        work.claim(workerId, tenantLimit, leaseDuration),
                        "work queue returned null claims");
        if (claimed.size() > tenantLimit) {
            throw new IllegalStateException("work queue exceeded the requested tenant bound");
        }
        Set<String> claimedOrganizations = new HashSet<>();
        for (SnapshotReconciliationWorkQueue.WorkLease lease : claimed) {
            if (!workerId.equals(lease.workerId())) {
                throw new SecurityException("work queue returned another worker's lease");
            }
            if (!claimedOrganizations.add(lease.organizationId())) {
                throw new SecurityException("work queue returned duplicate tenant work");
            }
        }
        int completed = 0;
        int remaining = 0;
        List<TenantFailure> failures = new ArrayList<>();
        for (SnapshotReconciliationWorkQueue.WorkLease lease : claimed) {
            RuntimeException reconciliationFailure = null;
            boolean successful = false;
            try {
                SnapshotProvisionalRootReconciler.ReconciliationReport report =
                        reconciler.reconcile(lease.organizationId(), perTenantLimit);
                successful = report.failed() == 0;
                if (!successful) {
                    failures.add(new TenantFailure(
                            lease.organizationId(), "RECONCILIATION_ITEM_FAILED"));
                }
            } catch (RuntimeException failure) {
                reconciliationFailure = failure;
                failures.add(new TenantFailure(
                        lease.organizationId(), failure.getClass().getSimpleName()));
            }
            try {
                boolean workRemains = work.complete(
                        lease, successful,
                        successful ? Duration.ZERO : failureRetryDelay);
                completed++;
                if (workRemains) remaining++;
            } catch (RuntimeException completionFailure) {
                if (reconciliationFailure != null) {
                    reconciliationFailure.addSuppressed(completionFailure);
                }
                failures.add(new TenantFailure(
                        lease.organizationId(), "WORK_LEASE_COMPLETION_FAILED"));
            }
        }
        return new RunReport(claimed.size(), completed, remaining, failures);
    }

    private static void requireDuration(
            Duration value, String field, long minimumSeconds, long maximumSeconds
    ) {
        Objects.requireNonNull(value, field);
        if (value.getNano() != 0
                || value.toSeconds() < minimumSeconds
                || value.toSeconds() > maximumSeconds) {
            throw new IllegalArgumentException(field + " is outside the allowed range");
        }
    }
}
