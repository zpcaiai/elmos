package io.elmos.workflow;

import java.time.Instant;
import java.util.Objects;

/** Orchestrates bounded journal replay, aggregation and atomic publication. */
public final class TaskFinopsAnalyticsService {
    private final TaskFinopsOperationsPort operations;

    public TaskFinopsAnalyticsService(TaskFinopsOperationsPort operations) {
        this.operations = Objects.requireNonNull(operations, "operations");
    }

    public record RebuildCommand(
            TaskFinopsPort.AuthenticatedContext context,
            String rebuildId,
            Instant windowStart,
            Instant windowEnd,
            long expectedGeneration,
            String idempotencyKey,
            String requestDigest
    ) {}

    public record RebuildReceipt(
            String rebuildId,
            long generation,
            long eventCount,
            long factCount,
            int runCount,
            int bucketCount,
            String journalChecksum,
            String hourlyChecksum,
            String dailyChecksum,
            TaskFinopsAnalytics.ExternalEvidenceState externalEvidence,
            TaskFinopsAnalytics.ProviderOutcome providerOutcome,
            TaskFinopsAnalytics.ProductionCertification productionCertification
    ) {}

    public RebuildReceipt rebuild(RebuildCommand command) {
        Objects.requireNonNull(command, "command");
        var window = new TaskFinopsOperationsPort.AnalyticsWindow(
                command.context(), command.windowStart(), command.windowEnd(),
                TaskFinopsOperationsPort.MAX_ANALYTICS_SOURCE_ROWS);
        TaskFinopsOperationsPort.AnalyticsSource source = operations.analyticsSource(window);
        TaskFinopsAnalytics.RebuildResult replay =
                TaskFinopsAnalytics.rebuild(command.context(), source.journal());
        TaskFinopsAnalytics.AggregationResult hourly = TaskFinopsAnalytics.aggregate(
                command.context(), source.financialFacts(), TaskFinopsAnalytics.Grain.HOUR);
        TaskFinopsAnalytics.AggregationResult daily = TaskFinopsAnalytics.aggregate(
                command.context(), source.financialFacts(), TaskFinopsAnalytics.Grain.DAY);
        long generation = operations.publishProjection(
                new TaskFinopsOperationsPort.ProjectionPublication(
                        command.context(), command.rebuildId(), command.windowStart(),
                        command.windowEnd(), command.expectedGeneration(), replay,
                        hourly, daily, command.idempotencyKey(), command.requestDigest()));
        return new RebuildReceipt(
                command.rebuildId(), generation, replay.eventCount(), hourly.factCount(),
                replay.runs().size(), hourly.rows().size() + daily.rows().size(),
                replay.checksum(), hourly.checksum(), daily.checksum(),
                TaskFinopsAnalytics.ExternalEvidenceState.NOT_RUN,
                TaskFinopsAnalytics.ProviderOutcome.UNKNOWN,
                TaskFinopsAnalytics.ProductionCertification.NOT_CERTIFIED);
    }

    public TaskFinopsAnalytics.ExportArtifact export(
            TaskFinopsPort.AuthenticatedContext context,
            TaskFinopsAnalytics.Grain grain,
            TaskFinopsAnalytics.ExportFormat format,
            Instant from,
            Instant to,
            int limit
    ) {
        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(grain, "grain");
        Objects.requireNonNull(format, "format");
        TaskFinopsOperationsPort.ProjectionSnapshot snapshot = operations
                .currentProjection(context, grain, from, to, limit)
                .orElseThrow(() -> new TaskFinopsPort.TaskFinopsStateException(
                        "ELMOS_MTF_ANALYTICS_PROJECTION_UNKNOWN"));
        if (snapshot.inputContinuity()
                != TaskFinopsAnalytics.InputContinuity.COMPLETE) {
            throw new TaskFinopsAnalytics.AnalyticsException(
                    "ELMOS_MTF_ANALYTICS_INPUT_CONTINUITY_INCOMPLETE");
        }
        var aggregation = TaskFinopsAnalytics.projectionSlice(
                context, snapshot.buckets(), grain, snapshot.sourceAsOf());
        return format == TaskFinopsAnalytics.ExportFormat.JSON
                ? TaskFinopsAnalytics.exportJson(context, aggregation)
                : TaskFinopsAnalytics.exportCsv(context, aggregation);
    }
}
