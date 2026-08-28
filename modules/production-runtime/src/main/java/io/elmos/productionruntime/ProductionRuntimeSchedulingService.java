package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeCoordinator.DispatchRequest;
import io.elmos.productionruntime.ProductionRuntimeCoordinator.WorkerGateway;

import java.time.Clock;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Executes one bounded fair-scheduler pass through the durable dispatch saga. */
public final class ProductionRuntimeSchedulingService {
    private final ProductionRuntimeScheduler scheduler;
    private final ProductionRuntimeCoordinator coordinator;
    private final Clock clock;
    private final Duration reservationTtl;
    private final Duration leaseDuration;

    public ProductionRuntimeSchedulingService(
            ProductionRuntimeScheduler scheduler,
            ProductionRuntimeCoordinator coordinator,
            Clock clock,
            Duration reservationTtl,
            Duration leaseDuration
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
        this.reservationTtl = reservationTtl;
        this.leaseDuration = leaseDuration;
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
                switch (result.status()) {
                    case ACKED, ALREADY_COMPLETED -> acknowledged++;
                    case WAITING_FOR_CREDIT -> waitingForCredit++;
                    case PROVIDER_OR_WORKER_OUTCOME_UNKNOWN -> unknown++;
                    case RELEASED_AFTER_REJECTION -> blocked++;
                }
            } catch (ProductionRuntimeException ex) {
                if (ex.code().startsWith("WORK_ITEM_")
                        || ex.code().startsWith("DISPATCH_INTENT_")) {
                    // Another scheduler replica won the durable transition.
                    conflicted++;
                } else if (ex.code().startsWith("ADMISSION_")
                        || ex.code().startsWith("WORKER_CAPACITY_")
                        || ex.code().equals("WORKER_NOT_ACTIVE")) {
                    blocked++;
                    blockerCodes.add(ex.code() + ":" + item.workItemId());
                } else {
                    throw ex;
                }
            }
        }
        return new SchedulingReport(
                inspected, acknowledged, waitingForCredit, unknown, blocked,
                conflicted, List.copyOf(blockerCodes));
    }

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
