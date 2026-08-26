package io.elmos.workflow;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Deterministic benchmark model for the workload-aware scheduler.
 *
 * <p>This class evaluates a bounded ready-set using the repository policy. It
 * does not create workers, call Temporal, emit telemetry, or claim that a
 * fairness/load campaign ran. The returned report is therefore a reproducible
 * local planning result with an explicit {@code NOT_RUN} runtime status.</p>
 */
public final class TaskFinopsFairnessBenchmark {
    public static final String RUNTIME_EVIDENCE = "NOT_RUN";

    public enum RuntimeStatus {
        NOT_RUN
    }

    public record BenchmarkRequest(
            List<TaskFinopsPolicy.QueueCandidate> candidates,
            int dispatchLimit,
            int maxDispatchesPerTenant,
            int maxResourceUnitsPerDispatch,
            Instant asOf
    ) {
        public BenchmarkRequest {
            candidates = List.copyOf(Objects.requireNonNull(candidates, "candidates"));
            if (candidates.isEmpty() || dispatchLimit < 1
                    || maxDispatchesPerTenant < 1
                    || maxResourceUnitsPerDispatch < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_BENCHMARK_REQUEST_INVALID");
            }
            Objects.requireNonNull(asOf, "asOf");
        }
    }

    public record BenchmarkReport(
            int requestedDispatches,
            List<String> dispatchOrder,
            Map<String, Integer> dispatchesByTenant,
            int totalResourceUnits,
            BigDecimal maxTenantShare,
            boolean starvationFree,
            boolean noisyNeighborBounded,
            RuntimeStatus runtimeStatus
    ) {
        public BenchmarkReport {
            if (requestedDispatches < 1 || dispatchOrder.isEmpty()
                    || totalResourceUnits < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_BENCHMARK_REPORT_INVALID");
            }
            dispatchOrder = List.copyOf(dispatchOrder);
            dispatchesByTenant = Map.copyOf(dispatchesByTenant);
            maxTenantShare = Objects.requireNonNull(maxTenantShare, "maxTenantShare")
                    .setScale(9, RoundingMode.HALF_EVEN);
            Objects.requireNonNull(runtimeStatus, "runtimeStatus");
        }
    }

    private TaskFinopsFairnessBenchmark() {}

    /**
     * Evaluates a bounded local model. A tenant is never dispatched more than
     * the request cap and every eligible tenant represented in the ready set
     * must receive a dispatch before the report can be starvation-free.
     */
    public static BenchmarkReport evaluate(BenchmarkRequest request) {
        Objects.requireNonNull(request, "request");
        List<TaskFinopsPolicy.QueueCandidate> remaining =
                new ArrayList<>(request.candidates());
        List<String> order = new ArrayList<>();
        Map<String, Integer> byTenant = new LinkedHashMap<>();
        int totalUnits = 0;
        while (!remaining.isEmpty() && order.size() < request.dispatchLimit()) {
            List<TaskFinopsPolicy.QueueCandidate> ordered =
                    WorkloadAwareScheduler.order(remaining, request.asOf());
            TaskFinopsPolicy.QueueCandidate selected = null;
            for (TaskFinopsPolicy.QueueCandidate candidate : ordered) {
                int tenantDispatches = byTenant.getOrDefault(candidate.tenantId(), 0);
                if (tenantDispatches < request.maxDispatchesPerTenant()
                        && candidate.resourceUnits()
                        <= request.maxResourceUnitsPerDispatch()) {
                    selected = candidate;
                    break;
                }
            }
            if (selected == null) {
                break;
            }
            remaining.remove(selected);
            order.add(selected.taskId());
            byTenant.merge(selected.tenantId(), 1, Integer::sum);
            totalUnits = Math.addExact(totalUnits, selected.resourceUnits());
        }
        if (order.isEmpty()) {
            throw new IllegalStateException("ELMOS_MTF_BENCHMARK_NO_DISPATCHABLE_TASK");
        }
        int maxDispatches = byTenant.values().stream().mapToInt(Integer::intValue).max()
                .orElseThrow();
        BigDecimal maxShare = BigDecimal.valueOf(maxDispatches)
                .divide(BigDecimal.valueOf(order.size()), 9, RoundingMode.HALF_EVEN);
        boolean allTenantsServed = request.candidates().stream()
                .map(TaskFinopsPolicy.QueueCandidate::tenantId)
                .distinct()
                .allMatch(byTenant::containsKey);
        boolean bounded = byTenant.values().stream()
                .allMatch(value -> value <= request.maxDispatchesPerTenant());
        return new BenchmarkReport(
                request.dispatchLimit(), order, byTenant, totalUnits, maxShare,
                allTenantsServed, bounded, RuntimeStatus.NOT_RUN);
    }
}
