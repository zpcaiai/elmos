package io.elmos.workflow;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * Pure, deterministic policy shared by the multi-tenant task control plane and
 * its PostgreSQL adapter.
 *
 * <p>This class deliberately contains no provider, clock, database or workflow
 * SDK calls. Those effects live behind ports; keeping the invariants pure makes
 * state, progress, scheduling and money decisions replayable in tests and by a
 * recovery worker.</p>
 */
public final class TaskFinopsPolicy {
    public static final int MAX_ACCOUNT_ROOT_TASKS = 3;
    public static final int MONEY_SCALE = 6;
    public static final RoundingMode MONEY_ROUNDING = RoundingMode.HALF_EVEN;

    public enum TaskState {
        WAITING_FOR_SLOT,
        ADMITTED,
        RUNNING,
        PAUSE_REQUESTED,
        PAUSED,
        RESUME_REQUESTED,
        UNKNOWN_RESULT,
        RECONCILING,
        SUCCEEDED,
        FAILED,
        CANCELLED
    }

    public enum WorkloadClass {
        PARSING,
        GENERATION,
        CONVERSION,
        VALIDATION,
        RENDERING,
        MODEL_GPU
    }

    public enum ErrorClass {
        TRANSIENT,
        THROTTLED,
        INVALID_INPUT,
        AUTHORIZATION,
        UNSUPPORTED,
        UNKNOWN_RESULT
    }

    public enum RecoveryDecision {
        RETRY_NODE,
        RESUME_CHECKPOINT,
        FORK_RUN,
        MANUAL_RECOVERY,
        FAIL
    }

    public record WorkloadProfile(int resourceUnits, int maxWorkerConcurrency) {
        public WorkloadProfile {
            if (resourceUnits < 1 || maxWorkerConcurrency < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_WORKLOAD_PROFILE_INVALID");
            }
        }
    }

    public record Progress(short percent, long elapsedMillis, long etaP50Millis, long etaP90Millis) {
        public Progress {
            if (percent < 0 || percent > 100 || elapsedMillis < 0
                    || etaP50Millis < 0 || etaP90Millis < etaP50Millis) {
                throw new IllegalArgumentException("ELMOS_MTF_PROGRESS_INVALID");
            }
        }
    }

    public record QueueCandidate(
            String taskId,
            String tenantId,
            int priority,
            Instant enqueuedAt,
            int resourceUnits,
            int tenantWeight,
            long tenantServiceUnits
    ) {
        public QueueCandidate {
            requireId(taskId, "TASK");
            requireId(tenantId, "TENANT");
            Objects.requireNonNull(enqueuedAt, "enqueuedAt");
            if (priority < 1 || priority > 1000 || resourceUnits < 1
                    || tenantWeight < 1 || tenantWeight > 100 || tenantServiceUnits < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_QUEUE_CANDIDATE_INVALID");
            }
        }
    }

    public record Money(String currency, BigDecimal minorUnits) {
        public Money {
            if (currency == null || !currency.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("ELMOS_MTF_CURRENCY_INVALID");
            }
            minorUnits = exact(minorUnits);
        }

        public Money add(Money other) {
            sameCurrency(this, other);
            return new Money(currency, minorUnits.add(other.minorUnits));
        }

        public Money subtract(Money other) {
            sameCurrency(this, other);
            return new Money(currency, minorUnits.subtract(other.minorUnits));
        }
    }

    public record FinancialTotals(
            Money postedCost,
            Money recognizedRevenue,
            Money collectedCash,
            Money grossProfit,
            BigDecimal grossMarginRatio,
            Instant asOf,
            boolean reconciled
    ) {
        public FinancialTotals {
            Objects.requireNonNull(asOf, "asOf");
            sameCurrency(postedCost, recognizedRevenue);
            sameCurrency(postedCost, collectedCash);
            sameCurrency(postedCost, grossProfit);
            if (grossMarginRatio != null) {
                grossMarginRatio = grossMarginRatio.setScale(9, MONEY_ROUNDING);
            }
        }
    }

    public record CheckpointIdentity(
            String inputManifestDigest,
            String repositoryRevision,
            String toolchainDigest,
            String modelDigest,
            String schemaVersion
    ) {
        public CheckpointIdentity {
            requireDigest(inputManifestDigest, "INPUT_MANIFEST");
            requireDigest(toolchainDigest, "TOOLCHAIN");
            if (modelDigest != null) requireDigest(modelDigest, "MODEL");
            requireId(repositoryRevision, "REVISION");
            requireId(schemaVersion, "SCHEMA_VERSION");
        }
    }

    private static final Map<TaskState, Set<TaskState>> TRANSITIONS = transitions();
    private static final Map<WorkloadClass, WorkloadProfile> WORKLOADS = workloads();

    private TaskFinopsPolicy() {}

    public static void requireTransition(TaskState from, TaskState to) {
        Objects.requireNonNull(from, "from");
        Objects.requireNonNull(to, "to");
        if (!TRANSITIONS.getOrDefault(from, Set.of()).contains(to)) {
            throw new IllegalStateException("ELMOS_MTF_ILLEGAL_TRANSITION_" + from + "_TO_" + to);
        }
    }

    public static boolean consumesAccountSlot(TaskState state) {
        return switch (state) {
            case ADMITTED, RUNNING, PAUSE_REQUESTED, UNKNOWN_RESULT, RECONCILING -> true;
            default -> false;
        };
    }

    public static WorkloadProfile workload(WorkloadClass workloadClass) {
        return WORKLOADS.get(Objects.requireNonNull(workloadClass, "workloadClass"));
    }

    /**
     * Orders a bounded ready set using weighted virtual service plus priority
     * aging. FIFO is the final tie breaker, so repeated calls are deterministic.
     */
    public static List<QueueCandidate> weightedFairOrder(
            List<QueueCandidate> candidates,
            Instant now
    ) {
        Objects.requireNonNull(now, "now");
        List<QueueCandidate> ordered = new ArrayList<>(List.copyOf(candidates));
        ordered.sort(Comparator
                .comparingLong((QueueCandidate candidate) -> virtualFinish(candidate, now))
                .thenComparing(QueueCandidate::enqueuedAt)
                .thenComparing(QueueCandidate::taskId));
        return List.copyOf(ordered);
    }

    private static long virtualFinish(QueueCandidate candidate, Instant now) {
        long ageSeconds = Math.max(0, Duration.between(candidate.enqueuedAt(), now).toSeconds());
        long ageCredit = Math.min(ageSeconds / 30, 10_000);
        long priorityCredit = (long) candidate.priority() * 100L;
        long normalizedService = Math.multiplyExact(
                candidate.tenantServiceUnits() + candidate.resourceUnits(), 10_000L)
                / candidate.tenantWeight();
        return normalizedService - priorityCredit - ageCredit;
    }

    public static Progress nextProgress(
            Progress previous,
            int proposedPercent,
            long elapsedMillis,
            long historicalP50Millis,
            long historicalP90Millis,
            TaskState state
    ) {
        Objects.requireNonNull(previous, "previous");
        Objects.requireNonNull(state, "state");
        int bounded = Math.max(previous.percent(), Math.min(proposedPercent, 100));
        if (state != TaskState.SUCCEEDED && bounded == 100) bounded = 99;
        long elapsed = Math.max(previous.elapsedMillis(), elapsedMillis);
        long eta50 = remaining(elapsed, historicalP50Millis, bounded);
        long eta90 = Math.max(eta50, remaining(elapsed, historicalP90Millis, bounded));
        return new Progress((short) bounded, elapsed, eta50, eta90);
    }

    private static long remaining(long elapsed, long historical, int percent) {
        if (percent >= 100) return 0;
        if (historical > 0) return Math.max(0, historical - elapsed);
        if (percent <= 0) return 0;
        BigDecimal projected = BigDecimal.valueOf(elapsed)
                .multiply(BigDecimal.valueOf(100))
                .divide(BigDecimal.valueOf(percent), 0, RoundingMode.CEILING);
        return Math.max(0, projected.longValueExact() - elapsed);
    }

    public static boolean shouldRetry(ErrorClass errorClass, int attempt, int maxAttempts) {
        if (attempt < 1 || maxAttempts < 1 || attempt > maxAttempts) {
            throw new IllegalArgumentException("ELMOS_MTF_ATTEMPT_INVALID");
        }
        if (attempt >= maxAttempts) return false;
        return errorClass == ErrorClass.TRANSIENT || errorClass == ErrorClass.THROTTLED;
    }

    public static RecoveryDecision recover(
            CheckpointIdentity expected,
            CheckpointIdentity actual,
            ErrorClass errorClass,
            boolean immutableReceiptProvesCompletion
    ) {
        if (errorClass == ErrorClass.UNKNOWN_RESULT) {
            return immutableReceiptProvesCompletion
                    ? RecoveryDecision.RESUME_CHECKPOINT
                    : RecoveryDecision.MANUAL_RECOVERY;
        }
        if (!expected.equals(actual)) return RecoveryDecision.FORK_RUN;
        return switch (errorClass) {
            case TRANSIENT, THROTTLED -> RecoveryDecision.RESUME_CHECKPOINT;
            case INVALID_INPUT, AUTHORIZATION, UNSUPPORTED -> RecoveryDecision.FAIL;
            case UNKNOWN_RESULT -> throw new IllegalStateException("unreachable");
        };
    }

    public static Money baseCost(
            BigDecimal quantity,
            BigDecimal unitPriceMinor,
            BigDecimal fxRate,
            String baseCurrency
    ) {
        requireNonNegative(quantity, "QUANTITY");
        requireNonNegative(unitPriceMinor, "UNIT_PRICE");
        if (fxRate == null || fxRate.signum() <= 0) {
            throw new IllegalArgumentException("ELMOS_MTF_FX_RATE_INVALID");
        }
        return new Money(baseCurrency,
                quantity.multiply(unitPriceMinor).multiply(fxRate));
    }

    public static FinancialTotals totals(
            Money postedCost,
            Money recognizedRevenue,
            Money collectedCash,
            Instant asOf,
            boolean usageReconciled,
            boolean revenueReconciled
    ) {
        Money profit = recognizedRevenue.subtract(postedCost);
        BigDecimal margin = recognizedRevenue.minorUnits().signum() == 0
                ? null
                : profit.minorUnits().divide(
                        recognizedRevenue.minorUnits(), 9, MONEY_ROUNDING);
        return new FinancialTotals(postedCost, recognizedRevenue, collectedCash,
                profit, margin, asOf, usageReconciled && revenueReconciled);
    }

    /**
     * Allocates an exact signed amount by non-negative weights. The final entry
     * receives the deterministic rounding residual, so conservation is exact at
     * the configured currency precision.
     */
    public static Map<String, Money> allocate(
            Money total,
            Map<String, BigDecimal> weights
    ) {
        if (weights == null || weights.isEmpty()) {
            throw new IllegalArgumentException("ELMOS_MTF_ALLOCATION_EMPTY");
        }
        BigDecimal weightTotal = BigDecimal.ZERO;
        for (Map.Entry<String, BigDecimal> entry : weights.entrySet()) {
            requireId(entry.getKey(), "ALLOCATION_TARGET");
            requireNonNegative(entry.getValue(), "ALLOCATION_WEIGHT");
            weightTotal = weightTotal.add(entry.getValue());
        }
        if (weightTotal.signum() <= 0) {
            throw new IllegalArgumentException("ELMOS_MTF_ALLOCATION_WEIGHT_ZERO");
        }
        List<String> keys = weights.keySet().stream().sorted().toList();
        Map<String, Money> result = new LinkedHashMap<>();
        BigDecimal allocated = BigDecimal.ZERO.setScale(MONEY_SCALE, MONEY_ROUNDING);
        for (int index = 0; index < keys.size(); index++) {
            String key = keys.get(index);
            BigDecimal amount = index == keys.size() - 1
                    ? total.minorUnits().subtract(allocated)
                    : total.minorUnits().multiply(weights.get(key))
                            .divide(weightTotal, MONEY_SCALE, MONEY_ROUNDING);
            Money share = new Money(total.currency(), amount);
            result.put(key, share);
            allocated = allocated.add(share.minorUnits());
        }
        if (allocated.compareTo(total.minorUnits()) != 0) {
            throw new IllegalStateException("ELMOS_MTF_ALLOCATION_NOT_CONSERVED");
        }
        return Map.copyOf(result);
    }

    private static Map<TaskState, Set<TaskState>> transitions() {
        Map<TaskState, Set<TaskState>> result = new EnumMap<>(TaskState.class);
        result.put(TaskState.WAITING_FOR_SLOT, Set.of(TaskState.ADMITTED, TaskState.CANCELLED));
        result.put(TaskState.ADMITTED, Set.of(TaskState.RUNNING, TaskState.CANCELLED,
                TaskState.UNKNOWN_RESULT));
        result.put(TaskState.RUNNING, Set.of(TaskState.PAUSE_REQUESTED, TaskState.SUCCEEDED,
                TaskState.FAILED, TaskState.CANCELLED, TaskState.UNKNOWN_RESULT));
        result.put(TaskState.PAUSE_REQUESTED, Set.of(TaskState.PAUSED, TaskState.CANCELLED,
                TaskState.UNKNOWN_RESULT));
        result.put(TaskState.PAUSED, Set.of(TaskState.RESUME_REQUESTED, TaskState.CANCELLED));
        result.put(TaskState.RESUME_REQUESTED, Set.of(TaskState.WAITING_FOR_SLOT, TaskState.CANCELLED));
        result.put(TaskState.UNKNOWN_RESULT, Set.of(TaskState.RECONCILING));
        result.put(TaskState.RECONCILING, Set.of(TaskState.WAITING_FOR_SLOT,
                TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED));
        result.put(TaskState.SUCCEEDED, Set.of());
        result.put(TaskState.FAILED, Set.of());
        result.put(TaskState.CANCELLED, Set.of());
        return Map.copyOf(result);
    }

    private static Map<WorkloadClass, WorkloadProfile> workloads() {
        Map<WorkloadClass, WorkloadProfile> result = new EnumMap<>(WorkloadClass.class);
        result.put(WorkloadClass.PARSING, new WorkloadProfile(1, 16));
        result.put(WorkloadClass.GENERATION, new WorkloadProfile(2, 8));
        result.put(WorkloadClass.CONVERSION, new WorkloadProfile(3, 6));
        result.put(WorkloadClass.VALIDATION, new WorkloadProfile(2, 8));
        result.put(WorkloadClass.RENDERING, new WorkloadProfile(4, 4));
        result.put(WorkloadClass.MODEL_GPU, new WorkloadProfile(8, 2));
        return Map.copyOf(result);
    }

    private static BigDecimal exact(BigDecimal value) {
        if (value == null) throw new IllegalArgumentException("ELMOS_MTF_MONEY_REQUIRED");
        return value.setScale(MONEY_SCALE, MONEY_ROUNDING);
    }

    private static void sameCurrency(Money left, Money right) {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");
        if (!left.currency().equals(right.currency())) {
            throw new IllegalArgumentException("ELMOS_MTF_CURRENCY_MISMATCH");
        }
    }

    private static void requireNonNegative(BigDecimal value, String field) {
        if (value == null || value.signum() < 0) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_INVALID");
        }
    }

    private static void requireDigest(String value, String field) {
        if (value == null || !value.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_DIGEST_INVALID");
        }
    }

    private static void requireId(String value, String field) {
        if (value == null || value.isBlank() || value.length() > 160
                || !value.matches("[A-Za-z0-9][A-Za-z0-9._:@/-]*")) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_INVALID");
        }
    }
}
