package io.elmos.workflow;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;

/**
 * Deterministic, side-effect-free task journal and FinOps projection logic.
 *
 * <p>The caller must supply an {@link TaskFinopsPort.AuthenticatedContext}
 * derived from authenticated membership. Every journal event, financial fact,
 * aggregate and export is checked against that context; tenant identifiers in
 * payload rows never select authorization scope.</p>
 *
 * <p>Continuity and checksums describe only the bounded input supplied to these
 * pure functions. Provider outcomes remain {@link ProviderOutcome#UNKNOWN},
 * external evidence remains {@link ExternalEvidenceState#NOT_RUN}, and this
 * class can never produce a production certification.</p>
 */
public final class TaskFinopsAnalytics {
    public static final String SCHEMA_VERSION = "elmos.task-finops.analytics.v1";

    public enum Grain {
        HOUR,
        DAY
    }

    public enum InputContinuity {
        COMPLETE,
        UNKNOWN
    }

    public enum DataCompleteness {
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

    public enum ExportFormat {
        JSON,
        CSV
    }

    /** Stable failures only; no provider or database text crosses this boundary. */
    public static final class AnalyticsException extends IllegalStateException {
        private final String code;

        public AnalyticsException(String code) {
            super(Objects.requireNonNull(code, "code"));
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    /** A single immutable event from one run-local, append-only sequence. */
    public record JournalEvent(
            String organizationId,
            String accountId,
            String taskId,
            long runNumber,
            long eventSequence,
            String eventId,
            TaskFinopsPolicy.TaskState taskState,
            short progressPercent,
            Instant occurredAt
    ) {
        public JournalEvent {
            organizationId = identifier(organizationId, "ORGANIZATION", 96);
            accountId = identifier(accountId, "ACCOUNT", 96);
            taskId = identifier(taskId, "TASK", 96);
            eventId = identifier(eventId, "EVENT", 96);
            if (runNumber < 1 || eventSequence < 1
                    || progressPercent < 0 || progressPercent > 100) {
                throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_EVENT_INVALID");
            }
            Objects.requireNonNull(taskState, "taskState");
            Objects.requireNonNull(occurredAt, "occurredAt");
            if (taskState == TaskFinopsPolicy.TaskState.SUCCEEDED
                    && progressPercent != 100) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_ANALYTICS_SUCCESS_PROGRESS_INVALID");
            }
            if (taskState != TaskFinopsPolicy.TaskState.SUCCEEDED
                    && progressPercent == 100) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_ANALYTICS_NON_SUCCESS_PROGRESS_INVALID");
            }
        }
    }

    /** Last replayed state for one exact task/run tuple. */
    public record RunProjection(
            String organizationId,
            String accountId,
            String taskId,
            long runNumber,
            TaskFinopsPolicy.TaskState taskState,
            short progressPercent,
            long lastEventSequence,
            Instant lastOccurredAt,
            String checksum
    ) {
        public RunProjection {
            organizationId = identifier(organizationId, "ORGANIZATION", 96);
            accountId = identifier(accountId, "ACCOUNT", 96);
            taskId = identifier(taskId, "TASK", 96);
            if (runNumber < 1 || lastEventSequence < 1
                    || progressPercent < 0 || progressPercent > 100) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_ANALYTICS_RUN_PROJECTION_INVALID");
            }
            Objects.requireNonNull(taskState, "taskState");
            Objects.requireNonNull(lastOccurredAt, "lastOccurredAt");
            checksum = digestValue(checksum, "RUN_CHECKSUM");
        }
    }

    /**
     * A deterministic local rebuild. COMPLETE means no gap was present in the
     * supplied sequence; it is not a statement about an external source.
     */
    public record RebuildResult(
            String organizationId,
            String accountId,
            List<RunProjection> runs,
            long eventCount,
            Instant asOf,
            String checksum,
            InputContinuity inputContinuity,
            ExternalEvidenceState externalEvidence,
            ProviderOutcome providerOutcome,
            ProductionCertification productionCertification
    ) {
        public RebuildResult {
            organizationId = identifier(organizationId, "ORGANIZATION", 96);
            accountId = identifier(accountId, "ACCOUNT", 96);
            runs = List.copyOf(Objects.requireNonNull(runs, "runs"));
            Objects.requireNonNull(inputContinuity, "inputContinuity");
            if (eventCount < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_EVENT_COUNT_INVALID");
            }
            long replayedEvents;
            try {
                replayedEvents = runs.stream().mapToLong(RunProjection::lastEventSequence)
                        .reduce(0L, Math::addExact);
            } catch (ArithmeticException exception) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_ANALYTICS_EVENT_COUNT_INVALID", exception);
            }
            String normalizedOrganizationId = organizationId;
            String normalizedAccountId = accountId;
            if (replayedEvents != eventCount
                    || (eventCount == 0) != runs.isEmpty()
                    || (eventCount == 0)
                    != (inputContinuity == InputContinuity.UNKNOWN)
                    || runs.stream().anyMatch(run ->
                    !run.organizationId().equals(normalizedOrganizationId)
                            || !run.accountId().equals(normalizedAccountId))) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_ANALYTICS_REBUILD_CONTINUITY_INVALID");
            }
            Objects.requireNonNull(asOf, "asOf");
            checksum = digestValue(checksum, "REBUILD_CHECKSUM");
            requireSafetyBoundary(externalEvidence, providerOutcome, productionCertification);
        }
    }

    /** Signed exact deltas; corrections are represented as later immutable facts. */
    public record FinancialFact(
            String organizationId,
            String accountId,
            String taskId,
            long runNumber,
            String factId,
            TaskFinopsPolicy.WorkloadClass workloadClass,
            String currency,
            TaskFinopsPort.AllocationBasis allocationBasis,
            BigDecimal costDeltaMinor,
            BigDecimal revenueDeltaMinor,
            Instant occurredAt,
            DataCompleteness completeness,
            TaskFinopsPort.ReconciliationStatus reconciliationStatus
    ) {
        public FinancialFact {
            organizationId = identifier(organizationId, "ORGANIZATION", 96);
            accountId = identifier(accountId, "ACCOUNT", 96);
            taskId = identifier(taskId, "TASK", 96);
            factId = identifier(factId, "FINANCIAL_FACT", 96);
            if (runNumber < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_RUN_INVALID");
            }
            Objects.requireNonNull(workloadClass, "workloadClass");
            currency = TaskFinopsAnalytics.currency(currency);
            Objects.requireNonNull(allocationBasis, "allocationBasis");
            costDeltaMinor = exactMoney(costDeltaMinor, "COST_DELTA");
            revenueDeltaMinor = exactMoney(revenueDeltaMinor, "REVENUE_DELTA");
            Objects.requireNonNull(occurredAt, "occurredAt");
            Objects.requireNonNull(completeness, "completeness");
            Objects.requireNonNull(reconciliationStatus, "reconciliationStatus");
            if (completeness == DataCompleteness.COMPLETE
                    && reconciliationStatus != TaskFinopsPort.ReconciliationStatus.RECONCILED) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_ANALYTICS_COMPLETE_RECONCILIATION_REQUIRED");
            }
            if ((reconciliationStatus == TaskFinopsPort.ReconciliationStatus.UNKNOWN
                    || reconciliationStatus == TaskFinopsPort.ReconciliationStatus.INCONCLUSIVE)
                    && completeness != DataCompleteness.UNKNOWN) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_ANALYTICS_UNKNOWN_COMPLETENESS_REQUIRED");
            }
        }
    }

    /** One stable UTC bucket. Currency and allocation basis are never mixed. */
    public record AggregateBucket(
            String organizationId,
            String accountId,
            String taskId,
            long runNumber,
            TaskFinopsPolicy.WorkloadClass workloadClass,
            Grain grain,
            Instant bucketStart,
            Instant bucketEnd,
            String currency,
            TaskFinopsPort.AllocationBasis allocationBasis,
            BigDecimal costDeltaMinor,
            BigDecimal revenueDeltaMinor,
            BigDecimal grossDeltaMinor,
            long factCount,
            DataCompleteness completeness,
            TaskFinopsPort.ReconciliationStatus reconciliationStatus
    ) {
        public AggregateBucket {
            organizationId = identifier(organizationId, "ORGANIZATION", 96);
            accountId = identifier(accountId, "ACCOUNT", 96);
            taskId = identifier(taskId, "TASK", 96);
            if (runNumber < 1 || factCount < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_BUCKET_INVALID");
            }
            Objects.requireNonNull(workloadClass, "workloadClass");
            Objects.requireNonNull(grain, "grain");
            Objects.requireNonNull(bucketStart, "bucketStart");
            Objects.requireNonNull(bucketEnd, "bucketEnd");
            if (!bucketEnd.equals(TaskFinopsAnalytics.bucketEnd(bucketStart, grain))) {
                throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_BUCKET_WINDOW_INVALID");
            }
            currency = TaskFinopsAnalytics.currency(currency);
            Objects.requireNonNull(allocationBasis, "allocationBasis");
            costDeltaMinor = exactMoney(costDeltaMinor, "BUCKET_COST");
            revenueDeltaMinor = exactMoney(revenueDeltaMinor, "BUCKET_REVENUE");
            grossDeltaMinor = exactMoney(grossDeltaMinor, "BUCKET_GROSS");
            if (grossDeltaMinor.compareTo(revenueDeltaMinor.subtract(costDeltaMinor)) != 0) {
                throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_GROSS_NOT_CONSERVED");
            }
            Objects.requireNonNull(completeness, "completeness");
            Objects.requireNonNull(reconciliationStatus, "reconciliationStatus");
        }
    }

    /** Stable, canonically sorted aggregate result. */
    public record AggregationResult(
            String organizationId,
            String accountId,
            Grain grain,
            List<AggregateBucket> rows,
            long factCount,
            Instant asOf,
            String checksum,
            ExternalEvidenceState externalEvidence,
            ProviderOutcome providerOutcome,
            ProductionCertification productionCertification
    ) {
        public AggregationResult {
            organizationId = identifier(organizationId, "ORGANIZATION", 96);
            accountId = identifier(accountId, "ACCOUNT", 96);
            Objects.requireNonNull(grain, "grain");
            rows = List.copyOf(Objects.requireNonNull(rows, "rows"));
            if (factCount < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_FACT_COUNT_INVALID");
            }
            long aggregatedFacts;
            try {
                aggregatedFacts = rows.stream().mapToLong(AggregateBucket::factCount)
                        .reduce(0L, Math::addExact);
            } catch (ArithmeticException exception) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_ANALYTICS_FACT_COUNT_INVALID", exception);
            }
            String normalizedOrganizationId = organizationId;
            String normalizedAccountId = accountId;
            Grain normalizedGrain = grain;
            if (aggregatedFacts != factCount
                    || (factCount == 0) != rows.isEmpty()
                    || rows.stream().anyMatch(row -> row.grain() != normalizedGrain
                    || !row.organizationId().equals(normalizedOrganizationId)
                    || !row.accountId().equals(normalizedAccountId))) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_ANALYTICS_AGGREGATION_SHAPE_INVALID");
            }
            Objects.requireNonNull(asOf, "asOf");
            checksum = digestValue(checksum, "AGGREGATION_CHECKSUM");
            requireSafetyBoundary(externalEvidence, providerOutcome, productionCertification);
        }
    }

    /** Content-addressed export bytes and their exact data-row count. */
    public record ExportArtifact(
            String organizationId,
            String accountId,
            ExportFormat format,
            String mediaType,
            String body,
            long rowCount,
            String digest,
            ExternalEvidenceState externalEvidence,
            ProviderOutcome providerOutcome,
            ProductionCertification productionCertification
    ) {
        public ExportArtifact {
            organizationId = identifier(organizationId, "ORGANIZATION", 96);
            accountId = identifier(accountId, "ACCOUNT", 96);
            Objects.requireNonNull(format, "format");
            mediaType = identifier(mediaType, "MEDIA_TYPE", 96);
            Objects.requireNonNull(body, "body");
            if (rowCount < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_ROW_COUNT_INVALID");
            }
            digest = digestValue(digest, "EXPORT_DIGEST");
            requireSafetyBoundary(externalEvidence, providerOutcome, productionCertification);
            if (!digest.equals(sha256(body))) {
                throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_EXPORT_DIGEST_MISMATCH");
            }
        }
    }

    private record RunKey(String taskId, long runNumber) {}

    private record BucketKey(
            String taskId,
            long runNumber,
            TaskFinopsPolicy.WorkloadClass workloadClass,
            Instant bucketStart,
            String currency,
            TaskFinopsPort.AllocationBasis allocationBasis
    ) {}

    private static final class ReplayCursor {
        private final List<JournalEvent> events = new ArrayList<>();
        private JournalEvent last;

        private ReplayCursor(JournalEvent first) {
            this.last = first;
            this.events.add(first);
        }

        private void append(JournalEvent event) {
            last = event;
            events.add(event);
        }
    }

    private static final class BucketAccumulator {
        private BigDecimal cost = zeroMoney();
        private BigDecimal revenue = zeroMoney();
        private long count;
        private DataCompleteness completeness = DataCompleteness.COMPLETE;
        private TaskFinopsPort.ReconciliationStatus reconciliation =
                TaskFinopsPort.ReconciliationStatus.RECONCILED;

        private void add(FinancialFact fact) {
            cost = cost.add(fact.costDeltaMinor());
            revenue = revenue.add(fact.revenueDeltaMinor());
            count = Math.addExact(count, 1L);
            completeness = leastComplete(completeness, fact.completeness());
            reconciliation = leastReconciled(reconciliation, fact.reconciliationStatus());
        }
    }

    private static final Comparator<RunKey> RUN_KEY_ORDER = Comparator
            .comparing(RunKey::taskId)
            .thenComparingLong(RunKey::runNumber);

    private static final Comparator<BucketKey> BUCKET_KEY_ORDER = Comparator
            .comparing(BucketKey::bucketStart)
            .thenComparing(BucketKey::taskId)
            .thenComparingLong(BucketKey::runNumber)
            .thenComparing(key -> key.workloadClass().name())
            .thenComparing(BucketKey::currency)
            .thenComparing(key -> key.allocationBasis().name());

    private static final Comparator<AggregateBucket> AGGREGATE_ROW_ORDER = Comparator
            .comparing(AggregateBucket::bucketStart)
            .thenComparing(AggregateBucket::taskId)
            .thenComparingLong(AggregateBucket::runNumber)
            .thenComparing(row -> row.workloadClass().name())
            .thenComparing(AggregateBucket::currency)
            .thenComparing(row -> row.allocationBasis().name());

    private TaskFinopsAnalytics() {}

    /** Replays input in append order and rejects every discontinuity. */
    public static RebuildResult rebuild(
            TaskFinopsPort.AuthenticatedContext context,
            List<JournalEvent> journal
    ) {
        Objects.requireNonNull(context, "context");
        List<JournalEvent> input = List.copyOf(Objects.requireNonNull(journal, "journal"));
        Map<RunKey, ReplayCursor> cursors = new TreeMap<>(RUN_KEY_ORDER);
        Set<String> eventIds = new HashSet<>();
        Instant asOf = Instant.EPOCH;

        for (JournalEvent event : input) {
            Objects.requireNonNull(event, "journal event");
            requireScope(context, event.organizationId(), event.accountId());
            if (!eventIds.add(event.eventId())) {
                throw failure("ELMOS_MTF_ANALYTICS_DUPLICATE_EVENT_ID");
            }
            RunKey key = new RunKey(event.taskId(), event.runNumber());
            ReplayCursor cursor = cursors.get(key);
            if (cursor == null) {
                requireGenesis(event);
                cursors.put(key, new ReplayCursor(event));
            } else {
                requireNext(cursor.last, event);
                cursor.append(event);
            }
            if (event.occurredAt().isAfter(asOf)) asOf = event.occurredAt();
        }
        requireContiguousRuns(cursors.keySet());

        List<RunProjection> projections = new ArrayList<>();
        StringBuilder canonical = new StringBuilder(SCHEMA_VERSION).append("\nrebuild\n");
        appendCanonical(canonical, "organization_id", context.organizationId());
        appendCanonical(canonical, "account_id", context.accountId());
        for (Map.Entry<RunKey, ReplayCursor> entry : cursors.entrySet()) {
            ReplayCursor cursor = entry.getValue();
            String runCanonical = canonicalJournal(cursor.events);
            String runChecksum = sha256(runCanonical);
            JournalEvent last = cursor.last;
            projections.add(new RunProjection(
                    last.organizationId(), last.accountId(), last.taskId(), last.runNumber(),
                    last.taskState(), last.progressPercent(), last.eventSequence(),
                    last.occurredAt(), runChecksum));
            canonical.append(runCanonical);
        }
        appendCanonical(canonical, "event_count", Long.toString(input.size()));
        appendCanonical(canonical, "as_of", asOf.toString());

        return new RebuildResult(
                context.organizationId(),
                context.accountId(),
                projections,
                input.size(),
                asOf,
                sha256(canonical.toString()),
                input.isEmpty() ? InputContinuity.UNKNOWN : InputContinuity.COMPLETE,
                ExternalEvidenceState.NOT_RUN,
                ProviderOutcome.UNKNOWN,
                ProductionCertification.NOT_CERTIFIED);
    }

    /** Aggregates exact signed deltas without mixing tenant, currency or basis. */
    public static AggregationResult aggregate(
            TaskFinopsPort.AuthenticatedContext context,
            List<FinancialFact> facts,
            Grain grain
    ) {
        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(grain, "grain");
        List<FinancialFact> input = List.copyOf(Objects.requireNonNull(facts, "facts"));
        Set<String> factIds = new HashSet<>();
        Map<BucketKey, BucketAccumulator> buckets = new TreeMap<>(BUCKET_KEY_ORDER);
        Instant asOf = Instant.EPOCH;

        for (FinancialFact fact : input) {
            Objects.requireNonNull(fact, "financial fact");
            requireScope(context, fact.organizationId(), fact.accountId());
            if (!factIds.add(fact.factId())) {
                throw failure("ELMOS_MTF_ANALYTICS_DUPLICATE_FINANCIAL_FACT");
            }
            Instant start = bucketStart(fact.occurredAt(), grain);
            BucketKey key = new BucketKey(
                    fact.taskId(), fact.runNumber(), fact.workloadClass(), start,
                    fact.currency(), fact.allocationBasis());
            buckets.computeIfAbsent(key, ignored -> new BucketAccumulator()).add(fact);
            if (fact.occurredAt().isAfter(asOf)) asOf = fact.occurredAt();
        }

        List<AggregateBucket> rows = new ArrayList<>();
        for (Map.Entry<BucketKey, BucketAccumulator> entry : buckets.entrySet()) {
            BucketKey key = entry.getKey();
            BucketAccumulator value = entry.getValue();
            rows.add(new AggregateBucket(
                    context.organizationId(), context.accountId(), key.taskId(), key.runNumber(),
                    key.workloadClass(), grain, key.bucketStart(),
                    bucketEnd(key.bucketStart(), grain), key.currency(), key.allocationBasis(),
                    value.cost, value.revenue, value.revenue.subtract(value.cost), value.count,
                    value.completeness, value.reconciliation));
        }

        List<FinancialFact> canonicalFacts = input.stream()
                .sorted(Comparator.comparing(FinancialFact::factId))
                .toList();
        String canonical = canonicalAggregation(
                context.organizationId(), context.accountId(), grain, rows,
                canonicalFacts, input.size(), asOf);
        return new AggregationResult(
                context.organizationId(), context.accountId(), grain, rows, input.size(), asOf,
                sha256(canonical), ExternalEvidenceState.NOT_RUN, ProviderOutcome.UNKNOWN,
                ProductionCertification.NOT_CERTIFIED);
    }

    /**
     * Rehydrates a bounded, already-published projection slice for export.
     * Its checksum binds the exact exported rows, not the full source-fact
     * generation from which the slice was selected.
     */
    public static AggregationResult projectionSlice(
            TaskFinopsPort.AuthenticatedContext context,
            List<AggregateBucket> rows,
            Grain grain,
            Instant asOf
    ) {
        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(grain, "grain");
        Objects.requireNonNull(asOf, "asOf");
        List<AggregateBucket> ordered = List.copyOf(
                Objects.requireNonNull(rows, "rows")).stream()
                .sorted(AGGREGATE_ROW_ORDER)
                .toList();
        long factCount = 0;
        for (AggregateBucket row : ordered) {
            requireScope(context, row.organizationId(), row.accountId());
            if (row.grain() != grain) {
                throw failure("ELMOS_MTF_ANALYTICS_EXPORT_GRAIN_MISMATCH");
            }
            factCount = Math.addExact(factCount, row.factCount());
        }
        String canonical = canonicalAggregation(
                context.organizationId(), context.accountId(), grain,
                ordered, List.of(), factCount, asOf);
        return new AggregationResult(
                context.organizationId(), context.accountId(), grain, ordered,
                factCount, asOf, sha256(canonical), ExternalEvidenceState.NOT_RUN,
                ProviderOutcome.UNKNOWN, ProductionCertification.NOT_CERTIFIED);
    }

    /** Emits canonical UTF-8 JSON with stable key and row ordering. */
    public static ExportArtifact exportJson(
            TaskFinopsPort.AuthenticatedContext context,
            AggregationResult result
    ) {
        requireExportScope(context, result);
        StringBuilder json = new StringBuilder();
        json.append('{');
        jsonField(json, "schemaVersion", SCHEMA_VERSION).append(',');
        jsonField(json, "organizationId", result.organizationId()).append(',');
        jsonField(json, "accountId", result.accountId()).append(',');
        jsonField(json, "grain", result.grain().name()).append(',');
        jsonField(json, "asOf", result.asOf().toString()).append(',');
        jsonField(json, "aggregationChecksum", result.checksum()).append(',');
        jsonField(json, "externalEvidence", result.externalEvidence().name()).append(',');
        jsonField(json, "providerOutcome", result.providerOutcome().name()).append(',');
        jsonField(json, "productionCertification",
                result.productionCertification().name()).append(',');
        List<AggregateBucket> rows = sortedRows(result);
        json.append("\"rowCount\":").append(rows.size()).append(',');
        json.append("\"rows\":[");
        for (int index = 0; index < rows.size(); index++) {
            if (index > 0) json.append(',');
            appendJsonRow(json, rows.get(index));
        }
        json.append("]}").append('\n');
        String body = json.toString();
        return artifact(result, ExportFormat.JSON, "application/json;charset=UTF-8", body);
    }

    /** Emits RFC-4180-style UTF-8 CSV and neutralizes spreadsheet formulas. */
    public static ExportArtifact exportCsv(
            TaskFinopsPort.AuthenticatedContext context,
            AggregationResult result
    ) {
        requireExportScope(context, result);
        StringBuilder csv = new StringBuilder();
        csv.append("schema_version,organization_id,account_id,task_id,run_number,")
                .append("workload_class,grain,bucket_start_utc,bucket_end_utc,currency,")
                .append("allocation_basis,cost_delta_minor,revenue_delta_minor,")
                .append("gross_delta_minor,fact_count,completeness,reconciliation_status,")
                .append("aggregation_checksum,external_evidence,provider_outcome,")
                .append("production_certification\n");
        for (AggregateBucket row : sortedRows(result)) {
            appendCsvRow(csv, List.of(
                    SCHEMA_VERSION,
                    row.organizationId(),
                    row.accountId(),
                    row.taskId(),
                    Long.toString(row.runNumber()),
                    row.workloadClass().name(),
                    row.grain().name(),
                    row.bucketStart().toString(),
                    row.bucketEnd().toString(),
                    row.currency(),
                    row.allocationBasis().name(),
                    moneyText(row.costDeltaMinor()),
                    moneyText(row.revenueDeltaMinor()),
                    moneyText(row.grossDeltaMinor()),
                    Long.toString(row.factCount()),
                    row.completeness().name(),
                    row.reconciliationStatus().name(),
                    result.checksum(),
                    result.externalEvidence().name(),
                    result.providerOutcome().name(),
                    result.productionCertification().name()), Set.of(1, 2, 3));
        }
        String body = csv.toString();
        return artifact(result, ExportFormat.CSV, "text/csv;charset=UTF-8", body);
    }

    private static void requireGenesis(JournalEvent event) {
        if (event.eventSequence() != 1) {
            throw failure("ELMOS_MTF_ANALYTICS_SEQUENCE_GAP");
        }
        if (event.taskState() != TaskFinopsPolicy.TaskState.WAITING_FOR_SLOT) {
            throw failure("ELMOS_MTF_ANALYTICS_GENESIS_STATE_INVALID");
        }
    }

    private static void requireNext(JournalEvent previous, JournalEvent next) {
        if (next.eventSequence() == previous.eventSequence()) {
            throw failure("ELMOS_MTF_ANALYTICS_DUPLICATE_SEQUENCE");
        }
        if (next.eventSequence() < previous.eventSequence()) {
            throw failure("ELMOS_MTF_ANALYTICS_OUT_OF_ORDER_SEQUENCE");
        }
        if (previous.eventSequence() == Long.MAX_VALUE) {
            throw failure("ELMOS_MTF_ANALYTICS_SEQUENCE_EXHAUSTED");
        }
        if (next.eventSequence() != previous.eventSequence() + 1L) {
            throw failure("ELMOS_MTF_ANALYTICS_SEQUENCE_GAP");
        }
        if (next.occurredAt().isBefore(previous.occurredAt())) {
            throw failure("ELMOS_MTF_ANALYTICS_TIME_REGRESSION");
        }
        if (next.progressPercent() < previous.progressPercent()) {
            throw failure("ELMOS_MTF_ANALYTICS_PROGRESS_REGRESSION");
        }
        if (previous.taskState() != next.taskState()) {
            try {
                TaskFinopsPolicy.requireTransition(previous.taskState(), next.taskState());
            } catch (IllegalStateException exception) {
                throw failure("ELMOS_MTF_ANALYTICS_ILLEGAL_TRANSITION");
            }
        }
    }

    private static void requireContiguousRuns(Set<RunKey> runKeys) {
        Map<String, Long> lastRuns = new TreeMap<>();
        for (RunKey key : runKeys) {
            long expected = lastRuns.getOrDefault(key.taskId(), 0L) + 1L;
            if (key.runNumber() != expected) {
                throw failure("ELMOS_MTF_ANALYTICS_RUN_GAP");
            }
            lastRuns.put(key.taskId(), key.runNumber());
        }
    }

    private static String canonicalJournal(List<JournalEvent> events) {
        StringBuilder canonical = new StringBuilder(SCHEMA_VERSION).append("\nrun\n");
        for (JournalEvent event : events) {
            appendCanonical(canonical, "organization_id", event.organizationId());
            appendCanonical(canonical, "account_id", event.accountId());
            appendCanonical(canonical, "task_id", event.taskId());
            appendCanonical(canonical, "run_number", Long.toString(event.runNumber()));
            appendCanonical(canonical, "event_sequence", Long.toString(event.eventSequence()));
            appendCanonical(canonical, "event_id", event.eventId());
            appendCanonical(canonical, "task_state", event.taskState().name());
            appendCanonical(canonical, "progress_percent",
                    Short.toString(event.progressPercent()));
            appendCanonical(canonical, "occurred_at", event.occurredAt().toString());
        }
        return canonical.toString();
    }

    private static String canonicalAggregation(
            String organizationId,
            String accountId,
            Grain grain,
            List<AggregateBucket> rows,
            List<FinancialFact> facts,
            long factCount,
            Instant asOf
    ) {
        StringBuilder canonical = new StringBuilder(SCHEMA_VERSION).append("\naggregation\n");
        appendCanonical(canonical, "organization_id", organizationId);
        appendCanonical(canonical, "account_id", accountId);
        appendCanonical(canonical, "grain", grain.name());
        for (FinancialFact fact : facts) {
            canonical.append("source_fact\n");
            appendCanonical(canonical, "fact_id", fact.factId());
            appendCanonical(canonical, "task_id", fact.taskId());
            appendCanonical(canonical, "run_number", Long.toString(fact.runNumber()));
            appendCanonical(canonical, "workload_class", fact.workloadClass().name());
            appendCanonical(canonical, "currency", fact.currency());
            appendCanonical(canonical, "allocation_basis", fact.allocationBasis().name());
            appendCanonical(canonical, "cost_delta_minor",
                    moneyText(fact.costDeltaMinor()));
            appendCanonical(canonical, "revenue_delta_minor",
                    moneyText(fact.revenueDeltaMinor()));
            appendCanonical(canonical, "occurred_at", fact.occurredAt().toString());
            appendCanonical(canonical, "completeness", fact.completeness().name());
            appendCanonical(canonical, "reconciliation_status",
                    fact.reconciliationStatus().name());
        }
        canonical.append("aggregate_rows\n");
        for (AggregateBucket row : rows) {
            appendCanonical(canonical, "task_id", row.taskId());
            appendCanonical(canonical, "run_number", Long.toString(row.runNumber()));
            appendCanonical(canonical, "workload_class", row.workloadClass().name());
            appendCanonical(canonical, "bucket_start", row.bucketStart().toString());
            appendCanonical(canonical, "bucket_end", row.bucketEnd().toString());
            appendCanonical(canonical, "currency", row.currency());
            appendCanonical(canonical, "allocation_basis", row.allocationBasis().name());
            appendCanonical(canonical, "cost_delta_minor", moneyText(row.costDeltaMinor()));
            appendCanonical(canonical, "revenue_delta_minor",
                    moneyText(row.revenueDeltaMinor()));
            appendCanonical(canonical, "gross_delta_minor", moneyText(row.grossDeltaMinor()));
            appendCanonical(canonical, "fact_count", Long.toString(row.factCount()));
            appendCanonical(canonical, "completeness", row.completeness().name());
            appendCanonical(canonical, "reconciliation_status",
                    row.reconciliationStatus().name());
        }
        appendCanonical(canonical, "fact_count", Long.toString(factCount));
        appendCanonical(canonical, "as_of", asOf.toString());
        appendCanonical(canonical, "external_evidence", ExternalEvidenceState.NOT_RUN.name());
        appendCanonical(canonical, "provider_outcome", ProviderOutcome.UNKNOWN.name());
        appendCanonical(canonical, "production_certification",
                ProductionCertification.NOT_CERTIFIED.name());
        return canonical.toString();
    }

    private static Instant bucketStart(Instant occurredAt, Grain grain) {
        return switch (grain) {
            case HOUR -> occurredAt.truncatedTo(ChronoUnit.HOURS);
            case DAY -> occurredAt.atZone(ZoneOffset.UTC).toLocalDate()
                    .atStartOfDay(ZoneOffset.UTC).toInstant();
        };
    }

    private static Instant bucketEnd(Instant start, Grain grain) {
        return switch (grain) {
            case HOUR -> start.plus(1, ChronoUnit.HOURS);
            case DAY -> start.plus(1, ChronoUnit.DAYS);
        };
    }

    private static DataCompleteness leastComplete(
            DataCompleteness left,
            DataCompleteness right
    ) {
        if (left == DataCompleteness.UNKNOWN || right == DataCompleteness.UNKNOWN) {
            return DataCompleteness.UNKNOWN;
        }
        if (left == DataCompleteness.PARTIAL || right == DataCompleteness.PARTIAL) {
            return DataCompleteness.PARTIAL;
        }
        return DataCompleteness.COMPLETE;
    }

    private static TaskFinopsPort.ReconciliationStatus leastReconciled(
            TaskFinopsPort.ReconciliationStatus left,
            TaskFinopsPort.ReconciliationStatus right
    ) {
        Map<TaskFinopsPort.ReconciliationStatus, Integer> rank = Map.of(
                TaskFinopsPort.ReconciliationStatus.RECONCILED, 0,
                TaskFinopsPort.ReconciliationStatus.PENDING, 1,
                TaskFinopsPort.ReconciliationStatus.REJECTED, 2,
                TaskFinopsPort.ReconciliationStatus.INCONCLUSIVE, 3,
                TaskFinopsPort.ReconciliationStatus.UNKNOWN, 4);
        return rank.get(left) >= rank.get(right) ? left : right;
    }

    private static void requireExportScope(
            TaskFinopsPort.AuthenticatedContext context,
            AggregationResult result
    ) {
        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(result, "result");
        requireScope(context, result.organizationId(), result.accountId());
        for (AggregateBucket row : result.rows()) {
            if (row.grain() != result.grain()) {
                throw failure("ELMOS_MTF_ANALYTICS_EXPORT_GRAIN_MISMATCH");
            }
            requireScope(context, row.organizationId(), row.accountId());
        }
    }

    private static List<AggregateBucket> sortedRows(AggregationResult result) {
        return result.rows().stream().sorted(AGGREGATE_ROW_ORDER).toList();
    }

    private static ExportArtifact artifact(
            AggregationResult result,
            ExportFormat format,
            String mediaType,
            String body
    ) {
        return new ExportArtifact(
                result.organizationId(), result.accountId(), format, mediaType, body,
                result.rows().size(), sha256(body), result.externalEvidence(),
                result.providerOutcome(), result.productionCertification());
    }

    private static void appendJsonRow(StringBuilder json, AggregateBucket row) {
        json.append('{');
        jsonField(json, "organizationId", row.organizationId()).append(',');
        jsonField(json, "accountId", row.accountId()).append(',');
        jsonField(json, "taskId", row.taskId()).append(',');
        json.append("\"runNumber\":").append(row.runNumber()).append(',');
        jsonField(json, "workloadClass", row.workloadClass().name()).append(',');
        jsonField(json, "grain", row.grain().name()).append(',');
        jsonField(json, "bucketStartUtc", row.bucketStart().toString()).append(',');
        jsonField(json, "bucketEndUtc", row.bucketEnd().toString()).append(',');
        jsonField(json, "currency", row.currency()).append(',');
        jsonField(json, "allocationBasis", row.allocationBasis().name()).append(',');
        jsonField(json, "costDeltaMinor", moneyText(row.costDeltaMinor())).append(',');
        jsonField(json, "revenueDeltaMinor", moneyText(row.revenueDeltaMinor())).append(',');
        jsonField(json, "grossDeltaMinor", moneyText(row.grossDeltaMinor())).append(',');
        json.append("\"factCount\":").append(row.factCount()).append(',');
        jsonField(json, "completeness", row.completeness().name()).append(',');
        jsonField(json, "reconciliationStatus", row.reconciliationStatus().name());
        json.append('}');
    }

    private static StringBuilder jsonField(StringBuilder json, String name, String value) {
        appendJsonString(json, name);
        json.append(':');
        appendJsonString(json, value);
        return json;
    }

    private static void appendJsonString(StringBuilder json, String value) {
        json.append('"');
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            switch (character) {
                case '"' -> json.append("\\\"");
                case '\\' -> json.append("\\\\");
                case '\b' -> json.append("\\b");
                case '\f' -> json.append("\\f");
                case '\n' -> json.append("\\n");
                case '\r' -> json.append("\\r");
                case '\t' -> json.append("\\t");
                default -> {
                    if (character < 0x20) {
                        json.append("\\u");
                        String hex = Integer.toHexString(character);
                        json.append("0".repeat(4 - hex.length())).append(hex);
                    } else {
                        json.append(character);
                    }
                }
            }
        }
        json.append('"');
    }

    private static void appendCsvRow(
            StringBuilder csv,
            List<String> values,
            Set<Integer> untrustedTextIndexes
    ) {
        for (int index = 0; index < values.size(); index++) {
            if (index > 0) csv.append(',');
            String safe = untrustedTextIndexes.contains(index)
                    ? neutralizeFormula(values.get(index))
                    : values.get(index);
            csv.append('"').append(safe.replace("\"", "\"\"")).append('"');
        }
        csv.append('\n');
    }

    private static String neutralizeFormula(String value) {
        if (value.isEmpty()) return value;
        int index = 0;
        while (index < value.length() && value.charAt(index) == ' ') index++;
        if (index == value.length()) return value;
        char first = value.charAt(index);
        if (first == '=' || first == '+' || first == '-' || first == '@'
                || first == '\t' || first == '\r' || first == '\n') {
            return "'" + value;
        }
        return value;
    }

    private static void requireScope(
            TaskFinopsPort.AuthenticatedContext context,
            String organizationId,
            String accountId
    ) {
        if (!context.organizationId().equals(organizationId)
                || !context.accountId().equals(accountId)) {
            throw failure("ELMOS_MTF_ANALYTICS_SCOPE_MISMATCH");
        }
    }

    private static void requireSafetyBoundary(
            ExternalEvidenceState externalEvidence,
            ProviderOutcome providerOutcome,
            ProductionCertification productionCertification
    ) {
        if (externalEvidence != ExternalEvidenceState.NOT_RUN
                || providerOutcome != ProviderOutcome.UNKNOWN
                || productionCertification != ProductionCertification.NOT_CERTIFIED) {
            throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_SAFETY_BOUNDARY_INVALID");
        }
    }

    private static AnalyticsException failure(String code) {
        return new AnalyticsException(code);
    }

    private static BigDecimal exactMoney(BigDecimal value, String field) {
        long integerDigits = value == null
                ? 0L
                : Math.max(0L, (long) value.precision() - value.scale());
        int maxIntegerDigits = TaskFinopsPort.DATABASE_DECIMAL_MAX_PRECISION
                - TaskFinopsPolicy.MONEY_SCALE;
        if (value == null || value.precision() > TaskFinopsPort.DATABASE_DECIMAL_MAX_PRECISION
                || integerDigits > maxIntegerDigits
                || value.scale() > TaskFinopsPolicy.MONEY_SCALE) {
            throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_" + field + "_INVALID");
        }
        try {
            return value.setScale(TaskFinopsPolicy.MONEY_SCALE, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException exception) {
            throw new IllegalArgumentException(
                    "ELMOS_MTF_ANALYTICS_" + field + "_INEXACT", exception);
        }
    }

    private static BigDecimal zeroMoney() {
        return BigDecimal.ZERO.setScale(TaskFinopsPolicy.MONEY_SCALE);
    }

    private static String moneyText(BigDecimal value) {
        return value.setScale(TaskFinopsPolicy.MONEY_SCALE, RoundingMode.UNNECESSARY)
                .toPlainString();
    }

    private static String currency(String value) {
        String candidate = value == null ? "" : value.trim().toUpperCase(Locale.ROOT);
        if (!candidate.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_CURRENCY_INVALID");
        }
        return candidate;
    }

    private static String identifier(String value, String field, int maxLength) {
        if (value == null || value.isBlank() || value.length() > maxLength
                || !value.equals(value.trim())) {
            throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_" + field + "_INVALID");
        }
        for (int index = 0; index < value.length(); index++) {
            if (Character.isISOControl(value.charAt(index))) {
                throw new IllegalArgumentException(
                        "ELMOS_MTF_ANALYTICS_" + field + "_INVALID");
            }
        }
        return value;
    }

    private static String digestValue(String value, String field) {
        String candidate = value == null ? "" : value.toLowerCase(Locale.ROOT);
        if (!candidate.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("ELMOS_MTF_ANALYTICS_" + field + "_INVALID");
        }
        return candidate;
    }

    private static void appendCanonical(StringBuilder output, String name, String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        output.append(name).append(':').append(bytes.length).append(':').append(value).append('\n');
    }

    private static String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("ELMOS_MTF_ANALYTICS_SHA256_UNAVAILABLE", exception);
        }
    }
}
