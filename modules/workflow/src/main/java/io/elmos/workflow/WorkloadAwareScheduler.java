package io.elmos.workflow;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.time.Instant;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Repository-owned scheduling policy and metric adapter boundary.
 *
 * <p>The queue catalog is deliberately provider-neutral. It binds the exact
 * workload profiles used by the V77 admission functions, while leaving the
 * Temporal and OpenTelemetry effects behind adapters. A local snapshot is
 * therefore useful engineering output but can never be presented as a
 * Temporal execution or external observability receipt.</p>
 */
public final class WorkloadAwareScheduler {
    public static final String POLICY_VERSION = "mtf-workload-v1";
    public static final String EXTERNAL_EVIDENCE = "NOT_RUN";

    public enum RuntimeStatus {
        LOCAL_POLICY_ONLY,
        NOT_RUN
    }

    public record QueueProfile(
            TaskFinopsPolicy.WorkloadClass workloadClass,
            String taskQueue,
            int resourceUnits,
            int maxWorkerConcurrency,
            int autoscaleMinWorkers,
            int autoscaleMaxWorkers,
            String policyVersion,
            RuntimeStatus runtimeStatus
    ) {
        public QueueProfile {
            Objects.requireNonNull(workloadClass, "workloadClass");
            taskQueue = identifier(taskQueue, "TASK_QUEUE", 96);
            policyVersion = identifier(policyVersion, "POLICY_VERSION", 64);
            if (resourceUnits < 1 || resourceUnits > 64
                    || maxWorkerConcurrency < 1 || maxWorkerConcurrency > 64
                    || autoscaleMinWorkers < 0
                    || autoscaleMaxWorkers < autoscaleMinWorkers
                    || autoscaleMaxWorkers > 128) {
                throw new IllegalArgumentException("ELMOS_MTF_QUEUE_PROFILE_INVALID");
            }
            Objects.requireNonNull(runtimeStatus, "runtimeStatus");
        }
    }

    public record QueueSnapshot(
            TaskFinopsPort.AuthenticatedContext context,
            QueueProfile profile,
            int queueDepth,
            Duration oldestWait,
            int activeWorkers,
            long throttledCount,
            Instant asOf
    ) {
        public QueueSnapshot {
            Objects.requireNonNull(context, "context");
            Objects.requireNonNull(profile, "profile");
            if (queueDepth < 0 || activeWorkers < 0 || throttledCount < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_QUEUE_SNAPSHOT_INVALID");
            }
            Objects.requireNonNull(oldestWait, "oldestWait");
            if (oldestWait.isNegative()) {
                throw new IllegalArgumentException("ELMOS_MTF_QUEUE_AGE_INVALID");
            }
            Objects.requireNonNull(asOf, "asOf");
            if (profile.workloadClass() != profileFor(profile.workloadClass()).workloadClass()) {
                throw new IllegalArgumentException("ELMOS_MTF_QUEUE_PROFILE_MISMATCH");
            }
        }

        public BigDecimal saturationRatio() {
            return BigDecimal.valueOf(activeWorkers())
                    .divide(BigDecimal.valueOf(profile().maxWorkerConcurrency()), 9,
                            RoundingMode.HALF_EVEN);
        }

        public BigDecimal estimatedStartSeconds() {
            if (queueDepth() == 0) {
                return BigDecimal.ZERO.setScale(3, RoundingMode.UNNECESSARY);
            }
            BigDecimal workerBatches = BigDecimal.valueOf(queueDepth())
                    .divide(BigDecimal.valueOf(Math.max(1, profile().maxWorkerConcurrency())),
                            3, RoundingMode.CEILING);
            return workerBatches.multiply(BigDecimal.valueOf(30))
                    .add(BigDecimal.valueOf(oldestWait().toMillis())
                            .divide(BigDecimal.valueOf(1000), 3, RoundingMode.HALF_EVEN))
                    .setScale(3, RoundingMode.HALF_EVEN);
        }
    }

    public record Metric(
            String name,
            BigDecimal value,
            Map<String, String> labels,
            Instant asOf
    ) {
        public Metric {
            name = identifier(name, "METRIC", 128);
            Objects.requireNonNull(value, "value");
            if (value.signum() < 0 || value.scale() > 9) {
                throw new IllegalArgumentException("ELMOS_MTF_METRIC_VALUE_INVALID");
            }
            Map<String, String> normalized = new LinkedHashMap<>();
            for (Map.Entry<String, String> entry : Objects.requireNonNull(labels, "labels").entrySet()) {
                normalized.put(identifier(entry.getKey(), "METRIC_LABEL", 64),
                        identifier(entry.getValue(), "METRIC_LABEL_VALUE", 160));
            }
            labels = Map.copyOf(normalized);
            Objects.requireNonNull(asOf, "asOf");
        }
    }

    @FunctionalInterface
    public interface MetricSink {
        /** The sink may bind a real OTel adapter, but that effect is external. */
        void emit(Metric metric);
    }

    private static final Map<TaskFinopsPolicy.WorkloadClass, QueueProfile> PROFILES = profiles();

    private WorkloadAwareScheduler() {}

    public static QueueProfile profileFor(TaskFinopsPolicy.WorkloadClass workloadClass) {
        return PROFILES.get(Objects.requireNonNull(workloadClass, "workloadClass"));
    }

    public static Map<TaskFinopsPolicy.WorkloadClass, QueueProfile> queueCatalog() {
        return PROFILES;
    }

    /** Deterministic weighted-fair ordering shared with the durable claim policy. */
    public static List<TaskFinopsPolicy.QueueCandidate> order(
            List<TaskFinopsPolicy.QueueCandidate> candidates,
            Instant now
    ) {
        return TaskFinopsPolicy.weightedFairOrder(candidates, now);
    }

    /**
     * Converts one bounded observation into stable metric names. No implicit
     * export, provider call, or certification transition occurs here.
     */
    public static List<Metric> metrics(QueueSnapshot snapshot) {
        Objects.requireNonNull(snapshot, "snapshot");
        Map<String, String> labels = labels(snapshot);
        return List.of(
                new Metric("elmos_task_finops_queue_depth",
                        BigDecimal.valueOf(snapshot.queueDepth()), labels, snapshot.asOf()),
                new Metric("elmos_task_finops_queue_age_seconds",
                        BigDecimal.valueOf(snapshot.oldestWait().toMillis())
                                .divide(BigDecimal.valueOf(1000), 3, RoundingMode.HALF_EVEN),
                        labels, snapshot.asOf()),
                new Metric("elmos_task_finops_worker_saturation_ratio",
                        snapshot.saturationRatio(), labels, snapshot.asOf()),
                new Metric("elmos_task_finops_throttled_total",
                        BigDecimal.valueOf(snapshot.throttledCount()), labels, snapshot.asOf()),
                new Metric("elmos_task_finops_estimated_start_seconds",
                        snapshot.estimatedStartSeconds(), labels, snapshot.asOf())
        );
    }

    public static void emit(QueueSnapshot snapshot, MetricSink sink) {
        Objects.requireNonNull(sink, "sink");
        metrics(snapshot).forEach(sink::emit);
    }

    private static Map<String, String> labels(QueueSnapshot snapshot) {
        Map<String, String> labels = new LinkedHashMap<>();
        labels.put("organization_id", snapshot.context().organizationId());
        labels.put("account_id", snapshot.context().accountId());
        labels.put("workload_class", snapshot.profile().workloadClass().name());
        labels.put("task_queue", snapshot.profile().taskQueue());
        labels.put("policy_version", snapshot.profile().policyVersion());
        return labels;
    }

    private static Map<TaskFinopsPolicy.WorkloadClass, QueueProfile> profiles() {
        Map<TaskFinopsPolicy.WorkloadClass, QueueProfile> profiles =
                new EnumMap<>(TaskFinopsPolicy.WorkloadClass.class);
        profiles.put(TaskFinopsPolicy.WorkloadClass.PARSING,
                profile(TaskFinopsPolicy.WorkloadClass.PARSING, "mtf.parsing.v1", 1, 16, 0, 32));
        profiles.put(TaskFinopsPolicy.WorkloadClass.GENERATION,
                profile(TaskFinopsPolicy.WorkloadClass.GENERATION, "mtf.generation.v1", 2, 8, 0, 16));
        profiles.put(TaskFinopsPolicy.WorkloadClass.CONVERSION,
                profile(TaskFinopsPolicy.WorkloadClass.CONVERSION, "mtf.conversion.v1", 3, 6, 0, 12));
        profiles.put(TaskFinopsPolicy.WorkloadClass.VALIDATION,
                profile(TaskFinopsPolicy.WorkloadClass.VALIDATION, "mtf.validation.v1", 2, 8, 0, 16));
        profiles.put(TaskFinopsPolicy.WorkloadClass.RENDERING,
                profile(TaskFinopsPolicy.WorkloadClass.RENDERING, "mtf.rendering.v1", 4, 4, 0, 8));
        profiles.put(TaskFinopsPolicy.WorkloadClass.MODEL_GPU,
                profile(TaskFinopsPolicy.WorkloadClass.MODEL_GPU, "mtf.model-gpu.v1", 8, 2, 0, 4));
        return Map.copyOf(profiles);
    }

    private static QueueProfile profile(
            TaskFinopsPolicy.WorkloadClass workloadClass,
            String taskQueue,
            int resourceUnits,
            int maxWorkerConcurrency,
            int autoscaleMinWorkers,
            int autoscaleMaxWorkers
    ) {
        return new QueueProfile(workloadClass, taskQueue, resourceUnits,
                maxWorkerConcurrency, autoscaleMinWorkers, autoscaleMaxWorkers,
                POLICY_VERSION, RuntimeStatus.NOT_RUN);
    }

    private static String identifier(String value, String field, int maxLength) {
        if (value == null || value.isBlank() || value.length() > maxLength
                || !value.matches("[A-Za-z0-9][A-Za-z0-9._:-]*")) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_INVALID");
        }
        return value;
    }
}
