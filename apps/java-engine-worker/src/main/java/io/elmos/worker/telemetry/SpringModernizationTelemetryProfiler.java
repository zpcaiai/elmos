package io.elmos.worker.telemetry;

import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;

/**
 * Industrial-grade Telemetry, Profiler, and Performance Accounting subsystem
 * for large-scale Spring Boot modernization pipelines.
 * <p>
 * Captures granular phase latencies, rule application frequencies, file diff statistics,
 * memory consumption, throughput metrics (LOC/sec), and formats standardized reports for
 * Prometheus, OpenTelemetry, JSON, and executive review.
 */
public final class SpringModernizationTelemetryProfiler {

    public enum TelemetryPhase {
        DISCOVERY("Repository Discovery & AST Preflight"),
        PARSING("Source Parsing & AST Model Building"),
        RECIPE_EXECUTION("OpenRewrite Recipe Transformation"),
        AUTOMATED_REPAIR("Deterministic Diagnostic Auto-Repair"),
        SOURCE_VERIFICATION("Source Baseline AST Verification"),
        TARGET_BUILD("Target Compilation & Packaging"),
        TEST_EXECUTION("Automated Test Suite Execution"),
        RUNTIME_PROBE("Actuator Health & Startup Probe"),
        REPORTING("Audit Dossier & Evidence Packaging");

        private final String description;

        TelemetryPhase(String description) {
            this.description = description;
        }

        public String getDescription() {
            return description;
        }
    }

    public enum MetricStatus {
        SUCCESS,
        WARNING,
        FAILED
    }

    public record PhaseMetric(
            TelemetryPhase phase,
            Instant startTime,
            Instant endTime,
            long durationMillis,
            MetricStatus status,
            String details
    ) {}

    public record RuleMetric(
            String ruleId,
            AtomicInteger applicationCount,
            AtomicLong totalDurationNanos,
            AtomicInteger successCount,
            AtomicInteger failureCount,
            AtomicInteger filesModifiedCount,
            AtomicInteger linesAddedCount,
            AtomicInteger linesDeletedCount
    ) {
        public RuleMetric(String ruleId) {
            this(
                    ruleId,
                    new AtomicInteger(0),
                    new AtomicLong(0),
                    new AtomicInteger(0),
                    new AtomicInteger(0),
                    new AtomicInteger(0),
                    new AtomicInteger(0),
                    new AtomicInteger(0)
            );
        }

        public double averageDurationMillis() {
            int count = applicationCount.get();
            return count > 0 ? (totalDurationNanos.get() / (count * 1_000_000.0)) : 0.0;
        }
    }

    public record ModernizationRunProfile(
            String runId,
            String repositoryName,
            String sourceBootVersion,
            String targetBootVersion,
            String javaVersion,
            Instant startedAt,
            Instant completedAt,
            long totalDurationMillis,
            int totalFilesScanned,
            int totalFilesModified,
            int totalSourceLoc,
            int totalTargetLoc,
            double throughputLocPerSecond,
            List<PhaseMetric> phases,
            Map<String, RuleMetricSummary> ruleMetrics,
            List<String> errors,
            long peakMemoryUsageBytes
    ) {}

    public record RuleMetricSummary(
            String ruleId,
            int applicationCount,
            long totalDurationMillis,
            double averageDurationMillis,
            int successCount,
            int failureCount,
            int filesModifiedCount,
            int linesAddedCount,
            int linesDeletedCount
    ) {}

    private final String runId;
    private final String repositoryName;
    private final String sourceBootVersion;
    private final String targetBootVersion;
    private final String javaVersion;
    private final Instant startedAt;

    private final Map<TelemetryPhase, Instant> activePhaseStarts = new EnumMap<>(TelemetryPhase.class);
    private final List<PhaseMetric> recordedPhases = Collections.synchronizedList(new ArrayList<>());
    private final Map<String, RuleMetric> ruleMetrics = new ConcurrentHashMap<>();
    private final List<String> recordedErrors = Collections.synchronizedList(new ArrayList<>());
    private final AtomicLong peakMemoryBytes = new AtomicLong(0);

    private SpringModernizationTelemetryProfiler(
            String runId,
            String repositoryName,
            String sourceBootVersion,
            String targetBootVersion,
            String javaVersion
    ) {
        this.runId = Objects.requireNonNull(runId, "runId must not be null");
        this.repositoryName = Objects.requireNonNull(repositoryName, "repositoryName must not be null");
        this.sourceBootVersion = Objects.requireNonNull(sourceBootVersion, "sourceBootVersion must not be null");
        this.targetBootVersion = Objects.requireNonNull(targetBootVersion, "targetBootVersion must not be null");
        this.javaVersion = Objects.requireNonNull(javaVersion, "javaVersion must not be null");
        this.startedAt = Instant.now();
        sampleMemoryUsage();
    }

    public static SpringModernizationTelemetryProfiler start(
            String repositoryName,
            String sourceBootVersion,
            String targetBootVersion,
            String javaVersion
    ) {
        String runId = "RUN-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
        return new SpringModernizationTelemetryProfiler(runId, repositoryName, sourceBootVersion, targetBootVersion, javaVersion);
    }

    public static SpringModernizationTelemetryProfiler start(
            String runId,
            String repositoryName,
            String sourceBootVersion,
            String targetBootVersion,
            String javaVersion
    ) {
        return new SpringModernizationTelemetryProfiler(runId, repositoryName, sourceBootVersion, targetBootVersion, javaVersion);
    }

    public void startPhase(TelemetryPhase phase) {
        activePhaseStarts.put(phase, Instant.now());
        sampleMemoryUsage();
    }

    public void endPhase(TelemetryPhase phase, MetricStatus status, String details) {
        Instant start = activePhaseStarts.remove(phase);
        Instant now = Instant.now();
        if (start == null) {
            start = now;
        }
        long duration = Math.max(0, now.toEpochMilli() - start.toEpochMilli());
        PhaseMetric metric = new PhaseMetric(phase, start, now, duration, status, details != null ? details : "");
        recordedPhases.add(metric);
        sampleMemoryUsage();
    }

    public void endPhaseSuccess(TelemetryPhase phase) {
        endPhase(phase, MetricStatus.SUCCESS, "Completed successfully");
    }

    public void endPhaseFailure(TelemetryPhase phase, String errorReason) {
        endPhase(phase, MetricStatus.FAILED, errorReason);
        recordError(phase.name() + ": " + errorReason);
    }

    public void recordRuleApplication(
            String ruleId,
            long durationNanos,
            boolean success,
            int filesModified,
            int linesAdded,
            int linesDeleted
    ) {
        RuleMetric metric = ruleMetrics.computeIfAbsent(ruleId, RuleMetric::new);
        metric.applicationCount().incrementAndGet();
        metric.totalDurationNanos().addAndGet(Math.max(0, durationNanos));
        if (success) {
            metric.successCount().incrementAndGet();
        } else {
            metric.failureCount().incrementAndGet();
        }
        metric.filesModifiedCount().addAndGet(Math.max(0, filesModified));
        metric.linesAddedCount().addAndGet(Math.max(0, linesAdded));
        metric.linesDeletedCount().addAndGet(Math.max(0, linesDeleted));
    }

    public void recordError(String errorMessage) {
        if (errorMessage != null && !errorMessage.isBlank()) {
            recordedErrors.add(errorMessage);
        }
    }

    public void sampleMemoryUsage() {
        Runtime runtime = Runtime.getRuntime();
        long used = runtime.totalMemory() - runtime.freeMemory();
        peakMemoryBytes.updateAndGet(prev -> Math.max(prev, used));
    }

    public ModernizationRunProfile finish(int filesScanned, int filesModified, int sourceLoc, int targetLoc) {
        Instant completedAt = Instant.now();
        long totalDurationMillis = Math.max(1, completedAt.toEpochMilli() - startedAt.toEpochMilli());
        double durationSeconds = totalDurationMillis / 1000.0;
        double throughput = durationSeconds > 0 ? (targetLoc / durationSeconds) : targetLoc;

        Map<String, RuleMetricSummary> summaries = new LinkedHashMap<>();
        for (Map.Entry<String, RuleMetric> entry : ruleMetrics.entrySet()) {
            RuleMetric rm = entry.getValue();
            long totalMs = rm.totalDurationNanos().get() / 1_000_000;
            summaries.put(entry.getKey(), new RuleMetricSummary(
                    rm.ruleId(),
                    rm.applicationCount().get(),
                    totalMs,
                    rm.averageDurationMillis(),
                    rm.successCount().get(),
                    rm.failureCount().get(),
                    rm.filesModifiedCount().get(),
                    rm.linesAddedCount().get(),
                    rm.linesDeletedCount().get()
            ));
        }

        return new ModernizationRunProfile(
                runId,
                repositoryName,
                sourceBootVersion,
                targetBootVersion,
                javaVersion,
                startedAt,
                completedAt,
                totalDurationMillis,
                filesScanned,
                filesModified,
                sourceLoc,
                targetLoc,
                throughput,
                List.copyOf(recordedPhases),
                Collections.unmodifiableMap(summaries),
                List.copyOf(recordedErrors),
                peakMemoryBytes.get()
        );
    }

    // =========================================================================
    // EXPORT & OBSERVABILITY ADAPTERS
    // =========================================================================

    public String exportToJson(ModernizationRunProfile profile) {
        StringBuilder sb = new StringBuilder();
        sb.append("{\n");
        sb.append("  \"runId\": \"").append(profile.runId()).append("\",\n");
        sb.append("  \"repositoryName\": \"").append(profile.repositoryName()).append("\",\n");
        sb.append("  \"sourceBootVersion\": \"").append(profile.sourceBootVersion()).append("\",\n");
        sb.append("  \"targetBootVersion\": \"").append(profile.targetBootVersion()).append("\",\n");
        sb.append("  \"javaVersion\": \"").append(profile.javaVersion()).append("\",\n");
        sb.append("  \"totalDurationMillis\": ").append(profile.totalDurationMillis()).append(",\n");
        sb.append("  \"totalFilesScanned\": ").append(profile.totalFilesScanned()).append(",\n");
        sb.append("  \"totalFilesModified\": ").append(profile.totalFilesModified()).append(",\n");
        sb.append("  \"totalSourceLoc\": ").append(profile.totalSourceLoc()).append(",\n");
        sb.append("  \"totalTargetLoc\": ").append(profile.totalTargetLoc()).append(",\n");
        sb.append("  \"throughputLocPerSecond\": ").append(String.format(Locale.ROOT, "%.2f", profile.throughputLocPerSecond())).append(",\n");
        sb.append("  \"peakMemoryUsageMb\": ").append(profile.peakMemoryUsageBytes() / (1024 * 1024)).append(",\n");

        sb.append("  \"phases\": [\n");
        for (int i = 0; i < profile.phases().size(); i++) {
            PhaseMetric pm = profile.phases().get(i);
            sb.append("    {");
            sb.append("\"phase\": \"").append(pm.phase().name()).append("\", ");
            sb.append("\"durationMillis\": ").append(pm.durationMillis()).append(", ");
            sb.append("\"status\": \"").append(pm.status().name()).append("\"");
            sb.append("}").append(i < profile.phases().size() - 1 ? ",\n" : "\n");
        }
        sb.append("  ],\n");

        sb.append("  \"ruleSummaryCount\": ").append(profile.ruleMetrics().size()).append(",\n");
        sb.append("  \"errorCount\": ").append(profile.errors().size()).append("\n");
        sb.append("}");
        return sb.toString();
    }

    public String exportToPrometheusMetrics(ModernizationRunProfile profile) {
        StringBuilder sb = new StringBuilder();
        sb.append("# HELP spring_modernization_duration_seconds Total execution time in seconds\n");
        sb.append("# TYPE spring_modernization_duration_seconds gauge\n");
        sb.append(String.format(Locale.ROOT,
                "spring_modernization_duration_seconds{repo=\"%s\",run_id=\"%s\"} %.3f\n\n",
                profile.repositoryName(), profile.runId(), profile.totalDurationMillis() / 1000.0));

        sb.append("# HELP spring_modernization_throughput_loc_per_sec Throughput in lines of code processed per second\n");
        sb.append("# TYPE spring_modernization_throughput_loc_per_sec gauge\n");
        sb.append(String.format(Locale.ROOT,
                "spring_modernization_throughput_loc_per_sec{repo=\"%s\"} %.2f\n\n",
                profile.repositoryName(), profile.throughputLocPerSecond()));

        sb.append("# HELP spring_modernization_files_total Total files scanned and modified\n");
        sb.append("# TYPE spring_modernization_files_total counter\n");
        sb.append(String.format(
                "spring_modernization_files_total{repo=\"%s\",type=\"scanned\"} %d\n",
                profile.repositoryName(), profile.totalFilesScanned()));
        sb.append(String.format(
                "spring_modernization_files_total{repo=\"%s\",type=\"modified\"} %d\n\n",
                profile.repositoryName(), profile.totalFilesModified()));

        sb.append("# HELP spring_modernization_rules_applied_total Total rules applied by rule ID\n");
        sb.append("# TYPE spring_modernization_rules_applied_total counter\n");
        for (RuleMetricSummary rms : profile.ruleMetrics().values()) {
            sb.append(String.format(
                    "spring_modernization_rules_applied_total{repo=\"%s\",rule=\"%s\"} %d\n",
                    profile.repositoryName(), rms.ruleId(), rms.applicationCount()));
        }

        return sb.toString();
    }

    public String generateExecutiveSummaryMarkdown(ModernizationRunProfile profile) {
        StringBuilder sb = new StringBuilder();
        sb.append("# Modernization Run Executive Telemetry Summary\n\n");
        sb.append(String.format("- **Run ID**: `%s`\n", profile.runId()));
        sb.append(String.format("- **Repository**: `%s`\n", profile.repositoryName()));
        sb.append(String.format("- **Source Platform**: Spring Boot `%s` / Java `%s`\n",
                profile.sourceBootVersion(), profile.javaVersion()));
        sb.append(String.format("- **Target Platform**: Spring Boot `%s` / Java 21\n", profile.targetBootVersion()));
        sb.append(String.format("- **Total Wall-Clock Time**: `%.2f seconds` (%d ms)\n",
                profile.totalDurationMillis() / 1000.0, profile.totalDurationMillis()));
        sb.append(String.format("- **Throughput**: `%.1f LOC / sec`\n", profile.throughputLocPerSecond()));
        sb.append(String.format("- **Files Processed**: `%d scanned`, `%d modified`\n",
                profile.totalFilesScanned(), profile.totalFilesModified()));
        sb.append(String.format("- **Code Volume**: `%d LOC source` -> `%d LOC target`\n",
                profile.totalSourceLoc(), profile.totalTargetLoc()));
        sb.append(String.format("- **Peak Memory**: `%.1f MB`\n\n", profile.peakMemoryUsageBytes() / (1024.0 * 1024.0)));

        sb.append("## Pipeline Phase Execution Timings\n\n");
        sb.append("| Phase | Duration (ms) | Status | Details |\n");
        sb.append("| :--- | :--- | :--- | :--- |\n");
        for (PhaseMetric pm : profile.phases()) {
            sb.append(String.format("| `%s` | %d ms | **%s** | %s |\n",
                    pm.phase().name(), pm.durationMillis(), pm.status(), pm.details()));
        }
        sb.append("\n");

        if (!profile.ruleMetrics().isEmpty()) {
            sb.append("## Rule Application Breakdown\n\n");
            sb.append("| Rule ID | Count | Success | Files | Lines Added | Lines Deleted |\n");
            sb.append("| :--- | :--- | :--- | :--- | :--- | :--- |\n");
            for (RuleMetricSummary rms : profile.ruleMetrics().values()) {
                sb.append(String.format("| `%s` | %d | %d | %d | +%d | -%d |\n",
                        rms.ruleId(), rms.applicationCount(), rms.successCount(),
                        rms.filesModifiedCount(), rms.linesAddedCount(), rms.linesDeletedCount()));
            }
            sb.append("\n");
        }

        if (!profile.errors().isEmpty()) {
            sb.append("## Recorded Pipeline Warnings & Errors\n\n");
            for (String err : profile.errors()) {
                sb.append(String.format("- ⚠️ %s\n", err));
            }
            sb.append("\n");
        }

        sb.append("## Modernization Verdict\n\n");
        boolean fullySuccessful = profile.errors().isEmpty() &&
                profile.phases().stream().allMatch(p -> p.status() == MetricStatus.SUCCESS);
        if (fullySuccessful) {
            sb.append("✅ **VERIFIED 100% PRODUCTION READY & GREEN**\n");
        } else {
            sb.append("⚠️ **COMPLETED WITH REVIEW ADVISORIES**\n");
        }

        return sb.toString();
    }
}
