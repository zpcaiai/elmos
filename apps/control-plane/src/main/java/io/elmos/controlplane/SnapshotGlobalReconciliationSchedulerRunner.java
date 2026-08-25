package io.elmos.controlplane;

import io.elmos.snapshot.SnapshotGlobalReconciliationScheduler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;

/** Optional global scheduler; disabled until an explicit stable worker identity is configured. */
@Component
@ConditionalOnProperty(
        name = {
                "elmos.github.app.enabled",
                "elmos.snapshot.reconciliation.scheduler-enabled"
        },
        havingValue = "true")
final class SnapshotGlobalReconciliationSchedulerRunner {
    private static final Logger LOG = LoggerFactory.getLogger(
            SnapshotGlobalReconciliationSchedulerRunner.class);

    private final SnapshotGlobalReconciliationScheduler scheduler;
    private final String workerId;
    private final int tenantLimit;
    private final int perTenantLimit;
    private final Duration leaseDuration;
    private final Duration failureRetry;

    SnapshotGlobalReconciliationSchedulerRunner(
            SnapshotGlobalReconciliationScheduler scheduler,
            @Value("${elmos.snapshot.reconciliation.worker-id:}") String workerId,
            @Value("${elmos.snapshot.reconciliation.tenant-limit:16}") int tenantLimit,
            @Value("${elmos.snapshot.reconciliation.per-tenant-limit:100}")
            int perTenantLimit,
            @Value("${elmos.snapshot.reconciliation.scheduler-lease:PT2M}")
            String leaseDuration,
            @Value("${elmos.snapshot.reconciliation.failure-retry:PT1M}")
            String failureRetry
    ) {
        this.scheduler = scheduler;
        if (workerId == null
                || !workerId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
            throw new IllegalStateException(
                    "global snapshot reconciliation worker id is required and must be stable");
        }
        if (tenantLimit < 1 || tenantLimit > 64) {
            throw new IllegalStateException(
                    "snapshot reconciliation tenant limit must be between 1 and 64");
        }
        if (perTenantLimit < 1 || perTenantLimit > 1_000) {
            throw new IllegalStateException(
                    "snapshot reconciliation per-tenant limit must be between 1 and 1000");
        }
        this.workerId = workerId;
        this.tenantLimit = tenantLimit;
        this.perTenantLimit = perTenantLimit;
        this.leaseDuration = requireWholeSeconds(
                parseDuration(leaseDuration, "scheduler lease"),
                "scheduler lease", 15, 900);
        this.failureRetry = requireWholeSeconds(
                parseDuration(failureRetry, "failure retry"),
                "failure retry", 1, 86_400);
    }

    @Scheduled(
            fixedDelayString =
                    "${elmos.snapshot.reconciliation.scheduler-interval-ms:30000}")
    void reconcile() {
        SnapshotGlobalReconciliationScheduler.RunReport report = scheduler.runOnce(
                workerId, tenantLimit, perTenantLimit, leaseDuration, failureRetry);
        if (!report.failures().isEmpty()) {
            LOG.warn(
                    "Snapshot reconciliation batch had failures: claimed={}, completed={}, remaining={}, failures={}",
                    report.claimed(), report.completed(), report.remaining(), report.failures());
        } else if (report.claimed() > 0) {
            LOG.info(
                    "Snapshot reconciliation batch completed: claimed={}, completed={}, remaining={}",
                    report.claimed(), report.completed(), report.remaining());
        }
    }

    private static Duration parseDuration(String raw, String field) {
        try {
            return Duration.parse(raw);
        } catch (RuntimeException invalid) {
            throw new IllegalStateException(
                    "snapshot reconciliation " + field + " is invalid", invalid);
        }
    }

    private static Duration requireWholeSeconds(
            Duration duration,
            String field,
            long minimum,
            long maximum
    ) {
        if (duration.getNano() != 0
                || duration.toSeconds() < minimum
                || duration.toSeconds() > maximum) {
            throw new IllegalStateException(
                    "snapshot reconciliation " + field + " is outside the allowed range");
        }
        return duration;
    }
}
