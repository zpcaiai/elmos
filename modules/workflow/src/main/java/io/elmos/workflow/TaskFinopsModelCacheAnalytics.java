package io.elmos.workflow;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;

/**
 * Pure model and cache efficiency projection for the task FinOps analytics
 * boundary. The source rows are immutable observations; callers must persist
 * them through an adapter before exposing the projection. Provider billing,
 * cache services, OTel, and production qualification remain external.
 */
public final class TaskFinopsModelCacheAnalytics {
    public static final int MONEY_SCALE = TaskFinopsPolicy.MONEY_SCALE;
    public static final int RATIO_SCALE = 9;

    public enum Completeness {
        COMPLETE,
        PARTIAL,
        UNKNOWN
    }

    public enum ExternalEvidenceState {
        NOT_RUN
    }

    public enum ProviderOutcome {
        UNKNOWN
    }

    public enum ProductionCertification {
        NOT_CERTIFIED
    }

    public record Observation(
            TaskFinopsPort.AuthenticatedContext context,
            String observationId,
            String taskId,
            long runNumber,
            String model,
            String provider,
            boolean cacheHit,
            long inputTokens,
            long outputTokens,
            long cacheReadTokens,
            long cacheWriteTokens,
            long latencyMillis,
            String currency,
            BigDecimal costMinor,
            Instant occurredAt,
            TaskFinopsPort.ReconciliationStatus reconciliationStatus
    ) {
        public Observation {
            Objects.requireNonNull(context, "context");
            observationId = identifier(observationId, "OBSERVATION", 96);
            taskId = identifier(taskId, "TASK", 96);
            if (runNumber < 1 || inputTokens < 0 || outputTokens < 0
                    || cacheReadTokens < 0 || cacheWriteTokens < 0 || latencyMillis < 0
                    || cacheReadTokens > inputTokens
                    || (cacheHit && cacheReadTokens == 0)) {
                throw new IllegalArgumentException("ELMOS_MTF_MODEL_CACHE_OBSERVATION_INVALID");
            }
            model = identifier(model, "MODEL", 160);
            provider = identifier(provider, "PROVIDER", 96);
            currency = TaskFinopsModelCacheAnalytics.currency(currency);
            costMinor = exactNonNegative(costMinor, "COST");
            Objects.requireNonNull(occurredAt, "occurredAt");
            Objects.requireNonNull(reconciliationStatus, "reconciliationStatus");
        }
    }

    public record MetricRow(
            String model,
            String provider,
            String currency,
            long observationCount,
            long cacheHitCount,
            long inputTokens,
            long outputTokens,
            long cacheReadTokens,
            long cacheWriteTokens,
            BigDecimal totalCostMinor,
            BigDecimal cacheHitRatio,
            BigDecimal costPerOutputTokenMinor,
            long totalLatencyMillis,
            Completeness completeness,
            TaskFinopsPort.ReconciliationStatus reconciliationStatus
    ) {
        public MetricRow {
            model = identifier(model, "MODEL", 160);
            provider = identifier(provider, "PROVIDER", 96);
            currency = TaskFinopsModelCacheAnalytics.currency(currency);
            if (observationCount < 1 || cacheHitCount < 0 || cacheHitCount > observationCount
                    || inputTokens < 0 || outputTokens < 0 || cacheReadTokens < 0
                    || cacheWriteTokens < 0 || totalLatencyMillis < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_MODEL_CACHE_METRIC_INVALID");
            }
            totalCostMinor = exactNonNegative(totalCostMinor, "TOTAL_COST");
            cacheHitRatio = exactRatio(cacheHitRatio, "CACHE_HIT_RATIO");
            if (cacheHitRatio.compareTo(BigDecimal.ZERO) < 0
                    || cacheHitRatio.compareTo(BigDecimal.ONE) > 0) {
                throw new IllegalArgumentException("ELMOS_MTF_MODEL_CACHE_RATIO_INVALID");
            }
            if (costPerOutputTokenMinor != null) {
                costPerOutputTokenMinor = exactNonNegative(
                        costPerOutputTokenMinor, "COST_PER_OUTPUT_TOKEN");
            }
            Objects.requireNonNull(completeness, "completeness");
            Objects.requireNonNull(reconciliationStatus, "reconciliationStatus");
        }
    }

    public record Result(
            TaskFinopsPort.AuthenticatedContext context,
            List<MetricRow> rows,
            long observationCount,
            Instant asOf,
            String checksum,
            ExternalEvidenceState externalEvidence,
            ProviderOutcome providerOutcome,
            ProductionCertification productionCertification
    ) {
        public Result {
            Objects.requireNonNull(context, "context");
            rows = List.copyOf(Objects.requireNonNull(rows, "rows"));
            if (observationCount < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_MODEL_CACHE_COUNT_INVALID");
            }
            long rowCount;
            try {
                rowCount = rows.stream().mapToLong(MetricRow::observationCount)
                        .reduce(0L, Math::addExact);
            } catch (ArithmeticException exception) {
                throw new IllegalArgumentException("ELMOS_MTF_MODEL_CACHE_COUNT_INVALID", exception);
            }
            if (rowCount != observationCount || (observationCount == 0) != rows.isEmpty()) {
                throw new IllegalArgumentException("ELMOS_MTF_MODEL_CACHE_SHAPE_INVALID");
            }
            Objects.requireNonNull(asOf, "asOf");
            checksum = digest(checksum, "CHECKSUM");
            if (externalEvidence != ExternalEvidenceState.NOT_RUN
                    || providerOutcome != ProviderOutcome.UNKNOWN
                    || productionCertification != ProductionCertification.NOT_CERTIFIED) {
                throw new IllegalArgumentException("ELMOS_MTF_MODEL_CACHE_SAFETY_BOUNDARY");
            }
            Objects.requireNonNull(externalEvidence, "externalEvidence");
            Objects.requireNonNull(providerOutcome, "providerOutcome");
            Objects.requireNonNull(productionCertification, "productionCertification");
        }
    }

    private record Key(String model, String provider, String currency) implements Comparable<Key> {
        @Override
        public int compareTo(Key other) {
            int modelOrder = model.compareTo(other.model);
            if (modelOrder != 0) return modelOrder;
            int providerOrder = provider.compareTo(other.provider);
            return providerOrder != 0 ? providerOrder : currency.compareTo(other.currency);
        }
    }

    private static final class Accumulator {
        private long observations;
        private long hits;
        private long input;
        private long output;
        private long cacheRead;
        private long cacheWrite;
        private long latency;
        private BigDecimal cost = BigDecimal.ZERO.setScale(MONEY_SCALE, RoundingMode.HALF_EVEN);
        private Completeness completeness = Completeness.COMPLETE;
        private TaskFinopsPort.ReconciliationStatus reconciliation =
                TaskFinopsPort.ReconciliationStatus.RECONCILED;

        private void add(Observation observation) {
            observations = Math.addExact(observations, 1);
            if (observation.cacheHit()) hits = Math.addExact(hits, 1);
            input = Math.addExact(input, observation.inputTokens());
            output = Math.addExact(output, observation.outputTokens());
            cacheRead = Math.addExact(cacheRead, observation.cacheReadTokens());
            cacheWrite = Math.addExact(cacheWrite, observation.cacheWriteTokens());
            latency = Math.addExact(latency, observation.latencyMillis());
            cost = cost.add(observation.costMinor()).setScale(MONEY_SCALE, RoundingMode.HALF_EVEN);
            completeness = leastComplete(completeness, observation.reconciliationStatus());
            reconciliation = leastReconciled(reconciliation, observation.reconciliationStatus());
        }
    }

    private TaskFinopsModelCacheAnalytics() {}

    public static Result aggregate(
            TaskFinopsPort.AuthenticatedContext context,
            List<Observation> observations
    ) {
        Objects.requireNonNull(context, "context");
        List<Observation> input = List.copyOf(Objects.requireNonNull(observations, "observations"));
        Set<String> observationIds = new HashSet<>();
        Map<Key, Accumulator> groups = new TreeMap<>();
        Instant asOf = Instant.EPOCH;

        for (Observation observation : input) {
            Objects.requireNonNull(observation, "observation");
            if (!observation.context().equals(context)) {
                throw new IllegalArgumentException("ELMOS_MTF_MODEL_CACHE_SCOPE_MISMATCH");
            }
            if (!observationIds.add(observation.observationId())) {
                throw new IllegalArgumentException("ELMOS_MTF_MODEL_CACHE_DUPLICATE_OBSERVATION");
            }
            groups.computeIfAbsent(new Key(observation.model(), observation.provider(),
                    observation.currency()), ignored -> new Accumulator()).add(observation);
            if (observation.occurredAt().isAfter(asOf)) asOf = observation.occurredAt();
        }

        List<MetricRow> rows = new ArrayList<>();
        StringBuilder canonical = new StringBuilder("elmos.task-finops.model-cache.v1\n");
        canonical.append(context.organizationId()).append('\n')
                .append(context.accountId()).append('\n');
        for (Map.Entry<Key, Accumulator> entry : groups.entrySet()) {
            Key key = entry.getKey();
            Accumulator value = entry.getValue();
            BigDecimal hitRatio = BigDecimal.valueOf(value.hits)
                    .divide(BigDecimal.valueOf(value.observations), RATIO_SCALE,
                            RoundingMode.HALF_EVEN);
            BigDecimal costPerOutput = value.output == 0
                    ? null
                    : value.cost.divide(BigDecimal.valueOf(value.output), MONEY_SCALE,
                            RoundingMode.HALF_EVEN);
            MetricRow row = new MetricRow(key.model(), key.provider(), key.currency(),
                    value.observations, value.hits, value.input, value.output,
                    value.cacheRead, value.cacheWrite, value.cost, hitRatio, costPerOutput,
                    value.latency, value.completeness, value.reconciliation);
            rows.add(row);
            canonical.append(key.model()).append('|').append(key.provider()).append('|')
                    .append(key.currency()).append('|').append(row.observationCount()).append('|')
                    .append(row.cacheHitCount()).append('|').append(row.inputTokens()).append('|')
                    .append(row.outputTokens()).append('|').append(row.cacheReadTokens()).append('|')
                    .append(row.cacheWriteTokens()).append('|').append(row.totalCostMinor())
                    .append('|').append(row.totalLatencyMillis()).append('|')
                    .append(row.completeness()).append('|').append(row.reconciliationStatus())
                    .append('\n');
        }
        return new Result(context, rows, input.size(), asOf, sha256(canonical.toString()),
                ExternalEvidenceState.NOT_RUN, ProviderOutcome.UNKNOWN,
                ProductionCertification.NOT_CERTIFIED);
    }

    private static Completeness leastComplete(
            Completeness current,
            TaskFinopsPort.ReconciliationStatus status
    ) {
        if (status == TaskFinopsPort.ReconciliationStatus.UNKNOWN
                || status == TaskFinopsPort.ReconciliationStatus.INCONCLUSIVE) {
            return Completeness.UNKNOWN;
        }
        if (status != TaskFinopsPort.ReconciliationStatus.RECONCILED) {
            return current == Completeness.UNKNOWN ? current : Completeness.PARTIAL;
        }
        return current;
    }

    private static TaskFinopsPort.ReconciliationStatus leastReconciled(
            TaskFinopsPort.ReconciliationStatus current,
            TaskFinopsPort.ReconciliationStatus candidate
    ) {
        if (candidate == TaskFinopsPort.ReconciliationStatus.UNKNOWN
                || candidate == TaskFinopsPort.ReconciliationStatus.INCONCLUSIVE) {
            return candidate;
        }
        if (candidate == TaskFinopsPort.ReconciliationStatus.REJECTED) return candidate;
        if (candidate == TaskFinopsPort.ReconciliationStatus.PENDING
                && current == TaskFinopsPort.ReconciliationStatus.RECONCILED) return candidate;
        return current;
    }

    private static String currency(String value) {
        if (value == null || !value.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("ELMOS_MTF_CURRENCY_INVALID");
        }
        return value;
    }

    private static BigDecimal exactNonNegative(BigDecimal value, String field) {
        if (value == null || value.signum() < 0 || value.precision() > 30) {
            throw new IllegalArgumentException("ELMOS_MTF_MODEL_CACHE_" + field + "_INVALID");
        }
        return value.setScale(MONEY_SCALE, RoundingMode.HALF_EVEN);
    }

    private static BigDecimal exactRatio(BigDecimal value, String field) {
        if (value == null || value.precision() > 30) {
            throw new IllegalArgumentException("ELMOS_MTF_MODEL_CACHE_" + field + "_INVALID");
        }
        return value.setScale(RATIO_SCALE, RoundingMode.HALF_EVEN);
    }

    private static String digest(String value, String field) {
        if (value == null || !value.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("ELMOS_MTF_MODEL_CACHE_" + field + "_INVALID");
        }
        return value;
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("ELMOS_MTF_SHA256_UNAVAILABLE", exception);
        }
    }

    private static String identifier(String value, String field, int maxLength) {
        if (value == null || value.isBlank() || value.length() > maxLength
                || !value.matches("[A-Za-z0-9][A-Za-z0-9._:/-]*")) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_INVALID");
        }
        return value;
    }
}
