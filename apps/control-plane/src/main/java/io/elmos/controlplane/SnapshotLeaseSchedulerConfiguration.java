package io.elmos.controlplane;

import io.elmos.persistence.JdbcSnapshotMaterializationLeaseStore;
import io.elmos.persistence.JdbcSnapshotReconciliationWorkQueue;
import io.elmos.snapshot.SnapshotGlobalReconciliationScheduler;
import io.elmos.snapshot.SnapshotMaterializationLeaseCoordinator;
import io.elmos.snapshot.SnapshotProvisionalRootReconciler;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.atomic.AtomicInteger;

/** Production wiring for fenced materialization and the global reconciliation coordinator. */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "elmos.github.app.enabled", havingValue = "true")
class SnapshotLeaseSchedulerConfiguration {
    @Bean(name = "snapshotLeaseHeartbeatExecutor", destroyMethod = "shutdown")
    ScheduledExecutorService snapshotLeaseHeartbeatExecutor(
            @Value("${elmos.snapshot.materialization-lease.heartbeat-threads:2}")
            int threads
    ) {
        if (threads < 1 || threads > 16) {
            throw new IllegalStateException(
                    "snapshot materialization heartbeat threads must be between 1 and 16");
        }
        AtomicInteger sequence = new AtomicInteger();
        return Executors.newScheduledThreadPool(threads, task -> {
            Thread thread = new Thread(
                    task, "snapshot-lease-heartbeat-" + sequence.incrementAndGet());
            thread.setDaemon(true);
            return thread;
        });
    }

    @Bean
    SnapshotMaterializationLeaseCoordinator snapshotMaterializationLeaseCoordinator(
            JdbcSnapshotMaterializationLeaseStore leases,
            @Qualifier("snapshotLeaseHeartbeatExecutor")
            ScheduledExecutorService heartbeatExecutor,
            @Value("${elmos.snapshot.materialization-lease.holder-id:}") String holderId,
            @Value("${elmos.snapshot.materialization-lease.duration:PT2M}")
            String leaseDuration,
            @Value("${elmos.snapshot.materialization-lease.heartbeat-interval:PT30S}")
            String heartbeatInterval
    ) {
        if (holderId == null || holderId.isBlank()) {
            throw new IllegalStateException(
                    "snapshot materialization lease holder id is required");
        }
        return new SnapshotMaterializationLeaseCoordinator(
                leases, heartbeatExecutor, holderId,
                parseDuration(leaseDuration, "materialization lease duration"),
                parseDuration(heartbeatInterval, "materialization heartbeat interval"));
    }

    @Bean
    SnapshotGlobalReconciliationScheduler snapshotGlobalReconciliationScheduler(
            JdbcSnapshotReconciliationWorkQueue work,
            SnapshotProvisionalRootReconciler reconciler
    ) {
        return new SnapshotGlobalReconciliationScheduler(work, reconciler);
    }

    private static Duration parseDuration(String raw, String field) {
        try {
            return Duration.parse(raw);
        } catch (RuntimeException invalid) {
            throw new IllegalStateException(field + " is invalid", invalid);
        }
    }
}
