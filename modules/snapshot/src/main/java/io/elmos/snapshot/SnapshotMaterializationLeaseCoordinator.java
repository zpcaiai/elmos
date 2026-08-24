package io.elmos.snapshot;

import java.time.Duration;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;

/** Acquires, heartbeats, fences, and finally releases a materialization lease. */
public final class SnapshotMaterializationLeaseCoordinator {
    private final SnapshotMaterializationLease.Store leases;
    private final ScheduledExecutorService heartbeatExecutor;
    private final String holderId;
    private final Duration leaseDuration;
    private final Duration heartbeatInterval;

    public SnapshotMaterializationLeaseCoordinator(
            SnapshotMaterializationLease.Store leases,
            ScheduledExecutorService heartbeatExecutor,
            String holderId,
            Duration leaseDuration,
            Duration heartbeatInterval
    ) {
        this.leases = Objects.requireNonNull(leases, "leases");
        this.heartbeatExecutor = Objects.requireNonNull(
                heartbeatExecutor, "heartbeatExecutor");
        // Reuse the record's exact validation without manufacturing a real lease.
        if (holderId == null
                || !holderId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
            throw new IllegalArgumentException("materialization holderId is invalid");
        }
        this.holderId = holderId;
        this.leaseDuration = requireDuration(
                leaseDuration, "leaseDuration", Duration.ofSeconds(15), Duration.ofHours(1));
        this.heartbeatInterval = requireDuration(
                heartbeatInterval, "heartbeatInterval", Duration.ofMillis(10),
                leaseDuration.dividedBy(2));
    }

    public <T> T withLease(
            SnapshotModel.RepositorySnapshot snapshot,
            Supplier<T> operation
    ) {
        Objects.requireNonNull(snapshot, "snapshot");
        Objects.requireNonNull(operation, "operation");
        if (snapshot.status() != SnapshotModel.Status.AVAILABLE) {
            throw new SecurityException("only an available snapshot may obtain a materialization lease");
        }
        SnapshotPorts.ArtifactResourceContext resource =
                new SnapshotPorts.ArtifactResourceContext(
                        snapshot.organizationId(), snapshot.repositoryId());
        SnapshotMaterializationLease acquired = Objects.requireNonNull(
                leases.acquire(resource, snapshot.snapshotId(),
                        "snapshot-materialize-" + UUID.randomUUID(), holderId, leaseDuration),
                "materialization lease store returned null");
        AtomicReference<SnapshotMaterializationLease> current = new AtomicReference<>(acquired);
        AtomicReference<RuntimeException> heartbeatFailure = new AtomicReference<>();
        ScheduledFuture<?> heartbeat = null;
        RuntimeException operationFailure = null;
        boolean exactLeaseIdentity = false;
        try {
            requireExactSnapshot(snapshot, current.get());
            exactLeaseIdentity = true;
            heartbeat = heartbeatExecutor.scheduleWithFixedDelay(
                    () -> renew(current, heartbeatFailure),
                    heartbeatInterval.toMillis(), heartbeatInterval.toMillis(),
                    TimeUnit.MILLISECONDS);
            T result = operation.get();
            RuntimeException failedHeartbeat = heartbeatFailure.get();
            if (failedHeartbeat != null) {
                throw new IllegalStateException(
                        "snapshot materialization lease heartbeat failed", failedHeartbeat);
            }
            SnapshotMaterializationLease active = leases.requireActive(current.get());
            if (!current.get().sameFence(active)) {
                throw new SecurityException("materialization lease changed fencing identity");
            }
            requireExactSnapshot(snapshot, active);
            return result;
        } catch (RuntimeException failure) {
            operationFailure = failure;
            throw failure;
        } finally {
            if (heartbeat != null) heartbeat.cancel(false);
            // Never mutate a resource named only by a conflicting adapter response. A corrupt
            // foreign lease is allowed to expire and is surfaced as a security failure.
            if (exactLeaseIdentity) {
                try {
                    leases.release(current.get());
                } catch (RuntimeException releaseFailure) {
                    if (operationFailure != null) {
                        operationFailure.addSuppressed(releaseFailure);
                    } else {
                        throw releaseFailure;
                    }
                }
            }
        }
    }

    private void renew(
            AtomicReference<SnapshotMaterializationLease> current,
            AtomicReference<RuntimeException> failure
    ) {
        if (failure.get() != null) return;
        try {
            SnapshotMaterializationLease previous = current.get();
            SnapshotMaterializationLease renewed = leases.renew(previous, leaseDuration);
            if (!previous.sameFence(renewed)) {
                throw new SecurityException("lease renewal changed fencing identity");
            }
            current.set(renewed);
        } catch (RuntimeException error) {
            failure.compareAndSet(null, error);
        }
    }

    private static void requireExactSnapshot(
            SnapshotModel.RepositorySnapshot snapshot,
            SnapshotMaterializationLease lease
    ) {
        if (!snapshot.organizationId().equals(lease.organizationId())
                || !snapshot.repositoryId().equals(lease.repositoryId())
                || !snapshot.snapshotId().equals(lease.snapshotId())) {
            throw new SecurityException("materialization lease belongs to another snapshot");
        }
    }

    private static Duration requireDuration(
            Duration value,
            String field,
            Duration minimum,
            Duration maximum
    ) {
        Objects.requireNonNull(value, field);
        if (value.compareTo(minimum) < 0 || value.compareTo(maximum) > 0) {
            throw new IllegalArgumentException(field + " is outside the allowed range");
        }
        return value;
    }
}
