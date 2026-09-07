package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeCoordinator.DispatchRequest;
import io.elmos.productionruntime.ProductionRuntimeCoordinator.WorkerGateway;

import java.time.Clock;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/** Executes one bounded fair-scheduler pass through the durable dispatch saga. */
public final class ProductionRuntimeSchedulingService implements AutoCloseable {
    private final ProductionRuntimeScheduler scheduler;
    private final ProductionRuntimeCoordinator coordinator;
    private final Clock clock;
    private final Duration reservationTtl;
    private final Duration leaseDuration;
    private final int dispatchParallelism;
    private final ThreadPoolExecutor dispatchExecutor;

    public ProductionRuntimeSchedulingService(
            ProductionRuntimeScheduler scheduler,
            ProductionRuntimeCoordinator coordinator,
            Clock clock,
            Duration reservationTtl,
            Duration leaseDuration
    ) {
        this(scheduler, coordinator, clock, reservationTtl, leaseDuration, 1);
    }

    public ProductionRuntimeSchedulingService(
            ProductionRuntimeScheduler scheduler,
            ProductionRuntimeCoordinator coordinator,
            Clock clock,
            Duration reservationTtl,
            Duration leaseDuration,
            int dispatchParallelism
    ) {
        this.scheduler = Objects.requireNonNull(scheduler, "scheduler");
        this.coordinator = Objects.requireNonNull(coordinator, "coordinator");
        this.clock = Objects.requireNonNull(clock, "clock");
        if (reservationTtl == null || reservationTtl.compareTo(Duration.ofSeconds(30)) < 0
                || reservationTtl.compareTo(Duration.ofHours(24)) > 0) {
            throw new IllegalArgumentException("reservationTtl must be within [30s, 24h]");
        }
        if (leaseDuration == null || leaseDuration.compareTo(Duration.ofSeconds(5)) < 0
                || leaseDuration.compareTo(Duration.ofHours(1)) > 0) {
            throw new IllegalArgumentException("leaseDuration must be within [5s, 1h]");
        }
        if (dispatchParallelism < 1 || dispatchParallelism > 64) {
            throw new IllegalArgumentException("dispatchParallelism must be within [1, 64]");
        }
        this.reservationTtl = reservationTtl;
        this.leaseDuration = leaseDuration;
        this.dispatchParallelism = dispatchParallelism;
        AtomicInteger threadSequence = new AtomicInteger();
        this.dispatchExecutor = new ThreadPoolExecutor(
                dispatchParallelism,
                dispatchParallelism,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(dispatchParallelism),
                runnable -> {
                    Thread thread = new Thread(
                            runnable,
                            "production-dispatch-" + threadSequence.incrementAndGet());
                    thread.setDaemon(true);
                    return thread;
                },
                new ThreadPoolExecutor.AbortPolicy());
        this.dispatchExecutor.prestartAllCoreThreads();
    }

    public SchedulingReport schedule(int limit, WorkerGateway gateway) {
        Objects.requireNonNull(gateway, "gateway");
        int inspected = 0;
        int acknowledged = 0;
        int waitingForCredit = 0;
        int unknown = 0;
        int blocked = 0;
        int conflicted = 0;
        List<String> blockerCodes = new ArrayList<>();
        List<ProductionRuntimeModels.ReadyWorkItem> dispatchable = new ArrayList<>();
        for (var item : scheduler.fairFrontier(limit)) {
            inspected++;
            if (item.walletId() == null) {
                blocked++;
                blockerCodes.add("SCHEDULER_WALLET_MISSING_OR_AMBIGUOUS:" + item.workItemId());
                continue;
            }
            if (item.workerId() == null) {
                blocked++;
                blockerCodes.add("SCHEDULER_COMPATIBLE_WORKER_UNAVAILABLE:" + item.workItemId());
                continue;
            }
            dispatchable.add(item);
        }
        for (int offset = 0; offset < dispatchable.size(); offset += dispatchParallelism) {
            int end = Math.min(dispatchable.size(), offset + dispatchParallelism);
            List<Future<DispatchResult>> wave = new ArrayList<>(end - offset);
            for (int index = offset; index < end; index++) {
                var item = dispatchable.get(index);
                wave.add(dispatchExecutor.submit(() -> dispatchOne(item, gateway)));
            }
            for (Future<DispatchResult> future : wave) {
                DispatchResult result;
                try {
                    result = future.get();
                } catch (InterruptedException ex) {
                    wave.forEach(pending -> pending.cancel(true));
                    Thread.currentThread().interrupt();
                    throw new ProductionRuntimeException(
                            "SCHEDULER_DISPATCH_INTERRUPTED",
                            "scheduler dispatch pass was interrupted", ex);
                } catch (ExecutionException ex) {
                    wave.forEach(pending -> pending.cancel(true));
                    Throwable cause = ex.getCause();
                    if (cause instanceof RuntimeException runtime) throw runtime;
                    throw new ProductionRuntimeException(
                            "SCHEDULER_DISPATCH_FAILED",
                            "scheduler dispatch task failed", cause);
                }
                acknowledged += result.acknowledged();
                waitingForCredit += result.waitingForCredit();
                unknown += result.unknown();
                blocked += result.blocked();
                conflicted += result.conflicted();
                if (result.blockerCode() != null) {
                    blockerCodes.add(result.blockerCode());
                }
            }
        }
        return new SchedulingReport(
                inspected, acknowledged, waitingForCredit, unknown, blocked,
                conflicted, List.copyOf(blockerCodes));
    }

    private DispatchResult dispatchOne(
            ProductionRuntimeModels.ReadyWorkItem item,
            WorkerGateway gateway
    ) {
        String generation = item.workItemId() + ":" + item.retryCount();
        try {
            var result = coordinator.dispatch(new DispatchRequest(
                    item.tenantId(), item.projectId(), item.jobId(), item.workItemId(),
                    item.walletId(), item.workerId(), item.estimatedCredits(),
                    clock.instant().plus(reservationTtl), leaseDuration,
                    "reserve:v1:" + generation, "dispatch:v1:" + generation,
                    Map.of(
                            "accountId", item.accountId().toString(),
                            "jobId", item.jobId().toString(),
                            "stageId", item.stageId().toString(),
                            "jobType", item.jobType(),
                            "workType", item.workType(),
                            "resourceKey", item.resourceKey(),
                            "retryCount", item.retryCount()
                    )), gateway);
            return switch (result.status()) {
                case ACKED, ALREADY_COMPLETED -> new DispatchResult(1, 0, 0, 0, 0, null);
                case WAITING_FOR_CREDIT -> new DispatchResult(0, 1, 0, 0, 0, null);
                case PROVIDER_OR_WORKER_OUTCOME_UNKNOWN -> new DispatchResult(0, 0, 1, 0, 0, null);
                case RELEASED_AFTER_REJECTION -> new DispatchResult(0, 0, 0, 1, 0, null);
            };
        } catch (ProductionRuntimeException ex) {
            if (ex.code().startsWith("WORK_ITEM_")
                    || ex.code().startsWith("DISPATCH_INTENT_")) {
                // Another scheduler replica won the durable transition.
                return new DispatchResult(0, 0, 0, 0, 1, null);
            }
            if (ex.code().startsWith("ADMISSION_")
                    || ex.code().startsWith("WORKER_CAPACITY_")
                    || ex.code().equals("WORKER_NOT_ACTIVE")) {
                return new DispatchResult(
                        0, 0, 0, 1, 0,
                        ex.code() + ":" + item.workItemId());
            }
            throw ex;
        }
    }

    @Override
    public void close() {
        dispatchExecutor.shutdownNow();
    }

    private record DispatchResult(
            int acknowledged,
            int waitingForCredit,
            int unknown,
            int blocked,
            int conflicted,
            String blockerCode
    ) {}

    public record SchedulingReport(
            int inspected,
            int acknowledged,
            int waitingForCredit,
            int unknown,
            int blocked,
            int conflicted,
            List<String> blockerCodes
    ) {}
}
